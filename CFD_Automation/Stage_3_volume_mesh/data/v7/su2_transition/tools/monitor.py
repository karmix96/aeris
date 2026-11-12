"""Watch one SU2 run's convergence, with no time limit (SU2 study of 12 Nov 2026: "remove the time limiter, just
monitor the convergence").

    python monitor.py --folder runs/<case>/<run folder> &

Every --every seconds it reads history.csv and writes monitor_status.json: the residual (rms[P] on the incompressible
solver, rms[Rho] on the compressible one), the orders dropped from the record's largest value, the rate over the
last 200 and 1,000 iterations, the forces and how much they moved in the last 500 iterations, the CFL. Every
--log-every seconds it appends one line to monitor_log.txt.

It stops the run only when solve/read_results.py's acceptance rule holds, with that file's own code (imported, not
copied): 6 orders of the residual (or an absolute 1e-12) and settled forces. SU2 8.5.0 catches SIGTERM and writes
all its files at the current iteration, so the stop loses nothing. A stall is reported in the status ("stalled":
no new residual minimum by 0.25 orders in the last 1,000 iterations), never acted on: that is decided by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

STAGE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(STAGE / "solve"))
from read_results import settled                               # noqa: E402  the acceptance rule, as written
from rss_watch import ranks                                     # noqa: E402  the same process matching


def uptime() -> float:
    return float(Path("/proc/uptime").read_text().split()[0])   # the WSL wall clock steps by ~90 s


def slope(it, r) -> float | None:
    import numpy as np
    if len(r) < 20:
        return None
    return float(np.polyfit(it, r, 1)[0] * 1000.0)              # orders per 1,000 iterations (negative = falling)


def state(hist: Path, res_ref: float | None = None) -> dict | None:
    """res_ref: for a continuation, the largest residual of the whole record (the first leg's), so the orders are
    counted from the start of the solve and not from the restart (S8 defect: "continuations invisible")."""
    import numpy as np
    import pandas as pd
    try:
        df = pd.read_csv(hist)
    except Exception:
        return None
    df.columns = [c.strip().strip('"') for c in df.columns]
    res = "rms[P]" if "rms[P]" in df else "rms[Rho]" if "rms[Rho]" in df else None
    if res is None or len(df) < 2:
        return None
    df = df.apply(pd.to_numeric, errors="coerce").dropna(subset=[res, "CL", "CD"])
    if len(df) < 2:
        return None
    r = df[res].to_numpy(float)
    it = df["Inner_Iter"].to_numpy(float) if "Inner_Iter" in df else np.arange(len(df), dtype=float)
    cl, cd = df["CL"].to_numpy(float), df["CD"].to_numpy(float)
    top = max(float(r.max()), res_ref) if res_ref is not None else float(r.max())
    drop = float(top - r[-1])
    st = settled(cl, cd)
    t5 = slice(-500, None)
    out = {"rows": int(len(df)), "inner_iter": int(it[-1]), "residual": res, "res_first": float(r[0]),
           "res_max": float(r.max()), "res_ref": res_ref, "res_last": float(r[-1]), "res_min": float(r.min()),
           "res_min_at": int(it[int(r.argmin())]), "orders_dropped": drop,
           "rate_last200_orders_per_1000": slope(it[-200:], r[-200:]),
           "rate_last1000_orders_per_1000": slope(it[-1000:], r[-1000:]),
           "converged": bool(drop >= 6.0 or r[-1] <= -12.0), "settled": bool(st.get("settled")), "settled_detail": st,
           "cl": float(cl[-1]), "cd_counts": float(cd[-1]) * 1e4,
           "cmy": float(df["CMy"].iloc[-1]) if "CMy" in df else None,
           "cd_moved_last500_counts": float((cd[t5].max() - cd[t5].min()) * 1e4),
           "cl_moved_last500_rel": float((cl[t5].max() - cl[t5].min()) / max(abs(cl[-1]), 1e-12))}
    # stalled: the best residual of the last 1,000 iterations is not 0.25 orders below the best before them
    if len(r) > 1500:
        out["stalled"] = bool(r[-1000:].min() > r[:-1000].min() - 0.25)
    for c in ("Avg CFL", "Avg_CFL"):
        if c in df:
            out["cfl_avg_median_last200"] = float(np.median(df[c].to_numpy(float)[-200:]))
    if "LinSolRes" in df:
        out["linsol_res_median_last200"] = float(np.median(df["LinSolRes"].to_numpy(float)[-200:]))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--folder", type=Path, required=True)
    p.add_argument("--every", type=float, default=60.0)
    p.add_argument("--log-every", type=float, default=600.0)
    p.add_argument("--wait", type=float, default=900.0, help="seconds to wait for the first SU2 rank")
    p.add_argument("--no-stop", action="store_true", help="report only, never stop the run")
    p.add_argument("--res-ref", type=float, default=None,
                   help="a continuation: the largest residual of the first leg, the base of the orders dropped")
    a = p.parse_args(argv)
    hist, st_path, log = a.folder / "history.csv", a.folder / "monitor_status.json", a.folder / "monitor_log.txt"
    rep = {"folder": str(a.folder), "rule": "solve/read_results.py: 6 orders of the residual (or 1e-12) and settled forces",
           "accepted_at": None, "stopped": None}
    t0, seen, last_log = uptime(), False, -1e9
    while True:
        alive = ranks("SU2_CFD")
        if alive:
            seen = True
        elif seen or uptime() - t0 > a.wait:
            break
        s = state(hist, a.res_ref) if hist.exists() else None
        if s:
            s |= {"seconds": round(uptime() - t0), "wall": time.strftime("%F %T")}
            st_path.write_text(json.dumps(s, indent=1))
            if uptime() - last_log >= a.log_every:
                last_log = uptime()
                with open(log, "a") as f:
                    f.write(f"{s['wall']} t={s['seconds']}s it={s['inner_iter']} {s['residual']}={s['res_last']:.3f} "
                            f"drop={s['orders_dropped']:.2f} rate200={s['rate_last200_orders_per_1000']} "
                            f"rate1000={s['rate_last1000_orders_per_1000']} CL={s['cl']:.5f} CD={s['cd_counts']:.2f} "
                            f"dCD500={s['cd_moved_last500_counts']:.2f} dCL500={s['cl_moved_last500_rel']:.2e} "
                            f"CFL={s.get('cfl_avg_median_last200')} stalled={s.get('stalled')} settled={s['settled']}\n")
            if s["converged"] and s["settled"] and not a.no_stop:
                rep["accepted_at"] = s
                for pid in ranks("SU2_CFD"):
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError:
                        pass
                rep["stopped"] = {"wall": time.strftime("%F %T"), "pids": sorted(alive)}
                print(f"monitor: the rule holds at inner iteration {s['inner_iter']}; SU2 stopped (SIGTERM)", flush=True)
                break
        time.sleep(a.every)
    rep["seconds"] = round(uptime() - t0)
    rep["last_state"] = state(hist, a.res_ref) if hist.exists() else None
    (a.folder / "monitor.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({k: v for k, v in rep.items() if k != "last_state"}, indent=1, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
