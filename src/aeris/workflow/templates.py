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


_PAPER_1_REQUIRED = (
    "geometry_dataset",
    "aero_sweep",
    "aero_dataset",
    "dataset_qc",
    "curation",
    "promotion",
    "dynamics_batch_labels",
    "flyability_ml_dataset",
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
    "paper_1": WorkflowTemplate(
        name="paper_1",
        title="Paper 1 workflow",
        description=(
            "Paper 1 static-airworthiness workflow: control-aware BWB aero dataset, "
            "QC/curation/promotion, first-order trim/flyability labels, ML training, "
            "model comparison, model promotion, and guarded inference."
        ),
        required_stages=_PAPER_1_REQUIRED,
        optional_stages=("multifidelity", "active_learning", "final_package"),
        notes=(
            "Use this for the PhD Paper 1 evidence chain, not as a hidden campaign runner.",
            "The key scientific outputs are static stability, trim/control authority, flyability labels, and trusted surrogate evidence.",
            "Start with smoke N, then pilot N, then paper-scale N only after QC and learning curves look sane.",
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
        "paper-1": "paper_1",
        "paper1": "paper_1",
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

def apply_template_status_hints(workflow_root: Path, template_name: str | None) -> None:
    """Apply template-specific operator command hints to workflow artifacts.

    This is intentionally narrow: it adjusts guidance text only. It does not
    mark stages complete, run commands, or change workflow truth/evidence.
    """

    if not template_name:
        return

    normalized = str(template_name).strip().lower().replace("-", "_")
    aliases = {
        "paper1": "paper_1",
        "paper_1": "paper_1",
        "canary": "canary",
    }
    normalized = aliases.get(normalized, normalized)

    canary_hints = {
        "geometry_dataset": (
            "aeris dataset generate "
            "-c configs/geometry/baseline_bwb_25.yaml "
            "--n <N> "
            "--sampler lhs_v1 "
            "--sampler-seed <seed> "
            "--no-save-plot "
            "--build-aerosandbox "
            "--workflow <workflow_root>"
        ),
    }

    paper_1_hints = {
        "geometry_dataset": (
            "aeris dataset generate "
            "-c configs/geometry/bwb_training_v2.yaml "
            "--n <N> "
            "--sampler lhs_v1 "
            "--sampler-seed <seed> "
            "--no-save-plot "
            "--build-aerosandbox "
            "--workflow <workflow_root>"
        ),
        "aero_sweep": (
            "aeris aero sweep "
            "--config configs/geometry/bwb_training_v2.yaml "
            "--alpha-values -2,0,4 "
            "--beta-values 0 "
            "--velocity-values 20 "
            "--altitude-values 700 "
            "--control-input-values -5,0,5 "
            "--workflow <workflow_root>"
        ),
        "aero_dataset": (
            "aeris dataset aero-generate "
            "-c configs/geometry/bwb_training_v2.yaml "
            "--n <N> "
            "--name <paper_1_dataset_name> "
            "--alpha-values -2,0,4 "
            "--velocity-values 20 "
            "--altitude-values 700 "
            "--control-input-values -5,0,5 "
            "--qc-preset production "
            "--retain-aero-runs failures_only "
            "--workflow <workflow_root>"
        ),
        "dataset_qc": (
            "aeris dataset aero-qc "
            "--dataset data/datasets/<paper_1_aero_dataset> "
            "--profile basic "
            "--workflow <workflow_root>"
        ),
        "curation": (
            "aeris dataset curate-aero "
            "--dataset data/datasets/<paper_1_aero_dataset> "
            "--workflow <workflow_root>"
        ),
        "promotion": (
            "aeris dataset promote-aero "
            "--dataset data/datasets/<paper_1_aero_dataset> "
            "--workflow <workflow_root>"
        ),
        "dynamics_batch_labels": (
            "aeris dynamics batch-labels "
            "--dataset data/datasets/<paper_1_aero_dataset> "
            "--source curated "
            "--control-column control_input_deg "
            "--max-abs-trim-delta-e-deg 25 "
            "--workflow <workflow_root>"
        ),
        "flyability_ml_dataset": (
            "aeris dynamics build-ml-dataset "
            "--dataset data/datasets/<paper_1_aero_dataset> "
            "--source curated "
            "--workflow <workflow_root>"
        ),
        "ml_eda": (
            "aeris ml eda "
            "--dataset data/datasets/<paper_1_aero_dataset>__flyability_ml "
            "--feature-set bwb_control_physics_v1 "
            "--targets Cm_delta_e_per_rad,trim_delta_e_required_deg,trim_delta_e_margin_to_limit_deg "
            "--no-plots "
            "--workflow <workflow_root>"
        ),
        "ml_training": (
            "aeris ml train "
            "--dataset data/datasets/<paper_1_aero_dataset>__flyability_ml "
            "--feature-set bwb_control_physics_v1 "
            "--targets Cm_delta_e_per_rad,trim_delta_e_required_deg,trim_delta_e_margin_to_limit_deg "
            "--model-type extra_trees "
            "--split-method grouped "
            "--group-column geometry_id "
            "--workflow <workflow_root>"
        ),
        "model_comparison": (
            "aeris ml compare "
            "--dataset data/datasets/<paper_1_aero_dataset>__flyability_ml "
            "--feature-set bwb_control_physics_v1 "
            "--targets Cm_delta_e_per_rad,trim_delta_e_required_deg,trim_delta_e_margin_to_limit_deg "
            "--models ridge,random_forest,extra_trees,gradient_boosting "
            "--split-method grouped "
            "--group-column geometry_id "
            "--workflow <workflow_root>"
        ),
        "model_promotion": (
            "aeris ml suggest-promotion-gates "
            "--model-run-dir data/processed/ml_runs/<paper_1_run> && "
            "aeris ml promote-model "
            "--model-run-dir data/processed/ml_runs/<paper_1_run> "
            "--gate-config <paper_1_gate_config.yaml>"
        ),
        "inference_guard": (
            "aeris ml check-inference-inputs "
            "--model-run-dir data/processed/ml_runs/<promoted_paper_1_run> "
            "--input-csv <candidate_inputs.csv>"
        ),
    }

    template_hints = {
        "canary": canary_hints,
        "paper_1": paper_1_hints,
    }

    hints_by_stage = template_hints.get(normalized)
    if not hints_by_stage:
        return

    root = Path(workflow_root).expanduser().resolve()
    status_path = root / "workflow_status.json"
    manifest_path = root / "workflow_manifest.json"

    def _patch_stage(stage: object) -> None:
        if not isinstance(stage, dict):
            return
        name = stage.get("name")
        if isinstance(name, str) and name in hints_by_stage:
            stage["recommended_command"] = hints_by_stage[name]

    def _patch_stage_collection(value: object) -> None:
        if isinstance(value, list):
            for stage in value:
                _patch_stage(stage)
        elif isinstance(value, dict):
            for stage in value.values():
                _patch_stage(stage)

    def _patch_payload(path: Path) -> None:
        if not path.exists():
            return

        payload = json.loads(path.read_text(encoding="utf-8"))

        _patch_stage(payload.get("next_required_stage"))

        for key in ("stages", "stage_definitions", "required_stages"):
            _patch_stage_collection(payload.get(key))

        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    _patch_payload(status_path)
    _patch_payload(manifest_path)

