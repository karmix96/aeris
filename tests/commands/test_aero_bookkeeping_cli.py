from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()
RUNS_ROOT = Path("data/runs")

pytestmark = [pytest.mark.integration, pytest.mark.avl]


def _latest_run_matching(tag: str) -> Path:
    matches = sorted(
        [p for p in RUNS_ROOT.glob(f"*{tag}*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No run directory found for tag: {tag}")
    return matches[0]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_standard_bookkeeping(
    run_dir: Path,
    *,
    phase: str,
    domain_manifest_name: str,
) -> dict:
    generic_manifest_path = run_dir / "manifest.json"
    input_config_path = run_dir / "input_config.yaml"
    log_path = run_dir / "logs" / "app.log"
    domain_manifest_path = run_dir / domain_manifest_name

    assert generic_manifest_path.exists(), f"Missing generic manifest: {generic_manifest_path}"
    assert input_config_path.exists(), f"Missing copied input config: {input_config_path}"
    assert log_path.exists(), f"Missing run log: {log_path}"
    assert domain_manifest_path.exists(), f"Missing domain manifest: {domain_manifest_path}"

    generic = _load_json(generic_manifest_path)

    assert generic["phase"] == phase
    assert generic["solver"] == "aerosandbox_avl"
    assert generic["geometry_source"] == "native"
    assert generic["domain_manifest"].endswith(domain_manifest_name)

    assert "config_path" in generic
    assert "config_sha256" in generic
    assert isinstance(generic["config_sha256"], str)
    assert len(generic["config_sha256"]) == 64

    assert "run_artifacts" in generic
    assert "geometry_dir" in generic["run_artifacts"]
    assert "aero_dir" in generic["run_artifacts"]

    log_text = log_path.read_text(encoding="utf-8")
    assert "Starting aero" in log_text
    assert "completed" in log_text.lower()

    # The standard copy is input_config.yaml. Avoid the older duplicate named copy.
    assert not (run_dir / "baseline_bwb_25.yaml").exists()

    return generic


def test_aero_run_writes_generic_manifest_log_and_standard_input_config() -> None:
    tag = f"bookkeeping_run_{uuid4().hex[:8]}"

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
            "0",
            "--solver",
            "aerosandbox_avl",
            "--avl-command",
            "avl",
            "--timeout-sec",
            "90",
            "--spanwise-resolution",
            "4",
            "--chordwise-resolution",
            "8",
            "--output-name",
            tag,
        ],
    )

    assert result.exit_code == 0, result.stdout

    run_dir = _latest_run_matching(tag)

    generic = _assert_standard_bookkeeping(
        run_dir,
        phase="aero_run",
        domain_manifest_name="aero_manifest.json",
    )

    assert generic["status"] == "success"
    assert (run_dir / "aero" / "aero_result.json").exists()


def test_aero_sweep_writes_generic_manifest_log_and_standard_input_config() -> None:
    tag = f"bookkeeping_sweep_{uuid4().hex[:8]}"

    result = runner.invoke(
        app,
        [
            "aero",
            "sweep",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--geometry-source",
            "native",
            "--alpha",
            "0",
            "--beta",
            "0",
            "--velocity",
            "28",
            "--altitude",
            "1500",
            "--alpha-values",
            "0",
            "--beta-values",
            "0",
            "--velocity-values",
            "28",
            "--altitude-values",
            "1500",
            "--control-input-values",
            "0",
            "--solver",
            "aerosandbox_avl",
            "--avl-command",
            "avl",
            "--timeout-sec",
            "90",
            "--spanwise-resolution",
            "4",
            "--chordwise-resolution",
            "8",
            "--max-cases",
            "1",
            "--output-name",
            tag,
        ],
    )

    assert result.exit_code == 0, result.stdout

    run_dir = _latest_run_matching(tag)

    generic = _assert_standard_bookkeeping(
        run_dir,
        phase="aero_sweep",
        domain_manifest_name="aero_sweep_manifest.json",
    )

    assert generic["status"] in {"success", "completed_with_failures"}
    assert generic["requested_n_cases"] is not None
    assert generic["completed_n_cases"] is not None
