from __future__ import annotations

from aeris.ml.per_regime_residuals import parse_regime_columns, run_per_regime_residuals
from tests.ml.test_learning_curves import _synthetic_grouped_df


def test_parse_regime_columns_defaults_and_dedupes() -> None:
    assert parse_regime_columns(None) == ["alpha_deg", "control_input_deg"]
    assert parse_regime_columns("alpha_deg, control_input_deg, alpha_deg") == ["alpha_deg", "control_input_deg"]


def test_run_per_regime_residuals_writes_artifacts(tmp_path, monkeypatch) -> None:
    import aeris.ml.per_regime_residuals as prr

    df = _synthetic_grouped_df()
    df["control_input_deg"] = 0.0

    def fake_materialize_dataset(**kwargs):
        return df, ["c1_m", "b_total_m", "alpha_deg"], {"fake": True}

    monkeypatch.setattr(prr, "_materialize_dataset_for_learning_curves", fake_materialize_dataset)

    result = run_per_regime_residuals(
        dataset_path=tmp_path,
        feature_columns=["c1_m", "b_total_m", "alpha_deg"],
        target_columns=["cl", "cd", "cm"],
        model_type="linear_regression",
        seeds=[11, 22],
        group_column="geometry_id",
        regime_columns=["alpha_deg", "control_input_deg"],
        min_regime_count=1,
        train_fraction=0.6,
        val_fraction=0.2,
        test_fraction=0.2,
        output_dir=tmp_path / "residuals",
        write_plots=True,
    )

    assert result["schema_version"] == "aeris.per_regime_residuals.v1"
    assert result["status"] == "completed"
    assert result["shape"]["n_residual_rows"] > 0
    assert result["target_summary"]
    assert result["regime_summary"]
    assert result["artifacts"]["per_regime_residuals_report_json"]
    assert (tmp_path / "residuals" / "per_regime_residuals.csv").exists()
    assert (tmp_path / "residuals" / "per_target_residual_summary.csv").exists()
    assert (tmp_path / "residuals" / "regime_residual_summary.csv").exists()
    assert any(item.get("kind") == "per_target_residual_rmse" for item in result.get("plot_artifacts", []))
