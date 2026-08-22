"""Measure facet-centroid fidelity over the representative designs.

The per-level facet limits were first calibrated from a single design.  Index 49
then missed the `coarse` limit by 2.5 percent while every other design carried
1.65x to 2.48x margin, which is a calibration defect rather than a geometry
defect: a gate must be sized against the population it has to cover.

This measures every representative design at every level with the facet gate
lifted, so the limits can be set from the worst real design plus margin.  It
changes nothing by itself and writes only a measurement table.
"""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2 import geometry as G  # noqa: E402
from S7_unstructured_gmsh_su2.common import load_policy  # noqa: E402
from S7_unstructured_gmsh_su2.qualification import REPRESENTATIVE_INDICES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / (
    "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/design_space"
)


def main() -> int:
    levels = sys.argv[1].split(",") if len(sys.argv) > 1 else ["coarse"]
    stock = load_policy()
    limits = stock["mesh_gates"]["source_geometry"]["max_facet_centroid_over_local_chord"]
    lifted = copy.deepcopy(stock)
    for level in lifted["mesh_gates"]["source_geometry"][
        "max_facet_centroid_over_local_chord"
    ]:
        lifted["mesh_gates"]["source_geometry"][
            "max_facet_centroid_over_local_chord"
        ][level] = 1.0e9

    rows: list[dict] = []
    for index in REPRESENTATIVE_INDICES:
        case = G.build_pygeo_case(
            str(stock["data"]["development_set"]), int(index), ROOT / f"pygeo_{index:03d}"
        )
        for level in levels:
            started = time.time()
            surface = G.build_surface(
                case, level=level, te_variant="te_1p0mm", policy=lifted
            )
            facet = float(
                surface.metadata["fidelity"]["max_facet_centroid_distance_over_local_chord"]
            )
            rows.append({"index": int(index), "level": level, "facet": facet})
            print(
                f"idx {index:3d} {level:<13s} facet {facet:.4e}"
                f"  current limit {limits[level]:.1e}"
                f"  margin {limits[level] / facet:5.2f}x"
                f"  ({time.time() - started:.0f}s)",
                flush=True,
            )

    print("\nworst design per level, and a 1.5x-margin limit:")
    for level in levels:
        worst = max(r["facet"] for r in rows if r["level"] == level)
        print(
            f"  {level:<13s} worst {worst:.4e}"
            f"  current {limits[level]:.1e}"
            f"  suggested {1.5 * worst:.2e}"
        )
    out = ROOT / f"facet_calibration_{'_'.join(levels)}.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
