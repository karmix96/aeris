from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

from aeris.geometry.params import BWBDesignSample, BWBGeneratorConfig


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


def generate_spline_linear(
    y_vals: np.ndarray,
    x_vals: np.ndarray,
    split_index: int,
    n_spline_inboard: int,
    n_spline_outboard: int,
    curvature_strength: float = 0.7,
) -> tuple[np.ndarray, np.ndarray]:
    y_spline = np.linspace(np.min(y_vals), y_vals[split_index], n_spline_inboard)

    spline_func = CubicSpline(y_vals, x_vals, bc_type="clamped")
    x_spline_full = spline_func(y_spline)

    x_linear_baseline = np.interp(
        y_spline,
        [np.min(y_vals), y_vals[split_index]],
        [x_vals[0], x_vals[split_index]],
    )

    x_spline = x_linear_baseline + curvature_strength * (x_spline_full - x_linear_baseline)

    y_linear = np.linspace(y_vals[split_index], y_vals[-1], n_spline_outboard)
    x_linear = np.interp(
        y_linear,
        [y_vals[split_index], y_vals[-1]],
        [x_vals[split_index], x_vals[-1]],
    )

    return np.concatenate((y_spline, y_linear[1:])), np.concatenate((x_spline, x_linear[1:]))


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

    Important architectural rule:
    once a BWBDesignSample has been chosen, geometry realization should be
    deterministic. The old version used RNG here, which meant that the same
    sampled design vector could produce different geometries depending on a
    downstream random stream.

    This implementation preserves the idea of controlled local variation while
    making the realization a pure function of (n_segments, total_length,
    variation).
    """
    if n_segments <= 0:
        return np.array([], dtype=float)

    mean_seg = total_length / n_segments
    if variation <= 0.0 or n_segments == 1:
        return np.full(n_segments, mean_seg, dtype=float)

    profile = _deterministic_profile(n_segments)
    segments = mean_seg * (1.0 + variation * profile)
    segments = segments * (total_length / np.sum(segments))
    return segments.astype(float)


def generate_group_sweep(
    n_segments: int,
    fixed_s_rad: float,
    variation: float = 0.10,
) -> np.ndarray:
    """
    Deterministic sweep realization for the same reason as
    generate_group_segments().
    """
    if n_segments <= 0:
        return np.array([], dtype=float)

    if variation <= 0.0 or n_segments == 1:
        return np.full(n_segments, fixed_s_rad, dtype=float)

    profile = _deterministic_profile(n_segments)
    return (fixed_s_rad * (1.0 + variation * profile)).astype(float)


def compute_le_curve(
    x0: float,
    y0: float,
    b_params: np.ndarray,
    s_rad_params: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    x_points = [x0]
    y_points = [y0]

    for b, s_rad in zip(b_params, s_rad_params):
        dx = b / np.tan(s_rad)
        x_points.append(x_points[-1] - dx)
        y_points.append(y_points[-1] + b)

    return np.array(x_points, dtype=float), np.array(y_points, dtype=float)


def _validate_controls(config: BWBGeneratorConfig) -> None:
    ctrl = config.controls

    if ctrl.n_points < 4:
        raise ValueError(
            f"controls.n_points must be at least 4, got {ctrl.n_points}."
        )

    if ctrl.n_spline_inboard < 2:
        raise ValueError(
            "controls.n_spline_inboard must be at least 2."
        )

    if ctrl.n_spline_outboard < 2:
        raise ValueError(
            "controls.n_spline_outboard must be at least 2."
        )

    if not (0.0 < ctrl.spline_split_ratio < 1.0):
        raise ValueError(
            f"controls.spline_split_ratio must be in (0, 1), got {ctrl.spline_split_ratio}."
        )


def generate_bwb_planform_from_sample(
    sample: BWBDesignSample,
    config: BWBGeneratorConfig,
) -> PlanformResult:
    _validate_controls(config)

    ctrl = config.controls

    c1 = sample.c1_m
    c2_ratio = sample.c2_ratio
    c3_ratio = sample.c3_ratio
    c4_ratio = sample.c4_ratio

    c2 = c1 * c2_ratio
    c3 = c1 * c3_ratio
    c4 = c1 * c4_ratio

    b_total = sample.b_total_m
    b3_ratio = sample.b3_ratio
    b3 = b_total * b3_ratio

    remaining_b = b_total - b3
    split_ratio = sample.split_ratio
    b1 = remaining_b * split_ratio
    b2 = remaining_b - b1

    sw1_deg = sample.sw1_deg
    sw2_deg = sample.sw2_deg
    sw3_deg = sample.sw3_deg

    sw1_rad, sw2_rad, sw3_rad = np.radians(90.0 - np.array([sw1_deg, sw2_deg, sw3_deg]))

    N1 = int(round((b1 / b_total) * (ctrl.n_points - 1)))
    N2 = int(round((b2 / b_total) * (ctrl.n_points - 1)))
    N3 = (ctrl.n_points - 1) - N1 - N2

    if min(N1, N2, N3) < 1:
        raise ValueError(
            "Invalid segment discretization produced by current sample and n_points: "
            f"N1={N1}, N2={N2}, N3={N3}. "
            "Increase controls.n_points or narrow span split bounds."
        )

    b_group1 = generate_group_segments(N1, b1, ctrl.segment_length_variation)
    b_group2 = generate_group_segments(N2, b2, ctrl.segment_length_variation)
    b_group3 = generate_group_segments(N3, b3, ctrl.segment_length_variation)
    b_le = np.concatenate((b_group1, b_group2, b_group3))

    s_group1 = generate_group_sweep(N1, sw1_rad, ctrl.sweep_variation)
    s_group2 = generate_group_sweep(N2, sw2_rad, ctrl.sweep_variation)
    s_group3 = generate_group_sweep(N3, sw3_rad, ctrl.sweep_variation)
    s_rad_le = np.concatenate((s_group1, s_group2, s_group3))

    x_le, y_le = compute_le_curve(0.0, 0.0, b_le, s_rad_le)

    key_indices = np.array([0, N1, N1 + N2, ctrl.n_points - 1], dtype=int)
    key_chords = np.array([c1, c2, c3, c4], dtype=float)
    all_indices = np.arange(ctrl.n_points, dtype=int)
    chords = np.interp(all_indices, key_indices, key_chords)

    x_te = x_le + chords
    y_te = y_le.copy()

    split_idx = int(ctrl.n_points * ctrl.spline_split_ratio)
    split_idx = min(max(split_idx, 1), ctrl.n_points - 2)

    front_y_fine, front_x_fine = generate_spline_linear(
        y_le,
        x_le,
        split_idx,
        ctrl.n_spline_inboard,
        ctrl.n_spline_outboard,
        curvature_strength=ctrl.curvature_strength,
    )
    rear_y_fine, rear_x_fine = generate_spline_linear(
        y_te,
        x_te,
        split_idx,
        ctrl.n_spline_inboard,
        ctrl.n_spline_outboard,
        curvature_strength=ctrl.curvature_strength,
    )

    front_x_mirrored = front_x_fine.copy()
    front_y_mirrored = -front_y_fine
    rear_x_mirrored = rear_x_fine.copy()
    rear_y_mirrored = -rear_y_fine

    local_chords_fine = rear_x_fine - front_x_fine
    semi_span_m = float(front_y_fine[-1])
    full_span_m = 2.0 * semi_span_m
    area_half = float(np.trapezoid(local_chords_fine, front_y_fine))
    approx_area_m2 = 2.0 * area_half
    approx_aspect_ratio = full_span_m**2 / approx_area_m2 if approx_area_m2 > 0.0 else float("nan")

    group_boundary_y = np.array([y_le[0], y_le[N1], y_le[N1 + N2], y_le[-1]], dtype=float)
    num_sections = ctrl.n_spline_inboard + ctrl.n_spline_outboard - 1

    return PlanformResult(
        n_points=ctrl.n_points,
        n_spline_inboard=ctrl.n_spline_inboard,
        n_spline_outboard=ctrl.n_spline_outboard,
        split_idx=split_idx,
        c1=float(c1),
        c2=float(c2),
        c3=float(c3),
        c4=float(c4),
        c2_ratio=float(c2_ratio),
        c3_ratio=float(c3_ratio),
        c4_ratio=float(c4_ratio),
        b_total=float(b_total),
        b1=float(b1),
        b2=float(b2),
        b3=float(b3),
        b3_ratio=float(b3_ratio),
        split_ratio=float(split_ratio),
        sw1_deg=float(sw1_deg),
        sw2_deg=float(sw2_deg),
        sw3_deg=float(sw3_deg),
        N1=N1,
        N2=N2,
        N3=N3,
        x_le=x_le,
        y_le=y_le,
        x_te=x_te,
        y_te=y_te,
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
        approx_aspect_ratio=float(approx_aspect_ratio),
    )


def generate_bwb_planform(
    config: BWBGeneratorConfig,
    rng: np.random.Generator,
) -> PlanformResult:
    from aeris.geometry.sampling import sample_bwb_design

    sample = sample_bwb_design(config, rng)
    return generate_bwb_planform_from_sample(sample, config)
