#!/usr/bin/env python3
"""Measure the TE absolute-thickness floor (SURFACE_MESH_LAWS.md law 10 / task a).

Builds L3 (seed 100) under four TE treatments and reports the trailing-edge
block (oml_2), the tip, and the actual per-section TE thickness, to answer:
does te_thickness_abs_floor (metres) let te_base_points pin the blunt-TE
corners without the outboard-sliver OML degradation law 10 measured?
"""
from __future__ import annotations

import json
from pathlib import Path

from aeris.cfd.meshing.registry import get_topology
from aeris.commands.mesh import _build_wing

L3 = dict(points_per_side=49, spanwise_panels=16, spanwise_allocation="proportional",
          cap_wrap_points=21, cap_wrap_x=0.15, tip_radial_points=9,
          tip_smooth_iters=20, te_thickness=0.005)

# Constant ABSOLUTE TE (te_thickness=0 fractional, floor supplies all of it).
VARIANTS = {"0.5%c fractional (current)": dict(te_thickness=0.005)}
for _mm in (3.0, 3.5, 4.0):
    VARIANTS[f"const {_mm:.1f}mm absolute"] = dict(
        te_thickness=0.0, te_thickness_abs_floor=_mm / 1000.0)


def _block(rep, name):
    return next(b for b in rep["blocks"] if b["name"] == name)


def main() -> None:
    gen = get_topology("wing_cap4_v1")
    out = Path("data/cfd_cases/te_floor_probe").resolve()
    out.mkdir(parents=True, exist_ok=True)
    wing, _, _ = _build_wing(Path("configs/geometry/baseline_bwb_25.yaml"), wing_index=0,
                             geometry_output_dir=out / "geom", seed_override=100, save_plot=False)
    chords = [float(getattr(x, "chord", float("nan"))) for x in wing.xsecs]
    print(f"chords: root={max(chords):.3f} m  tip={min(chords):.3f} m  "
          f"(0.5%c = {5*max(chords):.2f}mm root, {5*min(chords):.2f}mm tip)\n")
    hdr = ("variant", "oml2_grow", "oml2_skew", "oml2_shape", "oml2_ang",
           "tip_skew", "worstOMLgrow", "status")
    print("  ".join(f"{h:>11}" for h in hdr))
    for label, extra in VARIANTS.items():
        recipe = {**L3, **extra}
        vdir = out / label.strip().replace(" ", "_").replace("=", "")
        try:
            gen.generate(wing, vdir, recipe)
            rep = json.loads((vdir / "surface_report.json").read_text())
            o2 = _block(rep, "oml_2")
            oml = [b for b in rep["blocks"] if b["name"].startswith("oml")]
            tip = [b for b in rep["blocks"] if b["name"].startswith("tip")]
            row = (label,
                   f"{o2['max_growth_ratio']:.3f}",
                   f"{o2['max_equiangle_skewness']:.3f}",
                   f"{o2['min_shape_metric']:.3f}",
                   f"{o2['max_adjacent_normal_angle_deg']:.1f}",
                   f"{max(b['max_equiangle_skewness'] for b in tip):.3f}",
                   f"{max(b['max_growth_ratio'] for b in oml):.3f}",
                   "ok")
        except Exception as exc:  # noqa: BLE001
            row = (label, "-", "-", "-", "-", "-", "-", f"{type(exc).__name__}")
        print("  ".join(f"{c:>11}" for c in row))


if __name__ == "__main__":
    main()
