from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app
from aeris.commands import geometry as geometry_commands


def test_geometry_visualize_draw_failure_is_compact(monkeypatch):
    runner = CliRunner()

    def fake_visualize_geometry_from_config(*args, **kwargs):
        raise RuntimeError(
            "AERIS_DRAW_3D_FAILED: Interactive 3D viewer failed because "
            "AeroSandbox/PyVista/VTK could not initialize. "
            "Technical details were saved to: data/debug/visualization_runs/demo/draw_3d_error.txt. "
            "Use safe PNG preview: aeris geometry visualize --no-draw-3d --save-plot"
        )

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
            "--draw-3d",
        ],
    )

    assert result.exit_code == 2
    assert "Interactive 3D viewer failed" in result.output
    assert "PyVista/VTK" in result.output
    assert "--no-draw-3d --save-plot" in result.output
    assert "Traceback" not in result.output


def test_gui_source_documents_safe_visualization_fallback():
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")
    assert "PyVista/VTK fails" in text
    assert "safe PNG" in text
    assert "draw_3d_error.txt" in text
