from pathlib import Path
import json

import typer

from aeris.aero.io import read_aero_result
from aeris.dynamics.analysis import build_dynamics_foundation_result
from aeris.dynamics.cg_sweep import run_cg_sweep, write_cg_sweep, write_cg_sweep_csv
from aeris.dynamics.io import write_dynamics_foundation_result
from aeris.dynamics.models import InertiaPlaceholders, MassProperties, TrimDefinition
from aeris.dynamics.config import load_mass_properties_config
from aeris.dynamics.trim import estimate_longitudinal_trim, write_trim_result

app = typer.Typer(help="Mass / CG / dynamics-foundation utilities.")


def _fmt(value, digits=6):
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


@app.command("build")
def build_command(
    run_dir: str = typer.Option(..., help="Run directory"),
    mass_config: str | None = typer.Option(None, help="Path to mass-properties YAML/JSON config"),
    mass_kg: float | None = typer.Option(None, help="Aircraft mass [kg]"),
    x_cg_m: float | None = typer.Option(None, help="CG x [m]"),
    y_cg_m: float | None = typer.Option(None, help="CG y [m]"),
    z_cg_m: float | None = typer.Option(None, help="CG z [m]"),
    ixx_kg_m2: float | None = typer.Option(None, "--ixx-kg-m2"),
    iyy_kg_m2: float | None = typer.Option(None, "--iyy-kg-m2"),
    izz_kg_m2: float | None = typer.Option(None, "--izz-kg-m2"),
    x_positive_aft: bool = typer.Option(True, "--x-positive-aft/--x-positive-forward"),
):
    run_path = Path(run_dir)
    aero_result = read_aero_result(run_path)

    cfg = None
    if mass_config is not None:
        cfg = load_mass_properties_config(mass_config)

    resolved_mass_kg = mass_kg if mass_kg is not None else (cfg.mass_kg if cfg else None)
    resolved_x_cg_m = x_cg_m if x_cg_m is not None else (cfg.x_cg_m if cfg else None)
    resolved_y_cg_m = y_cg_m if y_cg_m is not None else (cfg.y_cg_m if cfg else 0.0)
    resolved_z_cg_m = z_cg_m if z_cg_m is not None else (cfg.z_cg_m if cfg else 0.0)
    resolved_ixx = ixx_kg_m2 if ixx_kg_m2 is not None else (cfg.ixx_kg_m2 if cfg else None)
    resolved_iyy = iyy_kg_m2 if iyy_kg_m2 is not None else (cfg.iyy_kg_m2 if cfg else None)
    resolved_izz = izz_kg_m2 if izz_kg_m2 is not None else (cfg.izz_kg_m2 if cfg else None)

    if resolved_mass_kg is None or resolved_x_cg_m is None:
        typer.echo("[AERIS] Need mass_kg and x_cg_m, either from --mass-config or explicit CLI options.")
        raise typer.Exit(code=1)

    mass = MassProperties(
        mass_kg=resolved_mass_kg,
        x_cg_m=resolved_x_cg_m,
        y_cg_m=resolved_y_cg_m,
        z_cg_m=resolved_z_cg_m,
        inertia=InertiaPlaceholders(
            ixx_kg_m2=resolved_ixx,
            iyy_kg_m2=resolved_iyy,
            izz_kg_m2=resolved_izz,
        ),
    )

    trim = TrimDefinition(
        enabled=False,
        notes="Schema only. No trim solver implemented.",
    )

    result = build_dynamics_foundation_result(
        aero_result=aero_result,
        mass_properties=mass,
        source_run_dir=str(run_path),
        trim_definition=trim,
        x_positive_aft=x_positive_aft,
    )

    output_path = write_dynamics_foundation_result(result, run_path / "dynamics")
    typer.echo(f"[AERIS] Dynamics foundation written to: {output_path}")

    sm = result.stability_metrics.static_margin_percent_mac
    if sm is None:
        typer.echo("[AERIS] Static margin: unavailable")
        missing = result.state_space_preparation.missing_items
        if missing:
            typer.echo(f"[AERIS] Missing inputs: {', '.join(missing)}")
    else:
        typer.echo(f"[AERIS] Static margin = {_fmt(sm)} %MAC")


@app.command("cg-sweep")
def cg_sweep_command(
    run_dir: str = typer.Option(..., help="Run directory"),
    mass_config: str | None = typer.Option(None, help="Path to mass-properties YAML/JSON config"),
    mass_kg: float | None = typer.Option(None, help="Aircraft mass [kg]"),
    cg_min_m: float = typer.Option(..., help="Minimum CG x [m]"),
    cg_max_m: float = typer.Option(..., help="Maximum CG x [m]"),
    n: int = typer.Option(9, help="Number of CG points"),
    y_cg_m: float | None = typer.Option(None, help="CG y [m]"),
    z_cg_m: float | None = typer.Option(None, help="CG z [m]"),
    ixx_kg_m2: float | None = typer.Option(None, "--ixx-kg-m2"),
    iyy_kg_m2: float | None = typer.Option(None, "--iyy-kg-m2"),
    izz_kg_m2: float | None = typer.Option(None, "--izz-kg-m2"),
    x_positive_aft: bool = typer.Option(True, "--x-positive-aft/--x-positive-forward"),
):
    cfg = None
    if mass_config is not None:
        cfg = load_mass_properties_config(mass_config)

    resolved_mass_kg = mass_kg if mass_kg is not None else (cfg.mass_kg if cfg else None)
    resolved_y_cg_m = y_cg_m if y_cg_m is not None else (cfg.y_cg_m if cfg else 0.0)
    resolved_z_cg_m = z_cg_m if z_cg_m is not None else (cfg.z_cg_m if cfg else 0.0)
    resolved_ixx = ixx_kg_m2 if ixx_kg_m2 is not None else (cfg.ixx_kg_m2 if cfg else None)
    resolved_iyy = iyy_kg_m2 if iyy_kg_m2 is not None else (cfg.iyy_kg_m2 if cfg else None)
    resolved_izz = izz_kg_m2 if izz_kg_m2 is not None else (cfg.izz_kg_m2 if cfg else None)

    if resolved_mass_kg is None:
        typer.echo("[AERIS] Need mass_kg, either from --mass-config or explicit CLI option.")
        raise typer.Exit(code=1)
    
    summary = run_cg_sweep(
        run_dir=run_dir,
        mass_kg=resolved_mass_kg,
        cg_min_m=cg_min_m,
        cg_max_m=cg_max_m,
        n=n,
        y_cg_m=resolved_y_cg_m,
        z_cg_m=resolved_z_cg_m,
        ixx_kg_m2=resolved_ixx,
        iyy_kg_m2=resolved_iyy,
        izz_kg_m2=resolved_izz,
        x_positive_aft=x_positive_aft,
    )

    output_path = write_cg_sweep(summary, Path(run_dir) / "dynamics")
    typer.echo(f"[AERIS] CG sweep written to: {output_path}")
    csv_path = write_cg_sweep_csv(summary, Path(run_dir) / "dynamics")
    typer.echo(f"[AERIS] CG sweep CSV written to: {csv_path}")
    typer.echo(
        f"[AERIS] Static-margin zero crossing estimate = "
        f"{_fmt(summary.get('static_margin_zero_crossing_estimate_m'))}"
    )
    typer.echo(f"[AERIS] Stable CG min = {_fmt(summary.get('stable_cg_min_m'))}")
    typer.echo(f"[AERIS] Stable CG max = {_fmt(summary.get('stable_cg_max_m'))}")

@app.command("trim")
def trim_command(
    run_dir: str = typer.Option(..., help="Run directory"),
):
    run_path = Path(run_dir)
    aero_result = read_aero_result(run_path)

    result = estimate_longitudinal_trim(
        aero_result=aero_result,
        run_dir=run_path,
    )

    output_path = write_trim_result(result, run_path / "dynamics")
    typer.echo(f"[AERIS] Trim result written to: {output_path}")

    if not result.longitudinal.valid:
        typer.echo(f"[AERIS] Trim estimate invalid: {result.longitudinal.reason}")
        raise typer.Exit(code=1)

    typer.echo(f"[AERIS] Current alpha = {_fmt(result.longitudinal.alpha_current_deg)} deg")
    typer.echo(f"[AERIS] Current Cm = {_fmt(result.longitudinal.cm_current)}")
    typer.echo(f"[AERIS] Cma = {_fmt(result.longitudinal.cma_per_rad)}")
    typer.echo(f"[AERIS] Delta alpha trim = {_fmt(result.longitudinal.delta_alpha_deg)} deg")
    typer.echo(f"[AERIS] Estimated trim alpha = {_fmt(result.longitudinal.alpha_trim_deg)} deg")

@app.command("inspect")
def inspect_command(
    run_dir: str = typer.Option(..., help="Run directory"),
):
    run_path = Path(run_dir)
    dyn_path = run_path / "dynamics" / "dynamics_foundation.json"

    if not dyn_path.exists():
        typer.echo("[AERIS] No dynamics_foundation.json found.")
        raise typer.Exit(code=1)

    data = json.loads(dyn_path.read_text(encoding="utf-8"))

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

@app.command("cg-sweep-inspect")
def cg_sweep_inspect_command(
    run_dir: str = typer.Option(..., help="Run directory"),
):
    run_path = Path(run_dir)
    sweep_path = run_path / "dynamics" / "cg_sweep.json"

    if not sweep_path.exists():
        typer.echo("[AERIS] No cg_sweep.json found.")
        raise typer.Exit(code=1)

    data = json.loads(sweep_path.read_text(encoding="utf-8"))

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

    typer.echo("\n=================================\n")

@app.command("trim-inspect")
def trim_inspect_command(
    run_dir: str = typer.Option(..., help="Run directory"),
):
    run_path = Path(run_dir)
    trim_path = run_path / "dynamics" / "trim_result.json"

    if not trim_path.exists():
        typer.echo("[AERIS] No trim_result.json found.")
        raise typer.Exit(code=1)

    data = json.loads(trim_path.read_text(encoding="utf-8"))
    longitudinal = data.get("longitudinal", {})

    typer.echo("\n=== AERIS Trim Inspection ===\n")
    typer.echo(f"Run dir: {run_dir}")
    typer.echo(f"Mode: {data.get('mode')}")
    typer.echo(f"Valid: {longitudinal.get('valid')}")
    typer.echo(f"Current alpha: {_fmt(longitudinal.get('alpha_current_deg'))} deg")
    typer.echo(f"Current Cm: {_fmt(longitudinal.get('cm_current'))}")
    typer.echo(f"Cma: {_fmt(longitudinal.get('cma_per_rad'))}")
    typer.echo(f"Delta alpha trim: {_fmt(longitudinal.get('delta_alpha_deg'))} deg")
    typer.echo(f"Estimated trim alpha: {_fmt(longitudinal.get('alpha_trim_deg'))} deg")

    reason = longitudinal.get("reason")
    if reason:
        typer.echo(f"Reason: {reason}")

    typer.echo("\n=============================\n")