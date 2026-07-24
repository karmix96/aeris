"""
Registered GeometryGenerator implementation for the bwb_segmented_v1 family.

This module adapts the framework-level GeometryGenerator contract to the
concrete BWB segmented generator implementation by delegating to:
    - config construction and validation (params + validation)
    - design sampling (sampling)
    - deterministic case generation (services, via the case.py shim)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from aeris.geometry.base import GeometryGenerator
from aeris.geometry.registry import register_geometry_generator

# case.py is a thin re-export shim from services.py; importing through it
# keeps scripts/ (which still import from case) functioning.
from aeris.generators.bwb_segmented_v1.case import (
    GeometryCaseResult,
    generate_geometry_case_from_sample,
)
from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    BWBGeneratorConfig,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.validation import validate_bwb_generator_config


@register_geometry_generator
class BwbSegmentedV1Generator(
    GeometryGenerator[BWBGeneratorConfig, BWBDesignSample, GeometryCaseResult]
):
    """Concrete generator for the BWB segmented v1 design family.

    This class is intentionally thin: no geometry math, no validation rules,
    no file I/O. All real work happens in params/sampling/validation/services.
    """

    GENERATOR_ID = "bwb_segmented"

    @property
    def display_name(self) -> str:
        return "BWB Segmented v1"

    def build_config(self, raw_config: dict[str, Any]) -> BWBGeneratorConfig:
        config = build_bwb_generator_config(raw_config)
        validate_bwb_generator_config(config)
        return config

    def sample_one(
        self,
        config: BWBGeneratorConfig,
        seed: int | None = None,
    ) -> BWBDesignSample:
        # Defensive runtime check at the CLI/Any boundary. Static typing
        # already enforces this at compile time for typed callers.
        if not isinstance(config, BWBGeneratorConfig):
            raise TypeError(
                f"BwbSegmentedV1Generator expects BWBGeneratorConfig, "
                f"got {type(config).__name__}."
            )
        # AERIS_PATCH_BATCH1_SAMPLE_ONE_CONFIG_SEED
        # Direct API callers expect sample_one(config) to follow the config seed,
        # matching CLI behavior. Passing seed=None to NumPy is nondeterministic.
        seed_final = config.generator.seed if seed is None else seed
        rng = np.random.default_rng(seed_final)
        return sample_bwb_design(config, rng)

    def run_full_case(
        self,
        sample: BWBDesignSample,
        config: BWBGeneratorConfig,
        output_dir: Path,
        save_plot: bool | None = None,
        build_aerosandbox: bool | None = None,
    ) -> GeometryCaseResult:
        # NOTE: save_plot/build_aerosandbox kwargs are BWB-specific and not
        # in the abstract base signature. Tracker item D15 covers moving
        # these into the config object so the base signature becomes complete.
        if not isinstance(config, BWBGeneratorConfig):
            raise TypeError(
                f"BwbSegmentedV1Generator expects BWBGeneratorConfig, "
                f"got {type(config).__name__}."
            )
        if not isinstance(sample, BWBDesignSample):
            raise TypeError(
                f"BwbSegmentedV1Generator expects BWBDesignSample, "
                f"got {type(sample).__name__}."
            )

        return generate_geometry_case_from_sample(
            config=config,
            sample=sample,
            output_dir=output_dir,
            save_plot=save_plot,
            build_aerosandbox=build_aerosandbox,
        )

    def summarize_case(self, case: GeometryCaseResult) -> dict[str, Any]:
        """Return the case summary as a dict.

        Downstream consumers (aeris.dataset.*, aeris.ml.*) expect a non-empty
        dict here. Missing or wrong-typed .summary raises explicitly rather
        than degrading silently to an empty dict.
        """
        if not hasattr(case, "summary"):
            raise AttributeError(
                f"{type(case).__name__} has no 'summary' attribute. "
                "BWB cases must produce a summary dict."
            )
        summary = case.summary
        if not isinstance(summary, dict):
            raise TypeError(
                f"BWB case.summary must be a dict, "
                f"got {type(summary).__name__}."
            )
        return summary