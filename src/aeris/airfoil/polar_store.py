"""
Airfoil polar store for the 2D→3D AVL bridge.

Loads a promoted XFOIL airfoil dataset and provides two services:

  1. fit_cdcl(airfoil_id, re, mach) → CdclParams
     Fits AVL-compatible CDCL 3-point parameters (CL1/CD1, CL2/CD2, CL3/CD3)
     from the tabular XFOIL polar.  Re interpolation uses log-spacing.

  2. query_cd(airfoil_id, cl, re, mach) → float | None
     Returns the profile drag coefficient at an arbitrary (cl, Re, Mach) point
     via nearest Re/Mach bin selection and linear interpolation in cl.
     Used as a post-processing cross-check against CDCL-corrected AVL totals.

  3. get_t_c(airfoil_id) → float | None
     Returns the maximum thickness ratio from the airfoil inventory, used to
     cross-check AeroSandbox's CLAF computation.

Design constraints
------------------
- Constructed once, shared across many AVL runs within a campaign.
- Thread-safe for read operations (no internal mutation after __init__).
- Graceful degradation: missing airfoil_id or insufficient data returns None
  without raising, so a failed polar lookup silently falls back to zero profile
  drag rather than aborting the aero run.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_MIN_POLAR_POINTS = 3
_CDCL_STALL_THRESHOLD_FACTOR = 3.0   # cd > factor*cd_min → stall region
_CDCL_STALL_ABS_FLOOR = 0.015        # absolute cd floor for stall detection


class CdclParams(NamedTuple):
    """AVL CDCL 3-point polar parameters.

    AVL interpolation model:
      cl < cl1  → rapid quadratic rise (negative stall)
      cl1–cl2   → parabolic drag bowl, left side
      cl2–cl3   → parabolic drag bowl, right side
      cl > cl3  → rapid quadratic rise (positive stall)
    """
    cl1: float   # negative-stall lift coefficient
    cd1: float   # drag at negative stall
    cl2: float   # lift at drag minimum (CLcdmin)
    cd2: float   # minimum drag coefficient (CDmin)
    cl3: float   # positive-stall lift coefficient
    cd3: float   # drag at positive stall

    def as_avl_line(self) -> str:
        """Format as AVL CDCL data line."""
        return (
            f"{self.cl1:.6f} {self.cd1:.8f}  "
            f"{self.cl2:.6f} {self.cd2:.8f}  "
            f"{self.cl3:.6f} {self.cd3:.8f}"
        )

    def is_valid(self) -> bool:
        return (
            self.cl1 < self.cl2 < self.cl3
            and self.cd1 >= self.cd2 > 0
            and self.cd3 >= self.cd2
        )


@dataclass(frozen=True)
class _PolarKey:
    """Hashable key for a (airfoil_id, Re, Mach) polar slice."""
    airfoil_id: str
    re_bin: float
    mach_bin: float


class AirfoilPolarStore:
    """Load-once, query-many polar store backed by a curated XFOIL dataset."""

    def __init__(self, dataset_path: Path | str) -> None:
        path = Path(dataset_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"AirfoilPolarStore: dataset not found at {path}. "
                "Run 'aeris airfoil dataset curate' first."
            )

        df = pd.read_csv(path)
        required = {"airfoil_id", "cl", "cd", "reynolds", "mach", "converged"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"AirfoilPolarStore: curated dataset missing columns: {missing}"
            )

        # Keep only converged rows with valid cl/cd
        df = df[df["converged"] == True].copy()   # noqa: E712
        df = df[df["cd"] > 0]
        df = df[df["cl"].notna() & df["cd"].notna()]
        df = df.sort_values(["airfoil_id", "reynolds", "mach", "cl"]).reset_index(drop=True)

        self._df = df
        self._airfoil_ids: frozenset[str] = frozenset(df["airfoil_id"].unique())

        # Optionally load inventory for t/c and geometry stats
        inv_path = path.parent / "airfoil_inventory.csv"
        self._inventory: pd.DataFrame | None = None
        if inv_path.exists():
            try:
                self._inventory = pd.read_csv(inv_path).set_index("airfoil_id")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def airfoil_ids(self) -> frozenset[str]:
        return self._airfoil_ids

    def has_airfoil(self, airfoil_id: str) -> bool:
        return airfoil_id in self._airfoil_ids

    def get_t_c(self, airfoil_id: str) -> float | None:
        """Return max thickness ratio from inventory, or None if unavailable."""
        if self._inventory is None or airfoil_id not in self._inventory.index:
            return None
        row = self._inventory.loc[airfoil_id]
        val = row.get("t_c", None)
        if val is None or (isinstance(val, float) and not math.isfinite(val)):
            return None
        return float(val)

    def fit_cdcl(
        self,
        airfoil_id: str,
        re: float,
        mach: float = 0.0,
    ) -> CdclParams | None:
        """Fit AVL CDCL 3-point parameters from the stored XFOIL polar.

        Selects the two Reynolds bins bracketing *re* and linearly interpolates
        the fitted CdclParams in log(Re) space.  Falls back to the nearest
        single bin if only one is available.

        Returns None if the airfoil is not in the store or data is insufficient.
        """
        sub = self._filter_airfoil(airfoil_id)
        if sub is None:
            return None

        re_bins = np.sort(sub["reynolds"].unique())
        mach_bins = np.sort(sub["mach"].unique())

        mach_sel = _nearest(mach_bins, mach)

        # Find the two Re bins bracketing the requested Re
        lo_re, hi_re = _bracket(re_bins, re)

        params_lo = self._fit_cdcl_at_bin(sub, lo_re, mach_sel)
        if lo_re == hi_re or params_lo is None:
            return params_lo

        params_hi = self._fit_cdcl_at_bin(sub, hi_re, mach_sel)
        if params_hi is None:
            return params_lo

        # Interpolate in log(Re) space
        t = (math.log(re) - math.log(lo_re)) / (math.log(hi_re) - math.log(lo_re))
        return _interpolate_cdcl(params_lo, params_hi, t)

    def get_cl_bounds(
        self,
        airfoil_id: str,
        re: float,
        mach: float = 0.0,
    ) -> tuple[float, float] | None:
        """Return (cl_min, cl_max) for the nearest Re/Mach bin, or None."""
        sub = self._filter_airfoil(airfoil_id)
        if sub is None:
            return None
        re_bins = np.sort(sub["reynolds"].unique())
        mach_bins = np.sort(sub["mach"].unique())
        re_sel = _nearest(re_bins, re)
        mach_sel = _nearest(mach_bins, mach)
        slice_df = sub[(sub["reynolds"] == re_sel) & (sub["mach"] == mach_sel)]
        if slice_df.empty:
            return None
        cl_arr = slice_df["cl"].to_numpy(float)
        return float(cl_arr.min()), float(cl_arr.max())

    def query_cd(
        self,
        airfoil_id: str,
        cl: float,
        re: float,
        mach: float = 0.0,
    ) -> float | None:
        """Return profile cd at (cl, Re, Mach) via nearest-bin + linear cl interpolation.

        Used as a post-processing cross-check; not on the critical path for AVL.
        Returns None if lookup fails (missing airfoil, insufficient data, etc.).
        """
        sub = self._filter_airfoil(airfoil_id)
        if sub is None:
            return None

        re_bins = np.sort(sub["reynolds"].unique())
        mach_bins = np.sort(sub["mach"].unique())

        re_sel = _nearest(re_bins, re)
        mach_sel = _nearest(mach_bins, mach)

        slice_df = sub[(sub["reynolds"] == re_sel) & (sub["mach"] == mach_sel)]
        if len(slice_df) < 2:
            return None

        cl_arr = slice_df["cl"].to_numpy(float)
        cd_arr = slice_df["cd"].to_numpy(float)
        order = np.argsort(cl_arr)
        cl_arr = cl_arr[order]
        cd_arr = cd_arr[order]

        return float(np.interp(cl, cl_arr, cd_arr))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _filter_airfoil(self, airfoil_id: str) -> pd.DataFrame | None:
        if not self.has_airfoil(airfoil_id):
            log.debug("AirfoilPolarStore: airfoil_id %r not found", airfoil_id)
            return None
        return self._df[self._df["airfoil_id"] == airfoil_id]

    def _fit_cdcl_at_bin(
        self,
        sub: pd.DataFrame,
        re: float,
        mach: float,
    ) -> CdclParams | None:
        slice_df = sub[(sub["reynolds"] == re) & (sub["mach"] == mach)]
        if len(slice_df) < _MIN_POLAR_POINTS:
            return None

        cl_arr = slice_df["cl"].to_numpy(float)
        cd_arr = slice_df["cd"].to_numpy(float)
        order = np.argsort(cl_arr)
        cl_arr = cl_arr[order]
        cd_arr = cd_arr[order]

        try:
            return _fit_cdcl_from_arrays(cl_arr, cd_arr)
        except Exception as exc:
            log.debug(
                "AirfoilPolarStore: CDCL fit failed for Re=%.0f Mach=%.2f: %s",
                re, mach, exc,
            )
            return None


# ---------------------------------------------------------------------------
# Core CDCL fitting algorithm
# ---------------------------------------------------------------------------

def _fit_cdcl_from_arrays(cl: np.ndarray, cd: np.ndarray) -> CdclParams:
    """Fit AVL CDCL 3-point parameters from sorted (cl, cd) arrays.

    Algorithm:
      1. Locate drag minimum → (CL2, CD2).
      2. Stall threshold = max(CD2 * FACTOR, CD2 + ABS_FLOOR).
      3. Negative stall (CL1, CD1): walk inward from left edge; use the last
         point with cd ≤ threshold, or the leftmost point if none exceed it.
      4. Positive stall (CL3, CD3): symmetric walk from right edge.
      5. Clamp cd values so cd1 ≥ cd2 and cd3 ≥ cd2.
    """
    if len(cl) < _MIN_POLAR_POINTS:
        raise ValueError(f"Need ≥ {_MIN_POLAR_POINTS} points, got {len(cl)}")

    idx_min = int(np.argmin(cd))
    cl2, cd2 = float(cl[idx_min]), float(cd[idx_min])

    threshold = max(cd2 * _CDCL_STALL_THRESHOLD_FACTOR, cd2 + _CDCL_STALL_ABS_FLOOR)

    # --- Negative stall ---
    left_cl = cl[:idx_min]
    left_cd = cd[:idx_min]
    cl1, cd1 = _find_stall_point(left_cl, left_cd, threshold, side="left",
                                  cl_ref=cl2, cd_ref=cd2)

    # --- Positive stall ---
    right_cl = cl[idx_min + 1:]
    right_cd = cd[idx_min + 1:]
    cl3, cd3 = _find_stall_point(right_cl, right_cd, threshold, side="right",
                                  cl_ref=cl2, cd_ref=cd2)

    # Enforce ordering invariants
    cd1 = max(cd1, cd2)
    cd3 = max(cd3, cd2)

    params = CdclParams(cl1=cl1, cd1=cd1, cl2=cl2, cd2=cd2, cl3=cl3, cd3=cd3)
    if not params.is_valid():
        raise ValueError(f"CDCL fit produced invalid params: {params}")
    return params


def _find_stall_point(
    cl_arr: np.ndarray,
    cd_arr: np.ndarray,
    threshold: float,
    side: str,
    cl_ref: float,
    cd_ref: float,
) -> tuple[float, float]:
    """Find the stall boundary on one side of the drag minimum.

    For the left side (side='left'), cl_arr runs from low to high CL
    (leftmost to rightmost approaching the minimum).  We want the furthest
    point (lowest CL) that is still within the drag bucket, i.e. the first
    point from the left that exceeds the threshold defines where the stall
    region starts — we use the point just inside that boundary.

    For the right side (side='right'), cl_arr runs from drag minimum outward.
    We want the last point before cd exceeds the threshold.
    """
    if len(cl_arr) == 0:
        # No data on this side — synthesize a mild extrapolation
        offset = 0.5 if side == "left" else 0.6
        sign = -1 if side == "left" else +1
        return float(cl_ref + sign * offset), float(min(cd_ref * 2.0, threshold * 0.9))

    if side == "left":
        # Walk left-to-right through left_arr; find where cd first exceeds threshold
        stall_pos = None
        for i in range(len(cl_arr)):
            if cd_arr[i] > threshold:
                stall_pos = i
                break
        if stall_pos is None:
            # All within bucket — use leftmost point
            return float(cl_arr[0]), float(cd_arr[0])
        # Use point just after the stall (first point inside the bucket from left)
        entry = stall_pos + 1 if stall_pos + 1 < len(cl_arr) else stall_pos
        return float(cl_arr[entry]), float(cd_arr[entry])
    else:
        # Walk left-to-right through right_arr; find where cd first exceeds threshold
        for i in range(len(cl_arr)):
            if cd_arr[i] > threshold:
                # Use the last good point before the rise
                if i == 0:
                    return float(cl_arr[0]), float(cd_arr[0])
                return float(cl_arr[i - 1]), float(cd_arr[i - 1])
        # All within bucket — use rightmost point
        return float(cl_arr[-1]), float(cd_arr[-1])


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------

def _nearest(bins: np.ndarray, value: float) -> float:
    """Return the bin value closest to *value*."""
    idx = int(np.argmin(np.abs(bins - value)))
    return float(bins[idx])


def _bracket(bins: np.ndarray, value: float) -> tuple[float, float]:
    """Return the two bin values that bracket *value* (or the same bin twice).

    When *value* is outside the range of *bins*, the boundary bin is returned
    twice so the caller gets t=0 or t=1 and no out-of-range extrapolation.
    """
    if len(bins) == 1:
        return float(bins[0]), float(bins[0])
    if value <= bins[0]:
        return float(bins[0]), float(bins[0])
    if value >= bins[-1]:
        return float(bins[-1]), float(bins[-1])
    idx_hi = int(np.searchsorted(bins, value, side="right"))
    idx_hi = min(idx_hi, len(bins) - 1)
    idx_lo = max(idx_hi - 1, 0)
    return float(bins[idx_lo]), float(bins[idx_hi])


def _interpolate_cdcl(lo: CdclParams, hi: CdclParams, t: float) -> CdclParams:
    """Linear interpolation between two CdclParams at parameter t ∈ [0, 1]."""
    def _lerp(a: float, b: float) -> float:
        return a + t * (b - a)

    params = CdclParams(
        cl1=_lerp(lo.cl1, hi.cl1),
        cd1=_lerp(lo.cd1, hi.cd1),
        cl2=_lerp(lo.cl2, hi.cl2),
        cd2=_lerp(lo.cd2, hi.cd2),
        cl3=_lerp(lo.cl3, hi.cl3),
        cd3=_lerp(lo.cd3, hi.cd3),
    )
    # Restore invariants that may drift under interpolation
    cd1 = max(params.cd1, params.cd2)
    cd3 = max(params.cd3, params.cd2)
    return CdclParams(
        cl1=params.cl1, cd1=cd1,
        cl2=params.cl2, cd2=params.cd2,
        cl3=params.cl3, cd3=cd3,
    )
