"""Build THE final report: everything, in plain language, with diagrams.

    python studies/figures/make_final_report.py

Output: studies/figures/AERIS_lowfi_final_report.html (self-contained).

Reads only tracked evidence under configs/aero/*_evidence/, so it survives a
data/ wipe. Chart helpers are shared with make_figures.py; the schematic diagrams
are hand-drawn SVG defined here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from make_figures import (  # noqa: E402
    CSS, JS, EV_DIS, EV_DOE, EV_VER, details_table, esc, fig_4a, fig_4b,
    fig_claf_cdcl, fig_doe_agreement, fig_elevon_cause, fig_hinge, fig_joint,
    fig_physics, fig_span_margin, hbar_chart, line_chart,
)

EV_ROB = REPO / "configs/aero/discretisation_robustness_evidence"
EV_ADA = REPO / "configs/aero/adaptive_sections_evidence"
OUT = HERE / "AERIS_lowfi_final_report.html"

INK, MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GOOD, CRIT = "#0ca30c", "#d03b3b"


# ------------------------------------------------------------- diagrams -----
def diagram(title, caption, svg_body, width=760, height=250, dia_id="d"):
    return (f'<figure class="fig dia" id="{dia_id}">'
            f'<figcaption><h3>{esc(title)}</h3></figcaption>'
            f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{esc(title)}">{svg_body}</svg>'
            f'<p class="note">{caption}</p></figure>')


def dia_centreline_gap():
    """Why a 2% inset at the root wrecked every number."""
    b = []
    for k, (x0, lab, gap, col) in enumerate([(70, "WRONG — 2% inset", 26, CRIT),
                                             (420, "RIGHT — full span", 0, GOOD)]):
        cx = x0 + 130
        b.append(f'<text class="dlab" x="{cx}" y="34" text-anchor="middle" '
                 f'fill="{col}">{lab}</text>')
        # two half wings, seen from above; centreline dashed
        for s in (-1, 1):
            pts = []
            for (dy, dx) in [(gap, 0), (128, 46), (128, 74), (gap, 30)]:
                pts.append((cx + s * dy, 60 + dx))
            b.append('<polygon points="' +
                     " ".join(f"{px:.0f},{py:.0f}" for px, py in pts) +
                     f'" fill="{col}" fill-opacity="0.16" stroke="{col}" stroke-width="1.6"/>')
        b.append(f'<line x1="{cx}" y1="46" x2="{cx}" y2="150" stroke="{MUTED}" '
                 f'stroke-width="1" stroke-dasharray="4 4"/>')
        b.append(f'<text class="tick" x="{cx}" y="166" text-anchor="middle">'
                 f'centreline</text>')
        if gap:
            b.append(f'<line x1="{cx - gap}" y1="72" x2="{cx + gap}" y2="72" '
                     f'stroke="{CRIT}" stroke-width="2.5"/>')
            b.append(f'<text class="tick" x="{cx}" y="196" text-anchor="middle" '
                     f'fill="{CRIT}">33 mm GAP — AVL sheds a</text>')
            b.append(f'<text class="tick" x="{cx}" y="211" text-anchor="middle" '
                     f'fill="{CRIT}">wingtip vortex pair HERE</text>')
        else:
            b.append(f'<text class="tick" x="{cx}" y="196" text-anchor="middle" '
                     f'fill="{GOOD}">halves meet — one wing</text>')
    return diagram(
        "Diagram 1 — The wing AVL was actually flying",
        "The section extractor started 2 % out from the centreline. AVL mirrors "
        "the half-wing, so that inset became a <strong>33 mm slot down the middle "
        "of the aircraft</strong>. AVL treated each half as a separate wing and "
        "shed tip vortices into the gap. Cost: lift understated <strong>55 %</strong>, "
        "lift-curve slope <strong>26 %</strong>, L/D halved. Fix: start at the "
        "centreline. <em>Every low-fidelity number produced before 25 July 2026 is "
        "invalid.</em>", "".join(b), dia_id="dia1")


def dia_nflap():
    """What sets the elevon's chordwise error."""
    b = []
    import math
    for k, (x0, n, lab, col) in enumerate([(60, 8, "8 panels — only 2 on the flap", CRIT),
                                           (410, 24, "24 panels — 6 on the flap", GOOD)]):
        w = 290
        b.append(f'<text class="dlab" x="{x0 + w/2}" y="34" text-anchor="middle" '
                 f'fill="{col}">{lab}</text>')
        # airfoil-ish outline
        b.append(f'<path d="M{x0},110 Q{x0+w*0.3},68 {x0+w*0.62},92 '
                 f'Q{x0+w*0.85},108 {x0+w},116 Q{x0+w*0.6},128 {x0},110 Z" '
                 f'fill="{MUTED}" fill-opacity="0.13" stroke="{MUTED}" stroke-width="1.3"/>')
        edges = [0.5 * (1 - math.cos(math.pi * i / n)) for i in range(n + 1)]
        for e in edges:
            x = x0 + w * e
            on = e > 0.75 - 1e-9
            b.append(f'<line x1="{x:.1f}" y1="78" x2="{x:.1f}" y2="132" '
                     f'stroke="{col if on else GRID}" stroke-width="{1.6 if on else 1}"/>')
        hx = x0 + w * 0.75
        b.append(f'<line x1="{hx:.1f}" y1="62" x2="{hx:.1f}" y2="146" stroke="{INK}" '
                 f'stroke-width="2"/>')
        b.append(f'<circle cx="{hx:.1f}" cy="104" r="4" fill="{INK}"/>')
        b.append(f'<text class="tick" x="{hx:.1f}" y="56" text-anchor="middle">hinge</text>')
        b.append(f'<text class="tick" x="{x0+w*0.87:.0f}" y="164" text-anchor="middle" '
                 f'fill="{col}">the elevon</text>')
        nf = sum(1 for e in edges if e > 0.75 - 1e-9) - 1
        b.append(f'<text class="dlab" x="{x0+w/2}" y="196" text-anchor="middle" '
                 f'fill="{col}">N_flap = {nf}   →   error '
                 f'{"8.7 %" if n == 8 else "1.8 %"}</text>')
    return diagram(
        "Diagram 2 — Why the elevon needed more chordwise panels",
        "Side view of one section. AVL divides the chord into panels; only the "
        "panels <strong>behind the hinge</strong> represent the moving elevon. "
        "With 8 panels, just 2 land on the flap — AVL is describing the control "
        "surface with 2 boxes. With 24, six do. Measured law: "
        "<strong>error ~ N_flap<sup>−1.47</sup></strong> (R² 0.966). "
        "<em>We first blamed the hinge landing between panel edges. A hinge sweep "
        "disproved that — it is the panel COUNT on the flap, not their alignment.</em>",
        "".join(b), dia_id="dia2")


def dia_ramp():
    """What sets the elevon's spanwise error."""
    b = []
    y0 = 96
    for k, (x0, s, e, lab, col) in enumerate(
            [(60, 0.30, 0.85, "wide band — ramps are a small share", GOOD),
             (410, 0.52, 0.68, "narrow band — ramps DOMINATE", CRIT)]):
        w = 290
        b.append(f'<text class="dlab" x="{x0+w/2}" y="34" text-anchor="middle" '
                 f'fill="{col}">{lab}</text>')
        b.append(f'<line x1="{x0}" y1="{y0+52}" x2="{x0+w}" y2="{y0+52}" '
                 f'stroke="{MUTED}" stroke-width="1.2"/>')
        b.append(f'<text class="tick" x="{x0}" y="{y0+70}">root</text>')
        b.append(f'<text class="tick" x="{x0+w}" y="{y0+70}" text-anchor="end">tip</text>')
        ramp = 0.075
        pts = [(0, 0), (s - ramp, 0), (s, 1), (e, 1), (e + ramp, 0), (1, 0)]
        d = " ".join(f"{'M' if i == 0 else 'L'}{x0 + w*px:.1f},{y0+52 - 46*py:.1f}"
                     for i, (px, py) in enumerate(pts))
        b.append(f'<path d="{d}" fill="{col}" fill-opacity="0.18" stroke="{col}" '
                 f'stroke-width="2"/>')
        for px in (s, e):
            b.append(f'<line x1="{x0+w*px:.1f}" y1="{y0-2}" x2="{x0+w*px:.1f}" '
                     f'y2="{y0+58}" stroke="{INK}" stroke-width="1.4" '
                     f'stroke-dasharray="3 3"/>')
        for px in (s - ramp, e + ramp):
            b.append(f'<line x1="{x0+w*px:.1f}" y1="{y0+40}" x2="{x0+w*px:.1f}" '
                     f'y2="{y0+58}" stroke="{col}" stroke-width="1.2"/>')
        b.append(f'<text class="tick" x="{x0+w*(s+e)/2:.0f}" y="{y0+22}" '
                 f'text-anchor="middle">elevon ON</text>')
        frac = 2 * ramp / (e - s)
        b.append(f'<text class="dlab" x="{x0+w/2}" y="{y0+96}" text-anchor="middle" '
                 f'fill="{col}">ramp share {frac:.0%}  →  error '
                 f'{"0.1–0.5 %" if k == 0 else "4.3 %"}</text>')
    return diagram(
        "Diagram 3 — Why a SHORT elevon was the one case that failed",
        "Looking along the span. AVL cannot switch a control on instantly — it "
        "<strong>ramps</strong> the deflection from full to zero across the gap to "
        "the next section. Those ramps are a fixed width set by the section "
        "spacing. On a long elevon they are a small share of it; on a short one "
        "they swamp it. Measured: <strong>error grows with ramp-width ÷ band-width"
        "</strong> (correlation +0.978). Keep that share under ~15 %.",
        "".join(b), dia_id="dia3")


def dia_two_questions():
    b = []
    b.append(f'<text class="dlab" x="380" y="30" text-anchor="middle">'
             f'The old study asked ONE question. There are TWO.</text>')
    cols = [(80, "SECTIONS", "slices of the real shape\nhanded to AVL", BLUE, 6),
            (400, "PANELS", "the calculation grid\nAVL builds on that shape", ORANGE, 6)]
    for x0, name, sub, col, n in cols:
        b.append(f'<text class="dlab" x="{x0+130}" y="66" text-anchor="middle" '
                 f'fill="{col}">{name}</text>')
        for i, ln in enumerate(sub.split("\n")):
            b.append(f'<text class="tick" x="{x0+130}" y="{84+i*15}" '
                     f'text-anchor="middle">{ln}</text>')
        pts = [(x0, 130), (x0 + 210, 148), (x0 + 210, 190), (x0, 205)]
        b.append('<polygon points="' + " ".join(f"{a},{c}" for a, c in pts) +
                 f'" fill="{col}" fill-opacity="0.10" stroke="{col}" stroke-width="1.5"/>')
        if name == "SECTIONS":
            for i in range(n):
                t = i / (n - 1)
                b.append(f'<line x1="{x0+210*t:.0f}" y1="{130+18*t:.0f}" '
                         f'x2="{x0+210*t:.0f}" y2="{205-15*t:.0f}" stroke="{col}" '
                         f'stroke-width="2"/>')
        else:
            for i in range(n * 3):
                t = i / (n * 3 - 1)
                b.append(f'<line x1="{x0+210*t:.0f}" y1="{130+18*t:.0f}" '
                         f'x2="{x0+210*t:.0f}" y2="{205-15*t:.0f}" stroke="{col}" '
                         f'stroke-width="0.8"/>')
            for j in range(1, 4):
                yy = 130 + (205 - 130) * j / 4
                b.append(f'<line x1="{x0}" y1="{yy:.0f}" x2="{x0+210}" '
                         f'y2="{yy+12:.0f}" stroke="{col}" stroke-width="0.8"/>')
    b.append(f'<text class="tick" x="380" y="234" text-anchor="middle" fill="{CRIT}">'
             f'Adding a SECTION also added PANELS, so the old curve mixed both effects.</text>')
    return diagram(
        "Diagram 4 — The two questions the old study could not separate",
        "In our writer, <code>panels = (sections − 1) × panels_per_gap</code>. So "
        "every time the old study added a section it also refined the calculation "
        "grid, and its convergence curve was two effects added together. We pinned "
        "the panel count and varied sections alone, then the reverse. "
        "<strong>The result: the section count was never the problem. The chordwise "
        "grid was, and it had been set three times too coarse from the start.</strong>",
        "".join(b), dia_id="dia4")


def dia_metric():
    b = []
    ch = [("sweep", BLUE), ("taper", ORANGE), ("twist", AQUA),
          ("dihedral", YELLOW), ("thickness", BLUE), ("elevon on/off", CRIT)]
    b.append(f'<text class="dlab" x="118" y="28" text-anchor="middle">'
             f'1. measure what changes</text>')
    for i, (nm, col) in enumerate(ch):
        y = 52 + i * 29
        b.append(f'<rect x="24" y="{y-14}" width="188" height="23" rx="5" '
                 f'fill="{col}" fill-opacity="0.13" stroke="{col}" stroke-width="1"/>')
        b.append(f'<text class="tick" x="36" y="{y+2}">{nm}</text>')
        b.append(f'<path d="M212,{y-3} L246,{y-3}" stroke="{MUTED}" stroke-width="1"/>')
    b.append(f'<text class="dlab" x="376" y="28" text-anchor="middle">'
             f'2. where does it BEND?</text>')
    b.append(f'<rect x="262" y="40" width="228" height="150" rx="7" fill="none" '
             f'stroke="{GRID}"/>')
    import math
    pts = []
    for i in range(120):
        t = i / 119
        v = (0.16 + 0.9 * math.exp(-((t - 0.34) / 0.05) ** 2)
             + 1.5 * math.exp(-((t - 0.62) / 0.022) ** 2)
             + 1.5 * math.exp(-((t - 0.92) / 0.022) ** 2))
        pts.append((262 + 228 * t, 182 - 52 * min(v, 1.7) / 1.7))
    b.append('<path d="' + " ".join(f"{'M' if i==0 else 'L'}{x:.1f},{y:.1f}"
                                    for i, (x, y) in enumerate(pts)) +
             f'" fill="none" stroke="{INK}" stroke-width="2"/>')
    b.append(f'<text class="tick" x="376" y="200" text-anchor="middle">'
             f'"information density" along the span</text>')
    b.append(f'<text class="dlab" x="640" y="28" text-anchor="middle">'
             f'3. put sections there</text>')
    b.append(f'<line x1="530" y1="120" x2="740" y2="120" stroke="{MUTED}" stroke-width="1.2"/>')
    for t in (0.0, 0.16, 0.30, 0.34, 0.40, 0.52, 0.60, 0.62, 0.66, 0.78,
              0.90, 0.92, 0.95, 1.0):
        x = 530 + 210 * t
        b.append(f'<line x1="{x:.1f}" y1="104" x2="{x:.1f}" y2="136" '
                 f'stroke="{BLUE}" stroke-width="2"/>')
    b.append(f'<text class="tick" x="640" y="158" text-anchor="middle">'
             f'clustered where the wing changes</text>')
    b.append(f'<text class="tick" x="640" y="176" text-anchor="middle" fill="{CRIT}">'
             f'…and this is what went wrong</text>')
    return diagram(
        "Diagram 5 — What the &ldquo;geometric information&rdquo; metric does",
        "AVL joins neighbouring sections with <strong>straight lines</strong>. So "
        "error appears wherever the real wing <em>bends</em> — at a sweep kink, a "
        "taper break, where the airfoil changes, and at the two ends of the "
        "elevon. The metric measures how sharply each of those seven properties "
        "bends along the span, adds them up into an &ldquo;information density&rdquo;, "
        "and places sections thickly where it is high. The elevon on/off switch is "
        "just one more property — which is why the method finds the control edges "
        "on its own.", "".join(b), width=760, height=224, dia_id="dia5")


def dia_criterion():
    b = [f'<text class="dlab" x="380" y="32" text-anchor="middle">'
         f'One rule covers both. Check it before you run anything.</text>']
    boxes = [(60, "CHORDWISE", "N_flap ≥ 6", "panels behind the hinge", BLUE),
             (410, "SPANWISE", "ramp share ≤ 15 %", "ramp width ÷ elevon length", ORANGE)]
    for x0, t1, rule, sub, col in boxes:
        b.append(f'<rect x="{x0}" y="56" width="290" height="112" rx="9" '
                 f'fill="{col}" fill-opacity="0.09" stroke="{col}" stroke-width="1.6"/>')
        b.append(f'<text class="tick" x="{x0+145}" y="82" text-anchor="middle" '
                 f'fill="{col}">{t1}</text>')
        b.append(f'<text class="big" x="{x0+145}" y="118" text-anchor="middle">{rule}</text>')
        b.append(f'<text class="tick" x="{x0+145}" y="144" text-anchor="middle">{sub}</text>')
    b.append(f'<text class="tick" x="380" y="196" text-anchor="middle">'
             f'Both say the same thing: it is the CONTROL SURFACE that has to be '
             f'resolved, not the wing.</text>')
    return diagram(
        "Diagram 6 — The single idea the whole campaign converged on",
        "Every large error we found in the low-fidelity model came from the same "
        "place: AVL smooths a control surface at its edges — at the hinge going "
        "along the chord, and at the two ends going along the span. How much that "
        "smoothing matters depends on how big it is <em>compared with the control "
        "itself</em>. Both numbers can be worked out from the geometry alone, "
        "before any calculation is run.", "".join(b), height=214, dia_id="dia6")


# --------------------------------------------------------------- figures ----
def fig_extremes():
    d = json.loads((EV_ROB / "extremes.json").read_text())
    order = ["benign", "min_ar", "max_ar", "max_gradient", "max_dihedral",
             "hinge_min", "hinge_max", "elevon_wide", "elevon_narrow"]
    nice = {"benign": "simple wing", "min_ar": "stubbiest (AR 2.3)",
            "max_ar": "slenderest (AR 7.9)", "max_gradient": "sharpest shape change",
            "max_dihedral": "most dihedral", "hinge_min": "hinge far forward",
            "hinge_max": "hinge far aft", "elevon_wide": "longest elevon",
            "elevon_narrow": "SHORTEST elevon"}
    rows = []
    for k in order:
        e = d.get(k, {})
        er = e.get("err_prod", {})
        if er:
            rows.append((nice[k], max(er.values()) * 100, None))
    return hbar_chart(
        rows=rows, chart_id="fex", max_val=5.0,
        colorize=lambda v: ("bar crit" if v > 2 else "bar warn" if v > 1 else "bar good"),
        title="Fig E — We built nine deliberately awkward wings. Eight were fine.",
        subtitle="Worst error of the recommended settings on each, against a much "
                 "finer calculation. Green = under 1 %.",
        note="Random sampling cannot test the corners of a 19-variable design space "
             "— the chance of landing in one is about 5 in 100 trillion. So these "
             "were <strong>built by hand</strong>. Shape extremes turned out not to "
             "matter at all: the slenderest and stubbiest wings, the sharpest sweep "
             "and twist changes, the most dihedral, and both hinge positions all "
             "come in under 0.5 %. <strong>Only the elevon LENGTH mattered</strong> "
             "— and the shortest one failed at 4.3 %.")


def fig_alpha():
    p = REPO / "configs/aero/discretisation_robustness_evidence/alpha_sweep.txt"
    lines = [ln.split() for ln in p.read_text().splitlines() if ln.strip()
             and ln.split()[0].replace(".", "").replace("-", "").isdigit()]
    a = [float(r[0]) for r in lines]
    worst = [float(r[-1].rstrip("%")) for r in lines]
    clde = [float(r[-2].rstrip("%")) for r in lines]
    cl = [float(r[1]) for r in lines]
    tbl = [["alpha (deg)", "CL", "clamped strips", "worst error"]]
    for r in lines:
        tbl.append([r[0], r[1], r[2], r[-1]])
    return line_chart(
        series=[{"name": "worst of all", "values": worst, "fmt": "{:.2f}%"},
                {"name": "elevon CL_δe", "values": clde, "fmt": "{:.2f}%"}],
        x_labels=[f"{x:g}" for x in a], chart_id="falpha", y_log=False,
        title="Fig F — The settings hold across the whole flight range",
        subtitle="Error of the recommended settings vs a finer calculation, at "
                 "angles of attack from 0° to 14° (lift coefficient −0.04 to 0.91).",
        y_label="angle of attack (degrees)",
        note="Flat and small everywhere. The 1.2 % at 0° is not a real problem — "
             "the wing makes almost no lift there, so a tiny absolute difference "
             "looks large as a percentage. <strong>What this DID find:</strong> at "
             "14° the viscous model ran out of data on 40 strips (the 2-D airfoil "
             "data does not reach that lift). So trust the drag up to about 10°, "
             "not beyond.",
        table_rows=tbl)


def fig_adaptive():
    d = json.loads((EV_ADA / "gradation.json").read_text())
    nice = {"benign": "simple wing", "elevon_narrow": "SHORT elevon (the hard case)",
            "max_gradient": "sharpest shape change"}
    rows = []
    for k, v in d.items():
        rows.append((nice.get(k, k), v["err_u"] * 100, v["err_a"] * 100))
    L = ['<figure class="fig" id="fada">',
         '<figcaption><h3>Fig G — Smart section placement: helps where it is '
         'needed, not everywhere</h3>'
         '<p>Same number of sections in both cases (25). Lower is better.</p>'
         '</figcaption>',
         '<svg viewBox="0 0 760 210" role="img" aria-label="adaptive placement">']
    mx = 1.4
    for i, (lab, u, a) in enumerate(rows):
        y = 34 + i * 56
        L.append(f'<text class="rowlab" x="250" y="{y+14}" text-anchor="end">{esc(lab)}</text>')
        for j, (v, col, nm) in enumerate([(u, MUTED, "evenly spaced"),
                                          (a, GOOD if a < u else CRIT, "smart placement")]):
            yy = y + j * 21
            w = max(4, 380 * v / mx)
            L.append(f'<rect x="266" y="{yy}" width="{w:.0f}" height="16" rx="4" '
                     f'fill="{col}" fill-opacity="{0.35 if j==0 else 1}" '
                     f'tabindex="0" data-t="{esc(nm)}: {v:.2f}% error"/>')
            L.append(f'<text class="val" x="{266+w+9:.0f}" y="{yy+12}">{v:.2f}%</text>')
            L.append(f'<text class="tick" x="{266+w+58:.0f}" y="{yy+12}">{nm}</text>')
    L.append("</svg>")
    L.append('<p class="note">On the wing it was designed for — the short elevon — '
             'smart placement is <strong>2.8× more accurate for free</strong>. On an '
             'ordinary wing it makes no difference, and on one case it is slightly '
             'worse. So we switch it on only when the ramp-share rule says the even '
             'spacing is not good enough. <strong>Our first attempt at this was '
             '10× WORSE than even spacing</strong> — it crowded sections onto the '
             'interesting bits and left an 18 %-of-span hole everywhere else.</p>')
    L.append("</figure>")
    return "\n".join(L)


# ------------------------------------------------------------------ page ----
EXTRA_CSS = """
.dia svg { background:transparent; }
.dlab { font-size:13px; font-weight:600; fill:#0b0b0b; }
.big { font-size:21px; font-weight:650; fill:#0b0b0b; }
.lead { font-size:16.5px; line-height:1.6; }
.settings { background:#fcfcfb; border:1px solid rgba(11,11,11,.10);
  border-left:3px solid #0ca30c; border-radius:10px; padding:14px 18px; margin:14px 0 24px; }
.settings h4 { margin:0 0 8px; font-size:14px; }
.settings code { font-size:12.5px; }
.q { background:#fcfcfb; border:1px solid rgba(11,11,11,.10); border-radius:10px;
  padding:16px 20px; margin:0 0 16px; }
.q h3 { margin:0 0 6px; }
.qa { color:#52514e; font-size:14px; }
.bad { color:#d03b3b; font-weight:600; }
.okk { color:#0ca30c; font-weight:600; }
ul.tight { margin:8px 0 0; padding-left:20px; }
ul.tight li { margin:5px 0; }
.chk td:first-child { width:34px; }
@media (prefers-color-scheme: dark) {
 :root:where(:not([data-theme="light"])) .dlab,
 :root:where(:not([data-theme="light"])) .big { fill:#fff; }
 :root:where(:not([data-theme="light"])) .settings,
 :root:where(:not([data-theme="light"])) .q { background:#1a1a19;
   border-color:rgba(255,255,255,.10); }
 :root:where(:not([data-theme="light"])) .qa { color:#c3c2b7; }
}
"""


def settings(title, rows, why=None):
    tr = "".join(f"<tr><td><code>{esc(k)}</code></td><td><strong>{esc(v)}</strong></td>"
                 f"<td>{w}</td></tr>" for k, v, w in rows)
    return (f'<div class="settings"><h4>✔ {esc(title)}</h4>'
            f'<div class="scroll"><table><tbody>{tr}</tbody></table></div>'
            + (f'<p class="note" style="margin-bottom:0">{why}</p>' if why else "")
            + '</div>')


def main() -> None:
    body = f"""<div class="wrap">
<h1>The low-speed aerodynamics model: what we checked, what we found, what we use</h1>
<p class="sub">AERIS · BWB ISR UAV · everything from July 2026, in plain language</p>

<p class="lead">We use a fast aerodynamics program called <strong>AVL</strong> to
estimate lift, drag and handling for thousands of candidate wings. It is fast
because it makes simplifications. This report is the record of us checking, one
by one, whether those simplifications are being fed the right wing — and whether
the answers can be trusted. We found four real bugs, discarded one of our own
explanations, and ended with a single rule that predicts the model's accuracy
before you run it.</p>

<h2><span class="num">A</span>The settings — start here</h2>
{settings("Use these. They are already the defaults in the code — you do not need to pass anything.", [
  ("n_sections", "25", "slices of the wing shape given to AVL"),
  ("span_margin", "0.0", "start at the centreline, not inset — see Study 1"),
  ("spanwise_panels_per_section", "4", "calculation strips between slices"),
  ("nchordwise", "24", "panels along the chord — was 8, see Study 5"),
  ("cspace", "1.0 (cosine)", "panels bunched near the leading edge"),
  ("adaptive placement", "only if ramp share > 15 %", "see Study 7"),
], why="Cost: 192 strips, 4 608 vortices — comfortably inside AVL's own limits. "
       "<strong>Two hard ceilings you cannot cross:</strong> "
       "<code>(sections − 1) × spanwise ≤ 250</code> and "
       "<code>strips × nchordwise ≲ 6000</code>. Going finer than this fails outright. "
       "If you do not care about elevon effectiveness, <code>nchordwise = 16</code> "
       "is a cheaper setting that is just as good for lift and drag.")}

<h2><span class="num">B</span>The one idea everything led to</h2>
{dia_criterion()}

<h2><span class="num">1</span>Study 1 — Is AVL even flying the right wing?</h2>
<p class="lead">This is where we started, and it immediately found the worst bug
of the whole project.</p>
{dia_centreline_gap()}
{fig_span_margin()}
{settings("From Study 1", [
  ("span_margin", "0.0", "extract sections over the full span, centreline to tip"),
  ("elevon extent", "sections snapped to the elevon ends", "so the control is the size the design says"),
], why="We also made the model report <em>everything</em> AVL can produce — "
       "efficiency, neutral point, all 43 stability derivatives, control power, "
       "hinge loads, and the load distribution for the structures team. Before "
       "this it reported nine numbers.")}

<h2><span class="num">2</span>Study 2 — Does AVL know what airfoil it is flying?</h2>
<p class="lead">AVL by itself has no idea about airfoil drag or thickness. We feed
it two corrections. The question was whether they were actually arriving — and
this had silently broken once before.</p>
{fig_claf_cdcl()}
{settings("From Study 2", [
  ("viscous drag (CDCL)", "on, per section", "a separate airfoil drag curve for every slice, at that slice's own speed/size"),
  ("thickness lift (CLAF)", "on, per section", "thicker airfoils lift slightly harder"),
  ("drag reported", "strip integration", "not AVL's internal number — ours is more accurate by 4.3 %"),
], why="<strong>The standard we adopted:</strong> it is not enough to see the "
       "correction written in the file. We switch it off and check the answer moves "
       "by the amount theory predicts. For thickness, theory says the wing-level "
       "effect should be 1.064× — we measured 1.058×.")}

<h2><span class="num">3</span>Study 3 — Is our new solver the same as the old one?</h2>
<p class="lead">We wrote our own AVL interface. Before trusting it we compared it
against the old AeroSandbox-based one on 30 different wings.</p>
{fig_doe_agreement()}
{fig_elevon_cause()}
{settings("From Study 3", [
  ("production solver", "our native path", "the old one CANNOT deflect an elevon asymmetrically at all"),
  ("old solver", "kept as a cross-check", "for symmetric, undeflected cases only"),
], why="The old path collapses every control surface into one variable, so roll "
       "commands were being <strong>silently ignored</strong>. Since the design "
       "study varies three elevon variables specifically to tune roll control, that "
       "ruled it out. We also found its elevon is about 6 % too big — consistently, "
       "on all 30 wings.")}

<h2><span class="num">4</span>Study 4 — Is our code right, not just consistent?</h2>
<p class="lead">Two programs agreeing proves nothing if they share the same
mistake — and ours share code and share their input. So we tested against wings
whose answers are known from textbook theory.</p>
{fig_physics()}
{settings("From Study 4", [
  ("verification standard", "three independent legs", "textbook answers, sign checks, and switch-it-off tests"),
], why="The elliptic wing is the strongest one: theory says its efficiency is "
       "exactly 1.0 and we got 0.9975. That single number can only come out right "
       "if the shape, the span, the areas and AVL's wake calculation are all correct "
       "at once. We also confirmed that twist, sweep and dihedral push the answers "
       "in the right direction — checks that comparing two programs can never make, "
       "because both read the same twist number.")}

<h2><span class="num">5</span>Study 5 — How fine does the grid need to be?</h2>
<p class="lead">This is the study that produced the settings. The key move was
realising there are <em>two</em> separate questions here, not one.</p>
{dia_two_questions()}
{fig_4a()}
{fig_4b()}
{dia_nflap()}
{fig_hinge()}
{fig_joint()}
{settings("From Study 5", [
  ("n_sections", "25", "≤0.6 % on lift, drag and all handling numbers"),
  ("spanwise_panels_per_section", "4", "≤0.54 %"),
  ("nchordwise", "24 (was 8)", "elevon power: 7.7 % error → about 1.1 %"),
  ("cspace", "cosine, not uniform", "uniform helps the elevon but ruins the neutral point"),
], why="<strong>Two traps worth remembering.</strong> First, the wing's <em>shape</em> "
       "numbers (area, mean chord) settle about three times sooner than the "
       "aerodynamics — so never use 'the area has converged' as proof. Second, "
       "elevon power does <em>not</em> improve smoothly as you add sections: 13 "
       "sections beat 17 and 25. That is not noise, and Study 7 explains it.")}

<h2><span class="num">6</span>Study 6 — Does it still hold for weird wings?</h2>
<p class="lead">Everything above was measured on ordinary, randomly-drawn wings.
A design study will produce extreme ones. So we built the extremes on purpose.</p>
{fig_extremes()}
{dia_ramp()}
{fig_alpha()}
{settings("From Study 6", [
  ("shape extremes", "no action needed", "AR 2.3 to 7.9, extreme sweep/twist/dihedral all fine"),
  ("short elevons", "watch the ramp share", "if > 15 %, use smart placement (Study 7)"),
  ("angle of attack", "trust drag to about 10°", "beyond that the airfoil data runs out"),
], why="This is also where we discovered our own published explanation was wrong. "
       "We had blamed the elevon error on the hinge landing between panel edges. "
       "Sweeping the hinge across its full range disproved it — the wing with "
       "<em>perfect</em> alignment was not the most accurate. The real cause is "
       "simply how many panels sit on the flap.")}

<h2><span class="num">7</span>Study 7 — Can we place the sections more cleverly?</h2>
<p class="lead">Study 5 showed that <em>where</em> the sections go matters more
than how many there are. So we tried to compute the best places automatically.
This is the part that did not work as hoped.</p>
{dia_metric()}
{fig_adaptive()}
{settings("From Study 7", [
  ("default", "evenly spaced sections", "with sections pinned to the elevon ends"),
  ("smart placement", "only if ramp share > 15 %", "2.8× better on a short elevon, no help otherwise"),
  ("the 'concentration' score", "do not use", "it predicts difficulty BACKWARDS"),
], why="<strong>What the metric is, in one sentence:</strong> AVL joins sections "
       "with straight lines, so we measure how sharply the wing bends along its "
       "span — sweep, taper, twist, dihedral, thickness, camber, and whether the "
       "elevon is on — and put sections where the bending is. <strong>What went "
       "wrong:</strong> done purely, it crowds sections onto the interesting parts "
       "and leaves big holes elsewhere; it was up to 10× worse than even spacing. "
       "Damping it down fixed that and left a real 2.8× gain on exactly the wing "
       "that needed it.")}

<h2><span class="num">C</span>The four bugs we found</h2>
<div class="q">
<table><tbody>
<tr><td><span class="bad">1</span></td><td><strong>The centreline gap.</strong>
Sections started 2 % out, so AVL flew two half-wings with a 33 mm slot between
them. Lift was 55 % low. <em>Every number produced before we found it was wrong.</em></td></tr>
<tr><td><span class="bad">2</span></td><td><strong>The elevon stopped short.</strong>
The control did not extend to the end of the band it was supposed to cover.
Elevon power was 17 % low.</td></tr>
<tr><td><span class="bad">3</span></td><td><strong>Three design variables never
arrived.</strong> The elevon's start, end and hinge are supposed to vary from
wing to wing. They were being generated and then thrown away — every single run
used the same elevon. Invisible to every check we had, because both solvers saw
the same wrong elevon and therefore still agreed with each other.</td></tr>
<tr><td><span class="bad">4</span></td><td><strong>The chordwise grid was three
times too coarse</strong> — set at 8 since the beginning, needed 24. Only visible
once we separated the two convergence questions.</td></tr>
</tbody></table>
</div>

<h2><span class="num">D</span>Things we got wrong and corrected</h2>
<div class="q">
<p class="qa">A committee will trust the work more if we volunteer these.</p>
<ul class="tight">
<li><strong>We blamed the hinge/panel-edge alignment</strong> for the elevon error
and published it. A hinge sweep disproved it. The real cause is the number of
panels on the flap. <em>Lesson: our supporting correlation was pooled across
grid levels, which confounded it.</em></li>
<li><strong>We said the residual between solvers was airfoil resolution.</strong>
It was not — matching the resolution changed nothing. It was entirely the
oversized elevon in the old path.</li>
<li><strong>We logged the speed derivatives as an unexplained problem.</strong>
They were not a problem at all — just a small number divided by an even smaller
one.</li>
<li><strong>We claimed all 19 design variables were exercised.</strong> It was 16;
bug 3 above meant the three elevon ones were not.</li>
</ul>
</div>

<h2><span class="num">E</span>What we did NOT do</h2>
<div class="q">
<ul class="tight">
<li><strong>No comparison with wind tunnel or CFD.</strong> Everything here checks
that the code does what we intend. Whether that matches reality has to come from
the high-fidelity ADflow work. This is the biggest single gap.</li>
<li><strong>Above about 10° angle of attack the drag is not trustworthy</strong> —
the 2-D airfoil data runs out and the model starts guessing (40 strips at 14°).</li>
<li><strong>Splitting the surface at the hinge</strong> is the textbook way to
model a flap exactly. We did not try it; it would probably let us drop back below
24 chordwise panels.</li>
<li><strong>Choosing the number of sections automatically</strong> — the metric
places a fixed budget, it does not yet decide the budget.</li>
<li><strong>Spanwise vs chordwise at equal cost.</strong> We tried, but the test
was flawed and we threw the result out rather than quote it.</li>
<li><strong>One aircraft, one speed, one airfoil set</strong> (mh91 / e374 /
nlf1015). Conclusions are for this design space.</li>
<li><strong>A 0.13 % mismatch</strong> in how the two solvers define mean chord.
Harmless, still unresolved.</li>
</ul>
</div>

<h2><span class="num">F</span>Did we miss anything? — the checklist</h2>
<div class="q">
<div class="scroll"><table class="chk"><tbody>
<tr><td><span class="okk">✔</span></td><td>Geometry reaches the solver correctly</td><td class="qa">Study 1</td></tr>
<tr><td><span class="okk">✔</span></td><td>Airfoil drag and thickness corrections active</td><td class="qa">Study 2, by switch-off test</td></tr>
<tr><td><span class="okk">✔</span></td><td>Agrees with the previous solver</td><td class="qa">Study 3, 30 wings</td></tr>
<tr><td><span class="okk">✔</span></td><td>Agrees with textbook theory</td><td class="qa">Study 4, 11/11 checks</td></tr>
<tr><td><span class="okk">✔</span></td><td>Sign conventions (twist, sweep, dihedral)</td><td class="qa">Study 4 — impossible via solver comparison</td></tr>
<tr><td><span class="okk">✔</span></td><td>Enough sections</td><td class="qa">Study 5, panel count held fixed</td></tr>
<tr><td><span class="okk">✔</span></td><td>Enough panels, spanwise and chordwise separately</td><td class="qa">Study 5</td></tr>
<tr><td><span class="okk">✔</span></td><td>Holds for extreme shapes</td><td class="qa">Study 6, 9 built by hand</td></tr>
<tr><td><span class="okk">✔</span></td><td>Holds across angle of attack</td><td class="qa">Study 6, 0°–14°</td></tr>
<tr><td><span class="okk">✔</span></td><td>Holds in sideslip</td><td class="qa">12 wings, all lateral derivatives ≤1.9 %</td></tr>
<tr><td><span class="okk">✔</span></td><td>Enough wings sampled</td><td class="qa">30 used; 10–15 would have sufficed</td></tr>
<tr><td><span class="okk">✔</span></td><td>Agrees with the earlier independent study</td><td class="qa">Exactly, on sections and spanwise panels</td></tr>
<tr><td><span class="bad">✗</span></td><td>Checked against wind tunnel or CFD</td><td class="qa">Not done — the main gap</td></tr>
<tr><td><span class="bad">✗</span></td><td>Valid near stall</td><td class="qa">Not above ~10°</td></tr>
<tr><td><span class="bad">✗</span></td><td>Automatic section budget</td><td class="qa">Not delivered</td></tr>
</tbody></table></div>
</div>

<h2><span class="num">G</span>Agreement with your earlier study</h2>
<div class="q">
<p class="qa">An earlier, independent study — different code, bigger aircraft, no
control surfaces — recommended <strong>25 sections and 4 spanwise panels</strong>.
We got exactly the same, from a completely different method. That is real
cross-validation.</p>
<p class="qa">The only difference is chordwise: it said 8, we say 24. That is not
a contradiction — <strong>that study's wing had no elevon</strong>, so elevon
power never appeared in it. On everything it did measure, 8 is fine and we agree.
The whole increase is bought for control authority.</p>
</div>

<p class="note" style="margin-top:34px">Full technical detail, with every number
and every caveat, is in <code>studies/discretisation_master_study.md</code> and
the decision records <code>decision/0005</code>–<code>0011</code>. All evidence is
tracked under <code>configs/aero/*_evidence/</code> and every figure here
regenerates from it.</p>
</div>"""

    html = (f"<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>AERIS — low-speed aerodynamics: final report</title>"
            f"<style>{CSS}{EXTRA_CSS}</style></head><body>{body}"
            f"<script>{JS}</script></body></html>")
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({len(html)/1024:.0f} kB)")


if __name__ == "__main__":
    main()
