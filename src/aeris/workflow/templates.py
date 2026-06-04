"""Workflow templates for guided AERIS workstation initialization.

Templates are lightweight operator presets. They do not run commands and they do
not replace the workflow spine. They tell the workflow which built-in stages are
expected for a named operating mode and record that choice in workflow artifacts.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from aeris.workflow.spine import DEFAULT_STAGE_DEFINITIONS, WorkflowResult, init_workflow


WORKFLOW_TEMPLATE_SCHEMA_VERSION = "aeris.workflow_template.v1"


@dataclass(frozen=True)
class WorkflowTemplate:
    """Named workflow initialization preset."""

    name: str
    title: str
    description: str
    required_stages: tuple[str, ...]
    optional_stages: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORKFLOW_TEMPLATE_SCHEMA_VERSION,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "required_stages": list(self.required_stages),
            "optional_stages": list(self.optional_stages),
            "notes": list(self.notes),
        }


_BASE_REQUIRED = (
    "geometry_dataset",
    "aero_sweep",
    "aero_dataset",
    "dataset_qc",
    "curation",
    "promotion",
    "ml_eda",
    "ml_training",
    "model_comparison",
    "model_promotion",
    "inference_guard",
)


_WORKFLOW_TEMPLATES: dict[str, WorkflowTemplate] = {
    "canary": WorkflowTemplate(
        name="canary",
        title="Canary workflow",
        description=(
            "Small proof-of-plumbing workflow for validating the guided chain "
            "before a larger campaign. Use tiny N and baseline_bwb_25 smoke settings."
        ),
        required_stages=_BASE_REQUIRED,
        optional_stages=("final_package",),
        notes=(
            "Use configs/geometry/baseline_bwb_25.yaml unless deliberately testing a wider design space.",
            "Tiny canaries prove plumbing, not surrogate quality.",
        ),
    ),
    "production": WorkflowTemplate(
        name="production",
        title="Production training workflow",
        description=(
            "Full required BWB aero-surrogate trust chain: dataset, aero, QC, curation, "
            "promotion, EDA, ML, model promotion, and inference guard."
        ),
        required_stages=_BASE_REQUIRED,
        optional_stages=("active_learning", "multifidelity", "final_package"),
        notes=(
            "Use grouped ML splits by geometry_id.",
            "Do not train on raw or curated-only datasets; use promoted datasets.",
        ),
    ),
    "multifidelity": WorkflowTemplate(
        name="multifidelity",
        title="Multifidelity workflow",
        description=(
            "Required core trust chain plus the optional LF/HF delta-learning branch. "
            "This does not run CFD; it records the expected workflow shape."
        ),
        required_stages=_BASE_REQUIRED + ("multifidelity",),
        optional_stages=("active_learning", "final_package"),
        notes=(
            "Multifidelity tools consume scalar LF/HF products and do not execute CFD or XFOIL.",
            "Pairing keys and delta reports must remain auditable.",
        ),
    ),
    "active_learning": WorkflowTemplate(
        name="active_learning",
        title="Active-learning workflow",
        description=(
            "Required core trust chain plus candidate ranking for the next solver batch. "
            "Use only after a promoted model and inference guard exist."
        ),
        required_stages=_BASE_REQUIRED + ("active_learning",),
        optional_stages=("multifidelity", "final_package"),
        notes=(
            "Active learning recommends new samples; it must not silently run solvers.",
            "Candidate pools should be traceable CSV/data products.",
        ),
    ),
}


def list_workflow_templates() -> list[dict[str, Any]]:
    """Return all built-in workflow templates as JSON-serializable dictionaries."""
    return [template.to_dict() for template in _WORKFLOW_TEMPLATES.values()]


def get_workflow_template(name: str) -> dict[str, Any]:
    """Return one workflow template by name."""
    key = name.strip().lower().replace("_", "-")
    aliases = {
        "active-learning": "active_learning",
        "active_learning": "active_learning",
        "multi-fidelity": "multifidelity",
        "multi_fidelity": "multifidelity",
    }
    normalized = aliases.get(key, key)
    if normalized not in _WORKFLOW_TEMPLATES:
        known = ", ".join(sorted(_WORKFLOW_TEMPLATES))
        raise ValueError(f"Unknown workflow template '{name}'. Available templates: {known}")
    return _WORKFLOW_TEMPLATES[normalized].to_dict()


def _template_stage_definitions(template: dict[str, Any]) -> list[dict[str, Any]]:
    required = set(template["required_stages"])
    optional = set(template["optional_stages"])
    allowed = required | optional

    out: list[dict[str, Any]] = []
    for stage in DEFAULT_STAGE_DEFINITIONS:
        if stage["name"] not in allowed:
            continue
        item = deepcopy(stage)
        item["required"] = item["name"] in required
        out.append(item)

    missing = sorted(allowed - {stage["name"] for stage in out})
    if missing:
        raise ValueError(
            "Workflow template references unknown stage(s): " + ", ".join(missing)
        )
    return out


def _initial_stage_state(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": stage["name"],
        "domain": stage.get("domain", ""),
        "required": bool(stage.get("required", True)),
        "status": "pending",
        "artifacts": [],
        "inputs": [],
        "outputs": [],
        "blockers": [],
        "warnings": [],
        "notes": "",
        "updated_at_utc": None,
    }


def _next_required_stage(stages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for stage in stages:
        if stage.get("required", True):
            return stage
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def init_workflow_from_template(
    *,
    template_name: str,
    name: str,
    output_dir: Path | None = None,
    description: str | None = None,
    force: bool = False,
) -> WorkflowResult:
    """Initialize a workflow and attach a named template to its artifacts."""
    template = get_workflow_template(template_name)
    stage_definitions = _template_stage_definitions(template)

    result = init_workflow(
        name=name,
        output_dir=output_dir,
        description=description or template["description"],
        force=force,
    )

    manifest = dict(result.manifest)
    status = dict(result.status)

    manifest["template"] = template
    manifest["stages"] = stage_definitions

    status["template"] = template
    status["stages"] = {stage["name"]: _initial_stage_state(stage) for stage in stage_definitions}
    status["completed_stages"] = 0
    status["total_stages"] = len(stage_definitions)
    status["required_stages"] = len([stage for stage in stage_definitions if stage.get("required", True)])
    status["next_required_stage"] = _next_required_stage(stage_definitions)
    status["workflow_status"] = "initialized"

    _write_json(result.paths.manifest_path, manifest)
    _write_json(result.paths.status_path, status)
    (result.paths.root / "workflow_template.json").write_text(
        json.dumps(template, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return WorkflowResult(paths=result.paths, manifest=manifest, status=status)
