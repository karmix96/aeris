from pathlib import Path


def test_gui_geometry_generate_exposes_save_plot_override() -> None:
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")

    assert "Planform plot" in text
    assert "gg_save_plot_policy" in text
    assert "Force save plot" in text
    assert "Force no plot" in text
    assert '"--save-plot"' in text
    assert '"--no-save-plot"' in text
