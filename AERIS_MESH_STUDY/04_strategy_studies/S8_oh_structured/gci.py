#!/usr/bin/env python
"""Grid-convergence index, by the ASME procedure, for UNEQUAL refinement ratios.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/gci.py \
        --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a0' --out report.json

Why this is a script and not three lines in a document.

An earlier draft of the desktop plan gave the observed order as

    p = ln|(f3 - f2) / (f2 - f1)| / ln(r21)

which is only valid when the refinement ratios are equal.  This family's are
not -- they come out of the cell counts and land near 1.24 to 1.26, differing by
about one per cent -- and using the simple form would have produced a wrong p,
a wrong extrapolation and a wrong uncertainty band after hours of solver time.
The generalised relation has to be solved for p, not evaluated.

Celik, Ghia, Roache, Freitas, Coleman and Raad (2008), "Procedure for Estimation
and Reporting of Uncertainty Due to Discretization in CFD Applications",
J. Fluids Eng. 130(7).  With grids ordered 1 = FINEST:

    r21 = h2/h1,  r32 = h3/h2,  h_i = (V/N_i)^(1/3)
    e21 = f2 - f1,  e32 = f3 - f2,  s = sign(e32/e21)

    p = |ln|e32/e21| + q(p)| / ln(r21),   q(p) = ln((r21^p - s)/(r32^p - s))

solved by fixed-point iteration, then

    f_ext  = (r21^p * f1 - f2) / (r21^p - 1)
    GCI21  = 1.25 * |(f1 - f2)/f1| / (r21^p - 1)

`s` matters: s = -1 signals oscillatory convergence, and the procedure reports
it rather than hiding it.

What this refuses to do
-----------------------
* include a run whose gate verdict is not ACCEPTED.  A solver that stopped
  taking steps gives no bound on iterative error, and a GCI is meaningless
  unless iterative error is far below discretization error.
* report a GCI when the three values are not monotonic, or when p is
  non-physical.  It reports the condition instead.
* produce anything at all from two grid levels, unless --two-level-trend is
  passed, which produces a TREND and says so in every line of its output.

Two levels
----------
`--two-level-trend` exists because a host may not hold the third level:
PLAN_desktop_campaign.md 2.1 anticipates exactly this and instructs that the
result be reported as "a trend, not a GCI. Say so."

Two points give the DIRECTION and the MAGNITUDE of the movement between two
grids.  They do not give an observed order of accuracy, because p is what the
third point measures; without p there is no Richardson extrapolation and no
GCI band.

An assumed-order band is offered alongside, and it is an ASSUMPTION rather than
a measurement.  Roache's own guidance for the two-grid case is to assume the
formal order and raise the safety factor from 1.25 to 3.0, precisely because
the order is no longer being checked.  It is reported under a name that cannot
be mistaken for a GCI, with the assumed p attached to it, and PLAN 3.4 is the
warning that goes with it: "Do not expect p ~ 2. RANS on stretched grids
frequently gives observed orders below the nominal spatial order."  If the true
order is below the assumed one, the band is optimistic -- and nothing in a
two-level study can tell you whether it is.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
from pathlib import Path

FUNCTIONS = ("cl", "cd", "cdp", "cdv", "cmy")


def solve_order(e21: float, e32: float, r21: float, r32: float,
                tol: float = 1e-12, itmax: int = 500) -> tuple[float, int, str]:
    """Observed order p from the generalised relation, by fixed-point iteration."""
    ratio = e32 / e21
    s = 1.0 if ratio > 0 else -1.0
    p = math.log(abs(ratio)) / math.log(r21) if r21 > 1 else 2.0
    p = max(abs(p), 0.1)
    for i in range(itmax):
        try:
            q = math.log((r21 ** p - s) / (r32 ** p - s))
        except (ValueError, ZeroDivisionError):
            return float("nan"), i, "q(p) undefined; r^p reached the branch point"
        new = abs(math.log(abs(ratio)) + q) / math.log(r21)
        if not math.isfinite(new):
            return float("nan"), i, "iteration diverged"
        if abs(new - p) < tol:
            return new, i, "converged"
        p = new
    return p, itmax, "did not converge in itmax iterations"


def gci_triplet(f1: float, f2: float, f3: float,
                r21: float, r32: float) -> dict:
    """f1 is the FINEST."""
    e21, e32 = f2 - f1, f3 - f2
    out: dict = {"f1_fine": f1, "f2_medium": f2, "f3_coarse": f3,
                 "r21": r21, "r32": r32, "e21": e21, "e32": e32}
    if e21 == 0.0:
        out["condition"] = "the two finest values are identical; p is undefined"
        return out
    ratio = e32 / e21
    out["sign"] = 1 if ratio > 0 else -1
    out["monotonic"] = bool(ratio > 0)
    p, iters, status = solve_order(e21, e32, r21, r32)
    out.update({"p_observed": p, "p_iterations": iters, "p_status": status})
    if not math.isfinite(p) or p <= 0:
        out["condition"] = f"observed order is non-physical ({p}); not in the asymptotic range"
        return out
    denom = r21 ** p - 1.0
    out["f_extrapolated"] = (r21 ** p * f1 - f2) / denom
    ea21 = abs((f1 - f2) / f1) if f1 != 0 else float("nan")
    out["approx_relative_error_21"] = ea21
    out["gci_21"] = 1.25 * ea21 / denom
    out["gci_21_percent"] = 100.0 * out["gci_21"]
    if f1 != 0:
        out["extrapolated_relative_error"] = abs((out["f_extrapolated"] - f1) / f1)
    # Defect 28. Celik's order formula takes the absolute value of the log
    # ratio, so it returns a POSITIVE p for a sequence that is running away.
    # Fed f(h) = 1 + h^-2 at h = 1, 1.3, 1.69 -- a family with no finite limit,
    # whose value goes to infinity as the grid refines -- this routine returned
    # p = +2, condition "ok" and a GCI of 36.98 %. An external review found it
    # with that exact counterexample on 2026-09-16.
    #
    # Monotonicity does not catch it: both successive differences have the same
    # sign, so e32/e21 > 0. The test that does catch it is whether the
    # differences SHRINK as the grid refines. The error model f = f0 + C h^p
    # with p > 0 and r > 1 predicts |e21| / |e32| = r^-p < 1. A family where the
    # fine-pair difference is the LARGER one is not approaching anything, and
    # no safety factor rescues a band computed around a limit that does not
    # exist.
    out["difference_ratio"] = abs(e21) / abs(e32) if e32 != 0 else float("inf")
    converging = out["difference_ratio"] < 1.0
    out["differences_shrink_under_refinement"] = bool(converging)
    if not out["monotonic"]:
        out["condition"] = ("OSCILLATORY: e32/e21 is negative, so the three values do "
                            "not converge monotonically. The GCI below is reported but "
                            "the asymptotic assumption is not demonstrated.")
    elif not converging:
        out["condition"] = (
            f"DIVERGENT: |f1-f2| = {abs(e21):.6g} is not smaller than "
            f"|f2-f3| = {abs(e32):.6g}, so refining the grid is moving the answer "
            f"FURTHER, not less far. This family has no demonstrated limit and the "
            f"order formula's absolute value hides the sign. No GCI.")
    elif not (0.5 <= p <= 4.0):
        out["condition"] = (f"observed order {p:.3f} is outside a plausible range for a "
                            f"second-order scheme; treat as not in the asymptotic range")
    else:
        out["condition"] = "ok"

    # The band is a DIAGNOSTIC on any family. It is a certified numerical
    # uncertainty only on one that passed every condition above, and that
    # distinction is structural here rather than left to whoever reads the
    # number: an unacceptable family leaves the field empty.
    out["certified_uncertainty_percent"] = (
        out["gci_21_percent"] if out["condition"] == "ok" else None)
    return out


#: Roache's safety factor for a TWO-grid comparison, where the order is assumed
#: rather than observed.  1.25 is for three grids with a measured p; 3.0 is the
#: price of not measuring it.
TWO_LEVEL_SAFETY_FACTOR = 3.0


def trend_pair(f1: float, f2: float, r21: float,
               assumed_p: float = 2.0) -> dict:
    """Movement between two grids.  f1 is the FINER.  Not a GCI."""
    out: dict = {
        "f1_fine": f1, "f2_coarse": f2, "r21": r21,
        "change_fine_minus_coarse": f1 - f2,
        "relative_change": abs((f1 - f2) / f1) if f1 != 0 else float("nan"),
        "p_observed": None,
        "p_observed_why_absent": ("the observed order is what the THIRD grid "
                                  "measures; two points cannot separate the order "
                                  "from the coefficient"),
        "f_extrapolated": None,
        "gci_21": None,
        "gci_21_why_absent": ("a GCI band requires an observed order. This is a "
                              "refinement trend, not a grid-convergence index."),
    }
    denom = r21 ** assumed_p - 1.0
    ea21 = abs((f1 - f2) / f1) if f1 != 0 else float("nan")
    out["assumed_order_band"] = {
        "assumed_p": assumed_p,
        "safety_factor": TWO_LEVEL_SAFETY_FACTOR,
        "band": TWO_LEVEL_SAFETY_FACTOR * ea21 / denom,
        "band_percent": 100.0 * TWO_LEVEL_SAFETY_FACTOR * ea21 / denom,
        "extrapolated_if_p_assumed": (r21 ** assumed_p * f1 - f2) / denom,
        "what_this_is": (f"an ASSUMPTION, not a measurement: p was set to "
                         f"{assumed_p}, not observed, and the safety factor raised "
                         f"from 1.25 to {TWO_LEVEL_SAFETY_FACTOR} because of that. "
                         f"If the true order is lower -- which PLAN 3.4 warns is "
                         f"common for RANS on stretched grids -- this band is "
                         f"optimistic, and no two-level study can tell you whether "
                         f"it is. Do not report it as a GCI."),
    }
    out["condition"] = "TREND_ONLY: two levels. No observed order, no GCI band."
    return out


def load(directory: Path) -> dict | None:
    result = directory / "result.json"
    if not result.exists():
        return None
    d = json.loads(result.read_text())
    short = {}
    for key, value in d.get("functions", {}).items():
        for name in FUNCTIONS:
            if key.endswith("_" + name):
                short[name] = float(value)
    d["short"] = short
    return d


def report_trend(kept: list[dict], args) -> int:
    """PLAN 2.1's third branch, made explicit in every line of the output."""
    f, c = kept[0], kept[1]
    r21 = (f["cells"] / c["cells"]) ** (1.0 / 3.0)

    banner = "=" * 78
    print(f"\n{banner}\nREFINEMENT TREND -- NOT A GRID-CONVERGENCE INDEX\n{banner}")
    print("Two grid levels. Two points give the direction and the size of the")
    print("movement between them. They do NOT give an observed order of accuracy,")
    print("a Richardson extrapolation, or an uncertainty band: all three need a")
    print("third level. PLAN 2.1: \"That is a trend, not a GCI. Say so.\"\n")
    for tag, r in (("fine", f), ("coarse", c)):
        print(f"  {tag:>7}  {r['level']:<9} {r['cells']:>10,} cells")
    print(f"\n  r21 = {r21:.4f}   (from the cell counts, not assumed)")

    report = {"study": "TREND_NOT_GCI", "plan_section": "2.1",
              "statement": ("Two grid levels. A refinement trend, not a "
                            "grid-convergence index. No observed order, no "
                            "Richardson extrapolation, no uncertainty band."),
              "grids": [{"level": r["level"], "cells": r["cells"], "dir": r["dir"]}
                        for r in (f, c)],
              "r21": r21, "assumed_order": args.assumed_order, "functions": {}}

    print(f"\n{'':>6}{'fine':>12}{'coarse':>12}{'change':>12}{'change %':>11}"
          f"{'assumed band %':>16}")
    for name in FUNCTIONS:
        if not all(name in r["short"] for r in (f, c)):
            continue
        g = trend_pair(f["short"][name], c["short"][name], r21, args.assumed_order)
        report["functions"][name] = g
        print(f"{name:>6}{g['f1_fine']:>12.6f}{g['f2_coarse']:>12.6f}"
              f"{g['change_fine_minus_coarse']:>+12.6f}"
              f"{100 * g['relative_change']:>11.2f}"
              f"{g['assumed_order_band']['band_percent']:>16.2f}")

    print(f"\n  The last column assumes p = {args.assumed_order} and applies a safety")
    print(f"  factor of {TWO_LEVEL_SAFETY_FACTOR} instead of 1.25, because the order was NOT measured.")
    print("  It is an assumption. PLAN 3.4: \"Do not expect p ~ 2. RANS on stretched")
    print("  grids frequently gives observed orders below the nominal spatial order.\"")
    print("  If the true order is lower, that band is optimistic, and no two-level")
    print("  study can tell you whether it is.\n")
    print("  What would close this: a third level. On this host that means a")
    print("  different machine -- see reports/s8_level_selection.json.")

    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", nargs="+", required=True,
                    help="glob(s) for the run directories, one per grid level")
    ap.add_argument("--cells", type=json.loads, default=None,
                    help='{"gci_C": 567256, ...} cell counts, if not in result.json')
    ap.add_argument("--gate", type=Path, default=None,
                    help="convergence_gate.py report; runs not ACCEPTED are refused")
    ap.add_argument("--allow-frozen", action="store_true",
                    help="include ACCEPTED_SOLVER_FROZEN runs. Do not use for a "
                         "publishable GCI: a stalled solver bounds no iterative error.")
    ap.add_argument("--ratios", type=float, nargs=2, default=None,
                    metavar=("R21", "R32"),
                    help="refinement ratios, overriding the cell-count estimate. "
                         "REQUIRED for a directional family: (N1/N2)^(1/3) assumes "
                         "all three directions refine together, and when only one "
                         "does, it understates r by a cube root. See below.")
    ap.add_argument("--two-level-trend", action="store_true",
                    help="accept TWO levels and report the refinement TREND. Not a "
                         "GCI: no observed order, no extrapolation, no uncertainty "
                         "band. PLAN 2.1 requires this when the third level does not "
                         "fit the host.")
    ap.add_argument("--assumed-order", type=float, default=2.0,
                    help="with --two-level-trend, the order ASSUMED for the "
                         "sensitivity band. Assumed, never measured.")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    dirs = sorted({Path(p) for pat in args.runs for p in glob.glob(pat)})
    runs = []
    for d in dirs:
        rec = load(d)
        if rec is None:
            print(f"  skipping {d.name}: no result.json")
            continue
        level = re.sub(r"_a-?\d+$", "", d.name)
        cells = (args.cells or {}).get(level) or rec.get("cells")
        if cells is None:
            print(f"  skipping {d.name}: no cell count; pass --cells")
            continue
        rec.update({"dir": str(d), "level": level, "cells": int(cells)})
        runs.append(rec)

    verdicts = {}
    if args.gate and args.gate.exists():
        for r in json.loads(args.gate.read_text())["results"]:
            verdicts[Path(r["directory"]).name] = r["verdict"]

    kept, refused = [], []
    for r in runs:
        v = verdicts.get(Path(r["dir"]).name)
        if v is None:
            kept.append(r); continue
        if v == "ACCEPTED" or (args.allow_frozen and v.startswith("ACCEPTED")):
            r["gate_verdict"] = v; kept.append(r)
        else:
            r["gate_verdict"] = v; refused.append(r)
    for r in refused:
        print(f"  REFUSED {Path(r['dir']).name}: gate verdict {r['gate_verdict']}. "
              f"A GCI needs iterative error far below discretization error.")

    kept.sort(key=lambda r: -r["cells"])          # finest first

    if len(kept) == 2 and args.two_level_trend:
        return report_trend(kept, args)

    if len(kept) < 3:
        print(f"\nneed three accepted grid levels, have {len(kept)}. No GCI.")
        if len(kept) == 2:
            print("  Two levels are a refinement TREND, not a grid-convergence index.\n"
                  "  Pass --two-level-trend to report the movement between them, and\n"
                  "  read PLAN 2.1 on why the band is absent rather than estimated.")
        return 1
    f, m, c = kept[0], kept[1], kept[2]
    r21 = (f["cells"] / m["cells"]) ** (1.0 / 3.0)
    r32 = (m["cells"] / c["cells"]) ** (1.0 / 3.0)
    ratio_source = "cell counts, (N1/N2)^(1/3)"
    if args.ratios:
        # A DIRECTIONAL family refines one axis. Its cell count grows by roughly
        # r, not r^3, so (N1/N2)^(1/3) returns about r^(1/3) -- 1.09 for a
        # chordwise ratio of 1.29. The extrapolated value and the GCI band are
        # insensitive to that, because p is solved FOR and only r^p enters them;
        # but the reported order comes out about three times too large, trips the
        # 0.5-4 plausibility check, and a perfectly good triplet is refused as
        # "not in the asymptotic range". The ratio has to be the one in the
        # direction that actually refined.
        r21, r32 = args.ratios
        ratio_source = "given explicitly (--ratios), for a directional family"

    print(f"\ngrids, finest first:")
    for tag, r in (("fine", f), ("medium", m), ("coarse", c)):
        print(f"  {tag:>7}  {r['level']:<9} {r['cells']:>10,} cells")
    print(f"\n  r21 = {r21:.4f}   r32 = {r32:.4f}   "
          f"(unequal by {100*abs(r21-r32)/r32:.2f} %, so p is SOLVED, not evaluated)")

    report = {"grids": [{"level": r["level"], "cells": r["cells"], "dir": r["dir"]}
                        for r in (f, m, c)],
              "r21": r21, "r32": r32, "ratio_source": ratio_source,
              "functions": {}}
    print(f"\n{'':>6}{'fine':>12}{'medium':>12}{'coarse':>12}{'p':>8}"
          f"{'extrapolated':>14}{'GCI21 %':>10}  condition")
    for name in FUNCTIONS:
        if not all(name in r["short"] for r in (f, m, c)):
            continue
        g = gci_triplet(f["short"][name], m["short"][name], c["short"][name], r21, r32)
        report["functions"][name] = g
        print(f"{name:>6}{g['f1_fine']:>12.6f}{g['f2_medium']:>12.6f}"
              f"{g['f3_coarse']:>12.6f}"
              f"{g.get('p_observed', float('nan')):>8.3f}"
              f"{g.get('f_extrapolated', float('nan')):>14.6f}"
              f"{g.get('gci_21_percent', float('nan')):>10.3f}  {g['condition'][:40]}")

    bad = [n for n, g in report["functions"].items() if g["condition"] != "ok"]
    if bad:
        print(f"\nNOT in the asymptotic range for: {', '.join(bad)}")
        for n in bad:
            print(f"  {n}: {report['functions'][n]['condition']}")
        print("\nReport the condition, do not quote a GCI band for these.")
    else:
        print("\nall functions monotonic with a plausible observed order")

    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
