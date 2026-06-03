"""
PATCH 05 — src/aeris/ml/cross_validation.py  (NEW FILE)
=========================================================
Grouped k-fold cross-validation for AERIS ML.

WHY THIS EXISTS
---------------
A single 70/15/15 split with 50–200 geometries gives a test set of
7–30 geometries. R² and RMSE on that many rows are high-variance statistics.
A model can "win" purely due to which geometries land in test.

Grouped k-fold solves this:
- Split by geometry_id (or any group column) so no geometry leaks
  between train and validation folds.
- K=5 folds → 5 independent evaluations → stable mean ± std.
- Repeated grouped k-fold (R × K) adds further stability.

USAGE
-----
from aeris.ml.cross_validation import (
    grouped_kfold_cv,
    repeated_grouped_kfold_cv,
    CrossValResult,
)

# Single 5-fold CV for one model type
result = grouped_kfold_cv(
    df=training_data.df,
    feature_columns=feature_columns,
    target_columns=target_columns,
    model_type="lightgbm",
    group_column="geometry_id",
    k=5,
    random_seed=123,
)
print(result.mean_metrics)   # per-target mean RMSE/R² across folds
print(result.std_metrics)    # per-target std across folds

# Compare multiple model types with the same folds
from aeris.ml.cross_validation import compare_models_cv

comparison = compare_models_cv(
    df=training_data.df,
    feature_columns=feature_columns,
    target_columns=target_columns,
    model_types=["lightgbm", "extra_trees", "xgboost"],
    group_column="geometry_id",
    k=5,
    random_seed=123,
)

INTEGRATION POINT
-----------------
aeris ml compare --cv-folds 5 --cv-repeats 3 (CLI option in patch_06)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.model_registry import build_model


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class FoldMetrics:
    """Metrics for one (fold, repeat) evaluation."""
    fold: int
    repeat: int
    n_train: int
    n_val: int
    train_groups: list[str]
    val_groups: list[str]
    metrics: dict[str, Any]   # same structure as evaluate_regression_metrics()


@dataclass
class CrossValResult:
    """Aggregated cross-validation result for one model type."""
    model_type: str
    k: int
    n_repeats: int
    n_folds_total: int          # k * n_repeats
    n_groups: int
    group_column: str
    feature_columns: list[str]
    target_columns: list[str]
    fold_results: list[FoldMetrics]
    mean_metrics: dict[str, Any]   # per_target + overall averages
    std_metrics: dict[str, Any]    # per_target + overall std devs
    schema_version: str = "aeris.cross_val_result.v1"


@dataclass
class ModelComparisonCV:
    """Cross-validation comparison across multiple model types."""
    model_types: list[str]
    k: int
    n_repeats: int
    group_column: str
    feature_columns: list[str]
    target_columns: list[str]
    results: dict[str, CrossValResult]  # model_type → CrossValResult
    ranking: list[dict[str, Any]]       # sorted by mean test RMSE
    schema_version: str = "aeris.model_comparison_cv.v1"


# ---------------------------------------------------------------------------
# Group splitting
# ---------------------------------------------------------------------------

def _split_groups_kfold(
    groups: np.ndarray,
    k: int,
    random_seed: int,
    repeat: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Split unique group IDs into k folds.

    Returns list of (train_groups, val_groups) arrays, one per fold.
    Different (k, repeat, random_seed) combinations give different fold
    assignments while remaining deterministic.
    """
    unique_groups = np.unique(groups)
    n_groups = len(unique_groups)

    if n_groups < k:
        raise ValueError(
            f"Cannot create {k} folds from {n_groups} unique groups. "
            f"Reduce --cv-folds to ≤ {n_groups}."
        )

    # Shuffle groups with a seed that depends on the repeat index
    rng = np.random.default_rng(random_seed + repeat * 9973)
    shuffled = unique_groups.copy()
    rng.shuffle(shuffled)

    fold_sizes = [n_groups // k + (1 if i < n_groups % k else 0) for i in range(k)]
    folds: list[np.ndarray] = []
    start = 0
    for size in fold_sizes:
        folds.append(shuffled[start:start + size])
        start += size

    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(k):
        val_groups = folds[i]
        train_groups = np.concatenate([folds[j] for j in range(k) if j != i])
        splits.append((train_groups, val_groups))
    return splits


def _rows_for_groups(df: pd.DataFrame, group_col: str, groups: np.ndarray) -> pd.DataFrame:
    mask = df[group_col].isin(set(groups))
    return df[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-fold evaluation
# ---------------------------------------------------------------------------

def _run_one_fold(
    *,
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str,
    group_column: str,
    train_groups: np.ndarray,
    val_groups: np.ndarray,
    fold: int,
    repeat: int,
    random_seed: int,
    model_params: dict[str, Any] | None = None,
) -> FoldMetrics:
    train_df = _rows_for_groups(df, group_column, train_groups)
    val_df   = _rows_for_groups(df, group_column, val_groups)

    if len(train_df) == 0:
        raise ValueError(f"Fold {fold} repeat {repeat}: train set is empty.")
    if len(val_df) == 0:
        raise ValueError(f"Fold {fold} repeat {repeat}: val set is empty.")

    X_train = train_df[feature_columns].to_numpy(dtype=float)
    y_train = train_df[target_columns].to_numpy(dtype=float)
    X_val   = val_df[feature_columns].to_numpy(dtype=float)
    y_val   = val_df[target_columns].to_numpy(dtype=float)

    # Use fold-specific seed so models within one repeat are independent
    fold_seed = random_seed + repeat * 9973 + fold * 97
    model = build_model(model_type, fold_seed, model_params)
    model.fit(X_train, y_train)

    y_pred_train = np.asarray(model.predict(X_train), dtype=float)
    y_pred_val   = np.asarray(model.predict(X_val),   dtype=float)
    if y_pred_train.ndim == 1: y_pred_train = y_pred_train.reshape(-1, 1)
    if y_pred_val.ndim   == 1: y_pred_val   = y_pred_val.reshape(-1, 1)

    metrics = {
        "train": evaluate_regression_metrics(y_train, y_pred_train, target_columns),
        "val":   evaluate_regression_metrics(y_val,   y_pred_val,   target_columns),
    }

    return FoldMetrics(
        fold=fold,
        repeat=repeat,
        n_train=len(train_df),
        n_val=len(val_df),
        train_groups=[str(g) for g in train_groups],
        val_groups=[str(g) for g in val_groups],
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate_fold_metrics(
    fold_results: list[FoldMetrics],
    target_columns: list[str],
    partition: str = "val",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute mean ± std across folds for one partition."""
    scalar_keys = ["rmse", "mae", "r2", "max_abs_error", "bias_mean",
                   "error_p50", "error_p90", "error_p95", "error_p99",
                   "nrmse_by_std", "nrmse_by_range"]
    overall_keys = ["rmse_mean", "mae_mean", "r2_mean", "max_abs_error_mean"]

    per_target_values: dict[str, dict[str, list[float]]] = {
        t: {k: [] for k in scalar_keys} for t in target_columns
    }
    overall_values: dict[str, list[float]] = {k: [] for k in overall_keys}

    for fr in fold_results:
        part = fr.metrics.get(partition, {})
        pt = part.get("per_target", {})
        ov = part.get("overall", {})
        for t in target_columns:
            t_met = pt.get(t, {})
            for k in scalar_keys:
                v = t_met.get(k)
                if v is not None and np.isfinite(v):
                    per_target_values[t][k].append(float(v))
        for k in overall_keys:
            v = ov.get(k)
            if v is not None and np.isfinite(v):
                overall_values[k].append(float(v))

    def safe_mean(vs: list[float]) -> float | None:
        return float(np.mean(vs)) if vs else None

    def safe_std(vs: list[float]) -> float | None:
        return float(np.std(vs)) if len(vs) > 1 else (0.0 if vs else None)

    mean_pt: dict[str, Any] = {}
    std_pt:  dict[str, Any] = {}
    for t in target_columns:
        mean_pt[t] = {k: safe_mean(per_target_values[t][k]) for k in scalar_keys}
        std_pt[t]  = {k: safe_std(per_target_values[t][k])  for k in scalar_keys}

    mean_metrics = {
        "per_target": mean_pt,
        "overall": {k: safe_mean(overall_values[k]) for k in overall_keys},
        "n_folds": len(fold_results),
        "partition": partition,
    }
    std_metrics = {
        "per_target": std_pt,
        "overall": {k: safe_std(overall_values[k]) for k in overall_keys},
        "n_folds": len(fold_results),
        "partition": partition,
    }
    return mean_metrics, std_metrics


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def grouped_kfold_cv(
    *,
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str,
    group_column: str = "geometry_id",
    k: int = 5,
    random_seed: int = 123,
    model_params: dict[str, Any] | None = None,
) -> CrossValResult:
    """
    Run grouped k-fold cross-validation for one model type.

    Parameters
    ----------
    df:
        Full training DataFrame (after feature engineering, before split).
    feature_columns:
        Final feature column names (post-engineering if applicable).
    target_columns:
        Target column names.
    model_type:
        Any key from model_registry.MODEL_REGISTRY.
    group_column:
        Column used for grouped splitting. Default: geometry_id.
    k:
        Number of folds. Recommend 5.
    random_seed:
        Controls group shuffle. Same seed = same fold assignment.
    model_params:
        Optional hyperparameter overrides passed to build_model().

    Returns
    -------
    CrossValResult with per-fold metrics and mean ± std aggregates.
    """
    if k < 2:
        raise ValueError(f"k must be ≥ 2. Got {k}.")
    if group_column not in df.columns:
        raise ValueError(f"group_column '{group_column}' not in DataFrame columns.")

    groups = df[group_column].to_numpy()
    unique_groups = np.unique(groups)
    n_groups = len(unique_groups)

    splits = _split_groups_kfold(groups, k, random_seed, repeat=0)
    fold_results: list[FoldMetrics] = []

    for fold_idx, (train_groups, val_groups) in enumerate(splits):
        fm = _run_one_fold(
            df=df,
            feature_columns=feature_columns,
            target_columns=target_columns,
            model_type=model_type,
            group_column=group_column,
            train_groups=train_groups,
            val_groups=val_groups,
            fold=fold_idx,
            repeat=0,
            random_seed=random_seed,
            model_params=model_params,
        )
        fold_results.append(fm)

    mean_metrics, std_metrics = _aggregate_fold_metrics(fold_results, target_columns)

    return CrossValResult(
        model_type=model_type,
        k=k,
        n_repeats=1,
        n_folds_total=k,
        n_groups=int(n_groups),
        group_column=group_column,
        feature_columns=list(feature_columns),
        target_columns=list(target_columns),
        fold_results=fold_results,
        mean_metrics=mean_metrics,
        std_metrics=std_metrics,
    )


def repeated_grouped_kfold_cv(
    *,
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str,
    group_column: str = "geometry_id",
    k: int = 5,
    n_repeats: int = 3,
    random_seed: int = 123,
    model_params: dict[str, Any] | None = None,
) -> CrossValResult:
    """
    Run repeated grouped k-fold CV.

    Each repeat uses a different group shuffle (deterministic via repeat index).
    Total evaluations = k × n_repeats. Recommended for small datasets.
    """
    if k < 2:
        raise ValueError(f"k must be ≥ 2. Got {k}.")
    if n_repeats < 1:
        raise ValueError(f"n_repeats must be ≥ 1. Got {n_repeats}.")

    groups = df[group_column].to_numpy()
    unique_groups = np.unique(groups)

    all_fold_results: list[FoldMetrics] = []

    for repeat in range(n_repeats):
        splits = _split_groups_kfold(groups, k, random_seed, repeat=repeat)
        for fold_idx, (train_groups, val_groups) in enumerate(splits):
            fm = _run_one_fold(
                df=df,
                feature_columns=feature_columns,
                target_columns=target_columns,
                model_type=model_type,
                group_column=group_column,
                train_groups=train_groups,
                val_groups=val_groups,
                fold=fold_idx,
                repeat=repeat,
                random_seed=random_seed,
                model_params=model_params,
            )
            all_fold_results.append(fm)

    mean_metrics, std_metrics = _aggregate_fold_metrics(all_fold_results, target_columns)

    return CrossValResult(
        model_type=model_type,
        k=k,
        n_repeats=n_repeats,
        n_folds_total=k * n_repeats,
        n_groups=int(len(unique_groups)),
        group_column=group_column,
        feature_columns=list(feature_columns),
        target_columns=list(target_columns),
        fold_results=all_fold_results,
        mean_metrics=mean_metrics,
        std_metrics=std_metrics,
    )


def compare_models_cv(
    *,
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    model_types: list[str],
    group_column: str = "geometry_id",
    k: int = 5,
    n_repeats: int = 1,
    random_seed: int = 123,
    model_params_map: dict[str, dict[str, Any]] | None = None,
) -> ModelComparisonCV:
    """
    Cross-validate multiple model types on the same k-fold assignment.

    Uses the same fold split for all models so the comparison is fair
    (same geometry groups in each val fold across all models).

    Parameters
    ----------
    model_types:
        List of model_type strings to compare.
    model_params_map:
        Optional {model_type: params_dict} for per-model hyperparameters.

    Returns
    -------
    ModelComparisonCV with per-model CrossValResult and a ranking by val RMSE.
    """
    params_map = model_params_map or {}
    results: dict[str, CrossValResult] = {}

    cv_fn = repeated_grouped_kfold_cv if n_repeats > 1 else grouped_kfold_cv

    for mt in model_types:
        mp = params_map.get(mt)
        kwargs: dict[str, Any] = dict(
            df=df,
            feature_columns=feature_columns,
            target_columns=target_columns,
            model_type=mt,
            group_column=group_column,
            k=k,
            random_seed=random_seed,
            model_params=mp,
        )
        if n_repeats > 1:
            kwargs["n_repeats"] = n_repeats
        results[mt] = cv_fn(**kwargs)  # type: ignore[arg-type]

    # Rank by mean val RMSE (overall)
    ranking: list[dict[str, Any]] = []
    for mt, res in results.items():
        rmse_mean = res.mean_metrics.get("overall", {}).get("rmse_mean")
        rmse_std  = res.std_metrics.get("overall", {}).get("rmse_mean")
        r2_mean   = res.mean_metrics.get("overall", {}).get("r2_mean")
        ranking.append({
            "model_type": mt,
            "val_rmse_mean": rmse_mean,
            "val_rmse_std":  rmse_std,
            "val_r2_mean":   r2_mean,
            "n_folds_total": res.n_folds_total,
        })
    ranking.sort(
        key=lambda x: x["val_rmse_mean"] if x["val_rmse_mean"] is not None else float("inf")
    )

    return ModelComparisonCV(
        model_types=list(model_types),
        k=k,
        n_repeats=n_repeats,
        group_column=group_column,
        feature_columns=list(feature_columns),
        target_columns=list(target_columns),
        results=results,
        ranking=ranking,
    )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _cv_result_to_dict(result: CrossValResult) -> dict[str, Any]:
    """Serialise a CrossValResult to a JSON-safe dict."""
    fold_dicts = [
        {
            "fold": fr.fold,
            "repeat": fr.repeat,
            "n_train": fr.n_train,
            "n_val": fr.n_val,
            "n_train_groups": len(fr.train_groups),
            "n_val_groups":   len(fr.val_groups),
            "metrics": fr.metrics,
        }
        for fr in result.fold_results
    ]
    return {
        "schema_version": result.schema_version,
        "model_type":     result.model_type,
        "k":              result.k,
        "n_repeats":      result.n_repeats,
        "n_folds_total":  result.n_folds_total,
        "n_groups":       result.n_groups,
        "group_column":   result.group_column,
        "feature_columns": result.feature_columns,
        "target_columns":  result.target_columns,
        "mean_metrics":   result.mean_metrics,
        "std_metrics":    result.std_metrics,
        "fold_results":   fold_dicts,
    }


def save_cv_result(result: CrossValResult, path: Path) -> Path:
    """Write CrossValResult to JSON. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_cv_result_to_dict(result), indent=2), encoding="utf-8")
    return path


def save_comparison_cv(comparison: ModelComparisonCV, output_dir: Path) -> dict[str, Path]:
    """Write ModelComparisonCV to JSON files. Returns {name: path} dict."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for mt, res in comparison.results.items():
        p = save_cv_result(res, output_dir / f"cv_{mt}.json")
        paths[f"cv_{mt}"] = p

    summary = {
        "schema_version":  comparison.schema_version,
        "model_types":     comparison.model_types,
        "k":               comparison.k,
        "n_repeats":       comparison.n_repeats,
        "group_column":    comparison.group_column,
        "feature_columns": comparison.feature_columns,
        "target_columns":  comparison.target_columns,
        "ranking":         comparison.ranking,
    }
    summary_path = output_dir / "cv_comparison_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    paths["summary"] = summary_path

    return paths
