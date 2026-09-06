#!/usr/bin/env python
"""What does stopping the solver earlier actually cost the forces?

    .venv/bin/python .../l2_sensitivity.py --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_C_a*' \
        --out AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_l2_sensitivity.json

The evidence behind `--l2 1e-6`, kept reproducible rather than quoted once in a
commit message.

The question a residual target actually answers
------------------------------------------------
Not "is the solution converged" -- that is the gate's job, and the gate asks for
five orders AND settled forces AND a healthy residual history. `L2Convergence`
only decides WHEN TO STOP. So the honest way to choose it is to take runs that
went further than needed, read the forces off at each candidate stopping point,
and see what the extra iterations bought.

This replays the convergence history of completed runs and reports, for each
candidate target, the iteration where the relative residual first crossed it and
how far the forces there sit from their final values.

Note on what L2Convergence means.  It is a convergence FACTOR, not an absolute
residual: ADflow's own check is `totalrfinal / totalr0` (pyADflow.py:2007), and
`solve_s8.py` records exactly that ratio.  This script uses the same quantity --
the last log column divided by its first value -- so the numbers here are
directly comparable with the target that was set.

Why it matters more than it looks
----------------------------------
PLAN 0.9: 100 designs is about 8 days of solving and 1000 is about 80. Per-run
cost is the entire campaign budget, and on the gci_C sweep the last 89 per cent
of alpha 4 and alpha 8 bought changes in the fifth decimal.

Re-run this on a handful of pilot geometries with a tightened target to confirm
the choice still holds away from index 83. A tolerance justified on one geometry
is justified on one geometry.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np

#: ADflow monitorVariables order in solve_s8.py; column indices in the log row
#: after the leading four (grid, iter, itertot, type) plus CFL/Step/LinRes.
COL = {"resrho": 7, "cl": 13, "cd": 14, "cdp": 15, "cdv": 16, "cmy": 17, "totalres": 18}
ROW = re.compile(r"^ +1 +\d+ +\d+ ")
DEFAULT_TARGETS = (1e-4, 1e-5, 1e-6, 1e-7, 1e-8)


def history(log: Path) -> tuple[np.ndarray, np.ndarray] | None:
    iters, cols = [], []
    for line in log.read_text().splitlines():
        if not ROW.match(line):
            continue
        parts = line.split()
        if len(parts) <= COL["totalres"]:
            continue
        try:
            iters.append(int(parts[1]))
            cols.append([float(parts[COL[k]]) for k in
                         ("resrho", "cl", "cd", "cdp", "cdv", "cmy", "totalres")])
        except ValueError:
            continue
    if len(iters) < 20:
        return None
    return np.array(iters), np.array(cols)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--targets", type=float, nargs="+", default=list(DEFAULT_TARGETS))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    names = ("cl", "cd", "cdp", "cdv", "cmy")
    report = {"targets": args.targets, "runs": [],
              "l2_definition": "totalR/totalR0, the same ratio ADflow's L2Convergence uses"}

    print(f"{'run':<12}{'target':>9}{'iter':>7}{'% of run':>10}"
          + "".join(f"{'d' + n:>12}" for n in names))
    for directory in sorted({Path(p) for pat in args.runs for p in glob.glob(pat)}):
        log = directory / "run.log"
        if not log.exists():
            continue
        got = history(log)
        if got is None:
            continue
        iters, cols = got
        total = cols[:, 6]
        relative = total / total[0]
        final = cols[-1]
        entry = {"run": directory.name, "final_iteration": int(iters[-1]),
                 "final_relative_residual": float(relative[-1]),
                 "final_forces": {n: float(final[1 + i]) for i, n in enumerate(names)},
                 "at_target": {}}
        for target in args.targets:
            hit = np.argmax(relative <= target) if (relative <= target).any() else None
            if hit is None:
                entry["at_target"][f"{target:g}"] = {
                    "reached": False,
                    "note": "the run never reached this target; it stopped on other grounds"}
                print(f"{directory.name:<12}{target:>9.0e}{'never':>7}{'-':>10}")
                continue
            deltas = {n: float((cols[hit, 1 + i] - final[1 + i]) /
                               (abs(final[1 + i]) if final[1 + i] else 1.0))
                      for i, n in enumerate(names)}
            entry["at_target"][f"{target:g}"] = {
                "reached": True, "iteration": int(iters[hit]),
                "fraction_of_run": float(iters[hit] / iters[-1]),
                "forces": {n: float(cols[hit, 1 + i]) for i, n in enumerate(names)},
                "relative_change_vs_final": deltas}
            print(f"{directory.name:<12}{target:>9.0e}{iters[hit]:>7}"
                  f"{100 * iters[hit] / iters[-1]:>9.0f}%"
                  + "".join(f"{deltas[n]:>12.1e}" for n in names))
        report["runs"].append(entry)

    # the summary that decides the policy
    worst: dict = {}
    for target in args.targets:
        key = f"{target:g}"
        rows = [r["at_target"][key] for r in report["runs"]
                if r["at_target"].get(key, {}).get("reached")]
        if not rows:
            continue
        worst[key] = {
            "runs_reaching_it": len(rows),
            "worst_relative_change": {
                n: max(abs(r["relative_change_vs_final"][n]) for r in rows)
                for n in names},
            "median_fraction_of_run": float(np.median([r["fraction_of_run"] for r in rows])),
        }
    report["worst_case_by_target"] = worst

    print(f"\nworst |change| across runs, and how much of the run each target needs")
    print(f"{'target':>9}{'runs':>6}{'median % of run':>17}"
          + "".join(f"{n:>11}" for n in names))
    for key, w in worst.items():
        print(f"{key:>9}{w['runs_reaching_it']:>6}"
              f"{100 * w['median_fraction_of_run']:>16.0f}%"
              + "".join(f"{w['worst_relative_change'][n]:>11.1e}" for n in names))

    print("\n  Read this against the DISCRETIZATION difference the campaign exists to")
    print("  measure -- order 1e-2 on CD between grid levels. A stopping target whose")
    print("  worst force change is orders below that is not costing anything real.")
    print("  Acceptance remains convergence_gate.py; this only chooses when to stop.")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
