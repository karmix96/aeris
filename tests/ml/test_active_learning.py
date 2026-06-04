from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app
from aeris.ml.active_learning import suggest_samples
from aeris.ml.model_promotion import promote_model_run
from aeris.ml.train import train_baseline_model

FEATURE_COLUMNS = [
    "c1_m",
    "b_total_m",
    "sw1_deg",
    "alpha_deg",
    "velocity_mps",
    "altitude_m",
    "control_input_deg",
]
TARGET_COLUMNS = ["cl", "cd", "cm"]




def _inject_test_dataset_promotion_context(model_run_dir: Path, dataset_root: Path) -> None:
    """Give synthetic test model runs the dataset provenance required by model promotion."""
    import json
    from datetime import datetime, timezone

    manifest_path = model_run_dir / "ml_run_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    dataset_block = data.setdefault("dataset", {})
    dataset_block["promotion_context"] = {
        "schema_version": "aeris.test_dataset_promotion_context.v1",
        "status": "approved",
        "dataset_root": str(dataset_root),
        "promotion_manifest_path": str(dataset_root / "promotion_manifest.json"),
        "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
        "promotion_ready_at_time_of_promotion": True,
        "promotion_forced": False,
        "promotion_blockers": [],
        "created_for_test_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    data["dataset"] = dataset_block

    manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "ml_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
        for alpha in [-2.0, 0.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.01 * geom_idx,
                    "sw1_deg": 40.0 + 0.1 * geom_idx,
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": 0.0,
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )
    pd.DataFrame(rows).to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
    (dataset_root / "rejected_aero_rows.csv").write_text("", encoding="utf-8")
    promotion_manifest = {
        "dataset_root": str(dataset_root),
        "promotion_forced": False,
        "promotion_ready_at_time_of_promotion": True,
        "promotion_blockers": [],
        "qc_context": {"qc_preset_used": "production", "geometry_qc_passed": True, "aero_qc_passed": True},
        "artifacts": {
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest, indent=2), encoding="utf-8")
    return dataset_root


def _train_and_promote(tmp_path: Path) -> Path:
    dataset_root = _build_dataset(tmp_path)
    model_run_dir = tmp_path / "model_run"
    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        model_params={"n_estimators": 25},
        output_dir=model_run_dir,
    )
    _inject_test_dataset_promotion_context(model_run_dir, dataset_root)
    result = promote_model_run(
        model_run_dir=model_run_dir,
        max_test_rmse_mean=0.5,
        min_test_r2_mean=-10.0,
    )
    assert result.passed is True
    return model_run_dir


def _candidate_csv(tmp_path: Path, model_run_dir: Path) -> Path:
    df = pd.read_csv(model_run_dir / "train_rows.csv").head(6).copy()
    df = df[FEATURE_COLUMNS].copy()
    df.insert(0, "candidate_name", [f"candidate_{i}" for i in range(len(df))])
    df.loc[0, "alpha_deg"] = 8.0  # intentionally outside typical train alpha envelope
    path = tmp_path / "candidate_pool.csv"
    df.to_csv(path, index=False)
    return path


def test_suggest_samples_writes_ranked_candidates_and_report(tmp_path: Path) -> None:
    model_run_dir = _train_and_promote(tmp_path)
    candidate_csv = _candidate_csv(tmp_path, model_run_dir)
    output_dir = tmp_path / "active_learning_out"

    result = suggest_samples(
        model_run_dir=model_run_dir,
        candidate_csv=candidate_csv,
        output_dir=output_dir,
        top_n=3,
        candidate_id_column="candidate_name",
        objective_column="pred__cl",
        objective_mode="maximize",
    )

    assert (output_dir / "ranked_candidate_samples.csv").exists()
    assert (output_dir / "active_learning_report.json").exists()
    assert len(result.ranked_df) == 6
    assert int(result.ranked_df["recommended"].sum()) == 3
    assert "active_learning_score" in result.ranked_df.columns
    assert "pred__cl" in result.ranked_df.columns
    assert "uncertainty__cl" in result.ranked_df.columns
    assert result.report["n_candidates"] == 6
    assert result.report["n_recommended"] == 3


def test_suggest_samples_cli(tmp_path: Path) -> None:
    model_run_dir = _train_and_promote(tmp_path)
    candidate_csv = _candidate_csv(tmp_path, model_run_dir)
    output_dir = tmp_path / "cli_out"

    runner = CliRunner()
    cli_result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "ml",
            "suggest-samples",
            "--model-run-dir",
            str(model_run_dir),
            "--candidate-csv",
            str(candidate_csv),
            "--output-dir",
            str(output_dir),
            "--top-n",
            "2",
            "--candidate-id-column",
            "candidate_name",
            "--objective-column",
            "pred__cl",
        ],
    )

    assert cli_result.exit_code == 0, cli_result.output
    assert "Active-learning sample suggestion completed" in cli_result.output
    ranked = pd.read_csv(output_dir / "ranked_candidate_samples.csv")
    assert int(ranked["recommended"].sum()) == 2

