"""Does the S7 surface stage hold across the design space, or only on index 0?

Every geometric conclusion so far rests on one wing.  Design space exploration
needs the pipeline to succeed across designs and trailing-edge variants without
per-case attention, so this walks the preregistered representative indices at
every level and variant and reports pass/fail plus the margins that matter.

Surface stage only: it is cheap, it is where all four corrected defects lived,
and it fails closed before Gmsh is ever invoked.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2 import geometry as G  # noqa: E402
from S7_unstructured_gmsh_su2.common import load_policy  # noqa: E402
from S7_unstructured_gmsh_su2.qualification import REPRESENTATIVE_INDICES  # noqa: E402

VARIANTS = ("te_0p5mm", "te_1p0mm", "te_1p5mm")
ROOT = Path(__file__).resolve().parents[2] / (
    "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/design_space"
)


def main() -> int:
    levels = sys.argv[1].split(",") if len(sys.argv) > 1 else ["laptop_smoke"]
    policy = load_policy()
    set_name = str(policy["data"]["development_set"])
    ROOT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for index in REPRESENTATIVE_INDICES:
        case = G.build_pygeo_case(set_name, int(index), ROOT / f"pygeo_{index:03d}")
        reference = case.pygeo_result.reference_values
        for level in levels:
            for variant in VARIANTS:
                started = time.time()
                row = {
                    "index": int(index),
                    "geometry_id": case.pygeo_result.geometry_id,
                    "mac_m": float(reference["mean_aerodynamic_chord_m"]),
                    "span_m": float(reference["span_m"]),
                    "level": level,
                    "te_variant": variant,
                }
                try:
                    surface = G.build_surface(
                        case, level=level, te_variant=variant, policy=policy
                    )
                    meta = surface.metadata
                    topo, fid = meta["topology"], meta["fidelity"]
                    row.update(
                        accepted=True,
                        triangles=int(topo["triangle_count"]),
                        self_intersections=int(topo["self_intersection_count"]),
                        boundary_edges=int(topo["boundary_edge_count"]),
                        nonmanifold_edges=int(topo["nonmanifold_edge_count"]),
                        node_fidelity=float(fid["max_node_distance_over_local_chord"]),
                        facet_fidelity=float(
                            fid["max_facet_centroid_distance_over_local_chord"]
                        ),
                        facet_limit=float(fid["limit_facet_centroid_over_local_chord"]),
                        te_opening_mm=1e3 * float(fid["min_realized_te_opening_m"]),
                    )
                except Exception as exc:  # noqa: BLE001 - failures are the result
                    row.update(accepted=False, error=f"{type(exc).__name__}: {exc}")
                row["seconds"] = round(time.time() - started, 1)
                rows.append(row)
                flag = "ok  " if row["accepted"] else "FAIL"
                extra = (
                    f"tris={row['triangles']:7d} si={row['self_intersections']} "
                    f"facet={row['facet_fidelity']:.3e}/{row['facet_limit']:.1e} "
                    f"te={row['te_opening_mm']:.2f}mm"
                    if row["accepted"]
                    else row["error"][:70]
                )
                print(
                    f"{flag} idx {index:3d} {level:<13s} {variant:<9s} {extra} "
                    f"({row['seconds']}s)",
                    flush=True,
                )
    out = ROOT / f"design_space_{'_'.join(levels)}.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    passed = sum(r["accepted"] for r in rows)
    print(f"\n{passed}/{len(rows)} accepted -> {out}")
    return 0 if passed == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
