#!/usr/bin/env python3
"""Evaluate the AeroSandbox-free pyGeo OML source through the real mesher path.

Meshes the seed-100 baseline two ways with the identical L3 recipe via the
wing_cap4_v1 topology generator: the native AeroSandbox wing, and the pyGeo
loft wrapped in PyGeoSurfaceGeometry (no Wing.mesh_line, no asb.Airfoil in the
mesh path).  Prints QC side by side.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("standalone").resolve()))

CFG = Path("configs/geometry/baseline_bwb_25.yaml")
AIRFOIL_DB = Path("data/airfoil_database")
RECIPE = dict(points_per_side=49, spanwise_panels=16, spanwise_allocation="proportional",
              cap_wrap_points=21, cap_wrap_x=0.15, tip_radial_points=9,
              tip_smooth_iters=20, te_thickness=0.005)


def _qc(report_path: Path) -> dict:
    rep = json.loads(report_path.read_text())
    oml = [b for b in rep["blocks"] if b["name"].startswith("oml")]
    tip = [b for b in rep["blocks"] if b["name"].startswith("tip")]
    return dict(
        cells=rep["global"]["total_cells"],
        oml_shape=min(b["min_shape_metric"] for b in oml),
        oml_skew=max(b["max_equiangle_skewness"] for b in oml),
        oml_AR=max(b["max_aspect_ratio"] for b in oml),
        oml_growth=max(b["max_growth_ratio"] for b in oml),
        tip_skew=max(b["max_equiangle_skewness"] for b in tip),
    )


def main() -> None:
    from aeris.cfd.meshing.registry import get_topology
    gen = get_topology("wing_cap4_v1")
    out = Path("data/cfd_cases/_pygeo_provider_eval").resolve()
    out.mkdir(parents=True, exist_ok=True)

    # native AeroSandbox wing
    from aeris.commands.mesh import _build_wing
    wing, _, _ = _build_wing(CFG, wing_index=0, geometry_output_dir=out / "native_g",
                             seed_override=100, save_plot=False)
    gen.generate(wing, out / "native", dict(RECIPE))
    native = _qc(out / "native" / "surface_report.json")

    # pyGeo loft -> surface carrier (AeroSandbox-free mesh path)
    from aeris.mesh.surface import PyGeoSurfaceGeometry
    from pygeo_avl_study.case_factory import build_study_case
    from pygeo_avl_study.geometry_bridge import build_pygeo, extract_sections
    case = build_study_case(CFG, airfoil_database=AIRFOIL_DB, seed=100)
    build = build_pygeo(case.pygeo_stations, k_span=3, frame_mode="asb_frame", tip="none")
    sections = extract_sections(build, np.linspace(0.0, 1.0, 14), cst_order=8, chordwise_points=301)
    geom = PyGeoSurfaceGeometry(sections=tuple(sections))
    gen.generate(geom, out / "pygeo", dict(RECIPE))
    pygeo = _qc(out / "pygeo" / "surface_report.json")

    print(f"\n{'metric':<12}{'AeroSandbox':>14}{'pyGeo (no asb)':>16}")
    for k in ("cells", "oml_shape", "oml_skew", "oml_AR", "oml_growth", "tip_skew"):
        print(f"{k:<12}{native[k]:>14.4f}{pygeo[k]:>16.4f}")
    print("\nBOTH BUILT + PASSED QC (generate() raises on QC failure).")
    print("pyGeo mesh path used no Wing.mesh_line and no asb.Airfoil.")


if __name__ == "__main__":
    main()
