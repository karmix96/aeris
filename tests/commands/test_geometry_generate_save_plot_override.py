from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import aeris.commands.geometry as geometry_commands
from aeris.cli import app

runner = CliRunner()


def test_geometry_generate_accepts_save_plot_override(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake_run_geometry_generation(config_path, *, save_plot=None):
        called["config_path"] = Path(config_path)
        called["save_plot"] = save_plot
        return 0, tmp_path

    monkeypatch.setattr(
        geometry_commands,
        "run_geometry_generation",
        fake_run_geometry_generation,
    )

    result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "geometry",
            "generate",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--save-plot",
        ],
    )

    assert result.exit_code == 0, result.output
    assert called["config_path"].name == "baseline_bwb_25.yaml"
    assert called["save_plot"] is True


def test_geometry_generate_accepts_no_save_plot_override(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake_run_geometry_generation(config_path, *, save_plot=None):
        called["config_path"] = Path(config_path)
        called["save_plot"] = save_plot
        return 0, tmp_path

    monkeypatch.setattr(
        geometry_commands,
        "run_geometry_generation",
        fake_run_geometry_generation,
    )

    result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "geometry",
            "generate",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--no-save-plot",
        ],
    )

    assert result.exit_code == 0, result.output
    assert called["config_path"].name == "baseline_bwb_25.yaml"
    assert called["save_plot"] is False


def test_geometry_generate_accepts_aerosandbox_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: dict[str, object] = {}

    def fake_run_geometry_generation(
        config_path,
        *,
        save_plot=None,
        build_aerosandbox=None,
    ):
        called["config_path"] = Path(config_path)
        called["save_plot"] = save_plot
        called["build_aerosandbox"] = build_aerosandbox
        return 0, tmp_path

    monkeypatch.setattr(
        geometry_commands,
        "run_geometry_generation",
        fake_run_geometry_generation,
    )

    result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "geometry",
            "generate",
            "--config",
            "configs/geometry/paper1_bwb_pygeo.yaml",
            "--build-aerosandbox",
        ],
    )

    assert result.exit_code == 0, result.output
    assert called["config_path"].name == "paper1_bwb_pygeo.yaml"
    assert called["build_aerosandbox"] is True
