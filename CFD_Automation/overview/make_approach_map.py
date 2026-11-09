"""The approach map: one page that explains the updated approach (7 Nov 2026) in pictures.

    python overview/make_approach_map.py      # writes overview/APPROACH_MAP.html

The wings and the airfoil are drawn by the generator itself (the reference wing 0 of each type, at unit mean
chord, and NACA 4415 as built by the new nose rule). Every other number on the page comes from the Stage 0, 1 and 2
docs of 7 Nov 2026 and is written here by hand, with the doc it comes from.
"""

from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.flowmap import engine  # noqa: E402
from cfdauto.geometry.build import load_set  # noqa: E402
from cfdauto.geometry.params import load_config, resolve  # noqa: E402
from cfdauto.geometry.sections import load_airfoil  # noqa: E402

OUT = Path(__file__).resolve().parent / "APPROACH_MAP.html"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
NAMES = {"bwb": "BWB", "flying_wing": "Flying wing", "cranked": "Cranked", "tapered": "Tapered"}
FAMILY = {"bwb": "tailless", "flying_wing": "tailless", "cranked": "conventional", "tapered": "conventional"}

# Stage 1 page, "Shapes we can make (unit mean chord)": focus and full ranges, in mean chords
RANGES = {  # type: (AR focus, AR full, root focus, root full, tip focus, tip full)
    "bwb": ((3, 9), (2.5, 10), (1.572, 2.831), (1.320, 4.904), (0.099, 0.511), (0.055, 0.919)),
    "flying_wing": ((3, 13), (2.5, 14), (1.053, 1.539), (1.000, 1.667), (0.462, 0.947), (0.333, 1.000)),
    "cranked": ((4.5, 16.5), (3, 20), (1.015, 1.369), (1.000, 2.361), (0.439, 0.883), (0.234, 1.000)),
    "tapered": ((4.5, 16.5), (3, 20), (1.000, 1.429), (1.000, 1.600), (0.571, 1.000), (0.400, 1.000)),
}
from cfdauto.paths import STAGE1, STAGE2, re_levels  # noqa: E402

LEVELS = re_levels()          # Stage 0 values.yaml: 1e5, 3e5, 1e6, 4e6 since 8 Nov 2026 (were 1e5, 3e5, 1.5e6, 3e6)
LEV_LAB = {1e5: "1 × 10⁵", 3e5: "3 × 10⁵", 1e6: "1 × 10⁶", 1.5e6: "1.5 × 10⁶", 3e6: "3 × 10⁶", 4e6: "4 × 10⁶"}
# Stage 1 docs/size_extremes.json: local Re, smallest focus tip at the lowest level, largest focus root at the top level
_EXT = json.loads((STAGE1 / "docs" / "size_extremes.json").read_text())
LOCAL_RE = {t: (_EXT[f"{t}/focus"]["re_tip_min"], _EXT[f"{t}/focus"]["re_root_max"]) for t in TYPES}
# Stage 1 docs/greek_uavs.json (8 Nov 2026): the Greek tactical UAVs, cruise at 3,048 m to top speed at sea level
GREEK = json.loads((STAGE1 / "docs" / "greek_uavs.json").read_text())["rows"]
# Stage 2 data/studies/screen_family_summary.json (Study 12, 8 Nov: every set at every level, upper band 0-100 % c;
# the reference wings at the 8 Nov levels): cells per level; Study 9's file if Study 12 is missing
_SF = STAGE2 / "data" / "studies" / "screen_family_summary.json"
_SN = json.loads((_SF if _SF.exists() else STAGE2 / "data" / "studies" / "screen_new_summary.json").read_text())["reference"]
CELLS = {lv: (_SN[lv]["cells_est"]["median"] / 1e6, _SN[lv]["cells_est"]["max"] / 1e6, _SN[lv]["cells_est"]["min"] / 1e6)
         for lv in ("VC", "C", "M", "F")}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def planforms() -> dict:
    cfg = load_config()
    out = {}
    for t in TYPES:
        spec = cfg.types[t]
        vec = resolve(spec, load_set(t, "reference")["vectors"][0])
        ws = engine.wing_strips(spec, vec, None, 2)
        pf = ws.pf
        out[t] = {"y": [float(v) for v in pf.y], "xle": [float(v) for v in pf.x_le], "c": [float(v) for v in pf.chord],
                  "semi": float(pf.semi_span), "ar": float(vec["aspect_ratio"]),
                  "airfoils": [s.airfoil.name for s in ws.stations]}
    return out


def poly(p: dict, s: float, x0: float, y0: float) -> str:
    le = [(x0 + y * s, y0 + x * s) for y, x in zip(p["y"], p["xle"])]
    te = [(x0 + y * s, y0 + (x + c) * s) for y, x, c in zip(p["y"], p["xle"], p["c"])]
    pts = le + te[::-1]
    return " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)


def svg(w: int, h: int, body: str, label: str, cls: str = "") -> str:
    return (f'<svg class="fig {cls}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}" '
            f'xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def T(x, y, s, cls="t", anchor="start", extra=""):
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}" {extra}>{esc(s)}</text>'


# ---------------------------------------------------------------- drawings
def fig_generator(pf: dict) -> str:
    p = pf["bwb"]
    s, x0, y0 = 150.0, 70.0, 58.0
    b = [f'<polygon points="{poly(p, s, x0, y0)}" class="wing"/>']
    names = ["b0 root", "b1", "b2", "b3 tip"]
    ymax = y0 + max(x + c for x, c in zip(p["xle"], p["c"])) * s
    for i, (y, x, c) in enumerate(zip(p["y"], p["xle"], p["c"])):
        X = x0 + y * s
        b.append(f'<line x1="{X:.1f}" y1="{y0 + x * s - 8:.1f}" x2="{X:.1f}" y2="{ymax + 14:.1f}" class="stn"/>')
        b.append(T(X, ymax + 30, names[i], "t sm", "middle"))
        b.append(T(X, y0 + x * s - 14, p["airfoils"][i].upper().replace("MH", "MH "), "t xs mut", "middle"))
    for i in range(3):
        xm = x0 + (p["y"][i] + p["y"][i + 1]) / 2 * s
        ym = y0 + ((p["xle"][i] + p["c"][i] / 2) + (p["xle"][i + 1] + p["c"][i + 1] / 2)) / 2 * s
        b.append(T(xm, ym + 5, f"panel {i + 1}", "t sm acc", "middle"))
    # root chord dimension
    xr = x0 - 26
    b.append(f'<line x1="{xr}" y1="{y0}" x2="{xr}" y2="{y0 + p["c"][0] * s:.1f}" class="dim" marker-start="url(#ar)" marker-end="url(#ar)"/>')
    b.append(T(xr - 8, y0 + p["c"][0] * s / 2, f'root {p["c"][0]:.2f} c̄', "t xs", "middle",
               f'transform="rotate(-90 {xr - 8} {y0 + p["c"][0] * s / 2:.1f})"'))
    # semi-span dimension
    yd = ymax + 48
    b.append(f'<line x1="{x0}" y1="{yd}" x2="{x0 + p["semi"] * s:.1f}" y2="{yd}" class="dim" marker-start="url(#ar)" marker-end="url(#ar)"/>')
    b.append(T(x0 + p["semi"] * s / 2, yd + 18, f'semi-span = AR / 2 = {p["semi"]:.1f} mean chords (AR {p["ar"]:.0f})', "t sm", "middle"))
    # mean chord bar
    xb = x0 + p["semi"] * s + 28
    b.append(f'<line x1="{xb:.1f}" y1="{y0 + 40}" x2="{xb:.1f}" y2="{y0 + 40 + s:.1f}" class="dim acc"/>')
    b.append(T(xb + 8, y0 + 40 + s / 2 - 6, "c̄ = 1", "t sm acc"))
    b.append(T(xb + 8, y0 + 40 + s / 2 + 10, "mean chord =", "t xs mut"))
    b.append(T(xb + 8, y0 + 40 + s / 2 + 24, "area / full span", "t xs mut"))
    defs = ('<defs><marker id="ar" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0,1 L9,5 L0,9 z" class="mk"/></marker></defs>')
    return svg(700, int(yd + 34), defs + "".join(b), "The BWB reference wing as the generator builds it: four stations b0 to b3, three straight panels, at unit mean chord", "wide")


def fig_section() -> str:
    a = load_airfoil("naca4415").selig()
    s, x0, y0 = 470.0, 40.0, 92.0
    pts = " ".join(f"{x0 + x * s:.1f},{y0 - y * s:.1f}" for x, y in a)
    b = [f'<polygon points="{pts}" class="wing"/>']
    # nose zoom marker
    b.append(f'<circle cx="{x0 + 2:.1f}" cy="{y0:.1f}" r="16" class="ring"/>')
    b.append(T(x0, y0 + 44, "nose: one cubic spline through the file's points,", "t xs"))
    b.append(T(x0, y0 + 59, "leading edge at its apex, 201 points per side", "t xs"))
    b.append(T(x0, y0 + 78, "trailing edge 0.2 % c, a blunt base on every wing", "t xs mut"))
    b.append(T(x0 + s / 2, 22, "NACA 4415 as built (new nose rule)", "t sm", "middle"))
    return svg(560, 180, "".join(b), "NACA 4415 as built by the new nose rule, with the nose and trailing-edge rules", "wide narrow")


def fig_types(pf: dict) -> str:
    cards = []
    s = 54.0
    for t in TYPES:
        p = pf[t]
        h = max(x + c for x, c in zip(p["xle"], p["c"])) * s + 20
        body = f'<polygon points="{poly(p, s, 10, 10)}" class="wing"/>'
        body += f'<line x1="10" y1="10" x2="10" y2="{10 + p["c"][0] * s:.1f}" class="root"/>'
        sv = svg(int(5.4 * s + 24), int(max(h, 3.0 * s)), body, f"{NAMES[t]} reference wing, top view, to scale")
        arf, _, rootf, _, tipf, _ = RANGES[t]
        cards.append(f'''<div class="tcard"><div class="thead"><span class="tname">{NAMES[t]}</span><span class="chip">{FAMILY[t]}</span></div>
{sv}
<p class="tnum">This wing: AR {p["ar"]:.1f}, root {p["c"][0]:.2f} c̄, tip {p["c"][-1]:.2f} c̄</p>
<p class="tnum mut">Focus: AR {arf[0]:g}–{arf[1]:g}; root {rootf[0]:.2f}–{rootf[1]:.2f} c̄; tip {tipf[0]:.2f}–{tipf[1]:.2f} c̄</p></div>''')
    return '<div class="types">' + "".join(cards) + "</div>"


def fig_ranges() -> str:
    """Full and focus ranges per type: aspect ratio, root chord, tip chord (mean chords)."""
    W, H = 660, 360
    panels = [(("Aspect ratio", "= full span, in c̄"), 0, 20, 0, 1, [0, 5, 10, 15, 20]),
              (("Root chord", "in mean chords c̄"), 0, 5, 2, 3, [0, 1, 2, 3, 4, 5]),
              (("Tip chord", "in mean chords c̄"), 0, 1, 4, 5, [0, 0.5, 1.0])]
    b = []
    pw, x0 = 150, 112
    for k, (title, lo, hi, ifo, ifu, ticks) in enumerate(panels):
        px = x0 + k * (pw + 36)
        b.append(T(px, 16, title[0], "t sm"))
        b.append(T(px, 31, title[1], "t xs mut"))
        for j, t in enumerate(TYPES):
            y = 52 + j * 62
            if k == 0:
                b.append(T(x0 - 10, y + 10, NAMES[t], "t sm", "end"))
            fu, fo = RANGES[t][ifu], RANGES[t][ifo]
            X = lambda v: px + (v - lo) / (hi - lo) * pw
            b.append(f'<rect x="{X(fu[0]):.1f}" y="{y}" width="{X(fu[1]) - X(fu[0]):.1f}" height="18" class="full"/>')
            b.append(f'<rect x="{X(fo[0]):.1f}" y="{y + 4}" width="{X(fo[1]) - X(fo[0]):.1f}" height="10" class="focus"/>')
            fmt = (lambda v: f"{v:g}") if k == 0 else (lambda v: f"{v:.2f}")
            b.append(T(X(fo[0]), y + 34, f"{fmt(fo[0])}–{fmt(fo[1])}", "t xs acc"))
        for tv in ticks:
            X = px + (tv - lo) / (hi - lo) * pw
            b.append(f'<line x1="{X:.1f}" y1="44" x2="{X:.1f}" y2="{52 + 4 * 62 - 12}" class="grid"/>')
            b.append(T(X, 52 + 4 * 62 + 2, f"{tv:g}", "t xs mut", "middle"))
    b.append(f'<rect x="{x0}" y="{H - 28}" width="22" height="10" class="full"/>')
    b.append(T(x0 + 28, H - 19, "full space: supported, sparse", "t xs mut"))
    b.append(f'<rect x="{x0 + 250}" y="{H - 28}" width="22" height="10" class="focus"/>')
    b.append(T(x0 + 278, H - 19, "focus space: real wings, dense", "t xs"))
    return svg(W, H, "".join(b), "Full space and focus space per wing type: aspect ratio, root chord and tip chord in mean chords", "wide")


def fig_similarity() -> str:
    """Three real wings of one shape at different sizes and speeds become one shape at c̄ = 1 and an Re."""
    b = []
    shape = [(0, 0), (1.0, 0.25), (1.0, 0.55), (0, 0.9)]  # a little half wing, x = span, y = chord
    rows = [(0.2, 15), (0.5, 30), (1.0, 45)]
    rho_mu = 68474
    for i, (cbar, V) in enumerate(rows):
        sc = 40 + 110 * cbar
        y = 30 + i * 92
        pts = " ".join(f"{20 + x * sc:.1f},{y + yy * sc * 0.55:.1f}" for x, yy in shape)
        b.append(f'<polygon points="{pts}" class="wing"/>')
        re_ = rho_mu * V * cbar
        b.append(T(196, y + 20, f"c̄ = {cbar:g} m, {V} m/s", "t sm"))
        b.append(T(196, y + 38, f"Re = {re_ / 10 ** math.floor(math.log10(re_)):.1f} × 10{sup(int(math.floor(math.log10(re_))))} · Mach {V / 340.3:.3f}", "t xs mut"))
    b.append(f'<path d="M 390 152 L 414 152" class="arrow" marker-end="url(#ar2)"/>')
    # unit shape
    sc = 120
    pts = " ".join(f"{420 + x * sc:.1f},{96 + yy * sc * 0.55:.1f}" for x, yy in shape)
    b.append(f'<polygon points="{pts}" class="wing now"/>')
    b.append(T(420, 86, "one shape, c̄ = 1", "t sm acc"))
    b.append(T(420, 188, "+ the Re as an input:", "t sm"))
    for k, lab in enumerate(LEV_LAB.get(r, f"{r:.2g}") for r in LEVELS):
        b.append(f'<rect x="{420 + k * 68}" y="198" width="64" height="22" rx="3" class="lvl"/>')
        b.append(T(452 + k * 68, 213, lab, "t xs", "middle"))
    b.append(T(420, 244, "Mach 0.1; CL, CM × 1/√(1−M²)", "t xs mut"))
    b.append(T(420, 260, "×1.005 at M 0.1 · ×1.021 at 0.2", "t xs mut"))
    defs = ('<defs><marker id="ar2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
            '<path d="M0,1 L9,5 L0,9 z" class="mk"/></marker></defs>')
    return svg(700, 290, defs + "".join(b), "Similarity: three wings of one shape at different sizes and speeds become one shape at unit mean chord plus an Re", "wide")


def sup(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))


def fig_re() -> str:
    """The Re ruler: levels, real wings, local Re per type, first approach, and the flow regimes."""
    W = 680
    x0, x1 = 150, 630
    lo, hi = math.log10(3e3), math.log10(2e7)
    X = lambda r: x0 + (math.log10(r) - lo) / (hi - lo) * (x1 - x0)
    b = []
    rows = []
    y = 40
    # regime bands (on the local chord), drawn first as a background
    reg = [(3e3, 4e4, "open separation", "r1"), (4e4, 1e5, "long bubbles", "r2"), (1e5, 5e5, "bubbles (93–99 %)", "r3"),
           (5e5, 2e6, "bubbles fade", "r4"), (2e6, 2e7, "short laminar run", "r5")]
    top, bot = 26, 364
    for a, c, lab, cls in reg:
        b.append(f'<rect x="{X(a):.1f}" y="{top}" width="{X(c) - X(a):.1f}" height="{bot - top}" class="reg {cls}"/>')
    for k, (a, c, lab, cls) in enumerate(reg):
        if k:
            b.append(f'<line x1="{X(a):.1f}" y1="{bot}" x2="{X(a):.1f}" y2="{bot + 38}" class="sep"/>')
        b.append(T((X(a) + X(c)) / 2, bot + 16 + (k % 2) * 16, lab, "t xs", "middle"))
    b.append(T(x0 - 10, bot + 24, "flow on the local chord", "t xs mut", "end"))
    # decade grid
    for e in range(4, 8):
        b.append(f'<line x1="{X(10 ** e):.1f}" y1="{top}" x2="{X(10 ** e):.1f}" y2="{bot}" class="grid"/>')
        b.append(T(X(10 ** e), top - 8, f"10{sup(e)}", "t xs mut", "middle"))
    # rows
    def label(y, s1, s2=""):
        b.append(T(x0 - 10, y + 4, s1, "t sm", "end"))
        if s2:
            b.append(T(x0 - 10, y + 18, s2, "t xs mut", "end"))
    y = 56
    label(y, "Study levels", "on the mean chord")
    for r in LEVELS:
        b.append(f'<circle cx="{X(r):.1f}" cy="{y}" r="7" class="lvldot"/>')
    b.append(T(X(LEVELS[-1]) + 12, y + 4, "since 8 Nov", "t xs mut"))
    y = 106
    label(y, "Real UAV wings", "34 wings, mean chord")
    b.append(f'<rect x="{X(1.22e5):.1f}" y="{y - 7}" width="{X(3.10e6) - X(1.22e5):.1f}" height="14" rx="7" class="realbar"/>')
    b.append(T(X(1.22e5), y + 24, "1.22 × 10⁵", "t xs", "middle"))
    b.append(T(X(3.10e6), y + 24, "3.10 × 10⁶", "t xs", "middle"))
    y = 146
    label(y, "Greek UAVs", "AR 8 assumed")
    lo_g = min(r["re_cruise_3048m"] for r in GREEK)
    hi_g = max(max(r["re_top_sea_level"]) for r in GREEK)
    b.append(f'<rect x="{X(lo_g):.1f}" y="{y - 6}" width="{X(hi_g) - X(lo_g):.1f}" height="12" rx="6" class="greekbar"/>')
    for r in GREEK:
        b.append(f'<circle cx="{X(r["re_cruise_3048m"]):.1f}" cy="{y}" r="3" class="enddot"/>')
    b.append(T(X(hi_g) + 8, y + 4, "LOTUS 11 m", "t xs mut"))
    y = 196
    for t in TYPES:
        a, c = LOCAL_RE[t]
        label(y, NAMES[t], "local Re, focus" if t == "bwb" else "")
        b.append(f'<line x1="{X(a):.1f}" y1="{y}" x2="{X(c):.1f}" y2="{y}" class="localbar"/>')
        b.append(f'<circle cx="{X(a):.1f}" cy="{y}" r="4" class="enddot"/><circle cx="{X(c):.1f}" cy="{y}" r="4" class="enddot"/>')
        b.append(T(X(a), y - 8, f"{fmt_sci(a)}", "t xs", "middle"))
        b.append(T(X(c), y - 8, f"{fmt_sci(c)}", "t xs", "middle"))
        y += 34
    y += 6
    label(y, "First approach", "real size and speed")
    b.append(f'<line x1="{X(1.4e4):.1f}" y1="{y}" x2="{X(5.5e6):.1f}" y2="{y}" class="oldbar"/>')
    b.append(f'<rect x="{X(5.4e4):.1f}" y="{y - 6}" width="{X(3.5e6) - X(5.4e4):.1f}" height="12" rx="6" class="oldmean"/>')
    b.append(T(X(5.4e4), y - 12, "mean chord 5.4 × 10⁴ – 3.5 × 10⁶", "t xs mut"))
    return svg(W, 412, "".join(b), "Reynolds number map: the four levels, the real wings, the local Re of each type, the first approach and the flow regimes", "wide")


def fmt_sci(r: float) -> str:
    e = int(math.floor(math.log10(r)))
    m = r / 10 ** e
    return f"{m:.1f} × 10{sup(e)}" if abs(m - 1) > 1e-9 else f"10{sup(e)}"


def fig_mach() -> str:
    x0, x1 = 30, 620
    X = lambda m: x0 + m / 0.6 * (x1 - x0)
    b = [f'<rect x="{X(0):.1f}" y="32" width="{X(0.3) - X(0):.1f}" height="68" class="incomp"/>',
         T(X(0.15), 24, "nearly incompressible below Mach 0.3", "t xs mut", "middle")]
    b.append(f'<rect x="{X(0.034):.1f}" y="40" width="{X(0.13) - X(0.034):.1f}" height="12" rx="6" class="oldmean"/>')
    b.append(T(X(0.13) + 6, 50, "first: tailless 0.034–0.13", "t xs"))
    b.append(f'<rect x="{X(0.034):.1f}" y="60" width="{X(0.20) - X(0.034):.1f}" height="12" rx="6" class="oldmean"/>')
    b.append(T(X(0.20) + 6, 70, "first: conventional 0.034–0.20", "t xs"))
    b.append(f'<rect x="{X(0.3):.1f}" y="80" width="{X(0.5) - X(0.3):.1f}" height="12" rx="6" class="later"/>')
    b.append(f'<line x1="{X(0.1):.1f}" y1="32" x2="{X(0.1):.1f}" y2="104" class="nowline"/>')
    b.append(f'<line x1="{x0}" y1="104" x2="{x1}" y2="104" class="axis"/>')
    for m in (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        b.append(f'<line x1="{X(m):.1f}" y1="104" x2="{X(m):.1f}" y2="108" class="axis"/>')
        b.append(T(X(m), 121, f"{m:g}", "t xs mut", "middle"))
    b.append(T(X(0.1) + 6, 140, "CFD now: every wing at Mach 0.1, + Prandtl–Glauert", "t xs acc"))
    b.append(T(X(0.5), 158, "later (pending): 0.3–0.5, a fast-UAV family", "t xs amb", "end"))
    b.append(T(x1, 176, "Mach · no supersonic flow anywhere", "t xs mut", "end"))
    return svg(650, 184, "".join(b), "Mach numbers: first approach, the CFD now and the later fast-UAV range", "wide")


def fig_flow() -> str:
    """The flow on one section at small angle: laminar run, bubble, turbulent; the lower side at -5 degrees."""
    a = load_airfoil("naca4415").selig()
    s, x0, y0 = 520.0, 50.0, 120.0
    n = len(a) // 2
    up, lo = a[: n + 1][::-1], a[n:]  # upper LE->TE, lower LE->TE
    P = lambda pts: " ".join(f"{x0 + x * s:.1f},{y0 - y * s:.1f}" for x, y in pts)
    b = [f'<polygon points="{P(a)}" class="wing"/>']
    def seg(pts, x_a, x_b, cls, off):
        q = [(x, y) for x, y in pts if x_a <= x <= x_b]
        if len(q) < 2:
            return ""
        return f'<polyline points="{" ".join(f"{x0 + x * s:.1f},{y0 - y * s - off:.1f}" for x, y in q)}" class="{cls}"/>'
    b.append(seg(up, 0.0, 0.47, "lam", 5))
    b.append(seg(up, 0.47, 0.62, "bub", 9))
    b.append(seg(up, 0.62, 1.0, "turb", 6))
    b.append(seg(lo, 0.0, 0.90, "lam", -5))
    b.append(seg(lo, 0.90, 1.0, "turb", -6))
    b.append(T(x0 + 0.20 * s, y0 - 0.12 * s - 18, "laminar run", "t xs good", "middle"))
    b.append(T(x0 + 0.545 * s, y0 - 0.11 * s - 26, "laminar bubble", "t xs amb", "middle"))
    b.append(T(x0 + 0.545 * s, y0 - 0.11 * s - 13, "(transition on it)", "t xs mut", "middle"))
    b.append(T(x0 + 0.84 * s, y0 - 0.06 * s - 18, "turbulent", "t xs hot", "middle"))
    b.append(T(x0 + 0.45 * s, y0 + 0.05 * s + 26, "lower side: laminar almost to the trailing edge at 0–10°", "t xs", "middle"))
    b.append(T(x0 + 0.45 * s, y0 + 0.05 * s + 42, "at −5° it becomes the suction side: transition at 1–15 % c", "t xs hot", "middle"))
    return svg(640, 230, "".join(b), "The flow on one section at a small angle: laminar run, laminar bubble, turbulent flow; the lower side at minus five degrees", "wide")


def fig_bands() -> str:
    """Where the transition band (fine cells) runs along the chord, first and now, both sides."""
    x0, x1 = 150, 620
    X = lambda f: x0 + f * (x1 - x0)
    b = []
    rows = [("First", "upper", 0.0, 0.85, None), ("First", "lower", 0.60, 1.0, None),
            ("Now", "upper", 0.0, 0.85, (0.85, 1.0)), ("Now", "lower", 0.0, 1.0, None)]
    for i, (ver, side, a, c, ext) in enumerate(rows):
        y = 30 + i * 40 + (12 if i >= 2 else 0)
        b.append(T(x0 - 12, y + 12, f"{ver} · {side}", "t sm" + (" acc" if ver == "Now" else ""), "end"))
        b.append(f'<rect x="{X(0):.1f}" y="{y}" width="{X(1) - X(0):.1f}" height="16" class="track"/>')
        b.append(f'<rect x="{X(a):.1f}" y="{y}" width="{X(c) - X(a):.1f}" height="16" class="{"bandnow" if ver == "Now" else "bandold"}"/>')
        if ext:
            b.append(f'<rect x="{X(ext[0]):.1f}" y="{y}" width="{X(ext[1]) - X(ext[0]):.1f}" height="16" class="bandext"/>')
    b.append(T(X(1.0), 154, "light blue: band-size cells to the trailing edge, as built", "t xs", "end"))
    for f in (0, 0.25, 0.5, 0.75, 1.0):
        b.append(T(X(f), 196, f"{int(f * 100)} % c", "t xs mut", "middle"))
    b.append(T(X(0.01), 214, "leading edge", "t xs mut"))
    b.append(T(X(0.99), 214, "trailing edge", "t xs mut", "end"))
    return svg(660, 222, "".join(b), "The transition band along the chord: first and now, upper and lower side", "wide")


def ladder_html() -> str:
    cols = [("VC", "desktop", "hard minimums", ["y⁺ ≤ 1 at the first cell", "growth ≤ 1.25", "base ≥ 8 cells", "no kinks; tip gap 2 × s0"], "nose 16.9° · 9.1 cells per bubble"),
            ("C", "university HPC", "", [], "nose 13° · 11.8 cells per bubble"),
            ("M", "university HPC", "accuracy (as DPW's medium grid)", ["nose 10° per cell", "trailing edge 0.1 % c", "station gap 0.25 × chord", "largest cell 2 % c"], "15.4 cells per bubble"),
            ("F", "university HPC", "transition", ["20 cells per bubble", "wall growth 1.107"], "nose 7.69°")]
    out = []
    for lv, where, anchor, items, vals in cols:
        li = "".join(f"<li>{x}</li>" for x in items)
        a = f'<span class="anch">{anchor}</span><ul>{li}</ul>' if anchor else '<span class="anch none">no anchor: follows the 1.3 step</span>'
        out.append(f'<div class="lv"><div class="lvtop"><span class="lvn">{lv}</span><span class="where">{where}</span></div>{a}<span class="vals">{vals}</span></div>')
    return ('<div class="ladder">' + "".join(out) + '</div><p class="note">Each step to a finer level divides every spacing by 1.3 (about 2.2 × the cells). '
            'First approach: levels C, M, F, FF with every rule met at C, the coarsest, so the finer levels went far past the targets (44 cells per bubble at FF).</p>')


def fig_topology() -> str:
    b = []
    def foil(cx, cy, L, cls="wing"):
        a = load_airfoil("naca4415").selig()
        return f'<polygon points="{" ".join(f"{cx + x * L:.1f},{cy - y * L:.1f}" for x, y in a)}" class="{cls}"/>'
    # first: overset
    cx, cy, L = 60, 110, 120
    b.append(T(20, 22, "First plan: overset (ADflow only)", "t sm"))
    b.append(f'<rect x="14" y="34" width="292" height="152" class="bgbox"/>')
    b.append(T(300, 50, "background box 0.03 c", "t xs mut", "end"))
    for k, r in enumerate((14, 28, 44)):
        b.append(f'<ellipse cx="{cx + L / 2:.1f}" cy="{cy}" rx="{L / 2 + r:.1f}" ry="{14 + r:.1f}" class="oring"/>')
    b.append(f'<rect x="{cx + L - 4:.1f}" y="{cy - 22}" width="128" height="44" class="wakebox"/>')
    b.append(T(cx + L + 60, cy + 40, "wake box 0.0075 c", "t xs", "middle"))
    b.append(foil(cx, cy, L))
    b.append(T(20, 206, "+ a tip-vortex tube; overlap ≥ 5 cells", "t xs mut"))
    # new: C-H
    ox = 340
    cx, cy = ox + 56, 110
    b.append(T(ox + 6, 22, "Now: one matched C-H mesh (ADflow + SU2)", "t sm acc"))
    b.append(f'<rect x="{ox}" y="34" width="300" height="152" class="bgbox"/>')
    for k, r in enumerate((12, 24, 37, 50)):
        d = (f"M {ox + 300} {cy - 14 - r} L {cx + L * 0.55:.1f} {cy - 14 - r} "
             f"A {L * 0.55 + r:.1f} {14 + r} 0 0 0 {cx + L * 0.55:.1f} {cy + 14 + r} L {ox + 300} {cy + 14 + r}")
        b.append(f'<path d="{d}" class="cline"/>')
    b.append(f'<line x1="{cx + L:.1f}" y1="{cy}" x2="{ox + 300}" y2="{cy}" class="wakeline"/>')
    b.append(T(ox + 296, cy + 20, "wake lines → far field", "t xs amb", "end"))
    b.append(foil(cx, cy, L))
    b.append(T(ox + 6, 206, "tip vortex in the outboard blocks; no overlap", "t xs mut"))
    return svg(660, 216, "".join(b), "Volume mesh: the first overset plan against the matched C-H mesh", "wide")


def fig_budget() -> str:
    x0, x1 = 230, 610
    X = lambda m: x0 + m / 18 * (x1 - x0)
    b = []
    b.append(f'<rect x="{X(9):.1f}" y="20" width="{X(11) - X(9):.1f}" height="236" class="target"/>')
    b.append(T((X(9) + X(11)) / 2, 14, "asked: 9–11 M", "t xs good", "middle"))
    rows = [("6 Nov estimate", "planned rules", 15.2, None, "bold"), ("", "+ lighter band", 10.9, None, "old"),
            ("7–8 Nov count", "built rules, wing blocks", round(CELLS["F"][0], 1), (round(CELLS["F"][2], 1), round(CELLS["F"][1], 1)), "now"),
            ("", "+ C-H wake lines (rough)", 9.0, (9.0, 11.0), "wake")]
    for i, (grp, lab, v, rng, cls) in enumerate(rows):
        y = 36 + i * 54 + (14 if i >= 2 else 0)
        if grp:
            b.append(T(x0 - 12, y + 4, grp, "t sm" + (" acc" if "Nov count" in grp and "6 Nov" not in grp else " mut"), "end"))
        b.append(T(x0 - 12, y + 20, lab, "t xs", "end"))
        if cls == "wake":
            f_med = round(CELLS["F"][0], 1)
            b.append(f'<rect x="{X(0):.1f}" y="{y + 6}" width="{X(f_med) - X(0):.1f}" height="18" class="barnow"/>')
            b.append(f'<rect x="{X(f_med):.1f}" y="{y + 6}" width="{X(11.0) - X(f_med):.1f}" height="18" class="barwake"/>')
            b.append(T(X(11.0) + 6, y + 20, "≈ 9–11 M", "t sm"))
            continue
        b.append(f'<rect x="{X(0):.1f}" y="{y + 6}" width="{X(v) - X(0):.1f}" height="18" class="{"barnow" if cls == "now" else "barold"}"/>')
        b.append(T(X(v) + 6, y + 20, f"{v:g} M", "t sm"))
        if rng:
            b.append(f'<line x1="{X(rng[0]):.1f}" y1="{y + 32}" x2="{X(rng[1]):.1f}" y2="{y + 32}" class="whisk"/>')
            b.append(T(X(rng[1]) + 6, y + 36, f"range {rng[0]:g}–{rng[1]:g} M", "t xs mut"))
    for m in (0, 3, 6, 9, 12, 15, 18):
        b.append(f'<line x1="{X(m):.1f}" y1="256" x2="{X(m):.1f}" y2="261" class="axis"/>')
        b.append(T(X(m), 276, f"{m} M", "t xs mut", "middle"))
    b.append(f'<line x1="{X(0):.1f}" y1="256" x2="{X(18):.1f}" y2="256" class="axis"/>')
    b.append(T(x1, 292, "cells at the fine level F, median over 20 reference wings × 4 Re", "t xs mut", "end"))
    return svg(640, 300, "".join(b), "Cells at the fine level F: the 6 Nov estimate and the 7 Nov count against the 9 to 11 million asked", "wide")


def fig_levels_cells() -> str:
    x0, x1 = 90, 610
    lo, hi = math.log10(0.3), math.log10(16)
    X = lambda m: x0 + (math.log10(m) - lo) / (hi - lo) * (x1 - x0)
    b = []
    data = [(lv, round(CELLS[lv][0], 2), round(CELLS[lv][1], 2)) for lv in ("VC", "C", "M", "F")]
    for i, (lv, med, mx) in enumerate(data):
        y = 34 + i * 46
        b.append(T(x0 - 12, y + 15, lv, "t lg", "end"))
        b.append(T(x0 + 2, y - 5, f"{med:g} M median, largest {mx:g} M", "t xs"))
        b.append(f'<rect x="{X(0.3):.1f}" y="{y}" width="{X(med) - X(0.3):.1f}" height="18" class="barnow"/>')
        b.append(f'<line x1="{X(med):.1f}" y1="{y + 9}" x2="{X(mx):.1f}" y2="{y + 9}" class="whisk"/>')
    for lim, lab, cls in ((1.2, "desktop 16 GB ≈ 1.2 M", "lim1"), (5.0, "+36 GB ≈ 5.0 M", "lim2")):
        b.append(f'<line x1="{X(lim):.1f}" y1="20" x2="{X(lim):.1f}" y2="196" class="{cls}"/>')
        b.append(T(X(lim) + 4, 210, lab, "t xs"))
    for m in (0.5, 1, 2, 5, 10):
        b.append(T(X(m), 230, f"{m:g} M", "t xs mut", "middle"))
    return svg(640, 238, "".join(b), "Cells per level on the wing blocks, against the desktop memory limits", "wide")


# ---------------------------------------------------------------- page
CSS = r"""
/* Layout: one column, the flow of thought from top to bottom; each step = a short claim, one drawing, a conclusion. */
:root {
  --bg: #F3F6F9; --surface: #FFFFFF; --ink: #142230; --muted: #5A6878; --line: #D6DEE6; --grid: #E6EBF0;
  --accent: #0C5EA8; --accent-soft: #DCE9F6; --good: #2E7D4F; --good-soft: #DDF0E4; --amber: #9A6200;
  --amber-soft: #F6E8CF; --hot: #B03A20; --hot-soft: #F6DED8; --wing: #CFDBE6; --wing-line: #3E5A74;
  --display: "Barlow Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, -apple-system, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #9AA9B7; --line: #2A3743; --grid: #1E2A35;
  --accent: #62AEF2; --accent-soft: #17324A; --good: #63C691; --good-soft: #163326; --amber: #E7B24F;
  --amber-soft: #392B12; --hot: #F08A72; --hot-soft: #3A201B; --wing: #23384B; --wing-line: #9CC0DE; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #9AA9B7; --line: #2A3743; --grid: #1E2A35;
  --accent: #62AEF2; --accent-soft: #17324A; --good: #63C691; --good-soft: #163326; --amber: #E7B24F;
  --amber-soft: #392B12; --hot: #F08A72; --hot-soft: #3A201B; --wing: #23384B; --wing-line: #9CC0DE; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.55; margin: 0;
  padding-block: 28px 72px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
main { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 22px; }
h1 { font-family: var(--display); font-weight: 700; font-size: clamp(32px, 6vw, 48px); line-height: 1.05; margin: 0; text-wrap: balance; letter-spacing: .01em; }
h2 { font-family: var(--display); font-weight: 600; font-size: clamp(24px, 4vw, 31px); line-height: 1.1; margin: 0; text-wrap: balance; }
h3 { font-family: var(--display); font-weight: 600; font-size: 20px; margin: 0; }
p { margin: 0; max-width: 72ch; }
.lede { color: var(--muted); font-size: 17px; }
.eyebrow { font-family: var(--mono); font-size: 11.5px; letter-spacing: .09em; text-transform: uppercase; color: var(--accent); }
section.step { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 22px clamp(14px, 3vw, 28px);
  display: flex; flex-direction: column; gap: 14px; scroll-margin-top: 16px; }
.flow { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 8px; }
.flow a { text-decoration: none; color: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: 6px;
  padding: 10px 10px 12px; display: flex; flex-direction: column; gap: 4px; min-width: 0; position: relative; }
.flow a:hover, .flow a:focus-visible { border-color: var(--accent); outline: none; }
.flow .n { font-family: var(--mono); font-size: 11px; color: var(--accent); }
.flow .h { font-family: var(--display); font-weight: 600; font-size: 18px; line-height: 1.1; }
.flow .s { font-size: 13px; color: var(--muted); line-height: 1.35; }
@media (max-width: 900px) { .flow { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.figwrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
svg.fig { display: block; width: 100%; height: auto; }
svg.fig.wide { min-width: 560px; }
svg.fig.narrow { max-width: 620px; }
svg .sep { stroke: var(--line); stroke-width: 1; }
svg .t { font-family: var(--mono); font-size: 12.5px; fill: var(--ink); }
svg .t.sm { font-size: 13px; } svg .t.xs { font-size: 11.5px; } svg .t.lg { font-family: var(--display); font-size: 21px; font-weight: 600; }
svg .mut { fill: var(--muted); } svg .acc { fill: var(--accent); } svg .good { fill: var(--good); } svg .amb { fill: var(--amber); } svg .hot { fill: var(--hot); }
svg .wing { fill: var(--wing); stroke: var(--wing-line); stroke-width: 1.4; }
svg .wing.now { fill: var(--accent-soft); stroke: var(--accent); }
svg .stn { stroke: var(--accent); stroke-width: 1.2; stroke-dasharray: 4 4; }
svg .dim { stroke: var(--muted); stroke-width: 1.2; fill: none; } svg .dim.acc { stroke: var(--accent); stroke-width: 3; }
svg .mk { fill: var(--muted); } svg .ring { fill: none; stroke: var(--accent); stroke-width: 1.6; }
svg .root { stroke: var(--wing-line); stroke-width: 2; }
svg .grid { stroke: var(--grid); stroke-width: 1; } svg .axis { stroke: var(--muted); stroke-width: 1; }
svg .full { fill: var(--grid); stroke: var(--line); } svg .focus { fill: var(--accent); }
svg .lvl { fill: var(--accent-soft); stroke: var(--accent); } svg .lvldot { fill: var(--accent); stroke: var(--surface); stroke-width: 2; }
svg .arrow { stroke: var(--muted); stroke-width: 2; fill: none; }
svg .reg { opacity: 1; } svg .r1 { fill: var(--hot-soft); } svg .r2 { fill: var(--amber-soft); } svg .r3 { fill: var(--amber-soft); opacity: .6; }
svg .r4 { fill: var(--good-soft); opacity: .7; } svg .r5 { fill: var(--accent-soft); opacity: .7; }
svg .realbar { fill: var(--good); opacity: .85; } svg .greekbar { fill: var(--amber, #9A6200); opacity: .75; } svg .localbar { stroke: var(--ink); stroke-width: 3; } svg .enddot { fill: var(--ink); }
svg .oldbar { stroke: var(--muted); stroke-width: 2; stroke-dasharray: 5 4; } svg .oldmean { fill: var(--muted); opacity: .55; }
svg .incomp { fill: var(--grid); } svg .nowline { stroke: var(--accent); stroke-width: 3; } svg .later { fill: var(--amber); opacity: .75; }
svg .lam { fill: none; stroke: var(--good); stroke-width: 4; stroke-linecap: round; }
svg .bub { fill: none; stroke: var(--amber); stroke-width: 6; stroke-linecap: round; }
svg .turb { fill: none; stroke: var(--hot); stroke-width: 4; stroke-linecap: round; }
svg .track { fill: var(--grid); } svg .bandold { fill: var(--muted); opacity: .55; } svg .bandnow { fill: var(--accent); }
svg .bandext { fill: var(--accent); opacity: .35; }
svg .lvbox { fill: var(--accent-soft); stroke: var(--accent); } svg .anchorold { fill: var(--grid); stroke: var(--muted); }
svg .anchornow { fill: var(--surface); stroke: var(--accent); stroke-width: 1.4; }
svg .bgbox { fill: none; stroke: var(--line); stroke-width: 1.4; } svg .oring { fill: none; stroke: var(--muted); stroke-width: 1.1; }
svg .wakebox { fill: var(--amber-soft); stroke: var(--amber); } svg .cline { fill: none; stroke: var(--accent); stroke-width: 1.2; }
svg .wakeline { stroke: var(--amber); stroke-width: 2; stroke-dasharray: 6 4; }
svg .target { fill: var(--good-soft); } svg .barold { fill: var(--muted); opacity: .5; } svg .barnow { fill: var(--accent); }
svg .barwake { fill: var(--accent); opacity: .35; } svg .whisk { stroke: var(--ink); stroke-width: 1.5; }
svg .lim1 { stroke: var(--hot); stroke-width: 1.5; stroke-dasharray: 5 4; } svg .lim2 { stroke: var(--amber); stroke-width: 1.5; stroke-dasharray: 5 4; }
.ladder { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 760px) { .ladder { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.lv { border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.lvtop { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; flex-wrap: wrap; }
.lvn { font-family: var(--display); font-weight: 700; font-size: 28px; line-height: 1; color: var(--accent); }
.where { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.anch { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--accent); }
.anch.none { color: var(--muted); text-transform: none; letter-spacing: 0; }
.lv ul { margin: 0; padding-left: 16px; } .lv li { font-size: 14px; margin: 1px 0; }
.vals { font-family: var(--mono); font-size: 11.5px; color: var(--muted); margin-top: auto; }
.two { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 18px; align-items: start; }
@media (max-width: 820px) { .two { grid-template-columns: minmax(0, 1fr); } }
.types { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 820px) { .types { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.tcard { border: 1px solid var(--line); border-radius: 6px; padding: 10px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.thead { display: flex; justify-content: space-between; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.tname { font-family: var(--display); font-weight: 600; font-size: 19px; }
.tnum { font-family: var(--mono); font-size: 11.5px; line-height: 1.45; } .mut { color: var(--muted); }
.chip { font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted);
  border: 1px solid var(--line); border-radius: 999px; padding: 1px 8px; }
.cmp { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; }
@media (max-width: 640px) { .cmp { grid-template-columns: minmax(0, 1fr); } }
.cmp > div { border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cmp .k { font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.cmp .now .k { color: var(--accent); } .cmp .now { border-color: var(--accent); }
.cmp ul { margin: 0; padding-left: 18px; } .cmp li { margin: 2px 0; font-size: 15px; }
.concl { border-left: 4px solid var(--good); background: var(--good-soft); border-radius: 0 6px 6px 0; padding: 10px 14px; font-size: 15.5px; max-width: none; }
.concl b { font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--good); display: block; margin-bottom: 2px; }
.note { font-size: 14px; color: var(--muted); }
.tbl { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; min-width: 760px; }
th, td { text-align: left; vertical-align: top; padding: 7px 10px; border-bottom: 1px solid var(--line); }
tr:last-child td { border-bottom: 0; }
th { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); background: var(--bg); }
td.num { font-family: var(--mono); font-size: 13px; font-variant-numeric: tabular-nums; }
table.laws td.rule { min-width: 200px; } table.laws td.num { white-space: normal; min-width: 64px; }
td.f { color: var(--accent); font-weight: 600; }
td.old { color: var(--muted); }
.cards3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 760px) { .cards3 { grid-template-columns: minmax(0, 1fr); } }
.cards3 > div { border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cards3 h3 { font-size: 18px; }
.cards3 p { font-size: 14.5px; }
.status { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 760px) { .status { grid-template-columns: minmax(0, 1fr); } }
.status > div { border: 1px solid var(--line); border-radius: 6px; padding: 12px; background: var(--surface); min-width: 0; }
.status ul { margin: 6px 0 0; padding-left: 18px; } .status li { font-size: 14.5px; margin: 3px 0; }
.status .k { font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.k.ok { color: var(--good); } .k.you { color: var(--amber); } .k.next { color: var(--accent); }
footer { color: var(--muted); font-size: 13px; }
code { font-family: var(--mono); font-size: 13px; overflow-wrap: anywhere; }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
"""


def step(n: int, sid: str, stage: str, title: str, lead: str, body: str, concl: str) -> str:
    return (f'<section class="step" id="{sid}"><span class="eyebrow">Step {n} · {stage}</span><h2>{title}</h2>'
            f'<p class="lede">{lead}</p>{body}<p class="concl"><b>Conclusion</b>{concl}</p></section>')


def cmp(first: list[str], now: list[str]) -> str:
    li = lambda xs: "".join(f"<li>{x}</li>" for x in xs)
    return (f'<div class="cmp"><div><span class="k">First (30 Oct – 6 Nov)</span><ul>{li(first)}</ul></div>'
            f'<div class="now"><span class="k">Now (decided 4–7 Nov, built 7 Nov)</span><ul>{li(now)}</ul></div></div>')


def laws_table() -> str:
    rows = [
        ("Nose: turning per cell (law 1)", "10° at C", "4.55°", "10° at M", "16.9°", "13°", "10°", "7.69°"),
        ("Trailing-edge cell, % c (law 3)", "0.1 at C", "0.046", "0.1 at M", "0.169", "0.130", "0.100", "0.077"),
        ("Largest cell outside the bands, % c", "2 at C", "0.91", "2 at M", "3.38", "2.60", "2.00", "1.54"),
        ("Cells across a laminar bubble", "20 at C", "44", "20 at F", "9.1", "11.8", "15.4", "20"),
        ("Bubble-length table (band cell = bubble / cells)", "down to 0.05 c at Re 10⁶", "band 0.11 % c", "stops at 0.10 c from Re 4 × 10⁵", "", "", "", "band 0.5 % c"),
        ("Station gap, × local chord (law 8)", "0.2 at C", "0.091", "0.25 at M", "0.42", "0.33", "0.25", "0.19"),
        ("Gaps per panel, at least", "12 at C", "", "12 at M", "8", "10", "12", "16"),
        ("Last gap at the tip (laws 9, 10, 13)", "s0", "", "2 × s0", "", "", "", ""),
        ("Growth along the ring and of the wall layers", "1.25 at C", "1.107", "1.25 at VC", "1.25", "1.19", "1.14", "1.107"),
        ("First wall cell, y⁺", "≤ 1 at C", "0.46", "≤ 1 at VC", "1", "0.77", "0.59", "0.46"),
        ("Blunt base cells (law 6)", "8 at C", "18", "8 at VC", "8", "10", "14", "18"),
        ("Lower transition band", "60–100 % c", "", "0–100 % c", "", "", "", ""),
    ]
    head = ("<tr><th>Rule</th><th>First: met at</th><th>First at FF</th><th>Now: anchored at</th>"
            "<th>VC</th><th>C</th><th>M</th><th>F</th></tr>")
    body = ""
    for r in rows:
        body += (f'<tr><td class="rule">{r[0]}</td><td class="num old">{r[1]}</td><td class="num old">{r[2]}</td><td class="num">{r[3]}</td>'
                 f'<td class="num">{r[4]}</td><td class="num">{r[5]}</td><td class="num">{r[6]}</td><td class="num f">{r[7]}</td></tr>')
    return f'<div class="tbl"><table class="laws">{head}{body}</table></div>'


def size_table() -> str:
    rows = [("BWB", "0.42–6.7 m", "0.14–0.95 m", "11.1–44.4 m/s", "0.034–0.13", "3–9", "1.57–2.83", "0.10–0.51"),
            ("Flying wing", "0.49–6.8 m", "0.16–0.96 m", "11.1–44.4 m/s", "0.034–0.13", "3–13", "1.05–1.54", "0.46–0.95"),
            ("Cranked", "0.43–6.5 m", "0.09–0.71 m", "11.1–66.9 m/s", "0.034–0.20", "4.5–16.5", "1.02–1.37", "0.44–0.88"),
            ("Tapered", "0.41–6.8 m", "0.09–0.72 m", "11.1–66.9 m/s", "0.034–0.20", "4.5–16.5", "1.00–1.43", "0.57–1.00")]
    head = ("<tr><th>Focus wing</th><th>First: full span</th><th>First: mean chord</th><th>First: speed</th><th>First: Mach</th>"
            "<th>Now: AR = full span</th><th>Now: root chord</th><th>Now: tip chord</th></tr>")
    body = "".join(f'<tr><td>{r[0]}</td>' + "".join(f'<td class="num{" old" if i < 4 else ""}">{v}</td>' for i, v in enumerate(r[1:])) + "</tr>" for r in rows)
    return f'<div class="tbl"><table>{head}{body}</table></div>'


def page() -> str:
    pf = planforms()
    flow = [("1", "step-1", "Generator", "17 numbers + 4 airfoils make a wing"),
            ("2", "step-2", "Focus subset", "where real UAV wings are"),
            ("3", "step-3", "Similarity", "one shape, four Re levels"),
            ("4", "step-4", "Flow", "laminar runs, bubbles, transition"),
            ("5", "step-5", "Surface mesh", "levels VC to F, each rule where needed"),
            ("6", "step-6", "Volume mesh", "one C-H mesh for ADflow and SU2"),
            ("7", "step-7", "Cell budget", "F near 10 M cells")]
    strip = '<nav class="flow" aria-label="The steps">' + "".join(
        f'<a href="#{sid}"><span class="n">{n}</span><span class="h">{h}</span><span class="s">{s}</span></a>' for n, sid, h, s in flow) + "</nav>"

    s1 = step(1, "step-1", "Stage 1", "The generator builds every wing from a few numbers",
              "Four stations (root, two breaks, tip), three straight panels, four airfoils. Since 7 Nov every wing is built at unit mean chord, and the nose follows the airfoil file.",
              '<div class="figwrap">' + fig_generator(pf) + '</div><div class="figwrap">' + fig_section() + "</div>"
              + fig_types(pf)
              + cmp(["18 numbers, root chord in metres", "nose: leading edge on the farthest raw point (one side sharp, one side flat)",
                     "trailing edge max(0.5 / 1.0 mm, 0.2 % c)", "730 wings in the working sets"],
                    ["17 numbers (16 sampled + the semi-span, which follows), unit mean chord",
                     "nose: one cubic spline, leading edge at its apex; 95.6 % of 2,183 files pass (old 21.0 %)",
                     "trailing edge 0.2 % c on every wing", "722 wings in the working sets + 60 hold-outs, kept closed"]),
              "One generator makes all four types. The wing has no size any more, only a shape, and its nose now turns like the airfoil within 5 % per mesh cell.")

    s2 = step(2, "step-2", "Stage 1", "The focus subset is where real UAV wings are",
              "The full space is what the generator promises to handle; the focus space is where real Class I–II wings sit, and where most runs go (100 wings per type, plus 5 reference wings).",
              '<div class="figwrap">' + fig_ranges() + "</div>" + size_table()
              + '<p class="note">First approach (left, grey): the focus wings at real size and speed. Now (right): the same shapes in mean chords (c̄).</p>',
              "The focus space covers the real wings: most real values sit inside it, and so does the Greek RX-3 family (BWB, AR 8, sweep 33°; LOTUS and Archytas, 8 Nov). The BWB is the extreme shape: a root up to 2.83 mean chords and a tip down to 0.10, up to 17 × smaller. A survey of 202 fixed-wing UAVs (Mitridis et al. 2023) finds the spread inside each NATO class wide (span and cruise speed against weight: R² < 0.2), so a sampled range, not a trend line, is the right description.")

    s3 = step(3, "step-3", "Stage 0 → 1", "Similarity: size and speed become one number, the Re",
              "At low Mach, the shape, the Re and the angle set the flow. So a small slow wing and a large fast wing of the same shape need the same mesh. We build each shape once, at c̄ = 1, and give it the Re.",
              '<div class="figwrap">' + fig_similarity() + '</div><div class="figwrap">' + fig_re() + '</div><div class="figwrap">' + fig_mach() + "</div>"
              + cmp(["each wing at its own size, speed, altitude", "21 meshes per wing, about 42,000 solves",
                     "focus capped at 7 m full span", "Mach 0.03–0.20 from the real speeds"],
                    ["each shape at c̄ = 1; Re 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ as inputs (8 Nov)", "4 meshes per wing, about 8,000 solves",
                     "no size cap: the full span is the aspect ratio", "Mach 0.1 + Prandtl–Glauert; 0.3–0.5 later (pending)"]),
              f"The four Re levels (since 8 Nov: 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶) cover the real wings (1.22 × 10⁵ – 3.10 × 10⁶) and every cruise point of the Greek tactical UAVs (LOTUS, Archytas, ACTUS; AR 8 assumed); LOTUS 11 m at top speed (up to 6.3 × 10⁶) is an extrapolation. 10⁵ sits 18 % below the slowest real wing, as a margin. Inside one wing the local Re spans far more: {fmt_sci(LOCAL_RE['bwb'][0])} at the smallest BWB tip to {fmt_sci(LOCAL_RE['bwb'][1])} at the largest BWB root.")

    s4 = step(4, "step-4", "Stage 1 flow study", "The flow: long laminar runs and bubbles, not fully turbulent",
              "2-D XFOIL strips along each wing (smooth wing, calm air). At our Re the flow stays laminar for a long way, often forms a laminar separation bubble, and turns turbulent late.",
              '<div class="figwrap">' + fig_flow() + "</div>"
              + '<div class="cards3"><div><h3>Bubbles by Re</h3><p>None below 4 × 10⁴ (open separation); long (0.4–0.6 c) at 4 × 10⁴ – 10⁵; almost always (93–99 %) at 1–4 × 10⁵; fading (64 → 26 %) at 5 × 10⁵ – 1.5 × 10⁶; rare above.</p></div>'
              '<div><h3>Angle</h3><p>A higher angle moves transition forward: the upper laminar run is 63 % c at 0° and 26 % c at 10°. At −5° the lower side becomes the suction side. Post-stall goes to a separate study.</p></div>'
              '<div><h3>3-D</h3><p>Two Re regimes on one BWB (root up to 17 × the tip); crossflow on swept panels (the 2-D strips cannot see it); tip vortex and tip stall; kinks at the breaks.</p></div></div>',
              "Fully turbulent SA puts the profile drag far too high: +59 % (median, 20 reference wings × 4 Re levels, 0–10°, tables rebuilt on the fixed nose; +62 % in the first dataset). So transition must be captured (SU2 SST + LM), and the mesh must be fine where transition moves.")

    s5 = step(5, "step-5", "Stage 2", "Surface mesh: each target is met at the level that needs it",
              "Same six steps and the same 13 checks. What changed is where each rule is anchored on the four levels (every spacing ÷ 1.3 per level), three rule values, and the lower band.",
              ladder_html() + '<div class="figwrap">' + fig_bands() + "</div>"
              + cmp(["levels C, M, F, FF; every rule met at C", "band cell = bubble / 20 at C", "lower band 60–100 % c", "station gap 0.2 c at C; last tip gap = s0",
                     "790 of 790 builds pass (first wings)"],
                    ["levels VC, C, M, F; anchors at VC, M and F", "band cell = bubble / 20 at F; 0.5 % c at F from local Re 4 × 10⁵",
                     "lower band 0–100 % c (option A); upper band 0–100 % c (8 Nov)",
                     "station gap 0.25 c at M; last tip gap = 2 × s0; the nose solved at every level; a nose repair on the whole family",
                     "3,128 of 3,128 builds pass: every set at every level, 0 nose repairs"]),
              "The surface mesher did not change, only its rule values. The coarse levels are now coarser (good enough for the SA mesh studies), and F holds the transition targets that SU2 with LM needs.")

    s6 = step(6, "step-6", "Stage 3 plan", "Volume mesh: one matched C-H mesh for both solvers",
              "SU2 has no overset, so the overset wake box and vortex tube cannot serve both solvers. One C-H mesh can: the C rows wrap the nose, the H lines carry the wake to the far field.",
              '<div class="figwrap">' + fig_topology() + "</div>"
              + cmp(["O-H body mesh to about 2 c, background box 0.03 c", "wake box 0.0075 c to 2 c, then to 10 c; vortex tube 15–20 cells across the core",
                     "overlap gate (≥ 5 cells); ADflow only"],
                    ["one matched C-H multiblock mesh; ADflow and SU2 (as unstructured hexes)", "wake lines to the far field (80 c; ladder 40 / 80 / 160): a rough +30–60 % cells",
                     "tip vortex resolved in the outboard blocks; no overlap; wall y⁺ ≤ 1 per Re level, growth 1.25 at VC = 1.107 at F"]),
              "The surface mesh stays the wall of the volume mesh. The cost moves to Stage 3: an open-line march, more wake cells and a tip vortex without its own tube, in exchange for one mesh family and one error bar for both solvers.")

    s7 = step(7, "step-7", "Stages 2 → 3", "The cell budget: the laws we adjusted to keep F near 10 M cells",
              "The first rules met every target at the coarsest level, so the finest level went far past them. The new rules anchor each target at its own level; the lighter bubble table and the wider station gap at M do the rest.",
              laws_table()
              + '<p class="note">Values per level follow the family rule: spacings and angles ÷ 1.3 per finer level, counts × 1.3, growth g^(1/1.3). "First at its finest (FF)" is the first rule carried to its fourth level, the place of F on the ladder.</p>'
              + '<div class="figwrap">' + fig_budget() + '</div><div class="figwrap">' + fig_levels_cells() + "</div>"
              + '<p class="note">The 7–8 Nov count can be redone: layers to 2 chords from the first cell (y⁺ = 1), growth 1.25 at VC; wing blocks only. The 6 Nov estimate (15.2 M and 10.9 M) did not record its wall-layer rule and used the first wings. Stage 3 sets the real wall-layer rule.</p>',
              f"F is {CELLS['F'][0]:.1f} M cells (median; largest {CELLS['F'][1]:.1f} M, at 4 × 10⁶) on the wing blocks, about 9–11 M with the C-H wake lines, inside the target. VC runs on the desktop ({CELLS['VC'][0]:.2f} M median); with +36 GB the desktop also takes C and M (wing blocks only); F needs the HPC.")

    status = ('<section class="step" id="status"><span class="eyebrow">Where we stand · 9 Nov 2026</span><h2>Built, pending, next</h2>'
              '<div class="status"><div><span class="k ok">Built and checked</span><ul><li>Similarity, nose fix, 722 wings rebuilt</li>'
              '<li>New surface rules; every set at every level: 3,128 of 3,128 builds pass, 0 nose repairs</li><li>Section tables rebuilt; refine map at the Re levels</li><li>8 Nov: Re levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ (Greek UAVs in scope; no 5th level); tables to 1.5 × 10⁷</li><li>8 Nov, your machine: pyGeo build 722 of 722; the reference meshes on pyGeo equal the numpy ones (VC and F)</li><li>8 Nov: label tolerance (79): 2 labels; new input hashes, the same surfaces</li><li>8 Nov, your calls built: decision 77 confirmed; upper band 0–100 % c; a nose repair on the whole family (80)</li><li>9 Nov: the band is an option (81): off = 1.8–1.9 × fewer cells at Re ≥ 3 × 10⁵</li></ul></div>'
              '<div><span class="k you">Your calls</span><ul><li>Close Stage 2</li>'
              '<li>Right before the runs: the solver (76) and the band option (81), together</li><li>Stage 0 leftovers</li></ul></div>'
              '<div><span class="k next">Before Stage 3</span><ul><li>One more pyGeo build --all on your machine (new input hashes)</li>'
              '<li>Fix the BWB tip cap for the band off (it fails at M)</li><li>Start the C-H volume mesh on one wing; count its cells</li></ul></div></div></section>')

    head = ('<title>CFD Automation Approach Map</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap">\n'
            f"<style>{CSS}</style>\n")
    intro = ('<header style="display:flex;flex-direction:column;gap:10px"><span class="eyebrow">CFD_Automation · Stages 0–3 · updated 8 Nov 2026</span>'
             '<h1>From a wing shape to a mesh that serves four Re levels</h1>'
             '<p class="lede">The flow of thought after the 4–7 Nov decisions, in seven steps. Wings and airfoil are drawn by the generator itself '
             '(reference wing 0 of each type, at unit mean chord). Click a step to jump to it.</p></header>')
    foot = ('<footer>Sources: the Stage 0 decisions, the Stage 1 Wing Generator page and executive summary, the Stage 2 Surface Mesh page and '
            'executive summary (repo karmix96/aeris, branch <code>stage2-surface-mesh</code>). Built by <code>CFD_Automation/overview/make_approach_map.py</code>.</footer>')
    return head + "<main>" + intro + strip + s1 + s2 + s3 + s4 + s5 + s6 + s7 + status + foot + "</main>\n"


if __name__ == "__main__":
    OUT.write_text(page())
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e3:.0f} kB)")
