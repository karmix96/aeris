"""Mondrian (grouped) conformal: per-group coverage, fallback, persistence."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aeris.ml.conformal import (
    fit_conformal,
    fit_conformal_grouped,
    load_grouped_conformal_calibration,
    predict_with_conformal_intervals_grouped,
    save_grouped_conformal_calibration,
)


class _ZeroModel:
    """Predicts 0 — residuals equal y, so quantiles are transparent."""

    def predict(self, X):
        return np.zeros((len(X), 1))


def _mixed_fidelity_data(rng, n_coarse=200, n_fine=200):
    """Two groups with different noise scales: coarse sigma=1.0, fine sigma=0.1."""
    X = rng.normal(size=(n_coarse + n_fine, 2))
    y = np.concatenate([rng.normal(0, 1.0, n_coarse), rng.normal(0, 0.1, n_fine)]).reshape(-1, 1)
    groups = np.array(["smoke"] * n_coarse + ["production"] * n_fine)
    return X, y, groups


def test_group_quantiles_reflect_group_noise():
    rng = np.random.default_rng(7)
    X, y, groups = _mixed_fidelity_data(rng)
    cal = fit_conformal_grouped(_ZeroModel(), X, y, ["cl"], groups, alpha=0.10)
    q_coarse = cal.q_hat_by_group["smoke"]["cl"]
    q_fine = cal.q_hat_by_group["production"]["cl"]
    assert q_coarse > 5 * q_fine  # intervals honestly widen on coarse data
    # marginal fallback sits between the two group quantiles
    assert q_fine < cal.fallback.q_hat["cl"] < q_coarse


def test_per_group_coverage_guarantee():
    rng = np.random.default_rng(11)
    X, y, groups = _mixed_fidelity_data(rng, n_coarse=500, n_fine=500)
    cal = fit_conformal_grouped(_ZeroModel(), X, y, ["cl"], groups, alpha=0.10)

    X_new, y_new, groups_new = _mixed_fidelity_data(rng, n_coarse=2000, n_fine=2000)
    _, lower, upper = predict_with_conformal_intervals_grouped(
        _ZeroModel(), X_new, cal, ["cl"], groups_new
    )
    covered = (y_new >= lower) & (y_new <= upper)
    for group in ("smoke", "production"):
        mask = groups_new == group
        coverage = covered[mask].mean()
        assert coverage >= 0.88, f"{group}: coverage {coverage:.3f} < target 0.90-eps"


def test_marginal_conformal_hides_per_group_undercoverage():
    """The motivating failure: marginal q undercovers the noisy group."""
    rng = np.random.default_rng(13)
    X, y, groups = _mixed_fidelity_data(rng, n_coarse=200, n_fine=800)
    marginal = fit_conformal(_ZeroModel(), X, y, ["cl"], alpha=0.10)
    q = marginal.q_hat["cl"]
    X_new, y_new, groups_new = _mixed_fidelity_data(rng, n_coarse=3000, n_fine=3000)
    covered = np.abs(y_new[:, 0]) <= q
    coarse_coverage = covered[groups_new == "smoke"].mean()
    assert coarse_coverage < 0.88  # marginal guarantee silently broken per group


def test_small_group_falls_back_to_marginal():
    rng = np.random.default_rng(3)
    X, y, groups = _mixed_fidelity_data(rng, n_coarse=200, n_fine=5)
    cal = fit_conformal_grouped(_ZeroModel(), X, y, ["cl"], groups, alpha=0.10, min_group_size=20)
    assert "production" not in cal.q_hat_by_group
    assert cal.n_calibration_by_group["production"] == 5
    # inference on the small group uses the fallback quantile
    _, lower, upper = predict_with_conformal_intervals_grouped(
        _ZeroModel(), np.zeros((2, 2)), cal, ["cl"], np.array(["production", "unseen"])
    )
    expected = cal.fallback.q_hat["cl"]
    assert upper[0, 0] == pytest.approx(expected)
    assert upper[1, 0] == pytest.approx(expected)


def test_save_load_roundtrip(tmp_path: Path):
    rng = np.random.default_rng(5)
    X, y, groups = _mixed_fidelity_data(rng)
    cal = fit_conformal_grouped(_ZeroModel(), X, y, ["cl"], groups, alpha=0.10)
    path = save_grouped_conformal_calibration(cal, tmp_path / "grouped.json")
    loaded = load_grouped_conformal_calibration(path)
    assert loaded.q_hat_by_group == cal.q_hat_by_group
    assert loaded.fallback.q_hat == cal.fallback.q_hat
    assert loaded.group_column == "fidelity"


def test_group_length_mismatch_rejected():
    rng = np.random.default_rng(1)
    X, y, groups = _mixed_fidelity_data(rng)
    with pytest.raises(ValueError, match="groups"):
        fit_conformal_grouped(_ZeroModel(), X, y, ["cl"], groups[:-5])
