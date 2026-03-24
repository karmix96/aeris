"""
Abstract base contract for dataset samplers.

A dataset sampler receives a resolved generator config, the requested number of
samples, and an optional seed, then returns explicit design samples ready to be
passed into the generator's deterministic realization path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DatasetSampler(ABC):
    """Abstract interface for dataset-sampling implementations."""

    @property
    @abstractmethod
    def sampler_id(self) -> str:
        raise NotImplementedError

    @property
    def display_name(self) -> str:
        return self.sampler_id

    @abstractmethod
    def sample(
        self,
        config: Any,
        n_samples: int,
        sampler_seed: int | None = None,
    ) -> list[Any]:
        raise NotImplementedError