"""Production orchestration for the optional pyGeo BWB realization backend."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from aeris.common.paths import get_project_root
from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    BWBGeneratorConfig,
)
from aeris.generators.bwb_segmented_v1.planform import PlanformResult
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
    ExtractedSection,
    PyGeoBuild,
    StationDefinition,
    build_pygeo,
    extract_sections,
    realised_reference_metrics,
    sample_main_surfaces,
    stations_from_records,
)
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult

PYGEO_BACKEND_SCHEMA = "aeris.bwb_segmented_v1.pygeo.v1"


@dataclass(frozen=True)
class PyGeoControlState:
    enabled: bool
    name: str
    family: str
    hinge_point: float
    symmetric: bool
    start_frac: float
    end_frac: float
    delta_e_sym_deg: float
    delta_a_diff_deg: float

    @property
    def right_deflection_deg(self) -> float:
        return self.delta_e_sym_deg + self.delta_a_diff_deg

    @property
    def left_deflection_deg(self) -> float:
        return self.delta_e_sym_deg - self.delta_a_diff_deg

    def geometry_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "name": self.name,
            "family": self.family,
            "hinge_point": self.hinge_point,
            "symmetric": self.symmetric,
            "start_frac": self.start_frac,
            "end_frac": self.end_frac,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.geometry_dict(),
            "delta_e_sym_deg": self.delta_e_sym_deg,
            "delta_a_diff_deg": self.delta_a_diff_deg,
            "right_deflection_deg": self.right_deflection_deg,
            "left_deflection_deg": self.left_deflection_deg,
            "mixing": {
                "right": "delta_e_sym_deg + delta_a_diff_deg",
                "left": "delta_e_sym_deg - delta_a_diff_deg",
            },
            "sign_convention": "positive is trailing-edge down",
        }


@dataclass
class PyGeoGeometryResult:
    geometry_id: str
    pygeo: PyGeoBuild
    stations: tuple[StationDefinition, ...]
    extracted: tuple[ExtractedSection, ...]
    upper_surface: np.ndarray
    lower_surface: np.ndarray
    metrics: dict[str, Any]
    control: PyGeoControlState
    output_dir: Path
    artifacts: dict[str, Any]
    exports: dict[str, str]
    physical_cad: dict[str, Any] | None = None

    @property
    def reference_values(self) -> dict[str, Any]:
        return {
            "span_m": self.metrics["b_ref_y_m"],
            "span_yz_m": self.metrics["b_ref_yz_m"],
            "area_m2": self.metrics["s_ref_xy_m2"],
            "area_yz_m2": self.metrics["s_ref_yz_m2"],
            "mean_aerodynamic_chord_m": self.metrics["c_ref_m"],
            "aspect_ratio": self.metrics["aspect_ratio_xy"],
            "volume_m3": self.metrics["volume_m3"],
            "wetted_area_m2": self.metrics["wetted_area_m2"],
        }

    def summary_dict(self) -> dict[str, Any]:
        return {
            "schema": PYGEO_BACKEND_SCHEMA,
            "enabled": True,
            "engine": "MDOLab pyGeo",
            "geometry_id": self.geometry_id,
            "master_geometry": "neutral pyGeo B-spline loft",
            "reference_values": self.reference_values,
            "metrics": self.metrics,
            "quality_status": self.metrics["geometry_qc"],
            "airfoil_names": [station.airfoil_name for station in self.stations],
            "control_surface": self.control.to_dict(),
            "pygeo": {
                "k_span": self.pygeo.k_span,
                "frame_mode": self.pygeo.frame_mode,
                "rot_x_deg": self.pygeo.rot_x_deg.tolist(),
                "rot_y_deg": self.pygeo.rot_y_deg.tolist(),
                "rot_z_deg": self.pygeo.rot_z_deg.tolist(),
                "thickness_scale": self.pygeo.thickness_scale.tolist(),
                "frame_reconstruction_error": self.pygeo.frame_reconstruction_error,
                "stdout": self.pygeo.stdout,
            },
            "exports": self.exports,
            "artifacts": self.artifacts,
            "physical_cad": self.physical_cad,
        }


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def _write_section_dat(path: Path, section: ExtractedSection) -> None:
    lines = [path.stem]
    lines.extend(f"{float(x): .10f} {float(z): .10f}" for x, z in section.direct_coordinates)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_airfoil_database(config: BWBGeneratorConfig) -> Path:
    database = Path(config.pygeo.airfoil_database).expanduser()
    if not database.is_absolute():
        database = get_project_root() / database
    database = database.resolve()
    if not database.is_dir():
        raise FileNotFoundError(f"geometry.pygeo.airfoil_database is not a directory: {database}")
    return database


def _control_state(config: BWBGeneratorConfig) -> PyGeoControlState:
    commands = config.pygeo.commands
    if not config.control_surfaces.enabled or not config.control_surfaces.surfaces:
        return PyGeoControlState(
            enabled=False,
            name="none",
            family="trailing_edge",
            hinge_point=0.75,
            symmetric=True,
            start_frac=0.0,
            end_frac=0.0,
            delta_e_sym_deg=commands.delta_e_sym_deg,
            delta_a_diff_deg=commands.delta_a_diff_deg,
        )
    surface = config.control_surfaces.surfaces[0]
    return PyGeoControlState(
        enabled=True,
        name=surface.name,
        family=surface.family,
        hinge_point=surface.hinge_point,
        symmetric=surface.symmetric,
        start_frac=surface.spanwise.start_frac,
        end_frac=surface.spanwise.end_frac,
        delta_e_sym_deg=commands.delta_e_sym_deg,
        delta_a_diff_deg=commands.delta_a_diff_deg,
    )


def _span_fractions(
    count: int,
    section_geometry: SectionGeometryResult,
    control: PyGeoControlState,
) -> np.ndarray:
    semispan = max(float(section.y_m) for section in section_geometry.sections)
    fractions = set(float(value) for value in np.linspace(0.0, 1.0, count))
    fractions.update(
        float(np.clip(float(y) / semispan, 0.0, 1.0)) for y in section_geometry.group_boundary_y
    )
    if control.enabled:
        fractions.update((control.start_frac, control.end_frac))
    return np.asarray(sorted(fractions), dtype=float)


def _polygon_area(coordinates: np.ndarray) -> float:
    points = np.asarray(coordinates, dtype=float)
    x, z = points[:, 0], points[:, 1]
    return abs(0.5 * float(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z)))


def _quad_strip_area(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape:
        raise ValueError("Extracted section surface arrays must have equal shapes")
    total = 0.0
    for index in range(len(first) - 1):
        p00, p10 = first[index], first[index + 1]
        p01, p11 = second[index], second[index + 1]
        total += 0.5 * float(np.linalg.norm(np.cross(p10 - p00, p11 - p00)))
        total += 0.5 * float(np.linalg.norm(np.cross(p11 - p00, p01 - p00)))
    return total


def _volume_and_wetted_area(
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


def _control_metrics(
    sections: Sequence[ExtractedSection],
    control: PyGeoControlState,
    s_ref_m2: float,
) -> dict[str, Any]:
    if not control.enabled:
        return {
            "control_surface_enabled": False,
            "control_surface_name": control.name,
            "control_surface_area_xy_m2": 0.0,
            "control_surface_area_yz_m2": 0.0,
            "control_surface_area_ratio_sref": 0.0,
            "control_hinge_length_m": 0.0,
            "control_span_m": 0.0,
            "control_geometry_state": "disabled",
        }

    ordered = sorted(sections, key=lambda section: section.span_fraction)
    fractions = np.asarray([section.span_fraction for section in ordered])
    sample_fractions = np.linspace(control.start_frac, control.end_frac, 201)

    def interp(values: Sequence[float]) -> np.ndarray:
        return np.interp(sample_fractions, fractions, np.asarray(values, dtype=float))

    leading = np.column_stack(
        [interp([section.le_xyz_m[axis] for section in ordered]) for axis in range(3)]
    )
    trailing = np.column_stack(
        [interp([section.te_xyz_m[axis] for section in ordered]) for axis in range(3)]
    )
    chords = interp([section.chord_m for section in ordered])
    control_chords = (1.0 - control.hinge_point) * chords
    hinge = leading + control.hinge_point * (trailing - leading)
    hinge_arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(hinge, axis=0), axis=1))])
    area_xy = 2.0 * float(np.trapezoid(control_chords, hinge[:, 1]))
    area_yz = 2.0 * float(np.trapezoid(control_chords, hinge_arc))
    return {
        "control_surface_enabled": True,
        "control_surface_name": control.name,
        "control_surface_area_xy_m2": area_xy,
        "control_surface_area_yz_m2": area_yz,
        "control_surface_area_ratio_sref": area_xy / max(s_ref_m2, 1.0e-12),
        "control_hinge_length_m": 2.0 * float(hinge_arc[-1]),
        "control_span_m": 2.0 * abs(float(hinge[-1, 1] - hinge[0, 1])),
        "control_hinge_fraction": control.hinge_point,
        "control_span_start_fraction": control.start_frac,
        "control_span_end_fraction": control.end_frac,
        "delta_e_sym_deg": control.delta_e_sym_deg,
        "delta_a_diff_deg": control.delta_a_diff_deg,
        "right_deflection_deg": control.right_deflection_deg,
        "left_deflection_deg": control.left_deflection_deg,
        "control_geometry_state": "neutral_master_plus_physical_cad_when_enabled",
    }


def _geometry_id(
    sample: BWBDesignSample,
    config: BWBGeneratorConfig,
    stations: Sequence[StationDefinition],
    control: PyGeoControlState,
) -> str:
    physical = config.pygeo.physical_cad
    payload = {
        "sample": sample.to_dict(),
        "airfoils": [
            {
                "index": station.index,
                "name": station.airfoil_name,
                "path": str(station.airfoil_path),
            }
            for station in stations
        ],
        "pygeo": {
            "k_span": config.pygeo.k_span,
            "frame_mode": config.pygeo.frame_mode,
            "n_ctl": config.pygeo.n_ctl,
            "tip": config.pygeo.tip,
            "tip_scale": config.pygeo.tip_scale,
        },
        "control_geometry": control.geometry_dict(),
        "physical_cad_geometry": {
            key: value
            for key, value in asdict(physical).items()
            if key
            not in {
                "tessellation_tolerance_m",
                "tessellation_angular_tolerance_rad",
                "max_master_to_cad_deviation_cref",
                "fail_on_invalid",
            }
        },
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"aeris_pygeo_bwb_{digest[:20]}"


def _build_metrics(
    *,
    planform: PlanformResult,
    stations: Sequence[StationDefinition],
    extracted: Sequence[ExtractedSection],
    upper: np.ndarray,
    lower: np.ndarray,
    pygeo: PyGeoBuild,
    control: PyGeoControlState,
    config: BWBGeneratorConfig,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        **realised_reference_metrics(extracted, symmetric=True),
        **_volume_and_wetted_area(extracted),
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
        _control_metrics(
            extracted,
            control,
            s_ref_m2=float(metrics["s_ref_xy_m2"]),
        )
    )
    quality = config.pygeo.quality
    metrics.update(
        {
            "plane_warp_warning_chord": quality.warn_plane_warp_chord,
            "plane_warp_limit_chord": quality.max_plane_warp_chord,
            "cst_rms_limit_chord": quality.max_cst_rms_chord,
            "section_planarity": (
                "warning_planarize_for_2d_use"
                if metrics["max_plane_warp_chord"] > quality.warn_plane_warp_chord
                else "within_warning_limit"
            ),
        }
    )
    accepted = (
        metrics["max_plane_warp_chord"] <= quality.max_plane_warp_chord
        and metrics["max_cst_rms_chord"] <= quality.max_cst_rms_chord
        and metrics["all_cst_valid"]
    )
    metrics["geometry_qc"] = "accepted" if accepted else "rejected"
    return metrics


def _equal_axes_3d(axis: Any, points: np.ndarray) -> None:
    mins = np.min(points, axis=0)
    maxs = np.max(points, axis=0)
    center = 0.5 * (mins + maxs)
    radius = 0.52 * max(float(np.max(maxs - mins)), 1.0e-6)
    axis.set_xlim(center[0] - radius, center[0] + radius)
    axis.set_ylim(center[1] - radius, center[1] + radius)
    axis.set_zlim(center[2] - 0.45 * radius, center[2] + 0.45 * radius)
    axis.set_box_aspect((1.0, 1.0, 0.45))


def _plot_geometry(result: PyGeoGeometryResult, path: Path, dpi: int) -> None:
    figure = plt.figure(figsize=(11.5, 7.5))
    axis = figure.add_subplot(111, projection="3d")
    for surface, color in (
        (result.upper_surface, "#2563EB"),
        (result.lower_surface, "#14B8A6"),
    ):
        for sign in (1.0, -1.0):
            plotted = surface.copy()
            plotted[:, :, 1] *= sign
            axis.plot_surface(
                plotted[:, :, 0],
                plotted[:, :, 1],
                plotted[:, :, 2],
                color=color,
                alpha=0.90,
                linewidth=0.0,
                antialiased=True,
            )
    points = np.vstack(
        [
            result.upper_surface.reshape(-1, 3),
            result.lower_surface.reshape(-1, 3),
            result.upper_surface.reshape(-1, 3) * np.array([1.0, -1.0, 1.0]),
        ]
    )
    _equal_axes_3d(axis, points)
    axis.view_init(elev=24, azim=-128)
    axis.set_xlabel("x [m]")
    axis.set_ylabel("y [m]")
    axis.set_zlabel("z [m]")
    axis.set_title(f"Aeris pyGeo BWB loft\n{result.geometry_id}")
    figure.tight_layout()
    figure.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def save_backend_comparison_plot(
    result: PyGeoGeometryResult,
    aerosandbox_wing: Any,
    path: Path,
    *,
    comparison: Mapping[str, Any] | None = None,
    dpi: int = 180,
) -> None:
    """Save a direct visual overlay of the two independently realised geometries."""

    vertices, faces = aerosandbox_wing.mesh_body(
        method="quad",
        chordwise_resolution=41,
        mesh_surface=True,
        mesh_tips=True,
        mesh_trailing_edge=True,
        mesh_symmetric=True,
    )
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=int)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2:
        raise ValueError("Unexpected AeroSandbox mesh shape for backend comparison")

    figure = plt.figure(figsize=(15, 7))
    axis_3d = figure.add_subplot(121, projection="3d")
    axis_top = figure.add_subplot(122)

    asb_collection = Poly3DCollection(
        vertices[faces],
        facecolor="#F59E0B",
        edgecolor="#B45309",
        linewidth=0.08,
        alpha=0.22,
    )
    axis_3d.add_collection3d(asb_collection)

    for surface, color in (
        (result.upper_surface, "#2563EB"),
        (result.lower_surface, "#14B8A6"),
    ):
        for sign in (1.0, -1.0):
            plotted = surface.copy()
            plotted[:, :, 1] *= sign
            axis_3d.plot_surface(
                plotted[:, :, 0],
                plotted[:, :, 1],
                plotted[:, :, 2],
                color=color,
                linewidth=0.0,
                antialiased=True,
                alpha=0.55,
            )

    mirrored_upper = result.upper_surface.copy()
    mirrored_upper[:, :, 1] *= -1.0
    all_points = np.vstack(
        [
            vertices,
            result.upper_surface.reshape(-1, 3),
            result.lower_surface.reshape(-1, 3),
            mirrored_upper.reshape(-1, 3),
        ]
    )
    _equal_axes_3d(axis_3d, all_points)
    axis_3d.view_init(elev=24, azim=-128)
    axis_3d.set_xlabel("x [m]")
    axis_3d.set_ylabel("y [m]")
    axis_3d.set_zlabel("z [m]")
    axis_3d.set_title("Independent 3-D realizations")

    axis_top.scatter(
        vertices[:, 0],
        vertices[:, 1],
        s=1.2,
        color="#D97706",
        alpha=0.22,
        rasterized=True,
    )
    surface = result.upper_surface
    chord_indices = np.unique(np.linspace(0, surface.shape[0] - 1, 13, dtype=int))
    span_indices = np.unique(np.linspace(0, surface.shape[1] - 1, 17, dtype=int))
    for sign in (1.0, -1.0):
        for index in chord_indices:
            axis_top.plot(
                surface[index, :, 0],
                sign * surface[index, :, 1],
                color="#2563EB",
                linewidth=0.55,
                alpha=0.72,
            )
        for index in span_indices:
            axis_top.plot(
                surface[:, index, 0],
                sign * surface[:, index, 1],
                color="#2563EB",
                linewidth=0.45,
                alpha=0.55,
            )
    axis_top.set_aspect("equal", adjustable="box")
    axis_top.grid(True, alpha=0.2)
    axis_top.set_xlabel("x [m]")
    axis_top.set_ylabel("y [m]")
    axis_top.set_title("Top-view overlay")
    axis_top.legend(
        handles=[
            Line2D([0], [0], color="#2563EB", lw=2, label="pyGeo loft"),
            Line2D([0], [0], color="#D97706", lw=2, label="AeroSandbox body"),
        ],
        loc="best",
    )

    if comparison is not None:
        metrics = comparison.get("metrics", {})
        labels = {
            "span_m": "span",
            "area_m2": "area",
            "aspect_ratio": "AR",
            "mean_aerodynamic_chord_m": "MAC",
            "volume_m3": "volume",
        }
        lines = []
        for key, label in labels.items():
            row = metrics.get(key)
            if row is not None and row.get("relative_delta_percent") is not None:
                lines.append(f"{label}: {float(row['relative_delta_percent']):+.3f}%")
        if lines:
            axis_top.text(
                0.02,
                0.02,
                "pyGeo - AeroSandbox\n" + "\n".join(lines),
                transform=axis_top.transAxes,
                va="bottom",
                ha="left",
                fontsize=9,
                bbox={
                    "boxstyle": "round,pad=0.35",
                    "facecolor": "white",
                    "edgecolor": "#94A3B8",
                    "alpha": 0.9,
                },
            )

    figure.suptitle(
        f"Aeris BWB backend comparison · no geometry-object translation\n{result.geometry_id}"
    )
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=int(dpi), bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _plot_sections(result: PyGeoGeometryResult, path: Path, dpi: int) -> None:
    targets = np.linspace(0.0, 1.0, 4)
    available = np.asarray([section.span_fraction for section in result.extracted], dtype=float)
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    for axis, target in zip(axes.flat, targets, strict=True):
        section = result.extracted[int(np.argmin(np.abs(available - target)))]
        direct = section.direct_coordinates
        axis.plot(direct[:, 0], direct[:, 1], color="#2563EB", linewidth=1.8)
        cst = section.cst.coordinates(n_per_surface=181)
        axis.plot(
            cst[:, 0],
            cst[:, 1],
            color="#DC2626",
            linestyle="--",
            linewidth=1.0,
            label="CST fit",
        )
        axis.axhline(0.0, color="black", linewidth=0.5, alpha=0.4)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(True, alpha=0.2)
        axis.set_title(f"y/b={section.span_fraction:.3f} · t/c={section.thickness_ratio:.4f}")
        axis.text(
            0.02,
            0.04,
            f"CST RMS={section.cst_rms_chord:.2e}",
            transform=axis.transAxes,
            fontsize=8,
            va="bottom",
        )
    axes[0, 0].legend(loc="upper right", fontsize=8)
    figure.supxlabel("x/c")
    figure.supylabel("z/c")
    figure.suptitle("Realised pyGeo sections and CST fits")
    figure.tight_layout()
    figure.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _export_base_artifacts(result: PyGeoGeometryResult, config: BWBGeneratorConfig) -> None:
    output = result.output_dir
    output.mkdir(parents=True, exist_ok=True)
    sections_dir = output / "sections"
    sections_dir.mkdir(exist_ok=True)

    authored_path = output / "authored_stations.csv"
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
        for station in result.stations
    ]
    _write_csv(authored_path, authored_rows, list(authored_rows[0]))
    result.artifacts["authored_stations_csv"] = str(authored_path)

    extracted_path = output / "extracted_sections.csv"
    extracted_rows = [section.as_metrics_row() for section in result.extracted]
    _write_csv(extracted_path, extracted_rows, list(extracted_rows[0]))
    result.artifacts["extracted_sections_csv"] = str(extracted_path)

    cst_path = output / "cst_coefficients.json"
    _write_json(
        cst_path,
        {
            "schema": "aeris.pygeo.cst_sections.v1",
            "geometry_id": result.geometry_id,
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
                for section in result.extracted
            ],
        },
    )
    result.artifacts["cst_coefficients_json"] = str(cst_path)

    control_path = output / "control_surface.json"
    _write_json(
        control_path,
        {
            "schema": "aeris.pygeo.control_surface.v1",
            "geometry_id": result.geometry_id,
            **result.control.to_dict(),
            "native_pygeo_geometry_state": "neutral",
            "physical_deflected_cad_enabled": config.pygeo.physical_cad.enabled,
        },
    )
    result.artifacts["control_surface_json"] = str(control_path)

    outputs = config.pygeo.outputs
    if outputs.write_surface_npz:
        path = output / "pygeo_surface.npz"
        np.savez_compressed(
            path,
            upper=result.upper_surface,
            lower=result.lower_surface,
        )
        result.artifacts["pygeo_surface_npz"] = str(path)
        result.exports["surface_npz"] = "written"

    if outputs.write_section_dat:
        for section in result.extracted:
            _write_section_dat(
                sections_dir / f"section_{section.index:03d}_yb_{section.span_fraction:.6f}.dat",
                section,
            )
        result.artifacts["section_dat_directory"] = str(sections_dir)
        result.exports["section_dat"] = "written"

    if outputs.write_iges:
        path = output / "pygeo_surface.igs"
        try:
            result.pygeo.geometry.writeIGES(str(path))
            result.artifacts["pygeo_iges"] = str(path)
            result.exports["iges"] = "written"
        except Exception as exc:
            result.exports["iges"] = f"failed: {type(exc).__name__}: {exc}"

    if outputs.write_tecplot:
        path = output / "pygeo_surface.dat"
        try:
            result.pygeo.geometry.writeTecplot(str(path), surfs=True, coef=True)
            result.artifacts["pygeo_tecplot"] = str(path)
            result.exports["tecplot"] = "written"
        except Exception as exc:
            result.exports["tecplot"] = f"failed: {type(exc).__name__}: {exc}"

    if outputs.save_visualization:
        geometry_plot = output / "geometry_3d.png"
        sections_plot = output / "sections.png"
        _plot_geometry(result, geometry_plot, outputs.visualization_dpi)
        _plot_sections(result, sections_plot, outputs.visualization_dpi)
        result.artifacts["geometry_3d_plot"] = str(geometry_plot)
        result.artifacts["sections_plot"] = str(sections_plot)
        result.exports["visualization"] = "written"


def _export_physical_cad(
    result: PyGeoGeometryResult,
    config: BWBGeneratorConfig,
) -> Exception | None:
    physical = config.pygeo.physical_cad
    if not physical.enabled:
        result.exports["physical_cad"] = "disabled"
        return None
    if result.metrics["geometry_qc"] != "accepted":
        result.exports["physical_cad"] = "skipped: neutral geometry QC rejected"
        return None

    from aeris.generators.bwb_segmented_v1.pygeo_physical_cad import (
        PhysicalCadSpec,
        build_physical_cad,
        export_physical_cad,
    )

    spec = PhysicalCadSpec(**asdict(physical))
    try:
        model = build_physical_cad(result, result.control, spec)
        physical_result = export_physical_cad(
            model,
            result.output_dir,
            output_flags=asdict(config.pygeo.outputs),
            visualization_enabled=config.pygeo.outputs.save_visualization,
            dpi=config.pygeo.outputs.visualization_dpi,
        )
        result.physical_cad = physical_result
        result.metrics.update(physical_result["metrics"])
        result.artifacts["physical_cad"] = physical_result["artifacts"]
        result.exports["physical_cad"] = str(physical_result["status"])
        return None
    except Exception as exc:
        result.exports["physical_cad"] = f"failed: {type(exc).__name__}: {exc}"
        result.metrics["physical_cad_accepted"] = False
        return exc if physical.fail_on_invalid else None


def _write_manifest(result: PyGeoGeometryResult, config: BWBGeneratorConfig) -> None:
    manifest_path = result.output_dir / "pygeo_manifest.json"
    result.artifacts["pygeo_manifest"] = str(manifest_path)
    _write_json(
        manifest_path,
        {
            **result.summary_dict(),
            "created_at_utc": datetime.now(UTC).isoformat(),
            "config": config.pygeo.to_dict(),
        },
    )


def build_pygeo_geometry(
    *,
    section_geometry: SectionGeometryResult,
    planform: PlanformResult,
    sample: BWBDesignSample,
    config: BWBGeneratorConfig,
    output_dir: Path,
) -> PyGeoGeometryResult:
    """Realize one Aeris-authored BWB as a pyGeo loft and export its utilities."""

    if not config.pygeo.enabled:
        raise ValueError("build_pygeo_geometry called while geometry.pygeo.enabled is false")

    stations = tuple(
        stations_from_records(
            section_geometry.sections,
            _resolve_airfoil_database(config),
        )
    )
    control = _control_state(config)
    geometry_id = _geometry_id(sample, config, stations, control)
    frame_mode = (
        "asb_frame" if config.pygeo.frame_mode == "aeris_frame" else config.pygeo.frame_mode
    )
    pygeo = build_pygeo(
        stations,
        k_span=config.pygeo.k_span,
        frame_mode=frame_mode,
        n_ctl=config.pygeo.n_ctl,
        tip=config.pygeo.tip,
        tip_scale=config.pygeo.tip_scale,
    )
    fractions = _span_fractions(
        config.pygeo.extraction.spanwise_sections,
        section_geometry,
        control,
    )
    extracted = tuple(
        extract_sections(
            pygeo,
            fractions,
            cst_order=config.pygeo.extraction.cst_order,
            chordwise_points=config.pygeo.extraction.chordwise_points,
        )
    )
    upper, lower = sample_main_surfaces(
        pygeo,
        chordwise_points=config.pygeo.surface_sampling.chordwise_points,
        spanwise_points=config.pygeo.surface_sampling.spanwise_points,
    )
    metrics = _build_metrics(
        planform=planform,
        stations=stations,
        extracted=extracted,
        upper=upper,
        lower=lower,
        pygeo=pygeo,
        control=control,
        config=config,
    )
    result = PyGeoGeometryResult(
        geometry_id=geometry_id,
        pygeo=pygeo,
        stations=stations,
        extracted=extracted,
        upper_surface=upper,
        lower_surface=lower,
        metrics=metrics,
        control=control,
        output_dir=Path(output_dir),
        artifacts={},
        exports={},
    )
    _export_base_artifacts(result, config)
    physical_error = _export_physical_cad(result, config)
    _write_manifest(result, config)

    if physical_error is not None:
        raise RuntimeError(
            "pyGeo physical CAD failed after neutral artifacts were written: "
            f"{type(physical_error).__name__}: {physical_error}"
        ) from physical_error
    if result.metrics["geometry_qc"] != "accepted" and config.pygeo.quality.fail_on_rejection:
        raise ValueError(
            "pyGeo geometry QC rejected the realized loft; inspect "
            f"{result.output_dir / 'pygeo_manifest.json'}"
        )
    return result
