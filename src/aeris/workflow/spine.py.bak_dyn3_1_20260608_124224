"""
Guided workflow/stage spine for AERIS.

This module provides the first small, generic backbone needed for an
ANSYS/Workbench-style AERIS operator flow without turning the platform into a
black-box campaign runner.

Design boundaries:
    - It does not run geometry, aero, QC, curation, ML, multifidelity, or MDAO.
    - It records stage state, artifacts, events, blockers, and next guidance.
    - Standalone CLI/domain commands remain the execution source of truth.
    - Future commands can call record_stage(...) after completing their own work.

Artifacts written under each workflow root:
    workflow_manifest.json
    workflow_status.json
    workflow_events.jsonl
    stages/<stage_name>/stage_status.json
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from aeris.common.paths import get_data_dir

WORKFLOW_SCHEMA_VERSION = "aeris.workflow.v1"
EVENT_SCHEMA_VERSION = "aeris.workflow_event.v1"

StageStatus = Literal["pending", "running", "complete", "failed", "blocked", "skipped"]

_ALLOWED_STAGE_STATUSES: set[str] = {"pending", "running", "complete", "failed", "blocked", "skipped"}
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


DEFAULT_STAGE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "geometry_dataset",
        "domain": "geometry",
        "required": True,
        "description": "Generate and inspect the geometry design-space dataset.",
        "recommended_command": "aeris dataset generate -c configs/geometry/bwb_training_v1.yaml --n <N> --sampler lhs_v1 --sampler-seed <seed> --no-save-plot --build-aerosandbox",
    },
    {
        "name": "aero_sweep",
        "domain": "aero",
        "required": True,
        "description": "Run a controlled single-geometry aero sweep to verify solver setup, flight-condition ranges, controls, and raw artifacts.",
        "recommended_command": "aeris aero sweep --config configs/geometry/baseline_bwb_25.yaml --alpha-values -2,0,4,8 --beta-values 0 --velocity-values 28 --altitude-values 1500 --control-input-values -5,0,5 --workflow <workflow_root>",
    },
    {
        "name": "aero_dataset",
        "domain": "aero",
        "required": True,
        "description": "Generate the unified aero-labeled dataset from geometry and flight-condition sweeps.",
        "recommended_command": "aeris dataset aero-generate -c configs/geometry/bwb_training_v1.yaml --n <N> --qc-preset production --retain-aero-runs failures_only --workflow <workflow_root>",
    },
    {
        "name": "dataset_qc",
        "domain": "dataset_trust",
        "required": True,
        "description": "Run post-hoc aero QC and confirm row/artifact consistency.",
        "recommended_command": "aeris dataset aero-qc --dataset data/datasets/<aero_dataset> --profile basic",
    },
    {
        "name": "curation",
        "domain": "dataset_trust",
        "required": True,
        "description": "Create curated_aero_dataset.csv and rejected_aero_rows.csv.",
        "recommended_command": "aeris dataset curate-aero --dataset data/datasets/<aero_dataset>",
    },
    {
        "name": "promotion",
        "domain": "dataset_trust",
        "required": True,
        "description": "Promote the curated dataset so ML can use it.",
        "recommended_command": "aeris dataset promote-aero --dataset data/datasets/<aero_dataset>",
    },
    {
        "name": "ml_eda",
        "domain": "ml",
        "required": True,
        "description": "Audit promoted data before training using EDA and feature-set checks.",
        "recommended_command": "aeris ml eda --dataset data/datasets/<promoted_dataset> --feature-set bwb_control_physics_v1 --targets cl,cd,cm --no-plots",
    },
    {
        "name": "ml_training",
        "domain": "ml",
        "required": True,
        "description": "Train baseline model(s) from promoted data with grouped split.",
        "recommended_command": "aeris ml train --dataset data/datasets/<promoted_dataset> --feature-set bwb_control_raw --targets cl,cd,cm --model-type extra_trees --split-method grouped --group-column geometry_id",
    },
    {
        "name": "model_comparison",
        "domain": "ml",
        "required": True,
        "description": "Compare candidate model families and/or split seeds.",
        "recommended_command": "aeris ml compare-seeds --dataset data/datasets/<promoted_dataset> --feature-set bwb_control_raw --targets cl,cd,cm --models extra_trees,gradient_boosting,hist_gradient_boosting --split-method grouped --group-column geometry_id",
    },
    {
        "name": "model_promotion",
        "domain": "ml_trust",
        "required": True,
        "description": "Promote the selected model using reviewed target-aware gates.",
        "recommended_command": "aeris ml suggest-promotion-gates --model-run-dir data/processed/ml_runs/<run> && aeris ml promote-model --model-run-dir data/processed/ml_runs/<run> --gate-config <template.yaml>",
    },
    {
        "name": "inference_guard",
        "domain": "ml_trust",
        "required": True,
        "description": "Check prediction inputs against the promoted model and training envelope.",
        "recommended_command": "aeris ml check-inference-inputs --model-run-dir data/processed/ml_runs/<promoted_run> --input-csv <candidate_inputs.csv>",
    },
    {
        "name": "multifidelity",
        "domain": "multifidelity",
        "required": False,
        "description": "Optional LF/HF delta dataset, delta model, corrected prediction, and evaluation.",
        "recommended_command": "aeris ml build-delta-dataset ... && aeris ml train-delta-model ... && aeris ml evaluate-delta-model ...",
    },
    {
        "name": "active_learning",
        "domain": "active_learning",
        "required": False,
        "description": "Optional candidate ranking for the next solver batch.",
        "recommended_command": "aeris ml suggest-samples --model-run-dir data/processed/ml_runs/<promoted_run> --candidate-csv <candidate_pool.csv>",
    },
    {
        "name": "final_package",
        "domain": "handoff",
        "required": False,
        "description": "Collect promoted model/package evidence for future MDAO or reporting.",
        "recommended_command": "aeris ml require-promoted-model --model-run-dir data/processed/ml_runs/<promoted_run>",
    },
]


@dataclass(frozen=True)
class WorkflowPaths:
    """Filesystem paths for one AERIS workflow root."""

    root: Path
    manifest_path: Path
    status_path: Path
    events_path: Path
    stages_dir: Path


@dataclass(frozen=True)
class WorkflowResult:
    """Return bundle for workflow operations."""

    paths: WorkflowPaths
    manifest: dict[str, Any]
    status: dict[str, Any]


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_name(name: str) -> str:
    safe = _SAFE_NAME_RE.sub("_", name.strip()).strip("._-")
    if not safe:
        raise ValueError("Workflow name must contain at least one safe character.")
    return safe[:100]


def get_workflows_dir() -> Path:
    """Return the default workflow directory under AERIS data."""
    path = get_data_dir() / "workflows"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _paths(root: Path) -> WorkflowPaths:
    root = root.expanduser().resolve()
    return WorkflowPaths(
        root=root,
        manifest_path=root / "workflow_manifest.json",
        status_path=root / "workflow_status.json",
        events_path=root / "workflow_events.jsonl",
        stages_dir=root / "stages",
    )


def resolve_workflow_dir(workflow: Path | None = None, *, name: str | None = None) -> Path:
    """Resolve a workflow root from an explicit path or workflow name."""
    if workflow is not None and name is not None:
        raise ValueError("Provide either workflow path or workflow name, not both.")
    if workflow is not None:
        return workflow.expanduser().resolve()
    if name is not None:
        return (get_workflows_dir() / _safe_name(name)).resolve()
    raise ValueError("A workflow path or workflow name is required.")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing workflow file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Workflow JSON must contain an object: {path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_event(paths: WorkflowPaths, event: dict[str, Any]) -> None:
    paths.events_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "timestamp_utc": utc_now_iso(),
        **event,
    }
    with paths.events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _initial_stage_state(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": stage["name"],
        "domain": stage["domain"],
        "required": bool(stage["required"]),
        "status": "pending",
        "description": stage.get("description", ""),
        "recommended_command": stage.get("recommended_command", ""),
        "inputs": [],
        "outputs": [],
        "artifacts": [],
        "warnings": [],
        "blockers": [],
        "updated_at_utc": None,
    }


def _stage_names(manifest: dict[str, Any]) -> list[str]:
    stages = manifest.get("stages", [])
    if not isinstance(stages, list):
        raise ValueError("workflow_manifest.json has invalid 'stages' field.")
    names = [str(stage["name"]) for stage in stages]
    if not names:
        raise ValueError("workflow_manifest.json contains no stages.")
    return names


def _required_stage_names(manifest: dict[str, Any]) -> list[str]:
    return [str(stage["name"]) for stage in manifest.get("stages", []) if bool(stage.get("required", True))]


def _compute_next_required_stage(manifest: dict[str, Any], status: dict[str, Any]) -> dict[str, Any] | None:
    stages = status.get("stages", {})
    if not isinstance(stages, dict):
        raise ValueError("workflow_status.json has invalid 'stages' field.")

    manifest_stage_map = {str(stage["name"]): stage for stage in manifest.get("stages", [])}
    for stage_name in _required_stage_names(manifest):
        stage_status = stages.get(stage_name, {})
        state = str(stage_status.get("status", "pending"))
        if state not in {"complete", "skipped"}:
            definition = manifest_stage_map[stage_name]
            return {
                "name": stage_name,
                "domain": definition.get("domain"),
                "description": definition.get("description", ""),
                "recommended_command": definition.get("recommended_command", ""),
            }
    return None


def _refresh_workflow_rollup(manifest: dict[str, Any], status: dict[str, Any]) -> None:
    stages = status.get("stages", {})
    if not isinstance(stages, dict):
        raise ValueError("workflow_status.json has invalid 'stages' field.")

    stage_values = [stages[name] for name in _stage_names(manifest)]
    n_total = len(stage_values)
    n_complete = sum(1 for item in stage_values if item.get("status") in {"complete", "skipped"})
    n_failed = sum(1 for item in stage_values if item.get("status") == "failed")
    n_blocked = sum(1 for item in stage_values if item.get("status") == "blocked")
    next_required = _compute_next_required_stage(manifest, status)

    if n_failed > 0:
        workflow_status = "failed"
    elif n_blocked > 0:
        workflow_status = "blocked"
    elif next_required is None:
        workflow_status = "complete"
    elif any(item.get("status") == "running" for item in stage_values):
        workflow_status = "running"
    else:
        workflow_status = "in_progress" if n_complete > 0 else "initialized"

    status.update(
        {
            "workflow_status": workflow_status,
            "updated_at_utc": utc_now_iso(),
            "completed_stages": n_complete,
            "total_stages": n_total,
            "required_stages": len(_required_stage_names(manifest)),
            "next_required_stage": next_required,
        }
    )


def _normalize_items(items: list[str] | None) -> list[str]:
    if not items:
        return []
    return [str(item) for item in items if str(item).strip()]


def _merge_list(existing: Any, additions: list[str]) -> list[str]:
    values = list(existing) if isinstance(existing, list) else []
    for item in additions:
        if item not in values:
            values.append(item)
    return values


def init_workflow(
    *,
    name: str,
    output_dir: Path | None = None,
    description: str | None = None,
    force: bool = False,
) -> WorkflowResult:
    """Initialize a guided AERIS workflow folder."""
    root = (output_dir.expanduser().resolve() if output_dir is not None else get_workflows_dir() / _safe_name(name))
    paths = _paths(root)

    if paths.root.exists() and not force:
        if paths.manifest_path.exists() or paths.status_path.exists() or paths.events_path.exists():
            raise FileExistsError(
                f"Workflow already exists: {paths.root}. Use force=True or choose another name/output_dir."
            )

    paths.root.mkdir(parents=True, exist_ok=True)
    paths.stages_dir.mkdir(parents=True, exist_ok=True)

    workflow_id = f"workflow_{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()
    manifest = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "name": name,
        "description": description or "",
        "created_at_utc": now,
        "updated_at_utc": now,
        "root": str(paths.root),
        "stage_policy": {
            "standalone_commands_remain_valid": True,
            "workflow_records_state_only": True,
            "solver_execution_inside_workflow_spine": False,
        },
        "stages": DEFAULT_STAGE_DEFINITIONS,
    }
    status = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "name": name,
        "created_at_utc": now,
        "updated_at_utc": now,
        "workflow_status": "initialized",
        "stages": {stage["name"]: _initial_stage_state(stage) for stage in DEFAULT_STAGE_DEFINITIONS},
        "completed_stages": 0,
        "total_stages": len(DEFAULT_STAGE_DEFINITIONS),
        "required_stages": len([s for s in DEFAULT_STAGE_DEFINITIONS if bool(s["required"])]),
        "next_required_stage": None,
    }
    _refresh_workflow_rollup(manifest, status)

    _write_json(paths.manifest_path, manifest)
    _write_json(paths.status_path, status)
    _append_event(
        paths,
        {
            "event_type": "workflow_initialized",
            "workflow_id": workflow_id,
            "workflow_name": name,
            "root": str(paths.root),
            "next_required_stage": status["next_required_stage"],
        },
    )
    return WorkflowResult(paths=paths, manifest=manifest, status=status)


def inspect_workflow(workflow_dir: Path, *, stage: str | None = None) -> dict[str, Any]:
    """Load workflow status, optionally narrowed to one stage."""
    paths = _paths(workflow_dir)
    manifest = _load_json(paths.manifest_path)
    status = _load_json(paths.status_path)

    if stage is None:
        return {
            "workflow_root": str(paths.root),
            "manifest": manifest,
            "status": status,
            "events_path": str(paths.events_path),
        }

    stages = status.get("stages", {})
    if stage not in stages:
        raise ValueError(f"Unknown workflow stage '{stage}'. Known stages: {sorted(stages)}")
    stage_path = paths.stages_dir / stage / "stage_status.json"
    return {
        "workflow_root": str(paths.root),
        "stage": stages[stage],
        "stage_status_path": str(stage_path),
        "stage_status_file": _load_json(stage_path) if stage_path.exists() else None,
    }


def get_next_required_stage(workflow_dir: Path) -> dict[str, Any] | None:
    """Return the current next required stage for a workflow."""
    paths = _paths(workflow_dir)
    status = _load_json(paths.status_path)
    return status.get("next_required_stage")




VALIDATION_SCHEMA_VERSION = "aeris.workflow_validation.v1"


@dataclass(frozen=True)
class WorkflowValidationResult:
    """Return bundle for workflow validation/doctor checks."""

    paths: WorkflowPaths
    report: dict[str, Any]
    report_path: Path | None = None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "passed", "approved", "success"}:
            return True
        if lowered in {"false", "no", "0", "failed", "rejected", "error"}:
            return False
    return None


def _resolve_recorded_path(value: str) -> Path | None:
    """Resolve a recorded artifact/input/output value if it looks path-like."""
    raw = str(value).strip()
    if not raw or "://" in raw:
        return None
    try:
        path = Path(raw).expanduser()
    except Exception:
        return None
    if path.is_absolute():
        return path
    # Recorded workflow artifacts are normally project-relative paths.
    return (Path.cwd() / path).resolve()


def _path_payload(value: str) -> dict[str, Any]:
    path = _resolve_recorded_path(value)
    if path is None:
        return {"recorded": str(value), "path_like": False, "exists": None, "resolved": None}
    return {
        "recorded": str(value),
        "path_like": True,
        "exists": path.exists(),
        "resolved": str(path),
    }


def _try_load_json(path: Path, *, blockers: list[str], warnings: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        blockers.append(f"Missing JSON artifact: {path}")
        return None
    except json.JSONDecodeError as exc:
        blockers.append(f"Invalid JSON artifact {path}: {exc}")
        return None
    except OSError as exc:
        warnings.append(f"Could not read JSON artifact {path}: {exc}")
        return None
    if not isinstance(data, dict):
        blockers.append(f"JSON artifact must contain an object: {path}")
        return None
    return data


def _first_existing_artifact(stage_state: dict[str, Any], filename: str) -> Path | None:
    for raw in stage_state.get("artifacts", []) or []:
        path = _resolve_recorded_path(str(raw))
        if path is not None and path.name == filename and path.exists():
            return path
    return None


def _truth_check(data: dict[str, Any], keys: list[str]) -> bool | None:
    for key in keys:
        if key in data:
            return _as_bool(data.get(key))
    return None


def _validate_trust_artifact(
    *,
    stage_name: str,
    stage_state: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any] | None:
    """Run stage-specific evidence checks for promoted/guarded artifacts."""
    if str(stage_state.get("status")) not in {"complete", "skipped"}:
        return None

    if stage_name == "promotion":
        artifact_name = "promotion_manifest.json"
        path = _first_existing_artifact(stage_state, artifact_name)
        check = {"stage": stage_name, "artifact": artifact_name, "status": "missing"}
        if path is None:
            blockers.append("Dataset promotion stage is complete but promotion_manifest.json was not found in artifacts.")
            return check
        data = _try_load_json(path, blockers=blockers, warnings=warnings)
        check.update({"path": str(path), "status": "checked"})
        if data is None:
            check["passed"] = False
            return check
        ready = _truth_check(data, ["promotion_ready_at_time_of_promotion", "promotion_ready"])
        forced = _truth_check(data, ["promotion_forced", "forced"])
        blockers_in_manifest = data.get("promotion_blockers") or data.get("blockers") or []
        if ready is not True:
            blockers.append("Dataset promotion manifest does not show promotion_ready_at_time_of_promotion=True.")
        if forced is True:
            warnings.append("Dataset promotion manifest indicates forced promotion; treat as smoke/debug evidence, not scientific trust.")
        if blockers_in_manifest:
            blockers.append(f"Dataset promotion manifest contains blockers: {blockers_in_manifest}")
        check.update({"passed": ready is True and not bool(blockers_in_manifest), "ready": ready, "forced": forced})
        return check

    if stage_name == "model_promotion":
        artifact_name = "model_promotion_manifest.json"
        path = _first_existing_artifact(stage_state, artifact_name)
        check = {"stage": stage_name, "artifact": artifact_name, "status": "missing"}
        if path is None:
            blockers.append("Model promotion stage is complete but model_promotion_manifest.json was not found in artifacts.")
            return check
        data = _try_load_json(path, blockers=blockers, warnings=warnings)
        check.update({"path": str(path), "status": "checked"})
        if data is None:
            check["passed"] = False
            return check
        status = str(data.get("status", "")).lower()
        ready = _truth_check(data, ["promotion_ready_at_time_of_promotion", "promotion_ready"])
        blockers_in_manifest = data.get("blockers") or data.get("promotion_blockers") or []
        approved = status == "approved" or ready is True
        if status and status != "approved":
            blockers.append(f"Model promotion manifest status is not approved: {status}")
        if ready is False:
            blockers.append("Model promotion manifest says promotion_ready_at_time_of_promotion=False.")
        if blockers_in_manifest:
            blockers.append(f"Model promotion manifest contains blockers: {blockers_in_manifest}")
        check.update({"passed": approved and not bool(blockers_in_manifest), "status_value": status, "ready": ready})
        return check

    if stage_name == "inference_guard":
        artifact_name = "inference_guard_report.json"
        path = _first_existing_artifact(stage_state, artifact_name)
        check = {"stage": stage_name, "artifact": artifact_name, "status": "missing"}
        if path is None:
            blockers.append("Inference guard stage is complete but inference_guard_report.json was not found in artifacts.")
            return check
        data = _try_load_json(path, blockers=blockers, warnings=warnings)
        check.update({"path": str(path), "status": "checked"})
        if data is None:
            check["passed"] = False
            return check
        passed = _truth_check(data, ["passed", "ok", "success"])
        errors = data.get("errors") or data.get("error_count") or []
        if isinstance(errors, int):
            has_errors = errors > 0
        elif isinstance(errors, list):
            has_errors = len(errors) > 0
        else:
            has_errors = bool(errors)
        if passed is not True:
            blockers.append("Inference guard report does not show passed=True.")
        if has_errors:
            blockers.append(f"Inference guard report contains errors: {errors}")
        check.update({"passed": passed is True and not has_errors, "guard_passed": passed, "has_errors": has_errors})
        return check

    return None


def validate_workflow(workflow_dir: Path, *, write_report: bool = True) -> WorkflowValidationResult:
    """Validate workflow state against recorded evidence artifacts.

    This is intentionally a validator/doctor, not a runner. It checks whether the
    workflow record is internally coherent and whether recorded evidence still
    exists and says what the stage claims it says.
    """
    paths = _paths(workflow_dir)
    manifest = _load_json(paths.manifest_path)
    status = _load_json(paths.status_path)

    blockers: list[str] = []
    warnings: list[str] = []
    missing_artifacts: list[dict[str, Any]] = []
    artifact_checks: list[dict[str, Any]] = []
    trust_checks: list[dict[str, Any]] = []
    stage_order_issues: list[dict[str, Any]] = []
    stage_summaries: dict[str, dict[str, Any]] = {}

    stages = status.get("stages", {})
    if not isinstance(stages, dict):
        blockers.append("workflow_status.json has invalid 'stages' field.")
        stages = {}

    manifest_stage_names = _stage_names(manifest)
    status_stage_names = list(stages)
    missing_status_stages = [name for name in manifest_stage_names if name not in stages]
    unknown_status_stages = [name for name in status_stage_names if name not in manifest_stage_names]
    for name in missing_status_stages:
        blockers.append(f"Stage exists in manifest but not status: {name}")
    for name in unknown_status_stages:
        warnings.append(f"Stage exists in status but not manifest: {name}")

    for name in manifest_stage_names:
        stage_state = stages.get(name, {})
        stage_status = str(stage_state.get("status", "pending"))
        required = bool(stage_state.get("required", True))
        artifacts = stage_state.get("artifacts", []) or []
        stage_artifact_checks = [_path_payload(str(item)) for item in artifacts]
        for check in stage_artifact_checks:
            artifact_checks.append({"stage": name, **check})
            if check["path_like"] is True and check["exists"] is False:
                missing_artifacts.append({"stage": name, **check})
                if stage_status == "complete":
                    blockers.append(f"Complete stage '{name}' records missing artifact: {check['recorded']}")
                else:
                    warnings.append(f"Stage '{name}' records missing artifact: {check['recorded']}")

        trust_check = _validate_trust_artifact(
            stage_name=name,
            stage_state=stage_state,
            blockers=blockers,
            warnings=warnings,
        )
        if trust_check is not None:
            trust_checks.append(trust_check)

        stage_summaries[name] = {
            "status": stage_status,
            "required": required,
            "artifact_count": len(artifacts),
            "missing_artifact_count": sum(1 for item in stage_artifact_checks if item["path_like"] and not item["exists"]),
            "blocker_count": len(stage_state.get("blockers", []) or []),
            "warning_count": len(stage_state.get("warnings", []) or []),
            "updated_at_utc": stage_state.get("updated_at_utc"),
        }

    first_incomplete_required: str | None = None
    for name in _required_stage_names(manifest):
        stage_status = str(stages.get(name, {}).get("status", "pending"))
        if stage_status not in {"complete", "skipped"}:
            first_incomplete_required = name
            break
    if first_incomplete_required is not None:
        seen_first = False
        for name in _required_stage_names(manifest):
            if name == first_incomplete_required:
                seen_first = True
                continue
            if not seen_first:
                continue
            later_status = str(stages.get(name, {}).get("status", "pending"))
            if later_status in {"complete", "skipped"}:
                issue = {
                    "first_incomplete_required_stage": first_incomplete_required,
                    "later_completed_stage": name,
                    "later_status": later_status,
                }
                stage_order_issues.append(issue)
                warnings.append(
                    f"Stage order gap: later required stage '{name}' is {later_status} while '{first_incomplete_required}' is incomplete."
                )

    explicit_blocked_or_failed = [
        name
        for name in manifest_stage_names
        if str(stages.get(name, {}).get("status", "pending")) in {"blocked", "failed"}
    ]
    required_complete = [
        name
        for name in _required_stage_names(manifest)
        if str(stages.get(name, {}).get("status", "pending")) in {"complete", "skipped"}
    ]
    required_total = len(_required_stage_names(manifest))

    if explicit_blocked_or_failed:
        health = "blocked"
    elif blockers:
        health = "inconsistent"
    elif len(required_complete) == required_total:
        health = "healthy"
    else:
        health = "incomplete"

    report = {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "workflow_root": str(paths.root),
        "workflow_id": status.get("workflow_id"),
        "workflow_name": status.get("name"),
        "workflow_status": status.get("workflow_status"),
        "health": health,
        "next_required_stage": status.get("next_required_stage"),
        "counts": {
            "total_stages": len(manifest_stage_names),
            "required_stages": required_total,
            "completed_required_stages": len(required_complete),
            "missing_artifacts": len(missing_artifacts),
            "blockers": len(blockers),
            "warnings": len(warnings),
            "trust_checks": len(trust_checks),
            "stage_order_issues": len(stage_order_issues),
        },
        "missing_artifacts": missing_artifacts,
        "artifact_checks": artifact_checks,
        "trust_checks": trust_checks,
        "stage_order_issues": stage_order_issues,
        "explicit_blocked_or_failed_stages": explicit_blocked_or_failed,
        "blockers": blockers,
        "warnings": warnings,
        "stage_summaries": stage_summaries,
    }

    report_path = paths.root / "workflow_validation_report.json" if write_report else None
    if report_path is not None:
        _write_json(report_path, report)
        _append_event(
            paths,
            {
                "event_type": "workflow_validated",
                "workflow_id": status.get("workflow_id"),
                "health": health,
                "blocker_count": len(blockers),
                "warning_count": len(warnings),
                "missing_artifact_count": len(missing_artifacts),
                "report_path": str(report_path),
            },
        )

    return WorkflowValidationResult(paths=paths, report=report, report_path=report_path)


def summarize_workflow(workflow_dir: Path) -> dict[str, Any]:
    """Return a compact workflow summary with validation health."""
    payload = inspect_workflow(workflow_dir)
    validation = validate_workflow(workflow_dir, write_report=False).report
    status = payload["status"]
    return {
        "workflow_root": payload["workflow_root"],
        "workflow_id": status.get("workflow_id"),
        "workflow_name": status.get("name"),
        "workflow_status": status.get("workflow_status"),
        "validation_health": validation.get("health"),
        "completed_stages": status.get("completed_stages"),
        "total_stages": status.get("total_stages"),
        "required_stages": status.get("required_stages"),
        "completed_required_stages": validation.get("counts", {}).get("completed_required_stages"),
        "next_required_stage": status.get("next_required_stage"),
        "blocker_count": validation.get("counts", {}).get("blockers"),
        "warning_count": validation.get("counts", {}).get("warnings"),
        "missing_artifact_count": validation.get("counts", {}).get("missing_artifacts"),
    }


def record_stage(
    *,
    workflow_dir: Path,
    stage: str,
    status: StageStatus,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    blockers: list[str] | None = None,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WorkflowResult:
    """Record or update one workflow stage state."""
    if status not in _ALLOWED_STAGE_STATUSES:
        raise ValueError(f"Invalid stage status '{status}'. Allowed: {sorted(_ALLOWED_STAGE_STATUSES)}")

    paths = _paths(workflow_dir)
    manifest = _load_json(paths.manifest_path)
    workflow_status = _load_json(paths.status_path)

    known_stage_names = _stage_names(manifest)
    if stage not in known_stage_names:
        raise ValueError(f"Unknown workflow stage '{stage}'. Known stages: {known_stage_names}")

    stages = workflow_status.get("stages", {})
    if not isinstance(stages, dict):
        raise ValueError("workflow_status.json has invalid 'stages' field.")

    stage_state = dict(stages[stage])
    now = utc_now_iso()
    stage_state["status"] = status
    stage_state["updated_at_utc"] = now
    stage_state["inputs"] = _merge_list(stage_state.get("inputs"), _normalize_items(inputs))
    stage_state["outputs"] = _merge_list(stage_state.get("outputs"), _normalize_items(outputs))
    stage_state["artifacts"] = _merge_list(stage_state.get("artifacts"), _normalize_items(artifacts))
    stage_state["warnings"] = _merge_list(stage_state.get("warnings"), _normalize_items(warnings))
    stage_state["blockers"] = _merge_list(stage_state.get("blockers"), _normalize_items(blockers))
    if notes is not None:
        stage_state["notes"] = notes
    if metadata is not None:
        stage_state["metadata"] = metadata

    stages[stage] = stage_state
    workflow_status["stages"] = stages
    _refresh_workflow_rollup(manifest, workflow_status)
    manifest["updated_at_utc"] = workflow_status["updated_at_utc"]

    stage_payload = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "workflow_id": workflow_status["workflow_id"],
        "workflow_name": workflow_status["name"],
        "stage": stage_state,
        "next_required_stage_after_record": workflow_status["next_required_stage"],
    }

    stage_dir = paths.stages_dir / stage
    _write_json(stage_dir / "stage_status.json", stage_payload)
    _write_json(paths.manifest_path, manifest)
    _write_json(paths.status_path, workflow_status)
    _append_event(
        paths,
        {
            "event_type": "stage_recorded",
            "workflow_id": workflow_status["workflow_id"],
            "stage": stage,
            "stage_status": status,
            "next_required_stage": workflow_status["next_required_stage"],
            "artifact_count": len(stage_state.get("artifacts", [])),
            "blocker_count": len(stage_state.get("blockers", [])),
        },
    )

    return WorkflowResult(paths=paths, manifest=manifest, status=workflow_status)
