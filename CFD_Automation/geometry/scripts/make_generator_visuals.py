"""Pictures of the generator: how one wing is built, and the published wings it rebuilds.

    python scripts/make_generator_visuals.py            # writes docs/*.gif, docs/*.png

No pyGeo needed: surfaces come from preview.ruled_surface, which is the k_span = 2
loft up to the cubic fit of each section.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.geometry import airfoils, preview, published_wings  # noqa: E402
from cfdauto.geometry.labels import label  # noqa: E402
from cfdauto.geometry.measure import measure, table_from_stations  # noqa: E402
from cfdauto.geometry.params import load_config, mid_vector  # noqa: E402
from cfdauto.geometry.planform import aspect_ratio, mean_aero_chord  # noqa: E402
from cfdauto.geometry.sections import build_stations, build_wing_sections  # noqa: E402

DOCS = ROOT / "docs"
INK, MUTED, ACCENT, ACCENT2, WARN = "#14202b", "#5a6875", "#0c5ea8", "#c0581a", "#b02a20"
SURF = "#9cc3e6"
W, H, DPI = 9.6, 5.4, 100

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED})


# --- drawing helpers ---------------------------------------------------------------

def draw_3d(ax, stations, title=None, mirror=True, color=SURF):
    up, lo = preview.ruled_surface(stations, per_panel=10)
    for s, flip in ((1, False), (-1, True)) if mirror else ((1, False),):
        for g in (up, lo):
            X, Y, Z = g[..., 0], s * g[..., 1], g[..., 2]
            ax.plot_surface(X, Y, Z, color=color, linewidth=0, antialiased=True, shade=True, alpha=1.0)
    le, te = preview.outline(stations)
    for s in (1, -1) if mirror else (1,):
        ax.plot(le[:, 0], s * le[:, 1], le[:, 2], color=INK, lw=0.8)
        ax.plot(te[:, 0], s * te[:, 1], te[:, 2], color=INK, lw=0.8)
    pts = np.concatenate([up.reshape(-1, 3), lo.reshape(-1, 3)])
    if mirror:
        pts = np.concatenate([pts, pts * [1, -1, 1]])
    lo_, hi_ = pts.min(0), pts.max(0)
    mid, half = 0.5 * (lo_ + hi_), 0.5 * np.max(hi_ - lo_)
    ax.set_xlim(mid[0] - half, mid[0] + half)
    ax.set_ylim(mid[1] - half, mid[1] + half)
    ax.set_zlim(mid[2] - half * 0.5, mid[2] + half * 0.5)
    ax.set_box_aspect((1, 1, 0.5), zoom=1.45)
    ax.view_init(elev=32, azim=-58)
    ax.patch.set_alpha(0.0)
    ax.set_axis_off()
    if title:
        ax.set_title(title, color=INK, fontsize=12, loc="left")


def draw_planform(ax, pf, stations, show_stations=True, color=ACCENT, label_chords=True):
    y = pf.y
    le, te = pf.x_le, pf.x_le + pf.chord
    for s in (1, -1):
        ax.plot(s * y, le, color=color, lw=2)
        ax.plot(s * y, te, color=color, lw=2)
        ax.plot([s * y[-1]] * 2, [le[-1], te[-1]], color=color, lw=2)
    ax.plot([0, 0], [le[0], te[0]], color=color, lw=1, ls=":")
    if show_stations:
        for i, st in enumerate(stations[:4]):
            ax.plot([st.y, st.y], [st.x_le, st.x_le + st.chord], color=ACCENT2, lw=1.4)
            ax.plot(st.y, st.x_le, "o", color=ACCENT2, ms=4)
            if label_chords:
                ax.text(st.y + 0.015 * pf.semi_span, st.x_le + 0.5 * st.chord, f"b{i}\n{st.chord:.3g} m",
                        ha="left", va="center", fontsize=8, color=ACCENT2)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_xlabel("span y [m]")
    ax.set_ylabel("x [m]")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def text_panel(ax, title, lines, foot=None):
    ax.set_axis_off()
    ax.text(0.0, 1.0, title, fontsize=14, weight="bold", color=INK, va="top", transform=ax.transAxes)
    y = 0.86
    for ln in lines:
        ax.text(0.0, y, ln, fontsize=10, color=INK, va="top", transform=ax.transAxes, wrap=True)
        y -= 0.075 * (1 + ln.count("\n"))
    if foot:
        ax.text(0.0, 0.02, foot, fontsize=8.5, color=MUTED, va="bottom", transform=ax.transAxes)


def grab(fig) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def frame(title_step, lines, draw, foot=None, three_d=False):
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.36, 0.02, 0.63, 0.94] if three_d else [0.42, 0.10, 0.55, 0.82],
                      projection="3d" if three_d else None)
    draw(ax)
    ax_t = fig.add_axes([0.03, 0.06, 0.36, 0.88])
    ax_t.set_zorder(10)
    ax_t.patch.set_alpha(0.0)
    text_panel(ax_t, title_step, lines, foot)
    return grab(fig)


# --- part 1: how one wing is built ---------------------------------------------------------

def build_steps() -> list[tuple[Image.Image, int]]:
    cfg = load_config()
    spec = cfg.types["bwb"]
    vec = mid_vector(spec)
    pf, raw = build_stations(spec, vec)
    _, st = build_wing_sections(spec, vec, cfg.te)
    m = measure(table_from_stations(st), st)
    labels, _ = label(m)
    frames = []

    def f1(ax):
        ax.set_axis_off()
        rows = [(k, f"{v:.3g}") for k, v in vec.items() if k != "airfoils"]
        tab = ax.table(cellText=[[k, v] for k, v in rows], colLabels=["variable", "value"],
                       loc="center", cellLoc="left", colWidths=[0.5, 0.25])
        tab.auto_set_font_size(False)
        tab.set_fontsize(8)
        tab.scale(1, 1.05)
    frames.append((frame("1 · The design vector",
                         ["18 numbers describe one wing:", "chords, spans, sweeps,",
                          "twist and dihedral at the", "four stations b0 (root) to b3 (tip).",
                          "", "One YAML file holds the ranges", "for BWB and conventional wings."],
                         f1, foot="Example: BWB, every variable at mid-range"), 2500))

    frames.append((frame("2 · Planform",
                         ["Leading and trailing edges are", "straight lines through the four",
                          "stations, so every chord and", "sweep is exactly what was set.",
                          "", f"Sweeps: {', '.join(f'{s:.1f}°' for s in pf.sweep_le_deg)}"],
                         lambda ax: draw_planform(ax, pf, raw)), 2500))

    def f3(ax):
        for i, s in enumerate(raw):
            a = s.airfoil
            off = -0.28 * i
            ax.fill_between(a.x, a.yl + off, a.yu + off, color=SURF, ec=ACCENT, lw=1)
            ax.text(1.03, off, f"b{i}: {a.name}", va="center", fontsize=9, color=INK)
        ax.set_aspect("equal")
        ax.set_xlim(-0.02, 1.45)
        ax.set_axis_off()
    frames.append((frame("3 · Sections",
                         ["An airfoil at each station,", "by name, from:",
                          "• the project's own files,", f"• the AERIS database ({len(airfoils.available())} files),",
                          "• or a NACA 4/5-digit formula.", "", "A type can also list several",
                          "candidates per station; the", "sampler then draws them evenly."],
                         f3, foot="Shown at unit chord"), 2500))

    def f4(ax):
        ys = np.array([s.y for s in raw])
        zs = np.array([s.z_le for s in raw])
        for sgn in (1, -1):
            ax.plot(sgn * ys, zs, "-o", color=ACCENT, ms=4)
        for s in raw:
            ax.text(s.y, s.z_le + 0.012 * pf.semi_span, f"{s.twist_deg:+.1f}°", ha="center", fontsize=9, color=ACCENT2)
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.set_aspect("equal")
        ax.set_ylim(-0.1 * pf.semi_span, 0.25 * pf.semi_span)
        ax.set_xlabel("span y [m]")
        ax.set_ylabel("z [m]")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    frames.append((frame("4 · Twist and dihedral",
                         ["Front view. Each station gets", "its twist (orange, nose up +)",
                          "and the dihedral sets its", "height. Both vary linearly", "between stations.",
                          "", "The root section stays in the", "symmetry plane, so dihedral", "from the root is allowed."],
                         f4), 2500))

    def f5(ax):
        a0, a1 = raw[0].airfoil, st[0].airfoil
        c = raw[0].chord * 1000
        x = a0.x * c
        sel = a0.x > 0.8
        ax.plot(x[sel], a0.yu[sel] * c, color=MUTED, lw=1.2, ls="--", label="as read")
        ax.plot(x[sel], a0.yl[sel] * c, color=MUTED, lw=1.2, ls="--")
        ax.plot(x[sel], a1.yu[sel] * c, color=ACCENT, lw=2, label="opened")
        ax.plot(x[sel], a1.yl[sel] * c, color=ACCENT, lw=2)
        ax.plot([c, c], [a1.yl[-1] * c, a1.yu[-1] * c], color=WARN, lw=3, label=f"base {a1.te_thickness * c:.2f} mm")
        ax.legend(frameon=False, loc="upper right")
        ax.set_xlabel("x [mm]")
        ax.set_ylabel("z [mm]")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    frames.append((frame("5 · Trailing edge",
                         ["The edge is opened to", f"max({cfg.te.floor_m * 1e3:.1f} mm, {cfg.te.chord_fraction * 100:.1f} % of chord),",
                          f"growing linearly from {cfg.te.open_from_xc * 100:.0f} % chord", "to the edge, half up, half down",
                          "(pyGeo's blunt-edge method):", "the camber line does not move.", "",
                          "Published wings keep their", "own edge ('as_is')."],
                         f5, foot="Root section, aft part (height stretched)"), 2500))

    frames.append((frame("6 · Loft",
                         ["The sections are joined by", "straight panels (pyGeo,", "kSpan = 2). This surface is",
                          "the only wing that the mesh,", "the solver and the data see."],
                         lambda ax: draw_3d(ax, st), three_d=True), 2500))

    frames.append((frame("7 · Measure, label, check",
                         [f"Area {m['area_m2']:.3f} m²,  AR {m['aspect_ratio']:.2f}",
                          f"Mean chord {m['mac_m']:.3f} m", "", "Labels (by rule):", "  " + ", ".join(labels), "",
                          "Four checks refuse a bad wing:", "numbers → loft, trailing edge,", "validity, repeatability."],
                         lambda ax: draw_3d(ax, st), three_d=True), 3000))
    return frames


# --- part 2: published wings -------------------------------------------------------------

def published_frames() -> list[tuple[Image.Image, int]]:
    out = []
    for name in published_wings.names():
        spec, vec, te, meta = published_wings.get(name)
        pf, st = build_wing_sections(spec, vec, te)
        lines = [meta["kind"].upper().replace("BWB", "BWB (blended wing body)"),
                 f"semi-span {pf.semi_span:.3g} m, root chord {pf.chord[0]:.3g} m",
                 f"aspect ratio {aspect_ratio(pf):.2f}, MAC {mean_aero_chord(pf):.3g} m",
                 "sections: " + ", ".join(dict.fromkeys(s.airfoil.name for s in st))]
        if "blendednet_parameters" in meta:
            p = meta["blendednet_parameters"]
            lines += ["", "from the BlendedNet parameters:",
                      f"C2 {p['C2']}  C3 {p['C3']}  C4 {p['C4']}",
                      f"B1 {p['B1']}  B2 {p['B2']}  B3 {p['B3']}",
                      f"S1 {p['S1']:.0f}°  S2 {p['S2']:.1f}°  S3 {p['S3']:.0f}°" + (f"  (X3 {p['X3']})" if "X3" in p else "")]
        else:
            lines += ["", _short(meta["fidelity"])]
        out.append((frame(_title(meta["title"]), lines, lambda ax, st=st: draw_3d(ax, st, color="#a9d0b8" if meta["kind"] == "bwb" else SURF),
                          foot="Rebuilt by the same generator · " + _src(meta), three_d=True), 2800))
    return out


def _title(t: str) -> str:
    t = t.replace("NASA Common Research Model wing", "NASA CRM wing").replace("BlendedNet design ", "BlendedNet: ")
    return t.replace(" (wind-tunnel model)", "").replace(" (half model)", " (half model)")


def _short(text: str, width: int = 34, max_lines: int = 7) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] += " …"
    return "\n".join(lines)


def _src(meta) -> str:
    s = meta["sources"][0]
    return (s[:60] + "…") if len(s) > 60 else s


# --- part 3: static figures -----------------------------------------------------------

def gallery_png(path: Path) -> None:
    names = published_wings.names()
    fig, axes = plt.subplots(2, 4, figsize=(13, 6.2))
    for ax, name in zip(axes.flat, names):
        spec, vec, te, meta = published_wings.get(name)
        pf, st = build_wing_sections(spec, vec, te)
        c0 = pf.chord[0]
        y, le, tr = pf.y / c0, pf.x_le / c0, (pf.x_le + pf.chord) / c0
        col = "#2e8b57" if meta["kind"] == "bwb" else ACCENT
        for s in (1, -1):
            ax.fill_between(s * y, le, tr, color=col, alpha=0.18, lw=0)
            ax.plot(s * y, le, color=col, lw=1.6)
            ax.plot(s * y, tr, color=col, lw=1.6)
            ax.plot([s * y[-1]] * 2, [le[-1], tr[-1]], color=col, lw=1.6)
        ax.set_title(_title(meta["title"]).replace(" (half model)", ""), fontsize=9.5, color=INK)
        ax.set_aspect("equal")
        ax.invert_yaxis()
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_xlabel(f"AR {aspect_ratio(pf):.2f}", fontsize=8.5, color=MUTED)
    for ax in axes.flat[len(names):]:
        ax.set_axis_off()
    fig.suptitle("Top views, scaled by root chord (blue: conventional, green: BWB)", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor="white")
    plt.close(fig)


def crm_check_png(path: Path) -> None:
    import importlib.util
    spec_t = importlib.util.spec_from_file_location("t", ROOT / "tests/geometry/test_airfoils_published.py")
    tab = None
    try:
        mod = importlib.util.module_from_spec(spec_t)
        spec_t.loader.exec_module(mod)
        tab = mod.CRM_TABLE
    except Exception:
        return
    spec, vec, te, meta = published_wings.get("nasa_crm")
    pf, st = build_wing_sections(spec, vec, te)
    eta = np.array([s.y for s in st]) / pf.semi_span
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
    a1.plot(tab[:, 0], tab[:, 1], "o", color=MUTED, ms=5, label="published (21 stations)")
    a1.plot(eta, [s.chord for s in st], "-", color=ACCENT, lw=2, label="generator (4 stations)")
    a1.set_xlabel("2y/b")
    a1.set_ylabel("chord [m]")
    a1.legend(frameon=False)
    a2.plot(tab[:, 0], tab[:, 2], "o", color=MUTED, ms=5, label="published")
    a2.plot(eta, [s.twist_deg for s in st], "-", color=ACCENT2, lw=2, label="generator")
    err = np.max(np.abs(np.interp(tab[:, 0], eta, [s.twist_deg for s in st]) - tab[:, 2]))
    a2.set_title(f"twist: largest gap {err:.2f}°", fontsize=10, color=INK)
    a2.set_xlabel("2y/b")
    a2.set_ylabel("twist [deg]")
    a2.legend(frameon=False)
    for a in (a1, a2):
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    fig.suptitle("NASA CRM: chords exact, twist approximate", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor="white")
    plt.close(fig)


def write_gif(frames, path: Path) -> None:
    imgs = [f for f, _ in frames]
    pal = [im.convert("P", palette=Image.ADAPTIVE, colors=128) for im in imgs]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=[d for _, d in frames], loop=0, optimize=True)


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    write_gif(build_steps(), DOCS / "how_a_wing_is_built.gif")
    write_gif(published_frames(), DOCS / "published_wings.gif")
    gallery_png(DOCS / "published_wings_topviews.png")
    crm_check_png(DOCS / "crm_check.png")
    for f in sorted(DOCS.glob("*")):
        print(f"{f.name:32s} {f.stat().st_size / 1e3:8.0f} kB")


if __name__ == "__main__":
    main()
