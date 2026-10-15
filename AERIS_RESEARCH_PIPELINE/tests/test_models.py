from __future__ import annotations

import numpy as np
import pytest

from aeris_research.common import PipelineError
from aeris_research.models import DenseAutoencoder, PODModel, grouped_geometry_split


def test_pod_reconstructs_low_rank_fields():
    rng = np.random.default_rng(3)
    coefficients = rng.normal(size=(12, 2))
    basis = rng.normal(size=(2, 20))
    fields = coefficients @ basis
    model = PODModel.fit(fields)
    reconstructed = model.decode(model.encode(fields, rank=2), rank=2)
    np.testing.assert_allclose(reconstructed, fields, atol=1.0e-10)


def test_geometry_split_has_no_leakage():
    groups = np.asarray(["g0", "g0", "g1", "g1", "g2", "g2", "g3", "g3"])
    split = grouped_geometry_split(groups, seed=7)
    memberships = {name: set(groups[index]) for name, index in split.items()}
    assert memberships["train"].isdisjoint(memberships["validation"])
    assert memberships["train"].isdisjoint(memberships["test"])
    assert memberships["validation"].isdisjoint(memberships["test"])


def test_geometry_split_refuses_one_geometry():
    with pytest.raises(PipelineError, match="at least 3 geometries"):
        grouped_geometry_split(np.asarray(["same", "same"]))


def test_regularized_autoencoder_learns_synthetic_manifold():
    rng = np.random.default_rng(9)
    latent = rng.normal(size=(30, 2))
    fields = np.tanh(latent @ rng.normal(size=(2, 12)))
    model = DenseAutoencoder(12, 3, seed=9)
    initial = np.mean((model.reconstruct(fields) - fields) ** 2)
    history = model.fit(fields, epochs=180, patience=180, learning_rate=1.0e-2)
    final = np.mean((model.reconstruct(fields) - fields) ** 2)
    assert history
    assert final < initial * 0.35
