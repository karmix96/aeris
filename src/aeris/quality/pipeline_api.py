from pathlib import Path

from aeris.quality.aero_validators import run_aero_checks
from aeris.quality.geometry_validators import run_geometry_checks


def run_geometry_dataset_qc(dataset_root: Path, profile: str = "basic"):
    if profile not in {"basic", "strict"}:
        profile = "basic"
    return run_geometry_checks(dataset_root, profile=profile)


def run_aero_dataset_qc(dataset_root: Path, profile: str = "basic"):
    if profile not in {"basic", "strict"}:
        profile = "basic"
    return run_aero_checks(dataset_root, profile=profile)