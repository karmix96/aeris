"""
Study specification dataclasses (schema ``aeris.cfd.study.v1``).

A study is a *base case* plus named variants, each a deep-merge patch onto
the base case mapping.  This makes every sensitivity analysis (farfield
distance, wall spacing, iterative tolerance, solver scheme, ...) a single
reviewable YAML instead of a pile of hand-edited case copies — the same
reproducibility argument the case spec makes, one level up.  The runner
executes each variant through the ordinary case runner (inheriting the
full provenance chain) and emits one ``study_report.json`` with deltas
against a designated baseline variant.

Method reference: parameter-sensitivity reporting as required by the
AIAA CFD verification & validation guide (AIAA G-077-1998) and the
ASME V&V 20 solution-verification framework — sensitivity claims must be
traceable to the exact inputs that produced them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

STUDY_SCHEMA_VERSION = "aeris.cfd.study.v1"
STUDY_REPORT_SCHEMA_VERSION = "aeris.cfd.study_report.v1"


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
    baseline: str | None = None  # variant deltas are computed against
    quantities: tuple[str, ...] = ("cl", "cd")
    stages: tuple[str, ...] = ("surface", "volume", "solve", "post")
    description: str | None = None
    source_path: Path | None = None
