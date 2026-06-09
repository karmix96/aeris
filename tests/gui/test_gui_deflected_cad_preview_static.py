from pathlib import Path


def test_gui_contains_physical_deflected_cad_preview_panel():
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")
    assert "Physical deflected CAD preview" in text
    assert "export-deflected-cad" in text
    assert "--save-preview" in text
    assert "--draw-3d" in text
    assert "physical_deflected_planform.png" in text
