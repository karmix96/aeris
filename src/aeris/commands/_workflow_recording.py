"""
CLI helper for optional guided-workflow stage recording.

Domain commands remain standalone. When an operator passes ``--workflow`` to a
supported command, that command can call ``record_workflow_stage_success`` after
its own business logic succeeds. This keeps the workflow layer as a state spine,
not as a hidden campaign runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from aeris.workflow import record_stage


def _normalize_path_item(value: Path | str | None) -> str | None:
    """Return a stable string representation for a path-like workflow item."""
    if value is None:
        return None
    if isinstance(value, Path):
        return str(value.expanduser().resolve())
    text = str(value).strip()
    return text or None


def _normalize_path_items(values: list[Path | str | None] | None) -> list[str]:
    """Normalize optional path/string values for workflow artifact lists."""
    if not values:
        return []
    items: list[str] = []
    for value in values:
        normalized = _normalize_path_item(value)
        if normalized is not None and normalized not in items:
            items.append(normalized)
    return items


def record_workflow_stage_success(
    *,
    workflow: Path | None,
    stage: str,
    inputs: list[Path | str | None] | None = None,
    outputs: list[Path | str | None] | None = None,
    artifacts: list[Path | str | None] | None = None,
    warnings: list[str] | None = None,
    blockers: list[str] | None = None,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
    echo: bool = True,
) -> None:
    """Record a completed workflow stage when ``--workflow`` was supplied.

    If no workflow path is provided, this function intentionally does nothing.
    If a workflow path is provided but recording fails, the caller should fail
    loudly instead of pretending the workstation state was updated.
    """
    if workflow is None:
        return

    result = record_stage(
        workflow_dir=workflow,
        stage=stage,
        status="complete",
        inputs=_normalize_path_items(inputs),
        outputs=_normalize_path_items(outputs),
        artifacts=_normalize_path_items(artifacts),
        warnings=warnings,
        blockers=blockers,
        notes=notes,
        metadata=metadata,
    )

    if echo:
        next_stage = result.status.get("next_required_stage") or {}
        typer.echo("")
        typer.echo("[AERIS] Workflow stage auto-recorded")
        typer.echo(f"  workflow_root: {result.paths.root}")
        typer.echo(f"  stage: {stage}")
        typer.echo("  status: complete")
        typer.echo(f"  next_required_stage: {next_stage.get('name') if next_stage else None}")
