from pathlib import Path


def test_gui_geometry_generate_exposes_save_plot_override() -> None:
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")

    assert "Planform plot" in text
    assert "gg_save_plot_policy" in text
    assert "Force save plot" in text
    assert "Force no plot" in text
    assert '"--save-plot"' in text
    assert '"--no-save-plot"' in text


def test_gui_design_variables_show_control_surface_enabled_status() -> None:
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")

    assert "control_surfaces.enabled" in text
    assert "surface_count" in text
    assert "controls_active" in text
    assert "plot_overlay_auto" in text


def test_gui_cad_panel_exposes_step_fallback_evidence() -> None:
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")

    assert "step_backend_final" in text
    assert "assembly_export_error_nonfatal" in text
    assert "per_body_export_errors" in text
    assert "Assembly fallback" in text
    assert "segmented/per-body fallback" in text

def test_gui_physical_deflection_explains_combined_sym_diff_mix() -> None:
    text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")

    assert "right = delta_e_sym_deg + delta_a_diff_deg" in text
    assert "left = delta_e_sym_deg - delta_a_diff_deg" in text
    assert "Both modes are active" in text
    assert "Max |δ|" in text
    assert "CAD stress-test" in text
