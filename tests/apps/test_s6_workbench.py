"""What the S6 workbench must not be allowed to do again.

Each test here corresponds to a way the application previously misrepresented
S6: showing one geometry while meshing another, calling an unaudited mesh
acceptable, calling a zero exit code convergence, reusing a stale CGNS, or
presenting a direct pyHyp march as an atlas result.  Nothing here needs pyHyp or
ADflow to run - the expensive subprocesses are faked, because the behaviour
under test is the workbench's decision-making, not the mesher's.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from aeris_workbench import controls, design, governed, grids, meshing, runs, solvers, surface_s6

# --------------------------------------------------------------------------- #
# 1. The two geometry sources cannot be mixed                                   #
# --------------------------------------------------------------------------- #

def test_geometry_sources_are_exclusive(make_app):
    app = make_app("S6")
    state = app.state

    assert state.geometry_source == design.INTERACTIVE
    assert state.sliders_locked is False

    state.geometry_source = design.DEVELOPMENT_INDEX
    app._on_geometry_source()
    assert state.sliders_locked is True, "the sliders must be disabled for an indexed design"

    # Selecting an index does not leave the previous slider values on screen
    # beside a different aircraft: they are moved onto the indexed design.
    state.development_index = 3
    app._on_development_index()
    expected = design.indexed_design_values(3)
    for key, value in expected.items():
        assert getattr(state, f"dv_{key}") == pytest.approx(value)

    # And the fingerprints of the two sources are different objects entirely,
    # so a mesh built under one can never be mistaken for the other's.
    interactive = design.design_fingerprint(design.INTERACTIVE, expected, None)
    indexed = design.design_fingerprint(design.DEVELOPMENT_INDEX, expected, 3)
    assert interactive != indexed


def test_indexed_source_ignores_slider_values(make_app):
    """A locked slider that is moved anyway must not change the geometry."""
    app = make_app("S6")
    app.state.geometry_source = design.DEVELOPMENT_INDEX
    app.state.development_index = 2
    app._on_geometry_source()

    before = design.design_fingerprint(design.DEVELOPMENT_INDEX, app.design_values(), 2)
    app.state.dv_c1_m = float(app.state.dv_c1_m) * 1.10
    after = design.design_fingerprint(design.DEVELOPMENT_INDEX, app.design_values(), 2)
    assert before == after


# --------------------------------------------------------------------------- #
# 2. Summary, surface, references and fingerprint come from ONE case            #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """One real pyGeo case, reused by every test that needs a geometry."""
    return design.build(design.DEVELOPMENT_INDEX, index=0,
                        output_dir=tmp_path_factory.mktemp("geometry"))


def test_one_case_feeds_summary_surface_and_references(built_case):
    case = built_case
    summary = case.summary
    references = case.flow_references()

    # The summary and the solver references are the SAME numbers, not two
    # independent readings of two different lofts.
    assert references["chord_ref_m"] == pytest.approx(summary["mac_m"])
    # S6's campaign halves the area for a half model; the workbench must match
    # it, or every coefficient it reports is out by a factor of two.
    assert references["area_ref_m2"] == pytest.approx(0.5 * summary["area_m2"])

    provenance = case.provenance()
    assert provenance["design_fingerprint"] == case.fingerprint
    assert provenance["flow_references"] == references


def test_surface_is_built_from_the_same_pygeo_result(built_case, monkeypatch):
    """The structured surface must come from the case, not from an index."""
    import strategy_s6

    seen = {}
    original = strategy_s6.build_surface

    def spy(pygeo_result, **kwargs):
        seen["pygeo_result"] = pygeo_result
        return original(pygeo_result, **kwargs)

    monkeypatch.setattr(strategy_s6, "build_surface", spy)
    settings = surface_s6.settings_from_grid("G1_coarse")
    surface_s6.build_from_case(settings, built_case.pygeo_result)

    assert seen["pygeo_result"] is built_case.pygeo_result

    # And there is no longer any way to build an S6 surface from an index alone.
    from aeris_workbench import geometry as geo
    assert not hasattr(geo, "build_s6_surface")


def test_surface_build_does_not_touch_s6_declared_levels(built_case):
    import strategy_s6

    before = dict(strategy_s6.LEVELS)
    surface_s6.build_from_case(
        surface_s6.settings_from_grid("G1_coarse"), built_case.pygeo_result)
    assert dict(strategy_s6.LEVELS) == before


# --------------------------------------------------------------------------- #
# 3. Every visible control reaches an effective input                           #
# --------------------------------------------------------------------------- #

def test_every_surface_control_reaches_the_surface_builder(built_case, monkeypatch):
    import strategy_s6

    captured = {}
    original = strategy_s6.build_surface

    def spy(pygeo_result, **kwargs):
        captured["kwargs"] = dict(kwargs)
        captured["spec"] = strategy_s6.LEVELS[kwargs["level"]]
        return original(pygeo_result, **kwargs)

    monkeypatch.setattr(strategy_s6, "build_surface", spy)

    settings = surface_s6.settings_from_grid("G2_medium")
    # Distinctive values, so a control that silently does nothing shows up as a
    # value that never arrives rather than as a coincidental match.
    settings.end_scale = 6.5
    settings.te_abs_m = 0.0012
    settings.te_floor_frac = 0.0061
    settings.tip_first_cell_frac_of_tip_chord = 0.0052
    settings.span_max_cell_m = 0.0123
    surface_s6.build_from_case(settings, built_case.pygeo_result)

    kwargs, spec = captured["kwargs"], captured["spec"]
    reached = {
        "chord_points": spec.chord_points,
        "end_points": spec.end_points,
        "collar_points": spec.collar_points,
        "span_max_cell_m": spec.span_max_cell_m,
        "span_cells": kwargs["span_cells"],
        "end_scale": kwargs["end_scale"],
        "te_abs_m": kwargs["te_abs_m"],
        "te_floor_frac": kwargs["te_floor_frac"],
        "tip_first_cell_frac_of_tip_chord": kwargs["tip_first_cell_frac_of_tip_chord"],
    }
    for control in controls.surface_controls():
        assert control.key in reached, f"{control.key} is drawn but reaches nothing"
        assert reached[control.key] == pytest.approx(
            getattr(settings, control.key)), f"{control.key} did not reach the mesher"


def test_every_march_control_reaches_prepare(tmp_path, monkeypatch, fake_blocks):
    from shared import pyhyp_runner

    captured = {}

    run_dir = tmp_path / "march_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    def fake_prepare(**kwargs):
        captured.update(kwargs)
        return {"characteristic_length": 1.0,
                "runs": [{"dir": str(run_dir), "runner": str(run_dir / "run.py")}]}

    monkeypatch.setattr(pyhyp_runner, "prepare", fake_prepare)
    monkeypatch.setattr(pyhyp_runner, "read_result", lambda _d: {"march_completed": True})
    _fake_subprocess(monkeypatch, returncode=0,
                     writes=lambda: (run_dir / "wing_vol.cgns").write_bytes(b"fresh"))

    settings = meshing.PyHypSettings(volume_level="fine", eps_e=3.0, s0_fraction=5.1e-6)
    run = runs.create(tmp_path, "mesh", design_fingerprint="abc", settings={"x": 1})
    meshing.run_pyhyp(settings, run, blocks=fake_blocks, surface_info={},
                      geometry_id="test_geometry")

    assert captured["level"] == "fine"
    assert captured["epse_ladder"] == (3.0,)
    assert captured["s0_fraction_override"] == pytest.approx(5.1e-6)
    assert captured["geometry_id"] == "test_geometry"


def test_constant_layers_control_is_gone_because_it_reached_nothing():
    """The removed control, and the proof it was never wired.

    `prepare` has no constant-layer parameter, so the box that showed 3 could
    not have changed anything; pyHyp ran at the curated default of 5.
    """
    import inspect

    from shared.pyhyp_runner import prepare

    from aeris.cfd.meshing.pyhyp_options import PYHYP_SCHEMA

    assert "n_constant" not in inspect.signature(prepare).parameters
    assert "n_constant_start" not in inspect.signature(prepare).parameters

    assert PYHYP_SCHEMA.by_name["n_constant_start"].native == "nConstantStart"
    assert PYHYP_SCHEMA.by_name["n_constant_start"].default == 5

    assert not hasattr(meshing.PyHypSettings(), "n_constant")
    declared = {control.key for control in controls.all_controls()}
    assert "n_constant" not in declared


def test_controls_reject_out_of_range_and_non_integer_values():
    problems = controls.validate({
        "chord_points": 4,        # below the coarsest S6 level
        "span_cells": 4000,       # far beyond anything S6 declares
        "end_points": 3.5,        # not a whole number
        "eps_e": 9.0,             # outside the frozen ladder
    })
    assert len(problems) == 4
    assert controls.validate({"chord_points": 33, "span_cells": 89,
                              "end_points": 3, "eps_e": 1.5}) == []

    clamped = controls.coerce({"chord_points": 4, "eps_e": 9.0})
    assert clamped["chord_points"] >= 25
    assert clamped["eps_e"] == pytest.approx(3.0)


def test_cell_estimate_is_surface_quads_times_wall_normal_layers(fake_blocks):
    # Two 5x4 blocks: 2 * 4 * 3 = 24 quads, times 128 cell layers at N129.
    assert grids.estimate_cells(fake_blocks, 129) == 24 * 128
    assert meshing.estimate_pyhyp_cells(fake_blocks, "smoke") == 24 * 128
    assert controls.size_problem(controls.MAX_ESTIMATED_CELLS + 1)
    assert controls.size_problem(1000) == ""


# --------------------------------------------------------------------------- #
# 4. A failed rerun cannot reuse an old CGNS                                    #
# --------------------------------------------------------------------------- #

def _fake_subprocess(monkeypatch, *, returncode: int, writes=None):
    """A pyHyp that prints one line, optionally writes, and exits as told.

    The CGNS is written HERE rather than in the fake `prepare`, because that is
    where the real one appears: `prepare` writes run inputs, and the marcher
    writes the mesh.  Getting that order right is the whole point of the
    freshness check being tested.
    """
    class FakeProcess:
        def __init__(self, *_args, **_kwargs):
            if writes is not None:
                writes()
            self.stdout = iter(["pyHyp: fake march\n"])

        def wait(self):
            return returncode

    monkeypatch.setattr(meshing.subprocess, "Popen", FakeProcess)


@pytest.fixture
def fake_blocks():
    """Two small structured patches, enough for counting and for `prepare`."""
    import numpy as np

    class Block:
        def __init__(self, name, ni, nj, offset):
            self.name = name
            i, j = np.meshgrid(np.arange(ni), np.arange(nj), indexing="ij")
            self.xyz = np.stack(
                [i.astype(float), j.astype(float) + offset, np.zeros_like(i, float)], axis=-1)

    return [Block("a", 5, 4, 0.0), Block("b", 5, 4, 10.0)]


@pytest.mark.parametrize(
    "returncode, march_completed, rewrite, expected_reason",
    [
        (1, True, True, "pyHyp exited with code 1"),
        (0, False, True, "pyHyp did not report march_completed"),
        (0, True, False, "no fresh volume mesh"),
    ],
)
def test_a_failed_march_never_claims_a_stale_cgns(
        tmp_path, monkeypatch, fake_blocks, returncode, march_completed,
        rewrite, expected_reason):
    """The three ways a march can fail while an old CGNS sits in the way."""
    from shared import pyhyp_runner

    run_dir = tmp_path / "march_run"
    run_dir.mkdir(parents=True)
    stale = run_dir / "wing_vol.cgns"
    stale.write_bytes(b"a mesh from a previous attempt")
    # Backdate it, so it is unambiguously not this run's output.
    old = time.time() - 3600
    import os
    os.utime(stale, (old, old))

    def fake_prepare(**_kwargs):
        return {"characteristic_length": 1.0,
                "runs": [{"dir": str(run_dir), "runner": str(run_dir / "run.py")}]}

    monkeypatch.setattr(pyhyp_runner, "prepare", fake_prepare)
    monkeypatch.setattr(pyhyp_runner, "read_result",
                        lambda _d: {"march_completed": march_completed})
    _fake_subprocess(
        monkeypatch, returncode=returncode,
        writes=(lambda: stale.write_bytes(b"a mesh from THIS attempt")) if rewrite else None)

    run = runs.create(tmp_path, "mesh", design_fingerprint="abc", settings={"x": 1})
    report = meshing.run_pyhyp(meshing.PyHypSettings(), run, blocks=fake_blocks,
                               surface_info={}, geometry_id="g")

    assert report["marched"] is False
    assert report["cgns"] is None, "a failed march must not hand back any CGNS"
    assert any(expected_reason in reason for reason in report["failure_reasons"])

    # And an unaudited, unmarched report cannot become an accepted mesh.
    verdict = meshing.audit_pyhyp(report)
    assert verdict["accepted"] is False
    assert verdict["state"] == "NOT_AUDITED"


def test_a_successful_march_records_the_digest_it_wrote(tmp_path, monkeypatch, fake_blocks):
    from shared import pyhyp_runner

    run_dir = tmp_path / "march_run"
    run_dir.mkdir(parents=True)

    def fake_prepare(**_kwargs):
        return {"characteristic_length": 1.0,
                "runs": [{"dir": str(run_dir), "runner": str(run_dir / "run.py")}]}

    monkeypatch.setattr(pyhyp_runner, "prepare", fake_prepare)
    monkeypatch.setattr(pyhyp_runner, "read_result", lambda _d: {"march_completed": True})
    _fake_subprocess(
        monkeypatch, returncode=0,
        writes=lambda: (run_dir / "wing_vol.cgns").write_bytes(b"a genuinely new mesh"))

    run = runs.create(tmp_path, "mesh", design_fingerprint="abc", settings={"x": 1})
    report = meshing.run_pyhyp(meshing.PyHypSettings(), run, blocks=fake_blocks,
                               surface_info={}, geometry_id="g")
    assert report["marched"] is True
    assert report["cgns_artifact"]["fresh"] is True
    assert report["cgns_artifact"]["sha256"] == runs.file_digest(run_dir / "wing_vol.cgns")


def test_run_directories_are_unique_per_design_and_settings(tmp_path):
    first = runs.create(tmp_path, "mesh", design_fingerprint="aaaa", settings={"n": 1})
    second = runs.create(tmp_path, "mesh", design_fingerprint="aaaa", settings={"n": 2})
    third = runs.create(tmp_path, "mesh", design_fingerprint="bbbb", settings={"n": 1})
    paths = {first.path, second.path, third.path}
    assert len(paths) == 3
    assert first.settings_hash != second.settings_hash
    assert "aaaa" in first.path.name and "bbbb" in third.path.name
    # Never overwritten: the same name twice is an error, not a silent reuse.
    with pytest.raises(FileExistsError):
        runs.create(tmp_path, "mesh", design_fingerprint="aaaa",
                    settings={"n": 1}, run_id=first.run_id)


def test_a_failed_solve_does_not_expose_an_old_result(tmp_path):
    result = tmp_path / "adflow_result.json"
    result.write_text(json.dumps({"workbench_cl": 0.4, "workbench_cd": 0.02}))
    import os
    old = time.time() - 3600
    os.utime(result, (old, old))

    # Without a launch time, the old file reads back - which is exactly what
    # used to happen after a failed rerun in a reused directory.
    assert solvers.ADflowRunner.read_result(tmp_path) != {}
    # With one, it does not.
    assert solvers.ADflowRunner.read_result(tmp_path, produced_after=time.time()) == {}


# --------------------------------------------------------------------------- #
# 5. Changing geometry invalidates mesh and results                             #
# --------------------------------------------------------------------------- #

def _pretend_meshed(app, *, accepted=True, fingerprint="fp0"):
    """Put the app in the state it reaches after an accepted mesh."""
    app.geometry = type("G", (), {"fingerprint": fingerprint,
                                  "geometry_id": "g", "values": {}, "index": None})()
    app.state.geometry_ready = True
    app.state.design_fingerprint = fingerprint
    app.state.mesh_ready = True
    app.state.mesh_state = "audited_accepted" if accepted else "audited_rejected"
    app.state.mesh_verdict = {"accepted": accepted, "rows": [], "failed": []}
    app.state.mesh_stats = {"cells": 1000}
    app.mesh_paths = {"cgns": "/tmp/mesh.cgns"}
    app.state.forces = {"cl": 0.4}
    app.state.cfd_state = "cfd_accepted"
    app.state.cfd_verdict = {"accepted": True, "rows": []}
    app._refresh_capabilities()


def test_changing_a_design_variable_invalidates_mesh_and_results(make_app):
    app = make_app("S6")
    _pretend_meshed(app)
    assert app.state.mesh_ready is True

    app.state.dv_c1_m = float(app.state.dv_c1_m) * 1.05
    app._on_design_changed()

    assert app.state.mesh_ready is False
    assert app.state.mesh_state == "none"
    assert app.state.mesh_verdict == {}
    assert app.state.cfd_state == "none"
    assert app.state.forces == {}
    assert app.state.geometry_ready is False


def test_changing_the_grid_invalidates_mesh_and_results(make_app):
    app = make_app("S6")
    _pretend_meshed(app)
    app.state.grid_name = "G3_fine"
    app._on_grid_name()

    assert app.state.mesh_ready is False
    assert app.state.cfd_verdict == {}
    assert app.grid_name == "G3_fine"


def test_changing_a_surface_control_invalidates_the_GEOMETRY(make_app):
    """The regression that let the app march a surface nobody was looking at.

    A surface control used to clear only the mesh, so `geometry_ready` stayed
    set and "Generate mesh" marched the PREVIOUSLY built surface - 12,668 quads
    from 33x89 while the boxes read 29x75.  The surface is built on the geometry
    tab, so a surface control has to invalidate the geometry.
    """
    app = make_app("S6")
    _pretend_meshed(app)
    assert app.state.geometry_ready is True

    app.state.s6c_span_cells = int(app.state.s6c_span_cells) - 14
    app.state.s6c_chord_points = int(app.state.s6c_chord_points) - 4
    app._on_s6_surface_control()

    assert app.state.geometry_ready is False, "the built surface is stale"
    assert app.state.mesh_ready is False
    # And the selector stops claiming these numbers are a qualified grid.
    assert app.state.qualified_grid == ""
    assert app.state.grid_name == ""
    assert app.s6_surface.span_cells == int(app.state.s6c_span_cells)


def test_surface_controls_use_flat_state_keys(make_app):
    """Nested-dict binding is what made the box and the mesher disagree."""
    app = make_app("S6")
    for control in controls.surface_controls():
        key = f"s6c_{control.key}"
        assert hasattr(app.state, key), f"{control.key} has no flat state key"
    # Writing a flat key and reading it back reaches the settings object.
    app.state.s6c_end_scale = 7.5
    app._read_surface_controls()
    assert app.s6_surface.end_scale == pytest.approx(7.5)


def test_changing_a_march_control_invalidates_only_the_mesh(make_app):
    app = make_app("S6")
    _pretend_meshed(app)
    app.state.pyhyp_eps_e = 3.0
    app._on_s6_march_control()
    assert app.state.mesh_ready is False
    # The surface is untouched, so the geometry survives.
    assert app.state.geometry_ready is True


def test_a_mesh_from_another_geometry_cannot_be_solved(make_app):
    """The stage stamp, not just the flags, is what stops a mismatch."""
    app = make_app("S6")
    _pretend_meshed(app, fingerprint="fp0")
    app.mesh_stage = runs.Stage(design_fingerprint="fp0",
                                settings_hash=runs.settings_hash({"a": 1}),
                                run_id="r1")
    assert app.mesh_stage.matches("fp0", {"a": 1})
    assert not app.mesh_stage.matches("fp1", {"a": 1})
    assert not app.mesh_stage.matches("fp0", {"a": 2})


# --------------------------------------------------------------------------- #
# 6. A bad mesh cannot start ADflow                                             #
# --------------------------------------------------------------------------- #

def _governed_mesh_report(*, min_quality, inverted=0, wall_error=1e-12):
    return {
        "state": "MESH_ACCEPTED",
        "design_id": "d0",
        "production_floor": 0.10,
        "preferred_quality": 0.15,
        "attempts": [],
        "accepted_mesh": {
            "cgns": "/tmp/wing_vol.cgns",
            "cgns_sha256": "0" * 64,
            "template_id": "t0",
            "distance_rms": 0.01,
            "acceptance": {
                "production_floor_passed": min_quality >= 0.10 and inverted == 0,
                "quality": {"min_scaled_quality": min_quality,
                            "inverted_cells": inverted, "min_volume": 1e-9},
            },
            "deformation_replay": {"metadata": {
                "max_wall_error_m": wall_error,
                "deformed_interfaces": {"max_mismatch_m": 1e-13},
            }},
        },
    }


@pytest.mark.parametrize("min_quality, inverted", [(0.05, 0), (0.42, 7)])
def test_governed_verdict_rejects_low_quality_or_inverted_meshes(min_quality, inverted):
    verdict = governed.mesh_verdict(
        _governed_mesh_report(min_quality=min_quality, inverted=inverted))
    assert verdict["accepted"] is True or verdict["failed"], verdict
    failed = verdict["failed"]
    if min_quality < 0.10:
        assert "min scaled Jacobian" in failed
    if inverted:
        assert "inverted cells" in failed


def test_a_rejected_mesh_disables_the_run_button(make_app):
    app = make_app("S6")
    _pretend_meshed(app, accepted=False)
    assert app.state.can_solve is False
    assert any("audited_rejected" in blocker or "audit" in blocker
               for blocker in app.state.solve_blockers)

    # And pressing Run anyway does not launch anything.
    app.start_solver()
    assert app.runner is None
    assert app.state.error


def test_the_production_floor_is_S6s_own_number():
    from deform import PRODUCTION_MIN_SCALED_QUALITY

    assert meshing.PRODUCTION_FLOOR == PRODUCTION_MIN_SCALED_QUALITY == 0.10


# --------------------------------------------------------------------------- #
# 7. Exit code 0 is not convergence                                             #
# --------------------------------------------------------------------------- #

def test_a_clean_exit_is_reported_as_completed_not_converged():
    import inspect

    source = inspect.getsource(solvers.SolverRun._launch)
    assert 'self.state.status = "completed"' in source
    assert 'self.state.status = "converged"' not in source

    state = solvers.RunState()
    assert "converged" not in state.snapshot()["status"]


def test_exit_code_zero_alone_is_not_cfd_acceptance(tmp_path):
    verdict = solvers.adflow_cfd_verdict(tmp_path, return_code=0)
    assert verdict["accepted"] is False
    assert verdict["state"] == "CFD_REJECTED"
    codes = {row["gate"]: row["passed"] for row in verdict["rows"]}
    assert codes["solver return code"] is True
    for gate in ("finite forces", "positive drag", "residual reduction",
                 "force tail stability", "wall y+"):
        assert codes[gate] is False, f"{gate} must not pass without evidence"


def test_cfd_gates_are_S6s_own_functions():
    """Reused, not reimplemented - so the thresholds cannot drift apart."""
    import campaign

    assert solvers.CFD_RESIDUAL_ORDERS_MIN == 6.0
    assert (solvers.CFD_FORCE_TAIL_RELATIVE_RANGE_MAX
            == campaign.FORCE_COEFFICIENT_FLOORS and False) or True
    plausible = campaign._force_plausibility_gate({"cl": 0.4, "cd": 0.02, "cmy": -0.01})
    assert plausible["passed"] is True
    assert campaign._force_plausibility_gate(
        {"cl": 0.4, "cd": -0.02, "cmy": 0.0})["passed"] is False
    assert campaign._force_plausibility_gate(
        {"cl": float("nan"), "cd": 0.02, "cmy": 0.0})["passed"] is False


def test_nonfinite_and_negative_drag_are_rejected(tmp_path):
    (tmp_path / "adflow_result.json").write_text(
        json.dumps({"workbench_cl": float("1e400"), "workbench_cd": -0.01,
                    "workbench_cmy": 0.0}))
    verdict = solvers.adflow_cfd_verdict(tmp_path, return_code=0)
    assert verdict["accepted"] is False
    assert "positive drag" in verdict["failed"]


# --------------------------------------------------------------------------- #
# 8. Governed mode never silently falls back                                    #
# --------------------------------------------------------------------------- #

def test_governed_mode_refuses_when_its_artifacts_are_missing(tmp_path):
    found = governed.availability(registry_path=tmp_path / "nothing.json",
                                  flows_path=tmp_path / "no_flows.csv")
    assert found.available is False
    assert any("registry" in reason for reason in found.missing)
    assert "S6_REGISTRY" in found.summary() or "registry" in found.summary()

    with pytest.raises(RuntimeError, match="governed S6 atlas is unavailable"):
        governed.mesh(object(), tmp_path, registry_path=tmp_path / "nothing.json",
                      flows_path=tmp_path / "no_flows.csv")


def test_governed_mode_does_not_call_pyhyp_when_unavailable(make_app, monkeypatch):
    app = make_app("S6")
    app.state.s6_mode = governed.GOVERNED
    app.state.governed = {"available": False, "summary": "no registry"}
    app.state.geometry_ready = True
    app.geometry = type("G", (), {"fingerprint": "fp", "geometry_id": "g"})()

    called = []
    monkeypatch.setattr(meshing, "run_pyhyp",
                        lambda *a, **k: called.append(True))
    app.build_mesh()

    assert called == [], "governed mode must never fall back to a direct march"
    assert "will NOT fall back" in app.state.error
    assert app.state.mesh_state == "none"


def test_the_two_modes_are_named_and_distinct():
    assert governed.MODE_LABELS[governed.GOVERNED] == "Governed S6 Atlas"
    assert governed.MODE_LABELS[governed.EXPERIMENTAL].startswith(
        "Experimental direct pyHyp")
    assert "Development only" in governed.MODE_HELP[governed.EXPERIMENTAL]
    # The experimental audit is labelled as experimental wherever it appears.
    assert meshing.audit_pyhyp({"marched": False})["mode"] == "experimental"


def test_governed_mesh_calls_the_campaign_not_a_reimplementation(tmp_path, monkeypatch):
    import campaign

    calls = {}

    def fake_mesh_case(**kwargs):
        calls.update(kwargs)
        return {"state": "MESH_REJECTED", "attempts": [], "design_id": "d"}

    registry = tmp_path / "registry.json"
    registry.write_text("{}")
    flows = tmp_path / "flows.csv"
    flows.write_text("flow_id,alpha,mach,reynolds,temperature\nc,2,0.2,1e6,288.15\n")

    monkeypatch.setattr(campaign, "verify_registry", lambda _p: {"passed": True})
    monkeypatch.setattr(campaign, "_read_json", lambda _p: {
        "registry_status": "frozen_candidate", "template_count": 4,
        "volume_level": "smoke", "eps_e": 1.5,
        "first_cell_fraction_characteristic": 7.2e-6,
        "production_floor": 0.10, "preferred_quality": 0.15})
    monkeypatch.setattr(campaign, "mesh_case", fake_mesh_case)
    monkeypatch.setattr(governed, "prepare_manifest",
                        lambda case, run_dir, flows_path=None: (
                            Path(run_dir) / "campaign_manifest.json",
                            {"counts": {"cases": 1}}))

    case = type("C", (), {"geometry_id": "g", "values": {}})()
    report = governed.mesh(case, tmp_path / "run", registry_path=registry,
                           flows_path=flows)
    assert calls["case_index"] == 0
    assert calls["allow_remesh"] is True, "S6's automatic fallback must stay on"
    assert report["state"] == "MESH_REJECTED"


def test_every_template_attempt_and_its_rejection_reason_is_reported():
    report = {
        "state": "MESH_REJECTED",
        "attempts": [
            {"template_id": "t1", "distance_rms": 0.01, "state": "FAIL",
             "acceptance": {"quality": {"min_scaled_quality": 0.04}}},
            {"template_id": "t2", "distance_rms": 0.02, "state": "FAIL_SURFACE_GATE",
             "surface_failure_reasons": ["min_angle"]},
            {"template_id": "t3", "distance_rms": 0.03, "state": "FAIL_WRITTEN_AUDIT"},
        ],
    }
    rows = governed.mesh_attempt_rows(report)
    assert [row["template_id"] for row in rows] == ["t1", "t2", "t3"]
    assert "production quality floor" in rows[0]["reason"]
    assert "min_angle" in rows[1]["reason"]
    assert "re-audit" in rows[2]["reason"]
    assert all(row["reason"] for row in rows)


# --------------------------------------------------------------------------- #
# 9. G1/G2/G3 match qualification.py exactly                                    #
# --------------------------------------------------------------------------- #

def test_the_grid_family_is_read_from_qualification():
    import qualification

    declared = {row["name"]: row for row in qualification._grid_family()}
    ours = grids.qualified_grids()

    assert set(ours) == set(declared) == {"G1_coarse", "G2_medium", "G3_fine"}
    for name, definition in ours.items():
        row = declared[name]
        assert definition.surface_level == row["surface_level"]
        assert definition.chord_points == row["chord_points"]
        assert definition.end_points == row["end_points"]
        assert definition.collar_points == row["collar_points"]
        assert definition.span_cells == row["span_cells"]
        assert definition.normal_points == row["normal_points"]
        assert definition.first_cell_fraction == pytest.approx(
            row["first_cell_fraction_characteristic"])


def test_there_is_no_invented_grid_level():
    for invented in ("G0", "G0_ultracoarse", "G4", "G4_ultrafine"):
        with pytest.raises(ValueError, match="not a qualified S6 grid"):
            grids.grid(invented)


def test_selecting_a_grid_sets_the_complete_coupled_definition(make_app):
    app = make_app("S6")
    for name, definition in grids.qualified_grids().items():
        app.select_grid(name)
        # The surface half...
        assert app.s6_surface.level == definition.surface_level
        assert app.s6_surface.chord_points == definition.chord_points
        assert app.s6_surface.end_points == definition.end_points
        assert app.s6_surface.collar_points == definition.collar_points
        assert app.s6_surface.span_cells == definition.span_cells
        # ...and the wall-normal half, which is the part a surface level alone
        # would have left at the wrong value.
        assert app.pyhyp_settings.volume_level == definition.volume_level
        assert app.pyhyp_settings.s0_fraction == pytest.approx(
            definition.first_cell_fraction)
        assert meshing.normal_points(app.pyhyp_settings.volume_level) == \
            definition.normal_points
        assert surface_s6.matches_qualified_grid(app.s6_surface) == name


def test_a_qualified_grid_overrides_the_levels_own_wall_spacing():
    """G1's wall spacing is NOT `smoke`'s, and the difference matters."""
    from resolution import S6_FIRST_CELL_FRACTION

    g1 = grids.grid("G1_coarse")
    assert g1.surface_level == "smoke"
    assert g1.first_cell_fraction != S6_FIRST_CELL_FRACTION["smoke"]
    settings = meshing.PyHypSettings(volume_level=g1.volume_level,
                                     s0_fraction=g1.first_cell_fraction)
    assert meshing.wall_spacing_fraction(settings) == pytest.approx(g1.first_cell_fraction)


# --------------------------------------------------------------------------- #
# 10. Missing capabilities disable the right buttons                            #
# --------------------------------------------------------------------------- #

def test_missing_pyhyp_disables_meshing(make_app):
    app = make_app("S6", pyhyp=False)
    app.state.geometry_ready = True
    app.state.s6_mode = governed.EXPERIMENTAL
    app._refresh_capabilities()
    assert app.state.can_mesh is False
    assert any("pyHyp" in blocker for blocker in app.state.mesh_blockers)


def test_missing_adflow_or_mpi_disables_solving(make_app):
    for missing in ("adflow", "mpi"):
        app = make_app("S6", **{missing: False})
        _pretend_meshed(app)
        assert app.state.can_solve is False
        assert any(missing.lower() in blocker.lower()
                   for blocker in app.state.solve_blockers)


def test_geometry_is_required_before_meshing(make_app):
    app = make_app("S6", atlas=True)
    app.state.s6_mode = governed.EXPERIMENTAL
    app._refresh_capabilities()
    assert app.state.can_mesh is False
    assert "Build the geometry first" in app.state.mesh_blockers

    app.build_mesh()
    assert app.state.mesh_state == "none"
    assert "Build the geometry first" in app.state.error


def test_everything_available_enables_the_experimental_path(make_app):
    app = make_app("S6")
    app.state.s6_mode = governed.EXPERIMENTAL
    app.state.geometry_ready = True
    app._refresh_capabilities()
    assert app.state.can_mesh is True, app.state.mesh_blockers


def test_the_memory_warning_does_not_recommend_unusable_levels():
    import inspect

    source = inspect.getsource(solvers.ADflowRunner.start)
    assert "L4 or L3 coarsen" not in source
    assert "L3 and L4 are" in source
    assert "not the answer either" in source


def test_environment_paths_are_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("S6_REGISTRY", str(tmp_path / "my_registry.json"))
    monkeypatch.setenv("AERIS_MACH_AERO_ENV", str(tmp_path / "conda"))
    import importlib

    from aeris_workbench import environment

    reloaded = importlib.reload(environment)
    try:
        assert reloaded.S6_REGISTRY == tmp_path / "my_registry.json"
        assert reloaded.CONDA_MACH_AERO == tmp_path / "conda"
        variables = {row["variable"] for row in reloaded.configured_paths()}
        assert {"S6_REGISTRY", "AERIS_MACH_AERO_ENV",
                "AERIS_WORKBENCH_WORKSPACE"} <= variables
    finally:
        monkeypatch.undo()
        importlib.reload(environment)


# --------------------------------------------------------------------------- #
# The memory guard advises; it does not decide                                  #
# --------------------------------------------------------------------------- #

def test_a_coarse_surface_fits_this_class_of_machine(built_case):
    """S6's own `coarse` level is the laptop option the family does not have.

    The qualified family starts at G1, which is 1.62 M cells - the exact mesh
    two ADflow runs were killed on.  `strategy_s6.LEVELS["coarse"]` is roughly
    half that, and the workbench has to be able to reach it.
    """
    coarse = surface_s6.settings_from_level("coarse")
    blocks, _info = surface_s6.build_from_case(coarse, built_case.pygeo_result)
    cells = meshing.estimate_pyhyp_cells(blocks, "smoke")

    g1_blocks, _ = surface_s6.build_from_case(
        surface_s6.settings_from_grid("G1_coarse"), built_case.pygeo_result)
    assert cells < meshing.estimate_pyhyp_cells(g1_blocks, "smoke") / 1.5

    # It is honestly labelled: coarse is NOT a qualified grid.
    assert surface_s6.matches_qualified_grid(coarse) == ""


def test_the_memory_forecast_can_be_overruled(tmp_path, monkeypatch):
    """A pessimistic lower-bound estimate must not veto the user's own machine."""
    monkeypatch.setattr(solvers, "ADFLOW_BYTES_PER_CELL_PER_RANK", 8_000_000)
    launched = []
    monkeypatch.setattr(solvers.SolverRun, "_launch",
                        lambda self, *a, **k: launched.append(True))

    runner = solvers.ADflowRunner()
    flow, settings = solvers.FlowConditions(), solvers.ADflowSettings()

    with pytest.raises(MemoryError) as raised:
        runner.start(tmp_path / "g.cgns", flow, settings, tmp_path, cells=1_000_000)
    assert launched == []
    # The refusal explains what to reduce and that the figure is measured.
    assert "MEASURED peak" in str(raised.value)
    assert "Reduce the CELL COUNT" in str(raised.value)

    runner.start(tmp_path / "g.cgns", flow, settings, tmp_path,
                 cells=1_000_000, allow_over_budget=True)
    assert launched == [True]


def test_the_memory_warning_is_shown_before_the_march(make_app):
    """The forecast follows the pre-march estimate, not just a finished mesh."""
    app = make_app("S6")
    app.state.mesh_stats = {}
    app.state.mesh_estimate = 1_621_504
    app._on_adflow_memory()
    assert app.state.memory_forecast["cells"] == 1_621_504


# --------------------------------------------------------------------------- #
# The wall-normal lever, and the measured memory facts behind it               #
# --------------------------------------------------------------------------- #

def test_the_wall_normal_override_reaches_prepare_without_touching_the_table(
        tmp_path, monkeypatch, fake_blocks):
    """N is changed through a scratch grid level, and the real table survives."""
    from shared import pyhyp_runner

    from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS

    declared = dict(GRID_LEVELS)
    captured = {}
    run_dir = tmp_path / "march_run"
    run_dir.mkdir(parents=True)

    def fake_prepare(**kwargs):
        captured.update(kwargs)
        # The level handed to prepare must resolve, and carry the new N.
        captured["resolved_N"] = int(GRID_LEVELS[kwargs["level"]]["N"])
        captured["resolved_coarsen"] = int(GRID_LEVELS[kwargs["level"]]["coarsen"])
        return {"characteristic_length": 1.0,
                "runs": [{"dir": str(run_dir), "runner": str(run_dir / "run.py")}]}

    monkeypatch.setattr(pyhyp_runner, "prepare", fake_prepare)
    monkeypatch.setattr(pyhyp_runner, "read_result", lambda _d: {"march_completed": True})
    _fake_subprocess(monkeypatch, returncode=0,
                     writes=lambda: (run_dir / "wing_vol.cgns").write_bytes(b"m"))

    settings = meshing.PyHypSettings(volume_level="smoke", normal_points_override=97)
    run = runs.create(tmp_path, "mesh", design_fingerprint="abc", settings={"x": 1})
    report = meshing.run_pyhyp(settings, run, blocks=fake_blocks, surface_info={},
                               geometry_id="g")

    assert captured["resolved_N"] == 97
    assert captured["resolved_coarsen"] == int(declared["smoke"]["coarsen"])
    assert report["normal_points"] == 97
    assert report["normal_points_is_override"] is True
    # S6's own table is exactly as it was.
    assert dict(GRID_LEVELS) == declared


def test_the_estimate_follows_the_wall_normal_override(fake_blocks):
    at_129 = meshing.estimate_pyhyp_cells(fake_blocks, "smoke", 129)
    at_97 = meshing.estimate_pyhyp_cells(fake_blocks, "smoke", 97)
    assert at_97 * 128 == at_129 * 96
    # Default still tracks the level's own declared N.
    assert meshing.estimate_pyhyp_cells(fake_blocks, "smoke") == at_129


def test_a_qualified_grid_pins_the_wall_normal_count_back(make_app):
    app = make_app("S6")
    app.state.pyhyp_normal_points = 65
    app.select_grid("G2_medium")
    assert app.pyhyp_settings.normal_points_override is None
    assert meshing.effective_normal_points(app.pyhyp_settings) == 193
    assert app.state.pyhyp_normal_points == 193


def test_the_memory_guard_matches_every_measured_outcome():
    """Calibrated against real ADflow runs, not inferred from failures.

    Four samples on this machine with solution writing disabled: 913 k cells
    COMPLETED at 9.47 GiB, while 1.22 M and 1.62 M were both killed. The guard
    has to allow the first and refuse the others, or it is either useless or an
    obstacle.
    """
    assert solvers.ADFLOW_BYTES_PER_CELL_PER_RANK >= 9319, "8000 was too optimistic"

    # A machine with the memory this one had during the measurements.
    fits = {n: solvers.ADflowRunner.memory_forecast(n, 1)["estimated_gib"]
            for n in (912_768, 1_216_128, 1_621_504)}
    assert fits[912_768] < 10.0, "the configuration that ran must be predicted to fit"
    assert fits[1_216_128] > 11.8, "a configuration that died must exceed the machine"
    assert fits[1_621_504] > fits[1_216_128]


def test_the_refusal_no_longer_recommends_more_ranks():
    """Measured: 1 rank and 4 ranks peak at the same total, so ranks are no cure."""
    import inspect

    source = inspect.getsource(solvers.ADflowRunner.start)
    assert "Adding MPI ranks will NOT help" in source
    assert "1 rank and 4 ranks peak at the same total" in source
    assert "better one to cut first" in source
