from __future__ import annotations

from pathlib import Path

from aeris.quality.base import DatasetValidator
from aeris.quality.models import QCReport


def run_validators(
    *,
    domain: str,
    dataset_root: Path,
    validators: list[DatasetValidator],
) -> QCReport:
    checks = [validator.validate(dataset_root) for validator in validators]
    passed = all(check.passed for check in checks)
    return QCReport(
        domain=domain,
        target_path=str(dataset_root),
        passed=passed,
        checks=checks,
    )


def qc_report_to_legacy_dict(report: QCReport) -> dict:
    """
    Backward-compatible adapter for older pipeline code that still expects a dict-shaped QC report.

    New workflow should prefer QCReport, but this adapter keeps existing callers stable while the
    production spine is migrated.
    """
    errors: list[str] = []
    warnings: list[str] = []
    checks_payload: list[dict] = []
    metrics_by_check: dict[str, dict] = {}

    for check in report.checks:
        check_errors: list[str] = []
        check_warnings: list[str] = []

        for msg in check.messages:
            if msg.level == "error":
                errors.append(msg.message)
                check_errors.append(msg.message)
            elif msg.level == "warning":
                warnings.append(msg.message)
                check_warnings.append(msg.message)

        metrics_by_check[check.validator_id] = dict(check.metrics)

        checks_payload.append(
            {
                "validator_id": check.validator_id,
                "passed": check.passed,
                "errors": check_errors,
                "warnings": check_warnings,
                "metrics": dict(check.metrics),
            }
        )

    return {
        "passed": report.passed,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "domain": report.domain,
            "target_path": report.target_path,
            "error_count": report.error_count(),
            "warning_count": report.warning_count(),
            "checks_by_validator": metrics_by_check,
        },
        "checks": checks_payload,
    }