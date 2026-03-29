from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "geometry" / "baseline_bwb_25.yaml"
DATASETS_ROOT = PROJECT_ROOT / "data" / "datasets"


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )


@pytest.mark.integration
@pytest.mark.avl
def test_promotion_strict_produces_passing_strict_geometry_qc_report() -> None:
    dataset_name = "zz_it_qc_strict_reason"
    dataset_root = DATASETS_ROOT / dataset_name
    geometry_root = DATASETS_ROOT / f"{dataset_name}__geometry"

    for path in [dataset_root, geometry_root]:
        if path.exists():
            shutil.rmtree(path)

    cmd = [
        sys.executable,
        "-m",
        "aeris.cli",
        "dataset",
        "aero-generate",
        "--config",
        str(CONFIG_PATH),
        "--n",
        "2",
        "--name",
        dataset_name,
        "--alpha-values",
        "0,2",
        "--velocity-values",
        "28",
        "--altitude-values",
        "1500",
        "--control-input-values",
        "-5,0,5",
        "--avl-command",
        "avl",
        "--qc-preset",
        "promotion_strict",
        "--retain-aero-runs",
        "none",
    ]

    result = _run_command(cmd)
    assert result.returncode == 0, (
        f"Command failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    summary = json.loads((dataset_root / "final_run_summary.json").read_text(encoding="utf-8"))

    geometry_qc_report_path = Path(summary["geometry_qc"]["report_path"])
    geometry_qc_report = json.loads(geometry_qc_report_path.read_text(encoding="utf-8"))

    assert geometry_qc_report["passed"] is True
    assert geometry_qc_report["metrics"]["profile"] == "strict"

    strict_validator_ids = {
        "geometry_scalar_consistency_v1",
        "geometry_chord_ratio_sanity_v1",
        "geometry_planform_parameter_sanity_v1",
    }

    seen_ids = {check["validator_id"] for check in geometry_qc_report.get("checks", [])}
    assert strict_validator_ids.issubset(seen_ids)