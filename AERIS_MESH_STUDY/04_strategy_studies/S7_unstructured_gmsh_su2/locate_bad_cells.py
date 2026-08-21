"""Diagnostic: where are the cells that violate the core quality gates?

A max-only verdict says how bad the worst cell is, never where it is.  Designing
refinement without that location is guesswork -- it is what produced the
withdrawn trailing-edge thickness law.  This regenerates the graded probe mesh
and reports, for each violating face, its distance to the wall and to the
trailing-edge line, so the offending region is identified from measurement.
"""

from __future__ import annotations

import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2 import gmsh_pipeline as P  # noqa: E402
from S7_unstructured_gmsh_su2.bl_te_probe import ROOT, _policy, _surface  # noqa: E402


def main() -> int:
    policy = _policy(1.0e-3, 1.35)
    surface = _surface(policy)
    target = ROOT / "locate"
    if target.exists():
        shutil.rmtree(target)
    report = P.generate_mesh(
        surface, output_dir=target, level="laptop_smoke",
        candidate_index=0, policy=policy,
    )
    print("mesh:", report["gmsh_element_counts"], flush=True)

    import gmsh

    gmsh.initialize([])
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.open(str(Path(report["mesh_msh"]).resolve()))
    tags, flat, _ = gmsh.model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    coords = np.asarray(flat, dtype=float).reshape(-1, 3)
    order = np.argsort(tags)
    tags, coords = tags[order], coords[order]

    tets = None
    for element_type, _etags, connectivity in zip(*gmsh.model.mesh.getElements(3), strict=True):
        if int(element_type) == 4:
            tets = np.asarray(connectivity, dtype=np.int64).reshape(-1, 4)
    gmsh.finalize()
    assert tets is not None
    idx = np.searchsorted(tags, tets)
    pts = coords[idx]
    volumes = np.abs(
        np.linalg.det(
            np.stack([pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0], pts[:, 3] - pts[:, 0]], axis=2)
        )
    ) / 6.0
    centres = pts.mean(axis=1)

    faces: dict[tuple[int, ...], list[int]] = {}
    for cell, row in enumerate(idx):
        for local in ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)):
            key = tuple(sorted(int(row[i]) for i in local))
            faces.setdefault(key, []).append(cell)

    wall = np.asarray(surface.points, dtype=float)
    te_line = P.trailing_edge_sample_points(surface, target_spacing=2.0e-3, max_points=4000)
    from scipy.spatial import cKDTree

    wall_tree, te_tree = cKDTree(wall), cKDTree(te_line)

    bad_centres, ratios = [], []
    for owners in faces.values():
        if len(owners) != 2:
            continue
        left, right = owners
        ratio = max(volumes[left], volumes[right]) / max(min(volumes[left], volumes[right]), 1e-300)
        if ratio > 5.0:
            bad_centres.append(0.5 * (centres[left] + centres[right]))
            ratios.append(ratio)
    if not bad_centres:
        print("no violating faces")
        return 0
    bad = np.asarray(bad_centres)
    ratios = np.asarray(ratios)
    d_wall, _ = wall_tree.query(bad, k=1)
    d_te, _ = te_tree.query(bad, k=1)
    L = float(surface.metadata["reference_values"]["mean_aerodynamic_chord_m"])
    print(f"violating faces: {len(bad)}   (limit 5)")
    print(
        f"  ratio       p50 {np.percentile(ratios, 50):.1f}"
        f"  p99 {np.percentile(ratios, 99):.1f}  max {ratios.max():.1f}"
    )
    for name, d in (("distance to wall", d_wall), ("distance to TE line", d_te)):
        print(
            f"  {name:22s} p05 {np.percentile(d, 5) / L:.3f} L"
            f"  p50 {np.percentile(d, 50) / L:.3f} L"
            f"  p95 {np.percentile(d, 95) / L:.3f} L"
        )
    near_wall = int((d_wall < 0.05 * L).sum())
    near_te = int((d_te < 0.05 * L).sum())
    print(f"  within 0.05 L of the wall: {near_wall} ({near_wall/len(bad):.1%})")
    print(f"  within 0.05 L of the TE  : {near_te} ({near_te/len(bad):.1%})")
    worst = np.argsort(ratios)[-8:][::-1]
    print("  worst faces (ratio, xyz, d_wall/L, d_te/L):")
    for w in worst:
        print(f"    {ratios[w]:10.1f}  {np.round(bad[w],4)}  {d_wall[w]/L:6.3f}  {d_te[w]/L:6.3f}")
    span = Counter()
    for w in range(len(bad)):
        span["|y| > 1.0 m (tip region)" if abs(bad[w][1]) > 1.0 else "inboard"] += 1
    print("  spanwise split:", dict(span))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
