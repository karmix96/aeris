from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app
import aeris.commands.dataset as dataset_commands

runner = CliRunner()


def test_dataset_aero_generate_exits_nonzero_when_aero_qc_fails(monkeypatch, tmp_path: Path) -> None:
    def fake_run_aero_dataset_generation(**kwargs):
        return 1

    monkeypatch.setattr(
        dataset_commands,
        "run_aero_dataset_generation",
        fake_run_aero_dataset_generation,
    )

    result = runner.invoke(
        app,
        [
            "dataset",
            "aero-generate",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--n",
            "2",
            "--alpha-values",
            "0,2",
            "--velocity-values",
            "28",
            "--altitude-values",
            "1500",
            "--control-input-values",
            "-5,0,5",
            "--run-aero-qc",
            "--fail-on-aero-qc-error",
        ],
    )

    assert result.exit_code != 0