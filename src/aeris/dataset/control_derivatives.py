from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

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

DEFAULT_TARGET_COLUMNS = ["cl", "cd", "cm", "cy", "cl_roll", "cn"]
DEFAULT_SYMMETRIC_CONTROL_COLUMN = "delta_e_sym_deg"
LEGACY_CONTROL_COLUMN = "control_input_deg"
DIFFERENTIAL_CONTROL_COLUMN = "delta_a_diff_deg"

DERIVATIVE_NAME_BY_TARGET = {
    "cl": "CL_delta_e_per_rad",
    "cd": "CD_delta_e_per_rad",
    "cm": "Cm_delta_e_per_rad",
    "cy": "CY_delta_e_per_rad",
    "cl_roll": "Cl_delta_e_per_rad",
    "cn": "Cn_delta_e_per_rad",
}


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _pick_source_csv(dataset_root: Path, source: str) -> tuple[Path, str]:
    source_norm = source.strip().lower()
    if source_norm not in {"auto", "curated", "raw"}:
        raise ValueError("source must be one of: auto, curated, raw")

    curated = dataset_root / "curated_aero_dataset.csv"
    raw = dataset_root / "aero_dataset.csv"

    if source_norm == "curated":
        if not curated.exists():
            raise FileNotFoundError(f"Missing curated aero dataset: {curated}")
        return curated, "curated"

    if source_norm == "raw":
        if not raw.exists():
            raise FileNotFoundError(f"Missing raw aero dataset: {raw}")
        return raw, "raw"

    if curated.exists():
        return curated, "curated"
    if raw.exists():
        return raw, "raw"
    raise FileNotFoundError(
        f"Could not find curated_aero_dataset.csv or aero_dataset.csv under {dataset_root}"
    )


def _coerce_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _resolve_control_column(df: pd.DataFrame, requested: str | None) -> tuple[str, bool]:
    if requested:
        if requested not in df.columns:
            raise ValueError(f"Requested control column is missing: {requested}")
        return requested, False

    if DEFAULT_SYMMETRIC_CONTROL_COLUMN in df.columns:
        return DEFAULT_SYMMETRIC_CONTROL_COLUMN, False
    if LEGACY_CONTROL_COLUMN in df.columns:
        return LEGACY_CONTROL_COLUMN, True
    raise ValueError(
        "Missing symmetric control column. Expected delta_e_sym_deg or legacy control_input_deg."
    )


def _available_columns(df: pd.DataFrame, candidates: list[str]) -> list[str]:
    return [c for c in candidates if c in df.columns]


def _finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def _row_for_control(group: pd.DataFrame, control_column: str, value: float, *, tol: float) -> pd.Series | None:
    subset = group[(group[control_column] - value).abs() <= tol]
    if subset.empty:
        return None
    if len(subset) > 1:
        raise ValueError(
            f"Duplicate rows found for control {value} in group; cannot compute unique finite difference."
        )
    return subset.iloc[0]


def _central_delta_candidates(values: list[float], *, tol: float) -> list[float]:
    unique_abs = sorted({round(abs(v), 12) for v in values if abs(v) > tol})
    candidates: list[float] = []
    rounded_values = {round(v, 12) for v in values}
    for delta in unique_abs:
        if round(delta, 12) in rounded_values and round(-delta, 12) in rounded_values:
            candidates.append(float(delta))
    return candidates


def _group_key_row(group_key: tuple[Any, ...], group_columns: list[str]) -> dict[str, Any]:
    return {column: group_key[i] for i, column in enumerate(group_columns)}


def _compute_group_derivatives(
    *,
    group: pd.DataFrame,
    group_key: tuple[Any, ...],
    group_columns: list[str],
    control_column: str,
    target_columns: list[str],
    control_tol: float,
    min_abs_cm_delta_e: float,
) -> dict[str, Any]:
    values = sorted(float(v) for v in group[control_column].dropna().unique())
    candidates = _central_delta_candidates(values, tol=control_tol)

    row: dict[str, Any] = _group_key_row(group_key, group_columns)
    row["control_column"] = control_column
    row["available_control_values_deg"] = ",".join(f"{v:g}" for v in values)

    zero_row = _row_for_control(group, control_column, 0.0, tol=control_tol)
    row["has_zero_control_row"] = zero_row is not None

    if not candidates:
        row["status"] = "skipped"
        row["skip_reason"] = "missing_symmetric_positive_negative_control_pair"
        row["control_delta_deg"] = None
        row["control_delta_rad"] = None
        row["pitch_authority_adequate"] = None
        return row

    # Use the smallest available symmetric pair by default. This is the closest
    # thing to a local derivative in a discrete control sweep.
    delta_deg = float(candidates[0])
    pos = _row_for_control(group, control_column, delta_deg, tol=control_tol)
    neg = _row_for_control(group, control_column, -delta_deg, tol=control_tol)
    if pos is None or neg is None:  # defensive; candidates should prevent this
        row["status"] = "skipped"
        row["skip_reason"] = "control_pair_disappeared_after_filtering"
        row["control_delta_deg"] = delta_deg
        row["control_delta_rad"] = math.radians(delta_deg)
        row["pitch_authority_adequate"] = None
        return row

    delta_rad = math.radians(delta_deg)
    denominator = 2.0 * delta_rad

    row["status"] = "computed"
    row["skip_reason"] = None
    row["control_delta_deg"] = delta_deg
    row["control_delta_rad"] = delta_rad

    for target in target_columns:
        pos_value = _finite_float(pos.get(target))
        neg_value = _finite_float(neg.get(target))
        deriv_col = DERIVATIVE_NAME_BY_TARGET.get(target, f"{target}_delta_e_per_rad")
        if pos_value is None or neg_value is None:
            row[deriv_col] = None
            row[f"{target}_delta_e_status"] = "nonfinite_target_value"
            continue
        row[deriv_col] = (pos_value - neg_value) / denominator
        row[f"{target}_delta_e_status"] = "computed"

    cm_deriv = _finite_float(row.get("Cm_delta_e_per_rad"))
    row["min_abs_Cm_delta_e_per_rad"] = float(min_abs_cm_delta_e)
    row["pitch_authority_adequate"] = None if cm_deriv is None else abs(cm_deriv) >= min_abs_cm_delta_e
    return row


def compute_control_derivatives(
    *,
    dataset_root: Path,
    source: str = "auto",
    control_column: str | None = None,
    group_columns: list[str] | None = None,
    target_columns: list[str] | None = None,
    min_abs_cm_delta_e: float = 0.10,
    control_tol: float = 1e-8,
    output_csv_name: str = "control_derivatives.csv",
    output_report_name: str = "control_derivatives_report.json",
) -> dict[str, Any]:
    """Compute finite-difference symmetric-elevon derivatives from aero sweeps.

    The current D2 implementation intentionally computes only symmetric elevon
    derivatives. Differential elevon (`delta_a_diff_deg`) remains a reserved
    column until the solver can generate real differential-control cases.
    """
    dataset_root = dataset_root.expanduser().resolve()
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")

    source_csv, source_kind = _pick_source_csv(dataset_root, source)
    df = pd.read_csv(source_csv)
    if df.empty:
        raise ValueError(f"Source aero dataset is empty: {source_csv}")

    resolved_control_column, used_legacy_alias = _resolve_control_column(df, control_column)

    requested_group_columns = group_columns or DEFAULT_GROUP_COLUMNS
    resolved_group_columns = [c for c in requested_group_columns if c in df.columns]
    missing_group_columns = [c for c in requested_group_columns if c not in df.columns]
    if "geometry_id" not in resolved_group_columns:
        raise ValueError("Cannot compute control derivatives without geometry_id column.")

    requested_target_columns = target_columns or DEFAULT_TARGET_COLUMNS
    resolved_target_columns = _available_columns(df, requested_target_columns)
    if not resolved_target_columns:
        raise ValueError(
            "No target columns are available for derivative computation. "
            f"Requested: {requested_target_columns}"
        )

    numeric_group_columns = [c for c in resolved_group_columns if c != "geometry_id"]
    numeric_columns = [resolved_control_column, *numeric_group_columns, *resolved_target_columns]
    if DIFFERENTIAL_CONTROL_COLUMN in df.columns:
        numeric_columns.append(DIFFERENTIAL_CONTROL_COLUMN)
    df = _coerce_numeric(df, numeric_columns)

    # BUG-24: Filter to symmetric-sweep rows only (diff_input_deg ≈ 0).
    # A combined sym+diff aero_dataset.csv has rows where delta_e_sym_deg=0
    # for BOTH the sym-zero reference AND every diff-sweep point. Without this
    # filter, groups contain multiple zero-control rows, crashing _row_for_control.
    # Filtering here is also physically correct: control derivatives for symmetric
    # elevon should only be computed from symmetric sweep rows.
    diff_col = DIFFERENTIAL_CONTROL_COLUMN
    if diff_col in df.columns:
        _diff_tol = 1e-8
        _sym_only_mask = df[diff_col].fillna(0.0).abs() <= _diff_tol
        _n_diff_rows_removed = int((~_sym_only_mask).sum())
        df = df.loc[_sym_only_mask].copy()
        if _n_diff_rows_removed > 0:
            import warnings as _w
            _w.warn(
                f"compute_control_derivatives: removed {_n_diff_rows_removed} differential-sweep "
                f"rows (diff_input_deg != 0) before computing symmetric elevon derivatives. "
                "Only symmetric-sweep rows are used for dCL/d(delta_e_sym) computation.",
                stacklevel=2,
            )

    before = len(df)
    df = df.dropna(subset=[resolved_control_column, *resolved_group_columns])
    dropped_missing_keys = before - len(df)
    if df.empty:
        raise ValueError("No rows remain after dropping missing control/group values.")

    derivative_rows: list[dict[str, Any]] = []
    grouped = df.groupby(resolved_group_columns, dropna=False, sort=True)
    for group_key, group in grouped:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        derivative_rows.append(
            _compute_group_derivatives(
                group=group,
                group_key=group_key,
                group_columns=resolved_group_columns,
                control_column=resolved_control_column,
                target_columns=resolved_target_columns,
                control_tol=control_tol,
                min_abs_cm_delta_e=min_abs_cm_delta_e,
            )
        )

    out_df = pd.DataFrame(derivative_rows)
    output_csv = dataset_root / output_csv_name
    output_report = dataset_root / output_report_name
    out_df.to_csv(output_csv, index=False)

    status_counts = out_df["status"].value_counts(dropna=False).to_dict() if "status" in out_df else {}
    pitch_counts: dict[str, int] = {}
    if "pitch_authority_adequate" in out_df.columns:
        for value, count in out_df["pitch_authority_adequate"].value_counts(dropna=False).items():
            pitch_counts[str(value)] = int(count)

    differential_summary = {
        "column_present": DIFFERENTIAL_CONTROL_COLUMN in df.columns,
        "unique_values": [],
        "varies": False,
        "status": "not_computed_reserved_for_future_solver_wiring",
    }
    if DIFFERENTIAL_CONTROL_COLUMN in df.columns:
        diff_values = sorted(
            float(v)
            for v in df[DIFFERENTIAL_CONTROL_COLUMN].dropna().unique()
            if math.isfinite(float(v))
        )
        differential_summary["unique_values"] = diff_values
        differential_summary["varies"] = len(diff_values) > 1

    report = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "dataset_root": str(dataset_root),
        "source": source_kind,
        "source_csv": str(source_csv),
        "output_csv": str(output_csv),
        "output_report": str(output_report),
        "control_column": resolved_control_column,
        "used_legacy_control_alias": used_legacy_alias,
        "group_columns": resolved_group_columns,
        "missing_optional_group_columns": missing_group_columns,
        "target_columns": resolved_target_columns,
        "requested_target_columns": requested_target_columns,
        "row_count_input": int(before),
        "row_count_after_key_filter": int(len(df)),
        "dropped_missing_control_or_group_rows": int(dropped_missing_keys),
        "group_count": int(len(out_df)),
        "computed_group_count": int((out_df["status"] == "computed").sum()) if "status" in out_df else 0,
        "skipped_group_count": int((out_df["status"] != "computed").sum()) if "status" in out_df else 0,
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "min_abs_Cm_delta_e_per_rad": float(min_abs_cm_delta_e),
        "pitch_authority_counts": pitch_counts,
        "differential_elevon": differential_summary,
        "manifest_context": _read_json_if_exists(dataset_root / "aero_dataset_manifest.json"),
    }
    _write_json(output_report, report)
    return report
