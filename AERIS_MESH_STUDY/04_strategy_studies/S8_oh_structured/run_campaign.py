#!/usr/bin/env python
"""Drive the S8 desktop campaign: PLAN_desktop_campaign.md, made executable.

    .venv/bin/python .../run_campaign.py build       --levels gci_C gci_M
    .venv/bin/python .../run_campaign.py regression                 # 3.2, alone
    .venv/bin/python .../run_campaign.py sweep       --levels gci_C gci_M
    .venv/bin/python .../run_campaign.py farfield                   # 2.2
    .venv/bin/python .../run_campaign.py pilot       --level gci_C
    .venv/bin/python .../run_campaign.py status

Why a driver and not the shell loops in the plan
------------------------------------------------
The plan's loops are correct and would work.  What they cannot carry is the
four rules in section 0 that this project paid for, each of which is a property
of HOW the runs are sequenced rather than of any one run:

0.2  One measurement at a time, on an otherwise idle machine.  A memory probe
     over a live rank sweep read 11.86 GiB for something that was not, and the
     wall-guard's negative test corrupted index 3 of a 100-design screen because
     it mutated march_o.py inside the ~40 s window that design was building in.
     -> an exclusive lock held for the whole of every run, and a refusal, not a
        queue, when a second run tries to start.

0.3  Exit code 0 does not mean success.  ADflow handles SIGTERM cleanly and
     wrote "exit": 0 for a run killed at iteration 1853 of 8000.
     -> every run is judged by convergence_gate.py on its own log, never by its
        exit status, and the gate verdict is what gets recorded.

3.2  The regression run goes first and ALONE, and a second-decimal shift in CD
     stops the campaign.
     -> `sweep` refuses to start until `regression` has passed, and `regression`
        writes a verdict file that says so.  Not a printed warning: a file the
        next stage reads.

2.1  A marginal grid level is a measurement, not an inequality.  gci_M is
     predicted at 12.0 GiB against 11.8 available on this host.
     -> --watch-memory samples resident set and swap throughout and aborts on
        SUSTAINED paging, so a level that does not fit costs minutes rather than
        finishing eight hours later with an answer that came off the disk.

Resumability is the fifth reason.  A run whose directory already holds a
result.json is skipped, so an interrupted campaign continues instead of
restarting, and no run is ever silently repeated on top of its own output.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

import env_s8  # noqa: E402

ARTIFACTS = REPO / "AERIS_MESH_STUDY/artifacts"
REPORTS = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports"
POLICY = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/POLICY.yaml"
GCI83 = ARTIFACTS / "s8_gci83"
CFD = ARTIFACTS / "s8_cfd"
PILOT = ARTIFACTS / "s8_pilot"
LOCK = ARTIFACTS / ".s8_campaign.lock"
VERDICT = REPORTS / "s8_regression_verdict.json"
REFERENCE_AREAS = HERE / "reference_areas.json"


def reference_half_area(index: int) -> float:
    """This geometry's own planform half-area, from the geometry, not the mesh.

    Defect 23. solve_s8.py's --area-ref default is index 83's area, and nothing
    passed anything else, so all ten pilot geometries were normalised by it:
    their own areas span -24.6 to +30.7 per cent of it. The forces were right and
    every coefficient of nine geometries was wrong, and it was invisible because
    the one geometry everything was checked on was the one it happened to fit.

    Fail-closed: a geometry with no recorded area is refused, never quietly given
    index 83's. And it comes from the GEOMETRY so it is identical at every grid
    level -- a per-mesh area differs between levels and would plant a fake
    grid-independent offset inside the GCI the fine levels exist to compute.
    """
    entry = json.loads(REFERENCE_AREAS.read_text())["areas"].get(str(index))
    if entry is None:
        raise SystemExit(f"no reference area for geometry {index} in {REFERENCE_AREAS}. "
                         f"Refusing to fall back to index 83's area -- that is defect 23.")
    return float(entry["half_area_m2"])

ALPHAS = (-2.0, 0.0, 4.0, 8.0)
REFERENCE_INDEX = 83
POLICY_EXCEPTION = "run-s8-campaign"

#: PLAN 3.2.  The pre-fix oh_L3 sweep, kept as a REGRESSION REFERENCE ONLY.
#: Nothing from that sweep may be quoted as a result: it ran on meshes the frame
#: fix destroyed.  Its value here is that the frame change alters the far field
#: and not the wing, so the forces should barely move; a large shift means
#: something other than the frame changed.
PREFIX_REFERENCE = {"cl": -0.159963, "cd": 0.020838,
                    "cdp": 0.011841, "cdv": 0.008996, "cmy": 0.001280}
#: "A shift in the third or fourth decimal of CD is the mesh. A shift in the
#: second is a problem -- stop."  0.005 is the smallest shift that changes the
#: second decimal digit.
CD_ABORT = 0.005
CD_NOTE = 0.0005


# --------------------------------------------------------------------------- #
# authorization

def check_authorization() -> dict:
    """POLICY.yaml must carry a live exception for this work.  Fail closed."""
    import yaml
    policy = yaml.safe_load(POLICY.read_text())
    heavy = policy.get("heavy_work", {})
    exceptions = heavy.get("exceptions", {})
    if POLICY_EXCEPTION not in exceptions:
        raise SystemExit(
            f"POLICY.yaml has no heavy_work.exceptions.{POLICY_EXCEPTION}.\n"
            f"Heavy work is blocked: {heavy.get('reason', '')!r}\n"
            f"This campaign needs its own signed entry (PLAN section 6). Not running."
        )
    entry = exceptions[POLICY_EXCEPTION]
    detail = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification" / entry["policy"]
    if not detail.exists():
        raise SystemExit(f"the policy file {detail} referenced by POLICY.yaml is missing.")
    signed = yaml.safe_load(detail.read_text()).get("authorization", {})
    if signed.get("status") != "AUTHORIZED" or not signed.get("authorized_by"):
        raise SystemExit(f"{detail} is not signed: authorization {signed!r}. Not running.")
    return {"exception": POLICY_EXCEPTION, "policy": str(detail),
            "authorized_by": signed["authorized_by"],
            "authorized_on": str(signed.get("authorized_on")),
            "scope": entry.get("scope", "")}


def check_in_scope(auth: dict, *, index: int | None = None,
                   level: str | None = None, alpha: float | None = None) -> None:
    import yaml
    entry = yaml.safe_load(POLICY.read_text())["heavy_work"]["exceptions"][POLICY_EXCEPTION]
    if index is not None and index not in entry.get("geometry_indices", [index]):
        raise SystemExit(f"geometry {index} is outside the authorized set "
                         f"{entry['geometry_indices']}. Not running.")
    if level is not None and level not in entry.get("grid_levels", [level]):
        raise SystemExit(f"grid level {level} is outside the authorized set "
                         f"{entry['grid_levels']}. Not running.")
    if alpha is not None and alpha not in entry.get("alpha_deg", [alpha]):
        raise SystemExit(f"alpha {alpha} is outside the authorized set "
                         f"{entry['alpha_deg']}. Not running.")


# --------------------------------------------------------------------------- #
# PLAN 0.2 -- one measurement at a time

class Exclusive:
    """An exclusive lock held for the whole of a run.

    Refuses rather than waits.  A queued second measurement is still a second
    measurement contending for the same memory, and the point of the rule is
    that the machine is idle apart from the thing being measured.
    """

    def __init__(self, what: str):
        self.what, self.handle = what, None

    def __enter__(self):
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(LOCK, "a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.seek(0)
            raise SystemExit(
                f"another S8 measurement is already running:\n  {self.handle.read().strip()}\n"
                f"PLAN 0.2: one measurement at a time, on an otherwise idle machine. "
                f"Two measurements sharing a machine is how 11.86 GiB was read for "
                f"something that was not. Wait for it, or kill it deliberately."
            ) from None
        self.handle.seek(0); self.handle.truncate()
        self.handle.write(f"pid {os.getpid()}  {self.what}  started {time.strftime('%FT%T')}\n")
        self.handle.flush()
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()
        return False


# --------------------------------------------------------------------------- #
# PLAN 2.1 -- a marginal level is a measurement

class MemoryWatch(threading.Thread):
    """Sample memory during a run and abort it on SUSTAINED paging.

    Not a limit check.  The question a marginal level asks is not "does the
    predicted figure exceed the available figure" -- the memory law is a
    two-point fit and the difference here is 0.2 GiB -- but "does this run
    actually page".  A run that touches swap briefly at allocation is fine.  A
    run whose working set does not fit pages continuously, runs at disk speed,
    and produces a correct answer so late that it is worthless, or gets
    OOM-killed after hours with nothing written.  Both are caught here in
    minutes instead.
    """

    def __init__(self, process, *, interval=5.0, grace=120.0,
                 swap_growth_gib=1.0, sustained=6, flush_to: Path | None = None):
        super().__init__(daemon=True)
        # Defect: the first gci_M attempt was killed by the host's memory
        # manager, and the parent driver died with it, so the samples that
        # would have said HOW CLOSE it got were held in memory and lost. That
        # is PLAN 0.4 one level up -- the quantity that would have shown it was
        # computed and discarded. Samples are now flushed to disk as they are
        # taken, so the evidence survives the process that collected it.
        self.flush_to = flush_to
        self.process, self.interval, self.grace = process, interval, grace
        self.swap_growth_gib, self.sustained = swap_growth_gib, sustained
        self.peak_rss_gib = 0.0
        self.peak_swap_gib = 0.0
        self.samples: list[dict] = []
        self.aborted_reason: str | None = None
        self._stop = threading.Event()

    @staticmethod
    def _meminfo() -> dict:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0]) / 1024.0 / 1024.0   # GiB
        return info

    def _adflow_rss_gib(self) -> float:
        """Resident set summed over the rank processes, from /proc.

        Summing RSS over ranks double-counts shared pages, so this is an upper
        bound rather than the figure the memory law predicts.  It is used to
        report a peak, never to trigger the abort -- the abort reads swap, which
        is unambiguous.
        """
        total = 0.0
        for status in Path("/proc").glob("[0-9]*/status"):
            try:
                text = status.read_text()
                if "adflow" not in text.split("\n", 1)[0].lower() and \
                        "python" not in text.split("\n", 1)[0].lower():
                    continue
                m = re.search(r"^VmRSS:\s+(\d+) kB", text, re.M)
                if m:
                    total += int(m.group(1)) / 1024.0 / 1024.0
            except (OSError, ValueError):
                continue
        return total

    def run(self) -> None:
        started = time.time()
        base = self._meminfo()
        base_swap_used = base["SwapTotal"] - base["SwapFree"]
        consecutive = 0
        while not self._stop.is_set():
            time.sleep(self.interval)
            try:
                info = self._meminfo()
            except OSError:
                continue
            swap_used = info["SwapTotal"] - info["SwapFree"]
            rss = self._adflow_rss_gib()
            self.peak_rss_gib = max(self.peak_rss_gib, rss)
            self.peak_swap_gib = max(self.peak_swap_gib, swap_used)
            self.samples.append({"t": round(time.time() - started, 1),
                                 "available_gib": round(info["MemAvailable"], 2),
                                 "swap_used_gib": round(swap_used, 2),
                                 "rank_rss_sum_gib": round(rss, 2)})
            if self.flush_to is not None:
                try:
                    self.flush_to.write_text(json.dumps(
                        {"in_progress": True,
                         "peak_rank_rss_sum_gib": round(self.peak_rss_gib, 2),
                         "peak_swap_used_gib": round(self.peak_swap_gib, 2),
                         "samples": self.samples[-400:]}, indent=2) + "\n")
                except OSError:
                    pass
            if time.time() - started < self.grace:
                continue
            if swap_used - base_swap_used > self.swap_growth_gib:
                consecutive += 1
            else:
                consecutive = 0
            if consecutive >= self.sustained:
                self.aborted_reason = (
                    f"sustained paging: swap use grew {swap_used - base_swap_used:.2f} GiB "
                    f"above baseline and stayed there for "
                    f"{self.sustained * self.interval:.0f} s. This level does not fit "
                    f"this host. The run is being stopped now rather than left to "
                    f"finish at disk speed or be OOM-killed with nothing written."
                )
                self._stop.set()
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
                return

    def stop(self) -> None:
        self._stop.set()


# --------------------------------------------------------------------------- #
# running things

def resolve_env() -> dict:
    env = env_s8.resolve()
    print(f"  mach-aero python : {env['mach_python']}")
    print(f"  mpirun           : {env['mpirun']}")
    print(f"                     ({env['mpirun_source']})")
    return env


def build_level(env: dict, level: str, index: int, out: Path,
                farfield_chords: float | None = None) -> dict:
    """Build one mesh and write its CGNS.  PLAN 3.1.

    The build is judged on `negative_cells_all_blocks` and `wall_layer_error_m`,
    which are the two things PLAN 0.1 and 0.3 say a clean exit does not
    establish: build_volume exited 0 on a mesh with 645 folded cells, and every
    shape metric was unchanged while the wing moved 1.2 mm.
    """
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / f"{level}_summary.json"
    cgns = out / f"{level}_volume.cgns"
    if cgns.exists() and summary_path.exists():
        print(f"  {level}: already built, skipping")
    else:
        cmd = [env["venv_python"], str(HERE / "build_volume.py"),
               "--level", level, "--index", str(index), "--out", str(out)]
        if farfield_chords is not None:
            cmd += ["--farfield-chords", str(farfield_chords)]
        print(f"  building {level} on index {index} ...", flush=True)
        log = out / f"{level}_build.log"
        with open(log, "w") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc != 0 or not summary_path.exists():
            raise SystemExit(f"build of {level} failed; see {log}")
        cmd = [env["mach_python"], str(HERE / "write_cgns.py"),
               "--blocks", str(out / f"{level}_blocks.npz")]
        print(f"  writing CGNS for {level} ...", flush=True)
        with open(out / f"{level}_cgns.log", "w") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc != 0 or not cgns.exists():
            raise SystemExit(f"CGNS write for {level} failed; see {out / f'{level}_cgns.log'}")

    summary = json.loads(summary_path.read_text())
    folded = summary["negative_cells_all_blocks"]
    wall = summary["volume"]["wall_layer_error_m"]
    print(f"  {level}: {summary['cells']:,} cells, {folded} folded, "
          f"wall error {wall:.3e} m")
    if folded:
        raise SystemExit(f"{level} has {folded} folded cells. A grid with inverted "
                         f"cells must never reach a solver (PLAN 0.3, defect 19).")
    if wall > 1.0e-9:
        raise SystemExit(f"{level} wall layer sits {wall:.3e} m from the loft, past the "
                         f"1e-9 guard. Defect 21: quality metrics do not check position.")
    return {"level": level, "cells": summary["cells"], "cgns": str(cgns),
            "folded": folded, "wall_layer_error_m": wall,
            "summary": str(summary_path)}


def solve(env: dict, grid: Path, alpha: float, out: Path, *,
          ranks: int = 6, watch_memory: bool = False,
          solver_args: list[str] | None = None,
          area_ref: float | None = None) -> dict:
    """One ADflow point.  Judged by the gate, never by its exit status."""
    out.mkdir(parents=True, exist_ok=True)
    result = out / "result.json"
    if result.exists():
        print(f"  {out.name}: already run, skipping")
        return {"skipped": True, **json.loads(result.read_text())}

    cmd = [env["mpirun"], "-np", str(ranks), env["mach_python"],
           str(HERE / "solve_s8.py"), "--grid", str(grid), "--alpha", str(alpha),
           "--out", str(out), "--i-have-authorization"] + list(solver_args or []) + \
          (["--area-ref", repr(area_ref)] if area_ref is not None else [])
    log = out / "run.log"
    print(f"  solving {out.name}: alpha {alpha:g} on {grid.name} ...", flush=True)
    started = time.time()
    with open(log, "w") as fh:
        process = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        watch = None
        if watch_memory:
            watch = MemoryWatch(process, flush_to=out / "memory_watch.json")
            watch.start()
        try:
            rc = process.wait()
        except KeyboardInterrupt:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            raise
        finally:
            if watch:
                watch.stop()
                watch.join(timeout=10)
    wall = time.time() - started

    record = {"alpha_deg": alpha, "grid": str(grid), "out": str(out),
              "exit_code": rc, "wall_seconds": round(wall, 1),
              "ranks": ranks, "log": str(log)}
    if watch:
        record["memory"] = {"peak_rank_rss_sum_gib": round(watch.peak_rss_gib, 2),
                            "peak_swap_used_gib": round(watch.peak_swap_gib, 2),
                            "aborted_reason": watch.aborted_reason,
                            "samples": watch.samples[-200:]}
        (out / "memory_watch.json").write_text(json.dumps(record["memory"], indent=2) + "\n")
        if watch.aborted_reason:
            print(f"  ABORTED: {watch.aborted_reason}")
            record["aborted"] = True
            return record
    # PLAN 0.3: exit 0 proves nothing.  ADflow exits cleanly on SIGTERM.
    if not result.exists():
        print(f"  {out.name}: exit {rc} but NO result.json was written. "
              f"That is a failed run whatever the exit code says. See {log}")
        record["failed"] = True
        return record
    record.update(json.loads(result.read_text()))
    print(f"  {out.name}: done in {wall/60:.1f} min, "
          f"relative residual {record.get('relative_residual')}")
    return record


def gate(env: dict, pattern: str, out: Path | None = None) -> dict:
    cmd = [env["venv_python"], str(HERE / "convergence_gate.py"), "--runs", pattern]
    if out:
        cmd += ["--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
    return json.loads(out.read_text()) if out and out.exists() else {}


def solver_flags(args) -> list[str]:
    """Solver overrides to pass through to solve_s8.py.

    Kept in one place so that a run's configuration is decided once, not per
    call site: two stages that disagree about the solver would produce results
    that look comparable and are not.
    """
    flags = []
    if getattr(args, "no_nk", False):
        flags.append("--no-nk")
    if getattr(args, "nk_switch_tol", None) is not None:
        flags += ["--nk-switch-tol", str(args.nk_switch_tol)]
    return flags


# --------------------------------------------------------------------------- #
# stages

def stage_build(args, env, auth) -> int:
    print("\nPLAN 3.1 -- build the family and write CGNS\n")
    built = []
    for level in args.levels:
        check_in_scope(auth, index=args.index, level=level)
        built.append(build_level(env, level, args.index, GCI83))
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "s8_gci83_builds.json").write_text(
        json.dumps({"index": args.index, "levels": built}, indent=2) + "\n")
    print(f"\nwrote {REPORTS / 's8_gci83_builds.json'}")
    return 0


def stage_regression(args, env, auth) -> int:
    """PLAN 3.2 -- the regression run, ALONE, before anything else."""
    print("\nPLAN 3.2 -- the regression run, alone, before anything else\n")
    check_in_scope(auth, index=REFERENCE_INDEX, level="gci_C", alpha=0.0)
    grid = GCI83 / "gci_C_volume.cgns"
    if not grid.exists():
        raise SystemExit(f"{grid} does not exist. Run the build stage first.")
    out = CFD / "gci_C_a0"
    with Exclusive("PLAN 3.2 regression, gci_C alpha 0"):
        record = solve(env, grid, 0.0, out, ranks=args.ranks,
                       watch_memory=args.watch_memory,
                       area_ref=reference_half_area(REFERENCE_INDEX))
    if record.get("failed") or record.get("aborted"):
        raise SystemExit("the regression run did not produce a result. Campaign stopped.")

    short = {}
    for key, value in record.get("functions", {}).items():
        for name in PREFIX_REFERENCE:
            if key.endswith("_" + name):
                short[name] = float(value)

    verdict = {"plan_section": "3.2", "directory": str(out),
               "reference": PREFIX_REFERENCE,
               "reference_note": "pre-fix oh_L3. A REGRESSION REFERENCE ONLY -- it "
                                 "ran on meshes the frame fix destroyed and may not "
                                 "be quoted as a result.",
               "measured": short, "deltas": {}, "checks": {}}
    print(f"\n{'':>6}{'pre-fix':>12}{'now':>12}{'delta':>12}")
    for name, ref in PREFIX_REFERENCE.items():
        got = short.get(name)
        if got is None:
            continue
        delta = got - ref
        verdict["deltas"][name] = delta
        print(f"{name:>6}{ref:>12.6f}{got:>12.6f}{delta:>+12.6f}")

    dcd = abs(verdict["deltas"].get("cd", 0.0))
    verdict["checks"]["cd_shift"] = {
        "value": dcd, "abort_at": CD_ABORT,
        "pass": dcd < CD_ABORT,
        "reading": ("second-decimal shift in CD -- PLAN 3.2 says STOP"
                    if dcd >= CD_ABORT else
                    "third/fourth-decimal shift in CD -- that is the mesh, as expected"
                    if dcd >= CD_NOTE else
                    "CD essentially unmoved")}
    directions = record.get("flow_directions", {})
    verdict["checks"]["flow_directions"] = {
        "lift_index_realised": directions.get("lift_index_realised"),
        "velocity_direction_error": directions.get("velocity_direction_error"),
        "pass": (directions.get("lift_index_realised") == 3
                 and directions.get("velocity_direction_error") == 0.0),
        "reading": "defect 14: alpha applied as sideslip if liftIndex is not 3"}

    gate_report = gate(env, str(out), REPORTS / "s8_regression_gate.json")
    gate_verdict = next((r["verdict"] for r in gate_report.get("results", [])), None)
    verdict["checks"]["gate"] = {"verdict": gate_verdict,
                                 "pass": gate_verdict == "ACCEPTED"}

    verdict["passed"] = all(c["pass"] for c in verdict["checks"].values())
    VERDICT.parent.mkdir(parents=True, exist_ok=True)
    VERDICT.write_text(json.dumps(verdict, indent=2) + "\n")
    print(f"\nwrote {VERDICT}")
    for name, check in verdict["checks"].items():
        print(f"  {name:<18} {'PASS' if check['pass'] else 'FAIL'}  {check.get('reading','')}")
    if not verdict["passed"]:
        print("\nREGRESSION FAILED. PLAN 3.2: stop. The sweep will refuse to start.")
        return 1
    print("\nregression passed; the sweep may proceed")
    return 0


def stage_sweep(args, env, auth) -> int:
    """PLAN 3.3 -- four angles on every level, sequentially."""
    if not VERDICT.exists():
        raise SystemExit("the PLAN 3.2 regression has not been run. It goes first and "
                         "alone, because it checks the whole chain after a change that "
                         "moved every cell. Run the regression stage.")
    if not json.loads(VERDICT.read_text())["passed"] and not args.force:
        raise SystemExit(f"the regression in {VERDICT} did not pass. PLAN 3.2 says stop. "
                         f"Pass --force only with a reason written down.")

    print("\nPLAN 3.3 -- four angles on every level, sequentially\n")
    done = []
    for level in args.levels:
        check_in_scope(auth, index=REFERENCE_INDEX, level=level)
        grid = GCI83 / f"{level}_volume.cgns"
        if not grid.exists():
            raise SystemExit(f"{grid} does not exist. Run the build stage first.")
        for alpha in ALPHAS:
            check_in_scope(auth, alpha=alpha)
            out = CFD / f"{level}_a{alpha:g}"
            with Exclusive(f"PLAN 3.3 {level} alpha {alpha:g}"):
                record = solve(env, grid, alpha, out, ranks=args.ranks,
                               watch_memory=args.watch_memory or level in args.marginal,
                               solver_args=solver_flags(args),
                               area_ref=reference_half_area(REFERENCE_INDEX))
            done.append(record)
            if record.get("aborted"):
                print(f"\n{level} was aborted by the memory watchdog. Skipping the rest "
                      f"of this level: if alpha {alpha:g} does not fit, nor do the others.")
                break
    gate(env, str(CFD / "gci_*_a*"), REPORTS / "s8_gci_gate.json")
    return 0


def stage_farfield(args, env, auth) -> int:
    """PLAN 2.2 -- one far-field sensitivity run, chords 40 -> 60."""
    print("\nPLAN 2.2 -- far-field sensitivity, gci_C alpha 0, chords 40 -> 60\n")
    print("The family refines the near body systematically and the far field only\n"
          "weakly: o_out and cap_out do not refine spanwise, and o_out is 49 % of\n"
          "cells at the coarse level. One run at a larger far field says how much\n"
          "of the answer that costs.\n")
    check_in_scope(auth, index=REFERENCE_INDEX, level="gci_C", alpha=0.0)
    out_mesh = ARTIFACTS / "s8_farfield60"
    build_level(env, "gci_C", REFERENCE_INDEX, out_mesh, farfield_chords=60.0)
    out = CFD / "farfield60_gci_C_a0"
    with Exclusive("PLAN 2.2 far-field sensitivity"):
        record = solve(env, out_mesh / "gci_C_volume.cgns", 0.0, out,
                       ranks=args.ranks, watch_memory=args.watch_memory,
                       area_ref=reference_half_area(REFERENCE_INDEX))
    baseline = CFD / "gci_C_a0" / "result.json"
    report = {"plan_section": "2.2", "farfield_chords": {"baseline": 40.0, "test": 60.0},
              "test": record.get("functions", {})}
    if baseline.exists():
        base = json.loads(baseline.read_text())["functions"]
        report["baseline"] = base
        report["delta"] = {k: record.get("functions", {}).get(k, float("nan")) - v
                           for k, v in base.items()}
        print(f"\n{'function':>28}{'chords 40':>14}{'chords 60':>14}{'delta':>14}")
        for k, v in base.items():
            got = record.get("functions", {}).get(k)
            if got is not None:
                print(f"{k:>28}{v:>14.6f}{got:>14.6f}{got - v:>+14.6f}")
    (REPORTS / "s8_farfield_sensitivity.json").write_text(
        json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {REPORTS / 's8_farfield_sensitivity.json'}")
    return 0


def stage_pilot(args, env, auth) -> int:
    """PLAN 4.2 -- the ten geometries, at the level chosen in 3.5."""
    selection = REPORTS / "s8_pilot_geometries.json"
    if not selection.exists():
        raise SystemExit(f"{selection} does not exist. Run select_pilot_geometries.py "
                         f"first: PLAN 4.4 says the set is fixed BEFORE the first case.")
    indices = json.loads(selection.read_text())["selected"]
    if args.indices:
        missing = [i for i in args.indices if i not in indices]
        if missing:
            raise SystemExit(f"{missing} are not in the authorized pilot set "
                             f"{indices}. The set is fixed BEFORE the first case "
                             f"(PLAN 4.1) and is not extended from the command line.")
        indices = [i for i in indices if i in args.indices]
    level = args.level
    print(f"\nPLAN 4.2 -- ten geometries at {level}, alphas {ALPHAS}\n")
    print(f"  {indices}\n")
    for index in indices:
        check_in_scope(auth, index=index, level=level)
        directory = PILOT / f"g{index}"
        build_level(env, level, index, directory)
        for alpha in ALPHAS:
            # The LEVEL must be in the path. It was not, so every run directory
            # was s8_pilot/g83/a0 regardless of grid, and running a second level
            # over the same geometries silently SKIPPED all twelve runs -- the
            # resumability check found the first level's result.json sitting
            # there and reported "already run".
            #
            # Nothing was lost only by luck: without that check the second level
            # would have OVERWRITTEN the first. What did happen is worse in kind,
            # because it is quiet: the post-processing then read the newly built
            # gci_M mesh summary and wrote dataset rows claiming grid_level
            # gci_M and 1,111,152 cells for forces produced on a 567,256-cell
            # gci_C solve. Correct-looking numbers, wrong label, which is the one
            # defect a surrogate cannot survive.
            out = directory / f"{level}_a{alpha:g}"
            with Exclusive(f"PLAN 4.2 g{index} alpha {alpha:g}"):
                record = solve(env, directory / f"{level}_volume.cgns", alpha, out,
                               ranks=args.ranks,
                               watch_memory=args.watch_memory or level in args.marginal,
                               solver_args=solver_flags(args),
                               area_ref=reference_half_area(index))
            if record.get("aborted"):
                raise SystemExit(f"g{index} alpha {alpha:g} aborted on memory. Stopping.")
        # PLAN 4.2: "Check the gate after each geometry, not at the end."
        gate(env, str(directory / f"{level}_a*"), directory / f"{level}_gate.json")
        subprocess.run([env["venv_python"], str(HERE / "verify_against_avl.py"),
                        "--index", str(index), "--alphas", *[str(a) for a in ALPHAS],
                        "--out", str(directory / "avl")], check=False)
        subprocess.run([env["venv_python"], str(HERE / "dataset_row.py"),
                        "--run-dir", str(directory), "--level", level,
                        "--index", str(index), "--gate",
                        str(directory / f"{level}_gate.json"),
                        "--out", str(directory / f"{level}_dataset_rows.json")],
                       check=False)
    return 0


def stage_probe(args, env, auth) -> int:
    """Time to the stopping target at several rank counts, on THIS host.

    AUDIT_2026-09-10 C8: on the six-core desktop, time per nonlinear step was
    flat beyond two ranks, while cloud_batch.py priced the batch at 75 %
    efficiency on 24. Renting the machine is the first moment its real curve can
    be measured, so this measures it before the batch bills its hours: one gci_C
    point on the reference geometry, converged to the governed target, at each
    rank count.
    """
    index, level = REFERENCE_INDEX, "gci_C"
    check_in_scope(auth, index=index, level=level)
    directory = ARTIFACTS / "s8_probe" / f"g{index}"
    built = build_level(env, level, index, directory)
    runs = []
    for ranks in args.probe_ranks:
        out = directory / f"{level}_a0_np{ranks}"
        with Exclusive(f"scaling probe, {ranks} ranks"):
            record = solve(env, Path(built["cgns"]), 0.0, out, ranks=ranks,
                           solver_args=solver_flags(args),
                           area_ref=reference_half_area(index))
        result = (json.loads((out / "result.json").read_text())
                  if (out / "result.json").exists() else {})
        runs.append({"ranks": ranks, "wall_seconds": record.get("wall_seconds"),
                     "converged": result.get("converged"),
                     "relative_residual": result.get("relative_residual")})
    timed = [r for r in runs if r["wall_seconds"] and r["converged"]]
    for r in timed:
        speedup = timed[0]["wall_seconds"] / r["wall_seconds"]
        r["speedup_vs_fewest"] = round(speedup, 3)
        r["efficiency_vs_fewest"] = round(speedup * timed[0]["ranks"] / r["ranks"], 3)
        r["core_hours_per_point"] = round(r["wall_seconds"] * r["ranks"] / 3600, 3)
    report = {"schema": "aeris.s8.scaling_probe.v1", "host_cpus": os.cpu_count(),
              "case": f"{level} index {index} alpha 0", "runs": runs,
              "reading": ("the batch rents every core for its whole length, so the "
                          "cheapest machine is the one with the fewest core-hours per "
                          "point; efficiency under 0.5 pays for cores that mostly wait")}
    (REPORTS / "s8_scaling_probe.json").write_text(json.dumps(report, indent=2) + "\n")
    nan = float("nan")
    print(f"\n  {'ranks':>6}{'wall s':>9}{'speed-up':>10}{'efficiency':>12}{'core-h/pt':>11}")
    for r in runs:
        print(f"  {r['ranks']:>6}{r['wall_seconds'] or nan:>9.0f}"
              f"{r.get('speedup_vs_fewest', nan):>10.2f}"
              f"{r.get('efficiency_vs_fewest', nan):>12.2f}"
              f"{r.get('core_hours_per_point', nan):>11.3f}")
    print(f"\n  wrote {REPORTS / 's8_scaling_probe.json'}")
    return 0


def stage_status(args, env, auth) -> int:
    print("\nS8 campaign state\n")
    print(f"  authorization : {auth['exception']}, signed by {auth['authorized_by']} "
          f"on {auth['authorized_on']}")
    print(f"  regression    : ", end="")
    if VERDICT.exists():
        v = json.loads(VERDICT.read_text())
        print("PASSED" if v["passed"] else "FAILED")
    else:
        print("not run")
    for label, root, pattern in (("grid family", GCI83, "*_volume.cgns"),
                                 ("refinement runs", CFD, "*/result.json"),
                                 ("pilot runs", PILOT, "*/a*/result.json")):
        found = sorted(root.glob(pattern)) if root.exists() else []
        print(f"  {label:<14}: {len(found)}")
        for f in found:
            print(f"      {f.relative_to(root)}")
    return 0


STAGES = {"build": stage_build, "regression": stage_regression, "sweep": stage_sweep,
          "farfield": stage_farfield, "pilot": stage_pilot, "status": stage_status,
          "probe": stage_probe}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("--levels", nargs="+", default=["gci_C", "gci_M"])
    ap.add_argument("--level", default="gci_C", help="single level, for the pilot")
    ap.add_argument("--indices", type=int, nargs="*", default=None,
                    help="run the pilot on a SUBSET of the authorized ten. Used "
                         "for the second grid level, where the question is only "
                         "whether the refinement offset is geometry-independent, "
                         "which three geometries answer and ten re-confirm. "
                         "Cannot add a geometry the policy does not authorize.")
    ap.add_argument("--index", type=int, default=REFERENCE_INDEX)
    ap.add_argument("--ranks", type=int, default=6)
    ap.add_argument("--probe-ranks", type=int, nargs="+", default=[6, 12, 24],
                    help="probe stage: the rank counts to time")
    ap.add_argument("--watch-memory", action="store_true",
                    help="sample RSS and swap throughout and abort on sustained "
                         "paging. Required for a level select_levels.py calls marginal.")
    ap.add_argument("--marginal", nargs="*", default=["gci_M"],
                    help="levels to watch even without --watch-memory")
    ap.add_argument("--no-nk", action="store_true",
                    help="converge with ANK alone. See solve_s8.py --no-nk: NK "
                         "froze at gci_M with LinRes 1.000 while ANK was still "
                         "descending. Uses less memory. Recorded in result.json.")
    ap.add_argument("--nk-switch-tol", type=float, default=None)
    ap.add_argument("--force", action="store_true",
                    help="proceed past a failed regression verdict. PLAN 3.2 says stop; "
                         "this exists so that overriding it is a deliberate, recorded act.")
    args = ap.parse_args()

    auth = check_authorization()
    print(f"authorized: {auth['exception']} by {auth['authorized_by']} "
          f"on {auth['authorized_on']}")
    env = resolve_env()
    return STAGES[args.stage](args, env, auth)


if __name__ == "__main__":
    raise SystemExit(main())
