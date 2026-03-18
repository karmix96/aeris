from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class GeometryGenerator(ABC):
    """
    Minimal contract for a geometry generator.

    Important:
    - This contract is intentionally small.
    - Different generator families may have completely different internal
      philosophies, parameterizations, and intermediate representations.
    - The pipeline should depend only on this external contract.
    """

    @property
    @abstractmethod
    def generator_id(self) -> str:
        """Stable unique identifier for the generator family/version."""
        raise NotImplementedError

    @property
    def display_name(self) -> str:
        """Human-friendly generator name."""
        return self.generator_id

    def get_default_config(self) -> Mapping[str, Any]:
        """
        Optional generator-specific default config.
        Keep empty unless there is a real need.
        """
        return {}

    @abstractmethod
    def sample_one(self, config: Mapping[str, Any], seed: int | None = None) -> Mapping[str, Any]:
        """
        Produce one explicit design sample for this generator.

        Returns a fully explicit sample dictionary suitable for deterministic
        geometry reconstruction.
        """
        raise NotImplementedError

    @abstractmethod
    def build_case_from_sample(
        self,
        sample: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Any:
        """
        Build the generator's geometry case from an explicit sample.

        The returned object may be generator-specific internally.
        """
        raise NotImplementedError

    def export_case_artifacts(
        self,
        case: Any,
        output_dir: str,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """
        Optional artifact export hook.

        Returns a dictionary summary of what was exported.
        """
        return {}

    def summarize_case(self, case: Any) -> Mapping[str, Any]:
        """
        Optional summary hook for metadata/reporting.
        """
        return {}