"""
Defines the abstract contract for all geometry generators.

A geometry generator in AERIS must implement:
- configuration construction from raw YAML input
- sampling of explicit design vectors
- deterministic geometry realization from a sample

Pipelines and higher-level systems depend only on this interface,
allowing multiple geometry families and implementations to coexist.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping


class GeometryGenerator(ABC):
    """
    External contract for geometry generators.

    Pipelines should depend on this contract, not on generator-specific files.
    """

    @property
    @abstractmethod
    def generator_id(self) -> str:
        raise NotImplementedError

    @property
    def display_name(self) -> str:
        return self.generator_id

    @abstractmethod
    def build_config(self, raw_config: dict[str, Any]) -> Any:
        """
        Build and validate the generator-specific typed config object.
        """
        raise NotImplementedError

    @abstractmethod
    def sample_one(self, config: Any, seed: int | None = None) -> Any:
        """
        Produce one explicit sampled design vector.
        """
        raise NotImplementedError

    @abstractmethod
    def run_full_case(
        self,
        sample: Any,
        config: Any,
        output_dir: Path,
    ) -> Any:
        """
        Run the full deterministic geometry realization from an explicit sample.
        """
        raise NotImplementedError

    def summarize_case(self, case: Any) -> Mapping[str, Any]:
        return {}
