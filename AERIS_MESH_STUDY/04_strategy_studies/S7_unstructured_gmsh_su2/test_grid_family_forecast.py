"""Tests for the M5 feasibility forecast.

The forecast decides whether days of campaign time are worth starting, so the
parts that are geometry rather than estimate must be exact, and the part that is
an estimate must be replaceable by a measurement.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

S7_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "s7_forecast_test_package",
    S7_DIR / "__init__.py",
    submodule_search_locations=[str(S7_DIR)],
)
assert _spec and _spec.loader
_package = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _package
_spec.loader.exec_module(_package)
forecast = importlib.import_module("s7_forecast_test_package.grid_family_forecast")
common = importlib.import_module("s7_forecast_test_package.common")

# The measured index-0 coarse half mesh.
COARSE_PRISMS = 126_984
COARSE_TETS = 1_422_127


def _rows(**kwargs):
    return {
        row["level"]: row
        for row in forecast.level_forecast(
            common.load_policy(),
            reference="coarse",
            prisms=COARSE_PRISMS,
            tets=COARSE_TETS,
            **kwargs,
        )
    }


def test_the_reference_level_reproduces_its_own_measurement():
    rows = _rows()
    assert rows["coarse"]["cells"] == COARSE_PRISMS + COARSE_TETS
    assert rows["coarse"]["source"] == "measured"


def test_refinement_ratios_come_from_the_policy_edge_lengths():
    """These are geometry, not a model: the levels are defined by edge length."""
    rows = _rows()
    assert rows["coarse"]["surface_refinement_ratio"] == pytest.approx(1.0)
    # 0.06 / 0.0424 and 0.06 / 0.03 as POLICY.yaml declares them.
    assert rows["medium"]["surface_refinement_ratio"] == pytest.approx(1.4151, abs=1e-3)
    assert rows["fine"]["surface_refinement_ratio"] == pytest.approx(2.0, abs=1e-3)
    # Each level is finer than the last, in both families.
    cells = [rows[n]["cells"] for n in ("coarse", "medium", "fine")]
    assert cells == sorted(cells)


def test_prisms_follow_surface_squared_times_the_layer_count():
    """Not an estimate: prisms are wall triangles times layers."""
    rows = _rows()
    ratio = rows["fine"]["surface_refinement_ratio"] ** 2 * (40.0 / 24.0)
    assert rows["fine"]["prisms"] == pytest.approx(COARSE_PRISMS * ratio, rel=1e-3)


def test_a_measurement_replaces_the_forecast():
    """The r^3 tetrahedral estimate is the one number meant to be overridden."""
    forecast_only = _rows()["medium"]["cells"]
    measured = _rows(measured={"medium": 3_000_000})["medium"]
    assert measured["cells"] == 3_000_000
    assert measured["source"] == "measured"
    assert measured["cells"] != forecast_only


def test_a_level_needing_more_than_the_whole_budget_is_not_solvable():
    """Each rank holds the full mesh, so one rank is the cheapest decomposition.

    A level whose single-rank footprint exceeds the host budget cannot be solved
    there at any rank count.  This is the S6 RESOURCE_BLOCKED condition, and the
    forecast must say NO rather than propose zero ranks as if that were a plan.
    """
    rows = {r["level"]: r for r in forecast.solvability(
        forecast.level_forecast(
            common.load_policy(), reference="coarse",
            prisms=COARSE_PRISMS, tets=COARSE_TETS,
        ),
        budget_gib=11.36,
    )}
    assert rows["coarse"]["solvable"] is True
    assert rows["fine"]["solvable"] is False
    assert rows["fine"]["max_ranks"] == 0
    # And it becomes solvable on a bigger host, rather than being impossible.
    big = {r["level"]: r for r in forecast.solvability(
        forecast.level_forecast(
            common.load_policy(), reference="coarse",
            prisms=COARSE_PRISMS, tets=COARSE_TETS,
        ),
        budget_gib=64.0,
    )}
    assert big["fine"]["solvable"] is True


def test_the_memory_law_is_shared_with_the_solver_tool():
    """One law, not two copies that can drift."""
    tuning = importlib.import_module("s7_forecast_test_package.solver_tuning")
    assert (
        forecast.GIB_PER_RANK_PER_MILLION_CELLS
        is tuning.GIB_PER_RANK_PER_MILLION_CELLS
    )


def test_census_summary_counts_what_the_decisions_need():
    """The summary must surface fallbacks and sub-ladder caps, not just averages."""
    census = importlib.import_module("s7_forecast_test_package.tip_cap_census")
    rows = [
        {"index": 0, "status": "ok", "any_fallback": False, "min_angle_deg": 12.9},
        {"index": 1, "status": "ok", "any_fallback": True, "min_angle_deg": 7.0},
        {"index": 2, "status": "ok", "any_fallback": False, "min_angle_deg": 7.5},
        {"index": 3, "status": "error", "error": "boom"},
    ]
    s = census.summarise(rows)
    assert s["designs"] == 4 and s["surfaces_built"] == 3
    assert s["errors"] == [3]
    assert s["fallback_count"] == 1 and s["fallback_indices"] == [1]
    # 7.209 is the rigid ladder this study rejected; a Delaunay cap below it is
    # more slender than the construction thrown out for being too slender.
    assert s["below_rejected_ladder_7p209"] == [1]
    assert s["min_angle_deg"]["min"] == 7.0
