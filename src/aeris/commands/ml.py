from __future__ import annotations

from pathlib import Path

import typer

from aeris.ml.train import train_baseline_model

ml_app = typer.Typer(
    help="Machine-learning training commands for promoted AERIS datasets."
)


@ml_app.command("train")
def ml_train(
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
    features: str = typer.Option(
        ...,
        "--features",
        help="Comma-separated feature columns.",
    ),
    targets: str = typer.Option(
        ...,
        "--targets",
        help="Comma-separated target columns.",
    ),
    model_type: str = typer.Option(
        "linear_regression",
        "--model-type",
        help="Model type: linear_regression or random_forest.",
    ),
    split_method: str = typer.Option(
        "grouped",
        "--split-method",
        help="Split method: grouped or random.",
    ),
    group_column: str = typer.Option(
        "geometry_id",
        "--group-column",
        help="Grouping column for grouped split.",
    ),
    train_fraction: float = typer.Option(0.7, "--train-fraction"),
    val_fraction: float = typer.Option(0.15, "--val-fraction"),
    test_fraction: float = typer.Option(0.15, "--test-fraction"),
    random_seed: int = typer.Option(123, "--random-seed"),
    allow_forced: bool = typer.Option(
        False,
        "--allow-forced",
        help="Allow use of a force-promoted dataset.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional output directory for model artifacts and metrics.",
    ),
) -> None:
    feature_cols = [f.strip() for f in features.split(",") if f.strip()]
    target_cols = [t.strip() for t in targets.split(",") if t.strip()]

    try:
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
            output_dir=output_dir,
        )
    except Exception as exc:
        raise typer.BadParameter(str(exc))

    artifacts = result["artifacts"]
    metrics = result["metrics"]
    split = result["split"]

    typer.echo("[AERIS] ML training completed")
    typer.echo(f"  model_type: {model_type}")
    typer.echo(f"  split_method: {split.method}")
    typer.echo(f"  train_rows: {len(split.train_df)}")
    typer.echo(f"  val_rows: {len(split.val_df)}")
    typer.echo(f"  test_rows: {len(split.test_df)}")
    typer.echo(f"  output_dir: {artifacts.run_dir}")
    typer.echo(f"  metrics_json: {artifacts.metrics_path}")
    typer.echo(f"  model_dir: {artifacts.models_dir}")
    typer.echo(
        f"  test_r2_mean: {metrics['test']['overall']['r2_mean']:.6f}"
    )
    typer.echo(
        f"  test_rmse_mean: {metrics['test']['overall']['rmse_mean']:.6f}"
    )