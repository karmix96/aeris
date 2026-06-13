from __future__ import annotations

from pathlib import Path


def test_ml_train_records_feature_preset_quick_inspection_aliases() -> None:
    text = Path("src/aeris/ml/train.py").read_text(encoding="utf-8")
    assert "feature_preset_name: str | None = None" in text
    assert '"feature_preset": feature_preset_name' in text
    assert '"feature_columns": list(feature_columns)' in text
    assert '"target_columns": list(target_columns)' in text
    assert '"group_column": group_column' in text
    assert '"model_type": model_type' in text
    assert '"split_method": split.method' in text


def test_ml_cli_prints_feature_preset_separately_from_feature_set() -> None:
    text = Path("src/aeris/commands/ml.py").read_text(encoding="utf-8")
    assert "feature_preset_applied" in text
    assert "feature_set_applied" in text
    assert "feature_preset_name=feature_preset" in text


def test_airfoil_cli_recommends_feature_preset_not_feature_set() -> None:
    text = Path("src/aeris/commands/airfoil.py").read_text(encoding="utf-8")
    assert "_airfoil_feature_preset_hint" in text
    assert "airfoil_cst_xfoil_v1" in text
    assert "--feature-preset" in text
    assert "--feature-set airfoil_xfoil_v1" not in text
