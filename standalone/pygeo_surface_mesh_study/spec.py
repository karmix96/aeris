"""Version-2 schema and deterministic design for the pyGeo mesh-law study.

The design separates independent generator controls, fixed fields required by
the canonical geometry contract, and realised descriptors recorded at runtime.
It combines dense one-factor curves, every two-factor corner, scrambled-Sobol
global training, and an independent IID uniform validation design by default.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml
from scipy.stats import qmc

SCHEMA_VERSION = "aeris.pygeo_surface_mesh_study.v2"
SAMPLE_FIELDS = (
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
    "elevon_start_frac",
    "elevon_end_frac",
    "elevon_hinge_frac",
)
VALID_OPERATORS = {"<=", ">="}
VALID_STAGES = {
    "baseline",
    "ofat",
    "pairwise",
    "global_train",
    "validation",
    "mesh_control_train",
    "mesh_control_validation",
}

MESH_CONTROL_PARAMETERS = {
    "points_per_block_side",
    "spanwise_panels_per_section",
    "cap_wrap_points",
    "tip_radial_points",
}


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


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _resolve_path(value: object, config_path: Path, label: str) -> Path:
    raw = Path(_string(value, label)).expanduser()
    if raw.is_absolute():
        return raw.resolve()
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
    return next(
        (candidate.resolve() for candidate in candidates if candidate.exists()),
        candidates[0].resolve(),
    )


@dataclass(frozen=True)
class VariableSpec:
    """One independent public factor and its Aeris sample-field mapping."""

    name: str
    sample_field: str
    units: str
    baseline: float
    low: float
    high: float
    sample_scale: float = 1.0
    description: str = ""

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(value)
            for value in (self.baseline, self.low, self.high, self.sample_scale)
        ):
            raise ValueError(f"{self.name}: values must be finite")
        if not self.low < self.baseline < self.high:
            raise ValueError(
                f"{self.name}: inferential baseline must be strictly interior; "
                f"got {self.low} < {self.baseline} < {self.high}"
            )
        if self.sample_scale == 0.0:
            raise ValueError(f"{self.name}: sample_scale must be non-zero")

    def value_at_fraction(self, fraction: float) -> float:
        fraction = float(fraction)
        if not -1.0 <= fraction <= 1.0:
            raise ValueError(f"{self.name}: fraction must be in [-1, 1]")
        endpoint = self.low if fraction < 0.0 else self.high
        return self.baseline + abs(fraction) * (endpoint - self.baseline)

    def normalized_fraction(self, value: float) -> float:
        value = float(value)
        if math.isclose(value, self.baseline, abs_tol=1.0e-14, rel_tol=0.0):
            return 0.0
        endpoint = self.low if value < self.baseline else self.high
        return (value - self.baseline) / abs(endpoint - self.baseline)

    def to_sample_value(self, value: float) -> float:
        return self.sample_scale * float(value)


@dataclass(frozen=True)
class MeshLevel:
    name: str
    order: int
    points_per_block_side: int
    spanwise_panels_per_section: int
    cap_wrap_points: int
    tip_radial_points: int

    def __post_init__(self) -> None:
        if self.order < 0 or self.points_per_block_side < 9:
            raise ValueError(f"{self.name}: invalid order/chordwise resolution")
        if self.spanwise_panels_per_section < 1 or self.cap_wrap_points < 5:
            raise ValueError(f"{self.name}: invalid span/wrap resolution")
        if self.tip_radial_points < 2:
            raise ValueError(f"{self.name}: tip_radial_points must be at least 2")


@dataclass(frozen=True)
class MeshControlSpec:
    """One independently varied numerical mesh-control knob."""

    name: str
    parameter: str
    units: str
    baseline: float
    low: float
    high: float
    integer: bool = False
    odd: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.baseline, self.low, self.high)):
            raise ValueError(f"{self.name}: values must be finite")
        if not self.low < self.baseline < self.high:
            raise ValueError(
                f"{self.name}: baseline must be strictly interior; "
                f"got {self.low} < {self.baseline} < {self.high}"
            )
        if self.odd and not self.integer:
            raise ValueError(f"{self.name}: odd mesh controls must be integer controls")
        if not self.parameter.strip():
            raise ValueError(f"{self.name}: parameter must be non-empty")

    def canonical_value(self, value: float) -> float:
        value = min(self.high, max(self.low, float(value)))
        if not self.integer:
            return value
        rounded = int(round(value))
        low = int(math.ceil(self.low))
        high = int(math.floor(self.high))
        rounded = min(high, max(low, rounded))
        if self.odd and rounded % 2 == 0:
            lower = rounded - 1
            upper = rounded + 1
            candidates = [candidate for candidate in (lower, upper) if low <= candidate <= high]
            if not candidates:
                raise ValueError(f"{self.name}: no odd integer value lies inside the bounds")
            rounded = min(candidates, key=lambda candidate: abs(candidate - value))
        return float(rounded)

    def value_at_unit(self, unit: float) -> float:
        unit = min(1.0, max(0.0, float(unit)))
        return self.canonical_value(self.low + unit * (self.high - self.low))

    def normalized_fraction(self, value: float) -> float:
        value = self.canonical_value(value)
        if math.isclose(value, self.baseline, abs_tol=1.0e-14, rel_tol=0.0):
            return 0.0
        endpoint = self.low if value < self.baseline else self.high
        return (value - self.baseline) / abs(endpoint - self.baseline)

    def to_parameter_value(self, value: float) -> int | float:
        value = self.canonical_value(value)
        return int(value) if self.integer else value


@dataclass(frozen=True)
class MetricLimit:
    path: str
    operator: str
    limit: float | None
    enabled: bool
    description: str = ""

    def __post_init__(self) -> None:
        if self.operator not in VALID_OPERATORS:
            raise ValueError(f"{self.path}: invalid operator {self.operator!r}")
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
    mesh_values: dict[str, float] | None = None
    mesh_perturbations: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.stage not in VALID_STAGES:
            raise ValueError(f"Invalid stage {self.stage!r}")

    @property
    def identity_hash(self) -> str:
        return _hash(
            {
                "case_id": self.case_id,
                "stage": self.stage,
                "public_values": self.public_values,
                "perturbations": self.perturbations,
                "mesh_values": self.mesh_values or {},
                "mesh_perturbations": self.mesh_perturbations or {},
            }
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "case_id": self.case_id,
            "stage": self.stage,
            "sequence_index": self.sequence_index,
            "public_values": dict(self.public_values),
            "perturbations": dict(self.perturbations),
            "identity_hash": self.identity_hash,
        }
        if self.mesh_values is not None:
            payload["mesh_values"] = dict(self.mesh_values)
            payload["mesh_perturbations"] = dict(self.mesh_perturbations or {})
        return payload


@dataclass(frozen=True)
class StudySpec:
    path: Path
    raw: dict[str, Any]
    name: str
    geometry_config: Path
    airfoil_database: Path
    fixed_sample_values: dict[str, float]
    variables: tuple[VariableSpec, ...]
    ofat_fractions: tuple[float, ...]
    pairwise_enabled: bool
    pairwise_fractions: tuple[float, ...]
    pairwise_max_cases: int
    global_method: str
    global_train_samples: int
    global_train_seed: int
    validation_method: str
    validation_samples: int
    validation_seed: int
    source_sections: int
    extraction_cst_order: int
    extraction_chordwise_points: int
    mesh_control_enabled: bool
    mesh_control_variables: tuple[MeshControlSpec, ...]
    mesh_control_train_method: str
    mesh_control_train_samples: int
    mesh_control_train_seed: int
    mesh_control_validation_method: str
    mesh_control_validation_samples: int
    mesh_control_validation_seed: int
    minimum_source_spacing_fraction: float
    levels: tuple[MeshLevel, ...]
    reference_level: str
    complete_ladder: bool
    mesh_common: dict[str, Any]
    metric_limits: tuple[MetricLimit, ...]
    require_limits_for_run: bool
    projection_enabled: bool
    projection_sample_nodes: int
    analysis_config: dict[str, Any]

    @property
    def mesh_control_variable_map(self) -> dict[str, MeshControlSpec]:
        return {variable.name: variable for variable in self.mesh_control_variables}

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
        return _hash(self.raw)

    @property
    def reference_level_spec(self) -> MeshLevel:
        return self.level_map[self.reference_level]

    def unset_enabled_limits(self) -> list[str]:
        return [
            metric.path for metric in self.metric_limits if metric.enabled and metric.limit is None
        ]

    def sample_values(self, public_values: Mapping[str, float]) -> dict[str, float]:
        if set(public_values) != set(self.variable_map):
            raise ValueError("Public study vector does not match configured variables")
        values = dict(self.fixed_sample_values)
        values.update(
            {
                variable.sample_field: variable.to_sample_value(public_values[variable.name])
                for variable in self.variables
            }
        )
        if set(values) != set(SAMPLE_FIELDS):
            raise ValueError("Complete BWB sample vector has missing or extra fields")
        return values

    def baseline_case(self, *, sequence_index: int = 0) -> StudyCase:
        return StudyCase("baseline", "baseline", self.baseline_values, {}, sequence_index)

    def ofat_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        cases: list[StudyCase] = []
        for variable in self.variables:
            for fraction in self.ofat_fractions:
                values = self.baseline_values
                values[variable.name] = variable.value_at_fraction(fraction)
                cases.append(
                    StudyCase(
                        f"ofat__{variable.name}__{_fraction_token(fraction)}",
                        "ofat",
                        values,
                        {variable.name: fraction},
                        sequence_start + len(cases),
                    )
                )
        return cases

    def pairwise_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        if not self.pairwise_enabled:
            return []
        names = [variable.name for variable in self.variables]
        required = math.comb(len(names), 2) * len(self.pairwise_fractions) ** 2
        if self.pairwise_max_cases < required:
            raise ValueError(
                f"pairwise.max_cases={self.pairwise_max_cases} truncates "
                f"the complete {required}-case pair design"
            )
        cases: list[StudyCase] = []
        for first_index, first in enumerate(names):
            for second in names[first_index + 1 :]:
                for first_fraction in self.pairwise_fractions:
                    for second_fraction in self.pairwise_fractions:
                        values = self.baseline_values
                        values[first] = self.variable_map[first].value_at_fraction(first_fraction)
                        values[second] = self.variable_map[second].value_at_fraction(
                            second_fraction
                        )
                        cases.append(
                            StudyCase(
                                f"pair__{first}_{_fraction_token(first_fraction)}__"
                                f"{second}_{_fraction_token(second_fraction)}",
                                "pairwise",
                                values,
                                {first: first_fraction, second: second_fraction},
                                sequence_start + len(cases),
                            )
                        )
        return cases

    def _unit_design(self, samples: int, seed: int, method: str, dimensions: int) -> np.ndarray:
        if method == "sobol":
            power = int(round(math.log2(samples)))
            if 2**power != samples:
                raise ValueError("Sobol sample counts must be powers of two")
            return qmc.Sobol(d=dimensions, scramble=True, seed=seed).random_base2(power)
        if method == "lhs":
            return qmc.LatinHypercube(d=dimensions, seed=seed).random(samples)
        return np.random.default_rng(seed).random((samples, dimensions))

    def _geometry_values_from_unit_row(
        self, row: np.ndarray
    ) -> tuple[dict[str, float], dict[str, float]]:
        values = {
            variable.name: variable.low + float(row[column]) * (variable.high - variable.low)
            for column, variable in enumerate(self.variables)
        }
        perturbations = {
            variable.name: variable.normalized_fraction(values[variable.name])
            for variable in self.variables
        }
        return values, perturbations

    def _space_filling_cases(
        self,
        stage: str,
        samples: int,
        seed: int,
        method: str,
        sequence_start: int,
    ) -> list[StudyCase]:
        cases: list[StudyCase] = []
        for row_index, row in enumerate(
            self._unit_design(samples, seed, method, len(self.variables))
        ):
            values, perturbations = self._geometry_values_from_unit_row(row)
            cases.append(
                StudyCase(
                    f"{stage}__{row_index:04d}",
                    stage,
                    values,
                    perturbations,
                    sequence_start + row_index,
                )
            )
        return cases

    def global_train_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        return self._space_filling_cases(
            "global_train",
            self.global_train_samples,
            self.global_train_seed,
            self.global_method,
            sequence_start,
        )

    def validation_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        return self._space_filling_cases(
            "validation",
            self.validation_samples,
            self.validation_seed,
            self.validation_method,
            sequence_start,
        )

    def geometry_law_cases(self) -> list[StudyCase]:
        baseline = self.baseline_case()
        ofat = self.ofat_cases(sequence_start=1)
        pairwise = self.pairwise_cases(sequence_start=1 + len(ofat))
        train = self.global_train_cases(sequence_start=1 + len(ofat) + len(pairwise))
        validation = self.validation_cases(
            sequence_start=1 + len(ofat) + len(pairwise) + len(train)
        )
        return [baseline, *ofat, *pairwise, *train, *validation]

    def _mesh_control_cases(
        self,
        stage: str,
        samples: int,
        seed: int,
        method: str,
        sequence_start: int,
    ) -> list[StudyCase]:
        if not self.mesh_control_enabled:
            return []
        dimensions = len(self.variables) + len(self.mesh_control_variables)
        cases: list[StudyCase] = []
        for row_index, row in enumerate(self._unit_design(samples, seed, method, dimensions)):
            geometry_row = row[: len(self.variables)]
            mesh_row = row[len(self.variables) :]
            values, perturbations = self._geometry_values_from_unit_row(geometry_row)
            mesh_values = {
                variable.name: variable.value_at_unit(float(mesh_row[column]))
                for column, variable in enumerate(self.mesh_control_variables)
            }
            mesh_perturbations = {
                variable.name: variable.normalized_fraction(mesh_values[variable.name])
                for variable in self.mesh_control_variables
            }
            cases.append(
                StudyCase(
                    f"{stage}__{row_index:04d}",
                    stage,
                    values,
                    perturbations,
                    sequence_start + row_index,
                    mesh_values=mesh_values,
                    mesh_perturbations=mesh_perturbations,
                )
            )
        return cases

    def mesh_control_train_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        return self._mesh_control_cases(
            "mesh_control_train",
            self.mesh_control_train_samples,
            self.mesh_control_train_seed,
            self.mesh_control_train_method,
            sequence_start,
        )

    def mesh_control_validation_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        return self._mesh_control_cases(
            "mesh_control_validation",
            self.mesh_control_validation_samples,
            self.mesh_control_validation_seed,
            self.mesh_control_validation_method,
            sequence_start,
        )

    def mesh_control_cases(self, *, sequence_start: int = 0) -> list[StudyCase]:
        train = self.mesh_control_train_cases(sequence_start=sequence_start)
        validation = self.mesh_control_validation_cases(sequence_start=sequence_start + len(train))
        return [*train, *validation]

    def all_cases(self) -> list[StudyCase]:
        geometry_cases = self.geometry_law_cases()
        mesh_cases = self.mesh_control_cases(sequence_start=len(geometry_cases))
        return [*geometry_cases, *mesh_cases]

    def initial_plan(self) -> dict[str, Any]:
        geometry_cases = self.geometry_law_cases()
        mesh_cases = self.mesh_control_cases(sequence_start=len(geometry_cases))
        cases = [*geometry_cases, *mesh_cases]
        counts = {stage: 0 for stage in sorted(VALID_STAGES)}
        for case in cases:
            counts[case.stage] += 1
        counts["geometry_law_geometries"] = len(geometry_cases)
        counts["mesh_control_cases"] = len(mesh_cases)
        counts["total_cases"] = len(cases)
        counts["planned_mesh_builds"] = len(geometry_cases) * len(self.levels) + len(mesh_cases)
        return {
            "schema": SCHEMA_VERSION,
            "study": self.name,
            "study_fingerprint": self.fingerprint,
            "global_design_method": self.global_method,
            "counts": counts,
            "validation_design_method": self.validation_method,
            "mesh_control_enabled": self.mesh_control_enabled,
            "mesh_control_train_design_method": self.mesh_control_train_method,
            "mesh_control_validation_design_method": self.mesh_control_validation_method,
            "mesh_control_variables": [
                {
                    "name": variable.name,
                    "parameter": variable.parameter,
                    "baseline": variable.baseline,
                    "low": variable.low,
                    "high": variable.high,
                    "integer": variable.integer,
                    "odd": variable.odd,
                }
                for variable in self.mesh_control_variables
            ],
            "cases": [case.to_dict() for case in cases],
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
        description=str(block.get("description", "")).strip(),
    )


def _parse_level(name: str, value: object, order: int) -> MeshLevel:
    block = _mapping(value, f"mesh.levels.{name}")
    return MeshLevel(
        name,
        _integer(block.get("order", order), f"mesh.levels.{name}.order"),
        _integer(
            block.get("points_per_block_side"),
            f"mesh.levels.{name}.points_per_block_side",
        ),
        _integer(
            block.get("spanwise_panels_per_section"),
            f"mesh.levels.{name}.spanwise_panels_per_section",
        ),
        _integer(
            block.get("cap_wrap_points"),
            f"mesh.levels.{name}.cap_wrap_points",
        ),
        _integer(
            block.get("tip_radial_points"),
            f"mesh.levels.{name}.tip_radial_points",
        ),
    )


def _parse_mesh_control(name: str, value: object) -> MeshControlSpec:
    block = _mapping(value, f"mesh_control.variables.{name}")
    return MeshControlSpec(
        name=name,
        parameter=_string(
            block.get("parameter", name),
            f"mesh_control.variables.{name}.parameter",
        ),
        units=_string(block.get("units", "1"), f"mesh_control.variables.{name}.units"),
        baseline=_number(block.get("baseline"), f"mesh_control.variables.{name}.baseline"),
        low=_number(block.get("low"), f"mesh_control.variables.{name}.low"),
        high=_number(block.get("high"), f"mesh_control.variables.{name}.high"),
        integer=_boolean(block.get("integer", False), f"mesh_control.variables.{name}.integer"),
        odd=_boolean(block.get("odd", False), f"mesh_control.variables.{name}.odd"),
        description=str(block.get("description", "")).strip(),
    )


def _parse_metric(path: str, value: object) -> MetricLimit:
    block = _mapping(value, f"acceptance.metrics.{path}")
    raw_limit = block.get("limit")
    return MetricLimit(
        path,
        _string(
            block.get("operator"),
            f"acceptance.metrics.{path}.operator",
        ),
        None if raw_limit is None else _number(raw_limit, path),
        _boolean(
            block.get("enabled", True),
            f"acceptance.metrics.{path}.enabled",
        ),
        str(block.get("description", "")).strip(),
    )


def load_study_spec(path: str | Path) -> StudySpec:
    config_path = Path(path).expanduser().resolve()
    raw = _mapping(
        yaml.safe_load(config_path.read_text(encoding="utf-8")),
        "study config",
    )
    schema = _string(raw.get("schema"), "schema")
    if schema != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema {schema!r}; expected {SCHEMA_VERSION!r}")

    geometry = _mapping(raw.get("geometry"), "geometry")
    extraction = _mapping(geometry.get("extraction"), "geometry.extraction")
    fixed_raw = _mapping(
        geometry.get("fixed_sample_values"),
        "geometry.fixed_sample_values",
    )
    fixed = {
        str(key): _number(value, f"geometry.fixed_sample_values.{key}")
        for key, value in fixed_raw.items()
    }
    variables_raw = _mapping(raw.get("variables"), "variables")
    variables = tuple(_parse_variable(name, value) for name, value in variables_raw.items())
    mapped = [variable.sample_field for variable in variables]
    if len(mapped) != len(set(mapped)) or set(mapped) & set(fixed):
        raise ValueError("Sample fields must be unique and either varied or fixed")
    covered = set(mapped) | set(fixed)
    if covered != set(SAMPLE_FIELDS):
        missing = set(SAMPLE_FIELDS) - covered
        extra = covered - set(SAMPLE_FIELDS)
        raise ValueError(f"Incomplete BWB sample: missing={sorted(missing)}, extra={sorted(extra)}")

    design = _mapping(raw.get("design"), "design")
    ofat = _mapping(design.get("ofat"), "design.ofat")
    fractions = tuple(
        _number(value, "design.ofat.fractions")
        for value in _sequence(ofat.get("fractions"), "design.ofat.fractions")
    )
    if not fractions or any(value == 0.0 or not -1.0 <= value <= 1.0 for value in fractions):
        raise ValueError("OFAT fractions must be non-zero and in [-1, 1]")
    pair = _mapping(design.get("pairwise"), "design.pairwise")
    pair_fractions = tuple(
        _number(value, "design.pairwise.fractions")
        for value in _sequence(pair.get("fractions"), "design.pairwise.fractions")
    )
    if not pair_fractions or any(
        value == 0.0 or not -1.0 <= value <= 1.0 for value in pair_fractions
    ):
        raise ValueError("Pair fractions must be non-zero and in [-1, 1]")
    global_block = _mapping(design.get("global"), "design.global")
    validation = _mapping(design.get("validation"), "design.validation")
    method = _string(global_block.get("method", "sobol"), "design.global.method").lower()
    if method not in {"sobol", "lhs"}:
        raise ValueError("Global method must be sobol or lhs")

    mesh = _mapping(raw.get("mesh"), "mesh")
    validation_method = _string(
        validation.get("method", "iid_uniform"),
        "design.validation.method",
    ).lower()
    if validation_method not in {"iid_uniform", "sobol", "lhs"}:
        raise ValueError("Validation method must be iid_uniform, sobol, or lhs")

    mesh_control = _mapping(raw.get("mesh_control", {}), "mesh_control")
    mesh_control_enabled = _boolean(
        mesh_control.get("enabled", False),
        "mesh_control.enabled",
    )
    mesh_control_train = _mapping(mesh_control.get("train", {}), "mesh_control.train")
    mesh_control_validation = _mapping(
        mesh_control.get("validation", {}),
        "mesh_control.validation",
    )
    mesh_control_variables = tuple(
        _parse_mesh_control(name, value)
        for name, value in _mapping(
            mesh_control.get("variables", {}),
            "mesh_control.variables",
        ).items()
    )
    mesh_control_train_method = _string(
        mesh_control_train.get("method", "sobol"),
        "mesh_control.train.method",
    ).lower()
    mesh_control_validation_method = _string(
        mesh_control_validation.get("method", "iid_uniform"),
        "mesh_control.validation.method",
    ).lower()
    if mesh_control_train_method not in {"sobol", "lhs", "iid_uniform"}:
        raise ValueError("Mesh-control train method must be sobol, lhs, or iid_uniform")
    if mesh_control_validation_method not in {"sobol", "lhs", "iid_uniform"}:
        raise ValueError("Mesh-control validation method must be sobol, lhs, or iid_uniform")

    levels_raw = _mapping(mesh.get("levels"), "mesh.levels")
    levels = tuple(
        sorted(
            (
                _parse_level(name, value, index)
                for index, (name, value) in enumerate(levels_raw.items(), start=1)
            ),
            key=lambda level: level.order,
        )
    )
    reference = _string(mesh.get("reference_level"), "mesh.reference_level")
    if len(levels) < 3 or reference not in {level.name for level in levels}:
        raise ValueError("At least three levels and a valid reference level are required")
    acceptance = _mapping(raw.get("acceptance"), "acceptance")
    metrics = tuple(
        _parse_metric(path, value)
        for path, value in _mapping(acceptance.get("metrics"), "acceptance.metrics").items()
    )
    projection = _mapping(
        raw.get("projection_diagnostic", {}),
        "projection_diagnostic",
    )

    spec = StudySpec(
        path=config_path,
        raw=raw,
        name=_string(raw.get("name"), "name"),
        geometry_config=_resolve_path(
            geometry.get("definition_config"),
            config_path,
            "geometry.definition_config",
        ),
        airfoil_database=_resolve_path(
            geometry.get("airfoil_database", "data/airfoil_database"),
            config_path,
            "geometry.airfoil_database",
        ),
        fixed_sample_values=fixed,
        variables=variables,
        ofat_fractions=fractions,
        pairwise_enabled=_boolean(pair.get("enabled", True), "design.pairwise.enabled"),
        pairwise_fractions=pair_fractions,
        pairwise_max_cases=_integer(pair.get("max_cases"), "design.pairwise.max_cases"),
        global_method=method,
        global_train_samples=_integer(global_block.get("samples"), "design.global.samples"),
        global_train_seed=_integer(global_block.get("seed"), "design.global.seed"),
        validation_samples=_integer(validation.get("samples"), "design.validation.samples"),
        validation_seed=_integer(validation.get("seed"), "design.validation.seed"),
        validation_method=validation_method,
        mesh_control_enabled=mesh_control_enabled,
        mesh_control_variables=mesh_control_variables,
        mesh_control_train_method=mesh_control_train_method,
        mesh_control_train_samples=_integer(
            mesh_control_train.get("samples", 0),
            "mesh_control.train.samples",
        ),
        mesh_control_train_seed=_integer(
            mesh_control_train.get("seed", 20260726),
            "mesh_control.train.seed",
        ),
        mesh_control_validation_method=mesh_control_validation_method,
        mesh_control_validation_samples=_integer(
            mesh_control_validation.get("samples", 0),
            "mesh_control.validation.samples",
        ),
        mesh_control_validation_seed=_integer(
            mesh_control_validation.get("seed", 20260727),
            "mesh_control.validation.seed",
        ),
        source_sections=_integer(
            extraction.get("source_sections", 14),
            "geometry.extraction.source_sections",
        ),
        extraction_cst_order=_integer(
            extraction.get("cst_order", 8),
            "geometry.extraction.cst_order",
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
        reference_level=reference,
        complete_ladder=_boolean(mesh.get("complete_ladder", True), "mesh.complete_ladder"),
        mesh_common=_mapping(mesh.get("common"), "mesh.common"),
        metric_limits=metrics,
        require_limits_for_run=_boolean(
            acceptance.get("require_limits_for_run", True),
            "acceptance.require_limits_for_run",
        ),
        projection_enabled=_boolean(
            projection.get("enabled", True),
            "projection_diagnostic.enabled",
        ),
        projection_sample_nodes=_integer(
            projection.get("sample_nodes", 500),
            "projection_diagnostic.sample_nodes",
        ),
        analysis_config=_mapping(raw.get("analysis"), "analysis"),
    )
    if spec.global_train_seed == spec.validation_seed:
        raise ValueError("Training and validation seeds must differ")
    if spec.mesh_control_enabled:
        if not spec.mesh_control_variables:
            raise ValueError("mesh_control.enabled requires at least one mesh-control variable")
        parameters = [variable.parameter for variable in spec.mesh_control_variables]
        if len(parameters) != len(set(parameters)):
            raise ValueError("mesh_control variables must map to unique mesher parameters")
        unsupported = sorted(set(parameters) - MESH_CONTROL_PARAMETERS)
        if unsupported:
            raise ValueError(
                "Unsupported mesh-control parameter(s) for this registered DOE: "
                f"{unsupported}. Supported: {sorted(MESH_CONTROL_PARAMETERS)}"
            )
        if spec.mesh_control_train_samples < 1 or spec.mesh_control_validation_samples < 1:
            raise ValueError("mesh-control train and validation samples must be positive")
        seeds = {
            spec.global_train_seed,
            spec.validation_seed,
            spec.mesh_control_train_seed,
            spec.mesh_control_validation_seed,
        }
        if len(seeds) != 4:
            raise ValueError("Geometry and mesh-control train/validation seeds must differ")
    elif spec.mesh_control_variables:
        raise ValueError("mesh_control.variables must be empty when mesh_control.enabled is false")
    if spec.source_sections < 4 or spec.extraction_cst_order < 2:
        raise ValueError("Invalid pyGeo extraction resolution")
    if spec.extraction_chordwise_points < max(21, spec.extraction_cst_order + 3):
        raise ValueError("geometry.extraction.chordwise_points is too small")
    if not 0.0 < spec.minimum_source_spacing_fraction < 1.0:
        raise ValueError("minimum source spacing fraction must lie in (0, 1)")
    if spec.projection_sample_nodes < 10:
        raise ValueError("projection sample must contain at least 10 nodes")
    spec.initial_plan()
    return spec
