"""Typed study schema and deterministic experiment planning.

The study deliberately stores *public* sweep values as positive aft-sweep
magnitudes.  ``VariableSpec.sample_scale=-1`` converts those values to the
negative-aft convention used by :class:`BWBDesignSample`.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from scipy.stats import qmc

SCHEMA_VERSION = "aeris.pygeo_surface_mesh_study.v1"
EXPECTED_SAMPLE_FIELDS = (
    "c1_m",
    "c2_ratio",
    "c3_ratio",
    "c4_ratio",
    "b_total_m",
    "b3_ratio",
    "split_ratio",
    "sw1_deg",
    "sw2_deg",
    "sw3_deg",
    "twist_b0_deg",
    "twist_b1_deg",
    "twist_b2_deg",
    "twist_b3_deg",
    "dihedral_b1_deg",
    "dihedral_b2_deg",
    "dihedral_b3_deg",
)
VALID_OPERATORS = {"<=", ">="}
VALID_STAGES = {"baseline", "ofat", "pairwise", "lhs"}


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return dict(value)


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return list(value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{label} must be a non-empty string")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must be numeric, got {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must be an integer, got {value!r}") from exc
    if float(result) != float(value):
        raise TypeError(f"{label} must be an integer, got {value!r}")
    return result


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be boolean")
    return value


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_path(value: object, *, config_path: Path, label: str) -> Path:
    raw = Path(_string(value, label)).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    # Repository configs conventionally use paths relative to the repository
    # root, while a portable external study can use paths relative to itself.
    repo = next(
        (
            parent
            for parent in (config_path.parent, *config_path.parents)
            if (parent / "pyproject.toml").is_file()
        ),
        None,
    )
    candidates = [config_path.parent / raw]
    if repo is not None:
        candidates.insert(0, repo / raw)
    candidates.append(Path.cwd() / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


@dataclass(frozen=True)
class VariableSpec:
    """One public study variable and its Aeris sample-field mapping."""

    name: str
    sample_field: str
    units: str
    baseline: float
    low: float
    high: float
    sample_scale: float = 1.0

    def __post_init__(self) -> None:
        values = (self.baseline, self.low, self.high, self.sample_scale)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{self.name}: all numeric values must be finite")
        if self.low > self.baseline or self.baseline > self.high:
            raise ValueError(
                f"{self.name}: expected low <= baseline <= high, got "
                f"{self.low} <= {self.baseline} <= {self.high}"
            )
        if self.low == self.high:
            raise ValueError(f"{self.name}: low and high must differ")
        if self.sample_scale == 0.0:
            raise ValueError(f"{self.name}: sample_scale must be non-zero")

    def value_at_fraction(self, fraction: float) -> float:
        """Map a normalized perturbation in [-1, 1] piecewise about baseline."""

        fraction = float(fraction)
        if not -1.0 <= fraction <= 1.0:
            raise ValueError(f"{self.name}: perturbation fraction must be in [-1, 1]")
        endpoint = self.low if fraction < 0.0 else self.high
        return self.baseline + abs(fraction) * (endpoint - self.baseline)

    def to_sample_value(self, public_value: float) -> float:
        return self.sample_scale * float(public_value)

    def normalized_fraction(self, public_value: float) -> float:
        value = float(public_value)
        if math.isclose(value, self.baseline, rel_tol=0.0, abs_tol=1.0e-14):
            return 0.0
        endpoint = self.low if value < self.baseline else self.high
        denominator = endpoint - self.baseline
        if denominator == 0.0:
            raise ValueError(f"{self.name}: value is on a zero-width side of the range")
        return math.copysign(abs((value - self.baseline) / denominator), value - self.baseline)


@dataclass(frozen=True)
class MeshLevel:
    name: str
    order: int
    points_per_block_side: int
    spanwise_panels_per_section: int
    cap_wrap_points: int
    tip_radial_points: int

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError(f"{self.name}: order must be positive")
        if self.points_per_block_side < 9:
            raise ValueError(f"{self.name}: points_per_block_side must be at least 9")
        if self.spanwise_panels_per_section < 1:
            raise ValueError(f"{self.name}: spanwise_panels_per_section must be at least 1")
        if self.cap_wrap_points < 5:
            raise ValueError(f"{self.name}: cap_wrap_points must be at least 5")
        if self.tip_radial_points < 2:
            raise ValueError(f"{self.name}: tip_radial_points must be at least 2")


@dataclass(frozen=True)
class MetricLimit:
    path: str
    operator: str
    limit: float | None
    enabled: bool
    description: str = ""

    def __post_init__(self) -> None:
        if self.operator not in VALID_OPERATORS:
            raise ValueError(f"{self.path}: operator must be one of {sorted(VALID_OPERATORS)}")
        if self.limit is not None and not math.isfinite(self.limit):
            raise ValueError(f"{self.path}: limit must be finite or null")

    def passes(self, value: float) -> bool | None:
        if not self.enabled or self.limit is None:
            return None
        if not math.isfinite(value):
            return False
        return value <= self.limit if self.operator == "<=" else value >= self.limit


@dataclass(frozen=True)
class StudyCase:
    case_id: str
    stage: str
    public_values: dict[str, float]
    perturbations: dict[str, float]
    sequence_index: int

    def __post_init__(self) -> None:
        if self.stage not in VALID_STAGES:
            raise ValueError(f"Invalid study stage {self.stage!r}")

    @property
    def identity_hash(self) -> str:
        return _canonical_hash(
            {
                "case_id": self.case_id,
                "stage": self.stage,
                "public_values": self.public_values,
                "perturbations": self.perturbations,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "stage": self.stage,
            "sequence_index": self.sequence_index,
            "public_values": dict(self.public_values),
            "perturbations": dict(self.perturbations),
            "identity_hash": self.identity_hash,
        }


@dataclass(frozen=True)
class StudySpec:
    path: Path
    raw: dict[str, Any]
    name: str
    geometry_config: Path
    airfoil_database: Path
    variables: tuple[VariableSpec, ...]
    ofat_fractions: tuple[float, ...]
    pairwise_enabled: bool
    pairwise_top_k: int
    pairwise_fractions: tuple[float, ...]
    pairwise_max_cases: int
    lhs_enabled: bool
    lhs_samples: int
    lhs_seed: int
    source_sections: int
    extraction_cst_order: int
    extraction_chordwise_points: int
    minimum_source_spacing_fraction: float
    levels: tuple[MeshLevel, ...]
    reference_level: str
    mesh_common: dict[str, Any]
    metric_limits: tuple[MetricLimit, ...]
    require_limits_for_run: bool
    projection_enabled: bool
    projection_sample_nodes: int

    @property
    def variable_map(self) -> dict[str, VariableSpec]:
        return {variable.name: variable for variable in self.variables}

    @property
    def level_map(self) -> dict[str, MeshLevel]:
        return {level.name: level for level in self.levels}

    @property
    def baseline_values(self) -> dict[str, float]:
        return {variable.name: variable.baseline for variable in self.variables}

    @property
    def fingerprint(self) -> str:
        return _canonical_hash(self.raw)

    @property
    def reference_level_spec(self) -> MeshLevel:
        return self.level_map[self.reference_level]

    def unset_enabled_limits(self) -> list[str]:
        return [
            metric.path for metric in self.metric_limits if metric.enabled and metric.limit is None
        ]

    def sample_values(self, public_values: Mapping[str, float]) -> dict[str, float]:
        missing = set(self.variable_map) - set(public_values)
        extra = set(public_values) - set(self.variable_map)
        if missing or extra:
            raise ValueError(
                f"Study vector mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
            )
        return {
            variable.sample_field: variable.to_sample_value(public_values[variable.name])
            for variable in self.variables
        }

    def baseline_case(self, *, sequence_index: int = 0) -> StudyCase:
        return StudyCase(
            case_id="baseline",
            stage="baseline",
            public_values=self.baseline_values,
            perturbations={},
            sequence_index=sequence_index,
        )

    def ofat_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        cases: list[StudyCase] = []
        seen_vectors: set[str] = set()
        for variable in self.variables:
            for fraction in self.ofat_fractions:
                value = variable.value_at_fraction(fraction)
                if math.isclose(value, variable.baseline, rel_tol=0.0, abs_tol=1.0e-13):
                    continue
                values = self.baseline_values
                values[variable.name] = value
                vector_hash = _canonical_hash(values)
                if vector_hash in seen_vectors:
                    continue
                seen_vectors.add(vector_hash)
                cases.append(
                    StudyCase(
                        case_id=f"ofat__{variable.name}__{_fraction_token(fraction)}",
                        stage="ofat",
                        public_values=values,
                        perturbations={variable.name: float(fraction)},
                        sequence_index=sequence_start + len(cases),
                    )
                )
        return cases

    def pairwise_cases(
        self,
        ranked_variables: Sequence[str],
        *,
        sequence_start: int = 0,
    ) -> list[StudyCase]:
        if not self.pairwise_enabled:
            return []
        unknown = set(ranked_variables) - set(self.variable_map)
        if unknown:
            raise ValueError(f"Unknown ranked variables: {sorted(unknown)}")
        selected = list(dict.fromkeys(ranked_variables))[: self.pairwise_top_k]
        cases: list[StudyCase] = []
        for first_index, first in enumerate(selected):
            for second in selected[first_index + 1 :]:
                for first_fraction in self.pairwise_fractions:
                    for second_fraction in self.pairwise_fractions:
                        values = self.baseline_values
                        values[first] = self.variable_map[first].value_at_fraction(first_fraction)
                        values[second] = self.variable_map[second].value_at_fraction(
                            second_fraction
                        )
                        if math.isclose(
                            values[first],
                            self.variable_map[first].baseline,
                            rel_tol=0.0,
                            abs_tol=1.0e-13,
                        ) or math.isclose(
                            values[second],
                            self.variable_map[second].baseline,
                            rel_tol=0.0,
                            abs_tol=1.0e-13,
                        ):
                            continue
                        cases.append(
                            StudyCase(
                                case_id=(
                                    f"pair__{first}_{_fraction_token(first_fraction)}"
                                    f"__{second}_{_fraction_token(second_fraction)}"
                                ),
                                stage="pairwise",
                                public_values=values,
                                perturbations={
                                    first: float(first_fraction),
                                    second: float(second_fraction),
                                },
                                sequence_index=sequence_start + len(cases),
                            )
                        )
                        if len(cases) >= self.pairwise_max_cases:
                            return cases
        return cases

    def lhs_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        if not self.lhs_enabled:
            return []
        engine = qmc.LatinHypercube(d=len(self.variables), seed=self.lhs_seed)
        unit = engine.random(n=self.lhs_samples)
        cases: list[StudyCase] = []
        for row_index, row in enumerate(unit):
            values = {
                variable.name: (variable.low + float(row[column]) * (variable.high - variable.low))
                for column, variable in enumerate(self.variables)
            }
            perturbations = {
                variable.name: variable.normalized_fraction(values[variable.name])
                for column, variable in enumerate(self.variables)
            }
            cases.append(
                StudyCase(
                    case_id=f"lhs__{row_index:04d}",
                    stage="lhs",
                    public_values=values,
                    perturbations=perturbations,
                    sequence_index=sequence_start + row_index,
                )
            )
        return cases

    def initial_plan(self) -> dict[str, Any]:
        baseline = self.baseline_case(sequence_index=0)
        ofat = self.ofat_cases(sequence_start=1)
        lhs = self.lhs_cases(sequence_start=1 + len(ofat))
        return {
            "schema": SCHEMA_VERSION,
            "study": self.name,
            "study_fingerprint": self.fingerprint,
            "pairwise_deferred_until_ofat_ranking": self.pairwise_enabled,
            "counts": {
                "baseline": 1,
                "ofat": len(ofat),
                "lhs": len(lhs),
                "pairwise": None if self.pairwise_enabled else 0,
            },
            "cases": [
                baseline.to_dict(),
                *(case.to_dict() for case in ofat),
                *(case.to_dict() for case in lhs),
            ],
        }


def _fraction_token(fraction: float) -> str:
    sign = "m" if fraction < 0.0 else "p"
    return f"{sign}{abs(float(fraction)):0.3f}".replace(".", "")


def _parse_variable(name: str, value: object) -> VariableSpec:
    block = _mapping(value, f"variables.{name}")
    return VariableSpec(
        name=name,
        sample_field=_string(block.get("sample_field", name), f"variables.{name}.sample_field"),
        units=_string(block.get("units", "1"), f"variables.{name}.units"),
        baseline=_number(block.get("baseline"), f"variables.{name}.baseline"),
        low=_number(block.get("low"), f"variables.{name}.low"),
        high=_number(block.get("high"), f"variables.{name}.high"),
        sample_scale=_number(block.get("sample_scale", 1.0), f"variables.{name}.sample_scale"),
    )


def _parse_level(name: str, value: object, default_order: int) -> MeshLevel:
    block = _mapping(value, f"mesh.levels.{name}")
    return MeshLevel(
        name=name,
        order=_integer(block.get("order", default_order), f"mesh.levels.{name}.order"),
        points_per_block_side=_integer(
            block.get("points_per_block_side"),
            f"mesh.levels.{name}.points_per_block_side",
        ),
        spanwise_panels_per_section=_integer(
            block.get("spanwise_panels_per_section"),
            f"mesh.levels.{name}.spanwise_panels_per_section",
        ),
        cap_wrap_points=_integer(
            block.get("cap_wrap_points"), f"mesh.levels.{name}.cap_wrap_points"
        ),
        tip_radial_points=_integer(
            block.get("tip_radial_points"), f"mesh.levels.{name}.tip_radial_points"
        ),
    )


def _parse_metric(path: str, value: object) -> MetricLimit:
    block = _mapping(value, f"acceptance.metrics.{path}")
    raw_limit = block.get("limit")
    return MetricLimit(
        path=path,
        operator=_string(block.get("operator"), f"acceptance.metrics.{path}.operator"),
        limit=None if raw_limit is None else _number(raw_limit, f"acceptance.metrics.{path}.limit"),
        enabled=_boolean(block.get("enabled", True), f"acceptance.metrics.{path}.enabled"),
        description=str(block.get("description", "")).strip(),
    )


def load_study_spec(path: str | Path) -> StudySpec:
    """Load and validate a surface-mesh study YAML file."""

    config_path = Path(path).expanduser().resolve()
    raw_loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw = _mapping(raw_loaded, "study config")
    schema = _string(raw.get("schema"), "schema")
    if schema != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema {schema!r}; expected {SCHEMA_VERSION!r}")

    geometry = _mapping(raw.get("geometry"), "geometry")
    extraction = _mapping(geometry.get("extraction"), "geometry.extraction")
    variables_raw = _mapping(raw.get("variables"), "variables")
    variables = tuple(_parse_variable(name, value) for name, value in variables_raw.items())
    sample_fields = [variable.sample_field for variable in variables]
    if len(set(sample_fields)) != len(sample_fields):
        raise ValueError("variables contain duplicate sample_field mappings")
    if set(sample_fields) != set(EXPECTED_SAMPLE_FIELDS):
        raise ValueError(
            "variables must map exactly the 17 active BWB fields; "
            f"missing={sorted(set(EXPECTED_SAMPLE_FIELDS) - set(sample_fields))}, "
            f"extra={sorted(set(sample_fields) - set(EXPECTED_SAMPLE_FIELDS))}"
        )

    ofat = _mapping(raw.get("ofat"), "ofat")
    ofat_fractions = tuple(
        _number(value, f"ofat.fractions[{index}]")
        for index, value in enumerate(_sequence(ofat.get("fractions"), "ofat.fractions"))
    )
    if not ofat_fractions or any(not -1.0 <= value <= 1.0 for value in ofat_fractions):
        raise ValueError("ofat.fractions must be a non-empty list within [-1, 1]")
    if any(value == 0.0 for value in ofat_fractions):
        raise ValueError("ofat.fractions must omit zero; baseline is a separate case")

    interactions = _mapping(raw.get("interactions"), "interactions")
    pairwise = _mapping(interactions.get("pairwise"), "interactions.pairwise")
    pairwise_fractions = tuple(
        _number(value, f"interactions.pairwise.fractions[{index}]")
        for index, value in enumerate(
            _sequence(pairwise.get("fractions"), "interactions.pairwise.fractions")
        )
    )
    if any(not -1.0 <= value <= 1.0 for value in pairwise_fractions):
        raise ValueError("interactions.pairwise.fractions must lie within [-1, 1]")
    if not pairwise_fractions:
        raise ValueError("interactions.pairwise.fractions must not be empty")
    lhs = _mapping(interactions.get("lhs"), "interactions.lhs")

    mesh = _mapping(raw.get("mesh"), "mesh")
    levels_raw = _mapping(mesh.get("levels"), "mesh.levels")
    levels = tuple(
        sorted(
            (
                _parse_level(name, value, index)
                for index, (name, value) in enumerate(levels_raw.items(), start=1)
            ),
            key=lambda item: item.order,
        )
    )
    if len(levels) < 3:
        raise ValueError("mesh.levels must define at least three refinement levels")
    if len({level.name for level in levels}) != len(levels):
        raise ValueError("mesh.level names must be unique")
    if len({level.order for level in levels}) != len(levels):
        raise ValueError("mesh.level order values must be unique")
    reference_level = _string(mesh.get("reference_level"), "mesh.reference_level")
    if reference_level not in {level.name for level in levels}:
        raise ValueError(f"mesh.reference_level {reference_level!r} is not defined")

    acceptance = _mapping(raw.get("acceptance"), "acceptance")
    metrics_raw = _mapping(acceptance.get("metrics"), "acceptance.metrics")
    metric_limits = tuple(_parse_metric(path, value) for path, value in metrics_raw.items())
    if not metric_limits:
        raise ValueError("acceptance.metrics must not be empty")

    projection = _mapping(raw.get("projection_diagnostic", {}), "projection_diagnostic")
    spec = StudySpec(
        path=config_path,
        raw=raw,
        name=_string(raw.get("name"), "name"),
        geometry_config=_resolve_path(
            geometry.get("definition_config"),
            config_path=config_path,
            label="geometry.definition_config",
        ),
        airfoil_database=_resolve_path(
            geometry.get("airfoil_database", "data/airfoil_database"),
            config_path=config_path,
            label="geometry.airfoil_database",
        ),
        variables=variables,
        ofat_fractions=ofat_fractions,
        pairwise_enabled=_boolean(pairwise.get("enabled", True), "interactions.pairwise.enabled"),
        pairwise_top_k=_integer(pairwise.get("top_k", 6), "interactions.pairwise.top_k"),
        pairwise_fractions=pairwise_fractions,
        pairwise_max_cases=_integer(
            pairwise.get("max_cases", 60), "interactions.pairwise.max_cases"
        ),
        lhs_enabled=_boolean(lhs.get("enabled", True), "interactions.lhs.enabled"),
        lhs_samples=_integer(lhs.get("samples", 64), "interactions.lhs.samples"),
        lhs_seed=_integer(lhs.get("seed", 20260724), "interactions.lhs.seed"),
        source_sections=_integer(
            extraction.get("source_sections", 14), "geometry.extraction.source_sections"
        ),
        extraction_cst_order=_integer(
            extraction.get("cst_order", 8), "geometry.extraction.cst_order"
        ),
        extraction_chordwise_points=_integer(
            extraction.get("chordwise_points", 301),
            "geometry.extraction.chordwise_points",
        ),
        minimum_source_spacing_fraction=_number(
            extraction.get("minimum_spacing_fraction", 1.0e-4),
            "geometry.extraction.minimum_spacing_fraction",
        ),
        levels=levels,
        reference_level=reference_level,
        mesh_common=_mapping(mesh.get("common"), "mesh.common"),
        metric_limits=metric_limits,
        require_limits_for_run=_boolean(
            acceptance.get("require_limits_for_run", True),
            "acceptance.require_limits_for_run",
        ),
        projection_enabled=_boolean(
            projection.get("enabled", True), "projection_diagnostic.enabled"
        ),
        projection_sample_nodes=_integer(
            projection.get("sample_nodes", 500), "projection_diagnostic.sample_nodes"
        ),
    )
    if spec.source_sections < 4:
        raise ValueError("geometry.extraction.source_sections must be at least 4")
    if spec.extraction_cst_order < 2:
        raise ValueError("geometry.extraction.cst_order must be at least 2")
    if spec.extraction_chordwise_points < max(21, spec.extraction_cst_order + 3):
        raise ValueError("geometry.extraction.chordwise_points is too small")
    if not 0.0 < spec.minimum_source_spacing_fraction < 1.0:
        raise ValueError("geometry.extraction.minimum_spacing_fraction must lie in (0, 1)")
    if spec.pairwise_top_k < 2:
        raise ValueError("interactions.pairwise.top_k must be at least 2")
    if spec.pairwise_max_cases < 1:
        raise ValueError("interactions.pairwise.max_cases must be positive")
    if spec.lhs_samples < 1:
        raise ValueError("interactions.lhs.samples must be positive")
    if spec.projection_sample_nodes < 10:
        raise ValueError("projection_diagnostic.sample_nodes must be at least 10")
    return spec
