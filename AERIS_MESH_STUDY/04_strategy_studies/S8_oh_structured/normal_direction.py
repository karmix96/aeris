#!/usr/bin/env python3
"""The wall-normal direction, on both mesh families, judged by gci.py.

    python3 normal_direction.py

Refining only the wall-normal direction -- layers and first cell together at 1.3
and 1.3 squared, every other count held -- is the one direction in this study that
made drag WORSE under refinement, and faster each step. On family A:

    CD 208.237 -> 209.134 -> 213.330 counts, the second step 4.7x the first

`gci.py` returns p = -5.97 and refuses to certify: the family has no demonstrated
limit. That matters far beyond the direction itself, because Richardson
extrapolation and the GCI both assume an asymptotic range, and a GLOBAL refinement
refines this direction along with the others. A third grid level bought while this
stands is a third point on a family that may have nothing to extrapolate to.

But family A carries the tip cap declared defective on 13 September and since
rebuilt, and the production dataset is family B. So the result is attached to a
mesh the campaign abandoned. This re-measures it on family B, where the cap fix
also changed the outboard extrusion from 48 to 54 layers -- the region the
divergence signature (CDp rising while CDv falls) actually points at.

Written 2026-09-21 by the reliability audit follow-up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gci  # noqa: E402

REPORTS = HERE / "reports"

#: coarse -> fine. Each entry: label, run directory, mesh summary.
FAMILIES = {
    "A (tip cap 10.2 x s0, pre-fix)": [
        ("gci_C", HERE / "runs/s8_cfd/gci_C_a0", HERE / "runs/s8_gci83/gci_C_summary.json"),
        ("gci_C_normal_s0", HERE / "runs/s8_checklist/dir_normal_s0/gci_C_normal_s0_a0",
         HERE / "runs/s8_checklist/dir_normal_s0/gci_C_normal_s0_summary.json"),
        ("gci_C_normal_s0_2", HERE / "runs/s8_checklist/dir_normal_s0_2/gci_C_normal_s0_2_a0",
         HERE / "runs/s8_checklist/dir_normal_s0_2/gci_C_normal_s0_2_summary.json"),
    ],
    "B (tip cap 2.04 x s0, rebuilt)": [
        ("gci_C", HERE / "runs/s8_v2/g83/gci_C_a0", HERE / "runs/s8_v2/g83/gci_C_summary.json"),
        ("gci_C_normal_s0_b", HERE / "runs/s8_normalB/gci_C_normal_s0_b_a0",
         HERE / "runs/s8_normalB/gci_C_normal_s0_b_summary.json"),
        ("gci_C_normal_s0_2_b", HERE / "runs/s8_normalB/gci_C_normal_s0_2_b_a0",
         HERE / "runs/s8_normalB/gci_C_normal_s0_2_b_summary.json"),
    ],
}
QUANTITIES = ("cd", "cdp", "cdv")

#: The wall-normal node ratios the family is built on. Taken from the level
#: definitions rather than from the cell counts: this is a DIRECTIONAL family, so
#: the global cell-count ratio (~1.09) describes nothing that was refined, while
#: 1.3 is the ratio actually applied to the layers and the first cell. Recorded
#: explicitly because the choice of r is exactly what the 2026-09-20 audit found
#: being made silently elsewhere.
R21 = 109 / 84
R32 = 84 / 65


def forces(run: Path) -> dict | None:
    p = run / "result.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    f = r["functions"]
    out = {q: next(v for k, v in f.items() if k.endswith("_" + q)) for q in QUANTITIES}
    out["converged"] = r.get("converged")
    out["s0_frac_note"] = r.get("grid", "")
    return out


def cells(summary: Path) -> int | None:
    if not summary.exists():
        return None
    return int(json.loads(summary.read_text())["cells"])


def cap(summary: Path) -> float | None:
    if not summary.exists():
        return None
    return json.loads(summary.read_text())["outboard"]["first_cell_in_s0"]


def main() -> int:
    report = {
        "schema": "aeris.s8.normal_direction.v1",
        "question": ("the wall-normal direction diverged on family A. Does it still "
                     "diverge on family B, the meshes the production dataset uses?"),
        "why_it_matters": ("a global refinement refines this direction too, so a third "
                          "grid level cannot be read while any direction has no "
                          "demonstrated limit."),
        "refinement_ratios": {"r21": round(R21, 4), "r32": round(R32, 4),
                              "measured_on": "wall-normal layer count and first cell",
                              "note": ("a DIRECTIONAL family: the global cell-count ratio "
                                       "describes nothing that was refined here.")},
        "families": {},
    }

    for family, levels in FAMILIES.items():
        rows, missing = [], []
        for name, run, summary in levels:
            f = forces(run)
            if f is None:
                missing.append(str(run.relative_to(HERE)))
                continue
            rows.append({"level": name, "cells": cells(summary),
                         "tip_cap_first_cell_in_s0": (round(cap(summary), 3)
                                                      if cap(summary) else None),
                         "converged": f["converged"],
                         **{q: round(1e4 * f[q], 3) for q in QUANTITIES}})
        entry = {"levels": rows, "missing": missing}

        if len(rows) == 3:
            # WITH A TOLERANCE. The cap's first cell is a measured spacing, not a
            # setting: the same `tip_span_first_cell_in_s0` gives 10.205, 10.204 and
            # 10.203 across three levels because s0 itself changes. Comparing them
            # exactly reported a consistent family as mixed. The question is whether
            # one level was built at 2 while the others were built at 10, and 5 %
            # separates those by a factor of five.
            caps = [r["tip_cap_first_cell_in_s0"] for r in rows
                    if r["tip_cap_first_cell_in_s0"] is not None]
            entry["caps"] = sorted(caps)
            entry["cap_consistent"] = bool(caps) and (max(caps) - min(caps)) <= 0.05 * min(caps)
            if not entry["cap_consistent"]:
                entry["warning"] = ("the three levels do NOT share a tip cap, so any order "
                                    "below mixes the cap change into the normal direction")
            entry["verdicts"] = {}
            for q in QUANTITIES:
                f3, f2, f1 = (rows[0][q] * 1e-4, rows[1][q] * 1e-4, rows[2][q] * 1e-4)
                t = gci.gci_triplet(f1, f2, f3, R21, R32)
                entry["verdicts"][q] = {
                    "steps_counts": [round(rows[1][q] - rows[0][q], 3),
                                     round(rows[2][q] - rows[1][q], 3)],
                    "p_observed": (round(t["p_observed"], 4)
                                   if t.get("p_observed") is not None else None),
                    "condition": t.get("condition"),
                    "divergent": str(t.get("condition", "")).startswith("DIVERGENT"),
                    "gci_21_percent": (round(t["gci_21_percent"], 4)
                                       if t.get("gci_21_percent") is not None else None),
                    "certified_uncertainty_percent": t.get("certified_uncertainty_percent"),
                    "extrapolated_counts": (round(1e4 * t["f_extrapolated"], 3)
                                            if t.get("f_extrapolated") else None),
                }
        report["families"][family] = entry

    a = report["families"].get("A (tip cap 10.2 x s0, pre-fix)", {}).get("verdicts")
    b = report["families"].get("B (tip cap 2.04 x s0, rebuilt)", {}).get("verdicts")
    if a and b:
        report["comparison"] = {
            q: {"family_A_divergent": a[q]["divergent"],
                "family_B_divergent": b[q]["divergent"],
                "family_A_steps": a[q]["steps_counts"],
                "family_B_steps": b[q]["steps_counts"]}
            for q in QUANTITIES}
        still = [q for q in QUANTITIES if b[q]["divergent"]]
        report["gate"] = {
            "third_level_readable": not still,
            "divergent_quantities_on_family_B": still,
            "verdict": ("CLEAR: no quantity diverges in the wall-normal direction on the "
                        "production mesh family. A third global level can be read, and the "
                        "cloud pilot is justified."
                        if not still else
                        f"NOT CLEAR: {', '.join(still)} still diverge(s) on family B. A global "
                        f"refinement refines this direction too, so a third level cannot be "
                        f"read until the cause is localised. Do not rent hardware yet."),
        }

    out = REPORTS / "s8_normal_direction.json"
    out.write_text(json.dumps(report, indent=2) + "\n")

    for family, entry in report["families"].items():
        print(f"\n  FAMILY {family}")
        if entry["missing"]:
            print(f"    incomplete -- missing {', '.join(entry['missing'])}")
            continue
        print(f"    {'level':<24}{'cells':>10}{'cap':>7}{'CD':>10}{'CDp':>10}{'CDv':>10}")
        for r in entry["levels"]:
            print(f"    {r['level']:<24}{r['cells']:>10}{r['tip_cap_first_cell_in_s0']:>7}"
                  f"{r['cd']:>10.3f}{r['cdp']:>10.3f}{r['cdv']:>10.3f}")
        if not entry.get("cap_consistent", True):
            print(f"    WARNING: {entry['warning']}")
        for q, v in entry["verdicts"].items():
            mark = "DIVERGENT" if v["divergent"] else "ok"
            print(f"      {q:<4} steps {v['steps_counts'][0]:+8.3f} {v['steps_counts'][1]:+8.3f}"
                  f"   p={v['p_observed']}   {mark}")

    if "gate" in report:
        print(f"\n  GATE: {report['gate']['verdict']}")
    print(f"\nwrote {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
