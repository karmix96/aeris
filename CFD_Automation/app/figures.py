"""The app's pictures (Plotly): the planform, the sections, the wing in 3-D, the surface mesh, a station plane of the
volume mesh and a 3-D look at the volume mesh. Lengths in mean chords (c̄).

One mesh colour; the blocks are told apart by their outlines and names, never by colour alone.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from cfdauto.geometry.loft import section_points
from cfdauto.geometry.preview import outline, ruled_surface

try:
    from . import core
except ImportError:                       # run as a script folder (streamlit run app/app.py)
    import core

INK, MUTED, LINE = "#142230", "#566573", "#D6DEE6"
MESH = "#9db0c4"                          # grid lines
WALL = "#38495c"                          # the wing in the planes
SKIN = "#9fb4c8"                          # the wing in 3-D
ACCENT = "#2a78d6"                        # the wake fan
FONT = dict(family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif", size=13, color=INK)
MAX_POINTS = 160_000                      # per picture: thinner lines past this


def _layout(fig: go.Figure, title: str, height: int = 460, equal: bool = True, x_title="", y_title="") -> go.Figure:
    fig.update_layout(title=dict(text=title, x=0, xanchor="left", font=dict(size=15)), height=height,
                      margin=dict(l=10, r=10, t=44, b=10), paper_bgcolor="white", plot_bgcolor="white", font=FONT,
                      legend=dict(orientation="h", yanchor="top", y=-0.13, xanchor="left", x=0), hovermode="closest")
    fig.update_xaxes(title=x_title, showgrid=True, gridcolor="#eef2f6", zeroline=False, linecolor=LINE)
    fig.update_yaxes(title=y_title, showgrid=True, gridcolor="#eef2f6", zeroline=False, linecolor=LINE)
    if equal:
        fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def _lines(grids: list[np.ndarray], a: int, b: int, stride: int = 1) -> tuple[list, list]:
    """Every i-line and j-line of 2-D grids (ni, nj, 3) as one polyline set (None between lines), coordinates a, b."""
    xs, ys = [], []
    for G in grids:
        ni, nj = G.shape[:2]
        for j in list(range(0, nj, stride)) + ([nj - 1] if (nj - 1) % stride else []):
            xs += G[:, j, a].tolist() + [None]
            ys += G[:, j, b].tolist() + [None]
        for i in list(range(0, ni, stride)) + ([ni - 1] if (ni - 1) % stride else []):
            xs += G[i, :, a].tolist() + [None]
            ys += G[i, :, b].tolist() + [None]
    return xs, ys


def _stride(grids: list[np.ndarray], limit: int = MAX_POINTS) -> int:
    n = sum(2 * G.shape[0] * G.shape[1] for G in grids)
    return max(1, int(np.ceil(n / limit)))


# --- Stage 1 ----------------------------------------------------------------------------------------------------

def planform(stations) -> go.Figure:
    """Top view of the half wing: the flow goes down the page, the semi-span to the right."""
    le, te = outline(stations)
    fig = go.Figure()
    xs = np.r_[le[:, 0], te[::-1, 0], le[0, 0]]
    ys = np.r_[le[:, 1], te[::-1, 1], le[0, 1]]
    fig.add_trace(go.Scatter(x=ys, y=xs, mode="lines", fill="toself", fillcolor="#eaf1f8", line=dict(color=INK, width=2),
                             name="half wing", hoverinfo="skip"))
    for s, a, b in zip(stations, le, te):
        fig.add_trace(go.Scatter(x=[a[1], b[1]], y=[a[0], b[0]], mode="lines", line=dict(color=MUTED, width=1, dash="dot"),
                                 showlegend=False, hovertemplate=f"{s.name}: y %{{x:.3f}}, chord {s.chord:.3f} c̄<extra></extra>"))
        fig.add_annotation(x=a[1], y=a[0], text=s.name, showarrow=False, yshift=12, font=dict(size=12, color=MUTED))
    _layout(fig, "Planform (half wing, top view)", 380, True, "y along the semi-span (c̄)", "x, flow direction (c̄)")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(showlegend=False)
    return fig


def sections(stations) -> go.Figure:
    """The four sections at unit chord (trailing edge opened by the rule), one above the other."""
    fig = go.Figure()
    gap = 0.3
    for k, s in enumerate(stations):
        p = s.airfoil.selig()
        off = -k * gap
        fig.add_trace(go.Scatter(x=p[:, 0], y=p[:, 1] + off, mode="lines", line=dict(color=INK, width=1.6),
                                 name=s.name, hovertemplate=f"{s.name}: x/c %{{x:.3f}}<extra></extra>"))
        fig.add_annotation(x=1.02, y=off, text=f"{s.name}: {s.airfoil.name.split('|')[0]}, twist {s.twist_deg:+.1f}°",
                           showarrow=False, xanchor="left", font=dict(size=12, color=MUTED))
    _layout(fig, "Sections at b0–b3 (unit chord)", 380, True, "x / c", "")
    fig.update_xaxes(range=[-0.05, 1.75])
    fig.update_yaxes(showticklabels=False)
    fig.update_layout(showlegend=False)
    return fig


def wing_3d(stations, mirror: bool = True) -> go.Figure:
    up, lo = ruled_surface(stations, per_panel=8)
    fig = go.Figure()
    for sgn in ((1, -1) if mirror else (1,)):
        for S in (up, lo):
            fig.add_trace(go.Surface(x=S[..., 0], y=sgn * S[..., 1], z=S[..., 2], showscale=False, opacity=1.0,
                                     colorscale=[[0, SKIN], [1, SKIN]], lighting=dict(ambient=0.55, diffuse=0.7, specular=0.15),
                                     hoverinfo="skip"))
    pts = np.concatenate([up.reshape(-1, 3), lo.reshape(-1, 3)])
    if mirror:
        pts = np.concatenate([pts, pts * [1, -1, 1]])
    return _scene(fig, "The wing (full span, both halves)", 520, pts, eye=(-0.55, -0.7, 0.42))


def _scene(fig: go.Figure, title: str, height: int, pts: np.ndarray, eye=(-0.8, -0.95, 0.6),
           flat: float = 0.25) -> go.Figure:
    """Equal scale on x, y and z (the true shape), the box fitted to the points, at least `flat` of the longest side
    tall, so a thin wing still has room above and below it."""
    lo, hi = np.nanmin(pts, axis=0), np.nanmax(pts, axis=0)
    c, L = 0.5 * (lo + hi), np.maximum(hi - lo, 1e-6) * 1.06
    L[2] = max(L[2], flat * L.max())
    r = L / L.max()
    ax = dict(backgroundcolor="white", gridcolor="#eef2f6", showspikes=False)
    fig.update_layout(title=dict(text=title, x=0, xanchor="left", font=dict(size=15)), height=height, font=FONT,
                      margin=dict(l=0, r=0, t=44, b=0), paper_bgcolor="white", showlegend=False,
                      scene=dict(aspectmode="manual", aspectratio=dict(x=r[0], y=r[1], z=r[2]),
                                 camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2]), center=dict(x=0, y=0, z=-0.05)),
                                 xaxis=ax | dict(title="x (c̄)", range=[c[0] - L[0] / 2, c[0] + L[0] / 2]),
                                 yaxis=ax | dict(title="y (c̄)", range=[c[1] - L[1] / 2, c[1] + L[1] / 2]),
                                 zaxis=ax | dict(title="z (c̄)", range=[c[2] - L[2] / 2, c[2] + L[2] / 2])))
    return fig


# --- Stage 2 ----------------------------------------------------------------------------------------------------

def surface_mesh_3d(sm, skin: bool = True) -> go.Figure:
    """Every ring (one per station) and every spanwise line of the surface mesh, and the tip cap."""
    W = np.transpose(sm.wing, (1, 0, 2))          # (n_span, n_ring, 3)
    cap = sm.cap
    stride = _stride([W, cap], 120_000)
    fig = go.Figure()
    if skin:
        fig.add_trace(go.Surface(x=W[..., 0], y=W[..., 1], z=W[..., 2], showscale=False, colorscale=[[0, "#eef3f8"], [1, "#eef3f8"]],
                                 lighting=dict(ambient=0.8, diffuse=0.3), hoverinfo="skip"))
    for G, color, name in ((W, "#3f5a78", "wing"), (cap, "#8a4b0f", "tip cap")):
        xs, ys = _lines([G], 0, 1, stride)
        _, zs = _lines([G], 0, 2, stride)
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=color, width=1.5), name=name,
                                   hoverinfo="skip"))
    t = f"Surface mesh {sm.level}, Re {sm.re_mean:.0e}" + (f" (every {stride}th line)" if stride > 1 else "")
    return _scene(fig, t, 560, np.concatenate([W.reshape(-1, 3), cap.reshape(-1, 3)]), eye=(-0.75, -0.9, 0.6))


def surface_ring(sm, k: int, close: bool = True) -> go.Figure:
    """One station ring of the surface mesh, nodes shown: the chordwise spacing as built."""
    R = sm.wing[:, k, :]
    fig = go.Figure(go.Scatter(x=R[:, 0], y=R[:, 2], mode="lines+markers", line=dict(color=INK, width=1),
                               marker=dict(size=4, color=ACCENT), hovertemplate="x %{x:.4f}, z %{y:.4f}<extra></extra>"))
    _layout(fig, f"Station {k} (y = {R[0, 1]:.3f} c̄): {R.shape[0]} ring nodes", 360, True, "x (c̄)", "z (c̄)")
    fig.update_layout(showlegend=False)
    return fig


# --- Stage 3 ----------------------------------------------------------------------------------------------------

def _views(sm, k: int | None, grids: dict) -> dict:
    """Axis ranges for 'close', 'wake' and 'all' around the section at station k (or the tip cap past the tip)."""
    if k is not None:
        R = sm.wing[:, k, :]
    else:
        R = sm.cap.reshape(-1, 3)
    x0, x1 = float(R[:, 0].min()), float(R[:, 0].max())
    zc = float(R[:, 2].mean())
    c = max(x1 - x0, 1e-3)
    allp = np.concatenate([g.reshape(-1, 3) for g in grids.values()])
    return {"close": ([x0 - 0.45 * c, x1 + 0.75 * c], [zc - 0.6 * c, zc + 0.6 * c]),
            "wake": ([x0 - 0.3 * c, x1 + 2.6 * c], [zc - 1.0 * c, zc + 1.0 * c]),
            "all": ([float(allp[:, 0].min()), float(allp[:, 0].max())], [float(allp[:, 2].min()), float(allp[:, 2].max())])}


def volume_plane(vm, sm, plane: dict, view: str = "close", fan: bool = True, names: bool = True) -> go.Figure:
    """One station plane of the C-H mesh: its six blocks (and the tip cap past the tip), the wall, the wake fan."""
    side, k = plane["side"], plane["k"]
    grids = core.plane_grids(vm, side, k)
    rng = _views(sm, k if side == "in" else None, grids)[view]
    # keep only what is in view (plus a margin), so the picture stays light
    (xa, xb), (za, zb) = rng
    mx, mz = 0.15 * (xb - xa), 0.15 * (zb - za)
    shown = {}
    for n, G in grids.items():
        m = (G[..., 0] >= xa - mx) & (G[..., 0] <= xb + mx) & (G[..., 2] >= za - mz) & (G[..., 2] <= zb + mz)
        if not m.any():
            continue
        ii, jj = np.where(m)
        shown[n] = G[max(ii.min() - 1, 0): ii.max() + 2, max(jj.min() - 1, 0): jj.max() + 2]
    stride = _stride(list(shown.values()))
    fig = go.Figure()
    xs, zs = _lines(list(shown.values()), 0, 2, stride)
    fig.add_trace(go.Scattergl(x=xs, y=zs, mode="lines", line=dict(color=MESH, width=0.8), name="grid lines",
                               hoverinfo="skip"))
    bx, bz = [], []                                   # block outlines
    for G in shown.values():
        e = np.concatenate([G[:, 0], G[-1, :], G[::-1, -1], G[0, ::-1]])
        bx += e[:, 0].tolist() + [None]
        bz += e[:, 2].tolist() + [None]
    fig.add_trace(go.Scattergl(x=bx, y=bz, mode="lines", line=dict(color=INK, width=1.4), name="block edges",
                               hoverinfo="skip"))
    if side == "in":
        R = sm.wing[:, k, :]
        fig.add_trace(go.Scatter(x=np.r_[R[:, 0], R[0, 0]], y=np.r_[R[:, 2], R[0, 2]], mode="lines", fill="toself",
                                 fillcolor=WALL, line=dict(color=WALL, width=1), name="wing section", hoverinfo="skip"))
        if fan:
            _fan(fig, vm, k)
    if names:                                        # each name in the middle of what is seen of its block
        for n, G in shown.items():
            P = G.reshape(-1, 3)
            v = P[(P[:, 0] >= xa) & (P[:, 0] <= xb) & (P[:, 2] >= za) & (P[:, 2] <= zb)]
            if len(v):
                cx = 0.5 * (v[:, 0].min() + v[:, 0].max())
                cz = 0.5 * (v[:, 2].min() + v[:, 2].max())
                fig.add_annotation(x=cx, y=cz, text=n, showarrow=False, bgcolor="rgba(255,255,255,0.8)",
                                   font=dict(size=11, color=INK))
    where = f"station {k} of the wing" if side == "in" else f"plane {k} past the tip"
    t = f"Station plane, {where}: y = {plane['y']:.3f} c̄"
    if stride > 1:
        t += f" (every {stride}th line)"
    _layout(fig, t, 560, True, "x (c̄)", "z (c̄)")
    fig.update_xaxes(range=rng[0])
    fig.update_yaxes(range=rng[1])
    return fig


def _fan(fig: go.Figure, vm, k: int) -> None:
    """The wake fan (law 18): straight rays from the base mid-point, −5° to +10° plus the margin, 2 local chords long."""
    P = getattr(vm, "_plane", None)
    if not P:
        return
    st, b = P["sts"][k], P["rules"].band
    L = float(b["length_local_c"]) * st.chord
    s = np.linspace(0.0, L, 40)
    xm, zm = st.wake.M
    up = zm + float(b["margin_c"]) + s * np.tan(np.radians(float(b["alpha_hi_deg"])))
    lo = zm - float(b["margin_c"]) + s * np.tan(np.radians(float(b["alpha_lo_deg"])))
    fig.add_trace(go.Scatter(x=np.r_[xm + s, (xm + s)[::-1], xm], y=np.r_[up, lo[::-1], up[0]], mode="lines",
                             fill="toself", fillcolor="rgba(42,120,214,0.10)", line=dict(color=ACCENT, width=1.6),
                             name=f"wake fan {float(b['alpha_lo_deg']):g}° to +{float(b['alpha_hi_deg']):g}°",
                             hoverinfo="skip"))


def volume_3d(vm, sm, picks: list[dict]) -> go.Figure:
    """The wing and a few station planes in 3-D, cut to a box around the wing (the far field is 80 c̄ away)."""
    W = np.transpose(sm.wing, (1, 0, 2))
    x0, x1 = float(W[..., 0].min()), float(W[..., 0].max())
    y1 = float(W[..., 1].max())
    z0, z1 = float(W[..., 2].min()), float(W[..., 2].max())
    box = (x0 - 1.0, x1 + 2.5, -0.01, y1 + 1.5, z0 - 1.2, z1 + 1.2)
    fig = go.Figure(go.Surface(x=W[..., 0], y=W[..., 1], z=W[..., 2], showscale=False, colorscale=[[0, WALL], [1, WALL]],
                               lighting=dict(ambient=0.6, diffuse=0.6), hoverinfo="skip"))
    grids = []
    for p in picks:
        grids += list(core.plane_grids(vm, p["side"], p["k"]).values())
    stride = _stride(grids, 150_000)
    xs, ys, zs = [], [], []
    for G in grids:
        for lines in (np.transpose(G, (1, 0, 2))[::stride], G[::stride]):
            for L in lines:
                inside = ((L[:, 0] >= box[0]) & (L[:, 0] <= box[1]) & (L[:, 1] >= box[2]) & (L[:, 1] <= box[3])
                          & (L[:, 2] >= box[4]) & (L[:, 2] <= box[5]))
                if inside.sum() < 2:
                    continue
                P = L.astype(object)
                P[~inside] = None
                xs += list(P[:, 0]) + [None]
                ys += list(P[:, 1]) + [None]
                zs += list(P[:, 2]) + [None]
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color="#6f8aa6", width=1.2), hoverinfo="skip"))
    t = "Station planes in 3-D"
    corners = np.array([[box[0], box[2], box[4]], [box[1], box[3], box[5]]])
    return _scene(fig, t, 580, corners, eye=(-0.95, -1.1, 0.6), flat=0.0)
