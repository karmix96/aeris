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

    report = run_study(spec, workdir=run_dir, dry_run=dry_run, echo=typer.echo)

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
    from aeris.commands.mesh import _build_wing
    from aeris.mesh.surface import MeshBuildError

    config_path = Path(config).expanduser().resolve()
    workdir = workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

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
        row["minimum_scaled_jacobian"] = surface_report.get("minimum_scaled_jacobian")
        row["maximum_adjacent_normal_angle_deg"] = surface_report.get(
            "maximum_adjacent_normal_angle_deg"
        )
        row["minimum_te_thickness"] = surface_report.get("minimum_te_thickness")

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
            if report_path.is_file():
                march_status = json.loads(report_path.read_text(encoding="utf-8")).get("status")
            row["status"] = (
                "volume_mesh_invalid_march" if march_status == "invalid" else "volume_mesh_failed"
            )
            row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            typer.echo(f"  seed {seed:5d}  {row['status']}")
            continue
        row["timings_sec"]["volume"] = _time.perf_counter() - t0
        volume_report = json.loads((surface_dir / "volume_report.json").read_text(encoding="utf-8"))
        row["march_metrics"] = volume_report.get("march_metrics", {})
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
    for row in rows:
        if row["status"] != "ok":
            failure_counts[row["status"]] = failure_counts.get(row["status"], 0) + 1

    summary = {
        "schema": "aeris.cfd.mesh_robustness_campaign.v1",
        "config": str(config_path),
        "topology": topology_id,
        "preset": preset,
        "n_samples": n_total,
        "n_ok": n_ok,
        "success_rate_percent": 100.0 * n_ok / n_total if n_total else 0.0,
        "failure_counts": failure_counts,
        "samples": rows,
    }
    report_path = workdir / "campaign_report.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    typer.echo("")
    typer.echo(f"[campaign] success: {n_ok}/{n_total} ({summary['success_rate_percent']:.1f}%)")
    for reason, count in sorted(failure_counts.items()):
        typer.echo(f"  {reason:<28} {count}")
    typer.echo(f"[campaign] report: {report_path}")


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
