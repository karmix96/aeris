"""
CLI commands for geometry generation.

Responsibilities:
    - Expose user-facing geometry subcommands
    - Validate basic CLI inputs
    - Delegate execution to geometry workflows

Notes:
    - This module should remain thin
    - No generator-specific geometry logic should live here
"""

from __future__ import annotations

from pathlib import Path

import typer

from aeris.geometry.visualization import visualize_geometry_from_config
from aeris.pipeline.geometry_run import run_geometry_generation

geometry_app = typer.Typer(help="Geometry-related commands.")


@geometry_app.callback()
def geometry_callback() -> None:
    """Geometry command group."""
    pass


@geometry_app.command("info")
def geometry_info() -> None:
    """Show the current status of geometry tooling and registered generators."""
    from aeris.geometry.registry import list_geometry_generators
    try:
        generators = list_geometry_generators()
        n = len(generators)
    except Exception:
        generators = []
        n = 0

    typer.echo("")
    typer.echo("[AERIS] Geometry module — ready")
    typer.echo(f"  Registered generators : {n}")
    for gid in generators:
        typer.echo(f"    · {gid}")
    typer.echo(f"  Design variables      : 17  (10 planform + 7 section)")
    typer.echo(f"  Production config     : configs/geometry/bwb_training_v1.yaml")
    typer.echo(f"  Smoke config          : configs/geometry/baseline_bwb_25.yaml")
    typer.echo("")
    typer.echo("  Commands:")
    typer.echo("    aeris geometry generate  --config <yaml>")
    typer.echo("    aeris geometry visualize --config <yaml> [--seed N] [--draw-3d|--no-draw-3d]")
    typer.echo("    aeris geometry inspect   --run-dir <run_root>")


@geometry_app.command("generate")
def geometry_generate(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the YAML geometry config file.",
    ),
) -> None:
    """
    Generate one deterministic geometry case from a YAML config.

    This is the production single-case geometry entry point.
    The command stays thin: actual orchestration belongs in the geometry
    pipeline, and geometry mathematics belongs in the selected generator.
    """
    import json as _json

    exit_code, run_root = run_geometry_generation(config)

    if run_root is not None:
        typer.echo("")
        typer.echo(f"[AERIS] Geometry generate — {'SUCCESS' if exit_code == 0 else 'FAILED'}")
        typer.echo(f"  config   : {config}")
        typer.echo(f"  run_root : {run_root}")

        mpath = run_root / "manifest.json"
        if mpath.exists():
            try:
                m      = _json.loads(mpath.read_text(encoding="utf-8"))
                geo    = m.get("geometry") or {}
                seed   = geo.get("design_sampling_seed", "—")
                cs     = geo.get("case_summary") or {}
                # Metrics live under case_summary["metrics"], not at the top level.
                cs_met = cs.get("metrics") or {}
                cs_pf  = cs.get("sampled_planform") or {}

                typer.echo(f"  seed     : {seed}")
                typer.echo(f"  semi_span: {cs_met.get('semi_span_m', '—')} m")
                typer.echo(f"  full_span: {cs_met.get('full_span_m', '—')} m")
                typer.echo(f"  area     : {cs_met.get('approx_area_m2', '—')} m²")
                typer.echo(f"  AR       : {cs_met.get('approx_aspect_ratio_planform', '—')}")
                typer.echo(f"  c1_m     : {cs_pf.get('c1_m', '—')} m")
            except Exception as _e:
                typer.echo(f"  [warn] Could not read manifest metrics: {_e}")

    raise typer.Exit(code=exit_code)


@geometry_app.command("visualize")
def geometry_visualize(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the YAML geometry config file.",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        help="Optional seed override for the one-case visualization sample.",
    ),
    save_plot: bool | None = typer.Option(
        None,
        "--save-plot/--no-save-plot",
        help="Override plot saving behavior from config.",
    ),
    build_aerosandbox: bool | None = typer.Option(
        None,
        "--build-aerosandbox/--no-build-aerosandbox",
        help="Override AeroSandbox build behavior from config.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional output directory. Defaults to data/debug/visualization_runs/<timestamp>_geometry_<name>/",
    ),
    show_plot: bool = typer.Option(
        False,
        "--show-plot/--no-show-plot",
        help="Display the saved 2D plot image if available.",
    ),
    draw_3d: bool = typer.Option(
        True,
        "--draw-3d/--no-draw-3d",
        help="Open AeroSandbox 3D viewer using airplane.draw().",
    ),
) -> None:
    """
    Generate and visualize one geometry case from config.

    This is an operator/debugging path, not the production dataset hot path.
    For large dataset generation, keep plotting disabled unless explicitly needed.
    """
    viz_result = visualize_geometry_from_config(
        config_path=config,
        seed=seed,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
        output_dir=output_dir,
        show_plot=show_plot,
        draw_3d=draw_3d,
    )
    typer.echo(f"[AERIS] Geometry visualization output: {viz_result.output_dir}")
    if viz_result.plot_path is not None:
        typer.echo(f"[AERIS] Saved plot: {viz_result.plot_path}")
    typer.echo(f"[AERIS] AeroSandbox airplane available: {viz_result.has_aerosandbox_airplane}")


@geometry_app.command("inspect")
def geometry_inspect(
    run_dir: Path = typer.Option(
        ...,
        "--run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a geometry run root (produced by 'aeris geometry generate').",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print full manifest as JSON.",
    ),
) -> None:
    """Inspect a completed geometry run — print seed, key metrics, and artifact paths.

    Reads manifest.json and artifacts/geometry/geometry_summary.json from the run root.
    Use this to verify a geometry before passing it to 'aeris aero run' or 'aeris dataset'.
    """
    import json as _json

    mpath  = run_dir / "manifest.json"
    gspath = run_dir / "artifacts" / "geometry" / "geometry_summary.json"

    if not mpath.exists():
        typer.secho(f"[ERROR] No manifest.json found in {run_dir}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    m      = _json.loads(mpath.read_text(encoding="utf-8"))
    geo    = m.get("geometry") or {}
    cs     = geo.get("case_summary") or {}
    # Metrics live under case_summary["metrics"], planform values under case_summary["sampled_planform"].
    cs_met = cs.get("metrics") or {}
    cs_pf  = cs.get("sampled_planform") or {}

    if as_json:
        summary: dict = {"manifest": m}
        if gspath.exists():
            summary["geometry_summary"] = _json.loads(gspath.read_text(encoding="utf-8"))
        typer.echo(_json.dumps(summary, indent=2))
        return

    typer.echo("")
    typer.echo(f"[AERIS] Geometry inspect: {run_dir.name}")
    typer.echo(f"  status          : {m.get('status', '—')}")
    typer.echo(f"  config          : {m.get('config_path', '—')}")
    typer.echo(f"  created_at_utc  : {m.get('created_at_utc', '—')}")
    typer.echo(f"  completed_at_utc: {m.get('completed_at_utc', '—')}")
    typer.echo("")
    typer.echo("  Geometry parameters:")
    typer.echo(f"    generator_id  : {geo.get('generator_id', '—')}")
    typer.echo(f"    seed          : {geo.get('design_sampling_seed', '—')}")
    typer.echo(f"    name          : {geo.get('name', '—')}")

    if cs_met:
        typer.echo("")
        typer.echo("  Key metrics (case_summary → metrics):")
        semi   = cs_met.get("semi_span_m")
        full   = cs_met.get("full_span_m")
        area   = cs_met.get("approx_area_m2")
        ar     = cs_met.get("approx_aspect_ratio_planform")
        ar_asb = cs_met.get("aspect_ratio_aerosandbox")
        c1     = cs_pf.get("c1_m")

        if semi  is not None: typer.echo(f"    semi_span_m        : {semi:.4f} m")
        if full  is not None: typer.echo(f"    full_span_m        : {full:.4f} m")
        if area  is not None: typer.echo(f"    area_m2            : {area:.4f} m²")
        if ar    is not None: typer.echo(f"    aspect_ratio       : {ar:.3f}  (planform)")
        if ar_asb is not None: typer.echo(f"    aspect_ratio_asb   : {ar_asb:.3f}  (AeroSandbox)")
        if c1    is not None: typer.echo(f"    c1_m               : {c1:.4f} m")
    elif cs:
        typer.secho(
            "  [WARN] case_summary present but no 'metrics' key found. "
            "Schema mismatch — inspect manifest.json directly.",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho("  [WARN] No case_summary in manifest. Run may have failed.", fg=typer.colors.YELLOW)

    typer.echo("")
    typer.echo("  Artifact paths:")
    typer.echo(f"    manifest      : {mpath}")
    if gspath.exists():
        typer.echo(f"    geo_summary   : {gspath}")
    else:
        typer.echo(f"    geo_summary   : [not found] {gspath}")

    if m.get("error"):
        typer.secho(f"  [ERROR] {m['error']}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
