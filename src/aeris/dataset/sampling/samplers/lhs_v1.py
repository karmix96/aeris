"""
Latin hypercube dataset sampler for the current BWB segmented generator.

This module generates reproducible Latin hypercube samples over the active
BWB design-variable bounds and converts sampled rows into explicit
BWBDesignSample objects for deterministic geometry realization.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np

from aeris.dataset.sampling.base import DatasetSampler
from aeris.dataset.sampling.registry import register_dataset_sampler
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig

_BWB_SAMPLE_DIM = 17


def _lhs_unit(n_samples: int, n_dim: int, rng: np.random.Generator) -> np.ndarray:
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    if n_dim < 1:
        raise ValueError("n_dim must be >= 1")

    result = np.empty((n_samples, n_dim), dtype=float)

    for j in range(n_dim):
        cut_points = (np.arange(n_samples, dtype=float) + rng.uniform(size=n_samples)) / n_samples
        rng.shuffle(cut_points)
        result[:, j] = cut_points

    return result


def _scale_column(unit_values: np.ndarray, min_value: float, max_value: float) -> np.ndarray:
    if max_value < min_value:
        raise ValueError(f"Invalid bounds: min_value={min_value}, max_value={max_value}")
    return min_value + unit_values * (max_value - min_value)


def _bwb_bounds(config: BWBGeneratorConfig) -> list[tuple[float, float]]:
    pb = config.planform_bounds
    sb = config.section_bounds

    bounds = [
        (pb.c1_m.min, pb.c1_m.max),
        (pb.c2_ratio.min, pb.c2_ratio.max),
        (pb.c3_ratio.min, pb.c3_ratio.max),
        (pb.c4_ratio.min, pb.c4_ratio.max),
        (pb.b_total_m.min, pb.b_total_m.max),
        (pb.b3_ratio.min, pb.b3_ratio.max),
        (pb.split_ratio.min, pb.split_ratio.max),
        (-pb.sw1_deg.max, -pb.sw1_deg.min),
        (-pb.sw2_deg.max, -pb.sw2_deg.min),
        (-pb.sw3_deg.max, -pb.sw3_deg.min),
        (sb.twist_b0_deg.min, sb.twist_b0_deg.max),
        (sb.twist_b1_deg.min, sb.twist_b1_deg.max),
        (sb.twist_b2_deg.min, sb.twist_b2_deg.max),
        (sb.twist_b3_deg.min, sb.twist_b3_deg.max),
        (sb.dihedral_b1_deg.min, sb.dihedral_b1_deg.max),
        (sb.dihedral_b2_deg.min, sb.dihedral_b2_deg.max),
        (sb.dihedral_b3_deg.min, sb.dihedral_b3_deg.max),
    ]

    if len(bounds) != _BWB_SAMPLE_DIM:
        raise ValueError(
            f"BWB bounds definition mismatch: expected {_BWB_SAMPLE_DIM} variables, got {len(bounds)}"
        )

    return bounds


def build_lhs_design_matrix(
    config: BWBGeneratorConfig,
    n_samples: int,
    rng: np.random.Generator,
) -> np.ndarray:
    bounds = _bwb_bounds(config)
    unit = _lhs_unit(n_samples=n_samples, n_dim=len(bounds), rng=rng)
    scaled = np.empty_like(unit)

    for j, (min_value, max_value) in enumerate(bounds):
        scaled[:, j] = _scale_column(unit[:, j], min_value, max_value)

    return scaled


def lhs_matrix_to_samples(matrix: np.ndarray) -> list[BWBDesignSample]:
    if matrix.ndim != 2 or matrix.shape[1] != _BWB_SAMPLE_DIM:
        raise ValueError(f"Expected matrix shape (n, {_BWB_SAMPLE_DIM}), got {matrix.shape}")

    samples: list[BWBDesignSample] = []
    for row in matrix:
        samples.append(
            BWBDesignSample(
                c1_m=float(row[0]),
                c2_ratio=float(row[1]),
                c3_ratio=float(row[2]),
                c4_ratio=float(row[3]),
                b_total_m=float(row[4]),
                b3_ratio=float(row[5]),
                split_ratio=float(row[6]),
                sw1_deg=float(row[7]),
                sw2_deg=float(row[8]),
                sw3_deg=float(row[9]),
                twist_b0_deg=float(row[10]),
                twist_b1_deg=float(row[11]),
                twist_b2_deg=float(row[12]),
                twist_b3_deg=float(row[13]),
                dihedral_b1_deg=float(row[14]),
                dihedral_b2_deg=float(row[15]),
                dihedral_b3_deg=float(row[16]),
            )
        )

    return samples


def generate_lhs_samples(
    config: BWBGeneratorConfig,
    n_samples: int,
    sampler_seed: int | None = None,
) -> list[BWBDesignSample]:
    rng = np.random.default_rng(sampler_seed)
    matrix = build_lhs_design_matrix(config=config, n_samples=n_samples, rng=rng)
    return lhs_matrix_to_samples(matrix)


def sample_to_flat_dict(sample: BWBDesignSample) -> dict[str, Any]:
    return asdict(sample)


@register_dataset_sampler
class LhsV1Sampler(DatasetSampler):
    """Latin hypercube sampler for the current BWB segmented generator."""

    SAMPLER_ID = "lhs_v1"

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
                f"LhsV1Sampler currently expects BWBGeneratorConfig, got {type(config)}"
            )

        return generate_lhs_samples(
            config=config,
            n_samples=n_samples,
            sampler_seed=sampler_seed,
        )