"""The V7 night folder: copy one run's small files in, and rebuild summary.json from every run folder.

    python collect.py copy <run id> <case dir> <solver folder>     # adflow | adflow_fill0 | su2_sa | su2_sst_lm
    python collect.py summary                                       # -> ../summary.json, prints the run table

Every number comes from the copied files (result.json, rss.json, host.json, timing.json, history.csv,
forces_breakdown.dat, surface_flow.csv, results.json), never from memory.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

NIGHT = Path(__file__).resolve().parents[1]
STAGE = NIGHT.parents[2]                                        # Stage_3_volume_mesh
SMALL = ("result.json", "preflight.json", "rss.json", "rss.csv", "host.json", "host.csv", "timing.json",
         "lift_distribution.dat", "slices.dat", "history.csv", "forces_breakdown.dat")


def trim(src: Path, dst: Path, head: int, tail: int) -> None:
    lines = src.read_text(errors="replace").splitlines(keepends=True)
    if len(lines) <= head + tail:
        dst.write_text("".join(lines))
        return
    cut = len(lines) - head - tail
    dst.write_text("".join(lines[:head]) + f"\n[... {cut} lines left out: the first {head} and the last {tail} are kept ...]\n\n"
                   + "".join(lines[-tail:]))


def copy(run: str, case: str, sub: str) -> Path:
    c = STAGE / case
    d = NIGHT / run
    (d / sub).mkdir(parents=True, exist_ok=True)
    for f in ("case.json", "results.json", "results.md"):
        if (c / f).exists():
            shutil.copy2(c / f, d / f)
    for f in SMALL:
        if (c / sub / f).exists():
            shutil.copy2(c / sub / f, d / sub / f)
    if sub.startswith("adflow"):
        for f in sorted(c.glob(f"{sub}_*.txt")):                 # adflow_log.txt, adflow_preflight_log.txt, ...
            if f.name == f"{sub}_log.txt":
                trim(f, d / f.name, 0, 300)
            else:
                shutil.copy2(f, d / f.name)
    else:
        if (c / sub / "log.txt").exists():
            trim(c / sub / "log.txt", d / sub / "log.txt", 150, 300)
        for f in ("rss_log.txt", "host_log.txt"):
            if (c / sub / f).exists():
                shutil.copy2(c / sub / f, d / sub / f)
        if (c / f"{sub}_read_results.txt").exists():
            shutil.copy2(c / f"{sub}_read_results.txt", d / f"{sub}_read_results.txt")
        yp = yplus(c / sub / "surface_flow.csv", c / "case.json")
        if yp:
            (d / sub / "yplus.json").write_text(json.dumps(yp, indent=1))
    (d / "source.json").write_text(json.dumps({"run": run, "case_dir": case, "solver_folder": sub}, indent=1))
    return d


def yplus(csv: Path, case_json: Path) -> dict | None:
    """Q7: y+ over the wall from SU2's surface_flow.csv: largest, 99th percentile, median, where the largest sits."""
    if not csv.exists():
        return None
    import numpy as np
    import pandas as pd
    df = pd.read_csv(csv)
    df.columns = [k.strip().strip('"') for k in df.columns]
    col = next((k for k in df.columns if k.lower().replace("_", "") == "yplus"), None)
    if col is None:
        return {"error": f"no Y_Plus column in {csv.name}: {list(df.columns)}"}
    yp = df[col].to_numpy(float)
    x, y = df["x"].to_numpy(float), df["y"].to_numpy(float)
    i = int(np.argmax(yp))
    semi = json.loads(case_json.read_text())["references"]["semi_span"]
    near = np.abs(y - y[i]) <= 0.01 * semi                     # the wall points of that span station
    xle, xte = float(x[near].min()), float(x[near].max())
    return {"points": int(len(yp)), "max": float(yp[i]), "p99": float(np.percentile(yp, 99)),
            "median": float(np.median(yp)), "max_at_x_over_c": (float(x[i]) - xle) / (xte - xle),
            "max_at_y_over_semispan": float(y[i]) / semi, "column": col, "file": str(csv),
            "note": "x/c from the wall points within 1 % of the semi-span of the largest value"}


def forces_breakdown(p: Path) -> dict:
    """Total CL, CD, CMy and the pressure / friction parts of CD from SU2's forces_breakdown.dat."""
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(errors="replace").splitlines():
        s = line.strip()
        for key, name in (("Total CL:", "cl"), ("Total CD:", "cd"), ("Total CMy:", "cmy")):
            if s.startswith(key):
                parts = s.replace("|", " ").split()
                try:
                    out[name] = float(parts[2])
                    i = parts.index("Pressure")
                    out[name + "p"] = float(parts[i + 2])
                    j = parts.index("Friction")
                    out[name + "v"] = float(parts[j + 2])
                except (ValueError, IndexError):
                    pass
    return {k: v for k, v in out.items() if k in ("cl", "cd", "cmy", "cdp", "cdv")}


def jl(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def summarise(d: Path) -> dict:
    src = jl(d / "source.json") or {}
    sub = src.get("solver_folder", "")
    case = jl(d / "case.json") or {}
    res = jl(d / "results.json") or {}
    cells = case.get("cells")
    row = {"run": d.name, "case": src.get("case_dir"), "mesh": case.get("mesh"), "cells": cells,
           "alpha_deg": case.get("alpha_deg"), "solver_folder": sub}
    t = jl(d / sub / "timing.json") or {}
    rss = jl(d / sub / "rss.json") or {}
    host = jl(d / sub / "host.json") or {}
    row |= {"wall_seconds": t.get("wall_seconds"), "exit": t.get("exit"), "start": t.get("start"), "end": t.get("end"),
            "watchdog_peak_gib": rss.get("peak_rss_sum_gib"), "watchdog_min_available_gib": rss.get("min_available_gib"),
            "watchdog_killed": rss.get("killed"), "host_min_free_gib": host.get("min_free_gib"),
            "host_max_pagefile_gib": host.get("max_pagefile_gib"),
            "host_pagefile_at_start_gib": (host.get("at_start") or {}).get("pagefile_gib"),
            "host_max_vmmem_gib": host.get("max_vmmem_gib"), "host_killed": host.get("killed")}
    if sub.startswith("adflow"):
        r = jl(d / sub / "result.json")
        key = "ADflow SA"
        row |= {"solver": "ADflow", "model": "SA"}
        if r:
            m = r.get("memory", {})
            rr = r.get("relative_residual")
            row |= {"iterations": r.get("iterations"), "relative_residual": rr,
                    "residual_drop_orders": -math.log10(rr) if rr and rr > 0 else None,
                    "converged_flag": r.get("converged"), "coefficients": r.get("coefficients"),
                    "adflow_peak_gib_sum": m.get("peak_rss_gib_sum"), "adflow_peak_largest_rank_gib": m.get("peak_rss_gib_largest_rank"),
                    "law_ank_only_gib": m.get("law_ank_only_gib"), "law_ank_then_nk_gib": m.get("law_ank_then_nk_gib"),
                    "overrides": r.get("overrides"), "extras": r.get("extras"), "solver_seconds": r.get("seconds")}
        if sub == "adflow" and key in res:
            row |= {"verdict": res[key].get("verdict"), "why": res[key].get("why"),
                    "settled": res[key].get("settled"), "cd_wander_counts": res[key].get("cd_wander_counts"),
                    "cl_wander_rel": res[key].get("cl_wander_rel")}
    else:
        key = {"su2_sa": "SU2 SA", "su2_sst_lm": "SU2 SST+LM"}.get(sub)
        row |= {"solver": "SU2", "model": "SA" if sub == "su2_sa" else "SST+LM"}
        fb = forces_breakdown(d / sub / "forces_breakdown.dat")
        if key in res and res[key].get("verdict") != "not run":
            v = res[key]
            row |= {"iterations": v.get("iterations"), "residual_drop_orders": v.get("orders_dropped"),
                    "rms_rho_final": v.get("rms_rho_final"), "converged_flag": v.get("converged"),
                    "verdict": v.get("verdict"), "why": v.get("why"), "settled": v.get("settled"),
                    "cd_wander_counts": v.get("cd_wander_counts"), "cl_wander_rel": v.get("cl_wander_rel"),
                    "coefficients": v.get("coefficients")}
        if fb:
            row["forces_breakdown"] = fb
        row["yplus"] = jl(d / sub / "yplus.json")
    peak = row.get("adflow_peak_gib_sum") or row.get("watchdog_peak_gib")
    if peak and cells:
        row["gib_per_million_cells"] = peak / (cells / 1e6)
    if row.get("wall_seconds") and row.get("iterations"):
        row["seconds_per_iteration"] = row["wall_seconds"] / row["iterations"]
    if row.get("wall_seconds") and cells:
        row["minutes_per_million_cells"] = row["wall_seconds"] / 60 / (cells / 1e6)
    return row


def main() -> int:
    if len(sys.argv) >= 5 and sys.argv[1] == "copy":
        print(copy(sys.argv[2], sys.argv[3], sys.argv[4]))
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "summary":
        rows = [summarise(d) for d in sorted(NIGHT.iterdir()) if d.is_dir() and (d / "source.json").exists()]
        extra = jl(NIGHT / "summary_extra.json") or {}
        (NIGHT / "summary.json").write_text(json.dumps({"runs": rows} | extra, indent=1))
        for r in rows:
            c = r.get("coefficients") or {}
            print(r["run"], r.get("verdict"), r.get("iterations"), r.get("wall_seconds"), r.get("gib_per_million_cells"),
                  {k: c.get(k) for k in ("cl", "cd", "cmy")})
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
