"""Build docs/REFINE_MAP.html: the refine map at the Re levels (7 Nov; figures and numbers from
data/studies/refine_map_re.json), then the interactive first-approach map of where to refine, per wing (the record).

    python scripts/refine_map_re.py && python scripts/refine_map_data.py && python scripts/make_refine_page.py
"""

from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.paths import STAGE2  # noqa: E402

DATA = STAGE2 / "data" / "studies" / "refine_map_reference.json"        # the first approach (3 Nov; from -5 deg on 7 Nov)
DATA_RE = STAGE2 / "data" / "studies" / "refine_map_re.json"           # the Re levels (7 Nov; scripts/refine_map_re.py)
PAGE = STAGE2 / "docs" / "page"
OUT = STAGE2 / "docs" / "REFINE_MAP.html"
UPPER_CHECK = STAGE2 / "data" / "studies" / "upper_band_check.json"     # the upper band written 0-100 % c: the cost

HEAD = """<title>Where To Refine</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* layout: a control strip, then a 2 x 2 grid of half-wing planforms (condition | envelope) x (upper | lower), then readouts */
:root {
  --bg: #F3F6F9; --surface: #FFFFFF; --ink: #142230; --muted: #566573; --line: #D6DEE6; --grp: #E8EEF4;
  --accent: #0C5EA8; --good: #2E8B57; --warn: #B02A20; --amber: #9A6200; --violet: #6A4BB0;
  --lam: #CFE3F5; --turb: #D9DEE4; --bub: #E9B84A; --sep: #E07B72; --tr: #142230; --band: rgba(154, 98, 0, 0.28); --gen: #6A4BB0;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif; --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F; --grp: #1C2732;
  --accent: #62AEF2; --good: #5FC48F; --warn: #F08A80; --amber: #E7B24F; --violet: #B49BF0;
  --lam: #22405C; --turb: #2A3540; --bub: #B88A2A; --sep: #A64A42; --tr: #E4ECF3; --band: rgba(231, 178, 79, 0.30); --gen: #B49BF0; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F; --grp: #1C2732;
  --accent: #62AEF2; --good: #5FC48F; --warn: #F08A80; --amber: #E7B24F; --violet: #B49BF0;
  --lam: #22405C; --turb: #2A3540; --bub: #B88A2A; --sep: #A64A42; --tr: #E4ECF3; --band: rgba(231, 178, 79, 0.30); --gen: #B49BF0; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.5; margin: 0;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 24px 56px; }
.wrap { max-width: 1180px; margin: 0 auto; display: flex; flex-direction: column; gap: 22px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { font-family: var(--display); font-size: clamp(30px, 5vw, 42px); line-height: 1.05; margin: 0; text-wrap: balance; }
h2 { font-family: var(--display); font-size: 24px; margin: 0; }
h3 { font-family: var(--display); font-size: 18px; margin: 0; font-weight: 600; }
p { margin: 0; max-width: 80ch; }
.lede { color: var(--muted); font-size: 16px; }
.controls { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px 18px; }
.ctl { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.ctl label, .ctl .lab { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.ctl .val { font-family: var(--mono); font-size: 13px; color: var(--ink); font-variant-numeric: tabular-nums; }
.seg { display: flex; flex-wrap: wrap; gap: 4px; }
.seg button { font: 600 13px var(--body); padding: 4px 10px; border: 1px solid var(--line); background: var(--grp); color: var(--ink); border-radius: 4px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--accent); color: #fff; border-color: var(--accent); }
.seg button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
input[type=range] { width: 100%; accent-color: var(--accent); }
.range2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 720px) { .grid2 { grid-template-columns: 1fr; } }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.panel h3 { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 2px 8px; align-items: baseline; }
.panel h3 small { font-family: var(--mono); font-size: 11px; color: var(--muted); font-weight: 400; letter-spacing: .04em; }
svg.plan { width: 100%; height: auto; display: block; max-width: 100%; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; color: var(--muted); align-items: center; }
.legend i { display: inline-block; width: 14px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; border: 1px solid var(--line); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.card h3 { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.card .big { font-family: var(--display); font-size: 26px; line-height: 1.1; font-variant-numeric: tabular-nums; }
.card p { font-size: 13px; color: var(--muted); }
.card.warn { border-color: var(--warn); } .card.warn .big { color: var(--warn); }
.card.good { border-color: var(--good); } .card.good .big { color: var(--good); }
.card.amber { border-color: var(--amber); } .card.amber .big { color: var(--amber); }
.tbl { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 760px; }
th, td { text-align: left; vertical-align: top; padding: 6px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
th { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
td.num { font-family: var(--mono); font-size: 12px; font-variant-numeric: tabular-nums; }
.box { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.box h3 { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.box ul { margin: 0; padding-left: 18px; font-size: 14px; } .box li { margin-bottom: 4px; }
.box.warnb { border-left: 4px solid var(--warn); }
.box.goodb { border-left: 4px solid var(--good); }
#tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--line); border-radius: 5px;
  padding: 8px 10px; font-family: var(--mono); font-size: 11.5px; line-height: 1.45; box-shadow: 0 4px 16px rgba(0,0,0,.18); max-width: 300px; z-index: 20; white-space: pre; }
details summary { cursor: pointer; font-family: var(--display); font-size: 18px; font-weight: 600; }
code { font-family: var(--mono); font-size: 12.5px; overflow-wrap: anywhere; white-space: normal; }
section, details, .tbl { min-width: 0; max-width: 100%; }
.chg { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--amber); border-radius: 6px; padding: 10px 14px; font-size: 14.5px; line-height: 1.5; }
.chg .ctag { display: block; font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--amber); margin-bottom: 2px; }
.re { display: flex; flex-direction: column; gap: 14px; }
.fig { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.fig img { width: 100%; height: auto; display: block; border-radius: 4px; background: #fff; }
.fig img.tall { max-width: 620px; margin: 0 auto; }
.fig img.mid { max-width: 760px; margin: 0 auto; }
.fig p { font-size: 14.5px; }
.fig .k { font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin-right: 6px; }
.fig .k.c { color: var(--accent); }
.record { border-top: 2px solid var(--ink); padding-top: 12px; display: flex; flex-direction: column; gap: 6px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
"""

BODY = """
<div class="wrap">
<header>
  <div class="eyebrow">CFD_Automation · Stage 2 · refine map · from the Stage 1 section tables · 3 Nov 2026 · updated 8 Nov 2026</div>
  <h1>Where to refine: transition, bubbles and separation, per wing</h1>
  <p class="lede">The transition band of the mesh is generic: one band for every wing. First (2–3 Nov) it was upper surface 0–85 % c, lower 60–100 % c. Since 7 Nov the lower band runs from the leading edge, 0–100 % c (decision 74). The upper band is still written 0–85 % c, but as built the upper side gets band-size cells to the trailing edge too, because both sides share one node list. This page reads the Stage 1 section tables for one wing at a time and shows where the flow turns turbulent, where the laminar bubbles sit and where it separates, strip by strip. First section: the map at the four Re levels on the mean chord (7 Nov, new). Below it, the interactive first-approach map, kept as the record.</p>
</header>
__RE_SECTION__
<section class="record">
  <h2>The first approach (3 Nov; run again from −5° on 7 Nov): the interactive map, kept as the record</h2>
  <p>Each wing at its real size and flight speed (Mach 0.03–0.20 at sea level), the old 20 reference wings, the section tables before the nose fix, and the first generic band (upper 0–85 % c, lower 60–100 % c, dashed). The numbers and the misses below are the first approach's; the section above replaces them.</p>
  <div class="chg"><span class="ctag">Updated 7 Nov 2026: the map runs from −5°</span>The angles now run from −5° to post-stall (decided 6 Nov). So the map was run again for root angles −5° to 12° (it started at −2°). The envelope now starts at −5° by default and still stops at 8°: only the low end changes, so its effect is seen alone, and the top of the steady range (stall onset) is not set yet. The sliders reach 12°. <strong>What it shows for the lower side:</strong> at −5° the lower side turns turbulent close to the nose (median 1–15 % c over the strips, per wing type), and its transition or bubble sits in front of the generic lower band (60 % c) on every strip that has an answer. Already at 0° that is so on 51–83 % of the strips. At −5° many outboard strips of the BWBs and flying wings (MH 61, MH 45, at local angles of −6° to −11°) have no XFOIL answer: 42 % and 30 % of their strips (hatched). The two options for the lower band are counted in Study 8 of the Stage 2 page (decision 74). As before: the map is the 2-D XFOIL strip answer in calm air at real wing size, a candidate (decision 65), not a rule, and the cost card uses the first approach's band cell (bubble length / 20).</div>
  <div class="chg"><span class="ctag">Updated 7 Nov 2026, evening: what changed in the mesh since</span><strong>The lower band now runs from the leading edge</strong> (decision 74, option A, chosen by Mike on 7 Nov and built): it costs no cells, because both sides of a ring share one node list (Study 8 of the Stage 2 page). The dashed generic band on this page is still the first one (lower 60–100 % c), so the misses it shows on the lower side are what the new band covers. <strong>The new rules are built</strong> (levels VC, C, M, F; band cell = bubble length / 20 at F, with the bubble length at least 0.10 c from local Re 4 × 10⁵): the cost cards here still use the first approach's band cell. <strong>Similarity is built in Stage 1</strong> (every wing at unit mean chord; 13 of the 20 reference wings are new picks): this map still shows the old 20 reference wings at real size. Done on 7 Nov: the map per Re level on the new reference wings, the section above.</div>
</section>

<section class="controls" aria-label="Controls">
  <div class="ctl"><span class="lab">Wing type</span><div class="seg" id="typeSeg"></div></div>
  <div class="ctl"><span class="lab">Reference wing</span><div class="seg" id="idxSeg"></div></div>
  <div class="ctl"><label for="mach">Flight Mach (one condition, and the Re the mesh is built for)</label><input type="range" id="mach" min="0" max="6" step="1" value="2"><span class="val" id="machV"></span></div>
  <div class="ctl"><label for="alpha">Angle of attack at the root (one condition)</label><input type="range" id="alpha" min="0" max="__A_MAX__" step="1" value="__A_ONE__"><span class="val" id="alphaV"></span></div>
  <div class="ctl"><span class="lab">Envelope: angle range</span><div class="range2"><input type="range" id="aLo" min="0" max="__A_MAX__" step="1" value="__A_LO__" aria-label="lowest angle"><input type="range" id="aHi" min="0" max="__A_MAX__" step="1" value="__A_HI__" aria-label="highest angle"></div><span class="val" id="aRangeV"></span></div>
  <div class="ctl"><span class="lab">Envelope: Mach range</span><div class="range2"><input type="range" id="mLo" min="0" max="6" step="1" value="0" aria-label="lowest Mach"><input type="range" id="mHi" min="0" max="6" step="1" value="4" aria-label="highest Mach"></div><span class="val" id="mRangeV"></span></div>
  <div class="ctl"><label for="margin">Margin around the transition point</label><input type="range" id="margin" min="0" max="25" step="1" value="10"><span class="val" id="marginV"></span></div>
</section>

<section>
  <div class="legend"><span><i style="background:var(--lam)"></i>laminar</span><span><i style="background:var(--bub)"></i>laminar separation bubble</span><span><i style="background:var(--turb)"></i>turbulent</span><span><i style="background:var(--sep)"></i>separated to the trailing edge</span><span><i style="background:var(--tr); width: 3px"></i>transition point</span><span><i style="background:var(--band)"></i>band this wing needs (envelope + margin)</span><span><i style="border: 2px dashed var(--gen); background: none"></i>generic band</span><span><i style="background: repeating-linear-gradient(45deg, var(--turb) 0 3px, var(--surface) 3px 6px)"></i>no XFOIL answer (past 2-D stall)</span></div>
  <div class="grid2">
    <div class="panel"><h3>Upper surface at this condition <small id="condLabU"></small></h3><svg class="plan" id="pUc" role="img" aria-label="upper surface at one condition"></svg></div>
    <div class="panel"><h3>Upper surface: envelope over the ranges <small id="envLabU"></small></h3><svg class="plan" id="pUe" role="img" aria-label="upper surface envelope"></svg></div>
    <div class="panel"><h3>Lower surface at this condition <small id="condLabL"></small></h3><svg class="plan" id="pLc" role="img" aria-label="lower surface at one condition"></svg></div>
    <div class="panel"><h3>Lower surface: envelope over the ranges <small id="envLabL"></small></h3><svg class="plan" id="pLe" role="img" aria-label="lower surface envelope"></svg></div>
  </div>
  <p style="color: var(--muted); font-size: 13px">Half wing seen from above, root on the left, leading edge at the top; the air comes from the top. One bar per strip (3 per panel plus the breaks). Hover or tap a bar for its numbers.</p>
</section>

<section>
  <h2>What the envelope costs and saves</h2>
  <div class="cards" id="cards"></div>
</section>

<section>
  <details><summary>Every strip, at this condition and over the envelope</summary>
  <div class="tbl" style="margin-top: 8px"><table id="stripTable"></table></div></details>
</section>

<section class="grid2">
  <div class="box warnb"><h3>Limits of this map</h3><ul>
    <li>2-D strips: each strip is an XFOIL run of its section, free transition with N_crit 9 (calm air). Gusty air (N_crit 5) moves transition forward and shortens the laminar run; add margin for it.</li>
    <li>One induced angle for the whole wing (elliptic): the local angle of attack along the span is root angle + twist − that one number. On swept and tapered wings the real local angle differs along the span; the tip is usually unloaded more than this says.</li>
    <li>No crossflow transition on swept panels, no 3-D relief of bubbles, no tip vortex. Panels swept over about 25° with Re normal to the edge above 10⁶ can transition near the leading edge; the generic band's 0 % c start on the upper surface covers that, this map does not.</li>
    <li>Hatched strips had no XFOIL answer: past the section's 2-D stall, at high angle or at negative angle. At −5° these are mostly the washed-out outboard strips of the BWBs and flying wings (local angles −6° to −11°; some are below the tables' −10°). A strip with no answer anywhere in the range falls back to the generic band; a strip with some answers keeps only those.</li>
    <li>The dataset is the Stage 1 section tables (14 Re × 3 Mach × 49 angles per section, trilinear lookup); a strip between two sections takes the blend of its parents' answers.</li>
  </ul></div>
  <div class="box goodb"><h3>What would make it better, and stay cheap</h3><ul>
    <li><strong>AVL (vortex lattice) for the local angle.</strong> Replaces the one induced angle by a spanwise lift distribution that knows sweep, taper and twist: seconds per wing. Biggest correction on swept BWBs and on washed-out tips. Weak on the thick centre body (VLM sees only the camber line) and inviscid, so the strip lift must be fed back (a quasi-3D loop: section cl from the tables, AVL for the downwash, repeat).</li>
    <li><strong>NeuralFoil for the 2-D answer.</strong> A neural surrogate of XFOIL: milliseconds per strip, never fails to converge, takes the exact blended section instead of the parents' blend, and returns the boundary-layer state along the chord, from which separation and bubbles can be read. It inherits XFOIL's physics (2-D, e^N) and adds its own fit error, so check it against the tables on a sample first.</li>
    <li><strong>Neither fixes 3-D transition.</strong> Crossflow on swept panels and tip effects need a criterion of their own or a 3-D transition RANS check (γ-Re_θ in SU2) on a few wings before the per-wing band replaces the generic one. Until then the per-wing band is a candidate, not a rule.</li>
  </ul></div>
</section>

<footer style="color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 12px">Data: <code>Stage_2_surface_mesh/data/studies/refine_map_reference.json</code> from <code>cfdauto.mesh.refine_map</code> (the Stage 1 section tables through <code>cfdauto.flowmap.engine</code>), the 20 reference wings, Mach 0.03–0.20, −5…12° at the root, sea level, 3 strips per panel. Band cell = bubble length (Stage 1 table at the local Re) / 20, at the Mach of the slider. Page: <code>scripts/make_refine_page.py</code>.</footer>
</div>
<div id="tip" hidden></div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  const D = JSON.parse(document.getElementById('data').textContent);
  const TYPES = ['bwb', 'flying_wing', 'cranked', 'tapered'];
  const TNAME = {bwb: 'BWB', flying_wing: 'flying wing', cranked: 'cranked', tapered: 'tapered'};
  const st = {type: 'bwb', idx: 0};
  const $ = id => document.getElementById(id);
  const wingOf = () => D.wings.find(w => w.wing.type === st.type && w.wing.index === st.idx);
  const grid = D.wings[0].grid;
  const NM = grid.mach.length, NA = grid.alpha_deg.length;
  const fmt = (v, d) => (v == null || !isFinite(v)) ? '–' : Number(v).toFixed(d).replace(/^-/, '−');
  const deg = v => fmt(v, 0) + '°';
  const pct = v => (v == null || !isFinite(v)) ? '–' : (100 * v).toFixed(0) + ' %';
  const sci = v => { if (v == null || !isFinite(v)) return '–'; const e = Math.floor(Math.log10(v)); return (v / Math.pow(10, e)).toFixed(1) + ' × 10' + String(e).replace(/\\d/g, c => '⁰¹²³⁴⁵⁶⁷⁸⁹'[c]); };

  // the band-cell rule of the mesher, in the browser: bubble length from the Stage 1 table (log-log), / 20, capped at 2 % c
  function bubbleLen(re) { const t = D.rules.bubble_table; const lr = t.re.map(Math.log), ll = t.l_c.map(Math.log); const x = Math.log(re);
    if (x <= lr[0]) return t.l_c[0]; if (x >= lr[lr.length - 1]) return t.l_c[t.l_c.length - 1];
    for (let i = 1; i < lr.length; i++) if (x <= lr[i]) { const f = (x - lr[i - 1]) / (lr[i] - lr[i - 1]); return Math.exp(ll[i - 1] + f * (ll[i] - ll[i - 1])); } return t.l_c[0]; }
  const bandCell = re => Math.min(bubbleLen(re) / D.rules.nodes_per_bubble, D.rules.max_spacing_c);

  // segmented controls
  function seg(el, items, get, set) { el.innerHTML = ''; items.forEach(([v, label]) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
    b.setAttribute('aria-pressed', String(get() === v)); b.addEventListener('click', () => { set(v); render(); }); el.appendChild(b); }); }
  function buildSegs() { seg($('typeSeg'), TYPES.map(t => [t, TNAME[t]]), () => st.type, v => { st.type = v; });
    seg($('idxSeg'), [0, 1, 2, 3, 4].map(i => [i, 'wing ' + i]), () => st.idx, v => { st.idx = v; }); }
  ['mach', 'alpha', 'aLo', 'aHi', 'mLo', 'mHi', 'margin'].forEach(id => $(id).addEventListener('input', render));

  function field(w, name) { return w.fields[name]; }
  function val(w, name, i, k) { const v = w.fields[name][i * w.shape[1] + k]; return (v == null) ? NaN : v; }

  // the envelope per strip and side (the same rule as cfdauto.mesh.refine_map.envelope_band)
  function envelope(w, im0, im1, ia0, ia1, margin) {
    const n = w.shape[0]; const out = {upper: [], lower: [], shortest: {upper: [], lower: []}, fallback: [], missing: 0, total: 0};
    for (let i = 0; i < n; i++) {
      let any = false;
      for (const side of ['upper', 'lower']) {
        const xk = side === 'upper' ? 'xtr_u' : 'xtr_l', bs = side === 'upper' ? 'bub_u_s' : 'bub_l_s', be = side === 'upper' ? 'bub_u_e' : 'bub_l_e', sp = side === 'upper' ? 'sep_u_x' : 'sep_l_x';
        let lo = Infinity, hi = -Infinity, shortest = Infinity;
        for (let im = im0; im <= im1; im++) for (let ia = ia0; ia <= ia1; ia++) { const k = im * NA + ia; const ok = w.fields.answered[i * w.shape[1] + k];
          if (side === 'upper') { out.total++; if (!ok) out.missing++; } if (!ok) continue; any = true;
          const x = val(w, xk, i, k), s = val(w, bs, i, k), e = val(w, be, i, k), q = val(w, sp, i, k);
          if (isFinite(x)) { lo = Math.min(lo, x - margin); hi = Math.max(hi, x + margin); }
          if (isFinite(s)) lo = Math.min(lo, s); if (isFinite(e)) hi = Math.max(hi, e); if (isFinite(q)) hi = Math.max(hi, q);
          if (isFinite(s) && isFinite(e)) shortest = Math.min(shortest, e - s); }
        if (!isFinite(lo)) { out[side].push(D.rules.generic_band[side].slice()); out.shortest[side].push(null); }
        else { out[side].push([Math.max(0, lo), Math.min(1, hi)]); out.shortest[side].push(isFinite(shortest) ? shortest : null); }
      }
      out.fallback.push(!any);
    }
    return out;
  }

  // planform drawing: span along svg x, chord along svg y (leading edge at the top)
  function planform(svg, w, paint, overlays) {
    const S = w.wing.stations; const yS = S.y, xle = S.x_le, ch = S.chord; const n = w.shape[0];
    const xmin = Math.min(...xle), xmax = Math.max(...xle.map((x, j) => x + ch[j])); const span = yS[yS.length - 1];
    const W = 600, pad = 10; const sc = (W - 2 * pad) / span; const H = (xmax - xmin) * sc + 2 * pad + 14;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.innerHTML = '';
    const X = y => pad + y * sc, Y = x => pad + (x - xmin) * sc;
    const ns = 'http://www.w3.org/2000/svg';
    const el = (t, a) => { const e = document.createElementNS(ns, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
    const defs = el('defs', {}); const pat = el('pattern', {id: 'hatch' + svg.id, width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)'});
    pat.appendChild(el('rect', {width: 6, height: 6, fill: 'var(--surface)'})); pat.appendChild(el('rect', {width: 3, height: 6, fill: 'var(--turb)'})); defs.appendChild(pat); svg.appendChild(defs);
    // strip bars: each a quadrilateral that follows the planform between its two edges (linear between stations)
    const lerp = (arr, y) => { for (let j = 1; j < yS.length; j++) if (y <= yS[j] + 1e-12) { const f = (y - yS[j - 1]) / (yS[j] - yS[j - 1]); return arr[j - 1] + f * (arr[j] - arr[j - 1]); } return arr[arr.length - 1]; };
    const quad = (y0, y1, a, b) => `${X(y0)},${Y(lerp(xle, y0) + a * lerp(ch, y0))} ${X(y1)},${Y(lerp(xle, y1) + a * lerp(ch, y1))} ${X(y1)},${Y(lerp(xle, y1) + b * lerp(ch, y1))} ${X(y0)},${Y(lerp(xle, y0) + b * lerp(ch, y0))}`;
    const ys = w.strips.y; const edges = [0]; for (let i = 1; i < n; i++) edges.push(0.5 * (ys[i - 1] + ys[i])); edges.push(span);
    for (let i = 0; i < n; i++) {
      const y0 = edges[i], y1 = edges[i + 1];
      const g = el('g', {'data-i': i}); const segs = paint(i);                   // [{a, b, fill, stroke?}] fractions of the chord
      for (const s of segs) { if (s.b <= s.a) continue;
        g.appendChild(el('polygon', {points: quad(y0, y1, s.a, s.b), fill: s.fill, stroke: s.stroke || 'none', 'stroke-width': s.sw || 0, 'stroke-dasharray': s.dash || 'none', opacity: s.op == null ? 1 : s.op})); }
      for (const s of segs) if (s.line != null) { const d = 0.9 / (sc * Math.min(lerp(ch, y0), lerp(ch, y1))); g.appendChild(el('polygon', {points: quad(y0, y1, Math.max(0, s.line - d), Math.min(1, s.line + d)), fill: 'var(--tr)'})); }
      g.addEventListener('mousemove', ev => showTip(ev, w, i)); g.addEventListener('mouseleave', hideTip); g.addEventListener('click', ev => showTip(ev, w, i));
      svg.appendChild(g);
    }
    // overlays that follow the planform over the whole span (the generic band), then the outline on top
    for (const o of (overlays || [])) { const pts = yS.map((y, j) => `${X(y)},${Y(xle[j] + o.a * ch[j])}`).concat(yS.map((y, j) => `${X(y)},${Y(xle[j] + o.b * ch[j])}`).reverse()).join(' ');
      svg.appendChild(el('polygon', {points: pts, fill: 'none', stroke: o.stroke, 'stroke-width': 1.4, 'stroke-dasharray': '5 3'})); }
    const pts = yS.map((y, j) => `${X(y)},${Y(xle[j])}`).concat(yS.map((y, j) => `${X(y)},${Y(xle[j] + ch[j])}`).reverse()).join(' ');
    svg.appendChild(el('polygon', {points: pts, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 1.2}));
    yS.forEach((y, j) => { if (j > 0 && j < yS.length - 1) svg.appendChild(el('line', {x1: X(y), y1: Y(xle[j]), x2: X(y), y2: Y(xle[j] + ch[j]), stroke: 'var(--ink)', 'stroke-width': 0.6, 'stroke-dasharray': '3 3'})); });
    const t = el('text', {x: pad, y: H - 3, 'font-family': 'var(--mono)', 'font-size': 10, fill: 'var(--muted)'}); t.textContent = `root ← semi-span ${w.wing.semi_span_m.toFixed(2)} m → tip · chord ${(w.wing.stations.chord[0] * 100).toFixed(0)} → ${(w.wing.stations.chord[w.wing.stations.chord.length - 1] * 100).toFixed(0)} cm`; svg.appendChild(t);
  }

  let tipCtx = null;
  function showTip(ev, w, i) {
    const k = cur.k; const E = cur.env; const tip = $('tip');
    const a = w.fields.answered[i * w.shape[1] + k];
    const line = (name, v) => `${name.padEnd(14)} ${v}`;
    const bu = isFinite(val(w, 'bub_u_s', i, k)) ? `${pct(val(w, 'bub_u_s', i, k))} → ${pct(val(w, 'bub_u_e', i, k))}` : 'none';
    const bl = isFinite(val(w, 'bub_l_s', i, k)) ? `${pct(val(w, 'bub_l_s', i, k))} → ${pct(val(w, 'bub_l_e', i, k))}` : 'none';
    tip.textContent = [`strip ${i}  y/S ${w.strips.y_over_S[i].toFixed(2)}  ${w.strips.section[i]}`,
      line('chord', (w.strips.chord[i] * 100).toFixed(1) + ' cm'), line('local Re', sci(val(w, 're', i, k))), line('local angle', fmt(val(w, 'alpha_local', i, k), 1) + '°'),
      a ? line('upper: trans.', pct(val(w, 'xtr_u', i, k))) : 'no XFOIL answer at this condition', a ? line('upper: bubble', bu) : '', a ? line('lower: trans.', pct(val(w, 'xtr_l', i, k))) : '', a ? line('lower: bubble', bl) : '',
      isFinite(val(w, 'sep_u_x', i, k)) ? line('upper: separ.', 'from ' + pct(val(w, 'sep_u_x', i, k))) : '',
      '', `envelope band  upper ${pct(E.upper[i][0])}–${pct(E.upper[i][1])}  lower ${pct(E.lower[i][0])}–${pct(E.lower[i][1])}` + (E.fallback[i] ? '  (generic: no answer)' : ''),
      E.shortest.upper[i] != null ? line('shortest bubble', pct(E.shortest.upper[i]) + ' c (upper); table ' + pct(bubbleLen(val(w, 're', i, k))) + ' c') : ''].filter(s => s !== '').join('\\n');
    tip.hidden = false; const x = Math.min(ev.clientX + 14, window.innerWidth - 310), y = Math.min(ev.clientY + 14, window.innerHeight - 180); tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function hideTip() { $('tip').hidden = true; }

  const cur = {k: 0, env: null};
  function render() {
    const w = wingOf(); const n = w.shape[0];
    const im = +$('mach').value, ia = +$('alpha').value; const k = im * NA + ia; cur.k = k;
    let im0 = +$('mLo').value, im1 = +$('mHi').value, ia0 = +$('aLo').value, ia1 = +$('aHi').value; if (im0 > im1) [im0, im1] = [im1, im0]; if (ia0 > ia1) [ia0, ia1] = [ia1, ia0];
    const margin = +$('margin').value / 100;
    $('machV').textContent = `Mach ${grid.mach[im].toFixed(2)} · Re on the mean chord ${sci(w.per_condition.re_mean[k])}`;
    $('alphaV').textContent = `${deg(grid.alpha_deg[ia])} at the root · induced ${fmt(w.per_condition.alpha_induced_deg[k], 1)}° · wing CL ${fmt(w.per_condition.cl_wing[k], 2)}`;
    $('aRangeV').textContent = `${deg(grid.alpha_deg[ia0])} to ${deg(grid.alpha_deg[ia1])}`;
    $('mRangeV').textContent = `Mach ${grid.mach[im0].toFixed(2)} to ${grid.mach[im1].toFixed(2)}` + (grid.mach[im1] > D.focus_mach[w.wing.family][1] + 1e-9 ? ' (above the focus range of this family)' : '');
    $('marginV').textContent = `± ${(margin * 100).toFixed(0)} % of the chord`;
    document.querySelectorAll('#typeSeg button').forEach((b, j) => b.setAttribute('aria-pressed', String(TYPES[j] === st.type)));
    document.querySelectorAll('#idxSeg button').forEach((b, j) => b.setAttribute('aria-pressed', String(j === st.idx)));
    const E = envelope(w, im0, im1, ia0, ia1, margin); cur.env = E;
    const condPaint = side => i => { const k2 = k; if (!w.fields.answered[i * w.shape[1] + k2]) return [{a: 0, b: 1, fill: 'url(#hatch' + (side === 'upper' ? 'pUc' : 'pLc') + ')'}];
      const x = val(w, side === 'upper' ? 'xtr_u' : 'xtr_l', i, k2), s = val(w, side === 'upper' ? 'bub_u_s' : 'bub_l_s', i, k2), e = val(w, side === 'upper' ? 'bub_u_e' : 'bub_l_e', i, k2), q = val(w, side === 'upper' ? 'sep_u_x' : 'sep_l_x', i, k2);
      const segs = [{a: 0, b: isFinite(x) ? x : 1, fill: 'var(--lam)'}, {a: isFinite(x) ? x : 1, b: 1, fill: 'var(--turb)'}];
      if (isFinite(s) && isFinite(e)) segs.push({a: s, b: e, fill: 'var(--bub)'}); if (isFinite(q)) segs.push({a: q, b: 1, fill: 'var(--sep)'}); if (isFinite(x)) segs.push({a: 0, b: 0, fill: 'none', line: x}); return segs; };
    const envPaint = side => i => { const g = D.rules.generic_band[side]; const b = E[side][i];
      const segs = [{a: 0, b: 1, fill: E.fallback[i] ? 'url(#hatch' + (side === 'upper' ? 'pUe' : 'pLe') + ')' : 'var(--surface)'}];
      if (!E.fallback[i]) segs.push({a: b[0], b: b[1], fill: 'var(--band)'});
      return segs; };
    planform($('pUc'), w, condPaint('upper')); planform($('pLc'), w, condPaint('lower')); const G0 = D.rules.generic_band; planform($('pUe'), w, envPaint('upper'), [{a: G0.upper[0], b: G0.upper[1], stroke: 'var(--gen)'}]); planform($('pLe'), w, envPaint('lower'), [{a: G0.lower[0], b: G0.lower[1], stroke: 'var(--gen)'}]);
    const cl = `Mach ${grid.mach[im].toFixed(2)}, ${deg(grid.alpha_deg[ia])}`; $('condLabU').textContent = cl; $('condLabL').textContent = cl;
    const el_ = `Mach ${grid.mach[im0].toFixed(2)}–${grid.mach[im1].toFixed(2)}, ${deg(grid.alpha_deg[ia0])} to ${deg(grid.alpha_deg[ia1])}, margin ${(margin * 100).toFixed(0)} % c`; $('envLabU').textContent = el_; $('envLabL').textContent = el_;
    // cost: band cells per strip at the Re of the slider's Mach, generic against this wing's envelope
    let gen = 0, own = 0, nFall = 0, missedU = 0, missedL = 0; const rows = [];
    for (let i = 0; i < n; i++) { const re = val(w, 're', i, k); const h = bandCell(re); const G = D.rules.generic_band;
      const gu = (G.upper[1] - G.upper[0]) / h, gl = (G.lower[1] - G.lower[0]) / h; const ou = (E.upper[i][1] - E.upper[i][0]) / h, ol = (E.lower[i][1] - E.lower[i][0]) / h;
      gen += gu + gl; own += ou + ol; if (E.fallback[i]) nFall++;
      if (!E.fallback[i]) { missedU = Math.max(missedU, Math.max(0, E.upper[i][1] - G.upper[1]) + Math.max(0, G.upper[0] - E.upper[i][0])); missedL = Math.max(missedL, Math.max(0, E.lower[i][1] - G.lower[1]) + Math.max(0, G.lower[0] - E.lower[i][0])); }
      rows.push({i, re, h, ou, ol, gu, gl}); }
    const shortU = E.shortest.upper.filter(v => v != null); const tabRoot = bubbleLen(val(w, 're', 0, k)); const shortRoot = E.shortest.upper[0];
    const cards = [
      {cls: own < gen ? 'good' : 'amber', h: 'band cells along the chord, summed over the strips', big: `${Math.round(own)} vs ${Math.round(gen)}`, p: `this wing's envelope against the generic band, at the Re of Mach ${grid.mach[im].toFixed(2)} (band cell 0.25–2 % c by local Re). ${own < gen ? 'Saves ' + Math.round(100 * (1 - own / gen)) + ' %.' : 'Costs ' + Math.round(100 * (own / gen - 1)) + ' % more: the envelope is wider than the generic band on some strips.'}`},
      {cls: (missedU > 0.02 || missedL > 0.02) ? 'warn' : 'good', h: 'what the generic band would miss', big: `upper ${pct(missedU)} c · lower ${pct(missedL)} c`, p: 'the widest stretch of any strip\\'s envelope that lies outside the generic band. Above zero means the generic band is wrong in place, not only in size, for this wing and these conditions.'},
      {cls: (nFall || E.missing) ? 'warn' : 'good', h: 'strips without an XFOIL answer', big: `${nFall} of ${n}`, p: nFall ? 'past the section\\'s 2-D stall everywhere in the range: those strips keep the generic band (hatched).' : (E.missing ? `every strip has an answer somewhere in the range, but ${pct(E.missing / E.total)} of the strip-conditions have none (past the 2-D stall, at high or at negative angle): they are left out of the envelope.` : 'every strip answered at every condition in the range.')},
      {cls: 'amber', h: 'shortest bubble on the root strip', big: shortRoot != null ? `${pct(shortRoot)} c vs table ${pct(tabRoot)} c` : `none vs table ${pct(tabRoot)} c`, p: 'the shortest upper-surface bubble the dataset predicts at the root over the range, against the bubble length the band-cell rule assumes at the root\\'s Re. Shorter than the table means 20 cells per bubble is not met there; the rule is per Re, not per wing.'},
    ];
    $('cards').innerHTML = cards.map(c => `<div class="card ${c.cls}"><h3>${c.h}</h3><div class="big">${c.big}</div><p>${c.p}</p></div>`).join('');
    const G = D.rules.generic_band;
    $('stripTable').innerHTML = '<tr><th>strip</th><th>y/S</th><th>section</th><th>chord</th><th>local Re</th><th>local α</th><th>upper: transition</th><th>upper: bubble</th><th>lower: transition</th><th>lower: bubble</th><th>band upper (envelope)</th><th>band lower (envelope)</th><th>cells upper / generic</th><th>cells lower / generic</th></tr>' +
      rows.map(r => { const i = r.i; const a = w.fields.answered[i * w.shape[1] + k];
        const bu = isFinite(val(w, 'bub_u_s', i, k)) ? `${pct(val(w, 'bub_u_s', i, k))}–${pct(val(w, 'bub_u_e', i, k))}` : '–'; const bl = isFinite(val(w, 'bub_l_s', i, k)) ? `${pct(val(w, 'bub_l_s', i, k))}–${pct(val(w, 'bub_l_e', i, k))}` : '–';
        return `<tr><td class="num">${i}</td><td class="num">${w.strips.y_over_S[i].toFixed(2)}</td><td>${w.strips.section[i]}</td><td class="num">${(w.strips.chord[i] * 100).toFixed(1)} cm</td><td class="num">${sci(r.re)}</td><td class="num">${fmt(val(w, 'alpha_local', i, k), 1)}°</td><td class="num">${a ? pct(val(w, 'xtr_u', i, k)) : 'no answer'}</td><td class="num">${a ? bu : '–'}</td><td class="num">${a ? pct(val(w, 'xtr_l', i, k)) : 'no answer'}</td><td class="num">${a ? bl : '–'}</td><td class="num">${pct(E.upper[i][0])}–${pct(E.upper[i][1])}${E.fallback[i] ? ' (generic)' : ''}</td><td class="num">${pct(E.lower[i][0])}–${pct(E.lower[i][1])}${E.fallback[i] ? ' (generic)' : ''}</td><td class="num">${Math.round(r.ou)} / ${Math.round(r.gu)}</td><td class="num">${Math.round(r.ol)} / ${Math.round(r.gl)}</td></tr>`; }).join('');
  }
  buildSegs(); render();
})();
</script>
"""


TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
RE_NAME = {1e5: "10⁵", 3e5: "3 × 10⁵", 1e6: "10⁶", 1.5e6: "1.5 × 10⁶", 3e6: "3 × 10⁶", 4e6: "4 × 10⁶"}
FIG_CLASS = {"refine_re_transition.png": "tall", "refine_re_coverage.png": "mid", "refine_re_no_answer.png": "mid"}


def _img(name: str, alt: str) -> str:
    data = base64.b64encode((PAGE / name).read_bytes()).decode()
    return f'<img class="{FIG_CLASS.get(name, "")}" src="data:image/png;base64,{data}" alt="{html.escape(alt)}" loading="lazy">'


def _sci(v: float) -> str:
    m, e = f"{v:.1e}".split("e")
    sup = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    return f"{m} × 10{str(int(e)).translate(sup)}"


def re_section() -> str:
    """The refine map at the Re levels (7 Nov): what was done, the upper-side table, the three figures with what
    each shows and the conclusion (captions from refine_map_re.json), the as-built check and the upper band."""
    d = json.loads(DATA_RE.read_text())
    s, ab = d["summary"], d["as_built"]
    rows = []
    for k, name in ((k, RE_NAME.get(float(k), k)) for k in next(iter(s.values())).keys()):     # the levels the map ran at
        cells = "".join(f"<td class='num'>{100 * s[t][k]['to_8']['upper']['covered_share']:.0f} % "
                        f"({100 * s[t][k]['to_8']['upper']['transition_inside_share']:.0f} %)</td>" for t in TYPES)
        rows.append(f"<tr><td class='num'>{name}</td>{cells}</tr>")
    table = ('<div class="tbl"><table><tr><th>Re on the mean chord</th>' + "".join(f"<th>{TYPE_NAME[t]}</th>" for t in TYPES)
             + "</tr>" + "".join(rows) + "</table></div>")
    figs = []
    for name, cap in d["figures"].items():
        figs.append(f'<div class="fig">{_img(name, cap["what"])}<p><span class="k">What it shows</span>{html.escape(cap["what"])}</p>'
                    f'<p><span class="k c">Conclusion</span>{html.escape(cap["conclusion"])}</p></div>')
    uc = json.loads(UPPER_CHECK.read_text())["levels"]
    vc, f = uc["VC"], uc["F"]
    check = (f" That holds at VC only. On the 20 reference wings × 4 Re (7 Nov): at VC the same mesh to round-off "
             f"({vc['same_counts']} of {vc['builds']} with the same counts, no node moved by more than {_sci(vc['largest_node_move_c'])} c); "
             f"at F, 0–100 % c adds 2 ring nodes on {f['ring_nodes_added'].get('2', 0)} of {f['builds']} builds "
             f"({100 * (f['cells_ratio']['median'] - 1):.2f} % more cells, median; {100 * (f['cells_ratio']['max'] - 1):.2f} % at most), "
             f"because with 0–85 % c the upper cells over 85–100 % c at F can sit a little above the band cell, inside the 1 % check "
             f"(on BWB reference wing 0 at Re 3 × 10⁵: 0.00501 c against 0.0050 c). "
             f"So the written rule stays 0–85 % c: writing 0–100 % c is for the owner to decide, and the screen would need a re-run "
             f"(about 1.5 h). Data: <code>data/studies/upper_band_check.json</code>.")
    n16 = len(ab["builds"])
    return f"""
<section class="re" id="re-levels">
  <h2>Refine map at the Re levels (7 Nov; redone 8 Nov at the new levels)</h2>
  <p><strong>What was done.</strong> The map has a Re mode now (similarity, decision 70): each of the 20 reference wings (5 per type, the new picks) at the four Re levels on the mean chord (10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶ since 8 Nov; the 7 Nov run at 1.5 × 10⁶ and 3 × 10⁶ is kept in <code>data/studies/refine_map_re_levels_7nov.json</code>) and root angles −5° to 12°, at unit mean chord and sea level, with the 2-D section tables read at Mach 0.1 and rebuilt on the fixed nose (decision 64). 13 strips per half wing (3 per panel). For each wing, Re level, strip and side: where transition sits from −5° to 8° (and to 12°); the band it needs, as before (transition ± 10 % c, the bubbles, the separation start); whether the bands hold it; and the strips with no XFOIL answer. Then an as-built check on {n16} built surfaces (wing 0 of each type at the four Re levels, level VC). In the figures, the decided upper band is the written one, 0–85 % c. Code: the Re mode of <code>cfdauto/mesh/refine_map.py</code>; <code>scripts/refine_map_re.py</code>; data <code>data/studies/refine_map_re.json</code>; note <code>decisions/refine_map_re.md</code>.</p>
  <p><strong>Result.</strong> The lower band (0–100 % c) holds every strip at every Re level. The upper band as written (0–85 % c) does not hold the upper transition at low Re and low angle. Share of the strips whose band fits inside 0–85 % c, −5° to 8° (65 strips per type); in brackets, the share whose transition itself stays inside:</p>
  {table}
  <p>Where it does not fit, the cause is always the transition itself (+ 10 % c), never a bubble or a separation: at −5° and Re 10⁵ the median upper transition sits at 88–100 % c, and at 10⁵ some strips stay laminar to the trailing edge.</p>
  {"".join(figs)}
  <div class="chg"><span class="ctag">As built (7 Nov)</span>On all {n16} built surfaces at VC (all passed every check) the largest upper cell over 85–99.5 % c is {ab['upper_ratio_min']:.3f}–{ab['upper_ratio_max']:.3f} × the band cell: the upper side already has band-size cells to the trailing edge, because both sides of a ring share one node list (decision 60) and the lower band is 0–100 % c. So no mesh change is needed. Written as 0–100 % c, the {n16} surfaces come out the same (the same ring counts, no node moved by more than {_sci(ab['largest_node_move_with_upper_0_100_c'])} c, round-off).{check}</div>
  <p><strong>Limits.</strong> 2-D strips (XFOIL e^N, N_crit 9: calm air) with one uniform induced angle; no crossflow transition on swept panels, no 3-D relief of bubbles, no tip effects: where to look, not the 3-D answer. A strip without an answer at one angle drops out at that angle only. The as-built check covers wing 0 of each type. The per-wing band stays a candidate (decision 65) until a 3-D transition check.</p>
</section>"""


ONE_ALPHA, ENVELOPE_ALPHAS = 4.0, (-5.0, 8.0)     # the default condition, and the default envelope: from the new
                                                  # lowest angle (-5 deg, decided 6 Nov) to the first top (8 deg)


def main() -> None:
    data = DATA.read_text()
    alphas = json.loads(data)["wings"][0]["grid"]["alpha_deg"]
    body = (BODY.replace("__A_MAX__", str(len(alphas) - 1)).replace("__A_ONE__", str(alphas.index(ONE_ALPHA)))
            .replace("__A_LO__", str(alphas.index(ENVELOPE_ALPHAS[0]))).replace("__A_HI__", str(alphas.index(ENVELOPE_ALPHAS[1]))))
    body = body.replace("__RE_SECTION__", re_section())
    page = HEAD + body.replace("__DATA__", data.replace("</", "<\\/"))
    OUT.write_text(page)
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
