"""
CLI commands for AERIS machine-learning workflows.

Responsibilities:
    - Train baseline surrogate models from promoted aero datasets
    - Compare model families using identical train/validation/test splits
    - Run prediction using saved ML artifacts

Notes:
    - This module must remain a thin CLI/reporting layer.
    - Dataset loading, promotion checks, splitting, training, comparison, and
      prediction belong in aeris.dataset.* and aeris.ml.*.
    - ML inputs should come from promoted aero datasets, not raw solver output.
    - Do not put model-training logic directly in this command file.
"""

from __future__ import annotations

from pathlib import Path

import typer

from aeris.commands._helpers import fail_command, parse_csv_list
from aeris.ml.compare import compare_models
from aeris.ml.config import load_model_params_by_type_json, load_model_params_json
from aeris.ml.tune import load_tuning_param_space_json, tune_model, tune_model_from_config
from aeris.ml.model_registry import list_model_types
from aeris.ml.predict import predict_with_trained_model
from aeris.ml.train import train_baseline_model, train_baseline_model_from_config


_ALLOW_FORCED_HELP = (
    "Allow use of a force-promoted dataset. "
    "Use only when a dataset was explicitly promoted despite known blockers "
    "or rejected geometries. Normal ML/downstream workflows should prefer "
    "strictly promoted datasets."
)


ml_app = typer.Typer(
    help=(
        "Machine-learning training, comparison, and inference commands "
        "for promoted AERIS datasets."
    )
)


@ml_app.callback()
def ml_callback() -> None:
    """ML command group."""
    pass


def _echo_train_result(result: dict, *, model_type_label: str | None = None) -> None:
    artifacts = result["artifacts"]
    metrics = result["metrics"]
    split = result["split"]
    model_type = model_type_label or metrics["model"]["model_type"]

    typer.echo("[AERIS] ML training completed")
    typer.echo(f"  model_type: {model_type}")
    typer.echo(f"  split_method: {split.method}")
    typer.echo(f"  train_rows: {len(split.train_df)}")
    typer.echo(f"  val_rows: {len(split.val_df)}")
    typer.echo(f"  test_rows: {len(split.test_df)}")
    typer.echo(f"  output_dir: {artifacts.run_dir}")
    typer.echo(f"  metrics_json: {artifacts.metrics_path}")
    typer.echo(f"  model_dir: {artifacts.models_dir}")
    typer.echo(f"  train_rows_csv: {artifacts.train_rows_path}")
    typer.echo(f"  val_rows_csv: {artifacts.val_rows_path}")
    typer.echo(f"  test_rows_csv: {artifacts.test_rows_path}")
    if getattr(artifacts, "ml_run_manifest_path", None) is not None:
        typer.echo(f"  ml_run_manifest_json: {artifacts.ml_run_manifest_path}")
    if getattr(artifacts, "diagnostics_dir", None) is not None:
        typer.echo(f"  diagnostics_dir: {artifacts.diagnostics_dir}")

    if artifacts.coefficients_path is not None:
        typer.echo(f"  coefficients_json: {artifacts.coefficients_path}")
    if artifacts.feature_importances_path is not None:
        typer.echo(f"  feature_importances_json: {artifacts.feature_importances_path}")

    typer.echo(f"  test_r2_mean: {metrics['test']['overall']['r2_mean']:.6f}")
    typer.echo(f"  test_rmse_mean: {metrics['test']['overall']['rmse_mean']:.6f}")


@ml_app.command("train")
def ml_train(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Optional YAML ML experiment config. If provided, dataset/features/targets come from config.",
    ),
    dataset: Path | None = typer.Option(
        None,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a promoted aero dataset root. Required unless --config is used.",
    ),
    features: str | None = typer.Option(None, "--features", help="Comma-separated feature columns. Required unless --config is used."),
    targets: str | None = typer.Option(None, "--targets", help="Comma-separated target columns. Required unless --config is used."),
    model_type: str = typer.Option(
        "linear_regression",
        "--model-type",
        help=f"Model type. Supported: {', '.join(list_model_types())}",
    ),
    split_method: str = typer.Option("grouped", "--split-method", help="Split method: grouped or random."),
    group_column: str = typer.Option("geometry_id", "--group-column", help="Grouping column for grouped split."),
    train_fraction: float = typer.Option(0.7, "--train-fraction"),
    val_fraction: float = typer.Option(0.15, "--val-fraction"),
    test_fraction: float = typer.Option(0.15, "--test-fraction"),
    random_seed: int = typer.Option(123, "--random-seed"),
    allow_forced: bool = typer.Option(False, "--allow-forced", help=_ALLOW_FORCED_HELP),
    model_params_json: Path | None = typer.Option(
        None,
        "--model-params-json",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Optional JSON object containing model constructor parameters.",
    ),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Optional output directory."),
) -> None:
    """Train a baseline surrogate model from a promoted aero dataset."""
    try:
        model_params_override = (
            load_model_params_json(model_params_json)
            if model_params_json is not None
            else None
        )

        if config is not None:
            result = train_baseline_model_from_config(
                config_path=config,
                output_dir=output_dir,
                model_params_override=model_params_override,
            )
            _echo_train_result(result)
            return

        if dataset is None:
            raise typer.BadParameter("--dataset is required when --config is not used.")
        if features is None:
            raise typer.BadParameter("--features is required when --config is not used.")
        if targets is None:
            raise typer.BadParameter("--targets is required when --config is not used.")

        feature_cols = parse_csv_list(features, "--features")
        target_cols = parse_csv_list(targets, "--targets")

        result = train_baseline_model(
            dataset_path=dataset,
            feature_columns=feature_cols,
            target_columns=target_cols,
            model_type=model_type,
            split_method=split_method,
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=random_seed,
            allow_forced=allow_forced,
            model_params=model_params_override,
            output_dir=output_dir,
        )
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("ML train", exc)

    _echo_train_result(result, model_type_label=model_type)


@ml_app.command("compare")
def ml_compare(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a promoted aero dataset root.",
    ),
    features: str = typer.Option(..., "--features", help="Comma-separated feature columns."),
    targets: str = typer.Option(..., "--targets", help="Comma-separated target columns."),
    models: str = typer.Option(
        ...,
        "--models",
        help=f"Comma-separated model types. Supported: {', '.join(list_model_types())}",
    ),
    split_method: str = typer.Option("grouped", "--split-method", help="Split method: grouped or random."),
    group_column: str = typer.Option("geometry_id", "--group-column", help="Grouping column for grouped split."),
    train_fraction: float = typer.Option(0.7, "--train-fraction"),
    val_fraction: float = typer.Option(0.15, "--val-fraction"),
    test_fraction: float = typer.Option(0.15, "--test-fraction"),
    random_seed: int = typer.Option(123, "--random-seed"),
    allow_forced: bool = typer.Option(False, "--allow-forced", help=_ALLOW_FORCED_HELP),
    model_params_json: Path | None = typer.Option(
        None,
        "--model-params-json",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Optional JSON mapping of model_type -> constructor parameters.",
    ),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Optional output directory for comparison artifacts."),
) -> None:
    """Compare several model families on a single fixed train/val/test split."""
    feature_cols = parse_csv_list(features, "--features")
    target_cols = parse_csv_list(targets, "--targets")
    model_types = parse_csv_list(models, "--models")

    try:
        result = compare_models(
            dataset_path=dataset,
            feature_columns=feature_cols,
            target_columns=target_cols,
            model_types=model_types,
            split_method=split_method,
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=random_seed,
            allow_forced=allow_forced,
            model_params_by_type=(
                load_model_params_by_type_json(model_params_json)
                if model_params_json is not None
                else None
            ),
            output_dir=output_dir,
        )
    except Exception as exc:
        fail_command("ML compare", exc)

    summary = result["summary"]

    typer.echo("[AERIS] ML model comparison completed")
    typer.echo(f"  dataset: {summary['dataset_path']}")
    typer.echo(f"  models: {', '.join(summary['model_types'])}")
    typer.echo(f"  split_method: {summary['split_config']['split_method']}")
    typer.echo(f"  random_seed: {summary['split_config']['random_seed']}")
    typer.echo(f"  output_dir: {result['output_dir']}")
    typer.echo(f"  comparison_summary_json: {result['comparison_summary_json']}")
    typer.echo(f"  comparison_summary_csv: {result['comparison_summary_csv']}")
    typer.echo(f"  best_by_rmse: {summary['best_model_by_test_rmse_mean']}")
    typer.echo(f"  best_by_mae: {summary['best_model_by_test_mae_mean']}")
    typer.echo(f"  best_by_r2: {summary['best_model_by_test_r2_mean']}")

    typer.echo("")
    typer.echo("Model summary:")
    for run in summary["model_runs"]:
        typer.echo(
            f"  - {run['model_type']}: "
            f"rank_rmse={run['summary']['rank_test_rmse_mean']}, "
            f"rank_mae={run['summary']['rank_test_mae_mean']}, "
            f"rank_r2={run['summary']['rank_test_r2_mean']}, "
            f"test_r2_mean={run['metrics']['test']['overall']['r2_mean']:.6f}, "
            f"test_rmse_mean={run['metrics']['test']['overall']['rmse_mean']:.6f}"
        )


@ml_app.command("tune")
def ml_tune(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Optional YAML ML experiment config. If provided, dataset/features/targets/model/split come from config.",
    ),
    dataset: Path | None = typer.Option(
        None,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a promoted aero dataset root. Required unless --config is used.",
    ),
    features: str | None = typer.Option(None, "--features", help="Comma-separated feature columns. Required unless --config is used."),
    targets: str | None = typer.Option(None, "--targets", help="Comma-separated target columns. Required unless --config is used."),
    model_type: str = typer.Option(
        "random_forest",
        "--model-type",
        help=f"Model type. Supported: {', '.join(list_model_types())}",
    ),
    param_space_json: Path = typer.Option(
        ...,
        "--param-space-json",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="JSON parameter space for tuning.",
    ),
    strategy: str = typer.Option("grid", "--strategy", help="Tuning strategy: grid or random."),
    max_trials: int | None = typer.Option(None, "--max-trials", help="Maximum trials. Required for random strategy."),
    tuning_random_seed: int = typer.Option(123, "--tuning-random-seed", help="Seed for random search trial generation."),
    split_method: str = typer.Option("grouped", "--split-method", help="Split method: grouped or random."),
    group_column: str = typer.Option("geometry_id", "--group-column", help="Grouping column for grouped split."),
    train_fraction: float = typer.Option(0.7, "--train-fraction"),
    val_fraction: float = typer.Option(0.15, "--val-fraction"),
    test_fraction: float = typer.Option(0.15, "--test-fraction"),
    random_seed: int = typer.Option(123, "--random-seed"),
    allow_forced: bool = typer.Option(False, "--allow-forced", help=_ALLOW_FORCED_HELP),
    selection_metric: str = typer.Option("val.rmse_mean", "--selection-metric", help="Metric used to pick best trial, e.g. val.rmse_mean or val.r2_mean."),
    minimize: bool = typer.Option(True, "--minimize/--maximize", help="Whether lower selection metric is better."),
    fail_policy: str = typer.Option("continue", "--fail-policy", help="Trial failure policy: continue or raise."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Optional output directory for tuning artifacts."),
) -> None:
    """Tune one model family over a deterministic parameter search space."""
    try:
        loaded_space = load_tuning_param_space_json(param_space_json)
        param_space = loaded_space["params"]
        search = loaded_space.get("search", {}) or {}
        strategy_eff = str(search.get("strategy") or strategy)
        max_trials_eff = search.get("max_trials", max_trials)
        tuning_seed_eff = int(search.get("random_seed", tuning_random_seed))

        if config is not None:
            result = tune_model_from_config(
                config_path=config,
                param_space=param_space,
                strategy=strategy_eff,
                max_trials=None if max_trials_eff is None else int(max_trials_eff),
                tuning_random_seed=tuning_seed_eff,
                selection_metric=selection_metric,
                minimize=minimize,
                fail_policy=fail_policy,  # type: ignore[arg-type]
                source_param_space_path=param_space_json,
                output_dir=output_dir,
            )
        else:
            if dataset is None:
                raise typer.BadParameter("--dataset is required when --config is not used.")
            if features is None:
                raise typer.BadParameter("--features is required when --config is not used.")
            if targets is None:
                raise typer.BadParameter("--targets is required when --config is not used.")

            result = tune_model(
                dataset_path=dataset,
                feature_columns=parse_csv_list(features, "--features"),
                target_columns=parse_csv_list(targets, "--targets"),
                model_type=model_type,
                param_space=param_space,
                strategy=strategy_eff,  # type: ignore[arg-type]
                max_trials=None if max_trials_eff is None else int(max_trials_eff),
                tuning_random_seed=tuning_seed_eff,
                split_method=split_method,
                group_column=group_column,
                train_fraction=train_fraction,
                val_fraction=val_fraction,
                test_fraction=test_fraction,
                random_seed=random_seed,
                allow_forced=allow_forced,
                selection_metric=selection_metric,
                minimize=minimize,
                fail_policy=fail_policy,  # type: ignore[arg-type]
                source_param_space_path=param_space_json,
                output_dir=output_dir,
            )
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("ML tune", exc)

    summary = result["summary"]
    best = summary.get("best_trial") or {}
    best_params = best.get("model_params", {})

    typer.echo("[AERIS] ML tuning completed")
    typer.echo(f"  dataset: {summary['dataset_path']}")
    typer.echo(f"  model_type: {summary['model_type']}")
    typer.echo(f"  strategy: {summary['search']['strategy']}")
    typer.echo(f"  n_trials: {summary['n_trials']}")
    typer.echo(f"  n_successful_trials: {summary['n_successful_trials']}")
    typer.echo(f"  n_failed_trials: {summary['n_failed_trials']}")
    typer.echo(f"  selection_metric: {summary['search']['selection_metric']}")
    typer.echo(f"  output_dir: {result['output_dir']}")
    typer.echo(f"  tuning_summary_json: {result['tuning_summary_json']}")
    typer.echo(f"  tuning_trials_csv: {result['tuning_trials_csv']}")
    if best:
        typer.echo(f"  best_trial: {best['trial_id']}")
        typer.echo(f"  best_score: {best['selection_score']}")
        typer.echo(f"  best_params: {best_params}")


@ml_app.command("predict")
def ml_predict(
    model_run_dir: Path = typer.Option(
        ...,
        "--model-run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a saved ML training run directory.",
    ),
    input_csv: Path = typer.Option(
        ...,
        "--input-csv",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="CSV file containing required feature columns.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional output directory for prediction artifacts.",
    ),
    include_truth_if_available: bool = typer.Option(
        True,
        "--include-truth-if-available/--no-include-truth-if-available",
        help="If target columns already exist in the input CSV, also compute prediction error metrics.",
    ),
) -> None:
    """Run inference using a saved trained model against an input CSV."""
    try:
        result = predict_with_trained_model(
            model_run_dir=model_run_dir,
            input_csv=input_csv,
            output_dir=output_dir,
            include_truth_if_available=include_truth_if_available,
        )
    except Exception as exc:
        fail_command("ML predict", exc)

    summary = result["summary"]
    artifacts = result["artifacts"]

    typer.echo("[AERIS] ML prediction completed")
    typer.echo(f"  model_type: {summary['model_type']}")
    typer.echo(f"  n_rows: {summary['n_rows']}")
    typer.echo(f"  input_csv: {artifacts.input_csv_path}")
    typer.echo(f"  output_dir: {artifacts.run_dir}")
    typer.echo(f"  predictions_csv: {artifacts.predictions_csv_path}")
    typer.echo(f"  prediction_summary_json: {artifacts.prediction_summary_path}")
    typer.echo(f"  truth_available: {summary['truth_available']}")

    if summary["evaluation"] is not None:
        typer.echo(f"  rmse_mean: {summary['evaluation']['overall']['rmse_mean']:.6f}")
        typer.echo(f"  mae_mean: {summary['evaluation']['overall']['mae_mean']:.6f}")
        typer.echo(f"  r2_mean: {summary['evaluation']['overall']['r2_mean']:.6f}")
