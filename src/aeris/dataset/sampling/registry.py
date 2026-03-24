"""
Dataset sampler registry for AERIS.

This module stores the mapping from sampler ids to sampler implementation
classes, supports registration at import time, and provides lookup/listing
helpers used by dataset orchestration and config resolution.
"""

from __future__ import annotations

from typing import Dict, Type

from aeris.dataset.sampling.base import DatasetSampler


_DATASET_SAMPLERS: Dict[str, Type[DatasetSampler]] = {}


def register_dataset_sampler(sampler_cls: Type[DatasetSampler]) -> Type[DatasetSampler]:
    sampler_id = getattr(sampler_cls, "SAMPLER_ID", None)
    if not sampler_id:
        raise ValueError(
            f"Cannot register dataset sampler {sampler_cls.__name__}: "
            "missing class attribute 'SAMPLER_ID'."
        )

    if sampler_id in _DATASET_SAMPLERS:
        raise ValueError(f"Dataset sampler '{sampler_id}' is already registered.")

    _DATASET_SAMPLERS[sampler_id] = sampler_cls
    return sampler_cls


def get_dataset_sampler(sampler_id: str) -> DatasetSampler:
    try:
        sampler_cls = _DATASET_SAMPLERS[sampler_id]
    except KeyError as exc:
        available = ", ".join(sorted(_DATASET_SAMPLERS)) or "<none>"
        raise KeyError(
            f"Unknown dataset sampler '{sampler_id}'. "
            f"Available samplers: {available}"
        ) from exc

    return sampler_cls()


def list_dataset_samplers() -> list[str]:
    return sorted(_DATASET_SAMPLERS.keys())