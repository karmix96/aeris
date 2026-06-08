"""
CLI commands for AERIS 2D airfoil workflows.

Mirrors the 3D dataset command group structure exactly:
  aeris airfoil ingest          → X1: read xlsx library
  aeris airfoil dataset generate → X2: run XFOIL sweeps
  aeris airfoil dataset qc       → X3: quality checks
  aeris airfoil dataset curate   → X3: rejection + curation_report.json
  aeris airfoil dataset promote  → X3: promotion_manifest.json
  aeris airfoil dataset inspect  → X3: show dataset summary

This module stays thin — all logic lives in aeris.airfoil.* modules.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer

from aeris.commands._helpers import fail_command

airfoil_app = typer.Typer(
    help=(
        "2D airfoil XFOIL workflows.\n\n"
        "Workflow:\n"
        "  1. aeris airfoil ingest        — build library from .dat files\n"
        "  2. aeris airfoil dataset generate — run XFOIL polars\n"
        "  3. aeris airfoil dataset qc    — quality checks\n"
        "  4. aeris airfoil dataset curate — reject bad rows\n"
        "  5. aeris airfoil dataset promote — trust gate for ML\n"
        "Then use the standard 'aeris ml' commands with --feature-set airfoil_xfoil_v1"
    )
)

airfoil_dataset_app = typer.Typer(help="2D airfoil dataset subcommands.")
airfoil_app.add_typer(airfoil_dataset_app, name="dataset")


@airfoil_app.callback()
def airfoil_callback() -> None:
    """2D airfoil command group."""
    pass


@airfoil_dataset_app.callback()
def airfoil_dataset_callback() -> None:
    """2D airfoil dataset subcommand group."""
    pass


# ── aeris airfoil ingest ──────────────────────────────────────────────────────

@airfoil_app.command("ingest")
def airfoil_ingest(
    db_dir: Path = typer.Option(
        ...,
        "--db-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Directory containing .dat airfoil files (Selig format). "
        "This is the format used by AeroSandbox airfoil_database, UIUC, and XFOIL.",
    ),
    output_dir: Path = typer.Option(
        Path("data/airfoil_library"),
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Library output directory. Default: data/airfoil_library/",
    ),
) -> None:
    """Ingest xlsx airfoil files into the AERIS airfoil library.

    Reads all .xlsx files in --db-dir, extracts x/y coordinates,
    computes geometry statistics (t/c, camber, LE radius, TE angle),
    assigns SHA-256 airfoil_id, and writes airfoil_inventory.csv.
    """
    from aeris.airfoil.ingest import ingest_airfoil_library

    try:
        report = ingest_airfoil_library(db_dir=db_dir, output_dir=output_dir)
    except Exception as exc:
        fail_command("Airfoil ingest", exc)

    typer.echo("")
    typer.echo("[AERIS 2D] Airfoil library ingest completed")
    typer.echo(f"  db_dir:    {db_dir}")
    typer.echo(f"  output_dir:{output_dir}")
    typer.echo(f"  ingested:  {report.get('ingested')}")
    typer.echo(f"  failures:  {report.get('failures')}")
    typer.echo(f"  inventory: {report.get('inventory_csv')}")


# ── aeris airfoil dataset generate ───────────────────────────────────────────

@airfoil_dataset_app.command("generate")
def airfoil_dataset_generate(
    library_dir: Path = typer.Option(
        Path("data/airfoil_library"),
        "--library",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to ingested airfoil library. Default: data/airfoil_library/",
    ),
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="XFOIL sweep config YAML (e.g. configs/airfoil/xfoil_sweep_v1.yaml).",
    ),
    name: str = typer.Option(
        ...,
        "--name",
        help="Dataset name. Output: data/datasets/<name>/",
    ),
    dataset_root: Path = typer.Option(
        Path("data/datasets"),
        "--datasets-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Parent directory for datasets. Default: data/datasets/",
    ),
) -> None:
    """Run XFOIL alpha sweeps across the airfoil library and write airfoil_dataset.csv."""
    from aeris.airfoil.dataset_generate import generate_airfoil_dataset

    output = dataset_root / name
    try:
        manifest = generate_airfoil_dataset(
            library_dir=library_dir,
            config_path=config,
            dataset_root=output,
            name=name,
        )
    except Exception as exc:
        fail_command("Airfoil dataset generate", exc)

    typer.echo("")
    typer.echo("[AERIS 2D] Dataset generation completed")
    typer.echo(f"  name:            {name}")
    typer.echo(f"  dataset_root:    {output}")
    typer.echo(f"  total_rows:      {manifest.get('total_rows')}")
    typer.echo(f"  converged_rows:  {manifest.get('converged_rows')}")
    typer.echo(f"  convergence_rate:{manifest.get('convergence_rate'):.1%}")
    typer.echo(f"  failures:        {manifest.get('solver_failure_rows')}")


# ── aeris airfoil dataset qc ──────────────────────────────────────────────────

@airfoil_dataset_app.command("qc")
def airfoil_dataset_qc(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the airfoil dataset root.",
    ),
) -> None:
    """Run quality checks on the raw airfoil_dataset.csv."""
    from aeris.airfoil.qc import run_airfoil_dataset_qc

    try:
        report = run_airfoil_dataset_qc(dataset_root=dataset)
    except Exception as exc:
        fail_command("Airfoil dataset qc", exc)

    typer.echo("")
    typer.echo("[AERIS 2D] Airfoil dataset QC")
    typer.echo(f"  passed:         {report.get('passed')}")
    typer.echo(f"  total_rows:     {report.get('total_rows')}")
    typer.echo(f"  converged_rows: {report.get('converged_rows')}")
    for issue in report.get("issues", []):
        typer.secho(f"  [ISSUE] {issue}", fg=typer.colors.RED)
    for warn in report.get("warnings", []):
        typer.secho(f"  [WARN]  {warn}", fg=typer.colors.YELLOW)
    if report.get("passed"):
        typer.secho("  QC passed.", fg=typer.colors.GREEN)
    else:
        typer.secho("  QC FAILED — fix issues before curating.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


# ── aeris airfoil dataset curate ─────────────────────────────────────────────

@airfoil_dataset_app.command("curate")
def airfoil_dataset_curate(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the airfoil dataset root.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Continue even if QC did not pass (records as forced).",
    ),
) -> None:
    """Curate the raw 2D dataset — reject unconverged, negative-cd, and non-finite rows."""
    from aeris.airfoil.curate import curate_airfoil_dataset

    try:
        report = curate_airfoil_dataset(dataset_root=dataset)
    except Exception as exc:
        fail_command("Airfoil dataset curate", exc)

    typer.echo("")
    typer.echo("[AERIS 2D] Airfoil dataset curation completed")
    typer.echo(f"  kept_rows:      {report.get('kept_rows')}")
    typer.echo(f"  rejected_rows:  {report.get('rejected_rows')}")
    typer.echo(f"  kept_airfoils:  {report.get('kept_airfoils')}")
    typer.echo(f"  promotion_ready:{report.get('promotion_ready')}")
    for b in report.get("promotion_blockers", []):
        typer.secho(f"  [BLOCKER] {b}", fg=typer.colors.RED)
    for name, count in (report.get("rejection_reason_counts") or {}).items():
        typer.echo(f"  rejection [{name}]: {count}")


# ── aeris airfoil dataset promote ─────────────────────────────────────────────

@airfoil_dataset_app.command("promote")
def airfoil_dataset_promote(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the airfoil dataset root.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force promotion even if blockers exist (promotion_forced=True in manifest).",
    ),
) -> None:
    """Promote the curated 2D airfoil dataset for ML use.

    Writes promotion_manifest.json. After this, use 'aeris ml train' with
    --feature-set airfoil_xfoil_v1 and --group-column airfoil_id.
    """
    from aeris.airfoil.promote import promote_airfoil_dataset

    try:
        manifest = promote_airfoil_dataset(dataset_root=dataset, force=force)
    except Exception as exc:
        fail_command("Airfoil dataset promote", exc)

    typer.echo("")
    typer.echo("[AERIS 2D] Airfoil dataset promoted")
    typer.echo(f"  dataset_root:   {dataset}")
    typer.echo(f"  promotion_forced:{manifest.get('promotion_forced')}")
    curated = (manifest.get("artifacts") or {}).get("curated_aero_dataset_csv")
    typer.echo(f"  curated_csv:    {curated}")
    typer.echo("")
    typer.secho("  Ready for ML. Example:", fg=typer.colors.GREEN)
    typer.echo(f"    aeris ml eda --dataset {dataset} \\")
    typer.echo( "      --feature-set airfoil_xfoil_v1 --targets cl,cd,cm")
    typer.echo(f"    aeris ml compare-seeds --dataset {dataset} \\")
    typer.echo( "      --feature-set airfoil_xfoil_v1 --model-types lightgbm,xgboost \\")
    typer.echo( "      --targets cl,cd,cm --seeds 101,202,303,404,505")


# ── aeris airfoil dataset inspect ─────────────────────────────────────────────

@airfoil_dataset_app.command("inspect")
def airfoil_dataset_inspect(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the airfoil dataset root.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print summary as JSON.",
    ),
) -> None:
    """Inspect an airfoil dataset root — show manifest and curation summary."""
    import json

    manifest_path = dataset / "airfoil_dataset_manifest.json"
    curation_path = dataset / "curation_report.json"
    promotion_path = dataset / "promotion_manifest.json"

    summary: dict = {}
    for path in [manifest_path, curation_path, promotion_path]:
        if path.exists():
            summary[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    if as_json:
        typer.echo(json.dumps(summary, indent=2))
        return

    typer.echo("")
    typer.echo(f"[AERIS 2D] Airfoil dataset: {dataset}")
    for stem, data in summary.items():
        typer.echo(f"\n  [{stem}]")
        for k, v in data.items():
            if not isinstance(v, dict):
                typer.echo(f"    {k}: {v}")
