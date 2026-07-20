"""
External solver environment resolution.

The MDO Lab stack (pyHyp, ADflow) and SU2 live in a dedicated conda
environment, not in the AERIS interpreter (AERIS runs Python 3.13; the
mach-aero stack pins older ABI).  All solver execution therefore goes
through subprocess with the environment's own interpreter/binaries,
resolved here from environment variables with documented defaults.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

MACH_AERO_PREFIX_ENV = "MACH_AERO_CONDA_PREFIX"
DEFAULT_MACH_AERO_PREFIX = "/home/mike/miniconda3/envs/mach-aero"


def mach_aero_prefix() -> Path:
    return Path(os.environ.get(MACH_AERO_PREFIX_ENV, DEFAULT_MACH_AERO_PREFIX))


def mach_aero_python() -> Path:
    return mach_aero_prefix() / "bin" / "python"


def mach_aero_mpirun() -> Path:
    return mach_aero_prefix() / "bin" / "mpirun"


SU2_BIN_ENV = "AERIS_SU2_BIN"
SU2_PREFIX_ENV = "AERIS_SU2_CONDA_PREFIX"
DEFAULT_SU2_PREFIX = "/home/mike/miniconda3/envs/su2"


def su2_prefix() -> Path:
    return Path(os.environ.get(SU2_PREFIX_ENV, DEFAULT_SU2_PREFIX))


def su2_cfd() -> Path:
    """SU2_CFD binary: AERIS_SU2_BIN > PATH > dedicated su2 conda env."""
    explicit = os.environ.get(SU2_BIN_ENV)
    if explicit:
        return Path(explicit)
    found = shutil.which("SU2_CFD")
    if found:
        return Path(found)
    return su2_prefix() / "bin" / "SU2_CFD"


def su2_mpirun() -> Path:
    candidate = su2_prefix() / "bin" / "mpirun"
    if candidate.is_file():
        return candidate
    found = shutil.which("mpirun")
    return Path(found) if found else candidate
