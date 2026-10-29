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
from cfdauto.geometry.params import VARIABLES, WING_TYPES, load_config  # noqa: E402
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
        ("One generator, one YAML", "<code>wing_type: bwb | conventional | tapered | mixed</code>; <code>mixed</code> draws the types with stated shares (now 0.5 / 0.25 / 0.25).",
         "One design space and one contract. Two generators would mean two of each. The shares are our choice.", "req", ""),
        ("Three wing types", "<code>bwb</code> (tailless); <code>conventional</code> (cranked: chord and sweep may change at b1, b2); <code>tapered</code> (straight edges root to tip, rectangular at taper 1).",
         "Drawn freely, a straight taper has zero chance: 100 of 100 conventional wings came out cranked. Tapered wings are the most common real wings. Decided 29 Oct 2026.", "req", ""),
        ("Same 18 variables for every type", "Each type has its own range block in <code>configs/wing.yaml</code>.",
         "One vector shape for sampling, hashing and ML.", "own", ""),
        ("Everything varies", "A value is fixed only through <code>pinned:</code>.", "A study may pin; the default never does.", "req", ""),
        ("Chord law", "<code>stations</code>: c2, c3, c4 as fractions of the root (BWB). <code>per_panel</code>: each panel's own taper, at most 1 (cranked). <code>linear_taper</code>: one taper, c2 and c3 follow (tapered).",
         "Before, 46 of 100 conventional wings got wider toward the tip. With per-panel ratios no chord grows outboard, and the Latin hypercube stays intact.", "req", ""),
        ("Sweep law", "<code>panels</code>: one sweep per panel. <code>one</code>: sweep2 = sweep3 = sweep1 (tapered).",
         "Straight leading edge for tapered wings. Variables a law computes need no range.", "req", ""),
        ("Span mode", "<code>semi_span</code> (metres) or <code>root_chord_fractions</code> (semi-span read in root chords).",
         "BlendedNet gives spans in root chords. Conventional uses it so the aspect ratio stays 4–16.5.", "own", "open"),
        ("Size ranges from real wings", "BWB root chord 0.40–0.80 m, semi-span 0.75–2.2 root chords. Conventional and tapered root chord 0.13–0.75 m, semi-span 2–7.5 root chords.",
         "Every real wing with a published area but one (26: makers, papers, theses; Class II from Götten et al. 2021 and Essari 2015) has a generated wing within 10 % in span and mean chord (not the Aquila, a swept moderately tapered flying wing); every span-only wing with a tail is inside the span range (see <a href='#real'>Real wings</a>). Spans in root chords keep the aspect ratio real (BWB 2.7–10.2; real flying wings 2.9–8.6). Decided 29 Oct 2026.", "meas", ""),
        ("Shape ranges", "BWB chord ratios and sweeps from AERIS; dihedral 0–3° now allowed at b0, b1. Conventional and tapered: sweep −10° to +20°, dihedral −3° to +6°, taper down to 0.28 (cranked) or 0.40 (tapered).",
         "No source for these yet.", "own", "open"),
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
         "One bad point would put a bump in the surface. Kept by your decision on 29 Oct 2026; each dropped point is logged.", "req", ""),
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
         "kSpan 3 cut the corners at panel breaks by up to 4.8 % of chord; kSpan 2 is exact. It leaves a sharp kink at b1 and b2: see fix 3.", "meas", "fix"),
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
         "Content, never file names. Weak: the code version is a string set by hand: see fix 2.", "own", "fix"),
    ]),
    ("Sets", [
        ("Five sets per type", "Training 100 (Latin hypercube, seeds 1001/1002/1003); corner 1: each free variable at each bound (36, or 28 for tapered); corner 2: every pair at all four low/high combinations (8 or 7); reference 5 (by rule); hold-out 10 (seeds 2001/2002/2003).",
         "Training fills the inside, corners test the edges, the hold-out is the one honest test.", "req", ""),
        ("Failures stay in the list", "A refused wing keeps its row with the gate and the reason. Corners are never nudged inside.",
         "A failure marks the edge of the space.", "req", ""),
        ("Hold-out is never built here", "Only the vectors are saved.", "It is opened once, after the workflow is frozen.", "req", ""),
        ("Reference wings spread well", "Coverage distance BWB 1.49, conventional 1.50, tapered 1.37, against a median of 1.84 / 1.84 / 1.65 for 1,000 random sets of five (lower is better).",
         "Five wings must stand for the whole set.", "meas", ""),
    ]),
]

FIXES = [
    ("One dihedral variable does nothing.",
     "Four station dihedrals become three panel angles. [0, 3, 3, 6], [3, 0, 6, 3] and [1.5, 1.5, 4.5, 4.5] give the same wing to 0.003°. "
     "The gate compares with the derived angle, so it passes anyway.",
     "Use three panel dihedrals."),
    ("The hash ignores code changes.",
     "It uses <code>__version__</code>, a string bumped by hand. Code changes between bumps leave the hash the same.",
     "Hash the source files (or the git commit)."),
    ("The loft has sharp kinks at b1, b2 and the switch sections.",
     "Correct for straight panels, but the S8 mesher does not place stations at the breaks. Flat mesh faces would then cut the corner, about 0.5 % of chord (a rough estimate).",
     "Stage 2 must put a mesh station exactly at every <code>station_v</code>. No change here; put it in the Stage 2 prompt."),
]

OPEN = [
    ("Tailless Class II", "Fury (5.2 m), Albatroz (7 m) and Shahed 191 (7.3 m) have no published wing area and stay outside the BWB span range. Find areas, or leave tailless Class II out of scope?"),
    ("Aspect ratio of wings with a tail", "Generated AR reaches 21 (99 % below 20); real wings with a known area reach 16.5. Cap it (a gate, or a narrower span ratio), or accept?"),
    ("NTNU UAV database", "93 UAVs with span, AR and estimated chord (DataverseNO, CC0). Blocked from the cloud workspace: attach 02_Database.csv to add it."),
    ("Swept flying wings", "The Lockheed Aquila (3.76 m, mean chord 0.78 m, taper 0.58, sweep 28°) fits no type: bwb always tapers strongly, tapered sweeps at most 20°. Add a swept flying-wing option, or leave it out?"),
    ("Essari 2015 data", "Hermes 450, Ranger, Seeker, Shadow 600 areas come from a PhD thesis citing unread (Jane's-style) references; its Hermes 450 is internally inconsistent (0.69 m × 10.51 m = 7.25 m², listed 6.90). Confirm with Jane's before the paper."),
    ("Re levels", "Now 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶. Move the middle to about 9.5 × 10⁵ (log-middle)? Mini Class I wings fly at 1.2–2 × 10⁵, below the lowest level."),
    ("Label for slim tailless wings", "14 % of the bwb-type wings are slim flying wings without a centre body; the rule labels them \"conventional\", which reads like \"has a tail\". Rename to \"flying wing\"?"),
    ("Mixed shares", "BWB 0.5, cranked 0.25, tapered 0.25. Keep?"),
    ("Shape ranges", "Sweeps, twists, dihedrals and tapers have no source yet. Take them from real wings too?"),
    ("Trailing-edge floor", "Confirm 0.5 mm / 1.0 mm with the builder. Run the 0.1 / 0.2 / 0.3 % sensitivity once CFD works."),
    ("Airfoil search order", "Project folder → AERIS database → NACA formula. Keep? 22 database files are refused."),
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
    "<strong>Tailless Class II not covered.</strong> Flying wings stop at 3.5 m span. Fury, Albatroz and Shahed 191 (5–7.3 m) have no published area. Wings with a tail cover Class I and II up to 11 m.",
    "<strong>Shape ranges have no source.</strong> Sweeps, twists, dihedrals, tapers and airfoils are AERIS values or our choice; only sizes come from real aircraft.",
    "<strong>Swept, moderately tapered flying wings.</strong> The Aquila (taper 0.58, sweep 28°) fits no type.",
    "<strong>Slender wings with a tail.</strong> Generated aspect ratio reaches 21; real wings with a known area reach 16.5.",
    "<strong>Class II areas are uncertain.</strong> They rest on Götten et al. (from photos, about 10–15 %) and a thesis citing unread Jane's-style data.",
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
    specs = [cfg.types[t] for t in WING_TYPES]
    out = []
    for v in VARIABLES:
        def cell(spec):
            if v in spec.pinned:
                return f"{spec.pinned[v]:g} (pinned)"
            if v in spec.derived:
                return "from taper" if v.startswith("c") else "= sweep1"
            note = ""
            if spec.chord_law == "per_panel" and v in ("c2_ratio", "c3_ratio", "c4_ratio"):
                note = "<span class='muted'> of inboard</span>"
            elif spec.chord_law == "linear_taper" and v == "c4_ratio":
                note = "<span class='muted'> taper</span>"
            return fmt(*spec.ranges[v]) + note
        out.append(f"<tr><td><code>{v}</code></td><td>{html.escape(MEANING[v])}</td>"
                   + "".join(f"<td class='num'>{cell(sp)}</td>" for sp in specs) + "</tr>")
    laws = ("<tr><td><code>chord_law</code><br><code>sweep_law</code></td><td>how chords and sweeps are read</td>"
            + "".join(f"<td>{sp.chord_law}<br>{sp.sweep_law}</td>" for sp in specs) + "</tr>")
    air = ("<tr><td><code>airfoils</code></td><td>section at b0, b1, b2, b3</td>"
           + "".join(f"<td>{', '.join('/'.join(x) for x in sp.choices)}</td>" for sp in specs) + "</tr>")
    return "\n".join(out) + "\n" + laws + "\n" + air


def manifests() -> list[dict]:
    rows = []
    for t in WING_TYPES:
        for s in ("training", "corner1", "corner2", "reference", "holdout"):
            f = SETS / t / f"{s}_manifest.json"
            if f.is_file():
                d = json.loads(f.read_text())
                rows.append({"type": t, "set": s, "version": d.get("code_version", "?"), "wings": d["wings"]})
    return rows


TYPE_NAME = {"bwb": "BWB", "conventional": "Cranked", "tapered": "Tapered"}
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
        out.append(f"<tr><td><span class='tag {r['type']}'>{TYPE_NAME[r['type']]}</span></td>"
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


def real_table() -> tuple[str, dict]:
    """Rows of the real-UAV table and its summary, from docs/real_uavs.json."""
    d = json.loads((DOCS / "real_uavs.json").read_text())
    fam = {"tailless": "Tailless", "tailed": "With tail", "delta": "Delta + tail"}
    use = {"ranges": "<span class='flag ok'>sets range</span>", "span": "<span class='muted'>span only</span>",
           "none": "<span class='flag open'>not used</span>"}
    out = []
    for r in sorted(d["rows"], key=lambda r: (r["family"], r["span"])):
        num = lambda x, f: "—" if x in (None, "") else f.format(x)  # noqa: E731
        re_ = (f"{r['re_low']:.1e} – {r['re_high']:.1e}".replace("e+0", "e") if r.get("re_low") and r.get("re_high") else "—")
        out.append(
            f"<tr><td class='what'>{html.escape(r['name'])}</td><td>{fam[r['family']]}</td><td>{r['class']}</td>"
            f"<td class='num'>{num(r['span'], '{:.2f}')}</td><td class='num'>{num(r['area'], '{:.3g}')}</td>"
            f"<td class='num'>{num(r.get('mean_chord'), '{:.3f}')}</td><td class='num'>{num(r.get('aspect_ratio'), '{:.1f}')}</td>"
            f"<td class='num'>{num(r['cruise'], '{:.1f}')} / {num(r['max'], '{:.1f}')}</td><td class='num'>{re_}</td>"
            f"<td class='num'>{num(r.get('mtow'), '{:g}')}</td><td class='num'>{hcdi_cell(r.get('hcdi'))}</td>"
            f"<td>{use[r['use']]}{'<br><span class=muted>' + html.escape(r['note']) + '</span>' if r.get('note') else ''}</td>"
            f"<td class='src'><a href='{html.escape(r['source'])}'>{STYPE.get(r.get('stype'), 'source')}</a></td></tr>")
    return "\n".join(out), d["summary"]


STYPE = {"manufacturer": "maker", "paper": "paper", "thesis_report": "thesis / report", "government": "government",
         "secondary": "secondary", "model": "model", "measured_drawing": "drawing", "hcdi_db": "HCDI db"}


def stype_counts(rows: list[dict]) -> str:
    """How many range-setting wings rest on each kind of source."""
    c = Counter(r.get("stype") for r in rows if r["use"] == "ranges")
    return ", ".join(f"{STYPE.get(k, k)} {v}" for k, v in c.most_common())


def cover_text() -> str:
    rows = [r for r in json.loads((DOCS / "real_uavs.json").read_text())["rows"] if r["use"] == "ranges"]
    miss = [r["name"] for r in rows if not r.get("covered")]
    return f"{len(rows) - len(miss)} of {len(rows)} real wings" + (f" (not: {', '.join(miss)})" if miss else "")


def hcdi_cell(h: dict | None) -> str:
    """Class, MTOW, payload and span of the same aircraft in the HCDI UAS database."""
    if not h:
        return "—"
    parts = [f"Class {h['class']}"]
    parts += [f"{k} {h[k]:g}{u}" for k, u in (("mtow", " kg"), ("payload", " kg pl"), ("span", " m")) if h.get(k)]
    return "<br>".join(parts)


def hcdi_table(d: dict) -> str:
    fam = {"tailless": "Tailless", "tailed": "With tail"}
    out = []
    for r in sorted(d["hcdi_db"], key=lambda r: (r["family"], r["span"])):
        inside = ("<span class='flag ok'>inside</span>" if r.get("span_covered")
                  else "<span class='flag fix'>outside</span>" if r["use"] == "span" else "<span class='flag open'>not used</span>")
        g = lambda k, u="": "—" if r.get(k) in (None, "") else f"{r[k]:g}{u}"  # noqa: E731
        out.append(f"<tr><td class='what'>{html.escape(r['model'])}</td><td>{fam[r['family']]}</td><td>{r['class']}</td>"
                   f"<td class='num'>{g('span')}</td><td class='num'>{g('mtow')}</td><td class='num'>{g('payload')}</td>"
                   f"<td>{html.escape(r.get('role') or '—')}</td><td>{inside}</td>"
                   f"<td class='muted'>{html.escape(r.get('check') or '')}</td></tr>")
    return "\n".join(out)


PHENOMENA = [
    ("Laminar flow, transition and laminar separation bubbles",
     "Every type. Mean-chord Re 4 × 10⁴ – 3.4 × 10⁶; most BWB and mini Class I wings sit below 10⁶. Our sections (NLF1015, MH91, E374) are designed for long laminar runs.",
     "Drag and lift depend on where the boundary layer turns turbulent. A bubble adds drag; at high angle it can burst, giving abrupt stall and hysteresis. Small changes in turbulence or roughness move the result.",
     "No. Spalart–Allmaras without transition makes the wall flow turbulent from the nose, so drag is biased. Carried as a model band (Stage 0); SU2 γ-Reθ is the planned check.",
     "Carmichael 1981 (NASA CR-165803); Lissaman 1983 (Annu. Rev. Fluid Mech. 15); Mueller & DeLaurier 2003 (Annu. Rev. Fluid Mech. 35)"),
    ("Very low Re at the tips",
     "BWB tip chords 3.5–16 cm: tip Re down to 2 × 10⁴. Tapered and cranked tips down to 2–3 × 10⁴ on the smallest wings.",
     "Thick laminar boundary layers and early separation at the tip, where the vortex forms.",
     "Weakly. Same model limit as above, at its worst. The first-cell law must use the local chord, not the mean chord.",
     "Same as above; first-cell law: Grand Roadmap R-V.1"),
    ("Tip vortex, induced drag and wake roll-up",
     "Every wing; strongest at low aspect ratio (BWB down to 2.7) and high lift.",
     "Induced drag is a large share of the total; the wake and vortex move the pressure at the trailing edge and tip.",
     "Yes, if the wake has its own cells. The O-mesh had no designed wake: overset wake box and vortex tube planned (primer, section 05).",
     "Primer section 05; refining the near wake moved base drag by 23 counts"),
    ("Sweep: spanwise flow, tip or root stall, pitch-up",
     "BWB 5–40° (aft); cranked and tapered −10° to +20° (forward to aft).",
     "Aft sweep pushes the boundary layer outboard, so the tip stalls first and the nose can pitch up. Forward sweep stalls the root first.",
     "Spanwise flow: yes. Stall onset and pitch-up: less reliable with steady RANS near maximum lift.",
     "Standard swept-wing aerodynamics"),
    ("Panel breaks (kinks) at b1 and b2",
     "Every BWB and cranked wing; tapered wings have no break in the edges.",
     "Local suction peaks and a jump in the span loading at the break; a ruled loft has a slope break there.",
     "Yes, if a mesh station sits exactly on each break (fix 3). Otherwise flat faces cut the corner.",
     "Loft decision (kSpan 2)"),
    ("Separation and stall at high angle",
     "The 12° study angle, and 8° on thin or strongly cambered sections at low Re.",
     "Trailing-edge or leading-edge separation, unsteady flow, maximum lift.",
     "Steady RANS gives a number but is not reliable near maximum lift; convergence is harder. Keep 12° for the nose and wake studies only.",
     "Stage 0 angles 0 / 4 / 8 / 12°"),
    ("Blunt trailing edge: base flow",
     "Every wing: thickness max(0.5 mm, 0.2 % of chord) (Class I).",
     "A base pressure drag and, in reality, vortex shedding behind the base.",
     "Partly. Steady RANS damps the shedding. At 0.2 % with 8 cells the base was 2–4 % of pressure drag (measured in AERIS).",
     "Primer section 03; Papadakis & Manolesos 2020 (flatback, RANS damps shedding)"),
    ("Low Mach number",
     "Top speed 67 m/s: Mach ≤ 0.20 (BWB ≤ 0.12).",
     "The air is nearly incompressible.",
     "The compressible solver needs low-speed preconditioning; without it ADflow did not converge in AERIS.",
     "Primer track 3"),
    ("Slender, flexible wings",
     "Cranked and tapered aspect ratio up to 21.",
     "Long thin wings bend and twist in flight, which changes the span loading.",
     "No. The CFD wing is rigid. Many span stations are needed.",
     "Outside this study (no aeroelasticity)"),
]


def final_ranges_html() -> dict:
    cfg = load_config()
    d = json.loads((DOCS / "real_uavs.json").read_text())["summary"]
    env, rey = d["envelope"], d["reynolds"]
    specs = {t: cfg.types[t] for t in WING_TYPES}
    def rng(sp, v, f="{:g}"):
        lo, hi = sp.ranges[v]
        m = lambda x: f.format(x).replace("-", "−")  # noqa: E731
        return f"{m(lo)} to {m(hi)}" if min(lo, hi) < 0 else f"{m(lo)}–{m(hi)}"

    size = "".join(
        f"<tr><td class='what'>{TYPE_NAME[t]}</td><td class='num'>{rng(sp, 'root_chord_m')} m</td>"
        f"<td class='num'>{rng(sp, 'semi_span_m')} {'root chords' if sp.span_mode == 'root_chord_fractions' else 'm'}</td></tr>"
        for t, sp in specs.items())

    def chords(sp):
        if sp.chord_law == "linear_taper":
            return f"one taper {rng(sp, 'c4_ratio')}"
        if sp.chord_law == "per_panel":
            return f"per panel {rng(sp, 'c2_ratio')}, {rng(sp, 'c3_ratio')}, {rng(sp, 'c4_ratio')} of the chord inboard"
        return f"b1 {rng(sp, 'c2_ratio')}, b2 {rng(sp, 'c3_ratio')}, tip {rng(sp, 'c4_ratio')} of the root"

    def sweeps(sp):
        if sp.sweep_law == "one":
            return f"one sweep {rng(sp, 'sweep1_deg')}°"
        return " / ".join(rng(sp, f"sweep{i}_deg") for i in (1, 2, 3)) + "°"

    shape_rows = [
        ("Chords", chords),
        ("Panel spans", lambda sp: f"outer {rng(sp, 'b3_ratio')}, split {rng(sp, 'split_ratio')}"),
        ("LE sweep", sweeps),
        ("Twist b0 / b1 / b2 / b3", lambda sp: " / ".join(rng(sp, f"twist{i}_deg") for i in range(4)) + "°"),
        ("Dihedral b0 / b1 / b2 / b3", lambda sp: " / ".join(rng(sp, f"dihedral{i}_deg") for i in range(4)) + "°"),
        ("Airfoils b0–b3", lambda sp: ", ".join("/".join(c) for c in sp.choices)),
    ]
    shape = "".join(f"<tr><td class='what'>{n}</td>" + "".join(f"<td>{f(sp)}</td>" for sp in specs.values()) + "</tr>"
                    for n, f in shape_rows)

    def mm(a, f="{:.2f}"):
        return f"{f.format(a[0])}–{f.format(a[1])}"
    gen_rows = [("Span", "span_m", " m", "{:.1f}"), ("Mean chord", "mean_chord_m", " m", "{:.2f}"),
                ("Wing area", "area_m2", " m²", "{:.2f}"), ("Aspect ratio", "aspect_ratio", "", "{:.1f}"),
                ("Overall taper", "taper", "", "{:.2f}"), ("Tip chord", "tip_chord_m", " m", "{:.3f}")]
    gen = "".join(f"<tr><td class='what'>{n}</td>" + "".join(f"<td class='num'>{mm(env[t][k], f)}{u}</td>" for t in WING_TYPES) + "</tr>"
                  for n, k, u, f in gen_rows)

    sci = lambda x: f"{x:.1e}".replace("e+0", " × 10^").replace("^4", "⁴").replace("^5", "⁵").replace("^6", "⁶")  # noqa: E731
    re_rows = "".join(
        f"<tr><td class='what'>{TYPE_NAME[t]}</td><td class='num'>{r['speed_m_s'][0]:g}–{r['speed_m_s'][1]:g} m/s</td>"
        f"<td class='num'>{sci(r['mean_chord'][0])} – {sci(r['mean_chord'][1])}</td>"
        f"<td class='num'>{sci(r['tip'][0])} – {sci(r['tip'][1])}</td><td class='num'>{sci(r['root_max'])}</td>"
        f"<td class='num'>{r['mach_max']:.2f}</td></tr>" for t, r in rey.items())

    phen = "".join(f"<tr><td class='what'>{a}</td><td>{b}</td><td>{c}</td><td>{e}</td><td class='src'>{f}</td></tr>"
                   for a, b, c, e, f in PHENOMENA)
    return {"__SIZE__": size, "__SHAPE__": shape, "__GEN__": gen, "__RE_TYPES__": re_rows, "__PHEN__": phen,
            "__REAL_RE__": f"{sci(d['re_low_min'])} – {sci(d['re_high_max'])}"}


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
.tag.conventional, .tag.tapered { color: var(--accent); } .tag.bwb { color: var(--bwb); }
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
  <p class="lede">Eighteen numbers go in; one exact wing surface comes out, measured, labelled and checked. One generator and one YAML file make BWB, cranked and tapered wings, sized like real Class I and II UAVs. Every later stage (mesh, solver, data) reads only this surface.</p>
  <nav aria-label="On this page"><a href="#glance">At a glance</a><a href="#ranges">Final ranges</a><a href="#reynolds">Reynolds range</a><a href="#phenomena">Flow phenomena</a><a href="#fix">Fix before Stage 2</a><a href="#decisions">Design decisions</a><a href="#real">Real wings and Re</a><a href="#variables">The 18 numbers</a><a href="#checks">Checks and results</a><a href="#open">Open decisions</a><a href="#limits">What it cannot make</a><a href="#published">Published wings</a><a href="#commands">Commands</a></nav>
</header>

<section id="glance">
  <h2>At a glance</h2>
  <div class="three">
    <div class="box"><h3>In</h3><div class="big">18 numbers + a wing type</div><p>From <code>configs/wing.yaml</code>: chords, spans, sweeps, twists, dihedrals, and an airfoil per station. Types: BWB, conventional (cranked), tapered.</p></div>
    <div class="box"><h3>Out</h3><div class="big">One surface, checked</div><p>Upper, lower and trailing-edge base, read as <code>upper(u, v)</code>. Plus measured values, labels, four refusing checks, a hash, IGES.</p></div>
    <div class="box"><h3>Evidence</h3><div class="big">__OK__ of __BUILT__ wings pass</div><p>Sampled wings, both types, 0 refused (built with __SETVER__). __PUBOK__ of __PUB__ published wings verified. Tests: __TESTS__.</p></div>
    <div class="box verdict"><h3>Verdict</h3><div class="big">Ready for Stage 2 after three fixes</div><p>Not yet "any wing": straight panels only, no airfoil shape variable. Sets must be rebuilt: __STALE__</p></div>
  </div>
</section>

<section id="ranges">
  <h2>Final ranges</h2>
  <p>Size from real Class I–II UAVs (see <a href="#real">Real wings</a>); shape from AERIS or our own choice (no source yet). Every variable per type: <a href="#variables">The 18 numbers</a>.</p>
  <div class="three">
    <div class="tbl"><table>
      <thead><tr><th>Size</th><th>Root chord</th><th>Semi-span</th></tr></thead>
      <tbody>__SIZE__</tbody>
    </table></div>
  </div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Shape</th><th>BWB</th><th>Cranked</th><th>Tapered</th></tr></thead>
    <tbody>__SHAPE__</tbody>
  </table></div>
  <h2 style="font-size:22px">What the generator makes</h2>
  <p class="muted">2,000 Latin-hypercube wings per type.</p>
  <div class="tbl"><table class="mid">
    <thead><tr><th></th><th>BWB</th><th>Cranked</th><th>Tapered</th></tr></thead>
    <tbody>__GEN__</tbody>
  </table></div>
</section>

<section id="reynolds">
  <h2>Reynolds number range</h2>
  <div class="three">
    <div class="box"><h3>Study levels (Stage 0)</h3><div class="big">3 × 10⁵ · 1.5 × 10⁶ · 3 × 10⁶</div><p>On the mean chord. Every mesh study runs at these three.</p></div>
    <div class="box"><h3>Real wings fly at</h3><div class="big">__REAL_RE__</div><p>Mean chord, cruise at 3,048 m to top speed at sea level, for the real wings with a published area.</p></div>
    <div class="box"><h3>Below the lowest level</h3><div class="big">Tips and mini wings</div><p>Tips reach 2 × 10⁴ and mini Class I wings 1.2–2 × 10⁵: under 3 × 10⁵, where transition matters most.</p></div>
  </div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Speeds (real wings of the family)</th><th>Re, mean chord</th><th>Re, tip</th><th>Re, root max</th><th>Mach max</th></tr></thead>
    <tbody>__RE_TYPES__</tbody>
  </table></div>
  <p class="muted">Range a type can reach: smallest chord at the lowest cruise speed and 3,048 m, to largest chord at the highest top speed and sea level. Air from Stage 0 (ISA, Sutherland). A single wing spans a much narrower band. The largest generated wings at the top speed reach about 3.4 × 10⁶, a little above the top study level; the smallest at the lowest speed fall to 4 × 10⁴.</p>
</section>

<section id="phenomena">
  <h2>Flow phenomena you will meet</h2>
  <p>What the flow does on these wings, at these Re and angles, and whether the planned CFD (ADflow, steady RANS, Spalart–Allmaras, fully turbulent) can see it.</p>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Phenomenon</th><th>Where in our ranges</th><th>What it does</th><th>Does our CFD capture it?</th><th>Source</th></tr></thead>
    <tbody>__PHEN__</tbody>
  </table></div>
  <div class="weak"><strong>The biggest one.</strong> Most of these wings fly where transition and laminar bubbles set the drag, and the planned model cannot see them. Mesh error can be made small; this model error cannot. Every drag number needs its model band, and differences between wings are safer than absolute drag.</div>
</section>

<section id="fix" class="weak">
  <h2>Fix before Stage 2</h2>
  <p class="muted">Each fix changes the hashes, so do all three before one rebuild. Done on 29 Oct 2026: the unrealistic conventional set (tapered type and per-panel chords).</p>
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

<section id="real">
  <h2>Real wings and the Reynolds number</h2>
  <p>Your rule (29 Oct 2026): take the sizes from real Class I and II UAVs, compute the Re they fly at, and if it does not reach 5 × 10⁶, lower the top Re level instead of stretching the wings. Data and links: <code>configs/real_uavs.yaml</code>; check: <code>scripts/real_uav_check.py</code>.</p>
  <div class="three">
    <div class="box"><h3>Real wings fly at</h3><div class="big">Re __RE_LO__ – __RE_HI__</div><p>Lowest: Black Swift S0 cruising at 3,048 m. Highest: RUAG Ranger at top speed, sea level. Mean chord = wing area / span.</p></div>
    <div class="box verdict"><h3>So the top Re level</h3><div class="big">5 × 10⁶ → 3 × 10⁶</div><p>No wing of our families reaches 5 × 10⁶. Only the Sperwer (a delta) and the Vindicator (a target drone above Mach 0.3) do. Levels now 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶ (the highest real value, 2.74 × 10⁶ for the RUAG Ranger at top speed, rounded up).</p></div>
    <div class="box"><h3>Generator covers them</h3><div class="big">__COVER__</div><p>Each real wing with a published area has a generated wing within 10 % in span and mean chord. Every Class I span is inside too (sourced and HCDI database). BWB __ENV_BWB__; conventional __ENV_CONV__.</p></div>
    <div class="box"><h3>Class II</h3><div class="big">Chords 0.55–0.66 m</div><p>Nine Class II wings with an area: Götten et al. 2021 (from images and three-views, about 10–15 %) and Essari 2015 (Jane's-style: Hermes 450, Ranger, Seeker, Shadow 600). AR 7.8–16. At top speed, Re 2.1–2.7 × 10⁶. Gap: tailless Class II has no area.</p></div>
  </div>
  <div class="card">__PNG_REAL__</div>
  <p class="cap">Clouds: 2,000 generated wings per type (green BWB, blue conventional and tapered). Red: real wings with a published area. Dotted lines: real wings with a published span only.</p>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Aircraft</th><th>Family</th><th>Class</th><th>Span m</th><th>Area m²</th><th>Mean chord m</th><th>AR</th><th>Cruise / max m/s</th><th>Re low – high</th><th>MTOW kg</th><th>HCDI database</th><th>Use</th><th>Source (type)</th></tr></thead>
    <tbody>
__REAL__
    </tbody>
  </table></div>
  <p class="muted">Re low = cruise at 3,048 m; Re high = top speed (cruise if none) at sea level; air from Stage 0. Family from a text source or, where none says it, from photos (marked K in the YAML). Only wings with a published area set the ranges; they rest on: __STYPES__. HCDI database column: the same aircraft in your UAS dashboard, where listed.</p>
  <h2 style="font-size:22px">Spans from the HCDI UAS database (v13)</h2>
  <p>794 entries; 76 fixed-wing Class I–II; 18 give a span; <strong>none gives a wing area</strong>, so these rows test the span range only. Four Class I flying wings (3.1–3.5 m) were longer than the old BWB range; the BWB span now reaches 3.5 m. Every wing with a tail is inside; tailless Class II wings (5–7.3 m) stay outside until their areas are found.</p>
  <div class="weak amber"><strong>Database weak points.</strong> No source per row. 28 rows share cruise 35 m/s, endurance 6 h and range 100 km (look like defaults); on 8 rows cruise is above top speed. Orlan-10 is listed as Class II at 18 kg, Puma LE as a flying wing, XQ-58 Valkyrie (a jet) as Class II; Zala Z-16's maker field names a microchip company. Only span, class, MTOW and payload are used here.</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Aircraft</th><th>Family</th><th>Class</th><th>Span m</th><th>MTOW kg</th><th>Payload kg</th><th>Role</th><th>Span vs generator</th><th>Check</th></tr></thead>
    <tbody>
__HCDI__
    </tbody>
  </table></div>
</section>

<section id="variables">
  <h2>The 18 numbers</h2>
  <p>Four stations: root b0, breaks b1 and b2, tip b3. Three straight panels between them. Ranges as in <code>configs/wing.yaml</code> now.</p>
  <div class="tbl"><table class="mid">
    <thead><tr><th>Variable</th><th>Meaning</th><th>BWB</th><th>Conventional, cranked</th><th>Conventional, tapered</th></tr></thead>
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
    real_rows, real = real_table()
    env = real["envelope"]
    fr = final_ranges_html()
    page = PAGE
    for k, v in fr.items():
        page = page.replace(k, v)
    page = (page.replace("__REAL__", real_rows)
                .replace("__STYPES__", stype_counts(json.loads((DOCS / "real_uavs.json").read_text())["rows"]))
                .replace("__HCDI__", hcdi_table(json.loads((DOCS / "real_uavs.json").read_text())))
                .replace("__PNG_REAL__", img("real_uavs.png", "Real wings against generated wings: span and mean chord"))
                .replace("__RE_LO__", f"{real['re_low_min']:.1e}".replace("e+0", " × 10^").replace(" × 10^5", " × 10⁵"))
                .replace("__RE_HI__", f"{real['re_high_max']:.1e}".replace("e+0", " × 10^").replace(" × 10^6", " × 10⁶"))
                .replace("__COVER__", cover_text())
                .replace("__ENV_BWB__", f"span {env['bwb']['span_m'][0]:.1f}–{env['bwb']['span_m'][1]:.1f} m, mean chord {env['bwb']['mean_chord_m'][0]:.2f}–{env['bwb']['mean_chord_m'][1]:.2f} m")
                .replace("__ENV_CONV__", f"span {env['conventional']['span_m'][0]:.1f}–{env['conventional']['span_m'][1]:.1f} m, mean chord {env['conventional']['mean_chord_m'][0]:.2f}–{env['conventional']['mean_chord_m'][1]:.2f} m")
                .replace("__GIF_BUILD__", img("how_a_wing_is_built.gif", "Seven-step animation of one wing being built"))
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
