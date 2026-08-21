"""Gmsh tri-surface -> prism-layer -> tetrahedral-core construction for S7."""

from __future__ import annotations

import math
import os
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .common import load_policy, peak_self_rss_bytes, sha256_file, write_json
from .geometry import SurfaceMesh
from .wall_mapping import source_wall_rows

GMSH_REPORT_SCHEMA = "aeris.s7.gmsh_build.v1"


def cumulative_layer_heights(first_height: float, layers: int, growth: float) -> list[float]:
    first_height = float(first_height)
    growth = float(growth)
    layers = int(layers)
    if first_height <= 0.0 or not np.isfinite(first_height):
        raise ValueError("first boundary-layer height must be finite and positive")
    if layers < 1:
        raise ValueError("at least one boundary-layer element is required")
    if growth < 1.0 or not np.isfinite(growth):
        raise ValueError("boundary-layer growth ratio must be finite and >= 1")
    increments = first_height * growth ** np.arange(layers, dtype=float)
    return np.cumsum(increments).tolist()


def resolved_mesh_spec(
    surface: SurfaceMesh,
    *,
    level: str,
    candidate_index: int,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or load_policy()
    if level == "laptop_smoke":
        raw = dict(policy["laptop_smoke"])
        evidence_tier = "laptop_smoke"
    else:
        if level not in policy["grid_family"]["levels"]:
            raise KeyError(f"unknown grid level {level!r}")
        raw = dict(policy["grid_family"]["levels"][level])
        evidence_tier = "development"
    candidates = policy["gmsh"]["retries"]
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise IndexError(f"candidate index {candidate_index} is outside [0, {len(candidates)})")
    candidate = dict(candidates[candidate_index])
    L = float(surface.metadata["reference_values"]["mean_aerodynamic_chord_m"])
    keys = (
        "surface_edge_over_L",
        "te_surface_edge_over_L",
        "tip_surface_edge_over_L",
        "first_cell_height_over_L",
        "near_core_edge_over_L",
        "far_core_edge_over_L",
        "wake_edge_over_L",
    )
    absolute = {key.removesuffix("_over_L") + "_m": float(raw[key]) * L for key in keys}
    requested_layers = int(raw["prism_layers"])
    growth = float(raw["prism_growth_ratio"])
    first_height = absolute["first_cell_height_m"]
    bl_policy = policy["gmsh"]["boundary_layer"]
    te_opening_m = surface.metadata.get("fidelity", {}).get("min_realized_te_opening_m")
    applied_layers = requested_layers
    limit_m: float | None = None
    if bool(bl_policy["derive_prism_layers_from_te_opening"]):
        if (
            te_opening_m is None
            or not np.isfinite(float(te_opening_m))
            or float(te_opening_m) <= 0.0
        ):
            raise ValueError(
                "cannot derive prism layers: the source surface reports no finite "
                "minimum realized trailing-edge opening"
            )
        limit_m = float(bl_policy["max_total_thickness_over_te_opening"]) * float(te_opening_m)
        minimum_layers = int(bl_policy["min_prism_layers"])
        while (
            applied_layers > minimum_layers
            and cumulative_layer_heights(first_height, applied_layers, growth)[-1] > limit_m
        ):
            applied_layers -= 1
    heights = cumulative_layer_heights(first_height, applied_layers, growth)
    if limit_m is not None and heights[-1] > limit_m:
        # Fail closed: the floor on layer count cannot be met inside the opening.
        raise ValueError(
            f"boundary layer of {heights[-1]:.6e} m at the {bl_policy['min_prism_layers']}-layer "
            f"floor exceeds the {limit_m:.6e} m trailing-edge budget; a blunter TE variant or a "
            "smaller first cell height is required"
        )
    # The applied count is authoritative for every downstream consumer.
    raw = dict(raw)
    raw["prism_layers"] = applied_layers
    farfield = dict(policy["farfield"])
    if level == "laptop_smoke":
        farfield.update(dict(policy["laptop_smoke"]["farfield"]))
    return {
        "level": level,
        "evidence_tier": evidence_tier,
        "characteristic_length_m": L,
        "relative": raw,
        "absolute": absolute,
        "boundary_layer_cumulative_heights_m": heights,
        "boundary_layer_total_thickness_m": heights[-1],
        "boundary_layer": {
            "requested_prism_layers": requested_layers,
            "applied_prism_layers": applied_layers,
            "layers_removed_for_te_budget": requested_layers - applied_layers,
            "min_realized_te_opening_m": te_opening_m,
            "max_total_thickness_m": limit_m,
            "first_cell_height_m": first_height,
            "growth_ratio": growth,
        },
        "farfield": farfield,
        "candidate_index": int(candidate_index),
        "candidate": candidate,
    }


def estimate_cells(surface: SurfaceMesh, spec: Mapping[str, Any], policy: dict[str, Any]) -> int:
    n_prism = len(surface.triangles) * int(spec["relative"]["prism_layers"])
    points = np.asarray(surface.points)
    L = float(spec["characteristic_length_m"])
    far = spec["farfield"]
    xmin, ymin, zmin = points.min(axis=0)
    xmax, ymax, zmax = points.max(axis=0)
    dx = (xmax - xmin) + (float(far["upstream_over_L"]) + float(far["downstream_over_L"])) * L
    dy = (ymax - ymin) + 2.0 * float(far["radial_over_L"]) * L
    dz = (zmax - zmin) + 2.0 * float(far["radial_over_L"]) * L
    absolute = spec["absolute"]
    far_h = float(absolute["far_core_edge_m"])
    near_h = float(absolute["near_core_edge_m"])
    wake_h = float(absolute["wake_edge_m"])
    tiny = np.finfo(float).tiny
    # Conservative refusal estimate: count the entire box at the far size, then
    # over-count near-body and wake boxes at their finer sizes.  It is a memory
    # ceiling, never a promised production cell count.
    far_cells = 6.0 * dx * dy * dz / max(far_h**3, tiny)
    body_extent = np.maximum(np.ptp(points, axis=0), near_h)
    near_extent = body_extent + 12.0 * near_h
    near_cells = 6.0 * float(np.prod(near_extent)) / max(near_h**3, tiny)
    wake_length = min(dx, float(far["wake_length_over_L"]) * L)
    wake_cross_section = max(float(body_extent[1]), near_h) * max(float(body_extent[2]), near_h)
    wake_cells = 6.0 * wake_length * wake_cross_section / max(wake_h**3, tiny)
    n_tet = int(math.ceil(far_cells + near_cells + wake_cells))
    return int(n_prism + n_tet)


def _add_outer_box(gmsh: Any, bounds: tuple[float, float, float, float, float, float], lc: float):
    xmin, ymin, zmin, xmax, ymax, zmax = bounds
    geo = gmsh.model.geo
    point_coordinates = (
        (xmin, ymin, zmin),
        (xmax, ymin, zmin),
        (xmax, ymax, zmin),
        (xmin, ymax, zmin),
        (xmin, ymin, zmax),
        (xmax, ymin, zmax),
        (xmax, ymax, zmax),
        (xmin, ymax, zmax),
    )
    points = [geo.addPoint(*xyz, float(lc)) for xyz in point_coordinates]
    edges = [
        geo.addLine(points[a], points[b])
        for a, b in (
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 0),
            (4, 5),
            (5, 6),
            (6, 7),
            (7, 4),
            (0, 4),
            (1, 5),
            (2, 6),
            (3, 7),
        )
    ]
    loops = (
        (edges[0], edges[1], edges[2], edges[3]),
        (edges[4], edges[5], edges[6], edges[7]),
        (edges[0], edges[9], -edges[4], -edges[8]),
        (edges[1], edges[10], -edges[5], -edges[9]),
        (edges[2], edges[11], -edges[6], -edges[10]),
        (edges[3], edges[8], -edges[7], -edges[11]),
    )
    surfaces = [geo.addPlaneSurface([geo.addCurveLoop(list(loop))]) for loop in loops]
    return points, edges, surfaces


def _farfield_bounds(surface: SurfaceMesh, farfield: Mapping[str, Any], L: float):
    minimum = np.asarray(surface.points).min(axis=0)
    maximum = np.asarray(surface.points).max(axis=0)
    far = farfield
    return (
        float(minimum[0] - float(far["upstream_over_L"]) * L),
        float(minimum[1] - float(far["radial_over_L"]) * L),
        float(minimum[2] - float(far["radial_over_L"]) * L),
        float(maximum[0] + float(far["downstream_over_L"]) * L),
        float(maximum[1] + float(far["radial_over_L"]) * L),
        float(maximum[2] + float(far["radial_over_L"]) * L),
    )


def trailing_edge_sample_points(
    surface: SurfaceMesh, *, target_spacing: float, max_points: int
) -> np.ndarray:
    """Densified centre-line of the numerical trailing edge, for core refinement.

    The trailing-edge ribbon is the only place where a millimetre-scale feature
    is embedded in a centimetre-scale field, so it is the only place the core
    needs a size of its own.

    A Distance field sees a point cloud, not a curve: sampling only the existing
    trailing-edge nodes leaves gaps of roughly one spanwise step (measured 18.6 mm
    at graded resolution), so points midway between samples are already beyond the
    refinement radius and the field silently does nothing.  The centre-line is
    therefore resampled at the refinement size itself.
    """
    labels = np.asarray(surface.labels)
    te_faces = np.asarray(surface.triangles)[labels == "wall_te"]
    if len(te_faces) == 0:
        return np.empty((0, 3), dtype=float)
    points = np.asarray(surface.points, dtype=float)
    nodes = np.unique(te_faces)
    spacing = max(float(target_spacing), np.finfo(float).tiny)

    collected: list[np.ndarray] = []
    for side in (1.0, -1.0):
        chosen = [n for n in nodes if np.sign(points[n][1]) == side or points[n][1] == 0.0]
        if len(chosen) < 2:
            continue
        # One trailing-edge station per distinct spanwise position; its centre is
        # the mean of the upper and lower corner nodes there.
        ordered = sorted(chosen, key=lambda n: float(points[n][1]))
        stations: list[np.ndarray] = []
        bucket = [ordered[0]]
        for node in ordered[1:]:
            if abs(float(points[node][1] - points[bucket[-1]][1])) <= 0.25 * spacing:
                bucket.append(node)
            else:
                stations.append(points[bucket].mean(axis=0))
                bucket = [node]
        stations.append(points[bucket].mean(axis=0))
        line = np.asarray(stations, dtype=float)
        if len(line) < 2:
            collected.append(line)
            continue
        for start, end in zip(line[:-1], line[1:], strict=True):
            steps = max(1, int(math.ceil(float(np.linalg.norm(end - start)) / spacing)))
            for k in range(steps):
                collected.append((start + (end - start) * (k / steps))[None, :])
        collected.append(line[-1][None, :])

    if not collected:
        return np.empty((0, 3), dtype=float)
    dense = np.vstack(collected)
    if len(dense) > int(max_points):
        step = int(math.ceil(len(dense) / float(max_points)))
        dense = dense[::step]
    return dense


def _set_background_field(
    gmsh: Any,
    *,
    top_surfaces: list[int],
    bounds: tuple[float, float, float, float, float, float],
    body_bounds: tuple[float, float, float, float, float, float],
    near_size: float,
    far_size: float,
    wake_size: float,
    bl_thickness: float,
    wake_length: float,
    te_points: np.ndarray,
    te_refinement: Mapping[str, Any],
    te_opening: float,
    growth_ratio: float,
) -> dict[str, int]:
    def ramp_length(small: float, large: float) -> float:
        """Distance needed to grow `small` to `large` at the declared ratio.

        Sum of a geometric cell sequence, so the field asks for a transition the
        mesher can actually build one cell at a time.
        """
        if large <= small or growth_ratio <= 1.0:
            return max(large - small, 0.0)
        return small * (large / small - 1.0) / (growth_ratio - 1.0)

    field = gmsh.model.mesh.field
    distance = field.add("Distance")
    field.setNumbers(distance, "FacesList", top_surfaces)
    field.setNumber(distance, "Sampling", 200)
    threshold = field.add("Threshold")
    field.setNumber(threshold, "InField", distance)
    field.setNumber(threshold, "SizeMin", near_size)
    field.setNumber(threshold, "SizeMax", far_size)
    field.setNumber(threshold, "DistMin", max(bl_thickness, near_size))
    field.setNumber(
        threshold,
        "DistMax",
        max(bl_thickness, near_size) + ramp_length(near_size, far_size),
    )

    xmin, ymin, zmin, xmax, ymax, zmax = body_bounds
    outer_xmin, outer_ymin, outer_zmin, outer_xmax, outer_ymax, outer_zmax = bounds
    wake = field.add("Box")
    field.setNumber(wake, "VIn", wake_size)
    field.setNumber(wake, "VOut", far_size)
    field.setNumber(wake, "XMin", xmax)
    field.setNumber(wake, "XMax", min(outer_xmax, xmax + wake_length))
    field.setNumber(wake, "YMin", max(outer_ymin, ymin - 0.5 * (ymax - ymin)))
    field.setNumber(wake, "YMax", min(outer_ymax, ymax + 0.5 * (ymax - ymin)))
    field.setNumber(wake, "ZMin", max(outer_zmin, zmin - 0.5 * (zmax - zmin + near_size)))
    field.setNumber(wake, "ZMax", min(outer_zmax, zmax + 0.5 * (zmax - zmin + near_size)))
    # Without a transition thickness a Gmsh Box field steps discontinuously from
    # VIn to VOut across its faces, so cells straddling the wake box differ by the
    # full wake/far size ratio in one jump.  That is a dominant contributor to the
    # adjacent-core volume ratio.  Grade the step over several wake cells instead.
    field.setNumber(wake, "Thickness", ramp_length(wake_size, far_size))
    fields = [threshold, wake]
    identifiers = {
        "distance": distance,
        "threshold": threshold,
        "wake_box": wake,
    }
    if bool(te_refinement["enabled"]) and len(te_points):
        # Distance to the trailing-edge line, offset by the boundary-layer
        # thickness because the core begins at the prism cap.
        tags = [
            gmsh.model.geo.addPoint(float(x), float(y), float(z))
            for x, y, z in te_points
        ]
        gmsh.model.geo.synchronize()
        te_distance = field.add("Distance")
        field.setNumbers(te_distance, "PointsList", tags)
        te_threshold = field.add("Threshold")
        field.setNumber(te_threshold, "InField", te_distance)
        field.setNumber(
            te_threshold, "SizeMin", float(te_refinement["size_over_te_opening"]) * te_opening
        )
        # Grade into the near-body size, not the far-field size: a ramp from a few
        # millimetres to the far size over a couple of centimetres is far too steep
        # to be realised, and the outer Threshold already handles near -> far.
        field.setNumber(te_threshold, "SizeMax", near_size)
        field.setNumber(
            te_threshold,
            "DistMin",
            bl_thickness + float(te_refinement["dist_min_over_te_opening"]) * te_opening,
        )
        field.setNumber(
            te_threshold,
            "DistMax",
            bl_thickness
            + max(
                float(te_refinement["dist_max_over_te_opening"]) * te_opening,
                ramp_length(
                    float(te_refinement["size_over_te_opening"]) * te_opening, near_size
                ),
            ),
        )
        fields.append(te_threshold)
        identifiers["te_distance"] = te_distance
        identifiers["te_threshold"] = te_threshold
        identifiers["te_sample_points"] = len(tags)
    minimum = field.add("Min")
    field.setNumbers(minimum, "FieldsList", fields)
    field.setAsBackgroundMesh(minimum)
    identifiers["minimum"] = minimum
    return identifiers


def _all_nodes(gmsh: Any) -> tuple[np.ndarray, np.ndarray, dict[int, int]]:
    tags, flat_coordinates, _ = gmsh.model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    coordinates = np.asarray(flat_coordinates, dtype=float).reshape(-1, 3)
    order = np.argsort(tags)
    tags = tags[order]
    coordinates = coordinates[order]
    return tags, coordinates, {int(tag): i for i, tag in enumerate(tags)}


def _entity_surface_elements(gmsh: Any, entities: Iterable[int]):
    result: list[tuple[int, np.ndarray]] = []
    for entity in entities:
        types, _element_tags, node_tags = gmsh.model.mesh.getElements(2, int(entity))
        for element_type, flat in zip(types, node_tags, strict=True):
            _name, dim, _order, nodes_per_element, _local, _primary = (
                gmsh.model.mesh.getElementProperties(int(element_type))
            )
            if dim != 2:
                continue
            result.append(
                (int(element_type), np.asarray(flat, dtype=np.int64).reshape(-1, nodes_per_element))
            )
    return result


def write_su2_mesh(
    gmsh: Any,
    path: Path,
    *,
    surface: SurfaceMesh,
    source_surface_entity: int,
    farfield_surfaces: Iterable[int],
) -> dict[str, Any]:
    """Write linear SU2 elements and split source wall triangles by S7 label."""
    all_tags, all_coordinates, _all_index = _all_nodes(gmsh)
    # Only nodes referenced by a volume element belong in an SU2 mesh.  Geometric
    # points that exist solely to drive a size field are meshed by Gmsh as
    # isolated vertices and must not leak into the point list; boundary faces are
    # faces of volume elements, so this set covers every marker too.
    used: set[int] = set()
    for _type, _tags, flat in zip(*gmsh.model.mesh.getElements(3), strict=True):
        used.update(int(tag) for tag in np.asarray(flat, dtype=np.int64))
    keep = np.array(sorted(used), dtype=np.int64)
    positions = np.searchsorted(all_tags, keep)
    if not np.array_equal(all_tags[positions], keep):
        raise ValueError("volume connectivity references nodes absent from the model")
    node_tags = keep
    coordinates = all_coordinates[positions]
    node_index = {int(tag): i for i, tag in enumerate(node_tags)}
    volume_types = {
        4: (10, 4, "tetrahedron"),
        5: (12, 8, "hexahedron"),
        6: (13, 6, "prism"),
        7: (14, 5, "pyramid"),
    }
    volume_rows: list[tuple[int, list[int]]] = []
    element_counts: dict[str, int] = {}
    types, _element_tags, connectivity = gmsh.model.mesh.getElements(3)
    for element_type, flat in zip(types, connectivity, strict=True):
        element_type = int(element_type)
        if element_type not in volume_types:
            name = gmsh.model.mesh.getElementProperties(element_type)[0]
            raise ValueError(f"unsupported SU2 volume element {element_type}: {name}")
        su2_code, width, name = volume_types[element_type]
        rows = np.asarray(flat, dtype=np.int64).reshape(-1, width)
        element_counts[name] = element_counts.get(name, 0) + len(rows)
        for row in rows:
            volume_rows.append((su2_code, [node_index[int(tag)] for tag in row]))

    wall_markers = source_wall_rows(
        gmsh,
        surface=surface,
        source_surface_entity=source_surface_entity,
    )
    wall_markers = {
        label: [(code, [node_index[int(tag)] for tag in tags]) for code, tags in rows]
        for label, rows in wall_markers.items()
    }

    far_rows: list[tuple[int, list[int]]] = []
    surface_types = {2: (5, 3), 3: (9, 4)}
    for element_type, rows in _entity_surface_elements(gmsh, farfield_surfaces):
        if element_type not in surface_types:
            name = gmsh.model.mesh.getElementProperties(element_type)[0]
            raise ValueError(f"unsupported SU2 farfield element {element_type}: {name}")
        su2_code, width = surface_types[element_type]
        if rows.shape[1] != width:
            raise ValueError(f"unexpected width for Gmsh element type {element_type}")
        for row in rows:
            far_rows.append((su2_code, [node_index[int(tag)] for tag in row]))
    markers = {**wall_markers, "farfield": far_rows}
    if any(not rows for rows in markers.values()):
        missing = [name for name, rows in markers.items() if not rows]
        raise ValueError(f"cannot write SU2 mesh; empty required marker(s): {missing}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("NDIME= 3\n")
            stream.write(f"NELEM= {len(volume_rows)}\n")
            for index, (code, nodes) in enumerate(volume_rows):
                stream.write(" ".join(map(str, (code, *nodes, index))) + "\n")
            stream.write(f"NPOIN= {len(node_tags)}\n")
            for index, point in enumerate(coordinates):
                stream.write(f"{point[0]:.17e} {point[1]:.17e} {point[2]:.17e} {index}\n")
            stream.write(f"NMARK= {len(markers)}\n")
            for name, rows in markers.items():
                stream.write(f"MARKER_TAG= {name}\n")
                stream.write(f"MARKER_ELEMS= {len(rows)}\n")
                for code, nodes in rows:
                    stream.write(" ".join(map(str, (code, *nodes))) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary_name).replace(path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "node_count": len(node_tags),
        "volume_element_count": len(volume_rows),
        "element_counts": element_counts,
        "marker_counts": {name: len(rows) for name, rows in markers.items()},
    }


def generate_mesh(
    surface: SurfaceMesh,
    *,
    output_dir: Path,
    level: str,
    candidate_index: int,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate one immutable Gmsh attempt; audit and retries are caller-owned."""
    policy = policy or load_policy()
    spec = resolved_mesh_spec(surface, level=level, candidate_index=candidate_index, policy=policy)
    candidate = spec["candidate"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "resolved_mesh_config.json", spec)
    msh_path = output_dir / "mesh.msh"
    su2_path = output_dir / "mesh.su2"
    gmsh_log_path = output_dir / "gmsh.log"
    report_path = output_dir / "gmsh_build_report.json"
    started = time.time()
    gmsh_initialized = False
    log_lines: list[str] = []
    try:
        import gmsh

        gmsh.initialize([])
        gmsh_initialized = True
        gmsh.logger.start()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        for option in ("Mesh.MaxNumThreads1D", "Mesh.MaxNumThreads2D", "Mesh.MaxNumThreads3D"):
            gmsh.option.setNumber(option, 1)
        gmsh.model.add("aeris_s7")
        gmsh_policy = policy["gmsh"]
        optimization_policy = str(gmsh_policy["post_generation_optimization"])
        optimize_passes = int(candidate["optimize_passes"])
        supported_optimization = {
            # Nothing runs after generation; the prism schedule is trivially safe.
            "disabled_preserve_prism_schedule",
            # Optimizers run against the tetrahedral core volume only.  The prism
            # schedule must still be verified by the audit, never assumed.
            "core_volume_only",
        }
        if optimization_policy not in supported_optimization:
            raise ValueError(
                f"unsupported S7 post-generation optimization policy: {optimization_policy!r}"
            )
        if (
            optimization_policy == "disabled_preserve_prism_schedule"
            and optimize_passes != 0
        ):
            raise ValueError(
                "post-generation optimization is disabled by policy; a candidate "
                "may not request optimization passes under it"
            )
        L = float(spec["characteristic_length_m"])
        gmsh.option.setNumber(
            "Geometry.Tolerance", float(gmsh_policy["geometry_tolerance_over_L"]) * L
        )
        gmsh.option.setNumber("Mesh.RandomFactor", float(gmsh_policy["random_factor"]))
        gmsh.option.setNumber("Mesh.RandomSeed", int(gmsh_policy["random_seed"]))
        gmsh.option.setNumber(
            "Mesh.MeshSizeFromPoints", int(bool(gmsh_policy["mesh_size_from_points"]))
        )
        gmsh.option.setNumber(
            "Mesh.MeshSizeFromCurvature", int(gmsh_policy["mesh_size_from_curvature"])
        )
        gmsh.option.setNumber(
            "Mesh.MeshSizeExtendFromBoundary",
            int(bool(gmsh_policy["mesh_size_extend_from_boundary"])),
        )
        # The pyGeo-derived wall triangulation is immutable. This algorithm
        # applies only to surfaces Gmsh generates around it (principally the
        # outer boundary); candidate IDs state that scope explicitly.
        gmsh.option.setNumber("Mesh.Algorithm", int(candidate["generated_surface_algorithm"]))
        gmsh.option.setNumber("Mesh.Algorithm3D", int(candidate["volume_algorithm"]))
        gmsh.option.setNumber("Mesh.MshFileVersion", float(gmsh_policy["msh_version"]))
        gmsh.option.setNumber("Mesh.Binary", int(bool(gmsh_policy["binary_mesh"])))
        gmsh.option.setNumber("Mesh.SaveAll", int(bool(gmsh_policy["save_all"])))
        gmsh.option.setNumber("Geometry.ExtrudeReturnLateralEntities", 0)

        source_surface = gmsh.model.addDiscreteEntity(2, 1)
        node_tags = np.arange(1, len(surface.points) + 1, dtype=np.int64)
        gmsh.model.mesh.addNodes(2, source_surface, node_tags, surface.points.ravel())
        element_tags = np.arange(1, len(surface.triangles) + 1, dtype=np.int64)
        gmsh.model.mesh.addElementsByType(
            source_surface,
            2,
            element_tags,
            (surface.triangles + 1).astype(np.int64).ravel(),
        )

        heights = list(spec["boundary_layer_cumulative_heights_m"])
        layers = int(spec["relative"]["prism_layers"])
        extrusion = gmsh.model.geo.extrudeBoundaryLayer(
            [(2, source_surface)], [1] * layers, heights, True
        )
        top_surfaces = [int(tag) for dim, tag in extrusion if dim == 2]
        boundary_layer_volumes = [int(tag) for dim, tag in extrusion if dim == 3]
        if not top_surfaces or not boundary_layer_volumes:
            raise RuntimeError(f"Gmsh returned incomplete boundary-layer topology: {extrusion}")

        absolute = spec["absolute"]
        outer_bounds = _farfield_bounds(surface, spec["farfield"], L)
        _outer_points, _outer_edges, farfield_surfaces = _add_outer_box(
            gmsh, outer_bounds, float(absolute["far_core_edge_m"])
        )
        outer_loop = gmsh.model.geo.addSurfaceLoop(farfield_surfaces)
        inner_loop = gmsh.model.geo.addSurfaceLoop(top_surfaces)
        core_volume = gmsh.model.geo.addVolume([outer_loop, inner_loop])
        gmsh.model.geo.synchronize()

        gmsh.model.addPhysicalGroup(2, [source_surface], name="wall_source")
        gmsh.model.addPhysicalGroup(2, farfield_surfaces, name="farfield")
        gmsh.model.addPhysicalGroup(3, [*boundary_layer_volumes, int(core_volume)], name="fluid")
        body_min = np.asarray(surface.points).min(axis=0)
        body_max = np.asarray(surface.points).max(axis=0)
        field_ids = _set_background_field(
            gmsh,
            top_surfaces=top_surfaces,
            bounds=outer_bounds,
            body_bounds=(*body_min.tolist(), *body_max.tolist()),
            near_size=float(absolute["near_core_edge_m"]),
            far_size=float(absolute["far_core_edge_m"]),
            wake_size=float(absolute["wake_edge_m"]),
            bl_thickness=float(spec["boundary_layer_total_thickness_m"]),
            wake_length=float(spec["farfield"]["wake_length_over_L"]) * L,
            te_points=trailing_edge_sample_points(
                surface,
                target_spacing=float(
                    policy["gmsh"]["te_core_refinement"]["size_over_te_opening"]
                )
                * float(surface.metadata["fidelity"]["min_realized_te_opening_m"]),
                max_points=int(policy["gmsh"]["te_core_refinement"]["max_sample_points"]),
            ),
            te_refinement=policy["gmsh"]["te_core_refinement"],
            te_opening=float(
                surface.metadata["fidelity"]["min_realized_te_opening_m"]
            ),
            growth_ratio=float(policy["gmsh"]["core_size_field"]["max_growth_ratio"]),
        )
        gmsh.option.setNumber(
            "Mesh.MeshSizeMin", min(float(absolute["near_core_edge_m"]), heights[0])
        )
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(absolute["far_core_edge_m"]))
        gmsh.model.mesh.generate(3)
        # Scope every optimizer to the core volume so the boundary-layer prisms
        # are never handed to a node-relocation pass.  Whether that is sufficient
        # is a measurement, made by the prism audit, not an assumption.
        optimize_targets = (
            [(3, int(core_volume))]
            if optimization_policy == "core_volume_only"
            else []
        )
        for _ in range(optimize_passes):
            # Global relocation is forbidden: it can move intermediate prism
            # nodes while leaving the wall and outer prism surface fixed,
            # destroying the prescribed first height and growth schedule.
            gmsh.model.mesh.optimize(
                str(candidate["optimize"]),
                dimTags=optimize_targets,
            )

        gmsh.write(str(msh_path))
        su2_report = write_su2_mesh(
            gmsh,
            su2_path,
            surface=surface,
            source_surface_entity=source_surface,
            farfield_surfaces=farfield_surfaces,
        )
        element_types, element_tags_by_type, _ = gmsh.model.mesh.getElements(3)
        gmsh_counts = {
            gmsh.model.mesh.getElementProperties(int(element_type))[0]: int(len(tags))
            for element_type, tags in zip(element_types, element_tags_by_type, strict=True)
        }
        log_lines = list(gmsh.logger.get())
        report = {
            "schema": GMSH_REPORT_SCHEMA,
            "status": "completed",
            "candidate": candidate,
            "spec": spec,
            "source_surface_entity": source_surface,
            "top_surface_entities": top_surfaces,
            "boundary_layer_volumes": boundary_layer_volumes,
            "core_volume": int(core_volume),
            "farfield_surface_entities": farfield_surfaces,
            "farfield_bounds_m": list(outer_bounds),
            "field_ids": field_ids,
            "gmsh_element_counts": gmsh_counts,
            "mesh_msh": str(msh_path.resolve()),
            "mesh_msh_sha256": sha256_file(msh_path),
            "mesh_su2": su2_report,
            "wall_time_s": time.time() - started,
            "peak_process_rss_bytes": peak_self_rss_bytes(),
        }
    except BaseException as exc:
        if gmsh_initialized:
            try:
                log_lines = list(gmsh.logger.get())
            except Exception:
                pass
        report = {
            "schema": GMSH_REPORT_SCHEMA,
            "status": "failed",
            "candidate": candidate,
            "spec": spec,
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "traceback": traceback.format_exc(),
            "wall_time_s": time.time() - started,
            "peak_process_rss_bytes": peak_self_rss_bytes(),
        }
        raise
    finally:
        from .common import atomic_write_text

        atomic_write_text(gmsh_log_path, "\n".join(log_lines) + ("\n" if log_lines else ""))
        if "report" in locals():
            report["gmsh_log"] = str(gmsh_log_path.resolve())
            report["gmsh_log_sha256"] = sha256_file(gmsh_log_path)
            write_json(report_path, report)
        if gmsh_initialized:
            try:
                gmsh.logger.stop()
            except Exception:
                pass
            gmsh.finalize()
    return report
