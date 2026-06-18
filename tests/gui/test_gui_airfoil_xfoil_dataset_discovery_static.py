from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_airfoil_gui_discovers_generated_xfoil_datasets_by_csv() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "_airfoil_xfoil_dataset_candidates" in text
    assert '"data" / "datasets"' in text
    assert "airfoil_dataset.csv" in text


def test_airfoil_polar_viewer_uses_xfoil_dataset_discovery_not_library_list() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "polar_ds_dirs = _airfoil_xfoil_dataset_candidates(root)" in text
    assert "format_func=_airfoil_xfoil_dataset_label" in text
    assert "Expected folders containing airfoil_dataset.csv" in text
    assert "Manual dataset folder" in text
