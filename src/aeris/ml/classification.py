"""Classification utilities for flyability and red-flag labels.

DYN-4 boundary
---------------
This module adds ML classification infrastructure only. It does not run AVL,
XFOIL, CFD, dynamics solvers, nonlinear trim, or MIL-STD assessment. It consumes
promoted/curated tabular datasets, applies the same optional feature-set
materialization used by regression training, then trains classifier models for
operator-facing flyability labels.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from aeris.dataset.promoted_dataset import require_promoted_aero_dataset
from aeris.dataset.splitting import DatasetSplit, split_dataset
from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import FeatureSet, get_feature_set, validate_feature_set_dataframe
from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import build_environment_snapshot, utc_now_iso

SplitMethod = Literal["grouped", "random"]


@dataclass(frozen=True)
class ClassifierSpec:
    classifier_type: str
    display_name: str
    family_name: str
    supports_probabilities: bool


_CLASSIFIER_SPECS: dict[str, ClassifierSpec] = {
    "logistic_regression": ClassifierSpec(
        "logistic_regression", "Logistic Regression", "linear", True
    ),
    "random_forest_classifier": ClassifierSpec(
        "random_forest_classifier", "Random Forest Classifier", "tree_ensemble", True
    ),
    "extra_trees_classifier": ClassifierSpec(
        "extra_trees_classifier", "Extra Trees Classifier", "tree_ensemble", True
    ),
    "gradient_boosting_classifier": ClassifierSpec(
        "gradient_boosting_classifier", "Gradient Boosting Classifier", "boosting", True
    ),
    "hist_gradient_boosting_classifier": ClassifierSpec(
        "hist_gradient_boosting_classifier", "Histogram Gradient Boosting Classifier", "boosting", True
    ),
}


def list_classifier_types() -> list[str]:
    """Return supported classifier identifiers."""
    return sorted(_CLASSIFIER_SPECS)


def get_classifier_spec(classifier_type: str) -> ClassifierSpec:
    try:
        return _CLASSIFIER_SPECS[classifier_type]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported classifier_type '{classifier_type}'. "
            f"Supported: {', '.join(list_classifier_types())}"
        ) from exc


def _merge_params(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(defaults)
    params.update(overrides or {})
    return params


def build_classifier(
    *,
    classifier_type: str,
    random_seed: int = 123,
    model_params: dict[str, Any] | None = None,
) -> object:
    """Build one sklearn classifier instance.

    The returned model is a single-target classifier. Multi-target label training
    is handled by fitting one classifier per target column.
    """
    get_classifier_spec(classifier_type)

    if classifier_type == "logistic_regression":
        params = _merge_params(
            {
                "max_iter": 2000,
                "class_weight": "balanced",
                "random_state": random_seed,
            },
            model_params,
        )
        return Pipeline([("scaler", StandardScaler()), ("model", LogisticRegression(**params))])

    if classifier_type == "random_forest_classifier":
        params = _merge_params(
            {
                "n_estimators": 300,
                "random_state": random_seed,
                "n_jobs": -1,
                "class_weight": "balanced_subsample",
            },
            model_params,
        )
        return RandomForestClassifier(**params)

    if classifier_type == "extra_trees_classifier":
        params = _merge_params(
            {
                "n_estimators": 300,
                "random_state": random_seed,
                "n_jobs": -1,
                "class_weight": "balanced",
            },
            model_params,
        )
        return ExtraTreesClassifier(**params)

    if classifier_type == "gradient_boosting_classifier":
        params = _merge_params(
            {
                "n_estimators": 200,
                "learning_rate": 0.05,
                "max_depth": 3,
                "random_state": random_seed,
            },
            model_params,
        )
        return GradientBoostingClassifier(**params)

    if classifier_type == "hist_gradient_boosting_classifier":
        params = _merge_params(
            {
                "learning_rate": 0.05,
                "max_iter": 300,
                "max_depth": None,
                "random_state": random_seed,
            },
            model_params,
        )
        return HistGradientBoostingClassifier(**params)

    raise AssertionError("unreachable")


def _default_output_dir(dataset_path: Path, classifier_type: str, random_seed: int) -> Path:
    return (
        Path("data")
        / "processed"
        / "ml_runs"
        / f"classification__{classifier_type}__{dataset_path.name}__seed{random_seed}"
    )


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    return value


def _class_counts(values: Any) -> dict[str, int]:
    series = pd.Series(values)
    counts = series.value_counts(dropna=False)
    return {str(_json_safe_value(k)): int(v) for k, v in counts.items()}


def _labels_for_confusion(y_true: Any, y_pred: Any) -> list[Any]:
    labels = list(pd.Series(list(y_true) + list(y_pred)).dropna().unique())
    return sorted(labels, key=lambda x: str(x))


def _extract_probability_for_positive(model: object, X: np.ndarray, positive_class: Any) -> np.ndarray | None:
    if not hasattr(model, "predict_proba"):
        return None
    try:
        proba = model.predict_proba(X)
    except Exception:
        return None
    classes = getattr(model, "classes_", None)
    if classes is None and hasattr(model, "named_steps"):
        final = list(getattr(model, "named_steps").values())[-1]
        classes = getattr(final, "classes_", None)
    if classes is None:
        return None
    classes_list = list(classes)
    if positive_class not in classes_list:
        return None
    idx = classes_list.index(positive_class)
    arr = np.asarray(proba)
    if arr.ndim != 2 or idx >= arr.shape[1]:
        return None
    return arr[:, idx]


def _evaluate_target_classification(
    *,
    y_true: Any,
    y_pred: Any,
    model: object,
    X: np.ndarray,
) -> dict[str, Any]:
    y_true_s = pd.Series(y_true)
    y_pred_s = pd.Series(y_pred)
    labels = _labels_for_confusion(y_true_s, y_pred_s)

    metrics: dict[str, Any] = {
        "n_rows": int(len(y_true_s)),
        "n_classes_true": int(y_true_s.nunique(dropna=True)),
        "n_classes_pred": int(y_pred_s.nunique(dropna=True)),
        "true_class_counts": _class_counts(y_true_s),
        "pred_class_counts": _class_counts(y_pred_s),
        "labels": [str(_json_safe_value(x)) for x in labels],
        "accuracy": float(accuracy_score(y_true_s, y_pred_s)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true_s, y_pred_s)),
        "precision_weighted": float(
            precision_score(y_true_s, y_pred_s, average="weighted", zero_division=0)
        ),
        "recall_weighted": float(
            recall_score(y_true_s, y_pred_s, average="weighted", zero_division=0)
        ),
        "f1_weighted": float(f1_score(y_true_s, y_pred_s, average="weighted", zero_division=0)),
        "precision_macro": float(
            precision_score(y_true_s, y_pred_s, average="macro", zero_division=0)
        ),
        "recall_macro": float(recall_score(y_true_s, y_pred_s, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true_s, y_pred_s, average="macro", zero_division=0)),
    }

    cm = confusion_matrix(y_true_s, y_pred_s, labels=labels)
    metrics["confusion_matrix"] = {
        "labels": [str(_json_safe_value(x)) for x in labels],
        "matrix": cm.astype(int).tolist(),
    }

    metrics["roc_auc"] = None
    if y_true_s.nunique(dropna=True) == 2 and len(labels) == 2:
        positive_class = labels[-1]
        y_score = _extract_probability_for_positive(model, X, positive_class)
        if y_score is not None:
            try:
                metrics["roc_auc"] = float(roc_auc_score(y_true_s, y_score))
                metrics["roc_auc_positive_class"] = str(_json_safe_value(positive_class))
            except Exception:
                metrics["roc_auc"] = None

    return metrics


def _write_prediction_rows(
    *,
    partition_name: str,
    df: pd.DataFrame,
    target_columns: list[str],
    predictions: dict[str, np.ndarray],
    output_dir: Path,
) -> Path:
    out = df.copy()
    for target in target_columns:
        out[f"true__{target}"] = df[target].to_numpy()
        out[f"pred__{target}"] = predictions[target]
    path = output_dir / f"classification_predictions_{partition_name}.csv"
    out.to_csv(path, index=False)
    return path


def _load_classification_frame(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    allow_forced: bool,
    output_dir: Path,
    group_column: str,
    feature_set_name: str | None = None,
) -> tuple[pd.DataFrame, list[str], dict[str, Any], Path | None]:
    dataset_path = Path(dataset_path).expanduser().resolve()
    promoted_info = require_promoted_aero_dataset(
        dataset_root=dataset_path,
        allow_forced=allow_forced,
    )
    curated_csv = Path(promoted_info["curated_aero_dataset_csv"]).expanduser().resolve()
    if not curated_csv.exists():
        raise FileNotFoundError(f"Promoted curated dataset CSV not found: {curated_csv}")

    df = pd.read_csv(curated_csv)
    if df.empty:
        raise ValueError(f"Curated dataset is empty: {curated_csv}")

    feature_set: FeatureSet | None = None
    final_feature_columns = list(feature_columns)
    raw_source_columns = list(feature_columns)
    feature_set_metadata: dict[str, Any] | None = None
    feature_engineering_manifest_path: Path | None = None

    if feature_set_name is not None:
        feature_set = get_feature_set(feature_set_name)
        feature_set_metadata = feature_set.to_dict()
        raw_source_columns = list(feature_set.required_source_columns)
        final_feature_columns = list(feature_set.columns)
        if list(feature_columns) and list(feature_columns) != final_feature_columns:
            raise ValueError(
                f"feature_columns must match feature set '{feature_set.name}' final columns when feature_set_name is used. "
                f"Expected {final_feature_columns}; got {list(feature_columns)}"
            )

    missing_source = [c for c in raw_source_columns if c not in df.columns]
    missing_targets = [c for c in target_columns if c not in df.columns]
    if missing_source:
        raise ValueError(f"Missing feature/source columns: {missing_source}. Available columns: {list(df.columns)}")
    if missing_targets:
        raise ValueError(f"Missing target columns: {missing_targets}. Available columns: {list(df.columns)}")

    if feature_set is not None:
        feature_engineering_manifest_path = output_dir / "feature_engineering_manifest.json"
        df, _ = apply_feature_engineering(
            df,
            transforms=list(feature_set.transforms),
            manifest_path=feature_engineering_manifest_path,
        )
        validation = validate_feature_set_dataframe(
            df,
            feature_set=feature_set,
            target_columns=target_columns,
            group_column=group_column,
        )
        if not validation.passed:
            messages = [f"{issue.code}: {issue.message}" for issue in validation.errors]
            raise ValueError("Feature-set validation failed before classification: " + "; ".join(messages))

    missing_final = [c for c in final_feature_columns if c not in df.columns]
    if missing_final:
        raise ValueError(f"Missing final feature columns after transforms: {missing_final}")

    # Features must be numeric/finite; targets may be bool, int, or string labels.
    feature_frame = df[final_feature_columns].apply(pd.to_numeric, errors="coerce")
    feature_finite = np.isfinite(feature_frame.to_numpy(dtype=float)).all(axis=1)
    targets_present = df[target_columns].notna().all(axis=1).to_numpy()
    keep = feature_finite & targets_present
    dropped = int((~keep).sum())
    df = df.loc[keep].copy()
    for col in final_feature_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df.empty:
        raise ValueError("No valid rows remain after filtering non-finite features / missing labels.")

    metadata = {
        "dataset_path": str(dataset_path),
        "curated_csv_path": str(curated_csv),
        "promotion_context": promoted_info,
        "n_rows": int(len(df)),
        "dropped_invalid_rows": dropped,
        "feature_columns": list(final_feature_columns),
        "target_columns": list(target_columns),
        "feature_set_name": None if feature_set is None else feature_set.name,
        "feature_set": feature_set_metadata,
        "raw_source_columns": raw_source_columns,
    }
    return df, final_feature_columns, metadata, feature_engineering_manifest_path


def classify_targets(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    classifier_type: str = "logistic_regression",
    split_method: SplitMethod = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
    allow_forced: bool = False,
    model_params: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    feature_set_name: str | None = None,
) -> dict[str, Any]:
    """Train one classifier per requested target and write classification artifacts."""
    dataset_path = Path(dataset_path).expanduser().resolve()
    if output_dir is None:
        output_dir = _default_output_dir(dataset_path, classifier_type, random_seed)
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    spec = get_classifier_spec(classifier_type)
    df, final_feature_columns, data_metadata, fe_manifest_path = _load_classification_frame(
        dataset_path=dataset_path,
        feature_columns=feature_columns,
        target_columns=target_columns,
        allow_forced=allow_forced,
        output_dir=output_dir,
        group_column=group_column,
        feature_set_name=feature_set_name,
    )

    split: DatasetSplit = split_dataset(
        df,
        method=split_method,
        group_column=group_column,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        random_seed=random_seed,
    )

    X_train = split.train_df[final_feature_columns].to_numpy(dtype=float)
    X_val = split.val_df[final_feature_columns].to_numpy(dtype=float)
    X_test = split.test_df[final_feature_columns].to_numpy(dtype=float)

    base_model = build_classifier(
        classifier_type=classifier_type,
        random_seed=random_seed,
        model_params=model_params,
    )

    models: dict[str, object] = {}
    fallback_targets: dict[str, str] = {}
    predictions: dict[str, dict[str, np.ndarray]] = {"train": {}, "val": {}, "test": {}}
    metrics: dict[str, Any] = {
        "model": {
            "classifier_type": spec.classifier_type,
            "display_name": spec.display_name,
            "family_name": spec.family_name,
            "supports_probabilities": spec.supports_probabilities,
        },
        "targets": {},
        "train": {"targets": {}},
        "val": {"targets": {}},
        "test": {"targets": {}},
    }

    for target in target_columns:
        y_train = split.train_df[target]
        y_val = split.val_df[target]
        y_test = split.test_df[target]

        if y_train.nunique(dropna=True) < 2:
            model = DummyClassifier(strategy="most_frequent")
            fallback_targets[target] = "train_partition_has_one_class_used_dummy_classifier"
        else:
            model = clone(base_model)

        model.fit(X_train, y_train)
        models[target] = model

        predictions["train"][target] = np.asarray(model.predict(X_train))
        predictions["val"][target] = np.asarray(model.predict(X_val))
        predictions["test"][target] = np.asarray(model.predict(X_test))

        metrics["train"]["targets"][target] = _evaluate_target_classification(
            y_true=y_train,
            y_pred=predictions["train"][target],
            model=model,
            X=X_train,
        )
        metrics["val"]["targets"][target] = _evaluate_target_classification(
            y_true=y_val,
            y_pred=predictions["val"][target],
            model=model,
            X=X_val,
        )
        metrics["test"]["targets"][target] = _evaluate_target_classification(
            y_true=y_test,
            y_pred=predictions["test"][target],
            model=model,
            X=X_test,
        )

    for partition in ("train", "val", "test"):
        target_metrics = metrics[partition]["targets"]
        metrics[partition]["overall"] = {
            "accuracy_mean": float(np.mean([m["accuracy"] for m in target_metrics.values()])),
            "balanced_accuracy_mean": float(np.mean([m["balanced_accuracy"] for m in target_metrics.values()])),
            "f1_weighted_mean": float(np.mean([m["f1_weighted"] for m in target_metrics.values()])),
            "f1_macro_mean": float(np.mean([m["f1_macro"] for m in target_metrics.values()])),
        }

    artifacts_dir = output_dir
    models_dir = artifacts_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "classifier_models.pkl"
    with model_path.open("wb") as f:
        pickle.dump(models, f)

    train_pred_path = _write_prediction_rows(
        partition_name="train",
        df=split.train_df,
        target_columns=target_columns,
        predictions=predictions["train"],
        output_dir=artifacts_dir,
    )
    val_pred_path = _write_prediction_rows(
        partition_name="val",
        df=split.val_df,
        target_columns=target_columns,
        predictions=predictions["val"],
        output_dir=artifacts_dir,
    )
    test_pred_path = _write_prediction_rows(
        partition_name="test",
        df=split.test_df,
        target_columns=target_columns,
        predictions=predictions["test"],
        output_dir=artifacts_dir,
    )

    per_target_rows: list[dict[str, Any]] = []
    for partition in ("train", "val", "test"):
        for target, m in metrics[partition]["targets"].items():
            per_target_rows.append(
                {
                    "partition": partition,
                    "target": target,
                    "accuracy": m["accuracy"],
                    "balanced_accuracy": m["balanced_accuracy"],
                    "precision_weighted": m["precision_weighted"],
                    "recall_weighted": m["recall_weighted"],
                    "f1_weighted": m["f1_weighted"],
                    "f1_macro": m["f1_macro"],
                    "roc_auc": m.get("roc_auc"),
                    "n_rows": m["n_rows"],
                    "n_classes_true": m["n_classes_true"],
                }
            )
    per_target_metrics_path = artifacts_dir / "classification_per_target_metrics.csv"
    pd.DataFrame(per_target_rows).to_csv(per_target_metrics_path, index=False)

    summary = {
        "schema_version": "aeris_classification_run_v0.1",
        "created_at_utc": utc_now_iso(),
        "status": "completed",
        "dataset_path": str(dataset_path),
        "classifier_type": spec.classifier_type,
        "feature_columns": list(final_feature_columns),
        "target_columns": list(target_columns),
        "feature_set_name": feature_set_name,
        "split_config": {
            "split_method": split_method,
            "group_column": group_column,
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "random_seed": random_seed,
            "metadata": split.metadata,
        },
        "data": data_metadata,
        "model_params": dict(model_params or {}),
        "fallback_targets": fallback_targets,
        "metrics": metrics,
        "artifacts": {
            "run_dir": str(artifacts_dir),
            "model_pickle": str(model_path),
            "classification_summary_json": str(artifacts_dir / "classification_summary.json"),
            "per_target_metrics_csv": str(per_target_metrics_path),
            "train_predictions_csv": str(train_pred_path),
            "val_predictions_csv": str(val_pred_path),
            "test_predictions_csv": str(test_pred_path),
            "feature_engineering_manifest_json": None if fe_manifest_path is None else str(fe_manifest_path),
        },
        "hashes": {
            "model_pickle_sha256": file_sha256(model_path),
            "test_predictions_csv_sha256": file_sha256(test_pred_path),
        },
        "environment": build_environment_snapshot(),
        "limitations": [
            "classification_infrastructure_only_not_solver_execution",
            "metrics_on_tiny_or_imbalanced_smoke_datasets_are_not_scientific_evidence",
            "one_classifier_is_trained_per_target_column",
            "not_a_full_nonlinear_trim_solver",
            "not_a_mil_std_compliance_claim",
        ],
    }

    summary_path = artifacts_dir / "classification_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def compare_classifiers(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    classifier_types: list[str],
    split_method: SplitMethod = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
    allow_forced: bool = False,
    model_params_by_type: dict[str, dict[str, Any]] | None = None,
    output_dir: Path | None = None,
    feature_set_name: str | None = None,
) -> dict[str, Any]:
    """Run multiple classifiers over the same split configuration and rank them."""
    dataset_path = Path(dataset_path).expanduser().resolve()
    if not classifier_types:
        raise ValueError("classifier_types must not be empty.")
    for classifier_type in classifier_types:
        get_classifier_spec(classifier_type)

    if output_dir is None:
        output_dir = (
            Path("data")
            / "processed"
            / "ml_runs"
            / f"classifier_compare__{dataset_path.name}__seed{random_seed}"
        )
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for classifier_type in classifier_types:
        run_dir = output_dir / classifier_type
        summary = classify_targets(
            dataset_path=dataset_path,
            feature_columns=feature_columns,
            target_columns=target_columns,
            classifier_type=classifier_type,
            split_method=split_method,
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=random_seed,
            allow_forced=allow_forced,
            model_params=(model_params_by_type or {}).get(classifier_type),
            output_dir=run_dir,
            feature_set_name=feature_set_name,
        )
        test_overall = summary["metrics"]["test"]["overall"]
        row = {
            "classifier_type": classifier_type,
            "run_dir": str(run_dir),
            "test_accuracy_mean": test_overall["accuracy_mean"],
            "test_balanced_accuracy_mean": test_overall["balanced_accuracy_mean"],
            "test_f1_weighted_mean": test_overall["f1_weighted_mean"],
            "test_f1_macro_mean": test_overall["f1_macro_mean"],
        }
        rows.append(row)
        runs.append({"classifier_type": classifier_type, "summary": summary})

    df = pd.DataFrame(rows)
    for metric in [
        "test_f1_weighted_mean",
        "test_balanced_accuracy_mean",
        "test_accuracy_mean",
        "test_f1_macro_mean",
    ]:
        df[f"rank_{metric}"] = df[metric].rank(method="min", ascending=False).astype(int)

    best_by_f1 = str(df.sort_values(["test_f1_weighted_mean", "test_balanced_accuracy_mean"], ascending=False).iloc[0]["classifier_type"])
    best_by_balanced_accuracy = str(df.sort_values(["test_balanced_accuracy_mean", "test_f1_weighted_mean"], ascending=False).iloc[0]["classifier_type"])

    comparison_csv = output_dir / "classifier_comparison_summary.csv"
    df.to_csv(comparison_csv, index=False)

    report = {
        "schema_version": "aeris_classifier_comparison_v0.1",
        "created_at_utc": utc_now_iso(),
        "status": "completed",
        "dataset_path": str(dataset_path),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "feature_set_name": feature_set_name,
        "classifier_types": list(classifier_types),
        "split_config": {
            "split_method": split_method,
            "group_column": group_column,
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "random_seed": random_seed,
        },
        "best_by_f1_weighted": best_by_f1,
        "best_by_balanced_accuracy": best_by_balanced_accuracy,
        "rows": df.to_dict(orient="records"),
        "runs": [
            {
                "classifier_type": r["classifier_type"],
                "run_dir": r["summary"]["artifacts"]["run_dir"],
                "classification_summary_json": r["summary"]["artifacts"]["classification_summary_json"],
                "test_overall": r["summary"]["metrics"]["test"]["overall"],
            }
            for r in runs
        ],
        "artifacts": {
            "output_dir": str(output_dir),
            "classifier_comparison_summary_json": str(output_dir / "classifier_comparison_summary.json"),
            "classifier_comparison_summary_csv": str(comparison_csv),
        },
        "limitations": [
            "classification_comparison_infrastructure_only",
            "smoke_dataset_metrics_are_not_scientific_model_quality_evidence",
        ],
    }
    comparison_json = output_dir / "classifier_comparison_summary.json"
    comparison_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
