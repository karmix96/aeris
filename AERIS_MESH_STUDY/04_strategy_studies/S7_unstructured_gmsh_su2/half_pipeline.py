"""Assemble the half domain: marched prisms plus a Gmsh tetrahedral core.

The mirrored pipeline hands the whole job to Gmsh and reads the result back out of
the model.  The half domain cannot, because its prism layer is marched here in
order to respect the symmetry plane (see `prism_layer`), so the two halves of the
mesh are assembled explicitly and written from arrays rather than from Gmsh.

Element codes are SU2's: 5 triangle, 9 quadrilateral, 10 tetrahedron, 13 prism.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .common import sha256_file
from .geometry import SurfaceMesh
from .prism_layer import PrismLayer, march, prism_signed_volumes, top_boundary_loops

Array = np.ndarray

SU2_TRIANGLE = 5
SU2_QUAD = 9
SU2_TETRAHEDRON = 10
SU2_PRISM = 13

WELD_TOLERANCE_M = 1.0e-9


def weld(points: Array, *blocks: Array) -> tuple[Array, list[Array]]:
    """Merge coincident nodes and renumber every connectivity block onto them.

    Quantising to a fixed tolerance rather than clustering: the wall and the plane
    are built from the *same* coordinates, so their shared nodes are bit-identical
    and need no search, while genuinely distinct nodes are never this close.
    """
    keys = np.round(np.asarray(points, dtype=float) / WELD_TOLERANCE_M).astype(np.int64)
    unique_keys, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    welded = np.zeros((len(unique_keys), 3), dtype=float)
    welded[inverse] = points
    return welded, [inverse[np.asarray(b, dtype=np.int64)] for b in blocks]


def watertight_failures(triangles: Array) -> list[tuple[int, int, int]]:
    """Edges not shared by exactly two triangles, as (node, node, count).

    Checked before Gmsh is asked to fill the shell, because Gmsh reports an
    unclosed boundary as a warning and an empty region rather than an error - a
    volume with no cells at all looks like a successful run otherwise.
    """
    counts: dict[tuple[int, int], int] = {}
    for tri in np.asarray(triangles, dtype=np.int64):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (int(min(a, b)), int(max(a, b)))
            counts[key] = counts.get(key, 0) + 1
    return [(a, b, c) for (a, b), c in counts.items() if c != 2]


def build_layer(
    surface: SurfaceMesh,
    spec: Mapping[str, Any],
    *,
    symmetry_axis: int = 1,
) -> tuple[PrismLayer, Array]:
    """March the boundary layer off the wall labels of a half surface."""
    labels = np.asarray(surface.labels)
    triangles = np.asarray(surface.triangles)
    wall = triangles[labels != "symmetry"]
    if not len(wall):
        raise ValueError("half surface carries no wall triangles")
    layer = march(
        np.asarray(surface.points, dtype=float),
        wall,
        list(spec["boundary_layer_cumulative_heights_m"]),
        symmetry_axis=symmetry_axis,
    )
    volumes = prism_signed_volumes(layer.points, layer.prisms)
    if (volumes <= 0.0).any():
        raise ValueError(
            f"{int((volumes <= 0.0).sum())} prisms are inverted or degenerate; "
            f"worst signed volume {float(volumes.min()):.3e} m3"
        )
    return layer, wall


def boundary_planes(
    gmsh: Any,
    layer: PrismLayer,
    bounds: tuple[float, float, float, float, float],
    *,
    far_lc: float,
    symmetry_axis: int = 1,
) -> tuple[Array, Array, Array]:
    """Mesh the symmetry plane and the five farfield faces.

    Returns points, symmetry triangles and farfield triangles, all indexed into
    the returned points.  The hole in the symmetry plane is built from the layer's
    own capping nodes with one element per segment, so the plane's mesh lands on
    those coordinates exactly instead of interpolating near them.
    """
    xmin, xmax, ymax, zmin, zmax = bounds
    loops = top_boundary_loops(layer)
    if len(loops) != 1:
        raise ValueError(
            f"expected one loop bounding the capping surface, found {len(loops)}"
        )
    loop = loops[0]

    geo = gmsh.model.geo
    corners = [
        geo.addPoint(xmin, 0.0, zmin, far_lc),
        geo.addPoint(xmax, 0.0, zmin, far_lc),
        geo.addPoint(xmax, 0.0, zmax, far_lc),
        geo.addPoint(xmin, 0.0, zmax, far_lc),
    ]
    base_edges = [geo.addLine(corners[i], corners[(i + 1) % 4]) for i in range(4)]

    hole_points = [geo.addPoint(*layer.points[n].tolist(), far_lc) for n in loop]
    hole_edges = [
        geo.addLine(tag, hole_points[(i + 1) % len(hole_points)])
        for i, tag in enumerate(hole_points)
    ]
    for edge in hole_edges:
        geo.mesh.setTransfiniteCurve(edge, 2)

    symmetry_face = geo.addPlaneSurface(
        [geo.addCurveLoop(base_edges), geo.addCurveLoop(hole_edges)]
    )

    upper = [
        geo.addPoint(x, ymax, z, far_lc)
        for x, z in ((xmin, zmin), (xmax, zmin), (xmax, zmax), (xmin, zmax))
    ]
    top_edges = [geo.addLine(upper[i], upper[(i + 1) % 4]) for i in range(4)]
    risers = [geo.addLine(corners[i], upper[i]) for i in range(4)]
    far_faces = [geo.addPlaneSurface([geo.addCurveLoop(top_edges)])]
    for i in range(4):
        j = (i + 1) % 4
        far_faces.append(
            geo.addPlaneSurface(
                [geo.addCurveLoop([base_edges[i], risers[j], -top_edges[i], -risers[i]])]
            )
        )
    geo.synchronize()
    gmsh.model.mesh.generate(2)

    collected: list[Array] = []
    offset = 0
    per_face: dict[int, Array] = {}
    for tag in [symmetry_face, *far_faces]:
        node_tags, coordinates, _ = gmsh.model.mesh.getNodes(2, tag, includeBoundary=True)
        local = {int(n): i for i, n in enumerate(node_tags)}
        types, _, connectivity = gmsh.model.mesh.getElements(2, tag)
        faces = []
        for element_type, flat in zip(types, connectivity, strict=True):
            if element_type != 2:
                continue
            indices = np.array([local[int(n)] for n in flat], dtype=np.int64)
            faces.append(indices.reshape(-1, 3) + offset)
        per_face[tag] = np.vstack(faces) if faces else np.empty((0, 3), dtype=np.int64)
        collected.append(coordinates.reshape(-1, 3))
        offset += len(node_tags)

    points = np.vstack(collected)
    farfield = np.vstack([per_face[t] for t in far_faces])
    return points, per_face[symmetry_face], farfield


def write_su2(
    path: Path,
    points: Array,
    volume_rows: Sequence[tuple[int, Sequence[int]]],
    markers: Mapping[str, Sequence[tuple[int, Sequence[int]]]],
) -> dict[str, Any]:
    """Write an SU2 mesh from arrays, atomically."""
    empty = [name for name, rows in markers.items() if not rows]
    if empty:
        raise ValueError(f"cannot write SU2 mesh; empty required marker(s): {empty}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("NDIME= 3\n")
            stream.write(f"NELEM= {len(volume_rows)}\n")
            for index, (code, nodes) in enumerate(volume_rows):
                stream.write(" ".join(map(str, (code, *nodes, index))) + "\n")
            stream.write(f"NPOIN= {len(points)}\n")
            for index, point in enumerate(points):
                stream.write(
                    f"{point[0]:.17e} {point[1]:.17e} {point[2]:.17e} {index}\n"
                )
            stream.write(f"NMARK= {len(markers)}\n")
            for name, rows in markers.items():
                stream.write(f"MARKER_TAG= {name}\n")
                stream.write(f"MARKER_ELEMS= {len(rows)}\n")
                for code, nodes in rows:
                    stream.write(" ".join(map(str, (code, *nodes))) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "node_count": int(len(points)),
        "volume_element_count": len(volume_rows),
        "marker_counts": {name: len(rows) for name, rows in markers.items()},
    }


def _core_from_shell(gmsh: Any, points: Array, triangles: Array) -> tuple[Array, Array]:
    """Fill a watertight triangulated shell with tetrahedra.

    Built in its own model: the plane phase leaves geo curves behind, and
    createTopology on a discrete surface refuses to run alongside them.
    """
    gmsh.model.add("half_core")
    gmsh.model.setCurrent("half_core")
    entity = gmsh.model.addDiscreteEntity(2)
    gmsh.model.mesh.addNodes(
        2, entity, np.arange(1, len(points) + 1, dtype=np.int64), points.ravel()
    )
    gmsh.model.mesh.addElementsByType(
        entity,
        2,
        np.arange(1, len(triangles) + 1, dtype=np.int64),
        (triangles + 1).astype(np.int64).ravel(),
    )
    gmsh.model.mesh.createTopology()
    gmsh.model.geo.addVolume([gmsh.model.geo.addSurfaceLoop([entity])])
    gmsh.model.geo.synchronize()
    gmsh.model.mesh.generate(3)

    tags, coordinates, _ = gmsh.model.mesh.getNodes()
    index = {int(t): i for i, t in enumerate(tags)}
    types, _, connectivity = gmsh.model.mesh.getElements(3)
    tetrahedra = []
    for element_type, flat in zip(types, connectivity, strict=True):
        if element_type != 4:
            name = gmsh.model.mesh.getElementProperties(element_type)[0]
            raise ValueError(f"core produced a non-tetrahedral element: {name}")
        rows = np.array([index[int(n)] for n in flat], dtype=np.int64).reshape(-1, 4)
        tetrahedra.append(rows)
    if not tetrahedra:
        # Gmsh reports an unfillable region as a warning and an empty volume, so
        # an empty result here is a failure that would otherwise pass silently.
        raise ValueError("core meshing produced no tetrahedra; the shell did not bound a volume")
    return coordinates.reshape(-1, 3), np.vstack(tetrahedra)


def assemble(
    gmsh: Any,
    surface: SurfaceMesh,
    spec: Mapping[str, Any],
    *,
    reference_length_m: float,
    symmetry_axis: int = 1,
) -> dict[str, Any]:
    """Build the whole half-domain mesh and return arrays ready for SU2.

    Node bookkeeping is deliberately blunt: every block keeps its own numbering
    and they are concatenated, then welded once at the end.  Coincident nodes
    between the layer, the shell and the core are bit-identical by construction,
    so one weld resolves all of them and no block has to know about the others.
    """
    from .prism_layer import symmetry_quads

    layer, wall = build_layer(surface, spec, symmetry_axis=symmetry_axis)
    labels = np.asarray(surface.labels)
    wall_labels = labels[labels != "symmetry"]

    far = spec["farfield"]
    body = layer.points
    radial = float(far["radial_over_L"]) * reference_length_m
    bounds = (
        float(body[:, 0].min() - float(far["upstream_over_L"]) * reference_length_m),
        float(body[:, 0].max() + float(far["downstream_over_L"]) * reference_length_m),
        float(body[:, 1].max() + radial),
        float(body[:, 2].min() - radial),
        float(body[:, 2].max() + radial),
    )
    plane_points, symmetry_tris, farfield_tris = boundary_planes(
        gmsh, layer, bounds,
        far_lc=float(spec["absolute"]["far_core_edge_m"]),
        symmetry_axis=symmetry_axis,
    )

    cap_nodes = np.unique(layer.top_triangles)
    cap_map = {int(n): i for i, n in enumerate(cap_nodes)}
    cap_tris = np.vectorize(cap_map.get)(layer.top_triangles) + len(plane_points)
    shell_points = np.vstack([plane_points, layer.points[cap_nodes]])
    shell_tris = np.vstack([symmetry_tris, farfield_tris, cap_tris])

    shell_welded, (shell_conn,) = weld(shell_points, shell_tris)
    bad = watertight_failures(shell_conn)
    if bad:
        raise ValueError(
            f"half-domain shell is not watertight: {len(bad)} edges are not shared "
            f"by exactly two triangles"
        )

    core_points, tetrahedra = _core_from_shell(gmsh, shell_welded, shell_conn)

    quads = symmetry_quads(layer, axis=symmetry_axis)
    n_layer, n_plane = len(layer.points), len(plane_points)
    combined = np.vstack([layer.points, plane_points, core_points])
    points, blocks = weld(
        combined,
        layer.prisms,
        wall,
        quads,
        symmetry_tris + n_layer,
        farfield_tris + n_layer,
        tetrahedra + n_layer + n_plane,
    )
    prisms, wall_faces, quad_faces, sym_faces, far_faces, tets = blocks

    volume_rows: list[tuple[int, Sequence[int]]] = [
        (SU2_TETRAHEDRON, row.tolist()) for row in tets
    ]
    volume_rows += [(SU2_PRISM, row.tolist()) for row in prisms]

    markers: dict[str, list[tuple[int, Sequence[int]]]] = {}
    for name in sorted(set(wall_labels.tolist())):
        selected = wall_faces[wall_labels == name]
        markers[name] = [(SU2_TRIANGLE, row.tolist()) for row in selected]
    markers["symmetry"] = [(SU2_QUAD, row.tolist()) for row in quad_faces] + [
        (SU2_TRIANGLE, row.tolist()) for row in sym_faces
    ]
    markers["farfield"] = [(SU2_TRIANGLE, row.tolist()) for row in far_faces]

    return {
        "points": points,
        "volume_rows": volume_rows,
        "markers": markers,
        "diagnostics": {
            **layer.diagnostics,
            "tetrahedra": int(len(tets)),
            "prisms": int(len(prisms)),
            "symmetry_quads": int(len(quad_faces)),
            "symmetry_triangles": int(len(sym_faces)),
            "farfield_triangles": int(len(far_faces)),
            "node_count": int(len(points)),
            "min_symmetry_coordinate_m": float(points[:, symmetry_axis].min()),
        },
    }


# Gmsh element type codes for the shapes this domain uses.
_GMSH_TRIANGLE = 2
_GMSH_QUAD = 3
_GMSH_TETRAHEDRON = 4
_GMSH_PRISM = 6

_SU2_TO_GMSH = {
    SU2_TRIANGLE: _GMSH_TRIANGLE,
    SU2_QUAD: _GMSH_QUAD,
    SU2_TETRAHEDRON: _GMSH_TETRAHEDRON,
    SU2_PRISM: _GMSH_PRISM,
}


def to_gmsh_model(gmsh: Any, assembled: Mapping[str, Any], *, name: str = "half") -> None:
    """Load an assembled half mesh into a fresh Gmsh model.

    The audit reads a .msh rather than the arrays, so the mesh has to exist as a
    Gmsh model to be written at all.  Building it here means the half domain is
    audited by exactly the same instrument as the mirrored one, instead of
    acquiring a second, less exercised checker of its own.
    """
    points = np.asarray(assembled["points"], dtype=float)
    gmsh.model.add(name)
    gmsh.model.setCurrent(name)

    volume = gmsh.model.addDiscreteEntity(3)
    node_tags = np.arange(1, len(points) + 1, dtype=np.int64)
    gmsh.model.mesh.addNodes(3, volume, node_tags, points.ravel())

    by_type: dict[int, list[Sequence[int]]] = {}
    for code, nodes in assembled["volume_rows"]:
        by_type.setdefault(_SU2_TO_GMSH[code], []).append(nodes)
    tag = 1
    for element_type, rows in sorted(by_type.items()):
        block = np.asarray(rows, dtype=np.int64) + 1
        gmsh.model.mesh.addElementsByType(
            volume,
            element_type,
            np.arange(tag, tag + len(block), dtype=np.int64),
            block.ravel(),
        )
        tag += len(block)
    gmsh.model.addPhysicalGroup(3, [volume], name="fluid")

    for marker, rows in assembled["markers"].items():
        entity = gmsh.model.addDiscreteEntity(2)
        grouped: dict[int, list[Sequence[int]]] = {}
        for code, nodes in rows:
            grouped.setdefault(_SU2_TO_GMSH[code], []).append(nodes)
        for element_type, faces in sorted(grouped.items()):
            block = np.asarray(faces, dtype=np.int64) + 1
            gmsh.model.mesh.addElementsByType(
                entity,
                element_type,
                np.arange(tag, tag + len(block), dtype=np.int64),
                block.ravel(),
            )
            tag += len(block)
        gmsh.model.addPhysicalGroup(2, [entity], name=marker)
