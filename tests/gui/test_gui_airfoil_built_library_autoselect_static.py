from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_airfoil_gui_requires_manual_library_choice() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "__AERIS_CHOOSE_AIRFOIL_LIBRARY__" in text
    assert "Choose active airfoil library..." in text
    assert "active_airfoil_library_selected" in text
    assert "Manually choose which existing airfoil library XFOIL should sweep" in text


def test_airfoil_gui_labels_cst_libraries_with_seed() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "cst_airfoil_library_manifest.json" in text
    assert "seed=" in text
    assert "any CST/Kulfan-generated library" in text
