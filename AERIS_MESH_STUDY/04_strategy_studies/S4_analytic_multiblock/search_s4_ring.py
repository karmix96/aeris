"""S4 ring-corner search — which four Type 1 vertices should carry the cap corners.

    .venv/bin/python .../S4_analytic_multiblock/search_s4_ring.py [--geoms 0 1 2]

The tip cap's four ring corners are a *topology* choice, not a tuning knob, and
there are only 70 of them. Every admissible choice is built and measured rather than
argued for, on more than one geometry, because a corner that happens to fall on a
convex part of one section can fall on a concave part of the next.

Admissible means: the base is not isolated as its own boundary edge (`{0, 7}`) and
neither is the nose arc (`{3, 4}`) — see `strategy_s4.boundary_groups`.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s4 as S4  # noqa: E402
from shared import geometry_sets  # noqa: E402
from shared.ingestion import MeshBuildError  # noqa: E402
from shared.qc import qc_blocks, worst_corner_angle_deg  # noqa: E402

ART = HERE / "artifacts"
LEVEL = "L2_smoke"


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--geoms", type=int, nargs="+", default=[0, 3, 6])
    ap.add_argument("--shrink", type=float, nargs="+", default=[0.40, 0.55, 0.70])
    args = ap.parse_args()

    wings = [geometry_sets.wing("lhs100_seed42", g) for g in args.geoms]
    rows = []
    print(f"{'ring':>16s} {'shrink':>7s} {'worstMinJac':>12s} {'worstRange':>11s} "
          f"{'worstCorner':>12s} {'geoms':>6s}")
    for ring in itertools.combinations(range(8), 4):
        if (0 in ring and 7 in ring) or (3 in ring and 4 in ring):
            continue
        for shrink in args.shrink:
            per = []
            for w in wings:
                try:
                    blocks, _info = S4.build_surface(
                        w, level=LEVEL, ring_corners=ring, core_shrink=shrink
                    )
                except (MeshBuildError, ValueError, IndexError):
                    per = []
                    break
                qc = qc_blocks(blocks)
                tips = [b for b in blocks if b.name.startswith("tip")]
                per.append(
                    (
                        qc["global"]["min_scaled_jacobian"],
                        qc["cell_size_range"],
                        max(worst_corner_angle_deg(b.xyz) for b in tips),
                    )
                )
            if not per:
                continue
            row = {
                "ring": list(ring),
                "core_shrink": shrink,
                "worst_min_scaled_jacobian": min(p[0] for p in per),
                "worst_cell_size_range": max(p[1] for p in per),
                "worst_tip_corner_deg": max(p[2] for p in per),
                "geometries": len(per),
            }
            rows.append(row)
            print(f"{str(ring):>16s} {shrink:7.2f} {row['worst_min_scaled_jacobian']:12.5f} "
                  f"{row['worst_cell_size_range']:11.1f} {row['worst_tip_corner_deg']:12.3f} "
                  f"{row['geometries']:6d}")

    if not rows:
        print("no admissible ring built on every geometry")
        return 1

    ok = [r for r in rows if r["worst_min_scaled_jacobian"] > 0.0]
    print(f"\nadmissible rings built  : {len({tuple(r['ring']) for r in rows})}")
    print(f"combinations with minJac > 0 on every geometry: {len(ok)} of {len(rows)}")
    best = max(rows, key=lambda r: r["worst_min_scaled_jacobian"])
    print("\nbest:")
    for k, v in best.items():
        print(f"  {k:28s} {v}")
    print("\nS1 on the same geometries and level: minJac +0.236, range 114.1")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s4_ring_search.json").write_text(
        json.dumps(
            {"strategy_id": S4.STRATEGY_ID, "level": LEVEL,
             "geometries": [geometry_sets.geometry_id("lhs100_seed42", g) for g in args.geoms],
             "best": best, "positive_combinations": len(ok), "rows": rows},
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
