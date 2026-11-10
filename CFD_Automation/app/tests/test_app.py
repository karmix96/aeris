"""The app's engine and pictures on real wings (no Streamlit needed).

    python -m pytest CFD_Automation/app/tests -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core      # noqa: E402
import figures   # noqa: E402


@pytest.fixture(scope="module")
def built():
    g = core.build_geometry(core.from_set("bwb", "reference", 0))
    sm = core.build_surface_mesh(g, "VC", 3e5)
    return g, sm, core.build_volume_mesh(sm)


def test_hold_outs_are_never_offered_or_loaded():
    assert not any(s.startswith("holdout") for s in core.SETS)
    with pytest.raises(PermissionError):
        core.set_size("bwb", "holdout_focus")
    with pytest.raises(PermissionError):
        core.from_set("bwb", "holdout_full", 0)


def test_set_sizes_match_the_stage_1_sets():
    assert [core.set_size("bwb", s) for s in core.SETS] == [5, 100, 40, 32, 8]


def test_the_app_builds_the_same_mesh_as_the_stage_3_study(built):
    g, sm, vm = built
    assert g.passed and sm.passed and vm.outcome == "passed"
    assert g.summary["input_hash"].startswith("e32d995a")       # the V1/V7 wing
    assert vm.cells == 2_324_016                                 # V1 and the V7 case (rule set 2)
    assert core.count_cells(sm)["cells"] == vm.cells             # the count is the build


def test_a_wing_made_from_its_numbers_is_the_set_wing():
    w0 = core.from_set("cranked", "reference", 2)
    s = core.spec("cranked")
    w1 = core.from_values("cranked", {v: w0.vector[v] for v in s.free_variables}, w0.vector["airfoils"])
    assert w1.key() == w0.key()


def test_the_wing_file_round_trips():
    w0 = core.from_set("tapered", "training_focus", 7)
    w1 = core.from_json(w0.to_json(), name="x.json")
    assert w1.key() == w0.key()
    bare = json.dumps(w0.vector)                                 # a Stage 1 vector.json carries no type
    with pytest.raises(ValueError):
        core.from_json(bare)
    assert core.from_json(bare, "tapered").key() == w0.key()


def test_an_unknown_section_is_refused():
    s = core.spec("bwb")
    w0 = core.middle("bwb")
    with pytest.raises(ValueError):
        core.from_values("bwb", {v: w0.vector[v] for v in s.free_variables}, ["nosuchfoil"] * 4)


def test_every_plane_and_picture_draws(built):
    g, sm, vm = built
    pl = core.planes(vm)
    n_in = sum(p["side"] == "in" for p in pl)
    assert n_in == sm.wing.shape[1] and pl[0]["y"] == 0.0 and pl[-1]["side"] == "out"
    assert all(b["y"] > a["y"] for a, b in zip(pl, pl[1:]))     # root to far field, no plane twice
    for f in (figures.planform(g.stations), figures.sections(g.stations), figures.wing_3d(g.stations),
              figures.surface_mesh_3d(sm), figures.surface_ring(sm, 5),
              figures.volume_plane(vm, sm, pl[0], "close"), figures.volume_plane(vm, sm, pl[n_in // 2], "wake"),
              figures.volume_plane(vm, sm, pl[-1], "all"), figures.volume_plane(vm, sm, pl[n_in + 2], "close"),
              figures.volume_3d(vm, sm, [pl[0], pl[n_in - 1], pl[n_in + 2]])):
        assert len(f.data) >= 1
    assert sum(r["cells"] for r in core.block_table(vm)) == vm.cells
    assert [r["result"] for r in core.check_rows(vm.checks)].count("pass") == len(vm.checks)
