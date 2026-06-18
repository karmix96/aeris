from pathlib import Path


def test_gui_design_variables_show_control_surface_enabled_status() -> None:
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")

    assert "control_surfaces.enabled" in text
    assert "surface_count" in text
    assert "controls_active" in text
    assert "plot_overlay_auto" in text
