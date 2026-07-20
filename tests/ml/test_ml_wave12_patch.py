"""Regression tests for the July 2026 ML Wave-1/Wave-2 patch.

Covers: ML-H5 (conformal order statistic), ML-H2 (envelope valid-mask),
ML-H3 (bagging-only spread), ML-H4 (shared importances), ML-C1 (tombstone),
ML-C3 (TabPFN v2 params), ML-C2 (conformal branch end-to-end, gate off).
Pure unit tests: numpy/pandas/sklearn only, no solvers, no promoted datasets.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------- ML-H5
def test_conformal_qhat_is_order_statistic_not_interpolated() -> None:
    from aeris.ml.conformal import fit_conformal

    class _ZeroModel:
        def predict(self, X):
            return np.zeros((X.shape[0], 1), dtype=float)

    y = np.arange(1.0, 11.0).reshape(-1, 1)  # scores = 1..10
    X = np.zeros((10, 2), dtype=float)
    cal = fit_conformal(_ZeroModel(), X, y, ["t"], alpha=0.10)
    # level = min(1.1 * 0.9, 1.0) = 0.99 -> "higher" on 10 pts = 10.0
    # (linear interpolation would give 9.91 and break the guarantee)
    assert cal.q_hat["t"] == pytest.approx(10.0)


def test_conformal_level_uses_finite_count() -> None:
    from aeris.ml.conformal import fit_conformal

    class _ZeroModel:
        def predict(self, X):
            return np.zeros((X.shape[0], 1), dtype=float)

    y = np.array([[1.0], [2.0], [3.0], [4.0], [np.nan]])
    X = np.zeros((5, 1), dtype=float)
    cal = fit_conformal(_ZeroModel(), X, y, ["t"], alpha=0.10)
    # m = 4 finite scores -> level = min(1.25*0.9, 1) = 1.0 -> max score = 4
    assert cal.q_hat["t"] == pytest.approx(4.0)


# ---------------------------------------------------------------- ML-H2
def test_missing_envelope_feature_is_not_a_violation() -> None:
    from aeris.ml.quality.confidence import _envelope_metrics, _range_arrays

    ranges = {"a": {"min": 0.0, "max": 1.0}}  # "b" has no recorded range
    lows, highs, widths, missing, valid = _range_arrays(ranges, ["a", "b"])
    assert missing == ["b"]
    assert valid.tolist() == [True, False]
    X = np.array([[0.5, 123456.0], [2.0, -999.0]])
    viol, esum, emax = _envelope_metrics(X, lows, highs, widths, valid)
    assert viol.tolist() == [0, 1]          # row0 fully inside; row1 only 'a' violates
    assert esum[0] == pytest.approx(0.0)


# ---------------------------------------------------------------- ML-H3
class _FakeTree:
    def __init__(self, value: float):
        self._v = float(value)

    def predict(self, X):
        return np.full(X.shape[0], self._v, dtype=float)


class _FakeForest:
    """Name deliberately matches the bagging whitelist."""

    pass


_FakeForest.__name__ = "RandomForestRegressor"


class _FakeMultiOutput:
    pass


_FakeMultiOutput.__name__ = "MultiOutputRegressor"


def test_spread_valid_for_bagging_ensemble() -> None:
    from aeris.ml.quality.confidence import _estimate_uncertainty

    forest = _FakeForest()
    forest.estimators_ = [_FakeTree(1.0), _FakeTree(2.0), _FakeTree(3.0)]
    X = np.zeros((4, 2), dtype=float)
    unc, report = _estimate_uncertainty(forest, X, ["t"])
    assert report["supported"] is True
    assert report["method"] == "native_estimator_prediction_spread"
    assert np.all(np.isfinite(unc)) and unc[0, 0] > 0.0


def test_spread_unsupported_for_single_target_wrapper() -> None:
    from aeris.ml.quality.confidence import _estimate_uncertainty

    wrapper = _FakeMultiOutput()
    inner = _FakeTree(5.0)  # one per-target sub-model, no estimators_
    wrapper.estimators_ = [inner]
    X = np.zeros((3, 2), dtype=float)
    unc, report = _estimate_uncertainty(wrapper, X, ["t"])
    assert report["supported"] is False
    assert np.all(np.isnan(unc))


def test_spread_unsupported_for_boosting_stage_trees() -> None:
    from aeris.ml.quality.confidence import _estimate_uncertainty

    class _FakeGBR:
        pass

    _FakeGBR.__name__ = "GradientBoostingRegressor"
    gbr = _FakeGBR()
    gbr.estimators_ = [_FakeTree(0.1), _FakeTree(0.2), _FakeTree(0.3)]
    wrapper = _FakeMultiOutput()
    wrapper.estimators_ = [gbr, gbr]
    X = np.zeros((3, 2), dtype=float)
    unc, report = _estimate_uncertainty(wrapper, X, ["t1", "t2"])
    assert report["supported"] is False
    assert np.all(np.isnan(unc))


# ---------------------------------------------------------------- ML-H4
def test_multifidelity_native_importances_stored_shared(tmp_path: Path) -> None:
    from aeris.ml.multifidelity.delta_model import _write_explainability

    class _NativeModel:
        feature_importances_ = np.array([0.7, 0.3])

    _, path = _write_explainability(
        model=_NativeModel(),
        model_type="extra_trees",
        feature_columns=["f1", "f2"],
        target_columns=["delta__cl", "delta__cd"],
        output_dir=tmp_path,
    )
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["targets"] == {}
    assert payload["shared"]["f1"] == pytest.approx(0.7)


# ---------------------------------------------------------------- ML-C1
def test_lightgbm_builds_picklable_model_and_tombstone_raises() -> None:
    from aeris.ml import model_registry as mr

    # tombstone: legacy pickles must fail loudly, not recurse
    ghost = object.__new__(mr._AerisLightGBMWarningCleanModel)
    with pytest.raises(RuntimeError, match="ML-C1"):
        ghost.__setstate__({})

    lightgbm = pytest.importorskip("lightgbm")  # noqa: F841
    model = mr.build_model("lightgbm", 123, {"n_estimators": 5, "num_leaves": 7})
    X = np.random.default_rng(0).normal(size=(30, 3))
    y = np.column_stack([X[:, 0] * 2.0, X[:, 1] - X[:, 2]])
    model.fit(X, y)
    blob = pickle.dumps(model)
    restored = pickle.loads(blob)  # would RecursionError before the patch
    import warnings as _w

    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        pred = restored.predict(X)
    assert np.asarray(pred).shape == (30, 2)
    assert not [
        w for w in caught if "valid feature names" in str(w.message)
    ], "LightGBM feature-name warning resurfaced (ML-C1 filter regressed)"


# ---------------------------------------------------------------- ML-C3
def test_tabpfn_builder_uses_v2_params_and_seed() -> None:
    import inspect

    from aeris.ml import model_registry as mr

    src = inspect.getsource(mr._build_tabpfn)
    assert '"N_ensemble_configurations"' not in src  # kwarg gone (comment may cite it)
    assert '"n_estimators"' in src
    assert '"random_state": random_seed' in src


# ---------------------------------------------------------------- ML-C2
def test_predict_with_confidence_conformal_end_to_end(tmp_path: Path) -> None:
    from aeris.ml.conformal import fit_conformal, save_conformal_calibration
    from aeris.ml.quality.confidence import predict_with_confidence

    class _AffineModel:
        """Importable-by-pickle stand-in defined at module scope below."""

    run_dir = tmp_path / "run"
    (run_dir / "models").mkdir(parents=True)
    feature_columns = ["x1", "x2"]
    target_columns = ["cl"]

    model = _AFFINE_MODEL
    with (run_dir / "models" / "model.pkl").open("wb") as f:
        pickle.dump(model, f)
    (run_dir / "train_config.json").write_text(
        json.dumps(
            {"feature_columns": feature_columns, "target_columns": target_columns}
        ),
        encoding="utf-8",
    )
    (run_dir / "training_envelope.json").write_text(
        json.dumps(
            {
                "feature_ranges": {
                    "x1": {"min": -1.0, "max": 1.0},
                    "x2": {"min": -1.0, "max": 1.0},
                }
            }
        ),
        encoding="utf-8",
    )

    rng = np.random.default_rng(1)
    X_cal = rng.uniform(-1, 1, size=(50, 2))
    y_cal = (X_cal[:, 0] + X_cal[:, 1]).reshape(-1, 1) + rng.normal(
        0, 0.05, size=(50, 1)
    )
    cal = fit_conformal(
        model,
        X_cal,
        y_cal,
        target_columns,
        alpha=0.10,
        model_path=run_dir / "models" / "model.pkl",
    )
    save_conformal_calibration(cal, run_dir / "conformal_calibration.json")

    input_csv = tmp_path / "in.csv"
    pd.DataFrame({"x1": [0.1, 0.5], "x2": [-0.2, 0.9]}).to_csv(input_csv, index=False)

    result = predict_with_confidence(
        model_run_dir=run_dir,
        input_csv=input_csv,
        output_dir=tmp_path / "out",
        require_promoted_model_gate=False,
        uq_method="conformal",
    )
    df = result.output_df
    assert result.report["uq_method"] == "conformal"
    assert result.report["uncertainty"]["method"] == "split_conformal_v1"
    assert "lower__cl" in df.columns and "upper__cl" in df.columns
    half = float(cal.q_hat["cl"])
    assert df["upper__cl"].iloc[0] - df["pred__cl"].iloc[0] == pytest.approx(half)
    assert set(df["confidence_status"]) <= {"calibrated", "outside_envelope"}


class _AffinePickleModel:
    def predict(self, X):
        X = np.asarray(X, dtype=float)
        return (X[:, 0] + X[:, 1]).reshape(-1, 1)


_AFFINE_MODEL = _AffinePickleModel()
