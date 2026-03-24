from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from aeris.dataset.sampling.base import DatasetSampler
from aeris.dataset.sampling.samplers.lhs_v1 import (
    _lhs_unit,
    _scale_column,
    build_lhs_design_matrix,
    generate_lhs_samples,
    lhs_matrix_to_samples,
    LhsV1Sampler,
)
from aeris.dataset.sampling.samplers.random_v1 import (
    generate_random_samples,
    RandomV1Sampler,
)
from aeris.dataset.sampling.registry import (
    get_dataset_sampler,
    list_dataset_samplers,
    register_dataset_sampler,
)
from aeris.dataset.sampling.resolver import resolve_dataset_sampler
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

from pathlib import Path

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _make_raw_config() -> dict:
    config_path = _repo_root() / "configs" / "geometry" / "wing_bwb.yaml"
    return load_yaml_config(config_path)


def _make_config():
    return build_bwb_generator_config(_make_raw_config())

def test_resolve_dataset_sampler_defaults() -> None:
    sampler_id, sampler_seed = resolve_dataset_sampler({})
    assert sampler_id == "lhs_v1"
    assert sampler_seed is None


def test_resolve_dataset_sampler_uses_config_values() -> None:
    raw = {"dataset": {"sampling": {"method": "random_v1", "seed": 123}}}
    sampler_id, sampler_seed = resolve_dataset_sampler(raw)
    assert sampler_id == "random_v1"
    assert sampler_seed == 123


def test_resolve_dataset_sampler_override_wins() -> None:
    raw = {"dataset": {"sampling": {"method": "lhs_v1", "seed": 123}}}
    sampler_id, sampler_seed = resolve_dataset_sampler(
        raw,
        sampler_override="random_v1",
        sampler_seed_override=999,
    )
    assert sampler_id == "random_v1"
    assert sampler_seed == 999


def test_resolve_dataset_sampler_rejects_unknown_sampler() -> None:
    raw = {"dataset": {"sampling": {"method": "banana_v1"}}}
    with pytest.raises(ValueError, match="Unknown dataset sampler"):
        resolve_dataset_sampler(raw)


def test_resolve_dataset_sampler_rejects_non_mapping_dataset() -> None:
    with pytest.raises(TypeError, match="dataset"):
        resolve_dataset_sampler({"dataset": 123})


def test_resolve_dataset_sampler_rejects_non_mapping_sampling() -> None:
    with pytest.raises(TypeError, match="dataset.sampling"):
        resolve_dataset_sampler({"dataset": {"sampling": 123}})


def test_registry_lists_known_samplers() -> None:
    sampler_ids = list_dataset_samplers()
    assert "lhs_v1" in sampler_ids
    assert "random_v1" in sampler_ids


def test_get_dataset_sampler_returns_instance() -> None:
    sampler = get_dataset_sampler("lhs_v1")
    assert isinstance(sampler, LhsV1Sampler)


def test_get_dataset_sampler_rejects_unknown_id() -> None:
    with pytest.raises(KeyError, match="Unknown dataset sampler"):
        get_dataset_sampler("missing_sampler")


def test_register_dataset_sampler_rejects_missing_id() -> None:
    class BadSampler(DatasetSampler):
        @property
        def sampler_id(self) -> str:
            return "bad"

        def sample(self, config, n_samples, sampler_seed=None):
            return []

    with pytest.raises(ValueError, match="missing class attribute"):
        register_dataset_sampler(BadSampler)


def test_register_dataset_sampler_rejects_duplicate_id() -> None:
    class DuplicateSampler(DatasetSampler):
        SAMPLER_ID = "lhs_v1"

        @property
        def sampler_id(self) -> str:
            return self.SAMPLER_ID

        def sample(self, config, n_samples, sampler_seed=None):
            return []

    with pytest.raises(ValueError, match="already registered"):
        register_dataset_sampler(DuplicateSampler)


def test_lhs_unit_shape_and_range() -> None:
    rng = np.random.default_rng(42)
    unit = _lhs_unit(n_samples=5, n_dim=3, rng=rng)

    assert unit.shape == (5, 3)
    assert np.all(unit >= 0.0)
    assert np.all(unit < 1.0)


def test_lhs_unit_rejects_invalid_shape_args() -> None:
    rng = np.random.default_rng(42)

    with pytest.raises(ValueError, match="n_samples"):
        _lhs_unit(n_samples=0, n_dim=3, rng=rng)

    with pytest.raises(ValueError, match="n_dim"):
        _lhs_unit(n_samples=3, n_dim=0, rng=rng)


def test_scale_column_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="Invalid bounds"):
        _scale_column(np.array([0.1, 0.2]), 2.0, 1.0)


def test_build_lhs_design_matrix_shape_and_reproducibility() -> None:
    config = _make_config()

    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)

    m1 = build_lhs_design_matrix(config=config, n_samples=4, rng=rng1)
    m2 = build_lhs_design_matrix(config=config, n_samples=4, rng=rng2)

    assert m1.shape == (4, 17)
    assert np.allclose(m1, m2)


def test_lhs_matrix_to_samples_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError, match="Expected matrix shape"):
        lhs_matrix_to_samples(np.zeros((4, 16)))


def test_generate_lhs_samples_reproducible() -> None:
    config = _make_config()

    s1 = generate_lhs_samples(config=config, n_samples=3, sampler_seed=42)
    s2 = generate_lhs_samples(config=config, n_samples=3, sampler_seed=42)

    assert [x.to_dict() for x in s1] == [x.to_dict() for x in s2]


def test_generate_random_samples_reproducible() -> None:
    config = _make_config()

    s1 = generate_random_samples(config=config, n_samples=3, sampler_seed=42)
    s2 = generate_random_samples(config=config, n_samples=3, sampler_seed=42)

    assert [x.to_dict() for x in s1] == [x.to_dict() for x in s2]


def test_generate_random_samples_rejects_invalid_n() -> None:
    config = _make_config()

    with pytest.raises(ValueError, match="n_samples"):
        generate_random_samples(config=config, n_samples=0, sampler_seed=42)


def test_lhs_sampler_rejects_wrong_config_type() -> None:
    sampler = LhsV1Sampler()

    with pytest.raises(TypeError, match="BWBGeneratorConfig"):
        sampler.sample(config=object(), n_samples=3, sampler_seed=42)


def test_random_sampler_rejects_wrong_config_type() -> None:
    sampler = RandomV1Sampler()

    with pytest.raises(TypeError, match="BWBGeneratorConfig"):
        sampler.sample(config=object(), n_samples=3, sampler_seed=42)


def test_lhs_samples_respect_bounds() -> None:
    config = _make_config()
    samples = generate_lhs_samples(config=config, n_samples=10, sampler_seed=42)

    pb = config.planform_bounds
    sb = config.section_bounds

    for s in samples:
        assert pb.c1_m.min <= s.c1_m <= pb.c1_m.max
        assert pb.c2_ratio.min <= s.c2_ratio <= pb.c2_ratio.max
        assert pb.c3_ratio.min <= s.c3_ratio <= pb.c3_ratio.max
        assert pb.c4_ratio.min <= s.c4_ratio <= pb.c4_ratio.max
        assert pb.b_total_m.min <= s.b_total_m <= pb.b_total_m.max
        assert pb.b3_ratio.min <= s.b3_ratio <= pb.b3_ratio.max
        assert pb.split_ratio.min <= s.split_ratio <= pb.split_ratio.max
        assert -pb.sw1_deg.max <= s.sw1_deg <= -pb.sw1_deg.min
        assert -pb.sw2_deg.max <= s.sw2_deg <= -pb.sw2_deg.min
        assert -pb.sw3_deg.max <= s.sw3_deg <= -pb.sw3_deg.min
        assert sb.twist_b0_deg.min <= s.twist_b0_deg <= sb.twist_b0_deg.max
        assert sb.twist_b1_deg.min <= s.twist_b1_deg <= sb.twist_b1_deg.max
        assert sb.twist_b2_deg.min <= s.twist_b2_deg <= sb.twist_b2_deg.max
        assert sb.twist_b3_deg.min <= s.twist_b3_deg <= sb.twist_b3_deg.max
        assert sb.dihedral_b1_deg.min <= s.dihedral_b1_deg <= sb.dihedral_b1_deg.max
        assert sb.dihedral_b2_deg.min <= s.dihedral_b2_deg <= sb.dihedral_b2_deg.max
        assert sb.dihedral_b3_deg.min <= s.dihedral_b3_deg <= sb.dihedral_b3_deg.max


def test_random_samples_respect_bounds() -> None:
    config = _make_config()
    samples = generate_random_samples(config=config, n_samples=10, sampler_seed=42)

    pb = config.planform_bounds
    sb = config.section_bounds

    for s in samples:
        assert pb.c1_m.min <= s.c1_m <= pb.c1_m.max
        assert pb.c2_ratio.min <= s.c2_ratio <= pb.c2_ratio.max
        assert pb.c3_ratio.min <= s.c3_ratio <= pb.c3_ratio.max
        assert pb.c4_ratio.min <= s.c4_ratio <= pb.c4_ratio.max
        assert pb.b_total_m.min <= s.b_total_m <= pb.b_total_m.max
        assert pb.b3_ratio.min <= s.b3_ratio <= pb.b3_ratio.max
        assert pb.split_ratio.min <= s.split_ratio <= pb.split_ratio.max
        assert -pb.sw1_deg.max <= s.sw1_deg <= -pb.sw1_deg.min
        assert -pb.sw2_deg.max <= s.sw2_deg <= -pb.sw2_deg.min
        assert -pb.sw3_deg.max <= s.sw3_deg <= -pb.sw3_deg.min
        assert sb.twist_b0_deg.min <= s.twist_b0_deg <= sb.twist_b0_deg.max
        assert sb.twist_b1_deg.min <= s.twist_b1_deg <= sb.twist_b1_deg.max
        assert sb.twist_b2_deg.min <= s.twist_b2_deg <= sb.twist_b2_deg.max
        assert sb.twist_b3_deg.min <= s.twist_b3_deg <= sb.twist_b3_deg.max
        assert sb.dihedral_b1_deg.min <= s.dihedral_b1_deg <= sb.dihedral_b1_deg.max
        assert sb.dihedral_b2_deg.min <= s.dihedral_b2_deg <= sb.dihedral_b2_deg.max
        assert sb.dihedral_b3_deg.min <= s.dihedral_b3_deg <= sb.dihedral_b3_deg.max