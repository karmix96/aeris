"""S4 driver — surface, direct volume, and the ADR-0011/ADR-0014 gates.

    .venv/bin/python .../S4_analytic_multiblock/run_s4.py surface [--geom N ...]
    .venv/bin/python .../S4_analytic_multiblock/run_s4.py volume  [--geom N ...] [--level smoke]
    .venv/bin/python .../S4_analytic_multiblock/run_s4.py levels

S4 does not march, so unlike every other strategy's driver this one *builds* the
volume rather than preparing commands for it. That is not a heavy-compute exception:
a boundary-layer O-layer is seconds of numpy, and there is nothing to hand off.
"""

from __future__ import annotations

import argparse
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
import volume_s4 as V4  # noqa: E402
from shared import gates, geometry_sets, verify, volume_qc  # noqa: E402
from shared.qc import qc_blocks, worst_corner_angle_deg  # noqa: E402

ART = HERE / "artifacts"
DEV_SET = "lhs100_seed42"
SURFACE_LEVEL = "L2_smoke"

#: S1 on the same geometries and level, for a like-for-like row in every table.
#: The in-house quality figure is the ADR-0014 §3.4 measurement of S1's OWN pyHyp
#: volumes, not a conversion of pyHyp's number — the two metrics differ by a factor
#: of 0.585 to 0.660 and comparing across them would be meaningless.
S1_REFERENCE = {
    "surface_min_scaled_jacobian": 0.236,
    "surface_cell_size_range": 114.1,
    "volume_pyhyp_min_quality": "0.193 to 0.364 (10/10 at epsE 1.5 and 2.0)",
    "volume_inhouse_min_scaled_quality": "0.170 to 0.231 (ADR-0014 §3.4 sample)",
}


def _surface(wing, level=SURFACE_LEVEL, **kw):
    blocks, info = S4.build_surface(wing, level=level, **kw)
    qc = qc_blocks(blocks)
    fid = verify.oml_fidelity(wing, blocks, te_thickness_abs_m=info["te_thickness_abs_m"])
    water = verify.watertight_tip(blocks)
    tips = [b for b in blocks if b.name.startswith("tip")]
    passed, reasons = gates.surface_gate_checklist(
        qc, fid, info["orientation"], water["watertight_tip"], deterministic_connectivity=True
    )
    measured = {
        "blocks": qc["block_count"],
        "cells": qc["total_cells"],
        "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
        "min_shape_metric": qc["global"]["min_shape_metric"],
        "max_skewness": qc["global"]["max_equiangle_skewness"],
        "max_aspect_ratio": qc["global"]["max_aspect_ratio"],
        "cell_size_range": qc["cell_size_range"],
        "min_cell_edge_m": qc["min_cell_edge_m"],
        "min_cell_edge_block": qc["min_cell_edge_block"],
        "worst_tip_corner_deg": max(worst_corner_angle_deg(b.xyz) for b in tips),
        "watertight_tip": water["watertight_tip"],
        "fidelity_frac_of_chord": fid["worst_frac_of_local_chord"],
        "fidelity_unverified": fid["fidelity_unverified_for_refined_blocks"],
        "surface_gate": "PASS" if passed else "FAIL",
        "surface_gate_reasons": reasons,
        "spanwise_cells": info["spanwise"]["spanwise_cells"],
    }
    return blocks, info, measured


def surface(geoms: list[int]) -> int:
    rows, per_geometry = [], {}
    print(f"{'geometry':10s} {'blk':>3s} {'cells':>7s} {'minJac':>9s} {'shape':>8s} "
          f"{'range':>8s} {'tipCorner':>10s} {'water':>6s} {'gate':>5s}")
    for i in geoms:
        gid = geometry_sets.geometry_id(DEV_SET, i)
        wing = geometry_sets.wing(DEV_SET, i)
        blocks, info, m = _surface(wing)
        m["geometry"] = gid
        rows.append(m)
        per_geometry[gid] = verify.verify_geometry(
            wing, blocks, te_thickness_abs_m=info["te_thickness_abs_m"]
        )
        print(f"{gid[-7:]:10s} {m['blocks']:3d} {m['cells']:7d} {m['min_scaled_jacobian']:9.5f} "
              f"{m['min_shape_metric']:8.5f} {m['cell_size_range']:8.1f} "
              f"{m['worst_tip_corner_deg']:10.3f} {str(m['watertight_tip']):>6s} "
              f"{m['surface_gate']:>5s}")

    det = verify.verify_set(per_geometry)
    worst = min(r["min_scaled_jacobian"] for r in rows)
    print(f"\ndeterministic connectivity : {det['deterministic_connectivity']} "
          f"({det['distinct_connectivity_signatures']} signature/s)")
    print(f"dimensions adapt           : {det['dimensions_adapt_to_geometry']} "
          f"({det['distinct_block_dimension_sets']} dimension set/s)")
    print(f"worst min scaled Jacobian  : {worst:.5f} across {len(rows)} geometries")
    print(f"S1, same geometries/level  : {S1_REFERENCE['surface_min_scaled_jacobian']:.5f}, "
          f"range {S1_REFERENCE['surface_cell_size_range']}")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s4_surface.json").write_text(
        json.dumps(
            {"strategy_id": S4.STRATEGY_ID, "level": SURFACE_LEVEL,
             "s1_reference": S1_REFERENCE, "determinism": det, "rows": rows},
            indent=2,
        )
        + "\n"
    )
    return 0


def volume(geoms: list[int], level: str) -> int:
    rows = []
    print(f"{'geometry':10s} {'blk':>3s} {'cells':>9s} {'minVol':>11s} {'inv':>4s} "
          f"{'minQ':>9s} {'meanQ':>7s} {'>=0.30':>7s} {'gate':>5s}")
    for i in geoms:
        gid = geometry_sets.geometry_id(DEV_SET, i)
        wing = geometry_sets.wing(DEV_SET, i)
        blocks, info, _m = _surface(wing)
        s0 = V4.S0_for(blocks, level)
        vol, vinfo = V4.build_volume(
            wing, blocks, bl_points=S4.LEVELS[SURFACE_LEVEL]["bl_points"], s0=s0
        )
        rep = volume_qc.volume_report(vol)
        ok, why = gates.volume_gate_checklist_direct(rep)
        row = {"geometry": gid, "level": level, "s0_m": s0,
               **{k: rep[k] for k in ("block_count", "total_cells", "min_volume",
                                      "inverted_cells", "min_scaled_quality",
                                      "mean_scaled_quality", "low_quality_blocks",
                                      "fraction_at_or_above_0_30")},
               "build": vinfo, "volume_gate": "PASS" if ok else "FAIL",
               "volume_gate_reasons": why}
        rows.append(row)
        print(f"{gid[-7:]:10s} {rep['block_count']:3d} {rep['total_cells']:9d} "
              f"{rep['min_volume']:11.4e} {rep['inverted_cells']:4d} "
              f"{rep['min_scaled_quality']:+9.5f} {rep['mean_scaled_quality']:7.4f} "
              f"{rep['fraction_at_or_above_0_30']:7.3f} "
              f"{('PASS' if ok else 'FAIL'):>5s}")

    npass = sum(1 for r in rows if r["volume_gate"] == "PASS")
    print(f"\nADR-0014 volume gate       : {npass}/{len(rows)}")
    print(f"S1 in-house min quality    : {S1_REFERENCE['volume_inhouse_min_scaled_quality']}")
    print("Cell counts are NOT comparable with S1's — S4 builds the boundary layer "
          "only (ADR-0014 §4).")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / f"s4_volume_{level}.json").write_text(
        json.dumps(
            {"strategy_id": S4.STRATEGY_ID, "adr": "ADR-0014-non-pyhyp-volume-gate.md",
             "surface_level": SURFACE_LEVEL, "normal_level": level,
             "s1_reference": S1_REFERENCE, "passed": npass, "of": len(rows),
             "rows": rows},
            indent=2,
        )
        + "\n"
    )
    return 0


def levels(geom: int) -> int:
    """S4 at every surface level on one geometry — the refinement ladder."""
    wing = geometry_sets.wing(DEV_SET, geom)
    rows = []
    print(f"{'level':14s} {'blk':>3s} {'cells':>8s} {'minJac':>9s} {'range':>8s} "
          f"{'tipCorner':>10s} {'span':>5s} {'gate':>5s}")
    for lv in S4.LEVELS:
        _b, _i, m = _surface(wing, level=lv)
        m["level"] = lv
        rows.append(m)
        print(f"{lv:14s} {m['blocks']:3d} {m['cells']:8d} {m['min_scaled_jacobian']:9.5f} "
              f"{m['cell_size_range']:8.1f} {m['worst_tip_corner_deg']:10.3f} "
              f"{m['spanwise_cells']:5d} {m['surface_gate']:>5s}")
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s4_levels.json").write_text(
        json.dumps({"strategy_id": S4.STRATEGY_ID,
                    "geometry": geometry_sets.geometry_id(DEV_SET, geom),
                    "rows": rows}, indent=2) + "\n"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["surface", "volume", "levels"])
    ap.add_argument("--geom", type=int, nargs="+", default=list(range(10)))
    ap.add_argument("--level", default="smoke", choices=sorted(V4.S0_FRAC))
    a = ap.parse_args()
    if a.command == "surface":
        return surface(a.geom)
    if a.command == "volume":
        return volume(a.geom, a.level)
    return levels(a.geom[0])


if __name__ == "__main__":
    raise SystemExit(main())
