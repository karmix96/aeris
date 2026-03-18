from __future__ import annotations

from typing import Any

import numpy as np

from aeris.dataset.sampling.base import DatasetSampler
from aeris.dataset.sampling.registry import register_dataset_sampler
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig


def generate_random_samples(
    config: BWBGeneratorConfig,
    n_samples: int,
    sampler_seed: int | None = None,
) -> list[BWBDesignSample]:
    rng = np.random.default_rng(sampler_seed)

    pb = config.planform_bounds
    sb = config.section_bounds

    samples: list[BWBDesignSample] = []
    for _ in range(n_samples):
        samples.append(
            BWBDesignSample(
                c1_m=float(rng.uniform(pb.c1_m.min, pb.c1_m.max)),
                c2_ratio=float(rng.uniform(pb.c2_ratio.min, pb.c2_ratio.max)),
                c3_ratio=float(rng.uniform(pb.c3_ratio.min, pb.c3_ratio.max)),
                c4_ratio=float(rng.uniform(pb.c4_ratio.min, pb.c4_ratio.max)),
                b_total_m=float(rng.uniform(pb.b_total_m.min, pb.b_total_m.max)),
                b3_ratio=float(rng.uniform(pb.b3_ratio.min, pb.b3_ratio.max)),
                split_ratio=float(rng.uniform(pb.split_ratio.min, pb.split_ratio.max)),
                sw1_deg=float(rng.uniform(-pb.sw1_deg.max, -pb.sw1_deg.min)),
                sw2_deg=float(rng.uniform(-pb.sw2_deg.max, -pb.sw2_deg.min)),
                sw3_deg=float(rng.uniform(-pb.sw3_deg.max, -pb.sw3_deg.min)),
                twist_b0_deg=float(rng.uniform(sb.twist_b0_deg.min, sb.twist_b0_deg.max)),
                twist_b1_deg=float(rng.uniform(sb.twist_b1_deg.min, sb.twist_b1_deg.max)),
                twist_b2_deg=float(rng.uniform(sb.twist_b2_deg.min, sb.twist_b2_deg.max)),
                twist_b3_deg=float(rng.uniform(sb.twist_b3_deg.min, sb.twist_b3_deg.max)),
                dihedral_b1_deg=float(rng.uniform(sb.dihedral_b1_deg.min, sb.dihedral_b1_deg.max)),
                dihedral_b2_deg=float(rng.uniform(sb.dihedral_b2_deg.min, sb.dihedral_b2_deg.max)),
                dihedral_b3_deg=float(rng.uniform(sb.dihedral_b3_deg.min, sb.dihedral_b3_deg.max)),
            )
        )

    return samples


@register_dataset_sampler
class RandomV1Sampler(DatasetSampler):
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
