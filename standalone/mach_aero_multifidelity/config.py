"""Campaign configuration loading and validation.

The campaign YAML is an overlay, not a replacement for an Aeris geometry
configuration.  Bounds and generator controls are inherited from the base
file; this module declares which variables are varied or fixed, the fixed
station airfoils, control states, flow states, and the LF/HF policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from aeris.generators.bwb_segmented_v1.params import (
    BWBGeneratorConfig,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.validation import (
    validate_bwb_generator_config,
)

from . import SCHEMA_VERSION


DESIGN_VARIABLES = (
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

STATION_KEYS = ("b0", "b1", "b2", "b3")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return dict(value)


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, got {value!r}") from exc
    if not (-float("inf") < result < float("inf")):
        raise ValueError(f"{label} must be finite")
    return result


def _resolve(path_value: object, *, base: Path, label: str) -> Path:
    text = _nonempty_string(path_value, label)
    path = Path(text).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


@dataclass(frozen=True)
class ControlState:
    id: str
    symmetric_deg: float
    differential_deg: float

    @property
    def right_deg(self) -> float:
        return self.symmetric_deg + self.differential_deg

    @property
    def left_deg(self) -> float:
        return self.symmetric_deg - self.differential_deg


@dataclass(frozen=True)
class FlowState:
    id: str
    alpha_deg: float
    mach: float
    reynolds_ref: float
    temperature_k: float
    beta_deg: float = 0.0


@dataclass(frozen=True)
class CampaignConfig:
    source_path: Path
    repo_root: Path
    raw: dict[str, Any]
    name: str
    base_geometry_path: Path
    base_geometry_raw: dict[str, Any]
    base_geometry: BWBGeneratorConfig
    output_root: Path
    airfoil_database: Path
    sampling_method: str
    sampling_seed: int
    n_designs: int
    varied_variables: tuple[str, ...]
    fixed_variables: dict[str, float]
    unspecified_policy: str
    fixed_station_airfoils: dict[str, str]
    control_states: tuple[ControlState, ...]
    flow_states: tuple[FlowState, ...]
    geometry: dict[str, Any]
    low_fidelity: dict[str, Any]
    high_fidelity: dict[str, Any]
    dataset: dict[str, Any]

    @property
    def control_state_by_id(self) -> dict[str, ControlState]:
        return {state.id: state for state in self.control_states}

    @property
    def flow_state_by_id(self) -> dict[str, FlowState]:
        return {state.id: state for state in self.flow_states}


def _parse_control_states(raw: object) -> tuple[ControlState, ...]:
    states: list[ControlState] = []
    for index, item in enumerate(_list(raw, "controls.states")):
        block = _mapping(item, f"controls.states[{index}]")
        states.append(
            ControlState(
                id=_nonempty_string(block.get("id"), f"controls.states[{index}].id"),
                symmetric_deg=_finite_float(
                    block.get("symmetric_deg", 0.0),
                    f"controls.states[{index}].symmetric_deg",
                ),
                differential_deg=_finite_float(
                    block.get("differential_deg", 0.0),
                    f"controls.states[{index}].differential_deg",
                ),
            )
        )
    ids = [state.id for state in states]
    if not states:
        raise ValueError("controls.states must contain at least one state")
    if len(ids) != len(set(ids)):
        raise ValueError("controls.states ids must be unique")
    return tuple(states)


def _parse_flow_states(raw: object) -> tuple[FlowState, ...]:
    states: list[FlowState] = []
    for index, item in enumerate(_list(raw, "flows")):
        block = _mapping(item, f"flows[{index}]")
        mach = _finite_float(block.get("mach"), f"flows[{index}].mach")
        reynolds = _finite_float(
            block.get("reynolds_ref"), f"flows[{index}].reynolds_ref"
        )
        temperature = _finite_float(
            block.get("temperature_k", 288.15), f"flows[{index}].temperature_k"
        )
        if not 0.0 <= mach < 1.0:
            raise ValueError(f"flows[{index}].mach must be in [0, 1)")
        if reynolds <= 0.0:
            raise ValueError(f"flows[{index}].reynolds_ref must be positive")
        if temperature <= 0.0:
            raise ValueError(f"flows[{index}].temperature_k must be positive")
        states.append(
            FlowState(
                id=_nonempty_string(block.get("id"), f"flows[{index}].id"),
                alpha_deg=_finite_float(
                    block.get("alpha_deg"), f"flows[{index}].alpha_deg"
                ),
                beta_deg=_finite_float(
                    block.get("beta_deg", 0.0), f"flows[{index}].beta_deg"
                ),
                mach=mach,
                reynolds_ref=reynolds,
                temperature_k=temperature,
            )
        )
    ids = [state.id for state in states]
    if not states:
        raise ValueError("flows must contain at least one state")
    if len(ids) != len(set(ids)):
        raise ValueError("flow ids must be unique")
    return tuple(states)


def _station_airfoils(
    raw: dict[str, Any], base_geometry: BWBGeneratorConfig
) -> dict[str, str]:
    configured = raw.get("fixed_station_airfoils")
    if configured is None:
        inherited = base_geometry.section_bounds.station_airfoils
        if inherited is None:
            name = base_geometry.section_bounds.airfoil_name
            return {key: name for key in STATION_KEYS}
        return inherited.to_dict()
    block = _mapping(configured, "design_space.fixed_station_airfoils")
    missing = [key for key in STATION_KEYS if key not in block]
    if missing:
        raise ValueError(f"fixed_station_airfoils is missing {missing}")
    return {
        key: _nonempty_string(block[key], f"fixed_station_airfoils.{key}")
        for key in STATION_KEYS
    }


def load_campaign_config(path: str | Path) -> CampaignConfig:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    raw_loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw = _mapping(raw_loaded, "campaign config")
    if raw.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"schema must be {SCHEMA_VERSION!r}, got {raw.get('schema')!r}"
        )

    repo_root_value = raw.get("repo_root", "../..")
    repo_root = _resolve(
        repo_root_value, base=source.parent, label="repo_root"
    )
    campaign = _mapping(raw.get("campaign"), "campaign")
    name = _nonempty_string(campaign.get("name"), "campaign.name")
    base_geometry_path = _resolve(
        campaign.get("base_geometry_config"),
        base=repo_root,
        label="campaign.base_geometry_config",
    )
    if not base_geometry_path.is_file():
        raise FileNotFoundError(base_geometry_path)
    base_raw_loaded = yaml.safe_load(base_geometry_path.read_text(encoding="utf-8"))
    base_raw = _mapping(base_raw_loaded, "base geometry config")
    base_geometry = build_bwb_generator_config(base_raw)
    validate_bwb_generator_config(base_geometry)

    output_root = _resolve(
        campaign.get("output_root", f"artifacts/{name}"),
        base=repo_root,
        label="campaign.output_root",
    )
    airfoil_database = _resolve(
        campaign.get("airfoil_database", "data/airfoil_database"),
        base=repo_root,
        label="campaign.airfoil_database",
    )
    if not airfoil_database.is_dir():
        raise FileNotFoundError(airfoil_database)

    sampling = _mapping(campaign.get("sampling"), "campaign.sampling")
    method = _nonempty_string(
        sampling.get("method", "lhs"), "campaign.sampling.method"
    ).lower()
    if method not in {"lhs", "random", "center"}:
        raise ValueError("campaign.sampling.method must be lhs, random, or center")
    n_designs = int(sampling.get("n_designs", 1))
    sampling_seed = int(sampling.get("seed", 42))
    if n_designs < 1:
        raise ValueError("campaign.sampling.n_designs must be positive")

    design = _mapping(raw.get("design_space"), "design_space")
    varied_raw = _list(design.get("vary", []), "design_space.vary")
    varied = tuple(_nonempty_string(v, "design_space.vary[]") for v in varied_raw)
    if len(varied) != len(set(varied)):
        raise ValueError("design_space.vary contains duplicates")
    unknown = sorted(set(varied) - set(DESIGN_VARIABLES))
    if unknown:
        raise ValueError(f"design_space.vary contains unknown variables {unknown}")
    fixed_raw = _mapping(design.get("fixed", {}), "design_space.fixed")
    unknown_fixed = sorted(set(fixed_raw) - set(DESIGN_VARIABLES))
    if unknown_fixed:
        raise ValueError(f"design_space.fixed contains unknown variables {unknown_fixed}")
    overlap = sorted(set(varied) & set(fixed_raw))
    if overlap:
        raise ValueError(f"variables cannot be both varied and fixed: {overlap}")
    fixed = {
        key: _finite_float(value, f"design_space.fixed.{key}")
        for key, value in fixed_raw.items()
    }
    unspecified_policy = _nonempty_string(
        design.get("unspecified", "midpoint"), "design_space.unspecified"
    ).lower()
    if unspecified_policy not in {"midpoint", "vary"}:
        raise ValueError("design_space.unspecified must be midpoint or vary")
    if unspecified_policy == "vary":
        varied = tuple(
            name for name in DESIGN_VARIABLES if name not in fixed
        )

    controls = _mapping(raw.get("controls"), "controls")
    control_states = _parse_control_states(controls.get("states"))
    flow_states = _parse_flow_states(raw.get("flows"))

    geometry = _mapping(raw.get("geometry"), "geometry")
    low_fidelity = _mapping(raw.get("low_fidelity"), "low_fidelity")
    high_fidelity = _mapping(raw.get("high_fidelity"), "high_fidelity")
    dataset = _mapping(raw.get("dataset"), "dataset")

    high_control_ids = set(high_fidelity.get("control_states", []))
    missing_controls = sorted(high_control_ids - {s.id for s in control_states})
    if missing_controls:
        raise ValueError(
            f"high_fidelity.control_states contains unknown ids {missing_controls}"
        )
    high_flow_ids = set(high_fidelity.get("flow_states", []))
    missing_flows = sorted(high_flow_ids - {s.id for s in flow_states})
    if missing_flows:
        raise ValueError(
            f"high_fidelity.flow_states contains unknown ids {missing_flows}"
        )

    return CampaignConfig(
        source_path=source,
        repo_root=repo_root,
        raw=raw,
        name=name,
        base_geometry_path=base_geometry_path,
        base_geometry_raw=base_raw,
        base_geometry=base_geometry,
        output_root=output_root,
        airfoil_database=airfoil_database,
        sampling_method=method,
        sampling_seed=sampling_seed,
        n_designs=n_designs,
        varied_variables=varied,
        fixed_variables=fixed,
        unspecified_policy=unspecified_policy,
        fixed_station_airfoils=_station_airfoils(design, base_geometry),
        control_states=control_states,
        flow_states=flow_states,
        geometry=geometry,
        low_fidelity=low_fidelity,
        high_fidelity=high_fidelity,
        dataset=dataset,
    )

