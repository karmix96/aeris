#!/usr/bin/env python3
"""Size the high-fidelity batch from MEASURED data, not from the 2026-09-09 estimates.

Everything the old `s8_cloud_batch.json` asserted has now been measured:

  cells      built here on 2026-09-18, not estimated from a level definition
  memory     the ANK-only law fitted on this host, applied to the real counts
  time       a two-factor model fitted to 52 solves run on 2026-09-17, which
             separates the cost of a cell from the number of iterations --
             the old single number did neither
  ranks      chosen from the measured rank probe, where 4 ranks costs 32 %
             fewer core-hours than 6 for 3 % more wall time

The output is core-hours, which is hardware-independent. Money is core-hours
times a rate you confirm at purchase time; the rate is NOT asserted here.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPORTS = HERE / "reports"
INDICES = [12, 13, 16, 23, 29, 36, 47, 65, 81, 83]
ALPHAS = [-2.0, 0.0, 4.0, 8.0]

# ---- measured on 2026-09-17, 52 solves, 6 ranks, this host -------------------
# The useful decomposition: cost per (million cells x iteration) is FLAT across
# the two levels -- 9.44 s at gci_C, 9.97 s at gci_M, a 6 % spread -- so a cell
# costs what a cell costs and the superlinearity is entirely iteration COUNT,
# which rose 203 -> 262 (x1.29) from C to M.
SEC_PER_MCELL_ITER_6RANK = 9.7
ITERS = {"gci_C": 203, "gci_M": 262}
ITER_GROWTH_PER_LEVEL = 262 / 203          # 1.29, measured once, extrapolated
ITER_GROWTH_RANGE = (1.00, 1.50)           # flat, and half again as steep

# ---- measured rank probe [R38] ----------------------------------------------
# core-hours relative to 6 ranks, and wall time relative to 6 ranks
RANKS = {1: (0.427, 2.565), 2: (0.452, 1.355), 4: (0.684, 1.027), 6: (1.000, 1.000)}
CHOSEN_RANKS = 4

MEM_A, MEM_B, MEM_MARGIN = 2.69, 7.23, 1.05   # GiB = (a + b*Mcells) * margin


def iterations(level: str, lo_hi: str = "mid") -> float:
    steps = {"gci_F": 1, "gci_FF": 2}[level]
    g = {"lo": ITER_GROWTH_RANGE[0], "mid": ITER_GROWTH_PER_LEVEL,
         "hi": ITER_GROWTH_RANGE[1]}[lo_hi]
    return ITERS["gci_M"] * g ** steps


def solve_minutes(cells: int, level: str, ranks: int, band: str) -> float:
    at6 = cells / 1e6 * iterations(level, band) * SEC_PER_MCELL_ITER_6RANK / 60.0
    return at6 * RANKS[ranks][1]


def core_hours(cells: int, level: str, ranks: int, band: str) -> float:
    at6 = cells / 1e6 * iterations(level, band) * SEC_PER_MCELL_ITER_6RANK / 3600.0 * 6
    return at6 * RANKS[ranks][0]


def main() -> int:
    meshes = json.loads((REPORTS / "s8_cloud_meshes.json").read_text())["meshes"]
    by = {(m["level"], m["index"]): m for m in meshes if m.get("clean")}
    if len(by) != 11:
        raise SystemExit(f"only {len(by)} clean meshes; build them before sizing the batch")

    cases, totals = [], {b: 0.0 for b in ("lo", "mid", "hi")}
    for level, idx_list in (("gci_F", INDICES), ("gci_FF", [83])):
        for index in idx_list:
            m = by[(level, index)]
            for alpha in ALPHAS:
                c = {"index": index, "level": level, "alpha_deg": alpha,
                     "cells": m["cells"],
                     "memory_gib": m["solve_gib_ank_only"],
                     "ranks": CHOSEN_RANKS,
                     "predicted_minutes": round(
                         solve_minutes(m["cells"], level, CHOSEN_RANKS, "mid"), 1),
                     "predicted_core_hours": round(
                         core_hours(m["cells"], level, CHOSEN_RANKS, "mid"), 2)}
                cases.append(c)
                for b in totals:
                    totals[b] += core_hours(m["cells"], level, CHOSEN_RANKS, b)

    per_level = {}
    for level in ("gci_F", "gci_FF"):
        sel = [c for c in cases if c["level"] == level]
        per_level[level] = {
            "cases": len(sel),
            "cells_each": sorted({c["cells"] for c in sel}),
            "memory_gib_each": sorted({c["memory_gib"] for c in sel}),
            "minutes_each_at_%d_ranks" % CHOSEN_RANKS: round(
                sum(c["predicted_minutes"] for c in sel) / len(sel), 1),
            "core_hours_total": round(sum(c["predicted_core_hours"] for c in sel), 1)}

    out = {
        "schema": "aeris.s8.cloud_batch.v2",
        "supersedes": "reports/s8_cloud_batch.json (2026-09-09, all figures estimated)",
        "ranks_per_case": CHOSEN_RANKS,
        "why_these_ranks": (
            "The measured probe gives 2121/1121/849/827 s at 1/2/4/6 ranks. Four "
            "ranks is 2.7 % slower than six and costs 32 % fewer core-hours. Six "
            "ranks was chosen for the development host to finish one case sooner; "
            "the cloud runs 44 INDEPENDENT cases, so throughput is what is being "
            "bought and latency per case is nearly irrelevant."),
        "timing_model": {
            "form": "minutes = Mcells * iterations * 9.7 s / 60, then scaled by the rank probe",
            "sec_per_mcell_iteration_6rank": SEC_PER_MCELL_ITER_6RANK,
            "fitted_on": "52 solves, 2026-09-17: gci_C 9.44, gci_M 9.97 s per Mcell-iteration",
            "iterations_assumed": {lv: round(iterations(lv), 0) for lv in ("gci_F", "gci_FF")},
            "iteration_growth_per_level": round(ITER_GROWTH_PER_LEVEL, 3),
            "WEAKEST_LINK": (
                "Iteration growth is ONE measured ratio (203 -> 262, C to M) "
                "extrapolated two levels. The lo/hi band brackets it at flat and "
                "x1.5 per level. This is the dominant uncertainty in the bill."),
        },
        "memory_law": {
            "ank_only_gib": f"({MEM_A} + {MEM_B} * Mcells) * {MEM_MARGIN}",
            "WEAKEST_LINK": (
                "A two-point fit, extrapolated to 4x its largest input. Measure "
                "peak RSS on the pilot case before launching the other 42."),
        },
        "core_hours": {
            "low": round(totals["lo"], 0), "central": round(totals["mid"], 0),
            "high": round(totals["hi"], 0),
            "with_20pct_retry_margin": round(totals["mid"] * 1.2, 0),
            "note": "multiply by your confirmed $/core-hour; no rate is asserted here",
        },
        "per_level": per_level,
        "cases": cases,
    }
    path = REPORTS / "s8_cloud_batch_v2.json"
    path.write_text(json.dumps(out, indent=2) + "\n")

    print(f"  {len(cases)} cases at {CHOSEN_RANKS} ranks each\n")
    for lv, d in per_level.items():
        print(f"  {lv:7s} {d['cases']:2d} cases  {d['cells_each'][0]:,}-{d['cells_each'][-1]:,} cells  "
              f"{d['memory_gib_each'][0]}-{d['memory_gib_each'][-1]} GiB  "
              f"{d['minutes_each_at_%d_ranks' % CHOSEN_RANKS]:.0f} min each  "
              f"{d['core_hours_total']:.0f} core-h")
    print(f"\n  core-hours  low {totals['lo']:.0f}  central {totals['mid']:.0f}  "
          f"high {totals['hi']:.0f}   (+20 % retry: {totals['mid']*1.2:.0f})")
    print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
