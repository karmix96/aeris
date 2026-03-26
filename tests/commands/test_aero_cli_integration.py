from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()
RUNS_ROOT = Path("data/runs")

pytestmark = [pytest.mark.integration, pytest.mark.avl]


def _existing_run_dirs() -> set[Path]:
    if not RUNS_ROOT.exists():
        return set()
    return {p.resolve() for p in RUNS_ROOT.iterdir() if p.is_dir()}

def _latest_new_run_dir(before: set[Path]) -> Path:
    after = _existing_run_dirs()
    new_dirs = sorted(after - before, key=lambda p: p.stat().st_mtime)
    assert new_dirs, "No new run directory was created under data/runs."
    return new_dirs[-1]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def test_aero_run_smoke_creates_result() -> None:
    before = _existing_run_dirs()

    result = runner.invoke(
        app,
        [
            "aero",
            "run",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--geometry-source",
            "native",
            "--alpha",
            "2",
            "--beta",
            "0",
            "--velocity",
            "28",
            "--altitude",
            "1500",
            "--avl-command",
            "avl",
        ],
    )

    assert result.exit_code == 0, result.stdout

    after = _existing_run_dirs()
    new_dirs = sorted(after - before, key=lambda p: p.stat().st_mtime)

    assert new_dirs, "No new run directory was created under data/runs."
    run_dir = new_dirs[-1]

    aero_result = run_dir / "aero" / "aero_result.json"
    assert aero_result.exists(), f"Missing expected aero result: {aero_result}"

    payload = json.loads(aero_result.read_text())

    assert payload["status"] == "success"
    assert "scalars" in payload

    scalars = payload["scalars"]
    assert scalars["cl"] is not None
    assert scalars["cd"] is not None
    assert scalars["cm"] is not None

def test_aero_run_with_control_input_persists_metadata() -> None:
    before = _existing_run_dirs()

    result = runner.invoke(
        app,
        [
            "aero",
            "run",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--geometry-source",
            "native",
            "--alpha",
            "2",
            "--beta",
            "0",
            "--velocity",
            "28",
            "--altitude",
            "1500",
            "--control-input-deg",
            "5",
            "--avl-command",
            "avl",
        ],
    )

    assert result.exit_code == 0, result.stdout

    run_dir = _latest_new_run_dir(before)

    aero_result_path = run_dir / "aero" / "aero_result.json"
    manifest_path = run_dir / "aero_manifest.json"

    assert aero_result_path.exists(), f"Missing expected aero result: {aero_result_path}"
    assert manifest_path.exists(), f"Missing expected aero manifest: {manifest_path}"

    aero_payload = _load_json(aero_result_path)
    manifest_payload = _load_json(manifest_path)

    assert aero_payload["status"] == "success"

    solver_metadata = aero_payload.get("solver_metadata", {}) or {}
    assert solver_metadata.get("control_input_deg") == pytest.approx(5.0)

    assert manifest_payload.get("control_input_deg") == pytest.approx(5.0)

def test_aero_sweep_with_control_input_persists_metadata() -> None:
    before = _existing_run_dirs()

    result = runner.invoke(
        app,
        [
            "aero",
            "sweep",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--geometry-source",
            "native",
            "--alpha-values",
            "0,2",
            "--beta",
            "0",
            "--velocity",
            "28",
            "--altitude",
            "1500",
            "--control-input-deg",
            "5",
            "--avl-command",
            "avl",
            "--max-cases",
            "2",
        ],
    )

    assert result.exit_code == 0, result.stdout

    run_dir = _latest_new_run_dir(before)

    manifest_path = run_dir / "aero_sweep_manifest.json"
    assert manifest_path.exists(), f"Missing expected aero sweep manifest: {manifest_path}"

    manifest_payload = _load_json(manifest_path)

    assert manifest_payload.get("control_input_deg") == pytest.approx(5.0)

    sweep_result = manifest_payload.get("aero_sweep_result", {}) or {}
    summary = sweep_result.get("summary", {}) or {}

    assert summary.get("requested_n_cases") is not None
    assert summary.get("completed_n_cases") is not None