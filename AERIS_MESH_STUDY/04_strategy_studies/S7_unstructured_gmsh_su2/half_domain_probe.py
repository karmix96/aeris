"""Probe how Gmsh extrudes a boundary layer off an OPEN wall surface.

The half model needs the prism layer to terminate in the y=0 plane, where the
symmetry boundary lives.  Whether it actually does - and what entities Gmsh hands
back for those root-end faces - decides how the volume side is built, so it is
measured here rather than assumed.

    python half_domain_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2.common import load_policy  # noqa: E402
from S7_unstructured_gmsh_su2.geometry import (  # noqa: E402
    build_pygeo_case,
    build_surface,
)

OUT = (
    Path(__file__).resolve().parents[2]
    / "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/half_probe"
)


def main() -> int:
    import gmsh

    policy = load_policy()
    policy["geometry"]["modeled_domain"] = "half_wing_symmetry_y0"
    level = "laptop_smoke"

    OUT.mkdir(parents=True, exist_ok=True)
    case = build_pygeo_case("lhs100_seed42", 0, OUT)
    surface = build_surface(case, level=level, te_variant="te_1p0mm", policy=policy)

    labels = np.asarray(surface.labels)
    tris = np.asarray(surface.triangles)
    wall = tris[labels != "symmetry"]
    sym = tris[labels == "symmetry"]
    print(f"wall triangles {len(wall)}, symmetry triangles {len(sym)}")

    from S7_unstructured_gmsh_su2.gmsh_pipeline import resolved_mesh_spec

    spec = resolved_mesh_spec(surface, level=level, candidate_index=0, policy=policy)
    heights = list(spec["boundary_layer_cumulative_heights_m"])
    print(f"BL layers: {len(heights)}, total thickness {heights[-1]:.6f} m")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        # The whole point of the probe: ask for the lateral faces.
        gmsh.option.setNumber("Geometry.ExtrudeReturnLateralEntities", 1)

        wall_surface = gmsh.model.addDiscreteEntity(2, 1)
        node_tags = np.arange(1, len(surface.points) + 1, dtype=np.int64)
        gmsh.model.mesh.addNodes(2, wall_surface, node_tags, surface.points.ravel())
        gmsh.model.mesh.addElementsByType(
            wall_surface, 2,
            np.arange(1, len(wall) + 1, dtype=np.int64),
            (wall + 1).astype(np.int64).ravel(),
        )

        extrusion = gmsh.model.geo.extrudeBoundaryLayer(
            [(2, wall_surface)], [1] * len(heights), heights, True
        )
        gmsh.model.geo.synchronize()

        print(f"\nextrusion returned {len(extrusion)} entities")
        by_dim: dict[int, list[int]] = {}
        for dim, tag in extrusion:
            by_dim.setdefault(dim, []).append(int(tag))
        for dim in sorted(by_dim):
            print(f"  dim {dim}: {len(by_dim[dim])} entities")

        # Where does each returned 2-D entity sit in y? A root-end face should be
        # flat at y=0; the BL top should span the wing.
        print("\n2-D entities by y-extent:")
        flat_at_zero, spanning = [], []
        for tag in by_dim.get(2, []):
            try:
                box = gmsh.model.getBoundingBox(2, tag)
            except Exception:
                continue
            ymin, ymax = box[1], box[4]
            if abs(ymin) < 1e-9 and abs(ymax) < 1e-9:
                flat_at_zero.append(tag)
            else:
                spanning.append((tag, ymin, ymax))
        print(f"  flat at y=0 (candidate symmetry faces): {len(flat_at_zero)}")
        print(f"  spanning in y (BL top / walls):        {len(spanning)}")
        for tag, lo, hi in spanning[:3]:
            print(f"      tag {tag}: y {lo:+.5f} .. {hi:+.5f}")

        gmsh.model.mesh.generate(2)
        tags, coords, _ = gmsh.model.mesh.getNodes()
        nodes = coords.reshape(-1, 3)
        y = nodes[:, 1]
        thickness = heights[-1]
        print(f"\nafter 2-D mesh: {len(nodes)} nodes, y min {y.min():+.6f}")

        # How many nodes sit in the band the symmetry plane must contain, and how
        # far off-plane are they? This decides whether snapping is viable or
        # whether the extrusion direction itself has to be constrained.
        band = np.abs(y) < thickness
        print(f"nodes within one BL thickness of y=0: {int(band.sum())}")
        print(f"  of those, y<0: {int((y[band] < -1e-12).sum())}"
              f"   y>0: {int((y[band] > 1e-12).sum())}"
              f"   y==0: {int((np.abs(y[band]) <= 1e-12).sum())}")
        if band.any():
            off = y[band]
            print(f"  y range in band: {off.min():+.6f} .. {off.max():+.6f}")
            print(f"  worst leak as fraction of BL thickness: "
                  f"{abs(off.min())/thickness:.3%}")
        print("\nVERDICT:", "BL stays at y >= 0" if y.min() > -1e-7
              else "BL LEAKS below y=0 - the extrusion direction must be constrained")
    finally:
        gmsh.finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
