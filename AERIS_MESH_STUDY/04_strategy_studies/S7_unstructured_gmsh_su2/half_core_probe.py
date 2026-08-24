"""Prototype the tetrahedral core of the half domain.

The core is bounded by five farfield faces, the symmetry plane at y=0 with a hole
where the body and its layer sit, and the surface capping the prism layer.  The
hole boundary must be meshed with exactly the layer's own nodes, or the two meshes
meet at coincident-but-separate nodes and the domain is not closed.

    python half_core_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2 import prism_layer as pl  # noqa: E402
from S7_unstructured_gmsh_su2.common import load_policy  # noqa: E402
from S7_unstructured_gmsh_su2.geometry import (  # noqa: E402
    build_pygeo_case,
    build_surface,
)
from S7_unstructured_gmsh_su2.gmsh_pipeline import resolved_mesh_spec  # noqa: E402

OUT = (
    Path(__file__).resolve().parents[2]
    / "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/half_core"
)


def main() -> int:
    import gmsh

    policy = load_policy()
    policy["geometry"]["modeled_domain"] = "half_wing_symmetry_y0"
    level = "laptop_smoke"

    OUT.mkdir(parents=True, exist_ok=True)
    surface = build_surface(
        build_pygeo_case("lhs100_seed42", 0, OUT),
        level=level,
        te_variant="te_1p0mm",
        policy=policy,
    )
    spec = resolved_mesh_spec(surface, level=level, candidate_index=0, policy=policy)
    labels = np.asarray(surface.labels)
    tris = np.asarray(surface.triangles)
    layer = pl.march(
        np.asarray(surface.points),
        tris[labels != "symmetry"],
        list(spec["boundary_layer_cumulative_heights_m"]),
        symmetry_axis=1,
    )
    loops = pl.top_boundary_loops(layer)
    assert len(loops) == 1, f"expected one root loop, got {len(loops)}"
    loop = loops[0]
    print(f"layer: {len(layer.prisms)} prisms, root loop {len(loop)} nodes")

    L = float(surface.metadata["reference_values"]["mean_aerodynamic_chord_m"])
    far = spec["farfield"]
    body = layer.points
    xmin = float(body[:, 0].min() - float(far["upstream_over_L"]) * L)
    xmax = float(body[:, 0].max() + float(far["downstream_over_L"]) * L)
    radial = float(far["radial_over_L"]) * L
    ymax = float(body[:, 1].max() + radial)
    zmin = float(body[:, 2].min() - radial)
    zmax = float(body[:, 2].max() + radial)
    far_lc = float(spec["absolute"]["far_core_edge_m"])
    print(f"domain: x [{xmin:.2f}, {xmax:.2f}]  y [0, {ymax:.2f}]  z [{zmin:.2f}, {zmax:.2f}]")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        geo = gmsh.model.geo

        # Symmetry plane outline at y = 0.
        corners = [
            geo.addPoint(xmin, 0.0, zmin, far_lc),
            geo.addPoint(xmax, 0.0, zmin, far_lc),
            geo.addPoint(xmax, 0.0, zmax, far_lc),
            geo.addPoint(xmin, 0.0, zmax, far_lc),
        ]
        outer_edges = [
            geo.addLine(corners[i], corners[(i + 1) % 4]) for i in range(4)
        ]
        outer_loop = geo.addCurveLoop(outer_edges)

        # The hole: one geo point per layer node, one straight segment between
        # neighbours, each forced to a single element so the plane's mesh lands on
        # exactly these coordinates and nothing is interpolated in between.
        hole_points = [
            geo.addPoint(*layer.points[node].tolist(), far_lc) for node in loop
        ]
        hole_edges = []
        for i, tag in enumerate(hole_points):
            hole_edges.append(geo.addLine(tag, hole_points[(i + 1) % len(hole_points)]))
        for edge in hole_edges:
            geo.mesh.setTransfiniteCurve(edge, 2)
        hole_loop = geo.addCurveLoop(hole_edges)

        symmetry_plane = geo.addPlaneSurface([outer_loop, hole_loop])
        geo.synchronize()

        # The remaining five box faces are ordinary farfield.
        upper = [geo.addPoint(x, ymax, z, far_lc) for x, z in
                 ((xmin, zmin), (xmax, zmin), (xmax, zmax), (xmin, zmax))]
        top_edges = [geo.addLine(upper[i], upper[(i + 1) % 4]) for i in range(4)]
        risers = [geo.addLine(corners[i], upper[i]) for i in range(4)]
        farfield_faces = [geo.addPlaneSurface([geo.addCurveLoop(top_edges)])]
        for i in range(4):
            j = (i + 1) % 4
            side = geo.addCurveLoop(
                [outer_edges[i], risers[j], -top_edges[i], -risers[i]]
            )
            farfield_faces.append(geo.addPlaneSurface([side]))

        geo.synchronize()

        gmsh.model.mesh.generate(2)

        # Collect every boundary triangle Gmsh just produced, in real coordinates.
        shell_tris: list[np.ndarray] = []
        shell_pts: list[np.ndarray] = []
        offset = 0
        for tag in [symmetry_plane, *farfield_faces]:
            ntags, coords, _ = gmsh.model.mesh.getNodes(2, tag, includeBoundary=True)
            local = {int(n): i for i, n in enumerate(ntags)}
            pts = coords.reshape(-1, 3)
            etypes, _, enodes = gmsh.model.mesh.getElements(2, tag)
            for etype, conn in zip(etypes, enodes, strict=True):
                if etype != 2:
                    continue
                tri = np.array([local[int(n)] for n in conn], dtype=np.int64)
                shell_tris.append(tri.reshape(-1, 3) + offset)
            shell_pts.append(pts)
            offset += len(pts)
        gmsh_pts = np.vstack(shell_pts)
        gmsh_tris = np.vstack(shell_tris)
        print(f"\ngmsh boundary: {len(gmsh_tris)} triangles, {len(gmsh_pts)} nodes")
    finally:
        gmsh.finalize()

    # Add the layer cap and weld everything on coordinates.
    cap_nodes = np.unique(layer.top_triangles)
    cap_index = {int(n): i for i, n in enumerate(cap_nodes)}
    cap_pts = layer.points[cap_nodes]
    cap_tris = np.vectorize(cap_index.get)(layer.top_triangles) + len(gmsh_pts)

    points = np.vstack([gmsh_pts, cap_pts])
    triangles = np.vstack([gmsh_tris, cap_tris])

    # Weld on quantised coordinates. `inverse` already maps every original node to
    # its slot in the unique table, so it is the remap; deriving one from
    # `return_index` instead is where an earlier attempt went wrong, because
    # sorting those indices breaks their correspondence with `inverse`.
    keys = np.round(points / 1.0e-9).astype(np.int64)
    unique_keys, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    welded_points = np.zeros((len(unique_keys), 3), dtype=float)
    welded_points[inverse] = points
    welded = inverse[triangles]
    print(f"welded shell: {len(welded_points)} nodes "
          f"({len(points) - len(welded_points)} duplicates merged)")

    # A shell that is not watertight cannot bound a volume, so check before asking.
    counts: dict[tuple[int, int], int] = {}
    for tri in welded:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (int(min(a, b)), int(max(a, b)))
            counts[key] = counts.get(key, 0) + 1
    free = [e for e, c in counts.items() if c != 2]
    print(f"edges shared by exactly two triangles: {len(counts) - len(free)}/{len(counts)}")
    if free:
        print(f"VERDICT: shell is NOT watertight ({len(free)} bad edges)")
        involved = np.array(sorted({n for e in free for n in e}))
        counts_hist: dict[int, int] = {}
        for e in free:
            counts_hist[counts[e]] = counts_hist.get(counts[e], 0) + 1
        print(f"  bad-edge multiplicities: {counts_hist}")
        print(f"  distinct nodes involved: {len(involved)} of {len(welded_points)}")
        ys = welded_points[involved][:, 1]
        print(f"  their y range: {ys.min():+.4f} .. {ys.max():+.4f}")
        print(f"  how many at y=0 exactly: {int((np.abs(ys) < 1e-12).sum())}")
        return 1
    print("VERDICT: shell is watertight")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        ent = gmsh.model.addDiscreteEntity(2)
        gmsh.model.mesh.addNodes(
            2, ent, np.arange(1, len(welded_points) + 1, dtype=np.int64),
            welded_points.ravel(),
        )
        gmsh.model.mesh.addElementsByType(
            ent, 2, np.arange(1, len(welded) + 1, dtype=np.int64),
            (welded + 1).astype(np.int64).ravel(),
        )
        gmsh.model.mesh.createTopology()
        loop = gmsh.model.geo.addSurfaceLoop([ent])
        gmsh.model.geo.addVolume([loop])
        gmsh.model.geo.synchronize()
        print("\ngenerating the core...")
        gmsh.model.mesh.generate(3)
        types, tags, _ = gmsh.model.mesh.getElements(3)
        total = 0
        for etype, group in zip(types, tags, strict=True):
            name = gmsh.model.mesh.getElementProperties(etype)[0]
            print(f"  {name}: {len(group)}")
            total += len(group)
        allc = gmsh.model.mesh.getNodes()[1].reshape(-1, 3)
        print(f"core nodes: {len(allc)}   y min {allc[:,1].min():+.3e}")
        print("VERDICT:", f"core built: {total} cells, y >= 0"
              if total and allc[:, 1].min() > -1e-9 else "CORE FAILED")
        OUT.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(OUT / "half_core.msh"))
    finally:
        gmsh.finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
