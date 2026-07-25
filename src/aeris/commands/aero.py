"""
CLI commands for aerodynamic analysis and sweep inspection.

Responsibilities:
    - Expose aero run and sweep commands
    - Validate CLI inputs
    - Delegate workflow orchestration to pipeline helpers
    - Inspect and replay saved aero results

Notes:
    - Geometry preparation and manifest-writing now live in pipeline helpers
    - This module should remain a thin control/reporting layer
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer

from aeris.aero.io import load_aero_result_from_run_dir
from aeris.aero.cm_sanity import run_cm_sign_sanity
from aeris.commands._helpers import parse_float_list
from aeris.commands._workflow_recording import record_workflow_stage_success
from aeris.pipeline.aero_workflows import (
    execute_aero_run,
    execute_aero_sweep,
)

aero_app = typer.Typer(help="Aerodynamic analysis commands.")

_ALLOWED_SPACING = {"equal", "cosine"}

# CLI design note:
# The current aero command exposes AVL-oriented options because the only
# operational solver is aerosandbox_avl. This is acceptable for the current
# implementation, but future CFD/VLM solvers should move toward config-driven
# solver option blocks or generic --solver-option handling.
#
# Do not keep adding solver-specific flags here forever


def _aero_result_artifacts(run_root: Path, result: Any) -> list[Path | str]:
    """Return stable artifacts for a single aero run workflow record."""
    artifacts: list[Path | str] = [run_root]
    for value in (getattr(result, "artifact_paths", {}) or {}).values():
        if value:
            artifacts.append(str(value))
    for candidate in [run_root / "aero_manifest.json", run_root / "aero" / "aero_result.json"]:
        if candidate.exists():
            artifacts.append(candidate)
    return artifacts


def _aero_sweep_artifacts(run_root: Path) -> list[Path | str]:
    """Return stable artifacts for an aero sweep workflow record."""
    artifacts: list[Path | str] = [run_root]
    for candidate in [
        run_root / "aero_sweep_manifest.json",
    ]:
        if candidate.exists():
            artifacts.append(candidate)
    return artifacts


def _aero_sweep_completed_successfully(sweep_result: Any) -> bool:
    """Return True when all expanded sweep cases completed with success status."""
    summary = getattr(sweep_result, "summary", {}) or {}
    cases = getattr(sweep_result, "cases", []) or []
    requested = summary.get("requested_n_cases")
    completed = summary.get("completed_n_cases")
    if requested is not None and completed is not None and requested != completed:
        return False
    if cases and any(str(case.get("status", "")).lower() != "success" for case in cases):
        return False
    return True


def _print_aero_result(result: Any) -> None:
    typer.echo(f"[AERIS] Solver status: {result.status.value}")

    if result.cl is not None:
        typer.echo(f"[AERIS] CL   = {result.cl:.6f}")
    if result.cd is not None:
        typer.echo(f"[AERIS] CD   = {result.cd:.6f}")
    if result.cm is not None:
        typer.echo(f"[AERIS] Cm   = {result.cm:.6f}")
    if result.l_over_d is not None:
        typer.echo(f"[AERIS] L/D  = {result.l_over_d:.6f}")
    if result.cy is not None:
        typer.echo(f"[AERIS] CY   = {result.cy:.6f}")
    if result.cl_roll is not None:
        typer.echo(f"[AERIS] Cl   = {result.cl_roll:.6f}")
    if result.cn is not None:
        typer.echo(f"[AERIS] Cn   = {result.cn:.6f}")

    if result.cd_ind is not None:
        typer.echo(f"[AERIS] CDind = {result.cd_ind:.6f}")
    if result.cd_ff is not None:
        typer.echo(f"[AERIS] CDff  = {result.cd_ff:.6f}")
    if result.span_efficiency is not None:
        typer.echo(f"[AERIS] e     = {result.span_efficiency:.6f}")
    if result.x_np is not None:
        typer.echo(f"[AERIS] Xnp   = {result.x_np:.6f}")

    if result.stability_axis_derivatives:
        typer.echo("[AERIS] Stability-axis derivatives:")
        key_groups = [
            ["CLa", "CLb", "CYa", "CYb", "Cla", "Clb", "Cma", "Cmb", "Cna", "Cnb"],
            ["CLp", "CLq", "CLr", "CYp", "CYq", "CYr", "Clp", "Clq", "Clr", "Cmp", "Cmq", "Cmr", "Cnp", "Cnq", "Cnr"],
            ["Xnp"],
        ]
        for group in key_groups:
            printed_any = False
            for key in group:
                value = result.stability_axis_derivatives.get(key)
                if value is not None:
                    typer.echo(f"  - {key} = {value:.6f}")
                    printed_any = True
            if printed_any:
                typer.echo("")

    if result.body_axis_derivatives:
        typer.echo("[AERIS] Body-axis derivatives:")
        key_groups = [
            ["CXu", "CXv", "CXw", "CYu", "CYv", "CYw", "CZu", "CZv", "CZw"],
            ["Clu", "Clv", "Clw", "Cmu", "Cmv", "Cmw", "Cnu", "Cnv", "Cnw"],
        ]
        for group in key_groups:
            printed_any = False
            for key in group:
                value = result.body_axis_derivatives.get(key)
                if value is not None:
                    typer.echo(f"  - {key} = {value:.6f}")
                    printed_any = True
            if printed_any:
                typer.echo("")

    if result.derived_metrics:
        typer.echo("[AERIS] Derived metrics:")
        for key, value in result.derived_metrics.items():
            if value is not None:
                typer.echo(f"  - {key} = {value:.6f}")
        typer.echo("")

    if result.failure is not None:
        typer.echo(f"[AERIS] Failure reason: {result.failure.reason}")
        typer.echo(f"[AERIS] Failure message: {result.failure.message}")

    if result.warnings:
        typer.echo("[AERIS] Warnings:")
        for warning in result.warnings:
            typer.echo(f"  - {warning}")
        typer.echo("")

    if result.artifact_paths:
        typer.echo("[AERIS] Artifacts:")
        for key in sorted(result.artifact_paths.keys()):
            typer.echo(f"  - {key}: {result.artifact_paths[key]}")


def _print_aero_sweep_result(sweep_result: dict[str, Any]) -> None:
    summary = sweep_result.get("summary", {}) or {}
    cases = sweep_result.get("cases", []) or []

    typer.echo(f"[AERIS] Requested cases: {summary.get('requested_n_cases')}")
    typer.echo(f"[AERIS] Completed cases: {summary.get('completed_n_cases')}")

    status_counts: dict[str, int] = {}
    for case in cases:
        status = str(case.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    success_n = status_counts.get("success", 0)
    typer.echo(f"[AERIS] Successful cases: {success_n}")
    typer.echo(f"[AERIS] Non-success cases: {len(cases) - success_n}")

    if status_counts:
        typer.echo("[AERIS] Status breakdown:")
        for status in sorted(status_counts.keys()):
            typer.echo(f"  - {status}: {status_counts[status]}")

    typer.echo("[AERIS] Case statuses:")
    for case in cases:
        typer.echo(f"  - {case.get('case_label')}: {case.get('status')}")


def _validate_paneling(
    *,
    spanwise_resolution: int,
    chordwise_resolution: int,
    spanwise_spacing: str,
    chordwise_spacing: str,
) -> None:
    if spanwise_resolution <= 0:
        raise typer.BadParameter("--spanwise-resolution must be > 0.")
    if chordwise_resolution <= 0:
        raise typer.BadParameter("--chordwise-resolution must be > 0.")
    if spanwise_spacing not in _ALLOWED_SPACING:
        raise typer.BadParameter(
            f"--spanwise-spacing must be one of {sorted(_ALLOWED_SPACING)}."
        )
    if chordwise_spacing not in _ALLOWED_SPACING:
        raise typer.BadParameter(
            f"--chordwise-spacing must be one of {sorted(_ALLOWED_SPACING)}."
        )


def _warn_flight_condition(
    *,
    alpha: float,
    velocity: float,
    altitude: float,
) -> None:
    """Emit warnings for physically implausible flight condition values."""
    if not (-30.0 <= alpha <= 30.0):
        typer.secho(
            f"[WARN] alpha={alpha} deg is outside the typical envelope "
            "(-30 to +30 deg). AVL may diverge or produce meaningless results.",
            fg=typer.colors.YELLOW,
        )
    if velocity <= 0.0:
        typer.secho(
            f"[WARN] velocity={velocity} m/s is non-positive. "
            "AVL requires V > 0.",
            fg=typer.colors.YELLOW,
        )
    if velocity > 150.0:
        typer.secho(
            f"[WARN] velocity={velocity} m/s is unusually high for a BWB UAV. "
            "Check units (expected m/s).",
            fg=typer.colors.YELLOW,
        )
    if altitude < -500.0 or altitude > 20000.0:
        typer.secho(
            f"[WARN] altitude={altitude} m is outside the typical range "
            "(-500 to 20000 m).",
            fg=typer.colors.YELLOW,
        )


def _validate_source_selection(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
) -> None:
    mode_count = sum(x is not None for x in [config, run_dir, dataset])
    if mode_count != 1:
        raise typer.BadParameter("Provide exactly one of: --config, --run-dir, --dataset.")
    if dataset is not None and not geometry_id.strip():
        raise typer.BadParameter("--dataset requires --geometry-id.")


def _resolve_source_policy(*, geometry_source: str, config_mode: bool) -> str:
    gs = geometry_source.strip().lower()
    if gs not in {"auto", "native", "reconstruct"}:
        raise typer.BadParameter("--geometry-source must be auto, native, or reconstruct.")

    if gs == "auto":
        return "native" if config_mode else "reconstruct"

    if not config_mode and gs == "native":
        raise typer.BadParameter(
            "Native source is only available for fresh --config runs. "
            "Existing run/dataset paths must reconstruct."
        )

    return gs


def _load_aero_sweep_manifest(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()

    candidates = [
        run_dir / "aero_sweep_manifest.json",
        run_dir / "aero_sweep" / "aero_sweep_manifest.json",
    ]

    if run_dir.name == "aero_sweep":
        candidates.insert(0, run_dir / "aero_sweep_manifest.json")

    for path in candidates:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))

            if "aero_sweep_result" in data:
                return data

            if "cases" in data and "summary" in data:
                return {
                    "aero_sweep_result": {
                        "cases": data.get("cases", []),
                        "summary": data.get("summary", {}),
                    }
                }

    raise typer.BadParameter(
        f"Could not find a valid aero sweep manifest in '{run_dir}' "
        f"or '{run_dir / 'aero_sweep'}'."
    )


def _resolve_sweep_case_dir(
    run_dir: Path,
    case_label: str | None,
    case_index: int | None,
) -> Path:
    manifest = _load_aero_sweep_manifest(run_dir)
    sweep_result = manifest.get("aero_sweep_result", {}) or {}
    cases = sweep_result.get("cases", []) or []

    if case_label and case_index is not None:
        raise typer.BadParameter("Provide only one of --case-label or --case-index.")

    if not case_label and case_index is None:
        raise typer.BadParameter("Provide one of --case-label or --case-index.")

    if case_index is not None:
        if case_index < 0 or case_index >= len(cases):
            raise typer.BadParameter(
                f"--case-index {case_index} is out of range for {len(cases)} cases."
            )
        case_dir = cases[case_index].get("case_dir")
        if not case_dir:
            raise typer.BadParameter(f"Case index {case_index} has no case_dir recorded.")
        return Path(case_dir)

    for case in cases:
        if case.get("case_label") == case_label:
            case_dir = case.get("case_dir")
            if not case_dir:
                raise typer.BadParameter(f"Case '{case_label}' has no case_dir recorded.")
            return Path(case_dir)

    raise typer.BadParameter(f"Could not find case with label '{case_label}'.")


@aero_app.command("run")
def run_aero(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Fresh geometry config. Use this to generate geometry and run aero immediately.",
    ),
    run_dir: Path | None = typer.Option(
        None,
        "--run-dir",
        help="Existing geometry run directory to reuse.",
    ),
    dataset: Path | None = typer.Option(
        None,
        "--dataset",
        help="Existing dataset root to reuse geometry from.",
    ),
    geometry_id: str = typer.Option(
        "",
        "--geometry-id",
        help="Geometry ID inside dataset root, e.g. geom_00001.",
    ),
    geometry_source: str = typer.Option(
        "auto",
        "--geometry-source",
        help="Geometry source mode. auto=config->native, run/dataset->reconstruct.",
    ),
    generator_id: str = typer.Option(
        "",
        "--generator-id",
        help="Generator ID required for --run-dir and --dataset modes. Ignored for --config.",
    ),
    control_input_deg: float | None = typer.Option(
        None,
        "--control-input-deg",
        help="Symmetric elevon deflection in degrees (AVL d2 symmetric command). Positive = trailing edge down on both sides.",
    ),
    diff_input_deg: float | None = typer.Option(
        None,
        "--diff-input-deg",
        help="Differential (antisymmetric) elevon deflection in degrees (AVL d2 antisymmetric command). Positive = right TE down, left TE up.",
    ),
    alpha: float = typer.Option(
        ...,
        "--alpha",
        help="Angle of attack in degrees for a single aero run.",
    ),
    velocity: float = typer.Option(
        28.0,
        "--velocity",
        help="Freestream velocity in m/s.",
    ),
    altitude: float = typer.Option(
        0.0,
        "--altitude",
        help="Altitude in meters.",
    ),
    beta: float = typer.Option(
        0.0,
        "--beta",
        help="Sideslip angle in degrees.",
    ),
    mach: float | None = typer.Option(
        None,
        "--mach",
        help="Optional Mach metadata/QC value. Velocity and altitude remain authoritative.",
    ),
    p: float = typer.Option(
        0.0,
        "--p",
        help="Body roll rate in rad/s.",
    ),
    q: float = typer.Option(
        0.0,
        "--q",
        help="Body pitch rate in rad/s.",
    ),
    r: float = typer.Option(
        0.0,
        "--r",
        help="Body yaw rate in rad/s.",
    ),
    solver: str = typer.Option(
        "aerosandbox_avl",
        "--solver",
        help="Registered aero solver ID.",
    ),
    avl_command: str = typer.Option(
        "",
        "--avl-command",
        help="Optional AVL executable path/command. If omitted, AERIS tries PATH.",
    ),
    timeout_sec: int = typer.Option(
        180,
        "--timeout-sec",
        help="Solver timeout in seconds.",
    ),
    spanwise_resolution: int = typer.Option(
        4,
        "--spanwise-resolution",
        help="AVL spanwise panel resolution override.",
    ),
    chordwise_resolution: int = typer.Option(
        8,
        "--chordwise-resolution",
        help="AVL chordwise panel resolution override.",
    ),
    spanwise_spacing: str = typer.Option(
        "equal",
        "--spanwise-spacing",
        help="AVL spanwise spacing override: equal or cosine.",
    ),
    chordwise_spacing: str = typer.Option(
        "cosine",
        "--chordwise-spacing",
        help="AVL chordwise spacing override: equal or cosine.",
    ),
    save_surface_forces: bool = typer.Option(
        False,
        "--save-surface-forces",
        help="Write AVL surface force output files.",
    ),
    save_element_forces: bool = typer.Option(
        False,
        "--save-element-forces",
        help="Write AVL element force output files.",
    ),
    seed: int = typer.Option(
        0,
        "--seed",
        help="Random seed used when generating fresh geometry from config.",
    ),
    output_name: str = typer.Option(
        "",
        "--output-name",
        help="Optional run-name suffix for the created output folder.",
    ),
    viscous_polar_source: str = typer.Option(
        "none",
        "--viscous-polar-source",
        help=(
            "Viscous drag backend: 'neuralfoil' evaluates profile drag live from "
            "airfoil coordinates (requires neuralfoil package); 'none' (default) "
            "keeps pure inviscid AVL."
        ),
    ),
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        "-w",
        file_okay=False,
        dir_okay=True,
        help="Optional workflow root to auto-record the aero run stage after a successful run.",
    ),
) -> None:
    """Run a single aero evaluation against fresh geometry, an existing run, or a dataset row.

    Velocity defaults to 28 m/s (mid-envelope per AERIS prototype flight scope: 15-30 m/s).
    Altitude defaults to 0 m. AVL is the only operational solver today; other
    solvers will arrive via the registry.
    """
    
    _validate_source_selection(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
    )
    _validate_paneling(
        spanwise_resolution=spanwise_resolution,
        chordwise_resolution=chordwise_resolution,
        spanwise_spacing=spanwise_spacing,
        chordwise_spacing=chordwise_spacing,
    )

    _warn_flight_condition(alpha=alpha, velocity=velocity, altitude=altitude)

    source_policy = _resolve_source_policy(
        geometry_source=geometry_source,
        config_mode=config is not None,
    )

    run_root, result = execute_aero_run(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        geometry_source=source_policy,
        generator_id=generator_id.strip() or None,
        control_input_deg=control_input_deg,
        diff_input_deg=diff_input_deg,
        alpha=alpha,
        velocity=velocity,
        altitude=altitude,
        beta=beta,
        mach=mach,
        p=p,
        q=q,
        r=r,
        solver=solver,
        avl_command=avl_command,
        timeout_sec=timeout_sec,
        spanwise_resolution=spanwise_resolution,
        chordwise_resolution=chordwise_resolution,
        spanwise_spacing=spanwise_spacing,
        chordwise_spacing=chordwise_spacing,
        save_surface_forces=save_surface_forces,
        save_element_forces=save_element_forces,
        seed=seed,
        output_name=output_name,
        viscous_polar_source=viscous_polar_source,
    )

    typer.echo("")
    typer.echo(f"[AERIS] Aero run completed in: {run_root}")
    _print_aero_result(result)

    result_status = getattr(getattr(result, "status", None), "value", getattr(result, "status", ""))
    if str(result_status).lower() == "success":
        record_workflow_stage_success(
            workflow=workflow,
            stage="aero_run",
            inputs=[config, run_dir, dataset, geometry_id or None],
            artifacts=_aero_result_artifacts(run_root, result),
            notes="Single aero run completed successfully.",
            metadata={
                "command": "aeris aero run",
                "solver": solver,
                "alpha_deg": alpha,
                "beta_deg": beta,
                "velocity_mps": velocity,
                "altitude_m": altitude,
                "control_input_deg": control_input_deg,
                "diff_input_deg": diff_input_deg,
                "status": str(result_status),
            },
        )
    elif workflow is not None:
        typer.echo(
            "[AERIS] Workflow aero_sweep stage was not auto-recorded "
            f"because aero run status is {result_status!r}."
        )


@aero_app.command("inspect")
def inspect_aero(
    run_dir: Path = typer.Option(
        ...,
        "--run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Existing aero run directory or nested aero/ directory.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print saved aero result as machine-readable JSON.",
    ),
) -> None:
    """Inspect a single saved aero run by printing its result, or as JSON with --json."""

    result = load_aero_result_from_run_dir(run_dir)

    if as_json:
        typer.echo(json.dumps(asdict(result), indent=2))
        return

    typer.echo("")
    typer.echo(f"[AERIS] Inspecting aero result from: {run_dir}")
    _print_aero_result(result)


@aero_app.command("sweep")
def sweep_aero(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Fresh geometry config. Use this to generate geometry and run an aero sweep immediately.",
    ),
    run_dir: Path | None = typer.Option(
        None,
        "--run-dir",
        help="Existing geometry run directory to reuse.",
    ),
    dataset: Path | None = typer.Option(
        None,
        "--dataset",
        help="Existing dataset root to reuse geometry from.",
    ),
    geometry_id: str = typer.Option(
        "",
        "--geometry-id",
        help="Geometry ID inside dataset root, e.g. geom_00001.",
    ),
    geometry_source: str = typer.Option(
        "auto",
        "--geometry-source",
        help="Geometry source mode. auto=config->native, run/dataset->reconstruct.",
    ),
    generator_id: str = typer.Option(
        "",
        "--generator-id",
        help="Generator ID required for --run-dir and --dataset modes. Ignored for --config.",
    ),
    control_input_deg: float | None = typer.Option(
        None,
        "--control-input-deg",
        help="Symmetric elevon deflection in degrees (AVL d2 symmetric command) applied to every sweep case.",
    ),
    control_input_values: str = typer.Option(
        "",
        "--control-input-values",
        help="Comma-separated symmetric elevon sweep values in degrees, e.g. -5,0,5",
    ),
    diff_input_values: str = typer.Option(
        "",
        "--diff-input-values",
        help="Comma-separated differential (antisymmetric) elevon sweep values in degrees, e.g. -10,-5,0,5,10",
    ),
    alpha: float = typer.Option(
        0.0,
        "--alpha",
        help="Base alpha value used when --alpha-values is not provided.",
    ),
    velocity: float = typer.Option(
        28.0,
        "--velocity",
        help="Base velocity in m/s used when --velocity-values is not provided.",
    ),
    altitude: float = typer.Option(
        0.0,
        "--altitude",
        help="Base altitude in meters used when --altitude-values is not provided.",
    ),
    beta: float = typer.Option(
        0.0,
        "--beta",
        help="Base beta value used when --beta-values is not provided.",
    ),
    mach: float | None = typer.Option(
        None,
        "--mach",
        help="Optional Mach metadata/QC value. Velocity and altitude remain authoritative.",
    ),
    p: float = typer.Option(
        0.0,
        "--p",
        help="Base body roll rate in rad/s used when --p-values is not provided.",
    ),
    q: float = typer.Option(
        0.0,
        "--q",
        help="Base body pitch rate in rad/s used when --q-values is not provided.",
    ),
    r: float = typer.Option(
        0.0,
        "--r",
        help="Base body yaw rate in rad/s used when --r-values is not provided.",
    ),
    alpha_values: str = typer.Option(
        "",
        "--alpha-values",
        help="Comma-separated alpha sweep values, e.g. -2,0,2,4,6",
    ),
    beta_values: str = typer.Option(
        "",
        "--beta-values",
        help="Comma-separated beta sweep values, e.g. 0,2,4",
    ),
    velocity_values: str = typer.Option(
        "",
        "--velocity-values",
        help="Comma-separated velocity sweep values, e.g. 20,25,30",
    ),
    altitude_values: str = typer.Option(
        "",
        "--altitude-values",
        help="Comma-separated altitude sweep values, e.g. 0,1500,3000",
    ),
    p_values: str = typer.Option(
        "",
        "--p-values",
        help="Comma-separated p sweep values, e.g. 0,0.05",
    ),
    q_values: str = typer.Option(
        "",
        "--q-values",
        help="Comma-separated q sweep values, e.g. 0,0.05",
    ),
    r_values: str = typer.Option(
        "",
        "--r-values",
        help="Comma-separated r sweep values, e.g. 0,0.05",
    ),
    solver: str = typer.Option(
        "aerosandbox_avl",
        "--solver",
        help="Registered aero solver ID.",
    ),
    avl_command: str = typer.Option(
        "",
        "--avl-command",
        help="Optional AVL executable path/command. If omitted, AERIS tries PATH.",
    ),
    timeout_sec: int = typer.Option(
        180,
        "--timeout-sec",
        help="Solver timeout in seconds.",
    ),
    spanwise_resolution: int = typer.Option(
        4,
        "--spanwise-resolution",
        help="AVL spanwise panel resolution override.",
    ),
    chordwise_resolution: int = typer.Option(
        8,
        "--chordwise-resolution",
        help="AVL chordwise panel resolution override.",
    ),
    spanwise_spacing: str = typer.Option(
        "equal",
        "--spanwise-spacing",
        help="AVL spanwise spacing override: equal or cosine.",
    ),
    chordwise_spacing: str = typer.Option(
        "cosine",
        "--chordwise-spacing",
        help="AVL chordwise spacing override: equal or cosine.",
    ),
    save_surface_forces: bool = typer.Option(
        False,
        "--save-surface-forces",
        help="Write AVL surface force output files.",
    ),
    save_element_forces: bool = typer.Option(
        False,
        "--save-element-forces",
        help="Write AVL element force output files.",
    ),
    seed: int = typer.Option(
        0,
        "--seed",
        help="Random seed used when generating fresh geometry from config.",
    ),
    output_name: str = typer.Option(
        "",
        "--output-name",
        help="Optional run-name suffix for the created output folder.",
    ),
    max_cases: int | None = typer.Option(
        None,
        "--max-cases",
        help="Optional safety cap on total expanded sweep cases.",
    ),
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        "-w",
        file_okay=False,
        dir_okay=True,
        help="Optional workflow root to auto-record the aero sweep/setup stage after all sweep cases succeed.",
    ),
) -> None:
    """Run a parametric aero sweep across alpha/beta/V/h/p/q/r/control values.

    Provide any subset of *_values options; the workflow generates the Cartesian
    product of the populated lists. Use --max-cases as a safety cap.
    """
    _validate_source_selection(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
    )
    _validate_paneling(
        spanwise_resolution=spanwise_resolution,
        chordwise_resolution=chordwise_resolution,
        spanwise_spacing=spanwise_spacing,
        chordwise_spacing=chordwise_spacing,
    )

    _warn_flight_condition(alpha=alpha, velocity=velocity, altitude=altitude)

    source_policy = _resolve_source_policy(
        geometry_source=geometry_source,
        config_mode=config is not None,
    )

    parsed_alpha_values = parse_float_list(alpha_values, "--alpha-values")
    parsed_beta_values = parse_float_list(beta_values, "--beta-values")
    parsed_velocity_values = parse_float_list(velocity_values, "--velocity-values")
    parsed_altitude_values = parse_float_list(altitude_values, "--altitude-values")
    parsed_p_values = parse_float_list(p_values, "--p-values")
    parsed_q_values = parse_float_list(q_values, "--q-values")
    parsed_r_values = parse_float_list(r_values, "--r-values")
    parsed_control_input_values = parse_float_list(
        control_input_values,
        "--control-input-values",
    )
    parsed_diff_input_values = parse_float_list(
        diff_input_values,
        "--diff-input-values",
    )

    run_root, sweep_result = execute_aero_sweep(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        geometry_source=source_policy,
        generator_id=generator_id.strip() or None,
        control_input_deg=control_input_deg,
        control_input_values=parsed_control_input_values,
        diff_input_values=parsed_diff_input_values,
        alpha=alpha,
        velocity=velocity,
        altitude=altitude,
        beta=beta,
        mach=mach,
        p=p,
        q=q,
        r=r,
        alpha_values=parsed_alpha_values,
        beta_values=parsed_beta_values,
        velocity_values=parsed_velocity_values,
        altitude_values=parsed_altitude_values,
        p_values=parsed_p_values,
        q_values=parsed_q_values,
        r_values=parsed_r_values,
        solver=solver,
        avl_command=avl_command,
        timeout_sec=timeout_sec,
        spanwise_resolution=spanwise_resolution,
        chordwise_resolution=chordwise_resolution,
        spanwise_spacing=spanwise_spacing,
        chordwise_spacing=chordwise_spacing,
        save_surface_forces=save_surface_forces,
        save_element_forces=save_element_forces,
        seed=seed,
        output_name=output_name,
        max_cases=max_cases,
    )

    typer.echo("")
    typer.echo(f"[AERIS] Aero sweep completed in: {run_root}")
    _print_aero_sweep_result({
        "cases": sweep_result.cases,
        "summary": sweep_result.summary,
    })

    if _aero_sweep_completed_successfully(sweep_result):
        record_workflow_stage_success(
            workflow=workflow,
            stage="aero_sweep",
            inputs=[config, run_dir, dataset, geometry_id or None],
            artifacts=_aero_sweep_artifacts(run_root),
            notes="Aero sweep completed successfully.",
            metadata={
                "command": "aeris aero sweep",
                "solver": solver,
                "requested_n_cases": sweep_result.summary.get("requested_n_cases"),
                "completed_n_cases": sweep_result.summary.get("completed_n_cases"),
                "alpha_values": parsed_alpha_values or [alpha],
                "beta_values": parsed_beta_values or [beta],
                "velocity_values": parsed_velocity_values or [velocity],
                "altitude_values": parsed_altitude_values or [altitude],
                "control_input_values": parsed_control_input_values or ([control_input_deg] if control_input_deg is not None else []),
            },
        )
    elif workflow is not None:
        typer.echo(
            "[AERIS] Workflow aero_sweep stage was not auto-recorded "
            "because not all sweep cases succeeded."
        )


@aero_app.command("sweep-inspect")
def inspect_aero_sweep(
    run_dir: Path = typer.Option(
        ...,
        "--run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Existing aero sweep run directory or nested aero_sweep/ directory.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print saved aero sweep manifest/result as machine-readable JSON.",
    ),
) -> None:
    """Inspect a saved aero sweep summary by printing it, or as JSON with --json."""

    manifest = _load_aero_sweep_manifest(run_dir)
    sweep_result = manifest.get("aero_sweep_result", {}) or {}

    if as_json:
        typer.echo(json.dumps(sweep_result, indent=2))
        return

    typer.echo("")
    typer.echo(f"[AERIS] Inspecting aero sweep from: {run_dir}")
    _print_aero_sweep_result(sweep_result)


@aero_app.command("sweep-case-inspect")
def inspect_aero_sweep_case(
    run_dir: Path = typer.Option(
        ...,
        "--run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Existing aero sweep run directory or nested aero_sweep/ directory.",
    ),
    case_label: str = typer.Option(
        "",
        "--case-label",
        help="Exact sweep case label to inspect.",
    ),
    case_index: int | None = typer.Option(
        None,
        "--case-index",
        help="Sweep case index to inspect.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print saved aero case result as machine-readable JSON.",
    ),
) -> None:
    """Inspect a single case from a saved aero sweep by label or index."""

    case_dir = _resolve_sweep_case_dir(
        run_dir=run_dir,
        case_label=case_label.strip() or None,
        case_index=case_index,
    )

    result = load_aero_result_from_run_dir(case_dir)

    if as_json:
        typer.echo(json.dumps(asdict(result), indent=2))
        return

    typer.echo("")
    typer.echo(f"[AERIS] Inspecting aero sweep case from: {case_dir}")
    _print_aero_result(result)


@aero_app.command("cm-sanity")
def cm_sanity_command(
    dataset: Path | None = typer.Option(
        None,
        "--dataset",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Aero dataset root. Uses curated_aero_dataset.csv if present, else aero_dataset.csv.",
    ),
    csv_path: Path | None = typer.Option(
        None,
        "--csv",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Direct aero CSV path to check.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory for cm_sign_sanity_report.json. Defaults to no file output.",
    ),
    group_columns: str = typer.Option(
        "geometry_id,control_input_deg,velocity_mps,altitude_m,beta_deg,p_rad_s,q_rad_s,r_rad_s",
        "--group-columns",
        help="Comma-separated fixed-condition columns used before fitting Cm(alpha). Missing columns are ignored.",
    ),
    alpha_column: str = typer.Option("alpha_deg", "--alpha-column"),
    cm_column: str = typer.Option("cm", "--cm-column"),
    min_abs_cma_per_rad: float = typer.Option(
        1.0e-8,
        "--min-abs-cma-per-rad",
        help="Treat smaller |Cma| slopes as near-zero failures.",
    ),
    fail_on_violation: bool = typer.Option(
        False,
        "--fail-on-violation/--no-fail-on-violation",
        help="Exit non-zero if any evaluable group has unexpected Cma sign.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print full JSON report."),
) -> None:
    """Check whether Cm decreases with alpha within fixed-condition groups."""

    if (dataset is None) == (csv_path is None):
        raise typer.BadParameter("Provide exactly one of --dataset or --csv.")

    try:
        report = run_cm_sign_sanity(
            dataset=dataset,
            csv_path=csv_path,
            output_dir=output_dir,
            group_columns=group_columns,
            alpha_column=alpha_column,
            cm_column=cm_column,
            expected_negative=True,
            min_abs_cma_per_rad=min_abs_cma_per_rad,
        )
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc

    payload = report.to_dict()
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo("[AERIS] Cm sign sanity completed")
        typer.echo(f"  source_csv: {report.source_csv}")
        typer.echo(f"  expected_cma_sign: {report.expected_cma_sign}")
        typer.echo(f"  rows: {report.n_rows}")
        typer.echo(f"  groups_total: {report.n_groups_total}")
        typer.echo(f"  groups_evaluable: {report.n_groups_evaluable}")
        typer.echo(f"  groups_passed: {report.n_groups_passed}")
        typer.echo(f"  groups_failed: {report.n_groups_failed}")
        typer.echo(f"  groups_skipped: {report.n_groups_skipped}")
        typer.echo(f"  passed: {report.passed}")
        if output_dir is not None:
            typer.echo(f"  report_json: {Path(output_dir) / 'cm_sign_sanity_report.json'}")

    if fail_on_violation and not report.passed:
        raise typer.Exit(code=1)


@aero_app.command("pygeo-native")
def pygeo_native_aero(
    config: Path = typer.Option(..., "--config", "-c", help="pyGeo geometry config YAML."),
    alpha: float = typer.Option(..., "--alpha", help="Angle of attack (deg)."),
    velocity: float = typer.Option(28.0, "--velocity", help="Freestream velocity (m/s)."),
    altitude: float = typer.Option(0.0, "--altitude", help="Altitude (m)."),
    sections: int = typer.Option(25, "--sections", help="Spanwise extraction sections."),
    span_margin: float = typer.Option(
        0.0, "--span-margin",
        help="Inset of the extraction from both span ends (0 = full span; "
             "non-zero opens a centreline gap under YDUPLICATE).",
    ),
    nchordwise: int = typer.Option(
        24, "--nchordwise",
        help="AVL chordwise panels (DECISION-0009: 24; 16 is the economy setting; "
             "8 costs ~7.7% on elevon authority).",
    ),
    spanwise_panels: int = typer.Option(
        4, "--spanwise-panels", help="AVL spanwise panels per section interval."
    ),
    beta: float = typer.Option(0.0, "--beta", help="Sideslip angle (deg)."),
    control_input_deg: float = typer.Option(
        0.0, "--control-input-deg", help="Symmetric elevon deflection δe (pitch, deg)."
    ),
    diff_input_deg: float = typer.Option(
        0.0, "--diff-input-deg", help="Differential elevon deflection δa (roll, deg)."
    ),
    viscous: bool = typer.Option(
        True, "--viscous/--no-viscous", help="Apply the NeuralFoil viscous correction."
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Output dir (default: a new run folder)."
    ),
) -> None:
    """pyGeo geometry -> native AVL + NeuralFoil viscous, WITHOUT building an asb.Airplane.

    Authors the .avl directly from the pyGeo realized sections and drives the
    viscous correction from section coordinates (NeuralFoilCoordinateSource).
    AeroSandbox is never used to build an airplane on this path.
    """
    from aeris.aero.models import FlightCondition
    from aeris.common.paths import create_run_folder
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
        run_pygeo_native_avl_case,
        summarize_pygeo_avl_qc,
    )

    if output_dir is None:
        out = create_run_folder(prefix="aero_pygeo_native").root
    else:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

    typer.echo("[AERIS aero] pyGeo -> native AVL + viscous (no asb.Airplane)")
    typer.echo(f"  config   : {config}")
    ex, semispan, meta = build_pygeo_sections_from_config(
        config, n_sections=sections, span_margin=span_margin
    )
    typer.echo(
        f"  sections : {len(ex)}  semispan: {semispan:.3f} m  "
        f"control: {bool(meta['control'])}"
    )

    fc = FlightCondition(
        alpha_deg=alpha, beta_deg=beta, velocity_mps=velocity, altitude_m=altitude
    )
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=out, extracted_sections=ex, semispan_m=semispan,
        control=meta["control"], control_input_deg=control_input_deg,
        diff_input_deg=diff_input_deg, viscous=viscous, name="pygeo_native",
        nchordwise=nchordwise, spanwise_panels_per_section=spanwise_panels,
    )
    qc = summarize_pygeo_avl_qc(res) if viscous else {}

    payload = {
        "config": str(config), "alpha_deg": alpha, "beta_deg": beta,
        "velocity_mps": velocity, "altitude_m": altitude,
        "span_margin": span_margin, "n_sections_requested": sections,
        "nchordwise": nchordwise, "spanwise_panels_per_section": spanwise_panels,
        "viscous": viscous, "status": res.status,
        "CL": res.cl, "CD": res.cd, "cd_ind": res.cd_ind, "cd_profile": res.cd_profile,
        "cd_total": res.cd_total, "cd_vis_avl": res.cd_vis, "cd_ff": res.cd_ff,
        "cm": res.cm, "cl_roll": res.cl_roll, "cn": res.cn, "cy": res.cy,
        "span_efficiency": res.span_efficiency, "x_np": res.x_np,
        "x_np_over_c_ref": res.x_np_over_c_ref, "static_margin": res.static_margin,
        "s_ref": res.s_ref, "c_ref": res.c_ref, "b_ref": res.b_ref,
        "n_strips": res.n_strips, "n_vortices": res.n_vortices,
        "stability_axis_derivatives": res.stability_axis_derivatives,
        "body_axis_derivatives": res.body_axis_derivatives,
        "control_derivatives": res.control_derivatives,
        "derived_metrics": res.derived_metrics,
        "hinge_moments": res.hinge_moments,
        "surface_forces": res.surface_forces,
        "l_over_d": res.l_over_d,
        "l_over_d_viscous": res.l_over_d_viscous, "n_cdcl_injected": res.n_cdcl_injected,
        "artifact_paths": res.artifact_paths,
        "qc": qc, "meta": meta, "warnings": res.warnings,
    }
    result_path = out / "pygeo_native_aero.json"
    result_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    typer.echo(f"  status   : {res.status}")
    typer.echo(f"  CL={res.cl}  cd_ind={res.cd_ind}  cd_profile={res.cd_profile}")
    typer.echo(f"  cd_total={res.cd_total}  L/D_visc={res.l_over_d_viscous}")
    typer.echo(
        f"  e={res.span_efficiency}  Xnp={res.x_np}  Xnp/Cref={res.x_np_over_c_ref}"
    )
    stab = res.stability_axis_derivatives or {}
    typer.echo(
        f"  CLa={stab.get('CLa')}  Cma={stab.get('Cma')}  "
        f"Clb={stab.get('Clb')}  Cnb={stab.get('Cnb')}  Clp={stab.get('Clp')}"
    )
    if res.control_derivatives:
        for cname, cderivs in res.control_derivatives.items():
            typer.echo(
                f"  {cname}: CL_d={cderivs.get('CL')} Cm_d={cderivs.get('Cm')} "
                f"Cl_d={cderivs.get('Cl')}  Chinge={res.hinge_moments.get(cname)}"
            )
    if qc:
        typer.echo(f"  QC pass={qc.get('pass')}  drag_agree={qc.get('drag_agreement_rel_diff')}")
    for w in res.warnings:
        typer.echo(f"  WARN     : {w}")
    typer.echo(f"  result   : {result_path}")
    if res.status != "SUCCESS":
        raise typer.Exit(code=1)

