#!/usr/bin/env python
"""PLAN 3.4 and 3.5: read the refinement study, and choose the campaign level.

    .venv/bin/python .../analyse_refinement.py \
        --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*' \
        --out AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_refinement_analysis.json

Runs after `convergence_gate.py`, `gci.py --two-level-trend` (one per angle) and
`stability_convergence.py`, and pulls their separate verdicts into the one
decision PLAN 3.5 actually asks for: which level the ten-geometry pilot runs at,
and why.

The two things this adds that no other script does
---------------------------------------------------
1. **Over-bound cp counts across levels, at every angle.**  PLAN 3.4: 36 cells
   over the isentropic bound at alpha 8 on gci_C.  "If they fall with refinement
   the leading-edge excess is discretization; if flat, structural."  That is a
   question about a TREND across levels, so no single-run tool can answer it, and
   it is worth answering because it decides whether refinement is the fix.

2. **A recorded choice.**  PLAN 3.5 asks for the coarsest level whose uncertainty
   is acceptable for a SURROGATE-TRAINING dataset -- explicitly not for
   certification -- together with the justification.  A level chosen and not
   written down becomes a level nobody can defend later.

Why the choice is not automatic
--------------------------------
This script proposes and explains; it does not decide alone.  PLAN 3.5 warns
that CD and CMy need a finer level than CL -- CDp moved 5.2 % and CMy 18 % from a
single respacing, while CL barely moved -- and that running the campaign at a
level converged for lift while carrying a STATED uncertainty on drag and moment
is legitimate PROVIDED IT IS STATED.  That is a judgement about what the dataset
is for, so the script lays out the per-function movement, names the level it
would pick and on what grounds, and records whichever level is actually chosen.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FUNCTIONS = ("cl", "cd", "cdp", "cdv", "cmy")
CP_PHYSICAL_MAX = 1.0018
#: coarse to fine
LEVEL_ORDER = ("gci_CC", "gci_C", "gci_M", "gci_MF", "gci_F", "gci_FF")
#: PLAN 3.5: this dataset trains a surrogate. It does not certify anything.
PURPOSE = "surrogate-training dataset, not certification"


def cgns_variable(path: Path, name: str) -> np.ndarray | None:
    """One field, whichever CGNS container the file uses.

    This was an h5py reader. ADflow writes ADF here -- the linked CGNS was built
    without HDF5 -- so it silently returned None for every run and this script
    printed "no cp" for a quantity that was present in every file. Same defect
    as the blank cp panel in plot_sweep.py, in a second place, which is why the
    reader now lives in one module instead of being copied per script.
    """
    import cgns_read
    return cgns_read.read_variable(path, name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--gate", type=Path, default=None)
    ap.add_argument("--choose", default=None,
                    help="record this level as the campaign level. Without it the "
                         "script proposes one and records that it is a proposal.")
    ap.add_argument("--reason", default=None,
                    help="the justification to record alongside --choose")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    verdicts = {}
    if args.gate and args.gate.exists():
        for record in json.loads(args.gate.read_text())["results"]:
            verdicts[Path(record["directory"]).name] = record["verdict"]

    directories = sorted({Path(p) for pattern in args.runs for p in glob.glob(pattern)})
    runs: list[dict] = []
    for directory in directories:
        result = directory / "result.json"
        if not result.exists():
            continue
        data = json.loads(result.read_text())
        short = {}
        for key, value in data.get("functions", {}).items():
            for name in FUNCTIONS:
                if key.endswith("_" + name):
                    short[name] = float(value)
        level = re.sub(r"_a-?\d+(\.\d+)?$", "", directory.name)
        runs.append({"dir": directory, "level": level,
                     "alpha": float(data["alpha_deg"]),
                     "verdict": verdicts.get(directory.name), **short})

    levels = sorted({r["level"] for r in runs}, key=lambda l: LEVEL_ORDER.index(l)
                    if l in LEVEL_ORDER else 99)
    alphas = sorted({r["alpha"] for r in runs})
    report = {"plan_sections": ["3.4", "3.5"], "purpose": PURPOSE,
              "levels": levels, "alphas": alphas}

    # ---- 1. verdicts --------------------------------------------------------
    print("gate verdicts\n")
    print(f"{'alpha':>7}" + "".join(f"{l:>26}" for l in levels))
    verdict_table = {}
    for alpha in alphas:
        row = []
        for level in levels:
            match = next((r for r in runs if r["level"] == level and r["alpha"] == alpha), None)
            row.append(match["verdict"] if match and match["verdict"] else
                       ("no gate" if match else "-"))
        verdict_table[alpha] = dict(zip(levels, row))
        print(f"{alpha:>7.1f}" + "".join(f"{v:>26}" for v in row))
    report["gate_verdicts"] = verdict_table
    frozen = [(a, l) for a, row in verdict_table.items()
              for l, v in row.items() if v == "ACCEPTED_SOLVER_FROZEN"]
    if frozen:
        print(f"\n  solver-frozen points: {frozen}")
        print("  PLAN 3.4: gci.py refuses these. Whether the alpha 4 stall recurs on "
              "the\n  rebuilt meshes and at other levels is itself a result.")
    report["solver_frozen_points"] = [{"alpha": a, "level": l} for a, l in frozen]

    # ---- 2. per-function movement between levels ---------------------------
    print("\n\nmovement between levels, per function and angle")
    movement: dict = {}
    if len(levels) >= 2:
        coarse, fine = levels[0], levels[-1]
        print(f"  {coarse} -> {fine}\n")
        print(f"{'alpha':>7}" + "".join(f"{f:>22}" for f in FUNCTIONS))
        for alpha in alphas:
            c = next((r for r in runs if r["level"] == coarse and r["alpha"] == alpha), None)
            f = next((r for r in runs if r["level"] == fine and r["alpha"] == alpha), None)
            if not c or not f:
                continue
            cells = []
            movement.setdefault(alpha, {})
            for name in FUNCTIONS:
                if name not in c or name not in f:
                    cells.append(f"{'-':>22}")
                    continue
                delta = f[name] - c[name]
                pct = 100.0 * delta / c[name] if c[name] != 0 else float("nan")
                movement[alpha][name] = {"coarse": c[name], "fine": f[name],
                                         "change": delta, "change_percent": pct}
                cells.append(f"{delta:>+11.6f}{pct:>+10.2f}%")
            print(f"{alpha:>7.1f}" + "".join(cells))
        report["movement"] = {"coarse_level": coarse, "fine_level": fine,
                              "by_alpha": movement}
        worst = {}
        for name in FUNCTIONS:
            values = [abs(movement[a][name]["change_percent"])
                      for a in movement if name in movement[a]
                      and np.isfinite(movement[a][name]["change_percent"])]
            if values:
                worst[name] = max(values)
        report["worst_change_percent"] = worst
        print(f"\n  worst |change| over the angles, per function:")
        for name, value in sorted(worst.items(), key=lambda kv: -kv[1]):
            print(f"    {name:>5}  {value:>7.2f} %")

    # ---- 3. over-bound cp across levels (PLAN 3.4, last bullet) -------------
    print(f"\n\nsurface cp over the isentropic bound {CP_PHYSICAL_MAX}, by level")
    print("  falling with refinement => the leading-edge excess is DISCRETIZATION")
    print("  flat with refinement    => it is STRUCTURAL, and refinement will not fix it\n")
    cp_table: dict = {}
    print(f"{'alpha':>7}" + "".join(f"{l:>16}" for l in levels))
    for alpha in alphas:
        cells = []
        cp_table[alpha] = {}
        for level in levels:
            match = next((r for r in runs if r["level"] == level and r["alpha"] == alpha), None)
            if not match:
                cells.append(f"{'-':>16}")
                continue
            surfaces = sorted(match["dir"].glob("*surf*.cgns"))
            if not surfaces:
                cp_table[alpha][level] = None
                cells.append(f"{'no surf':>16}")
                continue
            cp = cgns_variable(surfaces[0], "CoefPressure")
            if cp is None or not cp.size:
                cp_table[alpha][level] = None
                cells.append(f"{'no cp':>16}")
                continue
            over = int((cp > CP_PHYSICAL_MAX).sum())
            peak = float(cp.max())
            cp_table[alpha][level] = {"cells_over_bound": over, "peak_cp": peak,
                                      "peak_excess": peak - CP_PHYSICAL_MAX,
                                      "of_faces": int(cp.size)}
            cells.append(f"{over:>9} /{peak:>6.3f}")
        print(f"{alpha:>7.1f}" + "".join(cells))
    report["cp_over_bound"] = cp_table
    if len(levels) >= 2:
        readings = []
        for alpha, row in cp_table.items():
            c = row.get(levels[0]); f = row.get(levels[-1])
            if isinstance(c, dict) and isinstance(f, dict) and c["peak_excess"] > 0:
                # Judge on the PEAK EXCESS, not the cell count.
                #
                # The count is the wrong metric the moment the cell size
                # changes: a finer grid puts more, smaller cells over the same
                # physical patch, so the count can rise while the region shrinks
                # and the overshoot weakens. Measured here, the count went UP at
                # three of four angles while the peak excess fell by 33 to 72 per
                # cent -- a count-based rule called that STRUCTURAL and it is the
                # opposite of what the data says. Same class of mistake as
                # judging force stability over a fixed iteration window: a metric
                # that does not account for the thing that changed.
                ratio = f["peak_excess"] / c["peak_excess"]
                count_ratio = (f["cells_over_bound"] / c["cells_over_bound"]
                               if c["cells_over_bound"] else float("nan"))
                readings.append({
                    "alpha": alpha,
                    "coarse_peak_excess": c["peak_excess"],
                    "fine_peak_excess": f["peak_excess"],
                    "peak_excess_ratio": ratio,
                    "coarse_count": c["cells_over_bound"],
                    "fine_count": f["cells_over_bound"],
                    "count_ratio": count_ratio,
                    "count_note": ("the count is reported but NOT used for the "
                                   "verdict: it scales with cell size, so it can "
                                   "rise under refinement while the excess falls"),
                    "reading": ("DISCRETIZATION: the peak excess falls with "
                                "refinement, so resolution is the cause"
                                if ratio < 0.7 else
                                "STRUCTURAL: the peak excess does not fall with "
                                "refinement; resolution will not fix it"
                                if ratio > 0.9 else
                                "ambiguous: the peak excess falls, but not decisively")})
        report["cp_over_bound_reading"] = readings
        for r in readings:
            print(f"\n  alpha {r['alpha']:g}: peak excess "
                  f"{r['coarse_peak_excess']:.3f} -> {r['fine_peak_excess']:.3f} "
                  f"({r['peak_excess_ratio']:.2f}x); count "
                  f"{r['coarse_count']} -> {r['fine_count']}"
                  f" ({r['count_ratio']:.2f}x, not used for the verdict)"
                  f"\n    {r['reading']}")

    # ---- 4. PLAN 3.5, the choice -------------------------------------------
    print(f"\n\nPLAN 3.5 -- the campaign level\n")
    decision: dict = {"purpose": PURPOSE, "levels_available": levels}
    if len(levels) < 2:
        decision["proposed"] = levels[0] if levels else None
        decision["basis"] = "only one level was run; there is nothing to choose between"
    else:
        worst = report.get("worst_change_percent", {})
        decision["movement_summary"] = worst
        decision["proposed"] = levels[0]
        decision["basis"] = (
            f"PLAN 3.5 asks for the COARSEST level whose uncertainty is acceptable "
            f"for a {PURPOSE}. Between {levels[0]} and {levels[-1]} the outputs move "
            + ", ".join(f"{k} {v:.2f} %" for k, v in sorted(worst.items(), key=lambda kv: -kv[1]))
            + f". The coarsest level is proposed because the campaign arithmetic is "
              f"what shapes this decision -- PLAN 0.9: 100 designs is about 8 days of "
              f"solving -- and because these movements are what the dataset must "
              f"CARRY as a stated uncertainty, not what it must eliminate.")
        decision["mandatory_caveat"] = (
            "Two levels. The movements above are the movement under one refinement "
            "step, NOT an uncertainty band: there is no observed order and no "
            "extrapolation. PLAN 3.5's phrase 'whose GCI band is acceptable' cannot "
            "be satisfied on this host, and the choice rests on the movement alone. "
            "Any dataset built at this level must state that.")
        decision["expected_split"] = (
            "PLAN 3.5: expect CD and CMy to need a finer level than CL. Running the "
            "campaign at a level converged for lift while carrying a stated "
            "uncertainty on drag and moment is legitimate -- provided it is stated.")
    if args.choose:
        decision["chosen"] = args.choose
        decision["chosen_reason"] = args.reason or "recorded without a stated reason"
        decision["chosen_matches_proposal"] = args.choose == decision.get("proposed")
        print(f"  CHOSEN: {args.choose}")
        print(f"  reason: {decision['chosen_reason']}")
    else:
        decision["chosen"] = None
        decision["status"] = ("PROPOSAL ONLY. Re-run with --choose <level> --reason "
                              "'...' to record a decision.")
        print(f"  proposed: {decision['proposed']}  (proposal only, nothing recorded "
              f"as chosen)")
    print(f"\n  {decision['basis']}")
    if "mandatory_caveat" in decision:
        print(f"\n  {decision['mandatory_caveat']}")
    report["campaign_level_decision"] = decision

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
