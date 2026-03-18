from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

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

    def sample_one(
        self,
        config: Mapping[str, Any],
        seed: int | None = None,
    ) -> Mapping[str, Any]:
        if not isinstance(config, BWBGeneratorConfig):
            raise TypeError(
                f"BwbSegmentedV1Generator expects BWBGeneratorConfig, got {type(config)}"
            )
        rng = np.random.default_rng(seed)
        sample: BWBDesignSample = sample_bwb_design(config, rng)
        return sample

    def generate_dataset_samples(
        self,
        config: BWBGeneratorConfig,
        n_samples: int,
        lhs_seed: int | None,
    ):
        from aeris.dataset.lhs import generate_lhs_samples

        return generate_lhs_samples(
            config=config,
            n_samples=n_samples,
            lhs_seed=lhs_seed,
        )

    def build_case_from_sample(
        self,
        sample: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Any:
        return sample

    def run_full_case(
        self,
        sample: BWBDesignSample,
        config: BWBGeneratorConfig,
        output_dir: Path,
    ):
        return generate_geometry_case_from_sample(
            config=config,
            sample=sample,
            output_dir=output_dir,
        )

    def summarize_case(self, case: Any) -> Mapping[str, Any]:
        if hasattr(case, "summary"):
            return case.summary
        return {}
