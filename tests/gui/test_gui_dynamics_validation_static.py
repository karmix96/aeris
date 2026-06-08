from pathlib import Path

APP = Path("src/aeris/gui/app.py")


def test_gui_dynamics_exposes_validation_tab_and_cli_command():
    text = APP.read_text(encoding="utf-8")
    assert "Validate" in text
    assert '"dynamics", "validate"' in text
    assert "dynamics_validation_report.json" in text
    assert "static-margin formula" in text or "static margin" in text
    assert "eigenvalue summary consistency" in text
