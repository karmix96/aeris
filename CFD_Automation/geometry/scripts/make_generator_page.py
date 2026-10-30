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
from cfdauto.geometry.planform import aspect_ratio, build_planform, mean_aero_chord  # noqa: E402
from cfdauto.geometry.sample import lhs  # noqa: E402
from cfdauto.geometry.sections import build_wing_sections  # noqa: E402

DOCS = ROOT / "docs"
SETS = ROOT / "data" / "sets"
TESTS_LINE = "140 pass without pyGeo, 11 more need pyGeo (run 30 Oct 2026)"

# --------------------------------------------------------------------------------------
# Content written by hand. Keep it short and plain.
# basis: req = your requirement, src = published source or tool, meas = measured here,
#        own = our choice, no source yet.   flag: "fix" (fix before Stage 2), "open" (needs a decision)
# --------------------------------------------------------------------------------------

MEANING = {
    "root_chord_m": "root chord (m) — sampled",
    "aspect_ratio": "aspect ratio span² / area — sampled",
    "semi_span_m": "semi-span (m) — derived: AR · c_root · K / 2",
    "c2_ratio": "chord at b1 (BWB: / root; cranked: / chord at b0)",
    "c3_ratio": "chord at b2 (BWB: / root; cranked: / chord at b1)",
    "c4_ratio": "tip chord (BWB: / root; cranked: / chord at b2; tapered, flying wing: taper)",
    "b3_ratio": "outer panel span / semi-span",
    "split_ratio": "inner panel / (inner + middle)",
    "sweep1_deg": "LE sweep, panel 1 (+ aft); the one sweep of tapered and flying wings",
    "sweep2_deg": "LE sweep, panel 2",
    "sweep3_deg": "LE sweep, panel 3",
    "twist0_deg": "twist at b0 (+ nose up)",
    "twist1_deg": "twist at b1",
    "twist2_deg": "twist at b2",
    "twist3_deg": "twist at b3 (tip)",
    "dihedral_p1_deg": "dihedral of panel 1, b0–b1 (+ tip up)",
    "dihedral_p2_deg": "dihedral of panel 2, b1–b2",
    "dihedral_p3_deg": "dihedral of panel 3, b2–b3",
}

DECISIONS = [
    ("Inputs", [
        ("One generator, one YAML", "<code>wing_type: bwb | conventional | tapered | flying_wing | mixed</code>; <code>mixed</code> draws the types with stated shares, now equal (1/4 each).",
         "One design space and one contract. Equal shares keep a mixed set from leaning to one type (decided 29 Oct 2026).", "req", ""),
        ("Four wing types", "<code>bwb</code> (tailless, big root chord, strong taper, cranked); <code>conventional</code> (cranked, with a tail); <code>tapered</code> (with a tail, straight edges, rectangular at taper 1); <code>flying_wing</code> (tailless, straight edges, moderate taper, swept).",
         "Drawn freely, a straight taper had zero chance (100 of 100 wings cranked). The Aquila (taper 0.58, sweep 28°) fitted no type, and plain swept flying wings are the most common small tailless UAVs. Decided 29 Oct 2026.", "req", ""),
        ("Same 18 variables for every type", "Each type samples some and derives the rest (see <a href='#inputs'>Inputs and derived</a>).",
         "One vector shape for sampling, hashing and ML.", "own", ""),
        ("Everything varies", "A value is fixed only through <code>pinned:</code>.", "A study may pin; the default never does.", "req", ""),
        ("Size inputs: root chord and aspect ratio", "<code>span_mode: aspect_ratio</code> for every type. The semi-span follows: S = AR · c_root · K / 2, K = mean chord / root chord.",
         "Drawing the span on its own let wings with a tail reach AR 21 (13 % above 16.5, the highest real value). Drawing AR keeps every wing inside the real range by construction, with no refusals. Decided 29 Oct 2026.", "req", ""),
        ("Chord law", "<code>stations</code>: c2, c3, c4 as fractions of the root (BWB). <code>per_panel</code>: each panel's own taper, at most 1 (cranked). <code>linear_taper</code>: one taper, c2 and c3 follow (tapered, flying wing).",
         "Before, 46 of 100 conventional wings got wider toward the tip. With per-panel ratios no chord grows outboard, and the Latin hypercube stays intact.", "req", ""),
        ("Sweep law", "<code>panels</code>: one sweep per panel. <code>one</code>: sweep2 = sweep3 = sweep1 (tapered, flying wing).",
         "Straight leading edge for straight-edged wings. Variables a law computes need no range.", "req", ""),
        ("Size ranges from real wings", "Root chord: BWB 0.40–1.80 m; cranked and tapered 0.13–0.75 m; flying wing 0.25–1.05 m. AR: tailless 3–9; with a tail 4.5–16.5.",
         "All 27 real wings with a published area (makers, papers, theses; Class II from Götten et al. 2021, Essari 2015 and the AUTh RX-3 BWB) have a generated wing within 10 % in span and mean chord, and all 62 real spans are inside (see <a href='#real'>Real wings</a>). BWB root raised from 0.80 to 1.80 m on 30 Oct 2026: the old range was sized on small flying wings and missed real BWBs (RX-3: 4.9 m², 260 kg; Wang &amp; Zhou: root 1.80 m).", "meas", ""),
        ("Cranked differs from tapered", "Cranked focus = constant-chord centre and tapered outer panels: inner chord 0.95–1, middle 0.80–1, outer 0.50–0.85 of the chord inboard; sweep −3–3° inner, −5–10° middle, 0–15° outer. Full space unchanged.",
         "Your remark (30 Oct 2026): the two types looked alike, because the old per-panel ratios (0.85/0.75/0.65–1) made mostly straight-tapered wings with faint breaks. The layout follows Class II UAVs like Hermes 450 and Heron (from photos; no published chord table), so it is our choice.", "own", ""),
        ("Shape ranges from sources", "Every range has its basis in the <a href='#inputs'>Why this range</a> column and in <code>decisions/shape_ranges.md</code>. Changed on 29 Oct 2026: tailed sweep −5° to +15° (was −10° to +20°); tailed washout at most 5° (was 7°); dihedral 0–5° for every type (Raymer); flying-wing taper 0.3–0.9 and sweep 10–40°; BWB tip down to 0.06, first sweep from 15°.",
         "Each range now rests on a design rule (Raymer) or on a published small UAV (BWB: Wang &amp; Zhou 2022, Suewatanakul 2022, Lehmkuehler 2012, Hainline 2017; flying wing: Milenković-Babić 2024, Panknin, PUL-10, a flying-wing MAV). Layout shares (b3, split) remain our choice. BlendedNet is a larger Group 3 BWB and is not used for the ranges.", "src", ""),
        ("Two spaces: full and focus", "Per type, <code>ranges</code> + <code>airfoils</code> = the focus space (realistic, suggested); <code>full_ranges</code> + <code>full_airfoils</code> = the full space (everything supported). The focus box must lie inside the full box, and each suggested section must be a full candidate; the YAML is refused otherwise.",
         "Your rule (30 Oct 2026): design everything, but put the wings and the simulations densely where the real wings are. Full bounds are our choice: the widest value in any source, rounded out (e.g. BlendedNet sweeps 60°, Wang &amp; Zhou root 1.8 m, Prandtl-D washout 10°).", "req", ""),
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
        ("Vertical sections; root in y = 0", "Every section is parallel to the symmetry plane and only twisted about its leading edge. The validity gate refuses a wing whose root leaves y = 0 by more than 1e-9 m, or any point that crosses y = 0.",
         "The two mirrored halves then meet exactly in the root section and never cross. AERIS (and its AVL path) rolled the root section with the first panel's dihedral, so the halves crossed and the root dihedral had to be pinned at zero. pyGeo only receives our section points, never a dihedral angle. Cost: on a panel with dihedral Γ the true thickness is cos Γ smaller (1.5 % at 10°).", "req", ""),
        ("One dihedral per panel", "Inputs <code>dihedral_p1, p2, p3</code>. Station heights: z<sub>i</sub> = Σ tan(Γ<sub>panel</sub>) · panel span.",
         "Four station values gave only three panel slopes, so one input did nothing ([0, 3, 3, 6], [3, 0, 6, 3] and [1.5, 1.5, 4.5, 4.5] built the same wing). The gate now checks each panel dihedral against the vector. Fixed 29 Oct 2026.", "req", ""),
        ("Twist", "Exact at the four stations; between them it follows the straight panel.",
         "Straight panels and linear twist cannot both hold. Difference 0.1–0.3 % of chord at the trailing edge.", "meas", ""),
        ("Aspect ratio exact with twist", "The mean chord K counts the true chord of a straight panel: where the twist changes, the chord turns and is a little shorter mid-panel (0.6 % for a 13° change). K = Σ f<sub>i</sub> ∫ |chord vector| dt, 32-point Gauss.",
         "Found by the full-space sets: with washout up to 12°, 4 wings missed their aspect ratio by 0.11–0.24 % (gate limit 0.1 %). Two causes: K assumed a linear chord, and the extra section at the trailing-edge switch took the linear chord and twist, so it sat off the straight panel. Both fixed 30 Oct 2026: the switch section now sits on the ruled panel (true chord and its twist). Worst aspect-ratio error on 730 built wings: 0.00004 %.", "meas", ""),
    ]),
    ("Airfoils", [
        ("Supported vs suggested sections", "Supported: any section in the database (2,159 files), in <code>geometry/airfoils/</code>, or a NACA 4/5-digit formula. Suggested: the per-type list from papers (focus space). The full space draws from every sourced section, on any type.",
         "Your rule (30 Oct 2026). A suggestion must have a source; support needs only a readable file.", "req", ""),
        ("Any airfoil by name", "Search order: <code>geometry/airfoils/</code> → AERIS database (2,159 of 2,181 files load) → NACA 4/5-digit formula. A station may list candidates; the sampler draws them evenly. One wing may carry its own four names.",
         "BlendedNet (NACA 25118), M6, RIBES and CRM need sections outside the default list.", "own", "open"),
        ("Default sections", "BWB: MH 104 body (15 %), MH 61 wing (10 %). Cranked and tapered: NACA 4415, 4415, 4412, 4412. Flying wing: MH 60 inboard, MH 45 outboard.",
         "BWB pair from a small BWB UAV (Suewatanakul et al. 2022). The old AERIS MH 91 is a paraglider section and NLF(1)-1015 a HALE section (Re 0.7–2 × 10⁶), so both were dropped. NACA 4415 flies on the Pioneer and the Shadow 200 (Lednicer). MH 45 and MH 60 are Hepperle's tailless sections; MH 60 suits Re ≥ 1.5 × 10⁵ (root), MH 45 lower Re (tip). Changed 29 Oct 2026.", "src", ""),
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
         "kSpan 3 cut the corners at panel breaks by up to 4.8 % of chord; kSpan 2 is exact. It leaves a sharp kink at b1 and b2: see the one fix left.", "meas", "fix"),
        ("Built with pySpline, one parameter s = √(x/c)", "Same construction as pyGeo's <code>liftingSurface</code>, held in a pyGeo object.",
         "<code>liftingSurface</code> split upper and lower 0.2–0.5 % of chord away from the nose. Here the split is exact and u = x/c on every station.", "meas", ""),
        ("Ask, never interpolate", "The mesher asks <code>upper(u, v)</code> and <code>lower(u, v)</code>; a 401-point table maps v to span.",
         "In AERIS, straight lines between stored sections missed the surface by up to 7.25 % of chord (ADR-0015).", "meas", ""),
        ("Tip", "Flat and open (<code>tip='none'</code>).", "Rounded tips are a later study.", "own", ""),
        ("Two backends, one export", "pyGeo (production, IGES) and numpy (same surface, no pyGeo). No STEP: pyGeo has no STEP writer.",
         "Tests and pictures run anywhere.", "own", ""),
    ]),
    ("Measure, label, hash", [
        ("Measured on the loft", "Chord, twist, LE position, sweep, dihedral, area, span, MAC, AR, thickness, trailing-edge thickness → <code>measured.json</code>. The gate checks chords, sweeps, twists, panel dihedrals and the aspect ratio against the vector.",
         "Later stages and any ML model use the measured wing; the vector is only its label.", "req", ""),
        ("Labels by rule", "Configuration: <code>bwb</code> (measured centre body), else <code>flying_wing</code> for a tailless type or <code>conventional</code> for a type with a tail. Then swept, cranked, rectangular, washout, dihedral, aspect ratio. BWB threshold 2.2.",
         "A tail is not part of the wing surface, so it cannot be measured; the family comes from the type. Before 29 Oct 2026 every tailless wing without a centre body was called 'conventional'. Checked on 20 hand-labelled wings and a flying-wing test.", "req", ""),
        ("Hash from the code itself", "sha256 of the vector (with its four section names), the type's laws and pinned values (not its ranges), the trailing-edge rule, the airfoil coordinates and the content of every geometry source file.",
         "Any code change now changes every input hash, so stored meshes and results are never reused for a wing the code builds differently. A version string set by hand could be forgotten. Fixed 29 Oct 2026.", "req", ""),
    ]),
    ("Sets", [
        ("Seven sets per type, two spaces", "Focus: training 100 (Latin hypercube, seeds 1001–1004), reference 5 (by rule), hold-out 10 (seeds 2001–2004). Full: training 40 (seeds 1101–1104), hold-out 5 (seeds 2101–2104), corner 1 (each free variable at each full bound: 34 or 26 wings) and corner 2 (every pair at all four low/high combinations: 8 or 7).",
         "Dense where real wings are, sparse over everything we support; the corners test the edges of what we claim. The hold-outs are the honest tests. Decided 30 Oct 2026.", "req", ""),
        ("Failures stay in the list", "A refused wing keeps its row with the gate and the reason. Corners are never nudged inside.",
         "A failure marks the edge of the space.", "req", ""),
        ("Hold-out is never built here", "Only the vectors are saved.", "It is opened once, after the workflow is frozen.", "req", ""),
        ("Reference wings spread well", "Coverage distance BWB 1.51, cranked 1.45, tapered 1.31, flying wing 1.35, against a median of 1.82 / 1.79 / 1.62 / 1.59 for 1,000 random sets of five (lower is better).",
         "Five wings must stand for the whole set.", "meas", ""),
    ]),
]

FIXES = [
    ("The loft has sharp kinks at b1, b2 and the switch sections.",
     "Correct for straight panels, but the S8 mesher does not place stations at the breaks. Flat mesh faces would then cut the corner, about 0.5 % of chord (a rough estimate).",
     "Stage 2 must put a mesh station exactly at every <code>station_v</code>. No change here; put it in the Stage 2 prompt."),
]

OPEN = [  # (group, title, text, kind)  kind: decide = needs your call; act = a task, no choice left
    ("Study plan (Stage 0)", "Middle Re level", "Levels are now 1 × 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶. Keep 1.5 × 10⁶, or move it to 1 × 10⁶ (log-middle of 3 × 10⁵ and 3 × 10⁶)?", "decide"),
    ("Study plan (Stage 0)", "Transition check", "ADflow has no transition model (SA is its only differentiated, tested model). In 2-D, tripped vs free transition changes profile drag by +37–128 % (median 76 %) at Re ≥ 3 × 10⁵ (XFOIL, <a href='#phenomena'>Flow phenomena</a>): tens of counts, far above the 3-count mesh budget. Run SU2 γ-Reθ on a few reference wings at 1 × 10⁵ and 3 × 10⁵ on a y+ ≤ 1 mesh? Needs a transition-ready mesh option.", "decide"),
    ("Study plan (Stage 0)", "Grid share 65 %", "Of the 3-count drag budget, 65 % goes to the mesh. Keep?", "decide"),
    ("Study plan (Stage 0)", "Iterative error", "≤ 10 % of the budget is loose; Eça &amp; Hoekstra ask 0.1–1 %. Tighten to 1 %?", "decide"),
    ("Study plan (Stage 0)", "Pitching-moment tolerance 0.002", "Our choice, no source. Keep?", "decide"),
    ("Study plan (Stage 0)", "Turbulence-model source", "Crivellini 2014 is weak support. Find a better source or call it our choice.", "decide"),
    ("Study plan (Stage 0)", "Stage 0 D5", "The Grand Roadmap lists a D5 (prior work, transition route, tunnel, cloud budget). Add it?", "decide"),
    ("Geometry", "Full-space edges", "The full space reaches 20 m span (beyond Class II) and Re 7.6 × 10⁶ on the largest BWB root (above the top level). Keep, or cap the span?", "decide"),
    ("Geometry", "BWB focus top size", "With root up to 1.80 m and AR up to 9 the focus BWB reaches 10.3 m span and 11.8 m²; the largest real BWB (RX-3) has 6–7 m and 4.9 m². Lower the top root chord or AR?", "decide"),
    ("Geometry", "Trailing-edge floor", "Confirm 0.5 mm (Class I) / 1.0 mm (Class II) with a builder; run the 0.1 / 0.2 / 0.3 % sensitivity once CFD works.", "decide"),
    ("Geometry", "Airfoil search order", "Project folder → AERIS database → NACA formula; 22 database files are refused. Keep?", "decide"),
    ("Geometry", "pyGeo run", "Run the 11 pyGeo tests and <code>build --all</code> on your machine; manifests must then say pygeo.", "act"),
    ("Sources", "Second-hand values", "Raymer's taper 0.4, washout 3° and 0° c/4 sweep come from a course page; PUL-10 and the flying-wing MAV were read by the agent only. Check in print.", "act"),
    ("Sources", "AUTh BWB papers", "Airfoils and station chords of their BWBs are in paywalled papers (AST 2018, AST 2021, AIAA 2020/2022, ICUAS 2020). Patras library or the authors.", "act"),
    ("Sources", "Essari 2015 data", "Hermes 450, Ranger, Seeker, Shadow 600 areas cite unread Jane's-style data; the Hermes 450 entry is inconsistent. Confirm with Jane's.", "act"),
    ("Sources", "NTNU UAV database", "93 UAVs (span, AR, chord), blocked from the cloud: attach 02_Database.csv.", "act"),
    ("Sources", "Tailless Class II areas", "Fury, Albatroz, Shahed 191 have spans only; the RX-3 is the one tailless Class II with an area.", "act"),
    ("Published wings", "BlendedNet twist and dihedral", "Set to zero because neither paper states them. Accept?", "decide"),
    ("Published wings", "Which published wing first", "RIBES is the only in-regime case; M6 and CRM are transonic.", "decide"),
    ("Published wings", "NASA CRM", "Four stations and stand-in sections: a shape check only, or add a many-station mode?", "decide"),
    ("Published wings", "RIBES trailing edge", "Fitted section 0.26 %, model 0.38–0.66 %. Rebuild before any drag comparison?", "decide"),
    ("Published wings", "Outside proof", "Only the M6 is checked against its own CAD. BlendedNet, CRM, RIBES need their surface files; NACA 25118 edge needs a BlendedNet STEP.", "act"),
    ("Paper", "Closest prior work", "Pliakos et al. 2025 (AUTh) automate OpenVSP → ANSA → Fluent for UAV wings (2 panels, M6 only, no transition). State what we add: 4 stations / 3 panels, full and focus spaces, refusing gates, Re bands with a transition check, open tools.", "decide"),
]

LIMITS = [
    "<strong>Straight edges only, three panels at most.</strong> No curved BWB centre body, no elliptic planform, no fourth panel.",
    "<strong>Airfoil shape is not a variable.</strong> Any named file can be used, and a station can draw from a list, but thickness and camber are not sampled continuously. The default sets use one section per station (t/c 10–15 %).",
    "<strong>No winglets, rounded or raked tips, fuselage, gaps.</strong> Panel dihedral: focus 0–5°, full ±10°.",
    "<strong>Some shape sources are thin.</strong> The layout shares (where b1 and b2 sit) are our choice. A few rules are second-hand (Raymer via a course page). BWB shapes rest on four small-UAV papers, two of them larger than Class I.",
    "<strong>Class II areas are uncertain.</strong> They rest on Götten et al. (from photos, about 10–15 %) and a thesis citing unread Jane's-style data. Tailless Class II have no area at all.",
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
                return {"c2_ratio": "from taper", "c3_ratio": "from taper", "sweep2_deg": "= sweep1",
                        "sweep3_deg": "= sweep1", "semi_span_m": "from AR", "aspect_ratio": "from span"}[v]
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
        for s in ("training", "training_full", "corner1", "corner2", "reference", "holdout", "holdout_full"):
            f = SETS / t / f"{s}_manifest.json"
            if f.is_file():
                d = json.loads(f.read_text())
                rows.append({"type": t, "set": s, "version": d.get("code_version", "?"), "code_hash": d.get("code_hash"),
                             "backend": d.get("loft_backend", "?"), "wings": d["wings"]})
    return rows


TYPE_NAME = {"bwb": "BWB", "conventional": "Cranked", "tapered": "Tapered", "flying_wing": "Flying wing"}
SET_NAME = {"training": "training (focus)", "training_full": "training (full)", "corner1": "corner 1 (full)",
            "corner2": "corner 2 (full)", "reference": "reference (focus)", "holdout": "hold-out (focus)",
            "holdout_full": "hold-out (full)"}


def sets_table(rows: list[dict]) -> str:
    out = []
    for r in rows:
        w = r["wings"]
        n = len(w)
        if r["set"].startswith("holdout"):
            res, labels = "vectors only, not built", "—"
        else:
            ok = sum(1 for x in w if x.get("passed"))
            bad = Counter(x.get("gate") for x in w if x.get("passed") is False)
            res = f"{ok} built, {n - ok} refused" + (f" ({', '.join(f'{k} {v}' for k, v in bad.items())})" if bad else "")
            lab = Counter(l for x in w for l in (x.get("labels") or []) if l not in ("bwb", "conventional"))
            labels = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in lab.most_common(5))
        stale = ("" if r["set"].startswith("holdout") else
                 f" <span class='flag open'>{r['backend']} loft</span>" if r["backend"] != "pygeo" else "")
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
     "Every type. Mean-chord Re 4 × 10⁴ – 3.4 × 10⁶; most BWB and mini Class I wings sit below 10⁶. Our low-Re sections (MH 45, MH 60, MH 61, MH 104) are designed for long laminar runs.",
     "Drag and lift depend on where the boundary layer turns turbulent. A bubble adds drag; at high angle it can burst, giving abrupt stall and hysteresis. Small changes in turbulence or roughness move the result.",
     "No. Spalart–Allmaras without transition makes the wall flow turbulent from the nose. In 2-D (XFOIL) that raises profile drag by 37–128 % (median 76 %) at Re ≥ 3 × 10⁵. Carried as a model band (Stage 0); SU2 γ-Reθ is the proposed check.",
     "Carmichael 1981 (NASA CR-165803); Lissaman 1983 (Annu. Rev. Fluid Mech. 15); Mueller & DeLaurier 2003 (Annu. Rev. Fluid Mech. 35); our XFOIL runs (Drela 1989)"),
    ("Very low Re at the tips",
     "BWB tip chords 3.5–16 cm: tip Re down to 2 × 10⁴. Tapered and cranked tips down to 2–3 × 10⁴ on the smallest wings.",
     "Thick laminar boundary layers and early separation at the tip, where the vortex forms.",
     "Weakly. Same model limit as above, at its worst. The first-cell law must use the local chord, not the mean chord.",
     "Same as above; first-cell law: Grand Roadmap R-V.1"),
    ("Wake behind the trailing edge",
     "Every wing, the whole span. At 12° the wake leaves the edge at an angle; behind a blunt base it starts wide.",
     "A thin sheet of slow air: the boundary layers of both surfaces leave the edge and carry the profile drag downstream. It sets the pressure at the trailing edge and base, and it rolls up toward the tips.",
     "Only if the wake has its own cells. The S8 O-mesh has none: its cells grow fast behind the edge, so the wake smears. In AERIS, refining the near wake alone moved base drag by 23 counts. Plan: an overset wake box.",
     "Primer section 05; Chan et al. 2002"),
    ("Tip vortex, roll-up and induced drag",
     "Every wing; strongest at low aspect ratio (BWB down to 2.7) and high lift.",
     "The wake sheet rolls up into one vortex per tip within about one chord. It causes the downwash and the induced drag, a large share of the total.",
     "Yes, if the vortex keeps fine cells along its path. Plan: the roll-up inside the near-body mesh, then a vortex tube from about 2 chords behind the tip.",
     "Primer section 05"),
    ("Sweep: spanwise flow, tip or root stall, pitch-up",
     "BWB 5–40° and flying wing 10–40° (aft); cranked and tapered −5° to +15° (forward to aft).",
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
     "Cranked and tapered aspect ratio up to 16.5.",
     "Long thin wings bend and twist in flight, which changes the span loading.",
     "No. The CFD wing is rigid. Many span stations are needed.",
     "Outside this study (no aeroelasticity)"),
]


SUMMARY_TEXT = {
    "what": {"bwb": "Tailless; long centre body, strong taper, cranked", "conventional": "With a tail; constant-chord centre, tapered outer panels",
             "tapered": "With a tail; straight edges root to tip (rectangular at taper 1)", "flying_wing": "Tailless; straight edges, moderate taper, swept"},
    "flow": {"bwb": "Two regimes on one wing (centre body ~10× the tip Re); spanwise flow and tip stall from sweep; kinks at b1, b2; thick 15 % centre body",
             "conventional": "Kinks at the breaks (suction peaks, loading jump); low sweep; small wings fly almost wholly below 10⁵",
             "tapered": "Smooth loading; low sweep; tips at lower Re as taper grows; strong tip vortex at high AR",
             "flying_wing": "Trim by sweep and washout with reflexed sections; spanwise flow; tip stalls first at high angle"},
    "mesh": {"bwb": "LE and TE everywhere; a station on each kink; tip; wake and tip vortex; fine first cell at the centre-body Re",
             "conventional": "LE and TE; a station on each break; tip vortex; wake",
             "tapered": "LE and TE; tip vortex; wake",
             "flying_wing": "LE and TE; tip (stall, vortex); wake behind a swept TE"},
}


def summary_html() -> str:
    """One table: final ranges and flows per type (focus bold, full grey)."""
    cfg = load_config()
    ext = json.loads((DOCS / "size_extremes.json").read_text())
    f = lambda x: f"{x:g}".replace("-", "−")  # noqa: E731

    def r(lo, hi, unit=""):
        return (f"{f(lo)} to {f(hi)}" if min(lo, hi) < 0 else f"{f(lo)}–{f(hi)}") + unit

    def both(fn):
        return [f"<strong>{fn(cfg.types[t], 'focus')}</strong><br><span class='fullr'>full {fn(cfg.full[t], 'full')}</span>"
                for t in WING_TYPES]

    def taper(sp, space):
        pts = [build_planform(sp, v) for v in lhs(sp, 400, 5)]
        tp = [q.chord[-1] / q.chord[0] for q in pts]
        return r(round(min(tp), 2), round(max(tp), 2))

    def sweeps(sp, space):
        if sp.sweep_law == "one":
            return r(*sp.ranges["sweep1_deg"], "°")
        return " / ".join(r(*sp.ranges[f"sweep{i}_deg"]) for i in (1, 2, 3)) + "°"

    def washout(sp, space):
        a0, b0 = sp.ranges["twist0_deg"]; a3, b3 = sp.ranges["twist3_deg"]
        return r(a0 - b3, b0 - a3, "°")

    def dih(sp, space):
        rr = [sp.ranges[f"dihedral_p{i}_deg"] for i in (1, 2, 3)]
        return (r(*rr[0], "°") if len(set(rr)) == 1 else " / ".join(r(*x) for x in rr) + "°")

    def span(sp, space):
        e = ext[f"{sp.name}/{space}"]
        return f"{e['span_m'][0]:.2f}–{e['span_m'][1]:.1f} m"

    def re_mc(sp, space):
        e = ext[f"{sp.name}/{space}"]
        return f"{sci(e['re_mean_chord'][0])} – {sci(e['re_mean_chord'][1])}"

    rows = [
        ("Shape", [SUMMARY_TEXT["what"][t] for t in WING_TYPES]),
        ("Span", both(span)),
        ("Root chord", both(lambda sp, s_: r(*sp.ranges["root_chord_m"], " m"))),
        ("Aspect ratio", both(lambda sp, s_: r(*sp.ranges["aspect_ratio"]))),
        ("Overall taper (tip / root)", both(taper)),
        ("LE sweep (per panel)", both(sweeps)),
        ("Washout (root − tip)", both(washout)),
        ("Dihedral (per panel)", both(dih)),
        ("Suggested sections b0–b3", [", ".join(cfg.types[t].airfoils) for t in WING_TYPES]),
        ("Speed · Mach", [f"{ext[t + '/focus']['speed_m_s'][0]:g}–{ext[t + '/focus']['speed_m_s'][1]:g} m/s · "
                          f"{ext[t + '/focus']['mach'][0]:.2f}–{ext[t + '/focus']['mach'][1]:.2f}" for t in WING_TYPES]),
        ("Re on the mean chord", both(re_mc)),
        ("Re, smallest tip · largest root (focus)", [f"{sci(ext[t + '/focus']['re_tip_min'])} · {sci(ext[t + '/focus']['re_root_max'])}" for t in WING_TYPES]),
        ("Main flow features", [SUMMARY_TEXT["flow"][t] for t in WING_TYPES]),
        ("Mesh must resolve", [SUMMARY_TEXT["mesh"][t] for t in WING_TYPES]),
    ]
    head = "".join(f"<th><span class='tag {t}'>{TYPE_NAME[t]}</span></th>" for t in WING_TYPES)
    body = "".join(f"<tr><td class='what'>{a}</td>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>" for a, cells in rows)
    return f"<thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody>"


def xfoil_note() -> str:
    f = DOCS / "xfoil_band.json"
    if not f.is_file():
        return "Run scripts/xfoil_band.py."
    d = json.loads(f.read_text())
    runs, re_of = d["runs"], {f"{r:.0e}": r for r in d["re"]}   # keys were written with one digit
    by_re = {}
    for k, v in runs.items():
        name, re_, mode = k.split("|")
        if mode != "free":
            continue
        t = runs[f"{name}|{re_}|trip"]["polar"]
        for al in ("0", "2", "4"):
            if al in v["polar"] and al in t:
                by_re.setdefault(re_of[re_], []).append(100 * (t[al]["cd"] / v["polar"][al]["cd"] - 1))
    parts = [f"{sci(r)}: {min(x):+.0f} to {max(x):+.0f} %" for r, x in sorted(by_re.items())]
    hi = [y for r, x in by_re.items() if r >= 2.9e5 for y in x]
    import statistics
    return ("Profile drag, tripped against free transition, at 0–4° for the four suggested sections — "
            + "; ".join(parts) + f". From 3 × 10⁵ up, turbulent-from-the-nose raises 2-D profile drag by {min(hi):.0f}–{max(hi):.0f} % "
            f"(median {statistics.median(hi):.0f} %): 30–60 drag counts, ten times the 3-count mesh budget. So the model band, "
            "not the mesh, sets the error on absolute drag. At 10⁵ the two stay close, because the free flow separates in a long bubble "
            "and is draggy too. Left: drag increase; right: where the free upper surface turns turbulent.")


def sci(x: float) -> str:
    e = int(f"{x:.1e}".split("e")[1]); m = x / 10 ** e
    sup = str(e).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))
    return f"{m:.1f} × 10{sup}"


def extremes_html() -> dict:
    f = DOCS / "size_extremes.json"
    if not f.is_file():
        return {"__EXTREMES__": "<tr><td colspan='7'>Run scripts/size_extremes.py</td></tr>", "__RE_MACH__": ""}
    d = json.loads(f.read_text())
    ex, rm = [], []
    for k, r in d.items():
        t, sp = r["type"], r["space"]
        s_, l_ = r["smallest"], r["largest"]
        tag = f"<span class='tag {t}'>{TYPE_NAME[t]}</span>"
        sp_txt = "<strong>focus</strong>" if sp == "focus" else "<span class='muted'>full</span>"
        ex.append(f"<tr><td>{tag}</td><td>{sp_txt}</td><td class='num'>{s_['span_m']:.2f} – {l_['span_m']:.1f} m</td>"
                  f"<td class='num'>{s_['area_m2']:.3f} – {l_['area_m2']:.1f} m²</td>"
                  f"<td class='num'>{s_['mean_chord_m']:.2f} – {l_['mean_chord_m']:.2f} m</td>"
                  f"<td class='num'>{s_['root_chord_m']:.2f} – {l_['root_chord_m']:.2f} m</td>"
                  f"<td class='num'>{s_['tip_chord_m']:.3f} – {l_['tip_chord_m']:.2f} m</td></tr>")
        lo, hi = r["re_mean_chord"]
        out = []
        if lo < 3e5:
            out.append(f"below 3 × 10⁵ down to {sci(lo)}")
        if hi > 3e6:
            out.append(f"above 3 × 10⁶ up to {sci(hi)}")
        rm.append(f"<tr><td>{tag}</td><td>{sp_txt}</td><td class='num'>{r['speed_m_s'][0]:g}–{r['speed_m_s'][1]:g} m/s</td>"
                  f"<td class='num'>{r['mach'][0]:.3f}–{r['mach'][1]:.2f}</td><td class='num'>{sci(lo)} – {sci(hi)}</td>"
                  f"<td class='num'>{sci(r['re_tip_min'])}</td><td class='num'>{sci(r['re_root_max'])}</td></tr>")
    return {"__EXTREMES__": "\n".join(ex), "__RE_MACH__": "\n".join(rm)}


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
        f"<td class='num'>{rng(sp, 'aspect_ratio')}</td><td class='num'>{env[t]['span_m'][0]:.1f}–{env[t]['span_m'][1]:.1f} m</td></tr>"
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
        ("Dihedral panel 1 / 2 / 3", lambda sp: " / ".join(rng(sp, f"dihedral_p{i}_deg") for i in (1, 2, 3)) + "°"),
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


# --------------------------------------------------------------------------------------
# Figures for the flow-phenomena section (inline SVG, theme-aware through CSS classes)
# --------------------------------------------------------------------------------------

def _x_re(re_: float, x0: float = 170, px_per_decade: float = 230) -> float:
    import math
    return x0 + (math.log10(re_) - 4.0) * px_per_decade


def fig_re_map() -> str:
    """Where each wing type flies on the Reynolds axis, against the regimes and the study levels."""
    d = json.loads((DOCS / "real_uavs.json").read_text())
    rey = d["summary"]["reynolds"]
    W, H = 900, 390
    X = _x_re
    out = [f'<svg class="dg" viewBox="0 0 {W} {H}" role="img" aria-label="Reynolds number map: mean-chord and tip Reynolds ranges of the four wing types and of the real wings with speeds, against the low-Re regime below 5 times 10 to the 5 and the four study levels">']
    # regimes
    out.append(f'<rect class="zone-low" x="{X(1e4):.1f}" y="34" width="{X(5e5) - X(1e4):.1f}" height="256"/>')
    out.append(f'<rect class="zone-mid" x="{X(5e5):.1f}" y="34" width="{X(1e7) - X(5e5):.1f}" height="256"/>')
    out.append(f'<text class="lab amber" x="{(X(1e4) + X(5e5)) / 2:.1f}" y="26" text-anchor="middle">low-Re regime: laminar bubbles, early transition</text>')
    out.append(f'<text class="lab acc" x="{(X(5e5) + X(1e7)) / 2:.1f}" y="26" text-anchor="middle">transition position still sets the drag</text>')
    # rows
    n_real = sum(1 for r in d["rows"] if r["use"] == "ranges" and r.get("re_low") and r.get("re_high"))
    rows = [(f"Real wings ({n_real})", 70), ("BWB", 125), ("Cranked", 170), ("Tapered", 215), ("Flying wing", 260)]
    for name, y in rows:
        out.append(f'<text class="lab" x="160" y="{y + 4}" text-anchor="end">{name}</text>')
    # real wings: one thin line each, spread over the band
    used = [r for r in d["rows"] if r["use"] == "ranges" and r.get("re_low") and r.get("re_high")]
    for k, r in enumerate(sorted(used, key=lambda r: r["re_low"])):
        y = 52 + 36 * k / max(len(used) - 1, 1)
        out.append(f'<line class="real" x1="{X(r["re_low"]):.1f}" y1="{y:.1f}" x2="{X(r["re_high"]):.1f}" y2="{y:.1f}"/>')
    # types: mean chord (thick) and tip (thin, below)
    for (name, y), t in zip(rows[1:], ("bwb", "conventional", "tapered", "flying_wing")):
        m, tip = rey[t]["mean_chord"], rey[t]["tip"]
        cls = {"bwb": "bwb", "flying_wing": "fw"}.get(t, "conv")
        out.append(f'<rect class="bar {cls}" x="{X(m[0]):.1f}" y="{y - 7}" width="{X(m[1]) - X(m[0]):.1f}" height="14" rx="2"/>')
        out.append(f'<rect class="bar {cls} tipbar" x="{X(tip[0]):.1f}" y="{y + 11}" width="{X(tip[1]) - X(tip[0]):.1f}" height="5" rx="1"/>')
    # study levels
    for lv, txt in ((1e5, "1 × 10⁵"), (3e5, "3 × 10⁵"), (1.5e6, "1.5 × 10⁶"), (3e6, "3 × 10⁶")):
        out.append(f'<line class="level" x1="{X(lv):.1f}" y1="40" x2="{X(lv):.1f}" y2="290"/>')
        out.append(f'<text class="lab warn" x="{X(lv):.1f}" y="304" text-anchor="middle">{txt}</text>')
    out.append(f'<text class="lab warn" x="{X(3e5) - 8:.1f}" y="320" text-anchor="end">study levels</text>')
    # axis
    out.append(f'<line class="axis" x1="{X(1e4)}" y1="340" x2="{X(1e7)}" y2="340"/>')
    for e in range(4, 8):
        out.append(f'<line class="axis" x1="{X(10**e):.1f}" y1="336" x2="{X(10**e):.1f}" y2="346"/>')
        out.append(f'<text class="lab" x="{X(10**e):.1f}" y="361" text-anchor="middle">10{"⁴⁵⁶⁷"[e - 4]}</text>')
        if e < 7:
            for k in (2, 5):
                out.append(f'<line class="axis" x1="{X(k * 10**e):.1f}" y1="338" x2="{X(k * 10**e):.1f}" y2="342"/>')
    out.append(f'<text class="lab muted" x="{X(1e7)}" y="380" text-anchor="end">Reynolds number (log scale)</text>')
    out.append(f'<text class="lab muted" x="{X(1e4)}" y="380">thick bar: mean chord · thin bar: tip chord</text>')
    out.append("</svg>")
    return "\n".join(out)


def fig_planform() -> str:
    """Top view of a half wing (a cranked, aft-swept BWB-like planform) with where each phenomenon sits."""
    # stations: (y_px, x_le, chord); flow goes down the page
    st = [(90, 80, 220), (270, 160, 125), (430, 215, 75), (600, 262, 30)]
    le = " ".join(f"{y},{x}" for y, x, c in st)
    te = " ".join(f"{y},{x + c}" for y, x, c in reversed(st))
    o = ['<svg class="dg" viewBox="0 0 1000 470" role="img" aria-label="Top view of a half wing showing where each flow phenomenon sits: '
         'symmetry plane at the root, laminar region behind the leading edge, kinks at b1 and b2, outboard drift of the boundary layer, '
         'tip stall region, blunt trailing-edge base, wake rolling up into the tip vortex, and the smallest chord and Reynolds number at the tip">',
         '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" class="fillc"/></marker></defs>']
    # free stream
    o.append('<line class="stroke" x1="40" y1="40" x2="40" y2="110" marker-end="url(#ah)"/><text class="lab" x="50" y="70">V∞</text>')
    # symmetry plane
    o.append('<line class="dash" x1="90" y1="50" x2="90" y2="440"/><text class="lab muted" x="96" y="452">symmetry plane (root)</text>')
    # laminar region band behind LE (to ~35 % chord)
    lam = " ".join(f"{y},{x}" for y, x, c in st) + " " + " ".join(f"{y},{x + 0.35 * c:.1f}" for y, x, c in reversed(st))
    o.append(f'<polygon class="wing" points="{le} {te}"/>')
    o.append(f'<polygon class="laminar" points="{lam}"/>')
    o.append(f'<polygon class="outline" points="{le} {te}"/>')
    # tip stall region (outer panel, aft part)
    (y2, x2, c2), (y3, x3, c3) = st[2], st[3]
    o.append(f'<polygon class="stall" points="{y2 + 60},{x2 + 0.55 * c2 + 6:.1f} {y3},{x3 + 0.4 * c3:.1f} {y3},{x3 + c3} {y2 + 60},{x2 + c2 + 4:.1f}"/>')
    # blunt base along the TE
    o.append(f'<polyline class="base" points="{te}"/>')
    # kinks
    for y, x, c in st[1:3]:
        o.append(f'<circle class="kink" cx="{y}" cy="{x}" r="6"/>')
    # outboard drift arrows on the inner and middle panels
    for y0, x0 in ((170, 225), (230, 245), (330, 245)):
        o.append(f'<line class="drift" x1="{y0}" y1="{x0}" x2="{y0 + 55}" y2="{x0 + 14}" marker-end="url(#ah)"/>')
    # wake sheet rolling into the tip vortex
    for k, (y, x, c) in enumerate(st[:3]):
        o.append(f'<path class="wake" d="M{y},{x + c + 4} C{y + 40},{x + c + 70} {560 - 30 * k},{380 - 6 * k} 620,392"/>')
    o.append('<circle class="vortex" cx="628" cy="392" r="14"/><circle class="vortex" cx="628" cy="392" r="7"/>')
    # labels (right column, leader lines)
    labels = [
        (120, "kinks b1, b2: suction peak, loading jump", (276, 158)),
        (165, "laminar region behind the leading edge", (380, 212)),
        (210, "boundary layer drifts outboard (aft sweep)", (285, 259)),
        (255, "tip stalls first at high angle", (560, 282)),
        (300, "smallest chord: Re down to 2 × 10⁴", (602, 268)),
        (345, "blunt base: base drag, shedding", (470, 292)),
        (392, "wake rolls up into the tip vortex", (644, 392)),
    ]
    for ly, txt, (px, py) in labels:
        o.append(f'<line class="leader" x1="{px}" y1="{py}" x2="676" y2="{ly - 4}"/><text class="lab" x="682" y="{ly}">{txt}</text>')
    o.append('<text class="lab muted" x="300" y="458">schematic: cranked, aft-swept half wing; forward sweep stalls at the root instead</text>')
    o.append("</svg>")
    return "\n".join(o)


def _naca4(m=0.04, p=0.4, t=0.12, n=60):
    import math
    pts = []
    for i in range(n + 1):
        x = 0.5 * (1 - math.cos(math.pi * i / n))
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)
        yc = m / p**2 * (2 * p * x - x**2) if x < p else m / (1 - p)**2 * ((1 - 2 * p) + 2 * p * x - x**2)
        pts.append((x, yc + yt, yc - yt))
    return pts


def fig_section() -> str:
    """One section: the real boundary layer against what the planned CFD assumes."""
    pts = _naca4()
    C, X0 = 560, 150

    def panel(yc, cfd):
        up = [(X0 + C * x, yc - C * yu) for x, yu, yl in pts]
        lo = [(X0 + C * x, yc - C * yl) for x, yu, yl in pts]
        poly = " ".join(f"{a:.1f},{b:.1f}" for a, b in up + lo[::-1])
        s = [f'<polygon class="wing" points="{poly}"/>']
        seg = lambda a, b: " ".join(f"{x:.1f},{y - 4:.1f}" for x, y in up if a <= (x - X0) / C <= b)  # noqa: E731
        s.append(f'<circle class="fillc" cx="{X0 - 2}" cy="{yc - C * pts[0][1]:.1f}" r="3"/>')
        if cfd:
            s.append(f'<polyline class="turb" points="{seg(0.0, 1.0)}"/>')
            s.append(f'<text class="lab warn" x="{X0 + 0.02 * C:.1f}" y="{yc - 70}">turbulent from the nose: no laminar run, no bubble</text>')
        else:
            s.append(f'<polyline class="lam" points="{seg(0.0, 0.42)}"/>')
            bx0, bx1 = X0 + 0.42 * C, X0 + 0.55 * C
            by = min(y for x, y in up if bx0 <= x <= bx1) - 6
            s.append(f'<path class="bubble" d="M{bx0:.1f},{by + 8:.1f} Q{(bx0 + bx1) / 2:.1f},{by - 14:.1f} {bx1:.1f},{by + 10:.1f}"/>')
            s.append(f'<polyline class="turb" points="{seg(0.55, 1.0)}"/>')
            s.append(f'<text class="lab bwbc" x="{X0 + 0.05 * C:.1f}" y="{yc - 70}">laminar boundary layer</text>')
            s.append(f'<text class="lab amber" x="{bx0 - 10:.1f}" y="{by - 22:.1f}">separation bubble → transition</text>')
            s.append(f'<text class="lab acc" x="{X0 + 0.68 * C:.1f}" y="{yc - 52}">turbulent boundary layer</text>')
        # blunt base, shedding and wake
        te_u, te_l = up[-1], lo[-1]
        s.append(f'<line class="base" x1="{te_u[0]:.1f}" y1="{te_u[1]:.1f}" x2="{te_l[0]:.1f}" y2="{te_l[1]:.1f}"/>')
        if cfd:
            s.append(f'<line class="wake" x1="{te_u[0] + 4:.1f}" y1="{yc:.1f}" x2="{te_u[0] + 110:.1f}" y2="{yc + 4:.1f}"/>')
            s.append(f'<text class="lab" x="{te_u[0] + 12:.1f}" y="{yc + 26:.1f}">steady wake (shedding damped)</text>')
        else:
            for k in range(3):
                cx = te_u[0] + 18 + 30 * k
                s.append(f'<circle class="vortex" cx="{cx:.1f}" cy="{yc + (6 if k % 2 else -6):.1f}" r="{6 - k}"/>')
            s.append(f'<text class="lab" x="{te_u[0] + 12:.1f}" y="{yc + 30:.1f}">base flow, shedding</text>')
        return "\n".join(s)

    o = ['<svg class="dg" viewBox="0 0 1000 400" role="img" aria-label="One wing section. Real flow: laminar boundary layer from the nose, a laminar separation bubble where it turns turbulent, a turbulent boundary layer to the blunt trailing edge, and vortex shedding behind the base. Planned CFD: turbulent from the nose, no bubble, steady wake.">',
         '<text class="lab head" x="20" y="40">Real flow</text>', panel(130, False),
         '<line class="dash" x1="20" y1="205" x2="980" y2="205"/>',
         '<text class="lab head" x="20" y="250">Planned CFD</text><text class="lab muted" x="20" y="266">SA, no transition</text>', panel(330, True),
         '<text class="lab muted" x="150" y="392">schematic NACA 4412 section; the difference between the two panels is the model band on every drag number</text>',
         "</svg>"]
    return "\n".join(o)


# zone | phenomena it captures | rule (starting value) | budget share (Stage 0) | where the rule comes from | today in S8
REFINE = [
    ("Wall-normal, every wall", "Boundary layer, skin friction, separation; transition if a transition model is run",
     "First cell from y⁺ ≤ 1 at each station's own Re (local chord), so small tips get their own; growth ≤ 1.25 inside the boundary layer, ≤ 1.3 outside; ≥ 30 cells across the boundary layer",
     "wall-normal 20 %", "Roadmap R-V.1, R-V.2 (laws 13, 14); DPW gridding guidelines",
     "One first cell (4.71 µm) for every station; growth 1.253; 29 cells across the boundary layer"),
    ("Leading edge (nose)", "Suction peak, start of the laminar run, stall at 12°",
     "Chordwise spacing solved so no cell turns the surface by more than 10° (ladder 12 / 10 / 8 / 6°); nose cells of neighbouring stations differ by at most 15 %",
     "chordwise 35 %", "Roadmap R-S.5, R-S.6 (laws 1, 2)", "In place"),
    ("Upper surface, about 30–60 % chord", "Laminar separation bubble and transition",
     "Only with a transition model: fine chordwise cells over the bubble and a cap on growth along the ring (≤ 1.25). With fully turbulent SA there is no bubble to resolve",
     "chordwise 35 %", "Our choice; depends on the transition route (Stage 0 D5)", "Not done"),
    ("Trailing edge and blunt base", "Base drag, base flow, start of the wake",
     "Chordwise spacing 0.1 % of local chord at the edge; 8 cells (9 points) across the base at the coarse level",
     "edges and base 15 %", "Roadmap R-S.3, R-S.4 (laws 3, 6); DPW (8/12/16/24 cells), SPICES (≥ 8 at the fine level)", "In place (family 3)"),
    ("Panel breaks b1, b2 (and switch sections)", "Local suction peak, jump in the span loading, slope break of the loft",
     "A mesh station exactly on every break; spanwise growth ≤ 1.3 away from it",
     "spanwise 15 %", "Fix 3 on this page; primer Track 2 (spanwise law with anchors)", "Not done: stations ignore the breaks"),
    ("Tip and tip cap", "Smallest chord and Re, first stall on aft sweep, birth of the vortex",
     "Stations squeezed toward the tip so the last gap equals the cap's first cell; cap first cell = the tip station's first cell (refuse above 3×); outboard blocks 1.5 root chords beyond the tip, growth ≤ 1.15",
     "spanwise 15 %", "Roadmap R-S.1, R-V.3, R-V.5 (laws 9–12)", "Squeeze in place; cap first cell to be tied to the tip"),
    ("Near wake, trailing edge to 2 chords", "Wake sheet (velocity deficit), base flow, start of roll-up",
     "Overset wake box with cells of 0.0075 c (about 20 across the wake), tall and tilted to hold the wake at 0–12°; starts inside the near-body mesh",
     "wake 15 %", "Roadmap R-V.6 (laws 17, 18); Chan et al. 2002", "No designed wake (O-mesh)"),
    ("Far wake, 2 to 10 chords", "Downwash, induced drag, wake convection",
     "Wake-box cells grow from 0.0075 c to the background size",
     "wake 15 %", "Roadmap R-V.6", "No designed wake"),
    ("Tip vortex core", "Roll-up and path of the tip vortex",
     "Tube with 15–20 near-cubic cells across the core, starting about 2 chords behind the tip (the vortex forms within about 1 chord, inside the near-body mesh)",
     "wake 15 %", "Roadmap R-V.6 (law 19); primer section 05", "None"),
    ("Overlap between meshes", "Nothing leaks: the wake and the boundary layer pass between grids cleanly",
     "≥ 5 cells from each mesh, cell-size ratio ≤ 1.5, no overlap inside the boundary layer or at the tip, 0 orphan cells",
     "—", "Roadmap R-V.7 (law 21); Chan et al. 2002; Kenway et al. 2017", "Not built yet (Stage 2, M3)"),
    ("Background and far field", "Domain error",
     "Background 0.03 c around the wing, coarsening outward; far field from 80 chords (ladder 40 / 80 / 160)",
     "domain 10 % (of the total)", "Roadmap R-V.6 (laws 15, 16); DPW about 100 chords", "40 chords; 40 → 60 moved drag 0.6–0.7 counts"),
    ("Every zone together", "Grid convergence (the error bar)",
     "Every spacing in every mesh refined by one ratio r ≥ 1.3; distances fixed",
     "—", "Roadmap R-V.8 (law 23); Celik et al. 2008", "Outboard blocks did not refine with the family"),
]


def refine_html() -> str:
    return "".join(f"<tr><td class='what'>{z}</td><td>{p}</td><td>{r}</td><td class='num'>{b}</td><td class='src'>{s}</td><td class='muted'>{t}</td></tr>"
                   for z, p, r, b, s, t in REFINE)


def fig_refine_side() -> str:
    """Side view (a cut along the flow): which zones get fine cells around one section."""
    pts = _naca4()
    C, X0, YC = 220, 150, 190
    up = [(X0 + C * x, YC - C * yu) for x, yu, yl in pts]
    lo = [(X0 + C * x, YC - C * yl) for x, yu, yl in pts]
    poly = " ".join(f"{a:.1f},{b:.1f}" for a, b in up + lo[::-1])
    o = ['<svg class="dg" viewBox="0 0 1000 380" role="img" aria-label="Side view of the mesh zones around one section: wall layers on the whole surface, fine cells at the nose, at the trailing edge and across the blunt base, the near-body mesh reaching about two chords, a tilted wake box with cells of 0.0075 chord to two chords behind the trailing edge then growing to ten chords, and the background box of 0.03 chord">',
         '<defs><marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="fillc"/></marker></defs>']
    # background box
    o.append('<rect class="zone-bg" x="40" y="40" width="930" height="300"/>')
    o.append('<text class="lab muted" x="960" y="330" text-anchor="end">background: 0.03 c, coarsening to the far field (80 c)</text>')
    # near-body reach ~2c (ellipse around section)
    o.append(f'<ellipse class="nearbody" cx="{X0 + 0.5 * C}" cy="{YC}" rx="{0.5 * C + 150:.0f}" ry="125"/>')
    o.append(f'<text class="lab acc" x="{X0 + 0.5 * C}" y="{YC - 132}" text-anchor="middle">near-body mesh, reach about 2 c</text>')
    # wake box: fine to 2c, then growing to 10c (compressed), tilted for 0–12°
    te = X0 + C
    x2 = te + 190
    o.append(f'<polygon class="wakebox" points="{te},{YC - 16} {x2:.0f},{YC - 16 + 30} {x2:.0f},{YC + 22} {te},{YC + 14}"/>')
    o.append(f'<polygon class="wakebox far" points="{x2:.0f},{YC + 14} 960,{YC + 40} 960,{YC + 110} {x2:.0f},{YC + 22}"/>')
    o.append(f'<text class="lab acc" x="{te + 10}" y="{YC - 26}">wake box 0.0075 c, to 2 c</text>')
    o.append(f'<text class="lab acc" x="{x2 + 30:.0f}" y="{YC - 14}">then cells grow to the background, to 10 c</text>')
    o.append(f'<text class="lab muted" x="{x2 + 30:.0f}" y="{YC + 2}">tall and tilted: holds the wake at 0–12°</text>')
    # wall layers (offset outlines)
    for k, d in enumerate((3, 6, 10)):
        offs = " ".join(f"{a:.1f},{b - d:.1f}" for a, b in up) + " " + " ".join(f"{a:.1f},{b + d:.1f}" for a, b in lo[::-1])
        o.append(f'<polygon class="layer" points="{offs}"/>')
    o.append(f'<polygon class="wing" points="{poly}"/>')
    # nose and TE clusters
    o.append(f'<circle class="hot" cx="{X0}" cy="{YC - C * pts[0][1]:.1f}" r="14"/>')
    o.append(f'<circle class="hot" cx="{te}" cy="{YC:.1f}" r="11"/>')
    # labels
    o.append(f'<line class="leader" x1="{X0 - 12}" y1="{YC - 8}" x2="{X0 - 60}" y2="{YC + 70}"/><text class="lab" x="{X0 - 110}" y="{YC + 88}">nose: ≤ 10° turning per cell</text>')
    o.append(f'<line class="leader" x1="{te + 6}" y1="{YC + 10}" x2="{te + 40}" y2="{YC + 80}"/><text class="lab" x="{te + 20}" y="{YC + 98}">edge 0.1 % c · 8 cells across the base</text>')
    o.append(f'<line class="leader" x1="{X0 + 0.5 * C}" y1="{YC - 30}" x2="{X0 + 0.45 * C}" y2="{YC - 70}"/><text class="lab" x="{X0 + 0.1 * C:.0f}" y="{YC - 76}">wall layers: y⁺ ≤ 1, growth ≤ 1.25, ≥ 30 cells</text>')
    o.append(f'<text class="lab muted" x="{X0 + 0.05 * C:.0f}" y="{YC + 50}">bubble zone 30–60 % c (with a transition model)</text>')
    o.append('<text class="lab muted" x="50" y="372">schematic, not to scale (the far wake is compressed)</text>')
    o.append("</svg>")
    return "\n".join(o)


def fig_refine_top() -> str:
    """Top view: spanwise stations, breaks, tip, outboard blocks, wake box and vortex tube."""
    st = [(90, 80, 220), (270, 160, 125), (430, 215, 75), (600, 262, 30)]
    le = " ".join(f"{y},{x}" for y, x, c in st)
    te = " ".join(f"{y},{x + c}" for y, x, c in reversed(st))
    o = ['<svg class="dg" viewBox="0 0 1000 470" role="img" aria-label="Top view of the mesh zones: span stations nearly even from the root and squeezed toward the tip, a station on each break b1 and b2, outboard blocks reaching 1.5 root chords beyond the tip, the wake box behind the whole trailing edge, and a vortex tube starting about two chords behind the tip">']
    # wake box behind TE
    o.append('<polygon class="wakebox" points="90,300 610,292 640,440 90,440"/>')
    o.append('<text class="lab acc" x="110" y="430">wake box behind the whole trailing edge</text>')
    # outboard blocks beyond tip
    o.append('<rect class="outboard" x="600" y="230" width="90" height="110"/>')
    o.append('<text class="lab" x="612" y="224">outboard blocks: 1.5 root c, growth ≤ 1.15</text>')
    # vortex tube starting ~2c behind tip (tip at x 262..292)
    o.append('<rect class="tube" x="585" y="370" width="40" height="80" rx="18"/>')
    o.append('<text class="lab acc" x="636" y="410">vortex tube: 15–20 cells across the core,</text>')
    o.append('<text class="lab acc" x="636" y="426">from about 2 c behind the tip</text>')
    # wing
    o.append(f'<polygon class="wing" points="{le} {te}"/>')
    # span stations: nearly even, squeezed toward the tip, plus breaks
    import math
    n = 26
    ys = [90 + 510 * (1 - math.cos(0.5 * math.pi * k / n)) ** 0.9 if False else 90 + 510 * (math.sin(0.5 * math.pi * k / n)) for k in range(n + 1)]
    def x_at(y):
        for (y0, x0, c0), (y1, x1, c1) in zip(st[:-1], st[1:]):
            if y0 <= y <= y1:
                s = (y - y0) / (y1 - y0)
                return x0 + s * (x1 - x0), c0 + s * (c1 - c0)
        return st[-1][1], st[-1][2]
    for y in ys:
        x, c = x_at(y)
        o.append(f'<line class="station" x1="{y:.1f}" y1="{x:.1f}" x2="{y:.1f}" y2="{x + c:.1f}"/>')
    for y, x, c in st[1:3]:
        o.append(f'<line class="station brk" x1="{y}" y1="{x}" x2="{y}" y2="{x + c}"/>')
        o.append(f'<line class="leader" x1="{y}" y1="{x - 2}" x2="350" y2="102"/>')
    o.append('<text class="lab amber" x="350" y="96" text-anchor="middle">a station exactly on each break (b1, b2)</text>')
    o.append('<line class="leader" x1="560" y1="268" x2="720" y2="120"/><text class="lab" x="726" y="118">stations squeezed toward the tip:</text>')
    o.append('<text class="lab" x="726" y="134">last gap = the cap\'s first cell</text>')
    o.append('<text class="lab muted" x="96" y="60">stations nearly even from the root</text>')
    o.append('<line class="dash" x1="90" y1="40" x2="90" y2="450"/>')
    o.append("</svg>")
    return "\n".join(o)


# Where each input range comes from (filled from the source review; key -> text)
RANGE_BASIS = {
    'root_chord_m':
        "Real Class I–II wings with a published area (<a href='#real'>Real wings</a>). BWB up to 1.80 m: root of <a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou 2022</a>; covers the AUTh RX-3 (S 4.9 m², AR 8, 260 kg, <a href='https://www.mdpi.com/2673-4591/90/1/18'>Antoniou et al. 2025</a>). Full space: design-space bounds of <a href='https://www.mdpi.com/2673-4591/90/1/52'>Pliakos et al. 2025</a> (twist ±5° / ±7°, dihedral ±10°, c/4 sweep 0–60°). <span class='flag ok'>checked</span>",
    'aspect_ratio':
        "Real wings: tailless 2.9–8.6, with a tail 4.9–16.0 (<a href='#real'>Real wings</a>); flying wing 4.29 (<a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić 2024</a>). <span class='flag ok'>checked</span> Panknin's example has AR 10 (a model glider), just above.",
    'b3_ratio':
        "Our choice: breaks anywhere in 25–80 % of the span. BWB: outer panel 0.50 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou 2022</a>). <span class='flag ok'>checked</span>",
    'split_ratio':
        "Our choice. BWB: 0.48 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou 2022</a>). <span class='flag ok'>checked</span>",
    'c2_ratio':
        "BWB 0.61 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou 2022</a>), 0.67 (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline &amp; Agarwal 2017</a>). <span class='flag ok'>checked</span> Cranked: constant-chord centre (0.95–1), tapered outer panels; overall taper 0.38–0.85 (Raymer about 0.4 unswept, <a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>; layout as on Hermes 450 and Heron, from photos). <span class='flag open'>second-hand</span>",
    'c3_ratio':
        "BWB 0.39 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou</a>), 0.42 (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline</a>). <span class='flag ok'>checked</span>",
    'c4_ratio':
        "BWB 0.14 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou</a>), 0.13 (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline</a>). Tapered: about 0.4 (Raymer, <a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>) to 1 (Pioneer, Shadow: <a href='https://m-selig.ae.illinois.edu/ads/aircraft.html'>Lednicer</a>). Flying wing: 0.667 (<a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić</a>), 0.85 (<a href='https://www.b2streamlines.com/Panknin/Panknin.html'>Panknin</a>), Aquila 0.58. <span class='flag ok'>checked</span>",
    'sweep1_deg':
        "BWB 15° (<a href='https://www.icas.org/ICAS_ARCHIVE/ICAS2012/PAPERS/675.PDF'>Lehmkuehler 2012</a>), 30° c/4 (<a href='https://www.mdpi.com/2226-4310/9/5/275'>Suewatanakul 2022</a>). Flying wing 25° (<a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić</a>), Aquila 28°, 35° (<a href='https://www.icas.org/ICAS_ARCHIVE/ICAS2008/PAPERS/335.PDF'>PUL-10</a>), 40° (<a href='https://www.mdpi.com/2072-666X/11/6/553'>MAV, Shams 2020</a>) <span class='flag open'>agent only</span>. Tailed: near 0° c/4 at low speed (Raymer, <a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>); −5° keeps a small forward-sweep edge case. <span class='flag ok'>checked</span> <span class='flag open'>second-hand</span>",
    'sweep2_deg':
        'As panel 1, a little less outboard on the BWB (sweep falls toward the tip on the BWB papers).',
    'sweep3_deg':
        'As panel 2.',
    'twist0_deg':
        "Washout (tip below root). Tailed: at most 5°, Raymer about 3° (<a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>) <span class='flag open'>second-hand</span>. BWB 3° (<a href='https://www.mdpi.com/2226-4310/9/5/275'>Suewatanakul</a>), 7° (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline</a>) <span class='flag ok'>checked</span>. Flying wing 3.2° (<a href='https://www.b2streamlines.com/Panknin/Panknin.html'>Panknin</a>) <span class='flag ok'>checked</span>.",
    'twist1_deg':
        'Between root and tip twist (see twist at the root).',
    'twist2_deg':
        'Between root and tip twist (see twist at the root).',
    'twist3_deg':
        'Total washout: tailed 0–5°, flying wing 0–8°, BWB 1–9° (see twist at the root).',
    'dihedral_p1_deg':
        '"Normally the dihedral is about 0 to 5 degrees or so" (<a href=\'https://aircraftdesign.com/?p=132\'>Raymer</a>). BWB 5° (<a href=\'https://www.mdpi.com/2226-4310/9/5/275\'>Suewatanakul</a>). Flying wing 4° (<a href=\'https://www.icas.org/ICAS_ARCHIVE/ICAS2008/PAPERS/335.PDF\'>PUL-10</a>), 2° (<a href=\'https://www.mdpi.com/2072-666X/11/6/553\'>MAV</a>) <span class=\'flag open\'>agent only</span>. <span class=\'flag ok\'>checked</span>',
    'dihedral_p2_deg':
        'Same as panel 1.',
    'dihedral_p3_deg':
        'Same as panel 1.',
    'airfoils':
        "BWB: MH 104 body, MH 61 wing (<a href='https://www.mdpi.com/2226-4310/9/5/275'>Suewatanakul 2022</a>). Tailed: NACA 4415 on Pioneer and Shadow 200 (<a href='https://m-selig.ae.illinois.edu/ads/aircraft.html'>Lednicer</a>). Flying wing: Hepperle tailless sections (<a href='https://www.mh-aerotools.de/airfoils/mh60koo.htm'>MH 60</a>: Re ≥ 1.5 × 10⁵, root; <a href='https://www.mh-aerotools.de/airfoils/mh45koo.htm'>MH 45</a>: lower Re, tip); MH 60 on <a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić</a>. <span class='flag ok'>checked</span>",
}

INPUT_ROWS = [
    # (group, label, symbol, unit, variables per type: one name, or None when the type derives it)
    ("Size", "Root chord", "c<sub>r</sub>", "m", "root_chord_m"),
    ("Size", "Aspect ratio", "AR", "", "aspect_ratio"),
    ("Layout", "Outer panel, share of the semi-span", "f<sub>3</sub>", "", "b3_ratio"),
    ("Layout", "Inner panel, share of the rest", "s", "", "split_ratio"),
    ("Chords", "Chord at b1", "r<sub>1</sub>", "", "c2_ratio"),
    ("Chords", "Chord at b2", "r<sub>2</sub>", "", "c3_ratio"),
    ("Chords", "Tip chord / taper", "r<sub>3</sub>, λ", "", "c4_ratio"),
    ("Sweep", "Leading-edge sweep, panel 1", "Λ<sub>1</sub>", "°", "sweep1_deg"),
    ("Sweep", "Leading-edge sweep, panel 2", "Λ<sub>2</sub>", "°", "sweep2_deg"),
    ("Sweep", "Leading-edge sweep, panel 3", "Λ<sub>3</sub>", "°", "sweep3_deg"),
    ("Twist", "Twist at the root b0", "θ<sub>0</sub>", "°", "twist0_deg"),
    ("Twist", "Twist at b1", "θ<sub>1</sub>", "°", "twist1_deg"),
    ("Twist", "Twist at b2", "θ<sub>2</sub>", "°", "twist2_deg"),
    ("Twist", "Twist at the tip b3", "θ<sub>3</sub>", "°", "twist3_deg"),
    ("Dihedral", "Dihedral, panel 1 (b0–b1)", "Γ<sub>1</sub>", "°", "dihedral_p1_deg"),
    ("Dihedral", "Dihedral, panel 2 (b1–b2)", "Γ<sub>2</sub>", "°", "dihedral_p2_deg"),
    ("Dihedral", "Dihedral, panel 3 (b2–b3)", "Γ<sub>3</sub>", "°", "dihedral_p3_deg"),
]

CHORD_NOTE = {"stations": "× root", "per_panel": "× chord inboard", "linear_taper": "tip / root (taper λ)"}

DERIVED_ROWS = [
    ("Panel span shares", "f<sub>1</sub> = (1 − f<sub>3</sub>) · s,  f<sub>2</sub> = 1 − f<sub>1</sub> − f<sub>3</sub>", "all"),
    ("Chord ratios r<sub>i</sub> = c<sub>i</sub> / c<sub>r</sub>",
     "BWB: (1, r<sub>1</sub>, r<sub>2</sub>, r<sub>3</sub>). Cranked: (1, r<sub>1</sub>, r<sub>1</sub>r<sub>2</sub>, r<sub>1</sub>r<sub>2</sub>r<sub>3</sub>). Tapered, flying wing: r(y) = 1 + (λ − 1) · y / S, so r<sub>1</sub>, r<sub>2</sub> follow", "all"),
    ("Mean chord ratio", "K = Σ f<sub>i</sub> (r<sub>i−1</sub> + r<sub>i</sub>) / 2  (straight panels)", "all"),
    ("Semi-span", "S = AR · c<sub>r</sub> · K / 2", "all"),
    ("Span, area, mean chord", "b = 2S,  A = 2 S c<sub>r</sub> K = b² / AR,  c̄ = A / b = c<sub>r</sub> K", "all"),
    ("Mean aerodynamic chord", "MAC = ∫c² dy / ∫c dy (exact for straight panels)", "all"),
    ("Station span positions", "y<sub>0</sub> = 0,  y<sub>i</sub> = y<sub>i−1</sub> + f<sub>i</sub> S", "all"),
    ("Sweeps 2 and 3", "Λ<sub>2</sub> = Λ<sub>3</sub> = Λ<sub>1</sub> (one straight leading edge)", "tapered, flying wing"),
    ("Leading-edge positions", "x<sub>i</sub> = x<sub>i−1</sub> + tan Λ<sub>i</sub> · f<sub>i</sub> S", "all"),
    ("Station heights", "z<sub>i</sub> = z<sub>i−1</sub> + tan Γ<sub>i</sub> · f<sub>i</sub> S  (sections vertical, root in y = 0)", "all"),
    ("Overall taper", "λ = c<sub>tip</sub> / c<sub>r</sub>", "all"),
    ("Trailing-edge thickness", "t = max(floor, 0.2 % · c), floor 0.5 mm (Class I) or 1.0 mm (Class II); opened over the last 10 % of chord", "all"),
]


def params_tables_html() -> dict:
    cfg = load_config()
    specs = [cfg.types[t] for t in WING_TYPES]

    fulls = [cfg.full[t] for t in WING_TYPES]

    def rtxt(lo, hi, unit):
        f = lambda x: f"{x:g}".replace("-", "−")  # noqa: E731
        txt = f"{f(lo)} to {f(hi)}" if min(lo, hi) < 0 else f"{f(lo)}–{f(hi)}"
        return f"{txt}{(' ' + unit) if unit and unit != '°' else unit}"

    def cell(sp, v, unit):
        if v in sp.derived:
            return "<span class='muted'>derived</span>"
        fu = fulls[specs.index(sp)]
        note = f"<br><span class='muted'>{CHORD_NOTE[sp.chord_law]}</span>" if v in ("c2_ratio", "c3_ratio", "c4_ratio") else ""
        full = ("<br><span class='fullr'>full " + rtxt(*fu.ranges[v], unit) + "</span>"
                if fu.ranges[v] != sp.ranges[v] else "<br><span class='fullr'>full: same</span>")
        return f"<strong>{rtxt(*sp.ranges[v], unit)}</strong>{full}{note}"

    rows, last = [], None
    for grp, lab, sym, unit, v in INPUT_ROWS:
        if grp != last:
            rows.append(f"<tr class='grp'><td colspan='{len(specs) + 3}'>{grp}</td></tr>")
            last = grp
        basis = RANGE_BASIS.get(v, "<span class='flag open'>no source yet</span>")
        rows.append(f"<tr><td class='what'>{lab}<span class='id'>{v}</span></td><td>{sym}</td>"
                    + "".join(f"<td class='num'>{cell(sp, v, unit)}</td>" for sp in specs)
                    + f"<td class='src'>{basis}</td></tr>")
    rows.append(f"<tr class='grp'><td colspan='{len(specs) + 3}'>Fixed per type (not sampled)</td></tr>")
    rows.append("<tr><td class='what'>Airfoils b0, b1, b2, b3</td><td></td>"
                + "".join(f"<td><strong>{', '.join('/'.join(c) for c in sp.choices)}</strong>"
                          f"<br><span class='fullr'>full: {' | '.join('/'.join(c) for c in fu.choices)}</span></td>"
                          for sp, fu in zip(specs, fulls))
                + f"<td class='src'>{RANGE_BASIS.get('airfoils', '')}</td></tr>")
    free = "".join(f"<td class='num'>{len(sp.free_variables)}</td>" for sp in specs)
    rows.append(f"<tr><td class='what'>Sampled variables</td><td></td>{free}<td></td></tr>")
    derived = "".join(f"<tr><td class='what'>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in DERIVED_ROWS)
    return {"__INPUTS__": "\n".join(rows), "__DERIVED__": derived}


def verification_sets_html() -> str:
    f = DOCS / "verification_sets.json"
    if not f.is_file():
        return "<tr><td colspan='12'>Run <code>python scripts/verify_sets.py</code>.</td></tr>"
    sm = json.loads(f.read_text())["summary"]
    keys = ("stations_pct", "chord_pct", "twist_deg", "sweep_deg", "dihedral_deg", "straight_pct", "ar_pct",
            "sections_pct", "ruled_pct", "root_y_m", "min_y_m")
    g = lambda x: "0" if x == 0 else f"{x:.1g}" if abs(x) < 1e-6 else f"{x:.2g}"  # noqa: E731
    return "\n".join(f"<tr><td>{TYPE_NAME[t]}</td><td class='num'>{r['wings']}</td>"
                     + "".join(f"<td class='num'>{g(r[k])}</td>" for k in keys) + "</tr>" for t, r in sm.items())


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
    built = [w for r in rows_ if not r["set"].startswith("holdout") for w in r["wings"]]
    ok = sum(1 for w in built if w.get("passed"))
    from cfdauto.geometry.build import code_hash
    versions = sorted({r["version"] for r in rows_})
    hashes = {r["code_hash"] for r in rows_ if not r["set"].startswith("holdout")}
    ver = json.loads((DOCS / "verification.json").read_text()) if (DOCS / "verification.json").is_file() else []
    return {"built": len(built), "ok": ok, "stale": hashes != {code_hash()}, "versions": ", ".join(versions),
            "backend": ", ".join(sorted({r["backend"] for r in rows_ if not r["set"].startswith("holdout")})),
            "pub": len(ver), "pub_ok": sum(1 for v in ver if v["pass"])}


# --------------------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------------------

PAGE = """<meta charset="utf-8">
<title>Wing Generator</title>
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
p code, li code, td code, footer code { overflow-wrap: anywhere; white-space: normal; }
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
td.src { font-size: 12.5px; color: var(--muted); width: 36%; min-width: 260px; line-height: 1.45; }
table.inp td.num { white-space: normal; font-size: 12.5px; }
.fullr { color: var(--muted); font-size: 11.5px; }
table.summ td { font-size: 13px; vertical-align: top; } table.summ td.what { white-space: nowrap; }
table.inp td.what { min-width: 120px; }
.muted { color: var(--muted); font-size: 13px; }
.tag, .basis, .flag { font-family: var(--mono); font-size: 11px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; border: 1px solid currentColor; white-space: nowrap; font-weight: 500; }
.tag.conventional, .tag.tapered { color: var(--accent); } .tag.bwb { color: var(--bwb); } .tag.flying_wing { color: var(--amber); }
.basis.req { color: var(--violet); } .basis.src { color: var(--accent); } .basis.meas { color: var(--bwb); } .basis.own { color: var(--amber); }
.flag.fix { color: var(--warn); } .flag.open { color: var(--amber); } .flag.ok { color: var(--bwb); }
.legend { font-size: 13px; color: var(--muted); display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; }
.weak { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--warn); border-radius: 6px; padding: 14px 18px; }
.weak ul, .weak ol { margin: 6px 0 0; padding-left: 22px; display: flex; flex-direction: column; gap: 10px; }
.weak.amber { border-left-color: var(--amber); }
.fixrow strong { display: block; }
.fixrow .do { color: var(--ink); font-weight: 600; }
figure.fig { margin: 0; display: flex; flex-direction: column; gap: 8px; }
figure.fig .svgwrap { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 8px; overflow-x: auto; }
svg.dg { display: block; width: 100%; min-width: 640px; height: auto; color: var(--ink); }
svg.dg .lab { fill: currentColor; font: 13px var(--body); }
svg.dg .lab.head { font: 700 16px var(--display); }
svg.dg .muted, svg.dg .lab.muted { fill: var(--muted); font-size: 12px; }
svg.dg .acc { fill: var(--accent); } svg.dg .warn { fill: var(--warn); } svg.dg .amber { fill: var(--amber); } svg.dg .bwbc { fill: var(--bwb); }
svg.dg .zone-low { fill: var(--amber); opacity: .10; } svg.dg .zone-mid { fill: var(--accent); opacity: .06; }
svg.dg .bar.bwb { fill: var(--bwb); } svg.dg .bar.conv { fill: var(--accent); } svg.dg .bar.fw { fill: var(--amber); } svg.dg .bar.tipbar { opacity: .5; }
svg.dg .real { stroke: var(--ink); stroke-width: 1.4; opacity: .55; }
svg.dg .level { stroke: var(--warn); stroke-width: 1.4; stroke-dasharray: 5 4; }
svg.dg .axis, svg.dg .stroke { stroke: currentColor; stroke-width: 1.4; fill: none; }
svg.dg .fillc { fill: currentColor; }
svg.dg .dash { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 4 4; fill: none; }
svg.dg .wing { fill: var(--grp); stroke: currentColor; stroke-width: 1.6; }
svg.dg .outline { fill: none; stroke: currentColor; stroke-width: 1.6; }
svg.dg .laminar { fill: var(--bwb); opacity: .30; }
svg.dg .stall { fill: var(--warn); opacity: .25; }
svg.dg .base { stroke: var(--warn); stroke-width: 4; fill: none; stroke-linecap: round; }
svg.dg .kink { fill: none; stroke: var(--amber); stroke-width: 2.5; }
svg.dg .drift { stroke: var(--accent); stroke-width: 2; }
svg.dg .wake { stroke: var(--muted); stroke-width: 1.2; stroke-dasharray: 3 3; fill: none; }
svg.dg .vortex { fill: none; stroke: var(--accent); stroke-width: 1.8; }
svg.dg .leader { stroke: var(--muted); stroke-width: .8; }
svg.dg .lam { stroke: var(--bwb); stroke-width: 3; fill: none; }
svg.dg .turb { stroke: var(--accent); stroke-width: 7; opacity: .55; fill: none; stroke-linejoin: round; }
svg.dg .bubble { stroke: var(--amber); stroke-width: 2.5; fill: none; }
svg.dg .zone-bg { fill: none; stroke: var(--muted); stroke-width: 1; stroke-dasharray: 2 4; }
svg.dg .nearbody { fill: var(--accent); opacity: .07; stroke: var(--accent); stroke-width: 1.2; }
svg.dg .wakebox { fill: var(--accent); opacity: .22; stroke: var(--accent); stroke-width: 1; }
svg.dg .wakebox.far { opacity: .10; }
svg.dg .layer { fill: none; stroke: var(--accent); stroke-width: .8; opacity: .7; }
svg.dg .hot { fill: var(--warn); opacity: .28; }
svg.dg .outboard { fill: var(--amber); opacity: .18; stroke: var(--amber); stroke-width: 1; }
svg.dg .tube { fill: var(--accent); opacity: .30; stroke: var(--accent); stroke-width: 1.2; }
svg.dg .station { stroke: var(--muted); stroke-width: .9; }
svg.dg .station.brk { stroke: var(--amber); stroke-width: 2.4; }
footer { color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 12px; }
@media (prefers-reduced-motion: reduce) { .card img[src^="data:image/gif"] { animation: none; } }
</style>
<div class="wrap">
<header>
  <div class="eyebrow">CFD_Automation · Stage 1 · geometry · code __VERSION__</div>
  <h1>Wing Generator</h1>
  <p class="lede">Eighteen numbers go in; one exact wing surface comes out, measured, labelled and checked. One generator and one YAML file make BWB, cranked, tapered and flying wings, sized like real Class I and II UAVs. Every later stage (mesh, solver, data) reads only this surface.</p>
  <nav aria-label="On this page"><a href="#glance">At a glance</a><a href="#summary">Final ranges and flows</a><a href="#design">Design space</a><a href="#pairs">Key pairs</a><a href="#family">Wing families</a><a href="#ranges">Sizes</a><a href="#inputs">Parameters</a><a href="#reynolds">Re and Mach</a><a href="#phenomena">Flow phenomena</a><a href="#refine">Where to refine</a><a href="#open">Open decisions</a><a href="#decisions">Design decisions</a><a href="#fix">Fix before Stage 2</a><a href="#real">Real wings</a><a href="#checks">Checks and results</a><a href="#limits">What it cannot make</a><a href="#published">Published wings</a><a href="#commands">Commands</a></nav>
</header>

<section id="glance">
  <h2>At a glance</h2>
  <div class="three">
    <div class="box"><h3>In</h3><div class="big">18 numbers + a wing type</div><p>From <code>configs/wing.yaml</code>: chords, spans, sweeps, twists, dihedrals, and an airfoil per station. Types: BWB, cranked, tapered, flying wing.</p></div>
    <div class="box"><h3>Out</h3><div class="big">One surface, checked</div><p>Upper, lower and trailing-edge base, read as <code>upper(u, v)</code>. Plus measured values, labels, four refusing checks, a hash, IGES.</p></div>
    <div class="box"><h3>Evidence</h3><div class="big">__OK__ of __BUILT__ wings pass</div><p>Sampled wings of all four types, focus and full space, 0 refused (__SETVER__). __PUBOK__ of __PUB__ published wings verified. Tests: __TESTS__.</p></div>
    <div class="box verdict"><h3>Verdict</h3><div class="big">Ready for Stage 2 after the pyGeo run</div><p>Fixes 1 and 2 done (panel dihedrals, code hash). Left: run the pyGeo tests and rebuild the sets with pyGeo on your machine; fix 3 belongs to the mesher. Not yet "any wing": straight panels only, no airfoil shape variable. Sets: __STALE__</p></div>
  </div>
</section>

<section id="summary">
  <h2>Final ranges and flows</h2>
  <p>Everything in one table. <strong>Bold</strong>: the focus space (realistic, sampled densely). <span class="fullr">Grey</span>: the full space (supported, sampled sparsely). Speeds come from the real wings of each family; study Re levels: 1 × 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶.</p>
  <div class="tbl"><table class="wide summ">__SUMMARY__</table></div>
  <p class="muted">Details: <a href="#design">Design space</a>, <a href="#ranges">Sizes</a>, <a href="#reynolds">Re and Mach</a>, <a href="#phenomena">Flow phenomena</a>, <a href="#refine">Where to refine</a>.</p>
</section>

<section id="design">
  <h2>Design space: what we support, where real wings are, where we focus</h2>
  <p>One row per variable, one lane per wing type. <strong>Light bar</strong>: the full space (everything the generator supports; 40 wings + 5 hold-out per type, both corner sets at its edges). <strong>Dark bar</strong>: the focus space (where real wings are; 100 wings + 5 reference + 10 hold-out per type). <strong>Black marks</strong>: real wings and published designs. Rows marked "derived" are computed from the inputs.</p>
  <figure class="fig card">__PNG_DESIGN__<figcaption>Read a row left to right: if the black marks sit inside the dark bar, the focus space covers the real wings; the light bar shows how far beyond them we still promise to work. Root twist only sets the incidence; washout is what changes the wing. Sources: <code>configs/shape_evidence.yaml</code>, <code>configs/real_uavs.yaml</code>.</figcaption></figure>
  <div class="weak amber"><strong>What the figure shows honestly.</strong> Shape evidence is thin for wings with a tail (Raymer rules, partly second-hand) and for the layout shares (one BWB paper). Sizes are well covered. The full space is our choice, set to the widest value in any source; nothing real sits at its far edges.</div>
</section>

<section id="pairs">
  <h2>Key pairs</h2>
  <p>The same three layers in two dimensions, one panel per type. Faint dots: full space. Strong dots: focus space. Black diamonds: real or published wings that give both values.</p>
  <figure class="fig card">__PNG_PAIR_SIZE__<figcaption><strong>Size</strong>: span against mean chord. Every real Class I–II wing with a published area, against its family (tailless: BWB and flying wing; with a tail: cranked and tapered).</figcaption></figure>
  <figure class="fig card">__PNG_PAIR_PLANFORM__<figcaption><strong>Planform</strong>: aspect ratio against overall taper. The BWB lives at very low taper (big centre body), the others at 0.3–1.</figcaption></figure>
  <figure class="fig card">__PNG_PAIR_SWEEP__<figcaption><strong>Sweep</strong>: aspect ratio against inner-panel leading-edge sweep. Published sweeps given at the quarter chord (marked c/4 in the sources) sit a few degrees below their leading-edge value.</figcaption></figure>
  <figure class="fig card">__PNG_PAIR_TWIST__<figcaption><strong>Trim</strong>: sweep against washout. Tailless wings trim with sweep and washout together; the published tailless wings sit inside the focus space.</figcaption></figure>
</section>

<section id="family">
  <h2>Wing families</h2>
  <p>For each type, one variable group at a time goes from the full minimum to the full maximum; all others stay at the focus mid-range. Columns 2–4 (solid) are the focus space; columns 1 and 5 (dashed) are the edges of the full space. Top views are scaled to equal span so the shape is visible; true sizes are in <a href="#ranges">Sizes</a>.</p>
  <figure class="fig card">__PNG_FAM_BWB__</figure>
  <figure class="fig card">__PNG_FAM_CONV__</figure>
  <figure class="fig card">__PNG_FAM_TAP__</figure>
  <figure class="fig card">__PNG_FAM_FW__</figure>
</section>

<section id="inputs">
  <h2>Parameters: inputs and derived</h2>
  <p>The generator samples only the <strong>inputs</strong> below. Everything else is <strong>derived</strong> from them by fixed formulas. Four stations: root b0, breaks b1 and b2, tip b3; three straight panels between them.</p>
  <div class="three">
    <div class="box"><h3>Full space</h3><div class="big">What we support</div><p>Wider ranges and every sourced airfoil. Sampled sparsely: 40 wings per type, plus both corner sets at its edges. Grey line in each cell.</p></div>
    <div class="box"><h3>Focus space</h3><div class="big">Where real wings are</div><p>Ranges from real Class I–II wings and papers; suggested airfoils. Sampled densely: 100 wings per type, the reference wings and the hold-out. Bold line in each cell.</p></div>
    <div class="box"><h3>Why two</h3><div class="big">Wide, but dense where it counts</div><p>The mesher must work on anything we claim to support; the studies and the ML spend most runs where real wings are. The focus box lies inside the full box (the YAML refuses it otherwise).</p></div>
  </div>
  <h2 style="font-size:22px">Inputs (sampled), by wing type</h2>
  <div class="tbl"><table class="wide inp">
    <thead><tr><th>Input</th><th>Symbol</th><th>BWB</th><th>Cranked</th><th>Tapered</th><th>Flying wing</th><th>Why this range (focus)</th></tr></thead>
    <tbody>
__INPUTS__
    </tbody>
  </table></div>
  <p class="muted">"derived": that type computes the value (see below). Sweep positive aft; twist positive nose up; dihedral positive tip up.</p>
  <h2 style="font-size:22px">Derived (computed, never sampled)</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Quantity</th><th>Formula</th><th>Types</th></tr></thead>
    <tbody>
__DERIVED__
    </tbody>
  </table></div>
  <p class="muted">Checked on every built wing: chords (0.1 %), sweeps (0.1°), twists and panel dihedrals (0.2°) and the aspect ratio (0.1 %), measured on the loft against the inputs.</p>
</section>

<section id="ranges">
  <h2>Sizes we can make</h2>
  <p>The input ranges are in <a href="#inputs">Parameters</a>. This is what they produce.</p>
  <figure class="fig">__GIF_SIZES__<figcaption>Smallest and largest wing (least and most area) of each type, true scale. Solid: focus space. Dashed: full space. Left view 0.6 m wide, right view 22 m wide; same scale in every frame.</figcaption></figure>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Space</th><th>Span</th><th>Wing area</th><th>Mean chord</th><th>Root chord</th><th>Tip chord</th></tr></thead>
    <tbody>__EXTREMES__</tbody>
  </table></div>
  <p class="muted">Smallest and largest over all corners of the size inputs (other inputs mid-range). <code>python scripts/size_extremes.py</code>.</p>
  <h2 style="font-size:22px">What the focus space makes</h2>
  <p class="muted">2,000 Latin-hypercube wings per type.</p>
  <div class="tbl"><table class="mid">
    <thead><tr><th></th><th>BWB</th><th>Cranked</th><th>Tapered</th><th>Flying wing</th></tr></thead>
    <tbody>__GEN__</tbody>
  </table></div>
</section>

<section id="reynolds">
  <h2>Reynolds and Mach numbers</h2>
  <div class="three">
    <div class="box"><h3>Study levels (Stage 0)</h3><div class="big">1 × 10⁵ · 3 × 10⁵ · 1.5 × 10⁶ · 3 × 10⁶</div><p>On the mean chord. Every mesh study runs at these four. 1 × 10⁵ added 30 Oct 2026 for mini Class I wings.</p></div>
    <div class="box"><h3>Real wings fly at</h3><div class="big">__REAL_RE__</div><p>Mean chord, cruise at 3,048 m to top speed at sea level, for the real wings with a published area.</p></div>
    <div class="box"><h3>Mach</h3><div class="big">0.03 – 0.20</div><p>Every type, both spaces: below 0.3, so the flow is incompressible to a good approximation. Speed comes from the real wings, not from the wing size.</p></div>
  </div>
  <h2 style="font-size:22px">By type and space</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Space</th><th>Speed</th><th>Mach</th><th>Re, mean chord</th><th>Re, smallest tip</th><th>Re, largest root</th></tr></thead>
    <tbody>__RE_MACH__</tbody>
  </table></div>
  <p class="muted">Lowest: smallest chord at the family's lowest cruise speed at 3,048 m. Highest: largest chord at its highest top speed at sea level. Air from Stage 0 (ISA, Sutherland); a = 328.6 m/s at 3,048 m, 340.3 m/s at sea level. One wing covers a much narrower band than its row. Below the lowest study level (1 × 10⁵): only tips and the smallest wings at their slowest speed. Above the top one (3 × 10⁶): only the largest wings.</p>
  <h2 style="font-size:22px">What each Re band means</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Re (on the local chord)</th><th>Flow</th><th>Who is there</th><th>RANS (SA, fully turbulent)</th></tr></thead>
    <tbody>
      <tr><td class="num">below 10⁵</td><td>Laminar; separation without reattachment is likely; strong hysteresis</td><td>Tips of small wings; full-space micro wings</td><td><span class="flag fix">poor</span> no transition model, results only indicative</td></tr>
      <tr><td class="num">10⁵ – 5 × 10⁵</td><td>Laminar separation bubbles, transition on the bubble</td><td>Most Class I wings; outer panels of BWBs</td><td><span class="flag open">biased</span> drag too high, bubble missed</td></tr>
      <tr><td class="num">5 × 10⁵ – 3 × 10⁶</td><td>Transition ahead of mid-chord; mostly attached turbulent flow</td><td>Class II wings; BWB centre bodies</td><td><span class="flag ok">good</span> small bias from the laminar run</td></tr>
      <tr><td class="num">above 3 × 10⁶</td><td>Turbulent over most of the chord</td><td>Largest full-space roots only</td><td><span class="flag ok">good</span> above the top study level</td></tr>
    </tbody>
  </table></div>
  <p class="muted">Bands are approximate (Carmichael 1981; Lissaman 1983; Mueller &amp; DeLaurier 2003), see <a href="#phenomena">Flow phenomena</a>.</p>
</section>

<section id="phenomena">
  <h2>Flow phenomena you will meet</h2>
  <p>What the flow does on these wings, at these Re and angles, and whether the planned CFD (ADflow, steady RANS, Spalart–Allmaras, fully turbulent) can see it.</p>
  <figure class="fig"><div class="svgwrap">__FIG_RE__</div>
    <figcaption class="cap">Where the wings fly. Most of every type sits in or near the low-Re regime, and the tips go furthest into it, down to 2 × 10⁴. The study level 1 × 10⁵ (added 30 Oct 2026) now reaches the mini Class I wings; only the tips stay below every level. From the generated envelope and the real wings with a published area and speeds (low-Re limit: below 5 × 10⁵, Univ. Waterloo Fluid Mechanics Research Lab; Carmichael 1981).</figcaption></figure>
  <figure class="fig card">__PNG_LOCALRE__
    <figcaption class="cap">Real geometry, real speeds: local chord Reynolds number along the span. The smallest wings at their slowest speed sit almost wholly below 10⁵ (red); the BWB carries two regimes at once, its centre body an order of magnitude above its tips. The largest wings at top speed are turbulent except near the BWB and flying-wing tips.</figcaption></figure>
  <h2 style="font-size:22px">What the planned CFD misses: measured in 2-D</h2>
  <p>Each suggested section was run in XFOIL (Drela 1989; e<sup>N</sup> transition, N<sub>crit</sub> 9) twice: free transition, and tripped at 1 % chord, which is what fully turbulent SA does. The gap is the 2-D size of the model band. It is a proxy: no sweep, no crossflow, no 3-D relief.</p>
  <figure class="fig card">__PNG_XFCF__
    <figcaption class="cap">Upper surface at 4°. At 10⁵ and 3 × 10⁵ the free flow runs laminar to mid-chord, separates (shaded, Cf &lt; 0) and turns turbulent on the bubble. At 1.5–3 × 10⁶ transition moves forward to 30–45 % chord with no bubble. Tripped: turbulent from the nose, with much higher friction everywhere.</figcaption></figure>
  <figure class="fig card">__PNG_XFBAND__
    <figcaption class="cap">__XF_NOTE__</figcaption></figure>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Phenomenon</th><th>Where in our ranges</th><th>What it does</th><th>Does our CFD capture it?</th><th>Source</th></tr></thead>
    <tbody>__PHEN__</tbody>
  </table></div>
  <div class="weak"><strong>The biggest one.</strong> Most of these wings fly where transition and laminar bubbles set the drag, and the planned model cannot see them. Mesh error can be made small; this model error cannot. Every drag number needs its model band, and differences between wings are safer than absolute drag.</div>
</section>

<section id="refine">
  <h2>Where the mesh must be fine</h2>
  <p>Each phenomenon above lives in one region of the flow; each region gets its own rule. The rules are the Grand Roadmap recipes (R-S, R-V) and the Stage 0 error budget: the share is how much of the 65 % grid error each direction may use. The last column says where S8 stands today.</p>
  <figure class="fig"><div class="svgwrap">__FIG_RSIDE__</div>
    <figcaption class="cap">Side view: fine cells at the wall (all around), at the nose and at the trailing edge, then a wake box that stays fine for 2 chords and coarsens to 10 chords, all inside the background box.</figcaption></figure>
  <figure class="fig"><div class="svgwrap">__FIG_RTOP__</div>
    <figcaption class="cap">Top view: stations nearly even from the root, squeezed toward the tip, and one exactly on each break; outboard blocks past the tip; the wake box behind the whole trailing edge; the vortex tube from about 2 chords behind the tip.</figcaption></figure>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Zone</th><th>Captures</th><th>Rule (starting value)</th><th>Budget share</th><th>Source</th><th>S8 today</th></tr></thead>
    <tbody>__REFINE__</tbody>
  </table></div>
  <p class="muted">Budget shares from Stage 0: chordwise 35 %, spanwise 15 %, wall-normal 20 %, edges and base 15 %, wake 15 % of the grid error; domain 10 % of the total. All values are starting values; the mesh studies (Grand Roadmap stage 4) confirm or replace them.</p>
</section>

<section id="fix" class="weak">
  <h2>Fix left (for Stage 2)</h2>
  <p class="muted">Done on 29 Oct 2026: the unrealistic conventional set (tapered type and per-panel chords), the dihedral input (three panel values) and the hash (from the code itself). One fix is left, and it belongs to Stage 2.</p>
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
  <h2 style="font-size:22px">Is the loft the designed wing? (every sampled wing)</h2>
  <p class="muted">Worst value over every training, corner and reference wing (<code>scripts/verify_sets.py</code>, numpy loft). Stations, chords, twists, sweeps, panel dihedrals and the straightness of each panel match the inputs to machine precision. AR: the loft measures the true chord, which is a little shorter between two stations of different twist (up to 0.035 %; 0 without twist). Sections: up to 0.012 % of chord, at the smallest tips, where the 0.5 mm trailing-edge floor is a large share of a 3 cm chord. Root: every point of the root section at y = 0, and no point of a half wing below y = 0, so the mirrored halves meet only there.</p>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Wings</th><th>Stations % c</th><th>Chord %</th><th>Twist °</th><th>Sweep °</th><th>Dihedral °</th><th>Straight panels % c</th><th>AR %</th><th>Sections % c</th><th>Ruled % c</th><th>Root |y| m</th><th>Min y m</th></tr></thead>
    <tbody>
__VSETS__
    </tbody>
  </table></div>
  <h2 style="font-size:22px">Is the surface the intended wing? (published wings)</h2>
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
  <p class="muted"><span class="flag open">decide</span> needs your call. <span class="flag ok">act</span> a task with no choice left. Full history: <code>Stage 0_Decisions/OPEN_DECISIONS.md</code>.</p>
__OPEN__
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


SECTION_ORDER = ("glance", "summary", "design", "pairs", "family", "ranges", "inputs", "reynolds", "phenomena", "refine",
                 "open", "decisions", "fix", "real", "checks", "limits", "published", "commands")


def open_html() -> str:
    out, last = [], None
    for g, t, q, k in OPEN:
        if g != last:
            if last is not None:
                out.append("</ul>")
            n_dec = sum(1 for x in OPEN if x[0] == g and x[3] == "decide")
            out.append(f"<h3>{g} <span class='muted'>({n_dec} to decide)</span></h3><ul>")
            last = g
        flag = "<span class='flag open'>decide</span>" if k == "decide" else "<span class='flag ok'>act</span>"
        out.append(f"<li>{flag} <strong>{t}.</strong> {q}</li>")
    out.append("</ul>")
    return "\n".join(out)


def reorder_sections(page: str) -> str:
    """Put the sections in reading order: overview and pictures first, details and evidence after."""
    import re
    blocks = {m.group(1): m.group(0) for m in re.finditer(r'<section id="([a-z]+)"[^>]*>.*?</section>', page, re.S)}
    missing = [k for k in blocks if k not in SECTION_ORDER]
    if missing:
        raise ValueError(f"sections without a place in SECTION_ORDER: {missing}")
    first = page.index(blocks[SECTION_ORDER[0]])
    end = max(page.index(b) + len(b) for b in blocks.values())
    body = "\n\n".join(blocks[k] for k in SECTION_ORDER if k in blocks)
    return page[:first] + body + page[end:]


def main() -> None:
    m = manifests()
    g = glance(m)
    fixes = "\n".join(
        f"<li class='fixrow'><strong>{t}</strong>{e.replace('__VERSION__', __version__)} <span class='do'>Do: {d}</span></li>"
        for t, e, d in FIXES)
    real_rows, real = real_table()
    env = real["envelope"]
    fr = final_ranges_html() | extremes_html() | {"__FIG_RE__": fig_re_map(), "__XF_NOTE__": xfoil_note(), "__SUMMARY__": summary_html(),
                                "__FIG_RSIDE__": fig_refine_side(), "__FIG_RTOP__": fig_refine_top(), "__REFINE__": refine_html(),
                                "__VSETS__": verification_sets_html()} | params_tables_html()
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
                .replace("__PNG_LOCALRE__", img("local_re.png", "Local chord Reynolds number along the span of the smallest and largest wing of each type"))
                .replace("__PNG_XFCF__", img("xfoil_cf.png", "XFOIL upper-surface skin friction, free transition vs tripped, at the four study Re levels"))
                .replace("__PNG_XFBAND__", img("xfoil_band.png", "XFOIL profile-drag increase when tripped, and transition position, against Re"))
                .replace("__PNG_DESIGN__", img("design_space.png", "Every variable: full range, focus range and published values per wing type"))
                .replace("__PNG_PAIR_SIZE__", img("pair_size.png", "Span against mean chord per type"))
                .replace("__PNG_PAIR_PLANFORM__", img("pair_planform.png", "Aspect ratio against taper per type"))
                .replace("__PNG_PAIR_SWEEP__", img("pair_sweep.png", "Aspect ratio against sweep per type"))
                .replace("__PNG_PAIR_TWIST__", img("pair_twist.png", "Sweep against washout per type"))
                .replace("__PNG_FAM_BWB__", img("family_bwb.png", "BWB family: one variable group at a time"))
                .replace("__PNG_FAM_CONV__", img("family_conventional.png", "Cranked family: one variable group at a time"))
                .replace("__PNG_FAM_TAP__", img("family_tapered.png", "Tapered family: one variable group at a time"))
                .replace("__PNG_FAM_FW__", img("family_flying_wing.png", "Flying-wing family: one variable group at a time"))
                .replace("__GIF_SIZES__", img("size_extremes.gif", "Smallest and largest wing of each type, focus and full space, true scale"))
                .replace("__GIF_REF__", img("published_wings.gif", "Animation of the published wings rebuilt by the generator"))
                .replace("__PNG_TOP__", img("published_wings_topviews.png", "Top views of all published wings"))
                .replace("__PNG_CRM__", img("crm_check.png", "CRM chord and twist against the published table"))
                .replace("__FIXES__", fixes)
                .replace("__DECISIONS__", decisions_html())
                .replace("__BASIS__", basis_counts())
                .replace("__VARS__", variables_table())
                .replace("__SETS__", sets_table(m))
                .replace("__VERIFY__", verification_table())
                .replace("__OPEN__", open_html())
                .replace("__LIMITS__", "\n".join(f"<li>{x}</li>" for x in LIMITS))
                .replace("__ROWS__", rows())
                .replace("__OK__", str(g["ok"])).replace("__BUILT__", str(g["built"]))
                .replace("__SETVER__", f"code {g['versions']}, {g['backend']} loft")
                .replace("__PUBOK__", str(g["pub_ok"])).replace("__PUB__", str(g["pub"]))
                .replace("__TESTS__", TESTS_LINE)
                .replace("__STALE__", (f"built with code {g['versions']}, older than the code: rebuild (<code>build --all</code>)."
                                       if g["stale"] else f"built with the current code, loft backend: {g['backend']}."))
                .replace("__VERSION__", __version__)
                .replace("__N_AIRFOILS__", f"{len(airfoils.available()):,}"))
    out = DOCS / "GEOMETRY_GENERATOR.html"
    page = reorder_sections(page)
    out.write_text(page)
    print(f"{out}  {out.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
