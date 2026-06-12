"""
Uniform-random dataset sampler for the current BWB segmented generator.

This module generates reproducible independent random samples over the active
BWB design-variable bounds and converts them into explicit BWBDesignSample
objects for deterministic geometry realization.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from aeris.dataset.sampling.base import DatasetSampler
from aeris.dataset.sampling.registry import register_dataset_sampler
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig


def _uniform_between(
    rng: np.random.Generator,
    min_value: float,
    max_value: float,
) -> float:
    if max_value < min_value:
        raise ValueError(f"Invalid bounds: min_value={min_value}, max_value={max_value}")
    return float(rng.uniform(min_value, max_value))


def generate_random_samples(
    config: BWBGeneratorConfig,
    n_samples: int,
    sampler_seed: int | None = None,
) -> list[BWBDesignSample]:
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")

    rng = np.random.default_rng(sampler_seed)

    pb = config.planform_bounds
    sb = config.section_bounds
    # BUG-17: elevon_bounds must be honoured so variable-elevon campaigns
    # actually sample the elevon design space. When absent, use the fixed
    # BWBDesignSample defaults (0.60/0.95/0.75) without consuming RNG state,
    # preserving backward compat for fixed-elevon configs.
    eb = config.elevon_bounds

    samples: list[BWBDesignSample] = []
    for _ in range(n_samples):
        if eb is not None:
            elevon_start = _uniform_between(rng, eb.elevon_start_frac.min, eb.elevon_start_frac.max)
            elevon_end   = _uniform_between(rng, eb.elevon_end_frac.min,   eb.elevon_end_frac.max)
            elevon_hinge = _uniform_between(rng, eb.elevon_hinge_frac.min, eb.elevon_hinge_frac.max)
        else:
            elevon_start = 0.60
            elevon_end   = 0.95
            elevon_hinge = 0.75

        samples.append(
            BWBDesignSample(
                c1_m=_uniform_between(rng, pb.c1_m.min, pb.c1_m.max),
                c2_ratio=_uniform_between(rng, pb.c2_ratio.min, pb.c2_ratio.max),
                c3_ratio=_uniform_between(rng, pb.c3_ratio.min, pb.c3_ratio.max),
                c4_ratio=_uniform_between(rng, pb.c4_ratio.min, pb.c4_ratio.max),
                b_total_m=_uniform_between(rng, pb.b_total_m.min, pb.b_total_m.max),
                b3_ratio=_uniform_between(rng, pb.b3_ratio.min, pb.b3_ratio.max),
                split_ratio=_uniform_between(rng, pb.split_ratio.min, pb.split_ratio.max),
                sw1_deg=_uniform_between(rng, -pb.sw1_deg.max, -pb.sw1_deg.min),
                sw2_deg=_uniform_between(rng, -pb.sw2_deg.max, -pb.sw2_deg.min),
                sw3_deg=_uniform_between(rng, -pb.sw3_deg.max, -pb.sw3_deg.min),
                twist_b0_deg=_uniform_between(rng, sb.twist_b0_deg.min, sb.twist_b0_deg.max),
                twist_b1_deg=_uniform_between(rng, sb.twist_b1_deg.min, sb.twist_b1_deg.max),
                twist_b2_deg=_uniform_between(rng, sb.twist_b2_deg.min, sb.twist_b2_deg.max),
                twist_b3_deg=_uniform_between(rng, sb.twist_b3_deg.min, sb.twist_b3_deg.max),
                dihedral_b1_deg=_uniform_between(rng, sb.dihedral_b1_deg.min, sb.dihedral_b1_deg.max),
                dihedral_b2_deg=_uniform_between(rng, sb.dihedral_b2_deg.min, sb.dihedral_b2_deg.max),
                dihedral_b3_deg=_uniform_between(rng, sb.dihedral_b3_deg.min, sb.dihedral_b3_deg.max),
                elevon_start_frac=elevon_start,
                elevon_end_frac=elevon_end,
                elevon_hinge_frac=elevon_hinge,
            )
        )

    return samples


@register_dataset_sampler
class RandomV1Sampler(DatasetSampler):
    """Uniform-random sampler for the current BWB segmented generator."""

    SAMPLER_ID = "random_v1"

    @property
    def sampler_id(self) -> str:
        return self.SAMPLER_ID

    def sample(
        self,
        config: Any,
        n_samples: int,
        sampler_seed: int | None = None,
    ) -> list[Any]:
        if not isinstance(config, BWBGeneratorConfig):
            raise TypeError(
                f"RandomV1Sampler currently expects BWBGeneratorConfig, got {type(config)}"
            )

        return generate_random_samples(
            config=config,
            n_samples=n_samples,
            sampler_seed=sampler_seed,
        )