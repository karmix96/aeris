from __future__ import annotations

import importlib.util
import warnings

import numpy as np
import pandas as pd
import pytest

from aeris.ml.model_registry import build_model


@pytest.mark.skipif(importlib.util.find_spec("lightgbm") is None, reason="LightGBM not installed")
def test_lightgbm_predict_does_not_emit_feature_name_warning():
    rng = np.random.default_rng(123)
    X_df = pd.DataFrame(rng.normal(size=(24, 3)), columns=["a", "b", "c"])
    y = np.column_stack([
        X_df["a"].to_numpy() + 0.1 * X_df["b"].to_numpy(),
        X_df["b"].to_numpy() - 0.2 * X_df["c"].to_numpy(),
    ])

    model = build_model("lightgbm", random_seed=123, model_params={"n_estimators": 5, "min_child_samples": 2})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(X_df, y)
        _ = model.predict(X_df.to_numpy(dtype=float))

    messages = [str(w.message) for w in caught]
    assert not any("valid feature names" in msg for msg in messages)
