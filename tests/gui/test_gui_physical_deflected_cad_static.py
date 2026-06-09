from pathlib import Path


def test_gui_exposes_physical_deflected_cad_workstation_controls():
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")

    required = [
        "export-deflected-cad",
        "--delta-e-sym-deg",
        "--delta-a-diff-deg",
        "--deflection-topology",
        "split-elevon",
        "unified-abrupt",
        "--hinge-gap-fraction",
        "--boundary-epsilon-fraction",
        "--save-preview",
        "--draw-3d",
        "physical_deflected_geometry_export_manifest.json",
        "physical_deflected_geometry.step_bodies.json",
        "physical_deflected_planform.png",
        "physical_control_deflection.json",
        "bwb_25_sections_asym_controls.yaml",
        "bwb_training_v2.yaml",
        "bwb_training_v3.yaml",
    ]
    for needle in required:
        assert needle in text


def test_gui_keeps_neutral_cad_export_controls():
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")
    assert "export-cad" in text
    assert "--step-backend" in text
    assert "geometry_export_manifest.json" in text
    assert "openvsp-doctor" in text
