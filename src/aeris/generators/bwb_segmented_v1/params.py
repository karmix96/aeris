"""
Typed configuration and sampled design-variable models for bwb_segmented_v1.

Defines:
- immutable generator configuration dataclasses
- immutable sampled design vectors
- conversion from raw config dictionaries into typed configuration objects
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PlotOutputsConfig:
    save_plot: bool = True
    build_aerosandbox: bool = True


@dataclass(frozen=True)
class GeneratorConfig:
    family: str
    version: str
    seed: int | None


@dataclass(frozen=True)
class ControlsConfig:
    n_points: int
    n_spline_inboard: int
    n_spline_outboard: int
    curvature_strength: float
    spline_split_ratio: float
    segment_length_variation: float
    sweep_variation: float


@dataclass(frozen=True)
class RangeConfig:
    min: float
    max: float


@dataclass(frozen=True)
class PlanformBoundsConfig:
    c1_m: RangeConfig
    c2_ratio: RangeConfig
    c3_ratio: RangeConfig
    c4_ratio: RangeConfig
    b_total_m: RangeConfig
    b3_ratio: RangeConfig
    split_ratio: RangeConfig
    sw1_deg: RangeConfig
    sw2_deg: RangeConfig
    sw3_deg: RangeConfig


@dataclass(frozen=True)
class SectionBoundsConfig:
    airfoil_name: str
    dihedral_root_deg: float

    twist_b0_deg: RangeConfig
    twist_b1_deg: RangeConfig
    twist_b2_deg: RangeConfig
    twist_b3_deg: RangeConfig

    dihedral_b1_deg: RangeConfig
    dihedral_b2_deg: RangeConfig
    dihedral_b3_deg: RangeConfig

@dataclass(frozen=True)
class ControlSurfaceSpanwiseConfig:
    start_frac: float
    end_frac: float


@dataclass(frozen=True)
class ControlSurfaceConfig:
    name: str
    family: str
    hinge_point: float
    symmetric: bool
    spanwise: ControlSurfaceSpanwiseConfig
    deflection_sign: str = "standard"
    side: str | None = None
    required: bool = False


@dataclass(frozen=True)
class ControlSurfacesConfig:
    enabled: bool
    surfaces: tuple[ControlSurfaceConfig, ...]

@dataclass(frozen=True)
class BWBDesignSample:
    # -----------------------------
    # Independent planform variables
    # -----------------------------
    c1_m: float
    c2_ratio: float
    c3_ratio: float
    c4_ratio: float
    b_total_m: float
    b3_ratio: float
    split_ratio: float
    sw1_deg: float
    sw2_deg: float
    sw3_deg: float

    # -----------------------------
    # Independent section variables
    # -----------------------------
    twist_b0_deg: float
    twist_b1_deg: float
    twist_b2_deg: float
    twist_b3_deg: float
    dihedral_b1_deg: float
    dihedral_b2_deg: float
    dihedral_b3_deg: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BWBGeneratorConfig:
    name: str
    generator: GeneratorConfig
    controls: ControlsConfig
    planform_bounds: PlanformBoundsConfig
    section_bounds: SectionBoundsConfig
    outputs: PlotOutputsConfig
    control_surfaces: ControlSurfacesConfig

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def design_variable_names(self) -> list[str]:
        return [
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
        ]

    def fixed_parameters(self) -> dict[str, Any]:
        return {
            "airfoil_name": self.section_bounds.airfoil_name,
            "dihedral_root_deg": self.section_bounds.dihedral_root_deg,
            "generator_family": self.generator.family,
            "generator_version": self.generator.version,
        }


def _require(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise KeyError(f"Missing required config key: {key}")
    return mapping[key]


def _range_cfg(mapping: dict[str, Any], key: str) -> RangeConfig:
    block = _require(mapping, key)
    return RangeConfig(
        min=float(_require(block, "min")),
        max=float(_require(block, "max")),
    )


def build_bwb_generator_config(config: dict[str, Any]) -> BWBGeneratorConfig:
    geometry_cfg = config.get("geometry", {})
    generator_cfg = geometry_cfg.get("generator", {})
    controls_cfg = geometry_cfg.get("controls", {})
    planform_cfg = geometry_cfg.get("planform_bounds", {})
    sections_cfg = geometry_cfg.get("section_bounds", {})
    outputs_cfg = geometry_cfg.get("outputs", {})
    control_surfaces_cfg = geometry_cfg.get("control_surfaces", {})

    return BWBGeneratorConfig(
        name=str(config.get("name", "wing_bwb")),
        generator=GeneratorConfig(
            family=str(_require(generator_cfg, "family")),
            version=str(_require(generator_cfg, "version")),
            seed=None if generator_cfg.get("seed") is None else int(generator_cfg["seed"]),
        ),
        controls=ControlsConfig(
            n_points=int(_require(controls_cfg, "n_points")),
            n_spline_inboard=int(_require(controls_cfg, "n_spline_inboard")),
            n_spline_outboard=int(_require(controls_cfg, "n_spline_outboard")),
            curvature_strength=float(_require(controls_cfg, "desired_curvature_strength")),
            spline_split_ratio=float(controls_cfg.get("spline_split_ratio", 0.55)),
            segment_length_variation=float(controls_cfg.get("segment_length_variation", 0.25)),
            sweep_variation=float(controls_cfg.get("sweep_variation", 0.10)),
        ),
        planform_bounds=PlanformBoundsConfig(
            c1_m=_range_cfg(planform_cfg, "c1_m"),
            c2_ratio=_range_cfg(planform_cfg, "c2_ratio"),
            c3_ratio=_range_cfg(planform_cfg, "c3_ratio"),
            c4_ratio=_range_cfg(planform_cfg, "c4_ratio"),
            b_total_m=_range_cfg(planform_cfg, "b_total_m"),
            b3_ratio=_range_cfg(planform_cfg, "b3_ratio"),
            split_ratio=_range_cfg(planform_cfg, "split_ratio"),
            sw1_deg=_range_cfg(planform_cfg, "sw1_deg"),
            sw2_deg=_range_cfg(planform_cfg, "sw2_deg"),
            sw3_deg=_range_cfg(planform_cfg, "sw3_deg"),
        ),
        section_bounds=SectionBoundsConfig(
            airfoil_name=str(sections_cfg.get("airfoil_name", "naca4412")),
            dihedral_root_deg=float(sections_cfg.get("dihedral_root_deg", 0.0)),
            twist_b0_deg=_range_cfg(sections_cfg, "twist_b0_deg"),
            twist_b1_deg=_range_cfg(sections_cfg, "twist_b1_deg"),
            twist_b2_deg=_range_cfg(sections_cfg, "twist_b2_deg"),
            twist_b3_deg=_range_cfg(sections_cfg, "twist_b3_deg"),
            dihedral_b1_deg=_range_cfg(sections_cfg, "dihedral_b1_deg"),
            dihedral_b2_deg=_range_cfg(sections_cfg, "dihedral_b2_deg"),
            dihedral_b3_deg=_range_cfg(sections_cfg, "dihedral_b3_deg"),
        ),
        outputs=PlotOutputsConfig(
            save_plot=bool(outputs_cfg.get("save_plot", True)),
            build_aerosandbox=bool(outputs_cfg.get("build_aerosandbox", True)),
        ),
        control_surfaces=_build_control_surfaces_config(control_surfaces_cfg),
    )

def _validate_control_surfaces_config(config: ControlSurfacesConfig) -> None:
    names: set[str] = set()

    if not config.enabled and len(config.surfaces) > 0:
        # This is allowed for now, but it is suspicious.
        # We keep it strict and explicit.
        raise ValueError(
            "geometry.control_surfaces.enabled is false, but surfaces are defined. "
            "Either set enabled: true or remove the surfaces block."
        )

    for surface in config.surfaces:
        if surface.name in names:
            raise ValueError(f"Duplicate control surface name: {surface.name!r}")
        names.add(surface.name)

        if surface.family not in {"trailing_edge"}:
            raise ValueError(
                f"Unsupported control surface family {surface.family!r}. "
                "v1 supports only 'trailing_edge'."
            )

        if not (0.0 < surface.hinge_point < 1.0):
            raise ValueError(
                f"Control surface {surface.name!r} has invalid hinge_point={surface.hinge_point}. "
                "Expected 0.0 < hinge_point < 1.0."
            )

        if not (0.0 <= surface.spanwise.start_frac < surface.spanwise.end_frac <= 1.0):
            raise ValueError(
                f"Control surface {surface.name!r} has invalid spanwise range "
                f"[{surface.spanwise.start_frac}, {surface.spanwise.end_frac}]. "
                "Expected 0.0 <= start_frac < end_frac <= 1.0."
            )

        if surface.symmetric:
            if surface.side is not None:
                raise ValueError(
                    f"Control surface {surface.name!r} is symmetric=True, so side must be omitted."
                )
        else:
            if surface.side not in {"left", "right"}:
                raise ValueError(
                    f"Control surface {surface.name!r} is symmetric=False, "
                    "so side must be 'left' or 'right'."
                )

        if surface.deflection_sign not in {"standard"}:
            raise ValueError(
                f"Unsupported deflection_sign {surface.deflection_sign!r} "
                f"for control surface {surface.name!r}."
            )

def _as_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise TypeError(f"{field_name} must be a bool, got {type(value).__name__}.")


def _as_float(value: Any, *, field_name: str) -> float:
    try:
        return float(value)
    except Exception as exc:
        raise TypeError(f"{field_name} must be numeric, got {value!r}.") from exc


def _as_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _build_control_surfaces_config(control_surfaces_cfg: dict[str, Any]) -> ControlSurfacesConfig:
    if not control_surfaces_cfg:
        return ControlSurfacesConfig(
            enabled=False,
            surfaces=(),
        )

    enabled = bool(control_surfaces_cfg.get("enabled", False))
    raw_surfaces = control_surfaces_cfg.get("surfaces", [])

    if not isinstance(raw_surfaces, list):
        raise TypeError("geometry.control_surfaces.surfaces must be a list.")

    surfaces: list[ControlSurfaceConfig] = []
    seen_names: set[str] = set()

    for i, raw in enumerate(raw_surfaces):
        if not isinstance(raw, dict):
            raise TypeError(f"geometry.control_surfaces.surfaces[{i}] must be a dict.")

        name = str(_require(raw, "name")).strip()
        family = str(_require(raw, "family")).strip()
        hinge_point = float(_require(raw, "hinge_point"))
        symmetric = bool(raw.get("symmetric", True))
        deflection_sign = str(raw.get("deflection_sign", "standard")).strip()
        side = raw.get("side", None)
        required = bool(raw.get("required", False))

        if side is not None:
            side = str(side).strip()

        spanwise_cfg = raw.get("spanwise", {})
        if not isinstance(spanwise_cfg, dict):
            raise TypeError(f"geometry.control_surfaces.surfaces[{i}].spanwise must be a dict.")

        start_frac = float(_require(spanwise_cfg, "start_frac"))
        end_frac = float(_require(spanwise_cfg, "end_frac"))

        if not name:
            raise ValueError(f"geometry.control_surfaces.surfaces[{i}].name must not be empty.")

        if name in seen_names:
            raise ValueError(f"Duplicate control surface name: {name!r}")
        seen_names.add(name)

        if family not in {"trailing_edge"}:
            raise ValueError(
                f"Unsupported control surface family {family!r}. "
                "Currently supported: 'trailing_edge'."
            )

        if not (0.0 < hinge_point < 1.0):
            raise ValueError(
                f"Control surface {name!r} has invalid hinge_point={hinge_point}. "
                "Expected 0.0 < hinge_point < 1.0."
            )

        if not (0.0 <= start_frac < end_frac <= 1.0):
            raise ValueError(
                f"Control surface {name!r} has invalid spanwise range "
                f"[{start_frac}, {end_frac}]. Expected 0.0 <= start_frac < end_frac <= 1.0."
            )

        if symmetric and side is not None:
            raise ValueError(
                f"Control surface {name!r} is symmetric=True, so side must be omitted."
            )

        if not symmetric and side not in {"left", "right"}:
            raise ValueError(
                f"Control surface {name!r} is symmetric=False, so side must be 'left' or 'right'."
            )

        if deflection_sign not in {"standard"}:
            raise ValueError(
                f"Unsupported deflection_sign {deflection_sign!r} for control surface {name!r}."
            )

        surfaces.append(
            ControlSurfaceConfig(
                name=name,
                family=family,
                hinge_point=hinge_point,
                symmetric=symmetric,
                spanwise=ControlSurfaceSpanwiseConfig(
                    start_frac=start_frac,
                    end_frac=end_frac,
                ),
                deflection_sign=deflection_sign,
                side=side,
                required=required,
            )
        )

    if not enabled and surfaces:
        raise ValueError(
            "geometry.control_surfaces.enabled is false, but surfaces are defined."
        )

    return ControlSurfacesConfig(
        enabled=enabled,
        surfaces=tuple(surfaces),
    )