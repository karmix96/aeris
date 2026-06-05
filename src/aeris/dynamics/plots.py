"""
AERIS Dynamics — Aerospace-Grade Plots
=======================================
Publication-quality plots for:
  1. Root locus (eigenvalue migration vs. CG or other parameter)
  2. Eigenvalue map (s-plane with MIL-STD-1797B damping lines)
  3. MIL-STD-1797B compliance map (per mode, per mission)
  4. CG sweep with static margin + trim δe overlay
  5. Step response (longitudinal, from A matrix)
  6. Stability derivative summary bar chart

All functions return (fig, ax) tuples for further customization.
Plotly used for interactive output; matplotlib for static/export.

Design rules:
- Dark aerospace theme consistent with AERIS workstation.
- All axes labelled with units.
- MIL-STD-1797B level bands drawn as coloured regions.
- Eigenvalue plots show damping ratio lines (ζ = 0.15, 0.25, 0.35, 1.0).
- All functions have a `backend` parameter: "plotly" (default) or "matplotlib".
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Colour palette (dark aerospace theme)
# ---------------------------------------------------------------------------

DARK_BG   = "#0F1923"
GRID_COL  = "#1E2F3E"
TEXT_COL  = "#C8D6E5"
BORDER    = "#334252"

LEVEL1_COL = "#22C55E"   # green
LEVEL2_COL = "#F59E0B"   # amber
LEVEL3_COL = "#EF4444"   # red
UNACCEPTABLE_COL = "#7F1D1D"

SP_COL     = "#3B82F6"   # blue — short period
PH_COL     = "#8B5CF6"   # purple — phugoid
ROLL_COL   = "#10B981"   # teal — roll subsidence
SPIRAL_COL = "#F97316"   # orange — spiral
DR_COL     = "#EC4899"   # pink — Dutch roll

LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor=DARK_BG,
    font=dict(color=TEXT_COL, size=12, family="JetBrains Mono, monospace"),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=BORDER, borderwidth=1),
    margin=dict(l=60, r=20, t=50, b=60),
    xaxis=dict(gridcolor=GRID_COL, zerolinecolor=BORDER, zerolinewidth=1),
    yaxis=dict(gridcolor=GRID_COL, zerolinecolor=BORDER, zerolinewidth=1),
)


def _plotly():
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        return go, make_subplots
    except ImportError:
        raise ImportError("plotly is required for dynamics plots. Run: pip install plotly")


# ---------------------------------------------------------------------------
# 1. Eigenvalue map (s-plane)
# ---------------------------------------------------------------------------

def plot_eigenvalue_map(
    long_modes=None,    # LongitudinalModes
    lat_modes=None,     # LateralDirectionalModes
    title: str = "Eigenvalue map — s-plane",
    height: int = 500,
) -> Any:
    """
    Plot all eigenvalues on the complex s-plane.
    Draws constant-damping lines ζ = 0.15, 0.25, 0.35, 1.0 as dashed lines.
    Left half-plane = stable.
    """
    go, _ = _plotly()
    fig = go.Figure()

    # ── Damping ratio lines ζ = const ────────────────────────────────────
    # For a constant-damping line: σ = -ζ·ω_n, ω_d = ω_n·√(1-ζ²)
    # Parametric: (σ, ω) where σ/ω = -ζ/√(1-ζ²)  → line through origin
    max_y = 15.0

    for zeta, col, label in [
        (1.30, LEVEL2_COL,  "ζ=1.30"),
        (0.35, LEVEL1_COL,  "ζ=0.35 (L1 min)"),
        (0.25, LEVEL2_COL,  "ζ=0.25 (L2 min)"),
        (0.15, LEVEL3_COL,  "ζ=0.15 (L3 min)"),
    ]:
        if zeta >= 1.0:
            # Overdamped — vertical line on negative real axis
            x = [-math.sqrt(max_y**2 - 0.01) * zeta, 0]
            y = [0, 0]
        else:
            angle = math.acos(zeta)  # angle from negative real axis
            slope = -zeta / math.sqrt(1 - zeta**2)
            x_max = -max_y * math.sin(angle)
            y_max =  max_y * math.cos(angle)
            x = [x_max, 0, x_max]
            y = [y_max, 0, -y_max]

        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode="lines",
            line=dict(color=col, width=1, dash="dash"),
            name=label,
            hoverinfo="skip",
        ))

    # Imaginary axis (stability boundary)
    fig.add_vline(x=0, line_color=TEXT_COL, line_width=1.5)

    # ── Eigenvalues ───────────────────────────────────────────────────────
    mode_colors = {
        "short_period":  SP_COL,
        "phugoid":       PH_COL,
        "roll_subsidence": ROLL_COL,
        "spiral":        SPIRAL_COL,
        "dutch_roll":    DR_COL,
    }

    def _add_mode(eig_real, eig_imag, name: str, color: str):
        # Plot both conjugate if oscillatory
        points_x = [eig_real]
        points_y = [eig_imag]
        if abs(eig_imag) > 1e-4:
            points_x.append(eig_real)
            points_y.append(-eig_imag)
        fig.add_trace(go.Scatter(
            x=points_x, y=points_y,
            mode="markers",
            marker=dict(color=color, size=10, symbol="x"),
            name=name,
            hovertemplate=f"<b>{name}</b><br>σ=%{{x:.4f}}<br>ωd=%{{y:.4f}}<extra></extra>",
        ))

    if long_modes and long_modes.valid:
        if long_modes.short_period:
            sp = long_modes.short_period
            _add_mode(sp.eigenvalue_real, sp.eigenvalue_imag, "Short period", SP_COL)
        if long_modes.phugoid:
            ph = long_modes.phugoid
            _add_mode(ph.eigenvalue_real, ph.eigenvalue_imag, "Phugoid", PH_COL)

    if lat_modes and lat_modes.valid:
        if lat_modes.roll_subsidence:
            r = lat_modes.roll_subsidence
            _add_mode(r.eigenvalue_real, 0.0, "Roll subsidence", ROLL_COL)
        if lat_modes.spiral:
            s = lat_modes.spiral
            _add_mode(s.eigenvalue_real, 0.0, "Spiral", SPIRAL_COL)
        if lat_modes.dutch_roll:
            dr = lat_modes.dutch_roll
            _add_mode(dr.eigenvalue_real, dr.eigenvalue_imag, "Dutch roll", DR_COL)

    layout = dict(**LAYOUT_BASE)
    layout.update(dict(
        title=dict(text=title, font=dict(size=14)),
        xaxis=dict(title="Real part σ [1/s]", **LAYOUT_BASE["xaxis"]),
        yaxis=dict(title="Imaginary part ωd [rad/s]", **LAYOUT_BASE["yaxis"]),
        height=height,
    ))
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# 2. Root locus (eigenvalue migration vs. CG)
# ---------------------------------------------------------------------------

def plot_root_locus(
    root_locus_result,   # RootLocusResult
    show_modes: list[str] | None = None,
    title: str | None = None,
    height: int = 550,
) -> Any:
    """
    Root locus: eigenvalue migration as CG moves from forward to aft.
    Arrows show direction of migration as CG moves aft.
    Critical boundary: imaginary axis (stability boundary).
    """
    go, _ = _plotly()
    from aeris.dynamics.state_space import RootLocusResult

    if not root_locus_result.points:
        return go.Figure()

    title = title or f"Root locus vs. {root_locus_result.parameter_label}"
    fig = go.Figure()

    # Stability boundary
    fig.add_vline(x=0, line_color=TEXT_COL, line_width=1.5,
                  annotation_text="Stability boundary",
                  annotation_position="top right")

    # Collect eigenvalue trajectories
    n_long = 4  # 4 longitudinal eigenvalues
    long_trajs = [[] for _ in range(n_long)]
    lat_trajs  = [[] for _ in range(4)]
    param_vals = [pt.parameter_value for pt in root_locus_result.points]

    for pt in root_locus_result.points:
        for i, eig in enumerate(pt.longitudinal_eigenvalues[:n_long]):
            long_trajs[i].append((eig.real, eig.imag))
        for i, eig in enumerate(pt.lateral_eigenvalues[:4]):
            lat_trajs[i].append((eig.real, eig.imag))

    colors_long = [SP_COL, SP_COL, PH_COL, PH_COL]
    colors_lat  = [ROLL_COL, SPIRAL_COL, DR_COL, DR_COL]
    labels_long = ["SP(1)", "SP(2)", "Phugoid(1)", "Phugoid(2)"]
    labels_lat  = ["Roll", "Spiral", "DR(1)", "DR(2)"]

    def _add_traj(traj, color, label):
        xs = [p[0] for p in traj]
        ys = [p[1] for p in traj]
        if not xs:
            return
        # Start marker (forward CG)
        fig.add_trace(go.Scatter(
            x=[xs[0]], y=[ys[0]],
            mode="markers",
            marker=dict(color=color, size=10, symbol="circle"),
            name=f"{label} (fwd CG)",
            showlegend=True,
            hovertemplate=f"<b>{label} start</b><br>σ=%{{x:.4f}}<br>ωd=%{{y:.4f}}<extra></extra>",
        ))
        # Trajectory
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines+markers",
            line=dict(color=color, width=1.5),
            marker=dict(size=4),
            name=label,
            showlegend=True,
            hovertemplate=(
                f"<b>{label}</b><br>"
                f"{root_locus_result.parameter_label}: "
                "%{customdata:.3f} " + root_locus_result.parameter_unit + "<br>"
                "σ=%{x:.4f}<br>ωd=%{y:.4f}<extra></extra>"
            ),
            customdata=param_vals,
        ))
        # End marker (aft CG)
        fig.add_trace(go.Scatter(
            x=[xs[-1]], y=[ys[-1]],
            mode="markers",
            marker=dict(color=color, size=10, symbol="x"),
            name=f"{label} (aft CG)",
            showlegend=False,
            hovertemplate=f"<b>{label} end</b><br>σ=%{{x:.4f}}<extra></extra>",
        ))

    for traj, col, lbl in zip(long_trajs, colors_long, labels_long):
        _add_traj(traj, col, lbl)
    for traj, col, lbl in zip(lat_trajs, colors_lat, labels_lat):
        _add_traj(traj, col, lbl)

    layout = dict(**LAYOUT_BASE)
    layout.update(dict(
        title=dict(text=title, font=dict(size=14)),
        xaxis=dict(
            title="Real part σ [1/s]",
            **LAYOUT_BASE["xaxis"]
        ),
        yaxis=dict(
            title="Imaginary part ωd [rad/s]",
            **LAYOUT_BASE["yaxis"]
        ),
        height=height,
        annotations=[dict(
            x=param_vals[0], y=0,
            text=f"Fwd CG: {param_vals[0]:.3f} m",
            showarrow=False,
            font=dict(color=TEXT_COL, size=10),
        )],
    ))
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# 3. MIL-STD-1797B compliance map
# ---------------------------------------------------------------------------

def plot_hq_compliance(
    hq_report,     # HandlingQualityReport
    title: str = "MIL-STD-1797B Handling Quality Summary",
    height: int = 400,
) -> Any:
    """
    Horizontal bar chart showing each mode's HQ level with colour coding.
    Green = L1, Amber = L2, Red = L3, Dark red = Unacceptable.
    """
    go, _ = _plotly()
    from aeris.dynamics.mil_std import HQLevel

    mode_map = [
        ("Static margin",     hq_report.static_margin),
        ("Short-period ζ_sp", hq_report.short_period_damping),
        ("Short-period ω_sp", hq_report.short_period_frequency),
        ("Phugoid ζ_ph",      hq_report.phugoid),
        ("Roll subsidence τ_r", hq_report.roll_subsidence),
        ("Dutch roll ζ_DR",   hq_report.dutch_roll),
        ("Spiral T₂",         hq_report.spiral),
    ]

    level_colors = {
        HQLevel.LEVEL_1:      LEVEL1_COL,
        HQLevel.LEVEL_2:      LEVEL2_COL,
        HQLevel.LEVEL_3:      LEVEL3_COL,
        HQLevel.UNACCEPTABLE: UNACCEPTABLE_COL,
    }
    level_labels = {
        HQLevel.LEVEL_1:      "Level 1",
        HQLevel.LEVEL_2:      "Level 2",
        HQLevel.LEVEL_3:      "Level 3",
        HQLevel.UNACCEPTABLE: "Unacceptable",
    }

    modes, levels, colors, texts, values_str = [], [], [], [], []
    for name, classif in mode_map:
        if classif is None:
            continue
        modes.append(name)
        levels.append(classif.level.value)
        colors.append(level_colors[classif.level])
        texts.append(level_labels[classif.level])
        v = classif.value
        values_str.append(f"{v:.4f}" if isinstance(v, float) and abs(v) < 1e5 else (str(v) if v is not None else "—"))

    fig = go.Figure(go.Bar(
        x=levels,
        y=modes,
        orientation="h",
        marker_color=colors,
        text=[f"{t} ({v})" for t, v in zip(texts, values_str)],
        textposition="inside",
        hovertemplate="<b>%{y}</b><br>Level: %{text}<extra></extra>",
    ))

    layout = dict(**LAYOUT_BASE)
    layout.update(dict(
        title=dict(text=f"{title}<br><sub>Mission {hq_report.mission.value} — "
                        f"{'✓ Compliant' if hq_report.mission_compliant else '✗ Non-compliant'}</sub>",
                   font=dict(size=13)),
        xaxis=dict(
            title="MIL-STD-1797B Level",
            tickvals=[1, 2, 3, 4],
            ticktext=["Level 1", "Level 2", "Level 3", "Unacceptable"],
            range=[0, 5],
            **LAYOUT_BASE["xaxis"]
        ),
        yaxis=dict(**LAYOUT_BASE["yaxis"]),
        height=height,
    ))
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# 4. CG sweep with static margin + trim δe overlay
# ---------------------------------------------------------------------------

def plot_cg_sweep(
    cg_sweep_json: dict,
    title: str = "CG sweep — static margin and trim elevon",
    height: int = 450,
) -> Any:
    """
    Dual-axis plot: static margin [%MAC] on left axis, trim δe [deg] on right.
    NP position shown as vertical dashed line.
    MIL-STD-1797B target bands shown as horizontal bands.
    """
    go, make_subplots = _plotly()

    cases = cg_sweep_json.get("cases", [])
    if not cases:
        return go.Figure()

    xs    = [c.get("x_cg_m") for c in cases]
    sm    = [c.get("static_margin_percent_mac") for c in cases]
    de    = [c.get("de_trim_deg") for c in cases]
    np_x  = cg_sweep_json.get("static_margin_zero_crossing_estimate_m")
    sm_min = cg_sweep_json.get("stable_cg_min_m")
    sm_max = cg_sweep_json.get("stable_cg_max_m")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Static margin curve
    fig.add_trace(go.Scatter(
        x=xs, y=sm,
        mode="lines+markers",
        name="Static margin [%MAC]",
        line=dict(color=SP_COL, width=2),
        marker=dict(size=6),
        hovertemplate="CG=%{x:.3f} m<br>SM=%{y:.2f}% MAC<extra></extra>",
    ), secondary_y=False)

    # Zero SM line (neutral stability)
    fig.add_hline(y=0, line_color=LEVEL3_COL, line_dash="dash", line_width=1.5,
                  annotation_text="SM=0 (neutral)", annotation_position="right",
                  secondary_y=False)

    # MIL-STD-1797B target bands
    fig.add_hrect(y0=5, y1=12, line_width=0,
                  fillcolor=LEVEL1_COL, opacity=0.08,
                  annotation_text="L1 target ISR (5-12%)",
                  annotation_position="top right")

    # Trim δe overlay
    if any(v is not None for v in de):
        fig.add_trace(go.Scatter(
            x=xs, y=de,
            mode="lines+markers",
            name="Trim δe [deg]",
            line=dict(color=LEVEL2_COL, width=2, dash="dot"),
            marker=dict(size=5, symbol="square"),
            hovertemplate="CG=%{x:.3f} m<br>Trim δe=%{y:.2f}°<extra></extra>",
        ), secondary_y=True)

        # Actuator limits
        fig.add_hrect(y0=-25, y1=25, line_width=0, fillcolor=LEVEL2_COL, opacity=0.05,
                      secondary_y=True)
        fig.add_hline(y=20, line_color=LEVEL3_COL, line_dash="dot", line_width=1,
                      annotation_text="δe=20° limit", secondary_y=True)
        fig.add_hline(y=-20, line_color=LEVEL3_COL, line_dash="dot", line_width=1,
                      secondary_y=True)

    # Neutral point vertical line
    if np_x is not None:
        fig.add_vline(x=np_x, line_color=SPIRAL_COL, line_dash="dash",
                      line_width=1.5,
                      annotation_text=f"NP ≈ {np_x:.3f} m",
                      annotation_position="top left")

    # Stable CG range shading
    if sm_min is not None and sm_max is not None:
        fig.add_vrect(x0=sm_min, x1=sm_max, line_width=0,
                      fillcolor=LEVEL1_COL, opacity=0.06,
                      annotation_text=f"Stable: {sm_min:.3f}–{sm_max:.3f} m",
                      annotation_position="top left")

    layout = dict(**LAYOUT_BASE)
    layout.update(dict(
        title=dict(text=title, font=dict(size=13)),
        xaxis=dict(title="CG x position [m]", **LAYOUT_BASE["xaxis"]),
        yaxis=dict(title="Static margin [%MAC]", **LAYOUT_BASE["yaxis"]),
        yaxis2=dict(
            title="Trim δe [deg]",
            gridcolor=GRID_COL, zerolinecolor=BORDER,
        ),
        height=height,
        legend=LAYOUT_BASE["legend"],
    ))
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# 5. Stability derivative bar chart
# ---------------------------------------------------------------------------

def plot_derivative_summary(
    derivatives: dict[str, float | None],
    title: str = "Stability derivative summary",
    height: int = 400,
) -> Any:
    """
    Horizontal bar chart of all available stability derivatives.
    Colour: green = correct sign, red = wrong sign, grey = unknown sign requirement.
    """
    go, _ = _plotly()

    # Expected signs: positive = "should be positive", negative = "should be negative"
    EXPECTED_SIGNS = {
        "CLa": +1, "Cma": -1, "Cmq": -1, "CLq": +1,
        "CYb": -1, "Clb": -1, "Cnb": +1,
        "Clp": -1, "Cnr": -1, "Clr": None, "Cnp": None,
    }

    keys   = [k for k, v in derivatives.items() if v is not None and isinstance(v, (int, float))]
    values = [derivatives[k] for k in keys]

    colors = []
    for k, v in zip(keys, values):
        expected = EXPECTED_SIGNS.get(k)
        if expected is None:
            colors.append(BORDER)
        elif (expected > 0 and v > 0) or (expected < 0 and v < 0):
            colors.append(LEVEL1_COL)
        else:
            colors.append(LEVEL3_COL)

    fig = go.Figure(go.Bar(
        x=values, y=keys,
        orientation="h",
        marker_color=colors,
        hovertemplate="%{y}: %{x:.5f}<extra></extra>",
    ))

    layout = dict(**LAYOUT_BASE)
    layout.update(dict(
        title=dict(text=title, font=dict(size=13)),
        xaxis=dict(title="Value [per rad]", **LAYOUT_BASE["xaxis"]),
        height=height,
    ))
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# 6. UQ distribution plots (Paper 2)
# ---------------------------------------------------------------------------

def plot_uq_mode_distributions(
    uq_result,     # EigenvalueUQResult
    title: str = "Dynamic mode uncertainty distributions",
    height: int = 600,
) -> Any:
    """
    Violin + box plots for all sampled mode metrics.
    MIL-STD-1797B Level 1 bands overlaid as horizontal coloured regions.
    One subplot per mode.
    Paper 2 Figure: shows how conformal intervals translate to mode uncertainty.
    """
    go, make_subplots = _plotly()
    from aeris.dynamics.mil_std import (
        SP_ZETA_LEVEL1_MIN, SP_ZETA_LEVEL1_MAX,
        SP_ZETA_LEVEL2_MIN,
        PH_ZETA_LEVEL1_MIN,
        ROLL_TAU_LEVEL1_MAX,
        SPIRAL_T2_MISSION_A,
        DR_ZETA_LEVEL1_MIN,
    )

    modes = [
        ("ζ_sp", uq_result.short_period_zeta,
         [{"y0": SP_ZETA_LEVEL1_MIN, "y1": SP_ZETA_LEVEL1_MAX, "col": LEVEL1_COL, "lbl": "L1 band"},
          {"y0": SP_ZETA_LEVEL2_MIN, "y1": SP_ZETA_LEVEL1_MIN, "col": LEVEL2_COL, "lbl": "L2 band"}]),
        ("ζ_ph", uq_result.phugoid_zeta,
         [{"y0": PH_ZETA_LEVEL1_MIN, "y1": 1.0, "col": LEVEL1_COL, "lbl": "L1 ≥ 0.04"}]),
        ("τ_r [s]", uq_result.roll_tau,
         [{"y0": 0, "y1": ROLL_TAU_LEVEL1_MAX, "col": LEVEL1_COL, "lbl": "L1 ≤ 1.0 s"}]),
        ("T₂ [s]", uq_result.spiral_t2,
         [{"y0": SPIRAL_T2_MISSION_A, "y1": 60, "col": LEVEL1_COL, "lbl": "L1 ISR ≥ 20 s"}]),
        ("ζ_DR", uq_result.dutch_roll_zeta,
         [{"y0": DR_ZETA_LEVEL1_MIN, "y1": 0.5, "col": LEVEL1_COL, "lbl": "L1 ≥ 0.08"}]),
    ]

    valid_modes = [(n, r, b) for n, r, b in modes if r is not None and r.n_samples > 0]
    if not valid_modes:
        return go.Figure()

    n_plots = len(valid_modes)
    fig = make_subplots(
        rows=1, cols=n_plots,
        subplot_titles=[m[0] for m in valid_modes],
    )

    for col_idx, (mode_name, mode_result, bands) in enumerate(valid_modes, 1):
        p = mode_result
        # Box plot approximation from percentiles
        if p.p05 is not None:
            # Level 1 band
            for band in bands:
                fig.add_hrect(
                    y0=band["y0"], y1=band["y1"],
                    fillcolor=band["col"], opacity=0.12, line_width=0,
                    row=1, col=col_idx,
                )

            # Point estimate
            if p.point_estimate is not None:
                fig.add_hline(
                    y=p.point_estimate,
                    line_color="#FFFFFF", line_dash="dash", line_width=1.5,
                    annotation_text="nominal",
                    row=1, col=col_idx,
                )

            # Distribution box (p05-p95 range)
            fig.add_trace(go.Box(
                y=[p.p05, p.p50, p.mean, p.p95],
                name=mode_name,
                boxpoints=False,
                marker_color=SP_COL,
                line_color=SP_COL,
                hovertemplate=(
                    f"<b>{mode_name}</b><br>"
                    f"P(L1): {p.p_level1:.3f}<br>"
                    f"median: {p.p50:.4f}<br>"
                    f"±σ: {p.std:.4f}<extra></extra>"
                ),
            ), row=1, col=col_idx)

    layout = dict(**LAYOUT_BASE)
    layout.update(dict(
        title=dict(
            text=f"{title}<br><sub>N={uq_result.n_samples} samples | "
                 f"success rate: {uq_result.sample_success_rate:.1%}</sub>",
            font=dict(size=13),
        ),
        height=height,
        showlegend=False,
    ))
    fig.update_layout(**layout)
    return fig


def plot_uq_sensitivity(
    sensitivity_results: list[dict],
    title: str = "P(Level 1) vs. conformal interval width — cost of uncertainty",
    height: int = 420,
) -> Any:
    """
    Paper 2 key figure: shows how P(Level 1 short-period) degrades as
    conformal interval width grows. Motivates HF data collection to narrow intervals.
    x-axis: interval scale factor (1.0 = nominal surrogate uncertainty)
    y-axis: P(Level 1 ζ_sp) and P(Level 1 ζ_ph)
    """
    go, _ = _plotly()
    if not sensitivity_results:
        return go.Figure()

    xs = [r["scale_factor"] for r in sensitivity_results]
    sp = [r.get("p_l1_sp_zeta") for r in sensitivity_results]
    ph = [r.get("p_l1_ph_zeta") for r in sensitivity_results]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=xs, y=sp,
        mode="lines+markers",
        name="P(Level 1 ζ_sp)",
        line=dict(color=SP_COL, width=2),
        marker=dict(size=8),
        hovertemplate="Scale: %{x:.2f}×<br>P(L1 ζ_sp): %{y:.3f}<extra></extra>",
    ))

    if any(v is not None for v in ph):
        fig.add_trace(go.Scatter(
            x=xs, y=ph,
            mode="lines+markers",
            name="P(Level 1 ζ_ph)",
            line=dict(color=PH_COL, width=2),
            marker=dict(size=8),
            hovertemplate="Scale: %{x:.2f}×<br>P(L1 ζ_ph): %{y:.3f}<extra></extra>",
        ))

    # 90% target line
    fig.add_hline(y=0.90, line_color=LEVEL1_COL, line_dash="dash",
                  annotation_text="P=0.90 target (Paper 4 constraint)",
                  annotation_position="right")
    # Nominal interval marker
    fig.add_vline(x=1.0, line_color=TEXT_COL, line_dash="dot", line_width=1,
                  annotation_text="Nominal width", annotation_position="top right")

    layout = dict(**LAYOUT_BASE)
    layout.update(dict(
        title=dict(text=title, font=dict(size=13)),
        xaxis=dict(title="Conformal interval scale factor", **LAYOUT_BASE["xaxis"]),
        yaxis=dict(title="P(Level 1 compliance)", range=[0, 1.05], **LAYOUT_BASE["yaxis"]),
        height=height,
    ))
    fig.update_layout(**layout)
    return fig
