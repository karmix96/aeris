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


def _good_rows():
    return [
        {"airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
         "alpha_deg": 0.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
         "cl": 0.2, "cd": 0.01, "cm": -0.05, "cp_min": -0.5,
         "converged": True, "solver_id": "xfoil_python"},
        {"airfoil_id": "abc123", "airfoil_name": "A", "source_file": "a.xlsx",
         "alpha_deg": 2.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
         "cl": 0.4, "cd": 0.012, "cm": -0.05, "cp_min": -0.8,
         "converged": True, "solver_id": "xfoil_python"},
        {"airfoil_id": "def456", "airfoil_name": "B", "source_file": "b.xlsx",
         "alpha_deg": 0.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
         "cl": 0.1, "cd": 0.009, "cm": -0.03, "cp_min": -0.3,
         "converged": True, "solver_id": "xfoil_python"},
    ]


def test_qc_passes_on_clean_dataset(tmp_path):
    root = tmp_path / "ds"
    _write_test_dataset(root, _good_rows())
    report = run_airfoil_dataset_qc(dataset_root=root)
    assert report["passed"] is True
    assert report["total_rows"] == 3
    assert report["converged_rows"] == 3
    assert report["issues"] == []


def test_curate_keeps_good_rows(tmp_path):
    root = tmp_path / "ds"
    _write_test_dataset(root, _good_rows())
    report = curate_airfoil_dataset(dataset_root=root)
    assert report["kept_rows"] == 3
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
    assert report["kept_rows"] == 3


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
