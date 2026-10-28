"""One HTML page to understand and evaluate the wing generator fast, with the pictures embedded.

    python scripts/make_generator_visuals.py     # first: the GIFs and PNGs
    python scripts/make_generator_page.py        # then: docs/GEOMETRY_GENERATOR.html

The variables table, the set results and the verification numbers are read from
configs/wing.yaml, data/sets/*/*_manifest.json and docs/verification.json, so they
stay current. The design decisions, the fixes and the open questions are written
below (DECISIONS, FIXES, OPEN, LIMITS): edit them when a decision changes.
"""

from __future__ import annotations

import base64
import html
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto import __version__  # noqa: E402
from cfdauto.geometry import airfoils, published_wings  # noqa: E402
from cfdauto.geometry.params import VARIABLES, load_config  # noqa: E402
from cfdauto.geometry.planform import aspect_ratio, mean_aero_chord  # noqa: E402
from cfdauto.geometry.sections import build_wing_sections  # noqa: E402

DOCS = ROOT / "docs"
SETS = ROOT / "data" / "sets"
TESTS_LINE = "122 pass without pyGeo, 11 more need pyGeo (run 28 Oct 2026)"

# --------------------------------------------------------------------------------------
# Content written by hand. Keep it short and plain.
# basis: req = your requirement, src = published source or tool, meas = measured here,
#        own = our choice, no source yet.   flag: "fix" (fix before Stage 2), "open" (needs a decision)
# --------------------------------------------------------------------------------------

MEANING = {
    "root_chord_m": "root chord (m)",
    "c2_ratio": "chord at b1 / root chord",
    "c3_ratio": "chord at b2 / root chord",
    "c4_ratio": "tip chord / root chord",
    "semi_span_m": "semi-span (m); conventional: in root chords",
    "b3_ratio": "outer panel span / semi-span",
    "split_ratio": "inner panel / (inner + middle)",
    "sweep1_deg": "LE sweep, panel 1 (+ aft)",
    "sweep2_deg": "LE sweep, panel 2",
    "sweep3_deg": "LE sweep, panel 3",
    "twist0_deg": "twist at b0 (+ nose up)",
    "twist1_deg": "twist at b1",
    "twist2_deg": "twist at b2",
    "twist3_deg": "twist at b3 (tip)",
    "dihedral0_deg": "dihedral at b0 (+ tip up)",
    "dihedral1_deg": "dihedral at b1",
    "dihedral2_deg": "dihedral at b2",
    "dihedral3_deg": "dihedral at b3",
}

DECISIONS = [
    ("Inputs", [
        ("One generator, one YAML", "<code>wing_type: bwb | conventional | mixed</code>; <code>mixed</code> draws both with stated shares (50/50).",
         "One design space and one contract. Two generators would mean two of each.", "req", ""),
        ("Same 18 variables for every type", "Each type has its own range block in <code>configs/wing.yaml</code>.",
         "One vector shape for sampling, hashing and ML.", "own", ""),
        ("Everything varies", "A value is fixed only through <code>pinned:</code>.", "A study may pin; the default never does.", "req", ""),
        ("Chord law", "<code>stations</code>: c2, c3, c4 drawn freely. <code>linear_taper</code>: c2, c3 follow from the tip chord.",
         "Straight-tapered wings need the second option.", "req", ""),
        ("Span mode", "<code>semi_span</code> (metres) or <code>root_chord_fractions</code> (semi-span read in root chords).",
         "BlendedNet gives spans in root chords. Conventional uses it so the aspect ratio stays 4–16.5.", "own", "open"),
        ("Ranges", "BWB: AERIS <code>bwb.yaml</code>, sweeps signed, dihedral 0–3° now allowed at b0 and b1. Conventional: proposed (root chord 0.15–1.35 m, AR 4–16.5, taper ≥ 0.4, sweep −10° to +20°, dihedral −3° to +6°).",
         "BWB keeps the AERIS space. Conventional covers Raven to Hermes-450 size and reaches Re 5 × 10⁶.", "own", "open"),
        ("Wing class", "<code>wing_class: I | II</code> sets the trailing-edge floor.", "Manufacturing differs by size.", "req", ""),
    ]),
    ("Planform", [
        ("Exact straight panels", "Leading and trailing edges are straight lines through b0–b3. Chords and sweeps equal the vector exactly.",
         "The old AERIS spline put the b2 chord up to 20 % off; a 12°/6°/6° wing came out 7.9°/7.9°/6.5°.", "meas", ""),
        ("Signed sweep", "Leading-edge sweep, positive aft. Forward sweep is allowed by the ranges, not blocked by code.", "Conventional wings need it.", "req", ""),
        ("No curved BWB centre body", "Not in this stage. To add later with a check that rejects wavy edges.",
         "Straight panels first. So today's BWB is a cranked tailless wing with a long root chord.", "own", ""),
    ]),
    ("Sections, twist, dihedral", [
        ("Vertical sections", "Every section is parallel to the symmetry plane and twisted about its leading edge.",
         "The root then stays in y = 0 with any dihedral, so the two halves never cross. AERIS rolled the root, so it had to force zero dihedral there. Cost: on a panel with dihedral Γ the true thickness is cos Γ smaller (1.5 % at 10°).", "own", ""),
        ("Height from dihedral", "z = ∫ tan(dihedral) dy, dihedral linear between stations (AERIS formula). Each straight panel gets one dihedral, the mean.",
         "Exact and independent of how the span is cut. But 4 station values give only 3 panel angles: see fix 1.", "own", "fix"),
        ("Twist", "Exact at the four stations; between them it follows the straight panel.",
         "Straight panels and linear twist cannot both hold. Difference 0.1–0.3 % of chord at the trailing edge.", "meas", ""),
    ]),
    ("Airfoils", [
        ("Any airfoil by name", "Search order: <code>geometry/airfoils/</code> → AERIS database (2,159 of 2,181 files load) → NACA 4/5-digit formula. A station may list candidates; the sampler draws them evenly. One wing may carry its own four names.",
         "BlendedNet (NACA 25118), M6, RIBES and CRM need sections outside the default list.", "own", "open"),
        ("Default sections", "BWB: MH91, MH91, E374, NLF1015 (from AERIS). Conventional: NACA 4415, 4415, 4412, 4412.", "Common choices for these wing types.", "own", ""),
        ("One way to read every file", "Leading edge = the point farthest from the trailing-edge midpoint; unit chord; both sides resampled on cosine x, in √x.",
         "The nose tangent is square to the chord, and every section has the same points, so the loft can join them.", "own", ""),
        ("Typo points dropped", "A single point that spikes off a smooth line is removed (18 database files, e.g. sc20412 at x/c 0.73).",
         "One bad point would put a bump in the surface.", "own", "open"),
    ]),
    ("Trailing edge", [
        ("Thickness rule", "Class I: max(0.5 mm, 0.2 % of local chord). Class II: max(1.0 mm, 0.2 %).",
         "Real wings are blunt. In AERIS, 0.5 % carried about a fifth of the pressure drag; 0.2 % with 8 base cells carried 2–4 %. 0.2 % is also pyGeo's default. The floors still need a builder's confirmation.", "meas", "open"),
        ("Made in the generator", "On the 2-D airfoil, before the loft. Not in the mesher.",
         "AVL, CFD and CAD see one wing. The AERIS mesher made 4.3 mm at one root, 2.4 times the rule, and moved lift 11–30 counts.", "meas", ""),
        ("How it opens", "pyGeo's method: linear ramp from x/c = 0.90 to the edge, half up, half down. Camber line unchanged.",
         "Same as <code>readAirfoilFile(bluntTe=True, bluntThickness=0.002, bluntTaperRange=0.1)</code>. Replaced the uncited 65 % start in v0.4. Cost: a 0.6° slope change at 90 % chord.", "src", ""),
        ("The rule wins over the file", "A file with its own blunt edge is set to the rule (NACA 4415: 0.32 % → rule). Published wings keep theirs (<code>as_is</code>).",
         "Sampled wings follow one rule; copies of real wings stay real.", "own", ""),
        ("Extra section at the switch", "Where the chord equals 0.25 m (Class I) or 0.5 m (Class II), a section is added.",
         "The loft blends thickness linearly; without it the edge would dip below the floor.", "own", ""),
    ]),
    ("Loft (the surface the mesher reads)", [
        ("Straight panels: kSpan = 2", "Sections only at b0–b3 plus switch points.",
         "kSpan 3 cut the corners at panel breaks by up to 4.8 % of chord; kSpan 2 is exact. It leaves a sharp kink at b1 and b2: see fix 4.", "meas", "fix"),
        ("Built with pySpline, one parameter s = √(x/c)", "Same construction as pyGeo's <code>liftingSurface</code>, held in a pyGeo object.",
         "<code>liftingSurface</code> split upper and lower 0.2–0.5 % of chord away from the nose. Here the split is exact and u = x/c on every station.", "meas", ""),
        ("Ask, never interpolate", "The mesher asks <code>upper(u, v)</code> and <code>lower(u, v)</code>; a 401-point table maps v to span.",
         "In AERIS, straight lines between stored sections missed the surface by up to 7.25 % of chord (ADR-0015).", "meas", ""),
        ("Tip", "Flat and open (<code>tip='none'</code>).", "Rounded tips are a later study.", "own", ""),
        ("Two backends, one export", "pyGeo (production, IGES) and numpy (same surface, no pyGeo). No STEP: pyGeo has no STEP writer.",
         "Tests and pictures run anywhere.", "own", ""),
    ]),
    ("Measure, label, hash", [
        ("Measured on the loft", "Chord, twist, LE position, sweep, dihedral, area, span, MAC, AR, thickness, trailing-edge thickness → <code>measured.json</code>.",
         "Later stages and any ML model use the measured wing; the vector is only its label.", "req", ""),
        ("Labels by rule", "BWB or conventional; swept, cranked, rectangular, washout, dihedral, aspect ratio. BWB threshold lowered from 2.5 to 2.2.",
         "Two wide BWB corners measured 2.39–2.5; conventional wings reach at most 1.84. Checked on 20 hand-labelled wings.", "meas", ""),
        ("Hash", "sha256 of the vector, the type's YAML block, the trailing-edge rule, the airfoil file contents and the code version.",
         "Content, never file names. Weak: the code version is a string set by hand: see fix 3.", "own", "fix"),
    ]),
    ("Sets", [
        ("Five sets per type", "Training 100 (Latin hypercube, seeds 1001/1002); corner 1: 36 (each variable at each bound); corner 2: 8 (every pair at all four low/high combinations); reference 5 (by rule); hold-out 10 (seeds 2001/2002).",
         "Training fills the inside, corners test the edges, the hold-out is the one honest test.", "req", ""),
        ("Failures stay in the list", "A refused wing keeps its row with the gate and the reason. Corners are never nudged inside.",
         "A failure marks the edge of the space.", "req", ""),
        ("Hold-out is never built here", "Only the vectors are saved.", "It is opened once, after the workflow is frozen.", "req", ""),
        ("Reference wings spread well", "Coverage distance BWB 1.49, conventional 1.50, against a median of 1.84 for 1,000 random sets of five (lower is better).",
         "Five wings must stand for the whole set.", "meas", ""),
    ]),
]

FIXES = [
    ("One dihedral variable does nothing.",
     "Four station dihedrals become three panel angles. [0, 3, 3, 6], [3, 0, 6, 3] and [1.5, 1.5, 4.5, 4.5] give the same wing to 0.003°. "
     "The gate compares with the derived angle, so it passes anyway.",
     "Use three panel dihedrals."),
    ("The conventional training set is not realistic.",
     "46 of 100 wings get wider toward the tip on at least one panel. 100 of 100 are labelled cranked; none is straight tapered and one is rectangular.",
     "Force c2 ≥ c3 ≥ c4 and draw part of the set with <code>linear_taper</code>."),
    ("The hash ignores code changes.",
     "It uses <code>__version__</code>, a string bumped by hand. The manifests were built with 0.1.0; the code is now __VERSION__ and the hash did not notice.",
     "Hash the source files (or the git commit)."),
    ("The loft has sharp kinks at b1, b2 and the switch sections.",
     "Correct for straight panels, but the S8 mesher does not place stations at the breaks. Flat mesh faces would then cut the corner, about 0.5 % of chord (a rough estimate).",
     "Stage 2 must put a mesh station exactly at every <code>station_v</code>. No change here; put it in the Stage 2 prompt."),
]

OPEN = [
    ("Conventional ranges", "Keep the proposed ranges (root chord up to 1.35 m so the mean chord reaches Re 5 × 10⁶)?"),
    ("BWB Reynolds number", "BWB stops at Re ≈ 3 × 10⁶. Widen the size range, or run 5 × 10⁶ as a flow condition only?"),
    ("Straight-tapered wings in training", "Use <code>linear_taper</code> for part of the set, or pin the sweeps equal? (Linked to fix 2.)"),
    ("Trailing-edge floor", "Confirm 0.5 mm / 1.0 mm with the builder. Run the 0.1 / 0.2 / 0.3 % sensitivity once CFD works."),
    ("Airfoil search order", "Project folder → AERIS database → NACA formula. Keep? 22 database files are refused."),
    ("Typo points", "Keep dropping single spikes, or fix the 18 files?"),
    ("NACA 25118 trailing edge", "Made from the formula (open edge, 0.38 %). OpenVSP may close it differently. Check with a BlendedNet STEP file."),
    ("NASA CRM", "Four stations and stand-in sections: a shape check only, or add a many-station mode for drag validation?"),
    ("BlendedNet twist and dihedral", "Set to zero because neither paper states them. Accept?"),
    ("Which published wing first", "RIBES is the only in-regime case; M6 and CRM are transonic."),
    ("RIBES trailing edge", "The fitted section has 0.26 %; the model measures 0.38–0.66 %. Rebuild before any drag comparison?"),
    ("Outside proof", "Only the M6 is checked against its own CAD (max 0.011 % of chord). BlendedNet, CRM and RIBES need their surface files."),
]

LIMITS = [
    "<strong>Straight edges only, three panels at most.</strong> No curved BWB centre body, no elliptic planform, no fourth panel.",
    "<strong>Airfoil shape is not a variable.</strong> Any named file can be used, and a station can draw from a list, but thickness and camber are not sampled continuously. The default sets use one section per station (t/c 11–15 %).",
    "<strong>No winglets, rounded or raked tips, fuselage, gaps.</strong> Dihedral is at most 10° (BWB) and 6° (conventional).",
    "<strong>0 refusals at the corners.</strong> The space is too safe to show where anything breaks. Robustness must be shown on the mesher, with lofts it has never seen (primer Track 5).",
    "<strong>Published wings:</strong> M6 and CRM are transonic (phase 1 stops at Mach 0.3). CRM is approximate. BlendedNet twist and dihedral are guessed as zero. Every tip is a flat cut, including the M6's rounded one.",
]

BASIS = {"req": ("Your rule", "req"), "src": ("Source", "src"), "meas": ("Measured", "meas"), "own": ("Our choice", "own")}
FLAG = {"fix": "Fix", "open": "Open"}


# --------------------------------------------------------------------------------------
# Tables built from the repo
# --------------------------------------------------------------------------------------

def img(name: str, alt: str) -> str:
    data = base64.b64encode((DOCS / name).read_bytes()).decode()
    mime = "image/gif" if name.endswith(".gif") else "image/png"
    return f'<img src="data:{mime};base64,{data}" alt="{html.escape(alt)}">'


def fmt(lo: float, hi: float) -> str:
    f = (lambda x: f"{x:g}")
    return f(lo) if lo == hi else f"{f(lo)} – {f(hi)}"


def variables_table() -> str:
    cfg = load_config()
    b, c = cfg.types["bwb"], cfg.types["conventional"]
    out = []
    for v in VARIABLES:
        def cell(spec):
            if v in spec.pinned:
                return f"{spec.pinned[v]:g} (pinned)"
            if spec.chord_law == "linear_taper" and v in ("c2_ratio", "c3_ratio"):
                return "from taper"
            return fmt(*spec.ranges[v])
        out.append(f"<tr><td><code>{v}</code></td><td>{html.escape(MEANING[v])}</td>"
                   f"<td class='num'>{cell(b)}</td><td class='num'>{cell(c)}</td></tr>")
    air = (f"<tr><td><code>airfoils</code></td><td>section at b0, b1, b2, b3</td>"
           f"<td>{', '.join('/'.join(x) for x in b.choices)}</td><td>{', '.join('/'.join(x) for x in c.choices)}</td></tr>")
    return "\n".join(out) + "\n" + air


def manifests() -> list[dict]:
    rows = []
    for t in ("bwb", "conventional"):
        for s in ("training", "corner1", "corner2", "reference", "holdout"):
            f = SETS / t / f"{s}_manifest.json"
            if f.is_file():
                d = json.loads(f.read_text())
                rows.append({"type": t, "set": s, "version": d.get("code_version", "?"), "wings": d["wings"]})
    return rows


SET_NAME = {"training": "training", "corner1": "corner 1", "corner2": "corner 2", "reference": "reference", "holdout": "hold-out"}


def sets_table(rows: list[dict]) -> str:
    out = []
    for r in rows:
        w = r["wings"]
        n = len(w)
        if r["set"] == "holdout":
            res, labels = "vectors only, not built", "—"
        else:
            ok = sum(1 for x in w if x.get("passed"))
            bad = Counter(x.get("gate") for x in w if x.get("passed") is False)
            res = f"{ok} built, {n - ok} refused" + (f" ({', '.join(f'{k} {v}' for k, v in bad.items())})" if bad else "")
            lab = Counter(l for x in w for l in (x.get("labels") or []) if l not in ("bwb", "conventional"))
            labels = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in lab.most_common(5))
        stale = "" if r["version"] == __version__ or r["set"] == "holdout" else f" <span class='flag open'>built with {r['version']}</span>"
        out.append(f"<tr><td><span class='tag {r['type']}'>{'BWB' if r['type'] == 'bwb' else 'Conv.'}</span></td>"
                   f"<td>{SET_NAME[r['set']]}</td><td class='num'>{n}</td><td>{res}{stale}</td><td class='muted'>{labels}</td></tr>")
    return "\n".join(out)


def verification_table() -> str:
    f = DOCS / "verification.json"
    if not f.is_file():
        return "<tr><td colspan='5'>Run <code>python scripts/verify_geometry.py</code>.</td></tr>"
    out = []
    for r in json.loads(f.read_text()):
        cad = r.get("cad")
        cad_s = f"max {cad['max_pct_chord']:.4f}" if cad else "no outside file"
        out.append(f"<tr><td><code>{r['wing']}</code></td><td class='num'>{r['sections_max_pct']:.4f}</td>"
                   f"<td class='num'>{r['edges_max_pct']:.0e}</td><td class='num'>{cad_s}</td>"
                   f"<td>{'<span class=\"flag ok\">pass</span>' if r['pass'] else '<span class=\"flag fix\">fail</span>'}</td></tr>")
    return "\n".join(out)


def decisions_html() -> str:
    out = []
    n = 0
    for group, items in DECISIONS:
        out.append(f"<tr class='grp'><td colspan='4'>{html.escape(group)}</td></tr>")
        for title, choice, why, basis, flag in items:
            n += 1
            label, cls = BASIS[basis]
            fl = f" <span class='flag {flag}'>{FLAG[flag]}</span>" if flag else ""
            out.append(f"<tr><td class='what'><span class='id'>D{n}</span>{title}{fl}</td><td>{choice}</td>"
                       f"<td>{why}</td><td><span class='basis {cls}'>{label}</span></td></tr>")
    return "\n".join(out)


def basis_counts() -> str:
    c = Counter(b for _, items in DECISIONS for *_, b, _f in items)
    return " · ".join(f"<span class='basis {BASIS[k][1]}'>{BASIS[k][0]}</span> {c[k]}" for k in ("req", "src", "meas", "own"))


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


def glance(rows_: list[dict]) -> dict:
    built = [w for r in rows_ if r["set"] != "holdout" for w in r["wings"]]
    ok = sum(1 for w in built if w.get("passed"))
    versions = sorted({r["version"] for r in rows_})
    ver = json.loads((DOCS / "verification.json").read_text()) if (DOCS / "verification.json").is_file() else []
    return {"built": len(built), "ok": ok, "stale": versions != [__version__], "versions": ", ".join(versions),
            "pub": len(ver), "pub_ok": sum(1 for v in ver if v["pass"])}


# --------------------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------------------

PAGE = """<title>Wing Generator</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@500&display=swap">
<style>
/* Layout: one reading column, verdict first, then decisions as one scannable table; pictures on white cards. */
:root {
  --bg: #F3F6F9; --surface: #FFFFFF; --ink: #142230; --muted: #566573; --line: #D6DEE6; --grp: #E8EEF4;
  --accent: #0C5EA8; --bwb: #2E8B57; --warn: #B02A20; --amber: #9A6200; --violet: #6A4BB0;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F; --grp: #1C2732;
  --accent: #62AEF2; --bwb: #5FC48F; --warn: #F08A80; --amber: #E7B24F; --violet: #B49BF0; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F; --grp: #1C2732;
  --accent: #62AEF2; --bwb: #5FC48F; --warn: #F08A80; --amber: #E7B24F; --violet: #B49BF0; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 28px 56px; }
.wrap { max-width: 1100px; margin: 0 auto; display: flex; flex-direction: column; gap: 36px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 16px; display: flex; flex-direction: column; gap: 10px; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { font-family: var(--display); font-size: clamp(32px, 5vw, 46px); line-height: 1.05; margin: 0; text-wrap: balance; }
h2 { font-family: var(--display); font-size: 28px; margin: 0; text-wrap: balance; }
p { margin: 0; max-width: 75ch; }
section { display: flex; flex-direction: column; gap: 14px; scroll-margin-top: 12px; }
.lede { color: var(--muted); font-size: 17px; }
nav { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 14px; }
nav a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
nav a:hover, nav a:focus-visible { border-bottom-color: currentColor; outline: none; }
.card { background: #FFFFFF; border: 1px solid var(--line); border-radius: 6px; padding: 10px; overflow-x: auto; }
.card img { display: block; width: 100%; height: auto; max-width: 100%; }
.cap { color: var(--muted); font-size: 14px; }
.three { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.box { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.box h3 { margin: 0; font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.box .big { font-family: var(--display); font-size: 24px; line-height: 1.1; }
.box.verdict { border-color: var(--amber); }
.box.verdict .big { color: var(--amber); }
code, pre { font-family: var(--mono); font-size: 13px; }
pre { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; overflow-x: auto; margin: 0; }
.tbl { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
table.wide { min-width: 900px; }
table.mid { min-width: 640px; }
th, td { text-align: left; vertical-align: top; padding: 9px 12px; border-bottom: 1px solid var(--line); }
tr:last-child td { border-bottom: 0; }
th { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
tr.grp td { background: var(--grp); font-family: var(--display); font-size: 18px; padding-block: 6px; }
td.what { font-weight: 700; width: 19%; }
td.what .id { display: block; font-family: var(--mono); font-weight: 500; font-size: 11px; color: var(--muted); }
td.num { font-family: var(--mono); font-size: 13px; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.src { font-size: 12.5px; color: var(--muted); width: 22%; }
.muted { color: var(--muted); font-size: 13px; }
.tag, .basis, .flag { font-family: var(--mono); font-size: 11px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; border: 1px solid currentColor; white-space: nowrap; font-weight: 500; }
.tag.conventional { color: var(--accent); } .tag.bwb { color: var(--bwb); }
.basis.req { color: var(--violet); } .basis.src { color: var(--accent); } .basis.meas { color: var(--bwb); } .basis.own { color: var(--amber); }
.flag.fix { color: var(--warn); } .flag.open { color: var(--amber); } .flag.ok { color: var(--bwb); }
.legend { font-size: 13px; color: var(--muted); display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; }
.weak { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--warn); border-radius: 6px; padding: 14px 18px; }
.weak ul, .weak ol { margin: 6px 0 0; padding-left: 22px; display: flex; flex-direction: column; gap: 10px; }
.weak.amber { border-left-color: var(--amber); }
.fixrow strong { display: block; }
.fixrow .do { color: var(--ink); font-weight: 600; }
footer { color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 12px; }
@media (prefers-reduced-motion: reduce) { .card img[src^="data:image/gif"] { animation: none; } }
</style>
<div class="wrap">
<header>
  <div class="eyebrow">CFD_Automation · Stage 1 · geometry · code __VERSION__</div>
  <h1>Wing Generator</h1>
  <p class="lede">Eighteen numbers go in; one exact wing surface comes out, measured, labelled and checked. One generator and one YAML file make BWB and conventional wings. Every later stage (mesh, solver, data) reads only this surface.</p>
  <nav aria-label="On this page"><a href="#glance">At a glance</a><a href="#fix">Fix before Stage 2</a><a href="#decisions">Design decisions</a><a href="#variables">The 18 numbers</a><a href="#checks">Checks and results</a><a href="#open">Open decisions</a><a href="#limits">What it cannot make</a><a href="#published">Published wings</a><a href="#commands">Commands</a></nav>
</header>

<section id="glance">
  <h2>At a glance</h2>
  <div class="three">
    <div class="box"><h3>In</h3><div class="big">18 numbers + a wing type</div><p>From <code>configs/wing.yaml</code>: chords, spans, sweeps, twists, dihedrals, and an airfoil per station.</p></div>
    <div class="box"><h3>Out</h3><div class="big">One surface, checked</div><p>Upper, lower and trailing-edge base, read as <code>upper(u, v)</code>. Plus measured values, labels, four refusing checks, a hash, IGES.</p></div>
    <div class="box"><h3>Evidence</h3><div class="big">__OK__ of __BUILT__ wings pass</div><p>Sampled wings, both types, 0 refused (built with __SETVER__). __PUBOK__ of __PUB__ published wings verified. Tests: __TESTS__.</p></div>
    <div class="box verdict"><h3>Verdict</h3><div class="big">Ready for Stage 2 after four fixes</div><p>Not yet "any wing": straight panels only, no airfoil shape variable. Sets must be rebuilt: __STALE__</p></div>
  </div>
</section>

<section id="fix" class="weak">
  <h2>Fix before Stage 2</h2>
  <p class="muted">Each fix changes the hashes, so do all four before one rebuild.</p>
  <ol>
__FIXES__
  </ol>
</section>

<section>
  <h2>One wing, step by step</h2>
  <div class="card">__GIF_BUILD__</div>
  <p class="cap">Seven steps: design vector, planform, sections, twist and dihedral, trailing edge, loft, measure-label-check. Example: a BWB with every variable at mid-range.</p>
</section>

<section id="decisions">
  <h2>Design decisions</h2>
  <p>Every choice behind the generator, with its reason and what it rests on. Details: <code>geometry/decisions/</code> and <code>Stage 0_Decisions/OPEN_DECISIONS.md</code>.</p>
  <div class="legend">Basis: __BASIS__ · <span class="flag fix">Fix</span> needs a change · <span class="flag open">Open</span> needs your call</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Decision</th><th>What we do</th><th>Why</th><th>Basis</th></tr></thead>
    <tbody>
__DECISIONS__
    </tbody>
  </table></div>
</section>

<section id="variables">
  <h2>The 18 numbers</h2>
  <p>Four stations: root b0, breaks b1 and b2, tip b3. Three straight panels between them. Ranges as in <code>configs/wing.yaml</code> now.</p>
  <div class="tbl"><table class="mid">
    <thead><tr><th>Variable</th><th>Meaning</th><th>BWB</th><th>Conventional</th></tr></thead>
    <tbody>
__VARS__
    </tbody>
  </table></div>
</section>

<section id="checks">
  <h2>Checks and results</h2>
  <div class="three">
    <div class="box"><h3>Gate 1 · vector → loft</h3><p>Measured on the loft: chords within 0.1 %, sweeps 0.1°, twist 0.2°, dihedral 0.2°.</p></div>
    <div class="box"><h3>Gate 2 · trailing edge</h3><p>Thickness equals the rule at every section, within 1 µm.</p></div>
    <div class="box"><h3>Gate 3 · validity</h3><p>Sections closed, upper never below lower, root flat in y = 0 within 1e-9 m, chords positive.</p></div>
    <div class="box"><h3>Gate 4 · repeatability</h3><p>Two builds give the same surface hash.</p></div>
  </div>
  <p class="muted">A wing that fails any gate is not written; its row keeps the gate and the reason. The fifth check, mesh on the loft within 1e-9 m, belongs to Stage 2.</p>
  <h2 style="font-size:22px">Sample sets</h2>
  <div class="tbl"><table class="mid">
    <thead><tr><th>Type</th><th>Set</th><th>Wings</th><th>Result</th><th>Main labels</th></tr></thead>
    <tbody>
__SETS__
    </tbody>
  </table></div>
  <h2 style="font-size:22px">Is the surface the intended wing?</h2>
  <p class="muted">Errors in % of local chord. Sections: the loft cut at each station against the original airfoil points (limit 0.01). Edges: against the exact straight lines (limit 1e-6). Outside CAD: only the M6 has one (limit 0.05).</p>
  <div class="tbl"><table class="mid">
    <thead><tr><th>Wing</th><th>Sections max</th><th>Edges max</th><th>Outside CAD</th><th>Result</th></tr></thead>
    <tbody>
__VERIFY__
    </tbody>
  </table></div>
</section>

<section id="open" class="weak amber">
  <h2>Open decisions</h2>
  <p class="muted">Choices made to keep going that still need your call.</p>
  <ul>
__OPEN__
  </ul>
</section>

<section id="limits" class="weak">
  <h2>What it cannot make (yet)</h2>
  <ul>
__LIMITS__
  </ul>
</section>

<section id="published">
  <h2>Published wings it rebuilds</h2>
  <div class="card">__GIF_REF__</div>
  <p class="cap">Each frame is a wing rebuilt by the same generator, with the same loft and checks as the sampled wings. BlendedNet wings are made directly from the BlendedNet parameters.</p>
  <div class="card">__PNG_TOP__</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Wing</th><th>Type</th><th>Size</th><th>What it is for</th><th>How close the copy is</th><th>Sources</th></tr></thead>
    <tbody>
__ROWS__
    </tbody>
  </table></div>
  <div class="card">__PNG_CRM__</div>
  <p class="cap">NASA CRM against its published 21-station table. Chords match exactly; with four stations the twist is off by at most 0.51°.</p>
</section>

<section id="commands">
  <h2>Commands</h2>
<pre>cd CFD_Automation/geometry
python -m cfdauto.geometry.sample                                    # write the sets
python -m cfdauto.geometry.build --type bwb --set training --index 7  # one wing
python -m cfdauto.geometry.build --all                               # every training, corner, reference wing (pyGeo)
python -m cfdauto.geometry.published_wings --build all               # M6, RIBES, CRM, BlendedNet (pyGeo)
python scripts/verify_geometry.py                                    # is the surface the intended wing?
python -m pytest -m "not pygeo"                                      # tests without pyGeo
python scripts/make_generator_visuals.py                             # the GIFs and pictures
python scripts/make_generator_page.py                                # this page</pre>
</section>

<footer>Generated by <code>CFD_Automation/geometry/scripts/make_generator_page.py</code> from <code>configs/wing.yaml</code>, the set manifests and <code>docs/verification.json</code>. Decision notes: <code>geometry/decisions/</code>.</footer>
</div>
"""


def main() -> None:
    m = manifests()
    g = glance(m)
    fixes = "\n".join(
        f"<li class='fixrow'><strong>{t}</strong>{e.replace('__VERSION__', __version__)} <span class='do'>Do: {d}</span></li>"
        for t, e, d in FIXES)
    page = (PAGE.replace("__GIF_BUILD__", img("how_a_wing_is_built.gif", "Seven-step animation of one wing being built"))
                .replace("__GIF_REF__", img("published_wings.gif", "Animation of the published wings rebuilt by the generator"))
                .replace("__PNG_TOP__", img("published_wings_topviews.png", "Top views of all published wings"))
                .replace("__PNG_CRM__", img("crm_check.png", "CRM chord and twist against the published table"))
                .replace("__FIXES__", fixes)
                .replace("__DECISIONS__", decisions_html())
                .replace("__BASIS__", basis_counts())
                .replace("__VARS__", variables_table())
                .replace("__SETS__", sets_table(m))
                .replace("__VERIFY__", verification_table())
                .replace("__OPEN__", "\n".join(f"<li><strong>{t}.</strong> {q}</li>" for t, q in OPEN))
                .replace("__LIMITS__", "\n".join(f"<li>{x}</li>" for x in LIMITS))
                .replace("__ROWS__", rows())
                .replace("__OK__", str(g["ok"])).replace("__BUILT__", str(g["built"]))
                .replace("__SETVER__", f"code {g['versions']}")
                .replace("__PUBOK__", str(g["pub_ok"])).replace("__PUB__", str(g["pub"]))
                .replace("__TESTS__", TESTS_LINE)
                .replace("__STALE__", (f"they were built with code {g['versions']}, before the pyGeo trailing edge (run <code>build --all</code>)."
                                       if g["stale"] else "no, they match the current code."))
                .replace("__VERSION__", __version__)
                .replace("__N_AIRFOILS__", f"{len(airfoils.available()):,}"))
    out = DOCS / "GEOMETRY_GENERATOR.html"
    out.write_text(page)
    print(f"{out}  {out.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
