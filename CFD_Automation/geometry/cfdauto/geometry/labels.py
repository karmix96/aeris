"""Labels by rule, from the measured values."""

from __future__ import annotations

import numpy as np

# Starting thresholds (Stage 1 brief). Changes are recorded in Stage 0_Decisions/OPEN_DECISIONS.md.
T = {
    "bwb_root_over_semispan": 0.5,
    "bwb_root_over_outer": 2.2,     # brief: 2.5; lowered, see Stage 0_Decisions/OPEN_DECISIONS.md
    "bwb_root_over_outer_with_loss": 2.0,
    "bwb_root_loss": 0.25,          # share of root chord lost ...
    "bwb_loss_span": 0.30,          # ... within this share of the span
    "sweep_deg": 5.0,
    "rect_taper": 0.95,
    "kink_window": 0.15,            # share of span on each side of a candidate kink
    "kink_zone": (0.05, 0.95),
    "kink_sweep_deg": 5.0,
    "kink_chord_factor": 1.5,
    "kink_chord_slope_floor": 0.1,  # |dc/dy| * S / c_root below this counts as no slope
    "twist_deg": 1.0,
    "dihedral_inner": 0.20,
    "dihedral_deg": 1.0,
    "varying_dihedral_deg": 2.0,
    "high_ar": 8.0,
    "low_ar": 4.0,
}


def _line_slope(y, f, y0, y1):
    """Slope of f between y0 and y1 (from the end values)."""
    return (np.interp(y1, y, f) - np.interp(y0, y, f)) / (y1 - y0)


def shape_values(m: dict) -> dict:
    """The numbers the rules use, all from the measured wing."""
    a = {k: np.asarray(v) for k, v in m["along_span"].items()}
    y, c = a["y"], a["chord"]
    s = float(y[-1])
    c0, ctip = float(c[0]), float(c[-1])
    outer = y >= 0.5 * s
    c_outer = float(np.trapezoid(c[outer], y[outer]) / (s - y[outer][0]))
    c_loss = float(np.interp(T["bwb_loss_span"] * s, y, c))

    # kink search: compare the inboard and outboard windows around each candidate point
    w = T["kink_window"] * s
    kinks = []
    for y0 in np.unique(np.concatenate([np.linspace(*T["kink_zone"], 181) * s,
                                        [v for v in m["stations"]["y_m"] if 0.05 * s <= v <= 0.95 * s]])):
        lo, hi = max(0.0, y0 - w), min(s, y0 + w)
        sw_in = np.degrees(np.arctan(_line_slope(y, a["x_le"], lo, y0)))
        sw_out = np.degrees(np.arctan(_line_slope(y, a["x_le"], y0, hi)))
        k_in = abs(_line_slope(y, c, lo, y0)) * s / c0
        k_out = abs(_line_slope(y, c, y0, hi)) * s / c0
        big, small = max(k_in, k_out), min(k_in, k_out)
        chord_kink = big >= T["kink_chord_slope_floor"] and big >= T["kink_chord_factor"] * max(small, 1e-12)
        if abs(sw_out - sw_in) >= T["kink_sweep_deg"] or chord_kink:
            kinks.append(float(y0 / s))

    yi = T["dihedral_inner"] * s
    # local dihedral on 200 even span steps (uneven loft points would amplify noise)
    ye = np.linspace(0.0, s, 201)
    ze = np.interp(ye, y, a["z_le"])
    local_dih = np.degrees(np.arctan(np.diff(ze) / np.diff(ye)))
    beyond = 0.5 * (ye[1:] + ye[:-1]) >= yi
    return {
        "root_chord_m": c0,
        "semi_span_m": s,
        "root_over_outer": c0 / c_outer,
        "root_loss": (c0 - c_loss) / c0,
        "qc_sweep_outer_deg": float(np.degrees(np.arctan(_line_slope(y, a["x_qc"], 0.5 * s, s)))),
        "qc_sweep_deg": float(np.degrees(np.arctan(_line_slope(y, a["x_qc"], 0.0, s)))),
        "taper": ctip / c0,
        "kinks_at_span_fraction": kinks,
        "twist_change_deg": float(a["twist_deg"][-1] - a["twist_deg"][0]),
        "mean_dihedral_outer_deg": float(np.degrees(np.arctan(_line_slope(y, a["z_le"], yi, s)))),
        "dihedral_range_outer_deg": float(np.ptp(local_dih[beyond])),
        "aspect_ratio": float(m["aspect_ratio"]),
    }


def label(m: dict) -> tuple[list[str], dict]:
    """Labels and the values behind them."""
    v = shape_values(m)
    out = []
    ratio = v["root_over_outer"]
    bwb = v["root_chord_m"] >= T["bwb_root_over_semispan"] * v["semi_span_m"] and (
        ratio >= T["bwb_root_over_outer"]
        or (ratio >= T["bwb_root_over_outer_with_loss"] and v["root_loss"] >= T["bwb_root_loss"]))
    out.append("bwb" if bwb else "conventional")

    sw = v["qc_sweep_outer_deg"]
    if sw >= T["sweep_deg"]:
        out.append("aft_swept")
    elif sw <= -T["sweep_deg"]:
        out.append("forward_swept")
    elif bwb:
        out.append("unswept_outer")

    kinked = bool(v["kinks_at_span_fraction"])
    straight = abs(v["qc_sweep_deg"]) < T["sweep_deg"]
    if not bwb and straight and v["taper"] >= T["rect_taper"]:
        out.append("rectangular")
    if kinked:
        out.append("cranked")
    elif not bwb and straight and v["taper"] < T["rect_taper"]:
        out.append("straight_tapered")

    if v["twist_change_deg"] <= -T["twist_deg"]:
        out.append("washout")
    elif v["twist_change_deg"] >= T["twist_deg"]:
        out.append("wash_in")

    if v["mean_dihedral_outer_deg"] >= T["dihedral_deg"]:
        out.append("dihedral")
    elif v["mean_dihedral_outer_deg"] <= -T["dihedral_deg"]:
        out.append("anhedral")
    if v["dihedral_range_outer_deg"] >= T["varying_dihedral_deg"]:
        out.append("varying_dihedral")

    if v["aspect_ratio"] >= T["high_ar"]:
        out.append("high_aspect_ratio")
    elif v["aspect_ratio"] <= T["low_ar"]:
        out.append("low_aspect_ratio")
    return out, v
