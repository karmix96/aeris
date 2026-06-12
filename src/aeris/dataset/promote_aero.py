from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def promote_aero_dataset(
    *,
    dataset_root: Path,
    force: bool = False,
) -> dict[str, Any]:
    dataset_root = dataset_root.expanduser().resolve()

    curation_report_path = dataset_root / "curation_report.json"
    final_summary_path = dataset_root / "final_run_summary.json"
    promotion_manifest_path = dataset_root / "promotion_manifest.json"

    curation_report = _read_json(curation_report_path)

    # PROM-1: validate curated CSV exists and is non-empty before promotion.
    # Prevents promoting a dataset where curation wrote an empty CSV.
    _curated_csv_value = (curation_report.get("artifacts") or {}).get("curated_aero_dataset_csv") or curation_report.get("curated_aero_dataset_csv")
    if _curated_csv_value:
        _curated_csv_path = Path(_curated_csv_value).expanduser().resolve()
        if not _curated_csv_path.exists():
            raise FileNotFoundError(
                f"Curated dataset CSV referenced in curation_report.json does not exist: {_curated_csv_path}. "
                "Re-run curate-aero before promoting."
            )
        import pandas as _pd
        try:
            _df_check = _pd.read_csv(_curated_csv_path, nrows=1)
            if _df_check.empty:
                raise ValueError(f"Curated dataset CSV is empty: {_curated_csv_path}")
        except Exception as _e:
            if not force:
                raise ValueError(
                    f"Cannot promote: curated CSV validation failed ({_e}). Use --force to override."
                ) from _e
    final_summary = _read_json_if_exists(final_summary_path) or {}

    promotion_ready = bool(curation_report.get("promotion_ready", False))
    promotion_blockers = list(curation_report.get("promotion_blockers", []) or [])

    if not promotion_ready and not force:
        raise ValueError(
            "Dataset is not promotion-ready. "
            f"Blockers: {promotion_blockers if promotion_blockers else ['unknown']}"
        )

    manifest = {
        "schema_version": "aero_promotion_manifest_v1",
        "dataset_root": str(dataset_root),
        "promoted_at_utc": _utc_now_iso(),
        "promotion_ready_at_time_of_promotion": promotion_ready,
        "promotion_forced": bool(force),
        "promotion_blockers": promotion_blockers,
        "source_reports": {
            "curation_report": str(curation_report_path),
            "final_run_summary": str(final_summary_path),
        },
        "qc_context": {
            "qc_preset_used": curation_report.get("qc_preset_used"),
            "geometry_qc_passed": curation_report.get("geometry_qc_passed"),
            "aero_qc_passed": curation_report.get("aero_qc_passed"),
        },
        "curation_context": {
            "kept_rows": curation_report.get("kept_rows"),
            "rejected_rows": curation_report.get("rejected_rows"),
            "kept_geometries": curation_report.get("kept_geometries"),
            "rejected_geometries": curation_report.get("rejected_geometries"),
            "rejection_reason_counts": curation_report.get("rejection_reason_counts", {}),
        },
        "artifacts": {
            "curated_aero_dataset_csv": curation_report.get("curated_aero_dataset_csv"),
            "rejected_aero_rows_csv": curation_report.get("rejected_aero_rows_csv"),
        },
        "final_summary_snapshot": {
            "dataset_name": final_summary.get("dataset_name"),
            "config_path": final_summary.get("config_path"),
            "generator_id": final_summary.get("generator_id"),
            "solver": final_summary.get("solver"),
            "final_status": final_summary.get("final_status"),
            "exit_code": final_summary.get("exit_code"),
        },
    }

    _write_json(promotion_manifest_path, manifest)
    return manifest