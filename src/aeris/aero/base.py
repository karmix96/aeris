"""
Abstract contract for aerodynamic solver plugins.

A solver adapter evaluates exactly one geometry view at exactly one flight
condition and returns one structured AeroResult. Multi-condition sweeps,
batching, retries, and dataset orchestration belong outside the solver in
pipeline/orchestration code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .models import AeroInput, AeroResult


class AeroSolver(ABC):
    """
    Formal solver contract for AERIS aero plugins.

    One call = one flight condition, one geometry view, one solver execution.
    Sweeps belong in pipeline/orchestration, not inside the solver adapter.
    """

    solver_id: str

    @abstractmethod
    def run_case(self, aero_input: AeroInput, output_dir: Path) -> AeroResult:
        raise NotImplementedError
