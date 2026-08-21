"""Coordinate-verified correspondence for Gmsh-renumbered S7 wall nodes."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from .geometry import LABELS, SurfaceMesh


def source_wall_correspondence(
    gmsh: Any, *, surface: SurfaceMesh, source_surface_entity: int
) -> dict[str, Any]:
    wall_tags, flat_wall_coordinates, _ = gmsh.model.mesh.getNodes(
        2, int(source_surface_entity), includeBoundary=True
    )
    wall_tags = np.asarray(wall_tags, dtype=np.int64)
    wall_coordinates = np.asarray(flat_wall_coordinates, dtype=float).reshape(-1, 3)
    if len(wall_tags) != len(surface.points):
        raise ValueError(
            f"Gmsh source wall has {len(wall_tags)} nodes; expected {len(surface.points)}"
        )
    distances, original_indices = cKDTree(surface.points).query(wall_coordinates, k=1)
    L = float(surface.metadata["reference_values"]["mean_aerodynamic_chord_m"])
    tolerance = max(1.0e-12, 1.0e-10 * L)
    if float(np.max(distances)) > tolerance:
        raise ValueError(f"Gmsh source wall moved by {float(np.max(distances)):.6e} m")
    if len(set(map(int, original_indices))) != len(surface.points):
        raise ValueError("Gmsh-to-source wall node correspondence is not bijective")
    gmsh_to_original = {
        int(tag): int(index) for tag, index in zip(wall_tags, original_indices, strict=True)
    }
    original_to_gmsh = np.empty(len(surface.points), dtype=np.int64)
    for tag, original in gmsh_to_original.items():
        original_to_gmsh[original] = tag
    return {
        "gmsh_node_tags": wall_tags,
        "coordinates": wall_coordinates,
        "gmsh_to_original": gmsh_to_original,
        "original_to_gmsh": original_to_gmsh,
        "distances_m": np.asarray(distances, dtype=float),
        "tolerance_m": tolerance,
    }


def source_wall_rows(
    gmsh: Any, *, surface: SurfaceMesh, source_surface_entity: int
) -> dict[str, list[tuple[int, list[int]]]]:
    mapping = source_wall_correspondence(
        gmsh, surface=surface, source_surface_entity=source_surface_entity
    )
    label_by_face = {
        tuple(sorted(map(int, triangle))): label
        for triangle, label in zip(surface.triangles, surface.labels, strict=True)
    }
    rows: dict[str, list[tuple[int, list[int]]]] = {label: [] for label in LABELS}
    types, _element_tags, connectivity = gmsh.model.mesh.getElements(2, int(source_surface_entity))
    for element_type, flat in zip(types, connectivity, strict=True):
        name, dim, order, width, _local, _primary = gmsh.model.mesh.getElementProperties(
            int(element_type)
        )
        if int(element_type) != 2 or dim != 2 or order != 1 or width != 3:
            raise ValueError(
                f"source wall contains non-linear-triangle element {element_type}: {name}"
            )
        for node_row in np.asarray(flat, dtype=np.int64).reshape(-1, 3):
            key = tuple(sorted(mapping["gmsh_to_original"][int(tag)] for tag in node_row))
            if key not in label_by_face:
                raise ValueError(f"Gmsh wall triangle is absent from labeled source: {key}")
            rows[label_by_face[key]].append((5, list(map(int, node_row))))
    if sum(map(len, rows.values())) != len(surface.triangles):
        raise ValueError("Gmsh wall triangle count changed during boundary-layer construction")
    if any(not rows[label] for label in LABELS):
        raise ValueError("one or more required S7 source-wall labels became empty")
    return rows
