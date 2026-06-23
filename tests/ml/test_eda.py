"""Tests for aeris.ml.eda — EDA module."""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aeris.ml.eda import (
    EDA_SCHEMA_VERSION,
    _detect_constant_columns,
    _detect_duplicates,
    _correlation_matrix,
    _per_geometry_coverage,
    _alpha_control_coverage,
    _outlier_scan,
    _nonlinearity_scan,
    _robust_outlier_scan,
    compare_eda_reports,
    run_eda,
    run_promoted_dataset_eda,
)


def _make_df() -> pd.DataFrame:
    rows = []
    for geom_id in [f"g{i}" for i in range(1, 5)]:
        for alpha in [-2.0, 0.0, 2.0, 4.0]:
            for ctrl in [-5.0, 0.0, 5.0]:
                rows.append({
                    "geometry_id": geom_id,
                    "c1_m": 1.5,
                    "b_total_m": 1.6,
                    "sw1_deg": -35.0,
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": ctrl,
                    "cl": 0.1 * alpha + 0.02 * ctrl,
                    "cd": 0.02 + 0.001 * alpha ** 2,
                    "cm": -0.01 * ctrl,
                })
    return pd.DataFrame(rows)


FEATURES = ["c1_m", "b_total_m", "sw1_deg", "alpha_deg", "velocity_mps", "altitude_m", "control_input_deg"]
TARGETS = ["cl", "cd", "cm"]


def test_run_eda_returns_schema_version():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    assert report["schema_version"] == EDA_SCHEMA_VERSION


def test_run_eda_shape():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    assert report["shape"]["n_rows"] == len(df)
    assert report["shape"]["n_columns"] == len(df.columns)


def test_run_eda_no_constants():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    # velocity_mps and c1_m are constant in this fixture
    assert "velocity_mps" in report["constant_columns"]["constant_columns"]


def test_run_eda_no_duplicates():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    assert report["duplicates"]["has_duplicates"] is False


def test_run_eda_duplicates_detected():
    df = pd.concat([_make_df(), _make_df()], ignore_index=True)
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    assert report["duplicates"]["has_duplicates"] is True
    assert report["duplicates"]["n_duplicate_rows"] == len(_make_df())


def test_run_eda_geometry_coverage():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    cov = report["per_geometry_coverage"]
    assert cov["n_geometries"] == 4
    assert cov["uniform_coverage"] is True


def test_run_eda_alpha_control_coverage():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    cov = report["alpha_control_coverage"]
    assert cov["n_alpha_values"] == 4
    assert cov["n_control_values"] == 3


def test_run_eda_v2_reports_missingness_dtypes_and_physics_sanity():
    df = _make_df()
    df.loc[0, "cl"] = np.nan
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)

    assert report["schema_version"] == "aeris.eda_report.v2"
    assert report["missingness"]["n_columns_with_missing"] >= 1
    assert report["missingness"]["by_column"]["cl"]["n_missing"] == 1
    assert report["dtypes"]["columns"]["alpha_deg"]["is_numeric_like"] is True
    assert "cd_sanity" in report["aero_physics_sanity"]
    assert report["aero_physics_sanity"]["cd_sanity"]["passed_positive_cd_check"] is True
    assert report["operator_recommendations"]


def test_run_eda_v21_reports_aerospace_refinement_blocks():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)

    assert report["regime_summary"]["status"] == "computed"
    assert report["regime_outliers"]["status"] == "computed"
    assert report["polar_diagnostics"]["status"] == "computed"
    assert report["control_effect_sanity"]["status"] == "computed"
    assert report["design_space_projection"]["status"] == "computed"
    assert report["learning_readiness"]["scale_label"] in {
        "smoke_only",
        "canary_or_small_pilot",
        "pilot_scale",
    }
    assert "cl" in report["learning_readiness"]["target_readiness"]


def test_run_eda_feature_stats_keys():
    df = _make_df()
    report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)
    for col in FEATURES:
        assert col in report["feature_stats"]
        assert "min" in report["feature_stats"][col]


def test_run_eda_skips_constant_columns_without_runtime_warnings():
    df = _make_df()
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        report = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS)

    skipped = {item["column"] for item in report["correlation"].get("skipped_columns", [])}
    assert "velocity_mps" in skipped
    assert "altitude_m" in skipped
    assert report["nonlinearity"]["cl"]["velocity_mps"]["status"] == "skipped"


def test_correlation_matrix_skips_constant_columns_explicitly():
    df = pd.DataFrame({"constant": [1.0, 1.0, 1.0, 1.0], "x": [1.0, 2.0, 3.0, 4.0], "y": [2.0, 4.0, 6.0, 8.0]})
    result = _correlation_matrix(df, ["constant", "x", "y"])
    assert result["columns"] == ["x", "y"]
    assert result["matrix"]["x"]["y"] == 1.0
    assert result["skipped_columns"][0]["column"] == "constant"
    assert result["skipped_columns"][0]["reason"] == "constant_or_single_unique_value"


def test_run_eda_writes_json(tmp_path: Path):
    df = _make_df()
    out = tmp_path / "eda_report.json"
    run_eda(df, feature_columns=FEATURES, target_columns=TARGETS, output_path=out)
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["schema_version"] == EDA_SCHEMA_VERSION


def test_detect_constant_columns():
    df = pd.DataFrame({"a": [1, 1, 1], "b": [1, 2, 3]})
    result = _detect_constant_columns(df)
    assert "a" in result["constant_columns"]
    assert "b" not in result["constant_columns"]


def test_outlier_scan_flags_extreme():
    df = pd.DataFrame({"x": [0.0] * 50 + [1000.0]})
    result = _outlier_scan(df, ["x"], sigma=4.0)
    assert "x" in result["columns_with_outliers"]


def test_robust_outlier_scan_flags_extreme():
    df = pd.DataFrame({"x": [0.0] * 50 + [1000.0]})
    result = _robust_outlier_scan(df, ["x"])
    assert "x" in result["columns"]
    assert result["columns"]["x"]["iqr_outlier_count"] > 0


def test_nonlinearity_scan_detects_nonlinear():
    # y = exp(x) is monotonic but nonlinear:
    # Spearman r = 1.0 (perfect rank correlation), Pearson r < 1.0 (curve).
    # The gap between them measures nonlinearity. For exp(x) it is ~0.10.
    x = np.linspace(-2, 2, 100)
    df = pd.DataFrame({"x": x, "y": np.exp(x)})
    result = _nonlinearity_scan(df, ["x"], ["y"])
    # Assert Spearman > Pearson, which is the correct statement for a
    # monotonic nonlinear relationship (gap direction, not magnitude).
    pearson_r = abs(result["y"]["x"]["pearson_r"])
    spearman_r = abs(result["y"]["x"]["spearman_r"])
    assert spearman_r > pearson_r, (
        f"Expected spearman_r ({spearman_r:.4f}) > pearson_r ({pearson_r:.4f}) "
        "for exponential nonlinearity"
    )


def _write_promoted_dataset(root: Path, df: pd.DataFrame) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    curated = root / "curated_aero_dataset.csv"
    rejected = root / "rejected_aero_rows.csv"
    df.to_csv(curated, index=False)
    rejected.write_text("", encoding="utf-8")
    manifest = {
        "dataset_root": str(root),
        "promotion_forced": False,
        "promotion_ready_at_time_of_promotion": True,
        "promotion_blockers": [],
        "artifacts": {
            "curated_aero_dataset_csv": str(curated),
            "rejected_aero_rows_csv": str(rejected),
        },
    }
    (root / "promotion_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def test_run_promoted_dataset_eda_writes_operator_artifacts(tmp_path: Path):
    dataset = _write_promoted_dataset(tmp_path / "promoted", _make_df())
    out = tmp_path / "eda_out"

    result = run_promoted_dataset_eda(
        dataset_root=dataset,
        feature_columns=FEATURES,
        target_columns=TARGETS,
        output_dir=out,
        write_plots=False,
    )

    assert result["report_path"].exists()
    assert result["summary_path"].exists()
    loaded = json.loads(result["report_path"].read_text(encoding="utf-8"))
    assert loaded["schema_version"] == EDA_SCHEMA_VERSION
    assert loaded["metadata"]["dataset_root"] == str(dataset.resolve())
    assert loaded["shape"]["n_rows"] == len(_make_df())


def test_run_promoted_dataset_eda_feature_set_materializes_engineered_columns(tmp_path: Path):
    dataset = _write_promoted_dataset(tmp_path / "promoted_fs", _make_df())
    out = tmp_path / "eda_fs_out"

    result = run_promoted_dataset_eda(
        dataset_root=dataset,
        feature_set_name="bwb_control_physics_v1",
        target_columns=TARGETS,
        output_dir=out,
        write_plots=False,
    )

    loaded = json.loads(result["report_path"].read_text(encoding="utf-8"))
    assert loaded["feature_set"]["feature_set_name"] == "bwb_control_physics_v1"
    assert loaded["feature_set"]["feature_set_applied"] is True
    assert "alpha_deg_sq" in loaded["metadata"]["engineered_columns"]
    assert "re_number" in loaded["metadata"]["final_feature_columns"]
    assert "alpha_deg_sq" in loaded["feature_stats"]
    assert loaded["feature_set"]["transform_manifest"]["n_engineered_columns"] > 0
    assert loaded["metadata"]["row_count"] == loaded["shape"]["n_rows"]
    assert loaded["metadata"]["column_count"] == loaded["shape"]["n_columns"]


def test_run_promoted_dataset_eda_rejects_columns_and_feature_set_together(tmp_path: Path):
    dataset = _write_promoted_dataset(tmp_path / "promoted_conflict", _make_df())

    with pytest.raises(ValueError, match="either feature_columns or feature_set_name"):
        run_promoted_dataset_eda(
            dataset_root=dataset,
            feature_columns=FEATURES,
            feature_set_name="bwb_control_raw",
            target_columns=TARGETS,
            output_dir=tmp_path / "eda_conflict",
            write_plots=False,
        )



def test_compare_eda_reports_summarizes_multiple_reports(tmp_path: Path):
    df = _make_df()
    p1 = tmp_path / "eda1.json"
    p2 = tmp_path / "eda2.json"
    r1 = run_eda(df, feature_columns=FEATURES, target_columns=TARGETS, output_path=p1)
    r2 = run_eda(df.iloc[:20].copy(), feature_columns=FEATURES, target_columns=TARGETS, output_path=p2)
    assert r1["schema_version"] == EDA_SCHEMA_VERSION
    assert r2["schema_version"] == EDA_SCHEMA_VERSION

    comparison = compare_eda_reports([p1, p2])
    assert comparison["schema_version"] == "aeris.eda_comparison.v1"
    assert comparison["n_reports"] == 2
    assert comparison["reports"][0]["rows"] == len(df)


def test_write_eda_plots_includes_v21_artifacts(tmp_path: Path):
    from aeris.ml.eda import write_eda_plots

    df = _make_df()
    artifacts = write_eda_plots(
        df,
        feature_columns=FEATURES,
        target_columns=TARGETS,
        output_dir=tmp_path,
    )
    written = {a.get("kind") for a in artifacts if a.get("status") == "written"}
    assert "aero_polar_cl_vs_cd" in written
    assert "targets_vs_features" in written
    assert "target_boxplots_by_alpha" in written
    assert "top_pairplot" in written
    assert "design_space_pca" in written
    assert "regime_target_means" in written
    assert "polar_fit_quality" in written
    assert "control_effect_slopes" in written
