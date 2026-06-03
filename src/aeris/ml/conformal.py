"""
PATCH 04 — src/aeris/ml/conformal.py  (NEW FILE)
==================================================
Split conformal prediction for AERIS ML promoted models.

WHY THIS EXISTS
---------------
Ensemble spread (the current uncertainty method) is a heuristic.
Split conformal prediction gives an exact marginal coverage guarantee:

    P(y_true ∈ [ŷ − q̂, ŷ + q̂]) ≥ 1 − α

with α user-specified (default 0.10 → 90% coverage). This guarantee
holds for any model and any data distribution — no assumptions required.

HOW IT WORKS
------------
1. Calibrate: on the held-out validation set, compute nonconformity
   scores s_i = |y_true_i − ŷ_i| per sample per target.
2. q̂ = (1 + 1/n) * (1−α)-th quantile of {s_i}.
   The (1+1/n) inflation ensures finite-sample coverage.
3. At inference: prediction interval is [ŷ − q̂, ŷ + q̂] per target.

USAGE
-----
# During a run that has val_rows.csv:
from aeris.ml.conformal import fit_conformal, save_conformal_calibration

cal = fit_conformal(model, X_val, y_val, target_columns, alpha=0.10)
save_conformal_calibration(cal, output_dir / "conformal_calibration.json")

# At inference:
from aeris.ml.conformal import load_conformal_calibration, predict_with_conformal_intervals

cal = load_conformal_calibration(model_run_dir / "conformal_calibration.json")
predictions, lower, upper = predict_with_conformal_intervals(model, X_new, cal, target_columns)

INTEGRATION POINT
-----------------
quality/confidence.py predict_with_confidence() should call this when
--uq-method conformal is passed. The CLI option is added in patch_06.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso


CONFORMAL_SCHEMA_VERSION = "aeris.conformal_calibration.v1"


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class ConformalCalibration:
    """Per-target conformal quantiles fitted on a calibration (val) set."""

    alpha: float
    """Miscoverage rate. 0.10 → 90% coverage guarantee."""

    target_columns: list[str]
    """Target names in the same order as q_hat."""

    q_hat: dict[str, float]
    """Per-target conformal quantile. interval = [pred − q, pred + q]."""

    n_calibration: int
    """Number of calibration rows used to compute q_hat."""

    coverage_theoretical: float
    """Theoretical coverage: 1 − alpha (exact for iid data)."""

    nonconformity_scores_p50: dict[str, float]
    """Median nonconformity score per target (diagnostic, not used at inference)."""

    nonconformity_scores_p95: dict[str, float]
    """p95 nonconformity score per target (diagnostic)."""

    created_at_utc: str = ""
    calibration_rows_sha256: str | None = None
    model_sha256: str | None = None


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def _as_2d(arr: Any) -> np.ndarray:
    a = np.asarray(arr, dtype=float)
    return a.reshape(-1, 1) if a.ndim == 1 else a


def _predict_2d(model: Any, X: np.ndarray, n_targets: int) -> np.ndarray:
    pred = np.asarray(model.predict(X), dtype=float)
    if pred.ndim == 1:
        pred = pred.reshape(-1, 1)
    if pred.shape[1] != n_targets:
        raise ValueError(
            f"Model predicted {pred.shape[1]} columns but {n_targets} targets expected."
        )
    return pred


def fit_conformal(
    model: Any,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
    target_columns: list[str],
    *,
    alpha: float = 0.10,
    calibration_csv_path: Path | None = None,
    model_path: Path | None = None,
) -> ConformalCalibration:
    """
    Fit split conformal calibration on a held-out calibration set.

    Parameters
    ----------
    model:
        A fitted sklearn-compatible model (already trained on train set only).
    X_cal:
        Feature matrix for calibration rows (val_rows.csv features).
    y_cal:
        True targets for calibration rows (val_rows.csv targets).
    target_columns:
        Target names, same order as y_cal columns.
    alpha:
        Miscoverage level. 0.10 = 90% coverage guarantee.
        Valid range: (0, 1). Typical: 0.05 (95%), 0.10 (90%), 0.20 (80%).
    calibration_csv_path:
        Optional path for fingerprinting the calibration CSV in the manifest.
    model_path:
        Optional path for fingerprinting the model artifact.

    Returns
    -------
    ConformalCalibration with per-target q_hat values.
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1). Got {alpha}.")
    if len(target_columns) == 0:
        raise ValueError("target_columns must not be empty.")

    X_cal = np.asarray(X_cal, dtype=float)
    y_cal = _as_2d(y_cal)
    n, n_targets = y_cal.shape

    if n_targets != len(target_columns):
        raise ValueError(
            f"y_cal has {n_targets} columns but target_columns has {len(target_columns)} entries."
        )
    if n < 2:
        raise ValueError(f"Need at least 2 calibration rows. Got {n}.")

    y_pred_cal = _predict_2d(model, X_cal, n_targets)

    # Nonconformity scores: absolute residual per sample per target
    scores = np.abs(y_cal - y_pred_cal)  # shape (n, n_targets)

    # Conformal quantile with finite-sample inflation.
    # This is the (1 + 1/n)(1 − α)-th quantile of the empirical distribution.
    q_level = min((1.0 + 1.0 / n) * (1.0 - alpha), 1.0)

    q_hat: dict[str, float] = {}
    p50: dict[str, float] = {}
    p95: dict[str, float] = {}

    for idx, target in enumerate(target_columns):
        s = scores[:, idx]
        finite = s[np.isfinite(s)]
        if len(finite) == 0:
            # Fallback: use +inf so all intervals are maximally wide.
            q_hat[target] = float("inf")
            p50[target] = float("nan")
            p95[target] = float("nan")
        else:
            q_hat[target] = float(np.quantile(finite, q_level))
            p50[target] = float(np.percentile(finite, 50))
            p95[target] = float(np.percentile(finite, 95))

    return ConformalCalibration(
        alpha=float(alpha),
        target_columns=list(target_columns),
        q_hat=q_hat,
        n_calibration=int(n),
        coverage_theoretical=float(1.0 - alpha),
        nonconformity_scores_p50=p50,
        nonconformity_scores_p95=p95,
        created_at_utc=utc_now_iso(),
        calibration_rows_sha256=(
            file_sha256(calibration_csv_path)
            if calibration_csv_path is not None and calibration_csv_path.exists()
            else None
        ),
        model_sha256=(
            file_sha256(model_path)
            if model_path is not None and model_path.exists()
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def predict_with_conformal_intervals(
    model: Any,
    X: np.ndarray,
    calibration: ConformalCalibration,
    target_columns: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Predict with symmetric conformal prediction intervals.

    Returns
    -------
    (predictions, lower, upper)
        Each is shape (n_rows, n_targets).
        lower = predictions − q_hat[target]
        upper = predictions + q_hat[target]

    Coverage guarantee: P(y_true ∈ [lower, upper]) ≥ 1 − alpha (marginal).
    This is an exact guarantee for exchangeable (iid) calibration + test data.
    """
    if target_columns != calibration.target_columns:
        raise ValueError(
            f"target_columns mismatch. Model: {target_columns}, "
            f"Calibration: {calibration.target_columns}"
        )

    n_targets = len(target_columns)
    X = np.asarray(X, dtype=float)
    predictions = _predict_2d(model, X, n_targets)

    q_arr = np.array([calibration.q_hat[t] for t in target_columns], dtype=float)
    lower = predictions - q_arr.reshape(1, -1)
    upper = predictions + q_arr.reshape(1, -1)

    return predictions, lower, upper


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_conformal_calibration(
    calibration: ConformalCalibration,
    path: Path,
) -> Path:
    """Write calibration to a JSON file. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CONFORMAL_SCHEMA_VERSION,
        **asdict(calibration),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_conformal_calibration(path: Path) -> ConformalCalibration:
    """Load a saved conformal calibration from JSON."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Conformal calibration file not found: {path}\n"
            "Run aeris ml calibrate-conformal to generate it."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    schema = raw.get("schema_version", "")
    if not schema.startswith("aeris.conformal_calibration"):
        raise ValueError(
            f"Unexpected schema version '{schema}'. "
            "Expected aeris.conformal_calibration.v1."
        )
    return ConformalCalibration(
        alpha=float(raw["alpha"]),
        target_columns=list(raw["target_columns"]),
        q_hat=dict(raw["q_hat"]),
        n_calibration=int(raw["n_calibration"]),
        coverage_theoretical=float(raw["coverage_theoretical"]),
        nonconformity_scores_p50=dict(raw["nonconformity_scores_p50"]),
        nonconformity_scores_p95=dict(raw["nonconformity_scores_p95"]),
        created_at_utc=str(raw.get("created_at_utc", "")),
        calibration_rows_sha256=raw.get("calibration_rows_sha256"),
        model_sha256=raw.get("model_sha256"),
    )


# ---------------------------------------------------------------------------
# Convenience: fit from a model run directory (uses val_rows.csv)
# ---------------------------------------------------------------------------

def fit_conformal_from_run_dir(
    model_run_dir: Path,
    model: Any,
    feature_columns: list[str],
    target_columns: list[str],
    *,
    alpha: float = 0.10,
) -> ConformalCalibration:
    """
    Fit conformal calibration from an existing model run directory.

    Uses val_rows.csv as the calibration set (correct: val was NOT used
    during fitting). Saves conformal_calibration.json to the run dir.

    Parameters
    ----------
    model_run_dir:
        Path to an existing aeris ml train output directory.
    model:
        The fitted model object (loaded from models/model.pkl).
    feature_columns, target_columns:
        From train_config.json.
    alpha:
        Miscoverage rate.
    """
    import pandas as pd

    model_run_dir = Path(model_run_dir).expanduser().resolve()
    val_csv = model_run_dir / "val_rows.csv"
    model_path = model_run_dir / "models" / "model.pkl"
    if not val_csv.exists():
        val_csv = model_run_dir / "val_rows.csv"
    if not val_csv.exists():
        raise FileNotFoundError(f"val_rows.csv not found in {model_run_dir}")

    df = pd.read_csv(val_csv)
    missing_feat = [c for c in feature_columns if c not in df.columns]
    missing_tgt  = [c for c in target_columns  if c not in df.columns]
    if missing_feat:
        raise ValueError(f"val_rows.csv is missing feature columns: {missing_feat}")
    if missing_tgt:
        raise ValueError(f"val_rows.csv is missing target columns: {missing_tgt}")

    X_cal = df[feature_columns].to_numpy(dtype=float)
    y_cal = df[target_columns].to_numpy(dtype=float)

    cal = fit_conformal(
        model,
        X_cal,
        y_cal,
        target_columns,
        alpha=alpha,
        calibration_csv_path=val_csv,
        model_path=model_path if model_path.exists() else None,
    )

    out_path = model_run_dir / "conformal_calibration.json"
    save_conformal_calibration(cal, out_path)
    return cal
