"""Load FEA studies and deep-merge variants onto one governed base case."""

from __future__ import annotations

import copy
from pathlib import Path

from aeris.common.config import load_yaml_config
from aeris.fea.case.loader import case_spec_from_mapping
from aeris.fea.case.spec import CaseSpec
from aeris.fea.study.spec import (
    STUDY_SCHEMA_VERSION,
    ConvergenceSpec,
    StudySpec,
    StudyVariant,
)


def deep_merge(base: dict[str, object], patch: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = copy.deepcopy(value)
    return result


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"study.{name} must be a mapping")
    return dict(value)


def _positive(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0.0:
        raise ValueError(f"study.{name} must be positive")
    return float(value)


def load_study_spec(path: str | Path) -> StudySpec:
    source = Path(path).expanduser().resolve()
    raw = load_yaml_config(source)
    if raw.get("schema") != STUDY_SCHEMA_VERSION:
        raise ValueError(f"study schema must be {STUDY_SCHEMA_VERSION!r}")
    study = _mapping(raw.get("study"), "study")
    name = study.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("study.name is required")
    base_value = study.get("base_case")
    if not isinstance(base_value, str) or not base_value:
        raise ValueError("study.base_case is required")
    base_case = (source.parent / base_value).resolve()
    if not base_case.is_file():
        raise ValueError(f"study.base_case not found: {base_case}")
    variants_raw = study.get("variants")
    if not isinstance(variants_raw, list) or not variants_raw:
        raise ValueError("study.variants must be a non-empty list")
    variants: list[StudyVariant] = []
    names: set[str] = set()
    for index, value in enumerate(variants_raw):
        item = _mapping(value, f"variants[{index}]")
        variant_name = item.get("name")
        if not isinstance(variant_name, str) or not variant_name:
            raise ValueError(f"study.variants[{index}].name is required")
        if variant_name in names:
            raise ValueError(f"study.variants duplicate name {variant_name!r}")
        names.add(variant_name)
        patch = item.get("patch", {})
        variants.append(
            StudyVariant(
                name=variant_name,
                patch=_mapping(patch, f"variants[{index}].patch"),
                description=item.get("description")
                if isinstance(item.get("description"), str)
                else None,
            )
        )
    baseline = study.get("baseline")
    if baseline is not None and baseline not in names:
        raise ValueError(f"study.baseline {baseline!r} is not a variant")
    stages = study.get(
        "stages", ["geometry", "validate", "mesh", "solve", "physics", "post"]
    )
    if not isinstance(stages, list) or not all(isinstance(v, str) for v in stages):
        raise ValueError("study.stages must be a list of strings")
    convergence_raw = _mapping(study.get("convergence", {}), "convergence")
    enabled = convergence_raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("study.convergence.enabled must be a bool")
    if enabled and len(variants) < 3:
        raise ValueError("enabled mesh convergence requires at least three variants")
    convergence = ConvergenceSpec(
        enabled=enabled,
        maximum_displacement_relative_change=_positive(
            convergence_raw.get("maximum_displacement_relative_change", 0.05),
            "convergence.maximum_displacement_relative_change",
        ),
        maximum_stress_relative_change=_positive(
            convergence_raw.get("maximum_stress_relative_change", 0.10),
            "convergence.maximum_stress_relative_change",
        ),
        maximum_mass_relative_change=_positive(
            convergence_raw.get("maximum_mass_relative_change", 0.01),
            "convergence.maximum_mass_relative_change",
        ),
    )
    return StudySpec(
        name=name,
        base_case=base_case,
        variants=tuple(variants),
        baseline=baseline,
        stages=tuple(stages),
        convergence=convergence,
        source_path=source,
    )


def build_variant_case_spec(study: StudySpec, variant: StudyVariant) -> CaseSpec:
    merged = deep_merge(load_yaml_config(study.base_case), {"case": variant.patch})
    case = merged.get("case")
    if not isinstance(case, dict):
        raise ValueError("base case has no case mapping")
    case["name"] = f"{study.name}_{variant.name}"
    return case_spec_from_mapping(merged, source_path=study.source_path)
