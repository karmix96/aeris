from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from aeris.dataset.splitting import split_dataset
from aeris.dataset.training_data import load_training_data
from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import FeatureSet, get_feature_set, validate_feature_set_dataframe
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.model_registry import build_model, get_model_spec


LEARNING_CURVES_SCHEMA_VERSION = "aeris.learning_curves.v1.3"


def parse_int_csv(value: str | Sequence[int], *, option_name: str = "--group-sizes") -> list[int]:
    """Parse a comma-separated positive-integer list for CLI-friendly use."""
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
    else:
        parts = [str(v).strip() for v in value]
    if not parts:
        raise ValueError(f"{option_name} must contain at least one integer.")
    out: list[int] = []
    for part in parts:
        try:
            n = int(part)
        except ValueError as exc:
            raise ValueError(f"{option_name} contains a non-integer value: {part!r}") from exc
        if n <= 0:
            raise ValueError(f"{option_name} values must be positive. Got {n}.")
        out.append(n)
    deduped = sorted(set(out))
    return deduped


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        return v if np.isfinite(v) else None
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_to_jsonable(payload), indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _to_jsonable(row.get(k)) for k in fieldnames})



_TARGET_SPEC_ALIASES = {
    "basic": "aero_basic",
    "default": "aero_basic",
    "aero": "aero_all",
    "all_aero": "aero_all",
    "all": "numeric_all",
    "all_numeric": "numeric_all",
}

_AERO_BASIC_TARGETS = ("cl", "cd", "cm")

_AERO_EXACT_TARGETS = {
    "cl", "cd", "cm", "cy", "cn", "cl_roll", "l_over_d", "l_d", "ld",
    "l_over_d_viscous", "cd_induced", "cdff", "cd_ff", "cd_profile",
    "cd_total", "cdtot", "oswald_e", "e", "xnp", "x_np", "spiral_metric",
}

_AERO_DERIVATIVE_TARGETS = {
    "cla", "clb", "clp", "clq", "clr",
    "cda", "cdb", "cdp", "cdq", "cdr",
    "cma", "cmb", "cmp", "cmq", "cmr",
    "cya", "cyb", "cyp", "cyq", "cyr",
    "cna", "cnb", "cnp", "cnq", "cnr",
    "cxa", "cxb", "cxp", "cxq", "cxr", "cxu", "cxv", "cxw",
    "czu", "czv", "czw", "cyu", "cyv", "cyw",
    "clu", "clv", "clw", "cmu", "cmv", "cmw", "cnu", "cnv", "cnw",
}

_FLYABILITY_TARGET_TOKENS = (
    "trim", "flyable", "red_flag", "pitch_authority", "control_sign", "delta_e_required",
    "cm_delta", "delta_e_feasible", "stability", "static_margin",
)

_EXCLUDE_TARGET_EXACT = {
    "alpha_deg", "alpha_deg_sq", "abs_alpha_deg", "beta_deg", "velocity_mps", "velocity_sq",
    "altitude_m", "control_input_deg", "control_input_deg_sq", "alpha_x_control",
    "delta_e_sym_deg", "delta_a_diff_deg", "diff_input_deg", "p_rad_s", "q_rad_s", "r_rad_s",
    "re_number", "mach", "reynolds", "ncrit", "sampler_seed", "realization_seed",
    "num_sections", "n_xsecs_aerosandbox", "geometry_qc_passed", "aero_qc_passed",
    "promotion_ready", "elevon_start_frac", "elevon_end_frac", "elevon_hinge_frac",
}

_EXCLUDE_TARGET_PREFIXES = (
    "c1_", "c2_", "c3_", "c4_", "b1_", "b2_", "b3_", "b_total",
    "sw1", "sw2", "sw3", "twist_", "dihedral_", "split_", "sampler_",
    "realization_", "generator_", "geometry_", "aero_", "diag_", "qc_",
)

_EXCLUDE_TARGET_TOKENS = (
    "id", "name", "path", "dir", "status", "reason", "message", "config", "manifest",
    "summary", "hash", "sha", "source", "artifact", "plot", "airfoil", "dataset",
)


def _is_numeric_series(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    return int(numeric.notna().sum()) > 0


def _target_finite_fraction(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce")
    if len(numeric) == 0:
        return 0.0
    return float(numeric.notna().sum()) / float(len(numeric))


def _looks_like_aero_target(column: str) -> bool:
    key = column.lower().strip()
    if key in _AERO_EXACT_TARGETS or key in _AERO_DERIVATIVE_TARGETS:
        return True
    if key.startswith("cd_") and not key.startswith("cdcl"):
        return True
    if key.startswith("cl_") and key not in {"cl_roll"}:
        return True
    if key.startswith(("cm_", "cy_", "cn_", "cx_", "cz_")):
        return True
    if key.endswith(("_per_rad", "_derivative")) and key.startswith(("cl", "cd", "cm", "cy", "cn", "cx", "cz")):
        return True
    return False


def _looks_like_flyability_target(column: str) -> bool:
    key = column.lower().strip()
    return any(token in key for token in _FLYABILITY_TARGET_TOKENS)


def _is_excluded_from_auto_targets(column: str, feature_columns: list[str], group_column: str | None) -> bool:
    key = column.lower().strip()
    feature_keys = {c.lower().strip() for c in feature_columns}
    if key in feature_keys:
        return True
    if group_column is not None and key == group_column.lower().strip():
        return True
    if key in _EXCLUDE_TARGET_EXACT:
        return True
    if any(key.startswith(prefix) for prefix in _EXCLUDE_TARGET_PREFIXES):
        return True
    if any(token in key for token in _EXCLUDE_TARGET_TOKENS):
        return True
    return False


def resolve_target_columns_from_dataframe(
    df: pd.DataFrame,
    target_spec: str | list[str] | tuple[str, ...],
    *,
    feature_columns: list[str] | None = None,
    group_column: str | None = "geometry_id",
    min_finite_fraction: float = 1.0,
) -> list[str]:
    """Resolve --targets specs such as aero_basic, aero_all, flyability_all, or all/numeric_all.

    Auto target sets intentionally exclude metadata, features, operating conditions,
    design variables, IDs, paths, and columns with missing/non-numeric values. This
    keeps broad learning-curve batches from silently training on junk columns.
    """
    feature_columns = list(feature_columns or [])
    if isinstance(target_spec, str):
        raw = target_spec.strip()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in target_spec if str(p).strip()]
    if not parts:
        raise ValueError("At least one target must be supplied.")
    if len(parts) > 1:
        missing = [p for p in parts if p not in df.columns]
        if missing:
            raise ValueError(f"Requested target columns are missing: {missing}")
        return parts

    spec = _TARGET_SPEC_ALIASES.get(parts[0].lower(), parts[0].lower())
    if spec not in {"aero_basic", "aero_all", "flyability_all", "numeric_all"}:
        if parts[0] not in df.columns:
            raise ValueError(f"Requested target column is missing: {parts[0]}")
        return [parts[0]]

    if spec == "aero_basic":
        targets = [c for c in _AERO_BASIC_TARGETS if c in df.columns]
    else:
        targets = []
        for col in df.columns:
            if _is_excluded_from_auto_targets(col, feature_columns, group_column):
                continue
            if not _is_numeric_series(df[col]):
                continue
            if _target_finite_fraction(df[col]) < float(min_finite_fraction):
                continue
            if spec == "aero_all" and not _looks_like_aero_target(col):
                continue
            if spec == "flyability_all" and not _looks_like_flyability_target(col):
                continue
            targets.append(col)
    if not targets:
        raise ValueError(f"Target spec {parts[0]!r} resolved to no usable target columns.")
    return targets


def resolve_target_columns_for_dataset(
    dataset_path: Path,
    target_spec: str | list[str] | tuple[str, ...],
    *,
    feature_columns: list[str] | None = None,
    group_column: str | None = "geometry_id",
    allow_forced: bool = False,
    min_finite_fraction: float = 1.0,
) -> list[str]:
    """Resolve broad target specs against a promoted dataset root."""
    from aeris.dataset.promoted_dataset import require_promoted_aero_dataset

    dataset_path = Path(dataset_path).expanduser().resolve()
    promoted_info = require_promoted_aero_dataset(dataset_root=dataset_path, allow_forced=allow_forced)
    curated = promoted_info.get("curated_aero_dataset_csv") or dataset_path / "curated_aero_dataset.csv"
    curated_path = Path(curated).expanduser().resolve()
    if not curated_path.exists():
        raise FileNotFoundError(f"Missing curated dataset CSV for target resolution: {curated_path}")
    df = pd.read_csv(curated_path)
    return resolve_target_columns_from_dataframe(
        df,
        target_spec,
        feature_columns=feature_columns,
        group_column=group_column,
        min_finite_fraction=min_finite_fraction,
    )

def _stats(values: Iterable[float | None]) -> dict[str, float | None]:
    vals = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    if not vals:
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    return {
        "mean": float(mean(vals)),
        "std": float(pstdev(vals)) if len(vals) > 1 else 0.0,
        "min": float(min(vals)),
        "max": float(max(vals)),
        "n": int(len(vals)),
    }


def _split_metric(metrics: dict[str, Any], split_name: str, metric: str) -> float | None:
    v = metrics.get(split_name, {}).get("overall", {}).get(metric)
    return None if v is None else float(v)


def _target_metric(metrics: dict[str, Any], split_name: str, target: str, metric: str) -> float | None:
    v = metrics.get(split_name, {}).get("per_target", {}).get(target, {}).get(metric)
    return None if v is None else float(v)


def _flatten_metrics_row(*, prefix: str, metrics: dict[str, Any], target_columns: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    overall = metrics.get(prefix, {}).get("overall", {})
    for metric in ["r2_mean", "rmse_mean", "mae_mean", "nrmse_by_std_mean", "nrmse_by_range_mean", "max_abs_error_mean"]:
        row[f"{prefix}_{metric}"] = overall.get(metric)
    for target in target_columns:
        per = metrics.get(prefix, {}).get("per_target", {}).get(target, {})
        for metric in ["r2", "rmse", "mae", "nrmse_by_std", "nrmse_by_range", "max_abs_error"]:
            row[f"{prefix}_{metric}__{target}"] = per.get(metric)
    return row


def _make_output_dir(dataset_path: Path | None, model_type: str, output_dir: Path | None) -> Path:
    if output_dir is not None:
        out = Path(output_dir).expanduser().resolve()
    elif dataset_path is not None:
        out = Path(dataset_path).expanduser().resolve() / "learning_curves"
    else:
        out = Path("data") / "processed" / "learning_curves" / model_type
    out.mkdir(parents=True, exist_ok=True)
    return out


def _evaluate_model(
    *,
    model: Any,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
) -> dict[str, Any]:
    X_train = train_df[feature_columns].to_numpy(dtype=float)
    y_train = train_df[target_columns].to_numpy(dtype=float)
    model.fit(X_train, y_train)

    metrics = {
        "train": evaluate_regression_metrics(
            y_train,
            np.asarray(model.predict(X_train), dtype=float),
            target_columns,
        ),
        "val": evaluate_regression_metrics(
            val_df[target_columns].to_numpy(dtype=float),
            np.asarray(model.predict(val_df[feature_columns].to_numpy(dtype=float)), dtype=float),
            target_columns,
        ),
        "test": evaluate_regression_metrics(
            test_df[target_columns].to_numpy(dtype=float),
            np.asarray(model.predict(test_df[feature_columns].to_numpy(dtype=float)), dtype=float),
            target_columns,
        ),
    }
    return metrics


def _ordered_training_groups(train_df: pd.DataFrame, group_column: str, random_seed: int) -> list[Any]:
    groups = np.array(sorted(train_df[group_column].dropna().unique(), key=lambda x: str(x)), dtype=object)
    rng = np.random.default_rng(random_seed + 104729)
    if len(groups) > 0:
        groups = rng.permutation(groups)
    return groups.tolist()


def _select_training_subset(
    *,
    split_method: str,
    train_df: pd.DataFrame,
    group_column: str,
    group_size: int,
    ordered_groups: list[Any],
    ordered_indices: np.ndarray,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if split_method == "grouped":
        available = len(ordered_groups)
        if group_size > available:
            return train_df.iloc[[]].copy(), {
                "status": "skipped",
                "reason": f"requested {group_size} training groups but only {available} are available after split",
                "available_training_groups": available,
                "group_size_used": 0,
                "selected_groups": [],
            }
        selected_groups = ordered_groups[:group_size]
        subset = train_df[train_df[group_column].isin(selected_groups)].copy()
        return subset, {
            "status": "computed",
            "available_training_groups": available,
            "group_size_used": int(group_size),
            "selected_groups": [str(g) for g in selected_groups],
        }

    available_rows = int(len(train_df))
    if group_size > available_rows:
        return train_df.iloc[[]].copy(), {
            "status": "skipped",
            "reason": f"requested {group_size} training rows but only {available_rows} are available after split",
            "available_training_rows": available_rows,
            "group_size_used": 0,
            "selected_groups": [],
        }
    selected_idx = ordered_indices[:group_size]
    subset = train_df.iloc[selected_idx].copy()
    selected_groups = []
    if group_column in subset.columns:
        selected_groups = [str(g) for g in sorted(subset[group_column].dropna().unique(), key=lambda x: str(x))]
    return subset, {
        "status": "computed",
        "available_training_rows": available_rows,
        "group_size_used": int(group_size),
        "selected_groups": selected_groups,
    }


def _build_summary_rows(rows: list[dict[str, Any]], target_columns: list[str]) -> list[dict[str, Any]]:
    computed = [row for row in rows if row.get("status") == "computed"]
    group_sizes = sorted({int(row["group_size_used"]) for row in computed})
    summary_rows: list[dict[str, Any]] = []
    for group_size in group_sizes:
        subset = [row for row in computed if int(row["group_size_used"]) == group_size]
        row: dict[str, Any] = {
            "group_size": group_size,
            "n_runs": len(subset),
            "n_train_rows_mean": _stats(r.get("n_train_rows") for r in subset)["mean"],
        }
        for split_name in ["train", "val", "test"]:
            for metric in ["r2_mean", "rmse_mean", "mae_mean"]:
                s = _stats(r.get(f"{split_name}_{metric}") for r in subset)
                row[f"{split_name}_{metric}_mean"] = s["mean"]
                row[f"{split_name}_{metric}_std"] = s["std"]
        for target in target_columns:
            for split_name in ["train", "val", "test"]:
                for metric in ["r2", "rmse", "mae", "nrmse_by_std", "nrmse_by_range"]:
                    key = f"{split_name}_{metric}__{target}"
                    s = _stats(r.get(key) for r in subset)
                    row[f"{key}_mean"] = s["mean"]
                    row[f"{key}_std"] = s["std"]
        summary_rows.append(row)
    return summary_rows



def _safe_float(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _mean_optional(values: Iterable[Any]) -> float | None:
    vals = [_safe_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    return None if not vals else float(mean(vals))


def _target_family(target: str) -> str:
    """Operator-facing target family for reporting and plotting."""
    key = target.lower().strip()
    if key in {"cl", "cd", "cm", "x_np", "xnp"}:
        return "primary_aero"
    if key in {"l_over_d", "l_over_d_viscous", "cd_total", "cd_profile", "cd_ind", "cd_ff"}:
        return "derived_or_drag_breakdown"
    if key in {"cy", "cl_roll", "cn"}:
        return "symmetric_lateral_expected_near_zero"
    if key.endswith("_per_rad") or key.startswith(("cla", "cma", "cyb", "clb", "cnb")):
        return "derivative_or_stability"
    return "other_numeric"


def _target_diagnostics(df: pd.DataFrame, target_columns: list[str]) -> list[dict[str, Any]]:
    """Summarize target scale/variance so broad-target scores are not misread.

    Normalization note:
    Raw RMSE/MAE cannot be compared across targets like CD, Cm, L/D, and Xnp.
    This table records each target's training-data scale and flags constant or
    near-constant targets so they can be excluded from broad overall readiness.
    """
    out: list[dict[str, Any]] = []
    for target in target_columns:
        numeric = pd.to_numeric(df[target], errors="coerce") if target in df.columns else pd.Series(dtype=float)
        finite = numeric[np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))]
        n = int(len(finite))
        n_unique = int(finite.nunique(dropna=True)) if n else 0
        min_v = _safe_float(finite.min()) if n else None
        max_v = _safe_float(finite.max()) if n else None
        mean_v = _safe_float(finite.mean()) if n else None
        std_v = _safe_float(finite.std(ddof=0)) if n else None
        range_v = None if min_v is None or max_v is None else float(max_v - min_v)
        is_constant = bool(n_unique <= 1 or std_v is None or std_v <= 1e-12 or range_v is None or range_v <= 1e-12)
        is_near_constant = bool(is_constant or n_unique <= 2 or (std_v is not None and abs(std_v) <= 1e-9))
        family = _target_family(target)
        include_in_overall = not is_near_constant
        out.append(
            {
                "target": target,
                "family": family,
                "n_finite": n,
                "n_unique": n_unique,
                "min": min_v,
                "max": max_v,
                "mean": mean_v,
                "std": std_v,
                "range": range_v,
                "is_constant": is_constant,
                "is_near_constant": is_near_constant,
                "include_in_overall_learning_score": include_in_overall,
                "normalization_note": "Use nRMSE_by_std/range for cross-target comparison; raw RMSE is target-scale dependent.",
            }
        )
    return out


def _target_diag_map(target_diagnostics: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {str(row.get("target")): row for row in list(target_diagnostics or [])}


def _informative_targets(target_diagnostics: list[dict[str, Any]] | None, target_columns: list[str]) -> list[str]:
    if not target_diagnostics:
        return list(target_columns)
    out = [str(row["target"]) for row in target_diagnostics if row.get("include_in_overall_learning_score")]
    return out or list(target_columns)


def _annotate_summary_rows_with_informative_metrics(
    summary_rows: list[dict[str, Any]],
    target_columns: list[str],
    target_diagnostics: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Add broad-score fields that exclude constant/near-constant targets.

    The original overall metrics remain for backward compatibility. New fields
    named *_informative_mean average only targets with non-trivial variance.
    """
    informative = _informative_targets(target_diagnostics, target_columns)
    excluded = [t for t in target_columns if t not in set(informative)]
    for row in summary_rows:
        row["informative_target_columns"] = list(informative)
        row["excluded_from_informative_score_target_columns"] = list(excluded)
        for split_name in ["train", "val", "test"]:
            for metric in ["r2", "rmse", "mae", "nrmse_by_std", "nrmse_by_range"]:
                row[f"{split_name}_{metric}_informative_mean"] = _mean_optional(
                    row.get(f"{split_name}_{metric}__{target}_mean") for target in informative
                )
    return summary_rows


def _classify_target_learning_state(test_r2: float | None, delta_last: float | None, gap: float | None) -> str:
    """Return a compact operator label for one target's learning curve."""
    if test_r2 is None:
        return "unknown"
    if test_r2 < 0.5:
        return "weak"
    if test_r2 < 0.8:
        return "moderate"
    if gap is not None and gap > 0.25:
        return "overfit_risk"
    if delta_last is not None and abs(delta_last) < 0.02:
        return "strong_plateau"
    return "strong_improving"


def _target_recommendation(target: str, state: str, test_r2: float | None, delta_last: float | None, gap: float | None) -> str:
    """Return a plain-language recommendation for one target."""
    value = "unknown" if test_r2 is None else f"{test_r2:.3f}"
    if state == "weak":
        return f"Target '{target}' is weak at the largest size (test R²={value}); do not use it for paper-scale claims or MDAO before feature/regime diagnosis."
    if state == "moderate":
        return f"Target '{target}' is moderate at the largest size (test R²={value}); useful for pilot insight, but needs more data/model comparison before promotion."
    if state == "overfit_risk":
        return f"Target '{target}' has strong apparent accuracy but a large train-test gap ({gap:.3f}); inspect grouped split/regime mismatch before trusting it."
    if state == "strong_plateau":
        delta = "unknown" if delta_last is None else f"{delta_last:.3f}"
        return f"Target '{target}' is strong and appears near plateau (test R²={value}, last-step ΔR²={delta}); extra geometries may have diminishing returns for this target."
    if state == "strong_improving":
        delta = "unknown" if delta_last is None else f"{delta_last:.3f}"
        return f"Target '{target}' is strong and still improving (test R²={value}, last-step ΔR²={delta}); scaling may still help."
    return f"Target '{target}' could not be classified; inspect the per-target curve rows."


def _build_per_target_summary(
    summary_rows: list[dict[str, Any]],
    target_columns: list[str],
    target_diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build an operator-facing per-target final/plateau table with normalized errors."""
    if not summary_rows:
        return []
    diag_by_target = _target_diag_map(target_diagnostics)
    last = summary_rows[-1]
    prev = summary_rows[-2] if len(summary_rows) >= 2 else None
    out: list[dict[str, Any]] = []
    for target in target_columns:
        diag = diag_by_target.get(target, {})
        train_r2 = last.get(f"train_r2__{target}_mean")
        val_r2 = last.get(f"val_r2__{target}_mean")
        test_r2 = last.get(f"test_r2__{target}_mean")
        test_rmse = last.get(f"test_rmse__{target}_mean")
        test_mae = last.get(f"test_mae__{target}_mean")
        test_nrmse_std = last.get(f"test_nrmse_by_std__{target}_mean")
        test_nrmse_range = last.get(f"test_nrmse_by_range__{target}_mean")
        prev_test_r2 = None if prev is None else prev.get(f"test_r2__{target}_mean")
        delta_last = None
        if test_r2 is not None and prev_test_r2 is not None:
            delta_last = float(test_r2) - float(prev_test_r2)
        gap = None
        if train_r2 is not None and test_r2 is not None:
            gap = float(train_r2) - float(test_r2)

        best_group_size = None
        best_test_r2 = None
        for row in summary_rows:
            val = row.get(f"test_r2__{target}_mean")
            if val is None:
                continue
            if best_test_r2 is None or float(val) > float(best_test_r2):
                best_test_r2 = float(val)
                best_group_size = int(row.get("group_size"))

        is_near_constant = bool(diag.get("is_near_constant", False))
        state = "constant_or_near_constant" if is_near_constant else _classify_target_learning_state(
            None if test_r2 is None else float(test_r2),
            None if delta_last is None else float(delta_last),
            None if gap is None else float(gap),
        )
        if is_near_constant:
            recommendation = (
                f"Target '{target}' is constant or near-constant in this dataset; do not treat high R² as evidence of learned physics."
            )
        else:
            recommendation = _target_recommendation(
                target,
                state,
                None if test_r2 is None else float(test_r2),
                None if delta_last is None else float(delta_last),
                None if gap is None else float(gap),
            )
        out.append(
            {
                "target": target,
                "target_family": diag.get("family", _target_family(target)),
                "target_std": diag.get("std"),
                "target_range": diag.get("range"),
                "target_n_unique": diag.get("n_unique"),
                "is_constant": bool(diag.get("is_constant", False)),
                "is_near_constant": is_near_constant,
                "include_in_overall_learning_score": bool(diag.get("include_in_overall_learning_score", True)),
                "largest_group_size": int(last.get("group_size")),
                "train_r2_at_largest": train_r2,
                "val_r2_at_largest": val_r2,
                "test_r2_at_largest": test_r2,
                "test_rmse_at_largest": test_rmse,
                "test_mae_at_largest": test_mae,
                "test_nrmse_by_std_at_largest": test_nrmse_std,
                "test_nrmse_by_range_at_largest": test_nrmse_range,
                "delta_test_r2_last_step": delta_last,
                "train_test_r2_gap_at_largest": gap,
                "best_group_size_by_test_r2": best_group_size,
                "best_test_r2_mean": best_test_r2,
                "learning_state": state,
                "recommendation": recommendation,
            }
        )
    return out


def _learning_curve_recommendations(summary_rows: list[dict[str, Any]], target_columns: list[str]) -> list[str]:
    if not summary_rows:
        return ["No computed learning-curve points. Check group sizes and split settings."]
    recommendations: list[str] = []
    last = summary_rows[-1]
    test_r2 = last.get("test_r2_informative_mean", last.get("test_r2_mean_mean"))
    train_r2 = last.get("train_r2_informative_mean", last.get("train_r2_mean_mean"))
    excluded = last.get("excluded_from_informative_score_target_columns", []) or []
    if excluded:
        recommendations.append(
            "Excluded constant/near-constant targets from informative overall score: " + ", ".join(map(str, excluded)) + "."
        )
    if test_r2 is not None:
        if test_r2 < 0.5:
            recommendations.append(
                f"Informative-target test R² at largest training size is low ({test_r2:.3f}); increase data, revise features, or try a stronger model before promotion."
            )
        elif test_r2 < 0.8:
            recommendations.append(
                f"Informative-target test R² at largest training size is moderate ({test_r2:.3f}); useful for pilot analysis, but not yet strong evidence."
            )
        else:
            recommendations.append(
                f"Informative-target test R² at largest training size is strong ({test_r2:.3f}); inspect per-target curves before promotion."
            )
    if test_r2 is not None and train_r2 is not None and train_r2 - test_r2 > 0.25:
        recommendations.append(
            f"Large train-test R² gap on informative targets ({train_r2 - test_r2:.3f}); likely overfit or grouped-distribution mismatch."
        )
    if len(summary_rows) >= 2:
        prev = summary_rows[-2].get("test_r2_informative_mean", summary_rows[-2].get("test_r2_mean_mean"))
        cur = summary_rows[-1].get("test_r2_informative_mean", summary_rows[-1].get("test_r2_mean_mean"))
        if prev is not None and cur is not None:
            delta = cur - prev
            if abs(delta) < 0.02:
                recommendations.append(
                    f"Informative-target test R² improved by only {delta:.3f} over the last curve step; possible plateau."
                )
            elif delta > 0.05:
                recommendations.append(
                    f"Informative-target test R² still improved by {delta:.3f} over the last curve step; more geometries may help."
                )
    per_target = _build_per_target_summary(summary_rows, target_columns)
    for row in per_target:
        if row.get("learning_state") == "constant_or_near_constant":
            continue
        recommendations.append(str(row.get("recommendation")))
    recommendations.append(
        "Use normalized RMSE (nRMSE by target std/range) for cross-target comparison; raw RMSE is not comparable across CD, Cm, L/D, and Xnp."
    )
    return recommendations


def _write_summary_markdown(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# AERIS ML Learning Curves Summary")
    lines.append("")
    lines.append("## Run")
    cfg = report.get("config", {})
    lines.append(f"- dataset: `{cfg.get('dataset_path')}`")
    lines.append(f"- model_type: `{cfg.get('model_type')}`")
    lines.append(f"- split_method: `{cfg.get('split_method')}`")
    lines.append(f"- group_column: `{cfg.get('group_column')}`")
    lines.append(f"- group_sizes_requested: `{cfg.get('group_sizes')}`")
    lines.append(f"- seeds: `{cfg.get('seeds')}`")
    lines.append("")
    lines.append("## Largest computed size")
    summary_rows = report.get("summary_rows", [])
    if summary_rows:
        last = summary_rows[-1]
        gap = None
        if last.get("train_r2_mean_mean") is not None and last.get("test_r2_mean_mean") is not None:
            gap = last.get("train_r2_mean_mean") - last.get("test_r2_mean_mean")
        lines.append(f"- group_size: `{last.get('group_size')}`")
        lines.append(f"- test R² mean: `{last.get('test_r2_mean_mean')}`")
        lines.append(f"- test RMSE mean: `{last.get('test_rmse_mean_mean')}`")
        lines.append(f"- train-test R² gap: `{gap}`")
    else:
        lines.append("- no computed points")
    per_target = report.get("per_target_summary", [])
    lines.append("")
    lines.append("## Per-target readiness")
    if per_target:
        lines.append("| target | family | state | test R² | nRMSE/std | nRMSE/range | ΔR² last step | train-test gap | best size | recommendation |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in per_target:
            lines.append(
                "| "
                + str(row.get("target"))
                + " | "
                + str(row.get("target_family"))
                + " | "
                + str(row.get("learning_state"))
                + " | "
                + str(row.get("test_r2_at_largest"))
                + " | "
                + str(row.get("test_nrmse_by_std_at_largest"))
                + " | "
                + str(row.get("test_nrmse_by_range_at_largest"))
                + " | "
                + str(row.get("delta_test_r2_last_step"))
                + " | "
                + str(row.get("train_test_r2_gap_at_largest"))
                + " | "
                + str(row.get("best_group_size_by_test_r2"))
                + " | "
                + str(row.get("recommendation"))
                + " |"
            )
    else:
        lines.append("- no per-target summary available")
    lines.append("")
    lines.append("## Recommendations")
    for rec in report.get("operator_recommendations", []):
        lines.append(f"- {rec}")
    lines.append("")
    lines.append("## Notes")
    lines.append("- For grouped split, group size means number of training groups/geometries, not total rows.")
    lines.append("- Curves are grouped-leakage-safe when `split_method=grouped` and `group_column` is a geometry/family ID.")
    lines.append("- Use per-target readiness before deciding whether CL/CD/Cm are all paper-ready.")
    lines.append("- Raw RMSE/MAE are target-scale dependent. Prefer nRMSE columns for comparing CD, Cm, L/D, and Xnp.")
    lines.append("- Constant or near-constant targets are tracked but excluded from informative overall score fields.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plot_metric_curve(
    *,
    summary_rows: list[dict[str, Any]],
    output_path: Path,
    metric: str,
    ylabel: str,
) -> Path | None:
    if not summary_rows:
        return None
    import matplotlib.pyplot as plt

    xs = [row["group_size"] for row in summary_rows]
    fig, ax = plt.subplots(figsize=(8, 5))
    for split_name in ["train", "val", "test"]:
        ys = [row.get(f"{split_name}_{metric}_mean") for row in summary_rows]
        if any(y is not None for y in ys):
            ax.plot(xs, ys, marker="o", label=split_name)
    ax.set_xlabel("Training groups" if len(xs) else "Training size")
    ax.set_ylabel(ylabel)
    ax.set_title(ylabel + " vs training size")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _plot_per_target_r2(
    *,
    summary_rows: list[dict[str, Any]],
    target_columns: list[str],
    output_path: Path,
) -> Path | None:
    if not summary_rows or not target_columns:
        return None
    import matplotlib.pyplot as plt

    xs = [row["group_size"] for row in summary_rows]
    fig_width = max(10.0, min(18.0, 0.9 * len(target_columns) + 6.0))
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    for target in target_columns:
        ys = [row.get(f"test_r2__{target}_mean") for row in summary_rows]
        if any(y is not None for y in ys):
            ax.plot(xs, ys, marker="o", label=target)
    ax.set_xlabel("Training groups")
    ax.set_ylabel("Test R²")
    ax.set_title("Per-target test R² learning curves")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize="small")
    fig.tight_layout(rect=(0, 0, 0.82, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _plot_gap(
    *,
    summary_rows: list[dict[str, Any]],
    output_path: Path,
) -> Path | None:
    if not summary_rows:
        return None
    import matplotlib.pyplot as plt

    xs: list[int] = []
    ys: list[float] = []
    for row in summary_rows:
        train = row.get("train_r2_mean_mean")
        test = row.get("test_r2_mean_mean")
        if train is not None and test is not None:
            xs.append(int(row["group_size"]))
            ys.append(float(train) - float(test))
    if not xs:
        return None
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(xs, ys, marker="o")
    ax.axhline(0.0, linewidth=1)
    ax.set_xlabel("Training groups")
    ax.set_ylabel("Train R² - Test R²")
    ax.set_title("Overfit / distribution-gap indicator")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path



def _plot_per_target_final_r2(
    *,
    per_target_summary: list[dict[str, Any]],
    output_path: Path,
) -> Path | None:
    if not per_target_summary:
        return None
    import matplotlib.pyplot as plt

    labels = [str(row.get("target")) for row in per_target_summary]
    xs = np.arange(len(labels))
    width = 0.25
    train = [row.get("train_r2_at_largest") for row in per_target_summary]
    val = [row.get("val_r2_at_largest") for row in per_target_summary]
    test = [row.get("test_r2_at_largest") for row in per_target_summary]
    fig_width = max(10.0, min(20.0, 0.75 * len(labels) + 5.0))
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    ax.bar(xs - width, [np.nan if v is None else float(v) for v in train], width, label="train")
    ax.bar(xs, [np.nan if v is None else float(v) for v in val], width, label="val")
    ax.bar(xs + width, [np.nan if v is None else float(v) for v in test], width, label="test")
    ax.axhline(0.8, linewidth=1, linestyle="--")
    ax.axhline(0.5, linewidth=1, linestyle=":")
    for i, row in enumerate(per_target_summary):
        if row.get("is_near_constant"):
            ax.text(i, 0.03, "const", rotation=90, ha="center", va="bottom", fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("R² at largest training size")
    ax.set_title("Per-target final learning readiness")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _plot_informative_metric_curve(
    *,
    summary_rows: list[dict[str, Any]],
    output_path: Path,
    metric_key: str,
    ylabel: str,
    title: str,
) -> Path | None:
    if not summary_rows:
        return None
    import matplotlib.pyplot as plt

    xs = [row["group_size"] for row in summary_rows]
    fig, ax = plt.subplots(figsize=(8, 5))
    wrote = False
    for split_name in ["train", "val", "test"]:
        ys = [row.get(f"{split_name}_{metric_key}_informative_mean") for row in summary_rows]
        if any(y is not None for y in ys):
            ax.plot(xs, ys, marker="o", label=split_name)
            wrote = True
    if not wrote:
        plt.close(fig)
        return None
    ax.set_xlabel("Training groups")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _plot_per_target_final_nrmse(
    *,
    per_target_summary: list[dict[str, Any]],
    output_path: Path,
) -> Path | None:
    usable = [row for row in per_target_summary if not row.get("is_near_constant")]
    if not usable:
        return None
    import matplotlib.pyplot as plt

    labels = [str(row.get("target")) for row in usable]
    xs = np.arange(len(labels))
    by_std = [row.get("test_nrmse_by_std_at_largest") for row in usable]
    by_range = [row.get("test_nrmse_by_range_at_largest") for row in usable]
    fig_width = max(10.0, min(20.0, 0.75 * len(labels) + 5.0))
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    width = 0.35
    ax.bar(xs - width / 2, [np.nan if v is None else float(v) for v in by_std], width, label="nRMSE/std")
    ax.bar(xs + width / 2, [np.nan if v is None else float(v) for v in by_range], width, label="nRMSE/range")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("Normalized RMSE at largest training size")
    ax.set_title("Per-target normalized error")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _write_plots(output_dir: Path, summary_rows: list[dict[str, Any]], target_columns: list[str], per_target_summary: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    plots_dir = output_dir / "plots"
    artifacts: list[dict[str, Any]] = []
    for kind, metric, ylabel, filename in [
        ("learning_curve_r2", "r2_mean", "R²", "learning_curve_r2.png"),
        ("learning_curve_rmse", "rmse_mean", "RMSE", "learning_curve_rmse.png"),
        ("learning_curve_mae", "mae_mean", "MAE", "learning_curve_mae.png"),
    ]:
        path = _plot_metric_curve(
            summary_rows=summary_rows,
            output_path=plots_dir / filename,
            metric=metric,
            ylabel=ylabel,
        )
        artifacts.append({"kind": kind, "status": "written" if path else "skipped", "path": None if path is None else str(path)})
    path = _plot_per_target_r2(summary_rows=summary_rows, target_columns=target_columns, output_path=plots_dir / "per_target_learning_curves.png")
    artifacts.append({"kind": "per_target_learning_curves", "status": "written" if path else "skipped", "path": None if path is None else str(path)})
    path = _plot_gap(summary_rows=summary_rows, output_path=plots_dir / "overfit_gap.png")
    artifacts.append({"kind": "overfit_gap", "status": "written" if path else "skipped", "path": None if path is None else str(path)})
    path = _plot_per_target_final_r2(
        per_target_summary=list(per_target_summary or []),
        output_path=plots_dir / "per_target_final_r2.png",
    )
    artifacts.append({"kind": "per_target_final_r2", "status": "written" if path else "skipped", "path": None if path is None else str(path)})
    path = _plot_informative_metric_curve(
        summary_rows=summary_rows,
        output_path=plots_dir / "learning_curve_informative_r2.png",
        metric_key="r2",
        ylabel="Informative-target mean R²",
        title="Informative-target R² vs training size",
    )
    artifacts.append({"kind": "learning_curve_informative_r2", "status": "written" if path else "skipped", "path": None if path is None else str(path)})
    path = _plot_informative_metric_curve(
        summary_rows=summary_rows,
        output_path=plots_dir / "learning_curve_nrmse_by_std.png",
        metric_key="nrmse_by_std",
        ylabel="Informative-target mean nRMSE/std",
        title="Normalized RMSE vs training size",
    )
    artifacts.append({"kind": "learning_curve_nrmse_by_std", "status": "written" if path else "skipped", "path": None if path is None else str(path)})
    path = _plot_per_target_final_nrmse(
        per_target_summary=list(per_target_summary or []),
        output_path=plots_dir / "per_target_final_nrmse.png",
    )
    artifacts.append({"kind": "per_target_final_nrmse", "status": "written" if path else "skipped", "path": None if path is None else str(path)})
    return artifacts


def run_learning_curves_on_dataframe(
    *,
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str,
    group_sizes: Sequence[int],
    seeds: Sequence[int],
    split_method: str = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    model_params: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    dataset_path: Path | None = None,
    write_plots: bool = False,
    feature_set_name: str | None = None,
    feature_preset_name: str | None = None,
    allow_forced: bool = False,
) -> dict[str, Any]:
    """Run grouped/random learning curves on an already materialized ML dataframe."""
    if split_method not in {"grouped", "random"}:
        raise ValueError("split_method must be 'grouped' or 'random'.")
    if split_method == "grouped" and group_column not in df.columns:
        raise ValueError(f"Grouped learning curves require group column '{group_column}'.")
    missing_features = [c for c in feature_columns if c not in df.columns]
    missing_targets = [c for c in target_columns if c not in df.columns]
    if missing_features:
        raise ValueError(f"Missing feature columns: {missing_features}")
    if missing_targets:
        raise ValueError(f"Missing target columns: {missing_targets}")

    group_sizes = parse_int_csv(list(group_sizes), option_name="group_sizes")
    seeds = parse_int_csv(list(seeds), option_name="seeds")
    spec = get_model_spec(model_type)
    output_dir = _make_output_dir(dataset_path, model_type, output_dir)

    rows: list[dict[str, Any]] = []
    split_metadata: list[dict[str, Any]] = []
    for seed in seeds:
        split = split_dataset(
            df,
            method=split_method,  # type: ignore[arg-type]
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=int(seed),
        )
        split_metadata.append({"seed": int(seed), "metadata": split.metadata})
        ordered_groups: list[Any] = []
        ordered_indices = np.arange(len(split.train_df))
        if split_method == "grouped":
            ordered_groups = _ordered_training_groups(split.train_df, group_column, int(seed))
        else:
            rng = np.random.default_rng(int(seed) + 104729)
            ordered_indices = rng.permutation(len(split.train_df))

        for requested_size in group_sizes:
            train_subset, selection = _select_training_subset(
                split_method=split_method,
                train_df=split.train_df,
                group_column=group_column,
                group_size=int(requested_size),
                ordered_groups=ordered_groups,
                ordered_indices=ordered_indices,
            )
            base_row: dict[str, Any] = {
                "seed": int(seed),
                "group_size_requested": int(requested_size),
                "group_size_used": int(selection.get("group_size_used", 0)),
                "status": selection.get("status"),
                "reason": selection.get("reason"),
                "n_train_rows": int(len(train_subset)),
                "n_val_rows": int(len(split.val_df)),
                "n_test_rows": int(len(split.test_df)),
            }
            if selection.get("status") != "computed":
                rows.append(base_row)
                continue
            model = build_model(model_type=model_type, random_seed=int(seed), model_params=model_params)
            metrics = _evaluate_model(
                model=model,
                train_df=train_subset,
                val_df=split.val_df,
                test_df=split.test_df,
                feature_columns=feature_columns,
                target_columns=target_columns,
            )
            base_row.update(_flatten_metrics_row(prefix="train", metrics=metrics, target_columns=target_columns))
            base_row.update(_flatten_metrics_row(prefix="val", metrics=metrics, target_columns=target_columns))
            base_row.update(_flatten_metrics_row(prefix="test", metrics=metrics, target_columns=target_columns))
            rows.append(base_row)

    summary_rows = _build_summary_rows(rows, target_columns)
    target_diagnostics = _target_diagnostics(df, target_columns)
    summary_rows = _annotate_summary_rows_with_informative_metrics(summary_rows, target_columns, target_diagnostics)
    per_target_summary = _build_per_target_summary(summary_rows, target_columns, target_diagnostics)
    plot_artifacts = _write_plots(output_dir, summary_rows, target_columns, per_target_summary) if write_plots else []
    report = {
        "schema_version": LEARNING_CURVES_SCHEMA_VERSION,
        "status": "completed",
        "config": {
            "dataset_path": None if dataset_path is None else str(Path(dataset_path).expanduser().resolve()),
            "feature_columns": list(feature_columns),
            "target_columns": list(target_columns),
            "feature_set_name": feature_set_name,
            "feature_preset_name": feature_preset_name,
            "model_type": model_type,
            "model_display_name": spec.display_name,
            "model_family_name": spec.family_name,
            "model_params": dict(model_params or {}),
            "split_method": split_method,
            "group_column": group_column,
            "group_sizes": list(group_sizes),
            "seeds": list(seeds),
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "allow_forced": allow_forced,
        },
        "shape": {
            "n_rows": int(len(df)),
            "n_features": int(len(feature_columns)),
            "n_targets": int(len(target_columns)),
            "n_informative_targets": int(len(_informative_targets(target_diagnostics, target_columns))),
            "n_constant_or_near_constant_targets": int(sum(1 for row in target_diagnostics if row.get("is_near_constant"))),
            "n_groups": int(df[group_column].nunique()) if group_column in df.columns else None,
        },
        "split_metadata": split_metadata,
        "rows": rows,
        "summary_rows": summary_rows,
        "target_diagnostics": target_diagnostics,
        "informative_target_columns": _informative_targets(target_diagnostics, target_columns),
        "excluded_from_informative_score_target_columns": [t for t in target_columns if t not in set(_informative_targets(target_diagnostics, target_columns))],
        "per_target_summary": per_target_summary,
        "normalization": {
            "used_for_training": False,
            "evaluation_normalized_metrics": ["nrmse_by_std", "nrmse_by_range"],
            "note": "Targets are not rescaled before fitting in this command. For cross-target comparison, use nRMSE metrics; raw RMSE is target-scale dependent.",
        },
        "operator_recommendations": _learning_curve_recommendations(summary_rows, target_columns),
        "plot_artifacts": plot_artifacts,
    }

    rows_csv = output_dir / "learning_curves.csv"
    summary_csv = output_dir / "learning_curves_summary.csv"
    target_summary_csv = output_dir / "learning_curves_per_target_summary.csv"
    target_diagnostics_csv = output_dir / "learning_curves_target_diagnostics.csv"
    report_json = output_dir / "learning_curves_report.json"
    summary_md = output_dir / "learning_curves_summary.md"
    _write_csv(rows_csv, rows)
    _write_csv(summary_csv, summary_rows)
    _write_csv(target_summary_csv, per_target_summary)
    _write_csv(target_diagnostics_csv, target_diagnostics)
    _write_json(report_json, report)
    _write_summary_markdown(summary_md, report)

    report["artifacts"] = {
        "output_dir": str(output_dir),
        "learning_curves_csv": str(rows_csv),
        "learning_curves_summary_csv": str(summary_csv),
        "learning_curves_per_target_summary_csv": str(target_summary_csv),
        "learning_curves_target_diagnostics_csv": str(target_diagnostics_csv),
        "learning_curves_report_json": str(report_json),
        "learning_curves_summary_md": str(summary_md),
        "plots_dir": str(output_dir / "plots") if write_plots else None,
    }
    _write_json(report_json, report)
    return report


def _materialize_dataset_for_learning_curves(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    allow_forced: bool,
    feature_set_name: str | None,
    group_column: str,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    feature_set: FeatureSet | None = None
    load_features = list(feature_columns)
    final_features = list(feature_columns)
    feature_set_payload: dict[str, Any] | None = None
    transforms: list[str] | None = None
    if feature_set_name:
        feature_set = get_feature_set(feature_set_name)
        load_features = list(feature_set.required_source_columns)
        final_features = list(feature_set.columns)
        transforms = list(feature_set.transforms)
        feature_set_payload = feature_set.to_dict()

    training_data = load_training_data(
        dataset_path=dataset_path,
        feature_columns=load_features,
        target_columns=target_columns,
        allow_forced=allow_forced,
    )
    df, fe_manifest = apply_feature_engineering(training_data.df, transforms=transforms)
    if feature_set is not None:
        validation = validate_feature_set_dataframe(
            df,
            feature_set=feature_set,
            target_columns=target_columns,
            group_column=group_column,
        )
        if not validation.passed:
            messages = [f"{issue.code}: {issue.message}" for issue in validation.errors]
            raise ValueError("Feature-set validation failed before learning curves: " + "; ".join(messages))

    missing_final = [col for col in final_features if col not in df.columns]
    if missing_final:
        raise ValueError(f"Learning-curve final features are missing after materialization: {missing_final}")

    metadata = {
        "training_data": training_data.metadata,
        "feature_engineering": fe_manifest,
        "feature_set": feature_set_payload,
    }
    return df, final_features, metadata


def run_learning_curves(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str,
    group_sizes: Sequence[int],
    seeds: Sequence[int],
    split_method: str = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    allow_forced: bool = False,
    model_params: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    write_plots: bool = False,
    feature_set_name: str | None = None,
    feature_preset_name: str | None = None,
) -> dict[str, Any]:
    """Run ML learning curves from a promoted AERIS dataset root."""
    dataset_path = Path(dataset_path).expanduser().resolve()
    df, final_features, materialization = _materialize_dataset_for_learning_curves(
        dataset_path=dataset_path,
        feature_columns=feature_columns,
        target_columns=target_columns,
        allow_forced=allow_forced,
        feature_set_name=feature_set_name,
        group_column=group_column,
    )
    report = run_learning_curves_on_dataframe(
        df=df,
        feature_columns=final_features,
        target_columns=target_columns,
        model_type=model_type,
        group_sizes=group_sizes,
        seeds=seeds,
        split_method=split_method,
        group_column=group_column,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        model_params=model_params,
        output_dir=output_dir,
        dataset_path=dataset_path,
        write_plots=write_plots,
        feature_set_name=feature_set_name,
        feature_preset_name=feature_preset_name,
        allow_forced=allow_forced,
    )
    report["materialization"] = materialization
    _write_json(Path(report["artifacts"]["learning_curves_report_json"]), report)
    return report
