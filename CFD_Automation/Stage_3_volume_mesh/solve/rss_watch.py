"""Watch one solver run: the summed resident memory of its ranks, and the machine's available memory and swap, every
N seconds. Kills the run before the machine runs out of memory (on WSL an out-of-memory can take the whole session
down, the agent included). Plain Python, no packages; Linux /proc only.

    python solve/rss_watch.py --match SU2_CFD --out runs/<case>/su2_sa/rss.csv &              # start it with the run
    python solve/rss_watch.py --match run_adflow.py --out runs/<case>/adflow/rss.csv &

It waits up to --wait seconds for the first matching process, then samples until none has been left for --gone
seconds, and writes the peak into <out>.json. Kill rule: when the available memory falls below --min-available of the total, or the swap in use
grows by more than --max-swap-gib, it sends SIGTERM to the matching processes (and says so in the json).
Wrappers (bash, mpirun, timeout, time, ...) and this script itself are never counted or killed.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

WRAPPERS = {"bash", "sh", "zsh", "dash", "timeout", "time", "mpirun", "mpiexec", "mpiexec.hydra", "hydra_pmi_proxy",
            "orted", "orterun", "prterun", "prted", "mpirun.openmpi", "mpiexec.openmp", "mpirun.mpich", "mpiexec.mpich",
            "srun", "nohup", "tee", "grep", "awk", "ps"}         # /proc/<pid>/comm holds at most 15 characters


def meminfo() -> dict:
    out = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        out[k] = int(v.split()[0]) / 1024.0 ** 2            # GiB
    return out


def ranks(match: str) -> dict[int, float]:
    """pid -> resident memory [GiB] of every process whose command line holds `match` (no wrappers, not this one)."""
    me, found = os.getpid(), {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit() or int(d.name) == me:
            continue
        try:
            cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            comm = (d / "comm").read_text().strip()
            if match not in cmd or "rss_watch" in cmd or comm in WRAPPERS:
                continue
            for line in (d / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    found[int(d.name)] = int(line.split()[1]) / 1024.0 ** 2
        except (OSError, ValueError):
            continue                                           # the process ended while we looked
    return found


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--match", required=True, help="a string in the ranks' command line: SU2_CFD, run_adflow.py")
    p.add_argument("--out", required=True, help="the csv of samples; the peak goes to the same name with .json")
    p.add_argument("--every", type=float, default=10.0, help="seconds between samples")
    p.add_argument("--wait", type=float, default=600.0, help="seconds to wait for the first matching process")
    p.add_argument("--gone", type=float, default=30.0, help="stop once no matching process is left for this long")
    p.add_argument("--min-available", type=float, default=0.08, help="kill below this share of the total memory")
    p.add_argument("--max-swap-gib", type=float, default=2.0, help="kill when the swap in use grows by more than this")
    a = p.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    m0 = meminfo()
    swap0 = m0.get("SwapTotal", 0.0) - m0.get("SwapFree", 0.0)
    rep = {"match": a.match, "mem_total_gib": m0["MemTotal"], "swap_total_gib": m0.get("SwapTotal", 0.0),
           "swap_used_at_start_gib": swap0, "peak_rss_sum_gib": 0.0, "peak_ranks": 0, "min_available_gib": m0["MemAvailable"],
           "killed": None, "samples": 0}
    t0, seen, gone_since = time.time(), False, None
    with open(out, "w") as f:
        f.write("seconds,ranks,rss_sum_gib,available_gib,swap_used_gib\n")
        while True:
            r, m = ranks(a.match), meminfo()
            swap = m.get("SwapTotal", 0.0) - m.get("SwapFree", 0.0)
            if r:
                seen, gone_since = True, None
                s = sum(r.values())
                rep["samples"] += 1
                if s > rep["peak_rss_sum_gib"]:
                    rep["peak_rss_sum_gib"], rep["peak_ranks"] = s, len(r)
                rep["min_available_gib"] = min(rep["min_available_gib"], m["MemAvailable"])
                f.write(f"{time.time() - t0:.0f},{len(r)},{s:.3f},{m['MemAvailable']:.3f},{swap:.3f}\n")
                f.flush()
                low = m["MemAvailable"] < a.min_available * m["MemTotal"]
                if (low or swap - swap0 > a.max_swap_gib) and rep["killed"] is None:
                    why = (f"available {m['MemAvailable']:.1f} GiB < {a.min_available:.0%} of {m['MemTotal']:.1f}"
                           if low else f"swap grew by {swap - swap0:.1f} GiB")
                    for pid in r:
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except OSError:
                            pass
                    rep["killed"] = {"at_seconds": round(time.time() - t0), "why": why, "pids": sorted(r)}
                    print(f"rss_watch: killed {a.match} ({why})", flush=True)
            elif seen:
                gone_since = gone_since or time.time()
                if time.time() - gone_since >= a.gone:
                    break
            elif time.time() - t0 > a.wait:
                break
            time.sleep(a.every)
    rep["seconds"] = round(time.time() - t0)
    rep["note"] = "summed VmRSS of the matching ranks (wrappers left out); sampled, so the true peak can be a little higher"
    out.with_suffix(".json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
