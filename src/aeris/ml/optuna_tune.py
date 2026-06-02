from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal

from aeris.ml.config import load_json_mapping, load_ml_experiment_config
from aeris.ml.fingerprints import file_sha256
from aeris.ml.model_registry import list_model_types
from aeris.ml.train import train_baseline_model

OptunaSamplerName = Literal["tpe", "random"]
FailPolicy = Literal["continue", "raise"]


def load_optuna_param_space_json(path: str | Path) -> dict[str, Any]:
    """Load an Optuna search-space JSON without AERIS grid/random normalization.

    The normal AERIS tuner expands every parameter value into a list so it can
    build grid/random trials. That is correct for the AERIS backend, but wrong
    for Optuna, where dictionaries such as {"type": "float", "low": ...,
    "high": ...} are semantic distribution specs and must be preserved.

    Accepted formats:
    1) {"alpha": {"type": "float", "low": 0.01, "high": 10.0}}
    2) {"params": {"alpha": {"type": "float", "low": 0.01, "high": 10.0}},
        "search": {"backend": "optuna", "sampler": "tpe"}}
    """
    payload = load_json_mapping(path)
    raw_params = payload.get("params", payload)
    if not isinstance(raw_params, dict) or not raw_params:
        raise ValueError("Optuna tuning JSON must contain a non-empty parameter mapping or 'params' mapping.")

    return {
        "params": dict(raw_params),
        "search": dict(payload.get("search", {}) or {}),
    }


def optuna_available() -> bool:
    """Return True when Optuna is importable in the current environment."""
    try:
        import optuna  # noqa: F401
    except Exception:
        return False
    return True


def _require_optuna():
    try:
        import optuna
    except Exception as exc:  # pragma: no cover - exercised when optional dep missing
        raise RuntimeError(
            "Optuna is not installed. Install it with `pip install optuna` "
            "or use the default AERIS tuner with `--backend aeris`."
        ) from exc
    return optuna


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


def _metric_from_result(metrics: dict[str, Any], selection_metric: str) -> float:
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


def _normalize_space_spec(name: str, spec: Any) -> dict[str, Any]:
    """Normalize AERIS/Optuna parameter-space specifications.

    Supported inputs:
    - [1, 2, 3] or scalar -> categorical choices
    - {"type": "categorical", "choices": [...]}
    - {"type": "int", "low": 1, "high": 10, "step": 1, "log": false}
    - {"type": "float", "low": 1e-4, "high": 1.0, "log": true}
    - {"type": "fixed", "value": ...}
    """
    if isinstance(spec, dict) and "type" in spec:
        kind = str(spec["type"]).strip().lower()
        if kind in {"categorical", "choice", "choices"}:
            choices = spec.get("choices", spec.get("values"))
            if not isinstance(choices, list) or not choices:
                raise ValueError(f"Optuna parameter '{name}' requires a non-empty choices list.")
            return {"type": "categorical", "choices": choices}
        if kind == "int":
            if "low" not in spec or "high" not in spec:
                raise ValueError(f"Optuna int parameter '{name}' requires low/high.")
            return {
                "type": "int",
                "low": int(spec["low"]),
                "high": int(spec["high"]),
                "step": None if spec.get("step") is None else int(spec["step"]),
                "log": bool(spec.get("log", False)),
            }
        if kind == "float":
            if "low" not in spec or "high" not in spec:
                raise ValueError(f"Optuna float parameter '{name}' requires low/high.")
            return {
                "type": "float",
                "low": float(spec["low"]),
                "high": float(spec["high"]),
                "step": None if spec.get("step") is None else float(spec["step"]),
                "log": bool(spec.get("log", False)),
            }
        if kind == "fixed":
            return {"type": "fixed", "value": spec.get("value")}
        raise ValueError(f"Unsupported Optuna parameter type for '{name}': {kind}")

    if isinstance(spec, list):
        if not spec:
            raise ValueError(f"Optuna parameter '{name}' has an empty choice list.")
        return {"type": "categorical", "choices": spec}

    return {"type": "fixed", "value": spec}


def suggest_params_from_space(trial: Any, param_space: dict[str, Any]) -> dict[str, Any]:
    """Suggest model parameters from an AERIS Optuna search-space mapping."""
    if not isinstance(param_space, dict) or not param_space:
        raise ValueError("Optuna parameter space must be a non-empty mapping.")

    suggested: dict[str, Any] = {}
    for name, raw_spec in param_space.items():
        param_name = str(name)
        spec = _normalize_space_spec(param_name, raw_spec)
        kind = spec["type"]

        if kind == "categorical":
            suggested[param_name] = trial.suggest_categorical(param_name, list(spec["choices"]))
        elif kind == "int":
            kwargs: dict[str, Any] = {"log": bool(spec.get("log", False))}
            if spec.get("step") is not None:
                kwargs["step"] = int(spec["step"])
            suggested[param_name] = trial.suggest_int(
                param_name,
                int(spec["low"]),
                int(spec["high"]),
                **kwargs,
            )
        elif kind == "float":
            kwargs = {"log": bool(spec.get("log", False))}
            if spec.get("step") is not None:
                kwargs["step"] = float(spec["step"])
            suggested[param_name] = trial.suggest_float(
                param_name,
                float(spec["low"]),
                float(spec["high"]),
                **kwargs,
            )
        elif kind == "fixed":
            suggested[param_name] = spec.get("value")
        else:  # pragma: no cover - guarded by normalizer
            raise ValueError(f"Unsupported normalized Optuna parameter type: {kind}")

    return suggested


def _make_sampler(optuna: Any, *, sampler_name: str, seed: int) -> Any:
    name = str(sampler_name).strip().lower()
    if name in {"tpe", "tp"}:
        return optuna.samplers.TPESampler(seed=int(seed))
    if name in {"random", "random_sampler"}:
        return optuna.samplers.RandomSampler(seed=int(seed))
    raise ValueError("Optuna sampler must be 'tpe' or 'random'.")


def _trial_status(trial: Any) -> str:
    state_name = getattr(trial.state, "name", str(trial.state)).lower()
    if "complete" in state_name:
        return "success"
    if "pruned" in state_name:
        return "pruned"
    if "fail" in state_name:
        return "failed"
    return state_name


def _load_trial_metrics(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "metrics.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_trial_run_payload(
    *,
    trial_row: dict[str, Any],
    metrics: dict[str, Any] | None,
    run_dir: Path,
) -> dict[str, Any]:
    artifacts = {
        "run_dir": str(run_dir),
        "model_path": str(run_dir / "models" / "model.pkl"),
        "metrics_path": str(run_dir / "metrics.json"),
        "ml_run_manifest_path": str(run_dir / "ml_run_manifest.json"),
    }
    payload = dict(trial_row)
    payload["metrics"] = metrics
    payload["artifacts"] = artifacts
    return payload


def _rank_successful_rows(rows: list[dict[str, Any]], *, minimize: bool) -> list[dict[str, Any]]:
    successful = [r for r in rows if r.get("status") == "success" and r.get("selection_score") is not None]
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


def tune_model_optuna(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str,
    param_space: dict[str, Any],
    n_trials: int = 20,
    sampler_name: OptunaSamplerName = "tpe",
    tuning_random_seed: int = 123,
    study_name: str | None = None,
    storage: str | None = None,
    load_if_exists: bool = True,
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
    fail_policy: FailPolicy = "continue",
    source_config_path: Path | None = None,
    source_param_space_path: Path | None = None,
    feature_set_name: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run Optuna-backed hyperparameter tuning while preserving AERIS artifacts."""
    optuna = _require_optuna()

    dataset_path = Path(dataset_path).expanduser().resolve()
    if model_type not in list_model_types():
        raise ValueError(f"Unsupported model type '{model_type}'. Supported: {', '.join(list_model_types())}")
    if int(n_trials) <= 0:
        raise ValueError("Optuna tuning requires n_trials > 0.")

    if output_dir is None:
        output_dir = (
            Path("data")
            / "processed"
            / "ml_tuning"
            / f"optuna_{model_type}__{dataset_path.name}__seed{random_seed}"
        )
    output_dir = _ensure_output_dir(Path(output_dir))
    trials_root = _ensure_output_dir(output_dir / "trials")

    base_params = dict(base_model_params or {})
    direction = "minimize" if minimize else "maximize"
    sampler = _make_sampler(optuna, sampler_name=sampler_name, seed=tuning_random_seed)

    if study_name is None:
        study_name = f"aeris_{model_type}_{dataset_path.name}_seed{random_seed}"

    study = optuna.create_study(
        direction=direction,
        study_name=study_name,
        storage=storage,
        sampler=sampler,
        load_if_exists=load_if_exists,
    )

    def objective(trial: Any) -> float:
        trial_id = f"trial_{int(trial.number):04d}"
        trial_output_dir = trials_root / trial_id
        trial_params = suggest_params_from_space(trial, param_space)
        merged_params = dict(base_params)
        merged_params.update(trial_params)

        trial.set_user_attr("aeris_trial_id", trial_id)
        trial.set_user_attr("run_dir", str(trial_output_dir))
        trial.set_user_attr("model_params", merged_params)

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
        score = _metric_from_result(result["metrics"], selection_metric)
        trial.set_user_attr("selection_score", float(score))
        trial.set_user_attr("metrics_path", str(trial_output_dir / "metrics.json"))
        return float(score)

    catch = () if fail_policy == "raise" else (Exception,)
    study.optimize(objective, n_trials=int(n_trials), catch=catch)

    rows: list[dict[str, Any]] = []
    for trial in study.trials:
        trial_id = str(trial.user_attrs.get("aeris_trial_id") or f"trial_{int(trial.number):04d}")
        run_dir = Path(str(trial.user_attrs.get("run_dir") or trials_root / trial_id))
        metrics = _load_trial_metrics(run_dir)
        params = dict(trial.user_attrs.get("model_params") or trial.params or {})
        selection_score = trial.value
        row: dict[str, Any] = {
            "trial_id": trial_id,
            "trial_index": int(trial.number),
            "optuna_trial_number": int(trial.number),
            "status": _trial_status(trial),
            "model_type": model_type,
            "model_params": params,
            "params_json": json.dumps(params, sort_keys=True, default=str),
            "selection_metric": selection_metric,
            "selection_score": None if selection_score is None else float(selection_score),
            "rank": None,
            "run_dir": str(run_dir),
            "failure_message": None,
            "train_rmse_mean": None if metrics is None else _safe_metric(metrics, "train", "rmse_mean"),
            "val_rmse_mean": None if metrics is None else _safe_metric(metrics, "val", "rmse_mean"),
            "test_rmse_mean": None if metrics is None else _safe_metric(metrics, "test", "rmse_mean"),
            "train_mae_mean": None if metrics is None else _safe_metric(metrics, "train", "mae_mean"),
            "val_mae_mean": None if metrics is None else _safe_metric(metrics, "val", "mae_mean"),
            "test_mae_mean": None if metrics is None else _safe_metric(metrics, "test", "mae_mean"),
            "train_r2_mean": None if metrics is None else _safe_metric(metrics, "train", "r2_mean"),
            "val_r2_mean": None if metrics is None else _safe_metric(metrics, "val", "r2_mean"),
            "test_r2_mean": None if metrics is None else _safe_metric(metrics, "test", "r2_mean"),
        }
        if row["status"] != "success":
            row["failure_message"] = str(getattr(trial, "system_attrs", {}).get("fail_reason", "")) or None
        rows.append(row)

    rows = _rank_successful_rows(rows, minimize=minimize)
    best_row = next((r for r in rows if r.get("rank") == 1), None)
    best_run = None
    trial_runs: list[dict[str, Any]] = []
    for row in rows:
        run_dir = Path(str(row["run_dir"]))
        metrics = _load_trial_metrics(run_dir)
        run_payload = _build_trial_run_payload(trial_row=row, metrics=metrics, run_dir=run_dir)
        trial_runs.append(run_payload)
        if best_row is not None and row["trial_id"] == best_row["trial_id"]:
            best_run = run_payload

    source_config_sha256 = None
    if source_config_path is not None:
        source_config_sha256 = file_sha256(Path(source_config_path).expanduser().resolve())
    source_param_space_sha256 = None
    if source_param_space_path is not None:
        source_param_space_sha256 = file_sha256(Path(source_param_space_path).expanduser().resolve())

    summary = {
        "schema_version": "aeris.ml_optuna_tuning_summary.v1",
        "status": "success" if best_row is not None else "failed",
        "backend": "optuna",
        "dataset_path": str(dataset_path),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "feature_set_name": feature_set_name,
        "model_type": model_type,
        "study": {
            "study_name": study.study_name,
            "storage": storage,
            "direction": direction,
            "sampler": str(sampler_name),
            "load_if_exists": load_if_exists,
        },
        "search": {
            "strategy": "optuna",
            "n_trials_requested": int(n_trials),
            "max_trials": int(n_trials),
            "tuning_random_seed": int(tuning_random_seed),
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
        "n_pruned_trials": sum(1 for r in rows if r.get("status") == "pruned"),
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
        "study": study,
    }


def tune_model_optuna_from_config(
    config_path: str | Path,
    *,
    param_space: dict[str, Any],
    n_trials: int = 20,
    sampler_name: OptunaSamplerName = "tpe",
    tuning_random_seed: int = 123,
    study_name: str | None = None,
    storage: str | None = None,
    load_if_exists: bool = True,
    selection_metric: str = "val.rmse_mean",
    minimize: bool = True,
    fail_policy: FailPolicy = "continue",
    source_param_space_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    cfg_path = Path(config_path).expanduser().resolve()
    cfg = load_ml_experiment_config(cfg_path)
    return tune_model_optuna(
        dataset_path=cfg.dataset_path,
        feature_columns=cfg.feature_columns,
        target_columns=cfg.target_columns,
        model_type=cfg.model_type,
        param_space=param_space,
        n_trials=n_trials,
        sampler_name=sampler_name,
        tuning_random_seed=tuning_random_seed,
        study_name=study_name,
        storage=storage,
        load_if_exists=load_if_exists,
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
