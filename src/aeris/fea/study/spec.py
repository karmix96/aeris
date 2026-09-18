from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

STUDY_SCHEMA_VERSION = "aeris.fea.study.v1"


@dataclass(frozen=True)
class ConvergenceSpec:
    enabled: bool = False
    maximum_displacement_relative_change: float = 0.05
    maximum_stress_relative_change: float = 0.10
    maximum_mass_relative_change: float = 0.01


@dataclass(frozen=True)
class StudyVariant:
    name: str
    patch: dict[str, object] = field(default_factory=dict)
    description: str | None = None


@dataclass(frozen=True)
class StudySpec:
    name: str
    base_case: Path
    variants: tuple[StudyVariant, ...]
    baseline: str | None = None
    stages: tuple[str, ...] = ("geometry", "validate", "mesh", "solve", "physics", "post")
    convergence: ConvergenceSpec = field(default_factory=ConvergenceSpec)
    source_path: Path | None = None
