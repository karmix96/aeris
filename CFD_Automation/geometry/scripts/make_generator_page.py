"""One HTML page that explains the generator, with the pictures embedded.

    python scripts/make_generator_visuals.py     # first: the GIFs and PNGs
    python scripts/make_generator_page.py        # then: docs/GEOMETRY_GENERATOR.html
"""

from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.geometry import airfoils, published_wings  # noqa: E402
from cfdauto.geometry.planform import aspect_ratio, mean_aero_chord  # noqa: E402
from cfdauto.geometry.sections import build_wing_sections  # noqa: E402

DOCS = ROOT / "docs"


def img(name: str, alt: str) -> str:
    data = base64.b64encode((DOCS / name).read_bytes()).decode()
    mime = "image/gif" if name.endswith(".gif") else "image/png"
    return f'<img src="data:{mime};base64,{data}" alt="{html.escape(alt)}">'


def rows() -> str:
    out = []
    for name in published_wings.names():
        spec, vec, te, meta = published_wings.get(name)
        pf, st = build_wing_sections(spec, vec, te)
        kind = "BWB" if meta["kind"] == "bwb" else "Conventional"
        use = meta.get("use", "BWB dataset design (FUN3D RANS, Spalart–Allmaras), 12,490 published solutions in BlendedNet++.")
        secs = ", ".join(dict.fromkeys(s.airfoil.name for s in st))
        src = "<br>".join(html.escape(s) for s in meta["sources"])
        out.append(
            f"<tr><td class='what'>{html.escape(meta['title'])}<span class='id'>{name}</span></td>"
            f"<td><span class='tag {meta['kind']}'>{kind}</span></td>"
            f"<td class='num'>{pf.semi_span:.3g} m<br>AR {aspect_ratio(pf):.2f}<br>MAC {mean_aero_chord(pf):.3g} m</td>"
            f"<td>{html.escape(use)}</td>"
            f"<td>{html.escape(meta['fidelity'])}<br><span class='muted'>Sections: {html.escape(secs)}</span></td>"
            f"<td class='src'>{src}</td></tr>")
    return "\n".join(out)


PAGE = """<title>Wing Generator</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@500&display=swap">
<style>
/* Layout: one reading column; pictures on white cards (they are drawn on white); tables scroll on phones. */
:root {
  --bg: #F3F6F9; --surface: #FFFFFF; --ink: #142230; --muted: #566573; --line: #D6DEE6;
  --accent: #0C5EA8; --bwb: #2E8B57; --warn: #B02A20;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F;
  --accent: #62AEF2; --bwb: #5FC48F; --warn: #F08A80; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F;
  --accent: #62AEF2; --bwb: #5FC48F; --warn: #F08A80; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 28px 56px; }
.wrap { max-width: 1060px; margin: 0 auto; display: flex; flex-direction: column; gap: 34px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 16px; display: flex; flex-direction: column; gap: 8px; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { font-family: var(--display); font-size: clamp(32px, 5vw, 46px); line-height: 1.05; margin: 0; text-wrap: balance; }
h2 { font-family: var(--display); font-size: 28px; margin: 0; text-wrap: balance; }
p { margin: 0; max-width: 72ch; }
section { display: flex; flex-direction: column; gap: 14px; }
.lede { color: var(--muted); font-size: 17px; }
.card { background: #FFFFFF; border: 1px solid var(--line); border-radius: 6px; padding: 10px; overflow-x: auto; }
.card img { display: block; width: 100%; height: auto; max-width: 100%; }
.cap { color: var(--muted); font-size: 14px; }
.three { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
.box { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; min-width: 0; }
.box h3 { margin: 0 0 6px; font-size: 17px; }
code, pre { font-family: var(--mono); font-size: 13px; }
pre { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; overflow-x: auto; margin: 0; }
.tbl { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; min-width: 900px; font-size: 14px; }
th, td { text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--line); }
tr:last-child td { border-bottom: 0; }
th { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
td.what { font-weight: 700; width: 17%; }
td.what .id { display: block; font-family: var(--mono); font-weight: 500; font-size: 12px; color: var(--muted); margin-top: 3px; }
td.num { font-family: var(--mono); font-size: 13px; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.src { font-size: 12.5px; color: var(--muted); width: 22%; }
.muted { color: var(--muted); font-size: 13px; }
.tag { font-family: var(--mono); font-size: 11px; text-transform: uppercase; padding: 2px 7px; border-radius: 3px; border: 1px solid currentColor; white-space: nowrap; }
.tag.conventional { color: var(--accent); } .tag.bwb { color: var(--bwb); }
.weak { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--warn); border-radius: 6px; padding: 14px 18px; }
.weak ul { margin: 6px 0 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px; }
footer { color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 12px; }
</style>
<div class="wrap">
<header>
  <div class="eyebrow">CFD_Automation · Stage 1 · geometry</div>
  <h1>How the wing generator works</h1>
  <p class="lede">Eighteen numbers go in; one exact wing surface comes out, measured, labelled and checked. The same generator makes BWB and conventional wings, uses any airfoil from the AERIS database, and rebuilds published wings so the CFD can be validated against them later.</p>
</header>

<section>
  <h2>One wing, step by step</h2>
  <div class="card">__GIF_BUILD__</div>
  <p class="cap">Seven steps, about 2.5 s each: design vector, planform, sections, twist and dihedral, trailing edge, loft, measure-label-check. Example: a BWB with every variable at mid-range.</p>
</section>

<section>
  <h2>Where the airfoils come from</h2>
  <div class="three">
    <div class="box"><h3>1 · Project files</h3><p><code>geometry/airfoils/</code>: sections made for this project, e.g. the ONERA M6 and the RIBES scan.</p></div>
    <div class="box"><h3>2 · AERIS database</h3><p><code>data/airfoil_database/</code>: __N_AIRFOILS__ sections, read by name (Selig and Lednicer files).</p></div>
    <div class="box"><h3>3 · NACA formula</h3><p>Any 4- or 5-digit NACA name not found as a file is made from the formula, e.g. <code>naca25118</code> for BlendedNet.</p></div>
  </div>
  <p>In <code>configs/wing.yaml</code> each station takes one name, or a list of candidates that the sampler draws evenly. A single wing can also carry its own four names.</p>
<pre>types:
  conventional:
    airfoils: [naca4415, naca4415, [naca4412, e387], [naca0012, sc20410]]   # b0, b1, b2, b3

# one wing, its own sections
{"root_chord_m": 0.6, ..., "airfoils": ["naca2415", "naca2412", "sc20412", "naca0012"]}</pre>
</section>

<section>
  <h2>Published wings it rebuilds</h2>
  <div class="card">__GIF_REF__</div>
  <p class="cap">Each frame is a wing rebuilt by the same generator, with the same loft, checks and (later) mesher as the sampled wings. BlendedNet wings are made directly from the BlendedNet parameters.</p>
  <div class="card">__PNG_TOP__</div>
  <div class="tbl"><table>
    <thead><tr><th>Wing</th><th>Type</th><th>Size</th><th>What it is for</th><th>How close the copy is</th><th>Sources</th></tr></thead>
    <tbody>
__ROWS__
    </tbody>
  </table></div>
  <div class="card">__PNG_CRM__</div>
  <p class="cap">NASA CRM against its published 21-station table. Chords match exactly; with four stations the twist is off by at most 0.51°.</p>
</section>

<section class="weak">
  <h2>Limits to know before validating</h2>
  <ul>
    <li><strong>ONERA M6 and NASA CRM are transonic cases</strong> (Mach 0.84–0.85). Phase 1 stops at Mach 0.3, so for now they test the shape and the mesher, not the flow. <strong>RIBES</strong> is the one in-regime case (40 m/s, Re 1.43 × 10⁶).</li>
    <li><strong>CRM is approximate.</strong> Its real twist and sections vary along 21 stations; four stations and SC(2) stand-in sections are not enough to validate drag. That needs the real CRM sections and more stations.</li>
    <li><strong>BlendedNet:</strong> sections as in BlendedNet++ (the first BlendedNet used fixed CST sections whose values are not published). Twist and dihedral are not stated in the papers and are set to zero. The trailing edge of NACA 25118 follows the classic open-edge formula; OpenVSP may close it differently.</li>
    <li><strong>RIBES:</strong> the fitted section's trailing edge (0.26 % chord) is thinner than the 0.38–0.66 % measured on the model.</li>
    <li><strong>Tips are flat cuts</strong> on every wing, including the M6, whose model tip is rounded.</li>
    <li>The final loft and its checks run where pyGeo is installed: <code>python -m cfdauto.geometry.published_wings --build all</code>.</li>
  </ul>
</section>

<section>
  <h2>Commands</h2>
<pre>cd CFD_Automation/geometry
python -m cfdauto.geometry.published_wings --list              # the published wings
python -m cfdauto.geometry.published_wings --build onera_m6    # loft, measure, label, check (pyGeo)
python scripts/make_generator_visuals.py                       # the GIFs and pictures
python scripts/make_generator_page.py                          # this page</pre>
</section>

<footer>Generated by <code>CFD_Automation/geometry/scripts/make_generator_page.py</code>. Definitions and sources: <code>configs/published_wings.yaml</code>.</footer>
</div>
"""


def main() -> None:
    page = (PAGE.replace("__GIF_BUILD__", img("how_a_wing_is_built.gif", "Seven-step animation of one wing being built"))
                .replace("__GIF_REF__", img("published_wings.gif", "Animation of the published wings rebuilt by the generator"))
                .replace("__PNG_TOP__", img("published_wings_topviews.png", "Top views of all published wings"))
                .replace("__PNG_CRM__", img("crm_check.png", "CRM chord and twist against the published table"))
                .replace("__N_AIRFOILS__", f"{len(airfoils.available()):,}")
                .replace("__ROWS__", rows()))
    out = DOCS / "GEOMETRY_GENERATOR.html"
    out.write_text(page)
    print(f"{out}  {out.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
