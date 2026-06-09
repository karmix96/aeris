from pathlib import Path

APP = Path("src/aeris/gui/app.py")


def test_gui_geometry_page_exposes_cad_export_controls():
    text = APP.read_text(encoding="utf-8")
    assert "⑤ CAD export" in text
    assert "Export CAD" in text
    assert "Export format selector" in text
    assert "OpenVSP executable/path" in text
    assert "STEP backend" in text
    assert "Output directory" in text


def test_gui_cad_export_uses_backend_cli_not_fake_logic():
    text = APP.read_text(encoding="utf-8")
    assert '"geometry", "export-cad"' in text
    assert '"--formats"' in text
    assert '"--openvsp-command"' in text
    assert "cad_exports" in text
    assert "geometry_export_manifest.json" in text
    assert "stdout.txt" in text
    assert "stderr.txt" in text
