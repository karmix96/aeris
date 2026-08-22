"""S0 driver — baseline build, the wrap_x sweep, and the refinement set.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S0_cap4/run_s0.py baseline
    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S0_cap4/run_s0.py wrapx
    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S0_cap4/run_s0.py refine [n]

Surface only. Heavy compute is prepared, never launched here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s0 as S0  # noqa: E402
from shared import gates, geometry_sets, verify  # noqa: E402
from shared.qc import qc_blocks, worst_corner_angle_deg  # noqa: E402

ART = HERE / "artifacts"

# Stage 01 / Stage 02 cap4, measured at the SHIPPED defaults, not the selected
# recipe. `status` sections 3.3, 5D.2 and 5E.1.
STAGE01_CAP4 = {
    "min_scaled_jacobian": 4.584e-03,
    "min_shape_metric": 3.716e-04,
    "worst_tip_corner_deg": 179.737,
    "cell_size_range": 153.0,
    "min_cell_edge_m": 650.6e-6,
    "min_cell_over_s0": 48.7,
}


def _measure(wing, blocks, info) -> dict:
    qc = qc_blocks(blocks)
    fid = verify.oml_fidelity(wing, blocks, info["te_thickness"])
    water = verify.watertight_tip(blocks)
    # Max over ALL tip blocks. Taking only the first one under-reported the
    # worst tip corner as 149.36 deg when it is 168.38 deg.
    tip_blocks = [b for b in blocks if b.name.startswith("tip")]
    passed, reasons = gates.surface_gate_checklist(
        qc, fid, info["orientation"], water["watertight_tip"], deterministic_connectivity=True
    )
    return {
        "blocks": qc["block_count"],
        "cells": qc["total_cells"],
        "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
        "min_shape_metric": qc["global"]["min_shape_metric"],
        "max_skewness": qc["global"]["max_equiangle_skewness"],
        "max_aspect_ratio": qc["global"]["max_aspect_ratio"],
        "cell_size_range": qc["cell_size_range"],
        "min_cell_edge_m": qc["min_cell_edge_m"],
        "min_cell_edge_block": qc["min_cell_edge_block"],
        "worst_tip_corner_deg": max(worst_corner_angle_deg(b.xyz) for b in tip_blocks),
        "watertight_tip": water["watertight_tip"],
        "fidelity_frac_of_chord": fid["worst_frac_of_local_chord"],
        "fidelity_unverified": fid["fidelity_unverified_for_refined_blocks"],
        "surface_gate": "PASS" if passed else "FAIL",
        "surface_gate_reasons": reasons,
        "spanwise_cells": info["spanwise"]["spanwise_cells"],
    }


def baseline() -> int:
    """Build S0 on the baseline geometry at every level, against Stage 01."""
    wing = geometry_sets.wing("epse_calibration_lhs10_seed7", 0)
    rows = []
    print(f"{'level':14s} {'blk':>3s} {'cells':>7s} {'minJac':>9s} {'shape':>9s} "
          f"{'range':>8s} {'tipCorner':>10s} {'skew':>6s} {'gate':>5s}")
    for level in S0.LEVELS:
        blocks, info = S0.build_surface(wing, level=level)
        m = _measure(wing, blocks, info)
        m["level"] = level
        rows.append(m)
        print(f"{level:14s} {m['blocks']:3d} {m['cells']:7d} {m['min_scaled_jacobian']:9.5f} "
              f"{m['min_shape_metric']:9.5f} {m['cell_size_range']:8.1f} "
              f"{m['worst_tip_corner_deg']:10.3f} {m['max_skewness']:6.3f} "
              f"{m['surface_gate']:>5s}")

    print("\nStage 01 cap4, at the SHIPPED defaults (wrap_x 0.03), for reference:")
    for k, v in STAGE01_CAP4.items():
        print(f"  {k:24s} {v}")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s0_baseline_levels.json").write_text(
        json.dumps(
            {
                "strategy_id": S0.STRATEGY_ID,
                "geometry": "epse_calibration_lhs10_seed7_000",
                "wrap_x": S0.WRAP_X,
                "stage01_cap4_shipped_defaults": STAGE01_CAP4,
                "levels": rows,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


def wrapx() -> int:
    """Sweep wrap_x — the knob ADR-0006's invariance probe never touched.

    That probe swept `split_x_fore` on `wing_cap4_v1`. cap4 does not read
    `split_x_fore` (surface.py line 776 passes `wrap_x=cap_wrap_x` for cap4;
    `split_x_fore` goes only to the mid4/split8 path), so all three variants were
    the same mesh — which is why they agreed to 11-12 significant figures.
    """
    wing = geometry_sets.wing("epse_calibration_lhs10_seed7", 0)
    rows = []
    print(f"{'wrap_x':>7s} {'minJac':>9s} {'shape':>9s} {'tipCorner':>10s} "
          f"{'range':>8s} {'skew':>6s} {'maxAR':>8s} {'cells':>7s}")
    for wx in (0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40):
        blocks, info = S0.build_surface(wing, level="L2_smoke", wrap_x=wx)
        m = _measure(wing, blocks, info)
        m["wrap_x"] = wx
        rows.append(m)
        print(f"{wx:7.2f} {m['min_scaled_jacobian']:9.5f} {m['min_shape_metric']:9.5f} "
              f"{m['worst_tip_corner_deg']:10.3f} {m['cell_size_range']:8.1f} "
              f"{m['max_skewness']:6.3f} {m['max_aspect_ratio']:8.1f} {m['cells']:7d}")

    best = max(rows, key=lambda r: r["min_scaled_jacobian"])
    print(f"\nbest min scaled Jacobian {best['min_scaled_jacobian']:.5f} at wrap_x "
          f"{best['wrap_x']}, versus Stage 01's {STAGE01_CAP4['min_scaled_jacobian']:.5f}")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s0_wrapx_sweep.json").write_text(
        json.dumps(
            {
                "strategy_id": S0.STRATEGY_ID,
                "level": "L2_smoke",
                "geometry": "epse_calibration_lhs10_seed7_000",
                "note": (
                    "ADR-0006 concluded cap4's tip corner was 'not tunable' from a "
                    "sweep of split_x_fore, which cap4 does not read. wrap_x is the "
                    "parameter that actually controls the corner location."
                ),
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


def refine(n: int = 8) -> int:
    """S0 on a subset of the development set `lhs100_seed42`."""
    rows = []
    per_geometry = {}
    print(f"{'geometry':10s} {'blk':>3s} {'cells':>7s} {'minJac':>9s} {'range':>8s} "
          f"{'tipCorner':>10s} {'water':>6s} {'gate':>5s}")
    for i in range(n):
        gid = geometry_sets.geometry_id("lhs100_seed42", i)
        wing = geometry_sets.wing("lhs100_seed42", i)
        blocks, info = S0.build_surface(wing, level="L2_smoke")
        m = _measure(wing, blocks, info)
        m["geometry"] = gid
        rows.append(m)
        per_geometry[gid] = verify.verify_geometry(wing, blocks, te_thickness=info["te_thickness"])
        print(f"{gid[-7:]:10s} {m['blocks']:3d} {m['cells']:7d} {m['min_scaled_jacobian']:9.5f} "
              f"{m['cell_size_range']:8.1f} {m['worst_tip_corner_deg']:10.3f} "
              f"{str(m['watertight_tip']):>6s} {m['surface_gate']:>5s}")

    det = verify.verify_set(per_geometry)
    worst = min(r["min_scaled_jacobian"] for r in rows)
    print(f"\ndeterministic connectivity : {det['deterministic_connectivity']} "
          f"({det['distinct_connectivity_signatures']} signature/s)")
    print(f"dimensions adapt           : {det['dimensions_adapt_to_geometry']} "
          f"({det['distinct_block_dimension_sets']} dimension set/s)")
    print(f"worst min scaled Jacobian  : {worst:.5f} across {len(rows)} geometries")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s0_refinement_set.json").write_text(
        json.dumps(
            {
                "strategy_id": S0.STRATEGY_ID,
                "set": "lhs100_seed42",
                "n": n,
                "level": "L2_smoke",
                "wrap_x": S0.WRAP_X,
                "determinism": det,
                "worst_min_scaled_jacobian": worst,
                "rows": rows,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if cmd == "baseline":
        raise SystemExit(baseline())
    if cmd == "wrapx":
        raise SystemExit(wrapx())
    if cmd == "refine":
        raise SystemExit(refine(int(sys.argv[2]) if len(sys.argv) > 2 else 8))
    raise SystemExit(f"unknown command {cmd!r}; use baseline | wrapx | refine")
