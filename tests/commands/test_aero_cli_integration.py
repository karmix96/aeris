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