"""
Inspection and quality checks for persisted AERIS datasets.

This module reads existing dataset folders and returns compact summaries for
operator-facing CLI inspection. It supports both geometry-only datasets and
unified aero datasets.

Supported dataset roots:
    - Geometry datasets with dataset_manifest.json + metadata.csv
    - Aero datasets with aero_dataset_manifest.json + aero_dataset.csv

The inspector is deliberately read-only. It does not run geometry generation,
aero solving, QC, curation, promotion, or ML. It only summarizes persisted
artifacts and flags obvious consistency problems.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError

from aeris.dataset.metadata import failure_fieldnames, metadata_fieldnames


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()


def _numeric_metric(df: pd.DataFrame, column: str) -> dict[str, float | None]:
    if column not in df.columns or df.empty:
        return {"min": None, "max": None, "mean": None}

    values = pd.to_numeric(df[column], errors="coerce")
    finite_values = values.dropna()
    if finite_values.empty:
        return {"min": None, "max": None, "mean": None}

    return {
        "min": _safe_float(finite_values.min()),
        "max": _safe_float(finite_values.max()),
        "mean": _safe_float(finite_values.mean()),
    }


def _unique_count(df: pd.DataFrame, column: str) -> int | None:
    if column not in df.columns or df.empty:
        return None
    return int(df[column].nunique(dropna=True))


def _known_count_match(expected: Any, actual: int) -> bool | None:
    expected_int = _safe_int(expected)
    if expected_int is None:
        return None
    return expected_int == int(actual)


def _all_known_checks_pass(checks: dict[str, bool | None]) -> bool:
    known_checks = [value for value in checks.values() if value is not None]
    if not known_checks:
        return True
    return all(bool(value) for value in known_checks)


def _inspect_geometry_dataset(dataset_root: Path) -> dict[str, Any]:
    manifest_path = dataset_root / "dataset_manifest.json"
    metadata_path = dataset_root / "metadata.csv"
    failures_path = dataset_root / "failures.csv"
    geometry_dir = dataset_root / "geometry"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata CSV: {metadata_path}")
    if not geometry_dir.exists():
        raise FileNotFoundError(f"Missing geometry directory: {geometry_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = pd.read_csv(metadata_path)
    failures = _read_csv_if_exists(failures_path)

    geometry_dirs = sorted([p for p in geometry_dir.iterdir() if p.is_dir()])

    required_columns = metadata_fieldnames()
    missing_columns = [c for c in required_columns if c not in metadata.columns]

    expected_failure_columns = failure_fieldnames()
    missing_failure_columns = [
        c for c in expected_failure_columns if not failures.empty and c not in failures.columns
    ]

    duplicate_geometry_ids = []
    if "geometry_id" in metadata.columns:
        duplicate_geometry_ids = (
            metadata["geometry_id"][metadata["geometry_id"].duplicated()].astype(str).tolist()
        )

    missing_files: list[dict[str, str]] = []
    for _, row in metadata.iterrows():
        geometry_id = str(row.get("geometry_id", "UNKNOWN"))

        for col in [
            "summary_path",
            "control_points_path",
            "planform_sections_path",
            "section_3d_path",
        ]:
            value = row.get(col)
            if pd.isna(value):
                missing_files.append({"geometry_id": geometry_id, "kind": col, "path": "NaN"})
            else:
                p = Path(str(value))
                if not p.exists():
                    missing_files.append({"geometry_id": geometry_id, "kind": col, "path": str(p)})

        plot_value = row.get("plot_path")
        if not pd.isna(plot_value):
            plot_path = Path(str(plot_value))
            if not plot_path.exists():
                missing_files.append(
                    {"geometry_id": geometry_id, "kind": "plot_path", "path": str(plot_path)}
                )

    metadata_rows = int(len(metadata))
    failure_rows = int(len(failures))
    geometry_dir_count = int(len(geometry_dirs))

    requested_n = manifest.get("requested_n")
    attempted_n = manifest.get("attempted_n")
    succeeded_n = manifest.get("succeeded_n")
    failed_n = manifest.get("failed_n")

    count_consistency = {
        "manifest_succeeded_matches_metadata_rows": succeeded_n == metadata_rows,
        "manifest_failed_matches_failure_rows": failed_n == failure_rows,
        "manifest_attempted_matches_success_plus_failure": attempted_n == (metadata_rows + failure_rows),
        "manifest_requested_matches_attempted": requested_n == attempted_n,
        "geometry_dir_count_matches_metadata_rows": geometry_dir_count == metadata_rows,
    }

    summary = {
        "dataset_type": "geometry",
        "dataset_root": str(dataset_root),
        "manifest_status": manifest.get("status"),
        "requested_n": requested_n,
        "attempted_n": attempted_n,
        "succeeded_n": succeeded_n,
        "failed_n": failed_n,
        "sampler_id": manifest.get("sampler_id"),
        "sampler_seed": manifest.get("sampler_seed"),
        "metadata_rows": metadata_rows,
        "failure_rows": failure_rows,
        "geometry_dir_count": geometry_dir_count,
        "missing_columns": missing_columns,
        "missing_failure_columns": missing_failure_columns,
        "duplicate_geometry_ids": duplicate_geometry_ids,
        "missing_file_count": len(missing_files),
        "missing_files_preview": missing_files[:20],
        "count_consistency": count_consistency,
        "all_count_checks_pass": all(count_consistency.values()),
        "available_artifacts": {
            "dataset_manifest_json": str(manifest_path) if manifest_path.exists() else None,
            "metadata_csv": str(metadata_path) if metadata_path.exists() else None,
            "failures_csv": str(failures_path) if failures_path.exists() else None,
            "geometry_dir": str(geometry_dir) if geometry_dir.exists() else None,
        },
        "metrics": {
            "full_span_m": _numeric_metric(metadata, "full_span_m"),
            "approx_area_m2": _numeric_metric(metadata, "approx_area_m2"),
            "approx_aspect_ratio_planform": _numeric_metric(metadata, "approx_aspect_ratio_planform"),
            "aspect_ratio_aerosandbox": _numeric_metric(metadata, "aspect_ratio_aerosandbox"),
        },
        "nan_counts": metadata.isna().sum().to_dict(),
    }

    return summary


def _inspect_aero_dataset(dataset_root: Path) -> dict[str, Any]:
    manifest_path = dataset_root / "aero_dataset_manifest.json"
    final_summary_path = dataset_root / "final_run_summary.json"
    aero_dataset_path = dataset_root / "aero_dataset.csv"
    aero_failures_path = dataset_root / "aero_failures.csv"
    curated_dataset_path = dataset_root / "curated_aero_dataset.csv"
    rejected_rows_path = dataset_root / "rejected_aero_rows.csv"
    curation_report_path = dataset_root / "curation_report.json"
    promotion_manifest_path = dataset_root / "promotion_manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing aero dataset manifest: {manifest_path}")
    if not aero_dataset_path.exists():
        raise FileNotFoundError(f"Missing aero dataset CSV: {aero_dataset_path}")

    manifest = _read_json_if_exists(manifest_path) or {}
    final_summary = _read_json_if_exists(final_summary_path) or {}
    curation_report = _read_json_if_exists(curation_report_path)
    promotion_manifest = _read_json_if_exists(promotion_manifest_path)

    aero_df = _read_csv_if_exists(aero_dataset_path)
    failures_df = _read_csv_if_exists(aero_failures_path)
    curated_df = _read_csv_if_exists(curated_dataset_path)
    rejected_df = _read_csv_if_exists(rejected_rows_path)

    aero_rows = int(len(aero_df))
    failure_rows = int(len(failures_df))
    curated_rows = int(len(curated_df)) if curated_dataset_path.exists() else None
    rejected_rows = int(len(rejected_df)) if rejected_rows_path.exists() else None

    unique_geometry_count = _unique_count(aero_df, "geometry_id")
    failed_geometry_count = _unique_count(failures_df, "geometry_id")
    curated_geometry_count = _unique_count(curated_df, "geometry_id") if curated_dataset_path.exists() else None
    rejected_geometry_count = _unique_count(rejected_df, "geometry_id") if rejected_rows_path.exists() else None

    count_consistency = {
        "manifest_successful_matches_aero_rows": _known_count_match(
            manifest.get("successful_aero_rows"), aero_rows
        ),
        "manifest_failed_matches_failure_rows": _known_count_match(
            manifest.get("failed_aero_rows"), failure_rows
        ),
        "final_summary_successful_matches_aero_rows": _known_count_match(
            final_summary.get("successful_aero_rows"), aero_rows
        ),
        "final_summary_failed_matches_failure_rows": _known_count_match(
            final_summary.get("failed_aero_rows"), failure_rows
        ),
        "curation_kept_matches_curated_rows": (
            _known_count_match(curation_report.get("kept_rows"), curated_rows)
            if curation_report is not None and curated_rows is not None
            else None
        ),
        "curation_rejected_matches_rejected_rows": (
            _known_count_match(curation_report.get("rejected_rows"), rejected_rows)
            if curation_report is not None and rejected_rows is not None
            else None
        ),
        "promotion_kept_matches_curated_rows": (
            _known_count_match(
                ((promotion_manifest.get("curation_context") or {}).get("kept_rows")),
                curated_rows,
            )
            if promotion_manifest is not None and curated_rows is not None
            else None
        ),
    }

    condition_columns = [
        "alpha_deg",
        "beta_deg",
        "velocity_mps",
        "altitude_m",
        "p_rad_s",
        "q_rad_s",
        "r_rad_s",
        "control_input_deg",
    ]
    target_columns = ["cl", "cd", "cm", "cy", "cl_roll", "cn", "l_over_d"]

    available_artifacts = {
        "aero_dataset_manifest_json": str(manifest_path) if manifest_path.exists() else None,
        "final_run_summary_json": str(final_summary_path) if final_summary_path.exists() else None,
        "aero_dataset_csv": str(aero_dataset_path) if aero_dataset_path.exists() else None,
        "aero_failures_csv": str(aero_failures_path) if aero_failures_path.exists() else None,
        "curated_aero_dataset_csv": str(curated_dataset_path) if curated_dataset_path.exists() else None,
        "rejected_aero_rows_csv": str(rejected_rows_path) if rejected_rows_path.exists() else None,
        "curation_report_json": str(curation_report_path) if curation_report_path.exists() else None,
        "promotion_manifest_json": str(promotion_manifest_path) if promotion_manifest_path.exists() else None,
    }

    missing_core_artifacts = [
        name
        for name in ["aero_dataset_manifest_json", "aero_dataset_csv"]
        if available_artifacts.get(name) is None
    ]

    qc_from_manifest = manifest.get("aero_qc") or {}
    geometry_qc_from_manifest = manifest.get("geometry_qc") or {}
    promotion_qc = (promotion_manifest or {}).get("qc_context") or {}
    promotion_curation = (promotion_manifest or {}).get("curation_context") or {}

    summary = {
        "dataset_type": "aero",
        "dataset_root": str(dataset_root),
        "manifest_status": manifest.get("status"),
        "final_status": final_summary.get("final_status"),
        "dataset_name": manifest.get("dataset_name") or final_summary.get("dataset_name"),
        "config_path": manifest.get("config_path") or final_summary.get("config_path"),
        "generator_id": manifest.get("generator_id") or final_summary.get("generator_id"),
        "solver": manifest.get("solver") or final_summary.get("solver"),
        "requested_geometry_n": manifest.get("requested_geometry_n") or final_summary.get("requested_geometry_n"),
        "attempted_geometry_sweeps": manifest.get("attempted_geometry_sweeps")
        or final_summary.get("attempted_geometry_sweeps"),
        "completed_geometry_sweeps": manifest.get("completed_geometry_sweeps")
        or final_summary.get("completed_geometry_sweeps"),
        "successful_aero_rows": manifest.get("successful_aero_rows"),
        "failed_aero_rows": manifest.get("failed_aero_rows"),
        "aero_dataset_rows": aero_rows,
        "aero_failure_rows": failure_rows,
        "curated_rows": curated_rows,
        "rejected_rows": rejected_rows,
        "unique_geometry_count": unique_geometry_count,
        "failed_geometry_count": failed_geometry_count,
        "curated_geometry_count": curated_geometry_count,
        "rejected_geometry_count": rejected_geometry_count,
        "available_artifacts": available_artifacts,
        "missing_core_artifacts": missing_core_artifacts,
        "count_consistency": count_consistency,
        "all_count_checks_pass": _all_known_checks_pass(count_consistency) and not missing_core_artifacts,
        "qc": {
            "qc_preset": final_summary.get("qc_preset")
            or (curation_report or {}).get("qc_preset_used")
            or promotion_qc.get("qc_preset_used"),
            "geometry_qc_passed": geometry_qc_from_manifest.get("passed")
            if isinstance(geometry_qc_from_manifest, dict)
            else None,
            "aero_qc_passed": qc_from_manifest.get("passed")
            if isinstance(qc_from_manifest, dict)
            else None,
            "curation_geometry_qc_passed": (curation_report or {}).get("geometry_qc_passed"),
            "curation_aero_qc_passed": (curation_report or {}).get("aero_qc_passed"),
            "promotion_geometry_qc_passed": promotion_qc.get("geometry_qc_passed"),
            "promotion_aero_qc_passed": promotion_qc.get("aero_qc_passed"),
        },
        "curation": {
            "exists": curation_report is not None,
            "promotion_ready": (curation_report or {}).get("promotion_ready"),
            "promotion_blockers": (curation_report or {}).get("promotion_blockers", []),
            "kept_rows": (curation_report or {}).get("kept_rows"),
            "rejected_rows": (curation_report or {}).get("rejected_rows"),
            "kept_geometries": (curation_report or {}).get("kept_geometries"),
            "rejected_geometries": (curation_report or {}).get("rejected_geometries"),
            "rejection_reason_counts": (curation_report or {}).get("rejection_reason_counts", {}),
        },
        "promotion": {
            "exists": promotion_manifest is not None,
            "promotion_forced": (promotion_manifest or {}).get("promotion_forced"),
            "promotion_ready_at_time_of_promotion": (promotion_manifest or {}).get(
                "promotion_ready_at_time_of_promotion"
            ),
            "promotion_blockers": (promotion_manifest or {}).get("promotion_blockers", []),
            "kept_rows": promotion_curation.get("kept_rows"),
            "rejected_rows": promotion_curation.get("rejected_rows"),
        },
        "flight_condition_unique_counts": {
            column: _unique_count(aero_df, column) for column in condition_columns if column in aero_df.columns
        },
        "target_metrics": {
            column: _numeric_metric(aero_df, column) for column in target_columns if column in aero_df.columns
        },
        "nan_counts": aero_df.isna().sum().to_dict(),
    }

    return summary


def inspect_dataset(dataset_root: Path) -> dict[str, Any]:
    """Inspect a persisted AERIS dataset root.

    The function auto-detects the dataset family from its manifest/CSV files:
    aero datasets take precedence over geometry datasets because unified aero
    datasets may also retain an intermediate geometry dataset.
    """
    dataset_root = dataset_root.expanduser().resolve()

    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")

    has_aero_manifest = (dataset_root / "aero_dataset_manifest.json").exists()
    has_aero_csv = (dataset_root / "aero_dataset.csv").exists()
    has_geometry_manifest = (dataset_root / "dataset_manifest.json").exists()

    if has_aero_manifest or has_aero_csv:
        return _inspect_aero_dataset(dataset_root)

    if has_geometry_manifest:
        return _inspect_geometry_dataset(dataset_root)

    raise FileNotFoundError(
        "Dataset root is not recognized as an AERIS geometry or aero dataset. "
        "Expected dataset_manifest.json or aero_dataset_manifest.json/aero_dataset.csv under: "
        f"{dataset_root}"
    )
