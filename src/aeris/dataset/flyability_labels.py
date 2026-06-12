from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aeris.dataset.control_derivatives import (
    DEFAULT_GROUP_COLUMNS,
    DEFAULT_SYMMETRIC_CONTROL_COLUMN,
    LEGACY_CONTROL_COLUMN,
)

DEFAULT_CM_COLUMN = "cm"
DEFAULT_CM_DELTA_E_COLUMN = "Cm_delta_e_per_rad"
DEFAULT_OUTPUT_CSV = "flyability_labels.csv"
DEFAULT_OUTPUT_REPORT = "flyability_labels_report.json"


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


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


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
        return requested, requested == LEGACY_CONTROL_COLUMN
    if DEFAULT_SYMMETRIC_CONTROL_COLUMN in df.columns:
        return DEFAULT_SYMMETRIC_CONTROL_COLUMN, False
    if LEGACY_CONTROL_COLUMN in df.columns:
        return LEGACY_CONTROL_COLUMN, True
    raise ValueError(
        "Missing symmetric control column. Expected delta_e_sym_deg or legacy control_input_deg."
    )


def _available_group_columns(aero_df: pd.DataFrame, deriv_df: pd.DataFrame, requested: list[str]) -> list[str]:
    return [c for c in requested if c in aero_df.columns and c in deriv_df.columns]


def _row_for_zero_control(group: pd.DataFrame, control_column: str, *, tol: float) -> pd.Series | None:
    subset = group[(group[control_column] - 0.0).abs() <= tol]
    if subset.empty:
        return None
    if len(subset) > 1:
        # BUG-25 (part b): Belt-and-suspenders. After the diff-row filter in
        # compute_flyability_labels(), this should not trigger. If it does (e.g.
        # the caller passed a pre-filtered df with genuine duplicates), warn and
        # return the first match rather than crashing the entire label computation.
        import warnings as _w
        _w.warn(
            f"_row_for_zero_control: found {len(subset)} rows with control ≈ 0 in group. "
            "Using the first match. Check that diff-sweep rows have been filtered "
            "before calling compute_flyability_labels().",
            stacklevel=3,
        )
    return subset.iloc[0]


def _sign_consistent(value: float | None, expected: str) -> bool | None:
    if value is None:
        return None
    if expected == "negative":
        return value < 0.0
    if expected == "positive":
        return value > 0.0
    raise ValueError(f"Unsupported expected sign: {expected}")


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "1", "yes"}:
            return True
        if lower in {"false", "0", "no"}:
            return False
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return bool(value)


def _bool_is_true(value: Any) -> bool:
    parsed = _safe_bool(value)
    return parsed is True


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except Exception:
        return value is None


def _join_reasons(reasons: list[str]) -> str | None:
    clean = [str(reason).strip() for reason in reasons if str(reason).strip()]
    return ";".join(clean) if clean else None


def _reason_counts(series: pd.Series) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in series.dropna():
        for reason in str(value).split(";"):
            reason = reason.strip()
            if reason:
                counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _infer_failure_stage(reasons: list[str]) -> str:
    if not reasons:
        return "none"
    buckets: list[str] = []
    for reason in reasons:
        if reason.startswith("label_skipped") or reason in {
            "control_derivative_not_computed",
            "matching_aero_group_not_found",
            "missing_zero_control_cm",
            "missing_or_zero_Cm_delta_e",
        }:
            buckets.append("skipped")
        elif reason.startswith("pitch_authority") or "authority" in reason:
            buckets.append("authority")
        elif reason.startswith("pitch_control_sign"):
            buckets.append("control_sign")
        elif reason.startswith("trim_delta_e"):
            buckets.append("trim")
        elif reason.startswith("alpha_trim"):
            buckets.append("alpha_trim")
        elif reason.startswith("pitch_stability"):
            buckets.append("static_stability")
        else:
            buckets.append("other")
    unique = sorted(set(buckets))
    if len(unique) == 1:
        return unique[0]
    return "multiple"


def _enrich_failure_reason_columns(out_df: pd.DataFrame) -> pd.DataFrame:
    """Add explicit failure-reason columns to flyability labels.

    This is an evidence/clarity layer over the existing D3 first-order labels.
    It does not change the underlying physics or promote the result to full
    nonlinear trim, MIL-STD compliance, or 6-DOF validation.
    """
    if out_df.empty:
        return out_df

    df = out_df.copy()
    if "trim_delta_e_limit_deg" not in df.columns:
        df["trim_delta_e_limit_deg"] = df.get("max_abs_trim_delta_e_deg")

    red_flags: list[bool] = []
    red_flag_reasons: list[str | None] = []
    trim_failure_reasons: list[str | None] = []
    pitch_authority_failure_reasons: list[str | None] = []
    pitch_control_sign_failure_reasons: list[str | None] = []
    alpha_trim_warning_reasons: list[str | None] = []
    pitch_stability_warning_reasons: list[str | None] = []
    failure_stages: list[str] = []

    for _, row in df.iterrows():
        reasons: list[str] = []
        trim_reasons: list[str] = []
        authority_reasons: list[str] = []
        sign_reasons: list[str] = []
        alpha_warnings: list[str] = []
        stability_warnings: list[str] = []

        status = str(row.get("status", "")).strip().lower()
        if status != "computed":
            skip = row.get("skip_reason")
            if _is_missing(skip) or not str(skip).strip():
                reasons.append("label_skipped")
            else:
                reasons.append(str(skip).strip())

        pitch_authority = _safe_bool(row.get("pitch_authority_adequate"))
        if pitch_authority is not True:
            if pitch_authority is False:
                authority_reasons.append("pitch_authority_below_threshold")
            else:
                authority_reasons.append("pitch_authority_unknown")

        pitch_sign = _safe_bool(row.get("pitch_control_sign_ok"))
        if pitch_sign is not True:
            if pitch_sign is False:
                sign_reasons.append("pitch_control_sign_not_expected_negative")
            else:
                sign_reasons.append("pitch_control_sign_unknown")

        trim_feasible = _safe_bool(row.get("trim_delta_e_feasible"))
        if trim_feasible is not True:
            if trim_feasible is False:
                trim_reasons.append("trim_delta_e_required_exceeds_limit")
            else:
                trim_reasons.append("trim_delta_e_feasibility_unknown")

        alpha_trim_feasible = _safe_bool(row.get("alpha_trim_feasible"))
        if alpha_trim_feasible is False:
            alpha_warnings.append("alpha_trim_outside_bounds")

        pitch_stability = _safe_bool(row.get("pitch_stability_sign_ok"))
        if pitch_stability is False:
            stability_warnings.append("pitch_stability_sign_not_expected_negative")

        reasons.extend(authority_reasons)
        reasons.extend(sign_reasons)
        reasons.extend(trim_reasons)
        # Optional stability/alpha signals are warnings. They become red flags
        # only when the underlying optional data exists and explicitly fails.
        reasons.extend(alpha_warnings)
        reasons.extend(stability_warnings)

        # Keep red_flag aligned with the declared basic label when present.
        flyable_value = _safe_bool(row.get("label_longitudinal_basic_flyable"))
        if flyable_value is True and not reasons:
            red_flag = False
        elif flyable_value is False:
            red_flag = True
            if not reasons:
                reasons.append("longitudinal_basic_flyable_false")
        elif flyable_value is None and reasons:
            red_flag = True
        else:
            red_flag = bool(reasons)

        red_flags.append(bool(red_flag))
        red_flag_reasons.append(_join_reasons(reasons))
        trim_failure_reasons.append(_join_reasons(trim_reasons))
        pitch_authority_failure_reasons.append(_join_reasons(authority_reasons))
        pitch_control_sign_failure_reasons.append(_join_reasons(sign_reasons))
        alpha_trim_warning_reasons.append(_join_reasons(alpha_warnings))
        pitch_stability_warning_reasons.append(_join_reasons(stability_warnings))
        failure_stages.append(_infer_failure_stage(reasons))

    df["red_flag"] = red_flags
    df["red_flag_reasons"] = red_flag_reasons
    df["trim_failure_reason"] = trim_failure_reasons
    df["pitch_authority_failure_reason"] = pitch_authority_failure_reasons
    df["pitch_control_sign_failure_reason"] = pitch_control_sign_failure_reasons
    df["alpha_trim_warning_reason"] = alpha_trim_warning_reasons
    df["pitch_stability_warning_reason"] = pitch_stability_warning_reasons
    df["label_failure_stage"] = failure_stages
    return df


def _build_label_row(
    *,
    derivative_row: pd.Series,
    zero_row: pd.Series | None,
    group_columns: list[str],
    cm_column: str,
    cm_delta_e_column: str,
    max_abs_trim_delta_e_deg: float,
    min_abs_cm_delta_e: float,
    alpha_min_deg: float,
    alpha_max_deg: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {column: derivative_row.get(column) for column in group_columns}
    row["label_schema_version"] = "d3_flyability_v1"
    row["status"] = "computed"
    row["skip_reason"] = None

    deriv_status = str(derivative_row.get("status", ""))
    if deriv_status != "computed":
        row["status"] = "skipped"
        row["skip_reason"] = "control_derivative_not_computed"
        row.update(_empty_label_values(max_abs_trim_delta_e_deg, min_abs_cm_delta_e, alpha_min_deg, alpha_max_deg))
        return row

    cm_delta_e = _finite_float(derivative_row.get(cm_delta_e_column))
    pitch_authority = _safe_bool(derivative_row.get("pitch_authority_adequate"))
    if pitch_authority is None and cm_delta_e is not None:
        pitch_authority = abs(cm_delta_e) >= min_abs_cm_delta_e

    cm0 = None if zero_row is None else _finite_float(zero_row.get(cm_column))
    alpha0 = _finite_float(derivative_row.get("alpha_deg"))
    cma = None
    for candidate in ("cma_per_rad", "Cma_per_rad", "cma", "Cma", "cm_alpha", "Cm_alpha", "C_m_alpha"):
        if zero_row is not None and candidate in zero_row.index:
            cma = _finite_float(zero_row.get(candidate))
            if cma is not None:
                break

    row["cm_at_zero_control"] = cm0
    row["Cm_delta_e_per_rad"] = cm_delta_e
    row["min_abs_Cm_delta_e_per_rad"] = float(min_abs_cm_delta_e)
    row["pitch_authority_adequate"] = pitch_authority
    row["pitch_control_sign_ok"] = _sign_consistent(cm_delta_e, "negative")
    row["max_abs_trim_delta_e_deg"] = float(max_abs_trim_delta_e_deg)

    if cm0 is None:
        row["status"] = "skipped"
        row["skip_reason"] = "missing_zero_control_cm"
        row.update(_trim_empty_values())
        return row

    if cm_delta_e is None or abs(cm_delta_e) < 1e-12:
        row["status"] = "skipped"
        row["skip_reason"] = "missing_or_zero_Cm_delta_e"
        row.update(_trim_empty_values())
        return row

    # Alpha-fixed trim: 0 = Cm0 + Cm_delta_e * delta_e_required.
    trim_delta_e_rad = -cm0 / cm_delta_e
    trim_delta_e_deg = math.degrees(trim_delta_e_rad)
    trim_delta_e_abs_deg = abs(trim_delta_e_deg)
    trim_delta_e_margin_deg = max_abs_trim_delta_e_deg - trim_delta_e_abs_deg
    trim_delta_e_feasible = trim_delta_e_abs_deg <= max_abs_trim_delta_e_deg

    row["trim_delta_e_required_rad"] = trim_delta_e_rad
    row["trim_delta_e_required_deg"] = trim_delta_e_deg
    row["trim_delta_e_abs_required_deg"] = trim_delta_e_abs_deg
    row["trim_delta_e_margin_to_limit_deg"] = trim_delta_e_margin_deg
    row["trim_delta_e_feasible"] = trim_delta_e_feasible

    # Optional control-fixed alpha trim if Cma is present in the source aero row.
    row["cma_per_rad"] = cma
    row["alpha_min_deg"] = float(alpha_min_deg)
    row["alpha_max_deg"] = float(alpha_max_deg)
    row["alpha_trim_deg"] = None
    row["alpha_trim_feasible"] = None
    row["pitch_stability_sign_ok"] = _sign_consistent(cma, "negative")
    if alpha0 is not None and cma is not None and abs(cma) >= 1e-12:
        alpha_trim_deg = alpha0 + math.degrees(-cm0 / cma)
        row["alpha_trim_deg"] = alpha_trim_deg
        row["alpha_trim_feasible"] = alpha_min_deg <= alpha_trim_deg <= alpha_max_deg

    row["longitudinal_basic_flyable"] = bool(
        pitch_authority is True
        and row["pitch_control_sign_ok"] is True
        and trim_delta_e_feasible is True
    )
    row["label_pitch_authority_ok"] = pitch_authority
    row["label_trim_delta_e_feasible"] = trim_delta_e_feasible
    row["label_longitudinal_basic_flyable"] = row["longitudinal_basic_flyable"]
    return row


def _trim_empty_values() -> dict[str, Any]:
    return {
        "trim_delta_e_required_rad": None,
        "trim_delta_e_required_deg": None,
        "trim_delta_e_abs_required_deg": None,
        "trim_delta_e_margin_to_limit_deg": None,
        "trim_delta_e_feasible": None,
        "cma_per_rad": None,
        "alpha_trim_deg": None,
        "alpha_trim_feasible": None,
        "pitch_stability_sign_ok": None,
        "longitudinal_basic_flyable": None,
        "label_pitch_authority_ok": None,
        "label_trim_delta_e_feasible": None,
        "label_longitudinal_basic_flyable": None,
    }


def _empty_label_values(
    max_abs_trim_delta_e_deg: float,
    min_abs_cm_delta_e: float,
    alpha_min_deg: float,
    alpha_max_deg: float,
) -> dict[str, Any]:
    out = {
        "cm_at_zero_control": None,
        "Cm_delta_e_per_rad": None,
        "min_abs_Cm_delta_e_per_rad": float(min_abs_cm_delta_e),
        "pitch_authority_adequate": None,
        "pitch_control_sign_ok": None,
        "max_abs_trim_delta_e_deg": float(max_abs_trim_delta_e_deg),
        "alpha_min_deg": float(alpha_min_deg),
        "alpha_max_deg": float(alpha_max_deg),
    }
    out.update(_trim_empty_values())
    return out


def compute_flyability_labels(
    *,
    dataset_root: Path,
    source: str = "auto",
    control_column: str | None = None,
    group_columns: list[str] | None = None,
    cm_column: str = DEFAULT_CM_COLUMN,
    control_derivatives_csv: Path | None = None,
    max_abs_trim_delta_e_deg: float = 25.0,
    min_abs_cm_delta_e: float = 0.10,
    alpha_min_deg: float = -5.0,
    alpha_max_deg: float = 15.0,
    control_tol: float = 1e-8,
    output_csv_name: str = DEFAULT_OUTPUT_CSV,
    output_report_name: str = DEFAULT_OUTPUT_REPORT,
) -> dict[str, Any]:
    """Generate first-order trim/control/flyability labels from aero + D2 outputs.

    This D3 layer intentionally stays diagnostic and first-order. It uses the
    zero-control Cm and finite-difference Cm_delta_e from D2 to estimate the
    symmetric-elevon deflection required to trim pitch at fixed alpha.
    """
    dataset_root = dataset_root.expanduser().resolve()
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")

    if max_abs_trim_delta_e_deg <= 0.0:
        raise ValueError("max_abs_trim_delta_e_deg must be positive.")
    if min_abs_cm_delta_e < 0.0:
        raise ValueError("min_abs_cm_delta_e must be non-negative.")
    if alpha_min_deg >= alpha_max_deg:
        raise ValueError("alpha_min_deg must be lower than alpha_max_deg.")

    source_csv, source_kind = _pick_source_csv(dataset_root, source)
    aero_df = pd.read_csv(source_csv)
    if aero_df.empty:
        raise ValueError(f"Source aero dataset is empty: {source_csv}")
    if cm_column not in aero_df.columns:
        raise ValueError(f"Missing required Cm column in aero dataset: {cm_column}")

    resolved_control_column, used_legacy_alias = _resolve_control_column(aero_df, control_column)

    derivatives_path = (
        control_derivatives_csv.expanduser().resolve()
        if control_derivatives_csv is not None
        else dataset_root / "control_derivatives.csv"
    )
    if not derivatives_path.exists():
        raise FileNotFoundError(
            f"Missing control derivatives CSV: {derivatives_path}. "
            "Run 'aeris dataset compute-control-derivatives' first."
        )
    deriv_df = pd.read_csv(derivatives_path)
    if deriv_df.empty:
        raise ValueError(f"Control derivatives CSV is empty: {derivatives_path}")
    if DEFAULT_CM_DELTA_E_COLUMN not in deriv_df.columns:
        raise ValueError(f"Missing required derivative column: {DEFAULT_CM_DELTA_E_COLUMN}")

    requested_group_columns = group_columns or DEFAULT_GROUP_COLUMNS
    resolved_group_columns = _available_group_columns(aero_df, deriv_df, requested_group_columns)
    missing_group_columns = [c for c in requested_group_columns if c not in resolved_group_columns]
    if "geometry_id" not in resolved_group_columns:
        raise ValueError("Cannot compute flyability labels without geometry_id in aero and derivative data.")

    numeric_aero_columns = [resolved_control_column, cm_column, *[c for c in resolved_group_columns if c != "geometry_id"]]
    for optional in ("cma_per_rad", "Cma_per_rad", "cma", "Cma", "cm_alpha", "Cm_alpha", "C_m_alpha"):
        if optional in aero_df.columns:
            numeric_aero_columns.append(optional)
    aero_df = _coerce_numeric(aero_df, numeric_aero_columns)

    numeric_derivative_columns = [
        DEFAULT_CM_DELTA_E_COLUMN,
        "min_abs_Cm_delta_e_per_rad",
        *[c for c in resolved_group_columns if c != "geometry_id"],
    ]
    deriv_df = _coerce_numeric(deriv_df, numeric_derivative_columns)

    # BUG-25 (part a): Filter to symmetric-sweep rows only before groupby.
    # Mirrors the fix applied to control_derivatives.py.
    from aeris.dataset.control_derivatives import DIFFERENTIAL_CONTROL_COLUMN as _DIFF_COL
    if _DIFF_COL in aero_df.columns:
        _diff_tol_fl = 1e-8
        _sym_mask_fl = aero_df[_DIFF_COL].fillna(0.0).abs() <= _diff_tol_fl
        _n_diff_fl = int((~_sym_mask_fl).sum())
        aero_df = aero_df.loc[_sym_mask_fl].copy()
        if _n_diff_fl > 0:
            import warnings as _w
            _w.warn(
                f"compute_flyability_labels: removed {_n_diff_fl} differential-sweep rows "
                f"(diff_input_deg != 0) before computing flyability labels. "
                "Only symmetric-sweep rows are used for Cm0 extraction and trim computation.",
                stacklevel=2,
            )

    before_aero = len(aero_df)
    aero_df = aero_df.dropna(subset=[resolved_control_column, cm_column, *resolved_group_columns])
    dropped_aero = before_aero - len(aero_df)
    if aero_df.empty:
        raise ValueError("No aero rows remain after dropping missing control/group/Cm values.")

    before_deriv = len(deriv_df)
    deriv_df = deriv_df.dropna(subset=resolved_group_columns)
    dropped_deriv = before_deriv - len(deriv_df)
    if deriv_df.empty:
        raise ValueError("No derivative rows remain after dropping missing group values.")

    aero_groups = {key if isinstance(key, tuple) else (key,): group for key, group in aero_df.groupby(resolved_group_columns, dropna=False, sort=True)}

    rows: list[dict[str, Any]] = []
    for _, derivative_row in deriv_df.iterrows():
        key = tuple(derivative_row.get(column) for column in resolved_group_columns)
        aero_group = aero_groups.get(key)
        zero_row = None
        if aero_group is not None:
            zero_row = _row_for_zero_control(aero_group, resolved_control_column, tol=control_tol)
        label_row = _build_label_row(
            derivative_row=derivative_row,
            zero_row=zero_row,
            group_columns=resolved_group_columns,
            cm_column=cm_column,
            cm_delta_e_column=DEFAULT_CM_DELTA_E_COLUMN,
            max_abs_trim_delta_e_deg=max_abs_trim_delta_e_deg,
            min_abs_cm_delta_e=min_abs_cm_delta_e,
            alpha_min_deg=alpha_min_deg,
            alpha_max_deg=alpha_max_deg,
        )
        if aero_group is None:
            label_row["status"] = "skipped"
            label_row["skip_reason"] = "matching_aero_group_not_found"
        rows.append(label_row)

    out_df = pd.DataFrame(rows)
    out_df = _enrich_failure_reason_columns(out_df)
    output_csv = dataset_root / output_csv_name
    output_report = dataset_root / output_report_name
    out_df.to_csv(output_csv, index=False)

    status_counts = out_df["status"].value_counts(dropna=False).to_dict() if "status" in out_df else {}
    flyable_counts: dict[str, int] = {}
    if "label_longitudinal_basic_flyable" in out_df.columns:
        for value, count in out_df["label_longitudinal_basic_flyable"].value_counts(dropna=False).items():
            flyable_counts[str(value)] = int(count)

    red_flag_count = int(out_df["red_flag"].sum()) if "red_flag" in out_df.columns else 0

    # FLY-1: trim summary stats — min/max/mean required trim deflection
    # and mean trim margin. Quick sanity check without opening the CSV.
    import numpy as _np
    trim_summary: dict = {}
    if "trim_delta_e_required_deg" in out_df.columns:
        _trim_vals = out_df["trim_delta_e_required_deg"].dropna()
        trim_summary["trim_delta_e_required_deg_min"] = float(_trim_vals.min()) if not _trim_vals.empty else None
        trim_summary["trim_delta_e_required_deg_max"] = float(_trim_vals.max()) if not _trim_vals.empty else None
        trim_summary["trim_delta_e_required_deg_mean"] = float(_trim_vals.mean()) if not _trim_vals.empty else None
        trim_summary["trim_delta_e_abs_required_deg_mean"] = (
            float(_trim_vals.abs().mean()) if not _trim_vals.empty else None
        )
    if "trim_delta_e_margin_to_limit_deg" in out_df.columns:
        _margin_vals = out_df["trim_delta_e_margin_to_limit_deg"].dropna()
        trim_summary["trim_delta_e_margin_deg_min"] = float(_margin_vals.min()) if not _margin_vals.empty else None
        trim_summary["trim_delta_e_margin_deg_mean"] = float(_margin_vals.mean()) if not _margin_vals.empty else None
    trim_summary["trim_limit_deg"] = float(max_abs_trim_delta_e_deg)
    _n_feasible = int(out_df["trim_delta_e_feasible"].sum()) if "trim_delta_e_feasible" in out_df.columns else 0
    _n_infeasible = int((out_df["trim_delta_e_feasible"] == False).sum()) if "trim_delta_e_feasible" in out_df.columns else 0
    trim_summary["trim_feasible_count"] = _n_feasible
    trim_summary["trim_infeasible_count"] = _n_infeasible
    red_flag_reason_counts = (
        _reason_counts(out_df["red_flag_reasons"])
        if "red_flag_reasons" in out_df.columns
        else {}
    )
    trim_failure_reason_counts = (
        _reason_counts(out_df["trim_failure_reason"])
        if "trim_failure_reason" in out_df.columns
        else {}
    )
    label_failure_stage_counts = (
        {str(k): int(v) for k, v in out_df["label_failure_stage"].value_counts(dropna=False).items()}
        if "label_failure_stage" in out_df.columns
        else {}
    )

    report = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "dataset_root": str(dataset_root),
        "source": source_kind,
        "source_csv": str(source_csv),
        "control_derivatives_csv": str(derivatives_path),
        "output_csv": str(output_csv),
        "output_report": str(output_report),
        "control_column": resolved_control_column,
        "used_legacy_control_alias": used_legacy_alias,
        "cm_column": cm_column,
        "group_columns": resolved_group_columns,
        "missing_optional_group_columns": missing_group_columns,
        "row_count_aero_input": int(before_aero),
        "row_count_aero_after_key_filter": int(len(aero_df)),
        "dropped_aero_rows_missing_keys": int(dropped_aero),
        "row_count_derivative_input": int(before_deriv),
        "row_count_derivative_after_key_filter": int(len(deriv_df)),
        "dropped_derivative_rows_missing_keys": int(dropped_deriv),
        "label_row_count": int(len(out_df)),
        "computed_label_count": int((out_df["status"] == "computed").sum()) if "status" in out_df else 0,
        "skipped_label_count": int((out_df["status"] != "computed").sum()) if "status" in out_df else 0,
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "longitudinal_basic_flyable_counts": flyable_counts,
        "red_flag_count": red_flag_count,
        "red_flag_reason_counts": red_flag_reason_counts,
        "trim_failure_reason_counts": trim_failure_reason_counts,
        "label_failure_stage_counts": label_failure_stage_counts,
        "thresholds": {
            "max_abs_trim_delta_e_deg": float(max_abs_trim_delta_e_deg),
            "min_abs_Cm_delta_e_per_rad": float(min_abs_cm_delta_e),
            "alpha_min_deg": float(alpha_min_deg),
            "alpha_max_deg": float(alpha_max_deg),
        },
        "limitations": [
            "first_order_linear_trim_estimate_only",
            "symmetric_elevon_pitch_trim_only",
            "differential_elevon_not_computed_until_solver_wiring_exists",
            "not_a_full_nonlinear_trim_solver",
            "not_a_mil_std_compliance_claim",
        ],
        "trim_summary": trim_summary,
        "control_derivatives_report_context": _read_json_if_exists(dataset_root / "control_derivatives_report.json"),
    }
    _write_json(output_report, report)
    return report
