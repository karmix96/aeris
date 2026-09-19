#!/usr/bin/env python3
"""Run the high-fidelity batch on rented compute, under a budget it cannot exceed.

    cloud_batch_run.py --pilot              one gci_F and one gci_FF, then stop
    cloud_batch_run.py --budget-core-hours 600

The pilot is not optional politeness. Three numbers in the batch estimate are
extrapolations: the ANK-only memory law is a TWO-POINT fit stretched to four
times its largest input, the iteration growth is ONE measured ratio (203 to 262,
gci_C to gci_M) extrapolated two levels, and 9.7 s per Mcell-iteration was
measured only up to 1.17M cells. Above all of that sits a fourth: ANK-only is
PROVEN only to 1,172,856 cells, and it was chosen because Newton-Krylov froze at
that size with this project's lean preconditioner. At 2.3M and 4.7M cells it is
unproven. Two cases cost about 20 core-hours and settle all four.

Safety, each item from something that has already gone wrong here:

  budget      core-hours are counted and no case launches past the cap
  killswitch  a file on disk stops the batch without needing this process
  groups      children are killed by process GROUP; `pkill -f` matches the
              killing shell's own command line and has killed it
  disk        checked before each case, not after the writes fail
  memory      every case runs with the memory watch, which stops a run that
              pages rather than letting it finish at disk speed
  timing      monotonic, because a suspended host made a 74-minute solve look
              like a 403-minute stall
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import subprocess
import sys
import time
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import cloud_identity as ident  # noqa: E402

REPORTS = HERE / "reports"
#: Defect 23: forces for every non-reference geometry had been divided by index
#: 83's area. The area is looked up per geometry here and written into the
#: manifest, so a row that used the wrong one is visible rather than plausible.
AREAS_FILE = HERE / "reference_areas.json"
BATCH = REPORTS / "s8_cloud_batch_v2.json"
MESHES = HERE / "runs/s8_cloud"
OUT_ROOT = HERE / "runs/s8_hf"
KILLSWITCH = OUT_ROOT / "STOP"
LEDGER = OUT_ROOT / "ledger.json"

#: Free space that must remain after a case writes. A gci_FF volume solution is
#: about 1.2 GiB and the batch writes 44 of them.
DISK_FLOOR_GIB = 25.0


def disk_free_gib(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free / (1 << 30)


def load_ledger() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text())
        except ValueError:
            pass
    return {"schema": "aeris.s8.cloud_ledger.v1", "core_hours_spent": 0.0, "runs": {}}


def save_ledger(ledger: dict) -> None:
    ident.write_atomic(LEDGER, ledger)


def stopped() -> str | None:
    """A file, so a human can stop the batch without this process cooperating."""
    if KILLSWITCH.exists():
        return KILLSWITCH.read_text().strip() or "STOP file present"
    return None


def run_case(case: dict, *, ranks: int, env: dict, dry: bool) -> dict:
    """One solve, fully identified, judged on its artefacts."""
    index, level, alpha = case["index"], case["level"], case["alpha_deg"]
    out = OUT_ROOT / f"g{index}" / f"{level}_a{alpha:g}"
    out.mkdir(parents=True, exist_ok=True)
    mesh = MESHES / f"g{index}" / f"{level}_volume.cgns"

    physics = {"mach": 0.0837, "reynolds_length_m": 0.9, "temperature_K": 278.4,
               "alpha_deg": alpha}
    numerics = {"equationType": "RANS", "turbulenceModel": "SA", "useNKSolver": False,
                "L2Convergence": 1.0e-6, "MGCycle": "sg", "liftIndex": 3,
                "eddyVisInfRatio": 0.21, "ranks": ranks}

    watch = ident.Stopwatch()
    proc = None
    if dry:
        print(f"    [dry run] would solve {out.relative_to(OUT_ROOT)} on {mesh.name}")
    else:
        cmd = [env["mach_python"], str(HERE / "solve_s8.py"),
               "--grid", str(mesh), "--alpha", str(alpha), "--out", str(out),
               "--ranks", str(ranks), "--no-nk", "--watch-memory"]
        # start_new_session: the children get their own process GROUP, so they can
        # be killed as one without a pattern match that could match this process.
        proc = subprocess.Popen(cmd, stdout=open(out / "run.log", "w"),
                                stderr=subprocess.STDOUT, start_new_session=True)
    return {"case": case, "out": out, "mesh": mesh, "physics": physics,
            "numerics": numerics, "watch": watch, "proc": proc, "ranks": ranks}


def reap(job: dict) -> dict:
    """Turn a finished job into its manifest."""
    rc = job["proc"].returncode if job["proc"] is not None else None
    timing = job["watch"].read()
    case = job["case"]
    manifest = ident.run_manifest(
        out=job["out"], geometry_index=case["index"], level=case["level"],
        alpha_deg=case["alpha_deg"], mesh=job["mesh"], physics=job["physics"],
        numerics=job["numerics"], repo=ROOT, timing=timing, exit_code=rc,
        area_ref_m2=case.get("area_ref_m2"),
        extra={"predicted_minutes": case.get("predicted_minutes"),
               "predicted_core_hours": case.get("predicted_core_hours"),
               "cells": case.get("cells"), "memory_gib_predicted": case.get("memory_gib")})
    manifest["core_hours"] = round(job["ranks"] * timing["seconds"] / 3600.0, 3)
    return manifest


def pilot_report(runs: list[dict]) -> dict:
    """Did the three extrapolations survive contact, and did ANK-only converge?"""
    checks = []
    for m in runs:
        cells = (m.get("cells") or 0) / 1e6
        predicted_mem = m.get("memory_gib_predicted")
        out = OUT_ROOT / f"g{m['geometry_index']}" / f"{m['level']}_a{m['alpha_deg']:g}"
        mw = out / "memory_watch.json"
        peak = None
        if mw.exists():
            try:
                peak = json.loads(mw.read_text()).get("peak_rank_rss_sum_gib")
            except ValueError:
                peak = None
        res = out / "result.json"
        iters = None
        if res.exists():
            try:
                iters = json.loads(res.read_text()).get("iterations_completed")
            except ValueError:
                iters = None
        seconds = m["timing"]["seconds"]
        per_mcell_iter = (seconds * (m["numerics"]["ranks"] / 6.0) / (cells * iters)
                          if cells and iters else None)
        checks.append({
            "case": m["label"],
            "usable": m["verdict"]["usable"],
            "problems": m["verdict"]["problems"],
            "memory_predicted_gib": predicted_mem,
            "memory_peak_gib": peak,
            "memory_within_prediction": (peak is not None and predicted_mem is not None
                                         and peak <= predicted_mem),
            "iterations": iters,
            "seconds_per_mcell_iteration_at_6_ranks": (round(per_mcell_iter, 2)
                                                       if per_mcell_iter else None),
            "model_said": 9.7,
        })
    ok = all(c["usable"] for c in checks)
    return {"schema": "aeris.s8.cloud_pilot.v1", "all_usable": ok, "checks": checks,
            "release_the_rest": ok,
            "note": ("Release the remaining cases only when every case here is usable, peak "
                     "memory is inside the prediction, and seconds per Mcell-iteration is "
                     "near 9.7. ANK-only is unproven above 1.17M cells and this is the test.")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pilot", action="store_true",
                    help="one gci_F and one gci_FF, then stop and report")
    ap.add_argument("--budget-core-hours", type=float, default=600.0)
    ap.add_argument("--ranks", type=int, default=4,
                    help="4 is measured: 2.7 %% slower than 6 for 32 %% fewer core-hours")
    ap.add_argument("--cores", type=int, default=os.cpu_count() or 4,
                    help="physical cores available to the batch")
    ap.add_argument("--ram-gib", type=float, default=None,
                    help="RAM the batch may use; defaults to 85 %% of the machine's")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.ram_gib is None:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1 << 30)
        args.ram_gib = round(total * 0.85, 1)

    if not BATCH.exists():
        raise SystemExit(f"{BATCH} not found; run cloud_batch_v2.py first")
    batch = json.loads(BATCH.read_text())
    cases = batch["cases"]
    areas = {}
    if AREAS_FILE.exists():
        areas = json.loads(AREAS_FILE.read_text()).get("areas", {})
    missing = sorted({c["index"] for c in cases if str(c["index"]) not in areas})
    if missing:
        raise SystemExit(f"no recorded reference area for geometries {missing}. "
                         f"Defect 23 was forces divided by the wrong geometry's area; "
                         f"the batch does not start without every area on file.")
    for c in cases:
        c["area_ref_m2"] = areas[str(c["index"])]["half_area_m2"]
    if args.pilot:
        first_f = next(c for c in cases if c["level"] == "gci_F")
        first_ff = next(c for c in cases if c["level"] == "gci_FF")
        cases = [first_f, first_ff]
        print(f"PILOT: {len(cases)} cases, about "
              f"{sum(c['predicted_core_hours'] for c in cases):.0f} core-hours\n")

    import env_s8
    env = env_s8.resolve()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()
    done: list[dict] = []

    cores, ram = args.cores, args.ram_gib
    print(f"  scheduling on {cores} cores / {ram:.0f} GiB, {args.ranks} ranks per case\n")
    pending, running = list(cases), []

    def can_start(case) -> bool:
        used_cores = sum(j["ranks"] for j in running)
        used_ram = sum(j["case"]["memory_gib"] for j in running)
        return (used_cores + args.ranks <= cores
                and used_ram + case["memory_gib"] <= ram)

    while pending or running:
        # reap anything that has finished
        for job in list(running):
            if job["proc"] is not None and job["proc"].poll() is None:
                continue
            running.remove(job)
            manifest = reap(job)
            done.append(manifest)
            ledger["core_hours_spent"] = round(
                ledger["core_hours_spent"] + manifest["core_hours"], 3)
            label = manifest["label"]
            ledger["runs"][manifest["case_id"]] = {
                "label": label, "execution_id": manifest["execution_id"],
                "usable": manifest["verdict"]["usable"],
                "core_hours": manifest["core_hours"],
                "seconds": manifest["timing"]["seconds"]}
            save_ledger(ledger)
            v = manifest["verdict"]
            print(f"    done {label:24s} "
                  f"{'usable' if v['usable'] else 'NOT USABLE: ' + '; '.join(v['problems'])}"
                  f"   {manifest['core_hours']:.2f} core-h", flush=True)

        why = stopped()
        if why and pending:
            print(f"\nSTOPPED by killswitch: {why} -- letting {len(running)} running case(s) finish")
            pending = []

        # start whatever fits
        started_any = False
        for case in list(pending):
            if not can_start(case):
                continue
            spent = ledger["core_hours_spent"] + sum(
                j["case"].get("predicted_core_hours", 0.0) for j in running)
            predicted = case.get("predicted_core_hours", 0.0)
            if spent + predicted > args.budget_core_hours:
                if not running:
                    print(f"\nBUDGET: {spent:.1f} core-hours committed, this case needs "
                          f"{predicted:.1f}, cap is {args.budget_core_hours:.0f}. Stopping.")
                    pending = []
                break
            free = disk_free_gib(OUT_ROOT)
            if free < DISK_FLOOR_GIB:
                print(f"\nDISK: {free:.1f} GiB free, floor is {DISK_FLOOR_GIB}. Stopping.")
                pending = []
                break
            pending.remove(case)
            label = f"g{case['index']}/{case['level']}/a{case['alpha_deg']:g}"
            print(f"  start {label:24s} {case['memory_gib']:.1f} GiB, "
                  f"predicted {case.get('predicted_minutes', 0):.0f} min   "
                  f"[{len(running) + 1} running, {len(pending)} queued]", flush=True)
            running.append(run_case(case, ranks=args.ranks, env=env, dry=args.dry_run))
            started_any = True
        if running and not started_any:
            time.sleep(5 if not args.dry_run else 0)

    if args.pilot and done:
        report = pilot_report(done)
        ident.write_atomic(REPORTS / "s8_cloud_pilot.json", report)
        print(f"\n  pilot: {'PASS -- release the rest' if report['release_the_rest'] else 'HOLD'}")
        for c in report["checks"]:
            print(f"    {c['case']}: usable {c['usable']}  peak mem {c['memory_peak_gib']} "
                  f"vs predicted {c['memory_predicted_gib']} GiB  "
                  f"{c['seconds_per_mcell_iteration_at_6_ranks']} s/Mcell-iter (model 9.7)")
        print(f"  wrote {REPORTS / 's8_cloud_pilot.json'}")
    print(f"\n  core-hours spent this batch: {ledger['core_hours_spent']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
