from pathlib import Path

APP = Path("src/aeris/gui/app.py")


def test_gui_exposes_cst_airfoil_library_generation():
    text = APP.read_text(encoding="utf-8")
    assert "Generate CST/Kulfan library" in text
    assert "generate-cst-library" in text
    assert "cst_library_smoke_v1.yaml" in text
    assert "library_report.json" in text


def test_gui_has_active_airfoil_library_selector():
    text = APP.read_text(encoding="utf-8")
    assert "Active airfoil library" in text
    assert "af_active_library" in text
    assert "_airfoil_library_candidates" in text


def test_gui_exposes_cst_airfoil_ml_preset():
    text = APP.read_text(encoding="utf-8")
    assert "airfoil_cst_xfoil_v1" in text
    assert "airfoil_xfoil_v1" in text
    assert "airfoil_id" in text
    assert "2D Airfoil / CST quick ML commands" in text


def test_gui_has_cst_preset_detection_helper():
    text = APP.read_text(encoding="utf-8")
    assert "_airfoil_feature_preset_hint_from_manifest" in text
    assert "has_cst_features" in text
    assert "cst_airfoil_v1" in text
