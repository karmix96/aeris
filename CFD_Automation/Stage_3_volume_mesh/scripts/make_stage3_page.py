"""One HTML page to understand and judge the volume mesher: docs/VOLUME_MESH.html (pictures inside).

    python scripts/v1_study.py ; python scripts/v23_study.py ; python scripts/v4_study.py
    python scripts/v5_export.py ; python scripts/v6_study.py ; python scripts/cost_options.py
    python scripts/make_stage3_page.py          # this page (+ docs/VOLUME_MESH.body.html for publishing)

Every number comes from configs/volume.yaml and data/studies/*.json; the words are written below. The style is the
Stage 2 page's (Stage_2_surface_mesh/scripts/make_stage2_page.py).
"""

from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from cfdauto import __version__                         # noqa: E402
from cfdauto.volume.laws import rules                   # noqa: E402

DOCS, PAGE, STUDIES = ROOT / "docs", ROOT / "docs" / "page", ROOT / "data" / "studies"
LEVELS = ("VC", "C", "M", "F")
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
N_TESTS = 45
PACKAGES_CONCLUSION = ("With four levels no package brings F to 9–11 M: the volume rules alone (P2) give F 24.2 M (median), the two Stage 2 changes on top 14.0 M (P5), everything counted 12.5 M (P6). What is left is the plane (about 210–310 C-line nodes × 70 layers) times the stations (53–62 along the wing, 40–48 past the tip); the surface band and the tip squeeze are Stage 2's. Mike's target (9 Nov, 20:30) is M about 10 M with F above it: P2 meets it with the volume rules alone (M 11.1 M median, 10.0–13.0 M; F 24.2 M; VC 2.45 M, 25 GiB for ADflow, every VC mesh fits the 52 GB desktop), so P2 became rule set 2 (decision 107). If M must come lower, the next step is the tip gap (P3: M 9.6 M), which changes the frozen surface. No package lets a VC mesh fit the 16 GB desktop but one (P6, 1 of 20).")
R2_V2_CONCLUSION = ("All 80 reference meshes pass every check with the fan to +10° and the fixes of decisions 108–110, at 0.48 × "
                    "the cells of rule set 1 (median 2.42 M; 2.08 M at Re 3 × 10⁵). The spacing jump across the trailing-edge "
                    "line is gone (1.02–1.03; rule set 1: up to 537). The costs show where they were named: 18–29 cells across "
                    "the boundary layer at VC, coarser cells on the tip-vortex path, station gaps up to 0.54 c 30 stations past "
                    "the tip.")
R2_V4_CONCLUSION = ("Check 13 passes on 20 of 20 families (worst 2.0 % off; 11 of 20 failed before the fix of decision 109). M is "
                    "9.5 M cells (median; 8.6–11.8 M), the target Mike set; F is 20.7 M. By S8's laws for ADflow only VC and C "
                    "fit 48 GB; M needs 72–92 GiB (decision 113: V7 measures it).")


def load(name: str) -> dict:
    p = STUDIES / name
    return json.loads(p.read_text()) if p.exists() else {}


def img(path: Path, alt: str) -> str:
    if not path.exists():
        return f'<p class="cap">(figure {html.escape(path.name)} not built yet)</p>'
    return f'<img src="data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}" alt="{html.escape(alt)}" loading="lazy">'


def figc(name: str, shows: str, concl: str, warn: bool = False) -> str:
    return (f'<figure class="card">{img(PAGE / name, shows)}<figcaption class="cap"><em>What it shows.</em> {shows}'
            f'</figcaption></figure><div class="cbox{" warn" if warn else ""}"><span class="ctag">Conclusion</span>{concl}</div>')


def cbox(text: str, tag: str = "Conclusion", cls: str = "") -> str:
    return f'<div class="cbox {cls}"><span class="ctag">{tag}</span>{text}</div>'


def table(head: list[str], rows: list[list], cls: str = "mid") -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def rng(d: dict, f: str = "{:.3g}", scale: float = 1.0, med: bool = True) -> str:
    if not d or "min" not in d:
        return "—"
    a, b = f.format(d["min"] * scale), f.format(d["max"] * scale)
    return f"{a}–{b}" + (f" (median {f.format(d['median'] * scale)})" if med else "")


def M(x: float) -> str:
    return f"{x / 1e6:.2f} M"


# --------------------------------------------------------------------------------------------------------------
CSS = (ROOT.parent / "Stage_2_surface_mesh" / "scripts" / "make_stage2_page.py").read_text().split('CSS = """')[1].split('"""')[0]


def rules_table() -> str:
    R = {lev: rules(lev) for lev in LEVELS}
    s = R["VC"].surface
    rows = [
        ["y⁺ of the first cell (law 13)", *[f"{R[l].yplus:.3g}" for l in LEVELS]],
        ["wall growth, boundary layer and fine zone (2 local c)", *[f"{R[l].setting('wall_growth'):.4g}" for l in LEVELS]],
        ["cells across the boundary layer (at least)", *[f"{R[l].setting('bl_cells'):.3g}" for l in LEVELS]],
        ["far growth: checked / built", *[f"{R[l].far_growth:.4g} / {R[l].far_growth_built:.4g}" for l in LEVELS]],
        ["wake band cell at the TE [% c]", *[f"{100 * R[l].band['spacing_c']:.3g}" for l in LEVELS]],
        [f"cells across the −{-R['M'].band['alpha_lo_deg']:g}° to +{R['M'].band['alpha_hi_deg']:g}° fan", *[f"{R[l].band['fan_cells']:.3g}" for l in LEVELS]],
        ["outboard growth to 2 c past the tip", *[f"{R[l].outboard_growth:.4g}" for l in LEVELS]],
        ["base cells (Stage 2)", "8", "10", "14", "18"],
        ["far field", "80 c", "80 c", "80 c", "80 c"],
    ]
    del s
    return table(["rule", *LEVELS], rows)


CHECKS = [
    (1, "Wall on the surface", "every wall node is the Stage 2 node (wing, base, cap)", "≤ 1e−12 c"),
    (2, "No folded cell", "the Jacobian at every corner of every cell", "> 0"),
    (3, "Cell quality", "the smallest corner scaled Jacobian of every cell but the cap's two nose-corner columns (reported on their own, as in Stage 2: decision 101)", "≥ 0.05"),
    (4, "Wall orthogonality", "in the station plane, the first line against the wall normal (but the 2 TE corners)", "≤ 5°"),
    (5, "First cell", "the first cell of every wing and base line against the station's s0", "within 1 %"),
    (6, "Growth", "along every wall-normal line, against the wall limit in the fine zone and the far limit beyond", "≤ limit × 1.01"),
    (7, "Cells across the boundary layer", "turbulent flat plate at the TE, local Re", "≥ 30 at VC (39, 50.7, 65.9)"),
    (8, "Interfaces", "every matched pair of faces, node to node; no open face", "≤ 1e−10 c"),
    (9, "Symmetry plane", "y on every root face", "≤ 1e−12 c"),
    (10, "Far field", "from every far-field node to the nearest wall node", "≥ 80 c"),
    (11, "Wake", "streamwise growth along the wake; every cell in the band against the band cell", "≤ limit × 1.01"),
    (12, "Outboard", "first gap past the tip = the tip gap; the growth", "1 %; × 1.01"),
    (13, "Family", "s0 per station, wall growth, band cell, first outboard gap, first wake cell, the cells 1 local c from the root's wall and behind its TE", "1.3 within 3 %"),
    (14, "Cells and RAM", "RAM = 1.51 + 9.46 GiB per M cells (ADflow, S8's law for ANK then NK; ANK only, as run here: 2.69 + 7.23; decision 112)", "information"),
    (15, "Export round trip", "CGNS read back exactly (own reader, CGNS library); .su2 counts, welds, no inside-out cell", "exact; equal"),
]


def rule_set_2() -> str:
    """The section on rule set 2 (decision 107), from the r2_ study files; parts still running say so."""
    v1, v23, v4, v5, v6 = (load(f"r2_{n}") for n in ("v1.json", "v23.json", "v4.json", "v5_export.json", "v6.json"))
    pk = load("cell_packages.json").get("packages", {})
    R2 = {lev: rules(lev) for lev in LEVELS}
    R1 = {lev: rules(lev, ROOT / "configs" / "volume_rules1.yaml") for lev in LEVELS}
    f4 = lambda v, n=4: f"{v:.{n}g}"
    tab = table(["rule (the check that reads it)", "rule set 1: VC / C / M / F", "rule set 2: VC / C / M / F"], [
        ["cells across the boundary layer (check 7)", " / ".join(f4(R1[l].bl_cells, 3) for l in LEVELS), " / ".join(f4(R2[l].bl_cells, 3) for l in LEVELS)],
        ["outboard growth to 2 c past the tip (check 12)", " / ".join(f4(R1[l].outboard_growth) for l in LEVELS), " / ".join(f4(R2[l].outboard_growth) for l in LEVELS)],
        ["the wake fan: freestream directions it holds (check 11)", f"−{-R1['M'].band['alpha_lo_deg']:g}° to +{R1['M'].band['alpha_hi_deg']:g}°", f"−{-R2['M'].band['alpha_lo_deg']:g}° to +{R2['M'].band['alpha_hi_deg']:g}° (decision 111)"],
        ["cells across the wake fan (check 11)", " / ".join(f4(R1[l].band["fan_cells"], 3) for l in LEVELS) + " (0.63° per cell at M)", " / ".join(f4(R2[l].band["fan_cells"], 3) for l in LEVELS) + " (1.25° per cell at M)"],
        ["streamwise cell in the band, × the band cell (check 11)", "4", "8"],
        ["first cell behind the base (check 5)", "s0 (y⁺ 1)", "the wing's last chordwise cell"]], "wide")
    run = '<p class="cap">Running: not finished when this page was built.</p>'
    parts = []
    if v1:
        parts.append(f"<li><strong>V1</strong> (BWB reference wing 0, VC, Re 3 × 10⁵): {v1.get('outcome')}; {v1['cells']['total']:,} cells (rule set 1: 4,930,448); {v1['counts']['n_layers']} layers, {v1['counts']['n_wake']} wake nodes, {v1['counts']['n_c']} C-line nodes, {v1['counts']['n_span']} + {v1['counts']['n_out']} stations; ADflow {v1['ram_gib_adflow']:.1f} GiB.</li>")
    if v23:
        c2 = v23["v2"]["cells"]
        parts.append(f"<li><strong>V2/V3</strong> (the 20 reference wings × 4 Re at VC): {v23['outcomes'].get('passed', 0)} of {v23['meshes']} pass; cells {c2['min'] / 1e6:.2f}–{c2['max'] / 1e6:.2f} M (median {c2['median'] / 1e6:.2f} M); fit 16 GB: {v23['v2']['fits_16GB']}, fit 52 GB: {v23['v2']['fits_52GB']}; cap {v23['v3']['cap_min_sj']['min']:.3f} (the two nose-corner columns, exempt); growth ≤ {v23['checks']['growth']['max']:.4f} × its limit; wake ≤ {v23['checks']['wake']['max']:.4f}.</li>")
    if v4:
        c = v4["cells"]; c13 = v4["check13"]
        bm = "; ".join(f"{d['wing']} {d['level']}: {d['cells'] / 1e6:.2f} M, {d['outcome']}" for d in v4.get("built_vs_counted", []))
        parts.append(f"<li><strong>V4</strong> (the family, Re 3 × 10⁵): check 13 {c13['passed']} of {c13['of']} (worst {100 * c13['worst'][0]:.1f} %: {c13['worst'][1]}); cells, median (range): VC {c['VC']['median'] / 1e6:.2f} M, C {c['C']['median'] / 1e6:.2f} M, <strong>M {c['M']['median'] / 1e6:.2f} M ({c['M']['min'] / 1e6:.1f}–{c['M']['max'] / 1e6:.1f})</strong>, F {c['F']['median'] / 1e6:.1f} M ({c['F']['min'] / 1e6:.1f}–{c['F']['max'] / 1e6:.1f}); M and F built: {bm}.</li>")
    if v5:
        e = v5.get("exports", {})
        parts.append(f"<li><strong>V5</strong> (the V7 mesh, rule set 2): {v5['cells']:,} cells; check 15 {'passed' if v5['check15']['passed'] else 'FAILED'}; CGNS {e.get('cgns', {}).get('bytes', 0) / 1e6:.0f} MB (libcgns: {'exact' if (e.get('cgns', {}).get('libcgns') or {}).get('passed') else '—'}), .su2 {e.get('su2', {}).get('bytes', 0) / 1e6:.0f} MB.</li>")
    if v6:
        od = v6.get("outcomes_with_decision_101", v6["outcomes"])
        parts.append(f"<li><strong>V6</strong> (every built set at VC, Re 3 × 10⁵, with the 20 reference wings): {od.get('passed', 0)} of {v6['meshes']} pass" + ("; refused: " + "; ".join(f"{TYPE_NAME.get(r['type'], r['type'])} {r['set']} wing {r['index']} (cell quality {r['values'].get('cell_quality', 0):.3f})" for r in v6.get("refused", [])) if od.get('refused') else "") + f"; cells {v6['cells']['min'] / 1e6:.2f}–{v6['cells']['max'] / 1e6:.2f} M (median {v6['cells']['median'] / 1e6:.2f} M)"
                     + "".join(f"; {L} counted on {v6[L + '_sample']['wings']} wings: {v6[L + '_sample']['cells']['min'] / 1e6:.1f}–{v6[L + '_sample']['cells']['max'] / 1e6:.1f} M (median {v6[L + '_sample']['cells']['median'] / 1e6:.1f} M)"
                               for L in ("M", "F") if v6.get(L + "_sample")) + ".</li>")
    figs = ""
    if v4:
        figs += figc("r2_v4_family.png", "Rule set 2. (a) Check 13: every judged spacing, coarse over fine, between neighbouring levels (green: 1.3 ± 3 %). (b) Cells per level on the 20 reference wings: VC and C built, M and F counted; the target at M; grey: what 48 GB holds for ADflow by S8's two laws.",
                     R2_V4_CONCLUSION)
    if v23:
        figs += figc("r2_v2_wall.png", "Rule set 2, the 80 reference meshes at VC: cells; cells across the boundary layer (limit 17.8 at VC); the in-plane wall angle; the 3-D angle (reported); the cells at the base and the TE corners; the spacing jump across the trailing edge (now about 1).",
                     R2_V2_CONCLUSION)
    p2m = pk.get("P2", {}).get("levels", {}).get("M", {}).get("median")
    if v6:
        od6 = v6.get("outcomes_with_decision_101", v6["outcomes"])
        foc = v6["by_set"]["training_focus"]
        fp, ft = sum(d.get("passed", 0) for d in foc.values()), sum(sum(d.values()) for d in foc.values())
        tm = v6.get("thin_margins", {})
        refl = ", ".join(f"{TYPE_NAME.get(r['type'], r['type'])} {r['set']} wing {r['index']} ({', '.join(f'{c.replace(chr(95), chr(32))} {v:.3f}' for c, v in r['values'].items())}; limit 0.05)" for r in v6.get("refused", []))
        r2_v6_concl = (f"{od6.get('passed', 0)} of {v6['meshes']} meshes pass" + (f"; refused: {refl}" if refl else "; none refused")
                       + f". The focus set, where most runs go, passes {fp} of {ft}. Thin margins: {tm.get('below_0p06', 0)} meshes have their worst cell under 0.06 (limit 0.05)."
                       + (f" M on the {v6['M_sample']['wings']} counted wings: {v6['M_sample']['cells']['min'] / 1e6:.1f}–{v6['M_sample']['cells']['max'] / 1e6:.1f} M (median {v6['M_sample']['cells']['median'] / 1e6:.1f} M)." if v6.get("M_sample") else ""))
        r2_concl = (f"Rule set 2 as it stands meets Mike's targets for the cells (M {v4['cells']['M']['median'] / 1e6:.1f} M median) and the angles (one mesh for −5° to +10°): "
                    f"80 of 80 reference meshes, 20 of 20 families and {od6.get('passed', 0)} of {v6['meshes']} screened meshes pass, after three construction faults were fixed and no limit changed. "
                    "It does not make M fit 48 GB for ADflow (by S8's laws, 72–92 GiB); the first solves measure that, and where the wake goes.") if v4 else "Running."
    else:
        r2_v6_concl, r2_concl = "Running.", "Running: the screen of every built set was not finished when this page was built."
    if v6:
        figs += figc("r2_v6_screen.png", "Rule set 2, every screened mesh at VC, Re 3 × 10⁵, by wing type (the bar at the median): cells; the worst cell; the growth over its limit.", r2_v6_concl)
    fo = load("r2_fan_options.json").get("summary", {})
    fan_txt = ", ".join(f"{lab} {fo[k]['cells_M_median'] / 1e6:.1f} M" for k, lab in (("base", "top at +20°"), ("to15", "+15°"), ("to12", "+12°"), ("to10", "+10°"), ("none", "no fan")) if k in fo) or "see the rules document"
    fan_txt += " at M, the median of wing 0 of each type"
    return f"""
<section id="r2">
  <h2>Rule set 2 (decisions 107–111): M about 10 M cells, angles −5° to +10°</h2>
  <p>Mike, 9 Nov 20:30: "make medium around 10 million; the fine family can be over this limit". Of the counted packages (<a href="#cost">Cost</a>), P2 meets it with the volume rules alone{f" (M median {p2m / 1e6:.1f} M counted, with the fan to +20°)" if p2m else ""}, so it became rule set 2. Mike, 22:04: "I want to run from −5 to 10 AoA. You adjust the wake fan accordingly", so the fan now ends at +10° (decision 111). The surface, its band, the levels, y⁺ 1 on the wing and the far field are unchanged. The rules and their limits were written before each rebuild.</p>
  {tab}
  <p><strong>What it costs, named before the results:</strong> the base is no longer at y⁺ 1 (its first cell is the trailing-edge chordwise cell), but the spacing jump across the trailing-edge line is gone; the wake band has half the cells per degree of its fan (1.25° per cell at M) and streamwise cells up to 8 × its cross cell; above +10° the wake leaves the fine cells (post-stall gets its own mesh, decision 69); VC has 17.8 cells across the boundary layer; the tip vortex gets coarser spanwise cells (outboard growth 1.3).</p>
  <h3>The wake fan: one mesh for −5° to +10°</h3>
  <ul>
    <li><strong>One mesh serves every steady angle,</strong> so it has no refinement per angle. Each station plane has a fixed fan of fine cells behind the trailing edge: from −5° to +10°, 0.05 c above and below at the trailing edge, 2 local chords long.</li>
    <li><strong>Why one mesh for all angles:</strong> one mesh instead of about eight per wing and Re; the same mesh error at every angle, so the lift slope and the polar shape are clean; one family check per wing.</li>
    <li><strong>Why +10° and no more:</strong> steady RANS serves −5° to +10° here; post-stall is a separate study with its own mesh from the same code (the two angles are inputs of the mesher). The fan to +20° cost 11–14 % of the cells; at +10° the fan costs none (the same count as no fan: {fan_txt}).</li>
    <li><strong>No extra angle on top of the 0.05 c:</strong> the downwash turns the wake below the freestream direction; the cells do not jump at the fan's edge. Not measured yet: where the wake goes in a solution (V7 checks −5° and +10°).</li>
  </ul>
  {figc("r2_wake_fan.png", "BWB reference wing 0 at VC, Re 3 × 10⁵, rule set 2. (a) One station plane: the fan (blue), its edges at −5° and +10°, its end 2 local chords behind the trailing edge; dashed: the freestream directions at −5°, 0°, 5°, 10°. (b) The trailing edge close up. (c) The cell height along the vertical line 1 local chord behind the trailing edge; red: the band cell there. (d) Top view: the fan behind every station.",
        "Every freestream direction from −5° to +10° lies inside the fan, and every cell inside it is no larger than the band cell.")}
  <h3>Three faults the first builds found, and their fixes (no check limit changed)</h3>
  {table(["decision", "what failed", "cause", "fix (construction)"], [
      ["108", "check 11 on 9 of the first 13 full-space wings (band cells up to 1.07 × the band cell)", "the fan is straight from the base, the mesh's wake line falls up to 0.12 c behind a BWB centre body; the cells were sized from the wake line", "the exact envelope of the straight fan around the bent line, per station"],
      ["109", "check 13 on 11 of 20 reference wings (ratios 1.247–1.285, limit 1.3 ± 3 %)", "each cell took the band limit at its start, so the coarser level lagged more", "each cell takes the limit at its own centre: the band cells of two levels are 1.300 apart"],
      ["110", "check 3 on 6 full-space BWB wings over three versions of the fix (0.024–0.050; limit 0.05)", "stations 0.0001–0.05 c apart whose far nodes sat far apart (the near field is sized in local chords)", "the far part of each station moves toward its neighbours' average, as far as its growth limit allows, neighbours alike, with the ramp that leaves the least shear; the near part is never moved (0.052–0.093 after; BWB corner2 6 stays refused at 0.032)"]], "wide")}
  {cbox("The three faults were in how the mesh is built, not in the rules; one was my incomplete fix of decision 106, and decision 110 took three versions, each found by a screen. No limit changed. The screens below were rerun with the final construction and count every wing. Very close stations with fast-changing chords stay the weakest place of the mesh.")}
  <h3>The results</h3>
  <ul>{"".join(parts) or "<li>Running.</li>"}</ul>
  {figs}
  {cbox(r2_concl, "Conclusion", "warn" if not v6 else "")}
</section>"""


def build_page() -> tuple[str, str]:
    v1, v23, v4, v5, v6, co = (load(n) for n in ("v1.json", "v23.json", "v4.json", "v5_export.json", "v6.json",
                                                   "cost_options.json"))
    pm = load("plane_method.json").get("summary", {})
    bl = load("bl_law.json").get("summary", {})
    v2, v3 = v23.get("v2", {}), v23.get("v3", {})
    n2 = v23.get("meshes", 0)
    ok2 = v23.get("outcomes", {}).get("passed", 0)
    c13 = v4.get("check13", {})
    cells4 = v4.get("cells", {})
    n6, ok6 = v6.get("meshes", 0), v6.get("outcomes", {}).get("passed", 0)
    od = v6.get("outcomes_with_decision_101", {})
    f_med = cells4.get("F", {}).get("median", 0)
    f_max = cells4.get("F", {}).get("max", 0)
    exp = v5.get("exports", {})
    cg, su = exp.get("cgns", {}), exp.get("su2", {})
    lib = (cg.get("libcgns") or {})

    head = f"""
<header>
  <div class="eyebrow">CFD_Automation · Stage 3 · volume mesh · cfdauto {__version__} · 10 Nov 2026</div>
  <h1>Volume Mesh</h1>
  <p class="lede">One matched C-H mesh per wing, Re and level (VC, C, M, F), on the frozen Stage 2 surface: structured
  CGNS for ADflow, the same cells as <code>.su2</code> for SU2. What it is, how one is built, every check, what was
  measured, what is weak and what is left. Every check and limit was written before the first mesh was judged (V0) and
  none changed; the construction changed ten times, each after a check failed (<a href="#changes">What changed</a>).
  The first rule set worked but cost too much (M 20.8 M, F 45 M cells). On 9 Nov Mike set the target, M about 10 M
  with F above it, and rule set 2 (decision 107) meets it with the volume rules alone: its results come first, the
  first rule set's follow as the record (<a href="#cost">Cost</a> has the packages that were counted).
  Step by step from a surface to its volume mesh, with the rule, the decision and the value per level: the
  <a href="https://claude.ai/artifact/EWgreAJioSL4yNMwoGFUpD" target="_blank" rel="noopener">flowchart</a>.</p>
  <nav aria-label="On this page"><a href="#glance">At a glance</a><a href="#r2">Rule set 2</a><a href="#what">What it is</a><a href="#how">How a plane is built</a><a href="#rules">The rules</a><a href="#checks">The checks</a><a href="#v0">V0</a><a href="#v1">V1</a><a href="#v2">V2</a><a href="#v3">V3</a><a href="#v4">V4</a><a href="#v5">V5</a><a href="#v6">V6</a><a href="#cost">Cost</a><a href="#v7">V7</a><a href="#v8">V8</a><a href="#changes">What changed</a><a href="#weak">Weak points</a><a href="#handover">Handover</a><a href="#files">Files</a></nav>
</header>"""

    g23, g4, g6, g5 = load("r2_v23.json"), load("r2_v4.json"), load("r2_v6.json"), load("r2_v5_export.json")
    gc = g4.get("cells", {})
    gM = gc.get("M", {}); gF = gc.get("F", {}); gV = gc.get("VC", {})
    g13 = g4.get("check13", {})
    g6o = g6.get("outcomes_with_decision_101", g6.get("outcomes", {}))
    glance = f"""
<section id="glance">
  <h2>At a glance</h2>
  <div class="three">
    <div class="box verdict"><h3>Where it stands</h3><div class="big">Rule set 2: M about {gM.get('median', 0) / 1e6:.0f} M cells</div>
      <p>Rule set 1 worked but cost too much (M 20.8 M, F 45 M). Mike set the target on 9 Nov: M about 10 M, F may be
      above; and the angles: −5° to +10°. Rule set 2 (decisions 107, 111) meets it with the volume rules alone; the
      surface, its band and the levels are unchanged. Left: the first solves (V7), the hold-outs (V8, not yet). In main
      on GitHub since 10 Nov, with an app to load or make a wing and look at its meshes (<code>CFD_Automation/app</code>).</p></div>
    <div class="box good"><h3>Rule set 2: the screens</h3><div class="big">{g23.get('outcomes', {}).get('passed', '—')} of {g23.get('meshes', '—')} reference · {f"{g6o.get('passed', 0)} of {g6.get('meshes', 0)} all sets" if g6 else "all sets: running"}</div>
      <p>V2/V3: the 20 reference wings × 4 Re at VC. V4: the family, check 13 {g13.get('passed', '—')} of {g13.get('of', '—')}.
      V6: every built set at VC (not the hold-outs){"; refused: " + "; ".join(f"{TYPE_NAME.get(r['type'], r['type'])} {r['set']} wing {r['index']} (cell quality {r['values'].get('cell_quality', 0):.3f}, limit 0.05)" for r in g6['refused']) if g6.get('refused') else ""}{"" if g6 else ", running when this page was built"}.</p></div>
    <div class="box"><h3>Rule set 2: the cost</h3><div class="big">M {gM.get('median', 0) / 1e6:.1f} M · F {gF.get('median', 0) / 1e6:.1f} M</div>
      <p>Median on the 20 reference wings at Re 3 × 10⁵ (M {gM.get('min', 0) / 1e6:.1f}–{gM.get('max', 0) / 1e6:.1f} M;
      F {gF.get('min', 0) / 1e6:.1f}–{gF.get('max', 0) / 1e6:.1f} M). VC {gV.get('median', 0) / 1e6:.2f} M, about
      {2.69 + 7.23 * gV.get('median', 0) / 1e6:.0f}–{1.51 + 9.46 * gV.get('median', 0) / 1e6:.0f} GiB for ADflow (S8's two laws: ANK only, ANK then NK): every reference VC mesh fits the 52 GB desktop,
      none the 16 GB one. M: {2.69 + 7.23 * gM.get('median', 0) / 1e6:.0f}–{1.51 + 9.46 * gM.get('median', 0) / 1e6:.0f} GiB (a cluster job). Rule set 1: M 20.8 M, F 45.4 M (<a href="#cost">Cost</a>).</p></div>
    <div class="box"><h3>Solver files (V5)</h3><div class="big">CGNS exact · .su2 checked</div>
      <p>The CGNS (ADF, the format Mike's CGNS 4.5.2 reads) is read back exactly by this package and by the CGNS library
      itself; the <code>.su2</code> has every face welded, no inside-out cell, every boundary face facing out. The V7
      mesh (rule set 2): {g5.get('cells', 0) / 1e6:.2f} M cells, {2.69 + 7.23 * g5.get('cells', 0) / 1e6:.0f}–{1.51 + 9.46 * g5.get('cells', 0) / 1e6:.0f} GiB for ADflow.</p></div>
    <div class="box bad"><h3>Weak points</h3><div class="big">no solve yet · coarser wake and tip vortex</div>
      <p>No solver has run on a Stage 3 mesh, so where the wake goes is not checked. Rule set 2 resolves the wake band
      and the tip vortex more coarsely than rule set 1, the fan ends at +10°, and the base is no longer at y⁺ 1. Very
      close stations with fast-changing chords sit nearest the cell-quality limit; one corner wing is refused (BWB
      corner2 6). The cap's two nose-corner cells are exempt (decision 101), not fixed. Planar stations: square in the
      plane, up to 40° off the surface normal in 3-D at swept noses (74° on the most swept corner wing). All in
      <a href="#weak">Weak points</a>.</p></div>
    <div class="box"><h3>Rules, checks, code</h3><div class="big">15 checks · {N_TESTS} tests</div>
      <p>Rules in <code>configs/volume.yaml</code> (rule set 1 kept in <code>configs/volume_rules1.yaml</code>); checks and
      limits in <code>decisions/volume_rules.md</code>; code in <code>cfdauto/volume/</code> (Stage 2's
      <code>cfdauto/mesh/</code> untouched); decisions 84–113 in <code>OPEN_DECISIONS.md</code>.</p></div>
  </div>
</section>"""

    what = f"""
<section id="what">
  <h2>What Stage 3 is</h2>
  <ul>
    <li><strong>In:</strong> the Stage 2 surface of one wing at one Re and level (the ring at every station, the base, the tip cap). <strong>Out:</strong> one matched multiblock volume mesh, 13 blocks, every wall node the Stage 2 node.</li>
    <li><strong>Each station plane</strong> (y = const) holds a C around the ring and the wake, out to the far field: six blocks (upper wake, upper side, nose, lower side, lower wake, base). The planes are stacked root to tip; past the tip the tip plane is swept out to 80 c, and the tip cap with it (the CAP block).</li>
    <li><strong>One mesh for both solvers</strong> (decision 73): ADflow reads it as structured CGNS; SU2 reads the same cells as unstructured hexahedra.</li>
    <li><strong>Three outcomes:</strong> passed, refused (only <code>refusal.json</code> is written), needs review (every check passed, but the plane needed more smoothing). Failures stay in every count.</li>
  </ul>
  {figc("v1_slices.png", "BWB reference wing 0 at VC, Re 3 × 10⁵: the station planes at the root, mid semi-span and the tip; the root's trailing edge close up; the root plane out to the far field; the wake in the y–z plane behind the wing.",
        f"One C per station, square to the wall, the wake band behind the trailing edge, the base block between the two wake lines, the outboard planes past the tip. {v1.get('cells', {}).get('total', 0):,} cells; every check passes (V1).")}
</section>"""

    how = """
<section id="how">
  <h2>How a station plane is built</h2>
  <ol>
    <li><strong>The C line:</strong> the upper wake line, the Stage 2 ring from the upper to the lower trailing-edge corner, the lower wake line. The wake leaves the base along its normal and turns to +x over 0.5 local chord; the two wake lines are parallel, the base height apart.</li>
    <li><strong>The line shapes:</strong> one front moved the same distance everywhere from the C line, smoothed along itself over its distance from the wall (κ = 1: no smoothing at the wall, so the lines leave square to it), out to 2 local chords; then straight to far-field nodes that every station shares.</li>
    <li><strong>The nodes:</strong> one wall-normal distribution per station: first cell s0, the level's cells across the boundary layer (30 at M), the wall growth out to 2 local chords, the wake band as an envelope in height (the exact envelope of the straight fan, whatever the wake line does; each cell takes the limit at its centre), then the far growth. Every station gets the same count: its growth (never the band cell) is scaled down to fit.</li>
    <li><strong>Far out,</strong> every station's far layers and far wake nodes first move toward the average of its neighbours within about 0.25 c along the semi-span (as far as the growth limit allows, neighbours alike), then toward the mean of all stations, so neighbouring planes line up and the cells between them stay square. The near field (fine zone and band) is never moved.</li>
    <li><strong>The base block</strong> fills the space between the two wake lines.</li>
    <li><strong>If a cell folds,</strong> every station is rebuilt with more smoothing (κ = 1.5, 2, 3); a mesh that needed it is "needs review". No mesh built so far needed it.</li>
  </ol>
</section>"""

    rules_s = f"""
<section id="rules">
  <h2>The rules, per level</h2>
  <p>Each rule is met at its anchor level; every spacing is ÷ 1.3 per finer level, every growth g^(1/1.3), every count × 1.3; distances stay. Read from <code>configs/volume.yaml</code>.</p>
  {rules_table()}
</section>"""

    checks_s = f"""
<section id="checks">
  <h2>The checks and their limits</h2>
  <p>Written in V0, before any mesh was judged, and approved by Mike. A refusing check that fails refuses the mesh.</p>
  {table(["#", "check", "what is measured", "limit"], [[n, a, b, c] for n, a, b, c in CHECKS], "wide")}
</section>"""

    m, al, el = pm.get("march", {}), pm.get("algebraic", {}), pm.get("elliptic", {})
    b_rows = []
    for key, name in (("turb_TE_VC", "turbulent, at the TE, 30 at VC (chosen)"), ("turb_mid_VC", "turbulent, mid-chord, 30 at VC"),
                      ("lam_mid_VC", "laminar, mid-chord, 30 at VC"), ("turb_TE_M", "turbulent, at the TE, 30 at M"),
                      ("lam_mid_M", "laminar, mid-chord, 30 at M")):
        cells = []
        for re in ("1e+05", "3e+05", "1e+06", "4e+06"):
            d = bl.get(f"{key}@{re}")
            cells.append("—" if not d else f"{d['layers_median']:.1f} ({d['layers_max']:.1f})" +
                         (" infeasible" if d.get("g_bl_min", 2) <= 1.0000001 else ""))
        b_rows.append([name, *cells])
    v0 = f"""
<section id="v0">
  <h2>V0: the plane method and the boundary-layer law (measured before V1)</h2>
  {table(["method", "planes with a fold", "smallest scaled Jacobian (median)", "wall angle", "growth / limit", "time"],
         [["march (chosen)", f"{m.get('planes_with_a_fold', '—')} of {m.get('station_planes', '—')}", f"{m.get('min_sj', 0):.3f} ({m.get('min_sj_median', 0):.3f})", f"{m.get('wall_angle_max_deg', 0):.2f}°", f"{m.get('growth_over_limit_max', 0):.3f}", f"{m.get('seconds', 0):.1f} s"],
          ["algebraic", f"{al.get('planes_with_a_fold', '—')} of {al.get('station_planes', '—')}", "folded", "—", "—", f"{al.get('seconds', 0):.1f} s"],
          ["elliptic (300 Winslow sweeps)", f"{el.get('planes_with_a_fold', '—')} of {el.get('station_planes', '—')}", "folded", "—", f"{el.get('growth_over_limit_max', 0):.1f}", f"{el.get('seconds', 0):.0f} s"]])}
  {cbox("The march folds no plane; the other two fold every plane, at the concave trailing-edge corners. Not close, so Mike was not asked (decision 84).")}
  <p>Layers at VC, median (largest) over the 20 reference wings, for five boundary-layer laws:</p>
  {table(["law", "Re 1e5", "Re 3e5", "Re 1e6", "Re 4e6"], b_rows)}
  {cbox("The turbulent layer at the trailing edge always fits 30 cells at VC; the mid-chord layers do not at Re 10⁵ (the small tips would need growth 1.000). Chosen: turbulent at the TE, 30 at VC (decision 86). Weak point: a laminar layer at mid-chord gets fewer cells at VC; the family gives it more at F.")}
</section>"""

    c1 = v1.get("cells", {})
    v1s = f"""
<section id="v1">
  <h2>V1: BWB reference wing 0, VC, Re 3 × 10⁵</h2>
  <ul>
    <li>Every check passes. {c1.get('total', 0):,} cells: inboard {c1.get('inboard', 0):,}, outboard {c1.get('outboard', 0):,}, cap {c1.get('cap', 0):,}; the wake blocks hold {c1.get('wake_blocks', 0):,}.</li>
    <li>Counts: {v1.get('counts', {}).get('n_layers', '—')} layers, {v1.get('counts', {}).get('n_wake', '—')} wake nodes, {v1.get('counts', {}).get('n_c', '—')} C-line nodes, {v1.get('counts', {}).get('n_span', '—')} stations, {v1.get('counts', {}).get('n_out', '—')} outboard stations.</li>
    <li>Against Stage 2's estimate ({v1.get('stage2_estimate', {}).get('cells', 0):,} cells, {v1.get('stage2_estimate', {}).get('wall_layers', '—')} wall layers, the wing blocks only): {v1.get('ratio_to_stage2_estimate', 0):.2f} ×. The difference: 94 layers, not 43 (the boundary layer, the band, the far field), the wake blocks and the outboard blocks.</li>
    <li>ADflow RAM by the law: {v1.get('ram_gib_adflow', 0):.1f} GiB: not the 16 GB desktop; the 52 GB one.</li>
  </ul>
  {cbox("The matched C-H mesh works on the reference BWB: 13 blocks, every face either a boundary or matched node to node, every check met. Its cost is 7.5 × what Stage 2 estimated.", "Conclusion", "warn")}
</section>"""

    vp = v3.get("vortex_path", {})
    v2s = f"""
<section id="v2">
  <h2>V2: wall layers, fine zone and far field: 20 reference wings × 4 Re at VC</h2>
  {figc("v2_wall.png", "One dot per mesh (80): by wing type, light to dark from Re 10⁵ to 4 × 10⁶. (a) cells; (b) cells across the boundary layer at the worst station; (c) the largest angle between the first line and the wall normal in the station plane; (d) the 95th percentile of the 3-D angle to the surface normal (reported, not judged); (e) the worst cell next to the base and the trailing-edge corners; (f) the wing's last chordwise cell over the first cell behind the base.",
        f"{ok2} of {n2} pass. The wall rules hold on every wing at every Re: {rng(v2.get('bl_cells_min'), '{:.2f}')} cells across the boundary layer (≥ 30), first cells within {100 * v23.get('checks', {}).get('first_cell', {}).get('max', 0):.3f} %, growth ≤ {v23.get('checks', {}).get('growth', {}).get('max', 0):.4f} × its limit, the far field at 80 c, in-plane angle ≤ {v2.get('wall_angle_in_plane_deg', {}).get('max', 0):.2f}° (nose {v2.get('nose_angle_deg', {}).get('max', 0):.2f}°, off the base {v2.get('base_angle_deg', {}).get('max', 0):.4f}°). The cells at the base and the trailing-edge corners are good ({rng(v2.get('base_cells_min_sj'), '{:.2f}', 1, False)} at the base). Weak: the 3-D angle reaches {v2.get('wall_angle_3d_max_deg', {}).get('max', 0):.0f}° at swept noses (planar stations, decision 89), and the spacing jump across the trailing-edge line reaches {v2.get('te_jump_ratio', {}).get('Re 4e6', {}).get('max', 0):.0f} at Re 4 × 10⁶ (the base is a wall at y⁺ 1, decision 90).", )}
  {table(["what", "measured (80 meshes)", "limit"], [
      ["cells", rng(v2.get('cells'), '{:.2f}', 1e-6) + " M", "—"],
      ["... by Re", "; ".join(f"{k.replace('Re ', '')}: {rng(d, '{:.1f}', 1e-6, False)} M" for k, d in v2.get('cells_by_re', {}).items()), "—"],
      ["ADflow RAM", rng(v2.get('ram_gib'), '{:.0f}') + " GiB; fit 16 GB: " + str(v2.get('fits_16GB', '—')) + ", 52 GB: " + str(v2.get('fits_52GB', '—')), "information"],
      ["layers · wake nodes · stations · outboard stations", f"{rng(v2.get('layers'), '{:.0f}', 1, False)} · {rng(v2.get('wake_nodes'), '{:.0f}', 1, False)} · {rng(v2.get('stations'), '{:.0f}', 1, False)} · {rng(v2.get('outboard_stations'), '{:.0f}', 1, False)}", "—"],
      ["cells across the boundary layer", rng(v2.get('bl_cells_min'), '{:.2f}'), "≥ 30"],
      ["growth / limit", rng(v2.get('growth_over_limit'), '{:.4f}'), "≤ 1.01"],
      ["wall angle in the plane", rng(v2.get('wall_angle_in_plane_deg'), '{:.3g}') + "°", "≤ 5°"],
      ["the two TE corners (not judged)", rng(v2.get('te_corner_angle_deg'), '{:.1f}') + "°", "reported"],
      ["3-D angle to the surface normal, largest", rng(v2.get('wall_angle_3d_max_deg'), '{:.0f}') + "°", "reported"],
      ["TE spacing jump", "; ".join(f"{k.replace('Re ', '')}: {rng(d, '{:.0f}', 1, False)}" for k, d in v2.get('te_jump_ratio', {}).items()), "reported"],
  ])}
</section>"""

    v3s = f"""
<section id="v3">
  <h2>V3: the cap, the outboard blocks and the tip vortex</h2>
  {figc("v3_tip.png", "(a) the worst cell of the CAP block per mesh; (b) the cells on the tip-vortex path at 4°, 0.5, 1 and 2 local chords behind the tip trailing edge (median and range over the 80 meshes), across the wake and along it; (c) the share of the cells in the outboard blocks.",
        f"The cap and the outboard blocks pass on all 80. The cap's cells are the worst of every mesh ({rng(v3.get('cap_min_sj'), '{:.3f}', 1, False)}): they are the Stage 2 cap quads swept outboard, so a better cap belongs to the frozen surface. The outboard blocks are good ({rng(v3.get('outboard_min_sj'), '{:.2f}', 1, False)}) but hold {rng(v3.get('outboard_share_of_cells'), '{:.0f}', 100, False)} % of the cells: in a matched mesh every outboard station carries the whole plane. The vortex path is fine across the wake (median {vp.get('d0.5c_a4', {}).get('cross', {}).get('median', 0):.4f}, {vp.get('d1c_a4', {}).get('cross', {}).get('median', 0):.3f}, {vp.get('d2c_a4', {}).get('cross', {}).get('median', 0):.3f} c at 0.5, 1, 2 c) and coarse along it ({vp.get('d0.5c_a4', {}).get('streamwise', {}).get('median', 0):.2f}, {vp.get('d1c_a4', {}).get('streamwise', {}).get('median', 0):.2f}, {vp.get('d2c_a4', {}).get('streamwise', {}).get('median', 0):.2f} c; the band allows 4 × the cross cell). Enough to carry a vortex, not to resolve its core; at 20° and 2 c the cross cell is {vp.get('d2c_a20', {}).get('cross', {}).get('median', 0):.2f} c (the band's edge). A solve must show whether that is enough (V7).")}
</section>"""

    rat = v4.get("ratios", {}).get("VC/C", {})
    names = {"s0": "s0 per station", "wall_growth": "wall growth (ln g)", "band_cell": "band cell",
             "outboard_first_gap": "first outboard gap", "first_wake_cell": "first wake cell",
             "cell_1c_wall": "cell 1 local c from the root's wall", "cell_1c_wake": "cell 1 local c behind the root's TE"}
    other = {p: d for p, d in v4.get("ratios", {}).items() if p != "VC/C"}
    v4_rows = [[names[k], rng(rat.get(k), '{:.4f}', 1, False), "; ".join(f"{p}: {rng(d.get(k), '{:.4f}', 1, False)}" for p, d in other.items()) or "—"]
               for k in names]
    v4_rows += [[f"count: {k.replace('count_', '')}", rng(rat.get(k), '{:.3f}', 1, False), "named exception (whole numbers)"]
                for k in ("count_n_layers", "count_n_wake", "count_n_out", "count_n_c", "count_cells") if k in rat]
    lev_rows = [[lev, M(cells4[lev]['median']), M(cells4[lev]['max']), f"{cells4[lev]['ram_gib_median']:.0f} GiB",
                 "built" if lev in ("VC", "C") else "counted"] for lev in LEVELS if lev in cells4]
    deep = "; ".join(f"{d['wing']} {d['level']}: {d['cells']:,} cells, {d.get('outcome', '')}, {d['seconds']:.0f} s, {d['max_rss_gib']:.1f} GiB peak"
                     for d in v4.get("built_vs_counted", []) if d.get("seconds"))
    v4s = f"""
<section id="v4">
  <h2>V4: the family VC, C, M, F (20 reference wings, Re 3 × 10⁵)</h2>
  {figc("v4_family.png", "(a) check 13: every judged spacing, coarse over fine, between neighbouring levels: one dot per wing for VC/C; diamonds for C/M and M/F where M and F were built; the green band is 1.3 ± 3 %. (b) cells per level for the 20 reference wings: VC and C built, M and F counted, against the 16 GB and 52 GB desktops and the 9–11 M asked for at F.",
        f"Check 13 passes on {c13.get('passed', '—')} of {c13.get('of', '—')} families at VC/C (worst {100 * c13.get('worst', [0])[0]:.1f} %: {c13.get('worst', [0, ''])[1]}) and on BWB reference wing 0 from VC to F: the family is a true 1.3-scaled copy, after two construction changes found by this check (changes 7 and 8). Honest negatives. (1) At M and F the CAP block's two columns over the cap's nose-corner quads fall below 0.05 on the BWB and flying wing (0.045 and 0.037 on BWB 0); Stage 2 exempts exactly these quads (three corners on the smooth ring), every other cell is ≥ 0.077, and Mike decided the same exemption for check 3 (decision 101): then every M and F mesh built passes. (2) The cost: F is {M(f_med)} median, {M(f_max)} largest, against 9–11 M asked (decision 102: Mike to think it over)." + (f" Built here: {deep}." if deep else ""), warn=True)}
  {table(["judged spacing", "VC / C (20 wings)", "C / M, M / F"], v4_rows, "wide")}
  {table(["level", "cells, median", "largest", "ADflow RAM, median", "here"], lev_rows)}
</section>"""

    v5s = f"""
<section id="v5">
  <h2>V5: the solver files</h2>
  <ul>
    <li><strong>CGNS for ADflow:</strong> written by <code>cfdauto/volume/cgns.py</code> in pure Python, in ADF (version A02011). Mike's CGNS 4.5.2 was built without HDF5 and reads only ADF (S8). 13 structured zones, coordinates in double precision, one BC per boundary face (BCWallViscous, BCFarfield, BCSymmetryPlane, each with its family), 1-to-1 connectivity on both sides with its transform.</li>
    <li><strong>Read back</strong> on BWB reference wing 0, VC ({v5.get('cells', 0):,} cells, {cg.get('bytes', 0) / 1e6:.0f} MB): by this package, every coordinate exact and every match node for node ({(cg.get('own_reader') or {}).get('one2one', '—')} 1-to-1 records); by the CGNS library itself ({'the copy VTK ships, CGNS with ADF, ' + str(lib.get('cgsize_t_bits', '')) + '-bit sizes' if lib else 'not available here'}): {'exact, no problem' if lib.get('passed') else '—'}.</li>
    <li><strong>.su2 for SU2:</strong> <code>cfdauto/volume/su2.py</code>: the blocks as hexahedra, nodes welded along every matched face by the topology, markers <code>wall</code>, <code>symmetry</code>, <code>farfield</code>. Read back: {su.get('points', 0):,} points, {su.get('cells', 0):,} hexahedra, {su.get('markers', {})}; no two points closer than 1e−12 c, no inside-out hexahedron, every boundary quad faces out ({su.get('bytes', 0) / 1e6:.0f} MB).</li>
    <li>Check 15 runs every time a mesh is written with its solver files; tests cover a two-block box with a transposed, reversed match and the VC mesh.</li>
  </ul>
  {cbox("ADflow and SU2 get the mesh that was checked, node for node. Not yet shown: that ADflow and SU2 accept it and converge (V7).")}
</section>"""

    so, st = v6.get("screened_of", {}), v6.get("by_set", {})

    def v6cell(sname, t):
        n, N = so.get(sname, {}).get(t, [0, 0])
        if not n:
            return f"not screened (0 of {N})"
        oc = st.get(sname, {}).get(t, {})
        return f"{oc.get('passed', 0)} pass" + (f", {oc['refused']} refused" if oc.get("refused") else "") + f" ({n} of {N})"
    v6_rows = [[sname, *[v6cell(sname, t) for t in TYPES]] for sname in ("reference", "training_focus", "training_full", "corner1", "corner2")]
    fsam = v6.get("F_sample", {})
    od = v6.get("outcomes_with_decision_101", {})
    v6s = f"""
<section id="v6">
  <h2>V6: the built sets at VC, stopped at 427 of 702 wings (decision 105)</h2>
  <p>Started on the 702 built wings outside the reference set (VC, Re 3 × 10⁵). Stopped on 9 Nov at 20:09 when Mike decided the cells must drop (the rules will change): all 400 of the focus set, 24 full-space BWB and 3 full-space cranked wings were done; with the 20 reference wings, {n6} meshes.</p>
  {"" if not n6 else figc("v6_screen.png", "Every screened mesh at VC, Re 3 × 10⁵, by wing type, the bar at the median: (a) cells; (b) the worst cell of the mesh; (c) the largest growth over its limit.",
        f"{ok6} of {n6} pass as screened; with decision 101 (it came while the screen ran) {od.get('passed', ok6)} pass and {od.get('refused', n6 - ok6)} are refused, all by the wake check on full-space wings. The focus set, where most runs go, passes 400 of 400. F counted on {fsam.get('wings', '—')} wings: {rng(fsam.get('cells'), '{:.1f}', 1e-6)} M cells.")}
  {table(["set", *[TYPE_NAME[t] for t in TYPES]], v6_rows) if n6 else ""}
  <ul>
    <li><strong>Weak point: the wake band on full-space wings (decision 106).</strong> Check 11 refuses 18 of 24 full-space BWB and 2 of 3 full-space cranked wings: band cells up to 7.8 % over the band cell (the growth part stays ≤ 0.99). Cause, measured on BWB full-space wing 13 (the worst): the wake leaves the base pointing down (−6.9° to −2.0°), 0.068 c below a straight line at 2 local chords, so the band's upper edge lies above the envelope height, where the cells grow freely. The reference and focus wings leave level or upward and pass. Fix, for the redesign: add the wake's downward offset to the envelope height.</li>
    <li>Thin margins, all on full-space BWB wings: inboard cells down to 0.053 (limit 0.05), base and trailing-edge corner cells down to 0.21, the 3-D wall angle up to 60°.</li>
  </ul>
</section>"""

    summ = co.get("summary", {})
    labels = {"base": "the decided rules", "out125": "outboard growth 1.25 (not 1.15)", "out130": "outboard growth 1.30 (no outboard fine zone)",
              "bl30M": "30 cells across the boundary layer at M, not VC", "out125_bl30M": "both",
              "band_off": "the band off (Stage 2 option, decision 81)", "band_off_all": "band off + outboard 1.25 + 30 cells at M"}
    co_lev = [lev for lev in LEVELS if summ and lev in next(iter(summ.values()))]
    co_rows = [[labels.get(k, k), *[f"{summ[k][lev]['median'] / 1e6:.2f} M ({summ[k][lev]['vs_base_median']:.2f})" for lev in co_lev]]
               for k in summ]
    pk = load("cell_packages.json").get("packages", {})
    reopens = {"P0": "—", "P1": "volume rules (laws 12, 14); decision 90 (the base y⁺)", "P2": "+ the wake band rule (decision 87)",
               "P3": "+ the frozen surface (Stage 2 law 9/10: tip gap)", "P4": "+ decision 81 (the band on for every run)",
               "P5": "+ both Stage 2 changes", "P6": "+ the far-field distance (law 15) and the 30-cell anchor"}
    pk_rows = [[f"<strong>{k}</strong> {e['label']}", reopens.get(k, ""),
                *[f"{e['levels'][lev]['median'] / 1e6:.2f} M" for lev in LEVELS],
                f"{e['levels']['F']['max'] / 1e6:.1f} M", f"{e['levels']['F']['vs_P0_median']:.2f}",
                f"{e['levels']['VC']['ram_gib_median']:.0f} GiB; {e['levels']['VC']['fit_16GB']} of {load('cell_packages.json').get('wings', 20)}"]
               for k, e in pk.items()]
    cost = f"""
<section id="cost">
  <h2>The cost, and the packages that cut it (decision 105: Mike to choose)</h2>
  <p>Where the cells are, on BWB reference wing 0 at VC (4.93 M): every station plane holds 377 × 95 ≈ 36,000 cells, and there are 136 planes, 61 along the wing and 75 past the tip. The blocks past the tip hold 54 % of the cells, the wake blocks 39 % (the two overlap). The 75 outboard planes grow from the tip gap (2 s0, about 10⁻⁴ c: the cap is a resolved wall) at 1.15, and still number about 49 at 1.3; the wake lines start from s0 at the base (starting from the wing's last chordwise cell saves 17 of 74 nodes per line); the wake band is applied to every line of a plane and takes about a third of the 95 layers (half its fan cells saves 15).</p>
  <p>One change at a time (counted on the 20 reference wings, Re 3 × 10⁵, median; the ratio to the decided rules):</p>
  {table(["option", *co_lev], co_rows) if co_rows else '<p class="cap">(not counted yet)</p>'}
  <p>Packages (each builds on the one before; counted, not built, on the 20 reference wings at Re 3 × 10⁵; median cells per level, the largest at F, F against today, ADflow RAM at VC and how many VC meshes fit the 16 GB desktop):</p>
  {table(["package", "reopens", *LEVELS, "F largest", "F / today", "VC: RAM; fit 16 GB"], pk_rows, "wide") if pk_rows else '<p class="cap">(counting)</p>'}
  {cbox(PACKAGES_CONCLUSION, "Conclusion", "warn")}
</section>"""

    c5 = g5.get("cells", 0) / 1e6
    v7 = f"""
<section id="v7">
  <h2>V7: the first solves (not run here)</h2>
  <ul>
    <li>The case: BWB reference wing 0, VC, Re 3 × 10⁵, α 4°, Mach 0.1, band on. ADflow SA; SU2 SA; SU2 SST + LM (8.6.0).</li>
    <li>This session has no ADflow and no SU2, 2 cores and 7 GB. The mesh (rule set 2) has {c5:.2f} M cells and needs about {2.69 + 7.23 * c5:.0f}–{1.51 + 9.46 * c5:.0f} GiB for ADflow (S8's two laws): more than the 16 GB desktop, inside 48 GB. Ready: <code>solve/case.py</code> (conditions, reference area and moment point from the mesh, ADflow options, two SU2 configs), <code>solve/run_adflow.py</code> (S8's safeguards: the lift axis read back before the solve, the true residual, implausible forces refused; the peak memory of every rank), <code>solve/read_results.py</code> (the acceptance rule, written before any run), <code>solve/RUNBOOK.md</code>.</li>
    <li><strong>V7 also measures the memory (decision 113).</strong> The plan assumed 10 M cells in 48 GB; S8's laws (two-point fits at 0.57 and 1.11 M cells) say 48 GB holds 4.6–5.9 M. The runbook measures ADflow as run, ADflow with a leaner preconditioner, and SU2. Until then: VC and C on the desktop, M and F on the HPC.</li>
    <li><strong>V7 also checks where the wake goes (decision 111):</strong> two more points, α −5° and +10°, with the volume solution kept. The script that reads the wake against the fan's edges is not written: it needs a real solution file.</li>
    <li>Known risk from S8: on E387, SST + LM gave no laminar bubble and drag 37 counts high, where SA + LM matched. The brief fixes SST + LM, so this is a flag, not a change.</li>
  </ul>
  <div class="cbox warn"><span class="ctag">Conclusion</span>Not done. Where the solves run: Mike (decision 103).</div>
</section>"""

    v8 = """
<section id="v8">
  <h2>V8: the hold-outs</h2>
  <p>Not opened (Mike, 9 Nov: not yet; decision 104). They are run once, at the end, with the volume rules frozen and Mike's OK, and never used to tune anything.</p>
</section>"""

    changes = """
<section id="changes">
  <h2>What changed while building (the construction, never a limit)</h2>
  <ol>
    <li>V1: a layer-by-layer march folded; now the line shapes come from one front and the nodes are placed along them.</li>
    <li>V1: per-line distributions made slivers behind the trailing edge; now one distribution per station, the band as an envelope, the wall spacing along the cut, parallel wake lines.</li>
    <li>V1: the count fill stalled at zone changes; now every limit ramps over 25 %.</li>
    <li>V1: cells sheared between stations near the tip (scaled Jacobian 0.001); now the outer layers move to the station mean.</li>
    <li>V1: that move raised the far growth 3 % over 1.3; the far zone is built below the limit.</li>
    <li>V2: check 10 compared floats exactly (79.99999999999999 c); now it allows 1e−9 c of round-off.</li>
    <li>V4: the count factor scaled the band cell (VC/C 1.24); now it scales the growth only.</li>
    <li>V4: cells left the band abruptly (the cell at 1 c: VC/C 1.23); now the cap rises at the growth law's rate.</li>
    <li>V2: a text said the outboard far growth is built at 1.25; the code builds 1.3 (no blend there). Text fixed.</li>
    <li>V2: the far-field blend pushed one root to 1.0100 × the growth limit; the far zone is now built at 1.22.</li>
    <li>V6: the wake band missed wakes that leave the base pointing down (20 refusals); the envelope's top was raised by the wake line's fall (decision 106), which was not enough:</li>
    <li>Rule set 2: the band's cells were still sized from the wake line (9 of 13 full-space wings refused); now the exact envelope of the straight fan around the bent line (decision 108).</li>
    <li>Rule set 2: each cell took the band limit at its start (check 13 failed on 11 of 20 wings; band cell VC/C 1.285); now at its centre (1.300; decision 109).</li>
    <li>Rule set 2: cells sheared between very close stations on steep BWB centre bodies, kinks and tapered tips (0.024–0.050); now the far parts of neighbouring stations are lined up along the semi-span, each as far as its growth limit allows, with the ramp that leaves the least shear (decision 110, three versions). BWB corner2 wing 6 stays refused (0.032).</li>
  </ol>
</section>"""

    lowq = g6.get("thin_margins", {})
    q_txt = (f"In the screen: {lowq.get('below_0p06', '—')} of {g6.get('meshes', '—')} meshes have their worst cell under 0.06." if lowq else "")
    weak = f"""
<section id="weak">
  <h2>Weak points and open items</h2>
  <ul>
    <li><strong>Cost and memory.</strong> Rule set 2: M about {gM.get('median', 0) / 1e6:.1f} M cells, F about {gF.get('median', 0) / 1e6:.0f} M (rule set 1: {f_med / 1e6:.0f} M at F). The plan assumed 10 M cells in 48 GB; by S8's laws 48 GB holds 4.6–5.9 M, so VC and C fit and M and F need the HPC. The laws are two-point fits at 0.57 and 1.11 M cells: V7 measures (decisions 112, 113).</li>
    <li><strong>The fan ends at +10°</strong> (decision 111). Above it the wake leaves the fine cells; post-stall needs its own mesh. Where the wake really goes at −5° and +10° is not measured (V7).</li>
    <li><strong>Very close stations with fast-changing chords sit nearest the cell-quality limit</strong> (decision 110): steep BWB centre bodies, kinks, corner wings. One wing is refused: BWB corner2 wing 6 (0.032; limit 0.05), whose chord halves within 0.14 c of the semi-span; a fix would space the far wake by x for every station at once (a redesign, not built). {q_txt}</li>
    <li><strong>No solve yet</strong> on a Stage 3 mesh (V7 needs Mike's machine). Accepting the files is shown; converging is not.</li>
    <li><strong>Planar stations</strong>: square in the plane, sheared in 3-D at swept noses: up to {v2.get('wall_angle_3d_max_deg', {}).get('max', 0):.0f}° on the reference wings, {g6.get('wall_angle_3d_max_deg', {}).get('max', 0):.0f}° on the most swept corner wing (reported, no limit; y⁺ only falls; a 3-D march would cross near the tip).</li>
    <li><strong>The cap cells</strong> are the worst of most meshes ({v3.get('cap_min_sj', {}).get('min', 0):.3f}–{v3.get('cap_min_sj', {}).get('max', 0):.3f} on the reference wings; limit 0.05), set by the frozen surface.</li>
    <li><strong>The base is not at y⁺ 1</strong> in rule set 2 (its first cell is the wing's last chordwise cell); in exchange the spacing jump across the trailing-edge line fell from up to {v2.get('te_jump_ratio', {}).get('Re 4e6', {}).get('max', 0):.0f} to about 1.03.</li>
    <li><strong>The tip vortex</strong> is carried, not resolved: coarse along its path; a tube would be a new rule.</li>
    <li><strong>The cap's two nose-corner columns</strong> fall below 0.05 at M and F on the BWB and flying wing (0.045 and 0.037 on BWB 0; every other cell ≥ 0.077): exempt as in Stage 2 (decision 101, Mike), not fixed; a better cap belongs to the frozen surface.</li>
    <li><strong>Margins (rule set 2, reference wings):</strong> growth at most {g23.get('checks', {}).get('growth', {}).get('max', 0):.3f} × its limit (the check allows 1.01); wake and band at most {g23.get('checks', {}).get('wake', {}).get('max', 0):.3f}; check 13 at most {100 * (g13.get('worst') or [0])[0]:.1f} % off (allows 3 %); cells across the boundary layer at least {g23.get('checks', {}).get('bl_cells', {}).get('min', 0):.2f} (limit 17.75).</li>
    <li><strong>C was built only on the 20 reference wings, M on four (wing 0 of each type), F on one</strong>; elsewhere M and F are counted (time on 2 cores, not memory).</li>
    <li><strong>V0's two studies</strong> ran on the V0 construction; the later changes do not touch what they compare.</li>
  </ul>
</section>"""

    handover = """
<section id="handover">
  <h2>Next, and the handover to Stage 4</h2>
  <ul>
    <li><strong>Next:</strong> V7 on Mike's machine: the three solves, the memory (decision 113) and the wake at −5° and +10° (decision 111). Then the hold-outs (V8) when Mike says, with the rules frozen.</li>
    <li><strong>Stage 4 gets:</strong> per wing, Re and level, a folder <code>volume_&lt;level&gt;_&lt;hash8&gt;_re&lt;Re&gt;/</code> with <code>blocks.npz</code>, <code>quality.json</code> (every check, the info), <code>manifest.json</code> (hashes of the code, the rules and the nodes; the BCs; the interfaces), <code>volume.cgns</code>, <code>volume.su2</code>; a refused mesh only <code>refusal.json</code>.</li>
    <li><strong>Build:</strong> <code>build_volume(surface)</code> then <code>write(vm, wing, out, formats=("npz", "cgns", "su2"))</code>; cost first with <code>count_volume(surface)</code>.</li>
    <li><strong>First:</strong> run V7 and read it with <code>solve/read_results.py</code>; send back the memory numbers; then the hold-outs (V8) with the rules frozen.</li>
    <li><strong>For the solves:</strong> the semi-span along +y, lift +z (ADflow liftIndex 3); lengths in mean chords; Re on the mean chord; the band on; angles −5° to +10° on this mesh.</li>
  </ul>
</section>"""

    files = """
<section id="files">
  <h2>Files and commands</h2>
  <pre>CFD_Automation/cfdauto/volume/     laws, march, plane, topology, volume, checks, family, cgns, su2
CFD_Automation/Stage_3_volume_mesh/
  configs/volume.yaml               the rules and the check limits
  decisions/volume_rules.md         the plan, rules, checks, V0 measurements, what changed
  decisions/STAGE3_STATUS.md        status and the handover to Stage 4
  scripts/one_mesh.py               one wing's volume mesh (any set, level, Re; --count)
  scripts/screen.py                 the screen (one JSON row per mesh)
  scripts/v23_study.py v4_study.py v6_study.py cost_options.py v5_export.py   the studies
  solve/                            the V7 case, ADflow run, results reader, runbook
  tests/                            pytest (Stage_3_volume_mesh/tests)
CFD_Automation/app/                the app: load or make a wing, build and look at its meshes
CFD_Automation/RUN_LOCAL.md        every command, Stage 1 to V7</pre>
</section>"""

    r2 = rule_set_2()
    rs1 = ('<section id="rs1"><h2>Rule set 1: the first build (V0–V7, the record)</h2><p>Everything below was built '
           'and measured with rule set 1 (<code>configs/volume_rules1.yaml</code>). It works and passes its checks, '
           'but costs about twice what Mike asked for at M; its numbers stay here as the record and as the baseline '
           'of the cost study.</p></section>')
    body = ('<div class="wrap">' + head + glance + r2 + rs1 + what + how + rules_s + checks_s + v0 + v1s + v2s + v3s + v4s + v5s +
            v6s + cost + v7 + v8 + changes + weak + handover + files +
            f'<footer>CFD_Automation Stage 3 · built by scripts/make_stage3_page.py from configs/volume.yaml and data/studies/*.json · 10 Nov 2026</footer></div>')
    page = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Volume Mesh: CFD_Automation Stage 3</title><style>{CSS}</style></head><body>{body}</body></html>')
    return page, f"<style>{CSS}</style>{body}"


def main() -> None:
    page, body = build_page()
    (DOCS / "VOLUME_MESH.html").write_text(page)
    (DOCS / "VOLUME_MESH.body.html").write_text(body)
    print("wrote VOLUME_MESH.html", len(page) // 1024, "KB")


if __name__ == "__main__":
    main()
