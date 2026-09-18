"""CLI for open-source wing structural automation (Gmsh + CalculiX)."""

# Typer command declarations intentionally use typer.Option/Argument defaults.
# ruff: noqa: B008

from __future__ import annotations

import dataclasses
import importlib.metadata
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Optional

import typer

from aeris.common.paths import DATA_DIR
from aeris.fea.case.loader import load_case_spec
from aeris.fea.case.runner import STAGES, CaseError, run_case
from aeris.fea.case.spec import CaseSpec
from aeris.fea.geometry import generate_aeris_stations

fea_app = typer.Typer(
    help=(
        "Open-source FEA automation for AERIS wings. Generates a closed shell "
        "wingbox, writes Gmsh/CalculiX artifacts, solves load cases, and applies gates."
    )
)
study_app = typer.Typer(help="Structural sensitivity studies (aeris.fea.study.v1).")
fea_app.add_typer(study_app, name="study")


@fea_app.callback()
def fea_callback() -> None:
    """Finite-element analysis command group."""


def _prepare_aeris_geometry(spec: CaseSpec, run_dir: Path) -> CaseSpec:
    if spec.geometry.aeris_config is None:
        return spec
    config = spec.geometry.aeris_config.expanduser().resolve()
    stations = run_dir / "inputs" / "stations.json"
    generate_aeris_stations(
        config,
        stations,
        seed=spec.geometry.seed,
        wing_index=spec.geometry.wing_index,
        design_matrix_file=spec.geometry.design_matrix_file,
        design_set=spec.geometry.design_set,
        design_index=spec.geometry.design_index,
        freeze_authority_file=spec.geometry.freeze_authority_file,
        holdout_authorized=spec.geometry.holdout_authorized,
    )
    return dataclasses.replace(
        spec,
        geometry=dataclasses.replace(spec.geometry, aeris_config=None, stations_file=stations),
    )


@fea_app.command("run")
def fea_run(
    case: Path = typer.Argument(..., help="Case YAML (schema aeris.fea.case.v1)."),
    workdir: Optional[Path] = typer.Option(
        None, "--workdir", help="Run directory (default: <data>/fea_cases/<case name>)."
    ),
    stage: list[str] = typer.Option(
        [],
        "--stage",
        help="Stages: geometry, validate, mesh, solve, physics, qualify, post (repeatable).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate and audit all inputs without running CalculiX."
    ),
) -> None:
    """Run one deterministic structural case end-to-end."""
    try:
        spec = load_case_spec(case)
        run_dir = (workdir or DATA_DIR / "fea_cases" / spec.name).expanduser().resolve()
        spec = _prepare_aeris_geometry(spec, run_dir)
        results = run_case(
            spec,
            workdir=run_dir,
            stages=tuple(stage) if stage else STAGES,
            dry_run=dry_run,
            echo=typer.echo,
        )
    except (ValueError, FileNotFoundError, CaseError) as exc:
        typer.secho(f"[fea] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    for result in results.values():
        typer.echo(f"  {result.stage:<10} {result.status}")
        for label, path in result.artifacts.items():
            typer.echo(f"    {label:<24} {path}")
    if results.get("post") and results["post"].status == "failed":
        typer.secho("[fea] analysis completed but verification gates failed", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho("[fea] done", fg=typer.colors.GREEN)


@study_app.command("run")
def fea_study_run(
    study: Path = typer.Argument(..., help="Study YAML (schema aeris.fea.study.v1)."),
    workdir: Optional[Path] = typer.Option(None, "--workdir", help="Study output directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Prepare variants without solving."),
) -> None:
    """Run independently reproducible structural sensitivity variants."""
    from aeris.fea.study.loader import load_study_spec
    from aeris.fea.study.runner import run_study

    try:
        spec = load_study_spec(study)
        run_dir = (workdir or DATA_DIR / "fea_cases" / spec.name).expanduser().resolve()
        report = run_study(
            spec,
            workdir=run_dir,
            dry_run=dry_run,
            echo=typer.echo,
            prepare=_prepare_aeris_geometry,
        )
    except (ValueError, FileNotFoundError, CaseError) as exc:
        typer.secho(f"[fea] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(report, indent=2))
    if not dry_run and report.get("status") != "pass":
        raise typer.Exit(code=1)


@fea_app.command("tools")
def fea_tools() -> None:
    """Report availability of the open-source preprocessing/solver stack."""
    oas_available = importlib.util.find_spec("openaerostruct") is not None
    tools = {
        "gmsh": shutil.which("gmsh"),
        "calculix_ccx": shutil.which("ccx"),
        "openaerostruct": (
            importlib.metadata.version("openaerostruct") if oas_available else None
        ),
    }
    typer.echo(json.dumps(tools, indent=2))
    if any(path is None for path in tools.values()):
        raise typer.Exit(code=1)
