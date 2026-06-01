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
        [p for p in RUNS_ROOT.glob(f"*_aero_*{tag}*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No aero run directory found for tag: {tag}")
    return matches[0]


def _find_aero_result_json(run_root: Path) -> Path:
    candidates = [
        run_root / "aero" / "aero_result.json",
        run_root / "aero_result.json",
        run_root / "artifacts" / "aero_result.json",
    ]
    for path in candidates:
        if path.exists():
            return path

    recursive = list(run_root.rglob("aero_result.json"))
    if recursive:
        return recursive[0]

    raise FileNotFoundError(f"No aero_result.json found under {run_root}")


def _load_aero_result(run_root: Path) -> dict:
    path = _find_aero_result_json(run_root)
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manifest_if_exists(run_root: Path) -> dict | None:
    candidates = [
        run_root / "aero_manifest.json",
        run_root / "manifest.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _assert_control_diagnostics_ok(payload: dict, expected_deg: float) -> None:
    meta = payload["solver_metadata"]
    diag = meta["control_diagnostics"]

    assert meta["control_input_deg"] == pytest.approx(expected_deg)
    assert meta["geometry_declares_controls"] is True
    assert meta["airplane_has_controls"] is True
    assert meta["geometry_control_surface_names"] == ["elevon"]

    assert diag["airplane_has_control_surfaces"] is True
    assert diag["airplane_avl_has_control_blocks"] is True
    assert diag["keystrokes_has_d1_command"] is True
    assert diag["stdout_control_variables"] == 1


def test_aero_cli_control_response_end_to_end():
    tag = f"ctrlreg_{uuid4().hex[:8]}"

    cases = {
        "zero": {
            "deg": 0.0,
            "suffix": f"{tag}_zero",
        },
        "plus5": {
            "deg": 5.0,
            "suffix": f"{tag}_plus5",
        },
        "minus5": {
            "deg": -5.0,
            "suffix": f"{tag}_minus5",
        },
    }

    for case in cases.values():
        result = runner.invoke(
            app,
            [
                "aero",
                "run",
                "--config", "configs/geometry/baseline_bwb_25.yaml",
                "--geometry-source", "native",
                "--alpha", "2",
                "--velocity", "28",
                "--altitude", "1500",
                "--beta", "0",
                "--p", "0",
                "--q", "0",
                "--r", "0",
                "--control-input-deg", str(case["deg"]),
                "--avl-command", "avl",
                "--output-name", case["suffix"],
            ],
        )
        assert result.exit_code == 0, result.output

    zero_run = _latest_run_matching(cases["zero"]["suffix"])
    plus_run = _latest_run_matching(cases["plus5"]["suffix"])
    minus_run = _latest_run_matching(cases["minus5"]["suffix"])

    zero_payload = _load_aero_result(zero_run)
    plus_payload = _load_aero_result(plus_run)
    minus_payload = _load_aero_result(minus_run)

    assert zero_payload["status"] == "success"
    assert plus_payload["status"] == "success"
    assert minus_payload["status"] == "success"

    _assert_control_diagnostics_ok(zero_payload, 0.0)
    _assert_control_diagnostics_ok(plus_payload, 5.0)
    _assert_control_diagnostics_ok(minus_payload, -5.0)

    cl0 = zero_payload["scalars"]["cl"]
    cm0 = zero_payload["scalars"]["cm"]

    clp = plus_payload["scalars"]["cl"]
    cmp = plus_payload["scalars"]["cm"]

    clm = minus_payload["scalars"]["cl"]
    cmm = minus_payload["scalars"]["cm"]

    assert clp != pytest.approx(cl0)
    assert clm != pytest.approx(cl0)
    assert cmp != pytest.approx(cm0)
    assert cmm != pytest.approx(cm0)

    assert clp > cl0 > clm
    assert cmp < cm0 < cmm


def test_aero_cli_accepts_control_request_with_baseline_bwb25_controls():
    """Baseline BWB-25 is the standard control-enabled smoke geometry."""
    tag = f"ctrlbwb25_{uuid4().hex[:8]}"

    result = runner.invoke(
        app,
        [
            "aero",
            "run",
            "--config", "configs/geometry/baseline_bwb_25.yaml",
            "--geometry-source", "native",
            "--alpha", "2",
            "--velocity", "28",
            "--altitude", "1500",
            "--beta", "0",
            "--p", "0",
            "--q", "0",
            "--r", "0",
            "--control-input-deg", "5",
            "--avl-command", "avl",
            "--output-name", tag,
        ],
    )

    assert result.exit_code == 0, result.output

    run_root = _latest_run_matching(tag)
    payload = _load_aero_result(run_root)

    assert payload["status"] == "success"
    _assert_control_diagnostics_ok(payload, 5.0)
