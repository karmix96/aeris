"""Triangle self-intersection instrument used by the S7 hard surface gate."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

Array = np.ndarray


def _orient2d(a: Array, b: Array, c: Array) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _point_in_triangle_2d(point: Array, triangle: Array, tolerance: float) -> bool:
    scale = max(float(np.linalg.norm(np.ptp(triangle, axis=0))), tolerance)
    orientation_tolerance = tolerance * scale
    values = np.asarray(
        [
            _orient2d(triangle[0], triangle[1], point),
            _orient2d(triangle[1], triangle[2], point),
            _orient2d(triangle[2], triangle[0], point),
        ]
    )
    return bool(np.all(values >= -orientation_tolerance) or np.all(values <= orientation_tolerance))


def _segments_intersect_2d(a: Array, b: Array, c: Array, d: Array, tolerance: float) -> bool:
    scale = max(
        float(np.linalg.norm(b - a)),
        float(np.linalg.norm(d - c)),
        tolerance,
    )
    orientation_tolerance = tolerance * scale
    o1, o2 = _orient2d(a, b, c), _orient2d(a, b, d)
    o3, o4 = _orient2d(c, d, a), _orient2d(c, d, b)
    if (
        (o1 > orientation_tolerance and o2 < -orientation_tolerance)
        or (o1 < -orientation_tolerance and o2 > orientation_tolerance)
    ) and (
        (o3 > orientation_tolerance and o4 < -orientation_tolerance)
        or (o3 < -orientation_tolerance and o4 > orientation_tolerance)
    ):
        return True

    def on_segment(left: Array, point: Array, right: Array, orientation: float) -> bool:
        return abs(orientation) <= orientation_tolerance and bool(
            np.all(point >= np.minimum(left, right) - tolerance)
            and np.all(point <= np.maximum(left, right) + tolerance)
        )

    return any(
        (
            on_segment(a, c, b, o1),
            on_segment(a, d, b, o2),
            on_segment(c, a, d, o3),
            on_segment(c, b, d, o4),
        )
    )


def _coplanar_triangles_intersect(
    left: Array, right: Array, normal: Array, tolerance: float
) -> bool:
    drop = int(np.argmax(np.abs(normal)))
    a = np.delete(left, drop, axis=1)
    b = np.delete(right, drop, axis=1)
    for i in range(3):
        for j in range(3):
            if _segments_intersect_2d(a[i], a[(i + 1) % 3], b[j], b[(j + 1) % 3], tolerance):
                return True
    return _point_in_triangle_2d(a[0], b, tolerance) or _point_in_triangle_2d(b[0], a, tolerance)


def _segment_triangle_intersection(
    start: Array, end: Array, triangle: Array, tolerance: float
) -> bool:
    direction = end - start
    edge1 = triangle[1] - triangle[0]
    edge2 = triangle[2] - triangle[0]
    cross = np.cross(direction, edge2)
    determinant = float(edge1 @ cross)
    scale = max(
        float(np.linalg.norm(direction)),
        float(np.linalg.norm(edge1)),
        float(np.linalg.norm(edge2)),
        tolerance,
    )
    relative_tolerance = max(np.finfo(float).eps * 32.0, tolerance / scale)
    determinant_tolerance = relative_tolerance * float(
        np.linalg.norm(direction) * np.linalg.norm(edge1) * np.linalg.norm(edge2)
    )
    if abs(determinant) <= determinant_tolerance:
        return False
    inverse = 1.0 / determinant
    relative = start - triangle[0]
    u = float(relative @ cross) * inverse
    if u < -relative_tolerance or u > 1.0 + relative_tolerance:
        return False
    q = np.cross(relative, edge1)
    v = float(direction @ q) * inverse
    if v < -relative_tolerance or u + v > 1.0 + relative_tolerance:
        return False
    distance = float(edge2 @ q) * inverse
    return -relative_tolerance <= distance <= 1.0 + relative_tolerance


def _straddles(distances: Array, tolerance: float) -> bool:
    """True when a triangle carries material strictly on both sides of a plane."""
    return bool(distances.max() > tolerance and distances.min() < -tolerance)


def _triangles_intersect(left: Array, right: Array, tolerance: float) -> bool:
    if np.any(np.max(left, axis=0) < np.min(right, axis=0) - tolerance) or np.any(
        np.max(right, axis=0) < np.min(left, axis=0) - tolerance
    ):
        return False
    normal_left = np.cross(left[1] - left[0], left[2] - left[0])
    normal_right = np.cross(right[1] - right[0], right[2] - right[0])
    norm_left = float(np.linalg.norm(normal_left))
    norm_right = float(np.linalg.norm(normal_right))
    if norm_left <= tolerance or norm_right <= tolerance:
        return False
    distances_right = (right - left[0]) @ normal_left / norm_left
    distances_left = (left - right[0]) @ normal_right / norm_right
    if np.all(distances_right > tolerance) or np.all(distances_right < -tolerance):
        return False
    if np.all(distances_left > tolerance) or np.all(distances_left < -tolerance):
        return False
    unit_left = normal_left / norm_left
    unit_right = normal_right / norm_right
    edge_scale = max(
        float(np.max(np.linalg.norm(np.diff(left[[0, 1, 2, 0]], axis=0), axis=1))),
        float(np.max(np.linalg.norm(np.diff(right[[0, 1, 2, 0]], axis=0), axis=1))),
        tolerance,
    )
    angular_tolerance = max(np.finfo(float).eps * 32.0, tolerance / edge_scale)
    parallel = float(np.linalg.norm(np.cross(unit_left, unit_right))) <= angular_tolerance
    if (
        parallel
        and max(np.max(np.abs(distances_right)), np.max(np.abs(distances_left))) <= tolerance
    ):
        # Coplanar overlap is a genuine defect (two faces sharing area).
        return _coplanar_triangles_intersect(left, right, normal_left, tolerance)
    # Interpenetration requires BOTH triangles to carry material strictly on both
    # sides of the other's plane.  A triangle lying wholly on one side can at most
    # touch, which is normal where a closed surface meets its planar tip cap along
    # the shared tip curve.  Measured on lhs100_seed42 index 0 at `coarse`, four
    # such pairs reported a maximum penetration of 3.8e-17 m -- exact contact in
    # double precision -- and were being rejected as folds.
    if not (
        _straddles(distances_right, tolerance) and _straddles(distances_left, tolerance)
    ):
        return False
    for triangle_a, triangle_b in ((left, right), (right, left)):
        for i in range(3):
            if _segment_triangle_intersection(
                triangle_a[i], triangle_a[(i + 1) % 3], triangle_b, tolerance
            ):
                return True
    return False


def self_intersection_report(
    points: Array,
    triangles: Array,
    *,
    tolerance: float,
    sample_limit: int = 25,
) -> dict[str, Any]:
    """Count contacts between non-adjacent triangles using a spatial hash."""
    points = np.asarray(points, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64)
    tri_points = points[triangles]
    minimum = np.min(tri_points, axis=1) - tolerance
    maximum = np.max(tri_points, axis=1) + tolerance
    edge_lengths = np.concatenate(
        [
            np.linalg.norm(tri_points[:, 1] - tri_points[:, 0], axis=1),
            np.linalg.norm(tri_points[:, 2] - tri_points[:, 1], axis=1),
            np.linalg.norm(tri_points[:, 0] - tri_points[:, 2], axis=1),
        ]
    )
    finite_edges = edge_lengths[np.isfinite(edge_lengths) & (edge_lengths > tolerance)]
    if len(finite_edges) == 0:
        return {"self_intersection_count": 0, "candidate_pair_count": 0, "sample_pairs": []}
    cell_size = max(float(np.percentile(finite_edges, 75)) * 2.0, tolerance * 100.0)
    origin = np.min(minimum, axis=0)
    bins: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    large: list[int] = []
    for index, (lo, hi) in enumerate(zip(minimum, maximum, strict=True)):
        first = np.floor((lo - origin) / cell_size).astype(np.int64)
        last = np.floor((hi - origin) / cell_size).astype(np.int64)
        shape = last - first + 1
        if int(np.prod(shape)) > 4096:
            large.append(index)
            continue
        for i in range(int(first[0]), int(last[0]) + 1):
            for j in range(int(first[1]), int(last[1]) + 1):
                for k in range(int(first[2]), int(last[2]) + 1):
                    bins[(i, j, k)].append(index)
    candidates: set[tuple[int, int]] = set()
    for members in bins.values():
        for offset, left in enumerate(members):
            for right in members[offset + 1 :]:
                if left != right:
                    candidates.add((min(left, right), max(left, right)))
    for left in large:
        overlap = np.flatnonzero(
            np.all(maximum[left] >= minimum, axis=1) & np.all(maximum >= minimum[left], axis=1)
        )
        candidates.update(
            (min(left, int(right)), max(left, int(right))) for right in overlap if right != left
        )

    count = 0
    samples: list[list[int]] = []
    tested = 0
    for left, right in sorted(candidates):
        if set(map(int, triangles[left])) & set(map(int, triangles[right])):
            continue
        if np.any(maximum[left] < minimum[right]) or np.any(maximum[right] < minimum[left]):
            continue
        tested += 1
        if _triangles_intersect(tri_points[left], tri_points[right], tolerance):
            count += 1
            if len(samples) < sample_limit:
                samples.append([left, right])
    return {
        "self_intersection_count": count,
        "candidate_pair_count": len(candidates),
        "tested_pair_count": tested,
        "sample_pairs": samples,
        "tolerance_m": tolerance,
        "spatial_hash_cell_m": cell_size,
    }
