"""End an SU2 run once the plan's own acceptance rule is met (written for the V7 night run of 11-12 Nov 2026).

The case files stop SU2 at an absolute density residual of 1e-12 or at the iteration budget; the acceptance rule of
solve/read_results.py (6 orders of density residual and settled forces) is usually met long before that, so a run
would use its whole cap for nothing. This watcher reads history.csv every --every seconds and applies the rule with
read_results.py's own code (imported, not copied). Once it holds, it waits for SU2's next output write (surface,
restart and forces breakdown: OUTPUT_WRT_FREQ iterations), so the files on disk hold a state at or after acceptance,
then sends SIGTERM to the SU2_CFD ranks; with --immediate it stops at once, since SU2 8.5.0 writes all its
output files on SIGTERM. No solver setting changes. The record goes to <folder>/accept_stop.json.

    python su2_accept_stop.py --folder runs/<case>/su2_sa --write-every 500 &
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

SOLVE = Path(__file__).resolve().parents[4] / "solve"
sys.path.insert(0, str(SOLVE))
from read_results import settled                               # noqa: E402  the plan's rule, as written
from rss_watch import ranks                                     # noqa: E402  the same process matching


#: written together every OUTPUT_WRT_FREQ iterations (the case files' OUTPUT_FILES and the forces breakdown)
OUTPUTS = ("restart.dat", "surface_flow.csv", "forces_breakdown.dat")


def state(hist: Path) -> dict | None:
    import numpy as np
    import pandas as pd
    try:
        df = pd.read_csv(hist)
    except Exception:
        return None
    df.columns = [c.strip().strip('"') for c in df.columns]
    if len(df) < 2 or "rms[Rho]" not in df:
        return None
    df = df.apply(pd.to_numeric, errors="coerce").dropna(subset=["rms[Rho]", "CL", "CD"])
    rho = df["rms[Rho]"].to_numpy(float)
    drop = float(rho.max() - rho[-1])
    st = settled(df["CL"].to_numpy(float), df["CD"].to_numpy(float))
    it = int(df["Inner_Iter"].iloc[-1]) if "Inner_Iter" in df else len(df) - 1
    return {"rows": int(len(df)), "inner_iter": it, "rms_rho": float(rho[-1]), "orders_dropped": drop,
            "converged": bool(drop >= 6.0 or rho[-1] <= -12.0), "settled": bool(st.get("settled")), "settled_detail": st}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--folder", type=Path, required=True)
    p.add_argument("--every", type=float, default=60.0)
    p.add_argument("--write-every", type=int, default=500, help="OUTPUT_WRT_FREQ of the case file")
    p.add_argument("--wait", type=float, default=600.0)
    p.add_argument("--immediate", action="store_true",
                   help="stop as soon as the rule holds: SU2 8.5.0 catches SIGTERM and writes all its output files "
                        "('Interrupt signal (15) received, saving files and exiting', B1, 12 Nov 01:26)")
    a = p.parse_args(argv)
    hist = a.folder / "history.csv"
    rep = {"folder": str(a.folder), "rule": "solve/read_results.py: 6 orders of rms[Rho] (or 1e-12) and settled forces",
           "accepted_at": None, "stopped": None}
    t0, seen = time.time(), False
    while True:
        alive = ranks("SU2_CFD")
        if alive:
            seen = True
        elif seen or time.time() - t0 > a.wait:
            break
        s = state(hist) if hist.exists() else None
        if s and s["converged"] and s["settled"]:
            if rep["accepted_at"] is None:
                rep["accepted_at"] = s | {"wall": time.strftime("%F %T"), "epoch": time.time()}
                print(f"accept_stop: the rule holds at inner iteration {s['inner_iter']}; waiting for the next output write", flush=True)
            t_acc = rep["accepted_at"]["epoch"]
            outs = [a.folder / f for f in OUTPUTS]
            fresh = all(f.exists() and f.stat().st_mtime > t_acc for f in outs)
            quiet = fresh and time.time() - max(f.stat().st_mtime for f in outs) > 30
            if quiet or a.immediate:
                last = state(hist) or s
                for pid in ranks("SU2_CFD"):
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError:
                        pass
                rep["stopped"] = last | {"wall": time.strftime("%F %T"), "pids": sorted(alive)}
                print(f"accept_stop: stopped SU2 at inner iteration {last['inner_iter']}", flush=True)
                break
        time.sleep(a.every)
    rep["seconds"] = round(time.time() - t0)
    (a.folder / "accept_stop.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
