"""Typed configuration for the optional pyGeo BWB realization backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping, got {type(value).__name__}.")
    return dict(value)


def _bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool, got {type(value).__name__}.")
    return value


def _int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer, got bool.")
    if isinstance(value, float) and not value.is_integer():
        raise TypeError(f"{field_name} must be an integer, got {value!r}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be an integer, got {value!r}.") from exc


def _optional_int(value: Any, field_name: str) -> int | None:
    return None if value is None else _int(value, field_name)


def _float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric, got bool.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be numeric, got {value!r}.") from exc


def _str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string.")
    return value.strip()


@dataclass(frozen=True)
class PyGeoExtractionConfig:
    spanwise_sections: int = 25
    chordwise_points: int = 241
    cst_order: int = 8


@dataclass(frozen=True)
class PyGeoSurfaceSamplingConfig:
    chordwise_points: int = 141
    spanwise_points: int = 121


@dataclass(frozen=True)
class PyGeoQualityConfig:
    warn_plane_warp_chord: float = 3.0e-3
    max_plane_warp_chord: float = 1.0e-2
    max_cst_rms_chord: float = 1.0e-3
    fail_on_rejection: bool = True


@dataclass(frozen=True)
class PyGeoControlCommandsConfig:
    delta_e_sym_deg: float = 0.0
    delta_a_diff_deg: float = 0.0

    @property
    def right_deflection_deg(self) -> float:
        return self.delta_e_sym_deg + self.delta_a_diff_deg

    @property
    def left_deflection_deg(self) -> float:
        return self.delta_e_sym_deg - self.delta_a_diff_deg


@dataclass(frozen=True)
class PyGeoPhysicalCadConfig:
    enabled: bool = False
    topology: str = "split_elevon"
    hinge_gap_fraction: float = 0.005
    boundary_clearance_fraction: float = 0.005
    design_deflection_limit_deg: float = 20.0
    chordwise_points: int = 81
    minimum_te_thickness_fraction: float = 5.0e-4
    tessellation_tolerance_m: float = 7.5e-4
    tessellation_angular_tolerance_rad: float = 0.12
    max_master_to_cad_deviation_cref: float = 0.005
    fail_on_invalid: bool = True


@dataclass(frozen=True)
class PyGeoOutputsConfig:
    write_iges: bool = True
    write_tecplot: bool = True
    write_surface_npz: bool = True
    write_section_dat: bool = True
    write_step: bool = True
    verify_step_import: bool = True
    write_brep: bool = False
    write_stl: bool = True
    write_obj: bool = True
    write_vtk: bool = True
    write_cad_npz: bool = True
    save_visualization: bool = True
    visualization_dpi: int = 180


@dataclass(frozen=True)
class PyGeoBackendConfig:
    """Independent realization switch and settings for pyGeo.

    enabled is orthogonal to outputs.build_aerosandbox, so Aeris can realize
    the same authored BWB with either backend or with both.
    """

    enabled: bool = False
    airfoil_database: str = "data/airfoil_database"
    k_span: int = 3
    frame_mode: str = "aeris_frame"
    n_ctl: int | None = None
    tip: str = "none"
    tip_scale: float = 0.25
    enforce_flat_root_panel: bool = True
    extraction: PyGeoExtractionConfig = PyGeoExtractionConfig()
    surface_sampling: PyGeoSurfaceSamplingConfig = PyGeoSurfaceSamplingConfig()
    quality: PyGeoQualityConfig = PyGeoQualityConfig()
    commands: PyGeoControlCommandsConfig = PyGeoControlCommandsConfig()
    physical_cad: PyGeoPhysicalCadConfig = PyGeoPhysicalCadConfig()
    outputs: PyGeoOutputsConfig = PyGeoOutputsConfig()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_pygeo_backend_config(raw: Any) -> PyGeoBackendConfig:
    """Parse geometry.pygeo; an absent block keeps the backend disabled."""

    cfg = _mapping(raw, "geometry.pygeo")
    extraction = _mapping(cfg.get("extraction"), "geometry.pygeo.extraction")
    sampling = _mapping(cfg.get("surface_sampling"), "geometry.pygeo.surface_sampling")
    quality = _mapping(cfg.get("quality"), "geometry.pygeo.quality")
    commands = _mapping(cfg.get("commands"), "geometry.pygeo.commands")
    physical = _mapping(cfg.get("physical_cad"), "geometry.pygeo.physical_cad")
    outputs = _mapping(cfg.get("outputs"), "geometry.pygeo.outputs")

    parsed = PyGeoBackendConfig(
        enabled=_bool(cfg.get("enabled", False), "geometry.pygeo.enabled"),
        airfoil_database=_str(
            cfg.get("airfoil_database", "data/airfoil_database"),
            "geometry.pygeo.airfoil_database",
        ),
        k_span=_int(cfg.get("k_span", 3), "geometry.pygeo.k_span"),
        frame_mode=_str(cfg.get("frame_mode", "aeris_frame"), "geometry.pygeo.frame_mode").lower(),
        n_ctl=_optional_int(cfg.get("n_ctl"), "geometry.pygeo.n_ctl"),
        tip=_str(cfg.get("tip", "none"), "geometry.pygeo.tip").lower(),
        tip_scale=_float(cfg.get("tip_scale", 0.25), "geometry.pygeo.tip_scale"),
        enforce_flat_root_panel=_bool(
            cfg.get("enforce_flat_root_panel", True),
            "geometry.pygeo.enforce_flat_root_panel",
        ),
        extraction=PyGeoExtractionConfig(
            spanwise_sections=_int(
                extraction.get("spanwise_sections", 25),
                "geometry.pygeo.extraction.spanwise_sections",
            ),
            chordwise_points=_int(
                extraction.get("chordwise_points", 241),
                "geometry.pygeo.extraction.chordwise_points",
            ),
            cst_order=_int(
                extraction.get("cst_order", 8),
                "geometry.pygeo.extraction.cst_order",
            ),
        ),
        surface_sampling=PyGeoSurfaceSamplingConfig(
            chordwise_points=_int(
                sampling.get("chordwise_points", 141),
                "geometry.pygeo.surface_sampling.chordwise_points",
            ),
            spanwise_points=_int(
                sampling.get("spanwise_points", 121),
                "geometry.pygeo.surface_sampling.spanwise_points",
            ),
        ),
        quality=PyGeoQualityConfig(
            warn_plane_warp_chord=_float(
                quality.get("warn_plane_warp_chord", 3.0e-3),
                "geometry.pygeo.quality.warn_plane_warp_chord",
            ),
            max_plane_warp_chord=_float(
                quality.get("max_plane_warp_chord", 1.0e-2),
                "geometry.pygeo.quality.max_plane_warp_chord",
            ),
            max_cst_rms_chord=_float(
                quality.get("max_cst_rms_chord", 1.0e-3),
                "geometry.pygeo.quality.max_cst_rms_chord",
            ),
            fail_on_rejection=_bool(
                quality.get("fail_on_rejection", True),
                "geometry.pygeo.quality.fail_on_rejection",
            ),
        ),
        commands=PyGeoControlCommandsConfig(
            delta_e_sym_deg=_float(
                commands.get("delta_e_sym_deg", 0.0),
                "geometry.pygeo.commands.delta_e_sym_deg",
            ),
            delta_a_diff_deg=_float(
                commands.get("delta_a_diff_deg", 0.0),
                "geometry.pygeo.commands.delta_a_diff_deg",
            ),
        ),
        physical_cad=PyGeoPhysicalCadConfig(
            enabled=_bool(
                physical.get("enabled", False),
                "geometry.pygeo.physical_cad.enabled",
            ),
            topology=_str(
                physical.get("topology", "split_elevon"),
                "geometry.pygeo.physical_cad.topology",
            ).lower(),
            hinge_gap_fraction=_float(
                physical.get("hinge_gap_fraction", 0.005),
                "geometry.pygeo.physical_cad.hinge_gap_fraction",
            ),
            boundary_clearance_fraction=_float(
                physical.get("boundary_clearance_fraction", 0.005),
                "geometry.pygeo.physical_cad.boundary_clearance_fraction",
            ),
            design_deflection_limit_deg=_float(
                physical.get("design_deflection_limit_deg", 20.0),
                "geometry.pygeo.physical_cad.design_deflection_limit_deg",
            ),
            chordwise_points=_int(
                physical.get("chordwise_points", 81),
                "geometry.pygeo.physical_cad.chordwise_points",
            ),
            minimum_te_thickness_fraction=_float(
                physical.get("minimum_te_thickness_fraction", 5.0e-4),
                "geometry.pygeo.physical_cad.minimum_te_thickness_fraction",
            ),
            tessellation_tolerance_m=_float(
                physical.get("tessellation_tolerance_m", 7.5e-4),
                "geometry.pygeo.physical_cad.tessellation_tolerance_m",
            ),
            tessellation_angular_tolerance_rad=_float(
                physical.get("tessellation_angular_tolerance_rad", 0.12),
                "geometry.pygeo.physical_cad.tessellation_angular_tolerance_rad",
            ),
            max_master_to_cad_deviation_cref=_float(
                physical.get("max_master_to_cad_deviation_cref", 0.005),
                "geometry.pygeo.physical_cad.max_master_to_cad_deviation_cref",
            ),
            fail_on_invalid=_bool(
                physical.get("fail_on_invalid", True),
                "geometry.pygeo.physical_cad.fail_on_invalid",
            ),
        ),
        outputs=PyGeoOutputsConfig(
            write_iges=_bool(outputs.get("write_iges", True), "geometry.pygeo.outputs.write_iges"),
            write_tecplot=_bool(
                outputs.get("write_tecplot", True),
                "geometry.pygeo.outputs.write_tecplot",
            ),
            write_surface_npz=_bool(
                outputs.get("write_surface_npz", True),
                "geometry.pygeo.outputs.write_surface_npz",
            ),
            write_section_dat=_bool(
                outputs.get("write_section_dat", True),
                "geometry.pygeo.outputs.write_section_dat",
            ),
            write_step=_bool(outputs.get("write_step", True), "geometry.pygeo.outputs.write_step"),
            verify_step_import=_bool(
                outputs.get("verify_step_import", True),
                "geometry.pygeo.outputs.verify_step_import",
            ),
            write_brep=_bool(outputs.get("write_brep", False), "geometry.pygeo.outputs.write_brep"),
            write_stl=_bool(outputs.get("write_stl", True), "geometry.pygeo.outputs.write_stl"),
            write_obj=_bool(outputs.get("write_obj", True), "geometry.pygeo.outputs.write_obj"),
            write_vtk=_bool(outputs.get("write_vtk", True), "geometry.pygeo.outputs.write_vtk"),
            write_cad_npz=_bool(
                outputs.get("write_cad_npz", True),
                "geometry.pygeo.outputs.write_cad_npz",
            ),
            save_visualization=_bool(
                outputs.get("save_visualization", True),
                "geometry.pygeo.outputs.save_visualization",
            ),
            visualization_dpi=_int(
                outputs.get("visualization_dpi", 180),
                "geometry.pygeo.outputs.visualization_dpi",
            ),
        ),
    )
    validate_pygeo_backend_config(parsed)
    return parsed


def validate_pygeo_backend_config(config: PyGeoBackendConfig) -> None:
    if config.k_span < 2:
        raise ValueError("geometry.pygeo.k_span must be at least 2")
    if config.frame_mode not in {
        "aeris_frame",
        "asb_frame",
        "global_y",
        "dihedral_euler",
    }:
        raise ValueError(
            "geometry.pygeo.frame_mode must be aeris_frame, asb_frame, global_y, or dihedral_euler"
        )
    if config.n_ctl is not None and config.n_ctl < 2:
        raise ValueError("geometry.pygeo.n_ctl must be at least 2 when provided")
    if config.tip not in {"none", "rounded", "pinched"}:
        raise ValueError("geometry.pygeo.tip must be none, rounded, or pinched")
    if config.tip_scale <= 0.0:
        raise ValueError("geometry.pygeo.tip_scale must be positive")
    if config.extraction.spanwise_sections < 4:
        raise ValueError("geometry.pygeo.extraction.spanwise_sections must be at least 4")
    if config.extraction.cst_order < 2:
        raise ValueError("geometry.pygeo.extraction.cst_order must be at least 2")
    if config.extraction.chordwise_points < max(21, config.extraction.cst_order + 3):
        raise ValueError("geometry.pygeo.extraction.chordwise_points is too small")
    if config.surface_sampling.chordwise_points < 3:
        raise ValueError("geometry.pygeo.surface_sampling.chordwise_points must be at least 3")
    if config.surface_sampling.spanwise_points < 2:
        raise ValueError("geometry.pygeo.surface_sampling.spanwise_points must be at least 2")
    if not (0.0 <= config.quality.warn_plane_warp_chord <= config.quality.max_plane_warp_chord):
        raise ValueError("pyGeo plane-warp warning must lie within the rejection limit")
    if config.quality.max_cst_rms_chord <= 0.0:
        raise ValueError("geometry.pygeo.quality.max_cst_rms_chord must be positive")

    physical = config.physical_cad
    if physical.topology != "split_elevon":
        raise ValueError("geometry.pygeo.physical_cad.topology supports only split_elevon")
    if not 0.0 <= physical.hinge_gap_fraction < 0.15:
        raise ValueError("pyGeo physical CAD hinge_gap_fraction must be in [0, 0.15)")
    if not 0.0 <= physical.boundary_clearance_fraction < 0.05:
        raise ValueError("pyGeo physical CAD boundary_clearance_fraction must be in [0, 0.05)")
    if not 0.0 <= physical.design_deflection_limit_deg <= 60.0:
        raise ValueError("pyGeo physical CAD design_deflection_limit_deg must be in [0, 60]")
    if physical.chordwise_points < 21:
        raise ValueError("pyGeo physical CAD chordwise_points must be at least 21")
    if not 0.0 <= physical.minimum_te_thickness_fraction <= 0.02:
        raise ValueError("pyGeo physical CAD minimum_te_thickness_fraction must be in [0, 0.02]")
    if physical.tessellation_tolerance_m <= 0.0:
        raise ValueError("pyGeo physical CAD tessellation_tolerance_m must be positive")
    if physical.tessellation_angular_tolerance_rad <= 0.0:
        raise ValueError("pyGeo physical CAD angular tolerance must be positive")
    if physical.max_master_to_cad_deviation_cref <= 0.0:
        raise ValueError("pyGeo physical CAD master-to-CAD limit must be positive")
    if config.outputs.visualization_dpi < 50:
        raise ValueError("geometry.pygeo.outputs.visualization_dpi must be at least 50")

    max_command = max(
        abs(config.commands.right_deflection_deg),
        abs(config.commands.left_deflection_deg),
    )
    if physical.enabled and max_command > physical.design_deflection_limit_deg:
        raise ValueError("pyGeo control command exceeds physical_cad.design_deflection_limit_deg")
