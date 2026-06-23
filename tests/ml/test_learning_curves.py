from __future__ import annotations

import json

import numpy as np
import pandas as pd

from aeris.ml.learning_curves import parse_int_csv, run_learning_curves_on_dataframe


def _synthetic_grouped_df() -> pd.DataFrame:
    rows = []
    for gid in range(9):
        geom = f"g{gid:02d}"
        c1 = 1.0 + 0.05 * gid
        b = 1.6 + 0.03 * gid
        for alpha in [-2.0, 0.0, 2.0, 4.0, 6.0]:
            cl = 0.15 + 0.07 * alpha + 0.2 * c1
            cd = 0.015 + 0.002 * alpha**2 + 0.01 * (b - 1.6)
            cm = -0.05 - 0.03 * alpha + 0.1 * (c1 - 1.0)
            rows.append(
                {
                    "geometry_id": geom,
                    "c1_m": c1,
                    "b_total_m": b,
                    "alpha_deg": alpha,
                    "cl": cl,
                    "cd": cd,
                    "cm": cm,
                }
            )
    return pd.DataFrame(rows)


def test_parse_int_csv_sorts_and_deduplicates() -> None:
    assert parse_int_csv("20,10,10,5") == [5, 10, 20]


def test_run_learning_curves_on_dataframe_writes_artifacts(tmp_path) -> None:
    df = _synthetic_grouped_df()
    result = run_learning_curves_on_dataframe(
        df=df,
        feature_columns=["c1_m", "b_total_m", "alpha_deg"],
        target_columns=["cl", "cd", "cm"],
        model_type="linear_regression",
        group_sizes=[2, 4],
        seeds=[11, 22],
        split_method="grouped",
        group_column="geometry_id",
        train_fraction=0.6,
        val_fraction=0.2,
        test_fraction=0.2,
        output_dir=tmp_path,
        write_plots=True,
    )

    assert result["schema_version"] == "aeris.learning_curves.v1.3"
    assert result["status"] == "completed"
    assert len(result["summary_rows"]) == 2
    assert result["summary_rows"][-1]["group_size"] == 4
    assert result["summary_rows"][-1]["test_r2_mean_mean"] is not None
    assert result["per_target_summary"]
    assert "target_diagnostics" in result
    assert "normalization" in result
    assert "informative_target_columns" in result
    assert {row["target"] for row in result["per_target_summary"]} == {"cl", "cd", "cm"}
    assert all(row["learning_state"] for row in result["per_target_summary"])

    artifacts = result["artifacts"]
    assert (tmp_path / "learning_curves.csv").exists()
    assert (tmp_path / "learning_curves_summary.csv").exists()
    assert (tmp_path / "learning_curves_per_target_summary.csv").exists()
    assert (tmp_path / "learning_curves_target_diagnostics.csv").exists()
    assert (tmp_path / "learning_curves_report.json").exists()
    assert (tmp_path / "learning_curves_summary.md").exists()
    assert (tmp_path / "plots" / "learning_curve_r2.png").exists()
    assert (tmp_path / "plots" / "per_target_learning_curves.png").exists()
    assert (tmp_path / "plots" / "per_target_final_r2.png").exists()
    assert (tmp_path / "plots" / "learning_curve_informative_r2.png").exists()
    assert (tmp_path / "plots" / "learning_curve_nrmse_by_std.png").exists()
    assert (tmp_path / "plots" / "per_target_final_nrmse.png").exists()

    report = json.loads((tmp_path / "learning_curves_report.json").read_text(encoding="utf-8"))
    assert report["artifacts"]["learning_curves_csv"] == artifacts["learning_curves_csv"]
    assert report["operator_recommendations"]



def test_learning_curves_per_target_summary_classifies_weak_target(tmp_path) -> None:
    df = _synthetic_grouped_df()
    rng = np.random.default_rng(123)
    df["noisy"] = rng.normal(size=len(df))
    result = run_learning_curves_on_dataframe(
        df=df,
        feature_columns=["c1_m", "b_total_m", "alpha_deg"],
        target_columns=["cl", "noisy"],
        model_type="linear_regression",
        group_sizes=[2, 4],
        seeds=[11, 22],
        split_method="grouped",
        group_column="geometry_id",
        train_fraction=0.6,
        val_fraction=0.2,
        test_fraction=0.2,
        output_dir=tmp_path,
        write_plots=True,
    )
    by_target = {row["target"]: row for row in result["per_target_summary"]}
    assert by_target["noisy"]["learning_state"] in {"weak", "moderate", "overfit_risk", "unknown"}
    assert by_target["noisy"]["recommendation"]



def test_resolve_target_columns_from_dataframe_auto_sets() -> None:
    from aeris.ml.learning_curves import resolve_target_columns_from_dataframe

    df = _synthetic_grouped_df()
    df["l_over_d"] = df["cl"] / df["cd"]
    df["velocity_mps"] = 28.0
    df["config_name"] = "demo"

    targets = resolve_target_columns_from_dataframe(
        df,
        "aero_all",
        feature_columns=["c1_m", "b_total_m", "alpha_deg"],
        group_column="geometry_id",
    )

    assert "cl" in targets
    assert "cd" in targets
    assert "cm" in targets
    assert "l_over_d" in targets
    assert "alpha_deg" not in targets
    assert "velocity_mps" not in targets
    assert "geometry_id" not in targets



def test_learning_curves_flags_constant_targets(tmp_path) -> None:
    df = _synthetic_grouped_df()
    df["constant_target"] = 0.0
    result = run_learning_curves_on_dataframe(
        df=df,
        feature_columns=["c1_m", "b_total_m", "alpha_deg"],
        target_columns=["cl", "constant_target"],
        model_type="linear_regression",
        group_sizes=[2, 4],
        seeds=[11, 22],
        split_method="grouped",
        group_column="geometry_id",
        train_fraction=0.6,
        val_fraction=0.2,
        test_fraction=0.2,
        output_dir=tmp_path,
        write_plots=True,
    )
    by_target = {row["target"]: row for row in result["per_target_summary"]}
    assert by_target["constant_target"]["is_near_constant"] is True
    assert by_target["constant_target"]["learning_state"] == "constant_or_near_constant"
    assert "constant_target" in result["excluded_from_informative_score_target_columns"]
    assert "constant_target" not in result["informative_target_columns"]
    assert result["normalization"]["used_for_training"] is False
