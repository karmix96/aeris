from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from aeris.dataset.promoted_dataset import require_promoted_aero_dataset

FlyabilitySource = Literal["curated", "raw"]

DEFAULT_GROUP_COLUMNS = [
    "geometry_id",
    "alpha_deg",
    "beta_deg",
    "velocity_mps",
    "altitude_m",
    "p_rad_s",
    "q_rad_s",
    "r_rad_s",
]

PREFERRED_CONTROL_COLUMNS = ["delta_e_sym_deg", "control_input_deg"]

LABEL_TARGET_COLUMNS = [
    "Cm_delta_e_per_rad",
    "trim_delta_e_required_deg",
    "trim_delta_e_abs_required_deg",
    "trim_delta_e_margin_to_limit_deg",
    "trim_delta_e_feasible",
    "longitudinal_basic_flyable",
    "red_flag",
    "label_pitch_authority_ok",
    "label_trim_delta_e_feasible",
    "label_longitudinal_basic_flyable",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _select_control_column(df: pd.DataFrame) -> str:
    for col in PREFERRED_CONTROL_COLUMNS:
        if col in df.columns:
            return col
    raise ValueError(
        "Could not find a symmetric elevon control column. Expected one of: "
        + ", ".join(PREFERRED_CONTROL_COLUMNS)
    )


def _resolve_aero_csv(
    *,
    dataset_root: Path,
    source: FlyabilitySource,
    allow_forced: bool,
) -> tuple[Path, dict[str, Any] | None]:
    if source == "curated":
        context = require_promoted_aero_dataset(
            dataset_root=dataset_root,
            allow_forced=allow_forced,
        )
        return Path(context["curated_aero_dataset_csv"]).expanduser().resolve(), context

    if source == "raw":
        path = dataset_root / "aero_dataset.csv"
        if not path.exists():
            raise FileNotFoundError(f"Raw aero dataset CSV not found: {path}")
        return path.resolve(), None

    raise ValueError(f"Unsupported source: {source!r}. Use 'curated' or 'raw'.")


def _coerce_booleans_for_ml(df: pd.DataFrame) -> pd.DataFrame:
    """Add numeric aliases for boolean labels without deleting the human-readable columns."""
    out = df.copy()
    bool_candidates = [
        "trim_delta_e_feasible",
        "longitudinal_basic_flyable",
        "red_flag",
        "label_pitch_authority_ok",
        "label_trim_delta_e_feasible",
        "label_longitudinal_basic_flyable",
    ]
    for col in bool_candidates:
        if col not in out.columns:
            continue
        numeric_col = f"{col}_int"
        # Handles bool dtype and string True/False from CSV roundtrips.
        out[numeric_col] = out[col].map(
            {
                True: 1,
                False: 0,
                "True": 1,
                "False": 0,
                "true": 1,
                "false": 0,
                1: 1,
                0: 0,
            }
        )
    return out


def build_flyability_ml_dataset(
    *,
    dataset_root: Path,
    source: FlyabilitySource = "curated",
    output_dir: Path | None = None,
    allow_forced: bool = False,
    zero_control_value_deg: float = 0.0,
    zero_control_tolerance_deg: float = 1.0e-9,
) -> dict[str, Any]:
    """Build a promoted ML-ready table by joining aero zero-control rows with flyability labels.

    The output is intentionally shaped like a promoted AERIS dataset root so existing
    ``aeris ml train/compare/tune`` commands can consume it without special cases.

    Boundary:
    - This does not recompute aerodynamics.
    - This does not recompute flyability labels.
    - This does not claim full nonlinear trim or MIL-STD compliance.
    """
    dataset_root = Path(dataset_root).expanduser().resolve()
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")

    aero_csv, promotion_context = _resolve_aero_csv(
        dataset_root=dataset_root,
        source=source,
        allow_forced=allow_forced,
    )

    labels_csv = dataset_root / "flyability_labels.csv"
    labels_report_path = dataset_root / "flyability_labels_report.json"
    batch_report_path = dataset_root / "dynamics_label_run_report.json"
    control_derivatives_csv = dataset_root / "control_derivatives.csv"
    control_derivatives_report_path = dataset_root / "control_derivatives_report.json"

    if not labels_csv.exists():
        raise FileNotFoundError(
            f"Missing flyability labels: {labels_csv}. Run: "
            f"aeris dynamics batch-labels --dataset {dataset_root} --source {source}"
        )

    aero_df = pd.read_csv(aero_csv)
    labels_df = pd.read_csv(labels_csv)

    if aero_df.empty:
        raise ValueError(f"Aero CSV is empty: {aero_csv}")
    if labels_df.empty:
        raise ValueError(f"Flyability labels CSV is empty: {labels_csv}")

    group_columns = [c for c in DEFAULT_GROUP_COLUMNS if c in aero_df.columns and c in labels_df.columns]
    missing_required = [c for c in ("geometry_id", "alpha_deg") if c not in group_columns]
    if missing_required:
        raise ValueError(
            "Cannot join flyability labels to aero rows. Missing required join columns: "
            + ", ".join(missing_required)
        )

    control_column = _select_control_column(aero_df)
    aero_df[control_column] = pd.to_numeric(aero_df[control_column], errors="coerce")
    zero_mask = (aero_df[control_column] - float(zero_control_value_deg)).abs() <= float(
        zero_control_tolerance_deg
    )
    zero_df = aero_df.loc[zero_mask].copy()
    if zero_df.empty:
        raise ValueError(
            f"No zero-control aero rows found using {control_column} ~= {zero_control_value_deg} deg."
        )

    duplicate_zero_count = int(zero_df.duplicated(subset=group_columns, keep="first").sum())
    zero_df = zero_df.drop_duplicates(subset=group_columns, keep="first").copy()

    # Keep label columns authoritative on conflicts. Add aero geometry/condition/source columns
    # only when they do not already exist in the labels frame.
    aero_payload_columns = list(group_columns) + [
        c for c in aero_df.columns if c not in labels_df.columns and c not in group_columns
    ]
    merged = labels_df.merge(
        zero_df[aero_payload_columns],
        on=group_columns,
        how="left",
        validate="one_to_one",
    )

    # Rows without a matching zero-control aero row are not ML-ready.
    base_marker_columns = [c for c in ("cl", "cd", "cm", control_column) if c in merged.columns]
    if base_marker_columns:
        matched_mask = merged[base_marker_columns].notna().any(axis=1)
    else:
        # Fallback: use presence of any aero-only payload column.
        aero_only_columns = [c for c in aero_payload_columns if c not in group_columns]
        matched_mask = merged[aero_only_columns].notna().any(axis=1) if aero_only_columns else pd.Series(True, index=merged.index)

    unmatched_label_rows = int((~matched_mask).sum())
    ml_df = merged.loc[matched_mask].copy()
    ml_df = _coerce_booleans_for_ml(ml_df)

    if ml_df.empty:
        raise ValueError("No ML-ready rows remain after joining flyability labels to zero-control aero rows.")

    if output_dir is None:
        output_dir = dataset_root.parent / f"{dataset_root.name}__flyability_ml"
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    curated_out = output_dir / "curated_aero_dataset.csv"
    alias_out = output_dir / "flyability_ml_dataset.csv"
    report_out = output_dir / "flyability_ml_dataset_report.json"
    promotion_out = output_dir / "promotion_manifest.json"
    curation_out = output_dir / "curation_report.json"
    final_summary_out = output_dir / "final_run_summary.json"

    ml_df.to_csv(curated_out, index=False)
    ml_df.to_csv(alias_out, index=False)

    target_columns_available = [c for c in LABEL_TARGET_COLUMNS if c in ml_df.columns]
    numeric_target_aliases = [
        c for c in ml_df.columns if c.endswith("_int") and c.replace("_int", "") in LABEL_TARGET_COLUMNS
    ]

    labels_report = _read_json_if_exists(labels_report_path)
    batch_report = _read_json_if_exists(batch_report_path)
    control_report = _read_json_if_exists(control_derivatives_report_path)

    status = "completed" if unmatched_label_rows == 0 else "completed_with_warnings"
    report = {
        "schema_version": "dynamics_flyability_ml_dataset_v0.1",
        "created_at_utc": _utc_now(),
        "status": status,
        "dataset_root": str(dataset_root),
        "source": source,
        "source_aero_csv": str(aero_csv),
        "source_flyability_labels_csv": str(labels_csv.resolve()),
        "source_control_derivatives_csv": str(control_derivatives_csv.resolve()) if control_derivatives_csv.exists() else None,
        "output_dir": str(output_dir),
        "output_curated_csv": str(curated_out),
        "output_alias_csv": str(alias_out),
        "promotion_manifest": str(promotion_out),
        "row_counts": {
            "source_aero_rows": int(len(aero_df)),
            "source_zero_control_rows": int(len(zero_df)),
            "source_label_rows": int(len(labels_df)),
            "joined_ml_rows": int(len(ml_df)),
            "unmatched_label_rows": unmatched_label_rows,
            "duplicate_zero_control_rows_dropped": duplicate_zero_count,
        },
        "join": {
            "group_columns": list(group_columns),
            "control_column": control_column,
            "zero_control_value_deg": float(zero_control_value_deg),
            "zero_control_tolerance_deg": float(zero_control_tolerance_deg),
        },
        "ml_columns": {
            "feature_candidates": [
                c for c in [
                    "c1_m",
                    "b_total_m",
                    "sw1_deg",
                    "alpha_deg",
                    "velocity_mps",
                    "altitude_m",
                    "control_input_deg",
                    "delta_e_sym_deg",
                ] if c in ml_df.columns
            ],
            "label_targets_available": target_columns_available,
            "numeric_label_target_aliases": numeric_target_aliases,
        },
        "source_report_summaries": {
            "flyability_labels": {
                "computed_label_count": (labels_report or {}).get("computed_label_count"),
                "red_flag_count": (labels_report or {}).get("red_flag_count"),
                "red_flag_reason_counts": (labels_report or {}).get("red_flag_reason_counts"),
                "trim_failure_reason_counts": (labels_report or {}).get("trim_failure_reason_counts"),
            },
            "dynamics_batch": {
                "overall_status": (batch_report or {}).get("overall_status"),
                "label_summary": (batch_report or {}).get("label_summary"),
            },
            "control_derivatives": {
                "computed_group_count": (control_report or {}).get("computed_group_count"),
                "pitch_authority_counts": (control_report or {}).get("pitch_authority_counts"),
            },
        },
        "hashes": {
            "source_aero_csv_sha256": _file_sha256(aero_csv),
            "source_flyability_labels_csv_sha256": _file_sha256(labels_csv),
            "output_curated_csv_sha256": _file_sha256(curated_out),
        },
        "limitations": [
            "derived_dataset_not_new_solver_execution",
            "one_row_per_geometry_condition_group_using_zero_symmetric_elevon_row",
            "classification_labels_are_exported_as_boolean_and_numeric_int_aliases",
            "not_a_full_nonlinear_trim_solver",
            "not_a_mil_std_compliance_claim",
        ],
    }
    _write_json(report_out, report)

    curation_report = {
        "schema_version": "dynamics_flyability_ml_curation_v0.1",
        "created_at_utc": report["created_at_utc"],
        "source_dataset_root": str(dataset_root),
        "kept_rows": int(len(ml_df)),
        "rejected_rows": int(unmatched_label_rows),
        "promotion_ready": True,
        "promotion_blockers": [],
        "artifacts": {
            "curated_aero_dataset_csv": str(curated_out),
            "flyability_ml_dataset_csv": str(alias_out),
            "report_json": str(report_out),
        },
    }
    _write_json(curation_out, curation_report)

    final_summary = {
        "schema_version": "dynamics_flyability_ml_final_summary_v0.1",
        "created_at_utc": report["created_at_utc"],
        "dataset_name": output_dir.name,
        "dataset_type": "flyability_ml",
        "final_status": status,
        "source_dataset_root": str(dataset_root),
        "row_count": int(len(ml_df)),
        "artifacts": {
            "curated_aero_dataset_csv": str(curated_out),
            "flyability_ml_dataset_csv": str(alias_out),
            "flyability_ml_dataset_report_json": str(report_out),
        },
    }
    _write_json(final_summary_out, final_summary)

    promotion_manifest = {
        "schema_version": "dynamics_flyability_ml_promotion_manifest_v0.1",
        "created_at_utc": report["created_at_utc"],
        "promotion_ready_at_time_of_promotion": True,
        "promotion_forced": False,
        "qc_preset_used": "derived_from_promoted_aero_dataset" if source == "curated" else "derived_from_raw_aero_dataset",
        "geometry_qc_passed": None,
        "aero_qc_passed": None,
        "promotion_blockers": [],
        "source_dataset_root": str(dataset_root),
        "source_promotion_manifest_path": None if promotion_context is None else promotion_context.get("promotion_manifest_path"),
        "source_curated_aero_dataset_csv": None if promotion_context is None else promotion_context.get("curated_aero_dataset_csv"),
        "derived_product": "flyability_ml_dataset",
        "artifacts": {
            "curated_aero_dataset_csv": str(curated_out),
            "flyability_ml_dataset_csv": str(alias_out),
            "flyability_ml_dataset_report_json": str(report_out),
            "curation_report_json": str(curation_out),
            "final_run_summary_json": str(final_summary_out),
        },
        "limitations": report["limitations"],
    }
    _write_json(promotion_out, promotion_manifest)

    report["artifacts"] = {
        "curated_aero_dataset_csv": str(curated_out),
        "flyability_ml_dataset_csv": str(alias_out),
        "flyability_ml_dataset_report_json": str(report_out),
        "promotion_manifest_json": str(promotion_out),
        "curation_report_json": str(curation_out),
        "final_run_summary_json": str(final_summary_out),
    }
    _write_json(report_out, report)
    return report
