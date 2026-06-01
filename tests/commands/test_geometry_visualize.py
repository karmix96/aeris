from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app
import aeris.commands.geometry as geometry_commands

runner = CliRunner()


def test_geometry_visualize_delegates_to_visualization(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    class FakeResult:
        def __init__(self) -> None:
            self.output_dir = tmp_path / "viz_out"
            self.plot_path = tmp_path / "viz_out" / "planform.png"
            self.has_aerosandbox_airplane = True

    def fake_visualize_geometry_from_config(
        config_path,
        *,
        seed=None,
        save_plot=None,
        build_aerosandbox=None,
        output_dir=None,
        show_plot=False,
        draw_3d=True,
    ):
        called["config_path"] = Path(config_path)
        called["seed"] = seed
        called["save_plot"] = save_plot
        called["build_aerosandbox"] = build_aerosandbox
        called["output_dir"] = output_dir
        called["show_plot"] = show_plot
        called["draw_3d"] = draw_3d
        return FakeResult()

    monkeypatch.setattr(
        geometry_commands,
        "visualize_geometry_from_config",
        fake_visualize_geometry_from_config,
    )

    result = runner.invoke(
        app,
        [
            "geometry",
            "visualize",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--seed",
            "777",
            "--show-plot",
            "--draw-3d",
            "--save-plot",
            "--build-aerosandbox",
        ],
    )

    assert result.exit_code == 0
    assert called["config_path"].name == "baseline_bwb_25.yaml"
    assert called["seed"] == 777
    assert called["save_plot"] is True
    assert called["build_aerosandbox"] is True
    assert called["show_plot"] is True
    assert called["draw_3d"] is True
    assert "Geometry visualization output" in result.stdout
    assert "AeroSandbox airplane available: True" in result.stdout