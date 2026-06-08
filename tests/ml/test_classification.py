from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.classification import classify_targets, compare_classifiers, list_classifier_types


def _write_promoted_classification_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(6):
        geom = f"geom_{i:05d}"
        for alpha in (0.0, 2.0):
            trim_margin = 6.0 - i - alpha
            red_flag = trim_margin < 2.0
            flyable = not red_flag
            rows.append(
                {
                    "geometry_id": geom,
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": 0.0,
                    "delta_e_sym_deg": 0.0,
                    "c1_m": 1.2 + 0.1 * i,
                    "b_total_m": 1.4 + 0.05 * i,
                    "sw1_deg": -30.0 - i,
                    "longitudinal_basic_flyable_int": int(flyable),
                    "red_flag_int": int(red_flag),
                    "label_failure_stage": "trim" if red_flag else "none",
                }
            )
    df = pd.DataFrame(rows)
    curated = root / "curated_aero_dataset.csv"
    df.to_csv(curated, index=False)
    (root / "curation_report.json").write_text(json.dumps({"promotion_ready": True}), encoding="utf-8")
    (root / "final_run_summary.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (root / "promotion_manifest.json").write_text(
        json.dumps(
            {
                "promotion_forced": False,
                "promotion_ready_at_time_of_promotion": True,
                "promotion_blockers": [],
                "artifacts": {"curated_aero_dataset_csv": str(curated.resolve())},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


def test_list_classifier_types_contains_expected_models() -> None:
    types = list_classifier_types()
    assert "logistic_regression" in types
    assert "random_forest_classifier" in types
    assert "extra_trees_classifier" in types


def test_classify_targets_writes_summary_and_metrics(tmp_path: Path) -> None:
    ds = _write_promoted_classification_dataset(tmp_path / "ds")
    out = tmp_path / "classify"

    result = classify_targets(
        dataset_path=ds,
        feature_columns=["c1_m", "b_total_m", "sw1_deg", "alpha_deg", "velocity_mps", "altitude_m", "control_input_deg"],
        target_columns=["longitudinal_basic_flyable_int", "red_flag_int"],
        classifier_type="logistic_regression",
        split_method="grouped",
        group_column="geometry_id",
        random_seed=123,
        output_dir=out,
    )

    assert result["status"] == "completed"
    assert result["classifier_type"] == "logistic_regression"
    assert (out / "classification_summary.json").exists()
    assert (out / "classification_per_target_metrics.csv").exists()
    assert (out / "classification_predictions_test.csv").exists()
    assert "balanced_accuracy_mean" in result["metrics"]["test"]["overall"]


def test_compare_classifiers_writes_ranking(tmp_path: Path) -> None:
    ds = _write_promoted_classification_dataset(tmp_path / "ds")
    out = tmp_path / "compare"

    result = compare_classifiers(
        dataset_path=ds,
        feature_columns=["c1_m", "b_total_m", "sw1_deg", "alpha_deg", "velocity_mps", "altitude_m", "control_input_deg"],
        target_columns=["longitudinal_basic_flyable_int", "red_flag_int"],
        classifier_types=["logistic_regression", "random_forest_classifier"],
        split_method="grouped",
        group_column="geometry_id",
        random_seed=123,
        output_dir=out,
    )

    assert result["status"] == "completed"
    assert result["best_by_f1_weighted"] in {"logistic_regression", "random_forest_classifier"}
    assert (out / "classifier_comparison_summary.json").exists()
    assert (out / "classifier_comparison_summary.csv").exists()
