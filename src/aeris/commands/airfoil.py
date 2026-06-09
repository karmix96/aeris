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
    n_airfoils: int | None = typer.Option(
        None,
        "--n-airfoils",
        min=1,
        help=(
            "Limit to N airfoils sampled from the library. "
            "Omit to run all. Use 10 for smoke, 25 for pilot, 2156 for full campaign."
        ),
    ),
    seed: int = typer.Option(
        0,
        "--seed",
        help="Random seed for --n-airfoils subsetting. Ignored when --n-airfoils is not set.",
    ),
) -> None:
    """Run XFOIL alpha sweeps across the airfoil library and write airfoil_dataset.csv.

    Use --n-airfoils to subset for fast iteration before the full campaign.
    The subset is drawn with --seed so results are reproducible.
    """
    import random as _random
    from aeris.airfoil.dataset_generate import generate_airfoil_dataset
    from aeris.airfoil.library import AirfoilLibrary

    output = dataset_root / name

    airfoil_ids: list[str] | None = None
    if n_airfoils is not None:
        try:
            lib = AirfoilLibrary(library_dir)
        except Exception as exc:
            fail_command("Airfoil library load", exc)
        all_ids = lib.all_ids()
        if n_airfoils >= len(all_ids):
            typer.echo(
                f"[AERIS 2D] --n-airfoils {n_airfoils} >= library size {len(all_ids)};"
                " running all airfoils."
            )
        else:
            rng = _random.Random(seed)
            airfoil_ids = rng.sample(all_ids, n_airfoils)
            typer.echo(
                f"[AERIS 2D] Subset: {n_airfoils}/{len(all_ids)} airfoils (seed={seed})"
            )

    try:
        manifest = generate_airfoil_dataset(
            library_dir=library_dir,
            config_path=config,
            dataset_root=output,
            name=name,
            airfoil_ids=airfoil_ids,
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

@airfoil_app.command("check-solver")
def airfoil_check_solver() -> None:
    """Check that the XFOIL binary is accessible and show its version.

    Run before any sweep to confirm the solver is installed.
    Respects the AERIS_XFOIL_BIN environment variable.
    """
    import os as _os
    import shutil as _shutil
    from aeris.aero_2d.xfoil_adapter import _find_xfoil_binary, _xfoil_version

    binary = _find_xfoil_binary()
    found_path = _shutil.which(binary)

    typer.echo("")
    typer.echo("[AERIS 2D] XFOIL solver check")
    typer.echo(f"  binary name    : {binary}")
    typer.echo(f"  AERIS_XFOIL_BIN: {_os.environ.get('AERIS_XFOIL_BIN', '(not set)')}")

    if found_path:
        typer.secho(f"  found at       : {found_path}", fg=typer.colors.GREEN)
        version = _xfoil_version(binary)
        typer.echo(f"  version        : {version}")
        typer.secho("  XFOIL is ready.", fg=typer.colors.GREEN)
    else:
        typer.secho("  NOT FOUND on PATH.", fg=typer.colors.RED)
        typer.echo("  Install:")
        typer.echo("    Ubuntu/Debian: sudo apt-get install xfoil")
        typer.echo("    macOS:         brew install xfoil")
        typer.echo("    Custom path:   export AERIS_XFOIL_BIN=/path/to/xfoil")
        raise typer.Exit(code=1)


@airfoil_app.command("library-stats")
def airfoil_library_stats(
    library_dir: Path = typer.Option(
        Path("data/airfoil_library"),
        "--library",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Ingested airfoil library directory. Default: data/airfoil_library/",
    ),
) -> None:
    """Show summary statistics for the ingested airfoil library.

    Reads airfoil_inventory.csv and prints count, family breakdown,
    t/c range, camber range, and LE radius range.
    Run 'aeris airfoil ingest' first if the library is not yet built.
    """
    import pandas as _pd

    inv = library_dir / "airfoil_inventory.csv"
    if not inv.exists():
        typer.secho(
            f"[ERROR] airfoil_inventory.csv not found at {inv}. "
            "Run 'aeris airfoil ingest --db-dir <dat_dir>' first.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    df = _pd.read_csv(inv)
    n = len(df)

    typer.echo("")
    typer.echo(f"[AERIS 2D] Airfoil library: {library_dir}")
    typer.echo(f"  total airfoils : {n}")
    if "family" in df.columns:
        typer.echo("  family breakdown:")
        for fam, cnt in df["family"].value_counts().items():
            typer.echo(f"    {fam:<20}: {cnt}")
    if "t_c" in df.columns:
        typer.echo(f"  t/c  range     : {df['t_c'].min():.3f} - {df['t_c'].max():.3f}")
    if "camber_max" in df.columns:
        typer.echo(f"  camber range   : {df['camber_max'].min():.3f} - {df['camber_max'].max():.3f}")
    if "le_radius" in df.columns:
        typer.echo(f"  LE radius range: {df['le_radius'].min():.4f} - {df['le_radius'].max():.4f}")
    typer.echo(f"  inventory csv  : {inv}")
    if n > 0:
        typer.secho(
            "  Library is ready for 'aeris airfoil dataset generate'.",
            fg=typer.colors.GREEN,
        )

