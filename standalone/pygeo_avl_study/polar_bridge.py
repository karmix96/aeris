"""NeuralFoil and AVL-CDCL utilities for the standalone feasibility study.

Two NeuralFoil interfaces are intentionally exposed:

``core``
    The raw NeuralFoil call used by Aeris today.  It is incompressible.

``aerosandbox_extended``
    AeroSandbox's wrapper around the same network, which adds its documented
    compressibility and post-stall corrections while preserving NeuralFoil's
    confidence output.

This separation lets the study quantify what AeroSandbox still contributes
when pyGeo becomes the master geometry generator.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from aeris.airfoil.polar_store import CdclParams, _fit_cdcl_from_arrays


@dataclass(frozen=True)
class PolarCurve:
    alpha_deg: np.ndarray
    cl: np.ndarray
    cd: np.ndarray
    cm: np.ndarray
    confidence: np.ndarray
    reynolds: float
    mach: float
    interface: str

    def finite_mask(self) -> np.ndarray:
        return (
            np.isfinite(self.alpha_deg)
            & np.isfinite(self.cl)
            & np.isfinite(self.cd)
            & (self.cd > 0.0)
        )

    @property
    def min_confidence(self) -> float:
        values = self.confidence[np.isfinite(self.confidence)]
        return float(np.min(values)) if len(values) else float("nan")


def shape_id(coordinates: np.ndarray) -> str:
    rounded = np.round(np.asarray(coordinates, dtype="<f8"), decimals=12)
    return "pygeo_" + hashlib.sha256(rounded.tobytes()).hexdigest()[:20]


def evaluate_neuralfoil(
    coordinates: np.ndarray,
    *,
    alpha_deg: Sequence[float] | np.ndarray,
    reynolds: float,
    mach: float = 0.0,
    interface: str = "aerosandbox_extended",
    model_size: str = "large",
    n_crit: float = 9.0,
    include_360_deg_effects: bool = False,
) -> PolarCurve:
    """Evaluate one normalised Selig airfoil with a declared NF interface."""
    import aerosandbox as asb

    alpha = np.asarray(alpha_deg, dtype=float)
    if alpha.ndim != 1:
        raise ValueError("alpha_deg must be one-dimensional")
    if reynolds <= 0.0:
        raise ValueError("reynolds must be positive")

    airfoil = asb.Airfoil(name=shape_id(coordinates), coordinates=coordinates)
    kulfan = airfoil.to_kulfan_airfoil(
        n_weights_per_side=8,
        N1=0.5,
        N2=1.0,
    )
    mode = interface.strip().lower()
    if mode == "core":
        import neuralfoil as nf

        result = nf.get_aero_from_kulfan_parameters(
            kulfan_parameters={
                "lower_weights": np.asarray(kulfan.lower_weights, dtype=float),
                "upper_weights": np.asarray(kulfan.upper_weights, dtype=float),
                "leading_edge_weight": float(kulfan.leading_edge_weight),
                "TE_thickness": float(kulfan.TE_thickness),
            },
            alpha=alpha,
            Re=float(reynolds),
            n_crit=float(n_crit),
            xtr_upper=1.0,
            xtr_lower=1.0,
            model_size=model_size,
        )
    elif mode == "aerosandbox_extended":
        result = kulfan.get_aero_from_neuralfoil(
            alpha=alpha,
            Re=float(reynolds),
            mach=float(mach),
            n_crit=float(n_crit),
            model_size=model_size,
            include_360_deg_effects=bool(include_360_deg_effects),
        )
    else:
        raise ValueError("interface must be 'core' or 'aerosandbox_extended'")

    def vector(key: str, default: float = float("nan")) -> np.ndarray:
        value = result.get(key, np.full_like(alpha, default))
        array = np.asarray(value, dtype=float).reshape(-1)
        if array.size == 1:
            array = np.full_like(alpha, float(array[0]))
        if array.size != alpha.size:
            raise ValueError(f"NeuralFoil field {key!r} has size {array.size}")
        return array

    return PolarCurve(
        alpha_deg=alpha,
        cl=vector("CL"),
        cd=vector("CD"),
        cm=vector("CM"),
        confidence=vector("analysis_confidence"),
        reynolds=float(reynolds),
        mach=float(mach),
        interface=mode,
    )


def fit_cdcl_current(curve: PolarCurve) -> CdclParams:
    """Apply the current production Aeris CDCL fitter."""
    mask = curve.finite_mask()
    cl = curve.cl[mask]
    cd = curve.cd[mask]
    order = np.argsort(cl)
    return _fit_cdcl_from_arrays(cl[order], cd[order])


def fit_cdcl_corrected(curve: PolarCurve) -> CdclParams:
    """Symmetric drag-bucket endpoint selection used as an audit comparator.

    The production fitter's negative-side loop can select a point that is
    still outside the threshold when several consecutive low-CL points have
    high drag.  This version selects the first point *inside* the bucket on
    each side and is not injected unless explicitly requested.
    """
    mask = curve.finite_mask()
    cl = curve.cl[mask]
    cd = curve.cd[mask]
    order = np.argsort(cl)
    cl = cl[order]
    cd = cd[order]
    if len(cl) < 3:
        raise ValueError("Need at least three finite polar points")

    i_min = int(np.argmin(cd))
    cl2, cd2 = float(cl[i_min]), float(cd[i_min])
    threshold = max(3.0 * cd2, cd2 + 0.015)

    left_indices = np.arange(0, i_min)
    left_good = left_indices[cd[left_indices] <= threshold]
    if len(left_good):
        i_left = int(left_good[0])
    elif len(left_indices):
        i_left = int(left_indices[-1])
    else:
        i_left = i_min

    right_indices = np.arange(i_min + 1, len(cl))
    right_good = right_indices[cd[right_indices] <= threshold]
    if len(right_good):
        i_right = int(right_good[-1])
    elif len(right_indices):
        i_right = int(right_indices[0])
    else:
        i_right = i_min

    # Preserve strict CL ordering even for a one-sided truncated alpha sweep.
    if i_left == i_min:
        cl1, cd1 = cl2 - 0.5, min(2.0 * cd2, 0.9 * threshold)
    else:
        cl1, cd1 = float(cl[i_left]), float(cd[i_left])
    if i_right == i_min:
        cl3, cd3 = cl2 + 0.6, min(2.0 * cd2, 0.9 * threshold)
    else:
        cl3, cd3 = float(cl[i_right]), float(cd[i_right])
    params = CdclParams(
        cl1=cl1,
        cd1=max(cd1, cd2),
        cl2=cl2,
        cd2=cd2,
        cl3=cl3,
        cd3=max(cd3, cd2),
    )
    if not params.is_valid():
        raise ValueError(f"Corrected CDCL fit is invalid: {params}")
    return params


def cdcl_bucket_cd(params: CdclParams, cl: np.ndarray | float) -> np.ndarray:
    """Evaluate AVL's two in-bucket parabolas.

    Values beyond CL1/CL3 are clipped to the endpoint here; AVL itself adds a
    rapid quadratic post-endpoint rise.  Error metrics should therefore be
    reported separately for points inside and outside the bucket.
    """
    cl_array = np.asarray(cl, dtype=float)
    clipped = np.clip(cl_array, params.cl1, params.cl3)
    left = clipped <= params.cl2
    result = np.empty_like(clipped)
    left_scale = max(params.cl2 - params.cl1, 1.0e-12)
    right_scale = max(params.cl3 - params.cl2, 1.0e-12)
    result[left] = params.cd2 + (params.cd1 - params.cd2) * (
        (clipped[left] - params.cl2) / left_scale
    ) ** 2
    result[~left] = params.cd2 + (params.cd3 - params.cd2) * (
        (clipped[~left] - params.cl2) / right_scale
    ) ** 2
    return result


class SectionAirfoilMap:
    """Nearest realised-section lookup expected by Aeris's CDCL injector."""

    def __init__(self, y_m: Sequence[float], airfoil_ids: Sequence[str], coordinates):
        if not (len(y_m) == len(airfoil_ids) == len(coordinates)):
            raise ValueError("Section map inputs must have equal length")
        order = np.argsort(np.asarray(y_m, dtype=float))
        self.y_m = np.asarray(y_m, dtype=float)[order]
        self.airfoil_ids = [str(airfoil_ids[i]) for i in order]
        self.coordinates = [
            np.asarray(coordinates[i], dtype=float) for i in order
        ]

    def _index(self, y_m: float) -> int:
        return int(np.argmin(np.abs(self.y_m - float(y_m))))

    def get_airfoil_id(self, y_m: float) -> str:
        return self.airfoil_ids[self._index(y_m)]

    def get_coordinates(self, y_m: float) -> np.ndarray:
        return self.coordinates[self._index(y_m)]


class LiveNeuralFoilSource:
    """Exact-Re live polar source for injection and strip integration.

    Unlike the current production ``query_cd_batch`` implementation, rows
    sharing a shape but having different Reynolds numbers are not collapsed
    to the median Reynolds number.
    """

    def __init__(
        self,
        *,
        interface: str = "aerosandbox_extended",
        model_size: str = "large",
        n_crit: float = 9.0,
        alpha_grid_deg: Sequence[float] = tuple(np.linspace(-10.0, 20.0, 31)),
        fitter: str = "current",
        confidence_floor: float | None = None,
    ) -> None:
        self.interface = interface
        self.model_size = model_size
        self.n_crit = float(n_crit)
        self.alpha_grid_deg = np.asarray(alpha_grid_deg, dtype=float)
        self.fitter = fitter
        self.confidence_floor = confidence_floor
        self._coordinates: dict[str, np.ndarray] = {}
        self._cache: dict[tuple[str, float, float], PolarCurve] = {}

    def register_shape(self, coordinates: np.ndarray, airfoil_id: str | None = None) -> str:
        aid = airfoil_id or shape_id(coordinates)
        self._coordinates.setdefault(aid, np.asarray(coordinates, dtype=float))
        return aid

    def has_airfoil(self, airfoil_id: str) -> bool:
        return airfoil_id in self._coordinates

    def _curve(self, airfoil_id: str, re: float, mach: float) -> PolarCurve | None:
        coordinates = self._coordinates.get(airfoil_id)
        if coordinates is None:
            return None
        key = (airfoil_id, round(float(re), -2), round(float(mach), 4))
        if key not in self._cache:
            self._cache[key] = evaluate_neuralfoil(
                coordinates,
                alpha_deg=self.alpha_grid_deg,
                reynolds=float(re),
                mach=float(mach),
                interface=self.interface,
                model_size=self.model_size,
                n_crit=self.n_crit,
                include_360_deg_effects=False,
            )
        return self._cache[key]

    def fit_cdcl(self, airfoil_id: str, re: float, mach: float = 0.0) -> CdclParams | None:
        curve = self._curve(airfoil_id, re, mach)
        if curve is None:
            return None
        if self.confidence_floor is not None and curve.min_confidence < self.confidence_floor:
            return None
        try:
            if self.fitter == "corrected":
                return fit_cdcl_corrected(curve)
            return fit_cdcl_current(curve)
        except (ValueError, FloatingPointError):
            return None

    def get_cl_bounds(
        self, airfoil_id: str, re: float, mach: float = 0.0
    ) -> tuple[float, float] | None:
        curve = self._curve(airfoil_id, re, mach)
        if curve is None:
            return None
        mask = curve.finite_mask()
        if not np.any(mask):
            return None
        return float(np.min(curve.cl[mask])), float(np.max(curve.cl[mask]))

    def query_cd(
        self, airfoil_id: str, cl: float, re: float, mach: float = 0.0
    ) -> float | None:
        curve = self._curve(airfoil_id, re, mach)
        if curve is None:
            return None
        mask = curve.finite_mask()
        if np.count_nonzero(mask) < 2:
            return None
        order = np.argsort(curve.cl[mask])
        return float(np.interp(cl, curve.cl[mask][order], curve.cd[mask][order]))

    def query_cd_batch(
        self,
        airfoil_ids: Sequence[str],
        cls: np.ndarray,
        res: np.ndarray,
        mach: float = 0.0,
    ) -> np.ndarray:
        if not (len(airfoil_ids) == len(cls) == len(res)):
            raise ValueError("airfoil_ids, cls, and res must have equal length")
        output = np.full(len(cls), np.nan)
        for i, (aid, cl, re) in enumerate(zip(airfoil_ids, cls, res)):
            value = self.query_cd(str(aid), float(cl), float(re), float(mach))
            if value is not None:
                output[i] = value
        return output
