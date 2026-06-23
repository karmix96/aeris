from __future__ import annotations

from aeris.ml.repeated_grouped_cv import run_repeated_grouped_cv
from tests.ml.test_learning_curves import _synthetic_grouped_df


def test_run_repeated_grouped_cv_on_dataframe_like_dataset(tmp_path, monkeypatch) -> None:
    # Use the lower-level materialization seam by monkeypatching the dataset materializer.
    import aeris.ml.repeated_grouped_cv as rcv

    df = _synthetic_grouped_df()

    def fake_materialize_dataset(**kwargs):
        return df, ["c1_m", "b_total_m", "alpha_deg"], {"fake": True}

    monkeypatch.setattr(rcv, "_materialize_dataset_for_learning_curves", fake_materialize_dataset)

    result = run_repeated_grouped_cv(
        dataset_path=tmp_path,
        feature_columns=["c1_m", "b_total_m", "alpha_deg"],
        target_columns=["cl", "cd", "cm"],
        model_type="linear_regression",
        seeds=[11, 22, 33],
        group_column="geometry_id",
        train_fraction=0.6,
        val_fraction=0.2,
        test_fraction=0.2,
        output_dir=tmp_path / "rcv",
        write_plots=True,
    )

    assert result["schema_version"] == "aeris.repeated_grouped_cv.v1"
    assert result["status"] == "completed"
    assert result["overall_summary"]["n_runs"] == 3
    assert len(result["per_target_summary"]) == 3
    assert (tmp_path / "rcv" / "repeated_grouped_cv_report.json").exists()
    assert (tmp_path / "rcv" / "repeated_grouped_cv_per_target_summary.csv").exists()
    assert any(p.get("kind") == "per_target_repeated_cv_r2" for p in result["plot_artifacts"])
