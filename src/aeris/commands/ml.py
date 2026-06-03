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
from aeris.commands._workflow_recording import record_workflow_stage_success
from aeris.ml.compare import compare_models
from aeris.ml.compare_hardening import compare_models_across_seeds, compare_tuning_runs
from aeris.ml.config import load_model_params_by_type_json, load_model_params_json
from aeris.ml.feature_sets import FeatureSetError, get_feature_set
from aeris.ml.feature_presets import (
    FeaturePresetError,
    list_feature_presets,
    resolve_feature_columns,
)
from aeris.ml.eda import run_eda
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
from aeris.ml.promotion_gates import suggest_promotion_gates
from aeris.ml.model_registry import list_model_types
from aeris.ml.inference_guard import check_inference_inputs
from aeris.ml.multifidelity import build_delta_dataset
from aeris.ml.multifidelity.delta_model import predict_with_delta_model, train_delta_model
from aeris.ml.multifidelity.evaluation import evaluate_delta_model_run
from aeris.ml.predict import predict_with_trained_model
from aeris.ml.active_learning import suggest_samples
from aeris.ml.quality import audit_model, predict_with_confidence
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
    feature_set: str | None = None,
) -> list[str]:
    selected = [
        name
        for name, value in (
            ("--features", features),
            ("--feature-preset", feature_preset),
            ("--feature-set", feature_set),
        )
        if value is not None and str(value).strip()
    ]
    if len(selected) > 1:
        raise typer.BadParameter(
            "Use only one of --features, --feature-preset, or --feature-set. "
            f"Received: {', '.join(selected)}"
        )

    if feature_set is not None and str(feature_set).strip():
        try:
            return list(get_feature_set(feature_set).columns)
        except FeatureSetError as exc:
            raise typer.BadParameter(str(exc)) from exc

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




@ml_app.command("feature-sets")
def ml_feature_sets() -> None:
    """List named ML feature sets."""
    from aeris.ml.feature_sets import list_feature_sets

    typer.echo("[AERIS] ML feature sets")
    for feature_set in list_feature_sets(include_inactive=True):
        typer.echo(
            f"  - {feature_set.name} [{feature_set.status}] "
            f"({feature_set.domain}; generator={feature_set.generator_id or 'generic'})"
        )
        typer.echo(f"    raw_features: {', '.join(feature_set.raw_columns)}")
        if feature_set.engineered_columns:
            typer.echo(f"    engineered_features: {', '.join(feature_set.engineered_columns)}")
        else:
            typer.echo("    engineered_features: none")
        if feature_set.transforms:
            typer.echo(f"    transforms: {', '.join(feature_set.transforms)}")
        typer.echo(f"    description: {feature_set.description}")


@ml_app.command("describe-feature-set")
def ml_describe_feature_set(
    feature_set: str = typer.Option(
        ...,
        "--feature-set",
        help="Named feature set, e.g. bwb_control_raw or bwb_control_physics_v1.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON description."),
) -> None:
    """Describe one ML feature set."""
    import json

    from aeris.ml.feature_sets import FeatureSetError, describe_feature_set

    try:
        payload = describe_feature_set(feature_set)
    except FeatureSetError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except Exception as exc:
        fail_command("ML describe-feature-set", exc)

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo("[AERIS] ML feature set")
    typer.echo(f"  name: {payload['name']}")
    typer.echo(f"  status: {payload['status']}")
    typer.echo(f"  domain: {payload['domain']}")
    typer.echo(f"  generator_id: {payload.get('generator_id') or 'generic'}")
    typer.echo(f"  version: {payload['version']}")
    typer.echo(f"  raw_features: {', '.join(payload['raw_columns'])}")
    engineered = payload.get("engineered_columns", [])
    typer.echo(f"  engineered_features: {', '.join(engineered) if engineered else 'none'}")
    transforms = payload.get("transforms", [])
    typer.echo(f"  transforms: {', '.join(transforms) if transforms else 'none'}")
    typer.echo(f"  final_features: {', '.join(payload['columns'])}")
    typer.echo(f"  description: {payload['description']}")


@ml_app.command("validate-feature-set")
def ml_validate_feature_set(
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
    feature_set: str = typer.Option(
        ...,
        "--feature-set",
        help="Named feature set, e.g. bwb_control_raw or bwb_control_physics_v1.",
    ),
    targets: str | None = typer.Option(
        None,
        "--targets",
        help="Optional comma-separated target columns to validate with the feature set.",
    ),
    group_column: str = typer.Option(
        "geometry_id",
        "--group-column",
        help="Grouping column for grouped split readiness checks.",
    ),
    allow_forced: bool = typer.Option(False, "--allow-forced", help=_ALLOW_FORCED_HELP),
    json_output: bool = typer.Option(False, "--json", help="Print full validation result as JSON."),
) -> None:
    """Validate a promoted dataset against a named ML feature set."""
    import json

    from aeris.ml.feature_sets import FeatureSetError, validate_promoted_dataset_feature_set

    try:
        target_cols = parse_csv_list(targets, "--targets") if targets else []
        result = validate_promoted_dataset_feature_set(
            dataset_path=dataset,
            feature_set_name=feature_set,
            target_columns=target_cols,
            group_column=group_column,
            allow_forced=allow_forced,
        )
    except FeatureSetError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except Exception as exc:
        fail_command("ML validate-feature-set", exc)

    if json_output:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        metadata = result.metadata
        typer.echo("[AERIS] ML feature-set validation")
        typer.echo(f"  dataset: {metadata.get('dataset_path')}")
        typer.echo(f"  curated_csv: {metadata.get('curated_csv_path')}")
        typer.echo(f"  feature_set: {metadata.get('feature_set_id')}")
        typer.echo(f"  domain: {metadata.get('domain')}")
        typer.echo(f"  generator_id: {metadata.get('generator_id') or 'generic'}")
        typer.echo(f"  passed: {result.passed}")
        typer.echo(f"  rows: {metadata.get('n_rows')}")
        typer.echo(f"  raw_features: {', '.join(metadata.get('raw_features', []))}")
        engineered = metadata.get("engineered_features", [])
        typer.echo(f"  engineered_features: {', '.join(engineered) if engineered else 'none'}")
        typer.echo(f"  final_features: {', '.join(metadata.get('feature_columns', []))}")
        targets_out = metadata.get("target_columns", [])
        typer.echo(f"  targets: {', '.join(targets_out) if targets_out else 'none'}")
        typer.echo(f"  group_column: {metadata.get('group_column')}")
        typer.echo(f"  groups: {metadata.get('n_groups')}")
        typer.echo(f"  transforms: {', '.join(metadata.get('transforms', [])) if metadata.get('transforms') else 'none'}")
        typer.echo(f"  errors: {len(result.errors)}")
        typer.echo(f"  warnings: {len(result.warnings)}")
        for issue in result.errors:
            typer.echo(f"  ERROR [{issue.code}]: {issue.message}")
        for issue in result.warnings:
            typer.echo(f"  WARNING [{issue.code}]: {issue.message}")

    if not result.passed:
        raise typer.Exit(code=1)

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



@ml_app.command("eda")
def ml_eda(
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
    features: str | None = typer.Option(
        None,
        "--features",
        help="Comma-separated explicit feature columns. Use exactly one of --features, --feature-preset, or --feature-set.",
    ),
    feature_preset: str | None = typer.Option(
        None,
        "--feature-preset",
        help="Named feature preset such as bwb_control. Use exactly one of --features, --feature-preset, or --feature-set.",
    ),
    feature_set: str | None = typer.Option(
        None,
        "--feature-set",
        help="Named feature set to validate/materialize before EDA, e.g. bwb_control_physics_v1.",
    ),
    targets: str = typer.Option(
        ...,
        "--targets",
        help="Comma-separated target columns, e.g. cl,cd,cm.",
    ),
    group_column: str = typer.Option(
        "geometry_id",
        "--group-column",
        help="Grouping column used for coverage summaries.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Output directory for EDA artifacts. Defaults to <dataset>/eda.",
    ),
    allow_forced: bool = typer.Option(
        False,
        "--allow-forced",
        help="Allow EDA on a force-promoted dataset. Use only for smoke/debug workflows.",
    ),
    plots: bool = typer.Option(
        False,
        "--plots",
        help="Write basic PNG EDA plots in addition to JSON/Markdown reports.",
    ),
    no_plots: bool = typer.Option(
        False,
        "--no-plots",
        help="Disable EDA plots explicitly.",
    ),
    outlier_sigma: float = typer.Option(
        4.0,
        "--outlier-sigma",
        min=0.1,
        help="Sigma threshold used for simple outlier scan.",
    ),
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root to auto-record ML EDA after success.",
    ),
) -> None:
    """Run leakage-safe EDA on a promoted dataset or feature-set view."""
    from aeris.ml.eda import run_promoted_dataset_eda

    try:
        target_cols = parse_csv_list(targets, "--targets")
        resolved_feature_cols = _resolve_feature_columns_cli(
            features=features,
            feature_preset=feature_preset,
            feature_set=feature_set,
        )
        result = run_promoted_dataset_eda(
            dataset_root=dataset,
            feature_columns=None if feature_set else resolved_feature_cols,
            feature_set_name=feature_set,
            target_columns=target_cols,
            group_column=group_column,
            allow_forced=allow_forced,
            outlier_sigma=outlier_sigma,
            output_dir=output_dir,
            write_plots=bool(plots and not no_plots),
        )
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("ML EDA", exc)

    report = result["report"]
    metadata = report.get("metadata", {}) or {}
    plots_dir = result.get("plots_dir")

    typer.echo("[AERIS] ML EDA completed")
    typer.echo(f"  dataset: {Path(dataset).expanduser().resolve()}")
    typer.echo(f"  curated_csv: {result['curated_csv']}")
    typer.echo(f"  rows: {report.get('shape', {}).get('n_rows')}")
    typer.echo(f"  features: {', '.join(metadata.get('feature_columns', []))}")
    typer.echo(f"  targets: {', '.join(metadata.get('target_columns', []))}")
    typer.echo(f"  feature_set: {metadata.get('feature_set_name')}")
    typer.echo(f"  feature_set_applied: {metadata.get('feature_set_applied')}")
    typer.echo(f"  output_dir: {result['output_dir']}")
    typer.echo(f"  eda_report_json: {result['report_path']}")
    typer.echo(f"  eda_summary_md: {result['summary_path']}")
    if plots_dir is not None:
        typer.echo(f"  plots_dir: {plots_dir}")

    try:
        record_workflow_stage_success(
            workflow=workflow,
            stage="ml_eda",
            inputs=[dataset],
            artifacts=[result.get("output_dir"), result.get("report_path"), result.get("summary_path")],
            notes="ML EDA completed.",
            metadata={
                "command": "aeris ml eda",
                "feature_preset": feature_preset,
                "feature_set": feature_set,
                "targets": target_cols,
                "rows": report.get("shape", {}).get("n_rows"),
            },
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)




@ml_app.command("feature-engineer")
def ml_feature_engineer(
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
    feature_set: str = typer.Option(
        ...,
        "--feature-set",
        help="Named feature set to materialize, e.g. bwb_control_physics_v1.",
    ),
    targets: str | None = typer.Option(
        None,
        "--targets",
        help="Optional comma-separated target columns to keep/validate.",
    ),
    group_column: str = typer.Option(
        "geometry_id",
        "--group-column",
        help="Grouping column to keep/validate for leakage-safe splits.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Output directory. Defaults to <dataset>/features/<feature_set>.",
    ),
    allow_forced: bool = typer.Option(False, "--allow-forced", help=_ALLOW_FORCED_HELP),
    include_all_columns: bool = typer.Option(
        True,
        "--include-all-columns/--only-feature-columns",
        help="Write all source columns plus engineered columns, or only group/features/targets.",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing materialized artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print full materialization result as JSON."),
) -> None:
    """Materialize a named feature set into an explicit engineered dataset artifact."""
    import json

    from aeris.ml.feature_materialization import (
        FeatureMaterializationError,
        materialize_feature_set_dataset,
    )
    from aeris.ml.feature_sets import FeatureSetError

    try:
        target_cols = parse_csv_list(targets, "--targets") if targets else []
        result = materialize_feature_set_dataset(
            dataset_path=dataset,
            feature_set_name=feature_set,
            target_columns=target_cols,
            group_column=group_column,
            output_dir=output_dir,
            allow_forced=allow_forced,
            include_all_columns=include_all_columns,
            overwrite=overwrite,
        )
    except (FeatureMaterializationError, FeatureSetError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    except Exception as exc:
        fail_command("ML feature-engineer", exc)

    if json_output:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    validation = result.validation
    typer.echo("[AERIS] ML feature-set materialization completed")
    typer.echo(f"  dataset: {result.dataset_path}")
    typer.echo(f"  curated_csv: {result.curated_csv_path}")
    typer.echo(f"  feature_set: {result.feature_set.name}")
    typer.echo(f"  domain: {result.feature_set.domain}")
    typer.echo(f"  generator_id: {result.feature_set.generator_id or 'generic'}")
    typer.echo(f"  output_dir: {result.output_dir}")
    typer.echo(f"  engineered_dataset_csv: {result.engineered_dataset_csv}")
    typer.echo(f"  feature_engineering_manifest_json: {result.feature_engineering_manifest_json}")
    typer.echo(f"  feature_schema_json: {result.feature_schema_json}")
    typer.echo(f"  feature_materialization_report_json: {result.feature_materialization_report_json}")
    typer.echo(f"  rows: {result.n_rows}")
    typer.echo(f"  columns: {result.n_columns}")
    typer.echo(f"  final_features: {', '.join(result.feature_set.columns)}")
    typer.echo(f"  targets: {', '.join(validation.metadata.get('target_columns', [])) if validation.metadata.get('target_columns') else 'none'}")
    typer.echo(f"  validation_passed: {validation.passed}")
    typer.echo(f"  warnings: {len(validation.warnings)}")
    for issue in validation.warnings:
        typer.echo(f"  WARNING [{issue.code}]: {issue.message}")


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
    feature_set: str | None = typer.Option(
        None,
        "--feature-set",
        help="Named feature set, e.g. bwb_control_raw or bwb_control_physics_v1. Cannot be combined with --features or --feature-preset.",
    ),
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
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root to auto-record ML training after success.",
    ),
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
            try:
                artifacts = result["artifacts"]
                metrics = result["metrics"]
                record_workflow_stage_success(
                    workflow=workflow,
                    stage="ml_training",
                    inputs=[config],
                    artifacts=[artifacts.run_dir, artifacts.metrics_path, artifacts.model_path],
                    notes="ML training completed from config.",
                    metadata={
                        "command": "aeris ml train",
                        "config_mode": True,
                        "model_type": metrics.get("model", {}).get("model_type"),
                    },
                )
            except Exception as exc:
                fail_command("Workflow auto-record", exc)
            return

        if dataset is None:
            raise typer.BadParameter("--dataset is required when --config is not used.")
        if features is None and feature_preset is None and feature_set is None:
            raise typer.BadParameter("--features, --feature-preset, or --feature-set is required when --config is not used.")
        if targets is None:
            raise typer.BadParameter("--targets is required when --config is not used.")

        feature_cols = _resolve_feature_columns_cli(features=features, feature_preset=feature_preset, feature_set=feature_set)
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
            feature_set_name=feature_set,
        )
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("ML train", exc)

    _echo_train_result(result, model_type_label=model_type)

    try:
        artifacts = result["artifacts"]
        record_workflow_stage_success(
            workflow=workflow,
            stage="ml_training",
            inputs=[dataset],
            artifacts=[artifacts.run_dir, artifacts.metrics_path, artifacts.model_path],
            notes="ML training completed.",
            metadata={
                "command": "aeris ml train",
                "model_type": model_type,
                "feature_preset": feature_preset,
                "feature_set": feature_set,
                "targets": target_cols,
                "split_method": split_method,
                "group_column": group_column,
                "random_seed": random_seed,
            },
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)


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
    feature_set: str | None = typer.Option(
        None,
        "--feature-set",
        help="Named feature set, e.g. bwb_control_raw or bwb_control_physics_v1. Cannot be combined with --features or --feature-preset.",
    ),
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
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root to auto-record model comparison after success.",
    ),
) -> None:
    """Compare several model families on a single fixed train/val/test split."""
    feature_cols = _resolve_feature_columns_cli(features=features, feature_preset=feature_preset, feature_set=feature_set)
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
            feature_set_name=feature_set,
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


    try:
        record_workflow_stage_success(
            workflow=workflow,
            stage="model_comparison",
            inputs=[dataset],
            artifacts=[result.get("output_dir"), result.get("comparison_summary_json"), result.get("comparison_summary_csv")],
            notes="ML model comparison completed.",
            metadata={
                "command": "aeris ml compare",
                "models": model_types,
                "feature_preset": feature_preset,
                "feature_set": feature_set,
                "targets": target_cols,
                "split_method": split_method,
                "group_column": group_column,
                "random_seed": random_seed,
                "best_model_by_test_rmse_mean": summary.get("best_model_by_test_rmse_mean"),
            },
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)


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
    feature_set: str | None = typer.Option(
        None,
        "--feature-set",
        help="Named feature set, e.g. bwb_control_raw or bwb_control_physics_v1. Cannot be combined with --features or --feature-preset.",
    ),
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
                if features is None and feature_preset is None and feature_set is None:
                    raise typer.BadParameter("--features, --feature-preset, or --feature-set is required when --config is not used.")
                if targets is None:
                    raise typer.BadParameter("--targets is required when --config is not used.")

                result = tune_model_optuna(
                    dataset_path=dataset,
                    feature_columns=_resolve_feature_columns_cli(features=features, feature_preset=feature_preset, feature_set=feature_set),
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
                    feature_set_name=feature_set,
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
                if features is None and feature_preset is None and feature_set is None:
                    raise typer.BadParameter("--features, --feature-preset, or --feature-set is required when --config is not used.")
                if targets is None:
                    raise typer.BadParameter("--targets is required when --config is not used.")

                result = tune_model(
                    dataset_path=dataset,
                    feature_columns=_resolve_feature_columns_cli(features=features, feature_preset=feature_preset, feature_set=feature_set),
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
                    feature_set_name=feature_set,
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
    features: str | None = typer.Option(None, "--features", help="Comma-separated explicit feature columns. Mutually exclusive with --feature-set."),
    feature_set: str | None = typer.Option(None, "--feature-set", help="Named feature set to apply before delta training. LF target columns are appended automatically."),
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
            feature_columns=(parse_csv_list(features, "--features") if features is not None else None),
            feature_set_name=feature_set,
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
    typer.echo(f"  feature_set: {result['manifest'].get('feature_set_name')}")
    typer.echo(f"  feature_columns: {', '.join(result['manifest'].get('features', []))}")
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
    feature_set: str | None = typer.Option(None, "--feature-set", help="Named feature set to apply to raw delta-prediction inputs before correction."),
    allow_feature_set_mismatch: bool = typer.Option(False, "--allow-feature-set-mismatch", help="Allow requested feature set to differ from the delta model training feature set."),
) -> None:
    """Predict deltas and corrected HF-like scalar outputs using a trained delta model."""
    try:
        result = predict_with_delta_model(
            model_run_dir=model_run_dir,
            input_csv=input_csv,
            output_dir=output_dir,
            include_truth_if_available=include_truth_if_available,
            feature_set_name=feature_set,
            allow_feature_set_mismatch=allow_feature_set_mismatch,
        )
    except Exception as exc:
        fail_command("ML predict-delta-model", exc)

    summary = result["summary"]
    artifacts = result["artifacts"]
    typer.echo("[AERIS] ML multifidelity delta prediction completed")
    typer.echo(f"  model_run_dir: {summary['model_run_dir']}")
    typer.echo(f"  n_rows: {summary['n_rows']}")
    typer.echo(f"  input_csv: {summary['input_csv']}")
    typer.echo(f"  feature_set: {summary.get('feature_set_name')}")
    typer.echo(f"  feature_set_applied: {summary.get('feature_set_applied')}")
    typer.echo(f"  output_dir: {artifacts.output_dir}")
    typer.echo(f"  predictions_csv: {artifacts.predictions_csv}")
    typer.echo(f"  prediction_summary_json: {artifacts.prediction_summary_json}")
    typer.echo(f"  truth_available: {summary['truth_available']}")
    if summary["evaluation"] is not None:
        typer.echo(f"  corrected_rmse_mean: {summary['evaluation']['overall']['rmse_mean']:.6f}")
        typer.echo(f"  corrected_mae_mean: {summary['evaluation']['overall']['mae_mean']:.6f}")
        typer.echo(f"  corrected_r2_mean: {summary['evaluation']['overall']['r2_mean']:.6f}")


@ml_app.command("evaluate-delta-model")
def ml_evaluate_delta_model(
    model_run_dir: Path = typer.Option(..., "--model-run-dir", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True, help="Path to a trained delta model run directory."),
    partitions: str = typer.Option("train,val,test", "--partitions", help="Comma-separated partitions to evaluate, e.g. train,val,test or test."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Optional output directory for multifidelity evaluation artifacts."),
) -> None:
    """Evaluate whether a delta model improves LF predictions against HF truth."""
    try:
        result = evaluate_delta_model_run(
            model_run_dir=model_run_dir,
            partitions=parse_csv_list(partitions, "--partitions"),
            output_dir=output_dir,
        )
    except Exception as exc:
        fail_command("ML evaluate-delta-model", exc)

    winner = result.report["winner_report"]
    typer.echo("[AERIS] ML multifidelity delta-model evaluation completed")
    typer.echo(f"  model_run_dir: {result.model_run_dir}")
    typer.echo(f"  output_dir: {result.output_dir}")
    typer.echo(f"  report_json: {result.report_json}")
    typer.echo(f"  report_csv: {result.report_csv}")
    typer.echo(f"  selection_partition: {winner['selection_partition']}")
    typer.echo(f"  status: {winner['status']}")
    typer.echo(f"  lf_rmse_mean: {winner['lf_rmse_mean']:.6f}")
    typer.echo(f"  corrected_rmse_mean: {winner['corrected_rmse_mean']:.6f}")
    typer.echo(f"  rmse_improvement_pct_mean: {winner['rmse_improvement_pct_mean']}")
    typer.echo(f"  improved_targets: {winner['improved_targets']}")
    typer.echo(f"  worsened_targets: {winner['worsened_targets']}")


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
    feature_set: str | None = typer.Option(
        None,
        "--feature-set",
        help="Named feature set, e.g. bwb_control_raw or bwb_control_physics_v1. Cannot be combined with --features or --feature-preset.",
    ),
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
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root to auto-record model comparison after seed-stability analysis succeeds.",
    ),
) -> None:
    """Compare model families across multiple split seeds."""
    try:
        feature_cols = _resolve_feature_columns_cli(features=features, feature_preset=feature_preset, feature_set=feature_set)
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
            feature_set_name=feature_set,
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


    try:
        record_workflow_stage_success(
            workflow=workflow,
            stage="model_comparison",
            inputs=[dataset],
            artifacts=[result.get("output_dir"), result.get("summary_json"), result.get("summary_csv"), result.get("winner_report_json")],
            notes="ML seed-stability comparison completed.",
            metadata={
                "command": "aeris ml compare-seeds",
                "models": model_types,
                "seeds": seed_values,
                "feature_preset": feature_preset,
                "feature_set": feature_set,
                "targets": target_cols,
                "winner_by_mean_test_rmse": winner.get("winner_by_mean_test_rmse"),
                "winner_by_rmse_win_count": winner.get("winner_by_rmse_win_count"),
            },
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)


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



@ml_app.command("suggest-promotion-gates")
def ml_suggest_promotion_gates(
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
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Output directory for promotion_gate_suggestions.json and promotion_gates_template.yaml.",
    ),
    profile: str = typer.Option(
        "normal",
        "--profile",
        help="Suggestion profile: strict, normal, or loose.",
    ),
) -> None:
    """Suggest generic, scale-aware per-target model-promotion gates."""
    try:
        result = suggest_promotion_gates(
            model_run_dir=model_run_dir,
            output_dir=output_dir,
            profile=profile,
        )
    except Exception as exc:
        fail_command("ML suggest-promotion-gates", exc)

    targets = result.report.get("target_columns", [])
    typer.echo("[AERIS] ML promotion gate suggestions completed")
    typer.echo(f"  model_run_dir: {result.model_run_dir}")
    typer.echo(f"  profile: {result.report.get('profile')}")
    typer.echo(f"  targets: {', '.join(targets)}")
    typer.echo(f"  output_dir: {result.output_dir}")
    typer.echo(f"  suggestions_json: {result.report_path}")
    typer.echo(f"  gate_template_yaml: {result.template_path}")
    typer.echo(f"  template_preview_passes_current_model: {result.report.get('template_preview_passes_current_model')}")
    blockers = result.report.get("template_preview_blockers", [])
    typer.echo(f"  template_preview_blockers: {len(blockers)}")
    for blocker in blockers[:10]:
        typer.echo(f"  BLOCKER: {blocker}")
    warnings = result.report.get("warnings", [])
    typer.echo(f"  warnings: {len(warnings)}")
    for warning in warnings[:10]:
        typer.echo(f"  WARNING: {warning}")


@ml_app.command("promote-model")
def ml_promote_model(
    model_run_dir: Path = typer.Option(..., "--model-run-dir", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True, help="Path to a saved ML training run directory."),
    max_val_rmse_mean: float | None = typer.Option(None, "--max-val-rmse-mean", help="Optional maximum allowed validation RMSE mean."),
    max_test_rmse_mean: float | None = typer.Option(None, "--max-test-rmse-mean", help="Optional maximum allowed test RMSE mean."),
    min_test_r2_mean: float | None = typer.Option(None, "--min-test-r2-mean", help="Optional minimum allowed test R2 mean."),
    gate_config: Path | None = typer.Option(
        None,
        "--gate-config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Optional YAML/JSON promotion gate config with generic per-target thresholds.",
    ),
    require_diagnostics: bool = typer.Option(True, "--require-diagnostics/--no-require-diagnostics", help="Require diagnostics artifacts to exist."),
    allow_forced_dataset: bool = typer.Option(False, "--allow-forced-dataset", help="Allow promotion of models trained from force-promoted datasets."),
    notes: str | None = typer.Option(None, "--notes", help="Optional operator note recorded in the promotion manifest."),
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root to auto-record model promotion after success.",
    ),
) -> None:
    """Promote a trained ML model run for downstream use."""
    try:
        result = promote_model_run(
            model_run_dir=model_run_dir,
            max_val_rmse_mean=max_val_rmse_mean,
            max_test_rmse_mean=max_test_rmse_mean,
            min_test_r2_mean=min_test_r2_mean,
            gate_config_path=gate_config,
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

    try:
        record_workflow_stage_success(
            workflow=workflow,
            stage="model_promotion",
            inputs=[model_run_dir, gate_config],
            artifacts=[result.manifest_path, result.model_card_path, result.training_envelope_path],
            notes="ML model promotion completed.",
            metadata={
                "command": "aeris ml promote-model",
                "status": result.manifest.get("status"),
                "promotion_ready_at_time_of_promotion": bool(result.passed),
                "blocker_count": len(result.blockers),
                "warning_count": len(result.warnings),
            },
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)


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
    feature_set: str | None = typer.Option(None, "--feature-set", help="Named feature set to apply to the input CSV before checking inference envelope."),
    allow_feature_set_mismatch: bool = typer.Option(False, "--allow-feature-set-mismatch", help="Allow requested feature set to differ from the model training feature set."),
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root to auto-record inference-guard checks after success.",
    ),
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
            feature_set_name=feature_set,
            allow_feature_set_mismatch=allow_feature_set_mismatch,
        )
    except Exception as exc:
        fail_command("ML check-inference-inputs", exc)

    typer.echo("[AERIS] ML inference-input guard")
    typer.echo(f"  model_run_dir: {result.model_run_dir}")
    typer.echo(f"  input_csv: {result.input_csv}")
    typer.echo(f"  feature_set: {result.report.get('feature_set_name')}")
    typer.echo(f"  feature_set_applied: {result.report.get('feature_set_applied')}")
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

    if result.passed:
        try:
            record_workflow_stage_success(
                workflow=workflow,
                stage="inference_guard",
                inputs=[model_run_dir, input_csv],
                artifacts=[result.report_path, result.output_dir],
                notes="ML inference-input guard completed and passed.",
                metadata={
                    "command": "aeris ml check-inference-inputs",
                    "passed": bool(result.passed),
                    "error_count": len(result.errors),
                    "warning_count": len(result.warnings),
                    "feature_set": feature_set,
                    "require_promoted_model": require_promoted_model,
                },
            )
        except Exception as exc:
            fail_command("Workflow auto-record", exc)


@ml_app.command("audit-model")
def ml_audit_model(
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
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional output directory for model-quality artifacts.",
    ),
    max_test_rmse_mean: float | None = typer.Option(
        None,
        "--max-test-rmse-mean",
        help="Optional fail threshold: test RMSE mean must be <= this value.",
    ),
    min_test_r2_mean: float | None = typer.Option(
        None,
        "--min-test-r2-mean",
        help="Optional fail threshold: test R² mean must be >= this value.",
    ),
    max_test_error_p95_mean: float | None = typer.Option(
        None,
        "--max-test-error-p95-mean",
        help="Optional fail threshold: mean target p95 absolute error must be <= this value.",
    ),
    max_test_abs_bias_mean: float | None = typer.Option(
        None,
        "--max-test-abs-bias-mean",
        help="Optional fail threshold: mean absolute target bias must be <= this value.",
    ),
    top_k_worst_rows_per_target: int = typer.Option(
        20,
        "--top-k-worst-rows-per-target",
        min=1,
        help="Number of worst residual rows to retain per target and split.",
    ),
    fail_on_quality_gate: bool = typer.Option(
        False,
        "--fail-on-quality-gate/--no-fail-on-quality-gate",
        help="Exit nonzero if any supplied quality threshold fails.",
    ),
) -> None:
    """Audit a saved ML model run and write model-quality artifacts."""
    try:
        result = audit_model(
            model_run_dir=model_run_dir,
            output_dir=output_dir,
            max_test_rmse_mean=max_test_rmse_mean,
            min_test_r2_mean=min_test_r2_mean,
            max_test_error_p95_mean=max_test_error_p95_mean,
            max_test_abs_bias_mean=max_test_abs_bias_mean,
            top_k_worst_rows_per_target=top_k_worst_rows_per_target,
            fail_on_quality_gate=fail_on_quality_gate,
        )
    except Exception as exc:
        fail_command("ML audit-model", exc)

    typer.echo("[AERIS] ML model-quality audit completed")
    typer.echo(f"  model_run_dir: {model_run_dir}")
    typer.echo(f"  passed: {result.passed}")
    typer.echo(f"  status: {result.status}")
    typer.echo(f"  output_dir: {result.artifacts.output_dir}")
    typer.echo(f"  model_quality_report_json: {result.artifacts.report_path}")
    typer.echo(f"  residual_audit_csv: {result.artifacts.residual_audit_csv_path}")
    typer.echo(f"  errors: {len(result.report.get('errors', []))}")
    typer.echo(f"  warnings: {len(result.report.get('warnings', []))}")
    test_overall = result.report.get("partition_summaries", {}).get("test", {}).get("overall", {})
    if test_overall:
        typer.echo(f"  test_rmse_mean: {test_overall.get('rmse_mean')}")
        typer.echo(f"  test_r2_mean: {test_overall.get('r2_mean')}")


@ml_app.command("predict-with-confidence")
def ml_predict_with_confidence(
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
        help="Optional output directory for confidence artifacts.",
    ),
    require_promoted_model: bool = typer.Option(
        True,
        "--require-promoted-model/--no-require-promoted-model",
        help="Require model_promotion_manifest.json to be approved before prediction.",
    ),
    include_truth_if_available: bool = typer.Option(
        True,
        "--include-truth-if-available/--no-include-truth-if-available",
        help="If target columns exist in the input CSV, compute prediction error metrics.",
    ),
) -> None:
    """Run inference with heuristic uncertainty and training-envelope confidence diagnostics."""
    try:
        result = predict_with_confidence(
            model_run_dir=model_run_dir,
            input_csv=input_csv,
            output_dir=output_dir,
            require_promoted_model_gate=require_promoted_model,
            include_truth_if_available=include_truth_if_available,
        )
    except Exception as exc:
        fail_command("ML predict-with-confidence", exc)

    report = result.report
    typer.echo("[AERIS] ML prediction with confidence completed")
    typer.echo(f"  model_run_dir: {model_run_dir}")
    typer.echo(f"  input_csv: {input_csv}")
    typer.echo(f"  n_rows: {report['n_rows']}")
    typer.echo(f"  n_outside_envelope: {report['n_outside_envelope']}")
    typer.echo(f"  uncertainty_method: {report['uncertainty']['method']}")
    typer.echo(f"  output_dir: {result.artifacts.output_dir}")
    typer.echo(f"  prediction_confidence_csv: {result.artifacts.prediction_confidence_csv_path}")
    typer.echo(f"  prediction_confidence_report_json: {result.artifacts.report_path}")
    typer.echo(f"  truth_available: {report['truth_available']}")
    if report.get("evaluation") is not None:
        overall = report["evaluation"].get("overall", {})
        typer.echo(f"  rmse_mean: {overall.get('rmse_mean')}")
        typer.echo(f"  r2_mean: {overall.get('r2_mean')}")


@ml_app.command("suggest-samples")
def ml_suggest_samples(
    model_run_dir: Path = typer.Option(
        ...,
        "--model-run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a saved ML model run directory.",
    ),
    candidate_csv: Path = typer.Option(
        ...,
        "--candidate-csv",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="CSV file containing candidate rows with the model feature columns.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional output directory for active-learning artifacts.",
    ),
    reference_csv: Path | None = typer.Option(
        None,
        "--reference-csv",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Optional reference CSV for novelty scoring. Defaults to model_run_dir/train_rows.csv.",
    ),
    top_n: int = typer.Option(
        25,
        "--top-n",
        min=1,
        help="Number of top-ranked candidate rows to flag as recommended.",
    ),
    candidate_id_column: str | None = typer.Option(
        None,
        "--candidate-id-column",
        help="Optional existing candidate identifier column. If omitted, AERIS creates candidate_id.",
    ),
    require_promoted_model: bool = typer.Option(
        True,
        "--require-promoted-model/--no-require-promoted-model",
        help="Require an approved model_promotion_manifest.json before scoring candidates.",
    ),
    objective_column: str | None = typer.Option(
        None,
        "--objective-column",
        help="Optional column to reward during ranking, e.g. pred__cl or pred__cd.",
    ),
    objective_mode: str = typer.Option(
        "maximize",
        "--objective-mode",
        help="Objective mode: maximize, minimize, or target.",
    ),
    objective_target_value: float | None = typer.Option(
        None,
        "--objective-target-value",
        help="Required only when --objective-mode target is used.",
    ),
    uncertainty_weight: float = typer.Option(1.0, "--uncertainty-weight", help="Weight for estimator-spread uncertainty score."),
    novelty_weight: float = typer.Option(0.5, "--novelty-weight", help="Weight for distance-from-training novelty score."),
    objective_weight: float = typer.Option(0.25, "--objective-weight", help="Weight for optional objective score."),
    envelope_penalty_weight: float = typer.Option(2.0, "--envelope-penalty-weight", help="Penalty for leaving the training envelope."),
    exclude_outside_envelope: bool = typer.Option(
        False,
        "--exclude-outside-envelope/--allow-outside-envelope",
        help="If enabled, outside-envelope candidates are never recommended.",
    ),
) -> None:
    """Rank candidate samples for the next simulation batch.

    This command does not run AVL, XFOIL, CFD, or optimization. It only scores
    a candidate pool using a trained model, training-envelope metadata, and
    novelty relative to existing training rows.
    """
    if objective_mode not in {"maximize", "minimize", "target"}:
        raise typer.BadParameter("--objective-mode must be one of: maximize, minimize, target")

    try:
        result = suggest_samples(
            model_run_dir=model_run_dir,
            candidate_csv=candidate_csv,
            output_dir=output_dir,
            reference_csv=reference_csv,
            top_n=top_n,
            candidate_id_column=candidate_id_column,
            require_promoted_model_gate=require_promoted_model,
            objective_column=objective_column,
            objective_mode=objective_mode,  # type: ignore[arg-type]
            objective_target_value=objective_target_value,
            uncertainty_weight=uncertainty_weight,
            novelty_weight=novelty_weight,
            objective_weight=objective_weight,
            envelope_penalty_weight=envelope_penalty_weight,
            exclude_outside_envelope=exclude_outside_envelope,
        )
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("ML suggest-samples", exc)

    report = result.report
    artifacts = result.artifacts

    typer.echo("[AERIS] Active-learning sample suggestion completed")
    typer.echo(f"  model_run_dir: {report['model_run_dir']}")
    typer.echo(f"  candidate_csv: {report['candidate_csv']}")
    typer.echo(f"  n_candidates: {report['n_candidates']}")
    typer.echo(f"  n_recommended: {report['n_recommended']}")
    typer.echo(f"  n_outside_envelope: {report['n_outside_envelope']}")
    typer.echo(f"  uncertainty_method: {report['uncertainty']['method']}")
    typer.echo(f"  output_dir: {artifacts.output_dir}")
    typer.echo(f"  ranked_candidates_csv: {artifacts.ranked_candidates_csv_path}")
    typer.echo(f"  report_json: {artifacts.report_path}")

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
    feature_set: str | None = typer.Option(
        None,
        "--feature-set",
        help="Named feature set to apply to the input CSV before prediction.",
    ),
    allow_feature_set_mismatch: bool = typer.Option(
        False,
        "--allow-feature-set-mismatch",
        help="Allow requested feature set to differ from the model training feature set.",
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
                feature_set_name=feature_set,
                allow_feature_set_mismatch=allow_feature_set_mismatch,
            )

        result = predict_with_trained_model(
            model_run_dir=model_run_dir,
            input_csv=input_csv,
            output_dir=output_dir,
            include_truth_if_available=include_truth_if_available,
            feature_set_name=feature_set,
            allow_feature_set_mismatch=allow_feature_set_mismatch,
        )
    except Exception as exc:
        fail_command("ML predict", exc)

    summary = result["summary"]
    artifacts = result["artifacts"]

    typer.echo("[AERIS] ML prediction completed")
    typer.echo(f"  model_type: {summary['model_type']}")
    typer.echo(f"  n_rows: {summary['n_rows']}")
    typer.echo(f"  input_csv: {artifacts.input_csv_path}")
    typer.echo(f"  feature_set: {summary.get('feature_set_name')}")
    typer.echo(f"  feature_set_applied: {summary.get('feature_set_applied')}")
    typer.echo(f"  output_dir: {artifacts.run_dir}")
    typer.echo(f"  predictions_csv: {artifacts.predictions_csv_path}")
    typer.echo(f"  prediction_summary_json: {artifacts.prediction_summary_path}")
    typer.echo(f"  truth_available: {summary['truth_available']}")

    if summary["evaluation"] is not None:
        typer.echo(f"  rmse_mean: {summary['evaluation']['overall']['rmse_mean']:.6f}")
        typer.echo(f"  mae_mean: {summary['evaluation']['overall']['mae_mean']:.6f}")
        typer.echo(f"  r2_mean: {summary['evaluation']['overall']['r2_mean']:.6f}")
