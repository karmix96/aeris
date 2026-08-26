"""Discover which parts of the toolchain this machine can actually run.

The two strategies do not share one interpreter.  Measured on this machine:

    capability          project .venv (3.13)   conda mach-aero (3.11)
    pyGeo / pySpline    yes                    no
    gmsh                yes                    no
    SU2_CFD             yes (binary)           -
    pyHyp               no (libcgns missing)   yes
    ADflow              no (not installed)     yes

So the GUI runs in the .venv - it is the only one with VTK, PyVista and trame -
and hands pyHyp and ADflow work to the conda interpreter as subprocesses.  That
is also how a commercial workbench is built: the GUI process never IS the solver.

Nothing here raises on a missing tool.  The UI asks what is available and greys
out what is not, because a workbench that lies about its capabilities is worse
than one that is honest about a gap.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MESH_STUDY = REPO_ROOT / "AERIS_MESH_STUDY"
STRATEGY_DIR = MESH_STUDY / "04_strategy_studies"
S6_DIR = STRATEGY_DIR / "S6_bounded_mesh_atlas"
S7_DIR = STRATEGY_DIR / "S7_unstructured_gmsh_su2"
WORKSPACE = REPO_ROOT / "apps" / "workspace"

# The MACH-Aero side of the house.  These paths are probed, never assumed.
CONDA_MACH_AERO = Path("/home/mike/miniconda3/envs/mach-aero")
MACH_AERO_PACKAGES = Path("/home/mike/packages/mach-aero")


@dataclass
class Capability:
    """One tool, and whether this machine can actually run it."""

    key: str
    label: str
    available: bool
    detail: str = ""
    version: str = ""
    interpreter: str = ""

    @property
    def status(self) -> str:
        return "ready" if self.available else "unavailable"


@dataclass
class Environment:
    capabilities: dict[str, Capability] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Capability:
        return self.capabilities[key]

    def ok(self, *keys: str) -> bool:
        return all(self.capabilities[k].available for k in keys if k in self.capabilities)

    def missing(self, *keys: str) -> list[str]:
        return [self.capabilities[k].label for k in keys
                if k in self.capabilities and not self.capabilities[k].available]

    def as_rows(self) -> list[dict[str, Any]]:
        return [
            {"key": c.key, "tool": c.label, "status": c.status,
             "version": c.version, "detail": c.detail, "where": c.interpreter}
            for c in self.capabilities.values()
        ]


def _import_version(module: str) -> tuple[bool, str, str]:
    """Import a module in THIS interpreter and report its version."""
    try:
        import importlib.metadata as md
        mod = __import__(module)
        try:
            return True, md.version(module), ""
        except Exception:
            return True, str(getattr(mod, "__version__", "")), ""
    except Exception as exc:  # noqa: BLE001 - the reason is the useful part
        return False, "", f"{type(exc).__name__}: {exc}"[:160]


def _probe_conda(module: str) -> tuple[bool, str, str]:
    """Import a module in the conda interpreter, out of process."""
    python = CONDA_MACH_AERO / "bin" / "python"
    if not python.is_file():
        return False, "", f"interpreter not found at {python}"
    code = (
        "import importlib.metadata as md\n"
        f"m=__import__('{module}')\n"
        "try: v=md.version(m.__name__)\n"
        "except Exception: v=str(getattr(m,'__version__',''))\n"
        "print(v)\n"
    )
    try:
        done = subprocess.run([str(python), "-c", code], capture_output=True,
                              text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return False, "", str(exc)[:160]
    if done.returncode != 0:
        tail = (done.stderr or "").strip().splitlines()
        return False, "", (tail[-1] if tail else "import failed")[:160]
    return True, done.stdout.strip(), ""


def _probe_binary(name: str, version_args: list[str], line: int = 0) -> tuple[bool, str, str]:
    path = shutil.which(name)
    if not path:
        return False, "", f"{name} not on PATH"
    try:
        done = subprocess.run([path, *version_args], capture_output=True, text=True, timeout=60)
        text = (done.stdout or done.stderr or "").splitlines()
        return True, (text[line].strip() if len(text) > line else ""), path
    except Exception as exc:  # noqa: BLE001
        return True, "", f"{path} ({exc})"[:160]


def detect(*, quick: bool = False) -> Environment:
    """Probe every tool the two workbenches can use.

    `quick` skips the out-of-process conda probes, which cost about a second
    each; use it when redrawing the UI rather than on startup.
    """
    env = Environment()
    here = f"venv {sys.version_info.major}.{sys.version_info.minor}"

    for key, module, label in [
        ("pygeo", "pygeo", "pyGeo"),
        ("pyspline", "pyspline", "pySpline"),
        ("gmsh", "gmsh", "Gmsh"),
        ("vtk", "vtk", "VTK"),
        ("pyvista", "pyvista", "PyVista"),
        ("trame", "trame", "trame"),
    ]:
        ok, ver, why = _import_version(module)
        env.capabilities[key] = Capability(key, label, ok, why, ver, here)

    ok, ver, path = _probe_binary("SU2_CFD", ["--help"])
    env.capabilities["su2"] = Capability(
        "su2", "SU2_CFD", ok, path if ok else ver, ver.split(",")[0] if ok else "", "binary")

    ok, ver, path = _probe_binary("mpirun", ["--version"])
    env.capabilities["mpi"] = Capability("mpi", "mpirun", ok, path if ok else ver, ver[:40], "binary")

    conda_label = "conda mach-aero"
    if quick:
        for key, label in [("pyhyp", "pyHyp"), ("adflow", "ADflow")]:
            env.capabilities[key] = Capability(key, label, False, "not probed", "", conda_label)
        return env

    for key, module, label in [("pyhyp", "pyhyp", "pyHyp"), ("adflow", "adflow", "ADflow")]:
        ok, ver, why = _probe_conda(module)
        env.capabilities[key] = Capability(key, label, ok, why, ver, conda_label)

    return env


def conda_python() -> Path:
    return CONDA_MACH_AERO / "bin" / "python"


def worker_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a MACH-Aero worker subprocess.

    ADflow lives in a source checkout rather than site-packages, so its parent
    directory goes on PYTHONPATH.
    """
    out = dict(os.environ)
    adflow_parent = str(MACH_AERO_PACKAGES / "adflow")
    existing = out.get("PYTHONPATH", "")
    out["PYTHONPATH"] = f"{adflow_parent}{os.pathsep}{existing}" if existing else adflow_parent
    out.setdefault("OMP_NUM_THREADS", "1")
    if extra:
        out.update(extra)
    return out


def cpu_count() -> int:
    return os.cpu_count() or 1


def available_memory_gib() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for row in handle:
                if row.startswith("MemAvailable:"):
                    return int(row.split()[1]) / (1024 * 1024)
    except Exception:  # noqa: BLE001
        pass
    return 0.0


if __name__ == "__main__":
    found = detect()
    width = max(len(r["tool"]) for r in found.as_rows())
    for row in found.as_rows():
        mark = "OK " if row["status"] == "ready" else "-- "
        print(f"{mark}{row['tool']:<{width}}  {row['version'][:34]:<34} {row['where']:<16} {row['detail'][:60]}")
    print(f"\ncores {cpu_count()}   memory available {available_memory_gib():.1f} GiB")
