"""YAML -> StudySpec, and the deep-merge that turns a variant patch + a base
case mapping into a concrete, validated CaseSpec per variant.

Only mappings are merged recursively; lists and scalars in a patch replace
the base value outright (so e.g. ``solve.overrides`` can be fully replaced
without carrying stale keys, while ``solve.flow`` can be patched key-by-key).
"""

from __future__ import annotations

import copy
from pathlib import Path

from aeris.cfd.case.loader import case_spec_from_mapping
from aeris.cfd.case.spec import CaseSpec
from aeris.cfd.study.spec import STUDY_SCHEMA_VERSION, StudySpec, StudyVariant
from aeris.common.config import load_yaml_config


def _mapping(raw: object, name: str) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"study.{name} must be a mapping, got {type(raw).__name__}")
    return dict(raw)


def deep_merge(base: dict[str, object], patch: dict[str, object]) -> dict[str, object]:
    """Recursively merge ``patch`` onto ``base``; mappings merge, else patch wins."""
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_study_spec(config_path: str | Path) -> StudySpec:
    """Load and validate a study YAML (schema aeris.cfd.study.v1)."""
    path = Path(config_path).expanduser().resolve()
    raw = load_yaml_config(path)

    schema = raw.get("schema")
    if schema != STUDY_SCHEMA_VERSION:
        raise ValueError(f"study schema must be {STUDY_SCHEMA_VERSION!r}, got {schema!r}")

    study = _mapping(raw.get("study"), "study")
    if not study:
        raise ValueError("top-level 'study' mapping is required")

    name = study.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("study.name is required (non-empty string)")

    base_case_raw = study.get("base_case")
    if not isinstance(base_case_raw, str) or not base_case_raw:
        raise ValueError("study.base_case is required (path to a case YAML)")
    base_case = (path.parent / base_case_raw).resolve()
    if not base_case.is_file():
        raise ValueError(f"study.base_case not found: {base_case}")

    variants_raw = study.get("variants")
    if not isinstance(variants_raw, list) or not variants_raw:
        raise ValueError("study.variants must be a non-empty list")
    variants: list[StudyVariant] = []
    seen: set[str] = set()
    for index, entry in enumerate(variants_raw):
        entry_map = _mapping(entry, f"variants[{index}]")
        vname = entry_map.get("name")
        if not isinstance(vname, str) or not vname:
            raise ValueError(f"study.variants[{index}].name is required (non-empty string)")
        if vname in seen:
            raise ValueError(f"study.variants: duplicate name {vname!r}")
        seen.add(vname)
        variants.append(
            StudyVariant(
                name=vname,
                patch=_mapping(entry_map.get("patch"), f"variants[{index}].patch"),
                description=entry_map.get("description"),
            )
        )

    baseline = study.get("baseline")
    if baseline is not None and baseline not in seen:
        raise ValueError(f"study.baseline {baseline!r} not among variant names {sorted(seen)}")

    quantities = study.get("quantities", ["cl", "cd"])
    if not isinstance(quantities, list) or not all(isinstance(q, str) for q in quantities):
        raise ValueError(f"study.quantities must be a list of strings, got {quantities!r}")

    stages = study.get("stages", ["surface", "volume", "solve", "post"])
    if not isinstance(stages, list) or not all(isinstance(s, str) for s in stages):
        raise ValueError(f"study.stages must be a list of strings, got {stages!r}")

    return StudySpec(
        name=name,
        base_case=base_case,
        variants=tuple(variants),
        baseline=baseline,
        quantities=tuple(quantities),
        stages=tuple(stages),
        description=study.get("description"),
        source_path=path,
    )


def build_variant_case_spec(study: StudySpec, variant: StudyVariant) -> CaseSpec:
    """Deep-merge one variant's patch onto the base case mapping -> CaseSpec.

    The variant's case name becomes ``<study.name>_<variant.name>`` so every
    variant lands in its own workdir under the study's directory and is
    unambiguous in solve_summary / GCI tables.
    """
    base_raw = load_yaml_config(study.base_case)
    merged = deep_merge(base_raw, {"case": variant.patch})
    merged.setdefault("case", {})
    merged["case"]["name"] = f"{study.name}_{variant.name}"
    return case_spec_from_mapping(merged, source_path=study.source_path)
