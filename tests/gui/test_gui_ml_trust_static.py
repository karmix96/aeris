from pathlib import Path

APP = Path("src/aeris/gui/app.py")


def test_gui_ml_trust_tab_static_markers() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "⑫ ML Trust" in text
    assert "ML Trust diagnostics" in text
    assert "Run learning curves" in text
    assert "Run repeated grouped CV" in text
    assert "Run per-regime residual diagnostics" in text
    assert "learning-curves" in text
    assert "repeated-grouped-cv" in text
    assert "per-regime-residuals" in text
    assert "--plots / generate PNG plots" in text
    assert "Plot gallery" in text
    assert "Learning curve plots" in text
    assert "Repeated CV plots" in text
    assert "Per-regime residual plots" in text
    assert "st.image" in text
    assert "learning_curve_r2.png" in text
    assert "per_target_learning_curves.png" in text
    assert "per_target_final_r2.png" in text
    assert "per_target_repeated_cv_r2.png" in text
    assert "regime_rmse_alpha_control.png" in text
    assert "learning_curves_report.json" in text
    assert "repeated_grouped_cv_report.json" in text
    assert "per_regime_residuals_report.json" in text
    assert "Evidence package viewer" in text
    assert "Build evidence package" in text
    assert "package-evidence" in text
    assert "paper1_evidence_package" in text
    assert "evidence_package_summary.md" in text
    assert "evidence_artifact_index.csv" in text
    assert "evidence_package_manifest.json" in text
    assert "Load evidence package summary" in text
    assert "Load artifact index CSV" in text
    assert "Load evidence manifest JSON" in text
    assert "counts_raw = evi_manifest_data.get(\"counts\")" in text
    assert "present_count = counts.get(\"present\"" in text
    assert "missing_required_count = counts.get(\"missing_required\"" in text
