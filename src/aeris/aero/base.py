from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class AeroSolver(ABC):
    """
    Minimal contract for an aerodynamic solver adapter.

    Important:
    - Different solvers may require different geometry preparations.
    - Different solvers may produce different result structures.
    - The contract stays intentionally minimal to avoid over-constraining
      future implementations.
    """

    @property
    @abstractmethod
    def solver_id(self) -> str:
        """Stable unique identifier for the solver."""
        raise NotImplementedError

    @property
    def display_name(self) -> str:
        return self.solver_id

    def get_default_config(self) -> Mapping[str, Any]:
        return {}

    @abstractmethod
    def prepare_input(self, geometry_case: Any, config: Mapping[str, Any]) -> Any:
        """
        Convert or adapt a geometry case into the solver's required input form.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self, prepared_input: Any, config: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Run the solver and return a result dictionary.
        """
        raise NotImplementedError