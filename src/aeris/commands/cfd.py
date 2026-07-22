"""
CLI commands for the AERIS CFD suite (aeris.cfd).

Provides:
    aeris cfd run CASE.yaml   — execute a case spec (per-stage or end-to-end)
    aeris cfd presets list    — list validated presets (data-only recipes)
    aeris cfd presets show    — show one preset with values and citation

Architecture:
    - Thin CLI layer; suite logic lives in aeris.cfd.*.
    - The aeris.cfd core is standalone (no geometry imports); this layer is
      where AERIS geometry configs are resolved into surface-mesh directories
      before handing off to the core case runner.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Optional

import typer

from aeris.cfd.case.loader import load_case_spec
from aeris.cfd.case.runner import CaseError, run_case
from aeris.cfd.case.spec import CaseSpec
from aeris.cfd.presets.registry import get_preset, list_presets
from aeris.common.paths import DATA_DIR

cfd_app = typer.Typer(
    help=(
        "AERIS CFD suite: pre-process, mesh, solve, post-process.\n\n"
        "Cases are single YAML files (schema aeris.cfd.case.v1) runnable "
        "per-stage or end-to-end; every run records fully resolved options "
        "with per-key provenance."
    )
)
presets_app = typer.Typer(help="Validated, data-only presets (with citations).")
study_app = typer.Typer(help="Parametric sensitivity studies (schema aeris.cfd.study.v1).")
campaign_app = typer.Typer(help="Multi-geometry DOE campaigns (robustness, not single-case V&V).")
cfd_app.add_typer(presets_app, name="presets")
cfd_app.add_typer(study_app, name="study")
cfd_app.add_typer(campaign_app, name="campaign")


@cfd_app.callback()
def cfd_callback() -> None:
    """CFD suite command group."""


# Surface-spec key -> export_surface_mesh kwarg
_SURFACE_KWARG_MAP = {
    "points_per_side": "points_per_block_side",
    "spanwise_panels": "spanwise_panels_per_section",
    "tip_radial_points": "tip_radial_points",
    "tip_inner_scale": "tip_inner_scale",
    "split_x_fore": "split_x_fore",
    "oml_topology": "oml_topology",
    "cap_width_frac": "cap_width_frac",
    "cap_wrap_points": "cap_wrap_points",
    "cap_wrap_x": "cap_wrap_x",
}


def _resolve_surface_params(spec: CaseSpec) -> dict[str, object]:
    """Preset surface values, then case overrides (overrides win)."""
    params: dict[str, object] = {}
    surface = spec.surface_mesh
    if surface is not None and surface.preset is not None:
        params.update(get_preset(surface.preset).surface)
    if surface is not None:
        unknown = set(surface.overrides) - set(_SURFACE_KWARG_MAP)
        if unknown:
            raise CaseError(
                f"case.surface_mesh.overrides: unknown keys {sorted(unknown)}. "
                f"Known: {sorted(_SURFACE_KWARG_MAP)}"
            )
        params.update(surface.overrides)
    return params


def _build_surface_from_aeris(spec: CaseSpec, workdir: Path, echo) -> Path:
    """AERIS mode: geometry YAML → wing → structured surface in workdir/surface."""
    from aeris.cfd.meshing.registry import get_topology
    from aeris.commands.mesh import _build_wing

    params = _resolve_surface_params(spec)
    oml = str(params.pop("oml_topology", "cap4"))
    topology_id = (
        spec.surface_mesh.topology
        if spec.surface_mesh is not None and spec.surface_mesh.topology
        else f"wing_{oml}_v1"
    )
    generator = get_topology(topology_id)

    config_path = Path(spec.geometry.aeris_config).expanduser().resolve()
    if not config_path.is_file():
        raise CaseError(f"case.geometry.aeris_config not found: {config_path}")

    echo(f"[cfd] geometry: {config_path.name} (wing {spec.geometry.wing_index})")
    wing, _airplane, generator_id = _build_wing(
        config_path,
        wing_index=spec.geometry.wing_index,
        geometry_output_dir=workdir / "geometry",
        seed_override=spec.geometry.seed,
        save_plot=False,
    )
    echo(f"[cfd] surface: topology={topology_id} params={params}")
    surface_dir = workdir / "surface"
    generator.generate(wing, surface_dir, params)
    echo(f"[cfd] surface mesh written: {surface_dir} (generator {generator_id})")
    return surface_dir


@cfd_app.command("run")
def cfd_run(
    case: Path = typer.Argument(..., help="Case YAML (schema aeris.cfd.case.v1)."),
    workdir: Optional[Path] = typer.Option(
        None,
        "--workdir",
        help="Run directory (default: <data>/cfd_cases/<case name>).",
    ),
    stage: list[str] = typer.Option(
        ["surface", "volume"],
        "--stage",
        help="Stages to run (repeatable): surface, volume, solve, post.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Prepare everything (resolved options JSON, provenance manifest, "
            "runner scripts) without executing external tools."
        ),
    ),
) -> None:
    """Run a CFD case spec: stage inputs, mesh, (later) solve and post."""
    case_path = Path(case).expanduser().resolve()
    try:
        spec = load_case_spec(case_path)
    except (ValueError, FileNotFoundError) as exc:
        typer.secho(f"[cfd] invalid case: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    run_dir = (workdir or (DATA_DIR / "cfd_cases" / spec.name)).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    typer.echo(f"[cfd] case    : {spec.name}")
    typer.echo(f"[cfd] workdir : {run_dir}")
    typer.echo(f"[cfd] stages  : {list(stage)}{'  (dry run)' if dry_run else ''}")

    try:
        if spec.geometry.aeris_config is not None and "surface" in stage:
            surface_dir = _build_surface_from_aeris(spec, run_dir, typer.echo)
            spec = dataclasses.replace(
                spec,
                geometry=dataclasses.replace(spec.geometry, surface_dir=surface_dir),
            )
        results = run_case(
            spec,
            workdir=run_dir,
            stages=tuple(stage),
            dry_run=dry_run,
            echo=typer.echo,
        )
    except CaseError as exc:
        typer.secho(f"[cfd] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.secho(f"[cfd] failed: {type(exc).__name__}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    for result in results.values():
        typer.echo(f"  {result.stage:<8} {result.status}")
        for label, path in result.artifacts.items():
            typer.echo(f"    {label:<18} {path}")
    typer.secho("[cfd] done", fg=typer.colors.GREEN)


@cfd_app.command("solve")
def cfd_solve(
    grid: Path = typer.Option(..., "--grid", help="Volume mesh CGNS to solve on."),
    output_dir: Path = typer.Option(..., "--output-dir", "-o", help="Solve output directory."),
    area_ref: float = typer.Option(
        ..., "--area-ref", help="HALF-model reference area [m^2] (symmetry-plane mesh)."
    ),
    chord_ref: float = typer.Option(..., "--chord-ref", help="Mean aerodynamic chord [m]."),
    alpha: float = typer.Option(2.0, "--alpha", help="Angle of attack [deg]."),
    mach: float = typer.Option(0.2, "--mach", help="Freestream Mach number."),
    reynolds: float = typer.Option(1.0e6, "--reynolds", help="Reynolds number (on chord_ref)."),
    temperature: float = typer.Option(288.15, "--temperature", help="Static temperature [K]."),
    solver: str = typer.Option("adflow", "--solver", help="Solver adapter id."),
    solver_preset: Optional[str] = typer.Option(
        None,
        "--solver-preset",
        help=(
            "Solver-strategy preset (see 'aeris cfd presets list --kind "
            "solver_strategy'). Default: the adapter's validated strategy "
            "(adflow: rans_ank_nk_v1, su2: su2_rans_sa_v1)."
        ),
    ),
    mpi_np: int = typer.Option(8, "--np", help="MPI ranks."),
    solver_option: list[str] = typer.Option(
        [],
        "--solver-option",
        help=(
            "Raw native solver option KEY=VALUE, repeatable — full authority "
            "pass-through for ANY solver option (e.g. --solver-option "
            "turbulenceModel='SA' --solver-option nCycles=40000).  Values are "
            "parsed as YAML scalars; overrides are provenance-recorded."
        ),
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Prepare runner + options JSONs without executing."
    ),
) -> None:
    """Single-point RANS solve on an existing volume mesh (replaces adflow_smoke.py)."""
    import yaml as _yaml

    from aeris.cfd.case.spec import FlowConditions, SolveSpec
    from aeris.cfd.solvers.base import get_solver_adapter

    raw_options: dict[str, object] = {}
    for item in solver_option:
        key, sep, value = item.partition("=")
        if not sep or not key:
            typer.secho(
                f"[cfd] --solver-option must be KEY=VALUE, got {item!r}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        raw_options[key] = _yaml.safe_load(value)

    spec = SolveSpec(
        solver=solver,
        preset=solver_preset,
        flow=FlowConditions(alpha=alpha, mach=mach, reynolds=reynolds, temperature=temperature),
        area_ref=area_ref,
        chord_ref=chord_ref,
        mpi_np=mpi_np,
        raw_options=raw_options,
    )
    try:
        adapter = get_solver_adapter(solver)
        prepared = adapter.prepare(spec, Path(grid), Path(output_dir))
    except (ValueError, FileNotFoundError) as exc:
        typer.secho(f"[cfd] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"[cfd] solver  : {solver} (preset {solver_preset or 'adapter default'})")
    typer.echo(f"[cfd] command : {' '.join(prepared.command)}")
    if dry_run:
        for label, path in prepared.artifacts.items():
            typer.echo(f"  {label:<18} {path}")
        typer.secho("[cfd] dry run — nothing executed", fg=typer.colors.YELLOW)
        return

    returncode = adapter.run(prepared, stream=typer.echo)
    report = adapter.parse(prepared.workdir)
    typer.echo("")
    typer.echo(f"[cfd] status  : {report.status}  (exit {returncode})")
    for key, value in report.forces.items():
        typer.echo(f"  {key:<6} {value:.6f}")
    final_resrho = report.convergence.get("final_resrho")
    if final_resrho is not None:
        typer.echo(f"  final Res_rho: {final_resrho:.3e}")
    typer.echo(f"[cfd] report  : {prepared.workdir / 'solve_report.json'}")
    if report.status != "converged" or returncode != 0:
        raise typer.Exit(code=1)


@cfd_app.command("summary")
def cfd_summary(
    reports: list[Path] = typer.Argument(
        ..., help="solve_report.json files (or their directories) to compare."
    ),
) -> None:
    """Cross-solver / cross-fidelity comparison table from solve reports."""
    from aeris.cfd.post.reports import solve_summary

    paths = [path / "solve_report.json" if path.is_dir() else path for path in reports]
    try:
        summary = solve_summary(paths)
    except (ValueError, FileNotFoundError) as exc:
        typer.secho(f"[cfd] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    for row in summary["rows"]:
        forces = "  ".join(f"{k}={v:.6f}" for k, v in sorted(row["forces"].items()))
        typer.echo(
            f"{row['label']:<24} {row['solver']:<8} {row['status']:<12} {forces}  "
            f"(final res {row['final_resrho']})"
        )


@cfd_app.command("gci")
def cfd_gci(
    fine: Path = typer.Argument(..., help="Fine-grid solve_report.json (or its directory)."),
    medium: Path = typer.Argument(..., help="Medium-grid report."),
    coarse: Path = typer.Argument(..., help="Coarse-grid report."),
    quantity: str = typer.Option("cl", "--quantity", help="Force coefficient to study."),
    refinement_ratio: float = typer.Option(
        1.4,
        "--ratio",
        help="Grid refinement ratio (the cap4 family and 2D ladder use r ~ 1.4).",
    ),
) -> None:
    """Grid-convergence index (Celik et al. 2008 / ASME V&V 20 procedure)."""
    from aeris.cfd.post.reports import gci_study

    paths = [
        path / "solve_report.json" if path.is_dir() else path for path in (fine, medium, coarse)
    ]
    try:
        study = gci_study(paths, quantity=quantity, refinement_ratio=refinement_ratio)
    except (ValueError, FileNotFoundError) as exc:
        typer.secho(f"[cfd] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(study, indent=2))


@cfd_app.command("tolerance-sensitivity")
def cfd_tolerance_sensitivity(
    log: Path = typer.Argument(..., help="ADflow run log (e.g. solve/adflow_run.log)."),
    orders: list[float] = typer.Option(
        [3.0, 4.0, 5.0, 5.5, 6.0],
        "--orders",
        help="Residual-drop targets (log10 orders), repeatable.",
    ),
) -> None:
    """Post-hoc force-vs-stopping-criterion sensitivity from an existing log (no rerun)."""
    from aeris.cfd.post.reports import iterative_tolerance_sensitivity

    result = iterative_tolerance_sensitivity(log, targets_orders_dropped=tuple(orders))
    typer.echo(json.dumps(result, indent=2))


@cfd_app.command("topologies")
def cfd_topologies() -> None:
    """List registered mesh topologies (core + AERIS plugins)."""
    from aeris.cfd.meshing.registry import list_topologies

    topologies = list_topologies()
    if not topologies:
        typer.echo("(no topologies registered)")
        return
    width = max(len(t.TOPOLOGY_ID) for t in topologies)
    for topology in topologies:
        typer.echo(
            f"{topology.TOPOLOGY_ID:<{width}}  [{topology.DIMENSION}D]  " f"{topology.DESCRIPTION}"
        )


@study_app.command("run")
def study_run(
    study: Path = typer.Argument(..., help="Study YAML (schema aeris.cfd.study.v1)."),
    workdir: Optional[Path] = typer.Option(
        None,
        "--workdir",
        help="Study run directory (default: <data>/cfd_cases/<study name>).",
    ),
    stage: list[str] = typer.Option(
        [],
        "--stage",
        help="Stages to run per variant (repeatable). Default: the study's own 'stages'.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Prepare every variant without executing external tools."
    ),
) -> None:
    """Run every variant of a sensitivity study; write study_report.json with deltas."""
    from aeris.cfd.study.loader import load_study_spec
    from aeris.cfd.study.runner import run_study

    study_path = Path(study).expanduser().resolve()
    try:
        spec = load_study_spec(study_path)
    except (ValueError, FileNotFoundError) as exc:
        typer.secho(f"[cfd] invalid study: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    if stage:
        import dataclasses

        spec = dataclasses.replace(spec, stages=tuple(stage))

    run_dir = (workdir or (DATA_DIR / "cfd_cases" / spec.name)).expanduser().resolve()
    typer.echo(f"[cfd] study   : {spec.name}  ({len(spec.variants)} variants)")
    typer.echo(f"[cfd] workdir : {run_dir}")
    typer.echo(f"[cfd] stages  : {list(spec.stages)}{'  (dry run)' if dry_run else ''}")

    from aeris.cfd.status import record_status

    job_id = f"study_{spec.name}"
    if not dry_run:
        record_status(
            job_id,
            kind="study",
            status="running",
            progress=f"0/{len(spec.variants)} variants",
            workdir=run_dir,
        )

    report = run_study(spec, workdir=run_dir, dry_run=dry_run, echo=typer.echo)

    if not dry_run:
        n_ok = sum(1 for row in report["variants"] if row["status"] == "ok")
        record_status(
            job_id,
            kind="study",
            status="done",
            progress=f"{n_ok}/{len(report['variants'])} ok",
            detail=f"baseline={report.get('baseline')}",
            workdir=run_dir,
        )

    typer.echo("")
    for row in report["variants"]:
        forces = "  ".join(f"{k}={v:.6f}" for k, v in sorted(row["forces"].items()))
        typer.echo(f"  {row['name']:<24} {row['status']:<10} {forces}")
    deltas = report.get("deltas_vs_baseline") or {}
    if deltas:
        typer.echo("")
        typer.echo(f"deltas vs baseline '{report['baseline']}':")
        for name, per_qty in deltas.items():
            parts = "  ".join(
                f"{qty}: {d['absolute']:+.6f} ({d['relative_percent']:+.3f}%)"
                for qty, d in per_qty.items()
            )
            typer.echo(f"  {name:<24} {parts}")
    typer.secho("[cfd] study done", fg=typer.colors.GREEN)


def _record_volume_audit(row: dict, volume_report: dict) -> None:
    """Copy the geometric volume audit onto a campaign row.

    Flattens the fields a campaign is analysed by — how many cells inverted,
    whether the cluster sits on a spanwise extremity, where on the wall — so
    a sweep report can be grouped by failure mechanism without reopening
    every per-sample volume_report.json.
    """
    # Skew is tracked separately from inversion: a mesh can have every cell
    # positive-volume and still be badly skewed (seed 6 of the n=10 campaign
    # marched 30 layers at negative scaled quality yet scored a clean "ok",
    # because quality_warning never reached the campaign row).
    march = volume_report.get("march_metrics") or {}
    row["low_quality_layers"] = march.get("low_quality_layers")
    row["min_march_quality"] = march.get("min_quality")

    audit = volume_report.get("volume_audit")
    if not audit:
        return
    row["volume_audit_classification"] = audit.get("classification")
    row["inverted_cells"] = audit.get("inverted_cells")
    row["inverted_fraction"] = audit.get("inverted_fraction")
    clusters = audit.get("clusters") or []
    if clusters:
        primary = max(clusters, key=lambda c: c.get("inverted_cells", 0))
        row["inverted_primary_block"] = primary.get("block")
        row["inverted_on_spanwise_edge"] = primary.get("on_spanwise_edge")
        row["inverted_wall_adjacent"] = primary.get("wall_adjacent")
        row["inverted_wall_bbox"] = primary.get("wall_bbox")
        row["inverted_i_range"] = primary.get("i_range")
        row["inverted_layer_range"] = [primary.get("first_layer"), primary.get("last_layer")]
    summary = audit.get("classification", "")
    if audit.get("inverted_cells"):
        summary += f" ({audit['inverted_cells']} cells)"
    row["volume_audit_summary"] = summary


@campaign_app.command("mesh-robustness")
def campaign_mesh_robustness(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        help="AERIS geometry YAML with a sampler (e.g. configs/geometry/bwb_explore_wide.yaml).",
    ),
    n: int = typer.Option(100, "--n", min=1, help="Number of geometries to sample."),
    seed_start: int = typer.Option(
        0, "--seed-start", help="First seed; samples use seed_start..seed_start+n-1."
    ),
    preset: str = typer.Option(
        "smoke",
        "--preset",
        help="Mesh-family preset for surface+volume (see 'aeris cfd presets list').",
    ),
    topology: Optional[str] = typer.Option(
        None,
        "--topology",
        help=(
            "Override the preset's surface topology: mid4, split8, or cap4 "
            "(default: whatever the preset specifies, normally cap4). mid4/"
            "split8 use a different tip treatment than cap4, so cap-specific "
            "surface params (cap_width_frac/cap_wrap_points/cap_wrap_x) are "
            "dropped automatically when overriding away from cap4."
        ),
    ),
    volume_level: Optional[str] = typer.Option(
        None,
        "--volume-level",
        help=(
            "Override the preset's pyHyp grid level (see 'aeris cfd presets "
            "list'/mesh/pyhyp_options.py GRID_LEVELS). mid4/split8 require "
            "coarsen=4 to march at all -- use a legacy level (L1-L4) with "
            "--topology mid4/split8, not the cap4-family smoke/fine/"
            "production levels (coarsen=1)."
        ),
    ),
    workdir: Path = typer.Option(..., "--workdir", "-o", help="Campaign output directory."),
    keep_success_examples: int = typer.Option(
        3,
        "--keep-success-examples",
        help="Keep full mesh artifacts (CGNS/VTK) for this many successful samples, for ParaView.",
    ),
    skip_volume: bool = typer.Option(
        False,
        "--skip-volume",
        help=(
            "Stop after the surface mesh. Seconds per geometry instead of "
            "minutes, so a design space can be screened -- or a set of "
            "surfaces staged for 'campaign remarch' -- without paying for "
            "marches."
        ),
    ),
) -> None:
    """Mesh-only (no solve) DOE robustness campaign: sample N geometries, mesh each

    with a fixed policy, machine-classify every failure. This is the
    DSE_READINESS.md C1 acceptance criterion (>=98% unattended success over
    >=100 geometries, zero human intervention, every failure machine-tagged)
    -- deliberately mesh-only so the campaign cost stays bounded regardless
    of solve time; a solved subset is a separate, much smaller follow-up.
    """
    import time as _time

    from aeris.cfd.case.runner import _stage_volume  # local import: geometry-adjacent CLI layer
    from aeris.cfd.case.spec import GeometryInput, SurfaceMeshSpec, VolumeMeshSpec
    from aeris.cfd.meshing.registry import get_topology
    from aeris.cfd.status import record_status
    from aeris.commands.mesh import _build_wing
    from aeris.mesh.surface import MeshBuildError

    config_path = Path(config).expanduser().resolve()
    workdir = workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    job_id = f"mesh_robustness_{workdir.name}"
    record_status(
        job_id,
        kind="campaign:mesh-robustness",
        status="running",
        progress=f"0/{n} seeds",
        workdir=workdir,
    )

    surface_spec = SurfaceMeshSpec(preset=preset)
    volume_spec = VolumeMeshSpec(preset=preset, level=volume_level)
    params = _resolve_surface_params(
        CaseSpec(name="_probe", geometry=GeometryInput(seed=0), surface_mesh=surface_spec)
    )
    oml = str(topology) if topology else str(params.pop("oml_topology", "cap4"))
    params.pop("oml_topology", None)
    topology_id = f"wing_{oml}_v1"
    if oml != "cap4":
        for cap_key in ("cap_width_frac", "cap_wrap_points", "cap_wrap_x"):
            params.pop(cap_key, None)
    generator = get_topology(topology_id)

    rows: list[dict[str, object]] = []
    n_ok = 0
    typer.echo(f"[campaign] config   : {config_path}")
    level_label = volume_level or "(preset default)"
    typer.echo(
        f"[campaign] topology : {topology_id}  preset: {preset}  volume_level: {level_label}"
    )
    typer.echo(f"[campaign] samples  : seeds {seed_start}..{seed_start + n - 1}")
    typer.echo(f"[campaign] workdir  : {workdir}")

    for i in range(n):
        seed = seed_start + i
        sample_dir = workdir / f"sample_{seed:05d}"
        row: dict[str, object] = {"seed": seed, "status": None, "error": None, "timings_sec": {}}

        if i % 5 == 0 or i == n - 1:
            record_status(
                job_id,
                kind="campaign:mesh-robustness",
                status="running",
                progress=f"{i}/{n} seeds  ({n_ok} ok so far)",
                workdir=workdir,
            )

        t0 = _time.perf_counter()
        try:
            wing, _airplane, _generator_id = _build_wing(
                config_path,
                wing_index=0,
                geometry_output_dir=sample_dir / "geometry",
                seed_override=seed,
                save_plot=False,
            )
        except Exception as exc:  # noqa: BLE001 - campaign must classify every failure, not crash
            row["status"] = "geometry_failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["timings_sec"]["geometry"] = _time.perf_counter() - t0
            rows.append(row)
            typer.echo(f"  seed {seed:5d}  geometry_failed")
            continue
        row["timings_sec"]["geometry"] = _time.perf_counter() - t0

        t0 = _time.perf_counter()
        surface_dir = sample_dir / "surface"
        try:
            surface_report = generator.generate(wing, surface_dir, params)
        except (ValueError, MeshBuildError, RuntimeError) as exc:
            row["status"] = "surface_mesh_failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["timings_sec"]["surface"] = _time.perf_counter() - t0
            rows.append(row)
            typer.echo(f"  seed {seed:5d}  surface_mesh_failed")
            continue
        row["timings_sec"]["surface"] = _time.perf_counter() - t0
        row["block_count"] = surface_report.get("block_count")
        # NOTE: surface_report's top-level minimum_scaled_jacobian/
        # maximum_adjacent_normal_angle_deg/minimum_te_thickness are the QC
        # GATE THRESHOLDS used to accept/reject the mesh (an input echo, by
        # design, for provenance) -- not the measured values, and they are
        # therefore identical across every sample regardless of geometry.
        # The real per-mesh measurements are aggregated under "global".
        # There is no measured-TE-thickness counterpart anywhere in the
        # report (only pass/fail against the gate), so it isn't recorded here.
        surface_global = surface_report.get("global", {})
        row["measured_min_scaled_jacobian"] = surface_global.get("min_scaled_corner_jacobian")
        row["measured_max_adjacent_normal_angle_deg"] = surface_global.get(
            "max_adjacent_normal_angle_deg"
        )

        if skip_volume:
            row["status"] = "surface_ok"
            n_ok += 1
            rows.append(row)
            typer.echo(f"  seed {seed:5d}  surface_ok (volume skipped)")
            continue

        t0 = _time.perf_counter()
        try:
            _stage_volume(
                CaseSpec(
                    name=f"sample_{seed}",
                    geometry=GeometryInput(surface_dir=surface_dir),
                    volume_mesh=volume_spec,
                ),
                sample_dir,
                dry_run=False,
            )
        except Exception as exc:  # noqa: BLE001 - includes invalid-march RuntimeError from pyHyp QC
            row["timings_sec"]["volume"] = _time.perf_counter() - t0
            report_path = surface_dir / "volume_report.json"
            march_status = None
            volume_report = {}
            if report_path.is_file():
                volume_report = json.loads(report_path.read_text(encoding="utf-8"))
                march_status = volume_report.get("status")
            row["status"] = (
                "volume_mesh_invalid_march" if march_status == "invalid" else "volume_mesh_failed"
            )
            # The audit says how bad and where; without it a failure is just
            # "the march went negative somewhere", which cannot be acted on.
            _record_volume_audit(row, volume_report)
            row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            typer.echo(f"  seed {seed:5d}  {row['status']}  {row.get('volume_audit_summary', '')}")
            continue
        row["timings_sec"]["volume"] = _time.perf_counter() - t0
        volume_report = json.loads((surface_dir / "volume_report.json").read_text(encoding="utf-8"))
        row["march_metrics"] = volume_report.get("march_metrics", {})
        _record_volume_audit(row, volume_report)
        row["status"] = "ok"
        n_ok += 1
        typer.echo(f"  seed {seed:5d}  ok")

        if n_ok > keep_success_examples:
            for name in ("wing_vol_smoke.cgns", "wing_vol_fine.cgns", "wing_vol_production.cgns"):
                (surface_dir / name).unlink(missing_ok=True)
            (surface_dir / "surface.vtk").unlink(missing_ok=True)
            (surface_dir / "surface_blocks.npz").unlink(missing_ok=True)

        rows.append(row)

    n_total = len(rows)
    failure_counts: dict[str, int] = {}
    # Second, finer tally: the goal is every failure machine-classified, so
    # group by the audited mechanism rather than only the coarse status.
    failure_mechanisms: dict[str, int] = {}
    for row in rows:
        # "surface_ok" is the --skip-volume success status, not a failure.
        if row["status"] not in ("ok", "surface_ok"):
            failure_counts[row["status"]] = failure_counts.get(row["status"], 0) + 1
            mechanism = row.get("volume_audit_classification") or row["status"]
            if row.get("inverted_on_spanwise_edge"):
                mechanism += "@spanwise_edge"
            failure_mechanisms[mechanism] = failure_mechanisms.get(mechanism, 0) + 1

    summary = {
        "schema": "aeris.cfd.mesh_robustness_campaign.v1",
        "config": str(config_path),
        "topology": topology_id,
        "preset": preset,
        "n_samples": n_total,
        "n_ok": n_ok,
        "success_rate_percent": 100.0 * n_ok / n_total if n_total else 0.0,
        "failure_counts": failure_counts,
        "failure_mechanisms": failure_mechanisms,
        "samples": rows,
    }
    report_path = workdir / "campaign_report.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    record_status(
        job_id,
        kind="campaign:mesh-robustness",
        status="done",
        progress=f"{n_ok}/{n_total} ok ({summary['success_rate_percent']:.1f}%)",
        detail=f"failures: {failure_counts}" if failure_counts else "no failures",
        workdir=workdir,
    )

    typer.echo("")
    typer.echo(f"[campaign] success: {n_ok}/{n_total} ({summary['success_rate_percent']:.1f}%)")
    for reason, count in sorted(failure_counts.items()):
        typer.echo(f"  {reason:<28} {count}")
    typer.echo(f"[campaign] report: {report_path}")


_SURFACE_OPTION_TYPES: dict[str, type] = {
    "topology": str,
    "points_per_side": int,
    "spanwise_panels": int,
    "tip_radial_points": int,
    "tip_inner_scale": float,
    "split_x_fore": float,
    "cap_width_frac": float,
    "cap_wrap_points": int,
    "cap_wrap_x": float,
}


def _coerce_level(option: str, raw: str) -> object:
    caster = _SURFACE_OPTION_TYPES.get(option)
    if caster is None:
        raise CaseError(
            f"--option {option!r} not recognized. Known: {sorted(_SURFACE_OPTION_TYPES)}"
        )
    return raw if caster is str else caster(raw)


@campaign_app.command("surface-option-sweep")
def campaign_surface_option_sweep(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        help="AERIS geometry YAML (e.g. configs/geometry/bwb_explore_wide.yaml).",
    ),
    n: int = typer.Option(20, "--n", min=2, help="Number of Latin-hypercube geometries."),
    lhs_seed: int = typer.Option(
        42, "--lhs-seed", help="Seed for the Latin Hypercube sampler (aeris.dataset lhs_v1)."
    ),
    option: str = typer.Option(
        ...,
        "--option",
        help=(
            "Surface-mesh option to sweep: topology, points_per_side, "
            "spanwise_panels, tip_radial_points, tip_inner_scale, split_x_fore, "
            "cap_width_frac, cap_wrap_points, cap_wrap_x."
        ),
    ),
    levels: str = typer.Option(
        ...,
        "--levels",
        help="Comma-separated values for --option, e.g. '33,49,71,97' or 'cap4,mid4,split8'.",
    ),
    baseline_preset: str = typer.Option(
        "smoke",
        "--baseline-preset",
        help="Preset supplying every OTHER surface/volume param (see 'aeris cfd presets list').",
    ),
    volume_level: Optional[str] = typer.Option(
        None, "--volume-level", help="Override the preset's pyHyp grid level."
    ),
    workdir: Path = typer.Option(..., "--workdir", "-o", help="Sweep output directory."),
) -> None:
    """One-factor-at-a-time surface-mesh option sweep across N fixed LHS geometries.

    The same N Latin-hypercube geometries (built once, reused for every
    level) are meshed once per level of --option, holding every other
    surface/volume param at --baseline-preset. This is deliberately NOT a
    full factorial across all options (combinatorially infeasible and not
    how DOE is normally done) -- it is the standard one-factor-at-a-time
    design: find the safe range for each option in turn against a fixed,
    space-filling geometry sample, the basis for a defensible "surface mesh
    law" per option (DSE_READINESS.md / rubric items 2.1-2.5).
    """
    import time as _time

    from aeris.cfd.case.runner import _stage_volume  # local import: geometry-adjacent CLI layer
    from aeris.cfd.case.spec import CaseSpec, GeometryInput, VolumeMeshSpec
    from aeris.cfd.meshing.registry import get_topology
    from aeris.cfd.status import record_status
    from aeris.common.config import load_yaml_config
    from aeris.dataset.sampling.samplers.lhs_v1 import generate_lhs_samples
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator
    from aeris.mesh.surface import MeshBuildError, select_wing

    config_path = Path(config).expanduser().resolve()
    workdir = workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    job_id = f"sweep_{workdir.name}"
    record_status(
        job_id,
        kind=f"campaign:surface-option-sweep({option})",
        status="running",
        progress="building geometries",
        workdir=workdir,
    )

    level_values = [_coerce_level(option, raw.strip()) for raw in levels.split(",") if raw.strip()]
    if not level_values:
        raise typer.BadParameter("--levels must contain at least one value")

    baseline_surface = dict(get_preset(baseline_preset).surface)
    default_topology = str(baseline_surface.pop("oml_topology", "cap4"))
    volume_spec = VolumeMeshSpec(preset=baseline_preset, level=volume_level)

    raw_config = load_yaml_config(config_path)
    generator_id, generator_config = resolve_generator_and_config(raw_config)
    generator = get_geometry_generator(generator_id)
    samples = generate_lhs_samples(generator_config, n_samples=n, sampler_seed=lhs_seed)

    typer.echo(f"[sweep] config    : {config_path}")
    typer.echo(f"[sweep] geometries: {n} (Latin hypercube, seed={lhs_seed})")
    typer.echo(f"[sweep] option    : {option}  levels={level_values}")
    typer.echo(f"[sweep] baseline  : preset={baseline_preset}  topology={default_topology}")
    typer.echo(f"[sweep] workdir   : {workdir}")

    wings: list[object] = []
    for i, sample in enumerate(samples):
        geom_dir = workdir / f"geom_{i:03d}"
        try:
            case = generator.run_full_case(
                sample=sample, config=generator_config, output_dir=geom_dir, save_plot=False
            )
            airplane = case.aerosandbox_result.airplane
            wings.append(select_wing(airplane, 0))
        except Exception as exc:  # noqa: BLE001 - one bad LHS point must not abort the sweep
            typer.secho(
                f"  geometry {i:03d}: FAILED ({type(exc).__name__}: {exc})", fg=typer.colors.RED
            )
            wings.append(None)

    level_reports: list[dict[str, object]] = []
    for level in level_values:
        topology_id = f"wing_{level}_v1" if option == "topology" else f"wing_{default_topology}_v1"
        topology_gen = get_topology(topology_id)
        params = dict(baseline_surface)
        if option != "topology":
            params[option] = level
        if topology_id != "wing_cap4_v1":
            for cap_key in ("cap_width_frac", "cap_wrap_points", "cap_wrap_x"):
                params.pop(cap_key, None)

        rows: list[dict[str, object]] = []
        for i, wing in enumerate(wings):
            row: dict[str, object] = {"geom_index": i, "status": None, "error": None}
            if wing is None:
                row["status"] = "geometry_failed"
                rows.append(row)
                continue

            sample_dir = workdir / f"level_{option}_{level}" / f"geom_{i:03d}"
            surface_dir = sample_dir / "surface"
            t0 = _time.perf_counter()
            try:
                surface_report = topology_gen.generate(wing, surface_dir, params)
            except (ValueError, MeshBuildError, RuntimeError) as exc:
                row["status"] = "surface_mesh_failed"
                row["error"] = f"{type(exc).__name__}: {exc}"
                rows.append(row)
                continue
            row["surface_seconds"] = _time.perf_counter() - t0
            surface_global = surface_report.get("global", {})
            row["measured_min_scaled_jacobian"] = surface_global.get("min_scaled_corner_jacobian")
            row["measured_max_adjacent_normal_angle_deg"] = surface_global.get(
                "max_adjacent_normal_angle_deg"
            )

            t0 = _time.perf_counter()
            try:
                _stage_volume(
                    CaseSpec(
                        name=f"{option}_{level}_geom{i}",
                        geometry=GeometryInput(surface_dir=surface_dir),
                        volume_mesh=volume_spec,
                    ),
                    sample_dir,
                    dry_run=False,
                )
                row["status"] = "ok"
            except Exception as exc:  # noqa: BLE001 - includes invalid-march RuntimeError
                row["status"] = "volume_mesh_failed"
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["volume_seconds"] = _time.perf_counter() - t0

            report_path = surface_dir / "volume_report.json"
            volume_report = (
                json.loads(report_path.read_text(encoding="utf-8"))
                if report_path.is_file()
                else {}
            )
            if row["status"] != "ok" and volume_report.get("status") == "invalid":
                row["status"] = "volume_mesh_invalid_march"
            _record_volume_audit(row, volume_report)
            rows.append(row)

        n_ok = sum(1 for r in rows if r["status"] == "ok")
        level_reports.append(
            {
                "level": level,
                "n_ok": n_ok,
                "n_geometries": len(rows),
                "success_rate_percent": 100.0 * n_ok / len(rows) if rows else 0.0,
                "rows": rows,
            }
        )
        typer.echo(f"  {option}={level}: {n_ok}/{len(rows)} ok")
        record_status(
            job_id,
            kind=f"campaign:surface-option-sweep({option})",
            status="running",
            progress=(
                f"level {len(level_reports)}/{len(level_values)} "
                f"({option}={level}: {n_ok}/{len(rows)} ok)"
            ),
            workdir=workdir,
        )

    payload = {
        "schema": "aeris.cfd.surface_option_sweep.v1",
        "config": str(config_path),
        "n_geometries": n,
        "lhs_seed": lhs_seed,
        "option": option,
        "baseline_preset": baseline_preset,
        "default_topology": default_topology,
        "levels": level_reports,
    }
    report_path = workdir / "surface_option_sweep_report.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    overall_ok = sum(lr["n_ok"] for lr in level_reports)
    overall_n = sum(lr["n_geometries"] for lr in level_reports)
    record_status(
        job_id,
        kind=f"campaign:surface-option-sweep({option})",
        status="done",
        progress=f"{overall_ok}/{overall_n} ok across {len(level_values)} levels",
        detail=f"levels={level_values}",
        workdir=workdir,
    )
    typer.secho(f"[sweep] report: {report_path}", fg=typer.colors.GREEN)


def _parse_variant(raw: str) -> tuple[str, dict[str, object]]:
    """Parse ``name:key=value,key=value`` into (name, raw pyHyp overrides)."""
    name, _, body = raw.partition(":")
    name = name.strip()
    if not name:
        raise typer.BadParameter(f"variant needs a name: {raw!r}")
    overrides: dict[str, object] = {}
    for item in body.split(","):
        item = item.strip()
        if not item:
            continue
        key, _, value = item.partition("=")
        if not value:
            raise typer.BadParameter(f"variant {name!r}: expected key=value, got {item!r}")
        try:
            overrides[key.strip()] = json.loads(value)
        except json.JSONDecodeError:
            overrides[key.strip()] = value
    return name, overrides


@campaign_app.command("remarch")
def campaign_remarch(
    sample: list[Path] = typer.Option(
        ...,
        "--sample",
        help="Existing case dir containing surface/surface.fmt (repeatable).",
    ),
    variant: list[str] = typer.Option(
        ...,
        "--variant",
        help=(
            "Named pyHyp option set, 'name:key=value,key=value'. Use a bare "
            "'name:' to re-march with unmodified options as the control."
        ),
    ),
    workdir: Path = typer.Option(..., help="Output directory for the experiment."),
    preset: str = typer.Option("smoke", help="Volume preset to march with."),
    volume_level: str = typer.Option("smoke", help="Mesh level to march."),
    keep_meshes: bool = typer.Option(
        False,
        help=(
            "Keep every marched CGNS. Off by default: the audit records what "
            "the experiment is measuring, and one variant x one sample is "
            "~42 MB. Use for ParaView inspection of a specific result."
        ),
    ),
) -> None:
    """Re-march existing surface meshes under pyHyp option variants.

    The controlled experiment for a *volume*-side failure: the surface mesh
    is held byte-identical across variants, so any change in the audited
    inverted-cell count is attributable to the option that was varied and
    nothing else.  Re-marching also skips geometry and surface generation,
    which is what makes a single-variable study affordable.
    """
    from aeris.cfd.case.runner import _stage_volume  # local import: geometry-adjacent CLI layer
    from aeris.cfd.case.spec import GeometryInput, VolumeMeshSpec
    from aeris.cfd.status import record_status

    import shutil
    import time as _time

    variants = [_parse_variant(item) for item in variant]
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    job_id = f"remarch-{workdir.name}"
    n_total = len(sample) * len(variants)
    record_status(
        job_id, kind="campaign:remarch", status="running",
        progress=f"0/{n_total}", workdir=workdir,
    )

    rows: list[dict] = []
    done = 0
    for variant_name, overrides in variants:
        for source in sample:
            source = source.resolve()
            case_dir = workdir / variant_name / source.name
            target_surface = case_dir / "surface"
            target_surface.mkdir(parents=True, exist_ok=True)
            for name in ("surface.fmt", "surface_report.json"):
                origin = source / "surface" / name
                if not origin.is_file():
                    raise typer.BadParameter(f"{source} has no surface/{name}")
                shutil.copy2(origin, target_surface / name)

            row: dict[str, object] = {
                "variant": variant_name,
                "overrides": overrides,
                "sample": str(source),
            }
            t0 = _time.perf_counter()
            try:
                _stage_volume(
                    CaseSpec(
                        name=f"{variant_name}_{source.name}",
                        geometry=GeometryInput(surface_dir=target_surface),
                        volume_mesh=VolumeMeshSpec(
                            preset=preset, level=volume_level, raw_options=dict(overrides)
                        ),
                    ),
                    case_dir,
                    dry_run=False,
                )
                row["status"] = "ok"
            except Exception as exc:  # noqa: BLE001 - experiment must classify, not crash
                row["status"] = "volume_mesh_invalid_march"
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["seconds"] = _time.perf_counter() - t0
            report_path = target_surface / "volume_report.json"
            if report_path.is_file():
                _record_volume_audit(row, json.loads(report_path.read_text(encoding="utf-8")))
            if not keep_meshes:
                # The audit has already extracted everything the experiment
                # measures; the mesh itself re-marches from the surface.fmt
                # sitting next to it (see configs/cfd/RETENTION.md).
                for mesh in target_surface.glob("wing_vol_*.cgns"):
                    mesh.unlink()
            rows.append(row)
            done += 1
            typer.echo(
                f"  {variant_name:<12} {source.name:<16} {row['status']:<26} "
                f"inverted={row.get('inverted_cells', '?')}"
            )
            record_status(
                job_id, kind="campaign:remarch", status="running",
                progress=f"{done}/{n_total}", workdir=workdir,
            )

    by_variant: dict[str, dict[str, object]] = {}
    for variant_name, _ in variants:
        subset = [r for r in rows if r["variant"] == variant_name]
        by_variant[variant_name] = {
            "n_clean": sum(1 for r in subset if r.get("volume_audit_classification") == "clean"),
            "n_samples": len(subset),
            "total_inverted_cells": sum(int(r.get("inverted_cells") or 0) for r in subset),
        }

    payload = {
        "schema": "aeris.cfd.remarch_experiment.v1",
        "preset": preset,
        "volume_level": volume_level,
        "samples": [str(s.resolve()) for s in sample],
        "by_variant": by_variant,
        "rows": rows,
    }
    report_path = workdir / "remarch_report.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    typer.echo("")
    typer.echo(f"{'variant':<14}{'clean':>8}{'inverted cells':>16}")
    for variant_name, stats in by_variant.items():
        typer.echo(
            f"{variant_name:<14}{stats['n_clean']}/{stats['n_samples']:<6}"
            f"{stats['total_inverted_cells']:>16}"
        )
    record_status(
        job_id, kind="campaign:remarch", status="done",
        progress=f"{done}/{n_total}", detail=str(by_variant), workdir=workdir,
    )
    typer.secho(f"[remarch] report: {report_path}", fg=typer.colors.GREEN)


# Bulk artifacts a mesh/solve run writes that are regenerable from the
# inputs kept alongside them.  See configs/cfd/RETENTION.md for why this is
# safe (pyHyp meshing is bit-deterministic given surface.fmt + options).
PRUNABLE_SUFFIXES = (".cgns", ".vtk", ".npz", ".vtu", ".su2")
PRUNABLE_NAMES = ("restart.dat", "surface.vtk", "surface_blocks.npz")
# Never removed regardless of suffix: the evidence chain and the inputs
# that make everything else reproducible (rules 1 and 2).
RETAINED_NAMES = (
    "surface.fmt",
    "pyhyp_options.json",
    "pyhyp_effective_options.json",
    "run_pyhyp.py",
)


def _prunable_files(root: Path) -> list[Path]:
    victims = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in RETAINED_NAMES:
            continue
        if path.suffix in PRUNABLE_SUFFIXES or path.name in PRUNABLE_NAMES:
            victims.append(path)
    return victims


# Reported by every surface strategy, with the target each is judged
# against.  Targets follow common structured-meshing practice (Fluent/ANSYS
# skewness guidance, Verdict/CUBIT scaled Jacobian); they are comparison
# yardsticks, not gates.
SURFACE_METRIC_TARGETS = {
    "min_scaled_corner_jacobian": (">", 0.20),
    "max_equiangle_skewness": ("<", 0.50),
    "max_aspect_ratio": ("<", 100.0),
    "max_growth_ratio": ("<", 1.20),
    "max_adjacent_normal_angle_deg": ("<", 40.0),
}


def _group_block_metrics(blocks: list[dict]) -> dict[str, dict[str, float]]:
    """Aggregate per-block metrics separately for the OML and the tip cap.

    Scoring a wing surface as one number hides the thing that matters: the
    tip collar is a deliberately thin, fragile structure (3 radial points,
    forced by the volume march) whose skewness swamps the whole-mesh
    extrema, so a strategy that genuinely improves the wing surface looks
    identical to one that does not.  Judge the two independently.
    """
    groups = {
        "oml": [b for b in blocks if str(b.get("name", "")).startswith("oml")],
        "tip": [b for b in blocks if str(b.get("name", "")).startswith("tip")],
    }
    out: dict[str, dict[str, float]] = {}
    for label, members in groups.items():
        if not members:
            continue
        out[label] = {
            "min_scaled_corner_jacobian": min(
                float(b["min_scaled_corner_jacobian"]) for b in members
            ),
            "max_equiangle_skewness": max(float(b["max_equiangle_skewness"]) for b in members),
            "max_aspect_ratio": max(float(b["max_aspect_ratio"]) for b in members),
            "max_growth_ratio": max(float(b["max_growth_ratio"]) for b in members),
            "max_adjacent_normal_angle_deg": max(
                float(b["max_adjacent_normal_angle_deg"]) for b in members
            ),
            "worst_skew_block": max(members, key=lambda b: float(b["max_equiangle_skewness"]))[
                "name"
            ],
            "worst_jacobian_block": min(
                members, key=lambda b: float(b["min_scaled_corner_jacobian"])
            )["name"],
        }
    return out


def _score_surface_metrics(global_metrics: dict) -> tuple[int, list[str]]:
    """Count how many industry targets a surface mesh meets, and name the misses."""
    met = 0
    missed: list[str] = []
    for key, (sense, target) in SURFACE_METRIC_TARGETS.items():
        value = global_metrics.get(key)
        if value is None:
            continue
        ok = value > target if sense == ">" else value < target
        if ok:
            met += 1
        else:
            missed.append(key)
    return met, missed


@campaign_app.command("surface-strategy")
def campaign_surface_strategy(
    config: Path = typer.Option(..., "--config", "-c", help="Geometry YAML (one fixed wing)."),
    strategy: list[str] = typer.Option(
        ...,
        "--strategy",
        help=(
            "Named surface recipe, 'name:key=value,key=value'. 'topology' "
            "selects the generator (cap4/mid4/split8); every other key is a "
            "surface param (points_per_side, spanwise_panels, split_x_fore, "
            "chordwise_distribution, ...)."
        ),
    ),
    workdir: Path = typer.Option(..., help="Output directory."),
    seed: Optional[int] = typer.Option(None, help="Override the config's geometry seed."),
) -> None:
    """Compare surface-mesh strategies on ONE fixed wing, surface only.

    Holding the geometry fixed isolates the meshing recipe: every metric
    difference is the strategy, not the shape.  Surface generation is
    seconds, so a wide comparison is cheap -- volume marching is the
    expensive part and is deliberately not run here.

    Each strategy writes its own `surface.vtk` for ParaView alongside the
    metrics, because "which mesh is better" is partly a judgement you make
    by looking at the leading edge, not only by reading a table.
    """
    from aeris.cfd.meshing.registry import get_topology
    from aeris.commands.mesh import _build_wing
    from aeris.mesh.surface import MeshBuildError
    from aeris.cfd.status import record_status

    import time as _time

    _TOPOLOGY_IDS = {"cap4": "wing_cap4_v1", "mid4": "wing_mid4_v1", "split8": "wing_split8_v1"}

    strategies = [_parse_variant(item) for item in strategy]
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    job_id = f"surface-strategy-{workdir.name}"
    record_status(
        job_id, kind="campaign:surface-strategy", status="running",
        progress=f"0/{len(strategies)}", workdir=workdir,
    )

    wing, _airplane, _generator_id = _build_wing(
        config,
        wing_index=0,
        geometry_output_dir=workdir / "geometry",
        seed_override=seed,
        save_plot=False,
    )

    rows: list[dict] = []
    for index, (name, params) in enumerate(strategies, start=1):
        topology_key = str(params.pop("topology", "cap4"))
        if topology_key not in _TOPOLOGY_IDS:
            raise typer.BadParameter(f"topology must be one of {sorted(_TOPOLOGY_IDS)}")
        generator = get_topology(_TOPOLOGY_IDS[topology_key])
        out_dir = workdir / name

        row: dict[str, object] = {"strategy": name, "topology": topology_key, "params": params}
        t0 = _time.perf_counter()
        try:
            generator.generate(wing, out_dir, params)
            row["accepted"] = True
        except (MeshBuildError, ValueError) as exc:
            # A rejected mesh is a comparison result, not a crash: its report
            # is still written, so it can be scored alongside the others.
            row["accepted"] = False
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["seconds"] = _time.perf_counter() - t0

        report_path = out_dir / "surface_report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            metrics = report.get("global", {})
            row["metrics"] = metrics
            row["groups"] = _group_block_metrics(report.get("blocks") or [])
            row["block_count"] = report.get("block_count")
            row["targets_met"], row["targets_missed"] = _score_surface_metrics(metrics)
            # Rank on the wing surface, not the tip collar: the collar is
            # constrained by the volume march and cannot be tuned freely.
            oml = row["groups"].get("oml", {})
            row["oml_targets_met"], _ = _score_surface_metrics(oml)
            row["vtk"] = str(out_dir / "surface.vtk")
        rows.append(row)
        record_status(
            job_id, kind="campaign:surface-strategy", status="running",
            progress=f"{index}/{len(strategies)}", workdir=workdir,
        )

    ranked = sorted(
        rows,
        key=lambda r: (
            not r.get("accepted"),
            -int(r.get("oml_targets_met") or 0),
            float(((r.get("groups") or {}).get("oml") or {}).get("max_aspect_ratio") or 9e9),
        ),
    )
    payload = {
        "schema": "aeris.cfd.surface_strategy.v1",
        "config": str(config),
        "seed": seed,
        "targets": {k: f"{s} {v}" for k, (s, v) in SURFACE_METRIC_TARGETS.items()},
        "ranking": [r["strategy"] for r in ranked],
        "rows": rows,
    }
    report_path = workdir / "surface_strategy_report.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    header = (
        f"{'strategy':<22}{'ok':>4}{'oml':>5}"
        f"{'jac':>8}{'skew':>7}{'AR':>7}{'grow':>7}{'angle':>7}"
        f"{'|':>3}{'jac':>8}{'skew':>7}{'AR':>7}{'cells':>9}"
    )
    typer.echo("")
    typer.echo(header)
    typer.echo("-" * len(header))
    for row in ranked:
        m = row.get("metrics") or {}
        o = (row.get("groups") or {}).get("oml", {})
        t = (row.get("groups") or {}).get("tip", {})
        nan = float("nan")
        typer.echo(
            f"{row['strategy']:<22}"
            f"{('yes' if row.get('accepted') else 'NO'):>4}"
            f"{str(row.get('oml_targets_met', '-')) + '/5':>5}"
            f"{o.get('min_scaled_corner_jacobian', nan):>8.4f}"
            f"{o.get('max_equiangle_skewness', nan):>7.3f}"
            f"{o.get('max_aspect_ratio', nan):>7.1f}"
            f"{o.get('max_growth_ratio', nan):>7.3f}"
            f"{o.get('max_adjacent_normal_angle_deg', nan):>7.1f}"
            f"{'|':>3}"
            f"{t.get('min_scaled_corner_jacobian', nan):>8.4f}"
            f"{t.get('max_equiangle_skewness', nan):>7.3f}"
            f"{t.get('max_aspect_ratio', nan):>7.1f}"
            f"{m.get('total_cells', 0):>9}"
        )
    typer.echo("")
    typer.echo("  left block = OML (wing surface), right of | = tip cap; ranked on OML")
    typer.echo("targets: " + ", ".join(f"{k} {s}{v}" for k, (s, v) in SURFACE_METRIC_TARGETS.items()))
    typer.echo(f"ParaView: {workdir}/<strategy>/surface.vtk")
    record_status(
        job_id, kind="campaign:surface-strategy", status="done",
        progress=f"{len(strategies)}/{len(strategies)}",
        detail=f"best={ranked[0]['strategy'] if ranked else 'n/a'}", workdir=workdir,
    )
    typer.secho(f"[surface-strategy] report: {report_path}", fg=typer.colors.GREEN)


@cfd_app.command("prune")
def cfd_prune(
    target: list[Path] = typer.Argument(..., help="Case or campaign directories to prune."),
    apply: bool = typer.Option(
        False, "--apply", help="Actually delete. Without this, only reports what would go."
    ),
    keep_exemplar: bool = typer.Option(
        True,
        help="Keep one quarantined *.invalid.cgns per directory as a frozen failure exemplar.",
    ),
) -> None:
    """Delete regenerable bulk artifacts, keeping reports and inputs.

    Implements `configs/cfd/RETENTION.md`. Dry-run by default: deleting a
    campaign's meshes is irreversible and the reports that make them
    reproducible sit in the same tree, so the destructive form is opt-in.
    """
    total_bytes = 0
    total_files = 0
    for root in target:
        root = root.resolve()
        if not root.is_dir():
            typer.secho(f"skip (not a directory): {root}", fg=typer.colors.YELLOW)
            continue
        victims = _prunable_files(root)
        if keep_exemplar:
            exemplar = next((p for p in victims if p.name.endswith(".invalid.cgns")), None)
            if exemplar is not None:
                victims.remove(exemplar)
                typer.echo(f"  keeping failure exemplar: {exemplar.relative_to(root)}")
        size = sum(p.stat().st_size for p in victims)
        total_bytes += size
        total_files += len(victims)
        typer.echo(f"{root}: {len(victims)} files, {size / 1048576:.1f} MB")
        if apply:
            for path in victims:
                path.unlink()

    verb = "deleted" if apply else "would delete"
    typer.secho(
        f"[prune] {verb} {total_files} files, {total_bytes / 1048576:.1f} MB",
        fg=typer.colors.GREEN if apply else typer.colors.YELLOW,
    )
    if not apply:
        typer.echo("re-run with --apply to delete")


@presets_app.command("list")
def presets_list(
    kind: Optional[str] = typer.Option(
        None, "--kind", help="Filter by kind: mesh_family, solver_strategy."
    ),
) -> None:
    """List validated presets."""
    presets = list_presets(kind=kind)
    if not presets:
        typer.echo("(no presets)")
        return
    width = max(len(p.name) for p in presets)
    for preset in presets:
        typer.echo(f"{preset.name:<{width}}  [{preset.kind}]  {preset.description}")


@presets_app.command("show")
def presets_show(
    name: str = typer.Argument(..., help="Preset name (see 'aeris cfd presets list')."),
) -> None:
    """Show one preset: values, kind, and the citation for why it is validated."""
    try:
        preset = get_preset(name)
    except ValueError as exc:
        typer.secho(f"[cfd] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    payload = {
        "name": preset.name,
        "kind": preset.kind,
        "description": preset.description,
        "citation": preset.citation,
        "surface": preset.surface,
        "volume": preset.volume,
        "solver": preset.solver,
    }
    typer.echo(json.dumps(payload, indent=2))
