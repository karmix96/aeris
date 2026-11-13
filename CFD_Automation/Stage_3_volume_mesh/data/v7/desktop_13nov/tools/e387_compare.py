"""Block E: an SU2 E387 run (2-D) against McGhee, NASA TM-4062 (as S8 recorded it in reports/s8_su2_validation.json):
the forces and the laminar separation bubble on the upper side.

    python e387_compare.py <run folder with history.csv and surface_flow.dat> [<out.json>] [--from-iter N]

Forces: the last value and, from --from-iter on (default: the last 20 % of the record), the mean and the band.
Moment: SU2's CMz about the quarter chord. S8 measured the sign on this grid (SU2_REPORT section 7: a positive M_z
lifts the tail, nose down); McGhee's -0.0794 is nose down with nose down negative, so CM(McGhee) = -CMz(SU2).
Bubble: the upper side (above the chord line from the leading-edge node to the trailing-edge node), sorted by x;
reversed-flow runs where Skin_Friction_Coefficient_x < 0 between x/c 0.02 and 0.98; the main bubble is the longest
run, with gaps of up to 2 nodes inside it bridged, and the longest strictly contiguous run (both are reported: a
separated region with near-zero friction alternates in sign node to node); start, end and length against the oil flow
(0.43, 0.67, 0.24).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "../su2_transition/tools"))
from wall_map import read_tecplot                                   # noqa: E402

REF = {"CL": 0.574, "CD": 0.0118, "CD_uncertainty": 0.00026, "CM": -0.0794, "sep": 0.43, "reatt": 0.67,
       "source": "NASA TM-4062 table B1 runs 9, 10, 13; bubble table III (oil flow); alpha 2.04 measured, run at 2.0"}


def bubble(x, y, cfx):
    ile, ite = int(np.argmin(x)), int(np.argmax(x))
    xc = (x - x[ile]) / (x[ite] - x[ile])
    up = y >= y[ile] + (y[ite] - y[ile]) * xc
    o = np.argsort(xc[up])
    xs, cf = xc[up][o], cfx[up][o]
    m = (xs > 0.02) & (xs < 0.98)
    neg = (cf < 0) & m
    runs, i = [], 0
    idx = np.where(m)[0]
    while i < len(idx):
        k = idx[i]
        if neg[k]:
            j = i
            while j + 1 < len(idx) and (neg[idx[j + 1]] or (j + 3 < len(idx) and neg[idx[j + 2]]) or (j + 3 < len(idx) and neg[idx[j + 3]])):
                j += 1
            runs.append((float(xs[idx[i]]), float(xs[idx[j]])))
            i = j + 1
        else:
            i += 1
    main = max(runs, key=lambda r: r[1] - r[0]) if runs else None
    strict, i = [], 0                                            # contiguous reversed nodes only, no bridging
    while i < len(idx):
        if neg[idx[i]]:
            j = i
            while j + 1 < len(idx) and neg[idx[j + 1]]:
                j += 1
            strict.append((float(xs[idx[i]]), float(xs[idx[j]])))
            i = j + 1
        else:
            i += 1
    smain = max(strict, key=lambda r: r[1] - r[0]) if strict else None
    return main, runs, smain


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("folder", type=Path)
    p.add_argument("out", type=Path, nargs="?")
    p.add_argument("--from-iter", type=int, default=None)
    a = p.parse_args()
    d = pd.read_csv(a.folder / "history.csv")
    d.columns = [c.strip().strip('"') for c in d.columns]
    n0 = a.from_iter if a.from_iter is not None else int(0.8 * len(d))
    t = d[d.Inner_Iter >= n0]
    f = {"CL": d.CL.to_numpy(float), "CD": d.CD.to_numpy(float), "CM": -d.CMz.to_numpy(float)}
    rep = {"reference": REF, "iterations": int(len(d)), "window_from_iter": n0, "forces": {}}
    for k, v in f.items():
        w = v[-len(t):]
        rep["forces"][k] = {"last": float(v[-1]), "mean": float(w.mean()), "min": float(w.min()), "max": float(w.max()),
                            "mean_minus_ref": float(w.mean() - REF[k])}
    rep["forces"]["CD"]["mean_minus_ref_counts"] = rep["forces"]["CD"]["mean_minus_ref"] * 1e4
    names, W, _ = read_tecplot(a.folder / "surface_flow.dat")
    c = {nm: i for i, nm in enumerate(names)}
    main_b, runs, smain = bubble(W[:, c["x"]], W[:, c["y"]], W[:, c["Skin_Friction_Coefficient_x"]])
    rep["bubble"] = {"main": main_b, "length": (main_b[1] - main_b[0]) if main_b else None, "all_reversed_runs": runs,
                     "main_contiguous": smain, "length_contiguous": (smain[1] - smain[0]) if smain else None,
                     "measured": [REF["sep"], REF["reatt"]], "measured_length": REF["reatt"] - REF["sep"],
                     "note": "from the wall file at the run's end (SU2 writes it at the stop)"}
    if a.out:
        a.out.write_text(json.dumps(rep, indent=1))
    F = rep["forces"]
    print(f"{a.folder.name}: {len(d)} iterations, window from {n0}")
    print(f"  CL last {F['CL']['last']:.4f} mean {F['CL']['mean']:.4f} band {F['CL']['min']:.4f}-{F['CL']['max']:.4f} | McGhee 0.574")
    print(f"  CD last {F['CD']['last']*1e4:.1f} mean {F['CD']['mean']*1e4:.1f} band {F['CD']['min']*1e4:.1f}-{F['CD']['max']*1e4:.1f} counts | McGhee 118 +- 2.6 (mean - ref {F['CD']['mean_minus_ref_counts']:+.1f})")
    print(f"  CM last {F['CM']['last']:.4f} mean {F['CM']['mean']:.4f} | McGhee -0.0794")
    fm = lambda r: f"{r[0]:.3f}-{r[1]:.3f} ({r[1] - r[0]:.3f})" if r else "none"
    print(f"  bubble, gaps of up to 2 nodes bridged: {fm(main_b)}; contiguous only: {fm(smain)} | McGhee 0.430-0.670 (0.240)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
