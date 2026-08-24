"""S4 tip-cap parameter sweep — trial and error, measured rather than argued.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S4_analytic_multiblock/tune_s4_tip.py

The tip cap has four free parameters and none of them come from the paper:

    shape_alpha  how much of the boundary edge's shape the inner edge inherits
                 (Eq. 18's alpha; 0 = straight inner edge, 1 = a full scaled copy)
    core_frac    the core rectangle's half-height, as a fraction of local half-thickness
    fore_frac    chordwise station of the core's forward edge
    nose_points  points on the nose arc, which through |E_B| = |E_D| also sets the
                 aft collar

Swept on ONE development geometry, then the selection is confirmed across the set
by `run_s4.py`. Nothing here touches `round_c_lhs10_seed42`.
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
from shared.qc import qc_blocks, worst_corner_angle_deg  # noqa: E402

ART = HERE / "artifacts"
LEVEL = "L2_smoke"


def measure(wing, **kw):
    blocks, info = S4.build_surface(wing, level=LEVEL, **kw)
    qc = qc_blocks(blocks)
    tips = [b for b in blocks if b.name.startswith("tip")]
    return {
        "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
        "min_shape_metric": qc["global"]["min_shape_metric"],
        "max_skewness": qc["global"]["max_equiangle_skewness"],
        "cell_size_range": qc["cell_size_range"],
        "worst_tip_corner_deg": max(worst_corner_angle_deg(b.xyz) for b in tips),
        "cells": qc["total_cells"],
        "arc_counts": info["arc_counts"],
        "boundary_edge_points": info["boundary_edge_points"],
    }


def main() -> int:
    wing = geometry_sets.wing("lhs100_seed42", 0)
    grid = {
        "shape_alpha": (0.0, 0.15, 0.30, 0.45, 0.60),
        "core_frac": (0.35, 0.50, 0.65),
        "fore_frac": (0.06, 0.12, 0.20),
        "nose_points": (9, 13, 21),
    }
    keys = list(grid)
    rows = []
    print(f"{'alpha':>6s} {'core':>5s} {'fore':>5s} {'nose':>5s} "
          f"{'minJac':>9s} {'shape':>8s} {'skew':>6s} {'range':>8s} {'tipCorner':>10s}")
    for combo in itertools.product(*(grid[k] for k in keys)):
        kw = dict(zip(keys, combo, strict=True))
        try:
            m = measure(wing, **kw)
        except Exception as exc:
            print(f"{combo}  BUILD FAILED: {exc}")
            continue
        rows.append({**kw, **m})
        print(f"{kw['shape_alpha']:6.2f} {kw['core_frac']:5.2f} {kw['fore_frac']:5.2f} "
              f"{kw['nose_points']:5d} {m['min_scaled_jacobian']:9.5f} "
              f"{m['min_shape_metric']:8.5f} {m['max_skewness']:6.3f} "
              f"{m['cell_size_range']:8.1f} {m['worst_tip_corner_deg']:10.3f}")

    if not rows:
        print("every combination failed to build")
        return 1

    best = max(rows, key=lambda r: r["min_scaled_jacobian"])
    print("\nbest by min scaled Jacobian:")
    for k in ("shape_alpha", "core_frac", "fore_frac", "nose_points",
              "min_scaled_jacobian", "cell_size_range", "worst_tip_corner_deg"):
        print(f"  {k:24s} {best[k]}")
    print(f"  arc counts               {best['arc_counts']}")
    print(f"  boundary edges           {best['boundary_edge_points']}")
    print("\nS1 on the same geometry and level: minJac +0.236, range 114.1")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s4_tip_sweep.json").write_text(
        json.dumps(
            {
                "strategy_id": S4.STRATEGY_ID,
                "level": LEVEL,
                "geometry": geometry_sets.geometry_id("lhs100_seed42", 0),
                "grid": {k: list(v) for k, v in grid.items()},
                "best": best,
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
