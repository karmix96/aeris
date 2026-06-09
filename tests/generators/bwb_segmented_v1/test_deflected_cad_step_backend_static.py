from pathlib import Path


def test_segmented_step_backend_override_is_present():
    text = Path("src/aeris/generators/bwb_segmented_v1/deflected_cad.py").read_text(encoding="utf-8")
    assert "aeris_segmented_cadquery_assembly_v1" in text
    assert "_aeris_split_wing_into_step_runs" in text
    assert "def export_step_physical_deflected_airplane" in text
    assert ".step_bodies.json" in text
