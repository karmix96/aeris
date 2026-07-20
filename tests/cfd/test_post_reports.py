"""GCI/Richardson math and solve-report summarization."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from aeris.cfd.post.reports import (
    gci_study,
    grid_convergence_index,
    load_solve_report,
    solve_summary,
)


def test_gci_recovers_manufactured_second_order():
    """f(h) = f0 + C h^p with p=2: the procedure must recover p and f0 exactly."""
    f0, coefficient, r = 1.0909, 0.05, 1.4
    h_fine = 0.01
    f1 = f0 + coefficient * h_fine**2
    f2 = f0 + coefficient * (r * h_fine) ** 2
    f3 = f0 + coefficient * (r * r * h_fine) ** 2
    result = grid_convergence_index(f1, f2, f3, refinement_ratio=r)
    assert result["convergence"] == "monotone"
    assert result["observed_order"] == pytest.approx(2.0, rel=1e-10)
    assert result["extrapolated"] == pytest.approx(f0, rel=1e-10)
    assert result["gci_fine_percent"] > 0


def test_gci_first_order_sequence():
    f0, coefficient, r = 0.0123, 0.001, 2.0
    values = [f0 + coefficient * (r**k) for k in range(3)]
    result = grid_convergence_index(*values, refinement_ratio=r)
    assert result["observed_order"] == pytest.approx(1.0, rel=1e-10)


def test_gci_oscillatory_flagged():
    result = grid_convergence_index(1.0, 1.1, 1.05, refinement_ratio=1.4)
    assert result["convergence"] == "oscillatory"
    assert math.isnan(result["observed_order"])  # no defensible extrapolation


def test_gci_bad_ratio_rejected():
    with pytest.raises(ValueError, match="refinement_ratio"):
        grid_convergence_index(1.0, 1.1, 1.3, refinement_ratio=1.0)


def _write_report(path: Path, solver: str, cl: float, cd: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "aeris.cfd.solve_report.v1",
                "solver_id": solver,
                "status": "converged",
                "flow": {"alpha": 10.0, "mach": 0.15},
                "refs": {},
                "forces": {"cl": cl, "cd": cd},
                "convergence": {"iterations": 100, "final_resrho": 1e-9},
                "artifacts": {},
                "solver_version": None,
                "elapsed_seconds": 10.0,
            }
        )
    )
    return path


def test_solve_summary_rows(tmp_path: Path):
    a = _write_report(tmp_path / "adflow/solve_report.json", "adflow", 1.0850, 0.0124)
    s = _write_report(tmp_path / "su2/solve_report.json", "su2", 1.0910, 0.0122)
    summary = solve_summary([a, s], labels=["adflow", "su2"])
    assert summary["schema"] == "aeris.cfd.solve_summary.v1"
    assert [row["solver"] for row in summary["rows"]] == ["adflow", "su2"]
    assert summary["rows"][0]["forces"]["cl"] == pytest.approx(1.0850)


def test_gci_study_from_reports(tmp_path: Path):
    f0, coefficient, r = 1.0909, 0.05, 1.4
    paths = []
    for k, name in enumerate(["fine", "medium", "coarse"]):
        value = f0 + coefficient * (r**k * 0.01) ** 2
        paths.append(_write_report(tmp_path / name / "solve_report.json", "adflow", value, 0.01))
    study = gci_study(paths, quantity="cl", refinement_ratio=r)
    assert study["observed_order"] == pytest.approx(2.0, rel=1e-9)
    assert study["extrapolated"] == pytest.approx(f0, rel=1e-9)


def test_load_solve_report_validates_schema(tmp_path: Path):
    bad = tmp_path / "solve_report.json"
    bad.write_text(json.dumps({"schema": "other"}))
    with pytest.raises(ValueError, match="solve_report"):
        load_solve_report(bad)
