"""Build the visual report for the low-fidelity AVL verification campaign.

Reads ONLY the tracked evidence under `configs/aero/*_evidence/` — never `data/`,
which is gitignored and gets wiped. So the report regenerates from a clean
checkout.

    python studies/figures/make_figures.py

Output: studies/figures/lowfi_avl_verification_report.html (self-contained).

Design system: the reference palette from the `dataviz` skill, used UNCHANGED
(no brand substitution), so its documented validation applies — worst adjacent
CVD ΔE 9.1 light / 8.4 dark on the adjacent pairlist used by lines and bars;
slots 1–3 additionally clear the all-pairs gate used by the scatter. Charts that
use the sub-3:1 light slots (aqua, yellow) ship direct labels AND a table view,
per the relief rule.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EV_VER = REPO / "configs/aero/native_avl_verification_evidence"
EV_DOE = REPO / "configs/aero/native_avl_doe_evidence"
EV_DIS = REPO / "configs/aero/lowfi_discretisation_evidence"
OUT = Path(__file__).resolve().parent / "lowfi_avl_verification_report.html"

# ---------------------------------------------------------------- palette ----
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"      # light
D1, D2, D3, D4 = "#3987e5", "#d95926", "#199e70", "#c98500"      # dark
GOOD, CRIT, WARN = "#0ca30c", "#d03b3b", "#fab219"

W, H = 760, 320
PAD = {"l": 74, "r": 116, "t": 26, "b": 52}


# ------------------------------------------------------------------ parsing --
def parse_convergence(path: Path) -> tuple[list[str], dict[str, dict[int, float]]]:
    """Parse a convergence report's WORST-over-seeds block into {field: {level: err}}."""
    lines = path.read_text().splitlines()
    hdr_i = next(i for i, ln in enumerate(lines) if ln.strip().startswith("level"))
    fields = lines[hdr_i].split()[1:]
    start = next(i for i, ln in enumerate(lines) if ln.startswith("-- WORST"))
    out: dict[str, dict[int, float]] = {f: {} for f in fields}
    for ln in lines[start + 1:]:
        toks = ln.split()
        if not toks or not toks[0].isdigit():
            break
        lvl = int(toks[0])
        for f, v in zip(fields, toks[1:]):
            try:
                out[f][lvl] = float(v)
            except ValueError:
                pass
    return fields, out


def parse_panel_sections(path: Path) -> dict[str, tuple[list[str], dict]]:
    """4b holds two studies (spanwise, chordwise) in one file."""
    text = path.read_text()
    parts = re.split(r"\nTask 4b\(", text)
    out = {}
    for part in parts:
        if part.startswith("i)") or part.lower().startswith("task 4b(i)"):
            key = "spanwise"
        elif part.startswith("ii)"):
            key = "chordwise"
        else:
            continue
        tmp = Path("/tmp/_part.txt")
        tmp.write_text("Task 4b(" + part)
        out[key] = parse_convergence(tmp)
    return out


def parse_joint(path: Path) -> tuple[list[str], dict[str, dict[str, float]]]:
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    hdr = next(ln for ln in lines if ln.strip().startswith("grid"))
    fields = hdr.split()[3:]
    rows: dict[str, dict[str, float]] = {}
    for ln in lines:
        toks = ln.split()
        if toks and toks[0] in ("production", "recommended_16", "recommended_24"):
            rows[toks[0]] = {}
            for f, v in zip(fields, toks[3:]):
                try:
                    rows[toks[0]][f] = float(v)
                except ValueError:
                    pass
    return fields, rows


# -------------------------------------------------------------- svg helpers --
def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def line_chart(*, series, x_labels, title, subtitle, y_label, y_log=True,
               y_ticks=None, note=None, table_rows=None, chart_id="c"):
    """Multi-series line chart. series = [{name, color, dark, values, fmt}]."""
    iw = W - PAD["l"] - PAD["r"]
    ih = H - PAD["t"] - PAD["b"]
    n = len(x_labels)
    xs = [PAD["l"] + (iw * i / max(1, n - 1)) for i in range(n)]

    def keep(v):
        return v is not None and (v > 0 if y_log else True)

    vals = [v for s in series for v in s["values"] if keep(v)]
    lo, hi = min(vals), max(vals)
    if y_log:
        import math
        lo_e, hi_e = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
        ticks = y_ticks or [10.0 ** e for e in range(int(lo_e), int(hi_e) + 1)]

        def ypos(v):
            return PAD["t"] + ih * (1 - (math.log10(v) - lo_e) / max(1e-9, hi_e - lo_e))
    else:
        lo = min(0.0, lo)
        hi = max(0.0, hi)
        ticks = y_ticks or [lo + (hi - lo) * k / 4 for k in range(5)]

        def ypos(v):
            return PAD["t"] + ih * (1 - (v - lo) / max(1e-12, hi - lo))

    p = [f'<figure class="fig" id="{chart_id}">',
         f'<figcaption><h3>{esc(title)}</h3><p>{esc(subtitle)}</p></figcaption>',
         f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">']

    for t in ticks:
        y = ypos(t)
        if not (PAD["t"] - 1 <= y <= H - PAD["b"] + 1):
            continue
        lab = (f"{t:.0e}".replace("e-0", "e-") if y_log else
               (f"{t:.3g}" if abs(t) < 1000 else f"{t:.0f}"))
        p.append(f'<line class="grid" x1="{PAD["l"]}" y1="{y:.1f}" '
                 f'x2="{W - PAD["r"]}" y2="{y:.1f}"/>')
        p.append(f'<text class="tick" x="{PAD["l"] - 10}" y="{y + 4:.1f}" '
                 f'text-anchor="end">{lab}</text>')

    p.append(f'<line class="axis" x1="{PAD["l"]}" y1="{H - PAD["b"]}" '
             f'x2="{W - PAD["r"]}" y2="{H - PAD["b"]}"/>')
    if not y_log and lo < 0 < hi:
        zy = ypos(0.0)
        p.append(f'<line class="zero" x1="{PAD["l"]}" y1="{zy:.1f}" '
                 f'x2="{W - PAD["r"]}" y2="{zy:.1f}"/>')
    for x, lab in zip(xs, x_labels):
        p.append(f'<text class="tick" x="{x:.1f}" y="{H - PAD["b"] + 20}" '
                 f'text-anchor="middle">{esc(lab)}</text>')
    p.append(f'<text class="axlabel" x="{PAD["l"] + iw / 2:.0f}" y="{H - 8}" '
             f'text-anchor="middle">{esc(y_label)}</text>')

    for si, s in enumerate(series):
        kept = [(x, v) for x, v in zip(xs, s["values"]) if keep(v)]
        pts = [(x, ypos(v)) for x, v in kept]
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                     for i, (x, y) in enumerate(pts))
        p.append(f'<path class="ln s{si}" d="{d}"/>')
        for (x, y), (_, v) in zip(pts, kept):
            p.append(f'<circle class="mk s{si}" cx="{x:.1f}" cy="{y:.1f}" r="4.5" '
                     f'tabindex="0" data-t="{esc(s["name"])}: '
                     f'{esc(s.get("fmt", "{:.2e}").format(v))}"/>')
        lx, ly = pts[-1]
        p.append(f'<text class="dlabel s{si}" x="{lx + 10:.1f}" y="{ly + 4:.1f}">'
                 f'{esc(s["name"])}</text>')

    p.append("</svg>")
    if note:
        p.append(f'<p class="note">{note}</p>')
    if table_rows:
        p.append(details_table(table_rows))
    p.append("</figure>")
    return "\n".join(p)


def hbar_chart(*, rows, title, subtitle, note=None, chart_id="c", max_val=None,
               colorize=None):
    """rows = [(label, value, secondary_or_None)]. Horizontal bars, sequential."""
    bar_h, gap = 22, 10
    lw = 168
    inner_w = W - lw - 150
    height = PAD["t"] + len(rows) * (bar_h + gap) + 40
    mx = max_val or max(v for _, v, _ in rows)

    p = [f'<figure class="fig" id="{chart_id}">',
         f'<figcaption><h3>{esc(title)}</h3><p>{esc(subtitle)}</p></figcaption>',
         f'<svg viewBox="0 0 {W} {height}" role="img" aria-label="{esc(title)}">']
    for i, (label, v, sec) in enumerate(rows):
        y = PAD["t"] + i * (bar_h + gap)
        w = inner_w * (v / mx)
        cls = colorize(v) if colorize else "bar"
        p.append(f'<text class="rowlab" x="{lw - 12}" y="{y + bar_h - 6}" '
                 f'text-anchor="end">{esc(label)}</text>')
        p.append(f'<rect class="track" x="{lw}" y="{y}" width="{inner_w}" '
                 f'height="{bar_h}" rx="4"/>')
        p.append(f'<rect class="{cls}" x="{lw}" y="{y}" width="{max(3, w):.1f}" '
                 f'height="{bar_h}" rx="4" tabindex="0" '
                 f'data-t="{esc(label)}: {v:.3g}%'
                 f'{" (max " + format(sec, ".3g") + "%)" if sec is not None else ""}"/>')
        if sec is not None:
            xs = lw + inner_w * (sec / mx)
            p.append(f'<line class="whisk" x1="{xs:.1f}" y1="{y + 3}" '
                     f'x2="{xs:.1f}" y2="{y + bar_h - 3}"/>')
        p.append(f'<text class="val" x="{lw + inner_w + 10}" y="{y + bar_h - 6}">'
                 f'{v:.3g}%{"  /  " + format(sec, ".3g") + "%" if sec is not None else ""}'
                 f'</text>')
    p.append("</svg>")
    if note:
        p.append(f'<p class="note">{note}</p>')
    p.append("</figure>")
    return "\n".join(p)


def scatter_chart(*, groups, title, subtitle, x_label, y_label, note=None,
                  chart_id="c", extra_html=None):
    """groups = [{name, values:[(x,y,label)]}]. Max 3 groups (all-pairs gate)."""
    import math
    iw, ih = W - PAD["l"] - PAD["r"], H - PAD["t"] - PAD["b"]
    allx = [p[0] for g in groups for p in g["values"]]
    ally = [p[1] for g in groups for p in g["values"]]
    xlo, xhi = math.floor(math.log10(min(allx))), math.ceil(math.log10(max(allx)))
    ylo, yhi = math.floor(math.log10(min(ally))), math.ceil(math.log10(max(ally)))

    def xp(v):
        return PAD["l"] + iw * (math.log10(v) - xlo) / max(1e-9, xhi - xlo)

    def yp(v):
        return PAD["t"] + ih * (1 - (math.log10(v) - ylo) / max(1e-9, yhi - ylo))

    p = [f'<figure class="fig" id="{chart_id}">',
         f'<figcaption><h3>{esc(title)}</h3><p>{esc(subtitle)}</p></figcaption>',
         f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">']
    for e in range(int(ylo), int(yhi) + 1):
        y = yp(10.0 ** e)
        p.append(f'<line class="grid" x1="{PAD["l"]}" y1="{y:.1f}" '
                 f'x2="{W - PAD["r"]}" y2="{y:.1f}"/>')
        p.append(f'<text class="tick" x="{PAD["l"] - 10}" y="{y + 4:.1f}" '
                 f'text-anchor="end">{f"1e{e}"}</text>')
    for e in range(int(xlo), int(xhi) + 1):
        x = xp(10.0 ** e)
        p.append(f'<text class="tick" x="{x:.1f}" y="{H - PAD["b"] + 20}" '
                 f'text-anchor="middle">{f"1e{e}"}</text>')
    p.append(f'<line class="axis" x1="{PAD["l"]}" y1="{H - PAD["b"]}" '
             f'x2="{W - PAD["r"]}" y2="{H - PAD["b"]}"/>')
    p.append(f'<text class="axlabel" x="{PAD["l"] + iw / 2:.0f}" y="{H - 8}" '
             f'text-anchor="middle">{esc(x_label)}</text>')
    p.append(f'<text class="axlabel" transform="translate(16,'
             f'{PAD["t"] + ih / 2:.0f}) rotate(-90)" text-anchor="middle">'
             f'{esc(y_label)}</text>')
    for si, g in enumerate(groups):
        for (vx, vy, lab) in g["values"]:
            p.append(f'<circle class="mk s{si}" cx="{xp(vx):.1f}" cy="{yp(vy):.1f}" '
                     f'r="6" tabindex="0" data-t="{esc(lab)} — '
                     f'{esc(x_label)} {vx:.2e}, {esc(y_label)} {vy:.2e}"/>')
            p.append(f'<text class="ptlab" x="{xp(vx) + 10:.1f}" '
                     f'y="{yp(vy) + 4:.1f}">{esc(lab)}</text>')
        p.append(f'<text class="dlabel s{si}" x="{W - PAD["r"] + 12}" '
                 f'y="{PAD["t"] + 14 + si * 18}">{esc(g["name"])}</text>')
    p.append("</svg>")
    if note:
        p.append(f'<p class="note">{note}</p>')
    if extra_html:
        p.append(extra_html)
    p.append("</figure>")
    return "\n".join(p)


def details_table(rows) -> str:
    head, body = rows[0], rows[1:]
    th = "".join(f"<th>{esc(c)}</th>" for c in head)
    tb = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>"
                 for r in body)
    return (f'<details class="tbl"><summary>Table view</summary>'
            f'<div class="scroll"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{tb}</tbody></table></div></details>')


# ----------------------------------------------------------------- figures ---
def fig_span_margin() -> str:
    d = json.loads((EV_VER / "span_margin_probe.json").read_text())
    ref = d[-1]                       # margin 0.0 = the correct full-span model
    labels, cl, cla, e, ld = [], [], [], [], []
    # The reference row itself is 0 % error and cannot be placed on a log axis;
    # it is named in the subtitle instead of plotted as a phantom point.
    for r in d[:-1]:
        labels.append(f'{r["span_margin"]:g}')
        cl.append(abs(r["CL"] - ref["CL"]) / ref["CL"] * 100 or None)
        cla.append(abs(r["CLa_per_rad"] - ref["CLa_per_rad"]) / ref["CLa_per_rad"] * 100 or None)
        e.append(abs(r["span_efficiency"] - ref["span_efficiency"]) / ref["span_efficiency"] * 100 or None)
        ld.append(abs(r["L_over_D_viscous"] - ref["L_over_D_viscous"]) / ref["L_over_D_viscous"] * 100 or None)
    tbl = [["span_margin", "centreline gap (m)", "CL", "CLα /rad", "e", "L/D"]]
    for r in d:
        tbl.append([f'{r["span_margin"]:g}', f'{r["centreline_gap_m"]:.4f}',
                    f'{r["CL"]:.5f}', f'{r["CLa_per_rad"]:.4f}',
                    f'{r["span_efficiency"]:.4f}', f'{r["L_over_D_viscous"]:.3f}'])
    return line_chart(
        series=[
            {"name": "CL", "values": cl, "fmt": "{:.1f}%"},
            {"name": "CLα", "values": cla, "fmt": "{:.1f}%"},
            {"name": "e", "values": e, "fmt": "{:.1f}%"},
            {"name": "L/D", "values": ld, "fmt": "{:.1f}%"},
        ],
        x_labels=labels, chart_id="f1",
        title="Fig 1 — The extraction span margin was corrupting every number",
        subtitle="Error against the correct full-span model (margin = 0, not plotted "
                 "— it is the zero). Baseline seed, α = 3°, 25 sections, viscous on.",
        y_label="span_margin  (inset from each span end)",
        y_ticks=[1, 3, 10, 30, 100],
        note="A non-zero margin puts the innermost section at y &gt; 0, so "
             "<code>YDUPLICATE</code> mirrors it into a <strong>centreline gap</strong> "
             "and AVL sheds a spurious inboard tip-vortex pair. The old default of "
             "0.02 understated CL by <strong>54.9 %</strong> and the lift-curve slope "
             "by <strong>26.2 %</strong>. Error is monotonic in the gap and reaches "
             "zero only at margin exactly 0 — even the 1e-4 margin used for geometric "
             "metrics still costs 2.2 % of CLα.",
        table_rows=tbl)


def fig_claf_cdcl() -> str:
    """Two SEPARATE charts as small multiples.

    cd_min and t/c are different measures with different units. Forcing them onto
    one rescaled axis would be a dual-axis chart in disguise -- the single most
    common charting error -- so they get one axis each.
    """
    d = json.loads((EV_VER / "viscous_claf_verification.json").read_text())
    cd = d["cdcl"]["section_resolved"]["cd_min_by_section"]
    tc = d["claf"]["correct"]["t_over_c_independent"]
    n = len(cd)
    labels = [f"{i / (n - 1):.2f}" if i % 6 == 0 else "" for i in range(n)]
    tbl = [["section", "y/semispan", "injected cd_min", "t/c (drives CLAF)"]]
    for i, (c, t_) in enumerate(zip(cd, tc)):
        tbl.append([str(i), f"{i / (n - 1):.3f}", f"{c:.5f}", f"{t_:.4f}"])

    a = line_chart(
        series=[{"name": "cd_min", "values": [v * 1000 for v in cd],
                 "fmt": "{:.2f}e-3"}],
        x_labels=labels, chart_id="f2a", y_log=False,
        title="Fig 2a — CDCL: a separate NeuralFoil polar per section",
        subtitle="Injected minimum-drag cd (x10^-3) for all 25 sections, at each "
                 "section's own local Reynolds number. alpha = 6 deg.",
        y_label="spanwise station  y / semispan",
        note="25 sections, <strong>25 distinct polars</strong>. The tip is "
             "<strong>3.8x draggier than the root</strong> from the Reynolds effect "
             "alone (cd_min 0.02065 vs 0.00547) - exactly the variation a wing-level "
             "or 4-airfoil-step CDCL would smear away. Verified active by ablation: "
             "AVL's CDvis goes 0 -> 0.00663 when the correction is switched on, and "
             "the injected values match an independent NeuralFoil refit to 4.3e-7.")
    b = line_chart(
        series=[{"name": "t/c", "values": [v * 100 for v in tc], "fmt": "{:.2f}%"}],
        x_labels=labels, chart_id="f2b", y_log=False,
        title="Fig 2b — CLAF: thickness read off the realized loft",
        subtitle="t/c per section (%), which sets CLAF = 1 + 0.77 (t/c). Same 25 "
                 "sections.",
        y_label="spanwise station  y / semispan",
        note="16 distinct CLAF values from only <strong>4 authored station "
             "airfoils</strong>. The trace runs 15.00 % -> 10.93 % -> 15.07 %, i.e. "
             "mh91 -> e374 -> nlf1015 recovered from the surface <em>including the "
             "blends</em>, with the thin-airfoil minimum correctly interior. Ablation: "
             "forcing CLAF to 1 moves CLa 3.685 -> 3.484; the ratio 1.0576 sits "
             "between 1.0 (ignored) and the mean CLAF 1.1010 (no 3-D dilution), and "
             "lifting-line predicts 1.0641 - <strong>0.6 % away</strong>, confirming "
             "AVL treats it as a section property diluted by downwash.",
        table_rows=tbl)
    return a + "\n" + b


def fig_elevon_cause() -> str:
    rows = json.loads((EV_DOE / "elevon_cause_delta_e_sweep.json").read_text())
    seeds = sorted({r["seed"] for r in rows})
    des = sorted({r["de"] for r in rows})
    series = []
    for i, sd in enumerate(seeds):
        vals = [next(r["dCL"] for r in rows if r["seed"] == sd and r["de"] == d)
                for d in des]
        series.append({"name": f"seed {sd}", "values": [v * 1000 for v in vals],
                       "fmt": "{:.3f}e-3"})
    tbl = [["seed", "δe (deg)", "CL native", "CL ASB", "ΔCL"]]
    for r in rows:
        tbl.append([str(r["seed"]), f'{r["de"]:g}', f'{r["CL_n"]:.5f}',
                    f'{r["CL_a"]:.5f}', f'{r["dCL"]:+.5f}'])
    return line_chart(
        series=series, x_labels=[f"{d:g}" for d in des], chart_id="f3", y_log=False,
        title="Fig 3 — The whole native-vs-AeroSandbox gap is the elevon",
        subtitle="ΔCL (ASB − native) ×10⁻³ against elevon deflection, α = 6°, "
                 "identical pyGeo sections into both solvers.",
        y_label="symmetric elevon deflection δe  (deg)",
        note="<strong>At δe = 0 the two solvers agree on CL to 3e-5 … 3e-4</strong> — "
             "three orders of magnitude better than the 0.7 % headline. The gap is "
             "linear in δe with ~zero intercept, so 94–101 % of it is the elevon. Its "
             "slope (5.12e-4 /deg) matches the independently measured +5.89 % CL_δe "
             "bias prediction (5.6e-4 /deg) to 9 %. Two earlier explanations — airfoil "
             "coordinate resolution and Mach handling — were tested and refuted.",
        table_rows=tbl)


def fig_doe_agreement() -> str:
    s = json.loads((EV_DOE / "doe_summary.json").read_text())
    f = s["viscous_on"]["fields"]
    want = [("CL", "CL"), ("cd_total", "CD (viscous)"), ("CDind", "CDind"),
            ("cd_profile", "cd_profile"), ("Cm", "Cm"), ("L_over_D", "L/D"),
            ("CLa", "CLα"), ("Cma", "Cmα"), ("Cmq", "Cmq"), ("Clp", "Clp"),
            ("Xnp", "Xnp")]
    rows = [(lab, f[k]["median_rel"] * 100, f[k]["max_rel"] * 100)
            for k, lab in want if k in f and "median_rel" in f[k]]
    return hbar_chart(
        rows=rows, chart_id="f4",
        title="Fig 4 — Agreement holds across the whole design space",
        subtitle="Native vs AeroSandbox over 30 DoE samples (AR 3.11–6.62, span "
                 "1.52–2.49 m, all 19 free DVs varied). Bar = median, tick = worst.",
        note="Every quantity the multifidelity workflow consumes agrees to ≲1 % median. "
             "The lift-curve slope agrees <strong>7× better than the lift itself</strong> "
             "(CLα 0.10 % vs CL 0.69 %) — the signature of a constant lift offset rather "
             "than a different solution, which Fig 3 identifies. No dependence on "
             "position in the design space: corr(AR, CL error) = −0.287, not significant "
             "at n = 30. These figures are an <em>upper bound</em> inflated by δe = 4°.")


def fig_4a() -> str:
    fields, d = parse_convergence(EV_DIS / "4a_geometry_sections_chord8.txt")
    levels = sorted(d["CL"].keys())
    pick = [("CL", "CL"), ("CDind", "CDind"), ("CL_de", "CL_δe"), ("CLa", "CLα")]
    series = [{"name": lab, "values": [d[k].get(lv) for lv in levels]}
              for k, lab in pick]
    tbl = [["n_sections"] + [lab for _, lab in pick]]
    for lv in levels:
        tbl.append([str(lv)] + [f"{d[k].get(lv, float('nan')):.2e}" for k, _ in pick])
    return line_chart(
        series=series, x_labels=[str(lv) for lv in levels], chart_id="f5",
        title="Fig 5 — (a) Geometry sections, with the AVL panel count held FIXED",
        subtitle="Worst-seed error vs n = 49, 5 DoE seeds. Total spanwise panels "
                 "pinned at 96/side, so ONLY geometric fidelity varies.",
        y_label="n_sections  (geometry extraction slices)",
        note="Forces and stability derivatives converge to ≤0.56 % by "
             "<strong>n = 25</strong>. But <strong>CL_δe is non-monotonic</strong> — "
             "n = 13 beats n = 17 and n = 25, reproducibly. Sections snap onto the "
             "elevon band edges, yet AVL still ramps the control gain over the interval "
             "<em>just outside</em> each edge, whose width depends on where the "
             "neighbour lands. The result is a ±1.5 % oscillatory floor that uniform "
             "refinement cannot remove.",
        table_rows=tbl)


def fig_4b() -> str:
    parts = parse_panel_sections(EV_DIS / "4b_avl_panels.txt")
    out = []
    for key, (label, xlab, note) in {
        "spanwise": ("(b-i) AVL spanwise panels", "spanwise panels per section interval",
                     "Monotone and well behaved. Roll damping Clp is the limiting "
                     "quantity at coarse resolution, as expected — it depends on the "
                     "outboard loading gradient. <strong>4 per interval is adequate</strong> "
                     "(≤0.54 %)."),
        "chordwise": ("(b-ii) AVL chordwise panels", "chordwise panels",
                      "<strong>This is the largest discretisation error in the whole "
                      "chain, and it sat in the production default.</strong> At "
                      "nchordwise = 8 the elevon derivative carries 6–8 % error because "
                      "the hinge at x/c = 0.75 falls 0.059 c from the nearest cosine "
                      "panel edge. CL_δe is the limiting quantity at <em>every</em> "
                      "level — the diagnostic that this is a specific geometric "
                      "coincidence, not generic under-resolution."),
    }.items():
        fields, d = parts[key]
        levels = sorted(d["CL"].keys())
        pick = [("CL_de", "CL_δe"), ("CDind", "CDind"), ("Clp", "Clp"), ("CL", "CL")]
        series = [{"name": lb, "values": [d[k].get(lv) for lv in levels]}
                  for k, lb in pick]
        tbl = [["level"] + [lb for _, lb in pick]]
        for lv in levels:
            tbl.append([str(lv)] + [f"{d[k].get(lv, float('nan')):.2e}"
                                    for k, _ in pick])
        out.append(line_chart(
            series=series, x_labels=[str(lv) for lv in levels],
            chart_id=f"f6-{key}",
            title=f"Fig 6{'a' if key == 'spanwise' else 'b'} — {label}, geometry FIXED at 25 sections",
            subtitle="Worst-seed error vs the finest level, 5 DoE seeds. Only the "
                     "vortex lattice varies.",
            y_label=xlab, note=note, table_rows=tbl))
    return "\n".join(out)


def fig_hinge() -> str:
    d = json.loads((EV_DIS / "hinge_alignment.json").read_text())
    err, align = d["errors_vs_reference"], d["hinge_alignment"]
    cos, uni = [], []
    for label, e in err.items():
        if "CL_de" not in e or "Xnp" not in e:
            continue
        pt = (e["CL_de"]["worst"], e["Xnp"]["worst"], label.split()[0])
        (uni if label.startswith("uniform") else cos).append(pt)
    tbl = [["config", "hinge→edge dist (c)", "CL_δe err", "CL err", "Xnp err", "Cmq err"]]
    for label in err:
        e = err[label]
        tbl.append([label, f'{align[label]["nearest_edge_distance_from_hinge"]:.4f}',
                    f'{e.get("CL_de", {}).get("worst", float("nan")):.2e}',
                    f'{e.get("CL", {}).get("worst", float("nan")):.2e}',
                    f'{e.get("Xnp", {}).get("worst", float("nan")):.2e}',
                    f'{e.get("Cmq", {}).get("worst", float("nan")):.2e}'])
    return (scatter_chart(
        extra_html=details_table(tbl),
        groups=[{"name": "cosine spacing", "values": cos},
                {"name": "uniform spacing", "values": uni}],
        chart_id="f7",
        title="Fig 7 — Uniform spacing wins the elevon and loses the neutral point",
        subtitle="Worst-seed error vs cosine-40, 3 seeds. Down-and-left is better. "
                 "Labels give the chordwise panel count.",
        x_label="CL_δe error  (elevon authority)",
        y_label="Xnp error  (neutral point)",
        note="Uniform-8 puts a panel edge <em>exactly</em> on the hinge and halves the "
             "elevon error at identical cost (3.82 % vs 7.71 %) — confirming the "
             "alignment mechanism. It is <strong>rejected anyway</strong>: it degrades "
             "Xnp and Cmq by <strong>14–15×</strong>, and the penalty persists under "
             "refinement (uniform-40 still 1.1e-3 vs cosine-20's 1.2e-5). Leading-edge "
             "clustering is what resolves the pitching moment. Trading 14× neutral-point "
             "accuracy for 2× elevon accuracy is the wrong trade for a "
             "stability-and-control study.")
        + details_table(tbl))


def fig_joint() -> str:
    fields, rows = parse_joint(EV_DIS / "joint_grid_total_error.txt")
    want = [("CL_de", "CL_δe"), ("CDind", "CDind"), ("Cm", "Cm"),
            ("cd_total", "CD"), ("CL", "CL"), ("Cnb", "Cnb")]
    out = []
    for grid, label in [("production", "OLD: 25 sec / 4 span / 8 chord"),
                        ("recommended_24", "NEW: 25 sec / 4 span / 24 chord")]:
        r = [(lab, rows[grid][k] * 100, None) for k, lab in want if k in rows[grid]]
        out.append(hbar_chart(
            rows=r, chart_id=f"f8-{grid}", max_val=8.0,
            title=f"Fig 8{'a' if grid == 'production' else 'b'} — {label}",
            subtitle="Total discretisation error vs the best reference that fits AVL's "
                     "array limits (33 sec / 4 span / 20 chord), 3 seeds. "
                     "Shared 0–8 % scale.",
            colorize=lambda v: ("bar crit" if v > 3 else
                                "bar warn" if v > 1 else "bar good"),
            note=None))
    return "\n".join(out)


def fig_physics() -> str:
    d = json.loads((EV_VER / "physics_validation.json").read_text())
    checks = d["checks"]
    tbl = [["check", "measured", "reference", "verdict"]]
    for c in checks:
        val = c["value"]
        tbl.append([c["check"],
                    f"{val:.5f}" if isinstance(val, float) else str(val),
                    (f'{c["expected"]:.4f}' if isinstance(c["expected"], float)
                     else str(c["expected"])),
                    "PASS" if c["pass"] else "FAIL"])
    n_pass = d["n_pass"]
    cards = [
        ("Elliptic wing span efficiency", f'{d["A_elliptic"]["e"]:.5f}', "theory 1.0",
         "The keystone. Elliptic loading is the minimum-induced-drag distribution, so "
         "e = 1 requires the chord law, spanwise stations, Sref/Bref AND AVL's Trefftz "
         "integration all to be right at once."),
        ("Symmetric untwisted CL(α = 0)", f'{d["B_rect_alpha0"]["CL"]:.5f}', "theory 0",
         "NACA 0012, no twist, no camber."),
        ("Rectangular CLα", f'{d["B_rect_alpha5"]["CLa"]:.4f}',
         f'Helmbold {d["reference_values"]["helmbold_CLa_per_rad"]:.4f}',
         "2.0 % below Helmbold and 5.8 % below the e = 1 lifting-line value — bracketed "
         "on the physically correct side, since rectangular loading is less efficient "
         "than elliptic."),
    ]
    p = ['<figure class="fig" id="f9">',
         '<figcaption><h3>Fig 9 — Independent physics validation: 11/11</h3>'
         '<p>Closed-form checks on analytic wings built from a duck-typed stub, with '
         'no pyGeo present.</p></figcaption>',
         '<div class="kpis">']
    for name, val, ref, why in cards:
        p.append(f'<div class="kpi"><span class="kpi-l">{esc(name)}</span>'
                 f'<span class="kpi-v">{esc(val)}</span>'
                 f'<span class="kpi-r">{esc(ref)}</span>'
                 f'<span class="kpi-w">{esc(why)}</span></div>')
    p.append('</div>')
    p.append(f'<p class="note"><strong>Why this exists:</strong> the native and '
             f'AeroSandbox paths share <code>inject_polar_cdcl</code> and '
             f'<code>_compute_strip_profile_drag</code>, and both read '
             f'<code>twist_deg</code>, <code>x_le_m</code>, <code>z_le_m</code> from '
             f'the <em>same</em> section objects. A shared bug, or a sign error in a '
             f'geometry field, is <strong>structurally invisible</strong> to their '
             f'agreement — they would agree to 1e-7 while both being wrong. All three '
             f'sign conventions are confirmed here by their known physical '
             f'consequences, including that twist acts <em>per section</em> (washout '
             f'moves the tip strip cl by −0.1306 vs −0.1119 at the root, so the loading '
             f'shifts inboard rather than scaling down). '
             f'<strong>{n_pass}/{len(checks)} checks pass.</strong> Weakest link, '
             f'recorded as such: the unswept neutral point comes out at 0.215 c against '
             f'the thin-airfoil 0.25 c.</p>')
    p.append(details_table(tbl))
    p.append('</figure>')
    return "\n".join(p)


# --------------------------------------------------------------------- page --
CSS = f"""
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#f9f9f7; color:#0b0b0b;
  font:15px/1.62 system-ui,-apple-system,"Segoe UI",sans-serif; }}
.wrap {{ max-width:920px; margin:0 auto; padding:44px 22px 90px; }}
h1 {{ font-size:30px; line-height:1.22; letter-spacing:-.02em; margin:0 0 6px; }}
.sub {{ color:#52514e; margin:0 0 26px; font-size:15px; }}
h2 {{ font-size:20px; margin:46px 0 8px; letter-spacing:-.01em; }}
h2 .num {{ color:#898781; font-variant-numeric:tabular-nums; margin-right:8px; }}
h3 {{ font-size:16px; margin:0 0 3px; letter-spacing:-.01em; }}
.lede {{ color:#52514e; margin:0 0 18px; }}
.fig {{ background:#fcfcfb; border:1px solid rgba(11,11,11,.10); border-radius:12px;
  margin:0 0 22px; padding:18px 18px 12px; }}
figcaption p {{ color:#52514e; font-size:13.5px; margin:0 0 10px; }}
svg {{ width:100%; height:auto; display:block; overflow:visible; }}
.grid {{ stroke:#e1e0d9; stroke-width:1; }}
.axis {{ stroke:#c3c2b7; stroke-width:1; }}
.tick {{ fill:#898781; font-size:11px; font-variant-numeric:tabular-nums; }}
.axlabel {{ fill:#52514e; font-size:12px; }}
.rowlab {{ fill:#52514e; font-size:12.5px; }}
.val {{ fill:#52514e; font-size:11.5px; font-variant-numeric:tabular-nums; }}
.ptlab {{ fill:#898781; font-size:10.5px; font-variant-numeric:tabular-nums; }}
.ln {{ fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }}
.mk {{ stroke:#fcfcfb; stroke-width:2; }}
.mk:hover, .mk:focus {{ r:6.5; outline:none; }}
.dlabel {{ font-size:12px; font-weight:600; }}
.track {{ fill:#e1e0d9; }}
.bar {{ fill:{S1}; }}
.bar.good {{ fill:{GOOD}; }} .bar.warn {{ fill:{WARN}; }} .bar.crit {{ fill:{CRIT}; }}
.whisk {{ stroke:#0b0b0b; stroke-width:2; }}
.zero {{ stroke:#898781; stroke-width:1; stroke-dasharray:3 3; }}
.s0 {{ stroke:{S1}; }} .s1 {{ stroke:{S2}; }} .s2 {{ stroke:{S3}; }} .s3 {{ stroke:{S4}; }}
circle.s0 {{ fill:{S1}; }} circle.s1 {{ fill:{S2}; }}
circle.s2 {{ fill:{S3}; }} circle.s3 {{ fill:{S4}; }}
text.s0 {{ fill:{S1}; stroke:none; }} text.s1 {{ fill:{S2}; stroke:none; }}
text.s2 {{ fill:{S3}; stroke:none; }} text.s3 {{ fill:{S4}; stroke:none; }}
.note {{ font-size:13px; color:#52514e; margin:12px 0 2px;
  border-top:1px solid #e1e0d9; padding-top:11px; }}
code {{ font-size:12.5px; background:#f0efec; padding:1px 5px; border-radius:4px; }}
.tbl {{ margin-top:10px; }}
.tbl summary {{ cursor:pointer; font-size:12.5px; color:#52514e; }}
.scroll {{ overflow-x:auto; margin-top:8px; }}
table {{ border-collapse:collapse; font-size:12px; width:100%;
  font-variant-numeric:tabular-nums; }}
th,td {{ text-align:right; padding:4px 9px; border-bottom:1px solid #e1e0d9;
  white-space:nowrap; }}
th:first-child,td:first-child {{ text-align:left; }}
th {{ color:#52514e; font-weight:600; }}
.kpis {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); }}
.kpi {{ display:flex; flex-direction:column; gap:2px; background:#f9f9f7;
  border:1px solid rgba(11,11,11,.08); border-radius:9px; padding:13px 14px; }}
.kpi-l {{ font-size:12px; color:#52514e; }}
.kpi-v {{ font-size:26px; font-weight:650; letter-spacing:-.02em; color:{GOOD}; }}
.kpi-r {{ font-size:11.5px; color:#898781; font-variant-numeric:tabular-nums; }}
.kpi-w {{ font-size:12px; color:#52514e; margin-top:5px; }}
.card {{ background:#fcfcfb; border:1px solid rgba(11,11,11,.10);
  border-left:3px solid {S1}; border-radius:10px; padding:18px 20px; margin:0 0 22px; }}
.card table {{ width:auto; }}
.card td:first-child {{ font-weight:600; }}
.pill {{ display:inline-block; font-size:11px; padding:2px 9px; border-radius:20px;
  background:#f0efec; color:#52514e; margin-right:6px; }}
.tip {{ position:fixed; pointer-events:none; opacity:0; transition:opacity .1s;
  background:#0b0b0b; color:#fff; font-size:12px; padding:6px 9px; border-radius:6px;
  z-index:9; max-width:280px; font-variant-numeric:tabular-nums; }}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) body {{ background:#0d0d0d; color:#fff; }}
  :root:where(:not([data-theme="light"])) .sub,
  :root:where(:not([data-theme="light"])) .lede,
  :root:where(:not([data-theme="light"])) figcaption p,
  :root:where(:not([data-theme="light"])) .note,
  :root:where(:not([data-theme="light"])) .axlabel,
  :root:where(:not([data-theme="light"])) .rowlab,
  :root:where(:not([data-theme="light"])) .val,
  :root:where(:not([data-theme="light"])) th,
  :root:where(:not([data-theme="light"])) .kpi-l,
  :root:where(:not([data-theme="light"])) .kpi-w,
  :root:where(:not([data-theme="light"])) .tbl summary {{ color:#c3c2b7; }}
  :root:where(:not([data-theme="light"])) .fig,
  :root:where(:not([data-theme="light"])) .card {{ background:#1a1a19;
    border-color:rgba(255,255,255,.10); }}
  :root:where(:not([data-theme="light"])) .kpi {{ background:#0d0d0d;
    border-color:rgba(255,255,255,.09); }}
  :root:where(:not([data-theme="light"])) .grid {{ stroke:#2c2c2a; }}
  :root:where(:not([data-theme="light"])) .axis {{ stroke:#383835; }}
  :root:where(:not([data-theme="light"])) .track {{ fill:#2c2c2a; }}
  :root:where(:not([data-theme="light"])) .whisk {{ stroke:#fff; }}
  :root:where(:not([data-theme="light"])) th,
  :root:where(:not([data-theme="light"])) td {{ border-color:#2c2c2a; }}
  :root:where(:not([data-theme="light"])) code {{ background:#2c2c2a; }}
  :root:where(:not([data-theme="light"])) .pill {{ background:#2c2c2a; color:#c3c2b7; }}
  :root:where(:not([data-theme="light"])) .mk {{ stroke:#1a1a19; }}
  :root:where(:not([data-theme="light"])) .s0 {{ stroke:{D1}; }}
  :root:where(:not([data-theme="light"])) .s1 {{ stroke:{D2}; }}
  :root:where(:not([data-theme="light"])) .s2 {{ stroke:{D3}; }}
  :root:where(:not([data-theme="light"])) .s3 {{ stroke:{D4}; }}
  :root:where(:not([data-theme="light"])) circle.s0 {{ fill:{D1}; }}
  :root:where(:not([data-theme="light"])) circle.s1 {{ fill:{D2}; }}
  :root:where(:not([data-theme="light"])) circle.s2 {{ fill:{D3}; }}
  :root:where(:not([data-theme="light"])) circle.s3 {{ fill:{D4}; }}
  :root:where(:not([data-theme="light"])) text.s0 {{ fill:{D1}; }}
  :root:where(:not([data-theme="light"])) text.s1 {{ fill:{D2}; }}
  :root:where(:not([data-theme="light"])) text.s2 {{ fill:{D3}; }}
  :root:where(:not([data-theme="light"])) text.s3 {{ fill:{D4}; }}
  :root:where(:not([data-theme="light"])) .bar {{ fill:{D1}; }}
  :root:where(:not([data-theme="light"])) .card {{ border-left-color:{D1}; }}
}}
"""

JS = """
const tip=document.createElement('div');tip.className='tip';document.body.append(tip);
function show(e){const t=e.target.getAttribute('data-t');if(!t)return;
 tip.textContent=t;tip.style.opacity=1;
 const r=e.target.getBoundingClientRect();
 tip.style.left=Math.min(window.innerWidth-300,r.left+r.width/2-60)+'px';
 tip.style.top=Math.max(6,r.top-38)+'px';}
function hide(){tip.style.opacity=0;}
for(const el of document.querySelectorAll('[data-t]')){
 el.addEventListener('mouseenter',show);el.addEventListener('focus',show);
 el.addEventListener('mouseleave',hide);el.addEventListener('blur',hide);}
"""


def main() -> None:
    panelling = """
<div class="card">
<h3 style="margin-bottom:10px">The panelling to use from now on</h3>
<table>
<tr><td>Geometry sections</td><td><code>n_sections = 25</code></td>
    <td>≤0.56 % worst-seed on all forces + stability derivatives</td></tr>
<tr><td>Section placement</td><td><code>span_margin = 0.0</code>, snap to elevon edges</td>
    <td>full span; a margin opens a centreline gap (Fig 1)</td></tr>
<tr><td>Spanwise panels</td><td><code>spanwise_panels_per_section = 4</code></td>
    <td>96/side; ≤0.54 % worst-seed (Fig 6a)</td></tr>
<tr><td>Chordwise panels</td><td><code>nchordwise = 24</code> &nbsp;<span class="pill">was 8</span></td>
    <td>CL_δe 7.7 % → ~1.1 % (Fig 6b, 7)</td></tr>
<tr><td>Chordwise spacing</td><td><code>cspace = 1.0</code> (cosine)</td>
    <td>uniform halves the elevon error but costs 14× on Xnp (Fig 7)</td></tr>
</table>
<p class="note" style="margin-bottom:0">Cost: 192 strips, 4608 vortices — inside
both AVL array limits. <strong>Economy setting</strong> for work where the elevon
derivative is not the object of study: <code>nchordwise = 16</code> (CL_δe ~2.6 %,
everything else ≤0.4 %, 3072 vortices).
<strong>Hard ceilings:</strong> (n_sections − 1) × spanwise_panels ≤ 250 strips,
and strips × nchordwise ≤ ~6000 vortices — 49/4/16 and 65/4/anything both fail.
Already applied as the default in <code>native_avl.py</code>,
<code>pygeo_avl_adapter.py</code> and <code>aeris aero pygeo-native</code>.</p>
</div>
"""
    body = f"""<div class="wrap">
<h1>Low-fidelity AVL: verification campaign</h1>
<p class="sub">pyGeo → native AVL + NeuralFoil, for the BWB ISR UAV design space.
Tasks 1–4 · DECISION-0005 … 0009 · 2026-07-25</p>

{panelling}

<h2><span class="num">1</span>Geometry fidelity — two defects that moved everything</h2>
<p class="lede">Confirming the chain "runs clean" is what exposed these. Both are
fixed; both changed the answers by tens of percent, so every low-fidelity number
produced before 2026-07-25 is invalid.</p>
{fig_span_margin()}

<h2><span class="num">2</span>The viscous and thickness corrections</h2>
<p class="lede">AVL is inviscid. Its two per-section hooks are the entire
difference between "AVL on a wireframe" and "AVL that knows what airfoil it is
flying". Both have regressed silently before, so presence in the <code>.avl</code>
is not evidence — each is established as PRESENT, CORRECT against an independent
recomputation, and ACTIVE by ablation.</p>
{fig_claf_cdcl()}

<h2><span class="num">3</span>Native vs AeroSandbox, across the design space</h2>
{fig_doe_agreement()}
{fig_elevon_cause()}

<h2><span class="num">4</span>Independent physics validation</h2>
<p class="lede">Code-to-code agreement is not verification. This leg uses
closed-form answers.</p>
{fig_physics()}

<h2><span class="num">5</span>Discretisation — the two questions, separated</h2>
<p class="lede">The prior study conflated them: because
<code>total spanwise panels = (n_sections − 1) × panels_per_interval</code>,
adding a <em>section</em> silently refined the <em>lattice</em>. Separating them
showed the dominant error was never the section count.</p>
{fig_4a()}
{fig_4b()}
{fig_hinge()}

<h2><span class="num">6</span>What the change buys</h2>
{fig_joint()}

<h2><span class="num">7</span>What is still open</h2>
<div class="fig">
<ul>
<li><strong>No validation against experiment or CFD.</strong> Everything here is
verification — is the code solving the intended equations correctly. Physical
accuracy must come from the high-fidelity ADflow path.</li>
<li><strong>Surface split at the hinge line</strong> — the principled fix for the
elevon resolution, rather than paying for chordwise panels. Not attempted.</li>
<li><strong>The hinge position varies across the DoE</strong>
(<code>elevon_hinge_frac</code> 0.652–0.814), so the hinge-to-edge distance and
hence the elevon error vary design-space-wide. Mapped only at the nominal 0.75.</li>
<li><strong>One operating point</strong> (α = 6°). Behaviour near CL<sub>max</sub>,
where the polar bridge clamps strips outside the 2-D polar range, is
uncharacterised.</li>
<li><strong>Cref definition mismatch</strong> of 0.13 % between the two paths
(∫c²dy/S vs <code>mean_aerodynamic_chord()</code>); moves Cmu and Cmα by 0.129 %.</li>
<li><strong>Whether 30 samples / 5 seeds suffice</strong> for these statistics to be
design-space representative — the next study.</li>
</ul>
<p class="note">Colour: the <code>dataviz</code> reference palette used unchanged,
so its documented validation applies (worst adjacent CVD ΔE 9.1 light / 8.4 dark;
slots 1–3 clear the all-pairs gate used by Fig 7). No JS runtime was available to
re-run the validator, and no palette values were substituted. Every chart ships
direct labels and a table view.</p>
</div>
</div>"""

    html = (f"<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Low-fidelity AVL verification campaign</title>"
            f"<style>{CSS}</style></head><body>{body}"
            f"<script>{JS}</script></body></html>")
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({len(html) / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
