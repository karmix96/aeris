from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app


def test_gui_help_is_registered_without_streamlit_import_requirement():
    runner = CliRunner()
    result = runner.invoke(app, ["--no-check-writable", "gui", "--help"])
    assert result.exit_code == 0
    assert "run" in result.output


def test_gui_run_help_is_registered():
    runner = CliRunner()
    result = runner.invoke(app, ["--no-check-writable", "gui", "run", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output


def test_gui_app_source_contains_core_operator_tabs():
    source = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")
    assert "Config Lab" in source
    assert "Unified aero dataset" in source
    assert "control-input" in source or "control input" in source
    assert "ML" in source
