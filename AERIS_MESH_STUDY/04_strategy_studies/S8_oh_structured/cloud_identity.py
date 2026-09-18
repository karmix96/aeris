#!/usr/bin/env python3
"""Identity, timing and archiving for runs that cost money.

Every rule here was bought with a defect in this project, and the comment on
each one names it. On the development host a mislabelled run costs a re-run; on
rented compute it costs the run plus the hours that produced it plus the hours
that reproduce it.

Four things this provides:

  case_id        what was computed -- deterministic, from the inputs
  execution_id   which attempt computed it -- unique, from the clock and host
  archive        bytes verified against their own hash, then atomically renamed
  verdict        judged on the ARTEFACTS, never on the exit code

The last is the newest. On 2026-09-18 `e387_sa_lm` exited 1 after writing its
restart, surface and forces files, having written that same restart 24 times
during the run: the outputs were complete and only the final write failed. This
project already held that a zero exit proves nothing (PLAN 0.3, defect 19). A
non-zero exit disproves nothing either.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

CHUNK = 1 << 20


# --------------------------------------------------------------------------- hashing

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def sha256_json(payload) -> str:
    """Stable hash of a structure: sorted keys, no incidental whitespace."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------------- identity

def case_id(*, geometry_index: int, level: str, alpha_deg: float,
            mesh_sha256: str, physics: dict, numerics: dict) -> str:
    """WHAT was computed. Same inputs, same id, on any host, forever.

    Defects 25, 26 and the verdict index were one mistake three times: a run
    was identified by `gci_C_a0`, which is the name of ten different runs. A
    human-readable label is a label. This is the identity, and it includes the
    mesh bytes and the resolved settings, because a different mesh or a
    different limiter is a different case however it is spelled.
    """
    return sha256_json({"geometry_index": geometry_index, "level": level,
                        "alpha_deg": round(float(alpha_deg), 6),
                        "mesh_sha256": mesh_sha256,
                        "physics": physics, "numerics": numerics})[:32]


def execution_id() -> str:
    """WHICH ATTEMPT computed it. A re-run is a new execution of the same case."""
    return sha256_json({"host": socket.gethostname(), "pid": os.getpid(),
                        "t": time.time_ns()})[:16]


def git_commit(repo: Path) -> dict:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=20)
        commit = out.stdout.strip() or None
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
    # A dirty tree means the commit does NOT describe what ran. Recorded rather
    # than ignored: the collection commit was taken for the execution commit
    # once already, and the review caught it.
    return {"commit": commit, "dirty": bool(dirty),
            "dirty_paths": [line[3:] for line in dirty.splitlines()[:40]] or None}


def environment(repo: Path, solver_version: str | None = None) -> dict:
    return {"host": socket.gethostname(), "platform": platform.platform(),
            "cpu_count": os.cpu_count(), "python": platform.python_version(),
            "solver_version": solver_version, "git": git_commit(repo)}


# --------------------------------------------------------------------------- timing

class Stopwatch:
    """Elapsed time that a suspended host cannot corrupt.

    On 2026-09-17 a solve was logged at 402.8 minutes against 74.3 for its
    neighbour on the same mesh, and read as a stalling solver. The machine had
    been asleep for 344 of those minutes: two consecutive samples of a 5-second
    loop were 344 minutes apart and the clock then stepped BACKWARDS. Wall
    clock measures how long you waited. `monotonic` measures how long the
    process ran, and `process_time` how much CPU it actually got -- and a large
    gap between the two is itself the suspend signal.
    """

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.w0 = time.time()

    def read(self) -> dict:
        monotonic = time.monotonic() - self.t0
        wall = time.time() - self.w0
        return {"seconds": round(monotonic, 1),
                "wall_clock_seconds": round(wall, 1),
                "clock_skew_seconds": round(wall - monotonic, 1),
                "note": ("wall clock and monotonic disagree by more than a minute: the host "
                         "was suspended or its clock was stepped. Use `seconds`."
                         if abs(wall - monotonic) > 60 else None)}


# --------------------------------------------------------------------------- archiving

def archive(src: Path, dest: Path) -> dict:
    """Copy, verify the STORED bytes, then rename into place.

    Defect 26: the archive recorded `sha256(source)` for a file it had declined
    to write, because one already existed under that name. Forty-four of 52
    rows described bytes that were never stored. Two rules come out of it and
    both are here: hash what you STORED, and make the file appear only once it
    has been verified, so a killed job leaves a `.part` and never a plausible
    wrong answer.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    shutil.copy2(src, part)
    source_digest, stored_digest = sha256_file(src), sha256_file(part)
    if source_digest != stored_digest:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: stored bytes do not match the source "
                           f"({stored_digest} vs {source_digest}); nothing archived")
    os.replace(part, dest)
    return {"path": str(dest), "sha256": stored_digest, "bytes": dest.stat().st_size,
            "verified": "hash read back from the stored file, not the source"}


def write_atomic(dest: Path, payload: dict) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    part.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(part, dest)
    return {"path": str(dest), "sha256": sha256_file(dest)}


# --------------------------------------------------------------------------- verdict

#: What a finished ADflow point must have on disk before it counts as one.
REQUIRED_ARTEFACTS = ("result.json",)


def verdict_from_artefacts(out: Path, exit_code: int | None = None) -> dict:
    """Did this run produce a usable answer?  Read the files and decide.

    The exit code is RECORDED and never used to decide. Both directions have
    burned this project: ADflow exits 0 on SIGTERM, and SU2 exited 1 on
    2026-09-18 having written every output it owed.
    """
    problems, present = [], {}
    for name in REQUIRED_ARTEFACTS:
        path = out / name
        present[name] = path.exists()
        if not path.exists():
            problems.append(f"{name} was never written")
    result = None
    if present.get("result.json"):
        try:
            result = json.loads((out / "result.json").read_text())
        except (OSError, ValueError) as exc:
            problems.append(f"result.json is unreadable: {exc}")
    if result is not None:
        if result.get("routine_failed"):
            problems.append("the solver reported routine_failed")
        if not result.get("converged"):
            problems.append(f"not converged: relative residual "
                            f"{result.get('relative_residual')}")
        if result.get("implausible_forces"):
            problems.append(f"implausible forces: {result['implausible_forces']}")
        if result.get("too_few_iterations"):
            problems.append("converged in too few iterations to be believable")
    return {"usable": not problems, "problems": problems,
            "artefacts_present": present,
            "exit_code": exit_code,
            "exit_code_note": ("recorded only. ADflow exits 0 on SIGTERM and SU2 has "
                               "exited 1 with every output written; neither direction "
                               "decides anything here.")}


def run_manifest(*, out: Path, geometry_index: int, level: str, alpha_deg: float,
                 mesh: Path, physics: dict, numerics: dict, repo: Path,
                 timing: dict, exit_code: int | None,
                 area_ref_m2: float | None, extra: dict | None = None) -> dict:
    """The complete identity of one paid run, written atomically beside it."""
    mesh_digest = sha256_file(mesh) if mesh.exists() else None
    cid = case_id(geometry_index=geometry_index, level=level, alpha_deg=alpha_deg,
                  mesh_sha256=mesh_digest or "", physics=physics, numerics=numerics)
    manifest = {
        "schema": "aeris.s8.run_manifest.v1",
        "case_id": cid,
        "execution_id": execution_id(),
        "label": f"g{geometry_index}/{level}/a{alpha_deg:g}",
        "label_note": "human-readable only; case_id is the identity",
        "geometry_index": geometry_index, "level": level, "alpha_deg": alpha_deg,
        "mesh": {"path": str(mesh), "sha256": mesh_digest,
                 "bytes": mesh.stat().st_size if mesh.exists() else None},
        "physics": physics, "numerics": numerics,
        "area_ref_m2": area_ref_m2,
        "environment": environment(repo),
        "timing": timing,
        "verdict": verdict_from_artefacts(out, exit_code),
    }
    if extra:
        manifest.update(extra)
    write_atomic(out / "run_manifest.json", manifest)
    return manifest
