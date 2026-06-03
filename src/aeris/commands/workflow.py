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
