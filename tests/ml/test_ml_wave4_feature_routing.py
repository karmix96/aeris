"""Wave-4 regression tests. AERIS_ML_W4_TESTS_V1

Covers the four Wave-4 fixes:
  ML-BUG-02/03 — config-mode training accepts features | feature_preset | feature_set
  ML-BUG-04 / ML-REF-03 — predict-with-confidence materializes a feature set and
                          reports feature_set_name / feature_set_applied
  ML-REF-10 — `aeris ml doctor` reports optional backend availability

Pure unit/CLI tests: no solvers, no promoted datasets, no Streamlit runtime.
Run: pytest tests/ml/test_ml_wave4_feature_routing.py -q
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from aeris.cli import app
from aeris.ml.config import MLExperimentConfig, load_ml_experiment_config
from aeris.ml.quality.confidence import predict_with_confidence

runner = CliRunner()


# ---------------------------------------------------------------------------
# ML-BUG-02 / ML-BUG-03 — config-mode feature routing
# ---------------------------------------------------------------------------

def test_ml_experiment_config_has_feature_routing_fields():
    fields = MLExperimentConfig.__dataclass_fields__
    assert "feature_preset" in fields
    assert "feature_set" in fields


def _write_cfg(tmp_path: Path, ml_block: dict) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump({"ml": ml_block}), encoding="utf-8")
    return p


def test_config_accepts_feature_set(tmp_path: Path):
    cfg = load_ml_experiment_config(_write_cfg(tmp_path, {
        "dataset": str(tmp_path / "ds"),
        "feature_set": "bwb_control_physics_v1",
        "targets": ["cl", "cd"],
        "model": {"type": "extra_trees"},
    }))
    assert cfg.feature_set == "bwb_control_physics_v1"
    assert cfg.feature_preset is None
    assert cfg.feature_columns == []  # explicit features not required


def test_config_accepts_feature_preset(tmp_path: Path):
    cfg = load_ml_experiment_config(_write_cfg(tmp_path, {
        "dataset": str(tmp_path / "ds"),
        "feature_preset": "bwb_control",
        "targets": ["cl"],
    }))
    assert cfg.feature_preset == "bwb_control"
    assert cfg.feature_set is None


def test_config_legacy_explicit_features_still_works(tmp_path: Path):
    cfg = load_ml_experiment_config(_write_cfg(tmp_path, {
        "dataset": str(tmp_path / "ds"),
        "features": ["c1_m", "alpha_deg"],
        "targets": ["cl"],
    }))
    assert cfg.feature_columns == ["c1_m", "alpha_deg"]
    assert cfg.feature_set is None and cfg.feature_preset is None


def test_config_rejects_multiple_feature_sources(tmp_path: Path):
    with pytest.raises(ValueError, match="exactly one"):
        load_ml_experiment_config(_write_cfg(tmp_path, {
            "dataset": str(tmp_path / "ds"),
            "features": ["a", "b"],
            "feature_set": "bwb_control_physics_v1",
            "targets": ["cl"],
        }))


def test_config_rejects_zero_feature_sources(tmp_path: Path):
    with pytest.raises(ValueError, match="exactly one"):
        load_ml_experiment_config(_write_cfg(tmp_path, {
            "dataset": str(tmp_path / "ds"),
            "targets": ["cl"],
        }))


# ---------------------------------------------------------------------------
# ML-BUG-04 / ML-REF-03 — predict-with-confidence feature-set materialization
# ---------------------------------------------------------------------------

class _AffineModel:
    """Pickle-able single-target affine model: cl = x0."""
    def predict(self, X):
        X = np.asarray(X, dtype=float)
        return X[:, 0].reshape(-1, 1)


def _make_run(tmp_path: Path, feature_set_name: str | None) -> Path:
    run = tmp_path / "run"
    (run / "models").mkdir(parents=True, exist_ok=True)
    with (run / "models" / "model.pkl").open("wb") as f:
        pickle.dump(_AffineModel(), f)
    tc = {"feature_columns": ["c1_m"], "target_columns": ["cl"]}
    if feature_set_name is not None:
        tc["feature_set_name"] = feature_set_name
    (run / "train_config.json").write_text(json.dumps(tc), encoding="utf-8")
    (run / "training_envelope.json").write_text(
        json.dumps({"feature_ranges": {"c1_m": {"min": 0.0, "max": 5.0}}}), encoding="utf-8"
    )
    return run


def test_predict_with_confidence_reports_feature_set_keys(tmp_path: Path):
    # A model whose feature columns are already raw (c1_m) so a raw feature set
    # applies cleanly. This asserts the report EXPOSES the keys the CLI echoes.
    run = _make_run(tmp_path, feature_set_name=None)
    inp = tmp_path / "in.csv"
    pd.DataFrame({"c1_m": [1.0, 2.0], "cl": [0.1, 0.2]}).to_csv(inp, index=False)

    result = predict_with_confidence(
        model_run_dir=run,
        input_csv=inp,
        output_dir=tmp_path / "out",
        require_promoted_model_gate=False,
    )
    # Keys must be PRESENT even when no feature set is used (previously absent).
    assert "feature_set_name" in result.report
    assert "feature_set_applied" in result.report
    assert result.report["feature_set_applied"] is False


def test_predict_with_confidence_signature_accepts_feature_set(tmp_path: Path):
    import inspect
    sig = inspect.signature(predict_with_confidence)
    assert "feature_set_name" in sig.parameters
    assert "allow_feature_set_mismatch" in sig.parameters


# ---------------------------------------------------------------------------
# ML-REF-10 — `aeris ml doctor`
# ---------------------------------------------------------------------------

def test_ml_doctor_runs():
    out = runner.invoke(app, ["ml", "doctor"])
    assert out.exit_code == 0, out.stdout
    assert "ML backend doctor" in out.stdout


def test_ml_doctor_json_schema():
    out = runner.invoke(app, ["ml", "doctor", "--json"])
    assert out.exit_code == 0, out.stdout
    payload = json.loads(out.stdout)
    assert payload["schema_version"] == "aeris.ml_doctor.v1"
    # every optional backend must carry an install hint iff missing
    for b in payload["backends"]:
        if b["tier"] == "optional" and not b["available"]:
            assert b["install_hint"], b
        if b["available"]:
            assert b["install_hint"] is None


def test_ml_predict_with_confidence_help_has_feature_set_flag():
    # Introspect registered params (help text wraps unpredictably).
    from typer.main import get_command
    cmd = get_command(app)
    ml_group = cmd.commands["ml"]
    pwc = ml_group.commands["predict-with-confidence"]
    opts = [o for p in pwc.params for o in p.opts]
    assert "--feature-set" in opts
    assert "--allow-feature-set-mismatch" in opts
