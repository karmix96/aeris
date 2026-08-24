"""Build the prism boundary layer explicitly, instead of asking Gmsh to extrude it.

Gmsh marches each node along an average of its adjacent face normals and offers no
way to constrain that direction.  On a half model the wall does not meet the
symmetry plane perpendicularly - sweep and taper tilt it - so the root columns walk
out of the plane and into a region where there is no domain: measured at 0.705 mm
against a 15.449 mm layer.  See `half_domain_probe.py`.

Marching the layer here fixes that by construction.  A node on the root outline is
given a direction with its symmetry-normal component removed, which is exactly the
direction mirror symmetry would produce, so the root end of the layer lands flat in
the plane rather than being snapped there afterwards.

The layer is emitted as explicit prisms plus the triangulated surface that caps it,
which is what bounds the tetrahedral core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

Array = np.ndarray


@dataclass(frozen=True)
class PrismLayer:
    """One marched boundary layer.

    `points` holds the wall nodes first, in their original order, followed by each
    marched level in turn, so wall node `i` at level `k` is at
    `wall_count * k + i`.  Callers rely on that layout to identify the root band.
    """

    points: Array
    prisms: Array
    top_triangles: Array
    top_node_offset: int
    wall_count: int
    directions: Array
    diagnostics: dict[str, Any]


def _area_weighted_normals(points: Array, triangles: Array) -> Array:
    """Per-node outward normals, weighted by adjacent triangle area.

    Area weighting rather than a plain mean: a wall node at the trailing edge
    touches many slivers and a few large faces, and an unweighted mean lets the
    slivers dominate a direction they contribute almost no surface to.
    """
    normals = np.zeros_like(points)
    a = points[triangles[:, 0]]
    b = points[triangles[:, 1]]
    c = points[triangles[:, 2]]
    # Cross product magnitude is twice the area, so this is area weighting already.
    face = np.cross(b - a, c - a)
    for column in range(3):
        np.add.at(normals, triangles[:, column], face)
    lengths = np.linalg.norm(normals, axis=1)
    degenerate = lengths <= np.finfo(float).tiny
    if degenerate.any():
        raise ValueError(
            f"{int(degenerate.sum())} wall nodes have no usable normal; "
            "the wall triangulation is degenerate there"
        )
    return normals / lengths[:, None]


def march(
    points: Array,
    wall_triangles: Array,
    cumulative_heights: Sequence[float],
    *,
    symmetry_axis: int | None = None,
    symmetry_tolerance: float = 1.0e-9,
    min_direction_quality: float = 0.10,
) -> PrismLayer:
    """March `wall_triangles` outward through `cumulative_heights`.

    `symmetry_axis` names the coordinate held flat (1 for a y=0 plane).  Nodes
    already on that plane are marched with the plane's component removed, so they
    slide along it instead of leaving the domain.
    """
    points = np.asarray(points, dtype=float)
    wall_triangles = np.asarray(wall_triangles, dtype=np.int64)
    heights = [float(h) for h in cumulative_heights]
    if not heights:
        raise ValueError("no boundary-layer heights given")
    if any(second <= first for first, second in zip(heights[:-1], heights[1:], strict=True)):
        raise ValueError(f"cumulative heights must increase strictly: {heights}")

    directions = _area_weighted_normals(points, wall_triangles)

    on_plane = np.zeros(len(points), dtype=bool)
    if symmetry_axis is not None:
        on_plane = np.abs(points[:, symmetry_axis]) <= symmetry_tolerance
        if on_plane.any():
            constrained = directions[on_plane].copy()
            constrained[:, symmetry_axis] = 0.0
            lengths = np.linalg.norm(constrained, axis=1)
            # A direction that was almost purely along the symmetry normal has
            # nothing left once that component is removed; marching it would be
            # arbitrary, so refuse rather than emit a degenerate column.
            weak = lengths < min_direction_quality
            if weak.any():
                raise ValueError(
                    f"{int(weak.sum())} root nodes have no in-plane marching "
                    f"direction (worst residual {float(lengths.min()):.4f}); the "
                    "wall meets the symmetry plane almost tangentially there"
                )
            directions[on_plane] = constrained / lengths[:, None]

    wall_count = len(points)
    levels = [points]
    for height in heights:
        levels.append(points + height * directions)
    marched = np.vstack(levels)

    # Prisms: each wall triangle swept through each level.  Node ordering is the
    # bottom triangle then the top, which is the SU2 and Gmsh prism convention.
    prisms = []
    for level in range(len(heights)):
        low = wall_triangles + wall_count * level
        high = wall_triangles + wall_count * (level + 1)
        prisms.append(np.hstack([low, high]))
    prisms = np.vstack(prisms)

    top_offset = wall_count * len(heights)
    top_triangles = wall_triangles + top_offset

    if symmetry_axis is not None:
        beyond = marched[:, symmetry_axis] < -symmetry_tolerance
        if beyond.any():
            raise ValueError(
                f"{int(beyond.sum())} marched nodes crossed the symmetry plane "
                f"(worst {float(marched[:, symmetry_axis].min()):+.6e} m)"
            )

    diagnostics = {
        "wall_nodes": int(wall_count),
        "layers": len(heights),
        "total_thickness_m": heights[-1],
        "root_nodes_constrained": int(on_plane.sum()),
        "prism_count": int(len(prisms)),
        "marched_node_count": int(len(marched)),
    }
    if symmetry_axis is not None:
        diagnostics["min_symmetry_coordinate_m"] = float(
            marched[:, symmetry_axis].min()
        )
    return PrismLayer(
        points=marched,
        prisms=prisms,
        top_triangles=top_triangles,
        top_node_offset=top_offset,
        wall_count=wall_count,
        directions=directions,
        diagnostics=diagnostics,
    )


def prism_signed_volumes(points: Array, prisms: Array) -> Array:
    """Signed volume of each prism, by the three-tetrahedron decomposition.

    Reported rather than reduced to a boolean because a layer that is merely thin
    and one that is inverted need different responses, and the sign alone cannot
    tell them apart.
    """
    p = np.asarray(points, dtype=float)
    n = np.asarray(prisms, dtype=np.int64)
    total = np.zeros(len(n), dtype=float)
    for a, b, c, d in ((0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5)):
        v0 = p[n[:, b]] - p[n[:, a]]
        v1 = p[n[:, c]] - p[n[:, a]]
        v2 = p[n[:, d]] - p[n[:, a]]
        total += np.einsum("ij,ij->i", np.cross(v0, v1), v2) / 6.0
    return total

# Prism lateral faces, as (bottom_a, bottom_b, top_b, top_a) into the six-node
# ordering emitted by `march`.
_LATERAL = ((0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5))


def symmetry_quads(layer: PrismLayer, *, axis: int, tolerance: float = 1.0e-9) -> Array:
    """The prism faces that lie in the symmetry plane.

    These are the root end of the layer.  They exist only because the marching
    directions were constrained; with a free march the same faces would be tilted
    out of the plane and could not be a boundary at all.
    """
    coordinate = layer.points[:, axis]
    quads = []
    for face in _LATERAL:
        nodes = layer.prisms[:, face]
        on_plane = (np.abs(coordinate[nodes]) <= tolerance).all(axis=1)
        if on_plane.any():
            quads.append(nodes[on_plane])
    if not quads:
        return np.empty((0, 4), dtype=np.int64)
    return np.vstack(quads)


def top_boundary_loops(layer: PrismLayer) -> list[list[int]]:
    """Ordered node loops bounding the open edge of the capping surface.

    The tetrahedral core is bounded partly by the symmetry plane, and the hole in
    that plane is exactly this loop, so it has to come back ordered rather than as
    a set of edges.  More than one loop is possible in principle and is returned
    rather than collapsed, because silently taking the first would be wrong for
    any geometry that produced two.
    """
    counts: dict[tuple[int, int], int] = {}
    for a, b, c in layer.top_triangles:
        for edge in ((a, b), (b, c), (c, a)):
            key = (int(min(edge)), int(max(edge)))
            counts[key] = counts.get(key, 0) + 1
    boundary = [edge for edge, count in counts.items() if count == 1]
    if not boundary:
        return []

    neighbours: dict[int, list[int]] = {}
    for a, b in boundary:
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    if any(len(v) != 2 for v in neighbours.values()):
        raise ValueError(
            "capping-surface boundary is not a set of simple closed loops; "
            "the wall triangulation is non-manifold at its open edge"
        )

    loops: list[list[int]] = []
    unvisited = set(neighbours)
    while unvisited:
        start = min(unvisited)
        loop = [start]
        unvisited.discard(start)
        previous, current = None, start
        while True:
            options = [n for n in neighbours[current] if n != previous]
            nxt = options[0] if options else None
            if nxt is None or nxt == start:
                break
            loop.append(nxt)
            unvisited.discard(nxt)
            previous, current = current, nxt
        loops.append(loop)
    return loops
