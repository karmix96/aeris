"""
2D airfoil dataset promotion.

Mirrors promote_aero.py exactly — same promotion_manifest.json schema.
The ML layer requires promotion_manifest.json with
artifacts.curated_aero_dataset_csv pointing to the curated CSV.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def promote_airfoil_dataset(
    *,
    dataset_root: Path,
    force: bool = False,
) -> dict[str, Any]:
    """Promote a curated 2D airfoil dataset for ML use.

    Writes promotion_manifest.json following the same schema as the 3D
    promote_aero.py so the existing require_promoted_aero_dataset() gate
    works unchanged for 2D datasets.
    """
    dataset_root = dataset_root.expanduser().resolve()

    curation_report_path   = dataset_root / "curation_report.json"
    manifest_input_path    = dataset_root / "airfoil_dataset_manifest.json"
    promotion_manifest_path = dataset_root / "promotion_manifest.json"

    curation_report = _read_json(curation_report_path)
    dataset_manifest = _read_json(manifest_input_path)

    promotion_ready    = bool(curation_report.get("promotion_ready", False))
    promotion_blockers = list(curation_report.get("promotion_blockers", []) or [])

    if not promotion_ready and not force:
        raise ValueError(
            "Dataset is not promotion-ready. "
            f"Blockers: {promotion_blockers if promotion_blockers else ['unknown']}"
        )

    manifest: dict[str, Any] = {
        "dataset_root": str(dataset_root),
        "promoted_at_utc": _utc_now(),
        "promotion_ready_at_time_of_promotion": promotion_ready,
        "promotion_forced": bool(force),
        "promotion_blockers": promotion_blockers,
        "domain": "airfoil_2d",
        "source_reports": {
            "curation_report": str(curation_report_path),
            "dataset_manifest": str(manifest_input_path),
        },
        "qc_context": {
            "qc_preset_used": "airfoil_2d_default",
            "airfoil_qc_passed": curation_report.get("qc_passed"),
        },
        "curation_context": {
            "kept_rows":         curation_report.get("kept_rows"),
            "rejected_rows":     curation_report.get("rejected_rows"),
            "kept_airfoils":     curation_report.get("kept_airfoils"),
            "rejected_airfoils": curation_report.get("rejected_airfoils"),
            "rejection_reason_counts": curation_report.get("rejection_reason_counts", {}),
        },
        "artifacts": {
            # Same key as 3D — required by require_promoted_aero_dataset()
            "curated_aero_dataset_csv": curation_report.get("curated_airfoil_dataset_csv"),
        },
        "dataset_summary": {
            "dataset_name":    dataset_manifest.get("dataset_name"),
            "solver_id":       dataset_manifest.get("solver_id"),
            "n_airfoils":      dataset_manifest.get("n_airfoils"),
            "total_rows":      dataset_manifest.get("total_rows"),
            "converged_rows":  dataset_manifest.get("converged_rows"),
            "convergence_rate": dataset_manifest.get("convergence_rate"),
        },
    }

    _write_json(promotion_manifest_path, manifest)
    return manifest
