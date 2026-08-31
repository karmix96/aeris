"""Laptop-safe tests for the coarse solver confirmation.

Nothing here invokes SU2_CFD or mpirun.  What is under test is the arithmetic and
the bookkeeping around a run that costs hours: which variants are selected, where
the reference values come from, whether the memory plan would have caught the OOM
that stopped the first coarse attempt, and whether a resumed root can quietly
become a different experiment.
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
    "s7_tuning_test_package",
    S7_DIR / "__init__.py",
    submodule_search_locations=[str(S7_DIR)],
)
assert _spec and _spec.loader
_package = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _package
_spec.loader.exec_module(_package)
tuning = importlib.import_module("s7_tuning_test_package.solver_tuning")


# Whole-wing values as geometry_summary.json records them for development index 0.
AREA_M2 = 0.9610974474634779
CHORD_M = 0.5349896481665188


def _case_dir(
    root: Path, *, meshes: tuple[str, ...] = ("a",), cells: int | None = 1_549_111
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "geometry_summary.json").write_text(
        json.dumps(
            {
                "pygeo_reference_values": {
                    "area_m2": AREA_M2,
                    "mean_aerodynamic_chord_m": CHORD_M,
                }
            }
        ),
        encoding="utf-8",
    )
    for name in meshes:
        attempt = root / name
        attempt.mkdir(exist_ok=True)
        (attempt / "mesh.su2").write_text("NDIME= 3\n", encoding="utf-8")
    if cells is not None:
        (root / "audit.json").write_text(
            json.dumps({"counts": {"volume_cells": cells}}), encoding="utf-8"
        )
    return root


def test_shortlist_is_the_roadmap_shortlist(tmp_path: Path) -> None:
    """Every shortlisted variant exists, carries Newton-Krylov, and is not a duplicate."""
    assert set(tuning.SHORTLIST) <= set(tuning.VARIANTS)
    for name in tuning.SHORTLIST:
        assert tuning.VARIANTS[name].get("NEWTON_KRYLOV") == "YES", name
    # J_nk_no_mg produced a byte-identical history to I_combined because multigrid
    # is bypassed under NEWTON_KRYLOV.  Running it at coarse buys a duplicate at
    # coarse cost, so it must stay out of the shortlist.
    assert "J_nk_no_mg" not in tuning.SHORTLIST


def test_case_is_read_from_the_geometry_not_typed(tmp_path: Path) -> None:
    case = tuning.case_from_directory(_case_dir(tmp_path / "case"))
    assert case["cells"] == 1_549_111
    assert case["mesh"].endswith("/a/mesh.su2")
    # The whole-wing values, NOT pre-halved: fixed_su2_options halves REF_AREA
    # itself for a half mesh, and halving twice reports CL and CD at a quarter of
    # their true value on a run that looks entirely healthy.
    assert case["area_ref"] == pytest.approx(AREA_M2)
    assert case["chord_ref"] == pytest.approx(CHORD_M)


def test_ambiguous_or_unaudited_case_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one accepted mesh"):
        tuning.case_from_directory(_case_dir(tmp_path / "two", meshes=("a", "b")))
    with pytest.raises(ValueError, match="no audited cell count"):
        tuning.case_from_directory(_case_dir(tmp_path / "unaudited", cells=None))


def test_memory_plan_would_have_caught_the_recorded_oom(monkeypatch) -> None:
    """The measured datum: 2.5 M cells at eight ranks, OOM-killed on 16 GiB."""
    monkeypatch.setattr(tuning, "available_memory_gib", lambda: 16.0)
    killed = tuning.memory_plan(2_500_000, ranks=8, workers=1)
    assert killed["estimated_peak_gib"] == pytest.approx(24.0, abs=0.05)
    assert killed["fits"] is False
    # Two ranks on the same mesh is what actually ran, and it must not be refused.
    assert tuning.memory_plan(2_500_000, ranks=2, workers=1)["fits"] is True
    # Concurrency multiplies both ways; the laptop matrix's four workers at
    # coarse resolution is the same arithmetic ignored.
    assert tuning.memory_plan(1_549_111, ranks=4, workers=4)["fits"] is False


def test_memory_plan_is_unenforced_rather_than_wrong_without_meminfo(monkeypatch) -> None:
    monkeypatch.setattr(tuning, "available_memory_gib", lambda: None)
    plan = tuning.memory_plan(1_549_111, ranks=4, workers=1)
    assert plan["fits"] is None and plan["budget_gib"] is None


def test_solver_command_is_serial_at_one_rank_and_mpi_above(tmp_path: Path) -> None:
    assert tuning.solver_command(1) == ["SU2_CFD", "case.cfg"]
    assert tuning.solver_command(4) == ["mpirun", "-np", "4", "SU2_CFD", "case.cfg"]
    with pytest.raises(ValueError):
        tuning.solver_command(0)


def _identity(**overrides):
    case = {"mesh": "/m.su2", "cells": 10, "area_ref": 1.0, "chord_ref": 0.5}
    kwargs = {
        "variants": ("G_nk_cfl",),
        "iterations": 6000,
        "ranks": 4,
        "stop_residual": -12.0,
    }
    kwargs.update(overrides)
    return tuning.request_identity(case, **kwargs)


def test_request_identity_separates_experiments_not_schedules() -> None:
    base = _identity()
    assert _identity()["digest"] == base["digest"]
    for change in ({"ranks": 2}, {"iterations": 3000}, {"variants": ("I_combined",)}):
        assert _identity(**change)["digest"] != base["digest"], change


def test_a_root_continues_its_request_or_refuses(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    root.mkdir()
    tuning.claim_root(root, _identity())
    tuning.claim_root(root, _identity())  # resume: same request, no complaint
    with pytest.raises(SystemExit, match="new output root"):
        tuning.claim_root(root, _identity(ranks=2))


def test_resume_reloads_a_result_and_refuses_a_partial_attempt(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    done = root / "G_nk_cfl"
    done.mkdir(parents=True)
    (done / "result.json").write_text(
        json.dumps({"variant": "G_nk_cfl", "exit": 0, "rms_final": -9.5}), encoding="utf-8"
    )
    case = {"mesh": "/m.su2", "cells": 10, "area_ref": 1.0, "chord_ref": 0.5}
    # Reloaded without touching the solver: at coarse a re-run costs hours and
    # produces the same numbers.
    report = tuning.run_variant("G_nk_cfl", root, case, 10, 60, -12.0, 1)
    assert report["reused"] is True and report["rms_final"] == -9.5

    (root / "I_combined").mkdir()
    with pytest.raises(SystemExit, match="interrupted part way"):
        tuning.run_variant("I_combined", root, case, 10, 60, -12.0, 1)
