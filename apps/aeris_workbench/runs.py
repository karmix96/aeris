"""Unique, immutable run directories - and proof that a result is this run's.

The old workbench wrote every mesh to `workspace/s6/mesh` and every solve to
`workspace/s6/solve`, and reused both.  Three ways that lies:

  * `run_pyhyp` reported `cgns` as present whenever `wing_vol.cgns` existed in
    the run directory.  A march that failed on its second attempt left the FIRST
    attempt's file behind, so the workbench read a stale mesh, summarised it,
    showed it, and offered it to the solver.
  * `ADflowRunner.read_result` reads `adflow_result.json` from the solve
    directory.  After a failed rerun the previous run's forces were still there
    and were shown as current.
  * Moving a slider changed the geometry but nothing invalidated the mesh, so a
    mesh built from the previous shape stayed on screen and stayed solvable.

A run directory here is named for what produced it - the design fingerprint, the
settings hash and a monotonic run id - so a different input is a different
directory and cannot collide with an old result.  Nothing is ever overwritten,
and a file is only ever accepted as this run's output if it was created during
this run and its digest was recorded at the time.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_COUNTER = itertools.count(1)
_COUNTER_LOCK = threading.Lock()


def settings_hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def next_run_id() -> str:
    """Monotonic within a session, sortable, and unique across sessions."""
    with _COUNTER_LOCK:
        ordinal = next(_COUNTER)
    return f"{time.strftime('%Y%m%dT%H%M%S')}_{ordinal:04d}"


@dataclass
class RunDirectory:
    """One immutable directory, and the identity that produced it."""

    path: Path
    run_id: str
    kind: str
    design_fingerprint: str
    settings_hash: str
    started_at: float = field(default_factory=time.time)

    def provenance(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "design_fingerprint": self.design_fingerprint,
            "settings_hash": self.settings_hash,
            "directory": str(self.path),
            "started_at": self.started_at,
        }

    def write_provenance(self, extra: dict[str, Any] | None = None) -> Path:
        payload = self.provenance()
        if extra:
            payload.update(extra)
        target = self.path / "run_provenance.json"
        target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return target


def create(root: Path, kind: str, *, design_fingerprint: str,
           settings: Any, run_id: str | None = None) -> RunDirectory:
    """A directory that did not exist a moment ago.

    `exist_ok=False` is the point: if the name were ever to repeat, the failure
    is loud here rather than silent later when an old artifact is read back as
    though this run had written it.
    """
    run_id = run_id or next_run_id()
    digest = settings_hash(settings)
    path = Path(root) / kind / f"{design_fingerprint}_{digest}_{run_id}"
    path.mkdir(parents=True, exist_ok=False)
    directory = RunDirectory(path=path, run_id=run_id, kind=kind,
                             design_fingerprint=design_fingerprint, settings_hash=digest)
    directory.write_provenance()
    return directory


@dataclass
class Artifact:
    """A file this run is entitled to claim, with the proof attached."""

    path: Path
    digest: str
    bytes: int
    fresh: bool
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"path": str(self.path), "sha256": self.digest, "bytes": self.bytes,
                "fresh": self.fresh, "reason": self.reason}


def claim_output(path: Path, *, produced_after: float,
                 previous_digest: str | None = None) -> Artifact:
    """Accept a file only if THIS run produced it.

    Two independent tests, because either alone can be fooled.  The modification
    time has to postdate the moment the run started, which catches a leftover
    from a previous attempt; and if the file was there beforehand its digest has
    to have changed, which catches a filesystem whose timestamps are coarse or a
    tool that rewrites a file it did not change.
    """
    path = Path(path)
    if not path.is_file():
        return Artifact(path, "", 0, False, "not written")
    stat = path.stat()
    digest = file_digest(path)
    if previous_digest is not None and digest == previous_digest:
        return Artifact(path, digest, stat.st_size, False,
                        "identical to the file that was already there")
    # A one second allowance, because mtime granularity on some filesystems is
    # coarser than the gap between starting a run and the tool's first write.
    if stat.st_mtime + 1.0 < produced_after:
        return Artifact(path, digest, stat.st_size, False,
                        "older than this run")
    return Artifact(path, digest, stat.st_size, True)


def existing_digest(path: Path) -> str | None:
    path = Path(path)
    return file_digest(path) if path.is_file() else None


# --------------------------------------------------------------------------- #
# Downstream invalidation                                                       #
# --------------------------------------------------------------------------- #

#: Every piece of state that is only meaningful for one geometry and one set of
#: mesh controls.  Changing either has to clear all of it, or the interface goes
#: on showing a mesh, an audit verdict and a force history that belong to an
#: aircraft the user has already moved away from.
MESH_STATE_KEYS = (
    "mesh_ready", "mesh_stats", "mesh_validity", "mesh_audit", "mesh_paths",
    "mesh_verdict", "mesh_estimate", "mesh_provenance", "mesh_state",
)
SOLVER_STATE_KEYS = (
    "run_status", "run_iteration", "run_wall", "run_message", "convergence",
    "cfd_verdict", "cfd_state", "forces", "solver_log", "solve_provenance",
)
POST_STATE_KEYS = (
    "post_files", "post_source", "post_field", "post_fields", "post_summary",
)


@dataclass
class Stage:
    """What a stage was built from, so a change can be detected rather than assumed."""

    design_fingerprint: str = ""
    settings_hash: str = ""
    run_id: str = ""

    def matches(self, design_fingerprint: str, settings: Any) -> bool:
        return bool(
            self.design_fingerprint
            and self.design_fingerprint == design_fingerprint
            and self.settings_hash == settings_hash(settings)
        )
