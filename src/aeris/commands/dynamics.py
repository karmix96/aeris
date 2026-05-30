"""
CLI commands for AERIS dynamics-foundation workflows.

Responsibilities:
    - Build mass/CG/static-margin foundation artifacts from aero runs
    - Inspect saved dynamics artifacts
    - Run CG sweep diagnostics
    - Run first-order trim diagnostics

Notes:
    - This module must remain a thin CLI/reporting layer.
    - Mass-property parsing, static-margin logic, CG sweep logic, and trim
      calculations belong in aeris.dynamics.*.
    - Current trim is a first-order, longitudinal, control-fixed diagnostic.
      It is not a full nonlinear trim solver and does not yet solve control
      surface deflections.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from aeris.aero.io import read_aero_result
from aeris.commands._helpers import fail_command
from aeris.dynamics.analysis import build_dynamics_foundation_result
from aeris.dynamics.cg_sweep import run_cg_sweep, write_cg_sweep, write_cg_sweep_csv
from aeris.dynamics.config import load_mass_properties_config
from aeris.dynamics.io import write_dynamics_foundation_result
from aeris.dynamics.models import InertiaPlaceholders, MassProperties, TrimDefinition
from aeris.dynamics.trim import estimate_longitudinal_trim, write_trim_result


dynamics_app = typer.Typer(help="Mass / CG / dynamics-foundation utilities.")


@dynamics_app.callback()
def dynamics_callback() -> None:
    """Dynamics command group."""
    pass


def _fmt(value: Any, digits: int = 6) -> str:
    """Format a number with fixed decimal places; pass through None and non-floats."""
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _resolve_mass_inputs(
    *,
    mass_config: Path | None,
    mass_kg: float | None,
    x_cg_m: float | None = None,
    y_cg_m: float | None = None,
    z_cg_m: float | None = None,
    ixx_kg_m2: float | None = None,
    iyy_kg_m2: float | None = None,
    izz_kg_m2: float | None = None,
) -> dict[str, float | None]:
    """Merge CLI mass inputs with an optional mass-config file.

    Resolution priority for each field:
        1. Explicit CLI value (if provided)
        2. Value from --mass-config (if present)
        3. Default 0.0 for y_cg_m / z_cg_m; None otherwise.

    The 0.0 default for lateral/vertical CG keeps behavior consistent whether
    or not a mass config file is supplied.
    """
    cfg = load_mass_properties_config(mass_config) if mass_config is not None else None

    return {
        "mass_kg": mass_kg if mass_kg is not None else (cfg.mass_kg if cfg else None),
        "x_cg_m": x_cg_m if x_cg_m is not None else (cfg.x_cg_m if cfg else None),
        "y_cg_m": (
            y_cg_m
            if y_cg_m is not None
            else (cfg.y_cg_m if cfg and cfg.y_cg_m is not None else 0.0)
        ),
        "z_cg_m": (
            z_cg_m
            if z_cg_m is not None
            else (cfg.z_cg_m if cfg and cfg.z_cg_m is not None else 0.0)
        ),
        "ixx_kg_m2": ixx_kg_m2 if ixx_kg_m2 is not None else (cfg.ixx_kg_m2 if cfg else None),
        "iyy_kg_m2": iyy_kg_m2 if iyy_kg_m2 is not None else (cfg.iyy_kg_m2 if cfg else None),
        "izz_kg_m2": izz_kg_m2 if izz_kg_m2 is not None else (cfg.izz_kg_m2 if cfg else None),
    }


def _validate_cg_sweep_inputs(*, cg_min_m: float, cg_max_m: float, n: int) -> None:
    if cg_min_m > cg_max_m:
        raise typer.BadParameter("--cg-min-m must be <= --cg-max-m.")
    if n < 2:
        raise typer.BadParameter("--n must be >= 2 for a meaningful CG sweep.")


@dynamics_app.command("build")
def dynamics_build(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory"),
    mass_config: Path | None = typer.Option(None, exists=True, file_okay=True, dir_okay=False, resolve_path=True, help="Path to mass-properties YAML/JSON config"),
    mass_kg: float | None = typer.Option(None, help="Aircraft mass [kg]"),
    x_cg_m: float | None = typer.Option(None, help="CG x [m]"),
    y_cg_m: float | None = typer.Option(None, help="CG y [m]"),
    z_cg_m: float | None = typer.Option(None, help="CG z [m]"),
    ixx_kg_m2: float | None = typer.Option(None, "--ixx-kg-m2"),
    iyy_kg_m2: float | None = typer.Option(None, "--iyy-kg-m2"),
    izz_kg_m2: float | None = typer.Option(None, "--izz-kg-m2"),
    x_positive_aft: bool = typer.Option(True, "--x-positive-aft/--x-positive-forward"),
) -> None:
    """Build mass + CG + static-margin foundation artifacts from an aero run."""
    try:
        aero_result = read_aero_result(run_dir)
    except Exception as exc:
        fail_command("Dynamics build", exc)

    resolved = _resolve_mass_inputs(
        mass_config=mass_config,
        mass_kg=mass_kg,
        x_cg_m=x_cg_m,
        y_cg_m=y_cg_m,
        z_cg_m=z_cg_m,
        ixx_kg_m2=ixx_kg_m2,
        iyy_kg_m2=iyy_kg_m2,
        izz_kg_m2=izz_kg_m2,
    )

    if resolved["mass_kg"] is None or resolved["x_cg_m"] is None:
        typer.echo("[AERIS] Need mass_kg and x_cg_m, either from --mass-config or explicit CLI options.")
        raise typer.Exit(code=1)

    mass = MassProperties(
        mass_kg=resolved["mass_kg"],
        x_cg_m=resolved["x_cg_m"],
        y_cg_m=resolved["y_cg_m"],
        z_cg_m=resolved["z_cg_m"],
        inertia=InertiaPlaceholders(
            ixx_kg_m2=resolved["ixx_kg_m2"],
            iyy_kg_m2=resolved["iyy_kg_m2"],
            izz_kg_m2=resolved["izz_kg_m2"],
        ),
    )

    trim = TrimDefinition(
        enabled=False,
        notes="Schema only. No trim solver implemented.",
    )

    try:
        result = build_dynamics_foundation_result(
            aero_result=aero_result,
            mass_properties=mass,
            source_run_dir=str(run_dir),
            trim_definition=trim,
            x_positive_aft=x_positive_aft,
        )
        output_path = write_dynamics_foundation_result(result, run_dir / "dynamics")
    except Exception as exc:
        fail_command("Dynamics build", exc)

    typer.echo(f"[AERIS] Dynamics foundation written to: {output_path}")

    sm = result.stability_metrics.static_margin_percent_mac
    if sm is None:
        typer.echo("[AERIS] Static margin: unavailable")
        missing = result.state_space_preparation.missing_items
        if missing:
            typer.echo(f"[AERIS] Missing inputs: {', '.join(missing)}")
    else:
        typer.echo(f"[AERIS] Static margin = {_fmt(sm)} %MAC")


@dynamics_app.command("cg-sweep")
def dynamics_cg_sweep(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory"),
    mass_config: Path | None = typer.Option(None, exists=True, file_okay=True, dir_okay=False, resolve_path=True, help="Path to mass-properties YAML/JSON config"),
    mass_kg: float | None = typer.Option(None, help="Aircraft mass [kg]"),
    cg_min_m: float = typer.Option(..., "--cg-min-m", help="Minimum CG x [m]"),
    cg_max_m: float = typer.Option(..., "--cg-max-m", help="Maximum CG x [m]"),
    n: int = typer.Option(9, "--n", help="Number of CG points"),
    y_cg_m: float | None = typer.Option(None, help="CG y [m]"),
    z_cg_m: float | None = typer.Option(None, help="CG z [m]"),
    ixx_kg_m2: float | None = typer.Option(None, "--ixx-kg-m2"),
    iyy_kg_m2: float | None = typer.Option(None, "--iyy-kg-m2"),
    izz_kg_m2: float | None = typer.Option(None, "--izz-kg-m2"),
    x_positive_aft: bool = typer.Option(True, "--x-positive-aft/--x-positive-forward"),
) -> None:
    """Run a CG sweep and write CG-vs-static-margin diagnostic outputs."""
    _validate_cg_sweep_inputs(cg_min_m=cg_min_m, cg_max_m=cg_max_m, n=n)

    resolved = _resolve_mass_inputs(
        mass_config=mass_config,
        mass_kg=mass_kg,
        y_cg_m=y_cg_m,
        z_cg_m=z_cg_m,
        ixx_kg_m2=ixx_kg_m2,
        iyy_kg_m2=iyy_kg_m2,
        izz_kg_m2=izz_kg_m2,
    )

    if resolved["mass_kg"] is None:
        typer.echo("[AERIS] Need mass_kg, either from --mass-config or explicit CLI option.")
        raise typer.Exit(code=1)

    try:
        summary = run_cg_sweep(
            run_dir=run_dir,
            mass_kg=resolved["mass_kg"],
            cg_min_m=cg_min_m,
            cg_max_m=cg_max_m,
            n=n,
            y_cg_m=resolved["y_cg_m"],
            z_cg_m=resolved["z_cg_m"],
            ixx_kg_m2=resolved["ixx_kg_m2"],
            iyy_kg_m2=resolved["iyy_kg_m2"],
            izz_kg_m2=resolved["izz_kg_m2"],
            x_positive_aft=x_positive_aft,
        )
        output_path = write_cg_sweep(summary, run_dir / "dynamics")
        csv_path = write_cg_sweep_csv(summary, run_dir / "dynamics")
    except Exception as exc:
        fail_command("Dynamics cg-sweep", exc)

    typer.echo(f"[AERIS] CG sweep written to: {output_path}")
    typer.echo(f"[AERIS] CG sweep CSV written to: {csv_path}")
    typer.echo(
        f"[AERIS] Static-margin zero crossing estimate = "
        f"{_fmt(summary.get('static_margin_zero_crossing_estimate_m'))}"
    )
    typer.echo(f"[AERIS] Stable CG min = {_fmt(summary.get('stable_cg_min_m'))}")
    typer.echo(f"[AERIS] Stable CG max = {_fmt(summary.get('stable_cg_max_m'))}")


@dynamics_app.command("trim")
def dynamics_trim(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory"),
) -> None:
    """Run a first-order longitudinal trim diagnostic from a saved aero run."""
    try:
        aero_result = read_aero_result(run_dir)
        result = estimate_longitudinal_trim(
            aero_result=aero_result,
            run_dir=run_dir,
        )
        output_path = write_trim_result(result, run_dir / "dynamics")
    except Exception as exc:
        fail_command("Dynamics trim", exc)

    typer.echo(f"[AERIS] Trim result written to: {output_path}")

    if not result.longitudinal.valid:
        typer.echo(f"[AERIS] Trim estimate invalid: {result.longitudinal.reason}")
        raise typer.Exit(code=1)

    typer.echo(f"[AERIS] Current alpha = {_fmt(result.longitudinal.alpha_current_deg)} deg")
    typer.echo(f"[AERIS] Current Cm = {_fmt(result.longitudinal.cm_current)}")
    typer.echo(f"[AERIS] Cma = {_fmt(result.longitudinal.cma_per_rad)}")
    typer.echo(f"[AERIS] Delta alpha trim = {_fmt(result.longitudinal.delta_alpha_deg)} deg")
    typer.echo(f"[AERIS] Estimated trim alpha = {_fmt(result.longitudinal.alpha_trim_deg)} deg")


@dynamics_app.command("inspect")
def dynamics_inspect(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory"),
) -> None:
    """Inspect dynamics_foundation.json from a previously built dynamics run."""
    dyn_path = run_dir / "dynamics" / "dynamics_foundation.json"

    if not dyn_path.exists():
        typer.echo("[AERIS] No dynamics_foundation.json found.")
        raise typer.Exit(code=1)

    try:
        data = json.loads(dyn_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail_command("Dynamics inspect", exc)

    sm = data.get("stability_metrics", {})
    readiness = data.get("state_space_preparation", {})
    mp = data.get("mass_properties", {})

    typer.echo("\n=== AERIS Dynamics Inspection ===\n")

    typer.echo("Mass Properties:")
    typer.echo(f"  Mass: {_fmt(mp.get('mass_kg'))} kg")
    typer.echo(f"  CG x: {_fmt(mp.get('x_cg_m'))} m")

    typer.echo("\nStability Metrics:")
    typer.echo(f"  Neutral point: {_fmt(sm.get('x_np_m'))} m")
    typer.echo(f"  MAC: {_fmt(sm.get('mac_m'))} m")
    typer.echo(f"  Static margin: {_fmt(sm.get('static_margin_percent_mac'))} %MAC")
    typer.echo(f"  Cma: {_fmt(sm.get('cma'))}")
    typer.echo(f"  Cma consistency: {sm.get('cma_consistent_with_static_margin')}")
    typer.echo(f"  Spiral metric: {_fmt(sm.get('spiral_metric'))}")

    typer.echo("\nInterpretation:")
    typer.echo(f"  Longitudinal: {sm.get('longitudinal_interpretation')}")

    typer.echo("\nReadiness:")
    typer.echo(f"  Ready for trim: {readiness.get('ready_for_trim_solver')}")
    typer.echo(f"  Ready for eigenanalysis: {readiness.get('ready_for_eigenanalysis')}")

    missing = readiness.get("missing_items", [])
    if missing:
        typer.echo("  Missing items:")
        for item in missing:
            typer.echo(f"    - {item}")

    typer.echo("\n================================\n")


@dynamics_app.command("cg-sweep-inspect")
def dynamics_cg_sweep_inspect(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory"),
) -> None:
    """Inspect cg_sweep.json from a previously run CG sweep."""
    sweep_path = run_dir / "dynamics" / "cg_sweep.json"

    if not sweep_path.exists():
        typer.echo("[AERIS] No cg_sweep.json found.")
        raise typer.Exit(code=1)

    try:
        data = json.loads(sweep_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail_command("Dynamics cg-sweep-inspect", exc)

    cases = data.get("cases", [])
    stable_min = data.get("stable_cg_min_m")
    stable_max = data.get("stable_cg_max_m")
    zero_cross = data.get("static_margin_zero_crossing_estimate_m")

    typer.echo("\n=== AERIS CG Sweep Inspection ===\n")
    typer.echo(f"Run dir: {run_dir}")
    typer.echo(f"Mass: {_fmt(data.get('mass_kg'))} kg")
    typer.echo(f"CG range: {_fmt(data.get('cg_min_m'))} m -> {_fmt(data.get('cg_max_m'))} m")
    typer.echo(f"Number of cases: {len(cases)}")
    typer.echo(f"Stable CG min: {_fmt(stable_min)} m")
    typer.echo(f"Stable CG max: {_fmt(stable_max)} m")
    typer.echo(f"Static-margin zero crossing estimate: {_fmt(zero_cross)} m")

    if cases:
        sm_values = [c["static_margin_percent_mac"] for c in cases if c["static_margin_percent_mac"] is not None]
        if sm_values:
            typer.echo(f"Min static margin: {_fmt(min(sm_values))} %MAC")
            typer.echo(f"Max static margin: {_fmt(max(sm_values))} %MAC")

    typer.echo("\nCases:")
    for c in cases:
        typer.echo(
            f"  x_cg={_fmt(c.get('x_cg_m'))} m | "
            f"SM={_fmt(c.get('static_margin_percent_mac'))} %MAC | "
            f"{c.get('longitudinal_interpretation')}"
        )