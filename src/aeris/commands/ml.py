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
from aeris.ml.compare_hardening import compare_models_across_seeds, compare_tuning_runs
from aeris.ml.config import load_model_params_by_type_json, load_model_params_json
from aeris.ml.feature_presets import (
    FeaturePresetError,
    list_feature_presets,
    resolve_feature_columns,
)
from aeris.ml.validation import validate_promoted_dataset_schema
from aeris.ml.tune import load_tuning_param_space_json, tune_model, tune_model_from_config
from aeris.ml.optuna_tune import (
    load_optuna_param_space_json,
    tune_model_optuna,
    tune_model_optuna_from_config,
)
from aeris.ml.model_promotion import (
    inspect_model_run,
    promote_model_run,
    require_promoted_model as require_promoted_model_gate,
)
from aeris.ml.model_registry import list_model_types
from aeris.ml.inference_guard import check_inference_inputs
from aeris.ml.multifidelity import build_delta_dataset
from aeris.ml.multifidelity.delta_model import predict_with_delta_model, train_delta_model
from aeris.ml.predict import predict_with_trained_model
from aeris.ml.train import train_baseline_model, train_baseline_model_from_config


_ALLOW_FORCED_HELP = (
    "Allow use of a force-promoted dataset. "
    "Use only when a dataset was explicitly promoted despite known blockers "
    "or rejected geometries. Normal ML/downstream workflows should prefer "
    "strictly promoted datasets."
)


def _resolve_feature_columns_cli(
    *,
    features: str | None,
    feature_preset: str | None,
) -> list[str]:
    explicit = parse_csv_list(features, "--features") if features else None
    try:
        return resolve_feature_columns(
            explicit_features=explicit,
            preset_name=feature_preset,
        )
    except FeaturePresetError as exc:
        raise typer.BadParameter(str(exc)) from exc


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



@ml_app.command("feature-presets")
def ml_feature_presets() -> None:
    """List named ML feature presets."""
    typer.echo("[AERIS] ML feature presets")
    for preset in list_feature_presets(include_inactive=True):
        typer.echo(f"  - {preset.name} [{preset.status}] ({preset.domain})")
        typer.echo(f"    columns: {', '.join(preset.columns)}")
        typer.echo(f"    description: {preset.description}")


@ml_app.command("validate-schema")
def ml_validate_schema(
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
    features: str | None = typer.Option(None, "--features", help="Comma-separated feature columns."),
    feature_preset: str | None = typer.Option(None, "--feature-preset", help="Named feature preset, e.g. bwb_control."),
    targets: str = typer.Option(..., "--targets", help="Comma-separated target columns."),
    group_column: str = typer.Option("geometry_id", "--group-column", help="Grouping column for grouped split validation."),
    allow_forced: bool = typer.Option(False, "--allow-forced", help=_ALLOW_FORCED_HELP),
) -> None:
    """Validate a promoted dataset against ML feature/target schema expectations."""
    try:
        feature_cols = _resolve_feature_columns_cli(features=features, feature_preset=feature_preset)
        target_cols = parse_csv_list(targets, "--targets")
        result = validate_promoted_dataset_schema(
            dataset_path=dataset,
            feature_columns=feature_cols,
            target_columns=target_cols,
            group_column=group_column,
            allow_forced=allow_forced,
        )
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("ML validate-schema", exc)

    typer.echo("[AERIS] ML schema validation")
    typer.echo(f"  dataset: {result.metadata.get('dataset_path')}")
    typer.echo(f"  curated_csv: {result.metadata.get('curated_csv_path')}")
    typer.echo(f"  passed: {result.passed}")
    typer.echo(f"  rows: {result.metadata.get('n_rows')}")
    typer.echo(f"  features: {', '.join(result.metadata.get('feature_columns', []))}")
    typer.echo(f"  targets: {', '.join(result.metadata.get('target_columns', []))}")
    typer.echo(f"  group_column: {result.metadata.get('group_column')}")
    typer.echo(f"  groups: {result.metadata.get('n_groups')}")
    typer.echo(f"  errors: {len(result.errors)}")
    typer.echo(f"  warnings: {len(result.warnings)}")
    for issue in result.errors:
        typer.echo(f"  ERROR [{issue.code}]: {issue.message}")
    for issue in result.warnings:
        typer.echo(f"  WARNING [{issue.code}]: {issue.message}")
    if not result.passed:
        raise typer.Exit(code=1)


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
    features: str | None = typer.Option(None, "--features", help="Comma-separated feature columns. Required unless --config or --feature-preset is used."),
    feature_preset: str | None = typer.Option(None, "--feature-preset", help="Named feature preset, e.g. bwb_control. Cannot be combined with --features."),
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
        if features is None and feature_preset is None:
            raise typer.BadParameter("--features or --feature-preset is required when --config is not used.")
        if targets is None:
            raise typer.BadParameter("--targets is required when --config is not used.")

        feature_cols = _resolve_feature_columns_cli(features=features, feature_preset=feature_preset)
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
    features: str | None = typer.Option(None, "--features", help="Comma-separated feature columns."),
    feature_preset: str | None = typer.Option(None, "--feature-preset", help="Named feature preset, e.g. bwb_control. Cannot be combined with --features."),
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
    feature_cols = _resolve_feature_columns_cli(features=features, feature_preset=feature_preset)
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
    backend: str = typer.Option(
        "aeris",
        "--backend",
        help="Tuning backend: aeris or optuna. Keep aeris for deterministic grid/random; use optuna for advanced studies.",
    ),
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
    features: str | None = typer.Option(None, "--features", help="Comma-separated feature columns. Required unless --config or --feature-preset is used."),
    feature_preset: str | None = typer.Option(None, "--feature-preset", help="Named feature preset, e.g. bwb_control. Cannot be combined with --features."),
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
    strategy: str = typer.Option("grid", "--strategy", help="AERIS backend strategy: grid or random."),
    max_trials: int | None = typer.Option(None, "--max-trials", help="Maximum AERIS backend trials; also used as Optuna n_trials if --n-trials is omitted."),
    n_trials: int | None = typer.Option(None, "--n-trials", help="Number of Optuna trials. Defaults to search.n_trials, --max-trials, or 20."),
    tuning_random_seed: int = typer.Option(123, "--tuning-random-seed", help="Seed for random search / Optuna sampler."),
    optuna_sampler: str = typer.Option("tpe", "--optuna-sampler", help="Optuna sampler: tpe or random."),
    study_name: str | None = typer.Option(None, "--study-name", help="Optional Optuna study name."),
    storage: str | None = typer.Option(None, "--storage", help="Optional Optuna storage URL, e.g. sqlite:///data/processed/ml_runs/optuna.db."),
    load_if_exists: bool = typer.Option(True, "--load-if-exists/--no-load-if-exists", help="For Optuna: resume an existing study with the same name/storage."),
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
    """Tune one model family over a parameter search space."""
    try:
        loaded_space = load_tuning_param_space_json(param_space_json)
        param_space = loaded_space["params"]
        search = loaded_space.get("search", {}) or {}

        backend_eff = str(search.get("backend") or backend).strip().lower()

        # Important: the default AERIS loader normalizes every parameter into a
        # list for grid/random tuning. Optuna needs raw distribution specs
        # preserved, e.g. {"type": "float", "low": ..., "high": ...}.
        if backend_eff == "optuna":
            optuna_loaded_space = load_optuna_param_space_json(param_space_json)
            param_space = optuna_loaded_space["params"]
            search = optuna_loaded_space.get("search", {}) or {}
            backend_eff = str(search.get("backend") or backend).strip().lower()

        strategy_eff = str(search.get("strategy") or strategy)
        max_trials_eff = search.get("max_trials", max_trials)
        tuning_seed_eff = int(search.get("random_seed", tuning_random_seed))
        selection_metric_eff = str(search.get("selection_metric") or selection_metric)
        minimize_eff = bool(search.get("minimize", minimize))

        if backend_eff == "optuna":
            n_trials_eff = search.get("n_trials", n_trials if n_trials is not None else max_trials_eff)
            if n_trials_eff is None:
                n_trials_eff = 20
            sampler_eff = str(search.get("sampler") or search.get("optuna_sampler") or optuna_sampler)
            study_name_eff = search.get("study_name", study_name)
            storage_eff = search.get("storage", storage)

            if config is not None:
                result = tune_model_optuna_from_config(
                    config_path=config,
                    param_space=param_space,
                    n_trials=int(n_trials_eff),
                    sampler_name=sampler_eff,  # type: ignore[arg-type]
                    tuning_random_seed=tuning_seed_eff,
                    study_name=None if study_name_eff is None else str(study_name_eff),
                    storage=None if storage_eff is None else str(storage_eff),
                    load_if_exists=load_if_exists,
                    selection_metric=selection_metric_eff,
                    minimize=minimize_eff,
                    fail_policy=fail_policy,  # type: ignore[arg-type]
                    source_param_space_path=param_space_json,
                    output_dir=output_dir,
                )
            else:
                if dataset is None:
                    raise typer.BadParameter("--dataset is required when --config is not used.")
                if features is None and feature_preset is None:
                    raise typer.BadParameter("--features or --feature-preset is required when --config is not used.")
                if targets is None:
                    raise typer.BadParameter("--targets is required when --config is not used.")

                result = tune_model_optuna(
                    dataset_path=dataset,
                    feature_columns=_resolve_feature_columns_cli(features=features, feature_preset=feature_preset),
                    target_columns=parse_csv_list(targets, "--targets"),
                    model_type=model_type,
                    param_space=param_space,
                    n_trials=int(n_trials_eff),
                    sampler_name=sampler_eff,  # type: ignore[arg-type]
                    tuning_random_seed=tuning_seed_eff,
                    study_name=None if study_name_eff is None else str(study_name_eff),
                    storage=None if storage_eff is None else str(storage_eff),
                    load_if_exists=load_if_exists,
                    split_method=split_method,
                    group_column=group_column,
                    train_fraction=train_fraction,
                    val_fraction=val_fraction,
                    test_fraction=test_fraction,
                    random_seed=random_seed,
                    allow_forced=allow_forced,
                    selection_metric=selection_metric_eff,
                    minimize=minimize_eff,
                    fail_policy=fail_policy,  # type: ignore[arg-type]
                    source_param_space_path=param_space_json,
                    output_dir=output_dir,
                )
        elif backend_eff == "aeris":
            if config is not None:
                result = tune_model_from_config(
                    config_path=config,
                    param_space=param_space,
                    strategy=strategy_eff,  # type: ignore[arg-type]
                    max_trials=None if max_trials_eff is None else int(max_trials_eff),
                    tuning_random_seed=tuning_seed_eff,
                    selection_metric=selection_metric_eff,
                    minimize=minimize_eff,
                    fail_policy=fail_policy,  # type: ignore[arg-type]
                    source_param_space_path=param_space_json,
                    output_dir=output_dir,
                )
            else:
                if dataset is None:
                    raise typer.BadParameter("--dataset is required when --config is not used.")
                if features is None and feature_preset is None:
                    raise typer.BadParameter("--features or --feature-preset is required when --config is not used.")
                if targets is None:
                    raise typer.BadParameter("--targets is required when --config is not used.")

                result = tune_model(
                    dataset_path=dataset,
                    feature_columns=_resolve_feature_columns_cli(features=features, feature_preset=feature_preset),
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
                    selection_metric=selection_metric_eff,
                    minimize=minimize_eff,
                    fail_policy=fail_policy,  # type: ignore[arg-type]
                    source_param_space_path=param_space_json,
                    output_dir=output_dir,
                )
        else:
            raise typer.BadParameter("--backend must be 'aeris' or 'optuna'.")
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("ML tune", exc)

    summary = result["summary"]
    best = summary.get("best_trial") or {}
    best_params = best.get("model_params", {})

    typer.echo("[AERIS] ML tuning completed")
    typer.echo(f"  backend: {summary.get('backend', 'aeris')}")
    typer.echo(f"  dataset: {summary['dataset_path']}")
    typer.echo(f"  model_type: {summary['model_type']}")
    typer.echo(f"  strategy: {summary['search']['strategy']}")
    if summary.get("study"):
        typer.echo(f"  study_name: {summary['study'].get('study_name')}")
        typer.echo(f"  sampler: {summary['study'].get('sampler')}")
        typer.echo(f"  storage: {summary['study'].get('storage')}")
    typer.echo(f"  n_trials: {summary['n_trials']}")
    typer.echo(f"  n_successful_trials: {summary['n_successful_trials']}")
    typer.echo(f"  n_failed_trials: {summary['n_failed_trials']}")
    if 'n_pruned_trials' in summary:
        typer.echo(f"  n_pruned_trials: {summary['n_pruned_trials']}")
    typer.echo(f"  selection_metric: {summary['search']['selection_metric']}")
    typer.echo(f"  output_dir: {result['output_dir']}")
    typer.echo(f"  tuning_summary_json: {result['tuning_summary_json']}")
    typer.echo(f"  tuning_trials_csv: {result['tuning_trials_csv']}")
    if best:
        typer.echo(f"  best_trial: {best['trial_id']}")
        typer.echo(f"  best_score: {best['selection_score']}")
        typer.echo(f"  best_params: {best_params}")




@ml_app.command("build-delta-dataset")
def ml_build_delta_dataset(
    lf_csv: Path = typer.Option(..., "--lf-csv", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, help="Low-fidelity CSV, e.g. AVL/XFOIL scalar results."),
    hf_csv: Path = typer.Option(..., "--hf-csv", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, help="High-fidelity CSV, e.g. CFD scalar results."),
    pair_keys: str = typer.Option(..., "--pair-keys", help="Comma-separated pairing keys, e.g. geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg."),
    targets: str = typer.Option(..., "--targets", help="Comma-separated scalar targets to delta, e.g. cl,cd,cm."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Output directory for delta_dataset.csv and delta_dataset_report.json."),
) -> None:
    """Build a paired multifidelity delta dataset from LF/HF scalar CSV files."""
    try:
        result = build_delta_dataset(
            lf_csv=lf_csv,
            hf_csv=hf_csv,
            pair_keys=parse_csv_list(pair_keys, "--pair-keys"),
            targets=parse_csv_list(targets, "--targets"),
            output_dir=output_dir,
        )
    except Exception as exc:
        fail_command("ML build-delta-dataset", exc)

    typer.echo("[AERIS] ML multifidelity delta dataset built")
    typer.echo(f"  lf_csv: {lf_csv}")
    typer.echo(f"  hf_csv: {hf_csv}")
    typer.echo(f"  output_dir: {result.output_dir}")
    typer.echo(f"  delta_dataset_csv: {result.delta_dataset_csv}")
    typer.echo(f"  report_json: {result.report_json}")
    typer.echo(f"  pair_keys: {', '.join(result.pair_keys)}")
    typer.echo(f"  targets: {', '.join(result.targets)}")
    typer.echo(f"  lf_rows: {result.n_lf_rows}")
    typer.echo(f"  hf_rows: {result.n_hf_rows}")
    typer.echo(f"  paired_rows: {result.n_paired_rows}")
    typer.echo(f"  unmatched_lf_rows: {result.n_unmatched_lf_rows}")
    typer.echo(f"  unmatched_hf_rows: {result.n_unmatched_hf_rows}")


@ml_app.command("train-delta-model")
def ml_train_delta_model(
    delta_dataset: Path = typer.Option(..., "--delta-dataset", exists=True, readable=True, resolve_path=True, help="Path to delta_dataset.csv or a directory containing it."),
    features: str = typer.Option(..., "--features", help="Comma-separated feature columns. Usually includes design/condition columns and LF outputs."),
    base_targets: str = typer.Option(..., "--base-targets", help="Comma-separated base targets, e.g. cl,cd,cm. Delta targets are inferred as delta__<target>."),
    model_type: str = typer.Option("extra_trees", "--model-type", help=f"Model type. Supported: {', '.join(list_model_types())}"),
    split_method: str = typer.Option("grouped", "--split-method", help="Split method: grouped or random."),
    group_column: str = typer.Option("geometry_id", "--group-column", help="Grouping column for grouped split."),
    train_fraction: float = typer.Option(0.7, "--train-fraction"),
    val_fraction: float = typer.Option(0.15, "--val-fraction"),
    test_fraction: float = typer.Option(0.15, "--test-fraction"),
    random_seed: int = typer.Option(123, "--random-seed"),
    model_params_json: Path | None = typer.Option(None, "--model-params-json", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, help="Optional JSON object containing model constructor parameters."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Output directory for the trained delta model run."),
) -> None:
    """Train a multifidelity delta model from delta_dataset.csv."""
    try:
        result = train_delta_model(
            delta_dataset=delta_dataset,
            feature_columns=parse_csv_list(features, "--features"),
            base_targets=parse_csv_list(base_targets, "--base-targets"),
            model_type=model_type,
            split_method=split_method,  # type: ignore[arg-type]
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=random_seed,
            model_params=(load_model_params_json(model_params_json) if model_params_json is not None else None),
            output_dir=output_dir,
        )
    except Exception as exc:
        fail_command("ML train-delta-model", exc)

    artifacts = result["artifacts"]
    metrics = result["metrics"]
    split = result["split"]
    typer.echo("[AERIS] ML multifidelity delta model trained")
    typer.echo(f"  model_type: {metrics['model']['model_type']}")
    typer.echo(f"  split_method: {split.method}")
    typer.echo(f"  train_rows: {len(split.train_df)}")
    typer.echo(f"  val_rows: {len(split.val_df)}")
    typer.echo(f"  test_rows: {len(split.test_df)}")
    typer.echo(f"  output_dir: {artifacts.run_dir}")
    typer.echo(f"  model_path: {artifacts.model_path}")
    typer.echo(f"  metrics_json: {artifacts.metrics_path}")
    typer.echo(f"  delta_model_manifest_json: {artifacts.manifest_path}")
    typer.echo(f"  test_delta_rmse_mean: {metrics['test']['delta']['overall']['rmse_mean']:.6f}")
    typer.echo(f"  test_corrected_rmse_mean: {metrics['test']['corrected']['overall']['rmse_mean']:.6f}")


@ml_app.command("predict-delta-model")
def ml_predict_delta_model(
    model_run_dir: Path = typer.Option(..., "--model-run-dir", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True, help="Path to a trained delta model run directory."),
    input_csv: Path = typer.Option(..., "--input-csv", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, help="CSV containing required features and LF target columns."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Output directory for delta predictions."),
    include_truth_if_available: bool = typer.Option(True, "--include-truth-if-available/--no-include-truth-if-available", help="If HF target columns are present, compute corrected-output metrics."),
) -> None:
    """Predict deltas and corrected HF-like scalar outputs using a trained delta model."""
    try:
        result = predict_with_delta_model(
            model_run_dir=model_run_dir,
            input_csv=input_csv,
            output_dir=output_dir,
            include_truth_if_available=include_truth_if_available,
        )
    except Exception as exc:
        fail_command("ML predict-delta-model", exc)

    summary = result["summary"]
    artifacts = result["artifacts"]
    typer.echo("[AERIS] ML multifidelity delta prediction completed")
    typer.echo(f"  model_run_dir: {summary['model_run_dir']}")
    typer.echo(f"  n_rows: {summary['n_rows']}")
    typer.echo(f"  input_csv: {summary['input_csv']}")
    typer.echo(f"  output_dir: {artifacts.output_dir}")
    typer.echo(f"  predictions_csv: {artifacts.predictions_csv}")
    typer.echo(f"  prediction_summary_json: {artifacts.prediction_summary_json}")
    typer.echo(f"  truth_available: {summary['truth_available']}")
    if summary["evaluation"] is not None:
        typer.echo(f"  corrected_rmse_mean: {summary['evaluation']['overall']['rmse_mean']:.6f}")
        typer.echo(f"  corrected_mae_mean: {summary['evaluation']['overall']['mae_mean']:.6f}")
        typer.echo(f"  corrected_r2_mean: {summary['evaluation']['overall']['r2_mean']:.6f}")


@ml_app.command("compare-seeds")
def ml_compare_seeds(
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
    features: str | None = typer.Option(None, "--features", help="Comma-separated feature columns."),
    feature_preset: str | None = typer.Option(None, "--feature-preset", help="Named feature preset, e.g. bwb_control. Cannot be combined with --features."),
    targets: str = typer.Option(..., "--targets", help="Comma-separated target columns."),
    models: str = typer.Option(
        ...,
        "--models",
        help=f"Comma-separated model types. Supported: {', '.join(list_model_types())}",
    ),
    seeds: str = typer.Option(..., "--seeds", help="Comma-separated random seeds, e.g. 101,202,303."),
    split_method: str = typer.Option("grouped", "--split-method", help="Split method: grouped or random."),
    group_column: str = typer.Option("geometry_id", "--group-column", help="Grouping column for grouped split."),
    train_fraction: float = typer.Option(0.7, "--train-fraction"),
    val_fraction: float = typer.Option(0.15, "--val-fraction"),
    test_fraction: float = typer.Option(0.15, "--test-fraction"),
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
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Optional output directory for seed-stability artifacts."),
) -> None:
    """Compare model families across multiple split seeds."""
    try:
        feature_cols = _resolve_feature_columns_cli(features=features, feature_preset=feature_preset)
        target_cols = parse_csv_list(targets, "--targets")
        model_types = parse_csv_list(models, "--models")
        seed_values = [int(value) for value in parse_csv_list(seeds, "--seeds")]

        result = compare_models_across_seeds(
            dataset_path=dataset,
            feature_columns=feature_cols,
            target_columns=target_cols,
            model_types=model_types,
            seeds=seed_values,
            split_method=split_method,
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            allow_forced=allow_forced,
            model_params_by_type=(
                load_model_params_by_type_json(model_params_json)
                if model_params_json is not None
                else None
            ),
            output_dir=output_dir,
        )
    except Exception as exc:
        fail_command("ML compare-seeds", exc)

    winner = result["summary"]["winner_report"]
    typer.echo("[AERIS] ML seed-stability comparison completed")
    typer.echo(f"  dataset: {dataset}")
    typer.echo(f"  models: {models}")
    typer.echo(f"  seeds: {seeds}")
    typer.echo(f"  output_dir: {result['output_dir']}")
    typer.echo(f"  summary_json: {result['summary_json']}")
    typer.echo(f"  model_stability_summary_csv: {result['model_stability_summary_csv']}")
    typer.echo(f"  per_target_ranking_csv: {result['per_target_ranking_csv']}")
    typer.echo(f"  winner_report_json: {result['winner_report_json']}")
    typer.echo(f"  winner_by_mean_test_rmse: {winner['winner_by_mean_test_rmse']}")
    typer.echo(f"  winner_by_rmse_win_count: {winner['winner_by_rmse_win_count']}")


@ml_app.command("compare-tuning-runs")
def ml_compare_tuning_runs(
    runs: str = typer.Option(..., "--runs", help="Comma-separated tuning run directories containing best_trial.json."),
    selection_metric: str = typer.Option("val.rmse_mean", "--selection-metric", help="Metric used to rank tuning runs."),
    minimize: bool = typer.Option(True, "--minimize/--maximize", help="Whether lower selection metric is better."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Optional output directory for tuning-run comparison artifacts."),
) -> None:
    """Compare completed tuning campaigns by their best trials."""
    try:
        run_dirs = [Path(value) for value in parse_csv_list(runs, "--runs")]
        result = compare_tuning_runs(
            tuning_run_dirs=run_dirs,
            selection_metric=selection_metric,
            minimize=minimize,
            output_dir=output_dir,
        )
    except Exception as exc:
        fail_command("ML compare-tuning-runs", exc)

    winner = result["summary"]["winner_report"]
    typer.echo("[AERIS] ML tuning-run comparison completed")
    typer.echo(f"  runs: {runs}")
    typer.echo(f"  selection_metric: {selection_metric}")
    typer.echo(f"  minimize: {minimize}")
    typer.echo(f"  output_dir: {result['output_dir']}")
    typer.echo(f"  summary_json: {result['summary_json']}")
    typer.echo(f"  summary_csv: {result['summary_csv']}")
    typer.echo(f"  winner_report_json: {result['winner_report_json']}")
    typer.echo(f"  winner_model_type: {winner['winner_model_type']}")
    typer.echo(f"  winner_score: {winner['winner_score']}")



@ml_app.command("promote-model")
def ml_promote_model(
    model_run_dir: Path = typer.Option(..., "--model-run-dir", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True, help="Path to a saved ML training run directory."),
    max_val_rmse_mean: float | None = typer.Option(None, "--max-val-rmse-mean", help="Optional maximum allowed validation RMSE mean."),
    max_test_rmse_mean: float | None = typer.Option(None, "--max-test-rmse-mean", help="Optional maximum allowed test RMSE mean."),
    min_test_r2_mean: float | None = typer.Option(None, "--min-test-r2-mean", help="Optional minimum allowed test R2 mean."),
    require_diagnostics: bool = typer.Option(True, "--require-diagnostics/--no-require-diagnostics", help="Require diagnostics artifacts to exist."),
    allow_forced_dataset: bool = typer.Option(False, "--allow-forced-dataset", help="Allow promotion of models trained from force-promoted datasets."),
    notes: str | None = typer.Option(None, "--notes", help="Optional operator note recorded in the promotion manifest."),
) -> None:
    """Promote a trained ML model run for downstream use."""
    try:
        result = promote_model_run(
            model_run_dir=model_run_dir,
            max_val_rmse_mean=max_val_rmse_mean,
            max_test_rmse_mean=max_test_rmse_mean,
            min_test_r2_mean=min_test_r2_mean,
            require_diagnostics=require_diagnostics,
            allow_forced_dataset=allow_forced_dataset,
            notes=notes,
        )
    except Exception as exc:
        fail_command("ML promote-model", exc)

    typer.echo("[AERIS] Model promotion completed")
    typer.echo(f"  model_run_dir: {result.model_run_dir}")
    typer.echo(f"  status: {result.manifest['status']}")
    typer.echo(f"  promotion_ready_at_time_of_promotion: {result.passed}")
    typer.echo(f"  promotion_manifest: {result.manifest_path}")
    typer.echo(f"  model_card: {result.model_card_path}")
    typer.echo(f"  training_envelope: {result.training_envelope_path}")
    typer.echo(f"  blockers: {result.blockers}")
    typer.echo(f"  warnings: {result.warnings}")
    if not result.passed:
        raise typer.Exit(code=1)


@ml_app.command("inspect-model")
def ml_inspect_model(
    model_run_dir: Path = typer.Option(..., "--model-run-dir", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True, help="Path to a saved ML training run directory."),
) -> None:
    """Inspect a saved ML model run and its promotion status."""
    try:
        info = inspect_model_run(model_run_dir)
    except Exception as exc:
        fail_command("ML inspect-model", exc)

    typer.echo("[AERIS] ML model inspection")
    typer.echo(f"  model_run_dir: {info['model_run_dir']}")
    typer.echo(f"  model_type: {info['model_type']}")
    typer.echo(f"  dataset_path: {info['dataset_path']}")
    typer.echo(f"  features: {', '.join(info['feature_columns'])}")
    typer.echo(f"  targets: {', '.join(info['target_columns'])}")
    typer.echo(f"  val_rmse_mean: {info['metrics']['val_rmse_mean']}")
    typer.echo(f"  test_rmse_mean: {info['metrics']['test_rmse_mean']}")
    typer.echo(f"  test_r2_mean: {info['metrics']['test_r2_mean']}")
    typer.echo(f"  promotion_status: {info['promotion']['status']}")
    typer.echo(f"  promotion_ready: {info['promotion']['promotion_ready_at_time_of_promotion']}")
    typer.echo(f"  promotion_manifest: {info['promotion']['manifest_path']}")
    typer.echo(f"  promotion_blockers: {info['promotion']['blockers']}")
    typer.echo(f"  has_model_card: {info['has_model_card']}")


@ml_app.command("require-promoted-model")
def ml_require_promoted_model(
    model_run_dir: Path = typer.Option(..., "--model-run-dir", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True, help="Path to a saved ML training run directory."),
    verify_hashes: bool = typer.Option(True, "--verify-hashes/--no-verify-hashes", help="Verify current artifact hashes against promotion manifest."),
) -> None:
    """Require that a saved ML model run has an approved promotion manifest."""
    try:
        manifest = require_promoted_model_gate(model_run_dir, verify_hashes=verify_hashes)
    except Exception as exc:
        fail_command("ML require-promoted-model", exc)

    typer.echo("[AERIS] Promoted model gate check")
    typer.echo(f"  model_run_dir: {model_run_dir}")
    typer.echo(f"  status: {manifest.get('status')}")
    typer.echo(f"  promotion_ready_at_time_of_promotion: {manifest.get('promotion_ready_at_time_of_promotion')}")
    typer.echo(f"  model_type: {manifest.get('model', {}).get('model_type')}")
    typer.echo(f"  source_dataset: {manifest.get('dataset', {}).get('dataset_path')}")
    typer.echo(f"  blockers: {manifest.get('promotion_blockers', [])}")


@ml_app.command("check-inference-inputs")
def ml_check_inference_inputs(
    model_run_dir: Path = typer.Option(..., "--model-run-dir", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True, help="Path to a saved ML training run directory."),
    input_csv: Path = typer.Option(..., "--input-csv", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, help="CSV file containing required feature columns."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Optional output directory for inference-guard artifacts."),
    require_promoted_model: bool = typer.Option(True, "--require-promoted-model/--no-require-promoted-model", help="Require model_promotion_manifest.json to be approved before checking inference inputs."),
    fail_on_violations: bool = typer.Option(False, "--fail-on-violations/--no-fail-on-violations", help="Exit nonzero if envelope or schema violations are found."),
    tolerance: float = typer.Option(0.0, "--tolerance", help="Absolute tolerance applied to training-envelope min/max checks."),
) -> None:
    """Check whether an input CSV is inside the promoted model training envelope."""
    try:
        result = check_inference_inputs(
            model_run_dir=model_run_dir,
            input_csv=input_csv,
            output_dir=output_dir,
            require_promoted_model_gate=require_promoted_model,
            fail_on_violations=False,
            tolerance=tolerance,
        )
    except Exception as exc:
        fail_command("ML check-inference-inputs", exc)

    typer.echo("[AERIS] ML inference-input guard")
    typer.echo(f"  model_run_dir: {result.model_run_dir}")
    typer.echo(f"  input_csv: {result.input_csv}")
    typer.echo(f"  passed: {result.passed}")
    typer.echo(f"  report_json: {result.report_path}")
    typer.echo(f"  errors: {len(result.errors)}")
    typer.echo(f"  warnings: {len(result.warnings)}")
    for issue in result.errors:
        typer.echo(f"  ERROR: {issue}")
    for issue in result.warnings:
        typer.echo(f"  WARNING: {issue}")
    if fail_on_violations and not result.passed:
        raise typer.Exit(code=1)


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
    require_promoted_model: bool = typer.Option(
        False,
        "--require-promoted-model",
        help="Require model_promotion_manifest.json to be approved before prediction.",
    ),
    enforce_envelope: bool = typer.Option(
        False,
        "--enforce-envelope",
        help="Require input CSV feature ranges to stay within the promoted model training envelope.",
    ),
    envelope_tolerance: float = typer.Option(
        0.0,
        "--envelope-tolerance",
        help="Absolute tolerance applied to training-envelope min/max checks.",
    ),
    include_truth_if_available: bool = typer.Option(
        True,
        "--include-truth-if-available/--no-include-truth-if-available",
        help="If target columns already exist in the input CSV, also compute prediction error metrics.",
    ),
) -> None:
    """Run inference using a saved trained model against an input CSV."""
    try:
        if require_promoted_model:
            require_promoted_model_gate(model_run_dir)
        if enforce_envelope:
            check_inference_inputs(
                model_run_dir=model_run_dir,
                input_csv=input_csv,
                output_dir=output_dir,
                require_promoted_model_gate=require_promoted_model,
                fail_on_violations=True,
                tolerance=envelope_tolerance,
            )

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
