"""CLI commands for the guided AERIS workflow/stage spine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from aeris.commands._helpers import fail_command
from aeris.workflow import (
    DEFAULT_STAGE_DEFINITIONS,
    get_next_required_stage,
    init_workflow,
    inspect_workflow,
    record_stage,
    summarize_workflow,
    validate_workflow,
)

workflow_app = typer.Typer(
    help=(
        "Guided workflow/stage commands. These commands record workstation state; "
        "they do not run solvers, ML, or dataset generation by themselves."
    )
)

_STAGE_STATUS_VALUES = {"pending", "running", "complete", "failed", "blocked", "skipped"}


def _echo_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _parse_metadata_json(raw: str | None) -> dict[str, Any] | None:
    if raw is None or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"--metadata-json must be valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise typer.BadParameter("--metadata-json must decode to a JSON object.")
    return data


@workflow_app.command("stages")
def workflow_stages() -> None:
    """Print the built-in guided workflow stage definitions."""
    _echo_json({"stages": DEFAULT_STAGE_DEFINITIONS})


@workflow_app.command("init")
def workflow_init(
    name: str = typer.Option(..., "--name", "-n", help="Workflow name."),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional explicit workflow directory. Defaults to data/workflows/<name>.",
    ),
    description: str | None = typer.Option(None, "--description", help="Optional workflow description."),
    force: bool = typer.Option(False, "--force", help="Overwrite/reinitialize an existing workflow folder."),
) -> None:
    """Initialize a workflow root with manifest, status, and event log files."""
    try:
        result = init_workflow(name=name, output_dir=output_dir, description=description, force=force)
    except Exception as exc:
        fail_command("workflow init", exc)

    typer.echo("[AERIS] Workflow initialized")
    typer.echo(f"  workflow_root: {result.paths.root}")
    typer.echo(f"  manifest: {result.paths.manifest_path}")
    typer.echo(f"  status: {result.paths.status_path}")
    typer.echo(f"  events: {result.paths.events_path}")
    next_stage = result.status.get("next_required_stage")
    if next_stage:
        typer.echo(f"  next_required_stage: {next_stage['name']}")


@workflow_app.command("status")
def workflow_status(
    workflow: Path = typer.Option(
        ...,
        "--workflow",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Workflow root directory.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print full status JSON."),
) -> None:
    """Show compact workflow progress or the full status JSON."""
    try:
        payload = inspect_workflow(workflow)
    except Exception as exc:
        fail_command("workflow status", exc)

    status = payload["status"]
    if json_output:
        _echo_json(status)
        return

    typer.echo("[AERIS] Workflow status")
    typer.echo(f"  workflow_root: {payload['workflow_root']}")
    typer.echo(f"  name: {status.get('name')}")
    typer.echo(f"  workflow_status: {status.get('workflow_status')}")
    typer.echo(f"  completed_stages: {status.get('completed_stages')}/{status.get('total_stages')}")
    next_stage = status.get("next_required_stage")
    if next_stage:
        typer.echo(f"  next_required_stage: {next_stage['name']}")
        typer.echo(f"  next_command_hint: {next_stage.get('recommended_command', '')}")
    else:
        typer.echo("  next_required_stage: none")


@workflow_app.command("next")
def workflow_next(
    workflow: Path = typer.Option(
        ...,
        "--workflow",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Workflow root directory.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print next-stage JSON."),
) -> None:
    """Show the next required workflow stage and command hint."""
    try:
        next_stage = get_next_required_stage(workflow)
    except Exception as exc:
        fail_command("workflow next", exc)

    if json_output:
        _echo_json({"next_required_stage": next_stage})
        return

    if next_stage is None:
        typer.echo("[AERIS] No required workflow stages remain.")
        return

    typer.echo("[AERIS] Next required workflow stage")
    typer.echo(f"  stage: {next_stage['name']}")
    typer.echo(f"  domain: {next_stage.get('domain')}")
    typer.echo(f"  description: {next_stage.get('description')}")
    typer.echo(f"  command_hint: {next_stage.get('recommended_command')}")


@workflow_app.command("inspect")
def workflow_inspect(
    workflow: Path = typer.Option(
        ...,
        "--workflow",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Workflow root directory.",
    ),
    stage: str | None = typer.Option(None, "--stage", help="Optional stage name to inspect."),
) -> None:
    """Print the workflow manifest/status or one stage status as JSON."""
    try:
        _echo_json(inspect_workflow(workflow, stage=stage))
    except Exception as exc:
        fail_command("workflow inspect", exc)




@workflow_app.command("summary")
def workflow_summary(
    workflow: Path = typer.Option(
        ...,
        "--workflow",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Workflow root directory.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print summary JSON."),
) -> None:
    """Show a compact workflow summary plus validation health."""
    try:
        summary = summarize_workflow(workflow)
    except Exception as exc:
        fail_command("workflow summary", exc)

    if json_output:
        _echo_json(summary)
        return

    typer.echo("[AERIS] Workflow summary")
    typer.echo(f"  workflow_root: {summary.get('workflow_root')}")
    typer.echo(f"  name: {summary.get('workflow_name')}")
    typer.echo(f"  workflow_status: {summary.get('workflow_status')}")
    typer.echo(f"  validation_health: {summary.get('validation_health')}")
    typer.echo(f"  completed_stages: {summary.get('completed_stages')}/{summary.get('total_stages')}")
    typer.echo(
        f"  completed_required_stages: {summary.get('completed_required_stages')}/{summary.get('required_stages')}"
    )
    typer.echo(f"  missing_artifacts: {summary.get('missing_artifact_count')}")
    typer.echo(f"  blockers: {summary.get('blocker_count')}")
    typer.echo(f"  warnings: {summary.get('warning_count')}")
    next_stage = summary.get("next_required_stage")
    if next_stage:
        typer.echo(f"  next_required_stage: {next_stage['name']}")
        typer.echo(f"  next_command_hint: {next_stage.get('recommended_command', '')}")
    else:
        typer.echo("  next_required_stage: none")


@workflow_app.command("validate")
def workflow_validate(
    workflow: Path = typer.Option(
        ...,
        "--workflow",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Workflow root directory.",
    ),
    write_report: bool = typer.Option(True, "--write-report/--no-write-report", help="Write workflow_validation_report.json."),
    json_output: bool = typer.Option(False, "--json", help="Print validation report JSON."),
) -> None:
    """Validate workflow evidence, artifact paths, trust manifests, and stage order."""
    try:
        result = validate_workflow(workflow, write_report=write_report)
    except Exception as exc:
        fail_command("workflow validate", exc)

    report = result.report
    if json_output:
        _echo_json(report)
        return

    counts = report.get("counts", {})
    typer.echo("[AERIS] Workflow validation")
    typer.echo(f"  workflow_root: {report.get('workflow_root')}")
    typer.echo(f"  name: {report.get('workflow_name')}")
    typer.echo(f"  health: {report.get('health')}")
    typer.echo(
        f"  completed_required_stages: {counts.get('completed_required_stages')}/{counts.get('required_stages')}"
    )
    typer.echo(f"  missing_artifacts: {counts.get('missing_artifacts')}")
    typer.echo(f"  blockers: {counts.get('blockers')}")
    typer.echo(f"  warnings: {counts.get('warnings')}")
    next_stage = report.get("next_required_stage")
    if next_stage:
        typer.echo(f"  next_required_stage: {next_stage['name']}")
    else:
        typer.echo("  next_required_stage: none")
    if result.report_path is not None:
        typer.echo(f"  report: {result.report_path}")

    for blocker in report.get("blockers", [])[:5]:
        typer.echo(f"  BLOCKER: {blocker}")
    for warning in report.get("warnings", [])[:5]:
        typer.echo(f"  WARNING: {warning}")


@workflow_app.command("doctor")
def workflow_doctor(
    workflow: Path = typer.Option(
        ...,
        "--workflow",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Workflow root directory.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print validation report JSON."),
) -> None:
    """Alias for workflow validate, with operator-friendly naming."""
    try:
        result = validate_workflow(workflow, write_report=True)
    except Exception as exc:
        fail_command("workflow doctor", exc)

    if json_output:
        _echo_json(result.report)
        return

    counts = result.report.get("counts", {})
    typer.echo("[AERIS] Workflow doctor")
    typer.echo(f"  workflow_root: {result.report.get('workflow_root')}")
    typer.echo(f"  health: {result.report.get('health')}")
    typer.echo(f"  blockers: {counts.get('blockers')}")
    typer.echo(f"  warnings: {counts.get('warnings')}")
    typer.echo(f"  missing_artifacts: {counts.get('missing_artifacts')}")
    if result.report_path is not None:
        typer.echo(f"  report: {result.report_path}")
    for blocker in result.report.get("blockers", [])[:5]:
        typer.echo(f"  BLOCKER: {blocker}")
    for warning in result.report.get("warnings", [])[:5]:
        typer.echo(f"  WARNING: {warning}")

@workflow_app.command("record-stage")
def workflow_record_stage(
    workflow: Path = typer.Option(
        ...,
        "--workflow",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Workflow root directory.",
    ),
    stage: str = typer.Option(..., "--stage", help="Stage name, e.g. geometry_dataset."),
    status: str = typer.Option(..., "--status", help="pending|running|complete|failed|blocked|skipped"),
    input_path: list[str] | None = typer.Option(None, "--input", help="Input path/value to record. Repeatable."),
    output_path: list[str] | None = typer.Option(None, "--output", help="Output path/value to record. Repeatable."),
    artifact: list[str] | None = typer.Option(None, "--artifact", help="Artifact path/value to record. Repeatable."),
    warning: list[str] | None = typer.Option(None, "--warning", help="Warning text to record. Repeatable."),
    blocker: list[str] | None = typer.Option(None, "--blocker", help="Blocker text to record. Repeatable."),
    notes: str | None = typer.Option(None, "--notes", help="Optional operator note."),
    metadata_json: str | None = typer.Option(None, "--metadata-json", help="Optional JSON object with extra metadata."),
) -> None:
    """Record one workflow stage state without running the underlying domain command."""
    if status not in _STAGE_STATUS_VALUES:
        raise typer.BadParameter(f"--status must be one of: {sorted(_STAGE_STATUS_VALUES)}")

    metadata = _parse_metadata_json(metadata_json)

    try:
        result = record_stage(
            workflow_dir=workflow,
            stage=stage,
            status=status,  # type: ignore[arg-type]
            inputs=input_path,
            outputs=output_path,
            artifacts=artifact,
            warnings=warning,
            blockers=blocker,
            notes=notes,
            metadata=metadata,
        )
    except typer.BadParameter:
        raise
    except Exception as exc:
        fail_command("workflow record-stage", exc)

    typer.echo("[AERIS] Workflow stage recorded")
    typer.echo(f"  workflow_root: {result.paths.root}")
    typer.echo(f"  stage: {stage}")
    typer.echo(f"  status: {status}")
    next_stage = result.status.get("next_required_stage")
    if next_stage:
        typer.echo(f"  next_required_stage: {next_stage['name']}")
    else:
        typer.echo("  next_required_stage: none")
    typer.echo(f"  stage_status: {result.paths.stages_dir / stage / 'stage_status.json'}")


# -----------------------------------------------------------------------------
# Slice 9D.3.2 — Workflow coverage audit
# -----------------------------------------------------------------------------
from aeris.workflow.coverage import (
    build_workflow_coverage_report as _build_workflow_coverage_report,
    write_workflow_coverage_report as _write_workflow_coverage_report,
)


@workflow_app.command("coverage")
def workflow_coverage(
    output_json: Path | None = typer.Option(
        None,
        "--output-json",
        "-o",
        help="Optional path for workflow_coverage_report.json.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the complete machine-readable report JSON.",
    ),
) -> None:
    """Audit workflow-stage coverage across stage-driving CLI commands."""

    report = _build_workflow_coverage_report()

    written_path = None
    if output_json is not None:
        written_path = _write_workflow_coverage_report(report, output_json)

    if as_json:
        _echo_json(report)
    else:
        summary = report["summary"]
        typer.echo("[AERIS] Workflow coverage audit")
        typer.echo(f"  entries: {summary['entry_count']}")
        typer.echo(f"  required entries: {summary['required_entry_count']}")
        typer.echo(f"  all required covered: {summary['all_required_stage_commands_covered']}")
        typer.echo(f"  required blockers: {summary['required_blocker_count']}")
        typer.echo(f"  optional gaps: {summary['optional_gap_count']}")
        typer.echo("")
        typer.echo("stage                         command                          status")
        typer.echo("----------------------------  -------------------------------  -----------------------")

        for entry in report["entries"]:
            command = f"aeris {entry['command_group']} {entry['command_name']}"
            required = "*" if entry["required"] else " "
            typer.echo(
                f"{required}{entry['stage']:<27}  {command:<31}  {entry['coverage_status']}"
            )

    if written_path is not None:
        typer.echo(f"  report_json: {written_path}")
