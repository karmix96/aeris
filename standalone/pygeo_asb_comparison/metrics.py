"""Reliable geometric metrics for the pyGeo and AeroSandbox backends.

Both backends realize the SAME sampled Aeris sections (same design vector), so
differences in these metrics are the two tools' realization differences (smooth
pyGeo B-spline loft vs AeroSandbox piecewise), not different designs.

Common schema (one dict per backend, same keys):
    span_m, planform_area_m2, aspect_ratio, mean_aerodynamic_chord_m,
    root_chord_m, tip_chord_m, taper_ratio, volume_m3, wetted_area_m2

Definitions:
    - span_m           : full (mirrored) span.
    - planform_area_m2 : full reference (x-y projected) area.
    - aspect_ratio     : span^2 / area.
    - MAC              : mean aerodynamic chord.
    - taper_ratio      : tip_chord / root_chord.
    - volume_m3        : full enclosed volume.
    - wetted_area_m2   : full wetted (surface) area.

pyGeo metrics come from the REALIZED loft (integrated over extracted sections);
AeroSandbox metrics come from its analytic Wing. That the two are computed by
different means is itself a documented source of the difference.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

COMMON_METRIC_KEYS = [
    "span_m",
    "planform_area_m2",
    "aspect_ratio",
    "mean_aerodynamic_chord_m",
    "root_chord_m",
    "tip_chord_m",
    "taper_ratio",
    "volume_m3",
    "wetted_area_m2",
]


def _root_tip_taper(chords: Sequence[float]) -> tuple[float, float, float]:
    root = float(chords[0])
    tip = float(chords[-1])
    taper = tip / root if root > 0 else float("nan")
    return root, tip, taper


def pygeo_metrics(extracted: Sequence[Any]) -> dict[str, float]:
    """Common-schema metrics from the realized pyGeo sections."""
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import realised_reference_metrics
    from aeris.generators.bwb_segmented_v1.pygeo_backend import _volume_and_wetted_area

    ordered = sorted(extracted, key=lambda s: float(s.y_m))
    ref = realised_reference_metrics(ordered, symmetric=True)
    vw = _volume_and_wetted_area(ordered)
    root, tip, taper = _root_tip_taper([s.chord_m for s in ordered])
    return {
        "span_m": float(ref["b_ref_y_m"]),
        "planform_area_m2": float(ref["s_ref_xy_m2"]),
        "aspect_ratio": float(ref["aspect_ratio_xy"]),
        "mean_aerodynamic_chord_m": float(ref["c_ref_m"]),
        "root_chord_m": root,
        "tip_chord_m": tip,
        "taper_ratio": taper,
        "volume_m3": float(vw["volume_m3"]),
        "wetted_area_m2": float(vw["wetted_area_m2"]),
    }


def asb_metrics(asb_result: Any) -> dict[str, float]:
    """Common-schema metrics from the AeroSandbox Wing."""
    wing = asb_result.wing
    rv = asb_result.reference_values
    xsecs = wing.xsecs
    root, tip, taper = _root_tip_taper([float(x.chord) for x in xsecs])
    # ASB exposes taper_ratio directly; prefer it, fall back to root/tip.
    taper = float(rv.get("taper_ratio", taper))

    wetted = float("nan")
    for attempt in (("area", {"type": "wetted"}), ("area_wetted", {})):
        try:
            fn = getattr(wing, attempt[0])
            wetted = float(fn(**attempt[1]))
            break
        except Exception:
            continue

    return {
        "span_m": float(rv["span_m"]),
        "planform_area_m2": float(rv["area_m2"]),
        "aspect_ratio": float(rv["aspect_ratio"]),
        "mean_aerodynamic_chord_m": float(rv["mean_aerodynamic_chord_m"]),
        "root_chord_m": root,
        "tip_chord_m": tip,
        "taper_ratio": taper,
        "volume_m3": float(rv.get("volume_m3", float("nan"))),
        "wetted_area_m2": wetted,
    }


def relative_diff(pygeo: dict[str, float], asb: dict[str, float]) -> dict[str, float]:
    """Signed relative difference (pyGeo − ASB) / ASB per common metric."""
    out: dict[str, float] = {}
    for k in COMMON_METRIC_KEYS:
        a = asb.get(k)
        p = pygeo.get(k)
        if a is None or p is None or not np.isfinite(a) or not np.isfinite(p) or a == 0:
            out[k] = float("nan")
        else:
            out[k] = (p - a) / abs(a)
    return out
