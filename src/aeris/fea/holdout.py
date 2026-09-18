"""Fail-closed promotion of a frozen structural strategy to the hold-out set."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from aeris.common.config import file_sha256


def promote_holdout(
    study_report: Path,
    freeze_authority: Path,
    qualification_report: Path,
    output_path: Path,
) -> dict[str, object]:
    """Authorize hold-out access only after frozen strategy and evidence gates pass."""
    report = json.loads(study_report.read_text(encoding="utf-8"))
    authority = yaml.safe_load(freeze_authority.read_text(encoding="utf-8"))
    qualification = json.loads(qualification_report.read_text(encoding="utf-8"))
    errors: list[str] = []
    if report.get("status") != "pass":
        errors.append("study_report.status")
    if not isinstance(authority, dict) or authority.get("schema") != (
        "aeris.fea.freeze_authority.v1"
    ):
        errors.append("freeze_authority.schema")
    else:
        if authority.get("status") != "frozen":
            errors.append("freeze_authority.status")
        if authority.get("holdout_access_authorized") is not True:
            errors.append("freeze_authority.holdout_access_authorized")
    if qualification.get("physical_validation", {}).get("detailed_design_gate") is not True:
        errors.append("qualification.physical_validation.detailed_design_gate")
    payload = {
        "schema": "aeris.fea.holdout_promotion.v1",
        "status": "pass" if not errors else "blocked",
        "holdout_set": authority.get("holdout_set") if isinstance(authority, dict) else None,
        "study_report": str(study_report),
        "study_report_sha256": file_sha256(study_report),
        "freeze_authority": str(freeze_authority),
        "qualification_report": str(qualification_report),
        "blocking_checks": errors,
        "reason": "hold-out remains sealed" if errors else "frozen strategy authorized",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
