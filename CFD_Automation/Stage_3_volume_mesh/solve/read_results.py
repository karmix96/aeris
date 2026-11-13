"""Judge and compare the V7 runs: ADflow SA (result.json), SU2 SA and SU2 SST + LM (history.csv).

    python solve/read_results.py --case runs/v7_a4      # -> runs/v7_a4/results.json and results.md

The acceptance rule (adopted by Mike on 13 Nov 2026; a Fluent/CFX good-practice analogue; the evidence and the
rule applied to every run so far: data/v7/su2_transition/REPORT.md and accept_v2_applied.json):
    1 residual    continuity >= 4 orders below its largest value (SU2: rms[P] on the incompressible solver, rms[Rho]
                  on the compressible one); ADflow: relative total residual totalR/totalR0 <= 1e-4
    2 equations   SU2: every momentum residual >= 2 orders below its largest value; the turbulence and transition
                  residuals not rising (fitted change across the window <= +0.05 orders). ADflow's result.json holds
                  only the total residual, which contains them
    3 forces      over the last 20 % of the record, at least 30 iterations: CD moves <= 0.5 counts, CL <= 0.1 %,
                  CMy <= 0.0005, and the CD drift fitted over the window, carried over one more window, <= 0.5 counts
    4             forces that swing without drifting fail 3 and are labelled oscillating (mean and band reported)
    accepted      1, 2 and 3; otherwise "not accepted", with the reasons
Measured basis (SU2 R1f, SA): at 4 orders CD was 0.07 counts and CL 0.005 % from their converged values; at 3
orders 0.46 counts. The momentum residuals fall about half as far as the continuity one.

The rule before 13 Nov (V7 night): SU2 density residual 6 orders down (or 1e-12); ADflow relative residual 1e-6;
settled over the last 20 % with at least 200 iterations (CD 0.5 counts, CL 0.1 %). It could not judge ADflow's
converged runs (136 to 239 iterations), and on SU2 it waited on a residual held by about 100 points at two
leading-edge corners while the forces were final to 0.05 counts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

CONT_ORDERS = 4.0
ADFLOW_REL_RES = 1.0e-4
MOM_ORDERS = 2.0
TURB_RISE = 0.05
TAIL = 0.2
TAIL_MIN = 30
CD_COUNTS = 0.5
CL_REL = 1.0e-3
CMY_ABS = 5.0e-4
DRIFT_COUNTS = 0.5


def settled(cl: np.ndarray, cd: np.ndarray, cmy: np.ndarray | None = None) -> dict:
    """Rule 3 (and 4): the forces over the last 20 % of the record, at least TAIL_MIN iterations."""
    cl, cd = np.asarray(cl, float), np.asarray(cd, float)
    n = len(cd)
    m = max(TAIL_MIN, int(TAIL * n))
    if n < m + 1:
        return {"settled": False, "reason": f"{n} iterations: too short to judge", "window": n}
    c, d = cl[-m:], cd[-m:]
    wl = float(c.max() - c.min()) / max(abs(float(c[-1])), 1e-12)
    wd = float(d.max() - d.min()) * 1e4
    drift = abs(float(np.polyfit(np.arange(m), d, 1)[0]) * m * 1e4)
    out = {"window": m, "cd_wander_counts": wd, "cl_wander_rel": wl, "cd_drift_counts": drift}
    ok = wd <= CD_COUNTS and wl <= CL_REL and drift <= DRIFT_COUNTS
    if cmy is not None:
        wm = float(np.ptp(np.asarray(cmy, float)[-m:]))
        out["cmy_wander"] = wm
        ok = ok and wm <= CMY_ABS
    out["settled"] = bool(ok)
    if not ok and drift <= DRIFT_COUNTS and wd > CD_COUNTS:
        out["oscillating"] = {"cd_mean_counts": float(d.mean() * 1e4), "cd_band_counts": [float(d.min() * 1e4), float(d.max() * 1e4)]}
    if not ok:
        out["reason"] = "forces oscillating" if "oscillating" in out else "forces not settled"
    return out


def su2_residuals(df, cont_ref: float | None = None) -> dict:
    """Rules 1 and 2 on an SU2 history (columns already stripped). cont_ref: a continuation's first-leg peak."""
    inc = "rms[P]" in df
    col = "rms[P]" if inc else "rms[Rho]"
    r = df[col].to_numpy(float)
    top = max(float(r.max()), cont_ref) if cont_ref is not None else float(r.max())
    drop = top - float(r[-1])
    moms = [k for k in (("rms[U]", "rms[V]", "rms[W]") if inc else ("rms[RhoU]", "rms[RhoV]", "rms[RhoW]")) if k in df]
    mom = min(float(df[k].max() - df[k].iloc[-1]) for k in moms) if moms else None
    n = len(df)
    m = max(TAIL_MIN, int(TAIL * n))
    rising = []
    for k in ("rms[nu]", "rms[k]", "rms[w]", "rms[LM_1]", "rms[LM_2]"):
        if k in df and n > m:
            ch = float(np.polyfit(np.arange(m), df[k].to_numpy(float)[-m:], 1)[0]) * m
            if ch > TURB_RISE:
                rising.append(f"{k} +{ch:.2f} orders")
    return {"residual": col, "residual_final": float(r[-1]), "orders_dropped": drop, "momentum_orders_min": mom,
            "turbulence_rising": rising or None,
            "converged": bool(drop >= CONT_ORDERS and (mom is None or mom >= MOM_ORDERS) and not rising)}


def judge_su2_history(df, cont_ref: float | None = None) -> dict:
    cmy = df["CMy"].to_numpy(float) if "CMy" in df else None
    out = su2_residuals(df, cont_ref) | settled(df["CL"].to_numpy(float), df["CD"].to_numpy(float), cmy)
    return out


def read_su2(folder: Path) -> dict | None:
    import pandas as pd
    h = folder / "history.csv"
    if not h.exists():
        return None
    df = pd.read_csv(h)
    df.columns = [c.strip().strip('"') for c in df.columns]
    out = {"solver": "SU2", "iterations": int(len(df)),
           "coefficients": {k.lower(): float(df[k].iloc[-1]) for k in ("CL", "CD", "CMy") if k in df}}
    out |= judge_su2_history(df)
    if (folder / "forces_breakdown.dat").exists():
        out["forces_breakdown"] = "forces_breakdown.dat"          # pressure and friction parts, for the comparison
    return out


def read_adflow(folder: Path) -> dict | None:
    p = folder / "result.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    rr = r.get("relative_residual")
    conv = (rr is not None and rr <= ADFLOW_REL_RES and not r.get("routine_failed") and not r.get("implausible")
            and (r.get("iterations") or 0) >= 10)
    out = {"solver": "ADflow", "iterations": r.get("iterations"), "relative_residual": rr,
           "orders_dropped": -float(np.log10(rr)) if rr else None, "converged": bool(conv),
           "coefficients": r.get("coefficients", {})}
    h = r.get("history")
    if isinstance(h, dict) and "cl" in {k.lower() for k in h} and "cd" in {k.lower() for k in h}:
        hh = {k.lower(): np.array(v, float) for k, v in h.items()}
        out |= settled(hh["cl"], hh["cd"], hh.get("cmy"))
    else:
        out |= {"settled": False, "reason": "no force history in result.json"}
    return out


def judge(r: dict) -> dict:
    ok = r["converged"] and r.get("settled", False)
    why = []
    if not r["converged"]:
        why.append("not converged" + (f" (rising: {', '.join(r['turbulence_rising'])})" if r.get("turbulence_rising") else ""))
    if not r.get("settled"):
        why.append(r.get("reason", "forces not settled"))
    return r | {"verdict": "accepted" if ok else "not accepted", "why": why}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", type=Path, required=True)
    a = ap.parse_args()
    runs = {"ADflow SA": read_adflow(a.case / "adflow"), "SU2 SA": read_su2(a.case / "su2_sa"),
            "SU2 SST+LM": read_su2(a.case / "su2_sst_lm")}
    res = {k: (judge(v) if v else {"verdict": "not run"}) for k, v in runs.items()}
    (a.case / "results.json").write_text(json.dumps(res, indent=1))
    lines = ["| run | verdict | iterations | CL | CD | CMy | why |", "|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        c = v.get("coefficients", {})
        f = lambda x: f"{c[x]:.5f}" if x in c else ""
        lines.append(f"| {k} | {v['verdict']} | {v.get('iterations', '')} | {f('cl')} | {f('cd')} | {f('cmy')} | "
                     f"{'; '.join(v.get('why', []))} |")
    (a.case / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
