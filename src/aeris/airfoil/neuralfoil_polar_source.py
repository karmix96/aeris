"""
NeuralFoil-backed viscous polar source for the AVL polar bridge.

Alternative to AirfoilPolarStore (curated XFOIL CSV) for DoE-scale campaigns
where every wing section's airfoil shape is geometrically unique (e.g.
extracted from a piecewise 3D CST wing surface) and pre-curating a per-shape
XFOIL database is impractical.

Geometry input contract
------------------------
This class accepts shapes as Selig-format (N,2) coordinate arrays -- the
SAME format CSTAirfoil.coordinates() already produces and the same format
asb.Airfoil(coordinates=...) already accepts elsewhere in this codebase.
It does NOT accept raw CST coefficients directly, and deliberately does not
attempt a hand-rolled coefficient conversion between this codebase's
CSTAirfoil (order=8, i.e. 9 coefficients per side, N1=0.5/N2=1.0, no
separate leading-edge-modification or TE-thickness fields) and NeuralFoil's
native Kulfan format (upper_weights(8,) + lower_weights(8,) +
leading_edge_weight + TE_thickness = 18 parameters total). These are
related but NOT identical parameterizations -- confirmed against NeuralFoil's
own documentation and AeroSandbox's KulfanAirfoil constructor signature.

Instead, conversion goes through coordinates using AeroSandbox's own
canonical, NeuralFoil-tested converter:
    asb.Airfoil(coordinates=coords).to_kulfan_airfoil(
        n_weights_per_side=8, N1=0.5, N2=1.0
    )
This guarantees compatibility with whatever NeuralFoil expects, rather than
risking a silent accuracy bug from an approximate coefficient refit.

Per-airfoil_id caching: airfoil_id here is expected to be a per-section,
per-geometry-instance identifier (e.g. a hash of the section's coordinates),
NOT a small fixed set of named airfoils like the curated-CSV mode. Callers
must register each unique shape via register_shape() before querying it --
there is no upfront "load everything" step like AirfoilPolarStore's CSV read,
since there is no finite pre-built database in this mode.
"""
from __future__ import annotations

import hashlib
import math
import logging
from dataclasses import dataclass

import numpy as np

from aeris.airfoil.polar_store import (
    CdclParams,
    _fit_cdcl_from_arrays,
    _bracket,
    _interpolate_cdcl,
)

log = logging.getLogger(__name__)

_DEFAULT_ALPHA_SWEEP_DEG = np.linspace(-8.0, 18.0, 14)
_DEFAULT_MODEL_SIZE = "large"
_MIN_POLAR_POINTS = 3

# Reynolds binning resolution for batched CD lookups, in decades (log10 Re).
# Strips within one bin share a single alpha-sweep evaluation; 0.1 dex keeps
# each strip within a factor of ~1.26 in Re of its bin representative.  This
# replaces the previous single-median-Re-per-shape collapse, which produced up
# to ~37.5% CD error across a 2e5..2e6 strip-Reynolds range.
_RE_BIN_DEX = 0.1


def shape_id_from_coordinates(coordinates: np.ndarray) -> str:
    """Stable hash-based airfoil_id for a coordinate array.

    Mirrors the SHA-256-of-coordinates convention already used for
    airfoil_id elsewhere in this codebase (airfoil_xfoil_v1 feature set
    group key), so NeuralFoil-sourced and XFOIL-sourced airfoil_ids follow
    the same identification scheme.
    """
    arr = np.asarray(coordinates, dtype=float)
    digest = hashlib.sha256(arr.tobytes()).hexdigest()
    return f"cst_{digest[:16]}"


@dataclass
class _RegisteredShape:
    coordinates: np.ndarray
    kulfan_lower_weights: np.ndarray
    kulfan_upper_weights: np.ndarray
    kulfan_leading_edge_weight: float
    kulfan_TE_thickness: float


class NeuralFoilPolarSource:
    """Live NeuralFoil evaluation, satisfying the same interface as AirfoilPolarStore.

    Unlike AirfoilPolarStore (load-once-from-CSV, query-many), this class is
    register-then-query: each unique section shape must be registered once
    (which performs the coordinate -> Kulfan conversion), after which
    fit_cdcl/get_cl_bounds/query_cd evaluate NeuralFoil on demand, batched
    per call where the caller supplies multiple (cl, re) pairs at once.
    """

    def __init__(self, model_size: str = _DEFAULT_MODEL_SIZE, n_crit: float = 9.0) -> None:
        self.model_size = model_size
        self.n_crit = n_crit
        self._shapes: dict[str, _RegisteredShape] = {}
        # Per-(airfoil_id, re_bin, mach_bin) cache of computed CdclParams,
        # since fit_cdcl is potentially called many times per case across
        # strips that share the same section.
        self._cdcl_cache: dict[tuple[str, float, float], CdclParams | None] = {}
        # Pre-warmed Re grid: (airfoil_id, mach_bin) -> list of
        # (re_bin, CdclParams) sorted ascending by re_bin. Populated by
        # warm_cdcl_grid(); consulted by fit_cdcl() for log-Re bracket
        # interpolation, mirroring AirfoilPolarStore.fit_cdcl exactly.
        self._cdcl_grid: dict[tuple[str, float], list[tuple[float, CdclParams]]] = {}
        self._grid_warmed: bool = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_shape(self, coordinates: "np.ndarray", airfoil_id: str | None = None) -> str:
        """Register a section shape (Selig-format (N,2) coordinates) and return its airfoil_id.

        If airfoil_id is not supplied, one is derived deterministically from
        the coordinates (shape_id_from_coordinates), so re-registering the
        same shape twice is a safe no-op and returns the same id.
        """
        coords = np.asarray(coordinates, dtype=float)
        aid = airfoil_id or shape_id_from_coordinates(coords)
        if aid in self._shapes:
            return aid

        try:
            import aerosandbox as asb
        except ImportError as exc:
            raise RuntimeError(
                "NeuralFoilPolarSource requires aerosandbox to be installed "
                "(provides the coordinates -> Kulfan conversion and the "
                "NeuralFoil evaluation backend)."
            ) from exc

        kulfan_airfoil = asb.Airfoil(coordinates=coords).to_kulfan_airfoil(
            n_weights_per_side=8, N1=0.5, N2=1.0
        )
        self._shapes[aid] = _RegisteredShape(
            coordinates=coords,
            kulfan_lower_weights=np.asarray(kulfan_airfoil.lower_weights, dtype=float),
            kulfan_upper_weights=np.asarray(kulfan_airfoil.upper_weights, dtype=float),
            kulfan_leading_edge_weight=float(kulfan_airfoil.leading_edge_weight),
            kulfan_TE_thickness=float(kulfan_airfoil.TE_thickness),
        )
        return aid

    def has_airfoil(self, airfoil_id: str) -> bool:
        return airfoil_id in self._shapes

    # ------------------------------------------------------------------
    # PolarSource interface
    # ------------------------------------------------------------------

    def fit_cdcl(self, airfoil_id: str, re: float, mach: float = 0.0) -> CdclParams | None:
        """Run a small alpha sweep through NeuralFoil and fit AVL CDCL params.

        Reuses the existing, already-tested _fit_cdcl_from_arrays() --
        identical algorithm to the curated-CSV path, just fed NeuralFoil-
        sourced (cl, cd) points instead of XFOIL-sourced ones.
        """
        # Preferred path: interpolate against the pre-warmed Re grid,
        # mirroring AirfoilPolarStore.fit_cdcl (log-Re bracket + interp).
        if self._grid_warmed:
            return self._fit_cdcl_from_grid(airfoil_id, re, mach)

        # Fallback (grid never warmed): on-demand single-Re evaluation,
        # cached by nearest-1000 Re bin. Preserves prior behaviour for
        # callers that use NeuralFoilPolarSource without pre-warming.
        re_bin = round(float(re), -3)
        mach_bin = round(float(mach), 3)
        cache_key = (airfoil_id, re_bin, mach_bin)
        if cache_key in self._cdcl_cache:
            return self._cdcl_cache[cache_key]

        result = self._fit_cdcl_uncached(airfoil_id, re, mach)
        self._cdcl_cache[cache_key] = result
        return result

    def _fit_cdcl_from_grid(
        self, airfoil_id: str, re: float, mach: float
    ) -> CdclParams | None:
        """Bracket *re* in the pre-warmed grid and log-Re interpolate.

        Identical convention to AirfoilPolarStore.fit_cdcl: select the
        two Re bins bracketing *re*, interpolate the fitted CdclParams
        in log(Re) space, fall back to the nearest single bin at the
        edges. Mach is matched to the nearest warmed mach bin.
        """
        # Nearest warmed mach bin for this airfoil.
        mach_keys = [m for (aid, m) in self._cdcl_grid if aid == airfoil_id]
        if not mach_keys:
            return None
        mach_sel = min(mach_keys, key=lambda m: abs(m - float(mach)))
        grid = self._cdcl_grid.get((airfoil_id, mach_sel))
        if not grid:
            return None

        re_bins = np.array([rb for (rb, _p) in grid], dtype=float)
        params_by_re = {rb: p for (rb, p) in grid}
        lo_re, hi_re = _bracket(re_bins, float(re))
        p_lo = params_by_re.get(lo_re)
        if p_lo is None:
            return None
        if lo_re == hi_re:
            return p_lo
        p_hi = params_by_re.get(hi_re)
        if p_hi is None:
            return p_lo
        t = (math.log(float(re)) - math.log(lo_re)) / (
            math.log(hi_re) - math.log(lo_re)
        )
        return _interpolate_cdcl(p_lo, p_hi, t)

    def warm_cdcl_grid(
        self,
        airfoil_ids: "list[str] | None" = None,
        *,
        re_grid: "list[float]",
        mach: float = 0.0,
    ) -> int:
        """Pre-compute fitted CdclParams for every (airfoil, Re-bin).

        This is the per-campaign batch step. For the requested airfoils
        (default: all registered) and the representative *re_grid*, it
        evaluates NeuralFoil for ALL (shape x alpha) combinations at
        each Re bin, fits a 3-point CDCL per (airfoil, Re-bin), and
        stores them sorted ascending by Re for log-Re interpolation in
        fit_cdcl(). After this runs, the DoE geometry loop makes zero
        NeuralFoil calls.

        Returns the number of (airfoil, Re-bin) grid points fitted.
        """
        ids = list(airfoil_ids) if airfoil_ids is not None else list(self._shapes)
        mach_bin = round(float(mach), 3)
        n_fitted = 0
        for aid in ids:
            shape = self._shapes.get(aid)
            if shape is None:
                continue
            grid_points: list[tuple[float, CdclParams]] = []
            for re_val in sorted(float(r) for r in re_grid):
                cl_arr, cd_arr = self._evaluate_alpha_sweep(
                    shape, re=re_val, mach=mach
                )
                if cl_arr is None or len(cl_arr) < _MIN_POLAR_POINTS:
                    continue
                order = np.argsort(cl_arr)
                try:
                    params = _fit_cdcl_from_arrays(cl_arr[order], cd_arr[order])
                except Exception as exc:
                    log.debug(
                        "warm_cdcl_grid: fit failed %r Re=%.0f: %s",
                        aid, re_val, exc,
                    )
                    continue
                grid_points.append((re_val, params))
                n_fitted += 1
            if grid_points:
                self._cdcl_grid[(aid, mach_bin)] = grid_points
        if n_fitted > 0:
            self._grid_warmed = True
        log.info(
            "NeuralFoilPolarSource: warmed %d (airfoil, Re) grid points "
            "across %d airfoils, %d Re bins",
            n_fitted, len(ids), len(list(re_grid)),
        )
        return n_fitted

    def _fit_cdcl_uncached(self, airfoil_id: str, re: float, mach: float) -> CdclParams | None:
        shape = self._shapes.get(airfoil_id)
        if shape is None:
            log.debug("NeuralFoilPolarSource: airfoil_id %r not registered", airfoil_id)
            return None

        cl_arr, cd_arr = self._evaluate_alpha_sweep(shape, re=re, mach=mach)
        if cl_arr is None or len(cl_arr) < _MIN_POLAR_POINTS:
            return None

        order = np.argsort(cl_arr)
        cl_sorted = cl_arr[order]
        cd_sorted = cd_arr[order]
        try:
            return _fit_cdcl_from_arrays(cl_sorted, cd_sorted)
        except Exception as exc:
            log.debug(
                "NeuralFoilPolarSource: CDCL fit failed for %r Re=%.0f Mach=%.2f: %s",
                airfoil_id, re, mach, exc,
            )
            return None

    def get_cl_bounds(
        self, airfoil_id: str, re: float, mach: float = 0.0
    ) -> tuple[float, float] | None:
        shape = self._shapes.get(airfoil_id)
        if shape is None:
            return None
        cl_arr, _ = self._evaluate_alpha_sweep(shape, re=re, mach=mach)
        if cl_arr is None or len(cl_arr) == 0:
            return None
        return float(np.min(cl_arr)), float(np.max(cl_arr))

    def query_cd(
        self, airfoil_id: str, cl: float, re: float, mach: float = 0.0
    ) -> float | None:
        """Single-point CD query via a single-alpha NeuralFoil call.

        Used by the post-AVL strip-integration cross-check
        (_compute_strip_profile_drag), one call per strip. For batched,
        per-case evaluation across many strips at once, use
        query_cd_batch() instead -- that is the path the bridge wiring
        should prefer for performance; this single-point method exists so
        NeuralFoilPolarSource satisfies the exact same interface as
        AirfoilPolarStore for callers that don't batch.
        """
        shape = self._shapes.get(airfoil_id)
        if shape is None:
            return None
        cl_arr, cd_arr = self._evaluate_alpha_sweep(shape, re=re, mach=mach)
        if cl_arr is None or len(cl_arr) < 2:
            return None
        order = np.argsort(cl_arr)
        return float(np.interp(cl, cl_arr[order], cd_arr[order]))

    # ------------------------------------------------------------------
    # Batched evaluation (per-case batching entry point)
    # ------------------------------------------------------------------

    def query_cd_batch(
        self,
        airfoil_ids: "list[str]",
        cls: "np.ndarray",
        res: "np.ndarray",
        mach: float = 0.0,
    ) -> "np.ndarray":
        """Batched CD lookup for many (airfoil_id, cl, re) rows in one NeuralFoil call.

        This is the per-case batching entry point: aerosandbox_avl.py's
        strip-integration call site should collect all strips for ONE AVL
        case into arrays and call this once, rather than calling query_cd()
        per strip. Internally this does one alpha-sweep-style NeuralFoil call
        per (registered shape, Reynolds bin) present in the batch -- strips of
        one shape are grouped into log-Re bins of width ``_RE_BIN_DEX`` and
        each bin is evaluated at its own representative Re. This replaces the
        earlier single-median-Re-per-shape collapse, which assigned one Re's
        polar to strips spanning a wide Reynolds range (up to ~37.5% CD error).

        Returns an array of cd values, NaN where lookup failed (unregistered
        shape, or evaluation error for that row) -- callers should treat NaN
        the same way query_cd's None is treated (skip that strip's
        contribution, do not crash).
        """
        airfoil_ids = list(airfoil_ids)
        cls = np.asarray(cls, dtype=float)
        res = np.asarray(res, dtype=float)
        if not (len(airfoil_ids) == len(cls) == len(res)):
            raise ValueError("airfoil_ids, cls, and res must have equal length")

        cd_out = np.full(len(airfoil_ids), np.nan, dtype=float)

        unique_ids = sorted(set(airfoil_ids))
        for aid in unique_ids:
            shape = self._shapes.get(aid)
            if shape is None:
                continue
            idx = np.array([i for i, a in enumerate(airfoil_ids) if a == aid])

            # Group this shape's strips into Reynolds bins and evaluate one
            # polar per bin at that bin's representative (median) Re, rather
            # than collapsing every strip to a single median Re.
            safe_re = np.maximum(res[idx], 1.0)
            bin_keys = np.round(np.log10(safe_re) / _RE_BIN_DEX)
            for bkey in np.unique(bin_keys):
                bin_mask = bin_keys == bkey
                bin_idx = idx[bin_mask]
                rep_re = float(np.median(safe_re[bin_mask]))

                cl_curve, cd_curve = self._evaluate_alpha_sweep(
                    shape, re=rep_re, mach=mach
                )
                if cl_curve is None or len(cl_curve) < 2:
                    continue
                order = np.argsort(cl_curve)
                cd_out[bin_idx] = np.interp(
                    cls[bin_idx], cl_curve[order], cd_curve[order]
                )

        return cd_out

    # ------------------------------------------------------------------
    # Private: shared alpha-sweep evaluation
    # ------------------------------------------------------------------

    def _evaluate_alpha_sweep(
        self, shape: "_RegisteredShape", *, re: float, mach: float
    ) -> "tuple[np.ndarray | None, np.ndarray | None]":
        try:
            import neuralfoil as nf
        except ImportError as exc:
            raise RuntimeError(
                "NeuralFoilPolarSource requires the 'neuralfoil' package. "
                "Install with: pip install neuralfoil --break-system-packages"
            ) from exc

        n_alpha = len(_DEFAULT_ALPHA_SWEEP_DEG)
        kulfan_parameters = {
            "lower_weights": shape.kulfan_lower_weights,
            "upper_weights": shape.kulfan_upper_weights,
            "leading_edge_weight": shape.kulfan_leading_edge_weight,
            "TE_thickness": shape.kulfan_TE_thickness,
        }
        # NOTE (Mach): the raw NeuralFoil core (get_aero_from_kulfan_parameters)
        # is incompressible -- it has no Mach input and CD is Mach-independent.
        # ``mach`` is accepted for interface compatibility but is intentionally
        # NOT forwarded here, because doing so would be a silent no-op that
        # implies a compressibility model this source does not apply. If a
        # compressibility correction is wanted, route through AeroSandbox's
        # extended interface and document it as a wrapper correction, not
        # network output.
        _ = mach  # documented no-op for the raw incompressible core
        try:
            aero = nf.get_aero_from_kulfan_parameters(
                kulfan_parameters=kulfan_parameters,
                alpha=_DEFAULT_ALPHA_SWEEP_DEG,
                Re=np.full(n_alpha, max(float(re), 1.0)),
                n_crit=self.n_crit,
                model_size=self.model_size,
            )
        except Exception as exc:
            log.debug("NeuralFoilPolarSource: evaluation failed: %s", exc)
            return None, None

        cl = np.asarray(aero["CL"], dtype=float)
        cd = np.asarray(aero["CD"], dtype=float)
        valid = np.isfinite(cl) & np.isfinite(cd) & (cd > 0)
        if valid.sum() < _MIN_POLAR_POINTS:
            return None, None
        return cl[valid], cd[valid]



def build_neuralfoil_polar_store_for_segments(
    segment_airfoil_coords,
    *,
    semispan_m: float,
    model_size: str = _DEFAULT_MODEL_SIZE,
    n_crit: float = 9.0,
    re_grid: "list[float] | None" = None,
    mach: float = 0.0,
):
    """Build (SectionAirfoilMap, NeuralFoilPolarSource) for a fixed-airfoil DoE.

    This is the campaign-level entry point for the requested workflow: a
    segmented BWB with N fixed airfoils (e.g. root/kink/mid/tip), each given
    as Selig-format coordinates plus the spanwise fraction where its segment
    ends. The N shapes are registered ONCE (coords -> Kulfan via AeroSandbox),
    and -- if *re_grid* is supplied -- the CDCL grid is warmed ONCE via a
    batched NeuralFoil evaluation. The returned pair drops straight into
    solver_options["section_map"|"polar_store"]; the existing AVL injection
    path is unchanged.

    Args:
        segment_airfoil_coords: ordered list of (coords, y_frac_end) tuples,
            ascending by y_frac_end, last y_frac_end == 1.0. `coords` is an
            (N, 2) Selig-format array for that segment's airfoil.
        semispan_m: wing semispan, to convert y_frac_end -> y_m.
        model_size: NeuralFoil model size.
        n_crit: transition criterion.
        re_grid: representative Reynolds grid to pre-warm (default: no warm,
            on-demand evaluation). Pass the campaign's sweep.reynolds to get
            zero-NeuralFoil-calls-in-loop behaviour.
        mach: Mach number for the warmed grid.

    Returns:
        (SectionAirfoilMap, NeuralFoilPolarSource)
    """
    from types import SimpleNamespace
    from aeris.airfoil.section_map import SectionAirfoilMap

    source = NeuralFoilPolarSource(model_size=model_size, n_crit=n_crit)
    segments = []
    for coords, y_frac_end in segment_airfoil_coords:
        aid = source.register_shape(coords)
        segments.append(SimpleNamespace(airfoil_id=aid, y_frac_end=float(y_frac_end)))

    section_map = SectionAirfoilMap.from_segments(
        segments=segments,
        library_root=None,
        semispan_m=semispan_m,
    )

    if re_grid:
        source.warm_cdcl_grid(re_grid=list(re_grid), mach=mach)

    return section_map, source
