from __future__ import annotations

import json
from pathlib import Path

from aeris.airfoil.promote import promote_airfoil_dataset


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_airfoil_promotion_manifest_has_domain_specific_artifact_and_cst_schema(tmp_path: Path) -> None:
    root = tmp_path / "airfoil_ds"
    root.mkdir()
    curated = root / "curated_airfoil_dataset.csv"
    curated.write_text("airfoil_id,cl,cd,cm\na,1,0.01,0\n", encoding="utf-8")

    _write_json(root / "curation_report.json", {
        "promotion_ready": True,
        "promotion_blockers": [],
        "qc_passed": True,
        "kept_rows": 1,
        "rejected_rows": 0,
        "kept_airfoils": 1,
        "rejected_airfoils": 0,
        "rejection_reason_counts": {},
        "curated_airfoil_dataset_csv": str(curated),
    })
    _write_json(root / "airfoil_dataset_manifest.json", {
        "dataset_name": "airfoil_ds",
        "solver_id": "xfoil_subprocess",
        "total_rows": 1,
        "converged_rows": 1,
        "convergence_rate": 1.0,
        "n_airfoils": 1,
        "airfoil_source_schema": {
            "has_cst_features": True,
            "generator_ids": ["cst_airfoil_v1"],
        },
    })

    manifest = promote_airfoil_dataset(dataset_root=root)
    artifacts = manifest["artifacts"]
    assert artifacts["curated_aero_dataset_csv"] == str(curated)
    assert artifacts["curated_airfoil_dataset_csv"] == str(curated)
    assert manifest["dataset_summary"]["airfoil_source_schema"]["has_cst_features"] is True
