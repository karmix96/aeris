"""The acceptance rule proposed on 13 Nov 2026 (a Fluent/CFX good-practice analogue), applied to any run's record.
Proposed, not adopted: solve/read_results.py is unchanged until Mike decides.

    python accept_v2.py            # judges every run of the V7 night and of the SU2 study, prints a table

1. continuity residual >= 4 orders below its largest value (SU2: rms[P] incompressible, rms[Rho] compressible;
   ADflow: the relative total residual totalR / totalR0 <= 1e-4, its own convergence measure);
2. every momentum residual >= 2 orders below its largest value; the turbulence and transition residuals not
   rising over the window (fitted change across the window <= +0.05 orders);
3. forces flat over the window = the last 20 % of the record, at least 100 iterations: CD within 0.5 counts,
   CL within 0.1 %, CMy within 0.0005, and the CD drift fitted over the window, carried over one more window,
   under 0.5 counts;
4. a record whose forces swing without drifting fails 3 and is labelled "oscillating": mean and band reported.
A continuation is judged on the whole concatenated record (S8: continuations must not hide the first leg).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

STAGE = Path(__file__).resolve().parents[4]
NIGHT = STAGE / "data/v7/night_11nov"
RUNS = STAGE / "runs/su2t_VVC_a4"


def su2(path: Path, upto: int | None = None) -> pd.DataFrame:
    d = pd.read_csv(path)
    d.columns = [c.strip().strip('"') for c in d.columns]
    return d.iloc[:upto] if upto else d


MIN_WINDOW = 100


def judge(cont, moms, turbs, cl, cd, cmy, adflow=False) -> dict:
    n = len(cd)
    w = max(MIN_WINDOW, int(0.2 * n))
    out = {"iterations": n}
    if adflow:
        drop = math.log10(cont[0] / cont[-1])
    else:
        drop = float(np.max(cont) - cont[-1])
    out["continuity_orders"] = round(drop, 2)
    out["momentum_orders_min"] = round(min(m for m in moms), 2) if moms else None
    rising = []
    for name, t in turbs.items():
        if len(t) >= w:
            ch = np.polyfit(np.arange(w), t[-w:], 1)[0] * w
            if ch > 0.05:
                rising.append(f"{name} +{ch:.2f}")
    out["turbulence_rising"] = rising or None
    if n < w + 1:
        out["forces"] = "too short"
        ok_f = False
    else:
        c, d, m = cl[-w:], cd[-w:], cmy[-w:]
        rd, rl, rm = (d.max() - d.min()) * 1e4, (c.max() - c.min()) / abs(c[-1]), m.max() - m.min()
        drift = abs(np.polyfit(np.arange(w), d, 1)[0] * w * 1e4)
        out |= {"window": w, "cd_range_counts": round(rd, 3), "cl_range_pct": round(rl * 100, 4),
                "cmy_range": round(float(rm), 6), "cd_drift_counts": round(drift, 3)}
        ok_f = rd <= 0.5 and rl <= 1e-3 and rm <= 5e-4 and drift <= 0.5
        if not ok_f and drift <= 0.5 and rd > 0.5:
            out["oscillating"] = f"CD mean {d.mean() * 1e4:.2f} counts, band {d.min() * 1e4:.2f}-{d.max() * 1e4:.2f}"
    ok_r = drop >= 4.0
    ok_m = out["momentum_orders_min"] is None or out["momentum_orders_min"] >= 2.0
    out["checks"] = {"1_continuity": ok_r, "2_momentum": ok_m, "2_turb_not_rising": not rising, "3_forces": ok_f}
    out["verdict"] = "ACCEPTED" if all(out["checks"].values()) else "not accepted"
    out["final"] = {"CL": round(float(cl[-1]), 5), "CD_counts": round(float(cd[-1]) * 1e4, 2), "CMy": round(float(cmy[-1]), 5)}
    return out


def su2_run(d: pd.DataFrame) -> dict:
    inc = "rms[P]" in d
    cont = d["rms[P]" if inc else "rms[Rho]"].to_numpy(float)
    mcols = ["rms[U]", "rms[V]", "rms[W]"] if inc else ["rms[RhoU]", "rms[RhoV]", "rms[RhoW]"]
    moms = [float(d[k].max() - d[k].iloc[-1]) for k in mcols]
    turbs = {k: d[k].to_numpy(float) for k in ("rms[nu]", "rms[k]", "rms[w]", "rms[LM_1]", "rms[LM_2]") if k in d}
    return judge(cont, moms, turbs, d.CL.to_numpy(float), d.CD.to_numpy(float), d.CMy.to_numpy(float))


def adflow_run(folder: Path) -> dict:
    h = json.loads((folder / "adflow/history_from_log.json").read_text())["history"]
    a = {k: np.array([x for x in v], float) for k, v in h.items() if k not in ("type",)}
    ok = np.isfinite(a["totalres"])
    a = {k: v[ok] for k, v in a.items()}
    moms = [math.log10(np.nanmax(a[k]) / a[k][-1]) for k in ("resrhou", "resrhov", "resrhow")]
    turbs = {"resnuturb (log10)": np.log10(a["resnuturb"])}
    return judge(a["totalres"], moms, turbs, a["cl"], a["cd"], a["cmy"], adflow=True)


def main() -> int:
    rows = []
    for name, f in [("A1 ADflow SA as written (stopped)", "A1_today_VVC_a4"), ("A1b ADflow SA 4 deg", "A1b_today_VVC_a4_turbksp"),
                    ("A4 ADflow SA -5 deg", "A4_today_VVC_am5"), ("A5 ADflow SA +10 deg", "A5_today_VVC_a10")]:
        rows.append((name, adflow_run(NIGHT / f)))
    for name, f in [("B1 SU2 comp. SA", "B1_today_VVC_a4_su2_sa/su2_sa"), ("B1b SU2 comp. SA lin30", "B1b_today_VVC_a4_lin30_su2_sa/su2_sa"),
                    ("B1c SU2 comp. SA lin30+LMC", "B1c_today_VVC_a4_lmc_su2_sa/su2_sa"),
                    ("B2b SU2 comp. SST+LM", "B2b_today_VVC_a4_lmc_su2_sst_lm/su2_sst_lm")]:
        rows.append((name, su2_run(su2(NIGHT / f / "history.csv"))))
    b, c, dd, e = (su2(RUNS / f"{x}/history.csv") for x in ("R1b_inc_sa_venk", "R1c_inc_sa_venk_cfl25_cont",
                                                           "R1d_inc_sa_venk_cfl25_frz", "R1e_inc_sa_venk_adapt_frz"))
    rows.append(("R1 SU2 inc. SA no limiter (diverged)", su2_run(su2(RUNS / "R1_inc_sa/history.csv"))))
    rows.append(("R1b SU2 inc. SA + limiter", su2_run(b)))
    rows.append(("R1c = R1b + R1c (CFL 25)", su2_run(pd.concat([b, c], ignore_index=True))))
    rows.append(("R1d = R1b + R1c + R1d (frozen)", su2_run(pd.concat([b, c, dd], ignore_index=True))))
    rows.append(("R1e = ... + R1e (adaptive)", su2_run(pd.concat([b, c, dd, e], ignore_index=True))))
    f = su2(RUNS / "R1f_inc_sa_recipe/history.csv")
    rows.append(("R1f SU2 inc. SA recipe (killed at 1132)", su2_run(f)))
    fc = RUNS / "R1f_cont/history.csv"
    if fc.exists():
        rows.append(("R1f + R1f-cont (current)", su2_run(pd.concat([f.iloc[:1001], su2(fc).iloc[1:]], ignore_index=True))))
    for name, r in rows:
        ch = r["checks"]
        fail = [k for k, v in ch.items() if not v]
        print(f"{name:42s} {r['verdict']:13s} it {r['iterations']:5d} cont {r['continuity_orders']:5.2f} mom {r['momentum_orders_min']} "
              f"CDr {r.get('cd_range_counts')} CLr% {r.get('cl_range_pct')} CMr {r.get('cmy_range')} drift {r.get('cd_drift_counts')} "
              f"turb_rising {r['turbulence_rising']} fails {fail} final {r['final']} {r.get('oscillating', '')}")
    (Path(__file__).resolve().parents[1] / "accept_v2_applied.json").write_text(json.dumps(dict(rows), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
