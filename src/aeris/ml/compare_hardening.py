from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Sequence

from aeris.ml.compare import compare_models
from aeris.ml.model_registry import list_model_types


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(_to_jsonable(payload), indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    if not fieldnames:
        fieldnames = ["status"]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _normalize_seeds(seeds: Sequence[int]) -> list[int]:
    cleaned: list[int] = []
    seen: set[int] = set()
    for seed in seeds:
        value = int(seed)
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    if not cleaned:
        raise ValueError("At least one seed is required.")
    return cleaned


def _normalize_models(model_types: Sequence[str]) -> list[str]:
    supported = set(list_model_types())
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in model_types:
        model = str(value).strip()
        if not model:
            continue
        if model not in supported:
            raise ValueError(f"Unsupported model type '{model}'. Supported: {', '.join(list_model_types())}")
        if model not in seen:
            seen.add(model)
            cleaned.append(model)
    if not cleaned:
        raise ValueError("At least one model type is required.")
    return cleaned


def _metric_from_run(run: dict[str, Any], partition: str, metric_name: str) -> float:
    return float(run["metrics"][partition]["overall"][metric_name])


def _target_metric_from_run(run: dict[str, Any], partition: str, target: str, metric_name: str) -> float | None:
    try:
        return float(run["metrics"][partition]["per_target"][target][metric_name])
    except Exception:
        return None


def _stats(values: Sequence[float]) -> dict[str, float | None]:
    vals = [float(v) for v in values]
    if not vals:
        return {"mean": None, "std": None, "min": None, "max": None}
    return {
        "mean": float(mean(vals)),
        "std": float(pstdev(vals)) if len(vals) > 1 else 0.0,
        "min": float(min(vals)),
        "max": float(max(vals)),
    }


def _rank_rows(rows: list[dict[str, Any]], metric: str, *, lower_is_better: bool = True, rank_key: str | None = None) -> list[dict[str, Any]]:
    rank_key = rank_key or f"rank_{metric}"
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            float("inf") if row.get(metric) is None else float(row[metric]) if lower_is_better else -float(row[metric]),
            str(row.get("model_type") or row.get("run_name") or ""),
        ),
    )
    for rank, row in enumerate(sorted_rows, start=1):
        row[rank_key] = rank
    return rows


def compare_models_across_seeds(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_types: Sequence[str],
    seeds: Sequence[int],
    split_method: str = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    allow_forced: bool = False,
    model_params_by_type: dict[str, dict[str, Any]] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Compare model families across multiple split seeds.

    This is the stability layer above one-shot comparison. It answers whether a
    model wins consistently across split randomness, not only on one lucky split.
    """
    dataset_path = Path(dataset_path).expanduser().resolve()
    models = _normalize_models(model_types)
    seed_values = _normalize_seeds(seeds)

    if output_dir is None:
        output_dir = Path("data") / "processed" / "ml_compare_seeds" / f"{dataset_path.name}__{len(seed_values)}seeds"
    output_dir = _ensure_output_dir(output_dir)
    seed_root = _ensure_output_dir(output_dir / "seeds")

    seed_rows: list[dict[str, Any]] = []
    seed_summaries: list[dict[str, Any]] = []

    for seed in seed_values:
        seed_output_dir = seed_root / f"seed_{int(seed)}"
        result = compare_models(
            dataset_path=dataset_path,
            feature_columns=feature_columns,
            target_columns=target_columns,
            model_types=models,
            split_method=split_method,
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=int(seed),
            allow_forced=allow_forced,
            model_params_by_type=model_params_by_type,
            output_dir=seed_output_dir,
        )
        summary = result["summary"]
        seed_summaries.append(
            {
                "seed": int(seed),
                "comparison_summary_json": str(result["comparison_summary_json"]),
                "comparison_summary_csv": str(result["comparison_summary_csv"]),
                "best_model_by_test_rmse_mean": summary["best_model_by_test_rmse_mean"],
                "best_model_by_test_mae_mean": summary["best_model_by_test_mae_mean"],
                "best_model_by_test_r2_mean": summary["best_model_by_test_r2_mean"],
            }
        )

        for run in summary["model_runs"]:
            row = {
                "seed": int(seed),
                "model_type": run["model_type"],
                "model_name": run["model_name"],
                "family": run["family"],
                "train_rmse_mean": _metric_from_run(run, "train", "rmse_mean"),
                "val_rmse_mean": _metric_from_run(run, "val", "rmse_mean"),
                "test_rmse_mean": _metric_from_run(run, "test", "rmse_mean"),
                "train_mae_mean": _metric_from_run(run, "train", "mae_mean"),
                "val_mae_mean": _metric_from_run(run, "val", "mae_mean"),
                "test_mae_mean": _metric_from_run(run, "test", "mae_mean"),
                "train_r2_mean": _metric_from_run(run, "train", "r2_mean"),
                "val_r2_mean": _metric_from_run(run, "val", "r2_mean"),
                "test_r2_mean": _metric_from_run(run, "test", "r2_mean"),
                "rank_test_rmse_mean": run["summary"].get("rank_test_rmse_mean"),
                "rank_test_mae_mean": run["summary"].get("rank_test_mae_mean"),
                "rank_test_r2_mean": run["summary"].get("rank_test_r2_mean"),
                "run_dir": run["artifacts"].get("run_dir"),
                "metrics_path": run["artifacts"].get("metrics_path"),
            }
            seed_rows.append(row)

    model_rows: list[dict[str, Any]] = []
    for model in models:
        rows = [row for row in seed_rows if row["model_type"] == model]
        rmse_stats = _stats([row["test_rmse_mean"] for row in rows])
        mae_stats = _stats([row["test_mae_mean"] for row in rows])
        r2_stats = _stats([row["test_r2_mean"] for row in rows])
        val_rmse_stats = _stats([row["val_rmse_mean"] for row in rows])

        model_rows.append(
            {
                "model_type": model,
                "n_seeds": len(rows),
                "test_rmse_mean": rmse_stats["mean"],
                "test_rmse_std": rmse_stats["std"],
                "test_rmse_min": rmse_stats["min"],
                "test_rmse_max": rmse_stats["max"],
                "test_mae_mean": mae_stats["mean"],
                "test_mae_std": mae_stats["std"],
                "test_r2_mean": r2_stats["mean"],
                "test_r2_std": r2_stats["std"],
                "val_rmse_mean": val_rmse_stats["mean"],
                "val_rmse_std": val_rmse_stats["std"],
                "rmse_win_count": sum(1 for item in seed_summaries if item["best_model_by_test_rmse_mean"] == model),
                "mae_win_count": sum(1 for item in seed_summaries if item["best_model_by_test_mae_mean"] == model),
                "r2_win_count": sum(1 for item in seed_summaries if item["best_model_by_test_r2_mean"] == model),
                "mean_rank_test_rmse": float(mean([float(row["rank_test_rmse_mean"]) for row in rows])) if rows else None,
                "mean_rank_test_mae": float(mean([float(row["rank_test_mae_mean"]) for row in rows])) if rows else None,
                "mean_rank_test_r2": float(mean([float(row["rank_test_r2_mean"]) for row in rows])) if rows else None,
            }
        )

    _rank_rows(model_rows, "test_rmse_mean", lower_is_better=True, rank_key="rank_mean_test_rmse")
    _rank_rows(model_rows, "test_mae_mean", lower_is_better=True, rank_key="rank_mean_test_mae")
    _rank_rows(model_rows, "test_r2_mean", lower_is_better=False, rank_key="rank_mean_test_r2")

    per_target_rows: list[dict[str, Any]] = []
    for model in models:
        for target in target_columns:
            target_rmse_vals: list[float] = []
            target_mae_vals: list[float] = []
            target_r2_vals: list[float] = []
            for seed_summary in seed_summaries:
                seed = seed_summary["seed"]
                summary_path = Path(seed_summary["comparison_summary_json"])
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                run = next(r for r in summary["model_runs"] if r["model_type"] == model)
                rmse = _target_metric_from_run(run, "test", target, "rmse")
                mae = _target_metric_from_run(run, "test", target, "mae")
                r2 = _target_metric_from_run(run, "test", target, "r2")
                if rmse is not None:
                    target_rmse_vals.append(rmse)
                if mae is not None:
                    target_mae_vals.append(mae)
                if r2 is not None:
                    target_r2_vals.append(r2)

            per_target_rows.append(
                {
                    "model_type": model,
                    "target": target,
                    "test_rmse_mean": _stats(target_rmse_vals)["mean"],
                    "test_rmse_std": _stats(target_rmse_vals)["std"],
                    "test_mae_mean": _stats(target_mae_vals)["mean"],
                    "test_mae_std": _stats(target_mae_vals)["std"],
                    "test_r2_mean": _stats(target_r2_vals)["mean"],
                    "test_r2_std": _stats(target_r2_vals)["std"],
                }
            )

    # Rank models within each target by target RMSE.
    for target in target_columns:
        subset = [row for row in per_target_rows if row["target"] == target]
        subset_sorted = sorted(subset, key=lambda row: (float("inf") if row["test_rmse_mean"] is None else float(row["test_rmse_mean"]), row["model_type"]))
        for rank, row in enumerate(subset_sorted, start=1):
            row["rank_target_test_rmse"] = rank

    winner_by_mean_rmse = min(model_rows, key=lambda row: float("inf") if row["test_rmse_mean"] is None else float(row["test_rmse_mean"]))
    winner_by_mean_mae = min(model_rows, key=lambda row: float("inf") if row["test_mae_mean"] is None else float(row["test_mae_mean"]))
    winner_by_mean_r2 = max(model_rows, key=lambda row: float("-inf") if row["test_r2_mean"] is None else float(row["test_r2_mean"]))
    winner_by_rmse_wins = max(model_rows, key=lambda row: (int(row["rmse_win_count"]), -float(row["test_rmse_mean"] or 0.0)))

    winner_report = {
        "winner_by_mean_test_rmse": winner_by_mean_rmse["model_type"],
        "winner_by_mean_test_mae": winner_by_mean_mae["model_type"],
        "winner_by_mean_test_r2": winner_by_mean_r2["model_type"],
        "winner_by_rmse_win_count": winner_by_rmse_wins["model_type"],
        "n_seeds": len(seed_values),
        "seeds": seed_values,
        "caution": (
            "A stable winner across seed splits is stronger evidence than a one-shot comparison, "
            "but it is still only as trustworthy as the dataset size, coverage, and curation quality."
        ),
    }

    summary = {
        "dataset_path": str(dataset_path),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "model_types": models,
        "seeds": seed_values,
        "split_config": {
            "split_method": split_method,
            "group_column": group_column,
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "allow_forced": allow_forced,
        },
        "seed_summaries": seed_summaries,
        "model_stability": model_rows,
        "per_target_ranking": per_target_rows,
        "winner_report": winner_report,
    }

    summary_json = output_dir / "comparison_seed_stability_summary.json"
    seed_rows_csv = output_dir / "seed_stability_rows.csv"
    model_summary_json = output_dir / "model_stability_summary.json"
    model_summary_csv = output_dir / "model_stability_summary.csv"
    per_target_csv = output_dir / "per_target_ranking.csv"
    winner_json = output_dir / "winner_report.json"

    _write_json(summary_json, summary)
    _write_csv(seed_rows_csv, seed_rows)
    _write_json(model_summary_json, {"model_stability": model_rows})
    _write_csv(model_summary_csv, model_rows)
    _write_csv(per_target_csv, per_target_rows)
    _write_json(winner_json, winner_report)

    return {
        "output_dir": output_dir,
        "summary_json": summary_json,
        "seed_rows_csv": seed_rows_csv,
        "model_stability_summary_json": model_summary_json,
        "model_stability_summary_csv": model_summary_csv,
        "per_target_ranking_csv": per_target_csv,
        "winner_report_json": winner_json,
        "summary": summary,
    }


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_tuning_dir(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"Tuning run directory not found: {resolved}")
    if not (resolved / "best_trial.json").exists():
        raise FileNotFoundError(f"Missing best_trial.json under tuning run directory: {resolved}")
    return resolved


def compare_tuning_runs(
    *,
    tuning_run_dirs: Sequence[Path],
    selection_metric: str = "val.rmse_mean",
    minimize: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Compare already-completed tuning campaigns by their best trials."""
    run_dirs = [_resolve_tuning_dir(Path(p)) for p in tuning_run_dirs]
    if not run_dirs:
        raise ValueError("At least one tuning run directory is required.")

    if output_dir is None:
        output_dir = Path("data") / "processed" / "ml_compare_tuning_runs"
    output_dir = _ensure_output_dir(output_dir)

    rows: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        best = _load_json_if_exists(run_dir / "best_trial.json")
        tuning_summary = _load_json_if_exists(run_dir / "tuning_summary.json")
        model_type = best.get("model_type") or tuning_summary.get("model_type") or "unknown"
        score = best.get("selection_score")
        if score is None:
            best_trial = tuning_summary.get("best_trial") or {}
            score = best_trial.get("selection_score")

        rows.append(
            {
                "run_name": run_dir.name,
                "run_dir": str(run_dir),
                "model_type": model_type,
                "backend": tuning_summary.get("backend", tuning_summary.get("strategy", "unknown")),
                "strategy": tuning_summary.get("strategy", "unknown"),
                "study_name": tuning_summary.get("study_name"),
                "n_trials": tuning_summary.get("n_trials"),
                "n_successful_trials": tuning_summary.get("n_successful_trials"),
                "n_failed_trials": tuning_summary.get("n_failed_trials"),
                "selection_metric": best.get("selection_metric", tuning_summary.get("selection_metric", selection_metric)),
                "selection_score": None if score is None else float(score),
                "best_trial_id": best.get("trial_id") or (tuning_summary.get("best_trial") or {}).get("trial_id"),
                "best_params_json": json.dumps(best.get("model_params") or best.get("best_params") or {}, sort_keys=True, default=str),
                "best_trial_json": str(run_dir / "best_trial.json"),
                "tuning_summary_json": str(run_dir / "tuning_summary.json") if (run_dir / "tuning_summary.json").exists() else None,
            }
        )

    ranked = sorted(
        rows,
        key=lambda row: (
            float("inf") if row["selection_score"] is None else float(row["selection_score"]) if minimize else -float(row["selection_score"]),
            row["run_name"],
        ),
    )
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank

    winner = ranked[0]
    winner_report = {
        "winner_run_name": winner["run_name"],
        "winner_run_dir": winner["run_dir"],
        "winner_model_type": winner["model_type"],
        "winner_score": winner["selection_score"],
        "winner_best_trial_id": winner["best_trial_id"],
        "winner_best_params_json": winner["best_params_json"],
        "selection_metric": selection_metric,
        "minimize": minimize,
        "n_compared_runs": len(rows),
    }
    summary = {
        "selection_metric": selection_metric,
        "minimize": minimize,
        "n_compared_runs": len(rows),
        "rows": rows,
        "winner_report": winner_report,
    }

    summary_json = output_dir / "tuning_run_comparison.json"
    summary_csv = output_dir / "tuning_run_comparison.csv"
    winner_json = output_dir / "winner_report.json"
    _write_json(summary_json, summary)
    _write_csv(summary_csv, rows)
    _write_json(winner_json, winner_report)

    return {
        "output_dir": output_dir,
        "summary_json": summary_json,
        "summary_csv": summary_csv,
        "winner_report_json": winner_json,
        "summary": summary,
    }
