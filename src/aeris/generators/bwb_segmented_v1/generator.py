"""
Registered GeometryGenerator implementation for the bwb_segmented_v1 family.

This module adapts the framework-level GeometryGenerator contract to the
concrete BWB segmented generator implementation by delegating to:
- config construction and validation
- design sampling
- deterministic case generation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from aeris.geometry.base import GeometryGenerator
from aeris.geometry.registry import register_geometry_generator

from aeris.generators.bwb_segmented_v1.case import generate_geometry_case_from_sample
from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    BWBGeneratorConfig,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.validation import validate_bwb_generator_config


@register_geometry_generator
class BwbSegmentedV1Generator(GeometryGenerator):
    GENERATOR_ID = "bwb_segmented_v1"

    @property
    def generator_id(self) -> str:
        return self.GENERATOR_ID

    @property
    def display_name(self) -> str:
        return "BWB Segmented v1"

    def build_config(self, raw_config: dict[str, Any]) -> BWBGeneratorConfig:
        config = build_bwb_generator_config(raw_config)
        validate_bwb_generator_config(config)
        return config

    def sample_one(self, config: Any, seed: int | None = None) -> BWBDesignSample:
        if not isinstance(config, BWBGeneratorConfig):
            raise TypeError(
                f"BwbSegmentedV1Generator expects BWBGeneratorConfig, got {type(config)}"
            )
        rng = np.random.default_rng(seed)
        return sample_bwb_design(config, rng)

    def run_full_case(
        self,
        sample: Any,
        config: Any,
        output_dir: Path,
        save_plot: bool | None = None,
        build_aerosandbox: bool | None = None,
    ) -> Any:
        if not isinstance(config, BWBGeneratorConfig):
            raise TypeError(
                f"BwbSegmentedV1Generator expects BWBGeneratorConfig, got {type(config)}"
            )
        if not isinstance(sample, BWBDesignSample):
            raise TypeError(
                f"BwbSegmentedV1Generator expects BWBDesignSample, got {type(sample)}"
            )

        return generate_geometry_case_from_sample(
            config=config,
            sample=sample,
            output_dir=output_dir,
            save_plot=save_plot,
            build_aerosandbox=build_aerosandbox,
        )

    def summarize_case(self, case: Any) -> dict[str, Any]:
        if hasattr(case, "summary"):
            return case.summary
        return {}