#!/usr/bin/env python
"""Read an S8 alpha sweep and report the lift curve, with the checks that matter.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/summarise_sweep.py \
        --runs AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd/oh_L3_fixed_a*

Three things this checks that a table of numbers would not:

1. **Every run carries a verified freestream.**  `solve_s8.py` records the
   realised `velDirFreeStream` and `liftDirection` in `result.json`.  A run
   without that block predates the defect-14 fix and its forces are not
   comparable with one that has it, so it is reported as unverified rather than
   quietly averaged in.

2. **Convergence is read, not assumed.**  ADflow exits cleanly when it runs out
   of cycles, so `routine_failed: false` says nothing about whether the run
   converged.  The relative residual against the L2 target is what says it.

3. **alpha 0 reproduces the quantities that never depended on the lift axis.**
   CD, CDp, CDv and CMy are independent of `liftIndex`, so the corrected alpha 0
   run must return the pre-fix values.  If it does not, something other than the
   lift axis changed and the sweep should not be trusted.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

#: the pre-fix alpha 0 run, whose lift-axis-independent quantities must survive
PREFIX_ALPHA0 = {"cd": 0.021416089729801753, "cdp": 0.012494219073837673,
                 "cdv": 0.008921870655964084, "cmy": 0.0010851618638613705}
#: integrated from the pre-fix alpha 0 surface solution, pressure part only
PREDICTED_CL_ALPHA0 = -0.1607


def load(directory: Path) -> dict | None:
    path = directory / "result.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    functions = data.get("functions", {})
    # ADflow prefixes each function with the AeroProblem name
    short = {}
    for key, value in functions.items():
        for name in ("cl", "cdp", "cdv", "cd", "cmy"):
            if key.endswith("_" + name):
                short[name] = float(value)
                break
    data["short"] = short
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    directories = sorted({Path(p) for pattern in args.runs for p in glob.glob(pattern)})
    rows = []
    for directory in directories:
        data = load(directory)
        if data is None:
            print(f"  {directory.name}: no result.json -- did not finish")
            continue
        rows.append((directory, data))

    if not rows:
        print("no completed runs found")
        return 1

    rows.sort(key=lambda r: r[1]["alpha_deg"])

    print(f"\n{'alpha':>7}{'CL':>11}{'CD':>11}{'CDp':>11}{'CDv':>11}{'CMy':>11}"
          f"{'rel resid':>12}{'converged':>11}{'freestream':>12}")
    for directory, data in rows:
        s = data["short"]
        residual = data.get("relative_residual")
        directions = data.get("flow_directions")
        verified = "verified" if directions else "UNVERIFIED"
        print(f"{data['alpha_deg']:>7.1f}"
              f"{s.get('cl', float('nan')):>11.6f}{s.get('cd', float('nan')):>11.6f}"
              f"{s.get('cdp', float('nan')):>11.6f}{s.get('cdv', float('nan')):>11.6f}"
              f"{s.get('cmy', float('nan')):>11.6f}"
              f"{('n/a' if residual is None else f'{residual:.2e}'):>12}"
              f"{str(data.get('converged')):>11}{verified:>12}")

    problems: list[str] = []
    for directory, data in rows:
        if not data.get("flow_directions"):
            problems.append(
                f"alpha {data['alpha_deg']:g}: no flow_directions block. This run "
                f"predates the defect-14 fix; its forces are not comparable.")
        elif data["flow_directions"]["lift_index_realised"] != 3:
            problems.append(
                f"alpha {data['alpha_deg']:g}: ran at liftIndex "
                f"{data['flow_directions']['lift_index_realised']}, not 3.")
        if not data.get("converged"):
            problems.append(
                f"alpha {data['alpha_deg']:g}: did NOT converge "
                f"(relative residual {data.get('relative_residual')}).")

    # the alpha 0 regression check
    zero = [d for _, d in rows if abs(d["alpha_deg"]) < 1e-9]
    if zero:
        s = zero[0]["short"]
        print("\nalpha 0 against the pre-fix run "
              "(these four do not depend on the lift axis and must survive):")
        print(f"  {'':>6}{'pre-fix':>13}{'now':>13}{'change':>12}")
        for name, before in PREFIX_ALPHA0.items():
            now = s.get(name)
            if now is None:
                continue
            change = (now - before) / before if before else float("nan")
            flag = "" if abs(change) < 0.02 else "   <<< moved more than 2 %"
            print(f"  {name:>6}{before:>13.6f}{now:>13.6f}{change:>11.2%}{flag}")
            if abs(change) > 0.02:
                problems.append(
                    f"alpha 0: {name} moved {change:.1%} against the pre-fix run. "
                    f"That quantity does not depend on the lift axis, so something "
                    f"other than defect 14 changed.")
        if "cl" in s:
            print(f"\n  CL is the one that SHOULD move: pre-fix 0.032301 "
                  f"(the spanwise force), now {s['cl']:.6f}")
            print(f"  predicted from integrating the pre-fix surface: about "
                  f"{PREDICTED_CL_ALPHA0:+.4f} (pressure part only, so the viscous "
                  f"contribution is not in that number)")

    # lift curve slope, if there are two or more converged verified points
    usable = [(d["alpha_deg"], d["short"]["cl"]) for _, d in rows
              if d.get("converged") and d.get("flow_directions") and "cl" in d["short"]]
    if len(usable) >= 2:
        usable.sort()
        (a0, c0), (a1, c1) = usable[0], usable[-1]
        print(f"\nlift-curve slope over alpha {a0:g} to {a1:g}: "
              f"{(c1 - c0) / (a1 - a0):.5f} per degree")
        print("  a thin-aerofoil wing of aspect ratio about 4.8 gives roughly "
              "0.078 per degree")

    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("no problems found: every run verified its freestream and converged")

    if args.out:
        args.out.write_text(json.dumps(
            {"runs": [{"dir": str(d), **r} for d, r in rows], "problems": problems},
            indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
