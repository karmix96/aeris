"""
Shared interface for viscous polar sources used by the AVL polar bridge.

Both AirfoilPolarStore (curated XFOIL CSV) and NeuralFoilPolarSource
(live NeuralFoil evaluation) implement this same surface. The two call
sites that consume a polar source -- avl_polar_injection.inject_polar_cdcl()
and aerosandbox_avl._compute_strip_profile_drag() -- only ever call these
three methods, confirmed by direct inspection of both call sites. Neither
call site needs to know or care which backend it's talking to.

This is a Protocol (structural typing), not a base class -- AirfoilPolarStore
is NOT modified to inherit from anything. It already satisfies this shape.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from aeris.airfoil.polar_store import CdclParams


@runtime_checkable
class PolarSource(Protocol):
    """Structural interface for any viscous-polar backend usable by the AVL bridge."""

    def fit_cdcl(self, airfoil_id: str, re: float, mach: float = 0.0) -> CdclParams | None:
        """Return AVL CDCL 3-point parameters, or None if unavailable for this airfoil."""
        ...

    def get_cl_bounds(
        self, airfoil_id: str, re: float, mach: float = 0.0
    ) -> tuple[float, float] | None:
        """Return (cl_min, cl_max) covered by this source for this airfoil, or None."""
        ...

    def query_cd(
        self, airfoil_id: str, cl: float, re: float, mach: float = 0.0
    ) -> float | None:
        """Return profile cd at (cl, Re, Mach), or None if unavailable."""
        ...
