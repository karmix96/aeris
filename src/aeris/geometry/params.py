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

    return BWBGeneratorConfig(
        name=str(config.get("name", "wing_bwb")),
        generator=GeneratorConfig(
            family=str(generator_cfg.get("family", "bwb_segmented")),
            version=str(generator_cfg.get("version", "v1")),
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
    )