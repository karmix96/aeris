from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

from aeris.geometry.base import GeometryGenerator
from aeris.geometry.registry import register_geometry_generator

from aeris.geometry.sampling import sample_bwb_design
from aeris.geometry.case import generate_geometry_case_from_sample
from aeris.geometry.params import BWBGeneratorConfig, BWBDesignSample


@register_geometry_generator
class BwbSegmentedV1Generator(GeometryGenerator):
    """
    Thin wrapper around the current validated BWB segmented generator.
    """

    GENERATOR_ID = "bwb_segmented_v1"

    @property
    def generator_id(self) -> str:
        return self.GENERATOR_ID

    @property
    def display_name(self) -> str:
        return "BWB Segmented v1"

    # ---------------------------
    # Sampling
    # ---------------------------
    def sample_one(
        self,
        config: Mapping[str, Any],
        seed: int | None = None,
    ) -> Mapping[str, Any]:
        """
        Convert seed → RNG → BWBDesignSample
        """
        if not isinstance(config, BWBGeneratorConfig):
            raise TypeError(
                "BwbSegmentedV1Generator expects BWBGeneratorConfig, "
                f"got {type(config)}"
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
        """
        Generator-specific batch sample creation.

        For bwb_segmented_v1, batch sampling is LHS over the explicit design variables.
        """
        from aeris.dataset.lhs import generate_lhs_samples

        return generate_lhs_samples(
            config=config,
            n_samples=n_samples,
            lhs_seed=lhs_seed,
        )
    
    # ---------------------------
    # Geometry build
    # ---------------------------
    def build_case_from_sample(
        self,
        sample: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Any:
        """
        IMPORTANT:
        This wrapper DOES NOT know output_dir.
        So we do NOT call generate_geometry_case_from_sample here.

        This will be handled in pipeline layer.
        """
        return sample  # pass-through for now

    # ---------------------------
    # Full pipeline call (custom extension)
    # ---------------------------
    def run_full_case(
        self,
        sample: BWBDesignSample,
        config: BWBGeneratorConfig,
        output_dir: Path,
    ):
        """
        This is the REAL entrypoint for this generator family.
        """
        return generate_geometry_case_from_sample(
            config=config,
            sample=sample,
            output_dir=output_dir,
        )

    # ---------------------------
    # Summary extraction
    # ---------------------------
    def summarize_case(self, case: Any) -> Mapping[str, Any]:
        if hasattr(case, "summary"):
            return case.summary
        return {}