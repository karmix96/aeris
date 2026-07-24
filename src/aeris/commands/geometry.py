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

from aeris.geometry.cad_export import export_cad_from_config, openvsp_doctor
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

    from importlib.util import find_spec

    pygeo_available = find_spec("pygeo") is not None
    cadquery_available = find_spec("cadquery") is not None
    gmsh_available = find_spec("gmsh") is not None
    typer.echo("  Realization backends:")
    typer.echo("    · AeroSandbox (built in)")
    typer.echo(f"    · pyGeo ({'available' if pygeo_available else 'not installed'})")
    typer.echo(
        "      physical CAD: "
        f"CadQuery={'yes' if cadquery_available else 'no'}, "
        f"Gmsh={'yes' if gmsh_available else 'no'}"
    )
    typer.echo("  Design variables      : 20  (10 planform + 7 section + 3 elevon)")
    import os as _os

    _prod = "configs/geometry/bwb_training_v1.yaml"
    _prod_flag = "" if _os.path.isfile(_prod) else "  [FILE NOT FOUND]"
    typer.echo(f"  Production config     : {_prod}{_prod_flag}")
    typer.echo("  Smoke config          : configs/geometry/baseline_bwb_25.yaml")
    typer.echo("")
    typer.echo("  Commands:")
    typer.echo(
        "    aeris geometry generate  --config <yaml> "
        "[--build-aerosandbox|--no-build-aerosandbox]"
    )
    typer.echo("    aeris geometry export-cad --config <yaml> --formats vspscript,step")
    typer.echo("    aeris geometry openvsp-doctor [--openvsp-command vsp]")
    typer.echo("    aeris geometry visualize --config <yaml> [--seed N] [--draw-3d|--no-draw-3d]")
    typer.echo("    aeris geometry inspect   --run-dir <run_root>")
    typer.echo("    aeris geometry export-deflected-cad --config <yaml> --output-dir <dir>")


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
    save_plot: bool | None = typer.Option(
        None,
        "--save-plot/--no-save-plot",
        help="Override geometry.outputs.save_plot from the YAML for this run.",
    ),
    build_aerosandbox: bool | None = typer.Option(
        None,
        "--build-aerosandbox/--no-build-aerosandbox",
        help=(
            "Override geometry.outputs.build_aerosandbox. This is useful for "
            "running a direct AeroSandbox-versus-pyGeo comparison."
        ),
    ),
    backend: str | None = typer.Option(
        None,
        "--backend",
        help="Backend override: aerosandbox | pygeo | both. Sets which tool(s) build.",
    ),
    exports: str = typer.Option(
        "",
        "--exports",
        help=(
            "Comma-separated pyGeo exports to WRITE (default: none). Choices: "
            "iges,tecplot,sections,npz,step,stl,obj,vtk. CAD-family (step/stl/obj/vtk) "
            "auto-enables physical CAD. Nothing is written unless listed here."
        ),
    ),
    physical_cad: bool | None = typer.Option(
        None,
        "--physical-cad/--no-physical-cad",
        help="Build the split-elevon physical CAD (default: off).",
    ),
    save_metrics: bool = typer.Option(
        False,
        "--save-metrics/--no-save-metrics",
        help="Save per-geometry metrics (span, area, AR, taper, MAC, volume, wetted) "
        "to geometry_metrics.json.",
    ),
    seed: int | None = typer.Option(
        None, "--seed", help="Override geometry.generator.seed for this run."
    ),
) -> None:
    """
    Generate one deterministic geometry case from a YAML config.

    This is the production single-case geometry entry point. Outputs are OPT-IN:
    nothing (CAD/STEP/STL/VTK/plots) is written unless requested via --exports /
    --physical-cad / --save-plot.
    """
    import json as _json

    if backend is not None and backend.strip().lower() not in {
        "aerosandbox", "asb", "pygeo", "both"
    }:
        typer.secho(
            f"[AERIS] Invalid --backend {backend!r}. Use aerosandbox|pygeo|both.",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    export_set = {e.strip().lower() for e in exports.split(",") if e.strip()}

    generation_kwargs = {
        "save_plot": save_plot,
        "backend": backend,
        "pygeo_exports": export_set or None,
        "physical_cad": physical_cad,
        "save_metrics": save_metrics,
        "seed": seed,
    }
    # --backend is the primary switch; only pass the legacy flag when no backend.
    if build_aerosandbox is not None and backend is None:
        generation_kwargs["build_aerosandbox"] = build_aerosandbox
    exit_code, run_root = run_geometry_generation(config, **generation_kwargs)

    if run_root is not None:
        typer.echo("")
        typer.echo(f"[AERIS] Geometry generate — {'SUCCESS' if exit_code == 0 else 'FAILED'}")
        typer.echo(f"  config   : {config}")
        typer.echo(f"  run_root : {run_root}")
        if save_plot is not None:
            typer.echo(f"  save_plot override: {save_plot}")
        if build_aerosandbox is not None:
            typer.echo(f"  AeroSandbox override: {build_aerosandbox}")

        mpath = run_root / "manifest.json"
        if mpath.exists():
            try:
                m = _json.loads(mpath.read_text(encoding="utf-8"))
                geo = m.get("geometry") or {}
                seed = geo.get("design_sampling_seed", "—")
                cs = geo.get("case_summary") or {}
                # Metrics live under case_summary["metrics"], not at the top level.
                cs_met = cs.get("metrics") or {}
                cs_pf = cs.get("sampled_planform") or {}

                typer.echo(f"  seed     : {seed}")
                typer.echo(f"  semi_span: {cs_met.get('semi_span_m', '—')} m")
                typer.echo(f"  full_span: {cs_met.get('full_span_m', '—')} m")
                typer.echo(f"  area     : {cs_met.get('approx_area_m2', '—')} m²")
                typer.echo(f"  AR       : {cs_met.get('approx_aspect_ratio_planform', '—')}")
                typer.echo(f"  c1_m     : {cs_pf.get('c1_m', '—')} m")
                backends = cs.get("realization_backends") or {}
                pygeo_summary = cs.get("pygeo") or {}
                if (backends.get("pygeo") or {}).get("enabled"):
                    typer.echo(f"  pyGeo AR : {cs_met.get('aspect_ratio_pygeo', '—')}")
                    typer.echo(f"  pyGeo QC : {pygeo_summary.get('quality_status', '—')}")
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
        help=(
            "Open the AeroSandbox viewer when available, or write a native "
            "interactive pyGeo HTML view for a pyGeo-only configuration."
        ),
    ),
) -> None:
    """
    Generate and visualize one geometry case from config.

    This is an operator/debugging path, not the production dataset hot path.
    For large dataset generation, keep plotting disabled unless explicitly needed.
    """
    try:
        viz_result = visualize_geometry_from_config(
            config_path=config,
            seed=seed,
            save_plot=save_plot,
            build_aerosandbox=build_aerosandbox,
            output_dir=output_dir,
            show_plot=show_plot,
            draw_3d=draw_3d,
        )
    except RuntimeError as exc:
        message = str(exc)
        if "AERIS_DRAW_3D_FAILED" in message:
            typer.secho("[AERIS] Interactive 3D viewer failed.", fg=typer.colors.YELLOW)
            typer.echo(
                "The geometry generation path is still valid, but AeroSandbox/PyVista/VTK "
                "could not initialize the OpenGL viewer in this Python environment."
            )
            typer.echo(message.replace("AERIS_DRAW_3D_FAILED: ", ""))
            typer.echo(
                "Recommended GUI action: use 'Save plot as PNG' or run "
                "aeris geometry visualize --no-draw-3d --save-plot."
            )
            raise typer.Exit(code=2)
        raise

    typer.echo(f"[AERIS] Geometry visualization output: {viz_result.output_dir}")
    if viz_result.plot_path is not None:
        typer.echo(f"[AERIS] Saved plot: {viz_result.plot_path}")
    typer.echo(f"[AERIS] AeroSandbox airplane available: {viz_result.has_aerosandbox_airplane}")
    has_pygeo = bool(getattr(viz_result, "has_pygeo_geometry", False))
    typer.echo(f"[AERIS] pyGeo geometry available: {has_pygeo}")
    pygeo_plot = getattr(viz_result, "pygeo_plot_path", None)
    if pygeo_plot is not None:
        typer.echo(f"[AERIS] Native pyGeo plot: {pygeo_plot}")
    interactive_path = getattr(viz_result, "interactive_3d_path", None)
    if interactive_path is not None:
        typer.echo(f"[AERIS] Interactive 3-D view: {interactive_path}")
    backend = getattr(viz_result, "visualization_backend", None)
    if backend is not None:
        typer.echo(f"[AERIS] Visualization backend: {backend}")


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

    mpath = run_dir / "manifest.json"
    gspath = run_dir / "artifacts" / "geometry" / "geometry_summary.json"

    if not mpath.exists():
        typer.secho(f"[ERROR] No manifest.json found in {run_dir}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    m = _json.loads(mpath.read_text(encoding="utf-8"))
    geo = m.get("geometry") or {}
    cs = geo.get("case_summary") or {}
    # Metrics live under case_summary["metrics"], planform values under case_summary["sampled_planform"].
    cs_met = cs.get("metrics") or {}
    cs_pf = cs.get("sampled_planform") or {}

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
        semi = cs_met.get("semi_span_m")
        full = cs_met.get("full_span_m")
        area = cs_met.get("approx_area_m2")
        ar = cs_met.get("approx_aspect_ratio_planform")
        ar_asb = cs_met.get("aspect_ratio_aerosandbox")
        ar_pygeo = cs_met.get("aspect_ratio_pygeo")
        c1 = cs_pf.get("c1_m")

        if semi is not None:
            typer.echo(f"    semi_span_m        : {semi:.4f} m")
        if full is not None:
            typer.echo(f"    full_span_m        : {full:.4f} m")
        if area is not None:
            typer.echo(f"    area_m2            : {area:.4f} m²")
        if ar is not None:
            typer.echo(f"    aspect_ratio       : {ar:.3f}  (planform)")
        if ar_asb is not None:
            typer.echo(f"    aspect_ratio_asb   : {ar_asb:.3f}  (AeroSandbox)")
        if ar_pygeo is not None:
            typer.echo(f"    aspect_ratio_pygeo : {ar_pygeo:.3f}  (realised loft)")
        pygeo_summary = cs.get("pygeo") or {}
        if pygeo_summary.get("enabled"):
            typer.echo(f"    pygeo_qc            : {pygeo_summary.get('quality_status', '—')}")
        if c1 is not None:
            typer.echo(f"    c1_m               : {c1:.4f} m")
    elif cs:
        typer.secho(
            "  [WARN] case_summary present but no 'metrics' key found. "
            "Schema mismatch — inspect manifest.json directly.",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho(
            "  [WARN] No case_summary in manifest. Run may have failed.", fg=typer.colors.YELLOW
        )

    typer.echo("")
    typer.echo("  Artifact paths:")
    typer.echo(f"    manifest      : {mpath}")
    pygeo_dir = (cs.get("artifacts") or {}).get("pygeo_dir")
    if pygeo_dir:
        typer.echo(f"    pygeo         : {pygeo_dir}")
    if gspath.exists():
        typer.echo(f"    geo_summary   : {gspath}")
    else:
        typer.echo(f"    geo_summary   : [not found] {gspath}")

    if m.get("error"):
        typer.secho(f"  [ERROR] {m['error']}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@geometry_app.command("openvsp-doctor")
def geometry_openvsp_doctor(
    openvsp_command: str = typer.Option(
        "vsp",
        "--openvsp-command",
        help="OpenVSP executable name or absolute path.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check whether OpenVSP is discoverable for optional STEP export."""
    import json as _json

    report = openvsp_doctor(openvsp_command)
    if as_json:
        typer.echo(_json.dumps(report, indent=2))
        return

    typer.echo("")
    typer.echo("[AERIS] OpenVSP doctor")
    typer.echo(f"  command      : {report['openvsp_command']}")
    typer.echo(f"  found        : {report['found']}")
    typer.echo(f"  resolved_path: {report.get('resolved_path') or '—'}")
    typer.echo(f"  source       : {report.get('source') or '—'}")
    typer.echo(
        "  note         : VSP script export does not require OpenVSP. STEP can use CadQuery or OpenVSP."
    )
    if not report["found"]:
        typer.secho(
            "  [warn] STEP export will be skipped until OpenVSP is installed or the path is supplied.",
            fg=typer.colors.YELLOW,
        )


@geometry_app.command("export-cad")
def geometry_export_cad(
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
    formats: str = typer.Option(
        "vspscript",
        "--formats",
        help="Comma-separated export formats: vspscript, step. Alias .stp is accepted.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Run/output root. CAD artifacts are written under <output-dir>/cad_exports/.",
    ),
    openvsp_command: str = typer.Option(
        "vsp",
        "--openvsp-command",
        help="OpenVSP executable/path used only when STEP export is requested.",
    ),
    timeout_sec: int = typer.Option(
        180,
        "--timeout-sec",
        min=1,
        help="Timeout for optional OpenVSP batch execution.",
    ),
    step_backend: str = typer.Option(
        "auto",
        "--step-backend",
        help="STEP backend: auto, solid, cadquery, or openvsp.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print result as JSON."),
) -> None:
    """Export CAD reconstruction artifacts for a config-defined geometry."""
    import json as _json

    result = export_cad_from_config(
        config_path=config,
        formats=formats,
        output_dir=output_dir,
        openvsp_command=openvsp_command,
        timeout_sec=timeout_sec,
        step_backend=step_backend,
    )

    if as_json:
        typer.echo(_json.dumps(result.to_dict(), indent=2))
    else:
        typer.echo("")
        label = (
            "SUCCESS"
            if result.status == "success"
            else ("PARTIAL" if result.status == "partial_success" else "FAILED")
        )
        typer.echo(f"[AERIS] Geometry CAD export — {label}")
        typer.echo(f"  status      : {result.status}")
        typer.echo(f"  config      : {config}")
        typer.echo(f"  run_root    : {result.run_root}")
        typer.echo(f"  cad_exports : {result.cad_dir}")
        typer.echo(f"  requested   : {','.join(result.formats_requested)}")
        typer.echo(
            f"  produced    : {','.join(result.formats_produced) if result.formats_produced else '—'}"
        )
        typer.echo(f"  manifest    : {result.manifest_path}")
        if result.vspscript_path is not None:
            typer.echo(f"  vspscript   : {result.vspscript_path}")
        if result.step_path is not None:
            typer.echo(f"  step        : {result.step_path}")
        if result.stdout_path is not None:
            typer.echo(f"  stdout      : {result.stdout_path}")
        if result.stderr_path is not None:
            typer.echo(f"  stderr      : {result.stderr_path}")
        for warning in result.warnings:
            typer.secho(f"  [warn] {warning}", fg=typer.colors.YELLOW)

    raise typer.Exit(code=0 if result.succeeded else 1)


@geometry_app.command("export-deflected-cad")
def geometry_export_deflected_cad(
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
    formats: str = typer.Option(
        "vspscript,step",
        "--formats",
        help="Comma-separated CAD formats: vspscript, step, or both.",
    ),
    output_dir: Path = typer.Option(
        ...,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Output run directory for physical deflected CAD export.",
    ),
    delta_e_sym_deg: float = typer.Option(
        0.0,
        "--delta-e-sym-deg",
        help="Symmetric elevon deflection in degrees. Positive = both trailing edges down.",
    ),
    delta_a_diff_deg: float = typer.Option(
        0.0,
        "--delta-a-diff-deg",
        help="Differential elevon deflection in degrees. Positive = right TE down, left TE up.",
    ),
    hinge_gap_fraction: float = typer.Option(
        0.01,
        "--hinge-gap-fraction",
        min=0.0,
        max=0.10,
        help="Chordwise hinge gap fraction between fixed wing and separate elevon. Use 0 for touching hinge, small values like 0.005 for CFD meshing clearance.",
    ),
    boundary_epsilon_fraction: float = typer.Option(
        1.0e-6,
        "--boundary-epsilon-fraction",
        min=1.0e-8,
        max=1.0e-3,
        help="Spanwise epsilon used to force the abrupt control boundary. Smaller = sharper but more CAD-fragile.",
    ),
    deflection_topology: str = typer.Option(
        "split-elevon",
        "--deflection-topology",
        help="Physical CAD topology: split-elevon for separate mechanical elevons, or unified-abrupt for legacy one-body half-wings.",
    ),
    save_preview: bool = typer.Option(
        False,
        "--save-preview/--no-save-preview",
        help="Save a PNG top-view preview generated from the exact physical deflected airplane used for export.",
    ),
    preview_png_name: str | None = typer.Option(
        None,
        "--preview-png-name",
        help="Optional PNG filename for the saved physical deflected preview. Defaults to physical_deflected_planform.png.",
    ),
    draw_3d: bool = typer.Option(
        False,
        "--draw-3d",
        help="Open AeroSandbox interactive 3D viewer for the exact physical deflected airplane. Requires a local desktop.",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        help="Optional geometry sampling seed override. Defaults to the YAML generator seed.",
    ),
) -> None:
    """Export physically deflected abrupt-boundary BWB CAD.

    Unlike ordinary AVL control metadata, this command changes the actual CAD
    geometry: each half-wing remains one continuous body, but the control-span
    aft airfoil geometry is physically deflected with abrupt spanwise boundaries.
    """
    try:
        from aeris.generators.bwb_segmented_v1.deflected_cad import (
            export_bwb_physical_deflected_cad,
        )

        manifest = export_bwb_physical_deflected_cad(
            config_path=config,
            output_dir=output_dir,
            formats=formats,
            delta_e_sym_deg=delta_e_sym_deg,
            delta_a_diff_deg=delta_a_diff_deg,
            hinge_gap_fraction=hinge_gap_fraction,
            boundary_epsilon_fraction=boundary_epsilon_fraction,
            deflection_topology=deflection_topology,
            save_preview=save_preview,
            preview_png_name=preview_png_name,
            draw_3d=draw_3d,
            seed=seed,
        )
    except Exception as exc:
        typer.secho(
            f"[AERIS] Geometry physical deflected CAD export — FAILED: {exc}", fg=typer.colors.RED
        )
        raise typer.Exit(code=1)

    status = str(manifest.get("status", "unknown"))
    label = "SUCCESS" if status == "success" else status.upper()
    typer.echo(f"[AERIS] Geometry physical deflected CAD export — {label}")
    typer.echo(f"  status      : {status}")
    typer.echo(f"  config      : {manifest.get('config_path')}")
    typer.echo(f"  run_root    : {manifest.get('run_root')}")
    typer.echo(f"  cad_exports : {manifest.get('cad_dir')}")
    typer.echo(f"  surface_model: {manifest.get('surface_model')}")
    typer.echo(f"  body_model  : {manifest.get('body_model')}")
    typer.echo(f"  topology   : {manifest.get('deflection_topology')}")
    typer.echo(f"  requested   : {','.join(manifest.get('formats_requested', []))}")
    typer.echo(f"  produced    : {','.join(manifest.get('formats_produced', []))}")

    controls = manifest.get("physical_controls", {}) or {}
    typer.echo("  physical deflection:")
    typer.echo(f"    delta_e_sym_deg : {controls.get('delta_e_sym_deg')}")
    typer.echo(f"    delta_a_diff_deg: {controls.get('delta_a_diff_deg')}")
    typer.echo(f"    right_deg       : {controls.get('right_deflection_deg')}")
    typer.echo(f"    left_deg        : {controls.get('left_deflection_deg')}")
    typer.echo("    mix             : right = delta_e_sym_deg + delta_a_diff_deg")
    typer.echo("                      left  = delta_e_sym_deg - delta_a_diff_deg")
    if controls.get("deflection_warning"):
        typer.echo(f"    warning         : {controls.get('deflection_warning')}")

    artifacts = manifest.get("artifacts", {}) or {}
    for key in [
        "vspscript",
        "step",
        "physical_deflected_planform_png",
        "physical_control_deflection",
        "stdout",
        "stderr",
    ]:
        val = artifacts.get(key)
        if val:
            typer.echo(f"  {key:12s}: {val}")

    if status == "failed":
        raise typer.Exit(code=1)


@geometry_app.command("export-cad-from-run")
def export_cad_from_run(
    run_dir: str = typer.Argument(..., help="Geometry run directory."),
    formats: str = typer.Option("vspscript,step", help="vspscript, step, or both."),
    output_dir: Path | None = typer.Option(
        None, help="Output dir (default: <run_dir>/cad_exports_explicit/)."
    ),
    step_backend: str = typer.Option("auto", help="auto | solid | cadquery | openvsp."),
    openvsp_command: str = typer.Option("vsp"),
    timeout_sec: int = typer.Option(180, min=1),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Export CAD for a specific geometry from an existing DoE run directory.

    Unlike export-cad, uses exact DVs stored in geometry_summary.json (no re-sampling).
    Ideal for selecting N from 10,000 DoE runs for CFD meshing.
    """
    from aeris.geometry.cad_export import export_cad_from_sample, load_sample_from_geometry_run

    try:
        sample, config, run_path = load_sample_from_geometry_run(run_dir)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(1)
    resolved_out = output_dir or (run_path / "cad_exports_explicit")
    if not json_output:
        typer.echo(f"  Run: {run_path.name}\n  Formats: {formats}\n  Output: {resolved_out}")
    result = export_cad_from_sample(
        sample=sample,
        config=config,
        output_dir=resolved_out,
        formats=formats,
        step_backend=step_backend,
        openvsp_command=openvsp_command,
        timeout_sec=timeout_sec,
    )
    if json_output:
        import json as _j

        typer.echo(
            _j.dumps(
                {
                    "status": result.status,
                    "formats_produced": list(result.formats_produced),
                    "cad_dir": str(result.cad_dir),
                },
                indent=2,
            )
        )
    else:
        typer.echo(
            f"  Status: {result.status}  Produced: {', '.join(result.formats_produced) or '—'}"
        )
    if result.status not in ("success", "partial_success"):
        raise typer.Exit(1)
