"""Workflow coverage audit for stage-driving AERIS commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
from typing import Any


VALID_COVERAGE_STATUSES = {
    "covered",
    "missing_workflow_option",
    "missing_command",
    "standalone_only",
    "manual_record_only",
    "needs_review",
}


@dataclass(frozen=True)
class WorkflowCoverageSpec:
    stage: str
    required: bool
    domain: str
    recommended_command: str
    command_group: str
    command_name: str
    auto_record_expected: bool = True
    standalone_only: bool = False
    manual_record_only: bool = False
    notes: str = ""


WORKFLOW_COVERAGE_SPEC: tuple[WorkflowCoverageSpec, ...] = (
    WorkflowCoverageSpec("geometry_dataset", True, "dataset", "aeris dataset generate ... --workflow <workflow_root>", "dataset", "generate"),
    WorkflowCoverageSpec("aero_sweep", True, "aero", "aeris aero run ... --workflow <workflow_root>", "aero", "run"),
    WorkflowCoverageSpec("aero_sweep", True, "aero", "aeris aero sweep ... --workflow <workflow_root>", "aero", "sweep"),
    WorkflowCoverageSpec("aero_dataset", True, "dataset", "aeris dataset aero-generate ... --workflow <workflow_root>", "dataset", "aero-generate"),
    WorkflowCoverageSpec("dataset_qc", True, "dataset", "aeris dataset aero-qc ... --workflow <workflow_root>", "dataset", "aero-qc"),
    WorkflowCoverageSpec("curation", True, "dataset", "aeris dataset curate-aero ... --workflow <workflow_root>", "dataset", "curate-aero"),
    WorkflowCoverageSpec("promotion", True, "dataset", "aeris dataset promote-aero ... --workflow <workflow_root>", "dataset", "promote-aero"),
    WorkflowCoverageSpec("dynamics_batch_labels", False, "dynamics", "aeris dynamics batch-labels --dataset data/datasets/<promoted_dataset> --source curated --workflow <workflow_root>", "dynamics", "batch-labels"),
    WorkflowCoverageSpec("flyability_ml_dataset", False, "dynamics", "aeris dynamics build-ml-dataset --dataset data/datasets/<promoted_dataset> --source curated --workflow <workflow_root>", "dynamics", "build-ml-dataset"),
    WorkflowCoverageSpec("ml_eda", True, "ml", "aeris ml eda ... --workflow <workflow_root>", "ml", "eda"),
    WorkflowCoverageSpec("ml_training", True, "ml", "aeris ml train ... --workflow <workflow_root>", "ml", "train"),
    WorkflowCoverageSpec("model_comparison", True, "ml", "aeris ml compare ... --workflow <workflow_root>", "ml", "compare"),
    WorkflowCoverageSpec("model_comparison", False, "ml", "aeris ml compare-seeds ... --workflow <workflow_root>", "ml", "compare-seeds"),
    WorkflowCoverageSpec("model_promotion", True, "ml", "aeris ml promote-model ... --workflow <workflow_root>", "ml", "promote-model"),
    WorkflowCoverageSpec("inference_guard", True, "ml", "aeris ml check-inference-inputs ... --workflow <workflow_root>", "ml", "check-inference-inputs"),
    WorkflowCoverageSpec("multifidelity", False, "ml", "aeris ml build-delta-dataset ... --workflow <workflow_root>", "ml", "build-delta-dataset"),
    WorkflowCoverageSpec("multifidelity", False, "ml", "aeris ml train-delta-model ... --workflow <workflow_root>", "ml", "train-delta-model"),
    WorkflowCoverageSpec("multifidelity", False, "ml", "aeris ml evaluate-delta-model ... --workflow <workflow_root>", "ml", "evaluate-delta-model"),
    WorkflowCoverageSpec("active_learning", False, "ml", "aeris ml suggest-samples ... --workflow <workflow_root>", "ml", "suggest-samples"),
    WorkflowCoverageSpec(
        "final_package",
        False,
        "handoff",
        "aeris workflow record-stage --stage final_package --status complete --artifact <final_package_or_report>",
        "workflow",
        "record-stage",
        auto_record_expected=False,
        manual_record_only=True,
        notes="Final handoff/package is usually recorded manually after evidence review.",
    ),
)


def _command_apps() -> dict[str, Any]:
    from aeris.commands.aero import aero_app
    from aeris.commands.dataset import dataset_app
    from aeris.commands.dynamics import dynamics_app
    from aeris.commands.ml import ml_app
    from aeris.commands.workflow import workflow_app

    return {
        "aero": aero_app,
        "dataset": dataset_app,
        "dynamics": dynamics_app,
        "ml": ml_app,
        "workflow": workflow_app,
    }


def _typer_command_name(command_info: Any) -> str:
    explicit_name = getattr(command_info, "name", None)
    if explicit_name:
        return str(explicit_name)
    callback = getattr(command_info, "callback", None)
    callback_name = getattr(callback, "__name__", "")
    return callback_name.replace("_", "-")


def _find_typer_command(command_group: str, command_name: str) -> Any | None:
    app = _command_apps().get(command_group)
    if app is None:
        return None

    for command_info in getattr(app, "registered_commands", []):
        if _typer_command_name(command_info) == command_name:
            return command_info
    return None


def _command_parameter_names(command_info: Any | None) -> list[str]:
    if command_info is None:
        return []
    callback = getattr(command_info, "callback", None)
    if callback is None:
        return []
    return list(inspect.signature(callback).parameters)


def _coverage_status(spec: WorkflowCoverageSpec, command_exists: bool, supports_workflow_option: bool) -> str:
    if not command_exists:
        return "missing_command"
    if spec.standalone_only:
        return "standalone_only"
    if spec.manual_record_only:
        return "manual_record_only"
    if spec.auto_record_expected:
        return "covered" if supports_workflow_option else "missing_workflow_option"
    return "needs_review"


def build_workflow_coverage_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    for spec in WORKFLOW_COVERAGE_SPEC:
        command_info = _find_typer_command(spec.command_group, spec.command_name)
        params = _command_parameter_names(command_info)
        command_exists = command_info is not None
        supports_workflow_option = "workflow" in params

        entry = asdict(spec)
        entry.update(
            {
                "command_exists": command_exists,
                "supports_workflow_option": supports_workflow_option,
                "workflow_parameter_name": "workflow" if supports_workflow_option else None,
                "coverage_status": _coverage_status(spec, command_exists, supports_workflow_option),
                "audited_parameter_names": params,
            }
        )
        entries.append(entry)

    return entries


def build_workflow_coverage_report() -> dict[str, Any]:
    entries = build_workflow_coverage_entries()

    status_counts = {status: 0 for status in sorted(VALID_COVERAGE_STATUSES)}
    for entry in entries:
        status_counts[entry["coverage_status"]] = status_counts.get(entry["coverage_status"], 0) + 1

    required_entries = [entry for entry in entries if entry["required"]]
    required_blockers = [
        entry
        for entry in required_entries
        if entry["coverage_status"] not in {"covered", "standalone_only", "manual_record_only"}
    ]
    optional_gaps = [
        entry
        for entry in entries
        if not entry["required"]
        and entry["coverage_status"] not in {"covered", "standalone_only", "manual_record_only"}
    ]

    return {
        "report_type": "workflow_coverage_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage_statuses": sorted(VALID_COVERAGE_STATUSES),
        "summary": {
            "entry_count": len(entries),
            "required_entry_count": len(required_entries),
            "unique_stage_count": len({entry["stage"] for entry in entries}),
            "all_required_stage_commands_covered": len(required_blockers) == 0,
            "required_blocker_count": len(required_blockers),
            "optional_gap_count": len(optional_gaps),
            "status_counts": status_counts,
        },
        "required_blockers": required_blockers,
        "optional_gaps": optional_gaps,
        "entries": entries,
    }


def write_workflow_coverage_report(report: dict[str, Any], output_path: Path) -> Path:
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
