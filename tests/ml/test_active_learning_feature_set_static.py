from __future__ import annotations

from pathlib import Path


def test_active_learning_supports_feature_set_candidate_materialization() -> None:
    text = Path("src/aeris/ml/active_learning/suggest.py").read_text(encoding="utf-8")

    assert "prepare_dataframe_for_feature_set_inference" in text
    assert "trained_feature_set_name_from_config" in text
    assert "feature_set_name: str | None = None" in text
    assert "allow_feature_set_mismatch: bool = False" in text
    assert "materialized_candidate_pool.csv" in text
    assert "active_learning_feature_engineering_manifest.json" in text
    assert '"feature_set_applied"' in text


def test_suggest_samples_cli_exposes_feature_set_flags() -> None:
    text = Path("src/aeris/commands/ml.py").read_text(encoding="utf-8")

    suggest_idx = text.find('@ml_app.command("suggest-samples")')
    predict_idx = text.find('@ml_app.command("predict")')
    assert suggest_idx != -1
    assert predict_idx != -1

    suggest_block = text[suggest_idx:predict_idx]
    assert "--feature-set" in suggest_block
    assert "--allow-feature-set-mismatch" in suggest_block
    assert "feature_set_name=feature_set" in suggest_block
    assert "allow_feature_set_mismatch=allow_feature_set_mismatch" in suggest_block
