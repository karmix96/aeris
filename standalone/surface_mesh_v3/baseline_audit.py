"""Audit the CURRENT structured surface mesher on the registered baseline.

Three questions the AIAA reviewer will ask, answered with measurements rather
than with the existing reports:

1. What is the real per-region quality of the shipped ``cap4`` +
   ``airfoil_face`` recipe at the registered levels?
2. Does the surface mesh converge to the master pyGeo geometry under
   refinement, or only to a piecewise-linear stand-in for it?
3. Where, physically, are the worst cells?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aeris.mesh.surface import build_surface_mesh  # noqa: E402

from standalone.surface_mesh_v3.geom import build_baseline  # noqa: E402
from standalone.surface_mesh_v3.measure import HEADER, block_fields, pooled, score  # noqa: E402

LEVELS = {
    "L1": dict(points_per_block_side=25, spanwise_panels_per_section=8, cap_wrap_points=5,
               tip_radial_points=5),
    "L3": dict(points_per_block_side=49, spanwise_panels_per_section=16, cap_wrap_points=9,
               tip_radial_points=7),
    "L5": dict(points_per_block_side=97, spanwise_panels_per_section=32, cap_wrap_points=13,
               tip_radial_points=9),
}
COMMON = dict(
    oml_topology="cap4",
    tip_topology="airfoil_face",
    dense_airfoil_points_per_surface=301,
    split_x_fore=0.20,
    minimum_te_thickness=0.002,
    te_thickness=0.005,
    te_thickness_abs_floor=0.0,
    te_base_points=0,
    minimum_shape_metric=1e-6,
    maximum_adjacent_normal_angle_deg=180.0,
    cap_wrap_x=0.40,
    cap_width_frac=0.50,
    tip_inner_scale=0.60,
    tip_dome_scale=0.0,
    tip_conformal_ring=False,
    tip_smooth_iters=0,
    chordwise_distribution="uniform",
    chordwise_beta=2.0,
    spanwise_distribution="uniform",
    spanwise_beta=2.0,
    spanwise_allocation="proportional",
)


def surface_deviation(blocks, build, n_sample: int = 4000) -> dict[str, float]:
    """Distance from mesh nodes to the master pyGeo B-spline surfaces.

    Uses pySpline's own point-inversion (``projectPoint``) against both the
    upper and lower surface, taking the smaller residual. Reported relative to
    the root chord, which is the length every other geometry tolerance in this
    project is quoted against.
    """
    upper, lower = build.geometry.surfs[0], build.geometry.surfs[1]
    nodes = np.vstack([b.xyz.reshape(-1, 3) for b in blocks])
    rng = np.random.default_rng(20260726)
    idx = rng.choice(len(nodes), size=min(n_sample, len(nodes)), replace=False)
    sample = nodes[idx]

    best = np.full(len(sample), np.inf)
    for surf in (upper, lower):
        _u, _v, dist = surf.projectPoint(sample, nIter=60, eps=1e-12)
        best = np.minimum(best, np.abs(np.asarray(dist, float)).reshape(len(sample), -1).max(axis=1)
                          if np.ndim(dist) > 1 else np.abs(np.asarray(dist, float)))
    return {
        "max_m": float(np.max(best)),
        "rms_m": float(np.sqrt(np.mean(best**2))),
        "p99_m": float(np.percentile(best, 99)),
    }


def main() -> None:
    carrier, build, _geom = build_baseline()
    root_chord = float(carrier.sections[0].chord_m)
    out: dict[str, object] = {"root_chord_m": root_chord, "levels": {}}

    for name, level in LEVELS.items():
        blocks, report = build_surface_mesh(carrier, **COMMON, **level)
        by_name = {b.name: b.xyz for b in blocks}
        oml = [n for n in by_name if n.startswith("oml")]
        tip = [n for n in by_name if n.startswith("tip")]

        print(f"\n=== {name}  cells={report['global']['total_cells']}  "
              f"pts={level['points_per_block_side']} span={level['spanwise_panels_per_section']} "
              f"wrap={level['cap_wrap_points']}")
        print(HEADER)
        for group, names in (("OML", oml), ("TIP", tip)):
            s = score({**pooled(by_name, names), "growth": pooled(by_name, names)["growth"]},
                      None, group)
            if s:
                print(s.line())
        for bname in oml + tip:
            fields = block_fields(by_name[bname])
            s = score(fields, None, "  " + bname)
            if s:
                print(s.line())

        dev = surface_deviation(blocks, build)
        print(f"  geometry deviation from master loft: max {dev['max_m']*1e3:.3f} mm "
              f"({dev['max_m']/root_chord*100:.3f} %c_root), rms {dev['rms_m']*1e3:.4f} mm")
        out["levels"][name] = {
            "cells": report["global"]["total_cells"],
            "deviation": dev,
            "global": report["global"],
            "blocks": report["blocks"],
        }

    path = Path("data/surface_mesh_v3/baseline_audit.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
