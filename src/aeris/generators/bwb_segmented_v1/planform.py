"""
Deterministic 2D planform generation for bwb_segmented_v1.

This module converts an explicit sampled BWB design vector into a planform
representation containing:
- control-point geometry
- spline/linear discretized leading and trailing edges
- spanwise segmentation metadata
- basic geometric summary metrics

Convention notes
----------------
* Sweep angles (sw1_deg, sw2_deg, sw3_deg) are stored in BWBDesignSample as
  **negative** values (LE sweeps back toward +x as span increases).  The
  conversion ``sw_rad = radians(90 - sw_deg)`` maps the signed sweep angle
  to the angle measured from the spanwise axis, which is what compute_le_curve
  uses via ``dx = b / tan(sw_rad)``.  A sweep of 0° would give sw_rad = 90°
  → tan = ∞; that edge case is guarded in compute_le_curve.

* Dihedral is handled in sections.py, not here.  planform.py is purely 2-D
  (x–y plane).

NumPy compatibility shim
------------------------
``np.trapz`` was deprecated in NumPy 1.24 and removed in 2.0.
``np.trapezoid`` was introduced in NumPy 2.0.
The helper ``_trapezoid`` below works on both versions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.validation import validate_planform_controls

# ---------------------------------------------------------------------------
# NumPy compatibility shim (2B.2)
# np.trapz  removed in NumPy 2.0; np.trapezoid added in NumPy 2.0.
# ---------------------------------------------------------------------------
if hasattr(np, "trapezoid"):
    _trapezoid = np.trapezoid          # NumPy >= 2.0
else:
    _trapezoid = np.trapz              # NumPy < 2.0  (pragma: no cover)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanformResult:
    n_points: int
    n_spline_inboard: int
    n_spline_outboard: int
    split_idx: int

    c1: float
    c2: float
    c3: float
    c4: float

    c2_ratio: float
    c3_ratio: float
    c4_ratio: float

    b_total: float
    b1: float
    b2: float
    b3: float
    b3_ratio: float
    split_ratio: float

    sw1_deg: float
    sw2_deg: float
    sw3_deg: float

    N1: int
    N2: int
    N3: int

    x_le: np.ndarray
    y_le: np.ndarray
    x_te: np.ndarray
    y_te: np.ndarray
    chords: np.ndarray

    b_le: np.ndarray
    s_rad_le: np.ndarray
    key_indices: np.ndarray
    key_chords: np.ndarray
    group_boundary_y: np.ndarray

    front_y_fine: np.ndarray
    front_x_fine: np.ndarray
    rear_y_fine: np.ndarray
    rear_x_fine: np.ndarray

    front_x_mirrored: np.ndarray
    front_y_mirrored: np.ndarray
    rear_x_mirrored: np.ndarray
    rear_y_mirrored: np.ndarray

    num_sections: int
    semi_span_m: float
    full_span_m: float
    approx_area_m2: float
    approx_aspect_ratio: float

    def __post_init__(self) -> None:
        # 2B.5 — freeze all numpy arrays so callers cannot mutate planform state
        for field_name, value in self.__dataclass_fields__.items():
            arr = getattr(self, field_name)
            if isinstance(arr, np.ndarray):
                arr.flags.writeable = False


# ---------------------------------------------------------------------------
# Internal geometry helpers
# ---------------------------------------------------------------------------

def generate_spline_linear(
    y_vals: np.ndarray,
    x_vals: np.ndarray,
    split_index: int,
    n_spline_inboard: int,
    n_spline_outboard: int,
    curvature_strength: float = 0.7,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Blend a cubic spline (inboard) with a linear segment (outboard) to form
    the discretised LE or TE curve.

    The inboard region uses a CubicSpline with ``bc_type='clamped'`` (zero
    slope at both endpoints), blended toward a straight-line baseline by
    ``curvature_strength``.  curvature_strength=1.0 → full spline;
    curvature_strength=0.0 → straight line.

    The outboard region is purely linear (straight panels — manufacturable).

    Note (D22 — deferred): ``bc_type='clamped'`` forces zero slope at the tip
    control point, which is an opinionated choice for BWB root fairings.
    Switching to ``not-a-knot`` is a shape decision, not a bug fix, and is
    deferred until the design-space review.
    """
    y_spline = np.linspace(np.min(y_vals), y_vals[split_index], n_spline_inboard)

    spline_func = CubicSpline(y_vals, x_vals, bc_type="clamped")
    x_spline_full = spline_func(y_spline)

    x_linear_baseline = np.interp(
        y_spline,
        [float(np.min(y_vals)), float(y_vals[split_index])],
        [float(x_vals[0]), float(x_vals[split_index])],
    )

    x_spline = x_linear_baseline + curvature_strength * (x_spline_full - x_linear_baseline)

    y_linear = np.linspace(y_vals[split_index], y_vals[-1], n_spline_outboard)
    x_linear = np.interp(
        y_linear,
        [float(y_vals[split_index]), float(y_vals[-1])],
        [float(x_vals[split_index]), float(x_vals[-1])],
    )

    return (
        np.concatenate((y_spline, y_linear[1:])),
        np.concatenate((x_spline, x_linear[1:])),
    )


def _deterministic_profile(n_segments: int) -> np.ndarray:
    if n_segments <= 0:
        return np.array([], dtype=float)
    if n_segments == 1:
        return np.array([1.0], dtype=float)
    return np.linspace(-1.0, 1.0, n_segments, dtype=float)


def generate_group_segments(
    n_segments: int,
    total_length: float,
    variation: float = 0.25,
) -> np.ndarray:
    """
    Deterministic segment-length realization.

    Produces ``n_segments`` positive lengths that sum to ``total_length``.
    The variation parameter controls how much individual segments deviate from
    the mean; variation=0.0 gives uniform segments.
    """
    if n_segments <= 0:
        raise ValueError(f"n_segments must be > 0, got {n_segments}")
    if total_length <= 0.0:
        raise ValueError(f"total_length must be > 0, got {total_length}")
    if not (0.0 <= variation < 1.0):
        raise ValueError(f"variation must be in [0, 1), got {variation}")

    profile = _deterministic_profile(n_segments)
    raw = 1.0 + variation * profile
    segments = raw * (total_length / raw.sum())
    return segments


def compute_le_curve(
    x0: float,
    y0: float,
    b_params: np.ndarray,
    s_rad_le: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute leading-edge control-point positions from span increments and
    sweep angles.

    Parameters
    ----------
    x0, y0 : float
        Root LE position (typically 0, 0).
    b_params : ndarray, shape (N,)
        Spanwise segment lengths (must all be > 0).
    s_rad_le : ndarray, shape (N,)
        Sweep angle for each segment in radians, measured from the spanwise
        axis (i.e., ``s_rad = radians(90 - sw_deg)`` where sw_deg is the
        conventional LE sweep angle from the chord axis).

    Returns
    -------
    x_points, y_points : ndarray, shape (N+1,)

    Raises
    ------
    ValueError
        If ``b_params`` and ``s_rad_le`` differ in length, or if any
        segment length is non-positive.

    Notes
    -----
    2B.4 — length mismatch raises immediately rather than silently producing
    a wrong-shaped result.

    2B.8 — extreme sweep angles (s_rad near 0 or π) would cause
    ``tan(s_rad)`` to approach 0, making dx blow up (near-chordwise sweep).
    We guard with a minimum |tan| threshold corresponding to ~89° sweep from
    the spanwise axis (≈1° from the chord axis), which is beyond any
    physically realistic BWB sweep angle.
    """
    # 2B.4 — input length validation
    if len(b_params) != len(s_rad_le):
        raise ValueError(
            f"compute_le_curve: b_params length ({len(b_params)}) != "
            f"s_rad_le length ({len(s_rad_le)})"
        )
    if len(b_params) == 0:
        return np.array([x0], dtype=float), np.array([y0], dtype=float)

    if np.any(np.asarray(b_params) <= 0.0):
        raise ValueError(
            "compute_le_curve: all segment lengths in b_params must be > 0; "
            f"got min={float(np.min(b_params)):.6g}"
        )

    # 2B.8 — divide-by-zero guard for extreme sweep angles
    _MIN_TAN = 1e-6  # corresponds to ~89.9° sweep from span axis — unphysical
    x_points = [x0]
    y_points = [y0]
    for b, s_rad in zip(b_params, s_rad_le):
        tan_s = float(np.tan(s_rad))
        if abs(tan_s) < _MIN_TAN:
            raise ValueError(
                f"compute_le_curve: sweep angle produces |tan(s_rad)|={abs(tan_s):.2e} "
                f"(s_rad={s_rad:.4f} rad).  This implies a near-chordwise LE, which is "
                "unphysical for a BWB.  Check your sweep bounds."
            )
        dx = b / tan_s
        x_points.append(x_points[-1] - dx)
        y_points.append(y_points[-1] + b)

    return np.array(x_points, dtype=float), np.array(y_points, dtype=float)


# ---------------------------------------------------------------------------
# Main planform builder
# ---------------------------------------------------------------------------

def generate_bwb_planform_from_sample(
    sample: BWBDesignSample,
    config: BWBGeneratorConfig,
) -> PlanformResult:
    """
    Convert a sampled BWB design vector into a fully discretised 2-D planform.

    All geometry is deterministic given the same sample and config.  No
    random state is used here.
    """
    # 2C.4 — single source of truth: delegate to validation.py
    validate_planform_controls(config)
    ctrl = config.controls

    # --- Chord breakdown ---
    c1 = sample.c1_m
    c2 = c1 * sample.c2_ratio
    c3 = c1 * sample.c3_ratio
    c4 = c1 * sample.c4_ratio

    # --- Span breakdown ---
    b_total = sample.b_total_m
    b3 = b_total * sample.b3_ratio
    remaining_b = b_total - b3
    b1 = remaining_b * sample.split_ratio
    b2 = remaining_b - b1

    # --- Sweep angles ---
    # sw*_deg are negative in the sample (LE sweeps back); 90 - sw_deg maps to
    # the angle from the spanwise axis used by compute_le_curve.
    sw1_deg = sample.sw1_deg
    sw2_deg = sample.sw2_deg
    sw3_deg = sample.sw3_deg
    # 2B.3 — explicit comment: subtract from 90 to convert from LE-sweep
    # convention (measured from chord axis) to spanwise-axis convention.
    sw1_rad, sw2_rad, sw3_rad = np.radians(
        90.0 - np.array([sw1_deg, sw2_deg, sw3_deg], dtype=float)
    )

    # --- Point counts per segment ---
    N1 = int(round((b1 / b_total) * (ctrl.n_points - 1)))
    N2 = int(round((b2 / b_total) * (ctrl.n_points - 1)))
    N3 = (ctrl.n_points - 1) - N1 - N2

    if min(N1, N2, N3) < 1:
        raise ValueError(
            "Invalid segment discretization: "
            f"N1={N1}, N2={N2}, N3={N3}.  "
            "Increase controls.n_points or narrow span-split bounds."
        )

    # --- Segment lengths along LE ---
    variation = ctrl.segment_length_variation
    b_group1 = generate_group_segments(N1, b1, variation)
    b_group2 = generate_group_segments(N2, b2, variation)
    b_group3 = generate_group_segments(N3, b3, variation)
    b_le = np.concatenate([b_group1, b_group2, b_group3])

    # --- Per-segment sweep angles along LE ---
    sweep_variation = ctrl.sweep_variation
    profile1 = _deterministic_profile(N1)
    profile2 = _deterministic_profile(N2)
    profile3 = _deterministic_profile(N3)

    s_group1 = sw1_rad * (1.0 + sweep_variation * profile1)
    s_group2 = sw2_rad * (1.0 + sweep_variation * profile2)
    s_group3 = sw3_rad * (1.0 + sweep_variation * profile3)
    s_rad_le = np.concatenate([s_group1, s_group2, s_group3])

    # --- LE control points ---
    x_le, y_le = compute_le_curve(0.0, 0.0, b_le, s_rad_le)

    # --- Chord distribution (linearly interpolated at key span stations) ---
    key_indices = np.array([0, N1, N1 + N2, ctrl.n_points - 1], dtype=int)
    key_chords = np.array([c1, c2, c3, c4], dtype=float)
    all_indices = np.arange(ctrl.n_points, dtype=float)
    chords = np.interp(all_indices, key_indices.astype(float), key_chords)

    # --- TE control points ---
    x_te = x_le + chords
    y_te = y_le.copy()

    # --- Group boundary spanwise positions ---
    group_boundary_y = np.array(
        [y_le[0], y_le[N1], y_le[N1 + N2], y_le[-1]], dtype=float
    )

    # --- Spline + linear discretisation ---
    split_idx = int(round(ctrl.spline_split_ratio * (ctrl.n_points - 1)))
    split_idx = max(1, min(split_idx, ctrl.n_points - 2))

    front_y_fine, front_x_fine = generate_spline_linear(
        y_le, x_le, split_idx,
        n_spline_inboard=ctrl.n_spline_inboard,
        n_spline_outboard=ctrl.n_spline_outboard,
        curvature_strength=ctrl.curvature_strength,
    )
    rear_y_fine, rear_x_fine = generate_spline_linear(
        y_te, x_te, split_idx,
        n_spline_inboard=ctrl.n_spline_inboard,
        n_spline_outboard=ctrl.n_spline_outboard,
        curvature_strength=ctrl.curvature_strength,
    )

    # --- Mirror for full-span (symmetric wing) ---
    front_x_mirrored = front_x_fine.copy()
    front_y_mirrored = -front_y_fine
    rear_x_mirrored = rear_x_fine.copy()
    rear_y_mirrored = -rear_y_fine

    # --- Summary metrics ---
    num_sections = len(front_y_fine)
    semi_span_m = float(front_y_fine[-1])
    full_span_m = 2.0 * semi_span_m

    fine_chords = rear_x_fine - front_x_fine
    # 2B.2 — use the portability shim instead of np.trapz / np.trapezoid directly
    approx_area_m2 = float(2.0 * _trapezoid(fine_chords, front_y_fine))
    approx_aspect_ratio = float(full_span_m ** 2 / approx_area_m2) if approx_area_m2 > 0.0 else 0.0

    return PlanformResult(
        n_points=ctrl.n_points,
        n_spline_inboard=ctrl.n_spline_inboard,
        n_spline_outboard=ctrl.n_spline_outboard,
        split_idx=split_idx,
        c1=c1, c2=c2, c3=c3, c4=c4,
        c2_ratio=sample.c2_ratio,
        c3_ratio=sample.c3_ratio,
        c4_ratio=sample.c4_ratio,
        b_total=b_total, b1=b1, b2=b2, b3=b3,
        b3_ratio=sample.b3_ratio,
        split_ratio=sample.split_ratio,
        sw1_deg=sw1_deg, sw2_deg=sw2_deg, sw3_deg=sw3_deg,
        N1=N1, N2=N2, N3=N3,
        x_le=x_le, y_le=y_le,
        x_te=x_te, y_te=y_te,
        chords=chords,
        b_le=b_le,
        s_rad_le=s_rad_le,
        key_indices=key_indices,
        key_chords=key_chords,
        group_boundary_y=group_boundary_y,
        front_y_fine=front_y_fine,
        front_x_fine=front_x_fine,
        rear_y_fine=rear_y_fine,
        rear_x_fine=rear_x_fine,
        front_x_mirrored=front_x_mirrored,
        front_y_mirrored=front_y_mirrored,
        rear_x_mirrored=rear_x_mirrored,
        rear_y_mirrored=rear_y_mirrored,
        num_sections=num_sections,
        semi_span_m=semi_span_m,
        full_span_m=full_span_m,
        approx_area_m2=approx_area_m2,
        approx_aspect_ratio=approx_aspect_ratio,
    )


# ---------------------------------------------------------------------------
# D23 — generate_bwb_planform (rng-based wrapper)
# Status: DEFERRED pending usage verification in Layer 4 (dataset/sampling).
# Do NOT add new callers.  If confirmed dead, delete at Layer 4 review.
# ---------------------------------------------------------------------------
def generate_bwb_planform(
    config: BWBGeneratorConfig,
    rng: np.random.Generator,
) -> PlanformResult:
    """
    Sample one random design vector from config bounds and generate its planform.

    .. deprecated::
        This wrapper exists only for legacy script compatibility.  New code
        should use ``generate_bwb_planform_from_sample`` with an explicit
        ``BWBDesignSample``.  Will be removed once D23 is resolved.
    """
    from aeris.generators.bwb_segmented_v1.sampling import sample_one_bwb_design
    sample = sample_one_bwb_design(config, rng)
    return generate_bwb_planform_from_sample(sample, config)