"""Guided workflow/stage spine for AERIS workstation behavior."""

from aeris.workflow.spine import (
    DEFAULT_STAGE_DEFINITIONS,
    WORKFLOW_SCHEMA_VERSION,
    VALIDATION_SCHEMA_VERSION,
    WorkflowPaths,
    WorkflowValidationResult,
    get_next_required_stage,
    init_workflow,
    inspect_workflow,
    record_stage,
    resolve_workflow_dir,
    summarize_workflow,
    validate_workflow,
)

__all__ = [
    "DEFAULT_STAGE_DEFINITIONS",
    "WORKFLOW_SCHEMA_VERSION",
    "VALIDATION_SCHEMA_VERSION",
    "WorkflowPaths",
    "WorkflowValidationResult",
    "get_next_required_stage",
    "init_workflow",
    "inspect_workflow",
    "record_stage",
    "resolve_workflow_dir",
    "summarize_workflow",
    "validate_workflow",
    "WORKFLOW_TEMPLATE_SCHEMA_VERSION",
    "get_workflow_template",
    "init_workflow_from_template",
    "list_workflow_templates",
]

from aeris.workflow.templates import (
    WORKFLOW_TEMPLATE_SCHEMA_VERSION,
    get_workflow_template,
    init_workflow_from_template,
    list_workflow_templates,
)
