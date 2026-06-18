"""Integration tests for 2D QC → curate → promote pipeline."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from aeris.airfoil.qc import run_airfoil_dataset_qc
from aeris.airfoil.curate import curate_airfoil_dataset
from aeris.airfoil.promote import promote_airfoil_dataset


def _write_test_dataset(root, rows):
    root.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(root / "airfoil_dataset.csv", index=False)
    manifest = {
        "schema_version": "airfoil_dataset_v1",
        "dataset_name": "test",
        "solver_id": "xfoil_python",
        "n_airfoils": 2,
        "total_rows": len(rows),
        "converged_rows": sum(1 for r in rows if r.get("converged")),
        "convergence_rate": 0.8,
        "airfoil_dataset_csv": str(root / "airfoil_dataset.csv"),
        "airfoil_failures_csv": str(root / "airfoil_failures.csv"),
    }
    (root / "airfoil_dataset_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (root / "airfoil_failures.csv").write_text("", encoding="utf-8")
    # AERIS_FIX_QC_TEST_SETUP: ISSUE-C12 requires QC report to exist.
    import json as _json
    (root / "airfoil_qc_report.json").write_text(
        _json.dumps({"passed": True, "schema_version": "airfoil_qc_v1",
                     "total_rows": len(rows), "converged_rows": len(rows),
                     "issues": [], "warnings": []}),
        encoding="utf-8",
    )


def _good_rows():
    rows = []
    for airfoil_id, name, source, cl0, cm in [
        ("abc123", "A", "a.xlsx", 0.2, -0.05),
        ("def456", "B", "b.xlsx", 0.1, -0.03),
    ]:
        for alpha_deg, delta in [(0.0, 0.0), (2.0, 0.2), (4.0, 0.4)]:
            rows.append(
                {
                    "airfoil_id": airfoil_id,
                    "airfoil_name": name,
                    "source_file": source,
                    "alpha_deg": alpha_deg,
                    "reynolds": 1e6,
                    "mach": 0.0,
                    "ncrit": 9.0,
                    "cl": cl0 + delta,
                    "cd": 0.01 + 0.001 * alpha_deg,
                    "cm": cm,
                    "cp_min": -0.5 - 0.1 * alpha_deg,
                    "converged": True,
                    "solver_id": "xfoil_python",
                }
            )
    return rows


def test_qc_passes_on_clean_dataset(tmp_path):
    root = tmp_path / "ds"
    _write_test_dataset(root, _good_rows())
    report = run_airfoil_dataset_qc(dataset_root=root)
    assert report["passed"] is True
    assert report["total_rows"] == 6
    assert report["converged_rows"] == 6
    assert report["issues"] == []


def test_curate_keeps_good_rows(tmp_path):
    root = tmp_path / "ds"
    _write_test_dataset(root, _good_rows())
    report = curate_airfoil_dataset(dataset_root=root)
    assert report["kept_rows"] == 6
    assert report["rejected_rows"] == 0
    assert report["promotion_ready"] is True


def test_curate_rejects_unconverged(tmp_path):
    root = tmp_path / "ds"
    rows = _good_rows() + [{
        "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
        "alpha_deg": 14.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
        "cl": None, "cd": None, "cm": None, "cp_min": None,
        "converged": False, "solver_id": "xfoil_python",
    }]
    _write_test_dataset(root, rows)
    report = curate_airfoil_dataset(dataset_root=root)
    assert report["rejected_rows"] == 1
    assert report["kept_rows"] == 6


def test_promote_writes_manifest(tmp_path):
    root = tmp_path / "ds"
    _write_test_dataset(root, _good_rows())
    curate_airfoil_dataset(dataset_root=root)
    manifest = promote_airfoil_dataset(dataset_root=root)
    assert manifest["promotion_forced"] is False
    assert manifest["domain"] == "airfoil_2d"
    curated_csv = manifest["artifacts"]["curated_aero_dataset_csv"]
    assert curated_csv is not None
    assert (root / "promotion_manifest.json").exists()


def test_promote_blocked_without_curation(tmp_path):
    root = tmp_path / "ds"
    _write_test_dataset(root, _good_rows())
    # Intentionally skip curation
    with pytest.raises(FileNotFoundError):
        promote_airfoil_dataset(dataset_root=root)


def test_promote_force_flag(tmp_path):
    root = tmp_path / "ds"
    rows = [{
        "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
        "alpha_deg": 0.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
        "cl": None, "cd": None, "cm": None, "cp_min": None,
        "converged": False, "solver_id": "xfoil_python",
    }]
    _write_test_dataset(root, rows)
    curate_airfoil_dataset(dataset_root=root)
    # All rows rejected → not promotion_ready → force required
    with pytest.raises(ValueError, match="not promotion-ready"):
        promote_airfoil_dataset(dataset_root=root, force=False)
    manifest = promote_airfoil_dataset(dataset_root=root, force=True)
    assert manifest["promotion_forced"] is True


def test_qc_duplicate_key_includes_ncrit(tmp_path):
    root = tmp_path / "ds"
    rows = [
        {
            "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
            "alpha_deg": 0.0, "reynolds": 1e6, "mach": 0.0, "ncrit": ncrit,
            "cl": 0.2, "cd": 0.01, "cm": -0.05, "cp_min": -0.5,
            "converged": True, "solver_id": "xfoil_python",
        }
        for ncrit in [7.0, 9.0, 11.0]
    ]
    _write_test_dataset(root, rows)

    report = run_airfoil_dataset_qc(dataset_root=root)

    assert report["passed"] is True
    assert not any("duplicate" in issue for issue in report["issues"])


def test_qc_duplicate_key_fails_when_ncrit_matches(tmp_path):
    root = tmp_path / "ds"
    rows = [
        {
            "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
            "alpha_deg": 0.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": 0.2, "cd": 0.01, "cm": -0.05, "cp_min": -0.5,
            "converged": True, "solver_id": "xfoil_python",
        },
        {
            "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
            "alpha_deg": 0.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": 0.21, "cd": 0.011, "cm": -0.05, "cp_min": -0.5,
            "converged": True, "solver_id": "xfoil_python",
        },
        {
            "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
            "alpha_deg": 2.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": 0.4, "cd": 0.012, "cm": -0.05, "cp_min": -0.8,
            "converged": True, "solver_id": "xfoil_python",
        },
    ]
    _write_test_dataset(root, rows)

    report = run_airfoil_dataset_qc(dataset_root=root)

    assert report["passed"] is False
    assert any("duplicate" in issue for issue in report["issues"])


def test_qc_fails_group_with_fewer_than_three_converged_rows(tmp_path):
    root = tmp_path / "ds"
    rows = [
        {
            "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
            "alpha_deg": alpha, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": 0.2 + 0.1 * alpha, "cd": 0.01, "cm": -0.05, "cp_min": -0.5,
            "converged": conv, "solver_id": "xfoil_python",
        }
        for alpha, conv in [(0.0, True), (2.0, True), (4.0, False)]
    ]
    _write_test_dataset(root, rows)

    report = run_airfoil_dataset_qc(dataset_root=root)

    assert report["passed"] is True
    assert report["per_group_coverage_failures"]
    assert report["issues"] == []
    assert any("fewer than 3 converged rows" in warning for warning in report["warnings"])


def test_curate_blocks_promotion_for_insufficient_group_coverage(tmp_path):
    root = tmp_path / "ds"
    rows = [
        {
            "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
            "alpha_deg": alpha, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": 0.2 + 0.1 * alpha, "cd": 0.01, "cm": -0.05, "cp_min": -0.5,
            "converged": conv, "solver_id": "xfoil_python",
        }
        for alpha, conv in [(0.0, True), (2.0, True), (4.0, False)]
    ]
    _write_test_dataset(root, rows)
    run_airfoil_dataset_qc(dataset_root=root)

    report = curate_airfoil_dataset(dataset_root=root)

    assert "insufficient_per_group_coverage" in report["promotion_blockers"]
    assert report["promotion_ready"] is False
    assert report["post_curation_coverage_failure_count"] == 1


def test_curate_allows_promotion_when_bad_group_fully_removed(tmp_path):
    root = tmp_path / "ds"
    rows = []
    for alpha in [0.0, 2.0, 4.0]:
        rows.append(
            {
                "airfoil_id": "good123", "airfoil_name": "Good", "source_file": "good.xlsx",
                "alpha_deg": alpha, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
                "cl": 0.2 + 0.1 * alpha, "cd": 0.01, "cm": -0.05, "cp_min": -0.5,
                "converged": True, "solver_id": "xfoil_python",
            }
        )
    for alpha in [0.0, 2.0, 4.0]:
        rows.append(
            {
                "airfoil_id": "bad123", "airfoil_name": "Bad", "source_file": "bad.xlsx",
                "alpha_deg": alpha, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
                "cl": None, "cd": None, "cm": None, "cp_min": None,
                "converged": False, "solver_id": "xfoil_python",
            }
        )
    _write_test_dataset(root, rows)

    qc_report = run_airfoil_dataset_qc(dataset_root=root)

    assert qc_report["passed"] is True
    assert qc_report["per_group_coverage_failures"]
    assert qc_report["issues"] == []
    assert any("fewer than 3 converged rows" in warning for warning in qc_report["warnings"])

    report = curate_airfoil_dataset(dataset_root=root)

    assert "insufficient_per_group_coverage" not in report["promotion_blockers"]
    assert report["promotion_ready"] is True
    assert report["post_curation_coverage_failure_count"] == 0


def test_qc_group_coverage_passes_with_three_converged_rows(tmp_path):
    root = tmp_path / "ds"
    rows = [
        {
            "airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
            "alpha_deg": alpha, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": 0.2 + 0.1 * alpha, "cd": 0.01, "cm": -0.05, "cp_min": -0.5,
            "converged": True, "solver_id": "xfoil_python",
        }
        for alpha in [0.0, 2.0, 4.0]
    ]
    _write_test_dataset(root, rows)

    report = run_airfoil_dataset_qc(dataset_root=root)

    assert report["passed"] is True
    assert report["per_group_coverage_failures"] == []
