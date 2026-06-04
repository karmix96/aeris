from pathlib import Path

APP = Path("src/aeris/gui/app.py")
EVIDENCE = Path("src/aeris/gui/evidence.py")


def test_gui_imports_evidence_helpers():
    text = APP.read_text(encoding="utf-8")
    assert "from aeris.gui.evidence import" in text
    assert "load_workflow_evidence" in text
    assert "summarize_workflow_evidence" in text
    assert "stage_domain_page" in text


def test_gui_home_exposes_backend_owned_workflow_evidence():
    text = APP.read_text(encoding="utf-8")
    assert "Backend-owned workflow evidence" in text
    assert "workflow_status.json" in text
    assert "stage_status.json" in text
    assert "workflow_validation_report.json" in text
    assert "No simulated state" in text


def test_gui_workflow_page_exposes_coverage_audit_and_next_domain():
    text = APP.read_text(encoding="utf-8")
    assert "Workflow coverage audit" in text
    assert "Required blockers" in text
    assert "Open next domain" in text
    assert "backend next_required_stage" in text


def test_evidence_helper_is_read_only_gui_layer():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "build_workflow_coverage_report" in text
    assert "workflow_manifest.json" in text
    assert "workflow_events.jsonl" in text
    assert "does not run solvers" in text.lower()
    assert "does not run geometry" not in text.lower()  # keep wording focused, not copy-pasted boilerplate
