"""Guided workflow/stage spine for AERIS workstation behavior."""

from aeris.workflow.spine import (
    DEFAULT_STAGE_DEFINITIONS,
    WORKFLOW_SCHEMA_VERSION,
    WorkflowPaths,
    get_next_required_stage,
    init_workflow,
    inspect_workflow,
    record_stage,
    resolve_workflow_dir,
)

__all__ = [
    "DEFAULT_STAGE_DEFINITIONS",
    "WORKFLOW_SCHEMA_VERSION",
    "WorkflowPaths",
    "get_next_required_stage",
    "init_workflow",
    "inspect_workflow",
    "record_stage",
    "resolve_workflow_dir",
]
