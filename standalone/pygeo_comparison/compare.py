#!/usr/bin/env python3
"""Standalone pyGeo lifting-surface generator and AeroSandbox comparison.

This file intentionally imports no Aeris modules. It can:
  1. generate and visualize a pyGeo lifting surface by itself;
  2. rebuild the same authored stations with AeroSandbox;
  3. save a visual overlay and numerical surface-distance report.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
from contextlib import redirect_stdout
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class Station:
    x_le_m: float
    y_m: float
    z_le_m: float
    chord_m: float
    twist_deg: float
    airfoil_file: Path


@dataclass(frozen=True)
class Settings:
    name: str
    symmetric: bool
    stations: tuple[Station, ...]
    k_span: int
    n_ctl: int | None
    tip: str
    tip_scale: float
    write_iges: bool
    write_tecplot: bool


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be numeric, got bool.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must be numeric, got {value!r}.") from exc


def _resolve_airfoil(value: str, config_path: Path) -> Path:
    path = Path(value).expanduser()
    candidates = [path] if path.is_absolute() else [
        config_path.parent / path,
        Path.cwd() / path,
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    checked = ", ".join(str(candidate.resolve()) for candidate in candidates)
    raise FileNotFoundError(f"Airfoil {value!r} not found. Checked: {checked}")


def load_settings(config_path: Path) -> Settings:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("The YAML root must be a mapping.")

    default_airfoil = raw.get("airfoil_file")
    rows = raw.get("stations")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("'stations' must be a list containing at least two stations.")

    stations: list[Station] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise TypeError(f"stations[{index}] must be a mapping.")
        airfoil_value = row.get("airfoil_file", default_airfoil)
        if not isinstance(airfoil_value, str) or not airfoil_value.strip():
            raise ValueError(
                f"stations[{index}] needs airfoil_file, or define top-level airfoil_file."
            )
        station = Station(
            x_le_m=_number(row.get("x_le_m"), f"stations[{index}].x_le_m"),
            y_m=_number(row.get("y_m"), f"stations[{index}].y_m"),
            z_le_m=_number(row.get("z_le_m", 0.0), f"stations[{index}].z_le_m"),
            chord_m=_number(row.get("chord_m"), f"stations[{index}].chord_m"),
            twist_deg=_number(row.get("twist_deg", 0.0), f"stations[{index}].twist_deg"),
            airfoil_file=_resolve_airfoil(airfoil_value, config_path),
        )
        if station.chord_m <= 0.0:
            raise ValueError(f"stations[{index}].chord_m must be positive.")
        stations.append(station)

    if any(right.y_m <= left.y_m for left, right in zip(stations, stations[1:])):
        raise ValueError("Station y_m coordinates must be strictly increasing.")

    symmetric = raw.get("symmetric", True)
    if not isinstance(symmetric, bool):
        raise TypeError("'symmetric' must be true or false.")
    if symmetric and abs(stations[0].y_m) > 1e-12:
        raise ValueError("A symmetric surface must begin at y_m: 0.")

    pygeo = raw.get("pygeo", {})
    outputs = raw.get("outputs", {})
    if not isinstance(pygeo, dict) or not isinstance(outputs, dict):
        raise TypeError("'pygeo' and 'outputs' must be mappings.")

    k_span = pygeo.get("k_span", min(3, len(stations)))
    if isinstance(k_span, bool) or not isinstance(k_span, int):
        raise TypeError("pygeo.k_span must be an integer.")
    if not 2 <= k_span <= len(stations):
        raise ValueError(f"pygeo.k_span must be between 2 and {len(stations)}.")

    n_ctl = pygeo.get("n_ctl")
    if n_ctl is not None and (
        isinstance(n_ctl, bool) or not isinstance(n_ctl, int) or n_ctl < 4
    ):
        raise ValueError("pygeo.n_ctl must be null or an integer of at least 4.")

    tip = str(pygeo.get("tip", "rounded")).strip().lower()
    if tip not in {"rounded", "pinched", "none"}:
        raise ValueError("pygeo.tip must be rounded, pinched, or none.")

    return Settings(
        name=str(raw.get("name", "standalone_pygeo_surface")),
        symmetric=symmetric,
        stations=tuple(stations),
        k_span=k_span,
        n_ctl=n_ctl,
        tip=tip,
        tip_scale=_number(pygeo.get("tip_scale", 0.25), "pygeo.tip_scale"),
        write_iges=bool(outputs.get("write_iges", True)),
        write_tecplot=bool(outputs.get("write_tecplot", True)),
    )


def load_airfoil_coordinates(path: Path) -> np.ndarray:
    rows: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.replace(",", " ").split()
        if len(fields) < 2:
            continue
        try:
            rows.append((float(fields[0]), float(fields[1])))
        except ValueError:
            continue
    coordinates = np.asarray(rows, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[0] < 5 or coordinates.shape[1] != 2:
        raise ValueError(f"{path}: not enough valid two-column airfoil coordinates.")
    return coordinates


def build_pygeo(settings: Settings) -> tuple[Any, str]:
    try:
        from pygeo import pyGeo
    except ImportError as exc:
        raise RuntimeError(
            "pygeo is not installed in this Python environment. "
            "Run this script with the project .venv described in README.md."
        ) from exc

    stations = settings.stations
    capture = io.StringIO()
    with redirect_stdout(capture):
        geometry = pyGeo(
            "liftingSurface",
            xsections=[str(station.airfoil_file) for station in stations],
            x=[station.x_le_m for station in stations],
            y=[station.y_m for station in stations],
            z=[station.z_le_m for station in stations],
            scale=[station.chord_m for station in stations],
            offset=np.zeros((len(stations), 2)),
            # pyGeo airfoils begin in x-y. rotX=90 maps thickness to global z.
            # rotY then matches positive nose-up AeroSandbox twist.
            rotX=[90.0] * len(stations),
            rotY=[station.twist_deg for station in stations],
            rotZ=[0.0] * len(stations),
            nCtl=settings.n_ctl,
            kSpan=settings.k_span,
            bluntTe=False,
            roundedTe=False,
            squareTeTip=True,
            tip=settings.tip,
            tipScale=settings.tip_scale,
        )
    return geometry, capture.getvalue()


def sample_pygeo(
    geometry: Any,
    chordwise_points: int,
    spanwise_points: int,
) -> tuple[np.ndarray, ...]:
    u = np.linspace(0.0, 1.0, chordwise_points)
    v = np.linspace(0.0, 1.0, spanwise_points)
    v_grid, u_grid = np.meshgrid(v, u)
    return tuple(
        np.asarray(surface(u_grid, v_grid), dtype=float)
        for surface in geometry.surfs
    )


def grid_area(grid: np.ndarray) -> float:
    p00 = grid[:-1, :-1]
    p10 = grid[1:, :-1]
    p01 = grid[:-1, 1:]
    p11 = grid[1:, 1:]
    area_a = 0.5 * np.linalg.norm(np.cross(p10 - p00, p11 - p00), axis=2)
    area_b = 0.5 * np.linalg.norm(np.cross(p11 - p00, p01 - p00), axis=2)
    return float(np.sum(area_a + area_b))


def mesh_area(points: np.ndarray, faces: np.ndarray) -> float:
    vertices = points[faces]
    if vertices.shape[1] == 3:
        return float(
            np.sum(
                0.5
                * np.linalg.norm(
                    np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0]),
                    axis=1,
                )
            )
        )
    if vertices.shape[1] == 4:
        area_a = 0.5 * np.linalg.norm(
            np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0]),
            axis=1,
        )
        area_b = 0.5 * np.linalg.norm(
            np.cross(vertices[:, 2] - vertices[:, 0], vertices[:, 3] - vertices[:, 0]),
            axis=1,
        )
        return float(np.sum(area_a + area_b))
    raise ValueError("AeroSandbox mesh must contain triangular or quadrilateral faces.")


def planform_metrics(settings: Settings) -> dict[str, float]:
    y = np.asarray([station.y_m for station in settings.stations])
    chord = np.asarray([station.chord_m for station in settings.stations])
    dy = np.diff(y)
    semi_area = float(np.sum(0.5 * (chord[:-1] + chord[1:]) * dy))
    symmetry = 2.0 if settings.symmetric else 1.0
    area = symmetry * semi_area
    semi_span = float(y[-1] - y[0])
    full_span = symmetry * semi_span
    integral_c_squared = float(
        np.sum(dy * (chord[:-1] ** 2 + chord[:-1] * chord[1:] + chord[1:] ** 2) / 3.0)
    )
    return {
        "semi_span_m": semi_span,
        "full_span_m": full_span,
        "area_m2": area,
        "aspect_ratio": full_span**2 / area,
        "mean_aerodynamic_chord_m": integral_c_squared / semi_area,
    }


def build_aerosandbox(settings: Settings) -> tuple[Any, Any]:
    try:
        import aerosandbox as asb
    except ImportError as exc:
        raise RuntimeError("aerosandbox is required for --mode compare.") from exc

    cache: dict[Path, Any] = {}
    xsecs = []
    for station in settings.stations:
        if station.airfoil_file not in cache:
            cache[station.airfoil_file] = asb.Airfoil(
                name=station.airfoil_file.stem,
                coordinates=load_airfoil_coordinates(station.airfoil_file),
            )
        xsecs.append(
            asb.WingXSec(
                xyz_le=[station.x_le_m, station.y_m, station.z_le_m],
                chord=station.chord_m,
                twist=station.twist_deg,
                airfoil=cache[station.airfoil_file],
            )
        )
    wing = asb.Wing(name=settings.name, symmetric=settings.symmetric, xsecs=xsecs)
    airplane = asb.Airplane(name=settings.name, wings=[wing])
    return wing, airplane


def structured_grid_faces(grids: tuple[np.ndarray, ...]) -> np.ndarray:
    """Create quadrilateral faces for concatenated structured surface grids."""
    blocks: list[np.ndarray] = []
    offset = 0
    for grid in grids:
        n_u, n_v, _ = grid.shape
        indices = np.arange(n_u * n_v, dtype=int).reshape(n_u, n_v) + offset
        blocks.append(
            np.stack(
                (
                    indices[:-1, :-1],
                    indices[1:, :-1],
                    indices[1:, 1:],
                    indices[:-1, 1:],
                ),
                axis=-1,
            ).reshape(-1, 4)
        )
        offset += n_u * n_v
    return np.concatenate(blocks)


def _triangles_from_faces(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    faces = np.asarray(faces, dtype=int)
    if faces.shape[1] == 3:
        triangle_faces = faces
    elif faces.shape[1] == 4:
        triangle_faces = np.concatenate((faces[:, (0, 1, 2)], faces[:, (0, 2, 3)]))
    else:
        raise ValueError("Surface faces must be triangular or quadrilateral.")
    return np.asarray(points, dtype=float)[triangle_faces]


def point_to_mesh_distances(
    query_points: np.ndarray,
    mesh_points: np.ndarray,
    mesh_faces: np.ndarray,
    *,
    candidate_triangles: int = 48,
    batch_size: int = 2048,
) -> np.ndarray:
    """Approximate exact point-to-triangle distance using nearby triangle candidates.

    A centroid tree selects 48 nearby triangles, then the exact distance to each
    candidate triangle (face interior and all three edges) is evaluated. The
    meshes used here are dense and regular, making this materially less
    sampling-biased than point-to-point nearest-neighbor distances.
    """
    query_points = np.asarray(query_points, dtype=float)
    triangles = _triangles_from_faces(mesh_points, mesh_faces)
    centroids = np.mean(triangles, axis=1)
    tree = cKDTree(centroids)
    k = min(candidate_triangles, len(triangles))
    distances = np.empty(len(query_points), dtype=float)
    epsilon = np.finfo(float).eps

    def dot(left: np.ndarray, right: np.ndarray) -> np.ndarray:
        return np.einsum("...i,...i->...", left, right)

    for start in range(0, len(query_points), batch_size):
        stop = min(start + batch_size, len(query_points))
        points = query_points[start:stop]
        triangle_ids = tree.query(points, k=k, workers=-1)[1]
        if triangle_ids.ndim == 1:
            triangle_ids = triangle_ids[:, None]
        candidates = triangles[triangle_ids]
        p = points[:, None, :]
        a = candidates[:, :, 0]
        b = candidates[:, :, 1]
        c = candidates[:, :, 2]
        ab = b - a
        ac = c - a
        ap = p - a

        normal = np.cross(ab, ac)
        normal_squared = dot(normal, normal)
        safe_normal_squared = np.maximum(normal_squared, epsilon)
        plane_distance = np.abs(dot(ap, normal)) / np.sqrt(safe_normal_squared)

        d00 = dot(ab, ab)
        d01 = dot(ab, ac)
        d11 = dot(ac, ac)
        d20 = dot(ap, ab)
        d21 = dot(ap, ac)
        denominator = d00 * d11 - d01 * d01
        safe_denominator = np.where(
            np.abs(denominator) > epsilon,
            denominator,
            1.0,
        )
        bary_b = (d11 * d20 - d01 * d21) / safe_denominator
        bary_c = (d00 * d21 - d01 * d20) / safe_denominator
        bary_a = 1.0 - bary_b - bary_c
        inside = (
            (normal_squared > epsilon)
            & (bary_a >= -1e-12)
            & (bary_b >= -1e-12)
            & (bary_c >= -1e-12)
        )

        def segment_distance(first: np.ndarray, second: np.ndarray) -> np.ndarray:
            edge = second - first
            edge_squared = dot(edge, edge)
            safe_edge_squared = np.maximum(edge_squared, epsilon)
            fraction = np.clip(dot(p - first, edge) / safe_edge_squared, 0.0, 1.0)
            closest = first + fraction[..., None] * edge
            return np.linalg.norm(p - closest, axis=2)

        edge_distance = np.minimum.reduce(
            (
                segment_distance(a, b),
                segment_distance(b, c),
                segment_distance(c, a),
            )
        )
        candidate_distance = np.where(inside, plane_distance, edge_distance)
        distances[start:stop] = np.min(candidate_distance, axis=1)
    return distances


def surface_distance_metrics(
    pygeo_points: np.ndarray,
    pygeo_faces: np.ndarray,
    asb_points: np.ndarray,
    asb_faces: np.ndarray,
    reference_length: float,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    pygeo_to_asb = point_to_mesh_distances(pygeo_points, asb_points, asb_faces)
    asb_to_pygeo = point_to_mesh_distances(asb_points, pygeo_points, pygeo_faces)
    combined = np.concatenate((pygeo_to_asb, asb_to_pygeo))

    def one_way(values: np.ndarray) -> dict[str, float]:
        return {
            "mean_m": float(np.mean(values)),
            "rms_m": float(np.sqrt(np.mean(values**2))),
            "p95_m": float(np.percentile(values, 95)),
            "max_m": float(np.max(values)),
        }

    rms = float(np.sqrt(np.mean(combined**2)))
    result = {
        "method": "bidirectional point-to-triangle distance; 48 centroid-nearest candidates",
        "pygeo_to_aerosandbox": one_way(pygeo_to_asb),
        "aerosandbox_to_pygeo": one_way(asb_to_pygeo),
        "symmetric": {
            "rms_m": rms,
            "rms_mm": 1000.0 * rms,
            "rms_percent_mac": 100.0 * rms / reference_length,
            "p95_m": float(np.percentile(combined, 95)),
            "p95_mm": float(1000.0 * np.percentile(combined, 95)),
            "sampled_hausdorff_m": float(np.max(combined)),
            "sampled_hausdorff_mm": float(1000.0 * np.max(combined)),
        },
    }
    return result, pygeo_to_asb, asb_to_pygeo


def _set_equal_3d(axis: Any, points: np.ndarray) -> None:
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    center = 0.5 * (minimum + maximum)
    radius = max(float(np.max(maximum - minimum)) * 0.52, 1e-6)
    axis.set_xlim(center[0] - radius, center[0] + radius)
    axis.set_ylim(center[1] - radius, center[1] + radius)
    axis.set_zlim(center[2] - radius, center[2] + radius)


def save_pygeo_figure(
    grids: tuple[np.ndarray, ...],
    settings: Settings,
    path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(13, 6), constrained_layout=True)
    view = figure.add_subplot(1, 2, 1, projection="3d")
    plan = figure.add_subplot(1, 2, 2)
    displayed: list[np.ndarray] = []
    colors = ("#d1495b", "#e56b6f", "#f4a261", "#f6bd60")

    for index, grid in enumerate(grids):
        color = colors[index % len(colors)]
        view.plot_surface(
            grid[:, :, 0],
            grid[:, :, 1],
            grid[:, :, 2],
            color=color,
            alpha=0.78,
            linewidth=0,
        )
        plan.plot(grid[:, ::3, 0], grid[:, ::3, 1], color=color, alpha=0.35, linewidth=0.5)
        displayed.append(grid)
        if settings.symmetric:
            mirror = grid.copy()
            mirror[:, :, 1] *= -1.0
            view.plot_surface(
                mirror[:, :, 0],
                mirror[:, :, 1],
                mirror[:, :, 2],
                color=color,
                alpha=0.78,
                linewidth=0,
            )
            plan.plot(
                mirror[:, ::3, 0],
                mirror[:, ::3, 1],
                color=color,
                alpha=0.35,
                linewidth=0.5,
            )
            displayed.append(mirror)

    cloud = np.concatenate([grid.reshape(-1, 3) for grid in displayed])
    _set_equal_3d(view, cloud)
    view.set_title("pyGeo B-spline surface")
    view.set_xlabel("x [m]")
    view.set_ylabel("y [m]")
    view.set_zlabel("z [m]")
    view.view_init(elev=24, azim=-128)
    plan.set_title("pyGeo planform / patch grid")
    plan.set_xlabel("x [m]")
    plan.set_ylabel("y [m]")
    plan.set_aspect("equal", adjustable="box")
    plan.grid(alpha=0.2)
    figure.suptitle(f"{settings.name} — standalone pyGeo", fontsize=14)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def save_comparison_figure(
    pygeo_grids: tuple[np.ndarray, np.ndarray],
    pygeo_points: np.ndarray,
    asb_points: np.ndarray,
    pygeo_to_asb: np.ndarray,
    asb_to_pygeo: np.ndarray,
    report: dict[str, Any],
    path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    figure = plt.figure(figsize=(15, 11), constrained_layout=True)
    overlay = figure.add_subplot(2, 2, 1, projection="3d")
    error_map = figure.add_subplot(2, 2, 2)
    histogram = figure.add_subplot(2, 2, 3)
    numbers = figure.add_subplot(2, 2, 4)

    for grid in pygeo_grids:
        overlay.plot_surface(
            grid[:, :, 0],
            grid[:, :, 1],
            grid[:, :, 2],
            color="#d1495b",
            alpha=0.38,
            linewidth=0,
        )
    stride = max(1, len(asb_points) // 7000)
    overlay.scatter(
        asb_points[::stride, 0],
        asb_points[::stride, 1],
        asb_points[::stride, 2],
        color="#277da1",
        s=0.8,
        alpha=0.42,
        depthshade=False,
    )
    _set_equal_3d(overlay, np.vstack((pygeo_points, asb_points)))
    overlay.set_title("Right half-wing surface overlay")
    overlay.set_xlabel("x [m]")
    overlay.set_ylabel("y [m]")
    overlay.set_zlabel("z [m]")
    overlay.view_init(elev=23, azim=-126)
    overlay.legend(
        handles=[
            Line2D([0], [0], color="#d1495b", lw=5, alpha=0.55, label="pyGeo"),
            Line2D([0], [0], marker="o", linestyle="", color="#277da1", label="AeroSandbox"),
        ]
    )

    stride = max(1, len(pygeo_points) // 16000)
    colors = error_map.scatter(
        pygeo_points[::stride, 0],
        pygeo_points[::stride, 1],
        c=pygeo_to_asb[::stride] * 1000.0,
        cmap="magma",
        s=3,
        rasterized=True,
    )
    error_map.set_title("pyGeo → AeroSandbox point-to-surface distance")
    error_map.set_xlabel("x [m]")
    error_map.set_ylabel("y [m]")
    error_map.set_aspect("equal", adjustable="box")
    figure.colorbar(colors, ax=error_map, label="distance [mm]")

    histogram.hist(pygeo_to_asb * 1000.0, bins=70, alpha=0.58, label="pyGeo → ASB")
    histogram.hist(asb_to_pygeo * 1000.0, bins=70, alpha=0.58, label="ASB → pyGeo")
    histogram.set_yscale("log")
    histogram.set_xlabel("nearest distance [mm]")
    histogram.set_ylabel("sample count")
    histogram.set_title("Bidirectional distance distribution")
    histogram.grid(alpha=0.2)
    histogram.legend()

    planform = report["planform"]
    surface = report["surface_comparison"]
    distance = report["distance"]["symmetric"]
    numbers.axis("off")
    numbers.text(
        0.02,
        0.98,
        (
            "NUMERICAL COMPARISON\n\n"
            f"Projected y-span (pyGeo / ASB):\n"
            f"{planform['pygeo_sampled']['projected_y_span_m']:.6f} / "
            f"{planform['aerosandbox']['projected_y_span_m']:.6f} m\n"
            f"Projected XY area (pyGeo / ASB):\n"
            f"{planform['pygeo_sampled']['projected_xy_area_m2']:.6f} / "
            f"{planform['aerosandbox']['projected_xy_area_m2']:.6f} m²\n"
            f"Projected AR (pyGeo / ASB):\n"
            f"{planform['pygeo_sampled']['projected_aspect_ratio']:.6f} / "
            f"{planform['aerosandbox']['projected_aspect_ratio']:.6f}\n"
            f"Station-reference span / area / AR:\n"
            f"{planform['station_definition']['projected_y_span_m']:.6f} m / "
            f"{planform['station_definition']['projected_xy_area_m2']:.6f} m² / "
            f"{planform['station_definition']['projected_aspect_ratio']:.6f}\n"
            f"ASB geometric span / area / AR:\n"
            f"{planform['aerosandbox']['geometric_yz_span_m']:.6f} m / "
            f"{planform['aerosandbox']['geometric_planform_area_m2']:.6f} m² / "
            f"{planform['aerosandbox']['geometric_aspect_ratio']:.6f}\n\n"
            f"Right-side outer area (pyGeo / ASB):\n"
            f"{surface['pygeo_area_m2']:.6f} / {surface['aerosandbox_area_m2']:.6f} m²\n"
            f"Area delta: {surface['area_delta_percent']:+.3f}%\n\n"
            f"Symmetric RMS: {distance['rms_mm']:.3f} mm\n"
            f"95th percentile: {distance['p95_mm']:.3f} mm\n"
            f"Sampled Hausdorff: {distance['sampled_hausdorff_mm']:.3f} mm\n"
            f"RMS / MAC: {distance['rms_percent_mac']:.4f}%\n\n"
            "Surface comparison excludes root, tip, and TE caps.\n"
            "Distances use dense triangulated surface approximations."
        ),
        va="top",
        ha="left",
        family="monospace",
        fontsize=10.5,
        bbox={"facecolor": "#f5f5f5", "edgecolor": "#cccccc", "boxstyle": "round,pad=0.7"},
    )
    figure.suptitle("pyGeo vs AeroSandbox — visual and numerical comparison", fontsize=15)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _bounds(points: np.ndarray) -> dict[str, list[float]]:
    return {
        "min_xyz_m": [float(value) for value in points.min(axis=0)],
        "max_xyz_m": [float(value) for value in points.max(axis=0)],
        "extent_xyz_m": [float(value) for value in np.ptp(points, axis=0)],
    }


def _distribution_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def write_stations(settings: Settings, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ("station", "x_le_m", "y_m", "z_le_m", "chord_m", "twist_deg", "airfoil_file")
        )
        for index, station in enumerate(settings.stations):
            writer.writerow(
                (
                    index,
                    station.x_le_m,
                    station.y_m,
                    station.z_le_m,
                    station.chord_m,
                    station.twist_deg,
                    station.airfoil_file,
                )
            )


def write_comparison_csv(report: dict[str, Any], path: Path) -> None:
    planform = report["planform"]
    surface = report["surface_comparison"]
    distance = report["distance"]["symmetric"]
    rows = [
        ("station_projected_y_span", planform["station_definition"]["projected_y_span_m"], "m"),
        ("pygeo_projected_y_span", planform["pygeo_sampled"]["projected_y_span_m"], "m"),
        ("aerosandbox_projected_y_span", planform["aerosandbox"]["projected_y_span_m"], "m"),
        ("station_projected_xy_area", planform["station_definition"]["projected_xy_area_m2"], "m^2"),
        ("pygeo_projected_xy_area", planform["pygeo_sampled"]["projected_xy_area_m2"], "m^2"),
        ("aerosandbox_projected_xy_area", planform["aerosandbox"]["projected_xy_area_m2"], "m^2"),
        ("station_projected_aspect_ratio", planform["station_definition"]["projected_aspect_ratio"], "1"),
        ("pygeo_projected_aspect_ratio", planform["pygeo_sampled"]["projected_aspect_ratio"], "1"),
        ("aerosandbox_projected_aspect_ratio", planform["aerosandbox"]["projected_aspect_ratio"], "1"),
        ("aerosandbox_geometric_yz_span", planform["aerosandbox"]["geometric_yz_span_m"], "m"),
        ("aerosandbox_geometric_planform_area", planform["aerosandbox"]["geometric_planform_area_m2"], "m^2"),
        ("aerosandbox_geometric_aspect_ratio", planform["aerosandbox"]["geometric_aspect_ratio"], "1"),
        ("pygeo_outer_area_right", surface["pygeo_area_m2"], "m^2"),
        ("aerosandbox_outer_area_right", surface["aerosandbox_area_m2"], "m^2"),
        ("outer_area_delta", surface["area_delta_percent"], "%"),
        ("surface_symmetric_rms", distance["rms_mm"], "mm"),
        ("surface_symmetric_p95", distance["p95_mm"], "mm"),
        ("surface_sampled_hausdorff", distance["sampled_hausdorff_mm"], "mm"),
        ("surface_symmetric_rms_normalized", distance["rms_percent_mac"], "% MAC"),
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("metric", "value", "unit"))
        writer.writerows(rows)


def run(
    config_path: Path,
    output_dir: Path,
    mode: str,
    chordwise_points: int,
    spanwise_points: int,
) -> dict[str, Any]:
    settings = load_settings(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, output_dir / "input_config.yaml")
    write_stations(settings, output_dir / "stations.csv")

    geometry, build_log = build_pygeo(settings)
    (output_dir / "pygeo_build.log").write_text(build_log, encoding="utf-8")
    grids = sample_pygeo(geometry, chordwise_points, spanwise_points)
    if len(grids) < 2:
        raise RuntimeError("pyGeo did not return the expected upper and lower surface patches.")
    np.savez_compressed(
        output_dir / "pygeo_surface_samples.npz",
        **{f"patch_{index:02d}": grid for index, grid in enumerate(grids)},
    )
    if settings.write_iges:
        geometry.writeIGES(str(output_dir / "pygeo_surface.igs"))
    if settings.write_tecplot:
        geometry.writeTecplot(str(output_dir / "pygeo_surface.dat"), surfs=True, coef=True)

    standalone_plot = output_dir / "pygeo_standalone.png"
    save_pygeo_figure(grids, settings, standalone_plot)
    definition = planform_metrics(settings)
    pygeo_outer_area = grid_area(grids[0]) + grid_area(grids[1])
    mean_surface = 0.5 * (grids[0] + grids[1])
    projected_mean_surface = mean_surface.copy()
    projected_mean_surface[:, :, 2] = 0.0
    symmetry_factor = 2.0 if settings.symmetric else 1.0
    pygeo_projected_span = symmetry_factor * float(np.ptp(projected_mean_surface[:, :, 1]))
    pygeo_projected_area = symmetry_factor * grid_area(projected_mean_surface)
    pygeo_projected_aspect_ratio = pygeo_projected_span**2 / pygeo_projected_area
    report: dict[str, Any] = {
        "mode": mode,
        "config": str(config_path),
        "backend": {
            "pygeo_version": _distribution_version("pygeo"),
            "pyspline_version": _distribution_version("pyspline"),
        },
        "station_definition": definition,
        "pygeo": {
            "patch_count": len(grids),
            "projected_y_span_m": pygeo_projected_span,
            "projected_xy_area_m2": pygeo_projected_area,
            "projected_aspect_ratio": pygeo_projected_aspect_ratio,
            "right_side_outer_area_no_caps_m2": pygeo_outer_area,
            "modeled_geometry": (
                "right half-wing; symmetry is visualized and used for planform metrics"
                if settings.symmetric
                else "complete authored lifting surface"
            ),
        },
        "artifacts": {
            "standalone_plot": str(standalone_plot),
            "iges": str(output_dir / "pygeo_surface.igs") if settings.write_iges else None,
            "tecplot": str(output_dir / "pygeo_surface.dat") if settings.write_tecplot else None,
        },
    }

    if mode == "pygeo":
        (output_dir / "pygeo_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    wing, _airplane = build_aerosandbox(settings)
    section_count = len(settings.stations) - 1
    subdivision_ratio = max(2, math.ceil((spanwise_points - 1) / section_count))
    dense_wing = wing.subdivide_sections(subdivision_ratio)
    asb_points, asb_faces = dense_wing.mesh_body(
        method="quad",
        chordwise_resolution=chordwise_points,
        mesh_surface=True,
        mesh_tips=False,
        mesh_trailing_edge=False,
        mesh_symmetric=False,
    )
    asb_points = np.asarray(asb_points, dtype=float)
    asb_faces = np.asarray(asb_faces, dtype=int)
    pygeo_grids = (grids[0], grids[1])
    pygeo_points = np.concatenate([grid.reshape(-1, 3) for grid in pygeo_grids])
    pygeo_faces = structured_grid_faces(pygeo_grids)
    distance, pygeo_to_asb, asb_to_pygeo = surface_distance_metrics(
        pygeo_points,
        pygeo_faces,
        asb_points,
        asb_faces,
        definition["mean_aerodynamic_chord_m"],
    )
    distance["pygeo_to_aerosandbox"]["max_location_xyz_m"] = [
        float(value) for value in pygeo_points[int(np.argmax(pygeo_to_asb))]
    ]
    distance["aerosandbox_to_pygeo"]["max_location_xyz_m"] = [
        float(value) for value in asb_points[int(np.argmax(asb_to_pygeo))]
    ]

    asb_outer_area = mesh_area(asb_points, asb_faces)
    area_delta_percent = 100.0 * (pygeo_outer_area - asb_outer_area) / asb_outer_area

    comparison = {
        "comparison": "standalone pyGeo liftingSurface vs AeroSandbox Wing",
        "scope": {
            "side": "right half-wing",
            "included": "upper and lower outer-mold-line surfaces",
            "excluded": ["root cap", "tip cap", "trailing-edge cap", "mirrored half"],
        },
        "interpretation": {
            "pygeo": "B-spline loft through the authored stations",
            "aerosandbox": "piecewise interpolation through the same authored stations",
            "note": (
                "The station definitions are identical. Between stations, different interpolation "
                "and section-frame conventions can produce genuine geometric differences."
            ),
        },
        "sampling": {
            "station_count": len(settings.stations),
            "pygeo_chordwise_points_per_patch": chordwise_points,
            "pygeo_spanwise_points_per_patch": spanwise_points,
            "pygeo_point_count": len(pygeo_points),
            "pygeo_face_count": len(pygeo_faces),
            "distance_method": distance["method"],
            "aerosandbox_subdivision_ratio_per_section": subdivision_ratio,
            "aerosandbox_point_count": len(asb_points),
            "aerosandbox_face_count": len(asb_faces),
        },
        "planform": {
            "station_definition": {
                "projected_y_span_m": definition["full_span_m"],
                "projected_xy_area_m2": definition["area_m2"],
                "projected_aspect_ratio": definition["aspect_ratio"],
                "mean_aerodynamic_chord_m": definition["mean_aerodynamic_chord_m"],
            },
            "pygeo_sampled": {
                "projected_y_span_m": pygeo_projected_span,
                "projected_xy_area_m2": pygeo_projected_area,
                "projected_aspect_ratio": pygeo_projected_aspect_ratio,
            },
            "aerosandbox": {
                "projected_y_span_m": float(wing.span(type="y")),
                "projected_xy_area_m2": float(wing.area(type="xy")),
                "projected_aspect_ratio": float(
                    wing.span(type="y") ** 2 / wing.area(type="xy")
                ),
                "geometric_yz_span_m": float(wing.span(type="yz")),
                "geometric_planform_area_m2": float(wing.area(type="planform")),
                "geometric_aspect_ratio": float(wing.aspect_ratio()),
            },
        },
        "surface_comparison": {
            "pygeo_area_m2": pygeo_outer_area,
            "aerosandbox_area_m2": asb_outer_area,
            "area_delta_m2": pygeo_outer_area - asb_outer_area,
            "area_delta_percent": area_delta_percent,
        },
        "distance": distance,
        "bounds": {
            "pygeo": _bounds(pygeo_points),
            "aerosandbox": _bounds(asb_points),
        },
    }
    report.update(comparison)
    comparison_plot = output_dir / "pygeo_vs_aerosandbox.png"
    save_comparison_figure(
        pygeo_grids,
        pygeo_points,
        asb_points,
        pygeo_to_asb,
        asb_to_pygeo,
        report,
        comparison_plot,
    )
    report["artifacts"].update(
        {
            "comparison_plot": str(comparison_plot),
            "comparison_json": str(output_dir / "comparison_report.json"),
            "comparison_csv": str(output_dir / "comparison_metrics.csv"),
        }
    )
    (output_dir / "comparison_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    write_comparison_csv(report, output_dir / "comparison_metrics.csv")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("example.yaml"),
        help="Standalone YAML input (default: example.yaml beside this script).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/pygeo_comparison"),
        help="Persistent output directory (default: artifacts/pygeo_comparison).",
    )
    parser.add_argument(
        "--mode",
        choices=("pygeo", "compare"),
        default="compare",
        help="'pygeo' generates only pyGeo; 'compare' also builds AeroSandbox.",
    )
    parser.add_argument("--chordwise-points", type=int, default=101)
    parser.add_argument("--spanwise-points", type=int, default=81)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.chordwise_points < 11 or args.spanwise_points < 11:
        raise ValueError("Sampling counts must each be at least 11.")
    config_path = args.config.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    report = run(
        config_path=config_path,
        output_dir=output_dir,
        mode=args.mode,
        chordwise_points=args.chordwise_points,
        spanwise_points=args.spanwise_points,
    )

    print(f"Completed standalone mode: {args.mode}")
    print(f"Output directory: {output_dir}")
    print(f"pyGeo visualization: {report['artifacts']['standalone_plot']}")
    if args.mode == "compare":
        planform = report["planform"]
        surface = report["surface_comparison"]
        distance = report["distance"]["symmetric"]
        print(f"Comparison visualization: {report['artifacts']['comparison_plot']}")
        print(
            "Projected y-span [pyGeo / AeroSandbox]: "
            f"{planform['pygeo_sampled']['projected_y_span_m']:.6f} / "
            f"{planform['aerosandbox']['projected_y_span_m']:.6f} m"
        )
        print(
            "Projected XY area [pyGeo / AeroSandbox]: "
            f"{planform['pygeo_sampled']['projected_xy_area_m2']:.6f} / "
            f"{planform['aerosandbox']['projected_xy_area_m2']:.6f} m^2"
        )
        print(
            "Station-reference projected span / area: "
            f"{planform['station_definition']['projected_y_span_m']:.6f} m / "
            f"{planform['station_definition']['projected_xy_area_m2']:.6f} m^2"
        )
        print(
            "AeroSandbox geometric span / area / AR: "
            f"{planform['aerosandbox']['geometric_yz_span_m']:.6f} m / "
            f"{planform['aerosandbox']['geometric_planform_area_m2']:.6f} m^2 / "
            f"{planform['aerosandbox']['geometric_aspect_ratio']:.6f}"
        )
        print(f"Outer surface area delta: {surface['area_delta_percent']:+.3f}%")
        print(f"Symmetric surface RMS: {distance['rms_mm']:.3f} mm")
        print(f"Surface p95: {distance['p95_mm']:.3f} mm")
        print(f"Sampled Hausdorff: {distance['sampled_hausdorff_mm']:.3f} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
