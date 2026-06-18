from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_airfoil_gui_has_library_selector_before_xfoil_sweep() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "_airfoil_library_candidates" in text
    assert "_airfoil_inventory_count" in text
    assert "_airfoil_library_origin" in text
    assert "af_active_library_choice" in text
    assert "Use custom airfoil library path" in text


def test_airfoil_gui_caps_xfoil_subset_by_selected_library_count() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "active_airfoil_count" in text
    assert "sweep_slider_max = max(1, int(active_airfoil_count))" in text
    assert "Airfoils to sweep from active library (--n-airfoils)" in text
    assert "XFOIL does not create airfoils" in text
    assert "cannot exceed the selected library size" in text


def test_airfoil_gui_passes_selected_library_to_xfoil_dataset_generate() -> None:
    text = APP.read_text(encoding="utf-8")

    assert '"airfoil", "dataset", "generate"' in text
    assert '"--library", str(lib_dir)' in text
    assert '"--n-airfoils", str(n_airfoils)' in text
