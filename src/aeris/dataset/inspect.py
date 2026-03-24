"""
Inspection and quality checks for persisted AERIS datasets.

This module reads an existing dataset folder, validates expected structure,
checks metadata completeness and artifact-path integrity, and returns a compact
summary suitable for CLI inspection and operator-facing QC.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from aeris.dataset.metadata import failure_fieldnames, metadata_fieldnames


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def inspect_dataset(dataset_root: Path) -> dict[str, Any]:
    dataset_root = dataset_root.expanduser().resolve()

    manifest_path = dataset_root / "dataset_manifest.json"
    metadata_path = dataset_root / "metadata.csv"
    failures_path = dataset_root / "failures.csv"
    geometry_dir = dataset_root / "geometry"

    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata CSV: {metadata_path}")
    if not geometry_dir.exists():
        raise FileNotFoundError(f"Missing geometry directory: {geometry_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = pd.read_csv(metadata_path)
    failures = pd.read_csv(failures_path) if failures_path.exists() else pd.DataFrame()

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
        "metrics": {
            "full_span_m": {
                "min": _safe_float(metadata["full_span_m"].min()) if "full_span_m" in metadata else None,
                "max": _safe_float(metadata["full_span_m"].max()) if "full_span_m" in metadata else None,
                "mean": _safe_float(metadata["full_span_m"].mean()) if "full_span_m" in metadata else None,
            },
            "approx_area_m2": {
                "min": _safe_float(metadata["approx_area_m2"].min()) if "approx_area_m2" in metadata else None,
                "max": _safe_float(metadata["approx_area_m2"].max()) if "approx_area_m2" in metadata else None,
                "mean": _safe_float(metadata["approx_area_m2"].mean()) if "approx_area_m2" in metadata else None,
            },
            "approx_aspect_ratio_planform": {
                "min": _safe_float(metadata["approx_aspect_ratio_planform"].min())
                if "approx_aspect_ratio_planform" in metadata else None,
                "max": _safe_float(metadata["approx_aspect_ratio_planform"].max())
                if "approx_aspect_ratio_planform" in metadata else None,
                "mean": _safe_float(metadata["approx_aspect_ratio_planform"].mean())
                if "approx_aspect_ratio_planform" in metadata else None,
            },
            "aspect_ratio_aerosandbox": {
                "min": _safe_float(metadata["aspect_ratio_aerosandbox"].min())
                if "aspect_ratio_aerosandbox" in metadata else None,
                "max": _safe_float(metadata["aspect_ratio_aerosandbox"].max())
                if "aspect_ratio_aerosandbox" in metadata else None,
                "mean": _safe_float(metadata["aspect_ratio_aerosandbox"].mean())
                if "aspect_ratio_aerosandbox" in metadata else None,
            },
        },
        "nan_counts": metadata.isna().sum().to_dict(),
    }

    return summary