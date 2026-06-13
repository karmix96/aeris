"""Reporting helpers for generated CST/Kulfan airfoil libraries.

This module is intentionally small and post-processing oriented.  It does not
create new airfoils; it normalizes the generated AERIS airfoil-library contract
so operators and downstream pipelines see stable names:

- ``airfoil_name`` alias for inventory ``name``
- ``cst_json_path`` alias for inventory ``cst_json``
- ``coords_npz_path`` path to ``coords/<airfoil_id>.npz``
- manifest aliases ``generated_count`` / ``requested_count``
- compact ``library_report.json`` for quick inspection
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

CST_REPORTING_SCHEMA_VERSION = "aeris.cst_airfoil_library_report.v1"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _jsonable(value: Any) -> Any:
    try:
        import numpy as np
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            value = float(value)
    except Exception:
        pass
    if isinstance(value, float):
        if value != value:  # NaN
            return None
    return value


def _range_summary(df: pd.DataFrame, columns: list[str]) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for column in columns:
        if column not in df.columns:
            continue
        s = pd.to_numeric(df[column], errors="coerce")
        if s.dropna().empty:
            out[column] = {"min": None, "max": None, "mean": None}
        else:
            out[column] = {
                "min": _jsonable(float(s.min())),
                "max": _jsonable(float(s.max())),
                "mean": _jsonable(float(s.mean())),
            }
    return out



def _write_json_atomic(file_path, payload, *, default=None):
    """Atomic JSON write: temp-file + os.replace. AERIS_PATCH_C6_APPLIED."""
    import os
    import tempfile
    text = json.dumps(payload, indent=2, default=default)
    file_path = Path(file_path)
    tmp_fd, tmp_str = tempfile.mkstemp(dir=file_path.parent, prefix=f".{file_path.name}.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_str, file_path)
    except Exception:
        try:
            os.unlink(tmp_str)
        except OSError:
            pass
        raise


def polish_cst_library_outputs(output_dir: str | Path) -> dict[str, Any]:
    """Normalize CST library inventory/manifest/report artifacts.

    The function is idempotent: running it repeatedly updates the same files
    without duplicating rows or changing airfoil IDs.
    """
    root = Path(output_dir).expanduser().resolve()
    inventory_csv = root / "airfoil_inventory.csv"
    manifest_path = root / "cst_airfoil_library_manifest.json"
    ingest_report_path = root / "ingest_report.json"
    library_report_path = root / "library_report.json"

    if not inventory_csv.exists():
        raise FileNotFoundError(f"airfoil_inventory.csv not found: {inventory_csv}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"cst_airfoil_library_manifest.json not found: {manifest_path}")

    df = pd.read_csv(inventory_csv)

    # Stable, operator-friendly aliases.
    if "airfoil_name" not in df.columns and "name" in df.columns:
        df["airfoil_name"] = df["name"]
    if "cst_json_path" not in df.columns and "cst_json" in df.columns:
        df["cst_json_path"] = df["cst_json"]
    if "coords_npz_path" not in df.columns and "airfoil_id" in df.columns:
        df["coords_npz_path"] = [str(root / "coords" / f"{aid}.npz") for aid in df["airfoil_id"].astype(str)]

    # Keep useful path aliases physically valid when possible.
    if "dat_path" not in df.columns and "source_file" in df.columns:
        df["dat_path"] = [str(root / "dat" / str(name)) for name in df["source_file"]]

    df.to_csv(inventory_csv, index=False)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generated = int(manifest.get("n_airfoils_generated", len(df)))
    requested = int(manifest.get("n_airfoils_requested", generated))

    cst_coeff_cols = [c for c in df.columns if c.startswith("cst_u") or c.startswith("cst_l")]
    cst_feature_cols = [c for c in df.columns if c.startswith("cst_")]

    report: dict[str, Any] = {
        "schema_version": CST_REPORTING_SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "library_dir": str(root),
        "inventory_csv": str(inventory_csv),
        "manifest_json": str(manifest_path),
        "generator_id": manifest.get("generator_id", "cst_airfoil_v1"),
        "parameterization": "cst_kulfan",
        "requested_count": requested,
        "generated_count": generated,
        "inventory_rows": int(len(df)),
        "order": manifest.get("order"),
        "n1": manifest.get("n1"),
        "n2": manifest.get("n2"),
        "dz_te": manifest.get("dz_te"),
        "n_per_surface": manifest.get("n_per_surface"),
        "path_columns": [c for c in ["dat_path", "cst_json_path", "coords_npz_path"] if c in df.columns],
        "cst_feature_columns": cst_feature_cols,
        "cst_coefficient_columns": cst_coeff_cols,
        "coefficient_ranges": _range_summary(df, cst_coeff_cols),
        "geometry_metric_ranges": _range_summary(
            df,
            ["t_c", "camber_max", "le_radius", "te_angle_deg", "cst_t_max", "cst_area", "cst_r_le"],
        ),
        "validation": {
            "all_valid": bool(df["cst_validation_valid"].astype(bool).all()) if "cst_validation_valid" in df.columns else None,
            "n_invalid": int((~df["cst_validation_valid"].astype(bool)).sum()) if "cst_validation_valid" in df.columns else None,
        },
    }

    _write_json_atomic(library_report_path, report, default=_jsonable)

    manifest.update({
        # Alias fields: keep original n_* names but add quick-inspection names.
        "generated_count": generated,
        "requested_count": requested,
        "library_report_json": str(library_report_path),
        "inventory_schema": {
            "airfoil_name_column": "airfoil_name",
            "cst_json_path_column": "cst_json_path",
            "coords_npz_path_column": "coords_npz_path",
            "cst_feature_columns": cst_feature_cols,
            "cst_coefficient_columns": cst_coeff_cols,
        },
    })
    _write_json_atomic(manifest_path, manifest, default=_jsonable)
    _write_json_atomic(ingest_report_path, manifest, default=_jsonable)
    return manifest


def infer_airfoil_feature_preset_from_manifest(manifest: dict[str, Any] | None) -> str:
    """Suggest the best ML feature preset for an airfoil dataset manifest."""
    manifest = manifest or {}
    source_schema = manifest.get("airfoil_source_schema") or manifest.get("dataset_summary", {}).get("airfoil_source_schema") or {}
    if isinstance(source_schema, dict) and source_schema.get("has_cst_features"):
        return "airfoil_cst_xfoil_v1"
    return "airfoil_xfoil_v1"
