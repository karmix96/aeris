#!/usr/bin/env python
"""Choose the grid-refinement family from ACTUAL available memory, and say so.

    .venv/bin/python .../select_levels.py --out reports/s8_level_selection.json

PLAN_desktop_campaign.md 2.1, made executable.  The plan's rule is:

    available >= 26 GiB   ->  gci_C / gci_M / gci_F        the best family
    available 14-26 GiB   ->  gci_C / gci_M / gci_MF       weaker: r falls to ~1.13
    available <  14 GiB   ->  two levels only.  A TREND, NOT A GCI.  Say so.

Why this is a script and not a number in a document
---------------------------------------------------
The distinction the plan is protecting is between INSTALLED and AVAILABLE
memory.  `gci_M` needs 12.0 GiB; a "16 GB machine" does not have 16 GiB free
once the OS, the MPI runtime, Python and the filesystem cache are counted, and
an ADflow run that reaches the ceiling does not fail cleanly -- it swaps, and a
swapping run produces the right answer after an arbitrarily long time, or gets
OOM-killed after hours with nothing written.  Neither outcome is a result.

This host is also a WSL2 guest, where "installed" is ambiguous in a third way:
the guest's own /proc/meminfo reports the .wslconfig cap, not the Windows host's
physical memory, and raising the cap cannot conjure memory the host does not
have.  Both numbers are reported, because a plan that says "find a bigger
machine" needs to know whether THIS machine could become one.

Memory law: 1.51 GiB + 9.46 GiB per million cells, from two clean measurements
with NK engaged (measure_memory.py).  It reproduces the three verified builds to
better than 0.1 GiB, which is why it is trusted to extrapolate one rung.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: MEASURED cell counts.  Not estimated: every one of these came off a build.
#: gci_C/M/F are PLAN 2; gci_CC is the level generated and rejected as too
#: coarse to be credibly asymptotic for a wall-resolved BWB.
CELLS = {
    "gci_CC": 299_000,
    "gci_C": 567_256,
    "gci_M": 1_111_152,
    "gci_F": 2_217_680,
}
#: gci_MF has never been built here.  Its count is estimated from the h-law,
#: cells ~ r^3, and is flagged as an estimate wherever it is used.
CELLS_ESTIMATED = {"gci_MF": 1_600_000, "gci_FF": 4_700_000}  # superseded: built 2026-09-11 at 4,504,420

MEM_BASE_GIB = 1.51
MEM_PER_MCELL_GIB = 9.46

#: PLAN 2.1's thresholds, verbatim.
THREE_LEVEL_GIB = 26.0
FALLBACK_GIB = 14.0

#: How much of `available` to leave alone.  A solve that uses every last byte is
#: one page-cache eviction away from swapping, and the plan's own memory numbers
#: were taken with nothing else running.
HEADROOM_GIB = 0.5

#: A level whose predicted requirement lands within this much of the budget is
#: MARGINAL, not refused.  The memory law is a two-point fit, not a guarantee,
#: and the difference between "11.8 available, 12.0 predicted" and a genuine
#: refusal is a measurement, not an inequality.  A marginal level is allowed to
#: run only under an observed-RSS watchdog (run_campaign.py --watch-memory),
#: which aborts on sustained swap rather than discovering it eight hours later.
MARGINAL_BAND_GIB = 1.5


def memory_gib(cells: int) -> float:
    return MEM_BASE_GIB + MEM_PER_MCELL_GIB * cells / 1.0e6


def available_gib() -> float:
    text = Path("/proc/meminfo").read_text()
    kb = int(re.search(r"^MemAvailable:\s+(\d+) kB", text, re.M).group(1))
    return kb / 1024.0 / 1024.0


def wsl_host_gib() -> dict:
    """Physical memory of the Windows host, when this is a WSL2 guest.

    Inside WSL, MemTotal is the .wslconfig cap.  If the cap is the binding
    constraint the answer is "edit .wslconfig"; if the host is, the answer is
    "different machine", and those are very different recommendations.
    """
    if "microsoft" not in Path("/proc/version").read_text().lower():
        return {"is_wsl": False}
    out: dict = {"is_wsl": True}
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
            capture_output=True, text=True, timeout=60,
        )
        out["host_physical_gib"] = int(proc.stdout.strip()) / 1024**3
    except Exception as exc:  # noqa: BLE001 - absence is reported, not fatal
        out["host_physical_gib"] = None
        out["host_probe_error"] = f"{type(exc).__name__}: {exc}"
    for path in Path("/mnt/c/Users").glob("*/.wslconfig"):
        out["wslconfig"] = str(path)
        out["wslconfig_text"] = path.read_text()
        break
    return out


def select(available: float, host: dict) -> dict:
    budget = available - HEADROOM_GIB
    fits = {n: memory_gib(c) for n, c in {**CELLS, **CELLS_ESTIMATED}.items()}
    all_cells = {**CELLS, **CELLS_ESTIMATED}

    def verdict(g: float) -> str:
        if g <= budget:
            return "fits"
        if g <= budget + MARGINAL_BAND_GIB:
            return "marginal"
        return "refused"

    out = {
        "available_gib": available,
        "headroom_gib": HEADROOM_GIB,
        "budget_gib": budget,
        "memory_law": f"{MEM_BASE_GIB} GiB + {MEM_PER_MCELL_GIB} GiB per million cells",
        "marginal_band_gib": MARGINAL_BAND_GIB,
        "level_memory": {n: {"cells": all_cells[n],
                             "cells_measured": n in CELLS,
                             "memory_gib": round(g, 2),
                             "verdict": verdict(g)}
                         for n, g in sorted(fits.items(), key=lambda kv: kv[1])},
        "host": host,
    }

    if available >= THREE_LEVEL_GIB:
        out.update(selected_levels=["gci_C", "gci_M", "gci_F"], n_levels=3, study="GCI",
                   rule="PLAN 2.1: available >= 26 GiB",
                   statement="Three levels, r ~ 1.251 and 1.259. A grid-convergence "
                             "index with an observed order and an uncertainty band.")
    elif available >= FALLBACK_GIB:
        out.update(selected_levels=["gci_C", "gci_M", "gci_MF"], n_levels=3, study="GCI_WEAKENED",
                   rule="PLAN 2.1: available 14-26 GiB, gci_F does not fit",
                   statement="Three levels, but r falls to about 1.13 between the top "
                             "two. A small ratio makes the observed order noisy: p is "
                             "inferred from differences that shrink with r. This is a "
                             "GCI, and it is a weak one. PLAN 2.1: prefer a bigger machine.")
    else:
        two = [n for n in ("gci_C", "gci_M") if verdict(fits[n]) != "refused"]
        out.update(selected_levels=two, n_levels=len(two), study="TREND_NOT_GCI",
                   rule="PLAN 2.1: available < 14 GiB",
                   statement="TWO LEVELS ONLY. This is a refinement TREND, not a "
                             "grid-convergence index. Two points give a direction and "
                             "a magnitude of movement. They do NOT give an observed "
                             "order of accuracy, a Richardson extrapolation, or an "
                             "uncertainty band -- all three need a third point. Report "
                             "it as a trend and say the band is absent.")
        if len(two) < 2:
            out["statement"] += (" Worse: fewer than two levels fit. There is no "
                                 "refinement study to run on this host at all.")
        marginal = [n for n in two if verdict(fits[n]) == "marginal"]
        if marginal:
            out["marginal_levels"] = marginal
            out["statement"] += (
                f" {', '.join(marginal)} is MARGINAL: predicted "
                f"{max(fits[n] for n in marginal):.1f} GiB against a "
                f"{budget:.1f} GiB budget. The memory law is a two-point fit, so "
                f"that gap is not a refusal and it is not a pass either -- it is a "
                f"measurement waiting to be taken. Run it under "
                f"run_campaign.py --watch-memory, which samples resident set size "
                f"and swap and aborts on sustained paging, rather than finding out "
                f"after eight hours that the answer came from disk.")

    if host.get("is_wsl") and host.get("host_physical_gib"):
        needed = memory_gib(CELLS["gci_F"]) + HEADROOM_GIB
        out["can_this_host_become_bigger"] = (
            f"No. gci_F needs {needed:.1f} GiB and the Windows host has "
            f"{host['host_physical_gib']:.2f} GiB of physical memory in total, so no "
            f".wslconfig change reaches it. A third level needs a different machine."
            if host["host_physical_gib"] < needed else
            f"Possibly. gci_F needs {needed:.1f} GiB and the Windows host has "
            f"{host['host_physical_gib']:.2f} GiB physical; raising .wslconfig memory "
            f"may reach it, at the cost of what Windows keeps for itself."
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--assume-available-gib", type=float, default=None,
                    help="override the measured figure, to see what a bigger "
                         "machine would select. Recorded as an override.")
    args = ap.parse_args()

    host = wsl_host_gib()
    available = args.assume_available_gib or available_gib()
    report = select(available, host)
    if args.assume_available_gib:
        report["available_gib_source"] = "OVERRIDDEN on the command line, not measured"

    print(f"available memory: {available:.2f} GiB"
          f"{'  (OVERRIDDEN)' if args.assume_available_gib else ''}")
    if host.get("is_wsl"):
        h = host.get("host_physical_gib")
        print(f"  WSL2 guest; Windows host physical memory "
              f"{f'{h:.2f} GiB' if h else 'unknown'}")
    print(f"budget after {HEADROOM_GIB} GiB headroom: {report['budget_gib']:.2f} GiB\n")
    print(f"{'level':>8}{'cells':>12}{'memory GiB':>13}   verdict")
    for name, info in report["level_memory"].items():
        mark = "" if info["cells_measured"] else "   (cells ESTIMATED)"
        print(f"{name:>8}{info['cells']:>12,}{info['memory_gib']:>13.2f}   "
              f"{info['verdict']}{mark}")
    print(f"\nrule fired: {report['rule']}")
    print(f"selected:   {' '.join(report['selected_levels']) or '(nothing)'}"
          f"   -> {report['study']}")
    print(f"\n{report['statement']}")
    if "can_this_host_become_bigger" in report:
        print(f"\n{report['can_this_host_become_bigger']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
