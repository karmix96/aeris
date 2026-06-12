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
from aeris.commands._helpers import fail_command, parse_csv_list
from aeris.commands._workflow_recording import record_workflow_stage_success
from aeris.dataset.dynamics_labels import compute_dynamics_labels
from aeris.dynamics.analysis import build_dynamics_foundation_result
from aeris.dynamics.cg_sweep import run_cg_sweep, write_cg_sweep, write_cg_sweep_csv
from aeris.dynamics.config import load_mass_properties_config
from aeris.dynamics.io import write_dynamics_foundation_result
from aeris.dynamics.models import InertiaPlaceholders, MassProperties, TrimDefinition
from aeris.dynamics.state_space_run import (
    compute_state_space_result,
    find_state_space_result,
    read_state_space_result,
    write_state_space_result,
)

from aeris.dynamics.state_space_plots import render_state_space_plots
from aeris.dynamics.trim import estimate_longitudinal_trim, write_trim_result
from aeris.dynamics.validation import validate_dynamics_run, write_dynamics_validation_report


dynamics_app = typer.Typer(help="Mass / CG / dynamics-foundation utilities.")


@dynamics_app.callback()
def dynamics_callback() -> None:
    """Dynamics command group."""
    pass



@dynamics_app.command("batch-labels")
def dynamics_batch_labels(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to an existing unified aero dataset root.",
    ),
    source: str = typer.Option(
        "auto",
        "--source",
        help="Input aero CSV policy passed to the batch label chain. Options: auto, curated, raw.",
    ),
    control_column: str | None = typer.Option(
        None,
        "--control-column",
        help="Symmetric elevon control column. Defaults to delta_e_sym_deg, falling back to control_input_deg.",
    ),
    group_columns: str | None = typer.Option(
        None,
        "--group-columns",
        help="Optional comma-separated condition grouping columns shared by control/flyability labels.",
    ),
    targets: str | None = typer.Option(
        None,
        "--targets",
        help="Optional comma-separated target columns for control-derivative computation.",
    ),
    cm_column: str = typer.Option(
        "cm",
        "--cm-column",
        help="Pitching-moment coefficient column used for trim/flyability labels.",
    ),
    recompute_control_derivatives: bool = typer.Option(
        True,
        "--recompute-control-derivatives/--no-recompute-control-derivatives",
        help="Recompute control derivatives before batch labels, or reuse existing control_derivatives.csv.",
    ),
    max_abs_trim_delta_e_deg: float = typer.Option(
        25.0,
        "--max-abs-trim-delta-e-deg",
        help="Symmetric elevon deflection limit used for first-order trim feasibility.",
    ),
    min_abs_cm_delta_e: float = typer.Option(
        0.10,
        "--min-abs-cm-delta-e-per-rad",
        help="Pitch-authority threshold for |Cm_delta_e_per_rad|.",
    ),
    alpha_min_deg: float = typer.Option(
        -5.0,
        "--alpha-min-deg",
        help="Lower alpha bound for optional alpha-trim feasibility when Cma is available.",
    ),
    alpha_max_deg: float = typer.Option(
        15.0,
        "--alpha-max-deg",
        help="Upper alpha bound for optional alpha-trim feasibility when Cma is available.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the full batch-label report as JSON.",
    ),
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root; auto-records stage dynamics_batch_labels when this command succeeds.",
    ),
) -> None:
    """Generate dataset-level dynamics/flyability labels from a promoted aero dataset.

    This is the DYN-2 bridge: it turns a control-aware aero dataset into
    dataset-level labels suitable for later ML/MDAO screening. It deliberately
    reuses the dataset D2/D3 label modules instead of reimplementing physics in
    the CLI layer.
    """
    parsed_group_columns = None if group_columns is None else parse_csv_list(group_columns, "--group-columns")
    parsed_targets = None if targets is None else parse_csv_list(targets, "--targets")

    try:
        report = compute_dynamics_labels(
            dataset_root=dataset,
            source=source,
            control_column=control_column,
            group_columns=parsed_group_columns,
            target_columns=parsed_targets,
            cm_column=cm_column,
            recompute_control_derivatives=recompute_control_derivatives,
            max_abs_trim_delta_e_deg=max_abs_trim_delta_e_deg,
            min_abs_cm_delta_e=min_abs_cm_delta_e,
            alpha_min_deg=alpha_min_deg,
            alpha_max_deg=alpha_max_deg,
        )
    except Exception as exc:
        fail_command("Dynamics batch-labels", exc)


    try:
        record_workflow_stage_success(
            workflow=workflow,
            stage="dynamics_batch_labels",
            inputs=[dataset],
            outputs=list((report.get("artifacts", {}) or {}).values()),
            artifacts=list((report.get("artifacts", {}) or {}).values()),
            notes="Computed control derivatives and first-order flyability labels from an aero dataset.",
            metadata={
                "source": report.get("source"),
                "overall_status": report.get("overall_status"),
                "label_summary": report.get("label_summary", {}),
                "thresholds": report.get("thresholds", {}),
            },
            echo=not as_json,
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)

    if as_json:
        typer.echo(json.dumps(report, indent=2))
        return

    label_summary = report.get("label_summary", {}) or {}
    stages = report.get("stages", {}) or {}
    artifacts = report.get("artifacts", {}) or {}

    typer.echo("[AERIS] Dynamics batch labels completed")
    typer.echo(f"  dataset_root: {report.get('dataset_root')}")
    typer.echo(f"  source: {report.get('source')}")
    typer.echo(f"  overall_status: {report.get('overall_status')}")
    typer.echo("  stages:")
    for name in ("control_derivatives", "flyability_labels"):
        stage = stages.get(name, {}) or {}
        typer.echo(
            f"    - {name}: status={stage.get('status')}, mode={stage.get('mode')}"
        )
    typer.echo("  label_summary:")
    typer.echo(f"    computed_label_count: {label_summary.get('computed_label_count')}")
    typer.echo(f"    skipped_label_count: {label_summary.get('skipped_label_count')}")
    typer.echo(
        "    longitudinal_basic_flyable_true_count: "
        f"{label_summary.get('longitudinal_basic_flyable_true_count')}"
    )
    typer.echo(
        "    longitudinal_basic_flyable_false_count: "
        f"{label_summary.get('longitudinal_basic_flyable_false_count')}"
    )
    typer.echo(f"    red_flag_count: {label_summary.get('red_flag_count')}")
    typer.echo("  artifacts:")
    for key in (
        "control_derivatives_csv",
        "flyability_labels_csv",
        "dynamics_label_run_report_json",
    ):
        typer.echo(f"    {key}: {artifacts.get(key)}")


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
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root to auto-record the dynamics build stage after success.",
    ),
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
        typer.secho(
            "[ERROR] Need mass_kg and x_cg_m — supply via --mass-config or --mass-kg / --x-cg-m.",
            fg=typer.colors.RED,
        )
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

    try:
        record_workflow_stage_success(
            workflow=workflow,
            stage="dynamics_build",
            inputs=[run_dir],
            artifacts=[output_path],
            notes="Dynamics foundation built from aero run.",
            metadata={
                "command": "aeris dynamics build",
                "static_margin_percent_mac": getattr(
                    getattr(result, "stability_metrics", None), "static_margin_percent_mac", None
                ),
            },
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)

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
    json_output: bool = typer.Option(False, "--json", help="Print full trim result as JSON."),
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

    if json_output:
        import dataclasses as _dc
        try:
            typer.echo(json.dumps(_dc.asdict(result), indent=2))
        except Exception:
            typer.echo(json.dumps({"output_path": str(output_path)}, indent=2))
        return

    if not result.longitudinal.valid:
        typer.echo(f"[AERIS] Trim estimate invalid: {result.longitudinal.reason}")
        raise typer.Exit(code=1)

    typer.echo(f"[AERIS] Current alpha = {_fmt(result.longitudinal.alpha_current_deg)} deg")
    typer.echo(f"[AERIS] Current Cm = {_fmt(result.longitudinal.cm_current)}")
    typer.echo(f"[AERIS] Cma = {_fmt(result.longitudinal.cma_per_rad)}")
    typer.echo(f"[AERIS] Delta alpha trim = {_fmt(result.longitudinal.delta_alpha_deg)} deg")
    typer.echo(f"[AERIS] Estimated trim alpha = {_fmt(result.longitudinal.alpha_trim_deg)} deg")


@dynamics_app.command("state-space")
def dynamics_state_space(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory containing aero_result.json"),
    mass_config: Path | None = typer.Option(None, exists=True, file_okay=True, dir_okay=False, resolve_path=True, help="Path to mass-properties YAML/JSON config"),
    mass_kg: float | None = typer.Option(None, help="Aircraft mass [kg]"),
    x_cg_m: float | None = typer.Option(None, help="CG x [m]; accepted for consistency with other dynamics commands"),
    y_cg_m: float | None = typer.Option(None, help="CG y [m]"),
    z_cg_m: float | None = typer.Option(None, help="CG z [m]"),
    ixx_kg_m2: float | None = typer.Option(None, "--ixx-kg-m2"),
    iyy_kg_m2: float | None = typer.Option(None, "--iyy-kg-m2"),
    izz_kg_m2: float | None = typer.Option(None, "--izz-kg-m2"),
    ixz_kg_m2: float = typer.Option(0.0, "--ixz-kg-m2", help="Optional product of inertia Ixz [kg m^2]"),
    sref_m2: float | None = typer.Option(None, "--sref-m2", help="Override reference area [m^2] if geometry summary is unavailable"),
    mac_m: float | None = typer.Option(None, "--mac-m", help="Override mean aerodynamic chord [m] if geometry summary is unavailable"),
    span_m: float | None = typer.Option(None, "--span-m", help="Override reference span [m] if geometry summary is unavailable"),
    json_output: bool = typer.Option(False, "--json", help="Print full state-space result JSON"),
) -> None:
    """Compute full 4x4 longitudinal/lateral state-space eigenmodes for one aero run."""
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
    missing_mass = [
        name
        for name in ("mass_kg", "ixx_kg_m2", "iyy_kg_m2", "izz_kg_m2")
        if resolved[name] is None
    ]
    if missing_mass:
        typer.echo(
            "[AERIS] Need mass and principal inertias for state-space analysis: "
            + ", ".join(missing_mass)
        )
        raise typer.Exit(code=1)

    if resolved["x_cg_m"] is None:
        typer.secho(
            "[WARN] --x-cg-m not provided; defaulting to 0.0 m (nose reference). "
            "This gives a meaningless static margin. Provide --x-cg-m or --mass-config.",
            fg=typer.colors.YELLOW,
        )

    mass = MassProperties(
        mass_kg=resolved["mass_kg"],
        x_cg_m=resolved["x_cg_m"] if resolved["x_cg_m"] is not None else 0.0,
        y_cg_m=resolved["y_cg_m"],
        z_cg_m=resolved["z_cg_m"],
        inertia=InertiaPlaceholders(
            ixx_kg_m2=resolved["ixx_kg_m2"],
            iyy_kg_m2=resolved["iyy_kg_m2"],
            izz_kg_m2=resolved["izz_kg_m2"],
        ),
    )

    try:
        result = compute_state_space_result(
            run_dir=run_dir,
            mass_properties=mass,
            sref_m2=sref_m2,
            mac_m=mac_m,
            span_m=span_m,
            ixz_kg_m2=ixz_kg_m2,
        )
        output_path = write_state_space_result(result, run_dir / "dynamics")
    except Exception as exc:
        fail_command("Dynamics state-space", exc)

    if json_output:
        typer.echo(json.dumps(result, indent=2))
        return

    typer.echo("[AERIS] State-space analysis completed")
    typer.echo(f"  run_dir: {run_dir}")
    typer.echo(f"  overall_status: {result.get('overall_status')}")
    typer.echo(f"  output_report: {output_path}")

    stability_summary = result.get("linear_stability_summary", {}) or {}
    if stability_summary:
        typer.echo(
            "  linear_stability: "
            f"stable={stability_summary.get('overall_linear_stable')}, "
            f"unstable_eigenvalues={stability_summary.get('total_unstable_eigenvalue_count')}, "
            f"max_real={_fmt(stability_summary.get('max_real_eigenvalue'))}"
        )

    longitudinal = result.get("longitudinal", {})
    lateral = result.get("lateral_directional", {})
    typer.echo(f"  longitudinal_valid: {longitudinal.get('valid')}")
    if longitudinal.get("reason"):
        typer.echo(f"  longitudinal_reason: {longitudinal.get('reason')}")
    for mode_name in ("short_period", "phugoid"):
        mode = longitudinal.get(mode_name) or {}
        if mode:
            typer.echo(
                f"  {mode_name}: stable={mode.get('stable')}, "
                f"zeta={_fmt(mode.get('zeta'))}, omega_n={_fmt(mode.get('omega_n'))}"
            )

    typer.echo(f"  lateral_valid: {lateral.get('valid')}")
    if lateral.get("reason"):
        typer.echo(f"  lateral_reason: {lateral.get('reason')}")
    for mode_name in ("roll_subsidence", "spiral", "dutch_roll"):
        mode = lateral.get(mode_name) or {}
        if mode:
            typer.echo(
                f"  {mode_name}: stable={mode.get('stable')}, "
                f"real={_fmt(mode.get('eigenvalue_real'))}, imag={_fmt(mode.get('eigenvalue_imag'))}"
            )

    if result.get("overall_status") != "completed":
        missing = result.get("input_summary", {}).get("missing_inputs", [])
        if missing:
            typer.echo("  missing_inputs:")
            for item in missing:
                typer.echo(f"    - {item}")
        raise typer.Exit(code=1)


@dynamics_app.command("state-space-inspect")
def dynamics_state_space_inspect(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory"),
    json_output: bool = typer.Option(False, "--json", help="Print full state-space result JSON"),
) -> None:
    """Inspect state_space_result.json from a previous state-space run."""
    path = find_state_space_result(run_dir)
    if path is None:
        typer.echo("[AERIS] No state_space_result.json found.")
        raise typer.Exit(code=1)
    try:
        data = read_state_space_result(path)
    except Exception as exc:
        fail_command("Dynamics state-space-inspect", exc)

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    typer.echo("\n=== AERIS State-Space Inspection ===\n")
    typer.echo(f"Run dir: {run_dir}")
    typer.echo(f"Status: {data.get('overall_status')}")
    stability_summary = data.get("linear_stability_summary", {}) or {}
    if stability_summary:
        typer.echo(
            "Linear stability: "
            f"stable={stability_summary.get('overall_linear_stable')}, "
            f"unstable_eigenvalues={stability_summary.get('total_unstable_eigenvalue_count')}, "
            f"max_real={_fmt(stability_summary.get('max_real_eigenvalue'))}"
        )
    longitudinal = data.get("longitudinal", {})
    lateral = data.get("lateral_directional", {})
    typer.echo(f"Longitudinal valid: {longitudinal.get('valid')}")
    for mode_name in ("short_period", "phugoid"):
        mode = longitudinal.get(mode_name) or {}
        if mode:
            typer.echo(
                f"  {mode_name}: stable={mode.get('stable')}, "
                f"zeta={_fmt(mode.get('zeta'))}, omega_n={_fmt(mode.get('omega_n'))}, "
                f"real={_fmt(mode.get('eigenvalue_real'))}, imag={_fmt(mode.get('eigenvalue_imag'))}"
            )
    typer.echo(f"Lateral valid: {lateral.get('valid')}")
    for mode_name in ("roll_subsidence", "spiral", "dutch_roll"):
        mode = lateral.get(mode_name) or {}
        if mode:
            typer.echo(
                f"  {mode_name}: stable={mode.get('stable')}, "
                f"real={_fmt(mode.get('eigenvalue_real'))}, imag={_fmt(mode.get('eigenvalue_imag'))}, "
                f"zeta={_fmt(mode.get('zeta'))}"
            )
    missing = data.get("input_summary", {}).get("missing_inputs", [])
    if missing:
        typer.echo("Missing inputs:")
        for item in missing:
            typer.echo(f"  - {item}")
    typer.echo("\n====================================\n")


@dynamics_app.command("plot-state-space")
def dynamics_plot_state_space(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory containing dynamics/state_space_result.json"),
    plot: str = typer.Option(
        "all",
        "--plot",
        help="Plot to generate: all, eigenvalues, eigenvalues-zoom, mode-summary, or mode-summary-zoom.",
    ),
    output_dir: Path | None = typer.Option(None, file_okay=False, dir_okay=True, resolve_path=True, help="Optional output directory. Defaults to <run_dir>/dynamics/plots."),
    dpi: int = typer.Option(180, "--dpi", min=72, max=600, help="PNG resolution."),
    json_output: bool = typer.Option(False, "--json", help="Print the plot manifest JSON."),
) -> None:
    """Generate static PNG evidence plots from a saved state-space result."""
    try:
        manifest = render_state_space_plots(
            run_dir=run_dir,
            plot=plot,
            output_dir=output_dir,
            dpi=dpi,
        )
    except Exception as exc:
        fail_command("Dynamics plot-state-space", exc)

    if json_output:
        typer.echo(json.dumps(manifest, indent=2))
        return

    typer.echo("[AERIS] State-space plots generated")
    typer.echo(f"  run_dir: {run_dir}")
    typer.echo(f"  requested_plot: {manifest.get('requested_plot')}")
    typer.echo(f"  plot_count: {manifest.get('plot_count')}")
    stability_summary = manifest.get("linear_stability_summary") or {}
    if stability_summary:
        typer.echo(
            "  linear_stability: "
            f"stable={stability_summary.get('overall_linear_stable')}, "
            f"unstable_eigenvalues={stability_summary.get('total_unstable_eigenvalue_count')}, "
            f"max_real={_fmt(stability_summary.get('max_real_eigenvalue'))}"
        )
    artifacts = manifest.get("artifacts", {}) or {}
    for label, path in artifacts.items():
        if path:
            typer.echo(f"  {label}: {path}")
    typer.echo(f"  manifest: {manifest.get('manifest_path')}")


@dynamics_app.command("validate")
def dynamics_validate(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory containing dynamics artifacts"),
    json_output: bool = typer.Option(False, "--json", help="Print full validation report JSON"),
    fail_on_error: bool = typer.Option(False, "--fail-on-error", help="Exit with code 1 if validation errors are found"),
) -> None:
    """Validate saved dynamics artifacts for formula/schema/eigenvalue consistency."""
    try:
        report = validate_dynamics_run(run_dir)
        output_path = write_dynamics_validation_report(report, run_dir / "dynamics")
    except Exception as exc:
        fail_command("Dynamics validate", exc)

    if json_output:
        typer.echo(json.dumps(report, indent=2))
        if fail_on_error and not report.get("passed"):
            raise typer.Exit(code=1)
        return

    typer.echo("[AERIS] Dynamics validation completed")
    typer.echo(f"  run_dir: {run_dir}")
    typer.echo(f"  passed: {report.get('passed')}")
    typer.echo(f"  errors: {report.get('error_count')}")
    typer.echo(f"  warnings: {report.get('warning_count')}")
    typer.echo(f"  report: {output_path}")

    for error in report.get("errors", [])[:8]:
        typer.echo(f"  ERROR: {error}")
    extra_errors = len(report.get("errors", [])) - 8
    if extra_errors > 0:
        typer.echo(f"  ... {extra_errors} more error(s) in report")

    for warning in report.get("warnings", [])[:8]:
        typer.echo(f"  WARNING: {warning}")
    extra_warnings = len(report.get("warnings", [])) - 8
    if extra_warnings > 0:
        typer.echo(f"  ... {extra_warnings} more warning(s) in report")

    if fail_on_error and not report.get("passed"):
        raise typer.Exit(code=1)


@dynamics_app.command("inspect")
def dynamics_inspect(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Run directory"),
    json_output: bool = typer.Option(False, "--json", help="Print full dynamics_foundation.json as JSON."),
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

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

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
    json_output: bool = typer.Option(False, "--json", help="Print full cg_sweep.json as JSON."),
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

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

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

@dynamics_app.command("build-ml-dataset")
def dynamics_build_ml_dataset(
    dataset: Path = typer.Option(..., "--dataset", exists=True, file_okay=False, dir_okay=True, resolve_path=True, help="Promoted aero dataset root with flyability_labels.csv"),
    source: str = typer.Option("curated", "--source", help="Input aero table source: curated or raw."),
    output_dir: Path | None = typer.Option(None, "--output-dir", file_okay=False, dir_okay=True, resolve_path=True, help="Output dataset root. Defaults to <dataset_parent>/<dataset_name>__flyability_ml."),
    allow_forced: bool = typer.Option(False, "--allow-forced", help="Allow source dataset if it was force-promoted."),
    zero_control_value_deg: float = typer.Option(0.0, "--zero-control-value-deg", help="Symmetric elevon value used as the ML row anchor."),
    zero_control_tolerance_deg: float = typer.Option(1.0e-9, "--zero-control-tolerance-deg", help="Tolerance for matching the zero-control row."),
    json_output: bool = typer.Option(False, "--json", help="Print full JSON report."),
    workflow: Path | None = typer.Option(
        None,
        "--workflow",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional workflow root; auto-records stage flyability_ml_dataset when this command succeeds.",
    ),
) -> None:
    """Build an ML-ready derived dataset by joining zero-control aero rows with flyability labels."""
    try:
        if source not in {"curated", "raw"}:
            raise typer.BadParameter("--source must be 'curated' or 'raw'.")
        from aeris.dataset.flyability_ml_dataset import build_flyability_ml_dataset

        report = build_flyability_ml_dataset(
            dataset_root=dataset,
            source=source,  # type: ignore[arg-type]
            output_dir=output_dir,
            allow_forced=allow_forced,
            zero_control_value_deg=zero_control_value_deg,
            zero_control_tolerance_deg=zero_control_tolerance_deg,
        )
    except Exception as exc:
        fail_command("Dynamics build-ml-dataset", exc)


    try:
        record_workflow_stage_success(
            workflow=workflow,
            stage="flyability_ml_dataset",
            inputs=[dataset, report.get("source_flyability_labels_csv"), report.get("source_control_derivatives_csv")],
            outputs=[report.get("output_dir"), report.get("output_curated_csv"), report.get("output_alias_csv")],
            artifacts=list((report.get("artifacts", {}) or {}).values()),
            notes="Built an ML-ready flyability dataset from zero-control aero rows and flyability labels.",
            metadata={
                "source": report.get("source"),
                "status": report.get("status"),
                "row_counts": report.get("row_counts", {}),
                "ml_columns": report.get("ml_columns", {}),
            },
            echo=not json_output,
        )
    except Exception as exc:
        fail_command("Workflow auto-record", exc)

    if json_output:
        typer.echo(json.dumps(report, indent=2))
        return

    typer.echo("[AERIS] Flyability ML dataset completed")
    typer.echo(f"  source_dataset: {report.get('dataset_root')}")
    typer.echo(f"  output_dir: {report.get('output_dir')}")
    typer.echo(f"  status: {report.get('status')}")
    rows = report.get("row_counts", {}) or {}
    typer.echo(f"  source_label_rows: {rows.get('source_label_rows')}")
    typer.echo(f"  joined_ml_rows: {rows.get('joined_ml_rows')}")
    typer.echo(f"  unmatched_label_rows: {rows.get('unmatched_label_rows')}")
    targets = (report.get("ml_columns", {}) or {}).get("label_targets_available", [])
    typer.echo("  label_targets_available: " + (", ".join(targets) if targets else "none"))
    artifacts = report.get("artifacts", {}) or {}
    typer.echo("  artifacts:")
    for key, value in artifacts.items():
        typer.echo(f"    {key}: {value}")
