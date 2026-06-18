from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_gui_exposes_production_qc_profile_and_preset_semantics() -> None:
    text = APP.read_text(encoding="utf-8")

    assert 'QC_PROFILES  = ["basic", "production", "strict"]' in text
    assert "Production — physical QC + block on failures" in text
    assert "Production QC</b> now includes physical geometry checks" in text
    assert "aero CL-alpha and Cm-control sign checks" in text
    assert "Strict QC</b> additionally keeps statistical outliers, L/D, beta=0 lateral sanity, and target-variation checks" in text


def test_gui_describes_manifest_grid_and_airfoil_coverage_gates() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "manifest-defined sweep grid" in text
    assert "including beta/rates/differential controls" in text
    assert "duplicate key incl. ncrit" in text
    assert "at least 3 converged rows per airfoil/Re/Mach group" in text
    assert "per_group_coverage_failures" in text
    assert "insufficient" in text and "per-group coverage" in text
    assert "airfoil_qc_report.json" in text


def test_gui_model_promotion_mentions_dataset_promotion_context() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "Dataset promotion context is rechecked here" in text
    assert "force-promoted datasets and recorded QC/curation blockers" in text
