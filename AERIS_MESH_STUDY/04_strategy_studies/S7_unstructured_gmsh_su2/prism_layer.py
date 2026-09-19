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

from dataclasses import dataclass, field
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
    #: Hexahedra swept from quadrilateral wall faces, and the pyramids that cap
    #: them.  A hexahedron keeps its right angles under the stretching a boundary
    #: layer demands, where a prism grown from a split quad cannot.  The pyramid
    #: turns each top quad into four triangles so the tetrahedral core still sees
    #: a triangulated shell.  Both are empty for a triangle-only wall.
    hexes: Array = field(default_factory=lambda: np.zeros((0, 8), dtype=np.int64))
    pyramids: Array = field(default_factory=lambda: np.zeros((0, 5), dtype=np.int64))


def _vertex_normals(points: Array, triangles: Array) -> Array:
    """Per-node outward normals, weighted by the angle each face subtends there.

    Angle weighting rather than area: at the tip the flat cap faces are large
    beside the thin faces of the upper and lower surfaces, and area weighting lets
    them pull the normal round towards the cap, which is what squashes the prisms
    along that edge.  The angle a face subtends at a vertex is a property of the
    corner itself and does not care how big the face is elsewhere.
    """
    normals = np.zeros_like(points)
    corners = points[triangles]
    face = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    face_length = np.linalg.norm(face, axis=1)
    usable = face_length > np.finfo(float).tiny
    unit_face = np.zeros_like(face)
    unit_face[usable] = face[usable] / face_length[usable, None]

    for column in range(3):
        a = corners[:, column]
        b = corners[:, (column + 1) % 3]
        c = corners[:, (column + 2) % 3]
        u, v = b - a, c - a
        nu = np.linalg.norm(u, axis=1)
        nv = np.linalg.norm(v, axis=1)
        good = (nu > np.finfo(float).tiny) & (nv > np.finfo(float).tiny)
        cosine = np.ones(len(u))
        cosine[good] = np.clip(
            np.einsum("ij,ij->i", u[good], v[good]) / (nu[good] * nv[good]), -1.0, 1.0
        )
        angle = np.arccos(cosine)
        np.add.at(normals, triangles[:, column], unit_face * angle[:, None])

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
    wall_quads: Array | None = None,
    normal_faces: Array | None = None,
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

    quad_faces = (
        np.zeros((0, 4), dtype=np.int64)
        if wall_quads is None
        else np.asarray(wall_quads, dtype=np.int64).reshape(-1, 4)
    )
    # Node normals need the whole wall, so a quad wall passes the equivalent
    # triangulation in `normal_faces`; splitting a quad does not move any node.
    directions = _vertex_normals(
        points,
        wall_triangles if normal_faces is None else np.asarray(normal_faces, dtype=np.int64),
    )

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

    # March exactly the declared height along the node direction.  Scaling the
    # step to keep a corner node clear of every adjacent face - the classic mitre -
    # was tried and refused: it lifts the first cell off the wall by up to a factor
    # of two, and the first cell height is what sets y+.
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
    prisms = np.vstack(prisms) if prisms else np.zeros((0, 6), dtype=np.int64)

    # Hexahedra: each quadrilateral wall face swept the same way, bottom quad
    # then top quad, which is the SU2 and Gmsh hexahedron convention.
    hexes = np.zeros((0, 8), dtype=np.int64)
    if len(quad_faces):
        swept = []
        for level in range(len(heights)):
            low = quad_faces + wall_count * level
            high = quad_faces + wall_count * (level + 1)
            swept.append(np.hstack([low, high]))
        hexes = np.vstack(swept)

    top_offset = wall_count * len(heights)
    top_triangles = wall_triangles + top_offset

    # Cap each top quad with a pyramid so the core still meets a triangulated
    # shell.  The apex sits above the face centroid at a fraction of the face
    # size, which keeps the pyramid well shaped without reaching into the core.
    pyramids = np.zeros((0, 5), dtype=np.int64)
    if len(quad_faces):
        top_quads = quad_faces + top_offset
        corners = marched[top_quads]
        centroids = corners.mean(axis=1)
        diag_a = corners[:, 2] - corners[:, 0]
        diag_b = corners[:, 3] - corners[:, 1]
        face_normals = np.cross(diag_a, diag_b)
        norms = np.linalg.norm(face_normals, axis=1)
        if not np.all(norms > 0.0):
            raise ValueError("a top quad is degenerate; cannot place a pyramid apex")
        face_normals /= norms[:, None]
        # Twice the quad area is |diag_a x diag_b|, so this is a length scale.
        apex_height = 0.5 * np.sqrt(0.5 * norms)
        # Point the apex away from the wall, using the marching direction of the
        # face's own nodes rather than assuming a winding.
        outward = directions[quad_faces].mean(axis=1)
        sign = np.sign((face_normals * outward).sum(axis=1))
        sign[sign == 0.0] = 1.0
        apexes = centroids + (sign * apex_height)[:, None] * face_normals
        apex_start = len(marched)
        marched = np.vstack([marched, apexes])
        apex_ids = np.arange(apex_start, apex_start + len(apexes), dtype=np.int64)
        pyramids = np.hstack([top_quads, apex_ids[:, None]])
        # Four side triangles per pyramid replace the quad in the capping shell,
        # wound so the shell keeps facing the core.
        sides = []
        for k in range(4):
            a = top_quads[:, k]
            b = top_quads[:, (k + 1) % 4]
            sides.append(np.stack([a, b, apex_ids], axis=1))
        top_triangles = np.vstack([top_triangles, np.vstack(sides)])

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
        "hex_count": int(len(hexes)),
        "pyramid_count": int(len(pyramids)),
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
        hexes=hexes,
        pyramids=pyramids,
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


def hex_signed_volumes(points: Array, hexes: Array) -> Array:
    """Signed volume of each hexahedron, by decomposition about its centroid.

    A trilinear hexahedron is not generally a polyhedron with planar faces, so
    each face is split about its own centre before the divergence sum; taking
    the face as planar would misreport exactly the warped cells worth catching.
    """
    points = np.asarray(points, dtype=float)
    cells = np.asarray(hexes, dtype=np.int64).reshape(-1, 8)
    if not len(cells):
        return np.zeros(0, dtype=float)
    corners = points[cells]
    centres = corners.mean(axis=1)
    faces = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))
    total = np.zeros(len(cells), dtype=float)
    for face in faces:
        ring = corners[:, face, :]
        face_centre = ring.mean(axis=1)
        for k in range(4):
            a = ring[:, k, :] - centres
            b = ring[:, (k + 1) % 4, :] - centres
            total += (np.cross(a, b) * (face_centre - centres)).sum(axis=1) / 6.0
    return total


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
