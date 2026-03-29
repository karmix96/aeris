"""
CLI commands for dataset generation, inspection, and unified aero-dataset workflows.

Responsibilities:
    - Expose dataset-related user commands
    - Validate basic CLI arguments
    - Delegate geometry-dataset and aero-dataset orchestration to workflow code
    - Provide operator-facing help that reflects current QC preset behavior

Notes:
    - This module must remain thin
    - No sampling, geometry, or aero business logic should live here
    - The unified aero-dataset workflow writes structured manifests, QC reports,
      and final_run_summary.json
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from aeris.dataset.inspect import inspect_dataset
from aeris.dataset.dataset_run import run_dataset_generation
from aeris.dataset.curate_aero import curate_aero_dataset
from aeris.quality.presets import list_qc_presets, resolve_qc_preset
from aeris.dataset.promote_aero import promote_aero_dataset
from aeris.dataset.promoted_dataset import require_promoted_aero_dataset
from aeris.dataset.aero_dataset_run import run_aero_dataset_generation
from aeris.dataset.training_data import load_training_data
from aeris.dataset.splitting import split_dataset
# keep your existing unified aero-dataset imports here

dataset_app = typer.Typer(
    help=(
        "Dataset generation and inspection commands.\n\n"
        "Use:\n"
        "- 'generate' for geometry-only datasets\n"
        "- 'inspect' for saved dataset summaries\n"
        "- 'aero-generate' for the unified geometry -> aero sweep -> CSV -> QC workflow"
    )
)


def _echo_resolved_qc_configuration(
    *,
    qc_preset: str,
    geometry_qc_profile: str | None = None,
    fail_on_geometry_qc_error: bool | None = None,
    aero_qc_profile: str | None = None,
    fail_on_aero_qc_error: bool | None = None,
) -> None:
    typer.echo("")
    typer.echo("[AERIS] Resolved QC configuration")
    typer.echo(f"  qc_preset: {qc_preset or 'none'}")

    if geometry_qc_profile is not None:
        typer.echo(f"  geometry_qc_profile: {geometry_qc_profile}")
    if fail_on_geometry_qc_error is not None:
        typer.echo(f"  fail_on_geometry_qc_error: {fail_on_geometry_qc_error}")

    if aero_qc_profile is not None:
        typer.echo(f"  aero_qc_profile: {aero_qc_profile}")
    if fail_on_aero_qc_error is not None:
        typer.echo(f"  fail_on_aero_qc_error: {fail_on_aero_qc_error}")

def _print_curation_report(report: dict) -> None:
    typer.echo("")
    typer.echo("[AERIS] Aero dataset curation completed")
    typer.echo(f"  dataset_root: {report.get('dataset_root')}")
    typer.echo(f"  kept_rows: {report.get('kept_rows')}")
    typer.echo(f"  rejected_rows: {report.get('rejected_rows')}")
    typer.echo(f"  kept_geometries: {report.get('kept_geometries')}")
    typer.echo(f"  rejected_geometries: {report.get('rejected_geometries')}")
    typer.echo(f"  geometry_qc_passed: {report.get('geometry_qc_passed')}")
    typer.echo(f"  aero_qc_passed: {report.get('aero_qc_passed')}")
    typer.echo(f"  qc_preset_used: {report.get('qc_preset_used')}")
    typer.echo(f"  promotion_ready: {report.get('promotion_ready')}")

    blockers = report.get("promotion_blockers", []) or []
    if blockers:
        typer.echo("  promotion_blockers:")
        for blocker in blockers:
            typer.echo(f"    - {blocker}")
    else:
        typer.echo("  promotion_blockers: []")

    reason_counts = report.get("rejection_reason_counts", {}) or {}
    if reason_counts:
        typer.echo("  rejection_reason_counts:")
        for reason, count in sorted(reason_counts.items()):
            typer.echo(f"    - {reason}: {count}")

    typer.echo(f"  curated_csv: {report.get('curated_aero_dataset_csv')}")
    typer.echo(f"  rejected_csv: {report.get('rejected_aero_rows_csv')}")

def _print_promotion_manifest(manifest: dict) -> None:
    typer.echo("")
    typer.echo("[AERIS] Aero dataset promotion completed")
    typer.echo(f"  dataset_root: {manifest.get('dataset_root')}")
    typer.echo(f"  promoted_at_utc: {manifest.get('promoted_at_utc')}")
    typer.echo(
        f"  promotion_ready_at_time_of_promotion: "
        f"{manifest.get('promotion_ready_at_time_of_promotion')}"
    )
    typer.echo(f"  promotion_forced: {manifest.get('promotion_forced')}")

    qc_context = manifest.get("qc_context", {}) or {}
    typer.echo(f"  qc_preset_used: {qc_context.get('qc_preset_used')}")
    typer.echo(f"  geometry_qc_passed: {qc_context.get('geometry_qc_passed')}")
    typer.echo(f"  aero_qc_passed: {qc_context.get('aero_qc_passed')}")

    blockers = manifest.get("promotion_blockers", []) or []
    if blockers:
        typer.echo("  promotion_blockers:")
        for blocker in blockers:
            typer.echo(f"    - {blocker}")
    else:
        typer.echo("  promotion_blockers: []")

    artifacts = manifest.get("artifacts", {}) or {}
    typer.echo(f"  curated_csv: {artifacts.get('curated_aero_dataset_csv')}")
    typer.echo(
        f"  promotion_manifest: "
        f"{Path(manifest.get('dataset_root')) / 'promotion_manifest.json'}"
    )

def _print_promoted_dataset_context(context: dict) -> None:
    manifest = context.get("promotion_manifest", {}) or {}
    qc_context = manifest.get("qc_context", {}) or {}

    typer.echo("")
    typer.echo("[AERIS] Promoted dataset gate check")
    typer.echo(f"  dataset_root: {context.get('dataset_root')}")
    typer.echo(f"  curated_csv: {context.get('curated_aero_dataset_csv')}")
    typer.echo(f"  promotion_manifest_path: {context.get('promotion_manifest_path')}")
    typer.echo(f"  promotion_forced: {manifest.get('promotion_forced')}")
    typer.echo(
        f"  promotion_ready_at_time_of_promotion: "
        f"{manifest.get('promotion_ready_at_time_of_promotion')}"
    )
    typer.echo(f"  qc_preset_used: {qc_context.get('qc_preset_used')}")
    typer.echo(f"  geometry_qc_passed: {qc_context.get('geometry_qc_passed')}")
    typer.echo(f"  aero_qc_passed: {qc_context.get('aero_qc_passed')}")

    blockers = manifest.get("promotion_blockers", []) or []
    if blockers:
        typer.echo("  promotion_blockers:")
        for blocker in blockers:
            typer.echo(f"    - {blocker}")
    else:
        typer.echo("  promotion_blockers: []")

@dataset_app.command("qc")
def dataset_qc(
    dataset: Path = typer.Option(..., "--dataset"),
    profile: str = typer.Option("basic", "--profile"),
) -> None:
    """Run geometry dataset QC on an existing dataset."""
    report = run_geometry_dataset_qc(dataset, profile=profile)

    typer.echo(f"[AERIS] Geometry QC passed: {report['passed']}")
    typer.echo(f"Errors: {len(report['errors'])}")

    if not report["passed"]:
        raise typer.Exit(code=1)

@dataset_app.command("promote-aero")
def dataset_promote_aero(
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
    force: bool = typer.Option(
        False,
        "--force",
        help="Force promotion even if curation_report.json says promotion_ready=false.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the full promotion manifest as JSON.",
    ),
) -> None:
    """Promote a curated aero dataset by writing promotion_manifest.json."""
    try:
        manifest = promote_aero_dataset(
            dataset_root=dataset,
            force=force,
        )
    except Exception as exc:
        raise typer.BadParameter(str(exc))

    if as_json:
        typer.echo(json.dumps(manifest, indent=2))
        return

    _print_promotion_manifest(manifest)

    typer.echo("")
    if manifest.get("promotion_forced"):
        typer.echo("[AERIS] Promotion decision: FORCED")
    else:
        typer.echo("[AERIS] Promotion decision: APPROVED")

@dataset_app.command("aero-qc")
def dataset_aero_qc(
    dataset: Path = typer.Option(..., "--dataset"),
    profile: str = typer.Option("basic", "--profile"),
) -> None:
    """Run aero dataset QC on an existing dataset."""
    report = run_aero_dataset_qc(dataset, profile=profile)

    typer.echo(f"[AERIS] Aero QC passed: {report['passed']}")
    typer.echo(f"Errors: {len(report['errors'])}")

    if not report["passed"]:
        raise typer.Exit(code=1)


@dataset_app.callback()
def dataset_callback() -> None:
    """Dataset command group."""
    pass


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
                f"Use comma-separated numeric values, e.g. -5,0,5"
            ) from exc
    return values


@dataset_app.command("generate")
def dataset_generate(
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
    n: int = typer.Option(
        ...,
        "--n",
        min=1,
        help="Number of geometries to generate.",
    ),
    sampler: str | None = typer.Option(
        None,
        "--sampler",
        help="Dataset sampler (e.g. lhs_v1). Defaults to config or lhs_v1.",
    ),
    sampler_seed: int | None = typer.Option(
        None,
        "--sampler-seed",
        help="Seed for the selected sampler.",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Optional dataset folder name. If omitted, a deterministic name is used.",
    ),
    save_plot: bool | None = typer.Option(
        None,
        "--save-plot/--no-save-plot",
        help="Override config plotting behavior.",
    ),
    build_aerosandbox: bool | None = typer.Option(
        None,
        "--build-aerosandbox/--no-build-aerosandbox",
        help="Override config AeroSandbox behavior.",
    ),
    run_qc: bool = typer.Option(
        False,
        "--run-qc/--no-run-qc",
        help="Run QC checks after geometry dataset generation.",
    ),
    qc_profile: str = typer.Option(
        "basic",
        "--qc-profile",
        help="Geometry QC profile name.",
    ),
    qc_preset: str = typer.Option(
        "",
        "--qc-preset",
        help=(
            "Named QC preset for geometry dataset generation. "
            f"Valid: {', '.join(list_qc_presets())}. "
            "When provided, this overrides --qc-profile and "
            "--fail-on-qc-error. "
            "Examples: "
            "--qc-preset debug for exploratory runs, "
            "--qc-preset production for normal batch generation, "
            "--qc-preset promotion_strict before accepting/promoting a dataset."
        ),
    ),
    fail_on_qc_error: bool = typer.Option(
        False,
        "--fail-on-qc-error/--allow-qc-errors",
        help="Exit nonzero if geometry QC fails.",
    ),
) -> None:
    """Generate a batch geometry dataset using a modular sampling strategy."""
    preset = resolve_qc_preset(qc_preset)

    run_qc_effective = run_qc
    qc_profile_effective = qc_profile
    fail_on_qc_error_effective = fail_on_qc_error

    if preset is not None:
        run_qc_effective = preset.run_geometry_qc
        qc_profile_effective = preset.geometry_qc_profile
        fail_on_qc_error_effective = preset.fail_on_geometry_qc_error

    _echo_resolved_qc_configuration(
        qc_preset=qc_preset,
        geometry_qc_profile=qc_profile_effective,
        fail_on_geometry_qc_error=fail_on_qc_error_effective,
    )

    exit_code = run_dataset_generation(
        config_path=config,
        n_samples=n,
        sampler=sampler,
        sampler_seed=sampler_seed,
        dataset_name=name,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
        run_qc=run_qc_effective,
        qc_profile=qc_profile_effective,
        fail_on_qc_error=fail_on_qc_error_effective,
    )
    raise typer.Exit(code=exit_code)

@dataset_app.command("aero-generate")
def dataset_aero_generate(
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
    n: int = typer.Option(
        ...,
        "--n",
        min=1,
        help="Number of geometries to generate before aerodynamic evaluation.",
    ),
    sampler: str | None = typer.Option(
        None,
        "--sampler",
        help="Dataset sampler (e.g. lhs_v1). Defaults to config or lhs_v1.",
    ),
    sampler_seed: int | None = typer.Option(
        None,
        "--sampler-seed",
        help="Seed for the selected sampler.",
    ),
    name: str = typer.Option(
        ...,
        "--name",
        help="Final aero-dataset folder name under data/datasets/.",
    ),
    save_plot: bool | None = typer.Option(
        None,
        "--save-plot/--no-save-plot",
        help="Override geometry plotting behavior during dataset generation.",
    ),
    build_aerosandbox: bool | None = typer.Option(
        True,
        "--build-aerosandbox/--no-build-aerosandbox",
        help="Override config AeroSandbox behavior for geometry generation.",
    ),
    alpha_values: str = typer.Option(
        "",
        "--alpha-values",
        help="Comma-separated alpha sweep values, e.g. -2,0,2,4",
    ),
    beta_values: str = typer.Option(
        "",
        "--beta-values",
        help="Comma-separated beta sweep values, e.g. 0,2,4",
    ),
    velocity_values: str = typer.Option(
        "",
        "--velocity-values",
        help="Comma-separated velocity sweep values, e.g. 20,28,35",
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
    control_input_values: str = typer.Option(
        "",
        "--control-input-values",
        help="Comma-separated control-input values, e.g. -5,0,5",
    ),
    solver: str = typer.Option(
        "aerosandbox_avl",
        "--solver",
        help="Registered aero solver ID.",
    ),
    avl_command: str = typer.Option(
        "",
        "--avl-command",
        help="Optional AVL executable path/command.",
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
        help="AVL spanwise spacing override.",
    ),
    chordwise_spacing: str = typer.Option(
        "cosine",
        "--chordwise-spacing",
        help="AVL chordwise spacing override.",
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
    max_cases: int | None = typer.Option(
        None,
        "--max-cases",
        help="Optional safety cap on cases per geometry sweep.",
    ),
    keep_geometry_dataset: bool = typer.Option(
        True,
        "--keep-geometry-dataset/--delete-geometry-dataset",
        help="Keep or delete the intermediate geometry dataset after aero dataset creation.",
    ),
    retain_aero_runs: str = typer.Option(
        "all",
        "--retain-aero-runs",
        help="Retention mode for copied aero run folders: all, failures_only, or none.",
    ),
    run_geometry_qc: bool = typer.Option(
        False,
        "--run-geometry-qc/--no-run-geometry-qc",
        help="Run QC checks on the intermediate geometry dataset.",
    ),
    geometry_qc_profile: str = typer.Option(
        "basic",
        "--geometry-qc-profile",
        help="Geometry QC profile name.",
    ),
    fail_on_geometry_qc_error: bool = typer.Option(
        False,
        "--fail-on-geometry-qc-error/--allow-geometry-qc-errors",
        help="Exit nonzero if geometry QC fails.",
    ),
    run_aero_qc: bool = typer.Option(
        False,
        "--run-aero-qc/--no-run-aero-qc",
        help="Run QC checks on the generated aero dataset.",
    ),
    aero_qc_profile: str = typer.Option(
        "basic",
        "--aero-qc-profile",
        help="Aero QC profile name.",
    ),
    fail_on_aero_qc_error: bool = typer.Option(
        False,
        "--fail-on-aero-qc-error/--allow-aero-qc-errors",
        help="Exit nonzero if aero QC fails.",
    ),
    qc_preset: str = typer.Option(
        "",
        "--qc-preset",
        help=(
            "Named QC preset for unified aero dataset generation. "
            f"Valid: {', '.join(list_qc_presets())}. "
            "When provided, this overrides the explicit QC flags and profiles "
            "for both geometry and aero QC. "
            "Examples: "
            "--qc-preset debug for development/smoke runs, "
            "--qc-preset production for long unattended campaigns, "
            "--qc-preset promotion_strict before ML acceptance or dataset promotion."
        ),
    ),
) -> None:
    """Generate a unified aero dataset from a geometry config.

    This workflow:
    1. generates the intermediate geometry dataset
    2. runs aero/control sweeps for each geometry
    3. writes aero_dataset.csv and aero_failures.csv
    4. applies QC according to the selected preset/profile
    5. writes final manifests and final_run_summary.json

    Recommended presets:
    - debug
    - production
    - promotion_strict
    """
    parsed_alpha_values = _parse_float_list(alpha_values, "--alpha-values")
    parsed_beta_values = _parse_float_list(beta_values, "--beta-values")
    parsed_velocity_values = _parse_float_list(velocity_values, "--velocity-values")
    parsed_altitude_values = _parse_float_list(altitude_values, "--altitude-values")
    parsed_p_values = _parse_float_list(p_values, "--p-values")
    parsed_q_values = _parse_float_list(q_values, "--q-values")
    parsed_r_values = _parse_float_list(r_values, "--r-values")
    parsed_control_input_values = _parse_float_list(
        control_input_values,
        "--control-input-values",
    )

    if not parsed_alpha_values:
        raise typer.BadParameter("--alpha-values must not be empty.")
    if not parsed_velocity_values:
        raise typer.BadParameter("--velocity-values must not be empty.")
    if not parsed_altitude_values:
        raise typer.BadParameter("--altitude-values must not be empty.")
    if not parsed_control_input_values:
        raise typer.BadParameter("--control-input-values must not be empty.")

    preset = resolve_qc_preset(qc_preset)

    run_geometry_qc_effective = run_geometry_qc
    geometry_qc_profile_effective = geometry_qc_profile
    fail_on_geometry_qc_error_effective = fail_on_geometry_qc_error

    run_aero_qc_effective = run_aero_qc
    aero_qc_profile_effective = aero_qc_profile
    fail_on_aero_qc_error_effective = fail_on_aero_qc_error

    if preset is not None:
        run_geometry_qc_effective = preset.run_geometry_qc
        geometry_qc_profile_effective = preset.geometry_qc_profile
        fail_on_geometry_qc_error_effective = preset.fail_on_geometry_qc_error

        run_aero_qc_effective = preset.run_aero_qc
        aero_qc_profile_effective = preset.aero_qc_profile
        fail_on_aero_qc_error_effective = preset.fail_on_aero_qc_error

    _echo_resolved_qc_configuration(
        qc_preset=qc_preset,
        geometry_qc_profile=geometry_qc_profile_effective,
        fail_on_geometry_qc_error=fail_on_geometry_qc_error_effective,
        aero_qc_profile=aero_qc_profile_effective,
        fail_on_aero_qc_error=fail_on_aero_qc_error_effective,
    )

    exit_code = run_aero_dataset_generation(
        config_path=config,
        n_samples=n,
        sampler=sampler,
        sampler_seed=sampler_seed,
        dataset_name=name,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
        alpha_values=parsed_alpha_values,
        beta_values=parsed_beta_values,
        velocity_values=parsed_velocity_values,
        altitude_values=parsed_altitude_values,
        p_values=parsed_p_values,
        q_values=parsed_q_values,
        r_values=parsed_r_values,
        control_input_values=parsed_control_input_values,
        solver=solver,
        avl_command=avl_command,
        timeout_sec=timeout_sec,
        spanwise_resolution=spanwise_resolution,
        chordwise_resolution=chordwise_resolution,
        spanwise_spacing=spanwise_spacing,
        chordwise_spacing=chordwise_spacing,
        save_surface_forces=save_surface_forces,
        save_element_forces=save_element_forces,
        max_cases=max_cases,
        keep_geometry_dataset=keep_geometry_dataset,
        retain_aero_runs=retain_aero_runs,
        qc_preset=qc_preset,
        run_geometry_qc=run_geometry_qc_effective,
        geometry_qc_profile=geometry_qc_profile_effective,
        fail_on_geometry_qc_error=fail_on_geometry_qc_error_effective,
        run_aero_qc=run_aero_qc_effective,
        aero_qc_profile=aero_qc_profile_effective,
        fail_on_aero_qc_error=fail_on_aero_qc_error_effective,
    )

    raise typer.Exit(code=exit_code)

@dataset_app.command("curate-aero")
def dataset_curate_aero(
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
    reject_incomplete_groups: bool = typer.Option(
        True,
        "--reject-incomplete-groups/--keep-incomplete-groups",
        help="Reject geometries whose sweep grid is incomplete.",
    ),
    reject_groups_with_failures: bool = typer.Option(
        True,
        "--reject-groups-with-failures/--keep-groups-with-failures",
        help="Reject geometries that have failed aero cases recorded in aero_failures.csv.",
    ),
    reject_nonfinite_targets: bool = typer.Option(
        True,
        "--reject-nonfinite-targets/--keep-nonfinite-targets",
        help="Reject geometries with non-finite CL/CD/Cm values.",
    ),
    reject_control_diagnostic_failures: bool = typer.Option(
        True,
        "--reject-control-diagnostic-failures/--keep-control-diagnostic-failures",
        help="Reject geometries that failed control diagnostic columns.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the full curation report as JSON.",
    ),
) -> None:
    
    """Curate an existing aero dataset into kept/rejected outputs and report promotion readiness."""
    report = curate_aero_dataset(
        dataset_root=dataset,
        reject_incomplete_groups=reject_incomplete_groups,
        reject_groups_with_failures=reject_groups_with_failures,
        reject_nonfinite_targets=reject_nonfinite_targets,
        reject_control_diagnostic_failures=reject_control_diagnostic_failures,
    )

    if as_json:
        typer.echo(json.dumps(report, indent=2))
        return

    _print_curation_report(report)

    if report.get("promotion_ready") is True:
        typer.echo("")
        typer.echo("[AERIS] Promotion decision: READY")
    else:
        typer.echo("")
        typer.echo("[AERIS] Promotion decision: NOT READY")


@dataset_app.command("inspect")
def dataset_inspect(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a generated dataset root folder.",
    ),
) -> None:
    """Inspect a generated dataset and print QC summary as JSON."""
    summary = inspect_dataset(dataset)
    typer.echo(json.dumps(summary, indent=2))

@dataset_app.command("require-promoted-aero")
def dataset_require_promoted_aero(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a promoted aero dataset root.",
    ),
    allow_forced: bool = typer.Option(
        False,
        "--allow-forced",
        help="Allow use of a force-promoted dataset.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the resolved promoted-dataset context as JSON.",
    ),
) -> None:
    """Validate that a dataset is promoted and suitable for trusted downstream use."""
    try:
        context = require_promoted_aero_dataset(
            dataset_root=dataset,
            allow_forced=allow_forced,
        )
    except Exception as exc:
        raise typer.BadParameter(str(exc))

    if as_json:
        typer.echo(json.dumps(context, indent=2))
        return

    _print_promoted_dataset_context(context)

@dataset_app.command("training-data")
def training_data_cmd(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a promoted aero dataset root.",
    ),
    features: str = typer.Option(
        ...,
        "--features",
        help="Comma-separated feature columns.",
    ),
    targets: str = typer.Option(
        ...,
        "--targets",
        help="Comma-separated target columns.",
    ),
    allow_forced: bool = typer.Option(
        False,
        "--allow-forced",
        help="Allow use of a force-promoted dataset.",
    ),
) -> None:
    feature_cols = [f.strip() for f in features.split(",") if f.strip()]
    target_cols = [t.strip() for t in targets.split(",") if t.strip()]

    try:
        data = load_training_data(
            dataset_path=dataset,
            feature_columns=feature_cols,
            target_columns=target_cols,
            allow_forced=allow_forced,
        )
    except Exception as exc:
        raise typer.BadParameter(str(exc))

    typer.echo("[AERIS] Training data loaded")
    typer.echo(f"  dataset: {dataset}")
    typer.echo(f"  samples: {data.metadata['n_samples']}")
    typer.echo(f"  dropped_non_finite_rows: {data.metadata['dropped_non_finite_rows']}")
    typer.echo(f"  features: {data.feature_columns}")
    typer.echo(f"  targets: {data.target_columns}")

@dataset_app.command("split-training-data")
def split_training_data_cmd(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a promoted aero dataset root.",
    ),
    features: str = typer.Option(
        ...,
        "--features",
        help="Comma-separated feature columns.",
    ),
    targets: str = typer.Option(
        ...,
        "--targets",
        help="Comma-separated target columns.",
    ),
    method: str = typer.Option(
        "grouped",
        "--method",
        help="Split method: grouped or random.",
    ),
    group_column: str = typer.Option(
        "geometry_id",
        "--group-column",
        help="Grouping column for grouped split.",
    ),
    train_fraction: float = typer.Option(0.7, "--train-fraction"),
    val_fraction: float = typer.Option(0.15, "--val-fraction"),
    test_fraction: float = typer.Option(0.15, "--test-fraction"),
    random_seed: int = typer.Option(123, "--random-seed"),
    allow_forced: bool = typer.Option(
        False,
        "--allow-forced",
        help="Allow use of a force-promoted dataset.",
    ),
) -> None:
    feature_cols = [f.strip() for f in features.split(",") if f.strip()]
    target_cols = [t.strip() for t in targets.split(",") if t.strip()]

    data = load_training_data(
        dataset_path=dataset,
        feature_columns=feature_cols,
        target_columns=target_cols,
        allow_forced=allow_forced,
    )

    split = split_dataset(
        data.df,
        method=method,
        group_column=group_column,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        random_seed=random_seed,
    )

    typer.echo("[AERIS] Training data split completed")
    typer.echo(f"  method: {split.method}")
    typer.echo(f"  random_seed: {split.random_seed}")
    typer.echo(f"  train_rows: {len(split.train_df)}")
    typer.echo(f"  val_rows: {len(split.val_df)}")
    typer.echo(f"  test_rows: {len(split.test_df)}")

    if split.method == "grouped":
        typer.echo(f"  group_column: {split.metadata['group_column']}")
        typer.echo(f"  train_groups: {split.metadata['n_groups_train']}")
        typer.echo(f"  val_groups: {split.metadata['n_groups_val']}")
        typer.echo(f"  test_groups: {split.metadata['n_groups_test']}")