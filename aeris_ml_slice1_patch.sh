#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

if [ ! -d "src/aeris/ml" ]; then
  echo "[AERIS PATCH] ERROR: run this from the AERIS repo root, or pass repo root as first arg." >&2
  exit 1
fi

mkdir -p src/aeris/ml configs/ml tests/ml

cat > src/aeris/ml/fingerprints.py <<'PY'
"""
Reproducibility fingerprints for AERIS ML runs.

This module is deliberately small and dependency-light. It provides stable file
hashes and dataset artifact fingerprints so every trained model can be traced
back to the exact curated/promotion inputs that produced it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def file_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return SHA256 for a file using bounded memory."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot fingerprint missing file: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"Can only fingerprint files, got: {file_path}")

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(payload: Any) -> str:
    """Return SHA256 for JSON-serializable content with stable key ordering."""
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def optional_file_fingerprint(path: str | Path | None) -> dict[str, Any]:
    """Fingerprint a file if present; otherwise return an explicit missing record."""
    if path is None:
        return {"path": None, "exists": False, "sha256": None, "size_bytes": None}

    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return {
            "path": str(file_path),
            "exists": False,
            "sha256": None,
            "size_bytes": None,
        }

    return {
        "path": str(file_path),
        "exists": True,
        "sha256": file_sha256(file_path),
        "size_bytes": int(file_path.stat().st_size),
    }


def build_dataset_fingerprints(
    *,
    dataset_path: str | Path,
    curated_csv_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Build the core dataset fingerprints used by ML manifests.

    The curated CSV and promotion manifest are the load-bearing inputs for ML.
    Additional files are included when present, but they are not required for
    baseline tabular training.
    """
    dataset_root = Path(dataset_path).expanduser().resolve()
    curated_path = (
        Path(curated_csv_path).expanduser().resolve()
        if curated_csv_path is not None
        else dataset_root / "curated_aero_dataset.csv"
    )

    files = {
        "curated_aero_dataset_csv": curated_path,
        "promotion_manifest_json": dataset_root / "promotion_manifest.json",
        "curation_report_json": dataset_root / "curation_report.json",
        "aero_dataset_manifest_json": dataset_root / "aero_dataset_manifest.json",
        "final_run_summary_json": dataset_root / "final_run_summary.json",
    }

    return {
        "dataset_root": str(dataset_root),
        "files": {
            name: optional_file_fingerprint(path)
            for name, path in files.items()
        },
    }
PY

cat > src/aeris/ml/metrics.py <<'PY'
"""
Regression metrics for AERIS ML.

The old RMSE/MAE/R2 trio is kept for compatibility, but this module adds the
error percentiles and normalized metrics needed for serious aero surrogate work.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def _as_2d(array: np.ndarray) -> np.ndarray:
    arr = np.asarray(array, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


def _safe_float(value: float | np.floating | int | None) -> float | None:
    if value is None:
        return None
    value_f = float(value)
    if not np.isfinite(value_f):
        return None
    return value_f


def evaluate_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_columns: list[str],
) -> dict[str, Any]:
    """
    Compute per-target and overall regression metrics.

    Compatibility keys retained:
    - per_target[target].rmse / mae / r2
    - overall.rmse_mean / mae_mean / r2_mean
    """
    y_true = _as_2d(y_true)
    y_pred = _as_2d(y_pred)

    if y_true.shape != y_pred.shape:
        raise ValueError(f"y_true/y_pred shape mismatch: {y_true.shape} vs {y_pred.shape}")
    if y_true.shape[1] != len(target_columns):
        raise ValueError(
            f"target column count mismatch: y has {y_true.shape[1]} columns, "
            f"target_columns has {len(target_columns)}"
        )

    per_target: dict[str, dict[str, float | None]] = {}
    rmse_values: list[float] = []
    mae_values: list[float] = []
    r2_values: list[float] = []
    max_abs_values: list[float] = []

    for idx, target in enumerate(target_columns):
        yt = y_true[:, idx]
        yp = y_pred[:, idx]
        err = yp - yt
        abs_err = np.abs(err)

        rmse = float(np.sqrt(mean_squared_error(yt, yp)))
        mae = float(mean_absolute_error(yt, yp))
        r2 = float(r2_score(yt, yp))
        max_abs = float(np.max(abs_err)) if len(abs_err) else 0.0
        target_std = float(np.std(yt)) if len(yt) else 0.0
        target_range = float(np.max(yt) - np.min(yt)) if len(yt) else 0.0

        nrmse_std = rmse / target_std if target_std > 0 else None
        nrmse_range = rmse / target_range if target_range > 0 else None

        per_target[target] = {
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
            "max_abs_error": max_abs,
            "error_p50": float(np.percentile(abs_err, 50)),
            "error_p90": float(np.percentile(abs_err, 90)),
            "error_p95": float(np.percentile(abs_err, 95)),
            "error_p99": float(np.percentile(abs_err, 99)),
            "bias_mean": float(np.mean(err)),
            "error_std": float(np.std(err)),
            "target_mean": float(np.mean(yt)),
            "target_std": target_std,
            "target_min": float(np.min(yt)),
            "target_max": float(np.max(yt)),
            "target_range": target_range,
            "nrmse_by_std": _safe_float(nrmse_std),
            "nrmse_by_range": _safe_float(nrmse_range),
        }

        rmse_values.append(rmse)
        mae_values.append(mae)
        r2_values.append(r2)
        max_abs_values.append(max_abs)

    return {
        "per_target": per_target,
        "overall": {
            "rmse_mean": float(np.mean(rmse_values)),
            "mae_mean": float(np.mean(mae_values)),
            "r2_mean": float(np.mean(r2_values)),
            "max_abs_error_mean": float(np.mean(max_abs_values)),
            "n_rows": int(y_true.shape[0]),
            "n_targets": int(y_true.shape[1]),
        },
    }
PY

cat > src/aeris/ml/diagnostics.py <<'PY'
"""
Diagnostic artifact writers for AERIS ML runs.

These outputs make model failures inspectable by condition, geometry/airfoil id,
and target variable. They are intentionally CSV-first so they can be inspected
with normal tooling before we add plotting/report layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _as_2d(array: np.ndarray) -> np.ndarray:
    arr = np.asarray(array, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


def build_prediction_vs_truth_frame(
    *,
    base_df: pd.DataFrame,
    target_columns: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> pd.DataFrame:
    """Return a dataframe with true, predicted, residual, and absolute residual columns."""
    y_true = _as_2d(y_true)
    y_pred = _as_2d(y_pred)

    if y_true.shape != y_pred.shape:
        raise ValueError(f"y_true/y_pred shape mismatch: {y_true.shape} vs {y_pred.shape}")
    if y_true.shape[1] != len(target_columns):
        raise ValueError("target_columns does not match y array width")

    out = base_df.reset_index(drop=True).copy()
    for idx, target in enumerate(target_columns):
        out[f"true__{target}"] = y_true[:, idx]
        out[f"pred__{target}"] = y_pred[:, idx]
        out[f"error__{target}"] = y_pred[:, idx] - y_true[:, idx]
        out[f"abs_error__{target}"] = np.abs(y_pred[:, idx] - y_true[:, idx])
    return out


def build_residual_summary(
    *,
    frame: pd.DataFrame,
    target_columns: list[str],
) -> dict[str, Any]:
    """Build compact residual summary from a prediction-vs-truth dataframe."""
    summary: dict[str, Any] = {"targets": {}, "n_rows": int(len(frame))}
    for target in target_columns:
        err = frame[f"error__{target}"].to_numpy(dtype=float)
        abs_err = np.abs(err)
        summary["targets"][target] = {
            "bias_mean": float(np.mean(err)),
            "error_std": float(np.std(err)),
            "abs_error_mean": float(np.mean(abs_err)),
            "abs_error_max": float(np.max(abs_err)),
            "abs_error_p50": float(np.percentile(abs_err, 50)),
            "abs_error_p90": float(np.percentile(abs_err, 90)),
            "abs_error_p95": float(np.percentile(abs_err, 95)),
            "abs_error_p99": float(np.percentile(abs_err, 99)),
        }
    return summary


def write_regression_diagnostics(
    *,
    partition_name: str,
    df: pd.DataFrame,
    target_columns: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
    output_dir: Path,
) -> dict[str, Any]:
    """Write prediction-vs-truth and residual CSVs for one data partition."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = build_prediction_vs_truth_frame(
        base_df=df,
        target_columns=target_columns,
        y_true=y_true,
        y_pred=y_pred,
    )

    prediction_path = output_dir / f"{partition_name}_prediction_vs_truth.csv"
    residuals_path = output_dir / f"{partition_name}_residuals.csv"

    frame.to_csv(prediction_path, index=False)

    residual_cols: list[str] = []
    id_like_cols = [
        col for col in [
            "geometry_id",
            "airfoil_id",
            "case_id",
            "alpha_deg",
            "beta_deg",
            "reynolds",
            "mach",
            "velocity_mps",
            "altitude_m",
            "control_input_deg",
            "solver_id",
            "fidelity_level",
        ] if col in frame.columns
    ]
    residual_cols.extend(id_like_cols)
    for target in target_columns:
        residual_cols.extend([f"true__{target}", f"pred__{target}", f"error__{target}", f"abs_error__{target}"])

    frame[residual_cols].to_csv(residuals_path, index=False)

    return {
        "partition": partition_name,
        "prediction_vs_truth_csv": str(prediction_path),
        "residuals_csv": str(residuals_path),
        "summary": build_residual_summary(frame=frame, target_columns=target_columns),
    }
PY

cat > src/aeris/ml/manifest.py <<'PY'
"""Manifest utilities for AERIS ML runs."""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_environment_snapshot() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
    }


def write_ml_run_manifest(path: str | Path, payload: dict[str, Any]) -> Path:
    out_path = Path(path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out_path
PY

cat > src/aeris/ml/config.py <<'PY'
"""
Config helpers for future config-driven ML experiments.

This first version validates the common schema but does not force all CLI paths
to use YAML yet. It is intentionally conservative so we can adopt it command by
command without breaking the current interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aeris.common.config import load_yaml_config


def _list_from_value(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
        return out
    raise TypeError(f"ML config field '{field_name}' must be a list or comma-separated string.")


@dataclass(frozen=True)
class MLExperimentConfig:
    dataset_path: Path
    feature_columns: list[str]
    target_columns: list[str]
    model_type: str = "linear_regression"
    split_method: str = "grouped"
    group_column: str = "geometry_id"
    train_fraction: float = 0.7
    val_fraction: float = 0.15
    test_fraction: float = 0.15
    random_seed: int = 123
    allow_forced: bool = False
    model_params: dict[str, Any] = field(default_factory=dict)
    output_dir: Path | None = None


def load_ml_experiment_config(config_path: str | Path) -> MLExperimentConfig:
    raw = load_yaml_config(config_path)
    ml = raw.get("ml", raw)
    if not isinstance(ml, dict):
        raise ValueError("ML config must contain a mapping at top-level or under 'ml'.")

    dataset = ml.get("dataset") or ml.get("dataset_path")
    if not dataset:
        raise ValueError("ML config requires 'dataset' or 'dataset_path'.")

    features = _list_from_value(ml.get("features") or ml.get("feature_columns"), field_name="features")
    targets = _list_from_value(ml.get("targets") or ml.get("target_columns"), field_name="targets")
    if not features:
        raise ValueError("ML config requires non-empty features.")
    if not targets:
        raise ValueError("ML config requires non-empty targets.")

    split = ml.get("split", {}) or {}
    model = ml.get("model", {}) or {}
    if not isinstance(split, dict):
        raise TypeError("ML config field 'split' must be a mapping.")
    if not isinstance(model, dict):
        raise TypeError("ML config field 'model' must be a mapping.")

    output_dir_raw = ml.get("output_dir")

    return MLExperimentConfig(
        dataset_path=Path(dataset),
        feature_columns=features,
        target_columns=targets,
        model_type=str(model.get("type") or ml.get("model_type") or "linear_regression"),
        split_method=str(split.get("method") or ml.get("split_method") or "grouped"),
        group_column=str(split.get("group_column") or ml.get("group_column") or "geometry_id"),
        train_fraction=float(split.get("train_fraction", ml.get("train_fraction", 0.7))),
        val_fraction=float(split.get("val_fraction", ml.get("val_fraction", 0.15))),
        test_fraction=float(split.get("test_fraction", ml.get("test_fraction", 0.15))),
        random_seed=int(split.get("random_seed", ml.get("random_seed", 123))),
        allow_forced=bool(ml.get("allow_forced", False)),
        model_params=dict(model.get("params", ml.get("model_params", {})) or {}),
        output_dir=None if output_dir_raw is None else Path(output_dir_raw),
    )
PY

cat > configs/ml/tabular_baseline.yaml <<'YAML'
# AERIS ML baseline training template.
# Replace dataset with a promoted dataset root before use.
ml:
  dataset: data/datasets/<promoted_aero_dataset>
  features:
    - c1_m
    - b_total_m
    - sw1_deg
    - alpha_deg
    - velocity_mps
    - altitude_m
    - control_input_deg
  targets:
    - cl
    - cd
    - cm
  split:
    method: grouped
    group_column: geometry_id
    train_fraction: 0.70
    val_fraction: 0.15
    test_fraction: 0.15
    random_seed: 123
  model:
    type: gradient_boosting
    params: {}
  output_dir: data/processed/ml_runs/tabular_baseline
YAML

cat > configs/ml/airfoil_xfoil_baseline.yaml <<'YAML'
# AERIS 2D airfoil scalar-surrogate template for XFOIL/CFD campaigns.
# This assumes the dataset is already curated/promoted and contains these columns.
ml:
  dataset: data/datasets/<promoted_airfoil_dataset>
  features:
    - cst_u0
    - cst_u1
    - cst_u2
    - cst_u3
    - cst_u4
    - cst_l0
    - cst_l1
    - cst_l2
    - cst_l3
    - cst_l4
    - alpha_deg
    - reynolds
    - mach
  targets:
    - cl
    - cd
    - cm
  split:
    method: grouped
    group_column: airfoil_id
    train_fraction: 0.70
    val_fraction: 0.15
    test_fraction: 0.15
    random_seed: 123
  model:
    type: gradient_boosting
    params: {}
  output_dir: data/processed/ml_runs/airfoil_xfoil_baseline
YAML

cat > tests/ml/test_metrics_and_fingerprints.py <<'PY'
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from aeris.ml.fingerprints import file_sha256, json_sha256
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.diagnostics import write_regression_diagnostics


def test_file_and_json_hashes_are_stable(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("abc", encoding="utf-8")

    assert file_sha256(p) == file_sha256(p)
    assert json_sha256({"b": 2, "a": 1}) == json_sha256({"a": 1, "b": 2})


def test_enhanced_regression_metrics_keep_compatibility_keys() -> None:
    y_true = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])
    y_pred = np.array([[1.1, 1.9], [2.1, 4.2], [2.8, 5.7]])

    m = evaluate_regression_metrics(y_true, y_pred, ["cl", "cd"])

    assert "rmse" in m["per_target"]["cl"]
    assert "mae" in m["per_target"]["cl"]
    assert "r2" in m["per_target"]["cl"]
    assert "error_p95" in m["per_target"]["cl"]
    assert "nrmse_by_range" in m["per_target"]["cl"]
    assert "rmse_mean" in m["overall"]
    assert m["overall"]["n_rows"] == 3


def test_write_regression_diagnostics(tmp_path: Path) -> None:
    df = pd.DataFrame({"geometry_id": ["g1", "g2"], "alpha_deg": [0.0, 2.0], "cl": [0.1, 0.2]})
    y_true = np.array([[0.1], [0.2]])
    y_pred = np.array([[0.11], [0.19]])

    out = write_regression_diagnostics(
        partition_name="test",
        df=df,
        target_columns=["cl"],
        y_true=y_true,
        y_pred=y_pred,
        output_dir=tmp_path,
    )

    assert Path(out["prediction_vs_truth_csv"]).exists()
    assert Path(out["residuals_csv"]).exists()
    assert out["summary"]["n_rows"] == 2
PY

python - <<'PY'
from pathlib import Path

# Patch training_data.py to use the curated CSV path resolved by promotion context.
path = Path("src/aeris/dataset/training_data.py")
text = path.read_text(encoding="utf-8")
old = '''    curated_path = dataset_path / "curated_aero_dataset.csv"
    if not curated_path.exists():
        raise FileNotFoundError(
            f"Missing curated dataset CSV: {curated_path}"
        )

    df = pd.read_csv(curated_path)
'''
new = '''    curated_from_gate = promoted_info.get("curated_aero_dataset_csv")
    curated_path = (
        Path(curated_from_gate).expanduser().resolve()
        if curated_from_gate
        else dataset_path / "curated_aero_dataset.csv"
    )
    if not curated_path.exists():
        raise FileNotFoundError(
            f"Missing curated dataset CSV resolved by promotion gate: {curated_path}"
        )

    df = pd.read_csv(curated_path)
'''
if old not in text:
    raise SystemExit("[AERIS PATCH] training_data.py expected block not found; aborting")
path.write_text(text.replace(old, new), encoding="utf-8")

# Patch train.py imports, metrics, artifacts, diagnostics and manifest output.
path = Path("src/aeris/ml/train.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
'''import json
import pickle
from dataclasses import asdict, dataclass
''',
'''import json
import pickle
from dataclasses import asdict, dataclass
'''
)
text = text.replace(
'''from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from aeris.dataset.splitting import DatasetSplit, split_dataset
''',
'''from aeris.dataset.splitting import DatasetSplit, split_dataset
'''
)
text = text.replace(
'''from aeris.dataset.training_data import TrainingData, load_training_data
from aeris.ml.model_registry import build_model, get_model_spec
''',
'''from aeris.dataset.training_data import TrainingData, load_training_data
from aeris.ml.diagnostics import write_regression_diagnostics
from aeris.ml.fingerprints import build_dataset_fingerprints, file_sha256
from aeris.ml.manifest import build_environment_snapshot, utc_now_iso, write_ml_run_manifest
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.model_registry import build_model, get_model_spec
'''
)

old_eval = '''def _evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_columns: list[str],
) -> dict[str, Any]:
    if y_true.ndim == 1:
        y_true = y_true.reshape(-1, 1)
    if y_pred.ndim == 1:
        y_pred = y_pred.reshape(-1, 1)

    per_target: dict[str, dict[str, float]] = {}
    rmse_values: list[float] = []
    mae_values: list[float] = []
    r2_values: list[float] = []

    for idx, target in enumerate(target_columns):
        y_true_col = y_true[:, idx]
        y_pred_col = y_pred[:, idx]

        rmse = float(np.sqrt(mean_squared_error(y_true_col, y_pred_col)))
        mae = float(mean_absolute_error(y_true_col, y_pred_col))
        r2 = float(r2_score(y_true_col, y_pred_col))

        per_target[target] = {
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
        }

        rmse_values.append(rmse)
        mae_values.append(mae)
        r2_values.append(r2)

    return {
        "per_target": per_target,
        "overall": {
            "rmse_mean": float(np.mean(rmse_values)),
            "mae_mean": float(np.mean(mae_values)),
            "r2_mean": float(np.mean(r2_values)),
        },
    }
'''
new_eval = '''def _evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_columns: list[str],
) -> dict[str, Any]:
    return evaluate_regression_metrics(y_true, y_pred, target_columns)
'''
if old_eval not in text:
    raise SystemExit("[AERIS PATCH] train.py _evaluate_predictions block not found; aborting")
text = text.replace(old_eval, new_eval)

old_artifacts = '''    coefficients_path: Path | None = None
    feature_importances_path: Path | None = None
'''
new_artifacts = '''    coefficients_path: Path | None = None
    feature_importances_path: Path | None = None
    diagnostics_dir: Path | None = None
    train_prediction_vs_truth_path: Path | None = None
    val_prediction_vs_truth_path: Path | None = None
    test_prediction_vs_truth_path: Path | None = None
    train_residuals_path: Path | None = None
    val_residuals_path: Path | None = None
    test_residuals_path: Path | None = None
    ml_run_manifest_path: Path | None = None
'''
if old_artifacts not in text:
    raise SystemExit("[AERIS PATCH] train.py TrainArtifacts block not found; aborting")
text = text.replace(old_artifacts, new_artifacts)

old_metrics_write = '''    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    train_config = TrainConfig(
'''
new_metrics_write = '''    diagnostics_dir = output_dir / "diagnostics"
    train_diag = write_regression_diagnostics(
        partition_name="train",
        df=split.train_df,
        target_columns=target_columns,
        y_true=y_train,
        y_pred=y_pred_train,
        output_dir=diagnostics_dir,
    )
    val_diag = write_regression_diagnostics(
        partition_name="val",
        df=split.val_df,
        target_columns=target_columns,
        y_true=y_val,
        y_pred=y_pred_val,
        output_dir=diagnostics_dir,
    )
    test_diag = write_regression_diagnostics(
        partition_name="test",
        df=split.test_df,
        target_columns=target_columns,
        y_true=y_test,
        y_pred=y_pred_test,
        output_dir=diagnostics_dir,
    )
    metrics["diagnostics"] = {
        "train": train_diag,
        "val": val_diag,
        "test": test_diag,
    }

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    train_config = TrainConfig(
'''
if old_metrics_write not in text:
    raise SystemExit("[AERIS PATCH] train.py metrics write block not found; aborting")
text = text.replace(old_metrics_write, new_metrics_write)

old_after_explain = '''    coefficients_path, feature_importances_path = _write_explainability_artifacts(
        model=model,
        model_type=model_type,
        feature_columns=feature_columns,
        target_columns=target_columns,
        output_dir=output_dir,
    )

    artifacts = TrainArtifacts(
'''
new_after_explain = '''    coefficients_path, feature_importances_path = _write_explainability_artifacts(
        model=model,
        model_type=model_type,
        feature_columns=feature_columns,
        target_columns=target_columns,
        output_dir=output_dir,
    )

    curated_csv_path = training_data.metadata.get("curated_csv_path")
    dataset_fingerprints = build_dataset_fingerprints(
        dataset_path=dataset_path,
        curated_csv_path=curated_csv_path,
    )
    split_fingerprints = {
        "train_rows_csv": {"path": str(train_rows_path), "sha256": file_sha256(train_rows_path)},
        "val_rows_csv": {"path": str(val_rows_path), "sha256": file_sha256(val_rows_path)},
        "test_rows_csv": {"path": str(test_rows_path), "sha256": file_sha256(test_rows_path)},
    }

    ml_run_manifest = {
        "schema_version": "aeris.ml_run_manifest.v1",
        "status": "success",
        "created_at_utc": utc_now_iso(),
        "run_dir": str(output_dir),
        "environment": build_environment_snapshot(),
        "dataset": {
            "dataset_path": str(dataset_path),
            "curated_csv_path": str(curated_csv_path),
            "fingerprints": dataset_fingerprints,
            "promotion_context": training_data.metadata.get("promotion_context"),
        },
        "training_data": {
            "n_samples": training_data.metadata.get("n_samples"),
            "n_features": training_data.metadata.get("n_features"),
            "n_targets": training_data.metadata.get("n_targets"),
            "feature_columns": list(feature_columns),
            "target_columns": list(target_columns),
            "dropped_non_finite_rows": training_data.metadata.get("dropped_non_finite_rows"),
        },
        "split": {
            "method": split.method,
            "metadata": getattr(split, "metadata", {}),
            "train_rows": int(len(split.train_df)),
            "val_rows": int(len(split.val_df)),
            "test_rows": int(len(split.test_df)),
            "fingerprints": split_fingerprints,
        },
        "model": metrics["model"],
        "metrics": metrics,
        "artifacts": {
            "model_path": str(model_path),
            "metrics_path": str(metrics_path),
            "train_config_path": str(train_config_path),
            "diagnostics_dir": str(diagnostics_dir),
            "coefficients_path": None if coefficients_path is None else str(coefficients_path),
            "feature_importances_path": None if feature_importances_path is None else str(feature_importances_path),
        },
    }
    ml_run_manifest_path = write_ml_run_manifest(
        output_dir / "ml_run_manifest.json",
        ml_run_manifest,
    )

    artifacts = TrainArtifacts(
'''
if old_after_explain not in text:
    raise SystemExit("[AERIS PATCH] train.py explainability block not found; aborting")
text = text.replace(old_after_explain, new_after_explain)

old_artifacts_ctor = '''        coefficients_path=coefficients_path,
        feature_importances_path=feature_importances_path,
    )
'''
new_artifacts_ctor = '''        coefficients_path=coefficients_path,
        feature_importances_path=feature_importances_path,
        diagnostics_dir=diagnostics_dir,
        train_prediction_vs_truth_path=Path(train_diag["prediction_vs_truth_csv"]),
        val_prediction_vs_truth_path=Path(val_diag["prediction_vs_truth_csv"]),
        test_prediction_vs_truth_path=Path(test_diag["prediction_vs_truth_csv"]),
        train_residuals_path=Path(train_diag["residuals_csv"]),
        val_residuals_path=Path(val_diag["residuals_csv"]),
        test_residuals_path=Path(test_diag["residuals_csv"]),
        ml_run_manifest_path=ml_run_manifest_path,
    )
'''
# Replace only the last matching artifact constructor block. There is only one with both lines.
if old_artifacts_ctor not in text:
    raise SystemExit("[AERIS PATCH] train.py artifacts constructor tail not found; aborting")
text = text.replace(old_artifacts_ctor, new_artifacts_ctor, 1)

path.write_text(text, encoding="utf-8")
PY

# Optional: extend CLI readout if the artifact is present.
python - <<'PY'
from pathlib import Path
path = Path("src/aeris/commands/ml.py")
text = path.read_text(encoding="utf-8")
old = '''    typer.echo(f"  test_rows_csv: {artifacts.test_rows_path}")

    if artifacts.coefficients_path is not None:
'''
new = '''    typer.echo(f"  test_rows_csv: {artifacts.test_rows_path}")
    if getattr(artifacts, "ml_run_manifest_path", None) is not None:
        typer.echo(f"  ml_run_manifest_json: {artifacts.ml_run_manifest_path}")
    if getattr(artifacts, "diagnostics_dir", None) is not None:
        typer.echo(f"  diagnostics_dir: {artifacts.diagnostics_dir}")

    if artifacts.coefficients_path is not None:
'''
if old not in text:
    raise SystemExit("[AERIS PATCH] ml.py CLI readout block not found; aborting")
path.write_text(text.replace(old, new), encoding="utf-8")
PY

echo "[AERIS PATCH] ML Slice 1 applied."
echo "[AERIS PATCH] Recommended tests:"
echo "  pytest tests/ml/test_metrics_and_fingerprints.py tests/ml/test_train.py tests/commands/test_ml_cli.py"
