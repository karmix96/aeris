from __future__ import annotations

from pathlib import Path

# Import validator modules for registration side effects.
import aeris.quality.aero_validators  # noqa: F401
import aeris.quality.geometry_validators  # noqa: F401
from aeris.quality.profiles import resolve_aero_profile, resolve_geometry_profile
from aeris.quality.registry import AERO_VALIDATOR_REGISTRY, GEOMETRY_VALIDATOR_REGISTRY
from aeris.quality.runners import qc_report_to_legacy_dict, run_validators


def run_geometry_dataset_qc_report(dataset_root: Path, profile: str = "basic"):
    """
    Preferred internal API for geometry QC.

    Returns the resolved profile name plus the structured QCReport object produced by the
    registry/profile-based modular validator system.
    """
    resolved_profile, validator_ids = resolve_geometry_profile(profile)
    validators = GEOMETRY_VALIDATOR_REGISTRY.create_many(validator_ids)
    report = run_validators(
        domain="geometry",
        dataset_root=dataset_root,
        validators=validators,
    )
    return resolved_profile, report


def run_aero_dataset_qc_report(dataset_root: Path, profile: str = "basic"):
    """
    Preferred internal API for aero QC.

    Returns the resolved profile name plus the structured QCReport object produced by the
    registry/profile-based modular validator system.
    """
    resolved_profile, validator_ids = resolve_aero_profile(profile)
    validators = AERO_VALIDATOR_REGISTRY.create_many(validator_ids)
    report = run_validators(
        domain="aero",
        dataset_root=dataset_root,
        validators=validators,
    )
    return resolved_profile, report


def run_geometry_dataset_qc(dataset_root: Path, profile: str = "basic") -> dict:
    """
    Backward-compatible workflow API.

    Keep this dict-shaped return contract for existing pipeline / CLI code that expects:
    passed/errors/warnings/metrics/checks.

    New internal code may prefer run_geometry_dataset_qc_report().
    """
    resolved_profile, report = run_geometry_dataset_qc_report(dataset_root, profile=profile)
    payload = qc_report_to_legacy_dict(report)
    payload["metrics"]["profile"] = resolved_profile
    return payload


def run_aero_dataset_qc(dataset_root: Path, profile: str = "basic") -> dict:
    """
    Backward-compatible workflow API.

    Keep this dict-shaped return contract for existing pipeline / CLI code that expects:
    passed/errors/warnings/metrics/checks.

    New internal code may prefer run_aero_dataset_qc_report().
    """
    resolved_profile, report = run_aero_dataset_qc_report(dataset_root, profile=profile)
    payload = qc_report_to_legacy_dict(report)
    payload["metrics"]["profile"] = resolved_profile
    return payload