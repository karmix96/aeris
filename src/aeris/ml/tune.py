from __future__ import annotations

import csv
import itertools
import json
import random
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal

from aeris.ml.config import load_json_mapping, load_ml_experiment_config
from aeris.ml.fingerprints import file_sha256
from aeris.ml.model_registry import list_model_types
from aeris.ml.train import train_baseline_model

TuningStrategy = Literal["grid", "random"]


def _ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    if not fieldnames:
        fieldnames = ["trial_id", "status"]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _normalize_param_values(param_space: dict[str, Any]) -> dict[str, list[Any]]:
    if not isinstance(param_space, dict) or not param_space:
        raise ValueError("Tuning parameter space must be a non-empty mapping.")

    normalized: dict[str, list[Any]] = {}
    for key, value in param_space.items():
        if isinstance(value, list):
            values = value
        elif isinstance(value, tuple):
            values = list(value)
        else:
            values = [value]
        if not values:
            raise ValueError(f"Parameter '{key}' has an empty value list.")
        normalized[str(key)] = values
    return normalized


def load_tuning_param_space_json(path: str | Path) -> dict[str, Any]:
    """Load tuning parameter-space JSON.

    Accepted formats:
    1) {"n_estimators": [50, 100], "max_depth": [2, 3]}
    2) {"params": {"n_estimators": [50, 100]}, "search": {"strategy": "grid"}}
    """
    payload = load_json_mapping(path)
    raw_params = payload.get("params", payload)
    if not isinstance(raw_params, dict):
        raise ValueError("Tuning JSON must contain a parameter mapping or a 'params' mapping.")

    return {
        "params": _normalize_param_values(raw_params),
        "search": dict(payload.get("search", {}) or {}),
    }


def build_param_trials(
    param_space: dict[str, Any],
    *,
    strategy: TuningStrategy = "grid",
    max_trials: int | None = None,
    random_seed: int = 123,
) -> list[dict[str, Any]]:
    """Build deterministic hyperparameter trial dictionaries."""
    params = _normalize_param_values(param_space)
    strategy = str(strategy).lower()
    keys = list(params.keys())

    if strategy == "grid":
        combos = [dict(zip(keys, values)) for values in itertools.product(*(params[k] for k in keys))]
        if max_trials is not None:
            combos = combos[: int(max_trials)]
        return combos

    if strategy == "random":
        if max_trials is None or max_trials <= 0:
            raise ValueError("Random tuning requires max_trials > 0.")
        rng = random.Random(int(random_seed))
        trials: list[dict[str, Any]] = []
        seen: set[str] = set()
        max_attempts = max(int(max_trials) * 20, 100)
        attempts = 0
        while len(trials) < int(max_trials) and attempts < max_attempts:
            attempts += 1
            trial = {key: rng.choice(params[key]) for key in keys}
            signature = json.dumps(trial, sort_keys=True, default=str)
            if signature in seen:
                continue
            seen.add(signature)
            trials.append(trial)
        if not trials:
            raise ValueError("Random tuning produced zero trials.")
        return trials

    raise ValueError("Tuning strategy must be 'grid' or 'random'.")


def _metric_from_result(metrics: dict[str, Any], selection_metric: str) -> float:
    """Extract a scalar metric from train result metrics.

    Supported examples:
    - val.rmse_mean
    - test.r2_mean
    - val.overall.rmse_mean
    """
    parts = selection_metric.split(".")
    if len(parts) == 2:
        partition, metric_name = parts
        return float(metrics[partition]["overall"][metric_name])
    if len(parts) == 3 and parts[1] == "overall":
        partition, _, metric_name = parts
        return float(metrics[partition]["overall"][metric_name])
    raise ValueError(
        "selection_metric must look like 'val.rmse_mean', 'test.r2_mean', "
        "or 'val.overall.rmse_mean'."
    )


def _safe_metric(metrics: dict[str, Any], partition: str, metric_name: str) -> float | None:
    try:
        return float(metrics[partition]["overall"][metric_name])
    except Exception:
        return None


def _rank_successful_trials(
    rows: list[dict[str, Any]],
    *,
    minimize: bool,
) -> list[dict[str, Any]]:
    successful = [r for r in rows if r.get("status") == "success"]
    successful_sorted = sorted(
        successful,
        key=lambda r: (float(r["selection_score"]), int(r["trial_index"])),
        reverse=not minimize,
    )
    for rank, row in enumerate(successful_sorted, start=1):
        row["rank"] = rank
    for row in rows:
        if row.get("status") != "success":
            row["rank"] = None
    return rows


def tune_model(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str,
    param_space: dict[str, Any],
    strategy: TuningStrategy = "grid",
    max_trials: int | None = None,
    tuning_random_seed: int = 123,
    split_method: str = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
    allow_forced: bool = False,
    base_model_params: dict[str, Any] | None = None,
    selection_metric: str = "val.rmse_mean",
    minimize: bool = True,
    fail_policy: Literal["continue", "raise"] = "continue",
    source_config_path: Path | None = None,
    source_param_space_path: Path | None = None,
    feature_set_name: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run a deterministic hyperparameter tuning campaign for one model family."""
    dataset_path = Path(dataset_path).expanduser().resolve()
    if model_type not in list_model_types():
        raise ValueError(f"Unsupported model type '{model_type}'. Supported: {', '.join(list_model_types())}")

    trials = build_param_trials(
        param_space,
        strategy=strategy,
        max_trials=max_trials,
        random_seed=tuning_random_seed,
    )

    if output_dir is None:
        output_dir = (
            Path("data")
            / "processed"
            / "ml_tuning"
            / f"{model_type}__{dataset_path.name}__seed{random_seed}"
        )
    output_dir = _ensure_output_dir(Path(output_dir))
    trials_root = _ensure_output_dir(output_dir / "trials")

    rows: list[dict[str, Any]] = []
    trial_runs: list[dict[str, Any]] = []
    base_params = dict(base_model_params or {})

    for trial_index, trial_params in enumerate(trials):
        trial_id = f"trial_{trial_index:04d}"
        trial_output_dir = trials_root / trial_id
        merged_params = dict(base_params)
        merged_params.update(trial_params)

        row: dict[str, Any] = {
            "trial_id": trial_id,
            "trial_index": trial_index,
            "status": "pending",
            "model_type": model_type,
            "params_json": json.dumps(merged_params, sort_keys=True, default=str),
            "selection_metric": selection_metric,
            "selection_score": None,
            "rank": None,
            "run_dir": str(trial_output_dir),
            "failure_message": None,
        }

        try:
            result = train_baseline_model(
                dataset_path=dataset_path,
                feature_columns=feature_columns,
                target_columns=target_columns,
                model_type=model_type,
                split_method=split_method,
                group_column=group_column,
                train_fraction=train_fraction,
                val_fraction=val_fraction,
                test_fraction=test_fraction,
                random_seed=random_seed,
                allow_forced=allow_forced,
                model_params=merged_params,
                output_dir=trial_output_dir,
                source_config_path=source_config_path,
                feature_set_name=feature_set_name,
            )
            metrics = result["metrics"]
            row.update(
                {
                    "status": "success",
                    "selection_score": _metric_from_result(metrics, selection_metric),
                    "train_rmse_mean": _safe_metric(metrics, "train", "rmse_mean"),
                    "train_mae_mean": _safe_metric(metrics, "train", "mae_mean"),
                    "train_r2_mean": _safe_metric(metrics, "train", "r2_mean"),
                    "val_rmse_mean": _safe_metric(metrics, "val", "rmse_mean"),
                    "val_mae_mean": _safe_metric(metrics, "val", "mae_mean"),
                    "val_r2_mean": _safe_metric(metrics, "val", "r2_mean"),
                    "test_rmse_mean": _safe_metric(metrics, "test", "rmse_mean"),
                    "test_mae_mean": _safe_metric(metrics, "test", "mae_mean"),
                    "test_r2_mean": _safe_metric(metrics, "test", "r2_mean"),
                }
            )
            trial_runs.append(
                {
                    "trial_id": trial_id,
                    "trial_index": trial_index,
                    "status": "success",
                    "model_type": model_type,
                    "model_params": merged_params,
                    "selection_score": row["selection_score"],
                    "metrics": metrics,
                    "artifacts": {
                        "run_dir": str(result["artifacts"].run_dir),
                        "model_path": str(result["artifacts"].model_path),
                        "metrics_path": str(result["artifacts"].metrics_path),
                        "ml_run_manifest_path": (
                            None if result["artifacts"].ml_run_manifest_path is None else str(result["artifacts"].ml_run_manifest_path)
                        ),
                    },
                }
            )
        except Exception as exc:
            if fail_policy == "raise":
                raise
            row.update({"status": "failed", "failure_message": str(exc)})
            trial_runs.append(
                {
                    "trial_id": trial_id,
                    "trial_index": trial_index,
                    "status": "failed",
                    "model_type": model_type,
                    "model_params": merged_params,
                    "failure_message": str(exc),
                    "artifacts": {"run_dir": str(trial_output_dir)},
                }
            )
        rows.append(row)

    rows = _rank_successful_trials(rows, minimize=minimize)
    best_row = next((r for r in rows if r.get("rank") == 1), None)
    best_run = None
    if best_row is not None:
        best_run = next((r for r in trial_runs if r["trial_id"] == best_row["trial_id"]), None)

    source_config_sha256 = None
    if source_config_path is not None:
        source_config_sha256 = file_sha256(Path(source_config_path).expanduser().resolve())
    source_param_space_sha256 = None
    if source_param_space_path is not None:
        source_param_space_sha256 = file_sha256(Path(source_param_space_path).expanduser().resolve())

    summary = {
        "schema_version": "aeris.ml_tuning_summary.v1",
        "status": "success" if best_row is not None else "failed",
        "dataset_path": str(dataset_path),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "feature_set_name": feature_set_name,
        "model_type": model_type,
        "search": {
            "strategy": strategy,
            "n_trials_requested": len(trials),
            "max_trials": max_trials,
            "tuning_random_seed": tuning_random_seed,
            "selection_metric": selection_metric,
            "minimize": minimize,
            "fail_policy": fail_policy,
        },
        "split_config": {
            "split_method": split_method,
            "group_column": group_column,
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "random_seed": random_seed,
            "allow_forced": allow_forced,
        },
        "source_config": {
            "path": None if source_config_path is None else str(Path(source_config_path).expanduser().resolve()),
            "sha256": source_config_sha256,
        },
        "source_param_space": {
            "path": None if source_param_space_path is None else str(Path(source_param_space_path).expanduser().resolve()),
            "sha256": source_param_space_sha256,
        },
        "n_trials": len(rows),
        "n_successful_trials": sum(1 for r in rows if r.get("status") == "success"),
        "n_failed_trials": sum(1 for r in rows if r.get("status") == "failed"),
        "best_trial": best_run,
        "trials": trial_runs,
    }

    summary_json_path = output_dir / "tuning_summary.json"
    trials_csv_path = output_dir / "tuning_trials.csv"
    best_trial_json_path = output_dir / "best_trial.json"

    summary_json_path.write_text(json.dumps(_to_jsonable(summary), indent=2), encoding="utf-8")
    _write_csv(trials_csv_path, rows)
    best_trial_json_path.write_text(json.dumps(_to_jsonable(best_run or {}), indent=2), encoding="utf-8")

    return {
        "output_dir": output_dir,
        "tuning_summary_json": summary_json_path,
        "tuning_trials_csv": trials_csv_path,
        "best_trial_json": best_trial_json_path,
        "summary": summary,
        "trial_rows": rows,
    }


def tune_model_from_config(
    config_path: str | Path,
    *,
    param_space: dict[str, Any],
    strategy: TuningStrategy = "grid",
    max_trials: int | None = None,
    tuning_random_seed: int = 123,
    selection_metric: str = "val.rmse_mean",
    minimize: bool = True,
    fail_policy: Literal["continue", "raise"] = "continue",
    source_param_space_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    cfg_path = Path(config_path).expanduser().resolve()
    cfg = load_ml_experiment_config(cfg_path)
    return tune_model(
        dataset_path=cfg.dataset_path,
        feature_columns=cfg.feature_columns,
        target_columns=cfg.target_columns,
        model_type=cfg.model_type,
        param_space=param_space,
        strategy=strategy,
        max_trials=max_trials,
        tuning_random_seed=tuning_random_seed,
        split_method=cfg.split_method,
        group_column=cfg.group_column,
        train_fraction=cfg.train_fraction,
        val_fraction=cfg.val_fraction,
        test_fraction=cfg.test_fraction,
        random_seed=cfg.random_seed,
        allow_forced=cfg.allow_forced,
        base_model_params=cfg.model_params,
        selection_metric=selection_metric,
        minimize=minimize,
        fail_policy=fail_policy,
        source_config_path=cfg_path,
        source_param_space_path=source_param_space_path,
        feature_set_name=None,
        output_dir=output_dir if output_dir is not None else cfg.output_dir,
    )
