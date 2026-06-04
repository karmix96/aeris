"""Operational workflow preflight checks.

This module does not run solvers, datasets, QC, ML, or promotion.
It only checks whether a planned campaign looks coherent before spending time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from aeris.workflow.coverage import build_workflow_coverage_report


@dataclass(frozen=True)
class CampaignPlan:
    """Small campaign sizing model for operator preflight."""

    n_geometries: int
    alpha_values: list[float]
    beta_values: list[float]
    velocity_values: list[float]
    altitude_values: list[float]
    control_input_values: list[float]

    @property
    def aero_case_count(self) -> int:
        return (
            self.n_geometries
            * len(self.alpha_values)
            * len(self.beta_values)
            * len(self.velocity_values)
            * len(self.altitude_values)
            * len(self.control_input_values)
        )


def parse_float_list(value: str, *, default: list[float]) -> list[float]:
    """Parse comma-separated floats with a fallback default."""

    cleaned = (value or "").strip()
    if not cleaned:
        return list(default)

    values: list[float] = []
    for item in cleaned.split(","):
        token = item.strip()
        if not token:
            continue
        values.append(float(token))

    if not values:
        return list(default)

    return values


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_operational_preflight_report(
    *,
    workflow_root: Path | None,
    config: Path,
    n_geometries: int,
    alpha_values: list[float],
    beta_values: list[float],
    velocity_values: list[float],
    altitude_values: list[float],
    control_input_values: list[float],
    max_cases_warning: int = 1000,
) -> dict[str, Any]:
    """Build a campaign readiness report without executing the campaign."""

    warnings: list[str] = []
    blockers: list[str] = []

    config_path = config.expanduser().resolve()
    if not config_path.exists():
        blockers.append(f"Config does not exist: {config_path}")

    if n_geometries <= 0:
        blockers.append("n_geometries must be positive.")

    plan = CampaignPlan(
        n_geometries=n_geometries,
        alpha_values=alpha_values,
        beta_values=beta_values,
        velocity_values=velocity_values,
        altitude_values=altitude_values,
        control_input_values=control_input_values,
    )

    if plan.aero_case_count <= 0:
        blockers.append("Expanded aero case count is zero.")

    if plan.aero_case_count > max_cases_warning:
        warnings.append(
            f"Expanded aero case count is {plan.aero_case_count}, above warning threshold {max_cases_warning}."
        )

    coverage = build_workflow_coverage_report()
    coverage_summary = coverage["summary"]
    if not coverage_summary.get("all_required_stage_commands_covered", False):
        blockers.append("Required workflow command coverage has blockers.")
    if coverage_summary.get("optional_gap_count", 0) > 0:
        warnings.append("Workflow coverage still has optional gaps.")

    workflow_payload: dict[str, Any] | None = None
    workflow_status_path: str | None = None
    workflow_root_resolved: str | None = None

    if workflow_root is not None:
        root = workflow_root.expanduser().resolve()
        workflow_root_resolved = str(root)
        status_path = root / "workflow_status.json"
        workflow_status_path = str(status_path)
        workflow_payload = _read_json(status_path)

        if workflow_payload is None:
            blockers.append(f"Workflow status file does not exist: {status_path}")
        else:
            template = workflow_payload.get("template")
            next_stage = workflow_payload.get("next_required_stage")
            if not template:
                warnings.append("Workflow status does not record a template.")
            if not next_stage:
                warnings.append("Workflow status does not expose next_required_stage.")

    else:
        warnings.append("No workflow root supplied; preflight cannot inspect workflow state.")

    if "baseline_bwb_25.yaml" in str(config_path) and n_geometries > 5:
        warnings.append(
            "baseline_bwb_25.yaml is a smoke/canary config; it is not a real training design-space config."
        )

    if "bwb_training_v1.yaml" in str(config_path) and n_geometries < 10:
        warnings.append(
            "bwb_training_v1.yaml with very small N is only a canary, not a surrogate-quality campaign."
        )

    readiness = "blocked" if blockers else ("warning" if warnings else "ready")

    return {
        "report_type": "workflow_operational_preflight",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": readiness,
        "blockers": blockers,
        "warnings": warnings,
        "workflow_root": workflow_root_resolved,
        "workflow_status_path": workflow_status_path,
        "workflow_status": workflow_payload,
        "config": str(config_path),
        "campaign_plan": asdict(plan),
        "estimated_aero_case_count": plan.aero_case_count,
        "coverage_summary": coverage_summary,
        "operator_note": (
            "This report is a preflight only. It does not run geometry, AVL, QC, curation, "
            "promotion, EDA, ML, active learning, or multifidelity commands."
        ),
    }


def write_preflight_report(report: dict[str, Any], output_path: Path) -> Path:
    """Write preflight report JSON."""

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
