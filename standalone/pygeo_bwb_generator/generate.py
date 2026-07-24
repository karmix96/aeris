"""Config-driven standalone pyGeo generator for the Aeris BWB definition.

Run from the repository root:

    .venv/bin/python -m standalone.pygeo_bwb_generator.generate \
        --config standalone/pygeo_bwb_generator/config.yaml

No AeroSandbox geometry object is constructed. The exact Aeris
``generate_bwb_planform_from_sample`` and
``build_section_geometry_from_sample`` functions define the BWB; their
result is lofted by pyGeo and exported with reproducible DoE metadata.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

# Support both ``python -m ...generate`` and direct script execution from any
# working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from scipy.stats import qmc

from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    BWBGeneratorConfig,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.planform import (
    PlanformResult,
    generate_bwb_planform_from_sample,
)
from aeris.generators.bwb_segmented_v1.sections import (
    SectionGeometryResult,
    build_section_geometry_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (
    validate_bwb_generator_config,
)
from standalone.pygeo_avl_study.geometry_bridge import (
    ExtractedSection,
    PyGeoBuild,
    StationDefinition,
    build_pygeo,
    extract_sections,
    realised_reference_metrics,
    sample_main_surfaces,
    stations_from_records,
)
from standalone.pygeo_bwb_generator import SCHEMA_VERSION
from standalone.pygeo_bwb_generator.physical_cad import (
    build_physical_cad,
    export_physical_cad,
    physical_state_id,
    resolve_physical_cad_spec,
)

DIRECT_VARIABLES = (
    "c1_m",
    "c2_m",
    "c3_m",
    "c4_m",
    "b1_m",
    "b2_m",
    "b3_m",
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
AIRFOIL_STATIONS = ("b0", "b1", "b2", "b3")


@dataclass(frozen=True)
class Range:
    minimum: float
    maximum: float

    @property
    def varied(self) -> bool:
        return self.maximum > self.minimum

    def from_unit(self, value: float) -> float:
        return self.minimum + float(value) * (self.maximum - self.minimum)


@dataclass(frozen=True)
class GeneratorConfig:
    path: Path
    raw: dict[str, Any]
    name: str
    definition_path: Path
    definition: BWBGeneratorConfig
    airfoil_database: Path
    fixed_airfoils: dict[str, str]
    method: str
    seed: int
    n_samples: int
    ranges: dict[str, Range]
    geometry: dict[str, Any]
    outputs: dict[str, Any]
    output_root: Path


@dataclass(frozen=True)
class BuiltCase:
    case_index: int
    geometry_id: str
    direct_variables: dict[str, float]
    sample: BWBDesignSample
    planform: PlanformResult
    sections: SectionGeometryResult
    stations: tuple[StationDefinition, ...]
    pygeo: PyGeoBuild
    extracted: tuple[ExtractedSection, ...]
    upper_surface: np.ndarray
    lower_surface: np.ndarray
    metrics: dict[str, float | int | bool | str]


@dataclass(frozen=True)
class ControlSurfaceSpec:
    """One trailing-edge control definition carried with the geometry.

    The neutral pyGeo loft is unchanged by this metadata. The standalone GUI
    can render a kinematic deflection preview, while authoritative physical
    deflected CAD remains a separate implementation boundary.
    """

    enabled: bool
    name: str
    family: str
    hinge_point: float
    start_frac: float
    end_frac: float
    symmetric: bool
    deflection_sign: str
    delta_e_sym_deg: float
    delta_a_diff_deg: float

    @property
    def right_deflection_deg(self) -> float:
        return self.delta_e_sym_deg + self.delta_a_diff_deg

    @property
    def left_deflection_deg(self) -> float:
        return self.delta_e_sym_deg - self.delta_a_diff_deg

    def geometry_dict(self) -> dict[str, float | bool | str]:
        """Identity fields shared by every command applied to this geometry."""

        return {
            "enabled": self.enabled,
            "name": self.name,
            "family": self.family,
            "hinge_point": self.hinge_point,
            "start_frac": self.start_frac,
            "end_frac": self.end_frac,
            "symmetric": self.symmetric,
            "deflection_sign": self.deflection_sign,
        }

    def to_dict(self) -> dict[str, float | bool | str]:
        return {
            **self.geometry_dict(),
            "delta_e_sym_deg": self.delta_e_sym_deg,
            "delta_a_diff_deg": self.delta_a_diff_deg,
            "right_deflection_deg": self.right_deflection_deg,
            "left_deflection_deg": self.left_deflection_deg,
        }


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return dict(value)


def _float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, got {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    raise ValueError(f"{label} must be boolean")


def resolve_control_surface(config: GeneratorConfig) -> ControlSurfaceSpec:
    """Resolve a standalone override or fall back to the Aeris definition.

    The accepted YAML shape mirrors ``geometry.control_surfaces`` in Aeris,
    with an additional optional ``commands`` mapping used only to record and
    preview symmetric/differential commands.
    """

    raw = config.geometry.get("control_surfaces")
    if raw is None:
        definition = config.definition.control_surfaces
        if not definition.enabled or not definition.surfaces:
            return ControlSurfaceSpec(
                enabled=False,
                name="elevon",
                family="trailing_edge",
                hinge_point=0.75,
                start_frac=0.60,
                end_frac=0.95,
                symmetric=True,
                deflection_sign="standard",
                delta_e_sym_deg=0.0,
                delta_a_diff_deg=0.0,
            )
        source = definition.surfaces[0]
        return ControlSurfaceSpec(
            enabled=True,
            name=source.name,
            family=source.family,
            hinge_point=float(source.hinge_point),
            start_frac=float(source.spanwise.start_frac),
            end_frac=float(source.spanwise.end_frac),
            symmetric=bool(source.symmetric),
            deflection_sign=source.deflection_sign,
            delta_e_sym_deg=0.0,
            delta_a_diff_deg=0.0,
        )

    block = _mapping(raw, "geometry.control_surfaces")
    enabled = _bool(block.get("enabled", False), "geometry.control_surfaces.enabled")
    surfaces = block.get("surfaces", [])
    if not isinstance(surfaces, list):
        raise ValueError("geometry.control_surfaces.surfaces must be a list")
    if enabled and len(surfaces) != 1:
        raise ValueError(
            "The standalone GUI currently supports exactly one enabled trailing-edge surface"
        )
    surface = _mapping(surfaces[0], "geometry.control_surfaces.surfaces[0]") if surfaces else {}
    spanwise = _mapping(surface.get("spanwise", {}), "control surface spanwise")
    commands = _mapping(block.get("commands", {}), "control surface commands")
    spec = ControlSurfaceSpec(
        enabled=enabled,
        name=str(surface.get("name", "elevon")).strip() or "elevon",
        family=str(surface.get("family", "trailing_edge")).strip(),
        hinge_point=_float(surface.get("hinge_point", 0.75), "control hinge_point"),
        start_frac=_float(spanwise.get("start_frac", 0.60), "control start_frac"),
        end_frac=_float(spanwise.get("end_frac", 0.95), "control end_frac"),
        symmetric=_bool(surface.get("symmetric", True), "control symmetric"),
        deflection_sign=str(surface.get("deflection_sign", "standard")).strip(),
        delta_e_sym_deg=_float(
            commands.get("delta_e_sym_deg", 0.0),
            "control commands.delta_e_sym_deg",
        ),
        delta_a_diff_deg=_float(
            commands.get("delta_a_diff_deg", 0.0),
            "control commands.delta_a_diff_deg",
        ),
    )
    if spec.family != "trailing_edge":
        raise ValueError("Only family='trailing_edge' is currently supported")
    if not 0.0 < spec.hinge_point < 1.0:
        raise ValueError("control hinge_point must be within (0, 1)")
    if not 0.0 <= spec.start_frac < spec.end_frac <= 1.0:
        raise ValueError("control span must satisfy 0 <= start < end <= 1")
    if spec.deflection_sign != "standard":
        raise ValueError("Only deflection_sign='standard' is currently supported")
    return spec


def _resolve(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty path")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


def _parse_range(value: object, label: str) -> Range:
    block = _mapping(value, label)
    if "value" in block:
        fixed = _float(block["value"], f"{label}.value")
        return Range(fixed, fixed)
    minimum = _float(block.get("min"), f"{label}.min")
    maximum = _float(block.get("max"), f"{label}.max")
    if maximum < minimum:
        raise ValueError(f"{label}: max must be >= min")
    return Range(minimum, maximum)


def load_config(path: str | Path) -> GeneratorConfig:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    raw_loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw = _mapping(raw_loaded, "config")
    if raw.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"schema must be {SCHEMA_VERSION!r}, got {raw.get('schema')!r}")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError("name must be non-empty")

    definition_path = _resolve(raw.get("aeris_definition_config"), "aeris_definition_config")
    if not definition_path.is_file():
        raise FileNotFoundError(definition_path)
    definition_raw = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition = build_bwb_generator_config(_mapping(definition_raw, "Aeris config"))
    validate_bwb_generator_config(definition)
    root_dihedral = float(definition.section_bounds.dihedral_root_deg)
    if abs(root_dihedral) > 1.0e-12:
        raise ValueError(
            "The standalone pyGeo BWB requires Aeris section_bounds.dihedral_root_deg = 0.0"
        )

    database = _resolve(raw.get("airfoil_database"), "airfoil_database")
    if not database.is_dir():
        raise FileNotFoundError(database)
    fixed_raw = _mapping(raw.get("fixed_airfoils"), "fixed_airfoils")
    missing_airfoils = [key for key in AIRFOIL_STATIONS if key not in fixed_raw]
    if missing_airfoils:
        raise ValueError(f"fixed_airfoils is missing {missing_airfoils}")
    fixed_airfoils = {key: str(fixed_raw[key]).strip() for key in AIRFOIL_STATIONS}
    for key, name_value in fixed_airfoils.items():
        candidates = (database / name_value, database / f"{name_value}.dat")
        if not any(candidate.is_file() for candidate in candidates):
            raise FileNotFoundError(
                f"fixed_airfoils.{key}={name_value!r} was not found in {database}"
            )

    doe = _mapping(raw.get("doe"), "doe")
    method = str(doe.get("method", "lhs")).strip().lower()
    if method not in {"lhs", "random", "center"}:
        raise ValueError("doe.method must be lhs, random, or center")
    seed = int(doe.get("seed", 42))
    n_samples = int(doe.get("n_samples", 1))
    if n_samples < 1:
        raise ValueError("doe.n_samples must be positive")
    variables = _mapping(doe.get("variables"), "doe.variables")
    missing_variables = [name for name in DIRECT_VARIABLES if name not in variables]
    unknown_variables = sorted(set(variables) - set(DIRECT_VARIABLES))
    if missing_variables:
        raise ValueError(f"doe.variables is missing {missing_variables}")
    if unknown_variables:
        raise ValueError(f"doe.variables contains unknown keys {unknown_variables}")
    ranges = {
        name: _parse_range(variables[name], f"doe.variables.{name}") for name in DIRECT_VARIABLES
    }
    _validate_global_ranges(ranges)

    geometry = _mapping(raw.get("geometry"), "geometry")
    outputs = _mapping(raw.get("outputs"), "outputs")
    output_root = _resolve(outputs.get("root", f"artifacts/{name}"), "outputs.root")
    config = GeneratorConfig(
        path=source,
        raw=raw,
        name=name,
        definition_path=definition_path,
        definition=definition,
        airfoil_database=database,
        fixed_airfoils=fixed_airfoils,
        method=method,
        seed=seed,
        n_samples=n_samples,
        ranges=ranges,
        geometry=geometry,
        outputs=outputs,
        output_root=output_root,
    )
    control = resolve_control_surface(config)
    resolve_physical_cad_spec(config.geometry, control_enabled=control.enabled)
    return config


def _validate_global_ranges(ranges: Mapping[str, Range]) -> None:
    for name in ("c1_m", "c2_m", "c3_m", "c4_m", "b1_m", "b2_m", "b3_m"):
        if ranges[name].minimum <= 0.0:
            raise ValueError(f"{name} must remain positive")
    # This guarantees every independently sampled LHS row has monotonic chord.
    for inboard, outboard in (
        ("c1_m", "c2_m"),
        ("c2_m", "c3_m"),
        ("c3_m", "c4_m"),
    ):
        if ranges[inboard].minimum <= ranges[outboard].maximum:
            raise ValueError(
                f"To guarantee c1 > c2 > c3 > c4 for every DoE row, "
                f"{inboard}.min must exceed {outboard}.max"
            )
    for name in ("sw1_deg", "sw2_deg", "sw3_deg"):
        if ranges[name].minimum < 0.0 or ranges[name].maximum >= 89.0:
            raise ValueError(f"{name} must stay in [0, 89) degrees")
    root_panel = ranges["dihedral_b1_deg"]
    if abs(root_panel.minimum) > 1.0e-12 or abs(root_panel.maximum) > 1.0e-12:
        raise ValueError(
            "dihedral_b1_deg is a hard 0° invariant: the complete root panel "
            "must remain flat so mirrored finite-thickness halves cannot intersect"
        )


def create_doe(
    config: GeneratorConfig,
    *,
    n_samples_override: int | None = None,
) -> pd.DataFrame:
    n_samples = config.n_samples if n_samples_override is None else int(n_samples_override)
    if n_samples < 1:
        raise ValueError("n_samples must be positive")
    varied = [name for name in DIRECT_VARIABLES if config.ranges[name].varied]
    if config.method == "center":
        if n_samples != 1:
            raise ValueError("center DoE requires exactly one sample")
        unit = np.full((1, len(varied)), 0.5)
    elif config.method == "lhs":
        unit = qmc.LatinHypercube(d=len(varied), seed=config.seed).random(n_samples)
    else:
        unit = np.random.default_rng(config.seed).random((n_samples, len(varied)))

    rows: list[dict[str, float | int | str]] = []
    for case_index in range(n_samples):
        row: dict[str, float | int | str] = {"case_index": case_index}
        for name in DIRECT_VARIABLES:
            interval = config.ranges[name]
            if interval.varied:
                column = varied.index(name)
                row[name] = interval.from_unit(float(unit[case_index, column]))
                row[f"u__{name}"] = float(unit[case_index, column])
            else:
                row[name] = interval.minimum
        direct = {name: float(row[name]) for name in DIRECT_VARIABLES}
        _validate_direct_design(direct)
        row.update(_derived_variables(direct))
        row["geometry_id"] = _geometry_id(config, direct)
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame["geometry_id"].duplicated().any():
        raise ValueError("DoE generated duplicate geometry IDs")
    return frame


def _validate_direct_design(values: Mapping[str, float]) -> None:
    chords = [float(values[f"c{i}_m"]) for i in range(1, 5)]
    if not all(first > second for first, second in zip(chords[:-1], chords[1:], strict=False)):
        raise ValueError(f"chords must satisfy c1 > c2 > c3 > c4, got {chords}")
    spans = [float(values[f"b{i}_m"]) for i in range(1, 4)]
    if any(value <= 0.0 for value in spans):
        raise ValueError(f"b1, b2, and b3 must be positive, got {spans}")

    if abs(float(values["dihedral_b1_deg"])) > 1.0e-12:
        raise ValueError(
            "dihedral_b1_deg must be exactly 0 degrees so the complete root panel remains flat"
        )


def _derived_variables(values: Mapping[str, float]) -> dict[str, float]:
    c1 = float(values["c1_m"])
    b1, b2, b3 = (float(values[f"b{i}_m"]) for i in range(1, 4))
    semispan = b1 + b2 + b3
    return {
        "c2_ratio": float(values["c2_m"]) / c1,
        "c3_ratio": float(values["c3_m"]) / c1,
        "c4_ratio": float(values["c4_m"]) / c1,
        "b_total_m": semispan,
        "b3_ratio": b3 / semispan,
        "split_ratio": b1 / (b1 + b2),
    }


def _geometry_id(
    config: GeneratorConfig,
    values: Mapping[str, float],
) -> str:
    payload = {
        "variables": {key: float(values[key]) for key in DIRECT_VARIABLES},
        "airfoils": config.fixed_airfoils,
        "pygeo": dict(config.geometry.get("pygeo") or {}),
        "control_geometry": resolve_control_surface(config).geometry_dict(),
        "physical_cad_geometry": resolve_physical_cad_spec(
            config.geometry,
            control_enabled=resolve_control_surface(config).enabled,
        ).identity_dict(),
        "aeris_definition": str(config.definition_path),
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"pygeo_bwb_{digest[:20]}"


def direct_to_aeris_sample(values: Mapping[str, float]) -> BWBDesignSample:
    """Convert direct physical variables to Aeris's exact internal vector."""
    _validate_direct_design(values)
    derived = _derived_variables(values)
    return BWBDesignSample(
        c1_m=float(values["c1_m"]),
        c2_ratio=derived["c2_ratio"],
        c3_ratio=derived["c3_ratio"],
        c4_ratio=derived["c4_ratio"],
        b_total_m=derived["b_total_m"],
        b3_ratio=derived["b3_ratio"],
        split_ratio=derived["split_ratio"],
        sw1_deg=-abs(float(values["sw1_deg"])),
        sw2_deg=-abs(float(values["sw2_deg"])),
        sw3_deg=-abs(float(values["sw3_deg"])),
        twist_b0_deg=float(values["twist_b0_deg"]),
        twist_b1_deg=float(values["twist_b1_deg"]),
        twist_b2_deg=float(values["twist_b2_deg"]),
        twist_b3_deg=float(values["twist_b3_deg"]),
        dihedral_b1_deg=0.0,
        dihedral_b2_deg=float(values["dihedral_b2_deg"]),
        dihedral_b3_deg=float(values["dihedral_b3_deg"]),
    )


def _airfoil_at_y(
    y_m: float,
    boundaries: Sequence[float],
    fixed_airfoils: Mapping[str, str],
) -> str:
    if y_m >= float(boundaries[3]) - 1.0e-9:
        return fixed_airfoils["b3"]
    if y_m >= float(boundaries[2]) - 1.0e-9:
        return fixed_airfoils["b2"]
    if y_m >= float(boundaries[1]) - 1.0e-9:
        return fixed_airfoils["b1"]
    return fixed_airfoils["b0"]


def apply_fixed_airfoils(
    section_geometry: SectionGeometryResult,
    fixed_airfoils: Mapping[str, str],
) -> SectionGeometryResult:
    """Apply b0/b1/b2/b3 shapes explicitly in this standalone workflow."""
    records = [
        replace(
            section,
            airfoil_name=_airfoil_at_y(
                section.y_m,
                section_geometry.group_boundary_y,
                fixed_airfoils,
            ),
        )
        for section in section_geometry.sections
    ]
    return replace(section_geometry, sections=records)


def _span_fractions(
    count: int,
    section_geometry: SectionGeometryResult,
) -> np.ndarray:
    if count < 4:
        raise ValueError("geometry.extraction.spanwise_sections must be at least 4")
    semispan = max(float(section.y_m) for section in section_geometry.sections)
    fractions = set(float(value) for value in np.linspace(0.0, 1.0, count))
    fractions.update(
        float(np.clip(float(y) / semispan, 0.0, 1.0)) for y in section_geometry.group_boundary_y
    )
    return np.asarray(sorted(fractions), dtype=float)


def _polygon_area(coordinates: np.ndarray) -> float:
    coords = np.asarray(coordinates, dtype=float)
    x, z = coords[:, 0], coords[:, 1]
    return abs(0.5 * float(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z)))


def _quad_strip_area(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape:
        raise ValueError("section surface arrays must have equal shapes")
    total = 0.0
    for index in range(len(first) - 1):
        p00, p10 = first[index], first[index + 1]
        p01, p11 = second[index], second[index + 1]
        total += 0.5 * float(np.linalg.norm(np.cross(p10 - p00, p11 - p00)))
        total += 0.5 * float(np.linalg.norm(np.cross(p11 - p00, p01 - p00)))
    return total


def volume_and_wetted_area(
    sections: Sequence[ExtractedSection],
) -> dict[str, float]:
    ordered = sorted(sections, key=lambda section: section.y_m)
    yz = np.asarray([[section.y_m, section.z_le_m] for section in ordered])
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(yz, axis=0), axis=1))])
    areas = np.asarray(
        [_polygon_area(section.direct_coordinates) * section.chord_m**2 for section in ordered]
    )
    half_volume = float(np.trapezoid(areas, arc))
    half_wetted = 0.0
    for first, second in zip(ordered[:-1], ordered[1:], strict=False):
        half_wetted += _quad_strip_area(first.upper_xyz_m, second.upper_xyz_m)
        half_wetted += _quad_strip_area(first.lower_xyz_m, second.lower_xyz_m)
    return {
        "volume_m3": 2.0 * half_volume,
        "wetted_area_m2": 2.0 * half_wetted,
    }


def _surface_area_from_grid(surface: np.ndarray) -> float:
    area = 0.0
    for i in range(surface.shape[0] - 1):
        for j in range(surface.shape[1] - 1):
            p00 = surface[i, j]
            p10 = surface[i + 1, j]
            p11 = surface[i + 1, j + 1]
            p01 = surface[i, j + 1]
            area += 0.5 * float(np.linalg.norm(np.cross(p10 - p00, p11 - p00)))
            area += 0.5 * float(np.linalg.norm(np.cross(p11 - p00, p01 - p00)))
    return area


def control_surface_metrics(
    sections: Sequence[ExtractedSection],
    spec: ControlSurfaceSpec,
    *,
    s_ref_m2: float,
) -> dict[str, float | bool | str]:
    """Calculate the neutral control footprint on the realised pyGeo loft."""

    if not spec.enabled:
        return {
            "control_surface_enabled": False,
            "control_surface_name": spec.name,
            "control_surface_area_xy_m2": 0.0,
            "control_surface_area_yz_m2": 0.0,
            "control_surface_area_ratio_sref": 0.0,
            "control_hinge_length_m": 0.0,
            "control_span_m": 0.0,
            "control_geometry_state": "disabled",
        }

    ordered = sorted(sections, key=lambda section: section.span_fraction)
    fractions = np.asarray([section.span_fraction for section in ordered], dtype=float)
    sample_fractions = np.linspace(spec.start_frac, spec.end_frac, 201)

    def interp(values: Sequence[float]) -> np.ndarray:
        return np.interp(sample_fractions, fractions, np.asarray(values, dtype=float))

    le = np.column_stack(
        [interp([section.le_xyz_m[axis] for section in ordered]) for axis in range(3)]
    )
    te = np.column_stack(
        [interp([section.te_xyz_m[axis] for section in ordered]) for axis in range(3)]
    )
    chords = interp([section.chord_m for section in ordered])
    flap_chords = (1.0 - spec.hinge_point) * chords
    hinge = le + spec.hinge_point * (te - le)
    hinge_arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(hinge, axis=0), axis=1))])
    area_xy = 2.0 * float(np.trapezoid(flap_chords, hinge[:, 1]))
    area_yz = 2.0 * float(np.trapezoid(flap_chords, hinge_arc))
    return {
        "control_surface_enabled": True,
        "control_surface_name": spec.name,
        "control_surface_area_xy_m2": area_xy,
        "control_surface_area_yz_m2": area_yz,
        "control_surface_area_ratio_sref": area_xy / max(float(s_ref_m2), 1.0e-12),
        "control_hinge_length_m": 2.0 * float(hinge_arc[-1]),
        "control_span_m": 2.0 * abs(float(hinge[-1, 1] - hinge[0, 1])),
        "control_hinge_fraction": spec.hinge_point,
        "control_span_start_fraction": spec.start_frac,
        "control_span_end_fraction": spec.end_frac,
        "delta_e_sym_deg": spec.delta_e_sym_deg,
        "delta_a_diff_deg": spec.delta_a_diff_deg,
        "right_deflection_deg": spec.right_deflection_deg,
        "left_deflection_deg": spec.left_deflection_deg,
        "control_geometry_state": "neutral_master_with_kinematic_diagnostic",
    }


def build_case(
    config: GeneratorConfig,
    row: Mapping[str, Any],
) -> BuiltCase:
    direct = {name: float(row[name]) for name in DIRECT_VARIABLES}
    sample = direct_to_aeris_sample(direct)
    planform = generate_bwb_planform_from_sample(sample, config.definition)
    neutral_sections = build_section_geometry_from_sample(planform, sample, config.definition)
    sections = apply_fixed_airfoils(neutral_sections, config.fixed_airfoils)
    stations = tuple(stations_from_records(sections.sections, config.airfoil_database))
    control = resolve_control_surface(config)

    pygeo_cfg = _mapping(config.geometry.get("pygeo"), "geometry.pygeo")
    configured_frame = str(pygeo_cfg.get("frame_mode", "aeris_frame"))
    bridge_frame = "asb_frame" if configured_frame == "aeris_frame" else configured_frame
    pygeo = build_pygeo(
        stations,
        k_span=int(pygeo_cfg.get("k_span", 3)),
        frame_mode=bridge_frame,
        n_ctl=(None if pygeo_cfg.get("n_ctl") is None else int(pygeo_cfg["n_ctl"])),
        tip=str(pygeo_cfg.get("tip", "none")),
        tip_scale=float(pygeo_cfg.get("tip_scale", 0.25)),
    )

    extraction = _mapping(config.geometry.get("extraction"), "geometry.extraction")
    fractions = _span_fractions(int(extraction.get("spanwise_sections", 25)), sections)
    if control.enabled:
        fractions = np.unique(np.concatenate([fractions, [control.start_frac, control.end_frac]]))
    extracted = tuple(
        extract_sections(
            pygeo,
            fractions,
            cst_order=int(extraction.get("cst_order", 8)),
            chordwise_points=int(extraction.get("chordwise_points", 241)),
        )
    )
    sampling = _mapping(config.geometry.get("surface_sampling"), "geometry.surface_sampling")
    upper, lower = sample_main_surfaces(
        pygeo,
        chordwise_points=int(sampling.get("chordwise_points", 141)),
        spanwise_points=int(sampling.get("spanwise_points", 121)),
    )

    metrics: dict[str, float | int | bool | str] = {
        **realised_reference_metrics(extracted, symmetric=True),
        **volume_and_wetted_area(extracted),
        "pygeo_surface_area_m2": 2.0
        * (_surface_area_from_grid(upper) + _surface_area_from_grid(lower)),
        "semi_span_m": float(planform.semi_span_m),
        "full_span_m": float(planform.full_span_m),
        "planform_area_m2": float(planform.approx_area_m2),
        "planform_aspect_ratio": float(planform.approx_aspect_ratio),
        "n_authored_sections": len(stations),
        "n_extracted_sections": len(extracted),
        "max_plane_warp_chord": max(section.plane_warp_max_chord for section in extracted),
        "max_cst_rms_chord": max(section.cst_rms_chord for section in extracted),
        "max_cst_error_chord": max(section.cst_max_chord for section in extracted),
        "all_cst_valid": all(section.cst_valid for section in extracted),
        "frame_reconstruction_error": pygeo.frame_reconstruction_error,
    }
    metrics.update(
        control_surface_metrics(
            extracted,
            control,
            s_ref_m2=float(metrics["s_ref_xy_m2"]),
        )
    )
    quality = _mapping(config.geometry.get("quality"), "geometry.quality")
    warp_warning = float(quality.get("warn_plane_warp_chord", 3.0e-3))
    warp_limit = float(quality.get("max_plane_warp_chord", 1.0e-2))
    cst_limit = float(quality.get("max_cst_rms_chord", 1.0e-3))
    metrics["plane_warp_warning_chord"] = warp_warning
    metrics["plane_warp_limit_chord"] = warp_limit
    metrics["cst_rms_limit_chord"] = cst_limit
    metrics["section_planarity"] = (
        "warning_planarize_for_2d_use"
        if float(metrics["max_plane_warp_chord"]) > warp_warning
        else "within_warning_limit"
    )
    accepted = (
        float(metrics["max_plane_warp_chord"]) <= warp_limit
        and float(metrics["max_cst_rms_chord"]) <= cst_limit
        and bool(metrics["all_cst_valid"])
    )
    metrics["geometry_qc"] = "accepted" if accepted else "rejected"
    return BuiltCase(
        case_index=int(row["case_index"]),
        geometry_id=str(row["geometry_id"]),
        direct_variables=direct,
        sample=sample,
        planform=planform,
        sections=sections,
        stations=stations,
        pygeo=pygeo,
        extracted=extracted,
        upper_surface=upper,
        lower_surface=lower,
        metrics=metrics,
    )


def _write_dat(path: Path, section: ExtractedSection) -> None:
    lines = [f"{path.stem}"]
    lines.extend(f"{float(x): .10f} {float(z): .10f}" for x, z in section.direct_coordinates)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _equal_axes_3d(axis: Any, points: np.ndarray) -> None:
    mins = np.min(points, axis=0)
    maxs = np.max(points, axis=0)
    center = 0.5 * (mins + maxs)
    radius = 0.52 * max(float(np.max(maxs - mins)), 1.0e-6)
    axis.set_xlim(center[0] - radius, center[0] + radius)
    axis.set_ylim(center[1] - radius, center[1] + radius)
    axis.set_zlim(center[2] - radius, center[2] + radius)
    axis.set_box_aspect((1, 1, 0.45))


def plot_geometry_3d(case: BuiltCase, path: Path, dpi: int) -> None:
    fig = plt.figure(figsize=(11.5, 7.5))
    axis = fig.add_subplot(111, projection="3d")
    for surface, color in (
        (case.upper_surface, "#4C78A8"),
        (case.lower_surface, "#72B7B2"),
    ):
        axis.plot_surface(
            surface[:, :, 0],
            surface[:, :, 1],
            surface[:, :, 2],
            color=color,
            alpha=0.92,
            linewidth=0.0,
            antialiased=True,
        )
        mirrored = surface.copy()
        mirrored[:, :, 1] *= -1.0
        axis.plot_surface(
            mirrored[:, :, 0],
            mirrored[:, :, 1],
            mirrored[:, :, 2],
            color=color,
            alpha=0.92,
            linewidth=0.0,
            antialiased=True,
        )
    points = np.vstack(
        [
            case.upper_surface.reshape(-1, 3),
            case.lower_surface.reshape(-1, 3),
            case.upper_surface.reshape(-1, 3) * np.array([1.0, -1.0, 1.0]),
        ]
    )
    _equal_axes_3d(axis, points)
    axis.view_init(elev=24, azim=-128)
    axis.set_xlabel("x [m]")
    axis.set_ylabel("y [m]")
    axis.set_zlabel("z [m]")
    axis.set_title(f"pyGeo BWB loft — case {case.case_index:04d}\n{case.geometry_id}")
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_planform(
    case: BuiltCase,
    config: GeneratorConfig,
    path: Path,
    dpi: int,
) -> None:
    planform = case.planform
    fig, axis = plt.subplots(figsize=(11, 7))
    for sign in (1.0, -1.0):
        y = sign * planform.front_y_fine
        axis.plot(planform.front_x_fine, y, color="#1f77b4", linewidth=2.0)
        axis.plot(planform.rear_x_fine, y, color="#d62728", linewidth=2.0)
        axis.fill_betweenx(
            y,
            planform.front_x_fine,
            planform.rear_x_fine,
            color="#4C78A8",
            alpha=0.16,
        )
    colors = ("#9467bd", "#2ca02c", "#ff7f0e", "#8c564b")
    for index, (boundary_y, key) in enumerate(
        zip(planform.group_boundary_y, AIRFOIL_STATIONS, strict=False)
    ):
        y = float(boundary_y)
        x_le = float(np.interp(y, planform.front_y_fine, planform.front_x_fine))
        x_te = float(np.interp(y, planform.front_y_fine, planform.rear_x_fine))
        for sign in (1.0, -1.0):
            axis.plot(
                [x_le, x_te],
                [sign * y, sign * y],
                color=colors[index],
                linewidth=1.4,
            )
        axis.text(
            x_te + 0.025,
            y,
            f"{key}: {config.fixed_airfoils[key]}",
            fontsize=8,
            color=colors[index],
            va="center",
        )
    control = resolve_control_surface(config)
    if control.enabled:
        y0 = control.start_frac * float(planform.semi_span_m)
        y1 = control.end_frac * float(planform.semi_span_m)
        y_control = np.linspace(y0, y1, 101)
        le_control = np.interp(
            y_control,
            planform.front_y_fine,
            planform.front_x_fine,
        )
        te_control = np.interp(y_control, planform.front_y_fine, planform.rear_x_fine)
        hinge_control = le_control + control.hinge_point * (te_control - le_control)
        for index, sign in enumerate((1.0, -1.0)):
            axis.fill_betweenx(
                sign * y_control,
                hinge_control,
                te_control,
                color="#F59E0B",
                alpha=0.42,
                label=control.name if index == 0 else None,
            )
            axis.plot(
                hinge_control,
                sign * y_control,
                color="#B45309",
                linewidth=1.5,
                linestyle="--",
            )
        axis.text(
            float(te_control[-1]) + 0.025,
            y1,
            f"{control.name}: hinge={control.hinge_point:.2f}",
            fontsize=8,
            color="#B45309",
            va="center",
        )
    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, alpha=0.25)
    axis.set_xlabel("x [m]")
    axis.set_ylabel("y [m]")
    axis.set_title(f"Aeris BWB planform definition — pyGeo case {case.case_index:04d}")
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_sections(
    case: BuiltCase,
    config: GeneratorConfig,
    path: Path,
    dpi: int,
) -> None:
    semispan = max(section.y_m for section in case.extracted)
    targets = np.asarray(case.sections.group_boundary_y, dtype=float) / semispan
    available = np.asarray([section.span_fraction for section in case.extracted], dtype=float)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    for axis, key, target in zip(axes.flat, AIRFOIL_STATIONS, targets, strict=False):
        section = case.extracted[int(np.argmin(np.abs(available - target)))]
        coords = section.direct_coordinates
        axis.plot(coords[:, 0], coords[:, 1], color="#1f77b4", linewidth=1.8)
        cst_coords = section.cst.coordinates(n_per_surface=181)
        axis.plot(
            cst_coords[:, 0],
            cst_coords[:, 1],
            color="#d62728",
            linestyle="--",
            linewidth=1.0,
            label="CST fit",
        )
        axis.axhline(0.0, color="black", linewidth=0.5, alpha=0.4)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(True, alpha=0.2)
        axis.set_title(f"{key} · {config.fixed_airfoils[key]} · y/b={section.span_fraction:.3f}")
        axis.text(
            0.02,
            0.04,
            f"t/c={section.thickness_ratio:.4f}\nCST RMS={section.cst_rms_chord:.2e}",
            transform=axis.transAxes,
            fontsize=8,
            va="bottom",
        )
    axes[0, 0].legend(loc="upper right", fontsize=8)
    fig.supxlabel("x/c")
    fig.supylabel("z/c")
    fig.suptitle(f"Realised pyGeo sections — case {case.case_index:04d}")
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_case(
    config: GeneratorConfig,
    case: BuiltCase,
    case_dir: Path,
    *,
    disable_cad: bool,
    disable_visualization: bool,
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = case_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    control = resolve_control_surface(config)

    physical_spec = resolve_physical_cad_spec(
        config.geometry,
        control_enabled=control.enabled,
    )
    state_id = physical_state_id(case.geometry_id, control, physical_spec)
    section_rows = [section.as_metrics_row() for section in case.extracted]
    pd.DataFrame(section_rows).to_csv(case_dir / "extracted_sections.csv", index=False)
    authored_rows = [
        {
            "index": station.index,
            "x_le_m": station.x_le_m,
            "y_m": station.y_m,
            "z_le_m": station.z_le_m,
            "chord_m": station.chord_m,
            "twist_deg": station.twist_deg,
            "dihedral_deg": station.dihedral_deg,
            "airfoil_name": station.airfoil_name,
            "airfoil_path": str(station.airfoil_path),
        }
        for station in case.stations
    ]
    pd.DataFrame(authored_rows).to_csv(case_dir / "authored_stations.csv", index=False)
    _write_json(
        case_dir / "cst_coefficients.json",
        {
            "schema": "pygeo_bwb_cst_sections.v1",
            "geometry_id": case.geometry_id,
            "sections": [
                {
                    "section_index": section.index,
                    "span_fraction": section.span_fraction,
                    "chord_m": section.chord_m,
                    "cst": section.cst.to_dict(),
                    "cst_rms_chord": section.cst_rms_chord,
                    "cst_max_chord": section.cst_max_chord,
                    "valid": section.cst_valid,
                    "failures": list(section.cst_failures),
                }
                for section in case.extracted
            ],
        },
    )
    _write_json(
        case_dir / "control_surface.json",
        {
            **control.to_dict(),
            "neutral_loft_modified": False,
            "kinematic_preview_available_in_gui": True,
            "authoritative_physical_deflected_cad": False,
            "note": "Commands are recorded and previewed; native pyGeo IGES/Tecplot stay neutral.",
        },
    )

    output_cfg = config.outputs
    if bool(output_cfg.get("write_surface_npz", True)):
        np.savez_compressed(
            case_dir / "pygeo_surface.npz",
            upper=case.upper_surface,
            lower=case.lower_surface,
        )
    if bool(output_cfg.get("write_section_dat", True)):
        for section in case.extracted:
            _write_dat(
                sections_dir / f"section_{section.index:03d}_yb_{section.span_fraction:.6f}.dat",
                section,
            )

    export_status: dict[str, str] = {}
    if not disable_cad and bool(output_cfg.get("write_iges", True)):
        try:
            case.pygeo.geometry.writeIGES(str(case_dir / "pygeo_surface.igs"))
            export_status["iges"] = "written"
        except Exception as exc:
            export_status["iges"] = f"failed: {type(exc).__name__}: {exc}"
    if not disable_cad and bool(output_cfg.get("write_tecplot", True)):
        try:
            case.pygeo.geometry.writeTecplot(
                str(case_dir / "pygeo_surface.dat"), surfs=True, coef=True
            )
            export_status["tecplot"] = "written"
        except Exception as exc:
            export_status["tecplot"] = f"failed: {type(exc).__name__}: {exc}"

    visualization = _mapping(output_cfg.get("visualization", {}), "outputs.visualization")
    visualization_enabled = not disable_visualization and bool(visualization.get("enabled", True))
    dpi = int(visualization.get("dpi", 180))
    if visualization_enabled:
        plot_geometry_3d(case, case_dir / "geometry_3d.png", dpi)
        plot_planform(case, config, case_dir / "planform.png", dpi)
        plot_sections(case, config, case_dir / "sections.png", dpi)
    physical_result: dict[str, Any] | None = None
    if physical_spec.enabled and not disable_cad:
        try:
            physical_model = build_physical_cad(case, control, physical_spec)
            physical_result = export_physical_cad(
                physical_model,
                case_dir,
                output_flags=output_cfg,
                visualization_enabled=visualization_enabled,
                dpi=dpi,
            )
            case.metrics.update(physical_result["metrics"])
            export_status["physical_cad"] = str(physical_result["status"])
        except Exception as exc:
            export_status["physical_cad"] = f"failed: {type(exc).__name__}: {exc}"
            case.metrics["physical_cad_accepted"] = False
            if physical_spec.fail_on_invalid:
                raise
    elif physical_spec.enabled:
        export_status["physical_cad"] = "skipped_by_no_cad"
    else:
        export_status["physical_cad"] = "disabled"

    _write_json(
        case_dir / "control_surface.json",
        {
            "schema": "pygeo_bwb_control_surface.v2",
            **control.to_dict(),
            "geometry_id": case.geometry_id,
            "physical_state_id": state_id,
            "neutral_loft_modified": False,
            "kinematic_preview_available_in_gui": True,
            "authoritative_physical_deflected_cad": bool(
                physical_result is not None and physical_result.get("status") == "accepted"
            ),
            "physical_cad": physical_spec.to_dict(),
            "physical_cad_artifacts": (
                physical_result.get("artifacts", {}) if physical_result is not None else {}
            ),
            "note": (
                "Native pyGeo IGES/Tecplot remain neutral. Physical commands are "
                "represented by the reconstructed named split-solid STEP assembly."
            ),
        },
    )

    manifest = {
        "schema": "pygeo_bwb_case.v1",
        "case_index": case.case_index,
        "geometry_id": case.geometry_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config.path),
        "aeris_definition_config": str(config.definition_path),
        "direct_variables": case.direct_variables,
        "derived_aeris_variables": _derived_variables(case.direct_variables),
        "internal_aeris_sample": case.sample.to_dict(),
        "fixed_airfoils": config.fixed_airfoils,
        "metrics": case.metrics,
        "control_surface": control.to_dict(),
        "physical_state_id": state_id,
        "physical_cad": {
            "spec": physical_spec.to_dict(),
            "result": physical_result,
        },
        "pygeo": {
            "k_span": case.pygeo.k_span,
            "frame_mode": case.pygeo.frame_mode,
            "rot_x_deg": case.pygeo.rot_x_deg.tolist(),
            "rot_y_deg": case.pygeo.rot_y_deg.tolist(),
            "rot_z_deg": case.pygeo.rot_z_deg.tolist(),
            "thickness_scale": case.pygeo.thickness_scale.tolist(),
            "frame_reconstruction_error": (case.pygeo.frame_reconstruction_error),
            "stdout": case.pygeo.stdout,
        },
        "exports": export_status,
    }
    _write_json(case_dir / "case_manifest.json", manifest)
    return manifest


def plot_campaign_summary(
    config: GeneratorConfig,
    doe: pd.DataFrame,
    metrics: pd.DataFrame,
    output_root: Path,
) -> None:
    visualization = _mapping(config.outputs.get("visualization", {}), "outputs.visualization")
    if not bool(visualization.get("enabled", True)):
        return
    dpi = int(visualization.get("dpi", 180))

    varied = [name for name in DIRECT_VARIABLES if config.ranges[name].varied]
    normalized = np.column_stack(
        [
            (doe[name].to_numpy(float) - config.ranges[name].minimum)
            / (config.ranges[name].maximum - config.ranges[name].minimum)
            for name in varied
        ]
    )
    fig, axis = plt.subplots(figsize=(15, 7))
    for row in normalized:
        axis.plot(range(len(varied)), row, alpha=0.55, linewidth=1.0)
    axis.set_xticks(range(len(varied)))
    axis.set_xticklabels(varied, rotation=50, ha="right", fontsize=8)
    axis.set_ylim(-0.03, 1.03)
    axis.set_ylabel("Normalized DoE coordinate")
    axis.grid(True, alpha=0.2)
    axis.set_title(f"{config.name}: {len(doe)} deterministic {config.method.upper()} designs")
    fig.tight_layout()
    fig.savefig(
        output_root / "doe_parallel_coordinates.png",
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)

    successful = metrics[metrics["status"] == "ok"].copy()
    if successful.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fields = (
        ("s_ref_xy_m2", "Reference area [m²]"),
        ("aspect_ratio_xy", "Aspect ratio"),
        ("volume_m3", "Enclosed volume [m³]"),
        ("wetted_area_m2", "Wetted area [m²]"),
    )
    for axis, (field, label) in zip(axes.flat, fields, strict=False):
        axis.plot(
            successful["case_index"],
            successful[field],
            marker="o",
            linewidth=1.0,
        )
        axis.set_xlabel("Case index")
        axis.set_ylabel(label)
        axis.grid(True, alpha=0.25)
    fig.suptitle(f"{config.name}: realised pyGeo geometry metrics")
    fig.tight_layout()
    fig.savefig(
        output_root / "geometry_metrics.png",
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def _selected_indices(text: str | None, n_rows: int) -> set[int]:
    if text is None:
        return set(range(n_rows))
    selected: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        index = int(token)
        if index < 0 or index >= n_rows:
            raise ValueError(f"case index {index} outside [0, {n_rows - 1}]")
        selected.add(index)
    if not selected:
        raise ValueError("--indices selected no cases")
    return selected


def run_campaign(
    config: GeneratorConfig,
    *,
    n_samples_override: int | None,
    output_override: Path | None,
    indices: str | None,
    dry_run: bool,
    disable_cad: bool,
    disable_visualization: bool,
) -> Path:
    output_root = (
        config.output_root if output_override is None else output_override.expanduser().resolve()
    )
    output_root.mkdir(parents=True, exist_ok=True)
    doe = create_doe(config, n_samples_override=n_samples_override)
    doe.to_csv(output_root / "doe.csv", index=False)
    shutil.copy2(config.path, output_root / "config_snapshot.yaml")
    if dry_run:
        _write_json(
            output_root / "campaign_manifest.json",
            {
                "schema": "pygeo_bwb_campaign.v1",
                "status": "dry_run",
                "n_doe_rows": len(doe),
                "config": str(config.path),
            },
        )
        return output_root

    selected = _selected_indices(indices, len(doe))
    rows: list[dict[str, Any]] = []
    fail_fast = bool(config.outputs.get("fail_fast", False))
    cases_root = output_root / "cases"
    cases_root.mkdir(exist_ok=True)
    for _, row in doe.iterrows():
        case_index = int(row["case_index"])
        if case_index not in selected:
            continue
        geometry_id = str(row["geometry_id"])
        case_dir = cases_root / f"case_{case_index:04d}_{geometry_id[-8:]}"
        start = time.perf_counter()
        print(
            f"[{case_index + 1}/{len(doe)}] building {geometry_id}",
            flush=True,
        )
        try:
            case = build_case(config, row)
            write_case(
                config,
                case,
                case_dir,
                disable_cad=disable_cad,
                disable_visualization=disable_visualization,
            )
            result = {
                "case_index": case_index,
                "geometry_id": geometry_id,
                "status": "ok",
                "error": "",
                "runtime_sec": time.perf_counter() - start,
                "case_dir": str(case_dir),
                **case.direct_variables,
                **case.metrics,
            }
        except Exception as exc:
            case_dir.mkdir(parents=True, exist_ok=True)
            error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            (case_dir / "failure.txt").write_text(error_text, encoding="utf-8")
            result = {
                "case_index": case_index,
                "geometry_id": geometry_id,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "runtime_sec": time.perf_counter() - start,
                "case_dir": str(case_dir),
                **{name: float(row[name]) for name in DIRECT_VARIABLES},
            }
            print(f"  failed: {result['error']}", file=sys.stderr, flush=True)
            if fail_fast:
                rows.append(result)
                pd.DataFrame(rows).to_csv(output_root / "geometry_metrics.csv", index=False)
                raise
        rows.append(result)
        pd.DataFrame(rows).to_csv(output_root / "geometry_metrics.csv", index=False)

    results = pd.DataFrame(rows)
    visualization_cfg = _mapping(config.outputs.get("visualization", {}), "outputs.visualization")
    visualization_enabled = not disable_visualization and bool(
        visualization_cfg.get("enabled", True)
    )
    if visualization_enabled:
        plot_campaign_summary(config, doe, results, output_root)
    n_ok = int((results["status"] == "ok").sum()) if not results.empty else 0
    n_failed = int((results["status"] == "failed").sum()) if not results.empty else 0
    manifest = {
        "schema": "pygeo_bwb_campaign.v1",
        "status": "complete" if n_failed == 0 else "complete_with_failures",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config.path),
        "aeris_definition_config": str(config.definition_path),
        "output_root": str(output_root),
        "doe_method": config.method,
        "doe_seed": config.seed,
        "n_doe_rows": len(doe),
        "selected_case_indices": sorted(selected),
        "n_successful": n_ok,
        "n_failed": n_failed,
        "fixed_airfoils": config.fixed_airfoils,
        "control_surface": resolve_control_surface(config).to_dict(),
        "no_aerosandbox_geometry": True,
        "artifacts": {
            "doe_csv": str(output_root / "doe.csv"),
            "metrics_csv": str(output_root / "geometry_metrics.csv"),
            "parallel_coordinates": (
                str(output_root / "doe_parallel_coordinates.png") if visualization_enabled else None
            ),
            "metric_plot": (
                str(output_root / "geometry_metrics.png") if visualization_enabled else None
            ),
        },
    }
    _write_json(output_root / "campaign_manifest.json", manifest)
    return output_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone config-driven pyGeo BWB DoE generator")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override outputs.root without editing the YAML.",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=None,
        help="Override doe.n_samples (useful for a smoke run).",
    )
    parser.add_argument(
        "--indices",
        default=None,
        help="Comma-separated zero-based case indices; default runs all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and write the deterministic DoE only.",
    )
    parser.add_argument(
        "--no-cad",
        action="store_true",
        help="Skip native IGES/Tecplot and reconstructed STEP/control CAD export.",
    )
    parser.add_argument(
        "--no-visualization",
        action="store_true",
        help="Skip PNG plots.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    output = run_campaign(
        config,
        n_samples_override=args.n_samples,
        output_override=args.output,
        indices=args.indices,
        dry_run=bool(args.dry_run),
        disable_cad=bool(args.no_cad),
        disable_visualization=bool(args.no_visualization),
    )
    print(f"output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
