from __future__ import annotations

import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app
from aeris.ml.evidence_package import build_evidence_package


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_dataset(tmp_path: Path) -> Path:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _write_json(dataset / "promotion_manifest.json", {
        "status": "approved",
        "promotion_ready_at_time_of_promotion": True,
        "promotion_forced": False,
    })
    _write_json(dataset / "curation_report.json", {"status": "complete", "kept_rows": 10, "rejected_rows": 1})
    _write_json(dataset / "final_run_summary.json", {"status": "complete"})
    _write_json(dataset / "eda" / "eda_report.json", {"metadata": {"schema_version": "aeris.eda_report.v2", "row_count": 10}})
    _write_json(dataset / "learning_curves" / "learning_curves_report.json", {"schema_version": "aeris.learning_curves.v1.3", "status": "completed"})
    _write_text(dataset / "learning_curves" / "learning_curves_summary.md", "# LC")
    _write_json(dataset / "repeated_grouped_cv" / "repeated_grouped_cv_report.json", {"schema_version": "aeris.repeated_grouped_cv.v1", "status": "completed"})
    _write_json(dataset / "per_regime_residuals" / "per_regime_residuals_report.json", {"schema_version": "aeris.per_regime_residuals.v1", "status": "completed", "n_regime_rows": 5})
    _write_text(dataset / "per_regime_residuals" / "plots" / "regime_rmse_alpha_control.png", "fake-png")
    return dataset


def _make_model_run(tmp_path: Path) -> Path:
    model = tmp_path / "model_run"
    model.mkdir()
    _write_json(model / "model_promotion_manifest.json", {"status": "approved", "promotion_ready_at_time_of_promotion": True})
    _write_json(model / "model_card.json", {"status": "approved"})
    _write_json(model / "training_envelope.json", {"features": {}})
    _write_json(model / "metrics.json", {"test": {}})
    _write_json(model / "train_config.json", {"target_columns": ["cl"], "feature_columns": ["alpha_deg"]})
    _write_json(model / "quality" / "model_audit" / "model_quality_report.json", {"status": "passed", "passed": True})
    _write_json(model / "promotion_gate_suggestions" / "promotion_gate_suggestions.json", {"status": "complete"})
    return model


def test_build_evidence_package_indexes_and_copies_artifacts(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    model = _make_model_run(tmp_path)
    out = tmp_path / "evidence"

    result = build_evidence_package(
        dataset=dataset,
        model_run_dir=model,
        output_dir=out,
        allow_missing=True,
        copy_artifacts=True,
    )

    assert result.status in {"complete", "completed_with_missing_optional_artifacts"}
    assert (out / "evidence_package_manifest.json").exists()
    assert (out / "evidence_package_summary.md").exists()
    assert (out / "evidence_artifact_index.csv").exists()
    assert (out / "artifacts").exists()
    assert result.manifest["counts"]["present"] > 0
    assert result.manifest["counts"]["missing_required"] == 0

    with (out / "evidence_artifact_index.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    labels = {row["label"] for row in rows}
    assert "dataset_promotion_manifest" in labels
    assert "model_promotion_manifest" in labels
    assert "learning_curves_report" in labels


def test_evidence_package_fails_without_required_dataset_promotion(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    model = _make_model_run(tmp_path)

    try:
        build_evidence_package(dataset=dataset, model_run_dir=model, output_dir=tmp_path / "out")
    except ValueError as exc:
        assert "missing required artifacts" in str(exc)
    else:
        raise AssertionError("build_evidence_package should fail when required evidence is missing")


def test_package_evidence_cli_smoke(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    model = _make_model_run(tmp_path)
    out = tmp_path / "cli_evidence"

    result = CliRunner().invoke(
        app,
        [
            "--no-check-writable",
            "ml",
            "package-evidence",
            "--dataset",
            str(dataset),
            "--model-run-dir",
            str(model),
            "--output-dir",
            str(out),
            "--allow-missing",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "ML evidence package completed" in result.output
    assert (out / "evidence_package_manifest.json").exists()
    assert (out / "evidence_artifact_index.csv").exists()


def test_package_evidence_cli_has_workflow_flag() -> None:
    result = CliRunner().invoke(app, ["ml", "package-evidence", "--help"])
    assert result.exit_code == 0
    assert "--workflow" in result.output
