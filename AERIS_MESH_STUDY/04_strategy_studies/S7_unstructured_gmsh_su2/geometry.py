"""Independent pyGeo-derived closed triangular wall for S7.

The triangles are not inherited from S6's structured block topology.  S7 samples
the authoritative pyGeo B-spline patches at exact physical span fractions,
applies the same declared numerical trailing-edge law, closes each tip, mirrors
the half wing, and verifies the resulting triangle graph before Gmsh sees it.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from shared.geometry_sets import _config, sample

from aeris.generators.bwb_segmented_v1.pygeo_adapter import span_parameters_for_fractions

from .common import (
    POLICY_PATH,
    load_policy,
    require_development_set,
    sha256_file,
    source_digest,
    write_json,
)
from .intersections import self_intersection_report

Array = np.ndarray
SURFACE_SCHEMA = "aeris.s7.surface.v1"
LABELS = ("wall_upper", "wall_lower", "wall_te", "wall_tip")


@dataclass(frozen=True)
class SurfaceMesh:
    points: Array
    triangles: Array
    labels: tuple[str, ...]
    triangle_span_fraction: Array
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        points = np.asarray(self.points)
        triangles = np.asarray(self.triangles)
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError("surface points must have shape (N, 3)")
        if triangles.ndim != 2 or triangles.shape[1] != 3:
            raise ValueError("surface triangles must have shape (M, 3)")
        if len(self.labels) != len(triangles):
            raise ValueError("one label is required per triangle")
        if np.asarray(self.triangle_span_fraction).shape != (len(triangles),):
            raise ValueError("one span fraction is required per triangle")
        if len(triangles) and (triangles.min() < 0 or triangles.max() >= len(points)):
            raise ValueError("surface connectivity references an invalid point")


def _unit(vector: Array, label: str) -> Array:
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 1.0e-14:
        raise ValueError(f"degenerate {label}: {vector}")
    return np.asarray(vector, dtype=float) / norm


def _surface_points(surface: Any, u: Array, v: float) -> Array:
    vv = np.full_like(u, float(v), dtype=float)
    points = np.asarray(surface(u, vv), dtype=float)
    return points.reshape(len(u), 3)


def _opened_section(
    pygeo: Any,
    u: Array,
    v: float,
    *,
    te_abs_m: float,
    te_floor_frac: float,
) -> tuple[Array, Array, dict[str, Any]]:
    upper = _surface_points(pygeo.surfs[0], u, v)
    lower = _surface_points(pygeo.surfs[1], u, v)
    te = 0.5 * (upper[0] + lower[0])
    le = 0.5 * (upper[-1] + lower[-1])
    chord_axis = _unit(te - le, "section chord axis")
    chord = float(np.linalg.norm(te - le))
    separation = upper - lower
    thick_index = int(np.argmax(np.linalg.norm(separation, axis=1)))
    thickness = separation[thick_index]
    thickness -= float(thickness @ chord_axis) * chord_axis
    thickness_axis = _unit(thickness, "section thickness axis")
    target_te = max(float(te_abs_m), float(te_floor_frac) * chord)
    current_te = float(np.linalg.norm(upper[0] - lower[0]))
    half_added = 0.5 * max(0.0, target_te - current_te)

    for points, sign in ((upper, 1.0), (lower, -1.0)):
        xhat = np.clip((points - le) @ chord_axis / max(chord, 1.0e-14), 0.0, 1.0)
        points += sign * half_added * xhat[:, None] * thickness_axis
    # One shared leading-edge node is a topology invariant.
    shared_le = 0.5 * (upper[-1] + lower[-1])
    upper[-1] = shared_le
    lower[-1] = shared_le
    realized_te = float(np.linalg.norm(upper[0] - lower[0]))
    return (
        upper,
        lower,
        {
            "chord_m": chord,
            "target_te_m": target_te,
            "realized_te_m": realized_te,
            "te_relative_error": abs(realized_te - target_te) / target_te,
            "le": le,
            "te": te,
            "chord_axis": chord_axis,
            "thickness_axis": thickness_axis,
            "half_te_opening_added_m": half_added,
        },
    )


def _opened_points_at_u(
    pygeo: Any,
    u: Array,
    v: float,
    *,
    frame: dict[str, Any],
    upper: bool,
) -> Array:
    """Independently re-evaluate tracked wall nodes, as required by S6."""
    points = _surface_points(pygeo.surfs[0 if upper else 1], u, v)
    xhat = np.clip(
        (points - frame["le"]) @ frame["chord_axis"] / max(float(frame["chord_m"]), 1.0e-14),
        0.0,
        1.0,
    )
    sign = 1.0 if upper else -1.0
    return points + (
        sign * float(frame["half_te_opening_added_m"]) * xhat[:, None] * frame["thickness_axis"]
    )


def _level_spec(policy: dict[str, Any], level: str) -> dict[str, Any]:
    if level == "laptop_smoke":
        return dict(policy["laptop_smoke"])
    levels = policy["grid_family"]["levels"]
    if level not in levels:
        raise KeyError(f"unknown S7 level {level!r}; expected laptop_smoke or {sorted(levels)}")
    return dict(levels[level])


def _blended_parameters(count: int, target_end_interval: float) -> Array:
    """Monotone [0, 1] distribution whose end interval matches a target.

    Pure cosine clustering refines the ends quadratically in the point count, so
    once the count is fixed by the average-spacing requirement the end spacing is
    whatever the cosine happens to give -- measured 22x finer than the requested
    trailing-edge target at the tip of index 0.  That over-refinement is what
    produces sliver wall triangles (0.85 degree minimum angle) and poisons the
    core tetrahedra sitting on the prism cap.

    Blending uniform and cosine lets the end interval be requested directly while
    the count still controls the average.  Cosine is the finest end distribution
    available at a given count, so a target it cannot reach is clamped and the
    caller's count loop is responsible for adding points.
    """
    count = int(count)
    cosine = _cosine_parameters(count)
    if count < 3:
        return cosine
    uniform = np.linspace(0.0, 1.0, count)
    uniform_end = float(uniform[1] - uniform[0])
    cosine_end = float(cosine[1] - cosine[0])
    target = float(target_end_interval)
    if not np.isfinite(target) or target >= uniform_end:
        return uniform
    if target <= cosine_end or uniform_end - cosine_end <= np.finfo(float).tiny:
        return cosine
    weight = (uniform_end - target) / (uniform_end - cosine_end)
    weight = float(np.clip(weight, 0.0, 1.0))
    blended = (1.0 - weight) * uniform + weight * cosine
    blended[0], blended[-1] = 0.0, 1.0
    return blended


def _cosine_parameters(count: int) -> Array:
    theta = np.linspace(0.0, math.pi, int(count))
    return 0.5 * (1.0 - np.cos(theta))


class _PointRegistry:
    def __init__(self, tolerance: float):
        self.tolerance = float(tolerance)
        self.points: list[Array] = []
        self._bins: dict[tuple[int, int, int], list[int]] = defaultdict(list)

    def add(self, value: Iterable[float]) -> int:
        point = np.asarray(tuple(value), dtype=float)
        key = tuple(np.rint(point / self.tolerance).astype(np.int64))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for index in self._bins.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if float(np.linalg.norm(self.points[index] - point)) <= self.tolerance:
                            return index
        index = len(self.points)
        self.points.append(point.copy())
        self._bins[key].append(index)
        return index


def _polygon_delaunay_triangles(
    perimeter_xyz: Array, tolerance: float
) -> list[tuple[int, int, int]] | None:
    """Delaunay-triangulate a closed planar polygon given by its perimeter.

    Returns local index triples, or None when the result cannot be trusted.

    A rigid upper/lower ladder inherits the wall's chordwise node distribution.
    Near the trailing edge of the tip section that spacing is roughly half the
    trailing-edge opening, so the ladder is forced to connect three nearly
    collinear boundary nodes: measured 1.5 degree minimum angle at index 0,
    which inverts prisms when extruded.  A Delaunay triangulation of the same
    boundary nodes maximises the minimum angle instead.  Every perimeter edge
    must survive, otherwise the cap would not match the wall it closes and this
    returns None so the caller can fall back.
    """
    from scipy.spatial import Delaunay, QhullError

    count = len(perimeter_xyz)
    if count < 3:
        return None
    centre = perimeter_xyz.mean(axis=0)
    _u, _s, basis = np.linalg.svd(perimeter_xyz - centre, full_matrices=False)
    planar = (perimeter_xyz - centre) @ basis[:2].T
    try:
        triangulation = Delaunay(planar)
    except (QhullError, ValueError):
        return None

    # Keep only triangles whose centroid is inside the polygon (it is not convex).
    inside: list[tuple[int, int, int]] = []
    for simplex in triangulation.simplices:
        centroid = planar[simplex].mean(axis=0)
        crossings = 0
        for i in range(count):
            a, b = planar[i], planar[(i + 1) % count]
            if (a[1] > centroid[1]) != (b[1] > centroid[1]):
                span = b[1] - a[1]
                if abs(span) > np.finfo(float).tiny:
                    x = a[0] + (centroid[1] - a[1]) / span * (b[0] - a[0])
                    if x > centroid[0]:
                        crossings += 1
        if crossings % 2 == 1:
            inside.append(tuple(int(v) for v in simplex))

    if not inside:
        return None
    # Conformity: every perimeter edge must be owned by exactly one kept triangle.
    owners: dict[tuple[int, int], int] = defaultdict(int)
    for triangle in inside:
        for a, b in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            owners[tuple(sorted((a, b)))] += 1
    for i in range(count):
        edge = tuple(sorted((i, (i + 1) % count)))
        if owners.get(edge, 0) != 1:
            return None
    def _area2(triangle: tuple[int, int, int]) -> float:
        first = planar[triangle[1]] - planar[triangle[0]]
        second = planar[triangle[2]] - planar[triangle[0]]
        return 0.5 * abs(float(first[0] * second[1] - first[1] * second[0]))

    areas = [_area2(t) for t in inside]
    if min(areas) <= tolerance * tolerance:
        return None
    return inside


def _planform_record(stations: Sequence[Any]) -> dict[str, Any]:
    """Per-station twist, dihedral and derived sweep, as actually built.

    The mesh artifacts recorded aspect ratio but nothing about the shape that
    produced it, so a failure could never be correlated with dihedral, twist or
    sweep without going back to the design matrix.  These come off the station
    frames pyGeo was handed, so they describe the geometry that was meshed rather
    than what was requested.

    Leading-edge sweep is not a station field; it is the angle of the LE segment
    between consecutive stations, positive aft, and is undefined for a segment
    with no spanwise extent.
    """
    ordered = sorted(stations, key=lambda s: float(s.y_m))
    twist = [float(s.twist_deg) for s in ordered]
    dihedral = [float(s.dihedral_deg) for s in ordered]

    sweep_le_deg: list[float | None] = []
    for inboard, outboard in zip(ordered[:-1], ordered[1:], strict=True):
        run = float(outboard.y_m) - float(inboard.y_m)
        if abs(run) <= np.finfo(float).tiny:
            sweep_le_deg.append(None)
            continue
        sweep_le_deg.append(
            math.degrees(math.atan2(float(outboard.x_le_m) - float(inboard.x_le_m), run))
        )

    finite = [s for s in sweep_le_deg if s is not None]
    return {
        "station_y_m": [float(s.y_m) for s in ordered],
        "station_chord_m": [float(s.chord_m) for s in ordered],
        "twist_deg": twist,
        "dihedral_deg": dihedral,
        "sweep_le_deg": sweep_le_deg,
        "twist_deg_range": [min(twist), max(twist)] if twist else None,
        "dihedral_deg_range": [min(dihedral), max(dihedral)] if dihedral else None,
        "sweep_le_deg_range": [min(finite), max(finite)] if finite else None,
        "root_dihedral_deg": dihedral[0] if dihedral else None,
    }


def _point_segment_distance(point: Array, start: Array, end: Array) -> float:
    """Shortest distance from one point to a finite segment."""
    axis = end - start
    length_squared = float(axis @ axis)
    if length_squared <= np.finfo(float).tiny:
        return float(np.linalg.norm(point - start))
    t = float(np.clip((point - start) @ axis / length_squared, 0.0, 1.0))
    return float(np.linalg.norm(point - (start + t * axis)))


def _best_quad_diagonal(
    corners: Array,
) -> bool:
    """True when the a-c diagonal is safer than b-d for a thin planar quad.

    The tip section is extremely thin, so one diagonal of a cap quad can pass
    through a neighbouring in-plane node to machine precision.  That produces a
    degenerate triangulation which the self-intersection instrument correctly
    rejects.  Choosing the diagonal that keeps the two opposite vertices
    furthest away removes the degeneracy without touching any boundary edge:
    both diagonals yield exactly the same cap boundary.
    """
    a, b, c, d = corners
    ac = min(_point_segment_distance(b, a, c), _point_segment_distance(d, a, c))
    bd = min(_point_segment_distance(a, b, d), _point_segment_distance(c, b, d))
    return ac >= bd


def _edge_orientation(triangle: Array, a: int, b: int) -> int:
    for i in range(3):
        if int(triangle[i]) == a and int(triangle[(i + 1) % 3]) == b:
            return 1
        if int(triangle[i]) == b and int(triangle[(i + 1) % 3]) == a:
            return -1
    raise RuntimeError("edge is absent from triangle")


def orient_closed_surface(points: Array, triangles: Array) -> tuple[Array, dict[str, Any]]:
    triangles = np.asarray(triangles, dtype=np.int64).copy()
    edge_to_triangles: dict[tuple[int, int], list[int]] = defaultdict(list)
    for tri_index, triangle in enumerate(triangles):
        for a, b in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            edge_to_triangles[tuple(sorted((int(a), int(b))))].append(tri_index)
    boundary_edges = [edge for edge, owners in edge_to_triangles.items() if len(owners) == 1]
    nonmanifold_edges = [edge for edge, owners in edge_to_triangles.items() if len(owners) != 2]
    if nonmanifold_edges:
        raise ValueError(
            f"surface is not closed manifold: boundary={len(boundary_edges)}, "
            f"nonmanifold={len(nonmanifold_edges)}"
        )

    neighbors: dict[int, list[tuple[int, tuple[int, int]]]] = defaultdict(list)
    for edge, (left, right) in edge_to_triangles.items():
        neighbors[left].append((right, edge))
        neighbors[right].append((left, edge))
    visited: set[int] = set()
    components = 0
    flips = 0
    for start in range(len(triangles)):
        if start in visited:
            continue
        components += 1
        visited.add(start)
        queue = deque([start])
        while queue:
            left = queue.popleft()
            for right, edge in neighbors[left]:
                if right in visited:
                    if _edge_orientation(triangles[left], *edge) == _edge_orientation(
                        triangles[right], *edge
                    ):
                        raise ValueError("surface orientation graph is inconsistent")
                    continue
                if _edge_orientation(triangles[left], *edge) == _edge_orientation(
                    triangles[right], *edge
                ):
                    triangles[right, [1, 2]] = triangles[right, [2, 1]]
                    flips += 1
                visited.add(right)
                queue.append(right)
    p0 = points[triangles[:, 0]]
    p1 = points[triangles[:, 1]]
    p2 = points[triangles[:, 2]]
    signed_volume = float(np.sum(np.einsum("ij,ij->i", p0, np.cross(p1, p2))) / 6.0)
    globally_flipped = False
    if signed_volume < 0.0:
        triangles[:, [1, 2]] = triangles[:, [2, 1]]
        signed_volume *= -1.0
        globally_flipped = True
    return triangles, {
        "connected_components": components,
        "local_triangle_flips": flips,
        "global_flip": globally_flipped,
        "enclosed_signed_volume_m3": signed_volume,
        "boundary_edge_count": len(boundary_edges),
        "nonmanifold_edge_count": len(nonmanifold_edges),
    }


def surface_topology_report(
    points: Array, triangles: Array, labels: Iterable[str]
) -> dict[str, Any]:
    triangles = np.asarray(triangles, dtype=np.int64)
    xyz = np.asarray(points, dtype=float)
    p0, p1, p2 = (xyz[triangles[:, i]] for i in range(3))
    areas = 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
    edge_counts: dict[tuple[int, int], int] = defaultdict(int)
    edge_orientation_sum: dict[tuple[int, int], int] = defaultdict(int)
    edge_owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for triangle_index, triangle in enumerate(triangles):
        for a, b in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            left, right = int(a), int(b)
            key = tuple(sorted((left, right)))
            edge_counts[key] += 1
            edge_orientation_sum[key] += 1 if (left, right) == key else -1
            edge_owners[key].append(triangle_index)
    canonical_faces = [tuple(sorted(map(int, triangle))) for triangle in triangles]
    duplicates = len(canonical_faces) - len(set(canonical_faces))
    label_counts = {label: 0 for label in LABELS}
    for label in labels:
        label_counts[label] = label_counts.get(label, 0) + 1
    scale = float(np.linalg.norm(np.ptp(xyz, axis=0)))
    area_tol = max(scale * scale * 1.0e-24, np.finfo(float).tiny)
    signed_volume = float(np.sum(np.einsum("ij,ij->i", p0, np.cross(p1, p2))) / 6.0)
    neighbors: dict[int, set[int]] = defaultdict(set)
    for owners in edge_owners.values():
        for left in owners:
            neighbors[left].update(right for right in owners if right != left)
    unseen = set(range(len(triangles)))
    connected_components = 0
    while unseen:
        connected_components += 1
        stack = [unseen.pop()]
        while stack:
            current = stack.pop()
            adjacent = neighbors[current] & unseen
            unseen.difference_update(adjacent)
            stack.extend(adjacent)
    return {
        "node_count": len(xyz),
        "triangle_count": len(triangles),
        "finite": bool(np.all(np.isfinite(xyz))),
        "boundary_edge_count": sum(count == 1 for count in edge_counts.values()),
        "nonmanifold_edge_count": sum(count != 2 for count in edge_counts.values()),
        "inconsistently_oriented_edge_count": sum(
            edge_counts[edge] == 2 and orientation != 0
            for edge, orientation in edge_orientation_sum.items()
        ),
        "enclosed_signed_volume_m3": signed_volume,
        "connected_components": connected_components,
        "zero_area_face_count": int(np.count_nonzero(areas <= area_tol)),
        "duplicate_face_count": int(duplicates),
        "min_triangle_area_m2": float(np.min(areas)) if len(areas) else None,
        "max_triangle_area_m2": float(np.max(areas)) if len(areas) else None,
        "label_counts": label_counts,
    }


def build_pygeo_case(set_name: str, index: int, output_dir: Path):
    require_development_set(set_name)
    from aeris.geometry.registry import get_geometry_generator

    design = sample(set_name, int(index))
    return get_geometry_generator("bwb_segmented").run_full_case(
        sample=design,
        config=_config(),
        output_dir=Path(output_dir),
        save_plot=False,
        build_aerosandbox=False,
    )


def build_surface(
    pygeo_result: Any,
    *,
    level: str,
    te_variant: str,
    policy: dict[str, Any] | None = None,
) -> SurfaceMesh:
    policy = policy or load_policy()
    spec = _level_spec(policy, level)
    variant = policy["geometry"]["trailing_edge_variants"].get(te_variant)
    if variant is None:
        raise KeyError(
            f"unknown TE variant {te_variant!r}; expected "
            f"{sorted(policy['geometry']['trailing_edge_variants'])}"
        )
    reference = dict(pygeo_result.pygeo_result.reference_values)
    L = float(reference["mean_aerodynamic_chord_m"])
    if not np.isfinite(L) or L <= 0.0:
        raise ValueError(f"invalid mean aerodynamic chord {L}")
    pygeo_build = pygeo_result.pygeo_result.pygeo
    pygeo = pygeo_build.geometry

    surface_h = float(spec["surface_edge_over_L"]) * L
    tip_h = float(spec["tip_surface_edge_over_L"]) * L
    te_h = float(spec["te_surface_edge_over_L"]) * L
    # Counts are geometric targets, not claims about every edge. Cosine spacing
    # resolves both LE and TE while physical-span inversion follows ADR-0015.
    max_chord = max(float(section.chord_m) for section in pygeo_result.pygeo_result.extracted)
    semi_span = 0.5 * float(reference["span_m"])
    n_u = max(17, int(math.ceil(1.15 * max_chord / surface_h)) + 1)
    n_v = max(13, int(math.ceil(1.10 * semi_span / surface_h)) + 1)
    # Cosine is the finest end clustering available at a given count; add points
    # only if even that cannot reach the declared TE/tip edge target.
    while max_chord * (1.0 - math.cos(math.pi / (n_u - 1))) * 0.5 > te_h:
        n_u += 1
    while semi_span * (1.0 - math.cos(math.pi / (n_v - 1))) * 0.5 > tip_h:
        n_v += 1
    # Request the declared edge targets directly instead of accepting whatever
    # end spacing the cosine happens to produce at that count.  The largest chord
    # and the full semi-span are the binding cases, so meeting the target there
    # meets it everywhere.
    u = _blended_parameters(n_u, te_h / max_chord)
    physical_span_fractions = _blended_parameters(n_v, tip_h / semi_span)
    v_parameters = span_parameters_for_fractions(pygeo_build, physical_span_fractions)

    sections: list[tuple[Array, Array, dict[str, Any]]] = []
    for fraction, v in zip(physical_span_fractions, v_parameters, strict=True):
        upper, lower, frame = _opened_section(
            pygeo,
            u,
            float(v),
            te_abs_m=float(variant["absolute_m"]),
            te_floor_frac=float(variant["local_chord_fraction"]),
        )
        if fraction == 0.0:
            upper[:, 1] = 0.0
            lower[:, 1] = 0.0
        sections.append((upper, lower, frame))

    registry = _PointRegistry(max(1.0e-12, 1.0e-10 * L))
    triangles: list[tuple[int, int, int]] = []
    labels: list[str] = []
    triangle_span: list[float] = []
    side_grids: dict[int, tuple[Array, Array]] = {}

    def add_triangle(nodes: tuple[int, int, int], label: str, span_fraction: float) -> None:
        if len(set(nodes)) != 3:
            raise ValueError(f"degenerate {label} triangle connectivity {nodes}")
        triangles.append(nodes)
        labels.append(label)
        triangle_span.append(float(span_fraction))

    for side in (1, -1):
        upper_grid = np.empty((n_v, n_u), dtype=np.int64)
        lower_grid = np.empty((n_v, n_u), dtype=np.int64)
        for j, (upper, lower, _frame) in enumerate(sections):
            for i in range(n_u):
                up = upper[i].copy()
                lo = lower[i].copy()
                up[1] *= side
                lo[1] *= side
                upper_grid[j, i] = registry.add(up)
                lower_grid[j, i] = registry.add(lo)
        side_grids[side] = (upper_grid, lower_grid)
        for j in range(n_v - 1):
            span_mid = 0.5 * (physical_span_fractions[j] + physical_span_fractions[j + 1])
            for i in range(n_u - 1):
                a, b = int(upper_grid[j, i]), int(upper_grid[j, i + 1])
                c, d = int(upper_grid[j + 1, i]), int(upper_grid[j + 1, i + 1])
                add_triangle((a, b, d), "wall_upper", span_mid)
                add_triangle((a, d, c), "wall_upper", span_mid)
                a, b = int(lower_grid[j, i]), int(lower_grid[j, i + 1])
                c, d = int(lower_grid[j + 1, i]), int(lower_grid[j + 1, i + 1])
                add_triangle((a, d, b), "wall_lower", span_mid)
                add_triangle((a, c, d), "wall_lower", span_mid)

            # Numerical trailing-edge base between upper/lower u=0 curves.
            a = int(upper_grid[j, 0])
            b = int(lower_grid[j, 0])
            c = int(upper_grid[j + 1, 0])
            d = int(lower_grid[j + 1, 0])
            add_triangle((a, c, d), "wall_te", span_mid)
            add_triangle((a, d, b), "wall_te", span_mid)

        # Flat declared tip cap.  The tip section is a thin cambered airfoil and is
        # therefore NOT star-shaped about the mean of its boundary points, so a
        # centre fan emits triangles that leave the section and cut the lower
        # surface (measured: 24 wall_lower/wall_tip self-intersections at index 0).
        # Instead close the section by laddering the upper and lower tip curves at
        # matching chordwise stations.  Every triangle is spanned by one chordwise
        # step and the local thickness, so the cap stays inside the section, adds
        # no interior node, and keeps every boundary edge conformal with the
        # adjacent wall_upper / wall_lower / wall_te faces.
        upper_tip = [int(node) for node in upper_grid[-1]]
        lower_tip = [int(node) for node in lower_grid[-1]]
        # Perimeter walks the upper curve TE->LE then the lower curve back,
        # skipping the shared leading-edge node and the repeated TE corner.
        perimeter = upper_tip + [n for n in reversed(lower_tip) if n not in (upper_tip[-1],)]
        deduped: list[int] = []
        for node in perimeter:
            if node not in deduped:
                deduped.append(node)
        cap = _polygon_delaunay_triangles(
            np.asarray([registry.points[n] for n in deduped], dtype=float),
            registry.tolerance,
        )
        if cap is not None:
            for local in cap:
                add_triangle(
                    (deduped[local[0]], deduped[local[1]], deduped[local[2]]),
                    "wall_tip",
                    1.0,
                )
            continue
        # Verified fallback: the chordwise ladder, used only when Delaunay cannot
        # reproduce every perimeter edge.  It is always conformal by construction.
        for i in range(n_u - 1):
            a, b = upper_tip[i], upper_tip[i + 1]
            d, c = lower_tip[i], lower_tip[i + 1]
            # At the shared leading-edge node the quad collapses to one triangle.
            if b == c:
                add_triangle((a, b, d), "wall_tip", 1.0)
                continue
            if a == d:
                add_triangle((a, b, c), "wall_tip", 1.0)
                continue
            corners = np.asarray(
                [registry.points[n] for n in (a, b, c, d)], dtype=float
            )
            if _best_quad_diagonal(corners):
                add_triangle((a, b, c), "wall_tip", 1.0)
                add_triangle((a, c, d), "wall_tip", 1.0)
            else:
                add_triangle((a, b, d), "wall_tip", 1.0)
                add_triangle((b, c, d), "wall_tip", 1.0)

    points = np.asarray(registry.points, dtype=float)
    fidelity_distances: list[float] = []
    fidelity_fractions: list[float] = []
    fidelity_by_side_m: dict[str, float] = {}
    facet_distances: list[float] = []
    facet_fractions: list[float] = []
    facet_by_side_m: dict[str, float] = {}
    for side, (upper_grid, lower_grid) in side_grids.items():
        for j, (_upper, _lower, frame) in enumerate(sections):
            expected_upper = _opened_points_at_u(
                pygeo, u, float(v_parameters[j]), frame=frame, upper=True
            )
            expected_lower = _opened_points_at_u(
                pygeo, u, float(v_parameters[j]), frame=frame, upper=False
            )
            shared_le = 0.5 * (expected_upper[-1] + expected_lower[-1])
            expected_upper[-1] = shared_le
            expected_lower[-1] = shared_le
            if physical_span_fractions[j] == 0.0:
                expected_upper[:, 1] = 0.0
                expected_lower[:, 1] = 0.0
            expected_upper[:, 1] *= side
            expected_lower[:, 1] *= side
            for name, grid, expected in (
                ("upper", upper_grid, expected_upper),
                ("lower", lower_grid, expected_lower),
            ):
                distances = np.linalg.norm(points[grid[j]] - expected, axis=1)
                fidelity_distances.extend(distances.tolist())
                fidelity_fractions.extend((distances / float(frame["chord_m"])).tolist())
                key = f"{'positive' if side > 0 else 'negative'}_{name}"
                fidelity_by_side_m[key] = max(
                    fidelity_by_side_m.get(key, 0.0), float(np.max(distances))
                )
        # Node-on-surface checks alone do not bound the planar-facet error.
        # Independently sample both triangle centroids in every OML quad and
        # compare them with the exact opened pyGeo surface at the corresponding
        # parametric centroid. TE strips and flat tip caps are declared planar
        # numerical geometry and therefore need no curved-OML comparison.
        for j in range(n_v - 1):
            v0 = float(v_parameters[j])
            v1 = float(v_parameters[j + 1])
            centroid_specs = (
                ((u[:-1] + 2.0 * u[1:]) / 3.0, (2.0 * v0 + v1) / 3.0, 1),
                ((2.0 * u[:-1] + u[1:]) / 3.0, (v0 + 2.0 * v1) / 3.0, 2),
            )
            for centroid_u, centroid_v, triangle_kind in centroid_specs:
                _, _, frame = _opened_section(
                    pygeo,
                    u,
                    centroid_v,
                    te_abs_m=float(variant["absolute_m"]),
                    te_floor_frac=float(variant["local_chord_fraction"]),
                )
                for name, grid, upper in (
                    ("upper", upper_grid, True),
                    ("lower", lower_grid, False),
                ):
                    expected = _opened_points_at_u(
                        pygeo,
                        centroid_u,
                        centroid_v,
                        frame=frame,
                        upper=upper,
                    )
                    expected[:, 1] *= side
                    if triangle_kind == 1:
                        node_rows = np.column_stack((grid[j, :-1], grid[j, 1:], grid[j + 1, 1:]))
                    else:
                        node_rows = np.column_stack(
                            (grid[j, :-1], grid[j + 1, 1:], grid[j + 1, :-1])
                        )
                    actual = np.mean(points[node_rows], axis=1)
                    distances = np.linalg.norm(actual - expected, axis=1)
                    facet_distances.extend(distances.tolist())
                    facet_fractions.extend((distances / float(frame["chord_m"])).tolist())
                    key = f"{'positive' if side > 0 else 'negative'}_{name}"
                    facet_by_side_m[key] = max(
                        facet_by_side_m.get(key, 0.0), float(np.max(distances))
                    )
    connectivity = np.asarray(triangles, dtype=np.int64)
    connectivity, orientation = orient_closed_surface(points, connectivity)
    topology = surface_topology_report(points, connectivity, labels)
    topology.update(
        self_intersection_report(
            points,
            connectivity,
            tolerance=max(1.0e-13, 1.0e-10 * L),
        )
    )
    required = set(policy["geometry"]["required_surface_labels"])
    observed = {label for label, count in topology["label_counts"].items() if count > 0}
    topology["labels_exact"] = observed == required
    topology["required_labels"] = sorted(required)
    topology["observed_labels"] = sorted(observed)

    te_errors = np.asarray([frame["te_relative_error"] for _, _, frame in sections])
    # The thinnest realized trailing edge bounds how far prisms may be extruded
    # before opposing fronts collide; see the boundary-layer amendment.
    realized_te = np.asarray([frame["realized_te_m"] for _, _, frame in sections])
    max_fidelity_m = max(fidelity_distances, default=float("inf"))
    max_fidelity_fraction = max(fidelity_fractions, default=float("inf"))
    max_facet_distance_m = max(facet_distances, default=float("inf"))
    max_facet_fraction = max(facet_fractions, default=float("inf"))
    max_source_fraction = max(max_fidelity_fraction, max_facet_fraction)
    source_gates = policy["mesh_gates"]["source_geometry"]
    # Node fidelity (correctness) and facet chord error (resolution) are graded
    # against separate limits; a single grid-independent threshold is not
    # satisfiable by any preregistered level.  See ADR-0017 facet amendment.
    fidelity_limit = float(source_gates["max_distance_over_local_chord"])
    facet_limits = source_gates["max_facet_centroid_over_local_chord"]
    if level not in facet_limits:
        raise KeyError(
            f"no facet-centroid fidelity limit declared for level {level!r}; "
            f"expected one of {sorted(facet_limits)}"
        )
    facet_limit = float(facet_limits[level])
    fidelity = {
        "reference": "CFD-safe pyGeo loft after the declared TE opening",
        "instrument": (
            "each tracked upper/lower source node is independently re-evaluated "
            "on the pyGeo B-spline at its exact (u,v) coordinate; every OML "
            "triangle centroid is separately checked against its exact "
            "parametric centroid"
        ),
        "tracked_node_evaluations": len(fidelity_distances),
        "tracked_facet_centroid_evaluations": len(facet_distances),
        "construction_max_distance_m": max_fidelity_m,
        "construction_max_distance_over_local_chord": max_fidelity_fraction,
        "max_node_to_parametric_surface_m": max_fidelity_m,
        "max_node_distance_over_local_chord": max_fidelity_fraction,
        "max_facet_centroid_to_parametric_surface_m": max_facet_distance_m,
        "max_facet_centroid_distance_over_local_chord": max_facet_fraction,
        "max_fraction_of_local_chord": max_source_fraction,
        "oml_max_by_side_m": fidelity_by_side_m,
        "oml_facet_centroid_max_by_side_m": facet_by_side_m,
        "max_te_opening_relative_error": float(np.max(te_errors)),
        "min_realized_te_opening_m": float(np.min(realized_te)),
        "max_realized_te_opening_m": float(np.max(realized_te)),
        "limit_distance_over_local_chord": fidelity_limit,
        "limit_fraction_of_local_chord": fidelity_limit,
        "limit_facet_centroid_over_local_chord": facet_limit,
        "node_fidelity_passed": max_fidelity_fraction <= fidelity_limit,
        "facet_fidelity_passed": max_facet_fraction <= facet_limit,
        "limit_te_opening_relative_error": float(
            policy["mesh_gates"]["source_geometry"]["max_te_opening_relative_error"]
        ),
        "passed": (
            max_fidelity_fraction <= fidelity_limit
            and max_facet_fraction <= facet_limit
        ),
    }
    failures: list[str] = []
    if not topology["finite"]:
        failures.append("nonfinite_surface_coordinate")
    for metric in (
        "boundary_edge_count",
        "nonmanifold_edge_count",
        "zero_area_face_count",
        "duplicate_face_count",
    ):
        if topology[metric] != 0:
            failures.append(metric)
    if not topology["labels_exact"]:
        failures.append("surface_labels")
    if topology.get("self_intersection_count") != 0:
        failures.append("self_intersection_count")
    if orientation["connected_components"] != 1 or orientation["enclosed_signed_volume_m3"] <= 0:
        failures.append("surface_orientation_or_volume")
    if fidelity["max_te_opening_relative_error"] > fidelity["limit_te_opening_relative_error"]:
        failures.append("trailing_edge_opening")
    if not fidelity["node_fidelity_passed"]:
        failures.append("surface_node_fidelity")
    if not fidelity["facet_fidelity_passed"]:
        failures.append("surface_facet_fidelity")

    metadata = {
        "schema": SURFACE_SCHEMA,
        "geometry_id": pygeo_result.pygeo_result.geometry_id,
        "master_geometry": "direct pyGeo B-spline evaluation",
        "modeled_domain": "full_mirrored_wing",
        "level": level,
        "level_spec": spec,
        "te_variant": te_variant,
        "te_rule": variant,
        "reference_values": reference,
        "planform": _planform_record(pygeo_result.pygeo_result.stations),
        "sampling": {
            "chordwise_points": n_u,
            "half_span_points": n_v,
            "physical_span_fractions": physical_span_fractions.tolist(),
            "pygeo_v_parameters": v_parameters.tolist(),
            "chordwise_parameters": u.tolist(),
            "section_chords_m": [float(frame["chord_m"]) for _, _, frame in sections],
            "surface_edge_target_m": surface_h,
            "te_edge_target_m": te_h,
            "tip_edge_target_m": tip_h,
        },
        "topology": topology,
        "orientation": orientation,
        "fidelity": fidelity,
        "accepted_pre_gmsh": not failures,
        "failure_reasons": failures,
    }
    if failures:
        raise ValueError("S7 source surface failed pre-Gmsh gates: " + ", ".join(failures))
    return SurfaceMesh(
        points=points,
        triangles=connectivity,
        labels=tuple(labels),
        triangle_span_fraction=np.asarray(triangle_span, dtype=float),
        metadata=metadata,
    )


def write_surface(surface: SurfaceMesh, output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = output_dir / "source_surface.npz"
    np.savez_compressed(
        npz_path,
        points=np.asarray(surface.points, dtype=np.float64),
        triangles=np.asarray(surface.triangles, dtype=np.int64),
        labels=np.asarray(surface.labels, dtype="U32"),
        triangle_span_fraction=np.asarray(surface.triangle_span_fraction, dtype=np.float64),
    )
    report_path = write_json(output_dir / "source_surface_report.json", surface.metadata)
    # ASCII STL is diagnostic only; NPZ is the authoritative labeled source.
    stl_path = output_dir / "source_surface.stl"
    lines = ["solid aeris_s7_wall"]
    for triangle in surface.triangles:
        p0, p1, p2 = surface.points[triangle]
        normal = np.cross(p1 - p0, p2 - p0)
        normal /= max(float(np.linalg.norm(normal)), np.finfo(float).tiny)
        lines.append(f"  facet normal {normal[0]:.17e} {normal[1]:.17e} {normal[2]:.17e}")
        lines.append("    outer loop")
        for point in (p0, p1, p2):
            lines.append(f"      vertex {point[0]:.17e} {point[1]:.17e} {point[2]:.17e}")
        lines.extend(("    endloop", "  endfacet"))
    lines.append("endsolid aeris_s7_wall")
    from .common import atomic_write_text

    atomic_write_text(stl_path, "\n".join(lines) + "\n")
    return {
        "surface_npz": str(npz_path.resolve()),
        "surface_npz_sha256": sha256_file(npz_path),
        "surface_report": str(report_path.resolve()),
        "surface_report_sha256": sha256_file(report_path),
        "surface_stl": str(stl_path.resolve()),
        "surface_stl_sha256": sha256_file(stl_path),
    }


def load_surface(path: Path, report_path: Path | None = None) -> SurfaceMesh:
    with np.load(Path(path), allow_pickle=False) as archive:
        points = np.asarray(archive["points"], dtype=float)
        triangles = np.asarray(archive["triangles"], dtype=np.int64)
        labels = tuple(str(value) for value in archive["labels"].tolist())
        span = np.asarray(archive["triangle_span_fraction"], dtype=float)
    metadata: dict[str, Any] = {}
    candidate = report_path or Path(path).with_name("source_surface_report.json")
    if candidate.is_file():
        metadata = json.loads(candidate.read_text(encoding="utf-8"))
    return SurfaceMesh(points, triangles, labels, span, metadata)


def build_and_write_surface(
    *,
    set_name: str,
    index: int,
    level: str,
    te_variant: str,
    output_dir: Path,
) -> tuple[Any, SurfaceMesh, dict[str, Any]]:
    require_development_set(set_name)
    case_dir = Path(output_dir)
    case = build_pygeo_case(set_name, index, case_dir / "pygeo")
    if case.pygeo_result is None:
        raise RuntimeError("canonical geometry generator did not produce pyGeo geometry")
    surface = build_surface(case, level=level, te_variant=te_variant)
    surface.metadata["geometry_set"] = str(set_name)
    surface.metadata["development_index"] = int(index)
    surface.metadata["source_digest"] = source_digest()
    surface.metadata["policy_sha256"] = sha256_file(POLICY_PATH)
    artifacts = write_surface(surface, case_dir)
    return case, surface, artifacts
