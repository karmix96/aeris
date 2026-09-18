"""Evidence-driven calibration checks for coupon and representative-wing tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def run_calibration(evidence_path: Path, output_path: Path) -> dict[str, object]:
    """Compare measured/predicted evidence records using declared tolerances.

    The function intentionally requires measured evidence; missing records produce
    ``blocked`` rather than a synthetic pass.
    """
    raw = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != "aeris.fea.calibration_evidence.v1":
        raise ValueError("calibration evidence must use aeris.fea.calibration_evidence.v1")
    records = raw.get("records", [])
    if not isinstance(records, list):
        raise ValueError("calibration evidence.records must be a list")
    if not records:
        payload = {
            "schema": "aeris.fea.calibration_report.v1",
            "status": "blocked",
            "evidence_status": raw.get("status"),
            "records": [],
            "failures": ["no measured evidence records"],
            "detailed_design_gate": False,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return payload
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"record[{index}]")
            continue
        required = ("name", "quantity", "predicted", "measured", "tolerance")
        if any(key not in record for key in required):
            failures.append(f"record[{index}].fields")
            continue
        predicted = float(record["predicted"])
        measured = float(record["measured"])
        tolerance = float(record["tolerance"])
        relative_error = abs(predicted - measured) / max(abs(measured), 1e-30)
        passed = relative_error <= tolerance
        if not passed:
            failures.append(str(record["name"]))
        results.append({
            "name": record["name"],
            "quantity": record["quantity"],
            "relative_error": relative_error,
            "tolerance": tolerance,
            "status": "pass" if passed else "fail",
        })
    payload = {
        "schema": "aeris.fea.calibration_report.v1",
        "status": "pass" if not failures else "fail",
        "evidence_status": raw.get("status"),
        "records": results,
        "failures": failures,
        "detailed_design_gate": not failures and raw.get("status") == "released",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
