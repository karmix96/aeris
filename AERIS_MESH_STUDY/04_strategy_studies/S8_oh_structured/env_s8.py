#!/usr/bin/env python
"""Where the two interpreters and the MPI launcher actually are, on this host.

    .venv/bin/python .../env_s8.py          # print what was found, and why

S8 needs three different things to run a case and they do not live together:

  project venv     build_volume.py, gci.py, the gates, the AVL check.  Has
                   numpy/pyGeo/aerosandbox, does NOT have libcgns or ADflow.
  MACH-Aero env    write_cgns.py (needs cgnsutilities -> libcgns) and
                   solve_s8.py (needs ADflow).
  mpirun           must be the one the MACH-Aero env's mpi4py was built
                   against.  Mixing MPI runtimes gives six one-rank runs that
                   each think they are rank 0, and each writes over the others'
                   output while reporting success.

`PLAN_desktop_campaign.md` and `HANDOFF_desktop.md` write these as
`/home/mike/miniconda3/envs/mach-aero/...`, which is the path on the machine the
plan was written for and does not exist on this one.  A hard-coded absolute path
to another user's home directory is not a configuration, it is a note about
somebody else's laptop, and every command in the plan fails on it with a bare
"No such file or directory" that says nothing about the real problem.

So this resolves them, and says which rule fired.  Override any of the three
with AERIS_MACH_PYTHON, AERIS_VENV_PYTHON or AERIS_MPIRUN.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _importable(python: Path, module: str) -> bool:
    try:
        return subprocess.run(
            [str(python), "-c", f"import {module}"],
            capture_output=True, timeout=120,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _conda_roots() -> list[Path]:
    roots = []
    for base in (Path.home(), Path("/opt")):
        for name in ("miniconda3", "anaconda3", "miniforge3", "mambaforge", "conda"):
            roots.append(base / name)
    if os.environ.get("CONDA_EXE"):
        roots.append(Path(os.environ["CONDA_EXE"]).resolve().parents[1])
    return roots


def find_mach_python() -> tuple[Path, str]:
    """The interpreter that can import adflow.  Verified, not assumed."""
    override = os.environ.get("AERIS_MACH_PYTHON")
    if override:
        p = Path(override)
        if not _importable(p, "adflow"):
            raise SystemExit(f"AERIS_MACH_PYTHON={p} cannot import adflow.")
        return p, "AERIS_MACH_PYTHON"
    candidates: list[Path] = []
    for root in _conda_roots():
        envs = root / "envs"
        if envs.is_dir():
            # mach-aero first, then anything else, so a conventional name wins
            names = sorted(envs.iterdir(), key=lambda d: (d.name != "mach-aero", d.name))
            candidates += [d / "bin/python" for d in names]
    for python in candidates:
        if python.exists() and _importable(python, "adflow"):
            return python, "found an env whose interpreter imports adflow"
    raise SystemExit(
        "no interpreter on this host can import adflow.\n"
        "  looked under: " + ", ".join(str(r / "envs") for r in _conda_roots() if (r / "envs").is_dir())
        + "\n  set AERIS_MACH_PYTHON to the MACH-Aero interpreter."
    )


def find_venv_python() -> tuple[Path, str]:
    override = os.environ.get("AERIS_VENV_PYTHON")
    if override:
        return Path(override), "AERIS_VENV_PYTHON"
    venv = REPO / ".venv/bin/python"
    if venv.exists():
        return venv, "the project venv at <repo>/.venv"
    return Path(sys.executable), "falling back to the running interpreter"


def find_mpirun(mach_python: Path) -> tuple[Path, str]:
    """The launcher that belongs to the MACH-Aero env, preferred over $PATH.

    mpi4py links one MPI runtime.  Launching it with a different one is not an
    error anybody reports: the ranks simply do not form a communicator, every
    process believes it is rank 0 of 1, and six of them write the same output
    directory.  So the env's own launcher wins over whatever $PATH offers.
    """
    override = os.environ.get("AERIS_MPIRUN")
    if override:
        return Path(override), "AERIS_MPIRUN"
    sibling = mach_python.parent / "mpirun"
    if sibling.exists():
        return sibling, "the MACH-Aero env's own mpirun, which its mpi4py was built against"
    found = shutil.which("mpirun")
    if found:
        return Path(found), ("mpirun from $PATH -- NOT the MACH-Aero env's own. "
                             "Check that its mpi4py was built against this runtime.")
    raise SystemExit("no mpirun found; set AERIS_MPIRUN.")


def resolve() -> dict:
    mach, mach_why = find_mach_python()
    venv, venv_why = find_venv_python()
    mpirun, mpirun_why = find_mpirun(mach)
    return {
        "repo": str(REPO),
        "mach_python": str(mach), "mach_python_source": mach_why,
        "venv_python": str(venv), "venv_python_source": venv_why,
        "mpirun": str(mpirun), "mpirun_source": mpirun_why,
    }


if __name__ == "__main__":
    print(json.dumps(resolve(), indent=2))
