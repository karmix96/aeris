"""The Windows host's side of one solver run under WSL2 (written for the V7 night run of 11-12 Nov 2026).

solve/rss_watch.py sees only the WSL VM: its MemAvailable and its swap. WSL2's memory is backed by the Windows
host, and on this desktop the host has 15.86 GiB in all, so WSL can believe it has memory that Windows must page
to find. That paging is invisible inside WSL. This script samples the host every --every seconds through
powershell.exe: free physical memory, pagefile in use, the WSL VM (vmmem) and Memory Compression working sets.

Kill rule, the host twin of rss_watch's swap rule: when the host pagefile in use grows by more than --max-page-gib
over its value at the start, SIGTERM the matching ranks (found exactly as rss_watch finds them) and say so.

    HOST_WATCH_MATCH=run_adflow.py python host_watch.py --out runs/<case>/adflow/host.csv &

The match string comes from the environment, not the command line: rss_watch counts every process whose command
line holds its match string (only its own name is excluded), so a --match here would make this script a "rank".
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SOLVE = Path(__file__).resolve().parents[4] / "solve"           # Stage_3_volume_mesh/solve
sys.path.insert(0, str(SOLVE))
from rss_watch import ranks                                     # noqa: E402  the same process matching

PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
QUERY = ("$o=Get-CimInstance Win32_OperatingSystem; $p=(Get-CimInstance Win32_PageFileUsage | Measure-Object "
         "CurrentUsage -Sum).Sum; $v=(Get-Process vmmem,vmmemWSL -ErrorAction SilentlyContinue | Measure-Object "
         "WorkingSet64 -Sum).Sum; $c=(Get-Process 'Memory Compression' -ErrorAction SilentlyContinue | "
         "Measure-Object WorkingSet64 -Sum).Sum; [string]::Format([cultureinfo]::InvariantCulture, "
         "'{0:F3};{1:F3};{2:F3};{3:F3}', $o.FreePhysicalMemory/1MB, $p/1024, $v/1GB, $c/1GB)")


def host() -> dict | None:
    """free physical, pagefile in use, vmmem, Memory Compression [GiB]; None if powershell does not answer."""
    try:
        r = subprocess.run([PS, "-NoProfile", "-Command", QUERY], capture_output=True, text=True, timeout=45)
        f = [float(x) for x in r.stdout.strip().replace("\r", "").splitlines()[-1].split(";")]
        if len(f) != 4:
            return None
        return dict(zip(("free_gib", "pagefile_gib", "vmmem_gib", "compression_gib"), f))
    except Exception:
        return None


class Stop(Exception):
    pass


def _stop(signum, frame):
    raise Stop()


def main(argv=None) -> int:
    signal.signal(signal.SIGTERM, _stop)                       # stopped from outside: still write the record
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--match", default=os.environ.get("HOST_WATCH_MATCH"),
                   help="default: $HOST_WATCH_MATCH (keep the match string off this command line)")
    p.add_argument("--out", required=True)
    p.add_argument("--every", type=float, default=60.0)
    p.add_argument("--wait", type=float, default=600.0)
    p.add_argument("--gone", type=float, default=60.0)
    p.add_argument("--max-page-gib", type=float, default=2.0)
    a = p.parse_args(argv)
    if not a.match:
        p.error("set HOST_WATCH_MATCH")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    h0 = host() or {}
    rep = {"match": a.match, "at_start": h0, "min_free_gib": h0.get("free_gib"), "max_pagefile_gib": h0.get("pagefile_gib"),
           "max_vmmem_gib": h0.get("vmmem_gib"), "max_compression_gib": h0.get("compression_gib"), "killed": None,
           "samples": 0, "failed_samples": 0}
    t0, seen, gone_since = time.time(), False, None
    try:
        loop(a, out, h0, rep, t0)
    except Stop:
        rep["stopped_from_outside"] = True
    rep["seconds"] = round(time.time() - t0)
    rep["note"] = "Windows host, sampled through powershell.exe; WSL's own view is in rss.json"
    out.with_suffix(".json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1), flush=True)
    return 0


def loop(a, out: Path, h0: dict, rep: dict, t0: float) -> None:
    seen, gone_since = False, None
    with open(out, "w") as f:
        f.write("seconds,ranks,free_gib,pagefile_gib,vmmem_gib,compression_gib\n")
        while True:
            r = ranks(a.match)
            if r:
                seen, gone_since = True, None
                h = host()
                if h is None:
                    rep["failed_samples"] += 1
                else:
                    rep["samples"] += 1
                    for k, key, fn in (("free_gib", "min_free_gib", min), ("pagefile_gib", "max_pagefile_gib", max),
                                       ("vmmem_gib", "max_vmmem_gib", max), ("compression_gib", "max_compression_gib", max)):
                        rep[key] = h[k] if rep[key] is None else fn(rep[key], h[k])
                    f.write(f"{time.time() - t0:.0f},{len(r)},{h['free_gib']:.3f},{h['pagefile_gib']:.3f},"
                            f"{h['vmmem_gib']:.3f},{h['compression_gib']:.3f}\n")
                    f.flush()
                    grew = h["pagefile_gib"] - h0.get("pagefile_gib", h["pagefile_gib"])
                    if grew > a.max_page_gib and rep["killed"] is None:
                        for pid in ranks(a.match):
                            try:
                                os.kill(pid, signal.SIGTERM)
                            except OSError:
                                pass
                        rep["killed"] = {"at_seconds": round(time.time() - t0),
                                         "why": f"host pagefile grew by {grew:.1f} GiB", "pids": sorted(r)}
                        print(f"host_watch: killed {a.match} ({rep['killed']['why']})", flush=True)
            elif seen:
                gone_since = gone_since or time.time()
                if time.time() - gone_since >= a.gone:
                    break
            elif time.time() - t0 > a.wait:
                break
            time.sleep(a.every)


if __name__ == "__main__":
    raise SystemExit(main())
