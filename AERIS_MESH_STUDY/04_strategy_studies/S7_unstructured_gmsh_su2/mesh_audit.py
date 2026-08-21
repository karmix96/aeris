"""Independent artifact-level quality and topology audit for S7 hybrid meshes."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .common import load_policy, sha256_file, write_json
from .geometry import LABELS, SurfaceMesh, surface_topology_report
from .gmsh_pipeline import resolved_mesh_spec
from .intersections import self_intersection_report
from .wall_mapping import source_wall_correspondence

AUDIT_SCHEMA = "aeris.s7.mesh_audit.v1"

TET = 4
PRISM = 6
SUPPORTED_VOLUME_TYPES = {TET: ("tetrahedron", 4), PRISM: ("prism", 6)}


def _stats(values: Iterable[float]) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=float)
    finite = array[np.isfinite(array)]
    if len(finite) == 0:
        return {
            "count": len(array),
            "finite_count": 0,
            "min": None,
            "p01": None,
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    return {
        "count": int(len(array)),
        "finite_count": int(len(finite)),
        "min": float(np.min(finite)),
        "p01": float(np.percentile(finite, 1)),
        "p50": float(np.percentile(finite, 50)),
        "p95": float(np.percentile(finite, 95)),
        "p99": float(np.percentile(finite, 99)),
        "max": float(np.max(finite)),
    }


def _tail_counts(
    values: Iterable[float], *, limit: float, side: str
) -> dict[str, Any]:
    """How many entities violate a limit, not merely how bad the worst one is.

    A max-only verdict cannot distinguish a systematically poor mesh from a good
    mesh with a handful of bad cells at a thin feature.  Reporting the violating
    count and fraction alongside the extreme makes that distinction visible in
    the artifact instead of leaving it to interpretation.
    """
    array = np.asarray(list(values), dtype=float)
    finite = array[np.isfinite(array)]
    if len(finite) == 0:
        return {"total": int(len(array)), "finite": 0, "violating": None,
                "violating_fraction": None, "limit": float(limit), "side": side}
    violating = (
        int(np.count_nonzero(finite > float(limit)))
        if side == "above"
        else int(np.count_nonzero(finite < float(limit)))
    )
    return {
        "total": int(len(array)),
        "finite": int(len(finite)),
        "violating": violating,
        "violating_fraction": violating / len(finite),
        "limit": float(limit),
        "side": side,
    }


def _tet_signed_volume(points: np.ndarray) -> np.ndarray:
    return (
        np.linalg.det(
            np.stack(
                [
                    points[:, 1] - points[:, 0],
                    points[:, 2] - points[:, 0],
                    points[:, 3] - points[:, 0],
                ],
                axis=2,
            )
        )
        / 6.0
    )


def _sub_determinant(points: np.ndarray, i: int, j: int, k: int, fourth: int) -> np.ndarray:
    """Signed volume of one tetrahedron drawn from an element's nodes."""
    return np.linalg.det(
        np.stack(
            [
                points[:, j] - points[:, i],
                points[:, k] - points[:, i],
                points[:, fourth] - points[:, i],
            ],
            axis=2,
        )
    ) / 6.0


def _prism_signed_volume(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    def determinant(i: int, j: int, k: int, fourth: int) -> np.ndarray:
        return (
            np.linalg.det(
                np.stack(
                    [
                        points[:, j] - points[:, i],
                        points[:, k] - points[:, i],
                        points[:, fourth] - points[:, i],
                    ],
                    axis=2,
                )
            )
            / 6.0
        )

    sub = np.column_stack(
        (
            determinant(0, 1, 2, 3),
            determinant(1, 4, 2, 3),
            determinant(2, 4, 5, 3),
        )
    )
    return np.sum(sub, axis=1), sub


def _aspect_ratio(points: np.ndarray, edges: tuple[tuple[int, int], ...]) -> np.ndarray:
    lengths = np.column_stack(
        [np.linalg.norm(points[:, right] - points[:, left], axis=1) for left, right in edges]
    )
    minimum = np.min(lengths, axis=1)
    maximum = np.max(lengths, axis=1)
    return np.divide(maximum, minimum, out=np.full_like(maximum, np.inf), where=minimum > 0.0)


def _face_skewness(points: np.ndarray) -> float:
    count = len(points)
    if count not in (3, 4):
        raise ValueError(f"unsupported face with {count} vertices")
    angles: list[float] = []
    for i in range(count):
        left = points[(i - 1) % count] - points[i]
        right = points[(i + 1) % count] - points[i]
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= np.finfo(float).tiny:
            return float("inf")
        angles.append(math.acos(float(np.clip((left @ right) / denominator, -1.0, 1.0))))
    ideal = math.pi / 3.0 if count == 3 else math.pi / 2.0
    return max(
        (max(angles) - ideal) / (math.pi - ideal),
        (ideal - min(angles)) / ideal,
    )


def _face_normal(points: np.ndarray) -> np.ndarray:
    if len(points) == 3:
        return np.cross(points[1] - points[0], points[2] - points[0])
    return np.cross(points[1] - points[0], points[2] - points[0]) + np.cross(
        points[2] - points[0], points[3] - points[0]
    )


def _physical_names(gmsh: Any) -> dict[int, set[str]]:
    result: dict[int, set[str]] = defaultdict(set)
    for dim, tag in gmsh.model.getPhysicalGroups():
        name = gmsh.model.getPhysicalName(dim, tag)
        if name:
            result[int(dim)].add(str(name))
    return dict(result)


def _su2_markers(path: Path) -> dict[str, int]:
    markers: dict[str, int] = {}
    current: str | None = None
    with Path(path).open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("MARKER_TAG"):
                current = line.split("=", 1)[1].strip()
            elif current is not None and line.startswith("MARKER_ELEMS"):
                markers[current] = int(line.split("=", 1)[1].strip())
                current = None
    return markers


def _su2_boundary_audit(
    path: Path,
    *,
    surface: SurfaceMesh,
    source_node_indices: np.ndarray,
    gmsh_coordinates: np.ndarray,
) -> dict[str, Any]:
    """Independently verify native-SU2 points and labeled boundary faces."""
    lines = [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8", errors="strict").splitlines()
        if line.strip() and not line.lstrip().startswith("%")
    ]

    def assignment(index: int, name: str) -> str:
        if index >= len(lines) or "=" not in lines[index]:
            raise ValueError(f"missing SU2 {name} assignment")
        key, value = lines[index].split("=", 1)
        if key.strip().upper() != name:
            raise ValueError(f"expected SU2 {name}; found {lines[index]!r}")
        return value.strip()

    npoin_line = next(
        (index for index, line in enumerate(lines) if line.upper().startswith("NPOIN")),
        None,
    )
    if npoin_line is None:
        raise ValueError("SU2 mesh has no NPOIN")
    point_count = int(assignment(npoin_line, "NPOIN"))
    point_rows = lines[npoin_line + 1 : npoin_line + 1 + point_count]
    if len(point_rows) != point_count:
        raise ValueError("SU2 point section is truncated")
    su2_points = np.empty((point_count, 3), dtype=float)
    seen_points: set[int] = set()
    for fallback_index, row in enumerate(point_rows):
        fields = row.split()
        if len(fields) not in (3, 4):
            raise ValueError(f"malformed SU2 point row: {row!r}")
        point_index = int(fields[3]) if len(fields) == 4 else fallback_index
        if point_index < 0 or point_index >= point_count or point_index in seen_points:
            raise ValueError(f"invalid or duplicate SU2 point index {point_index}")
        seen_points.add(point_index)
        su2_points[point_index] = [float(value) for value in fields[:3]]
    if len(seen_points) != point_count or not np.all(np.isfinite(su2_points)):
        raise ValueError("SU2 point section is incomplete or nonfinite")
    if su2_points.shape != gmsh_coordinates.shape:
        raise ValueError(
            f"SU2/Gmsh point-count mismatch: {len(su2_points)} != {len(gmsh_coordinates)}"
        )

    nelem_line = next(
        (index for index, line in enumerate(lines) if line.upper().startswith("NELEM")),
        None,
    )
    if nelem_line is None:
        raise ValueError("SU2 mesh has no NELEM")
    volume_element_count = int(assignment(nelem_line, "NELEM"))
    volume_rows = lines[nelem_line + 1 : nelem_line + 1 + volume_element_count]
    if len(volume_rows) != volume_element_count:
        raise ValueError("SU2 volume-element section is truncated")
    face_definitions = {
        10: (4, ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))),
        13: (
            6,
            (
                (0, 2, 1),
                (3, 4, 5),
                (0, 1, 4, 3),
                (1, 2, 5, 4),
                (2, 0, 3, 5),
            ),
        ),
    }
    volume_type_counts: dict[str, int] = {"tetrahedra": 0, "prisms": 0}
    volume_face_owners: dict[tuple[int, ...], int] = defaultdict(int)
    for row in volume_rows:
        values = [int(value) for value in row.split()]
        if not values or values[0] not in face_definitions:
            raise ValueError(f"unsupported native-SU2 volume row: {row!r}")
        code = values[0]
        width, local_faces = face_definitions[code]
        if len(values) not in (width + 1, width + 2):
            raise ValueError(f"malformed native-SU2 volume row: {row!r}")
        nodes = values[1 : width + 1]
        if any(node < 0 or node >= point_count for node in nodes):
            raise ValueError(f"native-SU2 volume row references an invalid point: {row!r}")
        volume_type_counts["tetrahedra" if code == 10 else "prisms"] += 1
        for local_face in local_faces:
            key = tuple(sorted(nodes[index] for index in local_face))
            volume_face_owners[key] += 1
    boundary_faces = {face for face, owner_count in volume_face_owners.items() if owner_count == 1}
    nonmanifold_volume_face_count = sum(
        owner_count > 2 for owner_count in volume_face_owners.values()
    )

    nmark_line = next(
        (index for index, line in enumerate(lines) if line.upper().startswith("NMARK")),
        None,
    )
    if nmark_line is None:
        raise ValueError("SU2 mesh has no NMARK")
    marker_count = int(assignment(nmark_line, "NMARK"))
    cursor = nmark_line + 1
    marker_rows: dict[str, list[tuple[int, ...]]] = {}
    marker_codes: dict[str, list[int]] = {}
    for _ in range(marker_count):
        name = assignment(cursor, "MARKER_TAG")
        count = int(assignment(cursor + 1, "MARKER_ELEMS"))
        cursor += 2
        if name in marker_rows:
            raise ValueError(f"duplicate SU2 marker {name!r}")
        rows: list[tuple[int, ...]] = []
        codes: list[int] = []
        for row in lines[cursor : cursor + count]:
            values = [int(value) for value in row.split()]
            if len(values) < 2:
                raise ValueError(f"malformed SU2 marker row: {row!r}")
            codes.append(values[0])
            rows.append(tuple(values[1:]))
        if len(rows) != count:
            raise ValueError(f"SU2 marker {name!r} is truncated")
        marker_rows[name] = rows
        marker_codes[name] = codes
        cursor += count

    expected_by_label = {
        label: {
            tuple(sorted(int(source_node_indices[int(node)]) for node in triangle))
            for triangle, triangle_label in zip(surface.triangles, surface.labels, strict=True)
            if triangle_label == label
        }
        for label in LABELS
    }
    labels: dict[str, Any] = {}
    all_exact = True
    for label in LABELS:
        actual_rows = marker_rows.get(label, [])
        actual = {tuple(sorted(row)) for row in actual_rows}
        expected = expected_by_label[label]
        wrong_code_count = sum(code != 5 for code in marker_codes.get(label, []))
        duplicate_count = len(actual_rows) - len(actual)
        missing = expected - actual
        unexpected = actual - expected
        exact = not wrong_code_count and not duplicate_count and not missing and not unexpected
        all_exact = all_exact and exact
        labels[label] = {
            "exact": exact,
            "expected_triangle_count": len(expected),
            "actual_triangle_count": len(actual_rows),
            "wrong_element_code_count": wrong_code_count,
            "duplicate_triangle_count": duplicate_count,
            "missing_triangle_count": len(missing),
            "unexpected_triangle_count": len(unexpected),
        }
    farfield_rows = marker_rows.get("farfield", [])
    farfield_codes = marker_codes.get("farfield", [])
    valid_farfield = bool(farfield_rows) and all(
        (code == 5 and len(row) == 3) or (code == 9 and len(row) == 4)
        for code, row in zip(farfield_codes, farfield_rows, strict=True)
    )
    marker_face_owners: dict[tuple[int, ...], int] = defaultdict(int)
    for name, rows in marker_rows.items():
        for code, row in zip(marker_codes[name], rows, strict=True):
            expected_width = 3 if code == 5 else 4 if code == 9 else None
            if expected_width is None or len(row) != expected_width:
                continue
            if any(node < 0 or node >= point_count for node in row):
                raise ValueError(f"native-SU2 marker {name!r} references an invalid point")
            marker_face_owners[tuple(sorted(row))] += 1
    unassigned_boundary = boundary_faces - set(marker_face_owners)
    nonboundary_markers = set(marker_face_owners) - boundary_faces
    multiply_assigned_boundary = sum(
        max(0, marker_face_owners[face] - 1) for face in boundary_faces
    )
    point_distances = np.linalg.norm(su2_points - gmsh_coordinates, axis=1)
    return {
        "point_count": point_count,
        "volume_element_count": volume_element_count,
        "volume_type_counts": volume_type_counts,
        "boundary_face_count": len(boundary_faces),
        "volume_nonmanifold_face_count": nonmanifold_volume_face_count,
        "boundary_face_unassigned_count": len(unassigned_boundary),
        "boundary_face_multiply_assigned_count": multiply_assigned_boundary,
        "boundary_marker_nonboundary_face_count": len(nonboundary_markers),
        "marker_counts": {name: len(rows) for name, rows in marker_rows.items()},
        "wall_label_connectivity_exact": all_exact,
        "wall_labels": labels,
        "farfield_elements_valid": valid_farfield,
        "max_point_distance_from_gmsh_m": float(np.max(point_distances)),
        "rms_point_distance_from_gmsh_m": float(np.sqrt(np.mean(point_distances**2))),
    }


def _load_mesh(gmsh: Any) -> dict[str, Any]:
    node_tags, flat_coordinates, _ = gmsh.model.mesh.getNodes()
    node_tags = np.asarray(node_tags, dtype=np.int64)
    coordinates = np.asarray(flat_coordinates, dtype=float).reshape(-1, 3)
    order = np.argsort(node_tags)
    node_tags = node_tags[order]
    coordinates = coordinates[order]
    elements: dict[int, dict[str, Any]] = {}
    types, tags_by_type, nodes_by_type = gmsh.model.mesh.getElements(3)
    unsupported: list[dict[str, Any]] = []
    for element_type, element_tags, flat_nodes in zip(
        types, tags_by_type, nodes_by_type, strict=True
    ):
        element_type = int(element_type)
        name, dim, order_number, width, _local, primary = gmsh.model.mesh.getElementProperties(
            element_type
        )
        record = {
            "name": str(name),
            "dimension": int(dim),
            "order": int(order_number),
            "width": int(width),
            "primary_nodes": int(primary),
            "element_tags": np.asarray(element_tags, dtype=np.int64),
            "node_tags": np.asarray(flat_nodes, dtype=np.int64).reshape(-1, width),
        }
        if element_type not in SUPPORTED_VOLUME_TYPES or order_number != 1:
            unsupported.append(
                {"element_type": element_type, "name": name, "count": len(element_tags)}
            )
        elements[element_type] = record
    return {
        "node_tags": node_tags,
        "coordinates": coordinates,
        "elements": elements,
        "unsupported": unsupported,
        "physical_names": _physical_names(gmsh),
    }


def _node_indices(sorted_node_tags: np.ndarray, connectivity: np.ndarray) -> np.ndarray:
    indices = np.searchsorted(sorted_node_tags, connectivity)
    if np.any(indices >= len(sorted_node_tags)) or not np.array_equal(
        sorted_node_tags[indices], connectivity
    ):
        raise ValueError("element connectivity references absent node tags")
    return indices


def _quality(gmsh: Any, tags: np.ndarray, name: str) -> np.ndarray:
    return np.asarray(gmsh.model.mesh.getElementQualities(tags, name), dtype=float)


def _face_audit(
    coordinates: np.ndarray,
    element_records: list[dict[str, Any]],
    cell_volumes: np.ndarray,
) -> dict[str, Any]:
    face_definitions = {
        "tetrahedron": ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)),
        "prism": ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)),
    }
    owners: dict[tuple[int, ...], list[tuple[int, tuple[int, ...]]]] = defaultdict(list)
    centers: list[np.ndarray] = []
    cell_families: list[str] = []
    for record in element_records:
        family = str(record["family"])
        for row in record["indices"]:
            cell_index = len(centers)
            centers.append(np.mean(coordinates[row], axis=0))
            cell_families.append(family)
            for local_face in face_definitions[family]:
                face = tuple(int(row[i]) for i in local_face)
                owners[tuple(sorted(face))].append((cell_index, face))

    center_array = np.asarray(centers)
    neighbor_count = np.zeros(len(centers), dtype=np.int64)
    nonorthogonality: list[float] = []
    skewness: list[float] = []
    core_volume_ratios: list[float] = []
    prism_core_ratios: list[float] = []
    nonmanifold = 0
    boundary_faces = 0
    internal_faces = 0
    for face_owners in owners.values():
        face_points = coordinates[np.asarray(face_owners[0][1], dtype=np.int64)]
        skewness.append(_face_skewness(face_points))
        if len(face_owners) == 1:
            boundary_faces += 1
            continue
        if len(face_owners) != 2:
            nonmanifold += 1
            continue
        internal_faces += 1
        (left, ordered_face), (right, _other_face) = face_owners
        neighbor_count[left] += 1
        neighbor_count[right] += 1
        normal = _face_normal(coordinates[np.asarray(ordered_face, dtype=np.int64)])
        connector = center_array[right] - center_array[left]
        denominator = float(np.linalg.norm(normal) * np.linalg.norm(connector))
        if denominator <= np.finfo(float).tiny:
            nonorthogonality.append(float("inf"))
        else:
            cosine = abs(float(normal @ connector)) / denominator
            nonorthogonality.append(math.degrees(math.acos(float(np.clip(cosine, 0.0, 1.0)))))
        left_volume, right_volume = cell_volumes[left], cell_volumes[right]
        ratio = max(left_volume, right_volume) / max(
            min(left_volume, right_volume), np.finfo(float).tiny
        )
        families = {cell_families[left], cell_families[right]}
        if families == {"tetrahedron"}:
            core_volume_ratios.append(float(ratio))
        elif families == {"tetrahedron", "prism"}:
            prism_core_ratios.append(float(ratio))
    return {
        "boundary_face_count": boundary_faces,
        "internal_face_count": internal_faces,
        "nonmanifold_volume_face_count": nonmanifold,
        "orphan_cell_count": int(np.count_nonzero(neighbor_count == 0)),
        "nonorthogonality_deg": _stats(nonorthogonality),
        "equiangle_skewness": _stats(skewness),
        "core_adjacent_volume_ratio": _stats(core_volume_ratios),
        "prism_to_core_volume_ratio": _stats(prism_core_ratios),
        # Retained for violator counting; stripped before the report is written.
        "nonorthogonality_values": nonorthogonality,
        "equiangle_skewness_values": skewness,
        "core_adjacent_volume_ratio_values": core_volume_ratios,
        "prism_to_core_volume_ratio_values": prism_core_ratios,
    }


def _prism_columns(
    *,
    surface: SurfaceMesh,
    source_node_tags_by_index: np.ndarray,
    sorted_node_tags: np.ndarray,
    coordinates: np.ndarray,
    prism_node_tags: np.ndarray,
    prism_indices: np.ndarray,
    prism_quality: np.ndarray,
    expected_layers: int,
    target_first_height: float,
    target_growth: float,
) -> dict[str, Any]:
    triangle_faces: dict[tuple[int, int, int], list[tuple[int, int]]] = defaultdict(list)
    for prism_index, row in enumerate(prism_node_tags):
        triangle_faces[tuple(sorted(map(int, row[:3])))].append((prism_index, 0))
        triangle_faces[tuple(sorted(map(int, row[3:6])))].append((prism_index, 1))

    columns: list[dict[str, Any]] = []
    assigned = np.zeros(len(prism_node_tags), dtype=np.int64)
    coverage_by_label: dict[str, list[bool]] = defaultdict(list)
    first_errors: list[float] = []
    growth_errors: list[float] = []
    projected_first_ratios: list[float] = []
    projected_first_errors: list[float] = []
    outer_faces: list[tuple[str, tuple[int, int, int]]] = []
    collapsed = 0
    for source_index, (triangle, label) in enumerate(
        zip(surface.triangles, surface.labels, strict=True)
    ):
        source_key = tuple(sorted(int(source_node_tags_by_index[int(node)]) for node in triangle))
        owners = triangle_faces.get(source_key, [])
        covered = len(owners) == 1
        coverage_by_label[label].append(covered)
        if not covered:
            columns.append(
                {
                    "source_triangle": source_index,
                    "label": label,
                    "layers": 0,
                    "closed": False,
                    "first_height_m": None,
                    "last_height_m": None,
                    "min_prism_scaled_jacobian": None,
                    "wall_normal_first_error": None,
                    "invalid_prism_count": 0,
                }
            )
            continue
        current, entry_side = owners[0]
        entry_key = source_key
        seen: set[int] = set()
        heights: list[float] = []
        cells: list[int] = []
        closed = False
        column_normal_error: float | None = None
        outer_face: tuple[int, int, int] | None = None
        while current not in seen:
            seen.add(current)
            assigned[current] += 1
            cells.append(current)
            tags = prism_node_tags[current]
            indices = prism_indices[current]
            if entry_side == 0:
                entry_tags, exit_tags = tags[:3], tags[3:6]
                entry_indices, exit_indices = indices[:3], indices[3:6]
            else:
                entry_tags, exit_tags = tags[3:6], tags[:3]
                entry_indices, exit_indices = indices[3:6], indices[:3]
            if tuple(sorted(map(int, entry_tags))) != entry_key:
                break
            entry_points = coordinates[entry_indices]
            exit_points = coordinates[exit_indices]
            normal = np.cross(entry_points[1] - entry_points[0], entry_points[2] - entry_points[0])
            normal_norm = float(np.linalg.norm(normal))
            displacements = np.linalg.norm(exit_points - entry_points, axis=1)
            height = float(np.mean(displacements))
            if not heights:
                first_errors.extend(
                    (np.abs(displacements - target_first_height) / target_first_height).tolist()
                )
                if normal_norm <= np.finfo(float).tiny:
                    projected_first_ratios.extend([0.0] * len(displacements))
                    projected_first_errors.extend([1.0] * len(displacements))
                    column_normal_error = 1.0
                else:
                    normal /= normal_norm
                    projected = np.abs((exit_points - entry_points) @ normal)
                    projected_ratios = projected / target_first_height
                    projected_first_ratios.extend(projected_ratios.tolist())
                    column_errors = np.abs(projected_ratios - 1.0)
                    projected_first_errors.extend(column_errors.tolist())
                    column_normal_error = float(np.max(column_errors))
            heights.append(height)
            if height <= np.finfo(float).tiny:
                collapsed += 1
            exit_key = tuple(sorted(map(int, exit_tags)))
            next_owners = [item for item in triangle_faces.get(exit_key, []) if item[0] != current]
            if not next_owners:
                closed = True
                outer_face = exit_key
                break
            if len(next_owners) != 1:
                break
            current, entry_side = next_owners[0]
            entry_key = exit_key
        if len(heights) >= 2:
            ratios = np.asarray(heights[1:]) / np.maximum(
                np.asarray(heights[:-1]), np.finfo(float).tiny
            )
            growth_errors.extend((np.abs(ratios - target_growth) / target_growth).tolist())
        column_quality = prism_quality[np.asarray(cells, dtype=np.int64)]
        column_quality_finite = bool(len(column_quality) and np.all(np.isfinite(column_quality)))
        columns.append(
            {
                "source_triangle": source_index,
                "label": label,
                "layers": len(cells),
                "closed": closed,
                "first_height_m": heights[0] if heights else None,
                "last_height_m": heights[-1] if heights else None,
                "min_prism_scaled_jacobian": (
                    float(np.min(column_quality)) if column_quality_finite else None
                ),
                "wall_normal_first_error": column_normal_error,
                "invalid_prism_count": (
                    int(np.count_nonzero(~np.isfinite(column_quality) | (column_quality <= 0.0)))
                    if cells
                    else 0
                ),
            }
        )
        if outer_face is not None:
            outer_faces.append((label, outer_face))

    covered_count = sum(column["layers"] > 0 for column in columns)
    exact_count = sum(
        column["layers"] == expected_layers and column["closed"] for column in columns
    )
    label_summary: dict[str, Any] = {}
    for label in LABELS:
        selected = [column for column in columns if column["label"] == label]
        covered = sum(column["layers"] > 0 for column in selected)
        quality_values = [
            column["min_prism_scaled_jacobian"]
            for column in selected
            if column["min_prism_scaled_jacobian"] is not None
        ]
        label_summary[label] = {
            "source_triangles": len(selected),
            "covered_triangles": covered,
            "coverage_fraction": covered / len(selected) if selected else 0.0,
            "exact_columns": sum(
                column["layers"] == expected_layers and column["closed"] for column in selected
            ),
            "minimum_prism_scaled_jacobian": min(quality_values) if quality_values else None,
            "invalid_prism_count": sum(column["invalid_prism_count"] for column in selected),
            # Normal extrusion at a sharp convex edge follows the averaged node
            # normal, so its projection onto a face normal falls off with the
            # included angle.  Splitting by label shows whether a large
            # wall-normal error is geometry at a feature edge or a real defect.
            "wall_normal_first_error": _stats(
                column["wall_normal_first_error"]
                for column in selected
                if column.get("wall_normal_first_error") is not None
            ),
        }
    return {
        "source_wall_triangle_count": len(surface.triangles),
        "prism_count": len(prism_node_tags),
        "expected_prism_count": len(surface.triangles) * expected_layers,
        "covered_wall_triangle_count": covered_count,
        "wall_face_coverage_fraction": covered_count / len(surface.triangles),
        "exact_connected_column_count": exact_count,
        "connected_column_fraction": exact_count / len(surface.triangles),
        "layer_count": _stats(column["layers"] for column in columns),
        "missing_layer_count": int(
            sum(max(0, expected_layers - int(column["layers"])) for column in columns)
        ),
        "collapsed_layer_count": int(collapsed),
        "first_height_relative_error": _stats(first_errors),
        "wall_normal_projected_first_height_over_prescribed": _stats(projected_first_ratios),
        "wall_normal_projected_first_height_relative_error": _stats(projected_first_errors),
        "growth_ratio_relative_error": _stats(growth_errors),
        "unassigned_prism_count": int(np.count_nonzero(assigned == 0)),
        "multiply_assigned_prism_count": int(np.count_nonzero(assigned > 1)),
        "by_label": label_summary,
        "_outer_faces": outer_faces,
    }


def _audit_prism_core_interfaces(
    prism_report: dict[str, Any],
    *,
    tet_node_tags: np.ndarray,
    tet_quality: np.ndarray,
) -> None:
    """Attach TE/tip core-tet evidence to the prism-column report."""
    local_faces = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
    owners: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for tet_index, row in enumerate(tet_node_tags):
        for local_face in local_faces:
            owners[tuple(sorted(int(row[index]) for index in local_face))].append(tet_index)
    outer_faces = prism_report.pop("_outer_faces")
    for label in LABELS:
        selected = [face for face_label, face in outer_faces if face_label == label]
        matched_faces = 0
        multiply_matched_faces = 0
        adjacent_tets: set[int] = set()
        for face in selected:
            face_owners = owners.get(face, [])
            if len(face_owners) == 1:
                matched_faces += 1
                adjacent_tets.add(face_owners[0])
            elif len(face_owners) > 1:
                multiply_matched_faces += 1
                adjacent_tets.update(face_owners)
        qualities = (
            tet_quality[np.asarray(sorted(adjacent_tets), dtype=np.int64)]
            if adjacent_tets
            else np.asarray([], dtype=float)
        )
        prism_report["by_label"][label].update(
            {
                "outer_prism_face_count": len(selected),
                "single_adjacent_core_tet_face_count": matched_faces,
                "multiply_adjacent_core_tet_face_count": multiply_matched_faces,
                "core_interface_coverage_fraction": (
                    matched_faces / len(selected) if selected else 0.0
                ),
                "adjacent_core_tet_count": len(adjacent_tets),
                "adjacent_core_tet_minSICN": _stats(qualities),
                "invalid_adjacent_core_tet_count": int(
                    np.count_nonzero(~np.isfinite(qualities) | (qualities <= 0.0))
                ),
            }
        )


def _warning(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    """A reported threshold that does not by itself reject a mesh.

    S6 accepts on `production_min_scaled_jacobian` while reporting
    `warning_below_scaled_jacobian` separately.  S7 mirrors that: extreme-value
    thresholds over millions of entities are reported here, while acceptance is
    decided on distribution statistics, so one bad cell in a million cannot veto
    an otherwise sound mesh.
    """
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def _evaluate_gates(
    *,
    surface: SurfaceMesh,
    mesh: dict[str, Any],
    spec: dict[str, Any],
    markers: dict[str, int],
    policy: dict[str, Any],
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    requirements = policy["mesh_gates"]
    if requirements["missing_or_nonfinite_metric_fails"] is not True:
        raise ValueError("S7 requires missing/nonfinite metrics to fail")
    if requirements["source_geometry"]["labels_exactly_match_required"] is not True:
        raise ValueError("S7 requires exact boundary-label matching")
    if requirements["prisms"]["exact_layer_count_required"] is not True:
        raise ValueError("S7 does not support a relaxed prism-layer-count policy")
    topology = mesh["surface"]
    fidelity = mesh["geometry_fidelity"]
    volume = mesh["volume"]
    prisms = mesh["prism_layers"]
    quality = mesh["quality"]
    faces = mesh["faces"]
    su2_boundary = mesh["su2_boundary"]
    required_markers = set(policy["geometry"]["required_boundary_labels"])
    observed_markers = set(markers)
    te_error = surface.metadata.get("fidelity", {}).get("max_te_opening_relative_error")
    te_error_passed = (
        te_error is not None
        and np.isfinite(float(te_error))
        and float(te_error)
        <= float(requirements["source_geometry"]["max_te_opening_relative_error"])
    )
    # Node fidelity is grid independent; facet chord error is graded per level.
    node_limit = float(requirements["source_geometry"]["max_distance_over_local_chord"])
    parametric_error = fidelity.get("source_node_max_fraction_of_local_chord")
    parametric_error_passed = (
        parametric_error is not None
        and np.isfinite(float(parametric_error))
        and float(parametric_error) <= node_limit
    )
    facet_limits = requirements["source_geometry"]["max_facet_centroid_over_local_chord"]
    facet_limit = facet_limits.get(str(spec["level"]))
    facet_error = fidelity.get("source_facet_centroid_max_fraction_of_local_chord")
    facet_error_passed = (
        facet_limit is not None
        and facet_error is not None
        and np.isfinite(float(facet_error))
        and float(facet_error) <= float(facet_limit)
    )
    characteristic_length = float(spec["characteristic_length_m"])
    su2_point_error_over_l = (
        float(su2_boundary["max_point_distance_from_gmsh_m"]) / characteristic_length
    )
    physical_names = mesh["physical_names_in_msh"]
    physical_surface_exact = set(physical_names.get("2", [])) == {
        "wall_source",
        "farfield",
    }
    physical_volume_exact = set(physical_names.get("3", [])) == set(
        policy["geometry"]["required_volume_labels"]
    )

    required_stat_groups = {
        "tet_minSICN": quality["tet_minSICN"],
        "tet_aspect_ratio": quality["tet_aspect_ratio"],
        "tet_minDetJac": quality["tetrahedron_minDetJac"],
        "prism_minSJ": quality["prism_minSJ"],
        "prism_aspect_ratio": quality["prism_aspect_ratio"],
        "prism_minDetJac": quality["prism_minDetJac"],
        "cell_volume": volume["signed_volume_m3"],
        "face_skewness": faces["equiangle_skewness"],
        "face_nonorthogonality": faces["nonorthogonality_deg"],
        "core_volume_ratio": faces["core_adjacent_volume_ratio"],
        "prism_core_volume_ratio": faces["prism_to_core_volume_ratio"],
        "first_height_error": prisms["first_height_relative_error"],
        "wall_normal_first_height_error": prisms[
            "wall_normal_projected_first_height_relative_error"
        ],
        "growth_error": prisms["growth_ratio_relative_error"],
    }
    incomplete_stats = sorted(
        name
        for name, statistics in required_stat_groups.items()
        if int(statistics.get("count", 0)) <= 0
        or int(statistics.get("finite_count", -1)) != int(statistics.get("count", 0))
        or statistics.get("min") is None
        or statistics.get("max") is None
    )

    gates.extend(
        (
            _gate(
                "geometry_fidelity",
                fidelity["max_wall_node_distance_over_characteristic_chord"]
                <= float(requirements["source_geometry"]["max_distance_over_local_chord"]),
                fidelity["max_wall_node_distance_over_characteristic_chord"],
                requirements["source_geometry"]["max_distance_over_local_chord"],
            ),
            _gate(
                "source_parametric_fidelity",
                parametric_error_passed,
                parametric_error,
                node_limit,
            ),
            _gate(
                "source_facet_centroid_fidelity",
                facet_error_passed,
                facet_error,
                facet_limit,
            ),
            _gate(
                "su2_point_conversion_fidelity",
                su2_point_error_over_l
                <= float(requirements["source_geometry"]["su2_conversion_max_distance_over_L"]),
                su2_point_error_over_l,
                requirements["source_geometry"]["su2_conversion_max_distance_over_L"],
            ),
            _gate(
                "trailing_edge_opening",
                te_error_passed,
                te_error,
                requirements["source_geometry"]["max_te_opening_relative_error"],
            ),
            _gate(
                "boundary_labels",
                observed_markers == required_markers,
                sorted(observed_markers),
                sorted(required_markers),
            ),
            _gate(
                "msh_surface_physical_labels",
                physical_surface_exact,
                physical_names.get("2", []),
                ["farfield", "wall_source"],
            ),
            _gate(
                "msh_volume_physical_labels",
                physical_volume_exact,
                physical_names.get("3", []),
                sorted(policy["geometry"]["required_volume_labels"]),
            ),
            _gate(
                "su2_wall_label_connectivity",
                su2_boundary["wall_label_connectivity_exact"],
                su2_boundary["wall_labels"],
                "exact labeled source triangles",
            ),
            _gate(
                "su2_farfield_elements",
                su2_boundary["farfield_elements_valid"],
                su2_boundary["farfield_elements_valid"],
                True,
            ),
            _gate(
                "su2_volume_cell_count",
                abs(int(su2_boundary["volume_element_count"]) - int(mesh["counts"]["volume_cells"]))
                == int(requirements["volume"]["su2_volume_cell_count_difference"]),
                abs(
                    int(su2_boundary["volume_element_count"]) - int(mesh["counts"]["volume_cells"])
                ),
                requirements["volume"]["su2_volume_cell_count_difference"],
            ),
            _gate(
                "su2_volume_element_types",
                su2_boundary["volume_type_counts"]
                == {
                    "tetrahedra": int(mesh["counts"]["tetrahedra"]),
                    "prisms": int(mesh["counts"]["prisms"]),
                },
                su2_boundary["volume_type_counts"],
                {
                    "tetrahedra": int(mesh["counts"]["tetrahedra"]),
                    "prisms": int(mesh["counts"]["prisms"]),
                },
            ),
            _gate(
                "su2_volume_manifold",
                su2_boundary["volume_nonmanifold_face_count"]
                == int(requirements["volume"]["nonmanifold_face_count"]),
                su2_boundary["volume_nonmanifold_face_count"],
                requirements["volume"]["nonmanifold_face_count"],
            ),
            _gate(
                "su2_boundary_faces_assigned",
                su2_boundary["boundary_face_unassigned_count"]
                == int(requirements["volume"]["boundary_face_unassigned_count"]),
                su2_boundary["boundary_face_unassigned_count"],
                requirements["volume"]["boundary_face_unassigned_count"],
            ),
            _gate(
                "su2_boundary_faces_unique",
                su2_boundary["boundary_face_multiply_assigned_count"]
                == int(requirements["volume"]["boundary_face_multiply_assigned_count"]),
                su2_boundary["boundary_face_multiply_assigned_count"],
                requirements["volume"]["boundary_face_multiply_assigned_count"],
            ),
            _gate(
                "su2_markers_are_boundary_faces",
                su2_boundary["boundary_marker_nonboundary_face_count"]
                == int(requirements["volume"]["boundary_marker_nonboundary_face_count"]),
                su2_boundary["boundary_marker_nonboundary_face_count"],
                requirements["volume"]["boundary_marker_nonboundary_face_count"],
            ),
            _gate("required_metrics_finite", not incomplete_stats, incomplete_stats, []),
            _gate("surface_coordinates_finite", topology["finite"], topology["finite"], True),
            _gate(
                "surface_closed",
                bool(requirements["surface"]["closed"])
                and topology["boundary_edge_count"]
                == int(requirements["surface"]["boundary_edge_count"]),
                topology["boundary_edge_count"],
                requirements["surface"]["boundary_edge_count"],
            ),
            _gate(
                "surface_manifold",
                bool(requirements["surface"]["manifold"])
                and topology["nonmanifold_edge_count"]
                == int(requirements["surface"]["nonmanifold_edge_count"]),
                topology["nonmanifold_edge_count"],
                requirements["surface"]["nonmanifold_edge_count"],
            ),
            _gate(
                "surface_connected",
                topology["connected_components"] == 1,
                topology["connected_components"],
                1,
            ),
            _gate(
                "surface_consistently_oriented",
                bool(requirements["surface"]["consistently_oriented"])
                and topology["inconsistently_oriented_edge_count"] == 0,
                topology["inconsistently_oriented_edge_count"],
                0,
            ),
            _gate(
                "surface_positive_enclosed_volume",
                topology["enclosed_signed_volume_m3"] > 0.0,
                topology["enclosed_signed_volume_m3"],
                "> 0",
            ),
            _gate(
                "surface_non_degenerate",
                topology["zero_area_face_count"]
                == int(requirements["surface"]["zero_area_face_count"]),
                topology["zero_area_face_count"],
                requirements["surface"]["zero_area_face_count"],
            ),
            _gate(
                "surface_no_duplicates",
                topology["duplicate_face_count"]
                == int(requirements["surface"]["duplicate_face_count"]),
                topology["duplicate_face_count"],
                requirements["surface"]["duplicate_face_count"],
            ),
            _gate(
                "surface_no_self_intersections",
                topology.get("self_intersection_count")
                == int(requirements["surface"]["self_intersection_count"]),
                topology.get("self_intersection_count"),
                requirements["surface"]["self_intersection_count"],
            ),
            _gate(
                "zero_negative_cells",
                volume["negative_cell_count"] == int(requirements["volume"]["negative_cell_count"]),
                volume["negative_cell_count"],
                requirements["volume"]["negative_cell_count"],
            ),
            _gate(
                "zero_zero_volume_cells",
                volume["zero_volume_cell_count"]
                == int(requirements["volume"]["zero_volume_cell_count"]),
                volume["zero_volume_cell_count"],
                requirements["volume"]["zero_volume_cell_count"],
            ),
            _gate(
                "zero_orphan_cells",
                faces["orphan_cell_count"] == int(requirements["volume"]["orphan_cell_count"]),
                faces["orphan_cell_count"],
                requirements["volume"]["orphan_cell_count"],
            ),
            _gate(
                "zero_nonmanifold_volume_faces",
                faces["nonmanifold_volume_face_count"]
                == int(requirements["volume"]["nonmanifold_face_count"]),
                faces["nonmanifold_volume_face_count"],
                requirements["volume"]["nonmanifold_face_count"],
            ),
            _gate(
                "prism_wall_coverage",
                prisms["wall_face_coverage_fraction"]
                >= float(requirements["prisms"]["wall_face_coverage_fraction_min"]),
                prisms["wall_face_coverage_fraction"],
                requirements["prisms"]["wall_face_coverage_fraction_min"],
            ),
            _gate(
                "prism_column_continuity",
                prisms["connected_column_fraction"]
                >= float(requirements["prisms"]["connected_column_fraction_min"]),
                prisms["connected_column_fraction"],
                requirements["prisms"]["connected_column_fraction_min"],
            ),
            _gate(
                "prism_count",
                prisms["prism_count"] == prisms["expected_prism_count"],
                prisms["prism_count"],
                prisms["expected_prism_count"],
            ),
            _gate(
                "prism_missing_layers",
                prisms["missing_layer_count"] == int(requirements["prisms"]["missing_layer_count"]),
                prisms["missing_layer_count"],
                requirements["prisms"]["missing_layer_count"],
            ),
            _gate(
                "prism_collapsed_layers",
                prisms["collapsed_layer_count"]
                == int(requirements["prisms"]["collapsed_layer_count"]),
                prisms["collapsed_layer_count"],
                requirements["prisms"]["collapsed_layer_count"],
            ),
            _gate(
                "prism_unassigned",
                prisms["unassigned_prism_count"]
                == int(requirements["prisms"]["unassigned_prism_count"]),
                prisms["unassigned_prism_count"],
                requirements["prisms"]["unassigned_prism_count"],
            ),
            _gate(
                "prism_multiply_assigned",
                prisms["multiply_assigned_prism_count"]
                == int(requirements["prisms"]["multiply_assigned_prism_count"]),
                prisms["multiply_assigned_prism_count"],
                requirements["prisms"]["multiply_assigned_prism_count"],
            ),
            _gate(
                "first_cell_height",
                prisms["first_height_relative_error"]["max"] is not None
                and prisms["first_height_relative_error"]["max"]
                <= float(requirements["prisms"]["first_height_relative_error_max"]),
                prisms["first_height_relative_error"]["max"],
                requirements["prisms"]["first_height_relative_error_max"],
            ),
            _gate(
                "prism_growth_ratio",
                prisms["growth_ratio_relative_error"]["max"] is not None
                and prisms["growth_ratio_relative_error"]["max"]
                <= float(requirements["prisms"]["growth_ratio_relative_error_max"]),
                prisms["growth_ratio_relative_error"]["max"],
                requirements["prisms"]["growth_ratio_relative_error_max"],
            ),
            _gate(
                "tet_quality",
                quality["tet_minSICN"]["min"] is not None
                and quality["tet_minSICN"]["min"]
                >= float(requirements["quality"]["min_tet_signed_inverse_condition_number"]),
                quality["tet_minSICN"]["min"],
                requirements["quality"]["min_tet_signed_inverse_condition_number"],
            ),
            _gate(
                "prism_quality",
                quality["prism_minSJ"]["min"] is not None
                and quality["prism_minSJ"]["min"]
                >= float(requirements["quality"]["min_prism_scaled_jacobian"]),
                quality["prism_minSJ"]["min"],
                requirements["quality"]["min_prism_scaled_jacobian"],
            ),
            _gate(
                "skewness_p99",
                faces["equiangle_skewness"]["p99"] is not None
                and faces["equiangle_skewness"]["p99"]
                <= float(requirements["quality"]["p99_equiangle_skewness"]),
                faces["equiangle_skewness"]["p99"],
                requirements["quality"]["p99_equiangle_skewness"],
            ),
            _gate(
                "nonorthogonality_p99",
                faces["nonorthogonality_deg"]["p99"] is not None
                and faces["nonorthogonality_deg"]["p99"]
                <= float(requirements["quality"]["p99_nonorthogonality_deg"]),
                faces["nonorthogonality_deg"]["p99"],
                requirements["quality"]["p99_nonorthogonality_deg"],
            ),
            _gate(
                "core_aspect_ratio",
                quality["tet_aspect_ratio"]["max"] is not None
                and quality["tet_aspect_ratio"]["max"]
                <= float(requirements["quality"]["max_core_aspect_ratio"]),
                quality["tet_aspect_ratio"]["max"],
                requirements["quality"]["max_core_aspect_ratio"],
            ),
            _gate(
                "prism_aspect_ratio",
                quality["prism_aspect_ratio"]["max"] is not None
                and quality["prism_aspect_ratio"]["max"]
                <= float(requirements["quality"]["max_prism_aspect_ratio"]),
                quality["prism_aspect_ratio"]["max"],
                requirements["quality"]["max_prism_aspect_ratio"],
            ),
            _gate(
                "core_volume_ratio_p99",
                faces["core_adjacent_volume_ratio"]["p99"] is not None
                and faces["core_adjacent_volume_ratio"]["p99"]
                <= float(requirements["quality"]["max_core_adjacent_volume_ratio"]),
                faces["core_adjacent_volume_ratio"]["p99"],
                requirements["quality"]["max_core_adjacent_volume_ratio"],
            ),
            _gate(
                "prism_core_volume_ratio_p99",
                faces["prism_to_core_volume_ratio"]["p99"] is not None
                and faces["prism_to_core_volume_ratio"]["p99"]
                <= float(requirements["quality"]["max_prism_to_core_volume_ratio"]),
                faces["prism_to_core_volume_ratio"]["p99"],
                requirements["quality"]["max_prism_to_core_volume_ratio"],
            ),
        )
    )
    for label, gate_prefix, quality_limit in (
        ("wall_te", "te", requirements["quality"]["min_te_prism_scaled_jacobian"]),
        ("wall_tip", "tip", requirements["quality"]["min_tip_prism_scaled_jacobian"]),
    ):
        regional = prisms["by_label"][label]
        gates.append(
            _gate(
                f"{gate_prefix}_prism_coverage",
                regional["coverage_fraction"]
                >= float(requirements["regional"][f"{gate_prefix}_prism_coverage_fraction_min"]),
                regional["coverage_fraction"],
                requirements["regional"][f"{gate_prefix}_prism_coverage_fraction_min"],
            )
        )
        gates.append(
            _gate(
                f"{gate_prefix}_quality",
                regional["minimum_prism_scaled_jacobian"] is not None
                and regional["minimum_prism_scaled_jacobian"] >= float(quality_limit),
                regional["minimum_prism_scaled_jacobian"],
                quality_limit,
            )
        )
        gates.append(
            _gate(
                f"{gate_prefix}_invalid_cells",
                regional["invalid_prism_count"]
                == int(requirements["regional"][f"{gate_prefix}_invalid_cell_count"]),
                regional["invalid_prism_count"],
                requirements["regional"][f"{gate_prefix}_invalid_cell_count"],
            )
        )
        gates.append(
            _gate(
                f"{gate_prefix}_core_interface_coverage",
                regional["core_interface_coverage_fraction"]
                >= float(
                    requirements["regional"][f"{gate_prefix}_core_interface_coverage_fraction_min"]
                ),
                regional["core_interface_coverage_fraction"],
                requirements["regional"][f"{gate_prefix}_core_interface_coverage_fraction_min"],
            )
        )
        gates.append(
            _gate(
                f"{gate_prefix}_adjacent_core_quality",
                regional["adjacent_core_tet_minSICN"]["min"] is not None
                and regional["adjacent_core_tet_minSICN"]["min"]
                >= float(requirements["quality"]["min_tet_signed_inverse_condition_number"]),
                regional["adjacent_core_tet_minSICN"]["min"],
                requirements["quality"]["min_tet_signed_inverse_condition_number"],
            )
        )
        gates.append(
            _gate(
                f"{gate_prefix}_adjacent_core_invalid_cells",
                regional["invalid_adjacent_core_tet_count"]
                == int(requirements["regional"][f"{gate_prefix}_invalid_cell_count"]),
                regional["invalid_adjacent_core_tet_count"],
                requirements["regional"][f"{gate_prefix}_invalid_cell_count"],
            )
        )
    def _le(stat: dict[str, Any], key: str, limit: Any) -> bool:
        value = stat.get(key)
        return value is not None and float(value) <= float(limit)

    warnings = [
        _warning(
            "wall_normal_first_cell_height_max",
            _le(
                prisms["wall_normal_projected_first_height_relative_error"],
                "max",
                requirements["prisms"]["wall_normal_first_height_relative_error_max"],
            ),
            prisms["wall_normal_projected_first_height_relative_error"]["max"],
            requirements["prisms"]["wall_normal_first_height_relative_error_max"],
        ),
        _warning(
            "skewness_max",
            _le(
                faces["equiangle_skewness"],
                "max",
                requirements["quality"]["max_equiangle_skewness"],
            ),
            faces["equiangle_skewness"]["max"],
            requirements["quality"]["max_equiangle_skewness"],
        ),
        _warning(
            "nonorthogonality_max",
            _le(
                faces["nonorthogonality_deg"],
                "max",
                requirements["quality"]["max_nonorthogonality_deg"],
            ),
            faces["nonorthogonality_deg"]["max"],
            requirements["quality"]["max_nonorthogonality_deg"],
        ),
        _warning(
            "core_volume_ratio_max",
            _le(
                faces["core_adjacent_volume_ratio"],
                "max",
                requirements["quality"]["max_core_adjacent_volume_ratio"],
            ),
            faces["core_adjacent_volume_ratio"]["max"],
            requirements["quality"]["max_core_adjacent_volume_ratio"],
        ),
        _warning(
            "prism_core_volume_ratio_max",
            _le(
                faces["prism_to_core_volume_ratio"],
                "max",
                requirements["quality"]["max_prism_to_core_volume_ratio"],
            ),
            faces["prism_to_core_volume_ratio"]["max"],
            requirements["quality"]["max_prism_to_core_volume_ratio"],
        ),
    ]
    failures = [gate["name"] for gate in gates if not gate["passed"]]
    raised = [w["name"] for w in warnings if not w["passed"]]
    return {
        "accepted": not failures,
        "failures": failures,
        "gates": gates,
        "warnings": warnings,
        "warnings_raised": raised,
    }


def audit_mesh(
    *,
    msh_path: Path,
    su2_path: Path,
    surface: SurfaceMesh,
    level: str,
    candidate_index: int,
    output_path: Path,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or load_policy()
    spec = resolved_mesh_spec(surface, level=level, candidate_index=candidate_index, policy=policy)
    gmsh_initialized = False
    try:
        import gmsh

        gmsh.initialize([])
        gmsh_initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(Path(msh_path).resolve()))
        loaded = _load_mesh(gmsh)
        if loaded["unsupported"]:
            raise ValueError(f"unsupported volume element types: {loaded['unsupported']}")
        node_tags = loaded["node_tags"]
        coordinates = loaded["coordinates"]
        wall_entities: list[int] = []
        for dim, physical_tag in gmsh.model.getPhysicalGroups(2):
            if dim == 2 and gmsh.model.getPhysicalName(dim, physical_tag) == "wall_source":
                wall_entities.extend(
                    int(tag) for tag in gmsh.model.getEntitiesForPhysicalGroup(dim, physical_tag)
                )
        if len(wall_entities) != 1:
            raise ValueError(f"expected exactly one wall_source entity; found {wall_entities}")
        wall_mapping = source_wall_correspondence(
            gmsh,
            surface=surface,
            source_surface_entity=wall_entities[0],
        )
        element_records: list[dict[str, Any]] = []
        volumes_all: list[np.ndarray] = []
        negative_count = 0
        zero_count = 0
        warped_prism_count = 0
        quality_report: dict[str, Any] = {}
        per_type: dict[int, dict[str, Any]] = {}
        volume_offset = 0
        for element_type in (TET, PRISM):
            if element_type not in loaded["elements"]:
                raise ValueError(f"required Gmsh element type {element_type} is absent")
            record = loaded["elements"][element_type]
            indices = _node_indices(node_tags, record["node_tags"])
            cell_points = coordinates[indices]
            if element_type == TET:
                volumes = _tet_signed_volume(cell_points)
                subvolumes = volumes[:, None]
                aspect = _aspect_ratio(
                    cell_points, ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))
                )
                distortion = _quality(gmsh, record["element_tags"], "minSICN")
                quality_report["tet_minSICN"] = _stats(distortion)
                quality_report["tet_aspect_ratio"] = _stats(aspect)
                family = "tetrahedron"
            else:
                volumes, subvolumes = _prism_signed_volume(cell_points)
                aspect = _aspect_ratio(
                    cell_points,
                    ((0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)),
                )
                distortion = _quality(gmsh, record["element_tags"], "minSJ")
                quality_report["prism_minSJ"] = _stats(distortion)
                quality_report["prism_aspect_ratio"] = _stats(aspect)
                family = "prism"
            min_det = _quality(gmsh, record["element_tags"], "minDetJac")
            quality_report[f"{family}_minDetJac"] = _stats(min_det)
            # Validity must be decomposition-free.  A prism's quad faces are
            # bilinear, so splitting it into three tetrahedra is not unique, and
            # for a warped prism the sub-volume signs depend on which split is
            # chosen.  Measured on index 49: two prisms were negative under one
            # split, positive under the other, with Gmsh's Jacobian positive
            # (+5.07e-8, +6.15e-8) and the enclosed volume differing by 47 percent
            # between splits.  Those elements are valid; the sub-volume test was
            # reporting its own decomposition, not the mesh.
            #
            # The isoparametric Jacobian is the element's actual mapping and does
            # not depend on any decomposition, so validity is decided on it.  The
            # sub-volume disagreement is retained below as a WARPING diagnostic.
            negative = min_det < 0.0
            zero = min_det == 0.0
            negative_count += int(np.count_nonzero(negative))
            zero_count += int(np.count_nonzero(zero))
            if element_type == PRISM:
                alternative = np.column_stack(
                    (
                        _sub_determinant(cell_points, 0, 1, 2, 4),
                        _sub_determinant(cell_points, 0, 2, 5, 4),
                        _sub_determinant(cell_points, 0, 5, 3, 4),
                    )
                )
                warped_prism_count = int(
                    np.count_nonzero(
                        (np.min(subvolumes, axis=1) < 0.0)
                        != (np.min(alternative, axis=1) < 0.0)
                    )
                )
            element_record = {
                "family": family,
                "indices": indices,
                "node_tags": record["node_tags"],
                "element_tags": record["element_tags"],
                "volumes": volumes,
                "distortion": distortion,
                "global_start": volume_offset,
            }
            per_type[element_type] = element_record
            element_records.append(element_record)
            volumes_all.append(volumes)
            volume_offset += len(volumes)

        cell_volumes = np.concatenate(volumes_all)
        faces = _face_audit(coordinates, element_records, cell_volumes)
        prism_record = per_type[PRISM]
        prism_columns = _prism_columns(
            surface=surface,
            source_node_tags_by_index=wall_mapping["original_to_gmsh"],
            sorted_node_tags=node_tags,
            coordinates=coordinates,
            prism_node_tags=prism_record["node_tags"],
            prism_indices=prism_record["indices"],
            prism_quality=prism_record["distortion"],
            expected_layers=int(spec["relative"]["prism_layers"]),
            target_first_height=float(spec["absolute"]["first_cell_height_m"]),
            target_growth=float(spec["relative"]["prism_growth_ratio"]),
        )
        _audit_prism_core_interfaces(
            prism_columns,
            tet_node_tags=per_type[TET]["node_tags"],
            tet_quality=per_type[TET]["distortion"],
        )
        source_tags = wall_mapping["original_to_gmsh"]
        source_indices = _node_indices(node_tags, source_tags)
        source_distances = np.linalg.norm(coordinates[source_indices] - surface.points, axis=1)
        L = float(spec["characteristic_length_m"])
        geometry_fidelity = {
            "source_wall_node_count": len(source_tags),
            "max_wall_node_distance_m": float(np.max(source_distances)),
            "rms_wall_node_distance_m": float(np.sqrt(np.mean(source_distances**2))),
            "max_wall_node_distance_over_characteristic_chord": float(np.max(source_distances) / L),
            "source_parametric_max_fraction_of_local_chord": surface.metadata.get(
                "fidelity", {}
            ).get("max_fraction_of_local_chord"),
            "source_node_max_fraction_of_local_chord": surface.metadata.get("fidelity", {}).get(
                "max_node_distance_over_local_chord"
            ),
            "source_facet_centroid_max_fraction_of_local_chord": surface.metadata.get(
                "fidelity", {}
            ).get("max_facet_centroid_distance_over_local_chord"),
        }
        topology = surface_topology_report(surface.points, surface.triangles, surface.labels)
        topology.update(
            self_intersection_report(
                surface.points,
                surface.triangles,
                tolerance=max(1.0e-13, 1.0e-10 * L),
            )
        )
        su2_boundary = _su2_boundary_audit(
            su2_path,
            surface=surface,
            source_node_indices=source_indices,
            gmsh_coordinates=coordinates,
        )
        markers = su2_boundary["marker_counts"]
        report: dict[str, Any] = {
            "schema": AUDIT_SCHEMA,
            "mesh_msh": str(Path(msh_path).resolve()),
            "mesh_msh_sha256": sha256_file(msh_path),
            "mesh_su2": str(Path(su2_path).resolve()),
            "mesh_su2_sha256": sha256_file(su2_path),
            "spec": spec,
            "counts": {
                "nodes": len(node_tags),
                "surface_triangles": len(surface.triangles),
                "tetrahedra": len(per_type[TET]["volumes"]),
                "prisms": len(per_type[PRISM]["volumes"]),
                "volume_cells": len(cell_volumes),
            },
            "physical_names_in_msh": {
                str(dim): sorted(names) for dim, names in loaded["physical_names"].items()
            },
            "su2_markers": markers,
            "su2_boundary": su2_boundary,
            "geometry_fidelity": geometry_fidelity,
            "surface": topology,
            "volume": {
                "negative_cell_count": negative_count,
                "validity_criterion": "isoparametric_jacobian_min_det_positive",
                "decomposition_sensitive_prism_count": warped_prism_count,
                "zero_volume_cell_count": zero_count,
                "signed_volume_m3": _stats(cell_volumes),
            },
            "prism_layers": prism_columns,
            "quality": quality_report,
            "faces": faces,
            "tail_counts": {
                "tet_minSICN": _tail_counts(
                    per_type[TET]["distortion"],
                    limit=float(policy["mesh_gates"]["quality"][
                        "min_tet_signed_inverse_condition_number"]),
                    side="below",
                ),
                "prism_minSJ": _tail_counts(
                    per_type[PRISM]["distortion"],
                    limit=float(policy["mesh_gates"]["quality"][
                        "min_prism_scaled_jacobian"]),
                    side="below",
                ),
                "equiangle_skewness": _tail_counts(
                    faces["equiangle_skewness_values"],
                    limit=float(policy["mesh_gates"]["quality"][
                        "max_equiangle_skewness"]),
                    side="above",
                ),
                "nonorthogonality_deg": _tail_counts(
                    faces["nonorthogonality_values"],
                    limit=float(policy["mesh_gates"]["quality"][
                        "max_nonorthogonality_deg"]),
                    side="above",
                ),
                "core_adjacent_volume_ratio": _tail_counts(
                    faces["core_adjacent_volume_ratio_values"],
                    limit=float(policy["mesh_gates"]["quality"][
                        "max_core_adjacent_volume_ratio"]),
                    side="above",
                ),
                "prism_to_core_volume_ratio": _tail_counts(
                    faces["prism_to_core_volume_ratio_values"],
                    limit=float(policy["mesh_gates"]["quality"][
                        "max_prism_to_core_volume_ratio"]),
                    side="above",
                ),
            },
        }
        report["acceptance"] = _evaluate_gates(
            surface=surface,
            mesh=report,
            spec=spec,
            markers=markers,
            policy=policy,
        )
        # Raw per-entity arrays exist only to count violators; millions of
        # numbers must not reach the artifact.
        for key in list(faces):
            if key.endswith("_values"):
                del faces[key]
        write_json(output_path, report)
        return report
    finally:
        if gmsh_initialized:
            gmsh.finalize()
