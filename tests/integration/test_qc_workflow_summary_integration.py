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
def test_production_qc_preset_is_recorded_in_final_run_summary() -> None:
    dataset_name = "zz_it_qc_summary_production"
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
        "production",
        "--retain-aero-runs",
        "none",
    ]

    result = _run_command(cmd)

    assert result.returncode == 0, (
        f"Command failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    summary_path = dataset_root / "final_run_summary.json"
    assert summary_path.exists(), f"Missing final_run_summary.json: {summary_path}"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["qc_preset"] == "production"
    assert summary["geometry_qc"]["run_qc"] is True
    assert summary["geometry_qc"]["profile"] == "production"
    assert summary["geometry_qc"]["passed"] is True

    assert summary["aero_qc"]["run_qc"] is True
    assert summary["aero_qc"]["profile"] == "production"
    assert summary["aero_qc"]["passed"] is True

    assert summary["fail_on_geometry_qc_error"] is True
    assert summary["fail_on_aero_qc_error"] is True
    assert summary["final_status"] == "success"
    assert summary["exit_code"] == 0

    geometry_qc_report = Path(summary["geometry_qc"]["report_path"])
    aero_qc_report = Path(summary["aero_qc"]["report_path"])

    assert geometry_qc_report.exists(), f"Missing geometry QC report: {geometry_qc_report}"
    assert aero_qc_report.exists(), f"Missing aero QC report: {aero_qc_report}"

    geometry_report = json.loads(geometry_qc_report.read_text(encoding="utf-8"))
    aero_report = json.loads(aero_qc_report.read_text(encoding="utf-8"))

    assert geometry_report["passed"] is True
    assert aero_report["passed"] is True


@pytest.mark.integration
@pytest.mark.avl
def test_promotion_strict_qc_preset_is_recorded_in_final_run_summary() -> None:
    dataset_name = "zz_it_qc_summary_strict"
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

    summary_path = dataset_root / "final_run_summary.json"
    assert summary_path.exists(), f"Missing final_run_summary.json: {summary_path}"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["qc_preset"] == "promotion_strict"

    assert summary["geometry_qc"]["run_qc"] is True
    assert summary["geometry_qc"]["profile"] == "strict"
    assert summary["geometry_qc"]["passed"] is True

    assert summary["aero_qc"]["run_qc"] is True
    assert summary["aero_qc"]["profile"] == "strict"
    assert summary["aero_qc"]["passed"] is True

    assert summary["fail_on_geometry_qc_error"] is True
    assert summary["fail_on_aero_qc_error"] is True
    assert summary["final_status"] == "success"
    assert summary["exit_code"] == 0

    geometry_qc_report = Path(summary["geometry_qc"]["report_path"])
    aero_qc_report = Path(summary["aero_qc"]["report_path"])

    assert geometry_qc_report.exists(), f"Missing geometry QC report: {geometry_qc_report}"
    assert aero_qc_report.exists(), f"Missing aero QC report: {aero_qc_report}"

    geometry_report = json.loads(geometry_qc_report.read_text(encoding="utf-8"))
    aero_report = json.loads(aero_qc_report.read_text(encoding="utf-8"))

    assert geometry_report["passed"] is True
    assert aero_report["passed"] is True