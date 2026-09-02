"""Laptop-safe parser, gate, and deterministic SU2-recovery tests.

The recovery test uses a tiny local fake executable.  It exercises process
isolation, immutable attempt creation, output parsing, restart hashing, and
resume behavior; it is not CFD evidence and never invokes SU2_CFD.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

S7_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "s7_su2_test_package",
    S7_DIR / "__init__.py",
    submodule_search_locations=[str(S7_DIR)],
)
assert _spec and _spec.loader
_package = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _package
_spec.loader.exec_module(_package)
common = importlib.import_module("s7_su2_test_package.common")
su2 = importlib.import_module("s7_su2_test_package.su2_pipeline")


def _native_mesh(path: Path) -> Path:
    path.write_text(
        """NDIME= 3
NELEM= 1
10 0 1 2 3 0
NPOIN= 4
0.0 0.0 0.0 0
1.0 0.0 0.0 1
0.0 1.0 0.0 2
0.0 0.0 1.0 3
NMARK= 5
MARKER_TAG= wall_upper
MARKER_ELEMS= 1
5 0 1 2
MARKER_TAG= wall_lower
MARKER_ELEMS= 1
5 0 1 2
MARKER_TAG= wall_te
MARKER_ELEMS= 1
5 0 1 2
MARKER_TAG= wall_tip
MARKER_ELEMS= 1
5 0 1 2
MARKER_TAG= farfield
MARKER_ELEMS= 1
5 0 1 2
""",
        encoding="utf-8",
    )
    return path


def _fake_solver(path: Path) -> Path:
    path.write_text(
        """from pathlib import Path
import csv
import sys

cfg = Path(sys.argv[-1]).read_text(encoding='utf-8')
restart = 'RESTART_SOL= YES' in cfg
with Path('history.csv').open('w', encoding='utf-8', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['Inner_Iter', 'rms[Rho]', 'CL', 'CD', 'CMy'])
    for index in range(200):
        residual = ((-3.0 - 5.5 * index / 199.0) if restart else (-1.0 - 2.0 * index / 199.0))
        writer.writerow([index, residual, 0.42, 0.018, -0.031])
with Path('surface_flow.csv').open('w', encoding='utf-8', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['Global_Index', 'Y_PLUS'])
    writer.writerows([(0, 0.5), (1, 0.75), (2, 1.0)])
Path('restart_flow.dat').write_bytes(b'deterministic-restart')
# SU2 8.5 omits PRIMITIVE fields from the surface CSV, so wall y+ arrives in the
# surface Paraview file.  The fake solver writes one so that path is covered.
vtk = ['# vtk DataFile Version 3.0', 'fake', 'ASCII', 'DATASET POLYDATA',
       'POINTS 3 double', '0 0 0', '1 0 0', '0 1 0',
       'POINT_DATA 3', 'SCALARS Y_Plus double 1', 'LOOKUP_TABLE default',
       '0.51', '0.62', '0.73']
Path('surface_flow.vtk').write_text(chr(10).join(vtk) + chr(10))
""",
        encoding="utf-8",
    )
    return path


def _accepted_inputs(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    mesh = _native_mesh(tmp_path / "mesh.su2")
    geometry = tmp_path / "geometry.npz"
    geometry.write_bytes(b"synthetic-geometry")
    audit = tmp_path / "mesh_audit.json"
    common.write_json(
        audit,
        {
            "schema": "aeris.s7.mesh_audit.v1",
            "mesh_su2_sha256": common.sha256_file(mesh),
            "acceptance": {"accepted": True, "failures": []},
        },
    )
    return mesh, {"geometry": geometry, "mesh_audit": audit}


def test_history_force_and_yplus_gates_are_fail_closed(tmp_path):
    history = tmp_path / "history.csv"
    history.write_text(
        '"Inner_Iter","rms[Rho]","CL","CD","CMy"\n'
        + "\n".join(
            f"{index},{-1.0 - 8.0 * index / 199.0},0.42,0.018,-0.031" for index in range(200)
        )
        + "\n",
        encoding="utf-8",
    )
    parsed = su2.parse_su2_history(history)
    policy = common.load_policy()
    assert su2.residual_gate(parsed, policy)["passed"]
    forces = su2.force_tail_gate(parsed, policy)
    assert forces["passed"]
    assert forces["final_coefficients"] == pytest.approx({"CL": 0.42, "CD": 0.018, "CMy": -0.031})

    surface = tmp_path / "surface.csv"
    surface.write_text("Global_Index,Y_PLUS\n0,0.5\n1,1.0\n", encoding="utf-8")
    incomplete = su2.parse_surface_yplus(surface, expected_wall_point_indices={0, 1, 2})
    gate = su2.wall_yplus_gate(incomplete, policy)
    assert not gate["passed"]
    assert "incomplete_wall_point_coverage" in gate["failure_reasons"]


def test_fixed_config_uses_native_su2_85_names(tmp_path):
    mesh = _native_mesh(tmp_path / "mesh.su2")
    options = su2.fixed_su2_options(
        mesh,
        flow={"mach": 0.2, "alpha": 2.0, "reynolds": 1.0e6, "temperature": 288.15},
        references={"area_ref": 1.0, "chord_ref": 1.0},
        iterations=5,
        restart=False,
    )
    assert options["SOLVER"] == "RANS"
    assert options["KIND_TURB_MODEL"] == "SA"
    assert options["CONV_FILENAME"] == "history"
    assert "HISTORY_FILENAME" not in options
    assert "AERO_COEFF" in options["HISTORY_OUTPUT"]
    assert options["MARKER_PLOTTING"].count("wall_") == 4


def test_one_restart_is_digest_verified_and_resume_is_idempotent(tmp_path, monkeypatch):
    mesh, inputs = _accepted_inputs(tmp_path)
    solver = _fake_solver(tmp_path / "fake_su2.py")
    monkeypatch.setattr(
        su2,
        "verify_pinned_versions",
        lambda **_kwargs: {"passed": True, "mismatches": [], "synthetic": True},
    )
    kwargs = {
        "attempts_root": tmp_path / "attempts",
        "mesh_path": mesh,
        "flow": {
            "flow_id": "unit",
            "mach": 0.2,
            "alpha": 2.0,
            "reynolds": 1.0e6,
            "temperature": 288.15,
        },
        "references": {"area_ref": 1.0, "chord_ref": 1.0},
        "geometry_set": common.load_policy()["data"]["development_set"],
        "evidence_tier": "unit",
        "timeout_s": 30.0,
        "solver_command": [sys.executable, str(solver)],
        "input_artifacts": inputs,
    }
    result = su2.run_su2_pipeline(**kwargs)
    assert result["accepted"]
    assert result["attempt_count"] == 2
    assert result["automatic_restarts_used"] == 1
    first, second = result["attempts"]
    assert first["phase"] == "freestream" and not first["accepted"]
    assert second["phase"] == "restart" and second["accepted"]
    assert second["restart_input"]["sha256"] == first["gates"]["restart"]["sha256"]
    assert second["gates"]["residual"]["attempt_initial_log10"] == pytest.approx(-3.0)
    assert second["gates"]["residual"]["initial_log10"] == pytest.approx(-1.0)
    assert second["gates"]["residual"]["orders_dropped"] == pytest.approx(7.5)
    assert second["gates"]["residual"]["initial_source"] == "freestream_chain_history"
    assert first["run"]["peak_process_tree_rss_bytes"] > 0

    before = sorted((tmp_path / "attempts").glob("attempt_*"))
    resumed = su2.run_su2_pipeline(**kwargs)
    after = sorted((tmp_path / "attempts").glob("attempt_*"))
    assert resumed == result
    assert after == before
    assert json.loads((tmp_path / "attempts" / "pipeline_result.json").read_text())["accepted"]
    assert json.loads(
        (Path(second["attempt_dir"]) / "attempt_result.json").read_text(encoding="utf-8")
    )["accepted"]

    changed = dict(kwargs)
    changed["flow"] = dict(kwargs["flow"], alpha=3.0)
    with pytest.raises(RuntimeError, match="different mesh/flow/configuration"):
        su2.run_su2_pipeline(**changed)


def _half_mesh(path: Path) -> Path:
    """The same mesh with a symmetry marker, as the half domain produces."""
    text = _native_mesh(path).read_text(encoding="utf-8")
    text = text.replace("NMARK= 5", "NMARK= 6")
    text += "MARKER_TAG= symmetry\nMARKER_ELEMS= 1\n5 0 1 2\n"
    path.write_text(text, encoding="utf-8")
    return path


def test_half_domain_declares_the_symmetry_plane(tmp_path):
    options = su2.fixed_su2_options(
        _half_mesh(tmp_path / "half.su2"),
        flow={"mach": 0.2, "alpha": 2.0, "reynolds": 1.0e6, "temperature": 288.15},
        references={"area_ref": 1.0, "chord_ref": 1.0},
        iterations=5,
        restart=False,
    )
    # Without this SU2 treats the unlisted boundary as a wall, putting a viscous
    # surface down the centreline instead of a plane of symmetry.
    assert options["MARKER_SYM"] == "( symmetry )"
    assert "symmetry" not in options["MARKER_HEATFLUX"]
    assert "symmetry" not in options["MARKER_MONITORING"]


def test_half_domain_halves_the_reference_area(tmp_path):
    """Half the wing produces half the force; the reference must match it.

    The reference values describe the whole wing whatever is meshed, so leaving
    REF_AREA alone would report CL and CD at exactly half their true value while
    the run looked entirely healthy.
    """
    common_flow = {"mach": 0.2, "alpha": 2.0, "reynolds": 1.0e6, "temperature": 288.15}
    references = {"area_ref": 2.0, "chord_ref": 1.0}
    mirrored = su2.fixed_su2_options(
        _native_mesh(tmp_path / "full.su2"), flow=common_flow,
        references=references, iterations=5, restart=False,
    )
    half = su2.fixed_su2_options(
        _half_mesh(tmp_path / "half.su2"), flow=common_flow,
        references=references, iterations=5, restart=False,
    )
    assert mirrored["REF_AREA"] == pytest.approx(2.0)
    assert half["REF_AREA"] == pytest.approx(1.0)
    assert "MARKER_SYM" not in mirrored


def test_solver_stop_sits_below_the_acceptance_bar(tmp_path):
    """The solver must not be told to stop exactly where the gate is set.

    Deriving CONV_RESIDUAL_MINVAL from residual_log10_final_max halts SU2 the
    instant the residual touches the bar, so the final residual is the bar by
    construction and the achievable drop is exactly `initial + 8`.  Every S7 run
    starts near -2.6, which capped the drop at 5.4 orders against a gate asking
    for 6.0 and rejected two genuinely converged runs.  See ADR-0017.
    """
    options = su2.fixed_su2_options(
        _native_mesh(tmp_path / "mesh.su2"),
        flow={"mach": 0.2, "alpha": 2.0, "reynolds": 1.0e6, "temperature": 288.15},
        references={"area_ref": 1.0, "chord_ref": 1.0},
        iterations=5,
        restart=False,
    )
    limits = su2.load_policy()["su2"]["convergence"]
    stop = float(options["CONV_RESIDUAL_MINVAL"])
    assert stop == pytest.approx(float(limits["solver_stop_residual_log10"]))
    assert stop < float(limits["residual_log10_final_max"])
    # The reachable drop must leave room for the drop gate on a run starting at
    # the assumed worst free-stream residual.  The demanding case is the MOST
    # negative initial, because the drop is initial - final.
    assert (
        float(limits["assumed_worst_initial_residual_log10"]) - stop
        >= float(limits["residual_drop_orders_min"])
    )
    # And that assumption must bound every initial residual S7 has measured.
    # laptop_smoke starts between -2.576 and -2.687; COARSE starts at -3.6643,
    # which is what falsified the earlier -3.0 bound.  A resolution change moves
    # this number, so it is asserted against the measurement rather than against
    # the level the assumption was first calibrated on.
    assert float(limits["assumed_worst_initial_residual_log10"]) <= -3.6643


def test_a_solver_stop_at_the_bar_is_refused(tmp_path, monkeypatch):
    """Fail closed rather than silently reinstate an unsatisfiable gate."""
    policy = su2.load_policy()
    policy["su2"]["convergence"]["solver_stop_residual_log10"] = policy["su2"][
        "convergence"
    ]["residual_log10_final_max"]
    monkeypatch.setattr(su2, "load_policy", lambda: policy)
    with pytest.raises(ValueError, match="solver_stop_residual_log10"):
        su2.fixed_su2_options(
            _native_mesh(tmp_path / "mesh.su2"),
            flow={"mach": 0.2, "alpha": 2.0, "reynolds": 1.0e6, "temperature": 288.15},
            references={"area_ref": 1.0, "chord_ref": 1.0},
            iterations=5,
            restart=False,
        )


def _history_file(path: Path, initial: float, final: float, rows: int = 200) -> Path:
    """A linear residual descent from `initial` to `final` with steady forces."""
    step = (final - initial) / (rows - 1)
    path.write_text(
        '"Inner_Iter","rms[Rho]","CL","CD","CMy"\n'
        + "\n".join(
            f"{i},{initial + step * i},0.42,0.018,-0.031" for i in range(rows)
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_gate_names_a_truncated_setup_instead_of_blaming_the_solver(tmp_path):
    """Defect 10, recurring at coarse: the stop halted the run above the gate.

    A coarse run starts at -3.6643 and must reach -9.6643 to drop six orders.  A
    solver stopping at -9.0 cannot get there, so the drop gate is unsatisfiable
    by construction and `insufficient_residual_drop` alone would read as a solver
    that failed to converge.
    """
    policy = su2.load_policy()
    policy["su2"]["convergence"]["solver_stop_residual_log10"] = -9.0
    parsed = su2.parse_su2_history(_history_file(tmp_path / "coarse.csv", -3.6643, -9.0))
    result = su2.residual_gate(parsed, policy)
    assert result["passed"] is False
    assert "solver_stop_truncates_drop_gate" in result["failure_reasons"]
    assert result["required_final_for_drop_gate"] == pytest.approx(-9.6643)


def test_the_shipped_policy_stop_reaches_the_gate_at_coarse(tmp_path):
    """The repaired stop must let a coarse run satisfy the drop gate."""
    policy = su2.load_policy()
    parsed = su2.parse_su2_history(_history_file(tmp_path / "coarse.csv", -3.6643, -9.7))
    result = su2.residual_gate(parsed, policy)
    assert "solver_stop_truncates_drop_gate" not in result["failure_reasons"]
    assert result["passed"] is True


def test_the_truncation_reason_never_fires_on_a_run_that_would_pass(tmp_path):
    """The guard adds a diagnosis; it must not reclassify passing evidence.

    A run that satisfied the drop gate descended to at or below
    initial - drop_min without the solver stopping there, so the stop is
    necessarily at or below that level and the new reason cannot fire.
    """
    policy = su2.load_policy()
    for initial, final in ((-2.6029, -8.7), (-3.6643, -9.7), (-2.5755, -9.0)):
        parsed = su2.parse_su2_history(
            _history_file(tmp_path / f"{initial}_{final}.csv", initial, final)
        )
        result = su2.residual_gate(parsed, policy)
        if result["orders_dropped"] >= 6.0 and final <= -8.0:
            assert result["passed"] is True, (initial, final, result["failure_reasons"])
