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

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))   # CFD_Automation: the cfdauto package

from cfdauto import __version__  # noqa: E402
from cfdauto.geometry import airfoils, published_wings  # noqa: E402
from cfdauto.geometry.params import VARIABLES, WING_TYPES, load_config  # noqa: E402
from cfdauto.geometry.planform import aspect_ratio, mean_aero_chord  # noqa: E402
from cfdauto.geometry.sections import build_wing_sections  # noqa: E402

DOCS = ROOT / "docs"
SETS = ROOT / "data" / "sets"
TESTS_LINE = "181 pass, 13 skipped (12 need pyGeo, 1 needs gmsh; run 8 Nov 2026)"
CHANGED = "7 Nov 2026"          # the date of the two changes (decisions 64 and 70) this page explains


def _sci(x: float) -> str:
    """1.2 × 10⁵ style (the same as sci below; needed before it is defined)."""
    e = int(f"{x:.1e}".split("e")[1]); m = x / 10 ** e
    return f"{m:.1f} × 10" + str(e).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))


def _sim() -> dict:
    """The similarity numbers (docs/size_extremes.json from scripts/size_extremes.py) used in the hand-written text."""
    d = json.loads((DOCS / "size_extremes.json").read_text())
    if "_meta" not in d:
        raise SystemExit("docs/size_extremes.json is the first-approach file: run scripts/size_extremes.py first")
    return d


SIM = _sim()
LV = SIM["_meta"]["re_levels"]                       # the four Re levels on the mean chord (Stage 0)
F = {t: SIM[f"{t}/focus"] for t in ("bwb", "flying_wing", "cranked", "tapered")}
U = {t: SIM[f"{t}/full"] for t in ("bwb", "flying_wing", "cranked", "tapered")}
TIPW = F["bwb"]["smallest_tip"]                      # the focus BWB with the smallest tip chord

# --------------------------------------------------------------------------------------
# Content written by hand. Keep it short and plain.
# basis: req = your requirement, src = published source or tool, meas = measured here,
#        own = our choice, no source yet.   flag: "fix" (fix before Stage 2), "open" (needs a decision),
#        "chg" (changed on 7 Nov 2026), "gone" (removed on 7 Nov 2026, kept here for the record)
# --------------------------------------------------------------------------------------

MEANING = {
    "aspect_ratio": "aspect ratio = full span² / area = full span in mean chords — sampled",
    "semi_span_m": "semi-span in mean chords — derived: AR / 2",
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
        ("One generator, one YAML", "<code>wing_type</code>: a type (<code>bwb | flying_wing | cranked | tapered</code>), a family (<code>tailless | conventional</code>: its two types) or <code>mixed</code> (all four); shares equal (1/4 each).",
         "One design space and one contract. Equal shares keep a mixed set from leaning to one type (decided 29 Oct 2026).", "req", ""),
        ("Two families, two types each", "Every wing is first <strong>tailless</strong> or <strong>conventional</strong>. A tailless wing must trim itself (reflexed sections, sweep with washout); a conventional wing does not, because the aircraft trims it elsewhere. Tailless: <code>bwb</code> (centre body, strong taper, cranked) or <code>flying_wing</code> (straight edges, moderate taper, swept). Conventional: <code>cranked</code> (constant-chord centre, tapered outer panels) or <code>tapered</code> (straight edges, rectangular at taper 1).",
         "Your rule (31 Oct 2026). The family is an input (from the type or the user): whether the wing must trim itself is a property of the aircraft, so it cannot be measured on the wing. Inside a family our rules decide the type: tailless → bwb when the root chord is at least 2.2 × the outer-half mean chord (and at least half the semi-span), else flying_wing; conventional → cranked when the leading edge or the chord breaks (a kink), else tapered. The rules use ratios, so they work the same at unit mean chord. On the focus training sets of 7 Nov the rules return the drawn type for 100 % of flying-wing, cranked and tapered wings and 85 % of BWB wings (15 slim BWBs read as flying wings; 14 before 7 Nov).", "req", ""),
        ("Span words", "<strong>Full span b</strong> = tip to tip, both halves. <strong>Semi-span S = b / 2</strong> = root to one tip: the half wing we build, mesh and mirror at y = 0. <code>semi_span_m</code> is always S. At unit mean chord b equals the aspect ratio (in mean chords). Every table and figure says which one.",
         "Your rule (31 Oct 2026): never write 'span' without saying which.", "req", ""),
        ("No full-span cap (was: focus ends at b = 7 m)", "None since 7 Nov 2026. At unit mean chord the full span is the aspect ratio, and the aspect ratio has its own range, so the cap went with decision 70. The focus sets keep the same draw: a Latin hypercube of 200 rows, the first 100 kept. So 99 / 90 / 91 / 88 of the 100 focus shapes stay the same (BWB / flying wing / cranked / tapered; the cap had chosen by root chord). <span class='muted'>First approach (31 Oct–6 Nov): <code>focus: max_full_span_m: 7.0</code>; the focus sets kept only wings with full span ≤ 7 m, in draw order.</span>",
         "Your rule (31 Oct 2026) for wings at real size; similarity (6 Nov) made it meaningless. Then: 32 of 34 real wings with an area were in the focus space (Hermes 450, 10.5 m, and Götten UAV 9, 8.7 m, only in the full space). Cost now: a focus set is the first 100 of 200 rows, so its strata are not exactly balanced.", "req", "gone"),
        ("Same 17 variables for every type", "Each type samples some and derives the rest (see <a href='#inputs'>Inputs and derived</a>): 16 sampled for BWB and cranked, 12 for tapered and flying wing. The root chord left the vector on 7 Nov 2026 (decision 70: 18 → 17 names; 17 / 13 sampled before). Its hypercube column is still drawn and dropped, so the same seeds give the same shapes.",
         "One vector shape for sampling, hashing and ML.", "own", "chg"),
        ("Everything varies", "A value is fixed only through <code>pinned:</code>.", "A study may pin; the default never does.", "req", ""),
        ("Size: none, every wing at unit mean chord", "<code>span_mode: aspect_ratio</code> for every type. Every wing is built at <strong>unit mean chord</strong>: mean chord c̄ = area / full span = 1 (the geometric mean chord, not the MAC). So the aspect ratio is sampled, the semi-span is S = AR / 2 and the root chord is 1 / K (K = mean chord / root chord). Lengths are in mean chords. Size enters only through the Re on the mean chord, an input of each solve (the Stage 0 levels). Mach 0.1 with a Prandtl–Glauert correction on CL and CM is on the solver side. <span class='muted'>First approach (29 Oct–6 Nov): the root chord was sampled in metres and S = AR · c<sub>root</sub> · K / 2.</span>",
         "Decided 6 Nov 2026 (you), built 7 Nov 2026 (decision 70). One mesh family per shape then serves every size: about 5 × fewer solves (8,000, not 42,000). Drawing the aspect ratio (not the semi-span) still keeps every wing inside the real range by construction, with no refusals (decided 29 Oct 2026).", "req", "chg"),
        ("Chord law", "<code>stations</code>: c2, c3, c4 as fractions of the root (BWB). <code>per_panel</code>: each panel's own taper, at most 1 (cranked). <code>linear_taper</code>: one taper, c2 and c3 follow (tapered, flying wing).",
         "Before, 46 of 100 conventional wings got wider toward the tip. With per-panel ratios no chord grows outboard, and the Latin hypercube stays intact.", "req", ""),
        ("Sweep law", "<code>panels</code>: one sweep per panel. <code>one</code>: sweep2 = sweep3 = sweep1 (tapered, flying wing).",
         "Straight leading edge for straight-edged wings. Variables a law computes need no range.", "req", ""),
        ("Aspect ratios and the Re range from real wings", "Aspect ratio: BWB 3–9; flying wing 3–13; conventional (cranked, tapered) 4.5–16.5. Since 7 Nov the real wings set only the aspect ratios and the Re range. Real Class I–II wings fly at Re 1.22 × 10⁵ – 3.10 × 10⁶ on the mean chord (area / full span); the levels 1 × 10⁵ – 4 × 10⁶ cover them (1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ since 8 Nov), and 1 × 10⁵ sits 18 % below the slowest real UAV (kept as a margin: you, 7 Nov 2026). The Greek tactical BWBs (LOTUS, Archytas; 8 Nov) cruise at 1.4–3.7 × 10⁶. <span class='muted'>First approach: root chord BWB 0.40–1.80 m; cranked and tapered 0.13–0.75 m; flying wing 0.25–1.05 m.</span>",
         "The aspect ratio has no size, so the real wings still bound it: tailless 2.9–12.4 (ScanEagle), conventional 4.9–16.0. First approach (30 Oct–6 Nov): all 34 real wings with a published area had a generated wing within 10 % in full span and mean chord, and all 112 real full spans were inside. At unit mean chord that check compares real wings with wings of a 1 m mean chord, so it means nothing now (see <a href='#real'>Real wings</a>).", "meas", "chg"),
        ("Cranked differs from tapered", "Cranked focus = constant-chord centre and tapered outer panels: inner chord 0.95–1, middle 0.80–1, outer 0.50–0.85 of the chord inboard; sweep −3–3° inner, −5–10° middle, 0–15° outer. Full space unchanged.",
         "Your remark (30 Oct 2026): the two types looked alike, because the old per-panel ratios (0.85/0.75/0.65–1) made mostly straight-tapered wings with faint breaks. The layout follows Class II UAVs like Hermes 450 and Heron (from photos; no published chord table), so it is our choice.", "own", ""),
        ("Shape ranges from sources", "Every range has its basis in the <a href='#inputs'>Why this range</a> column and in <code>decisions/shape_ranges.md</code>. Changed on 29 Oct 2026: conventional sweep −5° to +15° (was −10° to +20°); conventional washout at most 5° (was 7°); dihedral 0–5° for every type (Raymer); flying-wing taper 0.3–0.9 and sweep 10–40°; BWB tip down to 0.06, first sweep from 15°.",
         "Each range now rests on a design rule (Raymer) or on a published small UAV (BWB: Wang &amp; Zhou 2022, Suewatanakul 2022, Lehmkuehler 2012, Hainline 2017; flying wing: Milenković-Babić 2024, Panknin, PUL-10, a flying-wing MAV). Layout shares (b3, split) remain our choice. BlendedNet is a larger Group 3 BWB and is not used for the ranges.", "src", ""),
        ("Two spaces: full and focus", "Per type, <code>ranges</code> + <code>airfoils</code> = the focus space (realistic, suggested); <code>full_ranges</code> + <code>full_airfoils</code> = the full space (everything supported). The focus box must lie inside the full box, and each suggested section must be a full candidate; the YAML is refused otherwise.",
         "Your rule (30 Oct 2026): design everything, but put the wings and the simulations densely where the real wings are. Full bounds are our choice: the widest value in any source, rounded out (e.g. BlendedNet sweeps 60°, Prandtl-D washout 10°).", "req", ""),
        ("No wing class (was: class I | II)", "None since 7 Nov 2026. A config that still has <code>wing_class</code>, <code>max_full_span_m</code> or <code>floor_m</code> is refused, so an old file cannot be misread. <span class='muted'>First approach: <code>wing_class: I | II</code> set the trailing-edge floor (0.5 mm Class I, 1.0 mm Class II).</span>",
         "A wing without size has no millimetres (decision 70). The trailing edge is now 0.2 % of the local chord on every wing (see Trailing edge).", "req", "gone"),
    ]),
    ("Planform", [
        ("Exact straight panels", "Leading and trailing edges are straight lines through b0–b3. Chords and sweeps equal the vector exactly.",
         "The old AERIS spline put the b2 chord up to 20 % off; a 12°/6°/6° wing came out 7.9°/7.9°/6.5°.", "meas", ""),
        ("Signed sweep", "Leading-edge sweep, positive aft. Forward sweep is allowed by the ranges, not blocked by code.", "Conventional wings need it.", "req", ""),
        ("No curved BWB centre body", "Not in this stage. To add later with a check that rejects wavy edges.",
         "Straight panels first. So today's BWB is a cranked tailless wing with a long root chord.", "own", ""),
    ]),
    ("Sections, twist, dihedral", [
        ("Vertical sections; root in y = 0", "Every section is parallel to the symmetry plane and only twisted about its leading edge. The validity gate refuses a wing whose root leaves y = 0 by more than 1e-9 mean chords (1e-9 m on the real-size wings before 7 Nov), or any point that crosses y = 0.",
         "The two mirrored halves then meet exactly in the root section and never cross. AERIS (and its AVL path) rolled the root section with the first panel's dihedral, so the halves crossed and the root dihedral had to be pinned at zero. pyGeo only receives our section points, never a dihedral angle. Cost: on a panel with dihedral Γ the true thickness is cos Γ smaller (1.5 % at 10°).", "req", ""),
        ("One dihedral per panel", "Inputs <code>dihedral_p1, p2, p3</code>. Station heights: z<sub>i</sub> = Σ tan(Γ<sub>panel</sub>) · f<sub>panel</sub> S (the panel's share of the semi-span).",
         "Four station values gave only three panel slopes, so one input did nothing ([0, 3, 3, 6], [3, 0, 6, 3] and [1.5, 1.5, 4.5, 4.5] built the same wing). The gate now checks each panel dihedral against the vector. Fixed 29 Oct 2026.", "req", ""),
        ("Twist", "Exact at the four stations; between them it follows the straight panel.",
         "Straight panels and linear twist cannot both hold. Difference 0.1–0.3 % of chord at the trailing edge.", "meas", ""),
        ("Aspect ratio exact with twist", "The mean chord K counts the true chord of a straight panel: where the twist changes, the chord turns and is a little shorter mid-panel (0.6 % for a 13° change). K = Σ f<sub>i</sub> ∫ |chord vector| dt, 32-point Gauss. So the built wing has exactly unit mean chord and the aspect ratio asked for.",
         "Found by the full-space sets: with washout up to 12°, 4 wings missed their aspect ratio by 0.11–0.24 % (gate limit 0.1 %). Two causes: K assumed a linear chord, and the extra section at the trailing-edge switch took the linear chord and twist, so it sat off the straight panel. Both fixed 30 Oct 2026 (the switch section went with the floors on 7 Nov). Worst aspect-ratio error on the 722 wings built on 7 Nov: __VS_AR__ %.", "meas", ""),
    ]),
    ("Airfoils", [
        ("Supported vs suggested sections", "Supported: any section in the AERIS database or in <code>Stage_1_geometry/airfoils/</code> that reads and passes the nose gate, or a NACA 4/5-digit formula. Suggested: the per-type list from papers (focus space). The full space draws from every sourced section, on any type.",
         "Your rule (30 Oct 2026). A suggestion must have a source; support needs only a readable file with a round nose.", "req", ""),
        ("Any airfoil by name", "Search order: <code>Stage_1_geometry/airfoils/</code> → AERIS database → NACA 4/5-digit formula. Of the 2,183 files on the search path (2,176 database, 7 local), 2,160 read and 2,146 build (23 are not unit chord; the nose gate refuses 14). A station may list candidates; the sampler draws them evenly. One wing may carry its own four names.",
         "BlendedNet (NACA 25118), M6, RIBES and CRM need sections outside the default list.", "own", "open"),
        ("Default sections", "BWB: MH 104 body (15 %), MH 61 wing (10 %). Cranked and tapered: NACA 4415, 4415, 4412, 4412. Flying wing: MH 60 inboard, MH 45 outboard.",
         "BWB pair from a small BWB UAV (Suewatanakul et al. 2022). The old AERIS MH 91 is a paraglider section and NLF(1)-1015 a HALE section (Re 0.7–2 × 10⁶), so both were dropped. NACA 4415 flies on the Pioneer and the Shadow 200 (Lednicer). MH 45 and MH 60 are Hepperle's tailless sections; MH 60 suits Re ≥ 1.5 × 10⁵ (root), MH 45 lower Re (tip). Changed 29 Oct 2026.", "src", ""),
        ("One way to read every file", "One cubic spline through the raw points (chord-length parameter, natural ends at the trailing edge). Leading edge = the apex of that spline: its point farthest from the trailing-edge midpoint. Both sides are sampled from the same spline on cosine x, <strong>201 points per side</strong> (401 per section); unit chord.",
         "Changed 7 Nov 2026 (decision 64, see <a href='#nose'>Nose study</a>). The old rule put the leading edge at the farthest <em>raw point</em> and resampled each side in √x with a square tangent (PCHIP, 101 points per side). Measured along the arc, that made a curvature spike on one side of the nose and a flat spot on the other, between the raw points, and the built nose failed a 5 % turning-per-cell test on all ten suggested airfoils (NACA 4415: a 0.18 % c nose cell turned 9.47°; the true shape turns 4.31°). The new rule passes on all ten (worst −3.9 %) and on 95.6 % of the database files (old rule 21.0 %).", "meas", "chg"),
        ("Typo points dropped", "A single point that spikes off a smooth line is removed (18 database files, e.g. sc20412 at x/c 0.73). Since 7 Nov this filter runs on the raw points, before the spline.",
         "One bad point would put a bump in the surface. Kept by your decision on 29 Oct 2026; each dropped point is logged.", "req", ""),
        ("Nose gate", "A section is refused when the cubic spline in s = √x that the loft puts through its points curves back harder than −1000/c anywhere within 3 % c of arc from its leading edge, on either side. The refusal names the side, the place and the value.",
         "Added 7 Nov 2026 (decision 64). A nose that folds back would put a tiny loop in the surface. On the database the gate refuses 14 files (very sharp or flat-faced noses; none is used by a config); no other file changes. A round nose is far from the limit: its smallest curvature is +1.9/c to +19.9/c on the ten study airfoils and the 14 named sections.", "meas", "chg"),
    ]),
    ("Trailing edge", [
        ("Thickness rule", "<strong>0.2 % of the local chord on every wing</strong> (decision 70, 7 Nov 2026). <span class='muted'>First approach: Class I max(0.5 mm, 0.2 % c), Class II max(1.0 mm, 0.2 % c). The edges then ran from 0.20 to 4.17 % c, and 370 of the 730 wings had at least one edge set by a floor.</span>",
         "Real wings are blunt. In AERIS, 0.5 % carried about a fifth of the pressure drag; 0.2 % with 8 base cells carried 2–4 %. 0.2 % is also pyGeo's default. A wing without size has no mm floor. Check C3 (CFD, to come): 0.1 / 0.2 / 0.3 % c, and the real floor of small wings, about 0.42 % c.", "meas", "chg"),
        ("Made in the generator", "On the 2-D airfoil, before the loft. Not in the mesher.",
         "AVL, CFD and CAD see one wing. The AERIS mesher made 4.3 mm at one root, 2.4 times the rule, and moved lift 11–30 counts.", "meas", ""),
        ("How it opens", "pyGeo's method: linear ramp from x/c = 0.90 to the edge, half up, half down. Camber line unchanged.",
         "Same as <code>readAirfoilFile(bluntTe=True, bluntThickness=0.002, bluntTaperRange=0.1)</code>. Replaced the uncited 65 % start in v0.4. Cost: a 0.6° slope change at 90 % chord.", "src", ""),
        ("The rule wins over the file", "A file with its own blunt edge is set to the rule (NACA 4415: 0.32 % → rule). Published wings keep theirs (<code>as_is</code>).",
         "Sampled wings follow one rule; copies of real wings stay real.", "own", ""),
        ("No switch section (was: a section at the switch)", "None since 7 Nov 2026. Between two sections the ruled loft blends the chord and the edge gap linearly, so a fraction of the chord holds all along the semi-span, twist or not. <span class='muted'>First approach: where the chord equalled 0.25 m (Class I) or 0.5 m (Class II), a section was added, so the floor held between the stations.</span>",
         "It existed only because of the mm floors.", "own", "gone"),
    ]),
    ("Loft (the surface the mesher reads)", [
        ("Straight panels: kSpan = 2", "Sections only at b0–b3 (no switch sections since 7 Nov 2026).",
         "kSpan 3 cut the corners at panel breaks by up to 4.8 % of chord; kSpan 2 is exact. It leaves a sharp kink at b1 and b2; the Stage 2 surface mesher puts a station exactly on each (fix 3, done).", "meas", ""),
        ("Built with pySpline, one parameter s = √(x/c)", "Same construction as pyGeo's <code>liftingSurface</code>, held in a pyGeo object.",
         "<code>liftingSurface</code> split upper and lower 0.2–0.5 % of chord away from the nose. Here the split is exact and u = x/c on every station.", "meas", ""),
        ("Ask, never interpolate", "The mesher asks <code>upper(u, v)</code> and <code>lower(u, v)</code>; a 401-point table maps v to the position along the semi-span.",
         "In AERIS, straight lines between stored sections missed the surface by up to 7.25 % of chord (ADR-0015).", "meas", ""),
        ("Tip", "Flat and open (<code>tip='none'</code>).", "Rounded tips are a later study.", "own", ""),
        ("Two backends, one export", "pyGeo (production, IGES) and numpy (same surface, no pyGeo). No STEP: pyGeo has no STEP writer.",
         "Tests and pictures run anywhere.", "own", ""),
    ]),
    ("Measure, label, hash", [
        ("Measured on the loft", "Chord, twist, LE position, sweep, dihedral, area, semi-span and full span, MAC, AR, thickness, trailing-edge thickness → <code>measured.json</code>. Lengths in mean chords (a key ending in <code>_m</code> is metres for a 1 m mean chord). The gate checks chords, sweeps, twists, panel dihedrals and the aspect ratio against the vector.",
         "Later stages and any ML model use the measured wing; the vector is only its label.", "req", ""),
        ("Labels by rule", "First the family (from the input) and the type (by the rules above), then shape labels: swept, cranked, rectangular, straight-tapered, washout, dihedral, aspect ratio. BWB threshold 2.2. A value exactly at a threshold gets the label (tolerance 1e-9 on every rule since 8 Nov 2026, decision 79; the aspect ratio 10⁻⁶ relative, above the area error).",
         "Whether the wing must trim itself is a property of the aircraft, so it cannot be measured on the wing; the family comes from the input (the type or the user). Before 29 Oct 2026 every tailless wing without a centre body was called 'conventional'. The tolerance: 35 wings at exactly 1.0° washout had lost the washout label by rounding. Checked on 20 hand-labelled wings and a flying-wing test.", "req", "chg"),
        ("Hash from the code itself", "sha256 of the vector (with its four section names), the type's laws and pinned values (not its ranges), the trailing-edge rule, the airfoil coordinates and the content of every geometry source file.",
         "Any code change changes every input hash, so stored meshes and results are never reused for a wing the code builds differently. A version string set by hand could be forgotten. Fixed 29 Oct 2026. Cost: a pure rename changes every hash too. On 7 Nov 2026 every hash changed again (similarity and the nose rule); the sets were rebuilt with the numpy loft, and on 8 Nov with pyGeo on your machine (722 of 722, the same input hashes). Stage 2 mesh names carry the wing hash (<code>mesh_&lt;level&gt;_&lt;wing_hash8&gt;_re&lt;Re&gt;</code>).", "req", ""),
    ]),
    ("Sets", [
        ("Seven sets per type, two spaces", "Focus: training 100 (a Latin hypercube of 200 rows, the first 100 kept; seeds 1001–1004), reference 5 (by rule), hold-out 10 (20 rows, the first 10 kept; seeds 2001–2004). Full: training 40 (seeds 1101–1104), hold-out 5 (seeds 2101–2104), corner 1 (each free variable at each full bound: 32 or 24 wings; 34 or 26 before 7 Nov, when the root chord had its two corners) and corner 2 (every pair at all four low/high combinations: 8 or 7). Files: <code>training_focus</code>, <code>reference</code>, <code>holdout_focus</code>, <code>training_full</code>, <code>holdout_full</code>, <code>corner1</code>, <code>corner2</code>.",
         "Dense where real wings are, sparse over everything we support; the corners test the edges of what we claim. The hold-outs are the honest tests. Decided 30 Oct 2026. On 7 Nov training_full, holdout_full and corner 2 kept their shapes.", "req", "chg"),
        ("Failures stay in the list", "A refused wing keeps its row with the gate and the reason. Corners are never nudged inside.",
         "A failure marks the edge of the space.", "req", ""),
        ("Hold-out is never built here", "Only the vectors are saved.", "It is opened once, after the workflow is frozen.", "req", ""),
        ("Reference wings spread well", "Rules: mid-range; lowest and highest aspect ratio (before 7 Nov: smallest and largest area; at unit mean chord the area is the aspect ratio); most sweep with the smallest tip (in mean chords); strongest washout. __REFCOV__",
         "Five wings must stand for the whole set. On 7 Nov 13 of the 20 reference wings became new picks; 7 are kept (the 4 mid-range wings and 3 of the 4 strongest-washout wings; the new BWB washout pick was the old smallest-area pick).", "meas", "chg"),
    ]),
]

FIXES = [
    ("Done (7 Nov 2026): the nose shape of the built sections (decision 64).",
     "Measured along the arc with one curvature method, the old rule made a curvature spike on one side of the nose and a flat spot on the other, and the built nose failed the 5 % turning-per-cell test on all ten suggested airfoils. The new rule (leading edge at the apex of one cubic spline, both sides from that spline, 201 points per side) passes on all ten and on 95.6 % of the database; a nose gate refuses the 14 files whose nose folds back. See <a href='#nose'>Nose study</a>.",
     "nothing left for the nose. The pyGeo <code>build --all</code> ran on your machine on 8 Nov: 722 of 722 (the manifests now say pygeo)."),
]

OPEN = [  # (group, title, text, kind)  kind: decide = needs your call; act = a task, no choice left
    ("Study plan (Stage 0)", "Re levels", "Changed (you, 8 Nov 2026): 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ on the mean chord (area / full span; were 1.5 × 10⁶ and 3 × 10⁶). 4 × 10⁶ takes in every cruise point of the Greek tactical programmes (LOTUS, Archytas, ACTUS); 1 × 10⁶ fills the old ×5 gap (check C4 on 2-D data, <a href='#greek'>below</a>). Same four levels and 8,000 solves. Real Class I–II wings fly at 1.22 × 10⁵ – 3.10 × 10⁶; the lowest level sits 18 % below the slowest real UAV: a margin (7 Nov). Still to run: check C4 with the solver.", "act"),
    ("Flow conditions", "Transition and solver split", "Decided (4 Nov 2026): transition must be captured, with ADflow and SU2. Our ADflow build has SA only and no transition model, so transition comes from SU2 (SST + LM γ-Reθ). Proposal, pending: ADflow SA for all mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings first. The flow dataset (<a href='#flowdata'>Flow dataset</a>, first approach) puts the SA profile-drag error at a median __FD_MED__ over all focus wings and conditions, __FD_LF__ in level flight, within ±10 % in only __FD_OK__ of rows; below Re 10⁵ it changes sign. Logic check (1 Nov 2026): what a mesh must resolve depends on the model, so an SA mesh study alone does not qualify the mesh for γ-Reθ: build the mesh transition-ready from the start and repeat a reduced mesh study with γ-Reθ. Fix the SA inflow eddy viscosity (ν̃/ν about 3, Spalart &amp; Rumsey 2007); with a low value SA shows an uncontrolled apparent transition (Crivellini &amp; D'Alessandro 2014). First SU2 smoke test (4 Nov): SU2 ran SA and LM on one Stage 2 ring mesh (a section extruded between two symmetry planes, 97,920 cells, Re 3 × 10⁵, Mach 0.15, 4°); after about 370 iterations, not converged: SA CL 0.860, CD 0.0184; LM CL 0.908, CD 0.0137. It shows the mesh path works; no wing has been run.", "decide"),
    ("Flow conditions", "Mach cap", "The Mach scope extends toward 0.5, with no supersonic flow (decided 4 Nov 2026); the cap is open. Under similarity the CFD runs at Mach 0.1 with a Prandtl–Glauert correction (check C2: Mach 0.05 / 0.1 / 0.2; if it fails, Mach becomes an input). The section tables and the flow dataset stop at Mach 0.2. Recommendation (pending): core data at Mach ≤ 0.2 now, Mach 0.3–0.5 later; at Mach 0.5 the angles would be capped near 4° by a supersonic-pocket gate.", "decide"),
    ("Flow conditions", "Fast-UAV family", "Proposal, pending: Mach 0.3–0.5 needs a fast-UAV family in Stage 1, with real fast UAVs, thinner sections and section tables up to Mach 0.5. Today fast wings such as the Vindicator and the CPJ 100-LE are left out as 'outside phase 1'.", "decide"),
    ("Flow conditions", "Data for the new angle range", "Angles now run from −5° to post-stall, plus a separate post-stall study (decided 6 Nov 2026; Stage 0 had 0 / 4 / 8° plus 12° for the nose and wake studies). Missing here: the flow dataset covers root angles 0–10°; the section tables reach −10° and stop at 14°, so stall is never reached.", "act"),
    ("Flow conditions", "Transition bands at the Re levels", "Decided (you, 7 Nov 2026; Stage 2 decision 74, option A): the lower band runs 0–100 % c. It costs no cells (one node list for both sides). The refine map at the four Re levels (7 Nov) finds it holds every strip at every level from −5° to 8°. New finding: at low Re the upper transition sits past 85 % c (at Re 10⁵ only 0–31 % of the strips fit 0–85 % c; at −5° the median is 88–100 % c). The built mesh already has about band-size cells to 100 % c on both sides (at F within 0.2 % of the band cell). Writing the upper band as 0–100 % c gives the same mesh at VC and 2 more ring nodes on 42 of the 80 reference builds at F (+0.4 % cells, median): decided by you on 8 Nov, built and screened (Stage 2 Study 12).", "done"),
    ("Flow conditions", "Volume mesh topology", "Proposal, pending: one matched C-H multiblock mesh for both solvers instead of the overset wake box, vortex tube, overlap and background boxes, because SU2 has no overset. The wake band is sized for the whole angle range, the outboard blocks must resolve the tip vortex, and the far field stays at 80 c. Rough cost: the C-H wake lines add about +45 % (30–60 %) cells on the wing blocks (not measured).", "decide"),
    ("Flow maps", "Sweep and aspect ratio stay in every set", "The 2-D strips do not use sweep or aspect ratio, so the sensitivity study cannot rank them; their low scores mean 'not modelled'. Keep both fully sampled in every CFD and ML set, and justify similarity scaling by dimensional analysis, not by the sensitivity result.", "act"),
    ("Flow maps", "The SA rule", "The tool proposes SA when fully turbulent SA changes the profile drag by under 10 %, the upper surface turns turbulent near the nose (mean laminar run under 20 % chord; a small drag error with a long laminar run is a coincidence of two different flows) and no strip is below Re 10⁵. Both thresholds are our choice. Tie the first to the drag budget instead (the error in counts)?", "decide"),
    ("Flow maps", "N<sub>crit</sub> of the tool", "Default 9 (quiet air, as in flight at altitude). Low-level flight in gusty air is nearer 5–7; the check shows N<sub>crit</sub> 5 changes the SA error by __FD_N5__ points. Keep 9 and show 5 as a band? Similarity (decided 6 Nov, built 7 Nov) fixes Tu 0.07 % (N<sub>crit</sub> 9) for the CFD.", "decide"),
    ("Flow maps", "Level-flight band", "First approach only: a grid point counted as level flight when its wing loading was within × / ÷ 2 of the fit to 37 real wings of the same full span (35 of them are). At unit mean chord a wing has no full span in metres and no wing loading. Drop the flag, or keep it only with a real size given per case?", "decide"),
    ("Flow maps", "Flow dataset in similarity form", "The Stage 1 flow dataset was made at real size and real speed (first approach, 30 Oct–2 Nov) and is not rebuilt. In similarity form each shape would run at the four Re levels on the mean chord, not at speeds and altitudes. Redo it at the Re levels, or let the 3-D CFD data replace it?", "decide"),
    ("Flow maps", "Checks of the flow results", "Mike, 2 Nov 2026: no check is needed before the mesh stage; the mesh rules come from ranges, which the checks would not move. Since then the ranges have moved (angles −5° to post-stall, Mach toward 0.5: see Flow conditions). Needed before the paper quotes flow numbers: SU2 SST + LM runs (proposal, pending: on about 20 % of the wings first, BWB centre body first), the first runs of the mesh stage; so far only a smoke test on one ring mesh has run (see Transition and solver split). Only if the paper states SA's error as a number: 2-D SA against tripped XFOIL at Re 10⁵, 3 × 10⁵ and 1.5 × 10⁶ (about 1 day). Optional: retry the failed XFOIL points, a hinge-line case, a vortex-lattice spanwise loading, a source for the crossflow threshold, E387 against wind-tunnel data.", "act"),
    ("Flow maps", "Raw XFOIL data", "Push the raw XFOIL data to GitHub (2,408 sweeps, 14.2 MB, 1.5 MB as tar.gz), or accept the 40-minute rebuild of the section tables. Still open. The section tables were rebuilt on the fixed nose on 7 Nov.", "act"),
    ("Study plan (Stage 0)", "Grid share 65 %", "Of the 3-count drag budget, 65 % goes to the mesh. Keep?", "decide"),
    ("Study plan (Stage 0)", "Iterative error", "≤ 10 % of the budget is loose; Eça &amp; Hoekstra ask 0.1–1 %. Tighten to 1 %?", "decide"),
    ("Study plan (Stage 0)", "Pitching-moment tolerance 0.002", "Our choice, no source. Keep?", "decide"),
    ("Study plan (Stage 0)", "Turbulence-model source", "Crivellini 2014 is weak support. Find a better source or call it our choice.", "decide"),
    ("Study plan (Stage 0)", "Stage 0 D5", "The Grand Roadmap lists a D5 (prior work, transition route, tunnel, cloud budget). Add it? Its transition route is now partly decided: transition must be captured (4 Nov 2026).", "decide"),
    ("Geometry", "Similarity checks C1–C4", "Similarity is built (7 Nov). Its four CFD checks are still to run: C1 scale (mean chord 0.3 m against 1 m), C2 Mach (0.05 / 0.1 / 0.2; CL and CM after Prandtl–Glauert), C3 trailing edge (0.1 / 0.2 / 0.3 % c and the real floor 0.42 % c), C4 Re levels (interpolation; done on 2-D data on 8 Nov, which added 1 × 10⁶). Limits: Re does not carry roughness or air turbulence; small real wings have thicker trailing edges.", "act"),
    ("Geometry", "Full-space edges", "At unit mean chord the full space reaches aspect ratio 20 and root chords up to " + f"{U['bwb']['root_chord'][1]:.2f}" + " mean chords (a BWB corner), so at the top level the local Re reaches " + _sci(U['bwb']['re_root_max']) + " at that root; at the lowest level the smallest tip (" + f"{U['bwb']['tip_chord'][0]:.3f}" + " mean chords) runs at " + _sci(U['bwb']['re_tip_min']) + ". The section tables cover 1.5 × 10⁴ – 6 × 10⁶. Keep, or narrow the full chord ratios?", "decide"),
    ("Geometry", "Airfoil search order", "Project folder → AERIS database → NACA formula; of 2,183 files, 23 cannot be read (not unit chord) and the nose gate refuses 14. Keep?", "decide"),
    ("Geometry", "pyGeo run", "The nose is decided (64) and similarity is built (70). Every geometry hash changed on 7 Nov, and the sets were rebuilt with the numpy loft (722 of 722 built). pyGeo run on your machine (8 Nov): pyGeo tests 24 of 24 (pyGeo and the numpy loft agree within 10⁻⁶ chord on the 7 published wings), Stage 1 tests 204 (1 skipped), <code>build --all</code> with pyGeo 722 of 722, with the same input hashes and pass/fail as the numpy loft (the manifests now say pygeo); the Stage 2 meshes of the 20 reference wings on pyGeo equal the numpy ones (VC, old levels: every check value within 6 × 10⁻¹⁰; new levels, VC and F: the same ring nodes and stations, 80 of 80 each). One label differed: BWB corner1 #8 was cranked with pyGeo only (its sweep changes by exactly 5°, the kink threshold). Fixed on 8 Nov (decision 79): every input hash changed, the surfaces did not, so one more pyGeo <code>build --all</code> is owed. Without pyGeo, here: __TESTS__. Stage 2 has screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (every set at VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels), and on 8 Nov every set at every level: 3,128 of 3,128, with no nose repair (one factor per family, Stage 2 decision 80), with the numpy loft.", "act"),
    ("Sources", "Second-hand values", "Raymer's taper 0.4, washout 3° and 0° c/4 sweep come from a course page; PUL-10 and the flying-wing MAV were read by the agent only. Check in print.", "act"),
    ("Sources", "AUTh BWB papers", "Airfoils and station chords of their BWBs are in paywalled papers (AST 2018, AST 2021, AIAA 2020/2022, ICUAS 2020). Patras library or the authors.", "act"),
    ("Sources", "Essari 2015 data", "Hermes 450, Ranger, Seeker, Shadow 600 areas cite unread Jane's-style data; the Hermes 450 entry is inconsistent. Confirm with Jane's.", "act"),
    ("Sources", "Database rows (NTNU, CNAS)", "Added 31 Oct 2026: 7 NTNU rows with an aspect ratio (set ranges) and 45 rows with only a full span. Families (tailless or conventional) are from photos; aspect ratios and speeds are as the databases list them. Some look wrong (RQ-7A cruise 58 m/s; Aludra MK1 chord). Check the rows you will quote.", "act"),
    ("Sources", "Tailless Class II areas", "Fury, Albatroz, Shahed 191 list only a full span; the RX-3 is the one tailless Class II with an area.", "act"),
    ("Published wings", "BlendedNet twist and dihedral", "Set to zero because neither paper states them. Accept?", "decide"),
    ("Published wings", "Which published wing first", "RIBES is the only in-regime case, and it is tripped at 1.4 % chord, so it checks fully turbulent RANS only: no published case here checks transition (candidate: the E387 wind-tunnel data). M6 and CRM are transonic, and the scope has no supersonic flow (decided 4 Nov 2026): shape and mesh checks only.", "decide"),
    ("Published wings", "NASA CRM", "Four stations and stand-in sections: a shape check only, or add a many-station mode? With no supersonic flow in the scope it cannot be a validation case.", "decide"),
    ("Published wings", "RIBES trailing edge", "Fitted section 0.26 %, model 0.38–0.66 %. Rebuild before any drag comparison?", "decide"),
    ("Published wings", "Outside proof", "Only the M6 is checked against its own CAD (needs gmsh; last run 2 Nov, before the two changes). BlendedNet, CRM, RIBES need their surface files; NACA 25118 edge needs a BlendedNet STEP.", "act"),
    ("Study plan (Stage 0)", "Code-to-code checks", "BlendedNet / BlendedNet++ (FUN3D, SA, fully turbulent, Group 3 BWB, mesh error up to 5 % CL / 8 % CD) and SHIFT-Wing (transonic, CRM-based) are surrogate datasets, not verification data. Use BlendedNet++ only for a few same-model (SA) code-to-code points inside our full space; verify our own meshes by grid convergence (GCI) and NASA TMR cases.", "act"),
    ("Paper", "Closest prior work", "Pliakos et al. 2025 (AUTh) automate OpenVSP → ANSA → Fluent for UAV wings (2 panels, M6 only, no transition). State what we add: 4 stations / 3 panels, full and focus spaces, refusing gates, Re bands with a transition check, open tools, similarity (one mesh family per shape), and a nose that follows the airfoil file at mesh scale.", "decide"),
]

LIMITS = [
    "<strong>Straight edges only, three panels at most.</strong> No curved BWB centre body, no elliptic planform, no fourth panel.",
    "<strong>Airfoil shape is not a variable.</strong> Any named file can be used, and a station can draw from a list, but thickness and camber are not sampled continuously. The default sets use one section per station (t/c 10–15 %).",
    "<strong>No winglets, rounded or raked tips, fuselage, gaps.</strong> Panel dihedral: focus 0–5°, full ±10°.",
    "<strong>Some shape sources are thin.</strong> The layout shares (where b1 and b2 sit) are our choice. A few rules are second-hand (Raymer via a course page). BWB shapes rest on four small-UAV papers, two of them larger than Class I.",
    "<strong>Similarity has limits.</strong> The Re on the mean chord carries the size, but not the roughness or the air turbulence (Tu 0.07 % is fixed), and small real wings have thicker trailing edges (about 0.42 % c) than the 0.2 % c rule. Checks C1–C4 (CFD) are still to run.",
    "<strong>Class II areas are uncertain.</strong> Most rest on Götten et al. (from photos, about 10–15 %) and a thesis citing unread Jane's-style data. The AUTh RX-3 is the only tailless Class II wing with an area (4.9 m²), and its full span is derived (√(AR · S)). Since 7 Nov they set only aspect ratios and the Re range.",
    "<strong>0 refusals at the corners</strong> here: 722 of 722 wings built on 7 Nov. The Stage 2 surface mesher passed 790 of 790 builds on the first-approach wings (real size, before 7 Nov); its lowest quad quality (scaled Jacobian 0.09, limit 0.05) was on corner wings with a very narrow first panel (4–6 mm at real size) and a trailing edge swept about 85°. Since 7 Nov it has screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (every set at VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels, again on 8 Nov at the new Re levels; 4 F builds after one nose repair); lofts it has never seen (the hold-outs; primer Track 5) are still untested.",
    "<strong>Published wings:</strong> M6 and CRM are transonic, and the scope has no supersonic flow (it extends toward Mach 0.5; decided 4 Nov 2026), so they are shape and mesh checks only. RIBES is tripped at 1.4 % chord, so no published case here checks transition (candidate: the E387 wind-tunnel data). CRM is approximate. BlendedNet twist and dihedral are guessed as zero. Every tip is a flat cut, including the M6's rounded one. Like every wing, the copies are built at unit mean chord (<code>real_mean_chord_m</code> scales back).",
    "<strong>Nose.</strong> The nose gate refuses 14 database files (very sharp or flat-faced noses; none is used): they would need more section points near the leading edge. On coarse files (about 61 points) the raw file itself does not settle the nose turning at the smallest cells better than about ±15 % (cubic against quintic spline). One file (nm26-3smoothed) has note lines that the reader takes as points.",
    "<strong>The flow data are first approach.</strong> The flow maps and the flow dataset were made at real size and speed before 7 Nov and are not rebuilt; the section tables are size-free and were rebuilt on the fixed nose on 7 Nov (no conclusion changes).",
    "<strong>No fast-UAV family yet.</strong> Mach 0.3–0.5 needs real fast UAVs, thinner sections and section tables up to Mach 0.5 (proposal, pending); the data here stop at Mach 0.2.",
]

BASIS = {"req": ("Your rule", "req"), "src": ("Source", "src"), "meas": ("Measured", "meas"), "own": ("Our choice", "own")}
FLAG = {"fix": "Fix", "open": "Open", "chg": "Changed 7 Nov", "gone": "Gone 7 Nov"}


# --------------------------------------------------------------------------------------
# Tables built from the repo
# --------------------------------------------------------------------------------------

def img(name: str, alt: str) -> str:
    data = base64.b64encode((DOCS / name).read_bytes()).decode()
    mime = "image/gif" if name.endswith(".gif") else "image/png"
    return f'<img src="data:{mime};base64,{data}" alt="{html.escape(alt)}">'


def fmex_caption() -> str:
    f = DOCS / "flowmap_example.json"
    if not f.is_file():
        return "BWB mid wing at 25 m/s, 1,000 m, 3°."
    fm = json.loads(f.read_text())
    re_ = [r["re"] for r in fm["strips"]]
    xt = [r["xtr_upper"] for r in fm["strips"] if r.get("xtr_upper") is not None]
    b = fm["model"]["sa_drag_bias"]
    lf = fm.get("level_flight") or {}
    return (f"BWB mid wing at {fm['conditions']['speed_m_s']:.0f} m/s, {fm['conditions']['altitude_m']:,.0f} m, "
            f"{fm['conditions']['alpha_deg']:g}°. The root runs at {max(re_) / min(re_):.1f} × the tip Re; the upper surface turns "
            f"turbulent at {100 * min(xt):.0f}–{100 * max(xt):.0f} % chord, later toward the tip as Re falls. Fully turbulent SA would "
            f"raise the profile drag by {100 * b:+.0f} %: the tool proposes: {fm['model']['category']}. "
            + (f"Level flight here carries {lf['wing_loading_n_m2']:.0f} N/m² ({'within' if lf['ok'] else 'outside'} the real band "
               f"{lf['real_band_n_m2'][0]:.0f}–{lf['real_band_n_m2'][1]:.0f} N/m² for its full span)." if lf else ""))


def img_opt(name: str, alt: str) -> str:
    return img(name, alt) if (DOCS / name).is_file() else f"<p class='muted'>({name} not built yet)</p>"


def chg(text: str, tag: str = f"What changes ({CHANGED})") -> str:
    """An amber box: what the two changes of 7 Nov 2026 (similarity, decision 70; the nose, decision 64) change here."""
    return f'<div class="cbox chg"><span class="ctag">{tag}</span>{text}</div>'


FA = '<span class="fa">First approach · real size and real speed, before 7 Nov 2026 · not rebuilt</span>'
FA_TAB = '<span class="fa">Built before 7 Nov 2026 · size-free · old nose (tables rebuilt 7 Nov: same conclusions)</span>'


def fd_rows() -> str:
    f = DOCS / "flow_analysis.json"
    return f"{json.loads(f.read_text())['rows']:,}" if f.is_file() else "about 200,000"


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
        for s in ("training_focus", "training_full", "corner1", "corner2", "reference", "holdout_focus", "holdout_full"):
            f = SETS / t / f"{s}_manifest.json"
            if f.is_file():
                d = json.loads(f.read_text())
                rows.append({"type": t, "set": s, "version": d.get("code_version", "?"), "code_hash": d.get("code_hash"),
                             "backend": d.get("loft_backend", "?"), "wings": d["wings"]})
    return rows


TYPE_NAME = {"bwb": "BWB", "cranked": "Cranked", "tapered": "Tapered", "flying_wing": "Flying wing"}
SET_NAME = {"training_focus": "training (focus)", "training_full": "training (full)", "corner1": "corner 1 (full)",
            "corner2": "corner 2 (full)", "reference": "reference (focus)", "holdout_focus": "hold-out (focus)",
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
            lab = Counter(l for x in w for l in (x.get("labels") or [])[1:2])   # the type the rules give
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
        cad_s = (f"max {cad['max_pct_chord']:.4f}" if cad else
                 "<span class='muted'>not run here (gmsh not installed); 2 Nov run, first approach: max 0.0113</span>"
                 if r.get("cad_note") else "no outside file")
        out.append(f"<tr><td><code>{r['wing']}</code></td><td class='num'>{r['sections_max_pct']:.4f}</td>"
                   f"<td class='num'>{r['edges_max_pct']:.0e}</td><td class='num'>{cad_s}</td>"
                   f"<td>{'<span class=\"flag ok\">pass</span>' if r['pass'] else '<span class=\"flag fix\">fail</span>'}</td></tr>")
    return "\n".join(out)


def real_table() -> tuple[str, dict]:
    """Rows of the real-UAV table and its summary, from docs/real_uavs.json."""
    d = json.loads((DOCS / "real_uavs.json").read_text())
    fam = {"tailless": "Tailless", "conventional": "Conventional", "delta": "Delta"}
    use = {"ranges": "<span class='flag ok'>sets AR, Re</span>", "span": "<span class='muted'>full span only</span>",
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
         "secondary": "secondary", "model": "model", "measured_drawing": "drawing", "hcdi_db": "HCDI db", "database": "UAV database (NTNU, CNAS)"}


def stype_counts(rows: list[dict]) -> str:
    """How many range-setting wings rest on each kind of source."""
    c = Counter(r.get("stype") for r in rows if r["use"] == "ranges")
    return ", ".join(f"{STYPE.get(k, k)} {v}" for k, v in c.most_common())


def cover_text() -> str:
    rows = [r for r in json.loads((DOCS / "real_uavs.json").read_text())["rows"] if r["use"] == "ranges"]
    miss = [r["name"] for r in rows if not r.get("covered")]
    full = sum(1 for r in rows if r.get("covered_full"))
    return (f"focus {len(rows) - len(miss)} of {len(rows)}, full {full} of {len(rows)} real wings"
            + (f" (only in the full space: {', '.join(miss)})" if miss else ""))


def hcdi_cell(h: dict | None) -> str:
    """Class, MTOW, payload and span of the same aircraft in the HCDI UAS database."""
    if not h:
        return "—"
    parts = [f"Class {h['class']}"]
    parts += [f"{w} {h[k]:g}{u}" for k, w, u in (("mtow", "mtow", " kg"), ("payload", "payload", " kg pl"), ("span", "full span", " m")) if h.get(k)]
    return "<br>".join(parts)


def hcdi_table(d: dict) -> str:
    fam = {"tailless": "Tailless", "conventional": "Conventional"}
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
     "Every type. Re on the mean chord: the four levels 1 × 10⁵ – 4 × 10⁶ (since 8 Nov), an input of each solve since 7 Nov (real Class I–II wings fly at 1.22 × 10⁵ – 3.10 × 10⁶). Our low-Re sections (MH 45, MH 60, MH 61, MH 104) are designed for long laminar runs. First approach (real size and speed): 5.4 × 10⁴ – 3.5 × 10⁶ on the mean chord (focus).",
     "Drag and lift depend on where the boundary layer turns turbulent. A bubble adds drag; at high angle it can burst, giving abrupt stall and hysteresis. Small changes in turbulence or roughness move the result.",
     "ADflow SA: no. Spalart–Allmaras without transition makes the wall flow turbulent from the nose. In 2-D (XFOIL, 2°) that raises profile drag by 39–128 % (median 81 %) at Re ≥ 3 × 10⁵ (7 Nov, new sections). Carried as a model band (Stage 0). Transition must be captured too (decided 4 Nov 2026): our ADflow build has SA only, so it comes from SU2 (SST + LM γ-Reθ).",
     "Carmichael 1981 (NASA CR-165803); Lissaman 1983 (Annu. Rev. Fluid Mech. 15); Mueller & DeLaurier 2003 (Annu. Rev. Fluid Mech. 35); our XFOIL runs (Drela 1989)"),
    ("Very low Re at the tips",
     f"At the lowest level (1 × 10⁵ on the mean chord): the smallest BWB tip, {F['bwb']['tip_chord'][0]:.3f} mean chords (focus; {U['bwb']['tip_chord'][0]:.3f} full), runs at {_sci(F['bwb']['re_tip_min'])} ({_sci(U['bwb']['re_tip_min'])}); flying-wing, cranked and tapered tips ({F['flying_wing']['tip_chord'][0]:.2f}, {F['cranked']['tip_chord'][0]:.2f} and {F['tapered']['tip_chord'][0]:.2f} mean chords) at about {_sci(F['cranked']['re_tip_min'])} – {_sci(F['tapered']['re_tip_min'])}. First approach: BWB tips from 2.4 cm, tip Re down to about 1.4 × 10⁴.",
     "Thick laminar boundary layers and early separation at the tip, where the vortex forms.",
     "Weakly. Same model limit as above, at its worst. The first wall cell barely changes along the semi-span (Re and chord change together), but the thicker root boundary layer needs more wall layers.",
     "Same as above; first-cell law: Grand Roadmap R-V.1"),
    ("Wake behind the trailing edge",
     "Every wing, along the whole trailing edge. At high angle the wake leaves the edge at an angle (angles now run to post-stall); behind a blunt base it starts wide.",
     "A thin sheet of slow air: the boundary layers of both surfaces leave the edge and carry the profile drag downstream. It sets the pressure at the trailing edge and base, and it rolls up toward the tips.",
     "Only if the wake has its own cells. The S8 O-mesh has none: its cells grow fast behind the edge, so the wake smears. In AERIS, refining the near wake alone moved base drag by 23 counts. Plan (proposal, pending): one matched C-H mesh for both solvers (SU2 has no overset), with wake cells sized for the whole angle range.",
     "Primer section 05; Chan et al. 2002"),
    ("Tip vortex, roll-up and induced drag",
     "Every wing; strongest at low aspect ratio (BWB down to AR 3 in the focus space, 2.5 in the full space) and high lift.",
     "The wake sheet rolls up into one vortex per tip within about one chord. It causes the downwash and the induced drag, a large share of the total.",
     "Yes, if the vortex keeps fine cells along its path. Plan (proposal, pending): with one C-H mesh there is no separate vortex tube; the outboard blocks must resolve the vortex.",
     "Primer section 05"),
    ("Sweep: spanwise flow, tip or root stall, pitch-up",
     "BWB 5–40° and flying wing 10–40° (aft); cranked and tapered −5° to +15° (forward to aft).",
     "Aft sweep pushes the boundary layer outboard, so the tip stalls first and the nose can pitch up. Forward sweep stalls the root first.",
     "Spanwise flow: yes. Stall onset and pitch-up: less reliable with steady RANS near maximum lift; the post-stall part gets its own study (decided 6 Nov 2026).",
     "Standard swept-wing aerodynamics"),
    ("Panel breaks (kinks) at b1 and b2",
     "Every BWB and cranked wing; tapered and flying wings have no break in the edges.",
     "Local suction peaks and a jump in the spanwise loading at the break; a ruled loft has a slope break there.",
     "Yes: the Stage 2 surface mesher puts a station on every loft station, so one sits exactly on each break (fix 3, done). Without it, flat faces would cut the corner.",
     "Loft decision (kSpan 2)"),
    ("Separation and stall at high angle",
     "High angles up to post-stall (now in scope: −5° to post-stall, decided 6 Nov 2026); already at 8° on thin or strongly cambered sections at low Re.",
     "Trailing-edge or leading-edge separation, unsteady flow, maximum lift.",
     "Steady RANS gives a number but is not reliable near maximum lift; convergence is harder. The post-stall part gets its own study (URANS or DDES on a few wings).",
     "Stage 0 angles 0 / 4 / 8 / 12°; owner decision 6 Nov 2026 (−5° to post-stall)"),
    ("Blunt trailing edge: base flow",
     "Every wing: 0.2 % of the local chord (since 7 Nov 2026; first approach: max(0.5 mm, 0.2 % c) for Class I). Check C3 (CFD, to come): 0.1 / 0.2 / 0.3 % c and the thicker edges of small real wings, about 0.42 % c.",
     "A base pressure drag and, in reality, vortex shedding behind the base.",
     "Partly. Steady RANS damps the shedding. At 0.2 % with 8 cells the base was 2–4 % of pressure drag (measured in AERIS).",
     "Primer section 03; Papadakis & Manolesos 2020 (flatback, RANS damps shedding)"),
    ("Low Mach number",
     "Under similarity the CFD runs at Mach 0.1, with a Prandtl–Glauert correction on CL and CM (check C2: 0.05 / 0.1 / 0.2). First approach: top speed 67 m/s, Mach ≤ 0.20 (tailless ≤ 0.13). Scope since 4 Nov 2026: Mach extends toward 0.5, with no supersonic flow; the data on this page stop at 0.2.",
     "The air is nearly incompressible at these speeds.",
     "The compressible solver needs low-speed preconditioning; without it ADflow did not converge in AERIS.",
     "Primer track 3"),
    ("Slender, flexible wings",
     "Cranked and tapered aspect ratio up to 16.5.",
     "Long thin wings bend and twist in flight, which changes the spanwise loading.",
     "No. The CFD wing is rigid. Many spanwise stations are needed.",
     "Outside this study (no aeroelasticity)"),
]


SUMMARY_TEXT = {
    "what": {"bwb": "Long centre body, strong taper, cranked", "cranked": "Constant-chord centre, tapered outer panels",
             "tapered": "Straight edges root to tip (rectangular at taper 1)", "flying_wing": "Straight edges, moderate taper, swept"},
    "flow": {"bwb": "Two regimes on one wing (centre body 5–17× the tip Re); spanwise flow and tip stall from sweep; kinks at b1, b2; thick 15 % centre body",
             "cranked": "Kinks at the breaks (suction peaks, loading jump); low sweep; at the lowest level (10⁵ on the mean chord) the outer panels run below 10⁵",
             "tapered": "Smooth loading; low sweep; tips at lower Re as taper grows; tip vortex weaker at high AR",
             "flying_wing": "Trim by sweep and washout with reflexed sections; spanwise flow; tip stalls first at high angle"},
    "mesh": {"bwb": "LE and TE everywhere; a station on each kink; tip; wake and tip vortex; one first cell (the smallest chord sets it), more wall layers at the centre body",
             "cranked": "LE and TE; a station on each break; tip vortex; wake",
             "tapered": "LE and TE; tip vortex; wake",
             "flying_wing": "LE and TE; tip (stall, vortex); wake behind a swept TE"},
}


def summary_html() -> str:
    """One table: final ranges and flows per type (focus bold, full grey), at unit mean chord (decision 70)."""
    cfg = load_config()
    f = lambda x: f"{x:g}".replace("-", "−")  # noqa: E731

    def r(lo, hi, unit=""):
        return (f"{f(lo)} to {f(hi)}" if min(lo, hi) < 0 else f"{f(lo)}–{f(hi)}") + unit

    def both(fn):
        return [f"<strong>{fn(cfg.types[t], 'focus')}</strong><br><span class='fullr'>full {fn(cfg.full[t], 'full')}</span>"
                for t in WING_TYPES]

    def taper(sp, space):
        """The tip / root range the inputs allow (cranked: the product of the three panel ratios)."""
        if sp.chord_law == "per_panel":
            lo = hi = 1.0
            for v in ("c2_ratio", "c3_ratio", "c4_ratio"):
                lo, hi = lo * sp.ranges[v][0], hi * sp.ranges[v][1]
        else:
            lo, hi = sp.ranges["c4_ratio"]
        return r(round(lo, 2), round(hi, 2))

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

    def chord(key):
        c = lambda x: f"{x:.3f}" if x < 1 else f"{x:.2f}"  # noqa: E731
        return lambda sp, space: "–".join(c(x) for x in SIM[f"{sp.name}/{space}"][key])

    def local_re(sp, space):
        e = SIM[f"{sp.name}/{space}"]
        return f"{sci(e['re_tip_min'])} · {sci(e['re_root_max'])}"

    rows = [
        ("Shape", [SUMMARY_TEXT["what"][t] for t in WING_TYPES]),
        ("Aspect ratio = full span b (in mean chords)", both(lambda sp, s_: r(*sp.ranges["aspect_ratio"]))),
        ("Root chord, mean chords (derived: 1 / K)", both(chord("root_chord"))),
        ("Tip chord, mean chords", both(chord("tip_chord"))),
        ("Overall taper (tip / root)", both(taper)),
        ("LE sweep (per panel)", both(sweeps)),
        ("Washout (root − tip)", both(washout)),
        ("Dihedral (per panel)", both(dih)),
        ("Suggested sections b0–b3", [", ".join(cfg.types[t].airfoils) for t in WING_TYPES]),
        ("Re on the mean chord (an input)", ["1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶: every shape at all four"] * 4),
        ("Local Re: smallest tip at 10⁵ · largest root at 4 × 10⁶", both(local_re)),
        ("Mach (CFD)", ["0.1, with a Prandtl–Glauert correction (check C2)"] * 4),
        ("Main flow features", [SUMMARY_TEXT["flow"][t] for t in WING_TYPES]),
        ("Mesh must resolve", [SUMMARY_TEXT["mesh"][t] for t in WING_TYPES]),
    ]
    head = "".join(f"<th><span class='tag {t}'>{TYPE_NAME[t]}</span></th>" for t in WING_TYPES)
    body = "".join(f"<tr><td class='what'>{a}</td>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>" for a, cells in rows)
    fam = "<tr><th></th><th colspan='2'>Tailless</th><th colspan='2'>Conventional</th></tr>"
    return f"<thead>{fam}<tr><th></th>{head}</tr></thead><tbody>{body}</tbody>"


def fig_pipeline() -> str:
    """The plan in five steps: full space -> what we can make -> focus -> flow maps -> the tool."""
    steps = [
        ("1  Full design space", ["17 inputs, 4 types", "aspect ratio up to 10–20", "every sourced section", "40 + 5 hold-out, sparse"], "acc"),
        ("2  What we can make", ["straight panels (≤ 3)", "vertical sections", "any database section", "722 of 722 built wings pass"], "acc"),
        ("3  Focus", ["Class I, small Class II", "unit mean chord, no size", "4 Re levels, 10⁵ – 4 × 10⁶", "dense: 100 + 5 + 10 each", "real Re inside the levels"], "bwbc"),
        ("4  Flow maps", ["local Re, root to tip", "transition and bubbles", "effect of the sections", "phenomena per family", "first approach: real size"], "amber"),
        ("5  The tool", ["wing in", "family and type by rule", "flow map at V, altitude, α", "proposed turbulence model"], "warn"),
    ]
    w, gap, h = 176, 22, 158
    o = [f'<svg class="dg" viewBox="0 0 {5 * w + 4 * gap + 20} {h + 70}" role="img" aria-label="Five steps: full design space, what the parametrization can make, the focus space, flow maps, and the tool that takes a wing and returns its flow map and a proposed model">']
    for k, (title, lines, cls) in enumerate(steps):
        x = 10 + k * (w + gap)
        o.append(f'<rect x="{x}" y="20" width="{w}" height="{h}" rx="8" class="stepbox"/>')
        o.append(f'<text class="lab head {cls}" x="{x + 12}" y="46" style="font-size:14px">{title}</text>')
        for j, ln in enumerate(lines):
            o.append(f'<text class="lab" x="{x + 12}" y="{74 + 22 * j}" style="font-size:12px">{ln}</text>')
        if k < 4:
            ax = x + w + 2
            o.append(f'<line class="stroke" x1="{ax}" y1="{20 + h / 2}" x2="{ax + gap - 6}" y2="{20 + h / 2}"/>'
                     f'<polygon class="arrowhead" points="{ax + gap - 4},{20 + h / 2} {ax + gap - 11},{16 + h / 2} {ax + gap - 11},{24 + h / 2}"/>')
    o.append(f'<text class="lab muted" x="10" y="{h + 42}">Each step narrows or reads the one before it. Steps 1–3: geometry (this module; every wing at unit mean chord since 7 Nov 2026).</text>')
    o.append(f'<text class="lab muted" x="10" y="{h + 60}">Steps 4–5: flow maps and the flow dataset (XFOIL strips via section tables), made at real size and speed before 7 Nov: first approach, not rebuilt.</text>')
    o.append("</svg>")
    return "\n".join(o)


def fig_runs() -> str:
    """Every run: inputs, 2-D XFOIL runs, strip theory (2-D -> 3-D), outputs, and the 3-D CFD still to come."""
    o = ['<svg class="dg" viewBox="0 0 1000 700" role="img" aria-label="What was run. 2-D XFOIL runs on single airfoils: '
         'an airfoil study and the section tables, plus direct checks. Strip theory turns the tables into 3-D wing results for '
         'the flow maps, the flow dataset and the checks. The geometry generator and the real UAV database feed it. No 3-D CFD '
         'on a wing has been run yet.">',
         '<defs><marker id="ahr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" class="fillc"/></marker></defs>']

    def box(x, y, w, h, head, lines, cls="acc", dashed=False, muted_from=None):
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="{"dash" if dashed else "stepbox"}"/>')
        o.append(f'<text class="lab head {cls}" x="{x + 12}" y="{y + 24}" style="font-size:14px">{head}</text>')
        for j, ln in enumerate(lines):
            c = "lab muted" if muted_from is not None and j >= muted_from else "lab"
            dx = 26 if ln.startswith(" ") else 12            # SVG drops leading spaces: indent by position
            o.append(f'<text class="{c}" x="{x + dx}" y="{y + 46 + 17 * j}" style="font-size:12px">{ln.strip()}</text>')

    def arrow(points):
        pts = " ".join(f"{a},{b}" for a, b in points)
        o.append(f'<polyline class="stroke" points="{pts}" marker-end="url(#ahr)"/>')

    o.append('<text class="lab muted" x="10" y="22" style="font-size:12px">2-D RUNS: XFOIL, ONE AIRFOIL AT A TIME</text>')
    o.append('<text class="lab muted" x="340" y="22" style="font-size:12px">2-D → 3-D</text>')
    o.append('<text class="lab muted" x="680" y="22" style="font-size:12px">WHAT CAME OUT</text>')
    # column 1: 2-D runs
    box(10, 40, 290, 78, "A · Airfoil study", ["4 airfoils × 4 Re × free / tripped", "32 polars 0–8° + 32 runs at exactly 2°"], "amber")
    box(10, 136, 290, 60, "Flow phenomena (2-D only)", ["drag, transition, bubbles per airfoil"], "amber")
    arrow([(155, 118), (155, 134)])
    box(10, 230, 290, 122, "B · Section tables", ["10 airfoils + 3 blends", "14 Re × 3 Mach × 49 angles",
                                                 "free (N_crit 5, 9, 11) and tripped", "2,408 sweeps = 58,996 points (91 % ok)"], "amber")
    box(10, 470, 290, 72, "C · Direct XFOIL checks", ["890 single runs: tables vs direct,", "whole-wing check, first flow maps"], "amber")
    # column 2: geometry and strip theory
    box(340, 40, 300, 96, "Geometry generator", ["722 wings built, checked (7 Nov)", "the strips used the 730 of before 7 Nov", "(no flow computed here)"], "acc")
    arrow([(490, 136), (490, 228)])
    box(340, 230, 300, 220, "Strip theory: 2-D → 3-D", [
        "1  cut the half wing into 10 strips",
        "2  each strip: its chord, twist, airfoil",
        "3  local Re = (ρ / μ) · V · chord",
        "    local angle = root + twist − induced",
        "4  read free + tripped answers (B)",
        "5  add up along the semi-span, chord-",
        "    weighted → the wing's results",
        "not included: crossflow,",
        "3-D bubble relief, tip vortex"], "bwbc", muted_from=7)
    arrow([(300, 290), (338, 290)])
    # column 3: inputs from real wings and the outputs
    box(680, 40, 310, 96, "Real UAV database", ["34 with area, 112 full spans", "speeds and wing loadings", "(no flow computed here)"], "acc")
    arrow([(835, 136), (835, 228)])
    o.append('<text class="lab muted" x="845" y="186" style="font-size:11px">speeds, wing loadings</text>')
    box(680, 230, 310, 60, "Flow maps (the tool)", ["1 example + 24 focus maps"], "bwbc")
    box(680, 300, 310, 80, "Flow dataset", ["400 wings × 4 sets × 126 conditions", "= 201,600 cases (real size: first approach)"], "bwbc")
    box(680, 390, 310, 60, "Assumption checks", ["6 re-runs × 40,320 cases"], "bwbc")
    for y in (260, 340, 420):
        arrow([(640, y), (678, y)])
    arrow([(300, 506), (920, 506), (920, 452)])
    # 3-D CFD
    box(10, 572, 980, 76, "3-D CFD on a wing: none run yet", [
        "First SU2 smoke test (4 Nov 2026): SA and LM ran on one Stage 2 ring mesh, not converged; it shows the mesh path works.",
        "Next (proposal, pending): ADflow SA for all mesh studies and the fully turbulent data; SU2 SST + LM γ-Reθ on about 20 % "
        "of the wings."], "warn", dashed=True)
    o.append('<text class="lab muted" x="10" y="684" style="font-size:12px">Every flow number on this page comes from 2-D XFOIL '
             'runs on single airfoils, used alone (A) or added up along the semi-span by strip theory (B).</text>')
    o.append("</svg>")
    return "\n".join(o)


def flowmap_table() -> str:
    f = DOCS / "focus_flowmaps.json"
    if not f.is_file():
        return "<tr><td colspan='6'>Run scripts/focus_flowmaps.py</td></tr>"
    d = json.loads(f.read_text())
    out = []
    for t in WING_TYPES:
        sets = list(dict.fromkeys(m["set"] for m in d.get(t, [])))
        for k, sname in enumerate(sets):
            cells = []
            for cond in ("slow", "fast"):
                m = next(x for x in d[t] if x["set"] == sname and x["condition"] == cond)["map"]
                rows = m["strips"]
                xt = [r["xtr_upper"] for r in rows if r.get("xtr_upper") is not None]
                bub = [b for r in rows for b in r.get("bubbles_upper") or []]
                bias = m["model"]["sa_drag_bias"]
                cells.append(f"<td class='num'>{sci(min(r['re'] for r in rows))} – {sci(max(r['re'] for r in rows))}</td>"
                             f"<td class='num'>{(f'{100 * min(xt):.0f}–{100 * max(xt):.0f} %' if xt else '—')}"
                             f"{(f'<br><span class=muted>bubble {100 * min(b[0] for b in bub):.0f}–{100 * max(b[1] for b in bub):.0f} %</span>' if bub else '')}</td>"
                             f"<td class='num'><strong>{(f'{100 * bias:+.0f} %' if bias is not None else '—')}</strong></td>")
            tag = f"<span class='tag {t}'>{TYPE_NAME[t]}</span>" if k == 0 else ""
            out.append(f"<tr><td>{tag}</td><td>{html.escape(sname)}</td>{''.join(cells)}</tr>")
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# Flow dataset and sensitivity (docs/flow_analysis.json from python -m cfdauto.flowmap.analysis)
# --------------------------------------------------------------------------------------
def _pc(x: float | None, sign: bool = True) -> str:
    """Percent with a true minus sign; anything that rounds to zero is plain 0 %."""
    if x is None or x != x:
        return "—"
    v = round(100 * x)
    if v == 0:
        return "0 %"
    return (f"{v:+d} %" if sign else f"{v:d} %").replace("-", "−")


def _pt(x: float, nd: int = 1) -> str:
    """Signed points with a true minus sign (no "−0.0")."""
    v = round(100 * x, nd)
    return "0" if v == 0 else f"{v:+.{nd}f}".replace("-", "−")


def flowdata_html() -> dict:
    f = DOCS / "flow_analysis.json"
    if not f.is_file():
        return {k: "<p>Run <code>python -m cfdauto.flowmap.dataset</code> and <code>python -m cfdauto.flowmap.analysis</code>.</p>"
                for k in ("__FD_INTRO__", "__FD_KPI__", "__FD_CONCL__", "__FD_STATS__", "__FD_CHECKS__", "__FD_DRIVERS__",
                          "__FD_TOTAL__", "__FD_LEVEL__", "__FD_STATS_NOTE__")}
    a = json.loads(f.read_text())
    fc = yaml.safe_load((ROOT / "configs" / "flowmap.yaml").read_text())
    ds = fc["dataset"]
    out = {}
    out["__FD_INTRO__"] = (
        f"First approach, not rebuilt: made at real size and real speed before 7 Nov 2026. "
        f"{a['rows']:,} rows: {a['wings']} focus wings (100 per type, the focus sets of 30 Oct–6 Nov at real size, full span ≤ 7 m) × 4 section sets × "
        f"{len(ds['mach'])} Mach ({min(ds['mach']):g}–{max(ds['mach']):g}) × {len(ds['alpha_deg'])} root angles "
        f"({min(ds['alpha_deg']):g}–{max(ds['alpha_deg']):g}°) × {len(ds['altitude_m'])} altitudes (0, 1,524, 3,048 m). "
        f"Each row is one wing at one condition with 10 strips along the half wing, each strip a 2-D section answer from the "
        f"section tables (XFOIL, free and tripped), with a uniform induced angle. {a['rows_realistic']:,} rows fly at speeds real "
        f"wings of the family fly, with a section set that can trim the wing; the statistics below use those, unless marked (the "
        f"NACA set on tailless wings cannot trim: it is shown, not counted). The scope has since grown: angles −5° to post-stall "
        f"(decided 6 Nov 2026) and Mach toward 0.5 with no supersonic flow (4 Nov 2026); this dataset covers root angles "
        f"{min(ds['alpha_deg']):g}–{max(ds['alpha_deg']):g}° and Mach {min(ds['mach']):g}–{max(ds['mach']):g} only.")
    ba, lf = a["bias_all"], a["level_flight"]
    low = sum(a["low_re_share_by_type"].values()) / 4
    out["__FD_KPI__"] = "\n".join([
        f"<div class='box'><h3>Rows</h3><div class='big'>{a['rows']:,}</div><p>{a['wings']} wings × 4 section sets × "
        f"{a['conditions']} conditions. Built in about two minutes from the section tables.</p></div>",
        f"<div class='box verdict'><h3>SA drag error, median</h3><div class='big'>{_pc(ba['median'])}</div><p>Fully turbulent "
        f"SA against free transition, profile drag. 10–90 %: {_pc(ba['q10'])} to {_pc(ba['q90'])}. Within ±10 % in "
        f"{_pc(ba['share_sa_ok'], False)} of rows.</p></div>",
        f"<div class='box'><h3>In level flight</h3><div class='big'>{_pc(lf['bias_all']['median'])}</div><p>Median in the "
        f"{_pc(lf['share_rows'], False)} of rows that carry a real wing loading for their size. Within ±10 %: "
        f"{_pc(lf['bias_all']['share_sa_ok'], False)}.</p></div>",
        f"<div class='box'><h3>Below Re 10⁵ somewhere</h3><div class='big'>{_pc(low, False)}</div><p>Share of rows with part of "
        f"the half wing below 10⁵, mean of the four types (BWB {_pc(a['low_re_share_by_type']['bwb'], False)}, flying wing "
        f"{_pc(a['low_re_share_by_type']['flying_wing'], False)}, cranked {_pc(a['low_re_share_by_type']['cranked'], False)}, "
        f"tapered {_pc(a['low_re_share_by_type']['tapered'], False)}).</p></div>"])
    rows = []
    for t in WING_TYPES:
        keys = [k for k in a["bias"] if k.startswith(t + "|")]
        for i, k in enumerate(keys):
            b, st = a["bias"][k], a["by_set"][k]
            tag = f"<span class='tag {t}'>{TYPE_NAME[t]}</span>" if i == 0 else ""
            note = "" if b.get("trims", True) else " <span class='muted'>(cannot trim: not counted)</span>"
            rows.append(f"<tr><td>{tag}</td><td>{html.escape(b['label'])}{note}</td><td class='num'><strong>{_pc(b['median'])}</strong></td>"
                        f"<td class='num'>{_pc(b['q10'])} to {_pc(b['q90'])}</td><td class='num'>{_pc(b['share_sa_ok'], False)}</td>"
                        f"<td class='num'>{_pc(st['lam_upper_median'], False)}</td><td class='num'>{_pc(st['bubble_span_mean'], False)}</td>"
                        f"<td class='num'>{_pc(st['te_sep_span_mean'], False)}</td><td class='num'>{_pc(st['conv_span_mean'], False)}</td></tr>")
    out["__FD_STATS__"] = "\n".join(rows)
    ci = a.get("median_ci", {})
    half = max((v["hi"] - v["lo"]) / 2 for v in ci.values()) if ci else None
    out["__FD_STATS_NOTE__"] = (
        "Realistic speeds only (tailless Mach ≤ 0.14, the grid level just above their top speed at Mach 0.13; conventional ≤ 0.20), "
        "all angles 0–10° and altitudes; every set is shown. "
        "Means and medians over rows; each wing counts once per condition."
        + (f" Precision: resampling the 100 wings of a type moves its median SA error by at most ±{100 * half:.1f} points (95 %)."
           if half is not None else ""))
    ck = a["checks"]
    lab = {"ncrit_5": "N<sub>crit</sub> 5 instead of 9 (air turbulence 0.37 % instead of 0.07 %)",
           "ncrit_11": "N<sub>crit</sub> 11 instead of 9 (0.03 %: very quiet air)",
           "mach0": "No compressibility in 2-D (Mach 0, same Re)", "strips1": "7 strips instead of 10",
           "strips5": "19 strips instead of 10", "no_induced": "Induced angle left out (the old baseline)"}
    rows = []
    for k, name in lab.items():
        c = ck[k]
        rows.append(f"<tr><td>{name}</td><td class='num'>{_pt(c['sa_bias']['median'])}</td>"
                    f"<td class='num'>{_pt(c['sa_bias']['q05'])} to {_pt(c['sa_bias']['q95'])}</td>"
                    f"<td class='num'>{_pt(c['lam_upper']['median'])}</td><td class='num'>{100 * c['bubble_span']['mean_abs']:.1f}</td>"
                    f"<td class='num'>{100 * c['te_sep_span']['mean_abs']:.1f}</td><td class='num'>{c['n']:,}</td></tr>")
    tv = a["tables_vs_direct"]
    rows.append(f"<tr><td>Section tables instead of direct XFOIL ({tv['n']} random points)</td>"
                f"<td class='num' colspan='2'>CD error, median {100 * tv['free']['cd_rel_median']:.1f} % (free), "
                f"{100 * tv['trip']['cd_rel_median']:.1f} % (tripped); 90 % below {100 * tv['free']['cd_rel_q90']:.0f} %</td>"
                f"<td class='num'>{100 * tv['free']['xtr_abs_median']:.1f}</td><td class='num' colspan='2'>bubble yes/no agrees "
                f"{100 * tv['free']['bubble_agree']:.0f} %</td><td class='num'>{tv['n']}</td></tr>")
    bl = a["blend_rule"]
    med = sorted(v["cd_rel_median"] for v in bl.values())
    rows.append(f"<tr><td>Blend rule (average of the two parents) instead of the blended section, 3 pairs</td>"
                f"<td class='num' colspan='2'>CD error, median {100 * min(med):.1f}–{100 * max(med):.1f} % by pair</td>"
                f"<td class='num'>{100 * max(v['xtr_abs_median'] for v in bl.values()):.1f}</td><td class='num' colspan='2'></td>"
                f"<td class='num'>{sum(v['n'] for v in bl.values()):,}</td></tr>")
    out["__FD_CHECKS__"] = "\n".join(rows)
    gname = {"wing shape": "wing shape", "sections": "sections", "flight condition": "flight condition"}
    oname = {"sa_bias": "SA drag error", "lam_upper": "laminar run (upper)", "bubble_span": "half wing with a bubble",
             "te_sep_span": "half wing with TE separation", "span_re_lt_1e5": "half wing below Re 10⁵"}
    iname = {"mean_chord_m": "size (mean chord)", "aspect_ratio": "aspect ratio", "taper": "taper", "max_sweep_deg": "sweep",
             "washout_deg": "washout", "twist0_deg": "root twist", "dihedral_p1_deg": "dihedral", "b3_ratio": "outer-panel share",
             "split_ratio": "panel split", "set": "section set", "mach": "Mach", "alpha_deg": "angle", "altitude_m": "altitude"}
    rows = []
    for fam in ("tailless", "conventional"):
        for i, (o, on) in enumerate(oname.items()):
            gf, gt = a["groups_first"][fam][o], a["groups_total"][fam][o]
            top = a["top_inputs"][fam][o]
            sp = a["spearman"][fam][o]
            tops = ", ".join(f"{iname[k]} {100 * v:.0f} %" + ("" if k == "set" or sp.get(k) is None or sp[k] != sp[k] else
                                                         (" ↑" if sp[k] > 0.05 else (" ↓" if sp[k] < -0.05 else "")))
                             for v, k in top if v >= 0.03)
            ftag = f"<strong>{fam}</strong>" if i == 0 else ""
            rows.append(f"<tr><td>{ftag}</td><td>{on}</td>" + "".join(
                f"<td class='num'>{100 * gf[g]:.0f} <span class='muted'>/ {100 * gt[g]:.0f}</span></td>" for g in gname)
                + f"<td class='num'>{100 * a['r2'][fam][o]:.0f} %</td><td>{tops}</td></tr>")
    out["__FD_DRIVERS__"] = "\n".join(rows)
    td = ck["total_drag"]
    out["__FD_TOTAL__"] = (
        "As a share of the whole drag (profile + an elliptic induced drag, CL from the strips with the induced angle, 20 wings per type): "
        + ", ".join(f"{TYPE_NAME[t]} {_pc(td[t]['total_bias_median'])} (profile only {_pc(td[t]['profile_bias_median'])})"
                    for t in WING_TYPES) + ". By root angle: " + ", ".join(f"{k}° {_pc(v)}" for k, v in td["by_alpha"].items()) + ".")
    lt = lf["bias"]
    out["__FD_LEVEL__"] = "\n".join(
        f"<tr><td><span class='tag {t}'>{TYPE_NAME[t]}</span></td><td class='num'>{_pc(lf['share_by_type'][t], False)}</td>"
        f"<td class='num'><strong>{_pc(lt[t]['median'])}</strong></td><td class='num'>{_pc(lt[t]['q10'])} to {_pc(lt[t]['q90'])}</td>"
        f"<td class='num'>{_pc(lt[t]['share_sa_ok'], False)}</td><td class='num'>{_pc(lt[t]['lam_upper_median'], False)}</td>"
        f"<td class='num'>{_pc(lt[t]['bubble_span_mean'], False)}</td><td class='num'>{_pc(lt[t]['te_sep_span_mean'], False)}</td>"
        f"<td class='num'>{_pc(lt[t]['low_re_share'], False)}</td></tr>" for t in WING_TYPES)
    out["__FD_CONCL__"] = flowdata_conclusions(a)
    return out


def flowdata_conclusions(a: dict) -> str:
    """Plain-word conclusions with the numbers of docs/flow_analysis.json (baseline: induced angle included)."""
    ba, lf, ck = a["bias_all"], a["level_flight"], a["checks"]
    by_a = {float(k): v for k, v in a["bias_by_alpha"].items()}
    by_m = {float(k): v for k, v in a["bias_by_mach"].items()}
    lf_m = {float(k): v for k, v in lf["bias_by_mach"].items()}
    a_peak = max(by_a, key=by_a.get)
    m_peak = max(lf_m, key=lf_m.get)
    bub_a = {float(k): v for k, v in a["bubble_span_by_alpha"].items()}
    bub_m = {float(k): v for k, v in a["bubble_span_by_mach"].items()}
    te_a = {float(k): v for k, v in a["te_sep_by_alpha"].items()}
    lam_a = {float(k): v for k, v in a["lam_by_alpha"].items()}
    lam_m = {float(k): v for k, v in a["lam_by_mach"].items()}
    be = a["bubble_extent"]
    gf = {fam: a["groups_first"][fam]["sa_bias"] for fam in ("tailless", "conventional")}
    gt = {fam: a["groups_total"][fam]["sa_bias"] for fam in ("tailless", "conventional")}
    sets = sorted(((v["median"], v["label"].replace(" (suggested)", "")) for k, v in a["bias"].items()
                   if k.split("|")[0] in ("cranked", "tapered")))
    lo_set, hi_set = sets[0], sets[-1]
    hi_names = " and ".join(dict.fromkeys(lb for m_, lb in reversed(sets) if round(100 * m_) == round(100 * hi_set[0])))
    cat = a["categories"]
    tm = cat.get("transition model", 0) + cat.get("transition model; part below 10⁵", 0)
    n5, n11 = ck["ncrit_5"]["sa_bias"]["median"], ck["ncrit_11"]["sa_bias"]["median"]
    ni = ck["no_induced"]["sa_bias"]
    st = max(abs(ck["strips1"]["sa_bias"]["median"]), abs(ck["strips5"]["sa_bias"]["median"]))
    m0 = ck["mach0"]["sa_bias"]
    tv = a["tables_vs_direct"]
    td = ck["total_drag"]
    tot = sorted(td[t]["total_bias_median"] for t in WING_TYPES)
    low = a["low_re_share_by_type"]
    lr = a["low_re_rows"]
    xf = a["crossflow_share"]
    pr = a["pairs"]
    lt = sorted(lf["bias"][t]["median"] for t in WING_TYPES)
    items = [
        f"<strong>Fully turbulent SA overestimates the profile drag on almost every wing and condition.</strong> Median "
        f"{_pc(ba['median'])} (10–90 %: {_pc(ba['q10'])} to {_pc(ba['q90'])}); within ±10 % in only {_pc(ba['share_sa_ok'], False)} "
        f"of rows. In level flight at real wing loadings: {_pc(lf['bias_all']['median'])} ({_pc(lt[0])} to {_pc(lt[-1])} by type), "
        f"within ±10 % in {_pc(lf['bias_all']['share_sa_ok'], False)}. The tool proposes a transition model for {_pc(tm, False)} of rows.",
        f"<strong>SA's error does not cancel between similar wings.</strong> For {pr['n']:,} pairs of wings of the same type and "
        f"section set at the same speed, altitude and lift, SA's error on the profile-drag difference is {pr['err_counts_median']:.0f} "
        f"counts (median; 90 %: {pr['err_counts_q90']:.0f}), above the 2-count target of Stage 0 in "
        f"{_pc(pr['share_above_2_counts'], False)} of pairs; SA ranks {_pc(pr['share_flipped'], False)} of the pairs the other way "
        f"round. A drag dataset meant to rank wings needs transition-model results, at least on a calibration subset.",
        f"<strong>In level flight the error rises with speed.</strong> {_pc(lf_m[min(lf_m)])} at Mach {min(lf_m):g}, "
        f"{_pc(lf_m[m_peak])} at Mach {m_peak:g}, {_pc(lf_m[max(lf_m)])} at Mach {max(lf_m):g}. In level flight the angle follows "
        f"the speed, so these are the trends to read; over the whole grid the speed trend is flatter ({_pc(by_m[min(by_m)])} → "
        f"{_pc(by_m[max(by_m)])}).",
        f"<strong>In this 2-D model, how the wing flies sets most of the error.</strong> Speed, angle and altitude explain "
        f"{100 * gf['tailless']['flight condition']:.0f} % of its spread alone on tailless wings "
        f"({100 * gt['tailless']['flight condition']:.0f} % with interactions), {100 * gf['conventional']['flight condition']:.0f} % "
        f"on conventional ones ({100 * gt['conventional']['flight condition']:.0f} %). The strips see the shape only through chord, "
        f"twist and the induced angle, and the shares depend on our grid, which crosses every angle with every speed.",
        f"<strong>The error peaks at a moderate angle.</strong> {_pc(by_a[a_peak])} at {a_peak:g}° root angle, {_pc(by_a[max(by_a)])} "
        f"at {max(by_a):g}°: at high angle the real flow turns turbulent near the nose by itself (laminar run "
        f"{_pc(lam_a[min(lam_a)], False)} of chord at {min(lam_a):g}°, {_pc(lam_a[max(lam_a)], False)} at {max(lam_a):g}°). "
        f"Trailing-edge separation stays small: at most {_pc(max(te_a.values()), False)} of the half wing at any root angle up to "
        f"{max(te_a):g}°.",
        f"<strong>On conventional wings the airfoil changes the error most.</strong> The airfoil set alone explains "
        f"{100 * gf['conventional']['sections']:.0f} % of the spread, {100 * gt['conventional']['sections']:.0f} % with its "
        f"interactions; on LA2573A the error grows with the angle, on the others it falls. Lowest median: "
        f"{html.escape(lo_set[1])} ({_pc(lo_set[0])}, its bubbles already cost drag in the real flow); highest: "
        f"{html.escape(hi_names)} ({_pc(hi_set[0])}). SA would rank airfoils wrongly.",
        f"<strong>Below Re 10⁵ the sign flips.</strong> Where most of the half wing is below 10⁵ ({lr['n']:,} rows), the median error is "
        f"{_pc(lr['bias_median'])} and {_pc(lr['share_negative'], False)} are negative: long laminar bubbles give the real flow more drag than "
        f"fully turbulent CFD. Part of the half wing is below 10⁵ in {_pc(low['bwb'], False)} of BWB rows, {_pc(low['flying_wing'], False)} "
        f"flying wing, {_pc(low['cranked'], False)} cranked, {_pc(low['tapered'], False)} tapered. There SA is wrong in sign, XFOIL itself is "
        f"least reliable, and a transition model must be checked against experiments before it is trusted.",
        f"<strong>Laminar bubbles are the normal case, and they move.</strong> On average {_pc(min(bub_a.values()), False)}–"
        f"{_pc(max(bub_a.values()), False)} of the half wing has an upper-surface bubble, depending on the angle; "
        f"{_pc(bub_m[min(bub_m)], False)} at Mach {min(bub_m):g}, {_pc(bub_m[max(bub_m)], False)} at Mach {max(bub_m):g}. Bubbles start "
        f"from about {_pc(be['start_q05'], False)} and end by about {_pc(be['end_q95'], False)} of the chord "
        f"({_pc(be['share_outside_30_70'], False)} of them lie partly outside 30–70 %); the lower surface stays laminar to about "
        f"{_pc(be['lam_lower_median'], False)} of the chord. A transition-model mesh needs fine streamwise cells over the upper "
        f"surface from about 10 to 85 % (Stage 2 builds it from the leading edge on every wing) and the lower surface from 60 to 100 %, "
        f"and y⁺ ≤ 1. These bands hold for root angles "
        f"{min(by_a):g}–{max(by_a):g}°: at negative angles (now in scope, down to −5°) the lower surface becomes the suction side, "
        f"so its band must start further forward.",
        f"<strong>Size acts through Re; sweep does not enter the strips.</strong> The mean chord is the strongest shape input (larger "
        f"chord, higher Re, larger SA error up to about Re 10⁶). Aspect ratio acts through the uniform induced angle, washout and taper "
        f"through the local angle and chord. Sweep scores like dihedral (a built-in placebo): 'not modelled', not 'unimportant'. In 3-D, "
        f"sweep drives spanwise flow, crossflow and tip stall.",
        f"<strong>Swept tailless wings may see crossflow transition (rough flag).</strong> {_pc(xf['bwb'], False)} of BWB rows and "
        f"{_pc(xf['flying_wing'], False)} of flying-wing rows have a strip swept over 25° with Re normal to its edge above 10⁶ (our "
        f"threshold, not sourced). Neither XFOIL nor γ-Reθ without a crossflow term sees it; there the transition position is less certain, so on swept panels the mesh transition band starts at the leading edge.",
        f"<strong>Our assumptions move the numbers, not the sign.</strong> More turbulent air (N<sub>crit</sub> 5) changes the error by "
        f"{_pt(n5, 0)} points, quieter air (11) by {_pt(n11, 0)}; leaving out the induced angle (the old baseline) by {_pt(ni['median'], 0)} "
        f"(5–95 %: {_pt(ni['q05'], 0)} to {_pt(ni['q95'], 0)}, the big changes at high angle); compressibility by {_pt(m0['median'])}; "
        f"the strip count by under {max(100 * st, 0.1):.1f}. The tables reproduce direct XFOIL to a median "
        f"{100 * tv['free']['cd_rel_median']:.1f} % in drag.",
        f"<strong>In the whole drag the error is smaller, but still large.</strong> With an elliptic induced drag added, fully turbulent "
        f"SA overestimates the total drag by a median {_pc(tot[0])} to {_pc(tot[-1])} by type: far above the 3-count drag budget of Stage 0.",
        "<strong>What this means for the CFD.</strong> Start the mesh studies with SA (ADflow), with its inflow eddy viscosity fixed "
        "(ν̃/ν about 3). SA gives an upper bound for drag only where Re is above about 10⁵ and there is no long bubble (below 10⁵, "
        "and for LA2573A in slow flight, the real flow has more drag). Make the mesh transition-ready (y⁺ ≤ 1 at each station's Re, fine cells "
        "over the whole chord on both sides, as Stage 2 builds since 7 Nov) and repeat a reduced mesh study with the "
        "transition model: what a mesh must resolve depends on the model. Transition must be captured (decided 4 Nov 2026): for drag "
        "numbers or rankings, run SU2 SST + LM γ-Reθ (proposal, pending: on about 20 % of the wings first; ADflow SA for all mesh "
        "studies and the fully turbulent data). Below Re 10⁵, neither is enough. The tool gives the band, the bubble positions and the "
        "model for any wing in milliseconds. Stage 2 now uses it: a per-wing refine map reads this dataset to place the band. Cost at "
        "the fine level: median 15.2 M cells with these rules; a relaxed band (0.5 % c spacing where local Re ≥ 4 × 10⁵) gives 10.9 M "
        "(proposal, pending).",
    ]
    return "\n".join(f"<li>{x}</li>" for x in items)


def xfoil_note() -> str:
    """Per Re, the range of tripped / free - 1 over the four sections at exactly 2 deg (the same runs as the bars)."""
    from cfdauto.flowmap import xfoil
    from cfdauto.geometry.sections import load_airfoil
    f = DOCS / "xfoil_band.json"
    if not f.is_file():
        return "Run scripts/xfoil_band.py."
    d = json.loads(f.read_text())
    parts, missing = [], []
    for r in d["re"]:
        vals = []
        for name in d["sections"]:
            pts = load_airfoil(name).selig()
            a, b = xfoil.run(pts, r, 2.0, False, 0.0), xfoil.run(pts, r, 2.0, True, 0.0)
            if a and b:
                vals.append(100 * (b["cd"] / a["cd"] - 1))
            else:
                missing.append(f"{name.upper().replace('MH', 'MH ')} at {sci(r)}")
        parts.append(f"{sci(r)}: {min(vals):+.0f} to {max(vals):+.0f} %".replace("-", "−"))
    return ("At 2°, by Re: " + "; ".join(parts) + ". "
            + ("Nothing is hidden: " + ", ".join(missing) + " has no light bar because XFOIL found no converged free-transition "
               "answer at 2° there (an earlier version silently showed 0° for it). " if missing else
               "Every section has a converged answer at 2° at every Re (on the sections before the nose fix, MH 60 at "
               "1.5 × 10⁶ had none). ")
            + "The section tables cover every angle from −10° to 14° and every Re; their maps are in the Flow dataset section "
              "(−6° to 14° shown).")


def sci(x: float) -> str:
    e = int(f"{x:.1e}".split("e")[1]); m = x / 10 ** e
    sup = str(e).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))
    return f"{m:.1f} × 10{sup}"


def sci3(x: float) -> str:
    """Three significant figures: 1.22 × 10⁵."""
    e = int(f"{x:.2e}".split("e")[1]); m = x / 10 ** e
    sup = str(e).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))
    return f"{m:.2f} × 10{sup}"


def extremes_html() -> dict:
    """Shapes at the edges (unit mean chord, docs/size_extremes.json) and, kept as the record, the first-approach
    sizes at real scale (docs/first_approach/size_extremes.json)."""
    ex, rm = [], []
    for t in WING_TYPES:
        for sp in ("focus", "full"):
            r = SIM[f"{t}/{sp}"]
            tag = f"<span class='tag {t}'>{TYPE_NAME[t]}</span>"
            sp_txt = "<strong>focus</strong>" if sp == "focus" else "<span class='muted'>full</span>"
            ex.append(f"<tr><td>{tag}</td><td>{sp_txt}</td><td class='num'>{r['aspect_ratio'][0]:g} – {r['aspect_ratio'][1]:g}</td>"
                      f"<td class='num'>{r['root_chord'][0]:.3f} – {r['root_chord'][1]:.3f}</td>"
                      f"<td class='num'>{r['tip_chord'][0]:.3f} – {r['tip_chord'][1]:.3f}</td>"
                      f"<td class='num'>{r['taper'][0]:.2f} – {r['taper'][1]:.2f}</td>"
                      f"<td class='num'>{r['root_over_tip_max']:.1f} ×</td></tr>")
            rm.append(f"<tr><td>{tag}</td><td>{sp_txt}</td><td class='num'>1 × 10⁵ – 4 × 10⁶</td>"
                      f"<td class='num'>{r['tip_chord'][0]:.3f} → {sci(r['re_tip_min'])}</td>"
                      f"<td class='num'>{r['root_chord'][1]:.3f} → {sci(r['re_root_max'])}</td></tr>")
    out = {"__EXTREMES__": "\n".join(ex), "__RE_MACH__": "\n".join(rm)}
    f = DOCS / "first_approach" / "size_extremes.json"
    d = json.loads(f.read_text()) if f.is_file() else {}
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
        rm.append(f"<tr><td>{tag}</td><td>{sp_txt}</td><td class='num'>{r['speed_m_s'][0]:g}–{r['speed_m_s'][1]:g} m/s</td>"
                  f"<td class='num'>{r['mach'][0]:.3f}–{r['mach'][1]:.2f}</td><td class='num'>{sci(lo)} – {sci(hi)}</td>"
                  f"<td class='num'>{sci(r['re_tip_min'])}</td><td class='num'>{sci(r['re_root_max'])}</td></tr>")
    out |= {"__EXTREMES_FIRST__": "\n".join(ex) or "<tr><td colspan='7'>(docs/first_approach/size_extremes.json missing)</td></tr>",
            "__RE_MACH_FIRST__": "\n".join(rm) or "<tr><td colspan='7'>(docs/first_approach/size_extremes.json missing)</td></tr>"}
    return out


def final_ranges_html() -> dict:
    cfg = load_config()
    d = json.loads((DOCS / "real_uavs.json").read_text())["summary"]
    env, rey = d["envelope"], d["reynolds"]
    specs = {t: cfg.types[t] for t in WING_TYPES}
    def rng(sp, v, f="{:g}"):
        lo, hi = sp.ranges[v]
        m = lambda x: f.format(x).replace("-", "−")  # noqa: E731
        return f"{m(lo)} to {m(hi)}" if min(lo, hi) < 0 else f"{m(lo)}–{m(hi)}"

    size = "".join(                       # (not on the page; at unit mean chord the aspect ratio is the only size input)
        f"<tr><td class='what'>{TYPE_NAME[t]}</td><td class='num'>{rng(sp, 'aspect_ratio')}</td></tr>"
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
    gen_rows = [("Full span b", "span_m", " m", "{:.1f}"), ("Mean chord", "mean_chord_m", " m", "{:.2f}"),
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
            "__REAL_RE__": f"{sci3(d['re_low_min'])} – {sci3(d['re_high_max'])}"}


# --------------------------------------------------------------------------------------
# Figures for the flow-phenomena section (inline SVG, theme-aware through CSS classes)
# --------------------------------------------------------------------------------------

def _x_re(re_: float, x0: float = 170, px_per_decade: float = 230) -> float:
    import math
    return x0 + (math.log10(re_) - 4.0) * px_per_decade


def fig_re_map() -> str:
    """Where each wing type flies on the Reynolds axis, at unit mean chord (decision 70): the four Re levels on the
    mean chord (an input of each solve), the local Re of each type from its smallest tip at the lowest level to its
    largest root at the top level (focus space), and the real wings (their own Re, on area / full span)."""
    d = json.loads((DOCS / "real_uavs.json").read_text())
    W, H = 900, 412
    X = _x_re
    out = [f'<svg class="dg" viewBox="0 0 {W} {H}" role="img" aria-label="Reynolds number map at unit mean chord: the four study levels on the mean chord, the local Re of each type from its smallest tip at the lowest level to its largest root at the top level, and the real wings, against the low-Re regime below 5 times 10 to the 5">']
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
    # types: the levels on the mean chord (thick) and the local Re reach (thin, below)
    for (name, y), t in zip(rows[1:], ("bwb", "cranked", "tapered", "flying_wing")):
        cls = {"bwb": "bwb", "flying_wing": "fw"}.get(t, "conv")
        lo, hi = F[t]["re_tip_min"], F[t]["re_root_max"]
        out.append(f'<rect class="bar {cls}" x="{X(LV[0]):.1f}" y="{y - 7}" width="{X(LV[-1]) - X(LV[0]):.1f}" height="14" rx="2"/>')
        out.append(f'<rect class="bar {cls} tipbar" x="{X(lo):.1f}" y="{y + 11}" width="{X(hi) - X(lo):.1f}" height="5" rx="1"/>')
    # study levels
    for lv, txt in ((v, {1e5: "1 × 10⁵", 3e5: "3 × 10⁵", 1e6: "1 × 10⁶", 4e6: "4 × 10⁶"}.get(v, f"{v:.2g}")) for v in LV):
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
    out.append(f'<text class="lab muted" x="{X(1e4)}" y="402">thick bar: Re on the mean chord (the four levels) · thin bar: local Re, smallest tip at 10⁵ to largest root at 4 × 10⁶ (focus)</text>')
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
        (300, "smallest chord: Re down to 1.4 × 10⁴", (602, 268)),
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


def fig_surfaces() -> str:
    """One airfoil at an angle: upper and lower surface, nose, trailing edge, chord, angle, flow."""
    import math
    pts = _naca4(m=0.04, p=0.4, t=0.12, n=60)
    a = math.radians(-8)                      # drawn nose-up
    C, X0, Y0 = 520, 200, 150

    def tr(x, y):
        return X0 + C * (x * math.cos(a) - y * math.sin(a)), Y0 - C * (x * math.sin(a) + y * math.cos(a))
    up = [tr(x, yu) for x, yu, yl in pts]
    lo = [tr(x, yl) for x, yu, yl in pts]
    poly = " ".join(f"{u:.1f},{v:.1f}" for u, v in up + lo[::-1])
    upl = " ".join(f"{u:.1f},{v - 3:.1f}" for u, v in up)
    lol = " ".join(f"{u:.1f},{v + 3:.1f}" for u, v in lo)
    le, te = tr(0, 0), tr(1, 0)
    o = ['<svg class="dg" viewBox="0 0 1000 300" role="img" aria-label="One airfoil section at an angle of attack: the upper surface is '
         'the top side, the suction side with lower pressure; the lower surface is the bottom side, the pressure side; flow comes from '
         'the left onto the leading edge (nose) and leaves at the trailing edge">',
         '<defs><marker id="ahs" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" class="fillc"/></marker></defs>',
         f'<polygon class="wing" points="{poly}"/>',
         f'<polyline class="lam" points="{upl}"/>',
         f'<polyline class="turb" style="opacity:.35" points="{lol}"/>',
         f'<line class="dash" x1="{le[0]:.1f}" y1="{le[1]:.1f}" x2="{te[0]:.1f}" y2="{te[1]:.1f}"/>',
         f'<line class="dash" x1="{le[0]:.1f}" y1="{le[1]:.1f}" x2="{le[0] + C:.1f}" y2="{le[1]:.1f}"/>',
         f'<text class="lab muted" x="{le[0] + C + 10:.1f}" y="{le[1] + 4:.1f}">flow direction</text>',
         f'<text class="lab muted" x="{le[0] + C + 10:.1f}" y="{le[1] + 24:.1f}">α = angle between flow and chord line</text>',
         f'<text class="lab muted" x="{le[0] + C + 10:.1f}" y="{le[1] + 44:.1f}">(chord line: nose to trailing edge, dashed)</text>']
    for k, y in enumerate((70, 110, 150)):
        o.append(f'<line class="stroke" x1="30" y1="{y + 40}" x2="140" y2="{y + 40}" marker-end="url(#ahs)"/>')
    o.append('<text class="lab" x="30" y="100">flow</text>')
    o.append(f'<text class="lab bwbc" x="{X0 + 160}" y="{Y0 - 95}"><tspan font-weight="700">Upper surface</tspan> = the top side '
             '(suction side: lower pressure, most of the lift)</text>')
    o.append(f'<text class="lab acc" x="{X0 + 200}" y="{Y0 + 95}"><tspan font-weight="700">Lower surface</tspan> = the bottom side '
             '(pressure side)</text>')
    o.append(f'<text class="lab" x="{le[0] - 8:.1f}" y="{le[1] - 22:.1f}" text-anchor="end">leading edge (nose)</text>')
    o.append(f'<text class="lab" x="{te[0] + 10:.1f}" y="{te[1] + 5:.1f}">trailing edge</text>')
    o.append('<text class="lab muted" x="30" y="290">One 2-D airfoil section, as XFOIL runs it: no spanwise extent, no sweep, no wing around it. '
             'Every 2-D figure below is of this kind.</text>')
    o.append("</svg>")
    return "\n".join(o)


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
    ("Wall-normal, every wall", "Boundary layer, skin friction, separation and transition (transition must be captured: decided 4 Nov 2026)",
     "First cell from y⁺ ≤ 1 at the Re of each case (law 13 per station; along the semi-span it changes only about 20 %, because Re and chord change together, and the smallest chord sets it); growth ≤ 1.25 inside the boundary layer, ≤ 1.3 outside (about 1.1 with a transition model: decision 57, Stage 3, pending); ≥ 30 cells across the boundary layer at every station (on a small BWB the root boundary layer is up to about 10 × thicker than the tip's)",
     "wall-normal 20 %", "Roadmap R-V.1, R-V.2 (laws 13, 14); DPW gridding guidelines; Ansys CFX transition-model grid guidance (growth about 1.1)",
     "Volume mesh: Stage 3, not built. Stage 2 uses the tip first cell s0 (y⁺ = 1 at the tip Re) for the last station gap. S8 for reference: one first cell (4.71 µm) for every station; growth 1.253; 29 cells across the boundary layer"),
    ("Leading edge (nose)", "Suction peak, start of the laminar run, leading-edge stall (angles now −5° to post-stall)",
     "Chordwise spacing solved so no cell turns the surface by more than 10° (ladder 12 / 10 / 8 / 6°); nose cells of neighbouring stations differ by at most 15 %",
     "edges and base 15 % (Stage 0 counts the nose cells there)", "Roadmap R-S.5, R-S.6 (laws 1, 2)",
     "Built on the first-approach wings: no ring node turns the surface by more than 10° (largest delivered 10.02°); the nose spacing changes by at most 1.15 between stations. It meshed the old nose as built; the 7 Nov nose (apex leading edge, 201 points per side, decision 64) is not meshed yet. On a NACA 4415 station the 10° target holds up to a nose spacing of 0.377 % c with the new rule (0.327 % c with the old)"),
    ("Transition band: lower surface 0–100 % chord (7 Nov; first 60–100 %); upper surface from the leading edge on every wing, 0–85 % as written (band cells reach 100 % as built)", "End of the laminar run and laminar bubbles; they move with the angle (on top from about 11 % to 78 % of the chord at 0–10°), and the lower surface turns turbulent near the trailing edge. At negative angles the lower surface becomes the suction side. On swept panels crossflow transition, which the 2-D strips cannot see, would start at the leading edge",
     "Required (transition must be captured: decided 4 Nov 2026): fine chordwise cells over the band, cell = bubble length / 20 at the fine level F (decided 6 Nov; first: at level C; bubble length from our XFOIL table at the local Re); band cell 0.5 % c at F where the local Re ≥ 4 × 10⁵ (decided 6 Nov); growth along the ring ≤ 1.25 at VC. Pending: the upper band written as 0–100 % c (+0.4 % cells at F); a per-wing band from the refine map (decision 65, candidate; now run at the four Re levels)",
     "chordwise 35 %", "Ansys CFX transition-model grid guidance (about 20 nodes per bubble, growth about 1.1, y⁺ about 1, 75–100 streamwise nodes); band edges from our 2-D strips (root angles 0–10°)",
     "Since 7 Nov: levels VC–F, lower band 0–100 % c (decision 74); at the four Re levels the refine map finds the upper transition past 85 % c at low Re, and the built band cells reach 100 % c on both sides. First: built at level C, with the upper band from the leading edge on every wing (Stage 2 choice 58). Refine map (decision 65, candidate): on washed-out outboard panels the generic band misses lower-surface transition near the leading edge (by 52–60 % c) and upper transition past 85 % c at low angle (by up to 15 % c); the shortest root bubbles (1.4–10.7 % c) get fewer than 20 cells (1.2–3.6× short)"),
    ("Trailing edge and blunt base", "Base drag, base flow, start of the wake",
     "Chordwise spacing 0.1 % of local chord at the edge; 8 cells (9 points) across the base at the coarse level",
     "edges and base 15 %", "Roadmap R-S.3, R-S.4 (laws 3, 6); DPW (8/12/16/24 cells), SPICES (≥ 8 at the fine level)",
     "Built: 0.1 % c at the corners; 8 base cells at level C (10, 14, 18 at M, F, FF)"),
    ("Panel breaks b1, b2", "Local suction peak, jump in the spanwise loading, slope break of the loft",
     "A mesh station exactly on every break; spanwise growth ≤ 1.3 away from it. Station count (Stage 2 starting values): gap 0.2 × local chord, at least 12 gaps per panel, growth 1.2",
     "spanwise 15 %", "Fix 3 (done in Stage 2); primer Track 2 (spanwise law with anchors); station count: law 8, our starting values",
     "Built: a station exactly on every loft station (b0–b3; since 7 Nov there is no trailing-edge switch station); growth 1.2 (checked 1.3)"),
    ("Tip and tip cap", "Smallest chord and Re, first stall on aft sweep, birth of the vortex",
     "Stations squeezed toward the tip so the last gap equals the cap's first cell; cap first cell = the tip station's first cell (refuse above 3×); outboard blocks 1.5 root chords beyond the tip, growth ≤ 1.15",
     "spanwise 15 %", "Roadmap R-S.1, R-V.3, R-V.5 (laws 9–12)",
     "Built: the last station gap = the tip first wall cell s0 (y⁺ = 1 at the tip Re). Tying the cap's first cell to it is a volume item (Stage 3). With C-H (proposal, pending) the outboard blocks must also resolve the tip vortex"),
    ("Near wake, trailing edge to 2 chords", "Wake sheet (velocity deficit), base flow, start of roll-up",
     "Overset plan, under review: wake box with cells of 0.0075 c (about 20 across the wake), tall and tilted to hold the wake from −5° to post-stall; starts inside the near-body mesh. C-H proposal (pending): one matched mesh for both solvers (SU2 has no overset), with the wake band sized for the whole angle range; its wake lines add about +45 % (30–60 %) cells on the wing blocks (rough, not measured)",
     "wake 15 %", "Roadmap R-V.6 (laws 17, 18); Chan et al. 2002", "Stage 3, not built (S8 had no designed wake: O-mesh)"),
    ("Far wake, 2 to 10 chords", "Downwash, induced drag, wake convection",
     "Overset plan, under review (C-H proposal, pending): wake-box cells grow from 0.0075 c to the background size",
     "wake 15 %", "Roadmap R-V.6", "Stage 3, not built"),
    ("Tip vortex core", "Roll-up and path of the tip vortex",
     "Overset plan, under review: a tube with 15–20 near-cubic cells across the core, starting about 2 chords behind the tip (the vortex forms within about 1 chord, inside the near-body mesh). With C-H (proposal, pending) there is no tube: the outboard blocks must resolve the core",
     "wake 15 %", "Roadmap R-V.6 (law 19); primer section 05", "Stage 3, not built"),
    ("Overlap between meshes", "Nothing leaks: the wake and the boundary layer pass between grids cleanly",
     "Overset plan, under review: ≥ 5 cells from each mesh, cell-size ratio ≤ 1.5, no overlap inside the boundary layer or at the tip, 0 orphan cells. With C-H (proposal, pending) there is no overlap",
     "—", "Roadmap R-V.7 (law 21); Chan et al. 2002; Kenway et al. 2017", "Stage 3 (step M3), not built"),
    ("Background and far field", "Domain error",
     "Background 0.03 c around the wing (overset plan, under review: C-H proposal, pending), coarsening outward; far field from 80 chords (ladder 40 / 80 / 160; unchanged with C-H)",
     "domain 10 % (of the total)", "Roadmap R-V.6 (laws 15, 16); DPW about 100 chords",
     "Stage 3, not built. S8 for reference: 40 chords; 40 → 60 moved drag 0.6–0.7 counts"),
    ("Every zone together", "Grid convergence (the error bar)",
     "Every spacing in every mesh refined by one ratio r ≥ 1.3; distances fixed",
     "—", "Roadmap R-V.8 (law 23); Celik et al. 2008",
     "Surface (Stage 2): every spacing ÷ 1.3 per level (C, M, F, FF), within 3 %; exception: the base cells 8 / 10 / 14 / 18 (ratios 1.25, 1.4, 1.29), so C → M is below 1.3 (decision 61). Volume: Stage 3. (S8: the outboard blocks did not refine with the family.)"),
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
    o = ['<svg class="dg" viewBox="0 0 1000 380" role="img" aria-label="Side view of the mesh zones around one section: wall layers on the whole surface, fine cells at the nose, at the trailing edge and across the blunt base, the near-body mesh reaching about two chords, a tilted wake box with cells of 0.0075 chord to two chords behind the trailing edge then growing to ten chords, and the background box of 0.03 chord. The wake box and the background box are the overset plan, under review: C-H proposal, pending">',
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
    o.append(f'<text class="lab muted" x="{x2 + 30:.0f}" y="{YC + 2}">tall and tilted: holds the wake from −5° to post-stall</text>')
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
    o.append(f'<line class="leader" x1="{X0 + 0.5 * C}" y1="{YC - 30}" x2="{X0 + 0.45 * C}" y2="{YC - 70}"/><text class="lab" x="{X0 + 0.1 * C:.0f}" y="{YC - 76}">wall layers: y⁺ ≤ 1, growth ≤ 1.25 (about 1.1 with transition: pending), ≥ 30 cells</text>')
    o.append(f'<text class="lab muted" x="{X0 + 0.05 * C:.0f}" y="{YC + 50}">transition band (built): fine cells 0–100 % c on both sides (upper written 0–85 %)</text>')
    o.append('<text class="lab muted" x="50" y="372">schematic, not to scale (the far wake is compressed); wake box and background box: overset plan, under review (C-H proposal, pending)</text>')
    o.append("</svg>")
    return "\n".join(o)


def fig_refine_top() -> str:
    """Top view: spanwise stations, breaks, tip, outboard blocks, wake box and vortex tube."""
    st = [(90, 80, 220), (270, 160, 125), (430, 215, 75), (600, 262, 30)]
    le = " ".join(f"{y},{x}" for y, x, c in st)
    te = " ".join(f"{y},{x + c}" for y, x, c in reversed(st))
    o = ['<svg class="dg" viewBox="0 0 1000 470" role="img" aria-label="Top view of the mesh zones: stations nearly even from the root and squeezed toward the tip, a station on each break b1 and b2, outboard blocks reaching 1.5 root chords beyond the tip, the wake box behind the whole trailing edge, and a vortex tube starting about two chords behind the tip. The wake box and the tube are the overset plan, under review: C-H proposal, pending">']
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
    o.append('<text class="lab amber" x="350" y="96" text-anchor="middle">a station exactly on each break (b1, b2; built)</text>')
    o.append('<line class="leader" x1="560" y1="268" x2="720" y2="120"/><text class="lab" x="726" y="118">stations squeezed toward the tip:</text>')
    o.append('<text class="lab" x="726" y="134">last gap = tip first cell (built)</text>')
    o.append('<text class="lab muted" x="96" y="60">stations nearly even from the root</text>')
    o.append('<line class="dash" x1="90" y1="40" x2="90" y2="450"/>')
    o.append('<text class="lab muted" x="96" y="464">wake box and tube: overset plan, under review (C-H proposal, pending)</text>')
    o.append("</svg>")
    return "\n".join(o)


# Where each input range comes from (filled from the source review; key -> text)
RANGE_BASIS = {
    'aspect_ratio':
        "Real wings: tailless 2.9–8.6 and the ScanEagle 12.4 (NTNU; flying wing only), conventional 4.9–16.0 (<a href='#real'>Real wings</a>); flying wing 4.29 (<a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić 2024</a>). <span class='flag ok'>checked</span> Panknin's example has AR 10 (a model glider): above the real tailless wings (2.9–8.6), inside the flying-wing focus range (3–13).",
    'b3_ratio':
        "Our choice. With b1 = (1 − f<sub>3</sub>) · s and b2 = 1 − f<sub>3</sub>, the breaks sit at 15–56 % (b1) and 45–80 % (b2) of the semi-span in the focus space, and anywhere in 8–85 % in the full space. BWB: outer panel 0.50 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou 2022</a>). <span class='flag ok'>checked</span>",
    'split_ratio':
        "Our choice. BWB: 0.48 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou 2022</a>). <span class='flag ok'>checked</span>",
    'c2_ratio':
        "BWB 0.61 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou 2022</a>), 0.67 (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline &amp; Agarwal 2017</a>). <span class='flag ok'>checked</span> Cranked: constant-chord centre (0.95–1), tapered outer panels; overall taper 0.38–0.85 (Raymer about 0.4 unswept, <a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>; layout as on Hermes 450 and Heron, from photos). <span class='flag open'>second-hand</span>",
    'c3_ratio':
        "BWB 0.39 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou</a>), 0.42 (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline</a>). <span class='flag ok'>checked</span>",
    'c4_ratio':
        "BWB 0.14 (<a href='https://www.mdpi.com/2226-4310/9/1/36'>Wang &amp; Zhou</a>), 0.13 (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline</a>). Tapered: about 0.4 (Raymer, <a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>) to 1 (Pioneer, Shadow: <a href='https://m-selig.ae.illinois.edu/ads/aircraft.html'>Lednicer</a>). Flying wing: 0.667 (<a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić</a>), 0.85 (<a href='https://www.b2streamlines.com/Panknin/Panknin.html'>Panknin</a>), Aquila 0.58. <span class='flag ok'>checked</span>",
    'sweep1_deg':
        "BWB 15° (<a href='https://www.icas.org/ICAS_ARCHIVE/ICAS2012/PAPERS/675.PDF'>Lehmkuehler 2012</a>), 30° c/4 (<a href='https://www.mdpi.com/2226-4310/9/5/275'>Suewatanakul 2022</a>). Flying wing 25° (<a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić</a>), Aquila 28°, 35° (<a href='https://www.icas.org/ICAS_ARCHIVE/ICAS2008/PAPERS/335.PDF'>PUL-10</a>), 40° (<a href='https://www.mdpi.com/2072-666X/11/6/553'>MAV, Shams 2020</a>) <span class='flag open'>agent only</span>. Conventional: near 0° c/4 at low speed (Raymer, <a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>); −5° keeps a small forward-sweep edge case. <span class='flag ok'>checked</span> <span class='flag open'>second-hand</span>",
    'sweep2_deg':
        'As panel 1, a little less outboard on the BWB (sweep falls toward the tip on the BWB papers).',
    'sweep3_deg':
        'As panel 2.',
    'twist0_deg':
        "Washout (tip below root). Conventional: at most 5°, Raymer about 3° (<a href='https://computationaldesignlab.github.io/aircraft-design/wing_layout.html'>via course page</a>) <span class='flag open'>second-hand</span>. BWB 3° (<a href='https://www.mdpi.com/2226-4310/9/5/275'>Suewatanakul</a>), 7° (<a href='https://core.ac.uk/download/233235722.pdf'>Hainline</a>) <span class='flag ok'>checked</span>. Flying wing 3.2° (<a href='https://www.b2streamlines.com/Panknin/Panknin.html'>Panknin</a>) <span class='flag ok'>checked</span>.",
    'twist1_deg':
        'Between root and tip twist (see twist at the root).',
    'twist2_deg':
        'Between root and tip twist (see twist at the root).',
    'twist3_deg':
        'Total washout: conventional 0–5°, flying wing 0–8°, BWB 1–9° (see twist at the root).',
    'dihedral_p1_deg':
        '"Normally the dihedral is about 0 to 5 degrees or so" (<a href=\'https://aircraftdesign.com/?p=132\'>Raymer</a>). BWB 5° (<a href=\'https://www.mdpi.com/2226-4310/9/5/275\'>Suewatanakul</a>). Flying wing 4° (<a href=\'https://www.icas.org/ICAS_ARCHIVE/ICAS2008/PAPERS/335.PDF\'>PUL-10</a>), 2° (<a href=\'https://www.mdpi.com/2072-666X/11/6/553\'>MAV</a>) <span class=\'flag open\'>agent only</span>. <span class=\'flag ok\'>checked</span>',
    'dihedral_p2_deg':
        'Same as panel 1.',
    'dihedral_p3_deg':
        'Same as panel 1.',
    'airfoils':
        "BWB: MH 104 body, MH 61 wing (<a href='https://www.mdpi.com/2226-4310/9/5/275'>Suewatanakul 2022</a>). Conventional: NACA 4415 on Pioneer and Shadow 200 (<a href='https://m-selig.ae.illinois.edu/ads/aircraft.html'>Lednicer</a>). Flying wing: Hepperle tailless sections (<a href='https://www.mh-aerotools.de/airfoils/mh60koo.htm'>MH 60</a>: Re ≥ 1.5 × 10⁵, root; <a href='https://www.mh-aerotools.de/airfoils/mh45koo.htm'>MH 45</a>: lower Re, tip); MH 60 on <a href='https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf'>Milenković-Babić</a>. <span class='flag ok'>checked</span>",
}

INPUT_ROWS = [
    # (group, label, symbol, unit, variables per type: one name, or None when the type derives it)
    ("Size", "Aspect ratio (= full span in mean chords)", "AR", "", "aspect_ratio"),
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
    ("Panel shares of the semi-span", "f<sub>1</sub> = (1 − f<sub>3</sub>) · s,  f<sub>2</sub> = 1 − f<sub>1</sub> − f<sub>3</sub>", "all"),
    ("Chord ratios r<sub>i</sub> = c<sub>i</sub> / c<sub>r</sub>",
     "BWB: (1, r<sub>1</sub>, r<sub>2</sub>, r<sub>3</sub>). Cranked: (1, r<sub>1</sub>, r<sub>1</sub>r<sub>2</sub>, r<sub>1</sub>r<sub>2</sub>r<sub>3</sub>). Tapered, flying wing: r(y) = 1 + (λ − 1) · y / S, so r<sub>1</sub>, r<sub>2</sub> follow", "all"),
    ("Mean chord ratio", "K = Σ f<sub>i</sub> · (mean true chord of panel i) / c<sub>r</sub>: (r<sub>i−1</sub> + r<sub>i</sub>) / 2 when the twist does not change along the panel; with a twist change the chord turns and is a little shorter mid-panel (exact, 32-point Gauss)", "all"),
    ("Semi-span", "S = AR / 2 (in mean chords; every wing at unit mean chord since 7 Nov 2026). <span class='muted'>First approach: S = AR · c<sub>r</sub> · K / 2, with c<sub>r</sub> sampled in metres</span>", "all"),
    ("Root chord", "c<sub>r</sub> = 1 / K (in mean chords; no longer sampled)", "all"),
    ("Full span, area, mean chord", "b = 2S = AR,  A = b · c̄ = AR,  c̄ = A / b = c<sub>r</sub> K = 1 (unit mean chord: every length in mean chords)", "all"),
    ("Mean aerodynamic chord", "MAC = ∫c² dy / ∫c dy (exact for straight panels)", "all"),
    ("Station positions along the semi-span", "y<sub>0</sub> = 0,  y<sub>i</sub> = y<sub>i−1</sub> + f<sub>i</sub> S", "all"),
    ("Sweeps 2 and 3", "Λ<sub>2</sub> = Λ<sub>3</sub> = Λ<sub>1</sub> (one straight leading edge)", "tapered, flying wing"),
    ("Leading-edge positions", "x<sub>i</sub> = x<sub>i−1</sub> + tan Λ<sub>i</sub> · f<sub>i</sub> S", "all"),
    ("Station heights", "z<sub>i</sub> = z<sub>i−1</sub> + tan Γ<sub>i</sub> · f<sub>i</sub> S  (sections vertical, root in y = 0)", "all"),
    ("Overall taper", "λ = c<sub>tip</sub> / c<sub>r</sub>", "all"),
    ("Trailing-edge thickness", "t = 0.2 % · c (the local chord) on every wing; opened over the last 10 % of chord. <span class='muted'>First approach: t = max(floor, 0.2 % · c), floor 0.5 mm (Class I) or 1.0 mm (Class II)</span>", "all"),
    ("Real size of a published wing", "lengths × <code>real_mean_chord_m</code> = metres (the copy is built at unit mean chord)", "published"),
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


def vsets_max() -> dict:
    """Worst section and aspect-ratio errors over every type, for the text under the table."""
    f = DOCS / "verification_sets.json"
    if not f.is_file():
        return {"__VS_SEC__": "—", "__VS_AR__": "—"}
    sm = json.loads(f.read_text())["summary"].values()
    return {"__VS_SEC__": f"{max(r['sections_pct'] for r in sm):.2g}", "__VS_AR__": f"{max(r['ar_pct'] for r in sm):.5f}"}


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
        kind = "Tailless (BWB)" if meta["kind"] == "bwb" else "Conventional"
        use = meta.get("use", "BWB dataset design (FUN3D RANS, Spalart–Allmaras), 12,490 published solutions in BlendedNet++.")
        secs = ", ".join(dict.fromkeys(s.airfoil.name for s in st))
        src = "<br>".join(html.escape(s) for s in meta["sources"])
        out.append(
            f"<tr><td class='what'>{html.escape(meta['title'])}<span class='id'>{name}</span></td>"
            f"<td><span class='tag {meta['kind']}'>{kind}</span></td>"
            f"<td class='num'>semi-span {pf.semi_span * meta['real_mean_chord_m']:.3g} m<br>AR {aspect_ratio(pf):.2f}<br>"
            f"MAC {mean_aero_chord(pf) * meta['real_mean_chord_m']:.3g} m<br><span class='muted'>built at c̄ = 1;<br>"
            f"× {meta['real_mean_chord_m']:.3g} m</span></td>"
            f"<td>{html.escape(use)}</td>"
            f"<td>{html.escape(meta['fidelity'])}<br><span class='muted'>Sections: {html.escape(secs)}</span></td>"
            f"<td class='src'>{src}</td></tr>")
    return "\n".join(out)


def change_table() -> str:
    """What was first (built and studied 30 Oct–6 Nov 2026) and what changes on 7 Nov 2026 (decisions 64 and 70)."""
    rows = [
        ("Size (similarity, decision 70)",
         "Every wing at real size. The root chord was sampled in metres (BWB 0.40–1.80 m; cranked and tapered 0.13–0.75 m; flying wing 0.25–1.05 m); semi-span S = AR · c<sub>root</sub> · K / 2.",
         "Every wing at <strong>unit mean chord</strong>: mean chord = area / full span = 1. Lengths are in mean chords. The root chord left the vector: 18 → 17 names (c2–c4 ratios, semi_span_m, aspect_ratio, b3_ratio, split_ratio, sweep1–3, twist0–3, dihedral_p1–3, plus 4 airfoils); 16 sampled for BWB and cranked, 12 for tapered and flying wing. S = AR / 2; root chord = 1 / K.",
         "you, 6 Nov", "built 7 Nov"),
        ("Mean chord",
         "Area / full span in the code; some texts said MAC.",
         "Area / full span: the geometric mean chord, not the MAC (on a BWB the MAC is 1.09–2.06 × larger). It is 1 on every wing; the MAC is only measured.",
         "Stage 0, 7 Nov", "built 7 Nov"),
        ("Re and Mach",
         "Re followed from the real size and the real speeds of each family: focus 5.4 × 10⁴ – 3.5 × 10⁶ on the mean chord; Mach 0.03–0.20.",
         "The Re on the mean chord is an <strong>input of each solve</strong>: the four Stage 0 levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ (since 8 Nov; were 1.5 × 10⁶ and 3 × 10⁶). Real Class I–II wings fly at 1.22 × 10⁵ – 3.10 × 10⁶ (on area / full span), so 1 × 10⁵ sits 18 % below the slowest real UAV: kept as a margin. Mach 0.1 with a Prandtl–Glauert correction on CL and CM, on the solver side (check C2).",
         "levels: Stage 0; margin: you, 7 Nov", "input of each solve"),
        ("Trailing edge",
         "Class I max(0.5 mm, 0.2 % c), Class II max(1.0 mm, 0.2 % c); a section added where the rule switched. Edges 0.20–4.17 % c; 370 of the 730 wings had an edge set by a floor.",
         "<strong>0.2 % of the local chord on every wing.</strong> No floors, no wing class, no switch section; a config that still names a size is refused. Check C3 (CFD, to come): 0.1 / 0.2 / 0.3 % c and the real floor of small wings, about 0.42 % c.",
         "you, 6 Nov", "built 7 Nov"),
        ("Full-span cap",
         "The focus space ended at full span b = 7 m: the focus sets kept only wings within it.",
         "Gone. At unit mean chord the full span is the aspect ratio, which has its own range.",
         "with 70", "built 7 Nov"),
        ("Sets",
         "730 wings built (numpy loft). Focus sets: a Latin hypercube, wings above 7 m dropped in draw order. Corner 1: 34 or 26 wings.",
         "722 of 722 built (7 Nov, numpy loft). Focus sets: the same 200-row draw, the first 100 kept, so 99 / 90 / 91 / 88 of the 100 focus shapes are the same (BWB / flying wing / cranked / tapered; the cap had chosen by root chord). Training full, hold-out full and corner 2 keep their shapes; corner 1 has 32 or 24 wings (the two root-chord corners went). Chords 0.062–3.60 mean chords; aspect ratio = full span in mean chords, 2.5–20.",
         "with 70", "built 7 Nov"),
        ("Reference picks",
         "Mid-range; smallest and largest area; most sweep with the smallest tip; strongest washout.",
         "Smallest / largest area → lowest / highest aspect ratio (at unit mean chord the area is the aspect ratio); the tip chord is ranked in mean chords. 13 of the 20 reference wings are new picks; 7 are kept (the 4 mid-range wings and 3 of the 4 strongest-washout wings).",
         "with 70", "built 7 Nov"),
        ("Labels",
         "A value exactly at a threshold could lose its label by rounding: 35 wings at exactly 1.0° washout had no washout label.",
         "A tolerance of 1e-9: a value at the threshold gets the label.",
         "7 Nov (fix)", "built 7 Nov"),
        ("Nose rule (decision 64)",
         "Leading edge at the farthest raw point; each side resampled in √x with a square tangent (PCHIP), 101 points per side. Along the arc: a curvature spike on one side, a flat spot on the other; the 5 % turning-per-cell test failed on all ten suggested airfoils (NACA 4415: a 0.18 % c nose cell turned 9.47°; the true shape turns 4.31°).",
         "One cubic spline through the raw points (natural ends at the trailing edge); leading edge = its apex (the spline point farthest from the trailing-edge midpoint); both sides sampled from that spline, <strong>201 points per side</strong>. Passes on all ten (worst −3.9 %) and on 95.6 % of the database (old rule 21.0 %). Side effects: the leading edge moves by a median 0.046 % c (max 1.69 % c); the chord line turns by a median 0.027° (max 0.96°; NACA 4415 0.12°).",
         "you, 7 Nov", "built 7 Nov"),
        ("Nose gate",
         "None.",
         "A section whose nose folds back (curvature below −1000/c within 3 % c of arc) is refused: 14 database files, none used.",
         "with 64", "built 7 Nov"),
        ("The 6 Nov nose note (item 75)",
         "“The first reading was overstated: measured the same way, the raw files show nearly the same split.”",
         "<strong>That note was wrong.</strong> The one-sided formula read the raw points, and the built section passes through them, so it saw the same split. The defect sat between the raw points. Measured along the arc the built split was real, and larger at the leading edge than first read (NACA 4415 radius 0.0018 / 0.155 c, not 0.008 / 0.074 c).",
         "7 Nov (study)", "corrected"),
        ("Section tables (2-D XFOIL)",
         "2,408 sweeps (10 airfoils + 3 blends, 14 Re × 3 Mach × 49 angles) on the sections of the old nose rule.",
         "<strong>Rebuilt on the fixed nose</strong> (7 Nov, 40 min). Upper transition moves a median 0.19 % c (95 % of points within 1.5 % c), drag a median 0.8 %; the larger changes sit near the 2-D stall and at high Re. SA drag error on the 20 reference wings × 4 Re levels × 0–10°: +59.0 % median (+58.1 % on the old tables); the model category is the same on 480 of 480 conditions. No Stage 1 conclusion changes.",
         "with 64", "rebuilt 7 Nov"),
        ("Flow maps and flow dataset",
         "Flow maps and 201,600 dataset rows: the focus wings at real size and real speed (Mach 0.03–0.20, root angles 0–10°, 3 altitudes), from the section tables.",
         "<strong>Not rebuilt</strong>: they stay the first-approach record. In similarity form each shape would run at the four Re levels instead of speeds and altitudes, and the level-flight flag needs a real size. The 2-D section tables are size-free; they were rebuilt on the fixed nose (row above).",
         "—", "not rebuilt"),
        ("Hashes, pyGeo, Stage 2",
         "Stored hashes stale since the 2 Nov rename; Stage 2 meshed the 730 first-approach wings (790 builds).",
         "Every geometry hash changed on 7 Nov; the sets are rebuilt with the numpy loft, and on 8 Nov with pyGeo on your machine (722 of 722; the manifests now say pygeo). Stage 2 screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (every set at VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels), and on 8 Nov every set at every level: 3,128 of 3,128, with no nose repair (one factor per family).",
         "—", "owed"),
    ]
    flag = {"built 7 Nov": "ok", "rebuilt 7 Nov": "ok", "input of each solve": "ok", "corrected": "fix", "not rebuilt": "open", "owed": "open"}
    out = ['<div class="tbl"><table class="wide"><thead><tr><th>What</th><th>First (30 Oct–6 Nov 2026)</th>'
           '<th>Now (7 Nov 2026)</th><th>Decided</th><th>Status</th></tr></thead><tbody>']
    for what, first, new, when, st in rows:
        out.append(f"<tr><td class='what'>{what}</td><td class='first'>{first}</td><td class='new'>{new}</td>"
                   f"<td class='when'>{when}</td><td><span class='flag {flag[st]}'>{st}</span></td></tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


NOSE_NAME = {"naca4415": "NACA 4415", "e387": "E387", "sd7032": "SD7032", "mh104": "MH 104", "mh61": "MH 61",
             "mh45": "MH 45", "mh60": "MH 60", "s5010": "S5010", "la2573a": "LA2573A", "naca25118": "NACA 25118"}


def nose_table() -> str:
    """The ten study airfoils of decision 64 (data/studies/nose_curvature.json): old rule and new rule against the raw file."""
    d = json.loads((ROOT / "data" / "studies" / "nose_curvature.json").read_text())
    h = d["meta"]["h_pct"]
    i04, i18 = h.index(0.04), h.index(0.18)
    pc = lambda x: "0.0" if round(x, 1) == 0 else f"{x:+.1f}".replace("-", "−")  # noqa: E731
    jf = lambda x: f"{x:.0f}" if x >= 10 else f"{x:.2f}" if x >= 1.15 else f"{x:.3f}"  # noqa: E731
    out = []
    for k, a in d["airfoils"].items():
        c = a["curves"]
        jo = a["old_le_one_sided"]; jn = a["new_le_one_sided"]
        jump = lambda j: max(j["R_le_upper_c"], j["R_le_lower_c"]) / min(j["R_le_upper_c"], j["R_le_lower_c"])  # noqa: E731
        ok = lambda p: "<span class='flag ok'>pass</span>" if p else "<span class='flag fix'>fail</span>"  # noqa: E731
        out.append(f"<tr><td class='what'>{NOSE_NAME.get(k, k)}</td><td class='num'>{a['n_points']}</td>"
                   f"<td class='num'>{c['raw']['R_min_c']:.4f}</td><td class='num'>{c['old']['R_min_c']:.4f}</td>"
                   f"<td class='num'>{c['new']['R_min_c']:.4f}</td>"
                   f"<td class='num'>{pc(c['old']['T_diff_vs_raw_pct'][i04])} / {pc(c['old']['T_diff_vs_raw_pct'][i18])} {ok(a['old_passes'])}</td>"
                   f"<td class='num'>{pc(c['new']['T_diff_vs_raw_pct'][i04])} / {pc(c['new']['T_diff_vs_raw_pct'][i18])} {ok(a['new_passes'])}</td>"
                   f"<td class='num'>{jf(jump(jo))} / {jf(jump(jn))}</td>"
                   f"<td class='num'>{a['le_move_pct']:.3f} / {a['chord_turn_deg']:+.3f}°</td></tr>".replace("+-", "−"))
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
.tag.cranked, .tag.tapered { color: var(--accent); } .tag.bwb { color: var(--bwb); } .tag.flying_wing { color: var(--amber); }
.basis.req { color: var(--violet); } .basis.src { color: var(--accent); } .basis.meas { color: var(--bwb); } .basis.own { color: var(--amber); }
.flag.fix { color: var(--warn); } .flag.open { color: var(--amber); } .flag.ok { color: var(--bwb); } .flag.later { color: var(--muted); }
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
svg.dg .stepbox { fill: var(--surface); stroke: var(--line); stroke-width: 1.2; } svg.dg .arrowhead { fill: currentColor; }
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
.cbox { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--bwb); border-radius: 6px; padding: 10px 14px; font-size: 15px; line-height: 1.5; max-width: 100%; }
.cbox .ctag { display: block; font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--bwb); margin-bottom: 2px; }
.cbox.chg { border-left-color: var(--amber); background: color-mix(in srgb, var(--amber) 6%, var(--surface)); } .cbox.chg .ctag { color: var(--amber); }
.cbox ul { margin: 4px 0 0; padding-left: 20px; display: flex; flex-direction: column; gap: 4px; }
td.new { font-size: 13.5px; background: color-mix(in srgb, var(--amber) 7%, transparent); width: 44%; min-width: 300px; }
td.first { font-size: 12.5px; color: var(--muted); width: 28%; min-width: 220px; line-height: 1.45; }
td.when { font-size: 12.5px; color: var(--muted); width: 10%; min-width: 90px; }
.fa { display: inline-block; align-self: flex-start; font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: #FFFFFF; background: #9A6200; border-radius: 3px; padding: 2px 8px; margin: 0 0 6px; line-height: 1.4; max-width: 100%; }
.flag.chg { color: var(--amber); } .flag.gone { color: var(--muted); }
li .flag { white-space: normal; display: inline-block; max-width: 100%; }
figcaption .howto { color: var(--ink); font-weight: 600; }
ol.concl { margin: 0; padding-left: 22px; display: flex; flex-direction: column; gap: 8px; max-width: 80ch; }
ol.concl li strong { color: var(--ink); }
footer { color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 12px; }
@media (prefers-reduced-motion: reduce) { .card img[src^="data:image/gif"] { animation: none; } }
</style>
<div class="wrap">
<header>
  <div class="eyebrow">CFD_Automation · Stage 1 · geometry · code __VERSION__ · updated 8 Nov 2026</div>
  <h1>Wing Generator</h1>
  <p class="lede">Seventeen numbers and four airfoil names go in; one exact wing surface comes out, measured, labelled and checked. One generator and one YAML file make BWB, cranked, tapered and flying wings, shaped like real Class I and II UAVs. Since 7 Nov 2026 every wing is built at unit mean chord: it has no size, and size enters the CFD only as the Re on the mean chord. On the same day the nose rule changed, so the built nose now follows the airfoil file. Every later stage (mesh, solver, data) reads only this surface. The section <a href="#change">What was first, and what changes</a> and an amber <em>What changes</em> box in every section it touches say what the two changes changed.</p>
  <nav aria-label="On this page"><a href="#glance">At a glance</a><a href="#change">What changes (7 Nov)</a><a href="#pipeline">The plan</a><a href="#runs">What was run</a><a href="#summary">Final ranges and flows</a><a href="#design">Design space</a><a href="#pairs">Key pairs</a><a href="#family">Wing families</a><a href="#ranges">Shapes</a><a href="#inputs">Parameters</a><a href="#nose">Nose study</a><a href="#reynolds">Re and Mach</a><a href="#greek">Greek UAVs</a><a href="#phenomena">Flow phenomena</a><a href="#flowmaps">Flow maps</a><a href="#flowdata">Flow dataset</a><a href="#refine">Where to refine</a><a href="#open">Open decisions</a><a href="#decisions">Design decisions</a><a href="#fix">Fixes</a><a href="#build">One wing, step by step</a><a href="#real">Real wings</a><a href="#checks">Checks and results</a><a href="#limits">What it cannot make</a><a href="#published">Published wings</a><a href="#commands">Commands</a></nav>
</header>

<section id="glance">
  <h2>At a glance</h2>
  <div class="weak" style="margin-bottom:14px"><strong>Words used on this page.</strong> <strong>Full span b</strong>: tip to tip, both halves. <strong>Semi-span S = b / 2</strong>: root to one tip, the half wing we build and mesh (mirrored at y = 0). <strong>Families</strong>: tailless (types BWB, flying wing) and conventional (types cranked, tapered). <strong>Focus space</strong>: realistic wing shapes, sampled densely. <strong>Full space</strong>: everything supported, sampled sparsely. <strong>Mean chord c̄</strong> = area / full span (not the MAC). <strong>Unit mean chord</strong>: every wing is built with c̄ = 1, so lengths are in mean chords and the full span equals the aspect ratio. <strong>First approach</strong>: what was built and studied at real size, 30 Oct–6 Nov 2026.</div>
  <div class="three">
    <div class="box"><h3>In</h3><div class="big">17 numbers + a wing type</div><p>From <code>configs/wing.yaml</code>: the aspect ratio (the semi-span follows: AR / 2), panel shares, chord ratios, sweeps, twists, dihedrals, and an airfoil per station. Types: BWB, cranked, tapered, flying wing. No size: every wing at unit mean chord (the root chord left the vector on 7 Nov: 18 → 17).</p></div>
    <div class="box"><h3>Out</h3><div class="big">One surface, checked</div><p>Upper, lower and trailing-edge base, read as <code>upper(u, v)</code>. Plus measured values, labels, four refusing checks, a hash, IGES.</p></div>
    <div class="box"><h3>Evidence</h3><div class="big">__OK__ of __BUILT__ wings pass</div><p>Sampled wings of all four types, focus and full space, 0 refused (__SETVER__). __PUBOK__ of __PUB__ published wings verified (ONERA M6, RIBES, NASA CRM and four BlendedNet designs). Tests: __TESTS__.</p></div>
    <div class="box verdict"><h3>Verdict</h3><div class="big">Stage 1 closed; Stage 2 under way</div><p>Fixes 1–3 done: panel dihedrals and code hash here; a mesh station on every break, made by the Stage 2 surface mesher (790 of 790 builds pass its 13 checks, on the first-approach wings). Done on 7 Nov: similarity (decision 70) and the nose fix (decision 64); every hash changed and the sets were rebuilt. Done on 8 Nov on your machine: the pyGeo tests (24 of 24) and <code>build --all</code> with pyGeo (722 of 722). Fixed on 8 Nov: the label rules at a threshold (decision 79; every input hash changed, no surface). Still owed in Stage 1: one more pyGeo <code>build --all</code> and the push of the raw XFOIL data. Stage 2 has screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (every set at VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels, again on 8 Nov at the new Re levels; 4 F builds after one nose repair). Not yet "any wing": straight panels only, no airfoil shape variable. Sets: __STALE__</p></div>
  </div>
  <div class="weak amber"><strong>What changed since 2 Nov 2026 (updated 8 Nov).</strong>
    <ul>
      <li><strong>Decided.</strong>
        <ul>
          <li>Repo renamed: <code>Stage_1_geometry/</code>; one shared <code>cfdauto</code> package (<code>pip install -e CFD_Automation</code>); sets <code>training_focus</code> / <code>holdout_focus</code>; one <code>CFD_Automation/OPEN_DECISIONS.md</code> for all stages.</li>
          <li>The Stage 2 surface mesh works: 790 of 790 builds pass 13 checks (numpy loft). It puts a station on every loft station, so one sits on every break (fix 3 done); the tip squeeze and the transition band are built.</li>
          <li>Transition must be captured, with ADflow and SU2 (4 Nov).</li>
          <li>Angles of attack: −5° to post-stall, plus a separate post-stall study (6 Nov).</li>
          <li>The Mach scope extends toward 0.5, with no supersonic flow (4 Nov); the data on this page stop at Mach 0.2.</li>
          <li>First SU2 smoke test (4 Nov): SU2 ran SA and LM on one Stage 2 ring mesh (a section extruded between two symmetry planes, 97,920 cells, Re 3 × 10⁵, Mach 0.15, 4°); after about 370 iterations, not converged: SA CL 0.860, CD 0.0184; LM CL 0.908, CD 0.0137. It shows the mesh path works; no wing has been run.</li>
          <li><strong>Re levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ (you, 8 Nov; were 1.5 × 10⁶ and 3 × 10⁶):</strong> the Greek tactical programmes (LOTUS, Archytas, ACTUS) are in scope, and 1 × 10⁶ fills the old ×5 gap (check C4 on 2-D data). Same 8,000 solves. The 2-D section tables gain the rows 1 × 10⁷ and 1.5 × 10⁷. See <a href="#greek">Greek UAVs and the Re levels</a>.</li>
          <li><strong>Label tolerance, built 8 Nov (decision 79; you):</strong> every label rule now takes a value exactly at its threshold (the kink tests had no tolerance: on a sweep change of exactly 5° the pyGeo and numpy lofts disagreed; a wing at AR exactly 8 missed its label). 2 labels changed, no type; every input hash changed; the surfaces and meshes did not.</li>
          <li><strong>Similarity, built 7 Nov (decision 70):</strong> every wing at unit mean chord; the root chord out of the vector (18 → 17); trailing edge 0.2 % c on every wing; no 7 m cap; the Re on the mean chord is an input (the four levels, kept). 722 of 722 wings built.</li>
          <li><strong>Nose fix, built 7 Nov (decision 64):</strong> leading edge at the apex of one cubic spline through the raw points, both sides from that spline, 201 points per side; a nose gate. The 6 Nov note that the nose finding was overstated (item 75) was wrong.</li>
        </ul></li>
      <li><strong>Proposals (pending).</strong>
        <ul>
          <li>One matched C-H volume mesh for both solvers (SU2 has no overset).</li>
          <li>Solver split: ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings.</li>
          <li>Mesh cost: at the fine level 15.2 M cells (median) with the planned rules, 10.9 M with a relaxed band (0.5 % c spacing where local Re ≥ 4 × 10⁵).</li>
          <li>Mach: core data at Mach ≤ 0.2 now; 0.3–0.5 later, with a fast-UAV family.</li>
        </ul></li>
      <li><strong>Open.</strong>
        <ul>
          <li>One more <code>build --all</code> with pyGeo on your machine: the label fix of 8 Nov changed every input hash.</li>
          <li>Similarity checks C1–C4 (CFD): scale, Mach, trailing edge, Re levels.</li>
          <li>Push the raw XFOIL data.</li>
        </ul></li>
    </ul></div>
</section>

<section id="change">
  <h2>What was first, and what changes (7 Nov 2026)</h2>
  <p>Stage 1 was built and studied with a first approach from 30 Oct to 6 Nov 2026: every wing at real size, in metres. On 7 Nov two changes went into the code. <strong>Similarity</strong> (decision 70, decided by you on 6 Nov): every wing is built at unit mean chord, so a wing has no size, and size enters each solve as the Re on the mean chord. <strong>The nose fix</strong> (decision 64, decided by you on 7 Nov): the built nose now follows the airfoil file at the size of a mesh cell. The code, the tests and the wing sets are done. This page keeps the first-approach content where it is still the record (what was built and studied 30 Oct–6 Nov), marks it <span class="fa">first approach</span>, and says in an amber <em>What changes</em> box in every section what changed there.</p>
  __CHANGE_TABLE__
  <div class="cbox"><span class="ctag">Conclusion</span>Two changes, both built. Similarity takes size out of the geometry: one mesh family per shape serves every size, and the four Re levels (which cover the real wings) set the size of each solve. The nose fix makes the built nose turn like the airfoil within 5 % per mesh cell on all ten suggested airfoils (it failed on all ten before). Both changed every hash; the 722 wings are rebuilt and checked. Still first approach: the flow maps and the flow dataset (made at real size before 7 Nov). Stage 2 has screened the 7 Nov wings: 1,724 of 1,724 builds pass (4 after one nose repair; the reference wings again on 8 Nov at the new Re levels, 320 of 320). The pyGeo build ran on 8 Nov (722 of 722; the same meshes on the reference wings). Owed: the similarity checks C1–C4.</div>
</section>

<section id="pipeline">
  <h2>The plan in five steps</h2>
  <p>From everything the generator can draw, down to the wings we study, to what the flow does on them, to a tool that does this for any wing.</p>
  <figure class="fig"><div class="svgwrap">__FIG_PIPE__</div></figure>
  <ol class="steps">
    <li><strong>Full design space</strong> (<a href="#design">Design space</a>): every input range we support, light bars.</li>
    <li><strong>What we can make</strong> (<a href="#limits">What it cannot make</a>, <a href="#checks">Checks</a>): straight panels, vertical sections, any database section; no curved edges, winglets or fuselage.</li>
    <li><strong>Focus</strong> (<a href="#summary">Final ranges and flows</a>): the shapes of Class I and small Class II wings, sourced; dark bars. Every wing at unit mean chord, run at the four Re levels.</li>
    <li><strong>Flow maps</strong> (<a href="#flowmaps">Flow maps</a>, <a href="#flowdata">Flow dataset</a>): local Re from root to tip, where the flow turns turbulent, bubbles, and how the sections change them, per family; then every focus wing × 4 section sets × 126 conditions, with trends, sensitivity and checks.</li>
    <li><strong>The tool</strong> (<code>python -m cfdauto.flowmap</code>): give it a wing, a speed (or Mach), an altitude and an angle; it names the family and type, draws the flow map, proposes the turbulence model with the size of the SA error, says whether the condition is level flight at a real wing loading, and where the wing sits in the dataset. <code>--sheet</code> adds the whole Mach × angle picture.</li>
  </ol>
  __CHG_PIPE__
  <div class="cbox"><span class="ctag">Conclusion</span>We look wide but study densely where real wings are. The generator makes the wings; 2-D flow runs on them say which turbulence model and which mesh refinement each wing needs; the tool does the same for any new wing.</div>
</section>

<section id="runs">
  <h2>What was run: 2-D, 3-D, and how 2-D becomes 3-D</h2>
  <p>No 3-D CFD has been run on a wing yet (a first SU2 smoke test ran on 4 Nov on one Stage 2 ring mesh: see <a href="#glance">At a glance</a>). All flow results on this page come from XFOIL, which solves one 2-D airfoil at a time. Strip theory turns those 2-D answers into wing results: the half wing is cut into strips, each strip is treated as its own airfoil at its own Re and angle, and the strips are added up.</p>
  <figure class="fig"><div class="svgwrap">__FIG_RUNS__</div></figure>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Study (section of this page)</th><th>What ran</th><th>Tool</th><th>How many</th></tr></thead>
    <tbody>
      <tr><td>Design space, Key pairs, Wing families, Sizes</td><td>planform maths on sampled design vectors</td><td>generator</td><td>1,500–2,000 vectors per type and space; no flow</td></tr>
      <tr><td>Checks and results</td><td>wings built, measured and checked</td><td>generator (numpy loft)</td><td>722 wings (7 Nov; 730 before)</td></tr>
      <tr><td>Nose study (decision 64)</td><td>curvature along the arc: raw files against the built sections</td><td>script, numpy loft</td><td>10 airfoils; 2,183 database files</td></tr>
      <tr><td>Real wings</td><td>real sizes and speeds against the generated wings (first approach)</td><td>database check</td><td>34 wings with an area, 112 full spans</td></tr>
      <tr><td>Reynolds and Mach</td><td>Re = (ρ / μ) · V · chord</td><td>formula</td><td>no runs</td></tr>
      <tr><td>Flow phenomena (2-D)</td><td>A: free vs tripped airfoils (rerun 7 Nov on the new sections)</td><td>XFOIL</td><td>32 polars (0–8°) + 32 runs at exactly 2°</td></tr>
      <tr><td>Flow maps</td><td>strip theory on the section tables (B)</td><td>flow-map engine</td><td>1 example + 24 focus maps</td></tr>
      <tr><td>Flow dataset</td><td>strip theory on the section tables (B)</td><td>flow-map engine</td><td>201,600 wing cases</td></tr>
      <tr><td>Flow dataset: sensitivity</td><td>statistics on the 201,600 cases</td><td>gradient-boosted model</td><td>no new flow runs</td></tr>
      <tr><td>Flow dataset: assumption checks</td><td>the same 80 wings with one assumption changed; tables vs direct</td><td>engine + XFOIL (C)</td><td>6 × 40,320 cases; 320 direct runs; 3 blend pairs</td></tr>
      <tr><td>Where the mesh must be fine</td><td>rules from Stage 0 and the roadmap (built since in Stage 2)</td><td>none</td><td>no runs</td></tr>
      <tr><td>3-D CFD on a wing</td><td>none yet; a first SU2 smoke test (SA and LM) ran on one Stage 2 ring mesh on 4 Nov, not converged</td><td>ADflow SA, SU2 SST + LM (planned)</td><td>0 wings</td></tr>
    </tbody>
  </table></div>
  __CHG_RUNS__
  <div class="cbox"><span class="ctag">Conclusion</span>No 3-D CFD has been run on a wing yet. Every flow number on this page is 2-D XFOIL, used alone (airfoil study) or added up along the semi-span by strip theory (wing results). These numbers show where to look and which model to use; 3-D CFD must confirm them before they go into the paper (proposal, pending: SU2 SST + LM on about 20 % of the wings first).</div>
</section>

<section id="summary">
  <h2>Final ranges and flows</h2>
  <p>Everything in one table, at unit mean chord. <strong>Bold</strong>: the focus space (realistic, sampled densely). <span class="fullr">Grey</span>: the full space (supported, sampled sparsely). Chords are in mean chords; the extremes come from all corners of the planform inputs (others mid-range). Study Re levels on the mean chord: 1 × 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶.</p>
  __CHG_SUMMARY__
  <div class="tbl"><table class="wide summ">__SUMMARY__</table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>Four types in two families, from one generator, every wing at unit mean chord. The focus aspect ratios run from 3 (tailless) to 16.5 (conventional); the BWB alone has a long root (up to __S_BWB_ROOT__ mean chords) and a small tip (down to __S_BWB_TIP__). Every shape runs at the four Re levels, which cover the real wings (1.22 × 10⁵ – 3.10 × 10⁶). Inside one wing the local Re reaches further: from about __S_BWB_RETIP__ at the smallest BWB tip (lowest level) to __S_BWB_REROOT__ at the largest BWB root (top level). Tailless wings are swept and washed out to fly without a tail; conventional wings are nearly straight. Every type needs a fine mesh at the leading and trailing edges, the tip and the wake.</div>
  <p class="muted">Details: <a href="#design">Design space</a>, <a href="#ranges">Shapes</a>, <a href="#reynolds">Re and Mach</a><a href="#greek">Greek UAVs</a>, <a href="#phenomena">Flow phenomena</a>, <a href="#refine">Where to refine</a>.</p>
</section>

<section id="design">
  <h2>Design space: what we support, where real wings are, where we focus</h2>
  <p>One row per variable, one lane per wing type. <strong>Light bar</strong>: the full space (everything the generator supports; 40 wings + 5 hold-out per type, both corner sets at its edges). <strong>Dark bar</strong>: the focus space (where real wings are; 100 wings + 5 reference + 10 hold-out per type). <strong>Black marks</strong>: real wings and published designs. Rows marked "derived" are computed from the inputs.</p>
  __CHG_DESIGN__
  <figure class="fig card">__PNG_DESIGN__<figcaption>Read a row left to right: if the black marks sit inside the dark bar, the focus space covers the real wings; the light bar shows how far beyond them we still promise to work. The first three rows are in mean chords: the aspect ratio (= the full span), the root chord (derived, 1 / K) and the tip chord (derived). Root twist only sets the incidence; washout is what changes the wing. Sources: <code>configs/shape_evidence.yaml</code>, <code>configs/real_uavs.yaml</code>.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Most real and published values (black marks) sit inside the dark focus bars, so the focus space covers real wings. A few sit only inside the light full-space bars: the lowest real tailless aspect ratio (2.9, just below the focus 3), a second-hand flying-wing washout of 10°, and one published range of the BWB chord at b2. The full space is needed, but rarely.</div>
  <div class="weak amber"><strong>What the figure shows honestly.</strong> Shape evidence is thin for conventional wings (Raymer rules, partly second-hand) and for the layout shares (one BWB paper). Aspect ratios are well covered (34 real wings). The full space is our choice, set to the widest value in any source; nothing real sits at its far edges.</div>
</section>

<section id="pairs">
  <h2>Key pairs</h2>
  <p>The same three layers in two dimensions, one panel per type. Faint dots: full space. Strong dots: focus space. Black diamonds: real or published wings that give both values.</p>
  __CHG_PAIRS__
  <figure class="fig card">__PNG_PAIR_SIZE__<figcaption><strong>Size, first approach</strong> (real size, before 7 Nov): full span b (tip to tip) against mean chord, in metres. Every real Class I–II wing with a published area, against its family (tailless: BWB and flying wing; conventional: cranked and tapered).</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>First approach: the focus space covered 32 of the 34 real wings with a published area (a generated wing within 10 % in full span and mean chord); the other two, Hermes 450 and Götten UAV 9, were larger than 7 m and only the full space covered them. Now this pair has no meaning: every wing has a mean chord of 1, and its full span is its aspect ratio (next figure). Size enters only as the Re on the mean chord, and the four levels cover the real wings (see <a href="#reynolds">Re and Mach</a><a href="#greek">Greek UAVs</a>).</div>
  <figure class="fig card">__PNG_PAIR_PLANFORM__<figcaption><strong>Planform</strong>: aspect ratio against overall taper. The BWB lives at very low taper (big centre body), the others at 0.3–1.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Taper separates the BWB from the rest: only the BWB has a very small tip (4–25 % of the root chord). The other three types overlap (taper 0.2–1), so the type rules use the kink and the root chord, not taper alone.</div>
  <figure class="fig card">__PNG_PAIR_SWEEP__<figcaption><strong>Sweep</strong>: aspect ratio against inner-panel leading-edge sweep. Published sweeps given at the quarter chord (marked c/4 in the sources) sit a few degrees below their leading-edge value.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Sweep separates the families. Tailless wings are swept to fly without a tail (BWB 15–40°, flying wing 10–40°, focus); conventional wings are nearly straight (cranked −3 to 3°, tapered −5 to 15°). The real wings sit inside these ranges.</div>
  <figure class="fig card">__PNG_PAIR_TWIST__<figcaption><strong>Trim</strong>: sweep against washout. Tailless wings trim with sweep and washout together; the published tailless wings sit inside the focus space.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Tailless wings need washout as well as sweep (focus: BWB 1–9°, flying wing 0–8°); conventional wings need little (0–5°). The published tailless wings that give both values sit inside the focus box.</div>
</section>

<section id="family">
  <h2>Wing families</h2>
  <p>For each type, one variable group at a time goes from the full minimum to the full maximum; all others stay at the focus mid-range. Columns 2–4 (solid) are the focus space; columns 1 and 5 (dashed) are the edges of the full space. Top views are scaled to equal full span so the shape is visible; aspect ratios and chords in mean chords are in <a href="#ranges">Shapes we can make</a>.</p>
  __CHG_FAMILY__
  <figure class="fig card">__PNG_FAM_BWB__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>BWB: aspect ratio, chords and sweep change the shape most. The solid (focus) shapes look like real BWBs; the dashed full-space edges (AR 2.5, 60° sweep, 16° washout) are extreme, but still valid wings the mesher must handle.</div>
  <figure class="fig card">__PNG_FAM_CONV__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Cranked: aspect ratio changes the shape most (stubby AR 4.5 to slender AR 16.5); the crank is mild and the sweep small. The dashed edges (−15° and 35° sweep, AR 20) are there only to test robustness.</div>
  <figure class="fig card">__PNG_FAM_TAP__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Tapered: like the cranked wing without the crank. Aspect ratio and taper set the shape; the sweep stays small (−5 to 15°). The dashed edges are there only to test robustness.</div>
  <figure class="fig card">__PNG_FAM_FW__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Flying wing: sweep and aspect ratio set the shape (10–40°, AR 3–13). Moving the breaks does not change its outline (straight edges); it only moves where the sections and the twist change.</div>
</section>

<section id="inputs">
  <h2>Parameters: inputs and derived</h2>
  <p>The generator samples only the <strong>inputs</strong> below. Everything else is <strong>derived</strong> from them by fixed formulas. Four stations: root b0, breaks b1 and b2, tip b3; three straight panels between them.</p>
  <div class="three">
    <div class="box"><h3>Full space</h3><div class="big">What we support</div><p>Wider ranges and every sourced airfoil. Sampled sparsely: 40 wings per type, plus both corner sets at its edges. Grey line in each cell.</p></div>
    <div class="box"><h3>Focus space</h3><div class="big">Where real wings are</div><p>Shape ranges from real Class I–II wings and papers; suggested airfoils. Sampled densely: 100 wings per type, the reference wings and the hold-out. Bold line in each cell.</p></div>
    <div class="box"><h3>Why two</h3><div class="big">Wide, but dense where it counts</div><p>The mesher must work on anything we claim to support; the studies and the ML spend most runs where real wings are. The focus box lies inside the full box (the YAML refuses it otherwise).</p></div>
  </div>
  <h2 style="font-size:22px">Inputs (sampled), by wing type</h2>
  <div class="tbl"><table class="wide inp">
    <thead><tr><th></th><th></th><th colspan="2">Tailless</th><th colspan="2">Conventional</th><th></th></tr><tr><th>Input</th><th>Symbol</th><th>BWB</th><th>Flying wing</th><th>Cranked</th><th>Tapered</th><th>Why this range (focus)</th></tr></thead>
    <tbody>
__INPUTS__
    </tbody>
  </table></div>
  <p class="muted">"derived": that type computes the value (see below). Sweep positive aft; twist positive nose up; dihedral positive tip up. Since 7 Nov every wing is built at unit mean chord, so the root chord is not sampled: 16 / 12 / 16 / 12 inputs (BWB / flying wing / cranked / tapered).</p>
  <h2 style="font-size:22px">Derived (computed, never sampled)</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Quantity</th><th>Formula</th><th>Types</th></tr></thead>
    <tbody>
__DERIVED__
    </tbody>
  </table></div>
  <p class="muted">Checked on every built wing: chords (0.1 %), sweeps (0.1°), twists and panel dihedrals (0.2°) and the aspect ratio (0.1 %), measured on the loft against the inputs.</p>
  __CHG_INPUTS__
  <div class="cbox"><span class="ctag">Conclusion</span>17 numbers and 4 airfoil names describe every wing, at unit mean chord. Everything else is computed from them and checked on the built surface.</div>
</section>

<section id="nose">
  <h2>Nose study: the built nose against the airfoil file (decision 64)</h2>
  <p>The question: is the nose of the built section the nose of the airfoil, at the size of one mesh cell? On 2 Nov the Stage 2 mesher found that the built noses of cambered sections were not round. On 6 Nov a second reading said this was overstated. On 7 Nov the nose was measured again, with one method for every curve, and fixed in the code.</p>
  <div class="three">
    <div class="box"><h3>Method</h3><div class="big">One curvature, along the arc</div><p>Every curve is a smooth spline. Its curvature comes from its own derivatives along its own arc length: no frame, no formula. Curves: the raw file (a cubic spline; a quintic as a check), the built section as the loft holds it (old and new rule), and the NACA 4415 formula.</p></div>
    <div class="box"><h3>Mesh number</h3><div class="big">T(h): turning per cell</div><p>The largest turning a cell of arc length h gets near the nose (within 3 % c of arc), for h = 0.04, 0.10, 0.18, 0.30 and 0.50 % c. Criterion, written before computing: built within 5 % of raw at every h, on all ten suggested airfoils.</p></div>
    <div class="box verdict"><h3>Result</h3><div class="big">Old rule fails all ten; new rule passes all ten</div><p>Old: NACA 4415 +449 % at 0.04 % c, +121 % at 0.18 % c. New: worst −3.9 % (MH 60 at 0.04 % c). Database: 95.6 % pass (old rule 21.0 %).</p></div>
  </div>
  <figure class="fig card">__PNG_NOSE__<figcaption><span class="howto">How to read.</span> Top row: curvature (1/c) along the arc from the old leading-edge point (− lower side, + upper side) on four airfoils: the raw file (black), the formula (dotted, NACA 4415 only), the old rule (orange), the new rule (blue dashed). Middle row: the turning per cell T, built against raw, at every h, for the old rule (left) and the new rule (centre; dashed: with only 101 points per side), and the Stage 2 nose solve on a NACA 4415 station (right). Bottom row: the whole database (left: the share of files at or below a miss; the dashed line is 5 %) and the two side effects: how far the leading edge moves (centre) and how much the chord line turns (right).</figcaption></figure>
  <div class="cbox"><span class="ctag">What it shows</span><ul>
    <li><strong>The old nose had a spike on one side and a flat spot on the other.</strong> On NACA 4415 the upper side curved at 567/c at the old leading edge (radius 0.0018 c), and the lower side was flat there (6.4/c). The raw file and the formula curve at about 40–42/c. Further down, the lower side got its angle back in a false bump (77.5/c at −0.755 % c; raw 41.5/c). So a 0.18 % c nose cell turned 9.47°, where the true shape turns 4.31°.</li>
    <li><strong>Why.</strong> The old rule put the leading edge at the farthest raw point. The apex of the curve lies between raw points, 0.003–0.210 % c of arc away on the ten, and there the tangent is already turned by 0.05–19.4°. The √x resampling then forced the tangent square to the chord, so that angle was packed into the first gap on one side and taken from the other. PCHIP resampling through coarse files added a second error.</li>
    <li><strong>The 6 Nov note was wrong.</strong> It read the raw points with a one-sided formula and saw the same split as on the built section. But the built section passes through the raw points, so no formula on those points can see what happens between them. Measured along the arc, the built split was real, and larger at the leading edge than first read (NACA 4415 radius 0.0018 / 0.155 c, not 0.008 / 0.074 c).</li>
    <li><strong>The new rule follows the file.</strong> All ten are within 5 % at every h (worst −3.9 %). With only 101 points per side the tight MH noses stay 6.3–9.4 % low at 0.04 % c, so the new rule holds 201 points per side.</li>
    <li><strong>Stage 2's flat nose line stays.</strong> On a NACA 4415 station the largest turning per node stays flat below a nose spacing of 0.2 % c with both rules (6.6–7.4° old, 6.0–6.8° new). The worst node sits 1.8–2.4 % c down the lower side, where the growth law (1.2) sets the cells, not the nose spacing. The 10° target now holds up to a nose spacing of 0.377 % c (0.327 % c with the old rule).</li>
    <li><strong>The whole database</strong> (2,143 files both rules build and measure): 95.6 % pass the 5 % test at 0.04 and 0.18 % c (old rule 21.0 %); the median worst miss is 0.52 % (old 15.8 %). A gate refuses the 14 files whose nose folds back (the old rule built 45 such hooks). Crossing surfaces: 4 and 4 (they are in the files). Every section the configs name passes (worst 3.89 %, MH 60).</li>
    <li><strong>Side effects.</strong> The leading edge moves along the nose by a median 0.046 % c (90 %: 0.28 % c; max 1.69 % c, on coarse files of 33–41 points). The chord line turns by a median 0.027° (max 0.96°; over 0.1° on 428 files). On the named sections the largest is NACA 4415: 0.209 % c and 0.12°. Every geometry hash changed; sections have 401 points instead of 201.</li>
  </ul></div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Airfoil</th><th>Points</th><th>R<sub>min</sub> raw</th><th>R<sub>min</sub> old</th><th>R<sub>min</sub> new</th><th>T old vs raw, % (0.04 / 0.18 % c)</th><th>T new vs raw, % (0.04 / 0.18 % c)</th><th>Jump old / new</th><th>LE move % c / chord turn</th></tr></thead>
    <tbody>__NOSE_TABLE__</tbody>
  </table></div>
  <p class="muted">R<sub>min</sub>: the smallest radius within 3 % c of the leading-edge point, in chords. T: the turning per cell, built against raw. Jump: the curvature of the two built branches at the leading-edge point, larger over smaller (1 = round). LE move and chord turn: what the new rule changes. Is the raw file a fair reference? For NACA 4415 yes: the file sits on the formula within 4.2 × 10⁻⁶ c, and its turning is within 0.7 % of the formula's. The 61-point files (E387, SD7032, S5010) only partly: a quintic spline through the same points gives 13.6–14.9 % less turning at 0.04 % c. Details: <code>decisions/nose_curvature.md</code>, <code>data/studies/nose_curvature.json</code>, <code>scripts/nose_curvature.py</code>.</p>
  <div class="cbox"><span class="ctag">Conclusion</span>Decision 64 is settled with a fix. The old rule made the built nose turn up to 5.5 × more per small cell than the airfoil (NACA 4415 at 0.04 % c), and the 5 % test failed on all ten suggested airfoils. The new rule (leading edge at the apex of one cubic spline, both sides from that spline, 201 points per side) passes on all ten and on 95.6 % of the database; a gate refuses the 14 files whose nose folds back. The cost: every hash changed, the leading edge moves (median 0.046 % c) and the chord line turns (median 0.027°). Stage 2's flat nose line is not a geometry error: it comes from the growth law.</div>
</section>

<section id="ranges">
  <h2>Shapes we can make (unit mean chord)</h2>
  <p>The input ranges are in <a href="#inputs">Parameters</a>. This is what they produce. Every wing has a mean chord of 1, so its area and its full span both equal its aspect ratio; chords are in mean chords.</p>
  __CHG_RANGES__
  <figure class="fig">__GIF_SIZES__<figcaption>Lowest and highest aspect ratio of each type at the corners of the planform inputs (aspect ratio, chord ratios, panel shares), other inputs at mid-range, at unit mean chord. Solid: focus space. Dashed: full space. A bar of 1 mean chord in each view; the same scale in every frame. The last frame shows the four focus types together.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>At unit mean chord the types differ by shape alone. The aspect ratio runs from 3 to 16.5 in the focus space and from 2.5 to 20 in the full space. The BWB is the extreme one: a root of up to __S_BWB_ROOT__ mean chords and a tip down to __S_BWB_TIP__ in the focus space (__S_BWBU_ROOT__ and __S_BWBU_TIP__ in the full space), up to __S_BWB_RATIO__ × from root to tip. The flying wing and the conventional types stay within __S_OTHER__ mean chords, even in the full space.</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Space</th><th>Aspect ratio (= full span)</th><th>Root chord</th><th>Tip chord</th><th>Overall taper</th><th>Root / tip, at most</th></tr></thead>
    <tbody>__EXTREMES__</tbody>
  </table></div>
  <p class="muted">Extremes over all corners of the planform inputs (other inputs mid-range), in mean chords. The built sets stay inside them: their chords run 0.062–3.60 mean chords, their aspect ratios 2.5–20. <code>python scripts/size_extremes.py</code>.</p>
  <h2 style="font-size:22px">First approach: sizes at real scale (30 Oct–6 Nov 2026)</h2>
  <p>Kept as the record: the wings of the first approach, at real size, in metres. The flow maps and the flow dataset on this page used them.</p>
  <figure class="fig">__GIF_SIZES_FIRST__<figcaption>First approach: smallest and largest wing (least and most area) of each type at the corners of the size inputs (then including the root chord in metres), other inputs at mid-range, true scale. Solid: focus space. Dashed: full space. Left view 0.6 m wide, right view 22 m wide; the same scale in every frame.</figcaption></figure>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Space</th><th>Full span b (tip to tip)</th><th>Wing area</th><th>Mean chord</th><th>Root chord</th><th>Tip chord</th></tr></thead>
    <tbody>__EXTREMES_FIRST__</tbody>
  </table></div>
  <p class="muted">First approach: smallest and largest over all corners of the size inputs (other inputs mid-range). Sampled wings could be a little larger (next table: BWB area up to 6.72 m², cranked up to 4.95 m²). Kept in <code>docs/first_approach/size_extremes.json</code>.</p>
  <h2 style="font-size:22px">What the focus space made (first approach)</h2>
  <p class="muted">2,000 Latin-hypercube wings per type, at real size, from <code>scripts/real_uav_check.py</code> (run before 7 Nov).</p>
  <div class="tbl"><table class="mid">
    <thead><tr><th></th><th>BWB</th><th>Flying wing</th><th>Cranked</th><th>Tapered</th></tr></thead>
    <tbody>__GEN__</tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>First approach: true scale showed the spread. Focus wings had a full span of about 0.4–7 m, the full space 0.1–20 m, and the smallest wings had tips of only 2–8 cm, which is why their tips flew at very low Re. The four focus spaces made wings of the same size (full span 0.5–7 m, mean chord 0.1–1 m) but of different shape: the BWB was the low-taper, low-aspect-ratio one (taper 0.06–0.2, AR 3–9); the conventional types were the slender ones (AR 4.5–16.5). Now the same shapes are built at unit mean chord, and the Re level does what the size did.</div>
</section>

<section id="reynolds">
  <h2>Reynolds and Mach numbers</h2>
  <div class="three">
    <div class="box"><h3>Study levels (Stage 0)</h3><div class="big">1 × 10⁵ · 3 × 10⁵ · 1 × 10⁶ · 4 × 10⁶</div><p>On the mean chord (area / full span, not the MAC). Since 7 Nov the Re is an input of each solve: every shape runs at all four. Every mesh study runs at these four. Changed on 8 Nov (you): 1 × 10⁶ and 4 × 10⁶ replace 1.5 × 10⁶ and 3 × 10⁶, for the Greek tactical programmes and check C4 (<a href="#greek">below</a>). 1 × 10⁵ added 30 Oct 2026 for mini Class I wings; it sits 18 % below the slowest real UAV, kept as a margin (you, 7 Nov).</p></div>
    <div class="box"><h3>Real wings fly at</h3><div class="big">__REAL_RE__</div><p>On the mean chord (area / full span), cruise at 3,048 m to top speed at sea level, for the 34 real wings with a published area. Inside the four levels.</p></div>
    <div class="box"><h3>Mach</h3><div class="big">0.1 (CFD)</div><p>Under similarity the CFD runs at Mach 0.1, with a Prandtl–Glauert correction on CL and CM (check C2: 0.05 / 0.1 / 0.2). First approach (the flow data on this page): Mach 0.03–0.20 from the real wings' speeds, well below 0.3, so the air is nearly incompressible. Since 4 Nov 2026 the Mach scope extends toward 0.5, with no supersonic flow. Proposal, pending: core data at Mach ≤ 0.2 now, 0.3–0.5 later with a fast-UAV family (the section tables stop at Mach 0.2).</p></div>
  </div>
  __CHG_REYNOLDS__
  <h2 style="font-size:22px">By type and space (unit mean chord)</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Space</th><th>Re on the mean chord</th><th>Smallest tip chord → tip Re at 1 × 10⁵</th><th>Largest root chord → root Re at 4 × 10⁶</th></tr></thead>
    <tbody>__RE_MACH__</tbody>
  </table></div>
  <p class="muted">Local Re = Re on the mean chord × local chord (in mean chords). Chords from all corners of the planform inputs (others mid-range). One wing at one level covers a much narrower band than its row.</p>
  <div class="cbox"><span class="ctag">Conclusion</span>The four study Re levels (10⁵ – 4 × 10⁶) cover the real wings (1.22 × 10⁵ – 3.10 × 10⁶ on the mean chord) and every cruise point of the Greek tactical BWBs (1.4–3.7 × 10⁶). Inside one wing, Re goes further: at the lowest level down to about __S_BWB_RETIP__ at the smallest focus BWB tip (__S_BWB_TIP__ mean chords), at the top level up to __S_BWB_REROOT__ at the largest focus BWB root (__S_BWB_ROOT__ mean chords). The other types stay within about __S_OTHER_RE__.</div>
  <h2 style="font-size:22px">First approach: Re and Mach at real size and speed</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Space</th><th>Speed</th><th>Mach</th><th>Re, mean chord</th><th>Re, smallest tip</th><th>Re, largest root</th></tr></thead>
    <tbody>__RE_MACH_FIRST__</tbody>
  </table></div>
  <p class="muted">First approach (before 7 Nov; the flow data on this page). Lowest: smallest chord at the family's lowest cruise speed at 3,048 m. Highest: largest chord at its highest top speed at sea level. Air from Stage 0 (ISA, Sutherland); a = 328.6 m/s at 3,048 m, 340.3 m/s at sea level.</p>
  <div class="cbox"><span class="ctag">Conclusion</span>First approach: the real-size wings at real speeds reached 5.4 × 10⁴ – 3.5 × 10⁶ on the mean chord in the focus space, down to about 1.4 × 10⁴ at the smallest tips and up to 5.5 × 10⁶ at the largest BWB roots. The similarity form gives a wider local reach at the two end levels, because every shape now runs at both.</div>
  <h2 style="font-size:22px">What each Re band means</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Re (on the local chord)</th><th>Flow</th><th>Who is there</th><th>RANS (SA, fully turbulent)</th></tr></thead>
    <tbody>
      <tr><td class="num">below 10⁵</td><td>Laminar; long bubbles close to bursting (bubbles appear from about 6 × 10⁴); lower down the flow can separate without reattaching; strong hysteresis</td><td>Tips and outer panels at the lowest level (10⁵ on the mean chord)</td><td><span class="flag fix">poor</span> no transition model, results only indicative</td></tr>
      <tr><td class="num">10⁵ – 5 × 10⁵</td><td>Laminar separation bubbles, transition on the bubble</td><td>The two lowest levels (most Class I wings fly there); outer panels of BWBs</td><td><span class="flag open">drag too high</span> bubble missed; SA drag error −2 to +77 % (2-D, 2°; near zero only at 10⁵)</td></tr>
      <tr><td class="num">5 × 10⁵ – 3 × 10⁶</td><td>Laminar to 30–60 % of chord, then turbulent; short bubbles still form up to about 2 × 10⁶</td><td>The level 1 × 10⁶ (Class II wings in loiter); BWB centre bodies</td><td><span class="flag open">drag too high</span> the laminar run is missed: the largest SA drag error, +74 to +128 % (2-D, 2°)</td></tr>
      <tr><td class="num">above 3 × 10⁶</td><td>Shorter laminar run in quiet air</td><td>The top level 4 × 10⁶ (Class II at top speed; the Greek tactical BWBs); large roots (up to __S_BWB_REROOT__)</td><td><span class="flag open">drag too high</span> still +74 to +120 % at 3 × 10⁶ in quiet air (2-D); closer in gusty air or on a rough surface</td></tr>
    </tbody>
  </table></div>
  <p class="muted">Bands are approximate (Carmichael 1981; Lissaman 1983; Mueller &amp; DeLaurier 2003). "SA drag error" = profile drag of fully turbulent CFD ÷ profile drag of the real flow − 1, from XFOIL (see <a href="#phenomena">Flow phenomena</a> and <a href="#flowdata">Flow dataset</a>). Corrected 1 Nov 2026: this table had called SA "good" above 5 × 10⁵; the 2-D runs show the opposite in quiet air. The 2-D numbers were rerun on 7 Nov on the sections of the new nose rule (they moved by at most 4 points).</p>
  <div class="cbox"><span class="ctag">Conclusion</span>No Re band in our range is safe for fully turbulent SA drag in quiet air: from 10⁵ up it gives too much drag (it misses the laminar run); below 10⁵ it misses the laminar separation. For drag, the model choice matters more than the mesh.</div>

  <h2 id="greek" style="font-size:22px">Greek tactical UAVs and the Re levels (8 Nov 2026)</h2>
  <p>You asked (8 Nov) that the range include the Greek programmes LOTUS, Archytas and ACTUS. ACTUS is not an aircraft: it is an EDF 2023 project (Intracom Defense, Dec 2024 – 2028) that develops and certifies LOTUS and the Safran Patroller. No wing area is published for any Greek aircraft, so the mean chord comes from an assumed aspect ratio of 8: the AUTh RX-3, which LOTUS is based on, has AR 8 and a 33° sweep (Kapsalis et al. 2025), inside our BWB focus (AR 3–9, sweep 15–40°). Every number with its source, the conflicts between sources and the assumptions: <code>configs/greek_uavs.yaml</code>; the numbers: <code>scripts/greek_uavs.py</code> (<code>docs/greek_uavs.json</code>).</p>
  <figure class="fig card">__PNG_GREEK__<figcaption class="cap"><span class="howto">How to read.</span> One bar per aircraft: from cruise at 3,048 m (dot) to top speed at sea level (diamond), on the mean chord. The lighter end is a range of top speeds in the sources. Dashed: the four Re levels since 8 Nov; dotted: 1.5 × 10⁶ and 3 × 10⁶, the levels before. The grey bar on top: the 31 real Class I–II wings with a published area. Shaded: above the top level, where the data are extrapolated.</figcaption></figure>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Aircraft</th><th>Full span</th><th>Cruise / top speed</th><th>Re (mean chord)</th><th>Mach at top speed</th><th>What is not published</th></tr></thead>
    <tbody>
      <tr><td>Archytas (HAI; AUTh aerodynamics; BWB, VTOL)</td><td class="num">6.4 m</td><td class="num">120 / 158 km/h</td><td class="num">1.4 → 2.4 × 10⁶</td><td class="num">0.13</td><td>wing area; MTOW (180–200 kg on one site)</td></tr>
      <tr><td>RX-3 (AUTh/DELAER; LOTUS is based on it)</td><td class="num">7.2 m</td><td class="num">180 / 241 km/h</td><td class="num">2.4 → 4.1 × 10⁶</td><td class="num">0.20</td><td>wing area (a paper airframe like it: 4.9 m², 6.26 m)</td></tr>
      <tr><td>LOTUS sub-scale demonstrator</td><td class="num">about 7 m</td><td class="num">the RX-3's</td><td class="num">2.3 → 4.0 × 10⁶</td><td class="num">0.20</td><td>speeds, area; one source says 6 m and 230 kg</td></tr>
      <tr><td>LOTUS (EDIDP, then ACTUS; BWB)</td><td class="num">11 m</td><td class="num">180 (assumed) / about 220–240 km/h (planned)</td><td class="num">3.7 → 5.8–6.3 × 10⁶</td><td class="num">0.18–0.20</td><td>cruise speed, area; weight 500–700 kg</td></tr>
      <tr><td>Safran Patroller (ACTUS)</td><td class="num">18 m</td><td class="num">92 / 265–314 km/h</td><td class="num">1.3 → 4.9–5.8 × 10⁶</td><td class="num">0.22–0.26</td><td>area (the Stemme S15 wing used: 17.4 m², AR 18.6)</td></tr>
    </tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>With the levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶ and 4 × 10⁶, every cruise point of the Greek tactical UAVs is inside (LOTUS 11 m: 2.8 × 10⁶ at 20,000 ft, 3.7 × 10⁶ at 10,000 ft), and so are the 6–7 m versions at top speed (the RX-3 3 % above). LOTUS 11 m flying low and fast (4.7–6.3 × 10⁶) and the Patroller at top speed are extrapolations; they stay so: no 5th level (you, 8 Nov). Every Greek number rests on an assumption (AR 8; AR 6 would raise each Re by a third), and the sources disagree on several values. Mach stays at or below 0.26: the Prandtl–Glauert correction from Mach 0.1 is +1.1 to +2.9 %. The shapes fit the generator: the RX-3 family (AR 8, sweep 33°) sits inside the BWB focus; the Patroller (AR 18.6) only in the full space. LOTUS 11 m (500–700 kg) and the Patroller (1.2 t) are NATO Class III by weight.</div>
  <h2 style="font-size:22px">Check C4 on 2-D data: can the data be read between the levels?</h2>
  <p>Each of the 13 section tables (free transition at N_crit 9, and tripped), at 0, 2, 4 and 6°, Mach 0.1: the drag at every grid Re that is not a level is read by a straight line in log Re and log cd between the two nearest levels (above the top: from the two highest), and compared with the table (<code>scripts/re_ladder_check.py</code>, <code>docs/re_ladder_check.json</code>).</p>
  <figure class="fig card">__PNG_LADDER__<figcaption class="cap"><span class="howto">How to read.</span> Each point: the 90th percentile of the drag error over the 13 sections and 4 angles at that Re. Grey: the levels until 8 Nov; blue: since 8 Nov. No point where the Re is itself a level. Left: with transition; right: fully turbulent (note the different scale).</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>With transition, the new levels read drag better where it changes fastest: at 6 × 10⁵ the error falls from 16.9 % to 8.8 % (90th percentile), and above the top (6 × 10⁶) from 12.0 % to 7.8 %. The price: between 1 × 10⁶ and 4 × 10⁶ it rises from 2.5–3.7 % to 6.8–7.0 %. Over 1 × 10⁵ – 4 × 10⁶ the median is 3.0 % (3.3 % before) and the worst 20 % (26 %). Fully turbulent drag reads well with either (median 0.7 %, at most 1.3 % at the 90th percentile). This is a 2-D proxy: check C4 with the solver is still to run, and wing drag also carries induced drag, which does not depend on Re.</div>
  <h2 style="font-size:22px">The scope by NATO class (Mitridis et al. 2023)</h2>
  <p>A peer-reviewed survey of 202 fixed-wing UAVs (AUTh, the group that did the aerodynamics of Archytas and the RX-3), sorted by NATO class. It gives the class limits, spans and speeds per class. It gives no aspect ratio or wing area (not enough solid data), so it cannot give a Re by itself; with our aspect ratios it supports the range.</p>
  <div class="tbl"><table class="wide">
    <thead><tr><th>NATO class (by take-off weight)</th><th>Altitude</th><th>Full span</th><th>Median cruise / top speed</th><th>Our scope</th></tr></thead>
    <tbody>
      <tr><td>Class I micro and mini (below 15 kg)</td><td class="num">below 3,000 ft</td><td class="num">about 0.7–3.5 m</td><td class="num">about 60 / 95 km/h</td><td>yes (the 1 × 10⁵ and 3 × 10⁵ levels)</td></tr>
      <tr><td>Class I small (15–150 kg)</td><td class="num">below 5,000 ft</td><td class="num">about 1–8 m</td><td class="num">about 120 / 160 km/h</td><td>yes</td></tr>
      <tr><td>Class II tactical (150–600 kg)</td><td class="num">below 18,000 ft</td><td class="num">about 2–16 m</td><td class="num">about 180 / 190 km/h</td><td>yes (Archytas, RX-3, LOTUS demonstrator)</td></tr>
      <tr><td>Class III (over 600 kg)</td><td class="num">up to 65,000 ft</td><td class="num">—</td><td class="num">—</td><td>only LOTUS 11 m and the Patroller (in cruise)</td></tr>
    </tbody>
  </table></div>
  <p class="muted">Speeds and spans read from the paper's box and dot plots (2005–2015; about ± 10 %); class limits from its Table 2. Within a class, span against weight and cruise speed against weight fit poorly (R² &lt; 0.2, Tables 5 and 9).</p>
  <div class="cbox"><span class="ctag">Conclusion</span>The paper fits our approach: within one class the spread is wide and the trend lines are weak, so a range sampled across the spread, not a trend line, is the right description of the design space. Its class limits make our scope precise: Class I and Class II up to 600 kg and 18,000 ft, with the Greek tactical BWBs inside and LOTUS 11 m at the Class III edge.</div>
</section>

<section id="phenomena">
  <h2>Flow phenomena you will meet</h2>
  <p>What the flow does on these wings, at these Re and angles, and whether fully turbulent CFD (ADflow, steady RANS, Spalart–Allmaras) can see it. Since 4 Nov 2026 transition must be captured too, with ADflow and SU2: our ADflow build has SA only, so transition comes from SU2 (SST + LM γ-Reθ).</p>
  __CHG_PHENOMENA__
  <figure class="fig"><div class="svgwrap">__FIG_RE__</div>
    <figcaption class="cap">Where the wings fly, at unit mean chord. Thick bars: the four levels on the mean chord, the same for every type. Thin bars: the local Re along the semi-span, from the smallest tip at the lowest level to the largest root at the top level (focus space). Top lines: the real wings with a published area and speeds, each at its own Re on the mean chord (cruise at 3,048 m to top speed at sea level). The tips go furthest into the low-Re regime, the BWB down to about __S_BWB_RETIP__ (low-Re limit: below 5 × 10⁵, Univ. Waterloo Fluid Mechanics Research Lab; Carmichael 1981).</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>At the two lowest levels every type flies in the low-Re regime (below 5 × 10⁵), and the tips go deepest: the BWB down to about __S_BWB_RETIP__ at 10⁵. Low-Re effects are the rule for these wings, not the exception.</div>
  <figure class="fig card">__PNG_LOCALRE__
    <figcaption class="cap">At unit mean chord: local Re = Re on the mean chord × local chord (in mean chords). Top: each type's focus wing with the smallest tip chord, at the lowest level (1 × 10⁵). Bottom: its focus wing with the largest root chord, at the top level (4 × 10⁶; 3 × 10⁶ until 8 Nov). At the lowest level the outer panels sit below 10⁵ (red) and the BWB carries two regimes at once; at the top level the roots pass 4 × 10⁶ (dark blue).</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>One wing can hold two regimes: at the lowest level the focus BWB with the smallest tip runs at __S_TIPW_REROOT__ at the root and __S_TIPW_RETIP__ at the tip, __S_TIPW_RATIO__ times less (first approach, real size: 2.4 × 10⁵ and 1.4 × 10⁴, 17 times). One flow model may not fit the whole half wing. One first-cell height does (it changes only about 20 % along the semi-span, because Re and chord change together), but the root boundary layer is up to about 10 × thicker and needs more wall layers.</div>
  <h2 style="font-size:22px">What fully turbulent CFD would miss: estimated in 2-D with XFOIL (no wing CFD run yet)</h2>
  <p>No CFD has been run on a wing yet (the 4 Nov SU2 smoke test on one ring mesh did not converge and gives no result). Four airfoils, each on its own (2-D, not a cut of a wing; rerun on 7 Nov 2026 on the sections of the new nose rule), were run in XFOIL (Drela 1989: a panel method coupled to a boundary-layer model, not RANS): MH 104, the BWB centre body (root); MH 61, the BWB outer wing (tip); MH 60, the flying wing; NACA 4415, the conventional wings (root). Each was run twice at the four study Re:</p>
  <ul>
    <li><strong>Real flow (free transition).</strong> XFOIL lets the boundary layer start laminar at the nose and predicts where it turns turbulent by itself (e<sup>N</sup> method, N<sub>crit</sub> 9 = quiet air), including laminar separation bubbles.</li>
    <li><strong>Fully turbulent (tripped).</strong> Transition forced at 1 % chord on both surfaces: turbulent from the nose, which is what fully turbulent CFD (ADflow SA) assumes.</li>
  </ul>
  <p>The gap between the two is the error that comes from ignoring transition. It is a 2-D proxy: no sweep, no crossflow, no 3-D relief.</p>
  <figure class="fig"><div class="svgwrap">__FIG_SURF__</div>
    <figcaption class="cap">Words used below. An airfoil has two surfaces: the upper (top, suction) side, where the boundary layer first stays laminar and then turns turbulent, and the lower (bottom, pressure) side. This holds at positive angles; at negative angles (now in scope, down to −5°) the two sides swap roles. Each XFOIL run is one such 2-D section on its own, not a cut through a 3-D wing.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>At the positive angles studied here, the laminar run, bubbles and transition that matter happen mostly on the upper surface, so the next figures show that surface.</div>
  <figure class="fig card">__PNG_XFCF__
    <figcaption class="cap">2-D airfoil sections in XFOIL, exactly 4°, top (upper) surface only: skin friction from nose (0) to trailing edge (1). Solid: free transition (real quiet air); dashed: tripped at 1 % chord (fully turbulent CFD). At 10⁵ and 3 × 10⁵ the free flow runs laminar to mid-chord, separates (shaded, Cf &lt; 0) and turns turbulent on the bubble. At 1.5–3 × 10⁶ transition moves forward to 30–45 % chord with no bubble. Tripped: turbulent from the nose, with much higher friction everywhere.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>In quiet real air the flow stays laminar (low friction) over a large part of the chord; fully turbulent CFD puts high friction everywhere. That difference is the extra drag fully turbulent CFD adds.</div>
  <figure class="fig card">__PNG_XFBAND__
    <figcaption class="cap">Four airfoils, each run alone in 2-D XFOIL (not a cut of a 3-D wing), at exactly 2° and Mach 0. <strong>Light bar</strong>: free transition (e<sup>N</sup>, N<sub>crit</sub> 9): the flow stays laminar from the nose and turns turbulent by itself, as in quiet real air. <strong>Dark bar</strong>: tripped at 1 % chord: turbulent from the nose, which is what fully turbulent CFD (SA) assumes. The % is tripped / free − 1: how much too high fully turbulent CFD puts the profile drag. At Re 10⁵ the two are close because the free flow separates in a long bubble, which is draggy too. __XF_NOTE__</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>From Re 3 × 10⁵ up, fully turbulent CFD puts the profile drag +39 to +128 % too high (2-D, 2°; median +81 %). At 10⁵ the gap is small (−2 to +21 %), but only because the real flow has a draggy bubble too: SA is close there by luck, not because it models the flow. On the old sections (before the nose fix) the same runs gave +40 to +128 % and −1 to +21 %; MH 60 at 1.5 × 10⁶ had no converged free answer at 2° then and has one now (+112 %).</div>
  <figure class="fig card">__PNG_XFTR__
    <figcaption class="cap">2-D airfoil sections in XFOIL, exactly 2°, free transition, top (upper) surface only: where the flow turns turbulent, from nose (left) to trailing edge (right). Light: laminar (low friction); dark: turbulent. Higher Re moves the change toward the nose; the BWB centre-body section (MH 104) turns turbulent earliest.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Where the flow turns turbulent depends on Re and on the airfoil, so it has to be predicted (a transition model), not assumed (fully turbulent).</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Phenomenon</th><th>Where in our ranges</th><th>What it does</th><th>Does our CFD capture it?</th><th>Source</th></tr></thead>
    <tbody>__PHEN__</tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>Most of these wings fly where transition and laminar bubbles set the drag, and fully turbulent SA cannot see them; that is why transition must be captured too (decided 4 Nov 2026). Mesh error can be made small; this model error cannot, so every SA drag number needs its model band. Differences between wings are safer than absolute drag only at a fixed airfoil, and even then not at the 2-count level (see <a href="#flowdata">Flow dataset</a>).</div>
</section>

<section id="flowmaps">
  <h2>Flow maps</h2>
  <p>What the tool returns for one wing: the half wing coloured by local Re, the line where the upper surface turns turbulent, laminar bubbles, trailing-edge separation, the phenomena, the proposed model with the size of the SA error, whether the condition is level flight at a real wing loading, where the wing sits in the flow dataset, and the other section sets at the same condition. The 2-D answers come from the section tables (the same engine as the <a href="#flowdata">flow dataset</a>; direct XFOIL for sections without a table).</p>
  __CHG_FLOWMAPS__
  <figure class="fig card">__FA__ __PNG_FMEX__<figcaption>__FMEX_CAP__</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>One run of the tool shows, for one wing at one condition, where the flow is laminar, where bubbles sit and which model to use. On this wing SA would add +96 % profile drag, so the tool proposes a transition model.</div>
  <figure class="fig card">__FA__ __PNG_FMEX_SHEET__<figcaption>The same wing over Mach × root angle (<code>--sheet</code>): SA error, laminar run, bubble share and trailing-edge separation per condition. Faded: not level flight at a real wing loading for its full span.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>No speed or angle makes SA right on this wing: the error is +41 to +103 % in every cell, and +60 to +101 % in the 9 level-flight cells.</div>
  <h2 style="font-size:22px">The focus space, per type: slow and fast, three section sets</h2>
  <p>Mid wing of each type. Slow: the family's lowest cruise speed at 3,048 m, 5°. Fast: its highest top speed at sea level, 1°. Sets: the suggested one and two sourced alternatives (SD7032 flies on the Puma 3AE, LA2573A on the Dragon Eye: NTNU database).</p>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Sections</th><th>Slow: Re</th><th>Slow: transition (upper)</th><th>Slow: SA drag</th><th>Fast: Re</th><th>Fast: transition (upper)</th><th>Fast: SA drag</th></tr></thead>
    <tbody>__FMTABLE__</tbody>
  </table></div>
  <p class="muted">"SA drag": how much fully turbulent SA would raise the wing's profile drag (chord-weighted XFOIL strips). Every case gets the same proposal: a transition model (γ-Reθ with SST, SU2) for drag; SA for mesh studies, and as an upper bound for drag except where a long bubble costs more than early turbulence (the negative values: LA2573A, slow).</p>
  <div class="cbox"><span class="ctag">Conclusion</span>Slow or fast, every type and section set gets about +27 to +85 % profile drag from SA. The one exception is LA2573A at slow speed (−9 to −11 %): its long bubble makes the real flow draggier than SA.</div>
  <figure class="fig card">__FA__ __PNG_FM_BWB__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>BWB: +54 to +69 % slow and +46 to +57 % fast, whatever the sections. Changing the airfoils does not fix SA. (The NACA set cannot trim a tailless wing; it is shown for contrast.)</div>
  <figure class="fig card">__FA__ __PNG_FM_FW__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Flying wing: +49 to +71 % slow and +67 to +79 % fast, the highest of all types at speed with the suggested sections (SD7032 on the conventional wings reaches +85 %).</div>
  <figure class="fig card">__FA__ __PNG_FM_CR__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Cranked: +56 to +61 % slow with NACA 4415 and SD7032, but −9 % with LA2573A; +28 to +85 % fast. On conventional wings the airfoil changes the error the most.</div>
  <figure class="fig card">__FA__ __PNG_FM_TA__</figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Tapered: as the cranked wing: +55 to +60 % slow (−11 % with LA2573A), +27 to +85 % fast.</div>
  <div class="weak amber"><strong>What these maps cannot tell.</strong> Strips are 2-D with one uniform induced angle: no spanwise change of the downwash, no crossflow transition on swept leading edges, no 3-D relief of bubbles. The angle (5° slow, 1° fast) is our choice, not trimmed. Use them to know where to look and which model to pick, not for numbers.</div>
</section>

<section id="flowdata">
  <h2>Flow dataset: every focus wing, four section sets, every speed and angle</h2>
  <p>__FD_INTRO__</p>
  __CHG_FLOWDATA__
  <div class="three">
__FD_KPI__
  </div>
  <div class="weak amber"><strong>Same assumptions as the flow maps.</strong> 2-D strips along the half wing; local angle = root angle + twist − a uniform induced angle (elliptic, iterated); XFOIL e<sup>N</sup> with N<sub>crit</sub> 9 (quiet air) for free transition, tripped at 1 % chord for fully turbulent (what SA does); Stage 0 air. "SA drag error" = profile drag tripped / free − 1, chord-weighted along the semi-span. A grid point is "level flight" when the lift it makes (the strip lift with the induced angle) carries the wing loading real wings of the same full span carry (fit to 37 real wings, within × / ÷ 2).</div>
  <div class="weak" style="border-left-color: var(--bwb)"><strong>Four words used in every figure below.</strong> <strong>SA drag error</strong>: how much more profile drag fully turbulent CFD (SA) gives than the real flow; +60 % means 1.6 times the real value, 0 means right. <strong>Laminar run</strong>: how far from the nose the flow on the upper surface stays laminar, in % of the chord. <strong>Bubble share</strong>: the share of the half wing with a laminar separation bubble (the figures call it "bubble span" or "span with a bubble"). <strong>Level flight</strong>: the wing makes the lift that real wings of its full span carry. Every figure has a <em>How to read</em> line and a conclusion box under it.</div>
  <div class="weak"><strong>Logic check (1 Nov 2026), applied 2 Nov 2026.</strong> An independent review found that the first version left out the induced angle, which put the strips too close to stall at high angle. This version includes it (uniform, elliptic, iterated); every number and figure in this section comes from it. Three earlier findings were artefacts and are gone: the error falling to +20 % at 10° (it is +40 %), trailing-edge separation on 20 % of the half wing at 10° (it is 2 %), and "SA adequate" for flying wings at 10° (never). Also fixed: "beyond 2-D stall" is now "no XFOIL answer" (mostly failed points, not stall); the NACA set on tailless wings cannot trim, so it is shown but not counted; the sensitivity codes airfoil sets by name and is tested on wings it has not seen; a filled table gap never turns a bubble flag into 0.5. Still true and important: between similar wings, SA's error on the drag difference is about 4 counts (median), above the 2-count target in 71 % of pairs.</div>
  <h2 style="font-size:22px">What we found, under these assumptions</h2>
  <ol class="concl">
__FD_CONCL__
  </ol>

  <h2 style="font-size:22px">1. The 2-D building blocks</h2>
  <p>Every section, free and tripped, on a grid of 14 Re (1.5 × 10⁴ – 6 × 10⁶) × 3 Mach (0, 0.1, 0.2) × 49 angles (−10° to 14°): 2,408 XFOIL sweeps, made robust (a failing angle is skipped, never hangs). A wing is then evaluated in milliseconds by interpolation. Outside the grid the tool holds Re and Mach at the grid edge (and flags it) and gives no answer for other angles: the full space reaches Re 7.1 × 10³ – 7.6 × 10⁶, and the smallest focus BWB tips (1.4 × 10⁴) sit just below the grid.</p>
  <figure class="fig card">__FA_TAB__ __PNG_FD_SXTR__<figcaption class="cap"><span class="howto">How to read.</span> Ten small maps, one per airfoil (2-D XFOIL, free transition, Mach 0.1). In each map, left to right is the angle the airfoil sees (−6° to 14°) and bottom to top is its Re (4 = 10⁴, 5 = 10⁵, 6 = 10⁶). The colour shows where the flow on the upper surface turns turbulent: yellow = near the trailing edge (long laminar run), dark purple = near the nose. Grey: XFOIL gave no answer (near stall, but also at some small angles). Dashed lines: the four study Re levels.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>On every airfoil the laminar run is long at low Re and small angles, and shrinks as Re or the angle grows. Our wings fly mostly at small angles and Re 10⁵ – 3 × 10⁶, where the run is long; fully turbulent CFD throws it away.</div>
  <figure class="fig card">__FA_TAB__ __PNG_FD_SBUB__<figcaption class="cap"><span class="howto">How to read.</span> Same ten maps and axes. Red: XFOIL finds a laminar separation bubble on the upper surface (the laminar flow lifts off, turns turbulent and lands again). White: no bubble. Grey: no answer.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Every airfoil has bubbles over a wide band, from about Re 6 × 10⁴ to 2 × 10⁶ at small and moderate angles. They change drag and lift, and fully turbulent CFD cannot see them.</div>
  <figure class="fig card">__FA_TAB__ __PNG_FD_SBIAS__<figcaption class="cap"><span class="howto">How to read.</span> Same maps. The colour is the SA drag error of the airfoil: how much more profile drag it gets when made fully turbulent (tripped) than with real free transition. Red: SA gives too much drag (darkest about +150 %). White: about the same. Blue: the real flow has more drag than SA (a long bubble).</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Fully turbulent CFD gives +50 to +150 % profile drag over most of the useful range (Re 3 × 10⁵ – 3 × 10⁶, small angles). It is close only near stall (white), and below about Re 10⁵ the sign flips (blue).</div>
  <h2 style="font-size:20px">The tables rebuilt on the fixed nose (7 Nov 2026)</h2>
  <p>All 2,408 sweeps were run again on the sections of the new nose rule (decision 64; 40 min on 2 workers). The three maps above are from the old tables (first approach); the code now reads the new ones.</p>
  <figure class="fig card">__PNG_TABLES_NOSE__<figcaption class="cap"><span class="howto">How to read.</span> New minus old, against the Re on the section chord (log scale), over the 10 sections, angles −10° to 14° and Mach 0, 0.1 and 0.2. Top: change in the transition position (% c), upper side blue, lower side orange; solid = 95th percentile, dotted = median. Middle: change in drag (%), free transition blue, tripped orange. Bottom: XFOIL answers gained (+) and lost (−), as % of the grid points.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>The fixed nose changes the tables little: the upper transition moves a median 0.19 % c (95 % of points within 1.5 % c) and drag a median 0.8 % (95 % within 9.9 %); the larger changes sit near the 2-D stall and at high Re. On the 20 reference wings × 4 Re levels × 0–10° the SA drag error is +59.0 % (median; +58.1 % on the old tables) and the model category is the same on 480 of 480 conditions: no Stage 1 conclusion changes. Weak spot: on single conditions the share of the half wing with an upper bubble can move by up to 37 points (its mean by 0.3).</div>

  <h2 style="font-size:22px">2. Where the wings fly in Re</h2>
  <figure class="fig card">__FA__ __PNG_FD_BANDS__<figcaption class="cap"><span class="howto">How to read.</span> One panel per type. Left to right: flight Mach (speed). Bottom to top: share of the half wing, 0–100 %. The coloured layers show how much of the half wing sits in each Re band: red below 10⁵, orange 10⁵ – 5 × 10⁵ (bubbles), light blue 5 × 10⁵ – 3 × 10⁶, dark blue above 3 × 10⁶. At any Mach the layers add up to 100 %. Mean over all focus wings, section sets and altitudes.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Slow flight puts most of the wing in the bubble band: at Mach 0.03, 67–91 % of the half wing is at Re 10⁵ – 5 × 10⁵ and 2–13 % is below 10⁵. At Mach 0.14 the bubble band shrinks to 3–16 %. Re above 3 × 10⁶ appears only at the highest speeds (a quarter of the BWB half wing at Mach 0.2, faster than real BWBs fly).</div>

  <h2 style="font-size:22px">3. How wrong is fully turbulent SA?</h2>
  <figure class="fig card">__FA__ __PNG_FD_VIOL__<figcaption class="cap"><span class="howto">How to read.</span> One panel per type; one violin per section set (* = suggested). A violin is wide where many cases have that SA drag error. Dot and bar: the median and the middle 80 % of cases. White diamond: the median in level flight. Green band: ±10 %, where SA would be good enough. Cases: all focus wings at realistic speeds, all angles and altitudes.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>For every type and section set the median error is +34 to +70 %. Few cases fall in the green band: at most 1 % with the suggested sections, at most 15 % (E387; LA2573A 14–15 %). Changing the airfoil does not make SA right.</div>
  <figure class="fig card">__FA__ __PNG_FD_BRE__<figcaption class="cap"><span class="howto">How to read.</span> One panel per type (suggested sections). Left to right: the wing's mean Re (log scale: 5 = 10⁵, 6 = 10⁶). Bottom to top: SA drag error. Each coloured line is the median for one root angle (dark purple 0° to yellow 10°); the grey cloud is all cases. Green band: ±10 %. Dotted red line: Re 10⁵.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>The error is largest near Re 10⁶ at 4–6° root angle, up to about +95 %. At 10° it is smaller (about +30 % on flying wings, +40 to +70 % on the others) but never inside ±10 %. On conventional wings it falls toward zero near Re 10⁵ and turns negative below it (bubbles).</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Section set</th><th>SA drag error, median</th><th>10–90 %</th><th>Within ±10 %</th><th>Laminar run, upper</th><th>Half wing with a bubble</th><th>Half wing with TE separation</th><th>Half wing with a 2-D answer</th></tr></thead>
    <tbody>__FD_STATS__</tbody>
  </table></div>
  <p class="muted">__FD_STATS_NOTE__</p>
  <div class="cbox"><span class="ctag">Conclusion</span>Over all cases at realistic speeds SA is within ±10 % only 5 % of the time. The type changes the median little (+59 to +67 %); on conventional wings the airfoil set matters more (+34 to +67 %).</div>
  <h2 style="font-size:22px">In level flight only</h2>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Rows in level flight</th><th>SA drag error, median</th><th>10–90 %</th><th>Within ±10 %</th><th>Laminar run, upper</th><th>Half wing with a bubble</th><th>Half wing with TE separation</th><th>Rows with part below Re 10⁵</th></tr></thead>
    <tbody>__FD_LEVEL__</tbody>
  </table></div>
  <p class="muted">__FD_TOTAL__</p>
  <div class="cbox"><span class="ctag">Conclusion</span>In level flight (23 % of cases) the error is even larger: median +62 to +78 % by type, within ±10 % in at most 6 %. Counted on the whole drag (profile + induced), fully turbulent CFD is about +18 to +33 % too high.</div>

  <h2 style="font-size:22px">4. Trends</h2>
  <figure class="fig card">__FA__ __PNG_FD_TMACH__<figcaption class="cap"><span class="howto">How to read.</span> Four columns, one per type. Three rows: SA drag error; laminar run on the upper surface (% of chord); share of the half wing with a bubble. Left to right: flight Mach. Line: median; shaded band: the middle half of the cases; one colour per section set. Grey zone: faster than any real wing of that family.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Flying faster (higher Re) shortens the laminar run (about 54 → 39 % of chord) and removes bubbles (from 90 % to 45 % of the half wing). The SA error grows from +44 % at Mach 0.03 to about +70 % at Mach 0.11–0.14 and stays near that. In level flight the rise is steeper: +20 % at Mach 0.03, +81 % at 0.14, +63 % at 0.20.</div>
  <figure class="fig card">__FA__ __PNG_FD_TALPHA__<figcaption class="cap"><span class="howto">How to read.</span> Same layout as above, but left to right is the root angle (0–10°).</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>A higher angle moves transition toward the nose (laminar run 63 → 26 % of chord). The error peaks at about 4° (+81 %) and falls to +40 % at 10°. LA2573A is the exception: its error grows with the angle. Trailing-edge separation stays at 1–2 % of the half wing up to 10°.</div>
  <figure class="fig card">__FA__ __PNG_FD_PART__<figcaption class="cap"><span class="howto">How to read.</span> Six panels, one wing input each: mean chord (size), aspect ratio, washout, sweep, taper, dihedral. Left to right: the input value; bottom to top: SA drag error. Line: median; band: the middle half; one colour per type. Suggested sections, realistic speeds.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Size acts through Re: bigger wings (larger mean chord) have about 15–22 points more error. With the induced angle, aspect ratio now acts too (flying wings: about −14 points from the lowest to the highest aspect ratio), and more washout lowers the error on flying wings (about −9 points). Sweep and dihedral stay within ±6 points: sweep does not enter the strips, and dihedral is the check that shows the noise level.</div>

  <h2 style="font-size:22px">5. Which model, where</h2>
  <figure class="fig card">__FA__ __PNG_FD_CAT__<figcaption class="cap"><span class="howto">How to read.</span> One panel per type (suggested sections). Left to right: flight Mach; bottom to top: root angle. Each cell is one flight condition. Colour: the model the tool proposes for most wings there (green: SA is enough; orange: transition model; red: transition model, part of the half wing below Re 10⁵; grey: no XFOIL answer). Number: the median SA drag error in %. Black frame: half or more of the wings fly level there at a real wing loading.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Almost every cell is orange: these wings need a transition model for drag; SA is adequate in only 2 % of cases. The BWB is red at the slowest speed (part of its half wing below Re 10⁵). In the framed level-flight cells the median error is +32 to +95 %.</div>

  <h2 style="font-size:22px">6. What drives the flow: sensitivity</h2>
  <p>The dataset crosses wings, section sets and conditions in full, so the three groups are independent and their shares can be read apart. A gradient-boosted model (test R² in the table) gives each group's share alone and with its interactions (total).</p>
  <figure class="fig card">__FA__ __PNG_FD_GROUPS__<figcaption class="cap"><span class="howto">How to read.</span> Two panels: tailless and conventional wings. One bar per output (SA drag error, laminar run, bubbles and so on). Each bar splits how much that output varies into what each group explains on its own: blue = wing shape, brown = sections, green = how it flies (speed, angle, altitude); grey = only when the groups act together. On the right, 'total' is each group's share including what it does together with the others.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>In this 2-D model, how the wing flies sets most of the SA error: 53 % on its own for tailless wings (78 % in total). On conventional wings the airfoil matters as much, mostly together with the angle (11 % alone, 54 % in total), so SA would rank airfoils wrongly. The wing shape alone explains 7–8 %. The strips see shape only through chord, twist and the induced angle, and the shares depend on our grid, which crosses every angle with every speed.</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Family</th><th>Output</th><th>Wing shape alone / total</th><th>Sections alone / total</th><th>Flight alone / total</th><th>Model R²</th><th>Strongest inputs (share of importance; ↑ grows with it, ↓ falls)</th></tr></thead>
    <tbody>__FD_DRIVERS__</tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>For the SA error the strongest inputs are the angle (51 %) and Mach (21 %) on tailless wings, and the airfoil set (35 %) and the angle (33 %) on conventional ones. The share of the half wing below Re 10⁵ depends on speed and size (and taper on tailless wings).</div>
  <figure class="fig card">__FA__ __PNG_FD_PERM__<figcaption class="cap"><span class="howto">How to read.</span> Two panels (tailless, conventional). Rows: inputs; columns: outputs. A darker cell means that input matters more for that output: it measures how much worse a fitted model predicts when that input is shuffled (each column adds up to 1). + / −: the output grows / falls as the input grows.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Angle, Mach, size and the airfoil set carry most of the importance. Taper matters for the low-Re tips of tailless wings, washout for where they lose the 2-D answer. Sweep cannot score: the strips do not use it.</div>
  <figure class="fig card">__FA__ __PNG_FD_ETA__<figcaption class="cap"><span class="howto">How to read.</span> Same layout, with a simpler measure that needs no model: the share of the variation one input explains on its own (η²). For wing inputs, values up to about 0.05 are noise: dihedral, which cannot change a strip answer, shows that level.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>The simple measure agrees with the model: angle and Mach dominate, size comes next, and the other wing inputs are near noise level, as expected for inputs the 2-D strips barely use.</div>

  <h2 style="font-size:22px">7. How much do our assumptions change the answer?</h2>
  <p>Each check reruns 20 wings per type with one assumption changed, and compares the same wing, sections and condition (percentage points of the SA drag error, laminar run, bubble share and TE-separation share of the half wing).</p>
  <figure class="fig card">__FA__ __PNG_FD_CHECKS__<figcaption class="cap"><span class="howto">How to read.</span> Left: one box per changed assumption, on the same wings, sections and conditions; it shows how many points the SA drag error moves (line: median; box: the middle half; 0 = no change). Middle: profile drag from the section tables (up) against a direct XFOIL run (across) at 320 random points; dots on the diagonal agree. Right: the same for where the flow turns turbulent.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Only the turbulence level of the air (N<sub>crit</sub>) moves the headline much: N<sub>crit</sub> 5 lowers the error by 11 points (median). Leaving out the induced angle (the old baseline) changes the median by only −4 points, but by up to −41 points at high angle: that is where the old trends went wrong. More or fewer strips and compressibility change almost nothing, and the tables match direct XFOIL (median drag difference 0.7 %). The main finding, SA gives too much drag, holds in every check.</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Changed</th><th>SA error, median change [points]</th><th>5–95 %</th><th>Laminar run, median change [points]</th><th>Bubble share, mean size of change [points]</th><th>TE-separation share, mean size of change [points]</th><th>Pairs</th></tr></thead>
    <tbody>__FD_CHECKS__</tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>Bubbles are the most fragile answer: with N<sub>crit</sub> 5 the bubble share changes by 37 points on average, far more than the laminar run (about 7 points). Bubble results need a 3-D or wind-tunnel check before we rely on them.</div>

  <div class="weak"><strong>Limits of this approach.</strong>
    <ul>
      <li><strong>2-D strips, not a 3-D flow.</strong> No crossflow transition on swept edges, no spanwise boundary-layer drift, no 3-D relief of bubbles, no tip vortex. The induced angle is one uniform (elliptic) value; its spanwise change is not modelled.</li>
      <li><strong>XFOIL is a model too.</strong> e<sup>N</sup> with one N<sub>crit</sub> for the whole wing; it is least reliable below Re 5 × 10⁴, in long bubbles and near stall. "Beyond 2-D stall" means no answer, not a measured stall.</li>
      <li><strong>The grid is a box, not a flight envelope.</strong> Speeds and angles are crossed in full; the level-flight subset uses a wing-loading fit (37 real wings) and a lift estimate, both rough.</li>
      <li><strong>Statistics describe our ranges.</strong> 100 wings per type, drawn evenly in the focus box, four section sets each. Shares and medians depend on those choices; they are not shares of real aircraft.</li>
      <li><strong>The error measure is a proxy.</strong> Tripped vs free 2-D profile drag is the part of the SA error that comes from transition. Real 3-D RANS adds its own errors, and a transition model has its own too.</li>
    </ul></div>
  <h2 style="font-size:22px">The tool, updated</h2>
<pre>pip install -e CFD_Automation                            # once, from the repo root: the shared cfdauto package (outputs: Stage_1_geometry/docs/)
python -m cfdauto.flowmap.tables --build                 # section tables (XFOIL, about 40 min on 2 cores; resumable)
python -m cfdauto.flowmap.dataset                        # the flow dataset (__FD_ROWS__ rows, about 2 min): first approach;
                                                         #   do not rerun as is: it would put every wing at a 1 m mean chord
python -m cfdauto.flowmap.analysis                       # figures, sensitivity, checks: docs/flow_*.png, docs/flow_analysis.json
python -m cfdauto.flowmap --type bwb --set reference --index 0 --speed 13.4 --altitude 0 --alpha 4
                                                         # one wing: flow map, model, where it sits in the dataset. The wing is at
                                                         #   unit mean chord and the tool reads it as 1 m: pick the speed for the Re
                                                         #   you want (here Re 9.2e5 at sea level); its level-flight flag needs a real size
python -m cfdauto.flowmap --type bwb --set reference --index 0 --speed 13.4 --sheet
                                                         # + a Mach × angle sheet: here Mach sets the Re (at a 1 m mean chord,
                                                         #   Mach 0.03–0.20 is Re 7.0 × 10⁵ – 4.7 × 10⁶ at sea level)
python -m cfdauto.flowmap ... --method xfoil | --ncrit 5 | --no-induced | --strips 5   # direct XFOIL, assumption checks</pre>
</section>

<section id="refine">
  <h2>Where the mesh must be fine</h2>
  <p>Each phenomenon above lives in one region of the flow; each region gets its own rule. The rules are the Grand Roadmap recipes (R-S, R-V) and the Stage 0 error budget: the share is how much of the 65 % grid error each direction may use. The last column says what the Stage 2 surface mesher does today (6 Nov 2026: 790 of 790 builds pass its 13 checks, numpy loft); the volume mesh is Stage 3 and not built, so S8's values stay there for reference. Angles now run from −5° to post-stall (decided 6 Nov 2026), and transition must be captured (decided 4 Nov 2026).</p>
  __CHG_REFINE__
  <figure class="fig"><div class="svgwrap">__FIG_RSIDE__</div>
    <figcaption class="cap">Side view: fine cells at the wall (all around), at the nose and at the trailing edge, then a wake box that stays fine for 2 chords and coarsens to 10 chords, all inside the background box. Under review: C-H proposal (pending): the wake box and the background box belong to the overset plan; one matched C-H mesh for both solvers would replace them (SU2 has no overset).</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Cells must be small where the flow changes fast: at the wall, the nose, the trailing edge and the near wake. Further away they can grow. The near wake must hold the wake from −5° to post-stall.</div>
  <figure class="fig"><div class="svgwrap">__FIG_RTOP__</div>
    <figcaption class="cap">Top view: stations nearly even from the root, squeezed toward the tip, and one exactly on each break; outboard blocks past the tip; the wake box behind the whole trailing edge; the vortex tube from about 2 chords behind the tip. Under review: C-H proposal (pending): no wake box and no tube; the outboard blocks would resolve the tip vortex.</figcaption></figure>
  <div class="cbox"><span class="ctag">Conclusion</span>Along the semi-span: more stations near the tip, where the flow changes fastest, and one exactly on each break, where the surface has a kink; the Stage 2 surface mesher builds both. The tip vortex needs fine cells along its path: a tube in the overset plan; with C-H (proposal, pending) the outboard blocks must resolve it.</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Zone</th><th>Captures</th><th>Rule (starting value)</th><th>Budget share</th><th>Source</th><th>Stage 2 today (6 Nov)</th></tr></thead>
    <tbody>__REFINE__</tbody>
  </table></div>
  <p class="muted">Budget shares from Stage 0: chordwise 35 %, spanwise 15 %, wall-normal 20 %, edges and base 15 %, wake 15 % of the grid error; domain 10 % of the total. All values are starting values; the mesh studies (Grand Roadmap stage 4) confirm or replace them.</p>
  <p><strong>Mesh cost (Stage 2, 6 Nov 2026).</strong> At the fine level: median 15.2 M cells with the planned rules; 10.9 M with the relaxed band (0.5 % c spacing where the local Re ≥ 4 × 10⁵; proposal, pending). The owner's target is about 9–11 M cells, so the planned rules miss it. With C-H (proposal, pending) the wake lines would add about +45 % (30–60 %) cells on the wing blocks (rough, not measured).</p>
  <div class="cbox"><span class="ctag">Conclusion</span>Each mesh direction gets its share of the allowed grid error. These are starting rules; the mesh studies will confirm or replace them. The planned rules cost more than the 9–11 M target, so the band rule is the first to test.</div>
</section>

<section id="fix" class="weak">
  <h2>Fixes: done and left</h2>
  <p class="muted">Done on 29 Oct 2026: the unrealistic conventional set (tapered type and per-panel chords), the dihedral input (three panel values) and the hash (from the code itself). Done on 2 Nov 2026 (fix 3): a mesh station on every break. The Stage 2 surface mesher puts a station exactly on every loft station, so its flat faces never cut a kink; 790 of 790 builds pass its 13 checks (numpy loft). Done on 7 Nov 2026: the nose shape (decision 64), below. Fixed on 8 Nov: the label rules at a threshold (decision 79); every input hash changed, no surface did. Left in Stage 1: one more pyGeo <code>build --all</code>.</p>
  <ol>
__FIXES__
  </ol>
</section>

<section id="build">
  <h2>One wing, step by step</h2>
  <div class="card">__GIF_BUILD__</div>
  <p class="cap">Seven steps: design vector, planform, sections, twist and dihedral, trailing edge, loft, measure-label-check. Example: a BWB with every variable at mid-range, at unit mean chord (lengths in mean chords).</p>
  __CHG_BUILD__
  <div class="cbox"><span class="ctag">Conclusion</span>The same seven fixed steps make every wing, and two builds of the same vector give the same surface hash: the generator is repeatable.</div>
</section>

<section id="decisions">
  <h2>Design decisions</h2>
  <p>Every choice behind the generator, with its reason and what it rests on. Details: <code>Stage_1_geometry/decisions/</code> and <code>CFD_Automation/OPEN_DECISIONS.md</code>.</p>
  __CHG_DECISIONS__
  <div class="legend">Basis: __BASIS__ · <span class="flag open">Open</span> needs your call · <span class="flag chg">Changed 7 Nov</span> · <span class="flag gone">Gone 7 Nov</span> kept for the record</div>
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
  __CHG_REAL__
  <div class="three">
    <div class="box"><h3>Real wings fly at</h3><div class="big">Re __RE_LO__ – __RE_HI__</div><p>Lowest: EMT Aladin and Black Swift S0 cruising at 3,048 m. Highest: CTRM Aludra MK1 at its listed top speed, sea level (NTNU; 3.1 × 10⁶, at the top study level). Mean chord = wing area / full span.</p></div>
    <div class="box verdict"><h3>So the top Re level</h3><div class="big">5 × 10⁶ → 3 × 10⁶ → 4 × 10⁶</div><p>No wing of our families reaches 5 × 10⁶. Only the Sperwer (a delta, 6.0 × 10⁶) does; the Vindicator (a target drone above Mach 0.3) comes close (4.8 × 10⁶). Until 8 Nov the levels were 1 × 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶ (3 × 10⁶ was the RUAG Ranger's 2.74 × 10⁶ rounded up; the NTNU Aludra MK1 row since reaches 3.1 × 10⁶). Since 8 Nov (decision 78): 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶, so the Greek tactical UAVs are in (<a href="#greek">Greek tactical UAVs</a>).</p></div>
    <div class="box"><h3>Generator covered them (first approach)</h3><div class="big">__COVER__</div><p>First approach (real size): in the full space each real wing with a published area had a generated wing within 10 % in full span and mean chord, and every Class I full span was inside (sourced and HCDI database). Focus space: BWB __ENV_BWB__; flying wing __ENV_FW__; cranked __ENV_CONV__; tapered __ENV_TAP__. Now this check means nothing: every generated wing has a 1 m mean chord in it.</p></div>
    <div class="box"><h3>Class II</h3><div class="big">Chords 0.54–0.78 m</div><p>13 Class II wings with an area set the aspect ratios and the Re range (first approach: the size ranges): Götten et al. 2021 (5; from images and three-views, about 10–15 %), Essari 2015 (4, Jane's-style: Hermes 450, Ranger, Seeker, Shadow 600), the NTNU RQ-7A Shadow and Aludra MK1 rows, the Pioneer (Bray 1991) and the tailless AUTh RX-3 (4.9 m²). AR 7.0–16. At top speed, where listed, Re 2.0–3.1 × 10⁶. Gap: the RX-3 is the only tailless Class II wing with an area.</p></div>
  </div>
  <figure class="fig card">__PNG_REAL__</figure>
  <p class="cap">First approach (real size, before 7 Nov). Clouds: 2,000 generated wings per type (tailless panel: green BWB, brown flying wing; conventional panel: blue cranked, light blue tapered). Red: real wings with a published area or aspect ratio. Ticks on the full-span axis: real wings with only a full span listed (brown: sources and the NTNU / CNAS databases; violet: HCDI UAS database).</p>
  <div class="cbox"><span class="ctag">Conclusion</span>First approach: the generated clouds covered the real wings: in the focus space 32 of the 34 real wings with an area had a generated wing within 10 % in full span and mean chord, and the full space covered all 34. Now the generator has no size, so any real wing whose shape is in the box has a similar generated wing; what must cover the real wings is the Re range, and it does (1.22 × 10⁵ – 3.10 × 10⁶ inside the levels 10⁵ – 4 × 10⁶; 10⁵ – 3 × 10⁶ until 8 Nov).</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Aircraft</th><th>Family</th><th>Class</th><th>Full span m</th><th>Area m²</th><th>Mean chord m</th><th>AR</th><th>Cruise / max m/s</th><th>Re low – high</th><th>MTOW kg</th><th>HCDI database</th><th>Use</th><th>Source (type)</th></tr></thead>
    <tbody>
__REAL__
    </tbody>
  </table></div>
  <p class="muted">Re low = cruise at 3,048 m; Re high = top speed (cruise if none) at sea level; air from Stage 0. Family from a text source or, where none says it, from photos (marked K in the YAML). Only wings with a published area set the ranges (since 7 Nov: the aspect ratios and the Re range); they rest on: __STYPES__. HCDI database column: the same aircraft in your UAS dashboard, where listed. Notes that say "above Mach 0.3" or "outside phase 1" (Vindicator, CPJ 100-LE) predate 4 Nov 2026: the Mach scope now extends toward 0.5 with no supersonic flow, and such wings wait on a fast-UAV family (proposal, pending).</p>
  <div class="cbox"><span class="ctag">Conclusion</span>Real Class I–II wings fly at Re 1.2 × 10⁵ – 3.1 × 10⁶ on the mean chord. None of our families reaches 5 × 10⁶, so 3 × 10⁶ is the right top study level for the core data (Mach ≤ 0.2). A fast-UAV family (proposal, pending) would reach higher: the Vindicator flies at up to 4.8 × 10⁶.</div>
  <h2 style="font-size:22px">Full spans from the HCDI UAS database (v13)</h2>
  <p>794 entries; 76 fixed-wing Class I–II; 22 give a full span; <strong>none gives a wing area</strong>, so these rows tested the full-span range only ("inside": within 10 % of the focus full-span range of its family, first approach). Every tailless full span was inside, up to 7.3 m. Four conventional Class II wings (8–10 m) were outside the focus space, which stopped at 7 m; the full space covered them. Since 7 Nov there is no full-span range in metres, so this column is first-approach only.</p>
  <div class="weak amber"><strong>Database weak points.</strong> No source per row. 28 rows share cruise 35 m/s, endurance 6 h and range 100 km (look like defaults); on 8 rows cruise is above top speed. Orlan-10 is listed as Class II at 18 kg, Puma LE as a flying wing, XQ-58 Valkyrie (a jet) as Class II; Zala Z-16's maker field names a microchip company. Only full span, class, MTOW and payload are used here.</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Aircraft</th><th>Family</th><th>Class</th><th>Full span m</th><th>MTOW kg</th><th>Payload kg</th><th>Role</th><th>Full span vs generator (first approach)</th><th>Check</th></tr></thead>
    <tbody>
__HCDI__
    </tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>The HCDI database gives full spans only. First approach: every Class I and every tailless full span fitted the focus space; only four conventional Class II wings (8–10 m) needed the full space. Now a full span in metres is only a scale: it sets the Re of a solve, not the wing.</div>
</section>

<section id="checks">
  <h2>Checks and results</h2>
  <div class="three">
    <div class="box"><h3>Gate 1 · vector → loft</h3><p>Measured on the loft: chords within 0.1 %, sweeps 0.1°, twist 0.2°, dihedral 0.2°, aspect ratio 0.1 %.</p></div>
    <div class="box"><h3>Gate 2 · trailing edge</h3><p>Thickness equals the rule (0.2 % of the local chord) at every section, within 1e-6 mean chords (1 µm on the real-size wings before 7 Nov).</p></div>
    <div class="box"><h3>Gate 3 · validity</h3><p>Sections closed, upper never below lower, root flat in y = 0 within 1e-9 mean chords, chords positive; since 7 Nov also no nose that folds back (the nose gate).</p></div>
    <div class="box"><h3>Gate 4 · repeatability</h3><p>Two builds give the same surface hash.</p></div>
  </div>
  <p class="muted">A wing that fails any gate is not written; its row keeps the gate and the reason. The fifth check, mesh on the loft within 1e-9, is done in Stage 2: the surface mesher asks every node from the loft and checks that every ring lies in its station plane within 1e-9; 790 of 790 builds pass its 13 checks (numpy loft, on the first-approach wings). On the 7 Nov wings: 1,724 of 1,724 (numpy loft), and on 8 Nov on pyGeo (your machine) the 20 reference wings gave the same meshes as the numpy loft.</p>
  __CHG_CHECKS__
  <h2 style="font-size:22px">Sample sets</h2>
  <div class="tbl"><table class="mid">
    <thead><tr><th>Type</th><th>Set</th><th>Wings</th><th>Result</th><th>Type by the rules</th></tr></thead>
    <tbody>
__SETS__
    </tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>All 722 sampled wings (7 Nov, numpy loft) build and pass the four checks; none is refused. The type rules usually agree with the sampled type, but not always: 15 of the 100 focus BWBs read as flying wings by the rule (14 before 7 Nov), and many corner wings read as the neighbouring type. The Stage 2 surface mesher meshed all 730 first-approach wings (790 builds, with the 20 reference wings at all four Re levels) with 0 refusals; on 7 Nov it screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (every set at VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels, again on 8 Nov at the new Re levels; 4 F builds after one nose repair). Every hash changed on 7 Nov; with pyGeo on your machine (8 Nov) all 722 build too, with the same input hashes, and the reference meshes equal the numpy ones (VC and F). One label of 722 differed between the two lofts (a sweep change of exactly 5°, the kink threshold); fixed on 8 Nov (decision 79), with every input hash new and every surface the same.</div>
  <h2 style="font-size:22px">Is the loft the designed wing? (every sampled wing)</h2>
  <p class="muted">Worst value over every training, corner and reference wing (<code>scripts/verify_sets.py</code>, numpy loft). Stations, chords, twists, sweeps, panel dihedrals and the straightness of each panel match the inputs to machine precision. AR: the loft measures the true chord, which is a little shorter between two stations of different twist; the aspect ratio still matches within __VS_AR__ %. Sections: within __VS_SEC__ % of chord on every wing (before 7 Nov up to 0.02 % c, on the smallest corner wings, where the 0.5 mm trailing-edge floor was a large share of the chord; the floor is gone). Root: every point of the root section at y = 0, and no point of a half wing below y = 0, so the mirrored halves meet only there. Lengths in mean chords.</p>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Type</th><th>Wings</th><th>Stations % c</th><th>Chord %</th><th>Twist °</th><th>Sweep °</th><th>Dihedral °</th><th>Straight panels % c</th><th>AR %</th><th>Sections % c</th><th>Ruled % c</th><th>Root |y|</th><th>Min y</th></tr></thead>
    <tbody>
__VSETS__
    </tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>The loft is the designed wing: stations, chords, twists, sweeps and dihedrals match the inputs to machine precision, and the sections within __VS_SEC__ % of the chord on every wing (before 7 Nov up to 0.02 %, where the mm floor was large).</div>
  <h2 style="font-size:22px">Is the surface the intended wing? (published wings)</h2>
  <p class="muted">Errors in % of local chord. Sections: the loft cut at each station against the original airfoil points (limit 0.01). This compares only at the file's own points, so it cannot see the nose between them: the <a href='#nose'>nose study</a> (decision 64) measured that part, along the arc. Since 7 Nov the check finds the section's frame on its own, as the new rule does. Edges: against the exact straight lines (limit 1e-6). Outside CAD: only the M6 has one (limit 0.05; it needs gmsh, which is not installed here).</p>
  <div class="tbl"><table class="mid">
    <thead><tr><th>Wing</th><th>Sections max</th><th>Edges max</th><th>Outside CAD</th><th>Result</th></tr></thead>
    <tbody>
__VERIFY__
    </tbody>
  </table></div>
  <div class="cbox"><span class="ctag">Conclusion</span>Every published wing passes on 7 Nov: sections within __VP_SEC__ % of the chord at the file's points (0.003 % before 7 Nov), edges exact. The ONERA M6 was within 0.011 % of the chord of its CAD model on 2 Nov (first approach); that check was not rerun here (no gmsh), and it now scales the CAD by <code>real_mean_chord_m</code>. The nose between the file's points is the nose study's job (decision 64).</div>
</section>

<section id="open" class="weak amber">
  <h2>Open decisions</h2>
  <p class="muted"><span class="flag open">decide</span> needs your call. <span class="flag ok">act</span> a task with no choice left. Full history: <code>CFD_Automation/OPEN_DECISIONS.md</code> (items 67–76 are the 4–6 Nov decisions and proposals; its items 64, 70 and 75 still read as open or planned: on this page 64 and 70 are decided and built, 7 Nov, and the 6 Nov note 75 was wrong).</p>
  __CHG_OPEN__
__OPEN__
</section>

<section id="limits" class="weak">
  <h2>What it cannot make (yet)</h2>
  <ul>
__LIMITS__
  </ul>
  __CHG_LIMITS__
</section>

<section id="published">
  <h2>Published wings it rebuilds</h2>
  <div class="card">__GIF_REF__</div>
  <p class="cap">Each frame is a wing rebuilt by the same generator, with the same loft and checks as the sampled wings. BlendedNet wings are made directly from the BlendedNet parameters. Like every wing, each copy is built at unit mean chord; the sizes shown are the real ones (lengths × <code>real_mean_chord_m</code>).</p>
  __CHG_PUBLISHED__
  <div class="cbox"><span class="ctag">Conclusion</span>The same generator rebuilds the ONERA M6, RIBES, NASA CRM and BlendedNet wings, so our meshes and results can be compared with published data.</div>
  <div class="card">__PNG_TOP__</div>
  <div class="cbox"><span class="ctag">Conclusion</span>Scaled by their root chord, the copies show the planforms of the published wings: the conventional M6, RIBES and CRM, and the four BlendedNet BWBs, which differ mostly in the centre-body chords and the outer sweep. The scale does not change the shape, so the unit-mean-chord copies are the same wings.</div>
  <div class="tbl"><table class="wide">
    <thead><tr><th>Wing</th><th>Family</th><th>Size</th><th>What it is for</th><th>How close the copy is</th><th>Sources</th></tr></thead>
    <tbody>
__ROWS__
    </tbody>
  </table></div>
  <p class="muted">The "What it is for" and "How close" texts come from <code>configs/published_wings.yaml</code>. Read "outside phase 1" and "kept for the transonic stage" as out of date: the scope has no supersonic flow and extends toward Mach 0.5 (decided 4 Nov 2026), so the M6 and the CRM are shape and mesh checks only. The M6's Re 11.72 × 10⁶ is on its MAC (0.646 m); its mean chord (area / full span) is 0.630 m. RIBES is tripped at 1.4 % chord: it checks fully turbulent RANS, not transition. Its "span 1.600 m" is the semi-span of the half model. Since 7 Nov the YAML keeps every wing at its real size; the copy is built at unit mean chord and <code>meta["real_mean_chord_m"]</code> scales it back (the M6 CAD check uses it).</p>
  <div class="card">__PNG_CRM__</div>
  <p class="cap">NASA CRM against its published 21-station table. Chords match exactly; with four stations the twist is off by at most 0.51°.</p>
  <div class="cbox"><span class="ctag">Conclusion</span>Four stations give the CRM chords exactly but not its smooth twist (up to 0.51° off): good for mesh tests, not for matching CRM force data exactly.</div>
</section>

<section id="commands">
  <h2>Commands</h2>
<pre>cd CFD_Automation/Stage_1_geometry
pip install -e ..                                                    # once: the shared cfdauto package
python -m cfdauto.geometry.sample                                    # write the sets
python -m cfdauto.geometry.build --type bwb --set training_focus --index 7  # one wing
python -m cfdauto.geometry.build --all                               # every training, corner, reference wing (pyGeo)
python -m cfdauto.geometry.published_wings --build all               # M6, RIBES, CRM, BlendedNet (pyGeo)
python scripts/verify_geometry.py                                    # is the surface the intended wing?
python -m pytest -m "not pygeo"                                      # tests without pyGeo
python scripts/make_generator_visuals.py                             # the GIFs and pictures
python scripts/verify_sets.py                                        # loft vs design on every built wing
python scripts/real_uav_check.py                                     # real wings: Re and aspect ratios (its coverage in metres is
                                                                     #   first approach: meaningless at unit mean chord; not rerun)
python scripts/size_extremes.py                                      # extreme shapes at unit mean chord, local Re at the levels
python scripts/nose_curvature.py [--database]                        # the nose study (decision 64)
python scripts/design_space_figs.py                                  # design space, key pairs, families
python scripts/xfoil_band.py                                         # 2-D free vs tripped (needs xfoil)
python scripts/focus_flowmaps.py                                     # flow maps of the focus space (needs xfoil)
python -m cfdauto.flowmap.tables --build                             # section tables: XFOIL on a Re x Mach x angle grid (resumable)
python -m cfdauto.flowmap.dataset                                    # the flow dataset (201,600 rows; first approach, not rebuilt)
python -m cfdauto.flowmap.analysis                                   # trends, sensitivity, checks: docs/flow_*.png, flow_analysis.json
python -m cfdauto.flowmap --type bwb --set reference --index 0 --speed 13.4 --altitude 0 --alpha 6 --sheet
                                                                     # the tool: one wing's flow map, model, Mach x angle sheet; the wing is
                                                                     #   read as a 1 m mean chord: pick the speed for the Re you want
python scripts/make_generator_page.py                                # this page</pre>
</section>

<footer>Generated by <code>CFD_Automation/Stage_1_geometry/scripts/make_generator_page.py</code> from <code>configs/wing.yaml</code>, the set manifests and <code>docs/verification.json</code>. Decision notes: <code>Stage_1_geometry/decisions/</code>.</footer>
</div>
"""


SECTION_ORDER = ("glance", "change", "pipeline", "runs", "summary", "design", "pairs", "family", "ranges", "inputs", "nose", "reynolds", "phenomena", "flowmaps", "flowdata", "refine",
                 "open", "decisions", "fix", "build", "real", "checks", "limits", "published", "commands")


def open_html() -> str:
    f = DOCS / "flow_analysis.json"
    fd = json.loads(f.read_text()) if f.is_file() else None
    rep = {"__FD_MED__": _pc(fd["bias_all"]["median"]) if fd else "(run the analysis)",
           "__FD_LF__": _pc(fd["level_flight"]["bias_all"]["median"]) if fd else "—",
           "__FD_OK__": _pc(fd["bias_all"]["share_sa_ok"], False) if fd else "—",
           "__FD_N5__": _pt(fd['checks']['ncrit_5']['sa_bias']['median'], 0) if fd else "—"}
    out = []
    for g in dict.fromkeys(x[0] for x in OPEN):          # groups in order of first appearance
        items = [x for x in OPEN if x[0] == g]
        n_dec = sum(1 for x in items if x[3] == "decide")
        out.append(f"<h3>{g} <span class='muted'>({n_dec} to decide)</span></h3><ul>")
        for _, t, q, k in items:
            for a_, b_ in rep.items():
                q = q.replace(a_, b_)
            flag = {"decide": "<span class='flag open'>decide</span>",
                    "later": "<span class='flag later'>later stage</span>"}.get(k, "<span class='flag ok'>act</span>")
            out.append(f"<li>{flag} <strong>{t}.</strong> {q}</li>")
        out.append("</ul>")
    return "\n".join(out)


def reorder_sections(page: str) -> str:
    """Put the sections in reading order: overview and pictures first, details and evidence after."""
    import re
    blocks = {m.group(1): m.group(0) for m in re.finditer(r'<section id="([a-z]+)"[^>]*>.*?</section>', page, re.S)}
    if page.count("<section") != len(blocks):          # a section without an id would be dropped silently
        raise ValueError("every <section> needs an id and a place in SECTION_ORDER")
    missing = [k for k in blocks if k not in SECTION_ORDER]
    if missing:
        raise ValueError(f"sections without a place in SECTION_ORDER: {missing}")
    first = page.index(blocks[SECTION_ORDER[0]])
    end = max(page.index(b) + len(b) for b in blocks.values())
    body = "\n\n".join(blocks[k] for k in SECTION_ORDER if k in blocks)
    return page[:first] + body + page[end:]


CHG = {   # the amber "What changes (7 Nov 2026)" box of each section it touches
    "__CHG_PIPE__": "Step 1 now has 17 inputs and no size: every wing is built at unit mean chord. Step 3 has no full-span cap; the focus wings run at the four Re levels on the mean chord. Steps 4–5 (flow maps, flow dataset) were made at real size and real speed before 7 Nov (first approach) and are not rebuilt.",
    "__CHG_RUNS__": "The geometry now has 722 wings at unit mean chord (7 Nov; 730 at real size before). The nose study (decision 64) is new. The 2-D XFOIL airfoil study (A) was rerun on 7 Nov on the sections of the new nose rule. The section tables (B) were rebuilt on the fixed nose on 7 Nov (no conclusion changes; the maps in this section are from the old tables). The flow maps, the flow dataset and the assumption checks used the first-approach wings and the old tables, and are not rebuilt.",
    "__CHG_SUMMARY__": "The size rows are gone: no full span or root chord in metres. Chords are in mean chords, the aspect ratio is the full span, and the Re on the mean chord is an input (the four levels) instead of following from real sizes and speeds. The local-Re row gives the smallest tip at the lowest level and the largest root at the top level. First approach (real size and speed): full span about 0.4–7 m (focus), Mach 0.03–0.13 (tailless) or 0.03–0.20 (conventional), Re about 5 × 10⁴ – 3.5 × 10⁶ on the mean chord.",
    "__CHG_DESIGN__": "The size rows are now in mean chords: the aspect ratio (= the full span), the root chord (derived, 1 / K) and the tip chord (derived). Real wings are marked by their aspect ratio only: their size in metres means nothing for a wing at unit mean chord. The first-approach rows (root chord, full span and mean chord in metres) are gone from this figure, and the focus samples now fill the whole box (no 7 m cap).",
    "__CHG_PAIRS__": "The size pair (full span against mean chord, in metres) belongs to the first approach: at unit mean chord every wing has a mean chord of 1. It is kept below, marked first approach. The other three pairs have no size; they were redrawn on 7 Nov, with the focus samples filling the whole box (no 7 m cap).",
    "__CHG_FAMILY__": "Nothing changes in these shapes: they are the same at unit mean chord; only the size is gone.",
    "__CHG_RANGES__": "This section was <em>Sizes we can make</em> (true scale, in metres). Since 7 Nov a wing has no size, so it now shows the extreme shapes in mean chords. The first-approach sizes at real scale are kept below as the record.",
    "__CHG_INPUTS__": "The root chord left the inputs (18 → 17 names; 16 / 12 / 16 / 12 sampled, 17 / 13 / 17 / 13 before). The semi-span is AR / 2 and the root chord 1 / K, in mean chords. The trailing edge is 0.2 % of the local chord on every wing. The airfoil rule changed too (decision 64): see <a href='#nose'>Nose study</a>.",
    "__CHG_REYNOLDS__": "The Re on the mean chord is now an input of each solve: every shape runs at all four levels. Before, the Re followed from the real size and the real speed of each wing (kept below as the first approach). The real-wing Re (1.22 × 10⁵ – 3.10 × 10⁶) did not change; it is on area / full span, the mean chord the levels use.",
    "__CHG_PHENOMENA__": "The Re figures now use the Re levels (an input) instead of real sizes and speeds. The 2-D XFOIL runs below were redone on 7 Nov on the sections of the new nose rule (the numbers moved by at most 4 points). The trailing edge is 0.2 % c on every wing; the CFD runs at Mach 0.1.",
    "__CHG_FLOWMAPS__": "These maps were made on 31 Oct–2 Nov at real size and real speed (the first-approach mid wings) and are not rebuilt. The tool still takes a speed (or Mach) and an altitude, and it now reads a unit-mean-chord wing as a wing with a 1 m mean chord: to set an Re on the mean chord, give the speed V = Re / (ρ/μ) (ρ/μ = 6.85 × 10⁴ s/m² at sea level). Its level-flight flag needs a real size.",
    "__CHG_FLOWDATA__": "This dataset was made at real size and real speed before 7 Nov (the 400 first-approach focus wings, full span ≤ 7 m, at speeds, altitudes and angles) and is not rebuilt: it is the first-approach record. In similarity form each shape would run at the four Re levels on the mean chord, at Mach 0.1. Its findings (SA's error, the bubbles, the bands) are statements about those wings at those Re, and they still guide the mesh and the model choice. The level-flight subset needs a real size. The 2-D section tables are size-free and were rebuilt on the fixed nose on 7 Nov: on the 20 reference wings at the four Re levels (0–10°) the SA drag error moves from +58.1 % to +59.0 % (median) and the model category stays the same on 480 of 480 conditions, so these findings stand.",
    "__CHG_REFINE__": "No switch sections (the trailing edge is 0.2 % c everywhere), so the loft stations sit only at b0–b3. The nose is the 7 Nov nose (apex leading edge, 201 points per side); on a NACA 4415 station the 10° target holds up to a nose spacing of 0.377 % c with it (0.327 % c with the old rule). Every wing is at unit mean chord, so the first cell follows from y⁺ = 1 at each case's Re. The Stage 2 values in the last column were measured on the first-approach wings (790 builds).",
    "__CHG_BUILD__": "The GIF is redrawn at unit mean chord: 17 numbers (no root chord), lengths in mean chords, trailing edge 0.2 % of the local chord.",
    "__CHG_DECISIONS__": "Decisions 64 (the nose) and 70 (similarity) are decided and built. Rows marked <span class='flag chg'>Changed 7 Nov</span> carry the new rule, with the first approach in grey. Three rows are gone and kept for the record: the 7 m cap, the wing class and the switch section. One row is new: the nose gate.",
    "__CHG_REAL__": "The real wings now set the aspect ratios and the Re range only. Every generated wing is at unit mean chord, so the coverage in this section (a generated wing within 10 % in full span and mean chord, in metres) compares real wings with wings of a 1 m mean chord: it means nothing now. It is the first-approach check (30 Oct–6 Nov), kept as the record. <code>scripts/real_uav_check.py</code> still runs, but its coverage numbers in metres are meaningless, so it was not rerun. The Re of each real wing (on area / full span) still holds: 1.22 × 10⁵ – 3.10 × 10⁶, inside the four levels.",
    "__CHG_CHECKS__": "722 wings (730 before): corner 1 has 32 or 24 wings (the two root-chord corners went). The gates read lengths in mean chords; the trailing-edge gate checks 0.2 % c; the validity gate also refuses a nose that folds back. The loft check was rerun on all 722 wings on 7 Nov (numpy loft), and the published-wing check on all 7.",
    "__CHG_OPEN__": "Decisions 64 (the nose) and 70 (similarity) left this list: they are decided and built. The trailing-edge floor question is gone (0.2 % c on every wing). New: the similarity checks C1–C4 and the flow dataset in similarity form. The Re levels are kept (you, 7 Nov). The 6 Nov note that the nose finding was overstated (item 75) was wrong.",
    "__CHG_LIMITS__": "New limits since 7 Nov: similarity carries size through Re, but not roughness, air turbulence or the thicker trailing edges of small real wings (checks C1–C4 to run); the nose gate refuses 14 database files; the flow data are first approach.",
    "__CHG_PUBLISHED__": "The YAML keeps each published wing at its real size; the copy is built at unit mean chord, and <code>meta[\"real_mean_chord_m\"]</code> scales it back to metres (the M6 CAD check uses it). The pictures and the table show real sizes. Every hash changed on 7 Nov.",
}


def tokens() -> dict:
    """Numbers for the text, read from the data (filled in after every other placeholder)."""
    others = ("flying_wing", "cranked", "tapered")
    cov = []
    for t in WING_TYPES:
        c = json.loads((SETS / t / "reference.json").read_text())["coverage"]
        cov.append((t, c["coverage"], c["random_median"]))
    ver = json.loads((DOCS / "verification.json").read_text()) if (DOCS / "verification.json").is_file() else []
    out = {
        "__S_BWB_ROOT__": f"{F['bwb']['root_chord'][1]:.2f}", "__S_BWB_TIP__": f"{F['bwb']['tip_chord'][0]:.3f}",
        "__S_BWBU_ROOT__": f"{U['bwb']['root_chord'][1]:.2f}", "__S_BWBU_TIP__": f"{U['bwb']['tip_chord'][0]:.3f}",
        "__S_BWB_RATIO__": f"{F['bwb']['root_over_tip_max']:.0f}",
        "__S_OTHER__": f"{min(U[t]['tip_chord'][0] for t in others):.2f}–{max(U[t]['root_chord'][1] for t in others):.2f}",
        "__S_BWB_RETIP__": sci(F["bwb"]["re_tip_min"]), "__S_BWB_REROOT__": sci(F["bwb"]["re_root_max"]),
        "__S_OTHER_RE__": f"{sci(min(F[t]['re_tip_min'] for t in others))} – {sci(max(F[t]['re_root_max'] for t in others))}",
        "__S_TIPW_REROOT__": sci(LV[0] * TIPW["root_chord"]), "__S_TIPW_RETIP__": sci(LV[0] * TIPW["tip_chord"]),
        "__S_TIPW_RATIO__": f"{TIPW['root_chord'] / TIPW['tip_chord']:.0f}",
        "__REFCOV__": ("Coverage distance (lower is better) " + ", ".join(f"{TYPE_NAME[t]} {c:.2f}" for t, c, _ in cov)
                       + ", against a median of " + " / ".join(f"{m:.2f}" for _, _, m in cov) + " for 1,000 random sets of five."),
        "__VP_SEC__": f"{max(r['sections_max_pct'] for r in ver):.2g}" if ver else "—",
        "__FA__": FA, "__FA_TAB__": FA_TAB,
    }
    return out | vsets_max() | {k: chg(v) for k, v in CHG.items()}


def main() -> None:
    m = manifests()
    g = glance(m)
    fixes = "\n".join(
        f"<li class='fixrow'><strong>{t}</strong>{e.replace('__VERSION__', __version__)} <span class='do'>Do: {d}</span></li>"
        for t, e, d in FIXES)
    real_rows, real = real_table()
    env = real["envelope"]
    fr = (final_ranges_html() | extremes_html() | {"__FIG_RE__": fig_re_map(), "__XF_NOTE__": xfoil_note(), "__FIG_PIPE__": fig_pipeline(), "__FIG_RUNS__": fig_runs(), "__FIG_SURF__": fig_surfaces(), "__FMTABLE__": flowmap_table(), "__SUMMARY__": summary_html(),
                                "__FIG_RSIDE__": fig_refine_side(), "__FIG_RTOP__": fig_refine_top(), "__REFINE__": refine_html(),
                                "__VSETS__": verification_sets_html(), "__CHANGE_TABLE__": change_table(), "__NOSE_TABLE__": nose_table()}
                                | vsets_max() | params_tables_html() | flowdata_html())
    page = PAGE
    for k, v in fr.items():
        page = page.replace(k, v)
    page = (page.replace("__REAL__", real_rows)
                .replace("__STYPES__", stype_counts(json.loads((DOCS / "real_uavs.json").read_text())["rows"]))
                .replace("__HCDI__", hcdi_table(json.loads((DOCS / "real_uavs.json").read_text())))
                .replace("__PNG_REAL__", img("first_approach/real_uavs.png", "First approach: real wings against generated wings at real size, full span and mean chord"))
                .replace("__PNG_NOSE__", img("nose_curvature.png", "Nose curvature study: the built nose against the raw file, old and new rule"))
                .replace("__PNG_TABLES_NOSE__", img("section_tables_nose.png", "Section tables rebuilt on the fixed nose: new minus old, by Re"))
                .replace("__PNG_GREEK__", img("greek_uavs.png", "Greek tactical UAVs against the Re levels: Re on the mean chord from cruise to top speed"))
                .replace("__PNG_LADDER__", img("re_ladder_check.png", "Check C4 on 2-D data: drag read between the Re levels, old against new levels"))
                .replace("__RE_LO__", sci3(real['re_low_min']))
                .replace("__RE_HI__", sci3(real['re_high_max']))
                .replace("__COVER__", cover_text())
                .replace("__ENV_BWB__", f"full span {env['bwb']['span_m'][0]:.1f}–{env['bwb']['span_m'][1]:.1f} m, mean chord {env['bwb']['mean_chord_m'][0]:.2f}–{env['bwb']['mean_chord_m'][1]:.2f} m")
                .replace("__ENV_CONV__", f"full span {env['cranked']['span_m'][0]:.1f}–{env['cranked']['span_m'][1]:.1f} m, mean chord {env['cranked']['mean_chord_m'][0]:.2f}–{env['cranked']['mean_chord_m'][1]:.2f} m")
                .replace("__ENV_FW__", f"full span {env['flying_wing']['span_m'][0]:.1f}–{env['flying_wing']['span_m'][1]:.1f} m, mean chord {env['flying_wing']['mean_chord_m'][0]:.2f}–{env['flying_wing']['mean_chord_m'][1]:.2f} m")
                .replace("__ENV_TAP__", f"full span {env['tapered']['span_m'][0]:.1f}–{env['tapered']['span_m'][1]:.1f} m, mean chord {env['tapered']['mean_chord_m'][0]:.2f}–{env['tapered']['mean_chord_m'][1]:.2f} m")
                .replace("__GIF_BUILD__", img("how_a_wing_is_built.gif", "Seven-step animation of one wing being built"))
                .replace("__PNG_LOCALRE__", img("local_re.png", "Local chord Reynolds number along the semi-span of the smallest and largest wing of each type"))
                .replace("__PNG_XFCF__", img("xfoil_cf.png", "XFOIL upper-surface skin friction, free transition vs tripped, at the four study Re levels"))
                .replace("__PNG_XFTR__", img("xfoil_transition.png", "Where the real flow turns turbulent, per section and Re"))
                .replace("__PNG_FMEX__", img("flowmap_example.png", "Flow map of the BWB mid wing: local Re, transition line, bubbles, phenomena and proposed model"))
                .replace("__PNG_FMEX_SHEET__", img_opt("flowmap_example_sheet.png", "Mach by angle sheet of the BWB mid wing"))
                .replace("__FMEX_CAP__", fmex_caption())
                .replace("__PNG_FM_BWB__", img("flowmap_bwb.png", "BWB mid wing flow maps: three section sets, slow and fast"))
                .replace("__PNG_FM_FW__", img("flowmap_flying_wing.png", "Flying-wing mid wing flow maps"))
                .replace("__PNG_FM_CR__", img("flowmap_cranked.png", "Cranked mid wing flow maps"))
                .replace("__PNG_FM_TA__", img("flowmap_tapered.png", "Tapered mid wing flow maps"))
                .replace("__PNG_FD_SXTR__", img_opt("flow_sections_xtr.png", "Transition maps of the ten sections"))
                .replace("__PNG_FD_SBUB__", img_opt("flow_sections_bub.png", "Laminar bubble maps of the ten sections"))
                .replace("__PNG_FD_SBIAS__", img_opt("flow_sections_bias.png", "Drag ratio tripped over free for the ten sections"))
                .replace("__PNG_FD_BANDS__", img_opt("flow_re_bands.png", "Share of the half wing in each Re band against Mach"))
                .replace("__PNG_FD_VIOL__", img_opt("flow_bias_violins.png", "Distribution of the SA drag error per type and section set"))
                .replace("__PNG_FD_BRE__", img_opt("flow_bias_vs_re.png", "SA drag error against wing mean Re per root angle"))
                .replace("__PNG_FD_TMACH__", img_opt("flow_trends_mach.png", "Trends with flight Mach"))
                .replace("__PNG_FD_TALPHA__", img_opt("flow_trends_alpha.png", "Trends with root angle"))
                .replace("__PNG_FD_PART__", img_opt("flow_partial.png", "SA drag error against single wing inputs"))
                .replace("__PNG_FD_CAT__", img_opt("flow_categories.png", "Proposed model per Mach and angle"))
                .replace("__PNG_FD_GROUPS__", img_opt("flow_groups.png", "Variance shares of wing shape, sections and flight condition"))
                .replace("__PNG_FD_PERM__", img_opt("flow_sensitivity_perm.png", "Permutation importance per input and output"))
                .replace("__PNG_FD_ETA__", img_opt("flow_sensitivity_eta2.png", "First-order variance share per input and output"))
                .replace("__PNG_FD_CHECKS__", img_opt("flow_checks.png", "Assumption checks and table verification"))
                .replace("__FD_ROWS__", fd_rows())
                .replace("__PNG_XFBAND__", img("xfoil_band.png", "XFOIL profile-drag increase when tripped, and transition position, against Re"))
                .replace("__PNG_DESIGN__", img("design_space.png", "Every variable: full range, focus range and published values per wing type"))
                .replace("__PNG_PAIR_SIZE__", img("first_approach/pair_size.png", "First approach: full span against mean chord per type, at real size"))
                .replace("__PNG_PAIR_PLANFORM__", img("pair_planform.png", "Aspect ratio against taper per type"))
                .replace("__PNG_PAIR_SWEEP__", img("pair_sweep.png", "Aspect ratio against sweep per type"))
                .replace("__PNG_PAIR_TWIST__", img("pair_twist.png", "Sweep against washout per type"))
                .replace("__PNG_FAM_BWB__", img("family_bwb.png", "BWB family: one variable group at a time"))
                .replace("__PNG_FAM_CONV__", img("family_cranked.png", "Cranked family: one variable group at a time"))
                .replace("__PNG_FAM_TAP__", img("family_tapered.png", "Tapered family: one variable group at a time"))
                .replace("__PNG_FAM_FW__", img("family_flying_wing.png", "Flying-wing family: one variable group at a time"))
                .replace("__GIF_SIZES__", img("size_extremes.gif", "Lowest and highest aspect ratio of each type, focus and full space, at unit mean chord"))
                .replace("__GIF_SIZES_FIRST__", img("first_approach/size_extremes.gif", "First approach: smallest and largest wing of each type, true scale"))
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
                .replace("__STALE__", (f"built with code {g['versions']}; the code changed after these builds, "
                                       f"so every stored hash is stale: rebuild once (<code>build --all</code>)."
                                       if g["stale"] else f"built with the current code, loft backend: {g['backend']}."))
                .replace("__VERSION__", __version__)
                .replace("__N_AIRFOILS__", f"{len(airfoils.available()):,}"))
    for k, v in tokens().items():          # last: numbers inside the hand-written lists and the amber boxes
        page = page.replace(k, v)
    left = sorted(set(__import__("re").findall(r"__[A-Z][A-Z0-9_]+__", page)))
    if left:
        raise SystemExit(f"placeholders left on the page: {left}")
    out = DOCS / "GEOMETRY_GENERATOR.html"
    page = reorder_sections(page)
    out.write_text(page)
    print(f"{out}  {out.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
