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
from aeris.pipeline.aero_workflows import (
    execute_aero_run,
    execute_aero_sweep,
)

aero_app = typer.Typer(help="Aerodynamic analysis commands.")

_ALLOWED_SPACING = {"equal", "cosine"}


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


def _parse_float_list(value: str, option_name: str) -> list[float]:
    text = value.strip()
    if not text:
        return []

    values: list[float] = []
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError as exc:
            raise typer.BadParameter(
                f"Invalid float value '{token}' for {option_name}. "
                f"Use comma-separated numeric values, e.g. 0,2,4"
            ) from exc
    return values


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
        help="Control surface input in degrees (AVL d1 command).",
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
) -> None:
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
    )

    typer.echo("")
    typer.echo(f"[AERIS] Aero run completed in: {run_root}")
    _print_aero_result(result)


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
        help="Control surface input in degrees (AVL d1 command) applied to every sweep case.",
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
) -> None:
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

    source_policy = _resolve_source_policy(
        geometry_source=geometry_source,
        config_mode=config is not None,
    )

    parsed_alpha_values = _parse_float_list(alpha_values, "--alpha-values")
    parsed_beta_values = _parse_float_list(beta_values, "--beta-values")
    parsed_velocity_values = _parse_float_list(velocity_values, "--velocity-values")
    parsed_altitude_values = _parse_float_list(altitude_values, "--altitude-values")
    parsed_p_values = _parse_float_list(p_values, "--p-values")
    parsed_q_values = _parse_float_list(q_values, "--q-values")
    parsed_r_values = _parse_float_list(r_values, "--r-values")

    run_root, sweep_result = execute_aero_sweep(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        geometry_source=source_policy,
        generator_id=generator_id.strip() or None,
        control_input_deg=control_input_deg,
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