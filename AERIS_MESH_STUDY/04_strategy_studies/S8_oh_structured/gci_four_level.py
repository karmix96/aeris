#!/usr/bin/env python3
"""The grid-convergence study the cloud batch exists to produce.

    gci_four_level.py --index 83

Checklist item B5. `gci_C` and `gci_M` were solved on the development host on
17 September; `gci_F` and `gci_FF` come from rented compute. A four-level study
is the only thing that yields an OBSERVED order of convergence rather than an
assumed one, and on 17 September the difference between assuming p = 1 and p = 2
was 82 drag counts on a CD of 179.

Combining runs from two machines is where this goes wrong quietly, so the
compatibility check comes first and is strict. The external review of 16
September put it plainly: the inputs to a GCI must share geometry, incidence,
Mach, Reynolds, model variant, trailing-edge treatment, outer boundary,
discretisation and force references. Picking the three meshes with the most
cells is not a grid-convergence study.

Nothing here computes a number it is not entitled to. `gci.py` refuses a family
whose successive differences grow under refinement -- it once returned p = +2,
"ok" and a GCI of 37 % for f(h) = 1 + h^-2, which runs away to infinity -- and
`certified_uncertainty_percent` stays empty for any quantity whose family fails
a condition.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import gci  # noqa: E402

REPORTS = HERE / "reports"
#: Where each level's runs live. gci_C and gci_M were solved here; the cloud
#: writes gci_F and gci_FF into s8_hf. Both are searched so the analysis works
#: the same before and after the batch.
SEARCH = [HERE / "runs/s8_v2",
          HERE / "runs/s8_hf",
          HERE / "runs/s8_cloud"]
LEVELS = ["gci_C", "gci_M", "gci_F", "gci_FF"]          # coarse to fine

#: Quantities the study reports. CL and CMy pass through zero on these wings, so
#: a relative GCI on them is meaningless near alpha 0 and the absolute band is
#: what gets quoted -- the same near-zero trap that made "AVL within 2 %" look
#: false at low incidence.
QUANTITIES = {"cd": "drag", "cdp": "pressure drag", "cdv": "viscous drag",
              "cl": "lift", "cmy": "pitching moment"}
RELATIVE_IS_MEANINGLESS = {"cl", "cmy"}

#: Fields that must agree across levels before they may be combined.
MUST_MATCH = {
    "mission": ("mach", "reynolds", "reynolds_length_m", "temperature_K", "chord_ref_m"),
    "solver": ("equationType", "turbulenceModel", "turbulenceOrder", "useft2SA",
               "eddyVisInfRatio", "liftIndex", "MGCycle", "useNKSolver",
               "L2Convergence", "useWallFunctions", "useQCR"),
    "top": ("area_ref_m2", "alpha_deg"),
}


def find_run(index: int, level: str, alpha: float) -> Path | None:
    for root in SEARCH:
        for name in (f"{level}_a{alpha:g}", f"{level}_a{alpha:.1f}"):
            p = root / f"g{index}" / name
            if (p / "result.json").exists():
                return p
    return None


def cells_for(index: int, level: str) -> int | None:
    for root in SEARCH:
        s = root / f"g{index}" / f"{level}_summary.json"
        if s.exists():
            try:
                return int(json.loads(s.read_text())["cells"])
            except (ValueError, KeyError):
                pass
    return None


def solver_version(run: Path, index: int, level: str, alpha: float) -> str | None:
    """Which ADflow produced this run.

    `result.json` does not record it -- the version only reaches the dataset row,
    which is built later by the collector. That is a real gap for this analysis,
    because the most likely difference between a run solved here and one solved
    on a rented machine is the SOLVER, and a grid-convergence study across two
    ADflow versions is not a grid-convergence study. Looked for in three places,
    and its ABSENCE is reported rather than passed over.
    """
    manifest = run / "run_manifest.json"
    if manifest.exists():
        try:
            env = json.loads(manifest.read_text()).get("environment") or {}
            if env.get("solver_version"):
                return str(env["solver_version"])
        except ValueError:
            pass
    rows = HERE / "data/dataset_v2/rows.json"
    if rows.exists():
        try:
            for r in json.loads(rows.read_text()):
                # NOT `r.get("alpha_deg") or 1e9`. Zero is falsy, so alpha 0 --
                # the point every comparison is anchored on -- falls through to
                # the sentinel and never matches. That exact line is already in
                # this project's defect ledger from the AVL lookup, and it was
                # written again here. A guard that fails for precisely one value
                # is worse than one that fails for all of them, because nothing
                # looks wrong.
                row_alpha = r.get("alpha_deg")
                if (r.get("geometry_index") == index and r.get("grid_level") == level
                        and row_alpha is not None and abs(row_alpha - alpha) < 1e-9):
                    v = (r.get("environment") or {}).get("adflow_version")
                    if v:
                        return str(v)
        except ValueError:
            pass
    return None


def functions(result: dict) -> dict:
    """Strip the per-run prefix: `s8_a0_cd` is `cd`."""
    out = {}
    for key, value in (result.get("functions") or {}).items():
        short = key.rsplit("_", 1)[-1]
        out[short] = value
    return out


def compatibility(levels: dict) -> dict:
    """Are these runs the same case at different resolutions, or different cases?"""
    names = list(levels)
    reference = names[0]
    differences = []
    for group, fields in MUST_MATCH.items():
        for field in fields:
            def pull(n):
                r = levels[n]["result"]
                if group == "mission":
                    return (r.get("mission") or {}).get(field)
                if group == "solver":
                    return (r.get("solver_options_effective") or {}).get(field)
                return r.get(field)
            base = pull(reference)
            for n in names[1:]:
                here = pull(n)
                same = (base == here or
                        (isinstance(base, float) and isinstance(here, float)
                         and abs(base - here) <= 1e-9 * max(1.0, abs(base))))
                if not same:
                    differences.append({"field": f"{group}.{field}",
                                        reference: base, n: here})
    moment = [tuple(levels[n]["result"].get("moment_ref_xyz_m") or []) for n in names]
    if len(set(moment)) > 1:
        differences.append({"field": "moment_ref_xyz_m",
                            **{n: list(m) for n, m in zip(names, moment)}})

    versions = {n: levels[n].get("solver_version") for n in names}
    known = {n: v for n, v in versions.items() if v}
    unknown = [n for n, v in versions.items() if not v]
    if len(set(known.values())) > 1:
        differences.append({"field": "solver_version", **versions})
    unverifiable = ([f"solver version unknown for {', '.join(unknown)}: "
                     f"result.json does not record it, and no run_manifest.json or "
                     f"dataset row was found. These levels may have been solved by "
                     f"different ADflow builds and nothing here can tell."]
                    if unknown else [])
    return {"compatible": not differences, "differences": differences,
            "unverifiable": unverifiable,
            "solver_versions": versions,
            "levels_compared": names,
            "note": ("a grid-convergence study needs the SAME case at different "
                     "resolutions. Any difference here means these runs answer "
                     "different questions and must not be combined.")}


def analyse(index: int, alpha: float) -> dict:
    levels: dict = {}
    for level in LEVELS:
        run = find_run(index, level, alpha)
        if run is None:
            continue
        result = json.loads((run / "result.json").read_text())
        cells = cells_for(index, level)
        levels[level] = {"run": str(run), "result": result, "cells": cells,
                         "functions": functions(result),
                         "solver_version": solver_version(run, index, level, alpha)}

    out = {"geometry_index": index, "alpha_deg": alpha,
           "levels_present": list(levels),
           "levels_missing": [l for l in LEVELS if l not in levels],
           "cells": {l: levels[l]["cells"] for l in levels}}
    if len(levels) < 2:
        out["verdict"] = "nothing to compare: fewer than two levels on disk"
        return out

    out["compatibility"] = compatibility(levels)
    if not out["compatibility"]["compatible"]:
        out["verdict"] = ("levels are NOT the same case; refusing to combine them. "
                          "See compatibility.differences.")
        return out

    # coarse -> fine, so index 0 is the coarsest
    order = [l for l in LEVELS if l in levels]
    counts = [levels[l]["cells"] for l in order]
    if any(c is None for c in counts):
        out["verdict"] = "a level has no recorded cell count; cannot form a refinement ratio"
        return out

    #: TWO honest ratios, and the error model gets the GLOBAL one.
    #:
    #: Near the wall (`o_wing`) the node arrays refine at 1.300 in every direction
    #: at every step. Globally they do not: `o_out` and `cap_out` are geometric
    #: extrusions crossing a fixed distance, so their layer count grows
    #: logarithmically and the domain refines at about 1.25.
    #:
    #: ASME V&V 20 and Celik define r on the REPRESENTATIVE cell size,
    #: h = (1/N * sum dV_i)^(1/3), which is a whole-domain quantity -- so the
    #: cell-count cube root is the ratio the procedure asks for, and the local
    #: near-wall spacing ratio is not a substitute for it.
    #:
    #: This function used to pass 1.300 into the band. That is the one substitution
    #: which makes the reported uncertainty SMALLER: on g83 at alpha 0 it shrinks
    #: the two-level CD band from 47.8 % to 38.6 %. `AUDIT_2026-09-05.md` had
    #: already settled the question -- "Claiming r = 1.300 while the domain refines
    #: at 1.25 would err the other way" -- and `PLAN_desktop_campaign.md` 2.2 says
    #: plainly: `gci.py` takes the ratios from the cell counts, do not pass 1.300.
    #: Restored 2026-09-20 by the reliability audit, with the alternative kept on
    #: the record so the choice stays visible instead of buried in a note.
    ratios = [(counts[i + 1] / counts[i]) ** (1 / 3) for i in range(len(counts) - 1)]
    out["refinement_ratio_from_cells"] = [round(r, 4) for r in ratios]
    out["refinement_ratio_measured_spacing"] = 1.300
    out["refinement_ratio_used"] = round(sum(ratios) / len(ratios), 4)
    out["ratio_note"] = (
        "The band below uses the GLOBAL ratio from the cell counts, which is the "
        "quantity ASME V&V 20 / Celik define r on (the representative cell size "
        "over the whole domain). The near-wall node arrays do refine at 1.300, but "
        "o_out and cap_out are geometric extrusions crossing a fixed distance, so "
        "the domain refines more slowly and the global ratio is smaller. A smaller "
        "ratio WIDENS the band: that is the conservative direction, and it is why "
        "the procedure asks for this quantity rather than the local one. Passing "
        "1.300 here understates the uncertainty. See "
        "`refinement_ratio_measured_spacing` for the near-wall value.")
    out["asme_r_requirement"] = {
        "required": 1.3,
        "global_r_per_step": [round(x, 4) for x in ratios],
        "met": bool(min(ratios) >= 1.3),
        "note": ("Celik's r >= 1.3 is a requirement on the global ratio. This family "
                 "does not meet it and cannot be said to, whatever the near-wall "
                 "spacing does.")}

    r = out["refinement_ratio_used"]
    results: dict = {}
    for q, label in QUANTITIES.items():
        values = [levels[l]["functions"].get(q) for l in order]
        if any(v is None for v in values):
            results[q] = {"label": label, "skipped": "not reported at every level"}
            continue
        entry: dict = {"label": label,
                       "by_level": {l: v for l, v in zip(order, values)},
                       "counts_by_level": {l: round(1e4 * v, 3) for l, v in zip(order, values)}
                       if q.startswith("cd") else None}
        triplets = {}
        for i in range(len(order) - 2):
            trio = order[i:i + 3]                      # coarse, medium, fine
            f3, f2, f1 = values[i], values[i + 1], values[i + 2]
            t = gci.gci_triplet(f1, f2, f3, r, r)
            if q in RELATIVE_IS_MEANINGLESS:
                t["relative_gci_suppressed"] = (
                    "this quantity passes through zero on these wings, so a percentage "
                    "is not usable; read the absolute band")
                t["absolute_band"] = abs(t.get("gci_21", float("nan")) * f1)
            triplets["/".join(x.replace("gci_", "") for x in trio)] = t
        entry["triplets"] = triplets
        if len(triplets) >= 2:
            orders = [t.get("p_observed") for t in triplets.values()
                      if t.get("condition") == "ok"]
            entry["triplet_consistency"] = {
                "observed_orders": orders,
                "spread": (round(max(orders) - min(orders), 3) if len(orders) > 1 else None),
                "consistent": (len(orders) > 1 and max(orders) - min(orders) <= 0.5),
                "note": ("two triplets of the same family should give the same observed "
                         "order. If they do not, the solutions are not in the asymptotic "
                         "range and no extrapolated value is quotable, whatever the "
                         "formula returns.")}
        elif len(levels) == 2:
            entry["two_level_only"] = gci.trend_pair(values[1], values[0], r)
        results[q] = entry
    out["quantities"] = results
    out["verdict"] = (f"{len(levels)} levels present. "
                      + ("Observed order available." if len(levels) >= 3 else
                         "TWO LEVELS ONLY: the order is assumed, not observed. "
                         "This is a trend, not a GCI."))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", type=int, default=83)
    ap.add_argument("--alphas", type=float, nargs="+", default=[-2.0, 0.0, 4.0, 8.0])
    args = ap.parse_args()

    report = {"schema": "aeris.s8.gci_four_level.v1", "geometry_index": args.index,
              "by_alpha": {}}
    for alpha in args.alphas:
        a = analyse(args.index, alpha)
        report["by_alpha"][f"{alpha:g}"] = a
        print(f"\n  alpha {alpha:g}: {', '.join(a['levels_present'])}"
              f"  (missing: {', '.join(a['levels_missing']) or 'none'})")
        print(f"    {a['verdict']}")
        if a.get("compatibility") and not a["compatibility"]["compatible"]:
            for d in a["compatibility"]["differences"][:5]:
                print(f"      INCOMPATIBLE {d}")
            continue
        for q, e in (a.get("quantities") or {}).items():
            if e.get("skipped"):
                continue
            if e.get("triplets"):
                for name, t in e["triplets"].items():
                    p = t.get("p_observed")
                    print(f"      {q:4s} {name:12s} p={p if p is None else round(p,3)}  "
                          f"{t['condition'][:56]}")
            elif e.get("two_level_only"):
                t = e["two_level_only"]
                print(f"      {q:4s} two levels: {t['condition'][:60]}")
    path = REPORTS / f"s8_gci_four_level_g{args.index}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
