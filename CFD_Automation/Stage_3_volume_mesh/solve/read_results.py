"""Judge and compare the V7 runs: ADflow SA (result.json), SU2 SA and SU2 SST + LM (history.csv).

    python solve/read_results.py --case runs/v7_a4      # -> runs/v7_a4/results.json and results.md

The acceptance rule is written here before any run (S8 learned that a residual target alone gives false fails and a
short window false passes):
    converged   ADflow: relative residual <= 1e-6 with >= 10 iterations and plausible forces;
                SU2: the density residual 6 orders below its largest value, or at 1e-12
    settled     over the last 20 % of the record (at least 200 iterations): CD moves <= 0.5 counts and CL <= 0.1 %
    accepted    converged and settled; otherwise "not accepted", with the reason
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

CD_COUNTS = 0.5
CL_REL = 1.0e-3
TAIL = 0.2
TAIL_MIN = 200


def settled(cl: np.ndarray, cd: np.ndarray) -> dict:
    n = len(cd)
    m = max(TAIL_MIN, int(TAIL * n))
    if n < m + 25:
        return {"settled": False, "reason": f"{n} iterations: too short to judge", "window": n}
    c, d = cl[-m:], cd[-m:]
    wl = float(c.max() - c.min()) / max(abs(float(c[-1])), 1e-12)
    wd = float(d.max() - d.min()) * 1e4
    return {"settled": wd <= CD_COUNTS and wl <= CL_REL, "window": m, "cd_wander_counts": wd, "cl_wander_rel": wl}


def read_su2(folder: Path) -> dict | None:
    import pandas as pd
    h = folder / "history.csv"
    if not h.exists():
        return None
    df = pd.read_csv(h)
    df.columns = [c.strip().strip('"') for c in df.columns]
    rho = df["rms[Rho]"].to_numpy(float)
    cl, cd = df["CL"].to_numpy(float), df["CD"].to_numpy(float)
    drop = float(rho.max() - rho[-1])
    out = {"solver": "SU2", "iterations": int(len(df)), "rms_rho_final": float(rho[-1]), "orders_dropped": drop,
           "converged": bool(drop >= 6.0 or rho[-1] <= -12.0),
           "coefficients": {k.lower(): float(df[k].iloc[-1]) for k in ("CL", "CD", "CMy") if k in df}}
    out |= settled(cl, cd)
    if (folder / "forces_breakdown.dat").exists():
        out["forces_breakdown"] = "forces_breakdown.dat"          # pressure and friction parts, for the comparison
    return out


def read_adflow(folder: Path) -> dict | None:
    p = folder / "result.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    out = {"solver": "ADflow", "iterations": r.get("iterations"), "relative_residual": r.get("relative_residual"),
           "converged": bool(r.get("converged")), "coefficients": r.get("coefficients", {})}
    h = r.get("history")
    if isinstance(h, dict) and "cl" in {k.lower() for k in h} and "cd" in {k.lower() for k in h}:
        hh = {k.lower(): np.array(v, float) for k, v in h.items()}
        out |= settled(hh["cl"], hh["cd"])
    else:
        out |= {"settled": False, "reason": "no force history in result.json"}
    return out


def judge(r: dict) -> dict:
    ok = r["converged"] and r.get("settled", False)
    why = [] if ok else ([] if r["converged"] else ["not converged"]) + ([] if r.get("settled") else
                                                                         [r.get("reason", "forces not settled")])
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
