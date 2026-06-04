"""Evidence helpers for the AERIS Streamlit workstation.

This module is intentionally boring: it reads workflow/backend artifacts and
summarizes them for the GUI. It does not run solvers, generate datasets, train
models, or decide workflow rules. The workflow and coverage backends remain the
source of truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aeris.workflow.coverage import build_workflow_coverage_report


@dataclass(frozen=True)
class WorkflowEvidenceBundle:
    """All backend-owned evidence files the GUI needs for one workflow root."""

    workflow_root: Path
    manifest: dict[str, Any]
    status: dict[str, Any]
    validation: dict[str, Any]
    stage_statuses: list[dict[str, Any]]
    events_tail: list[dict[str, Any]]
    coverage_report: dict[str, Any]


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_events_tail(path: Path, *, limit: int = 25) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            rows.append(event)
    return rows


def load_workflow_evidence(workflow_root: Path) -> WorkflowEvidenceBundle:
    """Load backend-owned workflow evidence for GUI display.

    Missing files are represented by empty dictionaries/lists. That keeps the
    GUI readable while still making absent evidence obvious to the operator.
    """

    workflow_root = workflow_root.expanduser().resolve()
    stage_statuses: list[dict[str, Any]] = []
    stages_dir = workflow_root / "stages"
    if stages_dir.exists():
        for stage_path in sorted(stages_dir.glob("*/stage_status.json")):
            payload = _read_json_object(stage_path)
            if payload:
                payload = dict(payload)
                payload.setdefault("_path", str(stage_path))
                payload.setdefault("_stage_name", stage_path.parent.name)
                stage_statuses.append(payload)

    return WorkflowEvidenceBundle(
        workflow_root=workflow_root,
        manifest=_read_json_object(workflow_root / "workflow_manifest.json"),
        status=_read_json_object(workflow_root / "workflow_status.json"),
        validation=_read_json_object(workflow_root / "workflow_validation_report.json"),
        stage_statuses=stage_statuses,
        events_tail=_read_events_tail(workflow_root / "workflow_events.jsonl"),
        coverage_report=build_workflow_coverage_report(),
    )


def summarize_workflow_evidence(bundle: WorkflowEvidenceBundle) -> dict[str, Any]:
    """Return a compact display summary for Streamlit."""

    validation = bundle.validation if isinstance(bundle.validation, dict) else {}
    status = bundle.status if isinstance(bundle.status, dict) else {}
    coverage = bundle.coverage_report if isinstance(bundle.coverage_report, dict) else {}
    counts = validation.get("counts", {}) if isinstance(validation.get("counts", {}), dict) else {}
    coverage_summary = coverage.get("summary", {}) if isinstance(coverage.get("summary", {}), dict) else {}
    next_stage = validation.get("next_required_stage") or status.get("next_required_stage") or {}
    if not isinstance(next_stage, dict):
        next_stage = {"name": str(next_stage)} if next_stage else {}

    completed = status.get("completed_stages", counts.get("completed_required_stages", 0))
    total = status.get("total_stages", counts.get("total_stages", len(bundle.stage_statuses)))

    return {
        "workflow_root": str(bundle.workflow_root),
        "has_manifest": bool(bundle.manifest),
        "has_status": bool(bundle.status),
        "has_validation": bool(bundle.validation),
        "health": validation.get("health", "not_validated" if bundle.manifest else "missing"),
        "completed_stages": completed,
        "total_stages": total,
        "required_blockers": coverage_summary.get("required_blocker_count", 0),
        "optional_gaps": coverage_summary.get("optional_gap_count", 0),
        "all_required_covered": bool(coverage_summary.get("all_required_stage_commands_covered", False)),
        "next_required_stage": next_stage,
        "next_stage_name": next_stage.get("name") or "—",
        "next_recommended_command": next_stage.get("recommended_command") or status.get("next_command_hint") or "—",
        "event_count_tail": len(bundle.events_tail),
        "stage_status_count": len(bundle.stage_statuses),
    }


def stage_domain_page(stage: str, domain: str | None = None) -> str:
    """Map backend stage/domain names to GUI pages for navigation only."""

    stage = str(stage or "").lower()
    domain = str(domain or "").lower()
    if stage in {"geometry_dataset"} or domain == "geometry":
        return "dataset"
    if stage in {"aero_sweep", "aero_dataset"} or domain == "aero":
        return "aero"
    if stage in {"dataset_qc", "curation", "promotion"} or domain == "dataset_trust":
        return "dataset"
    if stage.startswith("ml_") or stage in {"model_comparison", "model_promotion", "inference_guard"} or domain.startswith("ml"):
        return "ml"
    if "multifidelity" in stage or domain == "multifidelity":
        return "ml"
    if "active_learning" in stage or domain == "active_learning":
        return "ml"
    return "workflow"
