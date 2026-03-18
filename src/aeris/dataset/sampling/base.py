from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DatasetSampler(ABC):
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
