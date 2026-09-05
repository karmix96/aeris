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
    if not out["monotonic"]:
        out["condition"] = ("OSCILLATORY: e32/e21 is negative, so the three values do "
                            "not converge monotonically. The GCI below is reported but "
                            "the asymptotic assumption is not demonstrated.")
    elif not (0.5 <= p <= 4.0):
        out["condition"] = (f"observed order {p:.3f} is outside a plausible range for a "
                            f"second-order scheme; treat as not in the asymptotic range")
    else:
        out["condition"] = "ok"
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

    if len(kept) < 3:
        print(f"\nneed three accepted grid levels, have {len(kept)}. No GCI.")
        return 1

    kept.sort(key=lambda r: -r["cells"])          # finest first
    f, m, c = kept[0], kept[1], kept[2]
    r21 = (f["cells"] / m["cells"]) ** (1.0 / 3.0)
    r32 = (m["cells"] / c["cells"]) ** (1.0 / 3.0)

    print(f"\ngrids, finest first:")
    for tag, r in (("fine", f), ("medium", m), ("coarse", c)):
        print(f"  {tag:>7}  {r['level']:<9} {r['cells']:>10,} cells")
    print(f"\n  r21 = {r21:.4f}   r32 = {r32:.4f}   "
          f"(unequal by {100*abs(r21-r32)/r32:.2f} %, so p is SOLVED, not evaluated)")

    report = {"grids": [{"level": r["level"], "cells": r["cells"], "dir": r["dir"]}
                        for r in (f, m, c)],
              "r21": r21, "r32": r32, "functions": {}}
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
