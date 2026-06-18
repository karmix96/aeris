from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_sidebar_uses_clear_2d_and_3d_domain_names() -> None:
    text = APP.read_text(encoding="utf-8")

    assert '"Overview"' in text
    assert '"2D Airfoils"' in text
    assert '"3D Geometry"' in text


def test_airfoil_library_page_exposes_two_first_class_sources() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "Import existing airfoils (.dat)" in text
    assert "Generate CST/Kulfan airfoils" in text
    assert "af_library_source_workflow" in text
    assert "Active library path" in text
    assert "Origin" in text


def test_xfoil_solver_check_lives_near_sweep_context() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "XFOIL readiness" in text
    assert "Check XFOIL binary" in text
    assert "before running sweeps" in text


def test_home_is_minimal_overview_launchpad() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "AERIS Overview" in text
    assert "Use this page as a launchpad only" in text
    assert "Import airfoil library" in text
    assert "Generate CST airfoils" in text
    assert "Generate 3D geometry" in text
    assert "Export deflected CAD" in text
