"""
AERIS — Aerospace + AI conceptual design platform.

A modular pipeline for UAV
conceptual design: geometry generation, aero evaluation, dataset curation,
QC, promotion gating, and surrogate modeling.

This top-level package module is intentionally minimal. It does NOT eagerly
import any heavy subsystem (matplotlib, AeroSandbox, geometry generators).
Subpackages take care of their own initialization on first import.
"""

from __future__ import annotations

try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    try:
        __version__ = _pkg_version("aeris")
    except PackageNotFoundError:
        __version__ = "unknown"
except Exception:
    __version__ = "unknown"

__all__ = ["__version__"]