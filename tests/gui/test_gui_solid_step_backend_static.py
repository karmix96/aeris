from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_gui_exposes_solid_step_backend_and_metadata() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "solid" in text
    assert "--step-backend" in text
    assert "Solid STEP validation metadata" in text
    assert "_render_solid_step_metadata" in text
    assert "backend_final" in text
    assert "solid_count" in text
    assert "face_count" in text
    assert "volume_m3" in text
    assert "bbox_x_m" in text
    assert "bbox_y_m" in text
    assert "bbox_z_m" in text
