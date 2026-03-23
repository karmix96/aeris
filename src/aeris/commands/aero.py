"""
CLI commands for aerodynamic analysis and sweep inspection.

Responsibilities:
    - Expose aero run and sweep commands
    - Resolve geometry source mode for fresh and stored geometry
    - Delegate solver execution through the aero layer
    - Inspect and replay saved aero results

Notes:
    - This module is still heavier than ideal
    - Shared source-preparation logic is centralized here for now
    - Future cleanup should move workflow/IO/reporting helpers out of commands
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import typer

from aeris.aero import AeroInput, AeroSolverSettings, FlightCondition, create_solver
from aeris.aero.io import load_aero_result_from_run_dir
from aeris.aero.models import FlightConditionSweep
from aeris.aero.sweep_run import run_aero_sweep
from aeris.aero.views import (
    geometry_view_from_case,
    geometry_view_from_dataset_case,
    geometry_view_from_run_dir,
)
from aeris.common.config import load_yaml_config
from aeris.common.paths import create_run_folder
from aeris.geometry.config_resolver import resolve_generator_and_config

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


def _create_aero_run_root(output_name: str, label: str, prefix: str) -> tuple[Path, Path, Path]:
    suffix = output_name.strip() or label.strip()
    run_root = create_run_folder(prefix=f"{prefix}_{suffix}").root
    geometry_dir = run_root / "geometry"
    aero_dir = run_root / "aero"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    aero_dir.mkdir(parents=True, exist_ok=True)
    return run_root, geometry_dir, aero_dir


def _sample_one(generator_id: str, typed_config: Any, seed: int) -> Any:
    from aeris.geometry.registry import get_geometry_generator

    generator = get_geometry_generator(generator_id)
    return generator.sample_one(typed_config, seed=seed)


def _run_full_case(
    generator_id: str,
    sample: Any,
    typed_config: Any,
    output_dir: Path,
    save_plot: bool,
    build_aerosandbox: bool,
) -> Any:
    from aeris.geometry.registry import get_geometry_generator

    generator = get_geometry_generator(generator_id)
    return generator.run_full_case(
        sample=sample,
        config=typed_config,
        output_dir=output_dir,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
    )


def _summarize_case(generator_id: str, case: Any) -> Any:
    from aeris.geometry.registry import get_geometry_generator

    generator = get_geometry_generator(generator_id)
    return generator.summarize_case(case)


def _prepare_geometry_source(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
    source_policy: str,
    seed: int,
    geometry_dir: Path,
    copy_config_to: Path | None = None,
) -> tuple[Any, str, Any]:
    generator_id = "bwb_segmented_v1"
    summary: Any = {}
    geometry_view = None

    if config is not None:
        raw_config = load_yaml_config(config)
        generator_id, typed_config = resolve_generator_and_config(raw_config)

        sample = _sample_one(generator_id=generator_id, typed_config=typed_config, seed=seed)
        case = _run_full_case(
            generator_id=generator_id,
            sample=sample,
            typed_config=typed_config,
            output_dir=geometry_dir,
            save_plot=False,
            build_aerosandbox=True,
        )
        summary = _summarize_case(generator_id=generator_id, case=case)

        geometry_view = geometry_view_from_case(
            case=case,
            generator_id=generator_id,
            case_dir=geometry_dir,
            source_policy=source_policy,
        )

        if copy_config_to is not None and config.exists():
            shutil.copy2(config, copy_config_to / config.name)

        return geometry_view, generator_id, summary

    if run_dir is not None:
        geometry_view = geometry_view_from_run_dir(
            run_dir=run_dir,
            generator_id=generator_id,
        )
        summary = {
            "source_mode": "run_dir",
            "run_dir": str(run_dir.resolve()),
        }
        return geometry_view, generator_id, summary

    geometry_view = geometry_view_from_dataset_case(
        dataset_root=dataset,
        geometry_id=geometry_id,
        generator_id=generator_id,
    )
    summary = {
        "source_mode": "dataset",
        "dataset_root": str(dataset.resolve()),
        "geometry_id": geometry_id,
    }
    return geometry_view, generator_id, summary


def _dataclass_or_value(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


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
    config: Path | None = typer.Option(None, "--config", "-c", help="Generate fresh geometry from config."),
    run_dir: Path | None = typer.Option(None, "--run-dir", help="Existing geometry run directory."),
    dataset: Path | None = typer.Option(None, "--dataset", help="Existing dataset root."),
    geometry_id: str = typer.Option("", "--geometry-id", help="Geometry ID inside dataset root."),
    geometry_source: str = typer.Option("auto", "--geometry-source", help="auto | native | reconstruct"),
    alpha: float = typer.Option(..., "--alpha"),
    velocity: float = typer.Option(28.0, "--velocity"),
    altitude: float = typer.Option(0.0, "--altitude"),
    beta: float = typer.Option(0.0, "--beta"),
    mach: float = typer.Option(0.0, "--mach"),
    p: float = typer.Option(0.0, "--p", help="Body roll rate in rad/s."),
    q: float = typer.Option(0.0, "--q", help="Body pitch rate in rad/s."),
    r: float = typer.Option(0.0, "--r", help="Body yaw rate in rad/s."),
    solver: str = typer.Option("aerosandbox_avl", "--solver"),
    avl_command: str = typer.Option("", "--avl-command"),
    timeout_sec: int = typer.Option(180, "--timeout-sec"),
    spanwise_resolution: int = typer.Option(4, "--spanwise-resolution"),
    chordwise_resolution: int = typer.Option(8, "--chordwise-resolution"),
    spanwise_spacing: str = typer.Option("equal", "--spanwise-spacing"),
    chordwise_spacing: str = typer.Option("cosine", "--chordwise-spacing"),
    save_surface_forces: bool = typer.Option(False, "--save-surface-forces"),
    save_element_forces: bool = typer.Option(False, "--save-element-forces"),
    seed: int = typer.Option(0, "--seed"),
    output_name: str = typer.Option("", "--output-name"),
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

    label = (
        config.stem if config is not None
        else run_dir.name if run_dir is not None
        else geometry_id
    )

    run_root, geometry_dir, aero_dir = _create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero",
    )

    geometry_view, _generator_id, summary = _prepare_geometry_source(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=source_policy,
        seed=seed,
        geometry_dir=geometry_dir,
        copy_config_to=run_root,
    )

    aero_input = AeroInput(
        geometry=geometry_view,
        flight_condition=FlightCondition(
            alpha_deg=alpha,
            beta_deg=beta,
            mach=mach,
            velocity_mps=velocity,
            altitude_m=altitude,
            p_rad_s=p,
            q_rad_s=q,
            r_rad_s=r,
        ),
        settings=AeroSolverSettings(
            avl_command=avl_command or None,
            timeout_sec=timeout_sec,
            verbose=False,
            solver_options={
                "paneling": {
                    "spanwise_resolution": spanwise_resolution,
                    "chordwise_resolution": chordwise_resolution,
                    "spanwise_spacing": spanwise_spacing,
                    "chordwise_spacing": chordwise_spacing,
                },
                "save_surface_forces": save_surface_forces,
                "save_element_forces": save_element_forces,
            },
        ),
        provenance={
            "solver": solver,
            "seed": seed,
            "geometry_source": source_policy,
            "source_label": label,
        },
    )

    solver_instance = create_solver(solver)
    result = solver_instance.run_case(aero_input=aero_input, output_dir=aero_dir)

    manifest = {
        "run_name": run_root.name,
        "solver": solver,
        "geometry_source": source_policy,
        "flight_condition": _to_jsonable(asdict(aero_input.flight_condition)),
        "geometry_summary": _to_jsonable(_dataclass_or_value(summary)),
        "aero_result": _to_jsonable(_dataclass_or_value(result)),
    }
    (run_root / "aero_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
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
        help="Path to an existing aero run directory or its nested aero/ directory.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the saved aero result as machine-readable JSON.",
    ),
) -> None:
    result = load_aero_result_from_run_dir(run_dir)

    if as_json:
        typer.echo(json.dumps(_to_jsonable(asdict(result)), indent=2))
        return

    typer.echo("")
    typer.echo(f"[AERIS] Inspecting aero result from: {run_dir}")
    _print_aero_result(result)


@aero_app.command("sweep")
def sweep_aero(
    config: Path | None = typer.Option(None, "--config", "-c", help="Generate fresh geometry from config."),
    run_dir: Path | None = typer.Option(None, "--run-dir", help="Existing geometry run directory."),
    dataset: Path | None = typer.Option(None, "--dataset", help="Existing dataset root."),
    geometry_id: str = typer.Option("", "--geometry-id", help="Geometry ID inside dataset root."),
    geometry_source: str = typer.Option("auto", "--geometry-source", help="auto | native | reconstruct"),
    alpha: float = typer.Option(0.0, "--alpha"),
    velocity: float = typer.Option(28.0, "--velocity"),
    altitude: float = typer.Option(0.0, "--altitude"),
    beta: float = typer.Option(0.0, "--beta"),
    mach: float = typer.Option(0.0, "--mach"),
    p: float = typer.Option(0.0, "--p", help="Body roll rate in rad/s."),
    q: float = typer.Option(0.0, "--q", help="Body pitch rate in rad/s."),
    r: float = typer.Option(0.0, "--r", help="Body yaw rate in rad/s."),
    alpha_values: str = typer.Option("", "--alpha-values", help="Comma-separated alpha sweep values."),
    beta_values: str = typer.Option("", "--beta-values", help="Comma-separated beta sweep values."),
    velocity_values: str = typer.Option("", "--velocity-values", help="Comma-separated velocity sweep values."),
    altitude_values: str = typer.Option("", "--altitude-values", help="Comma-separated altitude sweep values."),
    p_values: str = typer.Option("", "--p-values", help="Comma-separated p sweep values."),
    q_values: str = typer.Option("", "--q-values", help="Comma-separated q sweep values."),
    r_values: str = typer.Option("", "--r-values", help="Comma-separated r sweep values."),
    solver: str = typer.Option("aerosandbox_avl", "--solver"),
    avl_command: str = typer.Option("", "--avl-command"),
    timeout_sec: int = typer.Option(180, "--timeout-sec"),
    spanwise_resolution: int = typer.Option(4, "--spanwise-resolution"),
    chordwise_resolution: int = typer.Option(8, "--chordwise-resolution"),
    spanwise_spacing: str = typer.Option("equal", "--spanwise-spacing"),
    chordwise_spacing: str = typer.Option("cosine", "--chordwise-spacing"),
    save_surface_forces: bool = typer.Option(False, "--save-surface-forces"),
    save_element_forces: bool = typer.Option(False, "--save-element-forces"),
    seed: int = typer.Option(0, "--seed"),
    output_name: str = typer.Option("", "--output-name"),
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

    label = (
        config.stem if config is not None
        else run_dir.name if run_dir is not None
        else geometry_id
    )

    run_root, geometry_dir, sweep_dir = _create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero_sweep",
    )

    geometry_view, _generator_id, summary = _prepare_geometry_source(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=source_policy,
        seed=seed,
        geometry_dir=geometry_dir,
        copy_config_to=run_root,
    )

    base_fc = FlightCondition(
        alpha_deg=alpha,
        beta_deg=beta,
        mach=mach,
        velocity_mps=velocity,
        altitude_m=altitude,
        p_rad_s=p,
        q_rad_s=q,
        r_rad_s=r,
    )

    sweep = FlightConditionSweep(
        alpha_deg_values=_parse_float_list(alpha_values, "--alpha-values"),
        beta_deg_values=_parse_float_list(beta_values, "--beta-values"),
        velocity_mps_values=_parse_float_list(velocity_values, "--velocity-values"),
        altitude_m_values=_parse_float_list(altitude_values, "--altitude-values"),
        p_rad_s_values=_parse_float_list(p_values, "--p-values"),
        q_rad_s_values=_parse_float_list(q_values, "--q-values"),
        r_rad_s_values=_parse_float_list(r_values, "--r-values"),
    )

    settings = AeroSolverSettings(
        avl_command=avl_command or None,
        timeout_sec=timeout_sec,
        verbose=False,
        solver_options={
            "paneling": {
                "spanwise_resolution": spanwise_resolution,
                "chordwise_resolution": chordwise_resolution,
                "spanwise_spacing": spanwise_spacing,
                "chordwise_spacing": chordwise_spacing,
            },
            "save_surface_forces": save_surface_forces,
            "save_element_forces": save_element_forces,
        },
    )

    sweep_result = run_aero_sweep(
        geometry=geometry_view,
        base_flight_condition=base_fc,
        sweep=sweep,
        solver_id=solver,
        settings=settings,
        output_dir=sweep_dir,
        provenance={
            "solver": solver,
            "seed": seed,
            "geometry_source": source_policy,
            "source_label": label,
        },
    )

    manifest = {
        "run_name": run_root.name,
        "solver": solver,
        "geometry_source": source_policy,
        "base_flight_condition": _to_jsonable(asdict(base_fc)),
        "flight_condition_sweep": _to_jsonable(asdict(sweep)),
        "geometry_summary": _to_jsonable(_dataclass_or_value(summary)),
        "aero_sweep_result": _to_jsonable(_dataclass_or_value(sweep_result)),
    }
    (run_root / "aero_sweep_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    typer.echo("")
    typer.echo(f"[AERIS] Aero sweep completed in: {run_root}")
    _print_aero_sweep_result(_to_jsonable(_dataclass_or_value(sweep_result)))


@aero_app.command("sweep-inspect")
def inspect_aero_sweep(
    run_dir: Path = typer.Option(
        ...,
        "--run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to an existing aero sweep run directory or its nested aero_sweep/ directory.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the saved aero sweep manifest as machine-readable JSON.",
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
        help="Path to an existing aero sweep run directory or its nested aero_sweep/ directory.",
    ),
    case_label: str = typer.Option("", "--case-label", help="Exact sweep case label to inspect."),
    case_index: int | None = typer.Option(None, "--case-index", help="Sweep case index to inspect."),
    as_json: bool = typer.Option(False, "--json", help="Print the saved aero case result as machine-readable JSON."),
) -> None:
    case_dir = _resolve_sweep_case_dir(
        run_dir=run_dir,
        case_label=case_label.strip() or None,
        case_index=case_index,
    )

    result = load_aero_result_from_run_dir(case_dir)

    if as_json:
        typer.echo(json.dumps(_to_jsonable(asdict(result)), indent=2))
        return

    typer.echo("")
    typer.echo(f"[AERIS] Inspecting aero sweep case from: {case_dir}")
    _print_aero_result(result)