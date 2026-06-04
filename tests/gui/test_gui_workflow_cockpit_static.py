from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_gui_exposes_workflow_cockpit_page():
    text = APP.read_text(encoding="utf-8")
    assert '("workflow", "▤",  "Workflow Cockpit")' in text
    assert '"workflow": pg_workflow' in text
    assert 'def pg_workflow(' in text


def test_gui_workflow_cockpit_uses_workflow_cli_commands():
    text = APP.read_text(encoding="utf-8")
    for command in [
        '"workflow", "init"',
        '"workflow", "status"',
        '"workflow", "next"',
        '"workflow", "validate"',
        '"workflow", "doctor"',
        '"workflow", "record-stage"',
    ]:
        assert command in text


def test_gui_workflow_cockpit_reads_validation_report_without_backend_duplication():
    text = APP.read_text(encoding="utf-8")
    assert "workflow_validation_report.json" in text
    assert "_workflow_stage_rows" in text
    assert "This panel is a cockpit over <b>aeris workflow</b>" in text
