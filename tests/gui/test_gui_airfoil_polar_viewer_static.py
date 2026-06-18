from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_airfoil_gui_exposes_saved_polar_viewer() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "Dataset polar viewer" in text
    assert "_render_airfoil_polar_viewer" in text
    assert "View XFOIL polar curves from an existing generated dataset" in text


def test_airfoil_polar_viewer_supports_core_plot_types() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "CL vs alpha" in text
    assert "CD vs alpha" in text
    assert "Cm vs alpha" in text
    assert "CL vs CD drag polar" in text
    assert "Save this plot as PNG" in text


def test_airfoil_polar_viewer_uses_saved_dataset_csv_not_live_xfoil() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "airfoil_dataset.csv" in text
    assert "Plot converged rows only" in text
    assert "This is different from live <code>--show-plots</code>" in text
