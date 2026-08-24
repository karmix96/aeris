"""Does the structured surface mesh converge to the master geometry?

The project's master geometry is the pyGeo B-spline loft (DECISION: master
geometry). A mesh family used for grid convergence must converge to *that*
surface as it refines; if it converges to something else, every GCI triplet
computed on it is measuring two things at once.

The current path is: sample 14 slices -> planarise each -> normalise to a 2-D
airfoil -> resample chordwise -> map back to 3-D -> **linearly interpolate
between neighbouring slices** for spanwise refinement. Three of those steps
throw geometry away, and only one of them shrinks when the mesh is refined.

This script separates the three contributions instead of quoting one number.
``projectPoint`` returns the *vector* offset (the docstring says distance, the
implementation fills an (N, 3) array), so distances are taken as norms.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aeris.mesh.surface import build_surface_mesh  # noqa: E402

from standalone.surface_mesh_v3.geom import build_baseline  # noqa: E402


def deviation(surfs, points: np.ndarray) -> np.ndarray:
    """Min distance from each point to any of the master surfaces."""
    best = np.full(len(points), np.inf)
    for surf in surfs:
        _u, _v, d = surf.projectPoint(points, nIter=80, eps=1e-12)
        d = np.atleast_2d(np.asarray(d, float))
        best = np.minimum(best, np.linalg.norm(d, axis=1))
    return best


COMMON = dict(
    oml_topology="cap4", tip_topology="airfoil_face", dense_airfoil_points_per_surface=301,
    split_x_fore=0.20, minimum_te_thickness=0.0, te_thickness_abs_floor=0.0,
    te_base_points=0, minimum_shape_metric=1e-6, maximum_adjacent_normal_angle_deg=180.0,
    cap_wrap_x=0.40, cap_width_frac=0.50, tip_inner_scale=0.60, tip_dome_scale=0.0,
    tip_conformal_ring=False, tip_smooth_iters=0, chordwise_distribution="uniform",
    chordwise_beta=2.0, spanwise_distribution="uniform", spanwise_beta=2.0,
    spanwise_allocation="proportional",
)


def main() -> None:
    carrier, build, _ = build_baseline()
    surfs = [build.geometry.surfs[0], build.geometry.surfs[1]]
    c_root = float(carrier.sections[0].chord_m)
    print(f"root chord {c_root*1e3:.1f} mm; 14 source sections\n")

    # --- 1. how much does planarising + normalising one slice already cost? ---
    print("1) PLANARISATION of the source slices (before any meshing)")
    for idx in (0, 4, 9, 13):
        sec = carrier.sections[idx]
        pts = np.vstack([sec.upper_xyz_m, sec.lower_xyz_m])
        le = np.asarray(sec.le_xyz_m, float)
        recon = (
            le
            + sec.chord_m
            * (
                np.concatenate([sec.x_upper, sec.x_lower])[:, None] * np.asarray(sec.chord_axis)
                + np.concatenate([sec.z_upper, sec.z_lower])[:, None]
                * np.asarray(sec.thickness_axis)
            )
        )
        d = deviation(surfs, recon)
        print(f"   section {idx:2d} (c={sec.chord_m*1e3:6.1f} mm): "
              f"max {d.max()*1e3:7.3f} mm  rms {np.sqrt((d**2).mean())*1e3:7.4f} mm  "
              f"plane_warp_max {sec.plane_warp_max_chord*sec.chord_m*1e3:6.3f} mm")

    # --- 2. spanwise linear interpolation, isolated ---------------------------
    print("\n2) SPANWISE LINEAR INTERPOLATION between neighbouring source sections")
    print("   (midpoints of each interval, on the section-frame reconstruction)")
    secs = carrier.sections
    worst = []
    for j in range(len(secs) - 1):
        a, b = secs[j], secs[j + 1]
        n = min(len(a.direct_coordinates), len(b.direct_coordinates))
        pa = (np.asarray(a.le_xyz_m) + a.chord_m * (
            a.direct_coordinates[:n, 0:1] * np.asarray(a.chord_axis)
            + a.direct_coordinates[:n, 1:2] * np.asarray(a.thickness_axis)))
        pb = (np.asarray(b.le_xyz_m) + b.chord_m * (
            b.direct_coordinates[:n, 0:1] * np.asarray(b.chord_axis)
            + b.direct_coordinates[:n, 1:2] * np.asarray(b.thickness_axis)))
        mid = 0.5 * (pa + pb)
        d = deviation(surfs, mid)
        worst.append((j, d.max(), np.sqrt((d**2).mean())))
    for j, mx, rms in worst:
        print(f"   interval {j:2d}-{j+1:<2d}: max {mx*1e3:7.3f} mm  rms {rms*1e3:7.4f} mm")
    print(f"   WORST interval max = {max(w[1] for w in worst)*1e3:.3f} mm "
          f"({max(w[1] for w in worst)/c_root*100:.3f} %c_root)")

    # --- 3. the built mesh, with and without the deliberate TE opening --------
    print("\n3) BUILT MESH deviation vs refinement (te_thickness = 0 removes the")
    print("   deliberate blunt-TE offset, isolating pure geometric fidelity)")
    for te in (0.0, 0.005):
        print(f"   te_thickness = {te}")
        for name, lvl in (
            ("L1", dict(points_per_block_side=25, spanwise_panels_per_section=8,
                        cap_wrap_points=5, tip_radial_points=5)),
            ("L3", dict(points_per_block_side=49, spanwise_panels_per_section=16,
                        cap_wrap_points=9, tip_radial_points=7)),
            ("L5", dict(points_per_block_side=97, spanwise_panels_per_section=32,
                        cap_wrap_points=13, tip_radial_points=9)),
        ):
            blocks, _rep = build_surface_mesh(carrier, **COMMON, te_thickness=te, **lvl)
            oml = np.vstack([b.xyz.reshape(-1, 3) for b in blocks if b.name.startswith("oml")])
            rng = np.random.default_rng(7)
            sample = oml[rng.choice(len(oml), size=min(3000, len(oml)), replace=False)]
            d = deviation(surfs, sample)
            print(f"     {name}: nodes {len(oml):7d}  max {d.max()*1e3:7.3f} mm "
                  f"({d.max()/c_root*100:6.3f} %c)  rms {np.sqrt((d**2).mean())*1e3:7.4f} mm")


if __name__ == "__main__":
    main()
