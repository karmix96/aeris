"""Tests for the registered bwb_segmented_v1 geometry generator."""

from __future__ import annotations

import pytest

from aeris.generators.bwb_segmented_v1.generator import BwbSegmentedV1Generator
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig


def test_bwb_segmented_v1_generator_identity():
    """Generator identity metadata should stay stable."""
    generator = BwbSegmentedV1Generator()

    assert generator.generator_id == "bwb_segmented_v1"
    assert generator.display_name == "BWB Segmented v1"


def test_bwb_segmented_v1_generator_build_config_returns_typed_config(raw_config):
    """build_config should return the expected typed config model."""
    generator = BwbSegmentedV1Generator()
    config = generator.build_config(raw_config)

    assert isinstance(config, BWBGeneratorConfig)


def test_bwb_segmented_v1_generator_sample_one_rejects_wrong_config_type():
    """sample_one should reject invalid config types clearly."""
    generator = BwbSegmentedV1Generator()

    with pytest.raises(TypeError, match="BWBGeneratorConfig"):
        generator.sample_one(config="not-a-config", seed=1)


def test_bwb_segmented_v1_generator_run_full_case_rejects_wrong_config_type(sample, tmp_path):
    """run_full_case should reject invalid config types clearly."""
    generator = BwbSegmentedV1Generator()

    with pytest.raises(TypeError, match="BWBGeneratorConfig"):
        generator.run_full_case(sample=sample, config="not-a-config", output_dir=tmp_path)


def test_bwb_segmented_v1_generator_run_full_case_rejects_wrong_sample_type(config, tmp_path):
    """run_full_case should reject invalid sample types clearly."""
    generator = BwbSegmentedV1Generator()

    with pytest.raises(TypeError, match="BWBDesignSample"):
        generator.run_full_case(sample="not-a-sample", config=config, output_dir=tmp_path)


def test_bwb_segmented_v1_generator_sample_one_returns_typed_sample(config):
    """sample_one should return the typed sampled design model."""
    generator = BwbSegmentedV1Generator()
    sample = generator.sample_one(config=config, seed=5)

    assert isinstance(sample, BWBDesignSample)