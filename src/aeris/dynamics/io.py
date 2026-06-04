"""
AERIS Dynamics — I/O Helpers
==============================
Persistence and readback for all dynamics artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

from aeris.dynamics.models import DynamicsFoundationResult


# ---------------------------------------------------------------------------
# Dynamics foundation
# ---------------------------------------------------------------------------

def write_dynamics_foundation_result(
    result: DynamicsFoundationResult,
    output_dir: Path,
) -> Path:
    """Write dynamics_foundation.json to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "dynamics_foundation.json"
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path


def read_dynamics_foundation_result(path: str | Path) -> dict:
    """Load dynamics_foundation.json as a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_dynamics_foundation(run_dir: str | Path) -> Path | None:
    """Locate dynamics_foundation.json in a run directory."""
    for cand in [
        Path(run_dir) / "dynamics" / "dynamics_foundation.json",
        Path(run_dir) / "dynamics_foundation.json",
    ]:
        if cand.exists():
            return cand
    return None


# ---------------------------------------------------------------------------
# CG sweep
# ---------------------------------------------------------------------------

def read_cg_sweep(path: str | Path) -> dict:
    """Load cg_sweep.json as a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_cg_sweep(run_dir: str | Path) -> Path | None:
    """Locate cg_sweep.json in a run directory."""
    for cand in [
        Path(run_dir) / "dynamics" / "cg_sweep.json",
        Path(run_dir) / "cg_sweep.json",
    ]:
        if cand.exists():
            return cand
    return None


# ---------------------------------------------------------------------------
# Trim result
# ---------------------------------------------------------------------------

def read_trim_result(path: str | Path) -> dict:
    """Load trim_result.json as a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_trim_result(run_dir: str | Path) -> Path | None:
    """Locate trim_result.json in a run directory."""
    for cand in [
        Path(run_dir) / "dynamics" / "trim_result.json",
        Path(run_dir) / "trim_result.json",
    ]:
        if cand.exists():
            return cand
    return None