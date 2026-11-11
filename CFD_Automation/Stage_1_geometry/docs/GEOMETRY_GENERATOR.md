# Stage_1 — Wing Generator page (text copy, updated 11 Nov 2026)

CFD_Automation · Stage 1 · geometry · code 0.7.0 · updated 11 Nov 2026

# Wing Generator

Seventeen numbers and four airfoil names go in; one exact wing surface comes out, measured, labelled and checked. One generator and one YAML file make BWB, cranked, tapered and flying wings, shaped like real Class I and II UAVs. Since 7 Nov 2026 every wing is built at unit mean chord: it has no size, and size enters the CFD only as the Re on the mean chord. On the same day the nose rule changed, so the built nose now follows the airfoil file. Every later stage (mesh, solver, data) reads only this surface. The section What was first, and what changes and an amber *What changes* box in every section it touches say what the two changes changed.

## At a glance

**Words used on this page.** **Full span b**: tip to tip, both halves. **Semi-span S = b / 2**: root to one tip, the half wing we build and mesh (mirrored at y = 0). **Families**: tailless (types BWB, flying wing) and conventional (types cranked, tapered). **Focus space**: realistic wing shapes, sampled densely. **Full space**: everything supported, sampled sparsely. **Mean chord c̄** = area / full span (not the MAC). **Unit mean chord**: every wing is built with c̄ = 1, so lengths are in mean chords and the full span equals the aspect ratio. **First approach**: what was built and studied at real size, 30 Oct–6 Nov 2026.

### In

17 numbers + a wing type

From `configs/wing.yaml`: the aspect ratio (the semi-span follows: AR / 2), panel shares, chord ratios, sweeps, twists, dihedrals, and an airfoil per station. Types: BWB, cranked, tapered, flying wing. No size: every wing at unit mean chord (the root chord left the vector on 7 Nov: 18 → 17).

### Out

One surface, checked

Upper, lower and trailing-edge base, read as `upper(u, v)`. Plus measured values, labels, four refusing checks, a hash, IGES.

### Evidence

722 of 722 wings pass

Sampled wings of all four types, focus and full space, 0 refused (code 0.7.0, pygeo loft). 7 of 7 published wings verified (ONERA M6, RIBES, NASA CRM and four BlendedNet designs). Tests: 181 pass, 13 skipped here (12 need pyGeo, 1 needs gmsh; 11 Nov 2026); on Mike's machine with pyGeo and gmsh 203 pass, 3 skipped (XFOIL not installed there; 11 Nov).

### Verdict

Stage 1 closed; Stage 2 under way

Fixes 1–3 done: panel dihedrals and code hash here; a mesh station on every break, made by the Stage 2 surface mesher (790 of 790 builds pass its 13 checks, on the first-approach wings). Done on 7 Nov: similarity (decision 70) and the nose fix (decision 64); every hash changed and the sets were rebuilt. Done on 8 Nov on your machine: the pyGeo tests (24 of 24) and `build --all` with pyGeo (722 of 722). Fixed on 8 Nov: the label rules at a threshold (decision 79; every input hash changed, no surface). Done on 11 Nov on your machine: the pyGeo `build --all` after the label fix (722 of 722, the same input hashes, pass flags and labels). The raw XFOIL data is in git since 9 Nov. Stage 2 has screened the 7 Nov wings: on 8 Nov every built set at every level, 3,128 of 3,128 builds pass with no nose repair (Study 12; the 20 reference wings at the four Re levels, the rest at 3 × 10⁵). Not yet "any wing": straight panels only, no airfoil shape variable. Sets: built with the current code, loft backend: pygeo.

**What changed since 2 Nov 2026 (updated 9 Nov).**

- **Decided.**
  - Repo renamed: `Stage_1_geometry/`; one shared `cfdauto` package (`pip install -e CFD_Automation`); sets `training_focus` / `holdout_focus`; one `CFD_Automation/OPEN_DECISIONS.md` for all stages.
  - The Stage 2 surface mesh works: on the 7 Nov wings 3,128 of 3,128 builds pass the 13 checks (every built set, the four levels, numpy loft; Study 12, 8 Nov). It puts a station on every loft station, so one sits on every break (fix 3 done); the tip squeeze and the transition band are built.
  - Transition must be captured, with ADflow and SU2 (4 Nov).
  - Angles of attack: −5° to post-stall, plus a separate post-stall study (6 Nov).
  - Volume mesh: one matched C-H mesh for both solvers (you, 6 Nov; decision 73), built in Stage 3.
  - **Surface rules frozen (you, 9 Nov; decisions 81, 82):** the transition band stays on for every run, SA and LM alike (one mesh family for both solvers; with it off the BWB tip cap fails at M); a rule changes only when a check fails or a solver result shows a problem.
  - **The hold-outs opened once for the surface mesh (you, 9 Nov; decision 83):** the 60 sealed wings built (60 of 60 pass the four gates) and meshed with the frozen rules: 960 of 960 builds pass (Stage 2 Study 14). They stay closed for tuning the volume mesh and the solver. The overset volume-mesh plan is kept as a fallback (decision 73, 9 Nov).
  - The Mach scope extends toward 0.5, with no supersonic flow (4 Nov); the data on this page stop at Mach 0.2.
  - First SU2 smoke test (4 Nov): SU2 ran SA and LM on one Stage 2 ring mesh (a section extruded between two symmetry planes, 97,920 cells, Re 3 × 10⁵, Mach 0.15, 4°); after about 370 iterations, not converged: SA CL 0.860, CD 0.0184; LM CL 0.908, CD 0.0137. It shows the mesh path works; no wing has been run.
  - **Re levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ (you, 8 Nov; were 1.5 × 10⁶ and 3 × 10⁶):** the Greek tactical programmes (LOTUS, Archytas, ACTUS) are in scope, and 1 × 10⁶ fills the old ×5 gap (check C4 on 2-D data). Same 8,000 solves. The 2-D section tables gain the rows 1 × 10⁷ and 1.5 × 10⁷. See Greek UAVs and the Re levels.
  - **Label tolerance, built 8 Nov (decision 79; you):** every label rule now takes a value exactly at its threshold (the kink tests had no tolerance: on a sweep change of exactly 5° the pyGeo and numpy lofts disagreed; a wing at AR exactly 8 missed its label). 2 labels changed, no type; every input hash changed; the surfaces and meshes did not.
  - **Similarity, built 7 Nov (decision 70):** every wing at unit mean chord; the root chord out of the vector (18 → 17); trailing edge 0.2 % c on every wing; no 7 m cap; the Re on the mean chord is an input (the four levels, kept). 722 of 722 wings built.
  - **Nose fix, built 7 Nov (decision 64):** leading edge at the apex of one cubic spline through the raw points, both sides from that spline, 201 points per side; a nose gate. The 6 Nov note that the nose finding was overstated (item 75) was wrong.
- **Proposals (pending).**
  - Solver split: ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings.
  - Mach: core data at Mach ≤ 0.2 now; 0.3–0.5 later, with a fast-UAV family.
- **Open.**
  - Similarity checks C1–C4 (CFD): scale, Mach, trailing edge, Re levels.

## What was first, and what changes (7 Nov 2026)

Stage 1 was built and studied with a first approach from 30 Oct to 6 Nov 2026: every wing at real size, in metres. On 7 Nov two changes went into the code. **Similarity** (decision 70, decided by you on 6 Nov): every wing is built at unit mean chord, so a wing has no size, and size enters each solve as the Re on the mean chord. **The nose fix** (decision 64, decided by you on 7 Nov): the built nose now follows the airfoil file at the size of a mesh cell. The code, the tests and the wing sets are done. This page keeps the first-approach content where it is still the record (what was built and studied 30 Oct–6 Nov), marks it first approach, and says in an amber *What changes* box in every section what changed there.

| What | First (30 Oct–6 Nov 2026) | Now (7 Nov 2026) | Decided | Status |
| --- | --- | --- | --- | --- |
| Size (similarity, decision 70) | Every wing at real size. The root chord was sampled in metres (BWB 0.40–1.80 m; cranked and tapered 0.13–0.75 m; flying wing 0.25–1.05 m); semi-span S = AR · c<sub>root</sub> · K / 2. | Every wing at **unit mean chord**: mean chord = area / full span = 1. Lengths are in mean chords. The root chord left the vector: 18 → 17 names (c2–c4 ratios, semi_span_m, aspect_ratio, b3_ratio, split_ratio, sweep1–3, twist0–3, dihedral_p1–3, plus 4 airfoils); 16 sampled for BWB and cranked, 12 for tapered and flying wing. S = AR / 2; root chord = 1 / K. | you, 6 Nov | built 7 Nov |
| Mean chord | Area / full span in the code; some texts said MAC. | Area / full span: the geometric mean chord, not the MAC (on a BWB the MAC is 1.09–2.06 × larger). It is 1 on every wing; the MAC is only measured. | Stage 0, 7 Nov | built 7 Nov |
| Re and Mach | Re followed from the real size and the real speeds of each family: focus 5.4 × 10⁴ – 3.5 × 10⁶ on the mean chord; Mach 0.03–0.20. | The Re on the mean chord is an **input of each solve**: the four Stage 0 levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ (since 8 Nov; were 1.5 × 10⁶ and 3 × 10⁶). Real Class I–II wings fly at 1.22 × 10⁵ – 3.10 × 10⁶ (on area / full span), so 1 × 10⁵ sits 18 % below the slowest real UAV: kept as a margin. Mach 0.1 with a Prandtl–Glauert correction on CL and CM, on the solver side (check C2). | levels: Stage 0; margin: you, 7 Nov | input of each solve |
| Trailing edge | Class I max(0.5 mm, 0.2 % c), Class II max(1.0 mm, 0.2 % c); a section added where the rule switched. Edges 0.20–4.17 % c; 370 of the 730 wings had an edge set by a floor. | **0.2 % of the local chord on every wing.** No floors, no wing class, no switch section; a config that still names a size is refused. Check C3 (CFD, to come): 0.1 / 0.2 / 0.3 % c and the real floor of small wings, about 0.42 % c. | you, 6 Nov | built 7 Nov |
| Full-span cap | The focus space ended at full span b = 7 m: the focus sets kept only wings within it. | Gone. At unit mean chord the full span is the aspect ratio, which has its own range. | with 70 | built 7 Nov |
| Sets | 730 wings built (numpy loft). Focus sets: a Latin hypercube, wings above 7 m dropped in draw order. Corner 1: 34 or 26 wings. | 722 of 722 built (7 Nov, numpy loft). Focus sets: the same 200-row draw, the first 100 kept, so 99 / 90 / 91 / 88 of the 100 focus shapes are the same (BWB / flying wing / cranked / tapered; the cap had chosen by root chord). Training full, hold-out full and corner 2 keep their shapes; corner 1 has 32 or 24 wings (the two root-chord corners went). Chords 0.062–3.60 mean chords; aspect ratio = full span in mean chords, 2.5–20. | with 70 | built 7 Nov |
| Reference picks | Mid-range; smallest and largest area; most sweep with the smallest tip; strongest washout. | Smallest / largest area → lowest / highest aspect ratio (at unit mean chord the area is the aspect ratio); the tip chord is ranked in mean chords. 13 of the 20 reference wings are new picks; 7 are kept (the 4 mid-range wings and 3 of the 4 strongest-washout wings). | with 70 | built 7 Nov |
| Labels | A value exactly at a threshold could lose its label by rounding: 35 wings at exactly 1.0° washout had no washout label. | A tolerance of 1e-9: a value at the threshold gets the label. | 7 Nov (fix) | built 7 Nov |
| Nose rule (decision 64) | Leading edge at the farthest raw point; each side resampled in √x with a square tangent (PCHIP), 101 points per side. Along the arc: a curvature spike on one side, a flat spot on the other; the 5 % turning-per-cell test failed on all ten suggested airfoils (NACA 4415: a 0.18 % c nose cell turned 9.47°; the true shape turns 4.31°). | One cubic spline through the raw points (natural ends at the trailing edge); leading edge = its apex (the spline point farthest from the trailing-edge midpoint); both sides sampled from that spline, **201 points per side**. Passes on all ten (worst −3.9 %) and on 95.6 % of the database (old rule 21.0 %). Side effects: the leading edge moves by a median 0.046 % c (max 1.69 % c); the chord line turns by a median 0.027° (max 0.96°; NACA 4415 0.12°). | you, 7 Nov | built 7 Nov |
| Nose gate | None. | A section whose nose folds back (curvature below −1000/c within 3 % c of arc) is refused: 14 database files, none used. | with 64 | built 7 Nov |
| The 6 Nov nose note (item 75) | “The first reading was overstated: measured the same way, the raw files show nearly the same split.” | **That note was wrong.** The one-sided formula read the raw points, and the built section passes through them, so it saw the same split. The defect sat between the raw points. Measured along the arc the built split was real, and larger at the leading edge than first read (NACA 4415 radius 0.0018 / 0.155 c, not 0.008 / 0.074 c). | 7 Nov (study) | corrected |
| Section tables (2-D XFOIL) | 2,408 sweeps (10 airfoils + 3 blends, 14 Re × 3 Mach × 49 angles) on the sections of the old nose rule. | **Rebuilt on the fixed nose** (7 Nov, 40 min). Upper transition moves a median 0.19 % c (95 % of points within 1.5 % c), drag a median 0.8 %; the larger changes sit near the 2-D stall and at high Re. SA drag error on the 20 reference wings × 4 Re levels × 0–10°: +59.0 % median (+58.1 % on the old tables); the model category is the same on 480 of 480 conditions. No Stage 1 conclusion changes. | with 64 | rebuilt 7 Nov |
| Flow maps and flow dataset | Flow maps and 201,600 dataset rows: the focus wings at real size and real speed (Mach 0.03–0.20, root angles 0–10°, 3 altitudes), from the section tables. | **Not rebuilt**: they stay the first-approach record. In similarity form each shape would run at the four Re levels instead of speeds and altitudes, and the level-flight flag needs a real size. The 2-D section tables are size-free; they were rebuilt on the fixed nose (row above). | — | not rebuilt |
| Hashes, pyGeo, Stage 2 | Stored hashes stale since the 2 Nov rename; Stage 2 meshed the 730 first-approach wings (790 builds). | Every geometry hash changed on 7 Nov; the sets are rebuilt with the numpy loft, and on 8 Nov with pyGeo on your machine (722 of 722; the manifests now say pygeo). After the label fix of 8 Nov, again with pyGeo on your machine on 11 Nov (722 of 722, the same input hashes, pass flags and labels). Stage 2 screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (every set at VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels), and on 8 Nov every set at every level: 3,128 of 3,128, with no nose repair (one factor per family). | — | rebuilt 11 Nov |

**Conclusion.** Two changes, both built. Similarity takes size out of the geometry: one mesh family per shape serves every size, and the four Re levels (which cover the real wings) set the size of each solve. The nose fix makes the built nose turn like the airfoil within 5 % per mesh cell on all ten suggested airfoils (it failed on all ten before). Both changed every hash; the 722 wings are rebuilt and checked. Still first approach: the flow maps and the flow dataset (made at real size before 7 Nov). Stage 2 has screened the 7 Nov wings: on 8 Nov every built set at every level, 3,128 of 3,128 builds pass with no nose repair (Study 12). The pyGeo build ran on 8 Nov (722 of 722; the same meshes on the reference wings) and again on 11 Nov after the label fix (722 of 722, the same input hashes, pass flags and labels). Owed: the similarity checks C1–C4.

## The plan in five steps

From everything the generator can draw, down to the wings we study, to what the flow does on them, to a tool that does this for any wing.

<figure class="fig">
<p><em>[Diagram: Five steps: full design space, what the parametrization can make, the focus space, flow maps, and the tool that takes a wing and returns its flow map and a proposed model]</em></p>
</figure>

1.  **Full design space** (Design space): every input range we support, light bars.
2.  **What we can make** (What it cannot make, Checks): straight panels, vertical sections, any database section; no curved edges, winglets or fuselage.
3.  **Focus** (Final ranges and flows): the shapes of Class I and small Class II wings, sourced; dark bars. Every wing at unit mean chord, run at the four Re levels.
4.  **Flow maps** (Flow maps, Flow dataset): local Re from root to tip, where the flow turns turbulent, bubbles, and how the sections change them, per family; then every focus wing × 4 section sets × 126 conditions, with trends, sensitivity and checks.
5.  **The tool** (`python -m cfdauto.flowmap`): give it a wing, a speed (or Mach), an altitude and an angle; it names the family and type, draws the flow map, proposes the turbulence model with the size of the SA error, says whether the condition is level flight at a real wing loading, and where the wing sits in the dataset. `--sheet` adds the whole Mach × angle picture.

**What changes (7 Nov 2026).** Step 1 now has 17 inputs and no size: every wing is built at unit mean chord. Step 3 has no full-span cap; the focus wings run at the four Re levels on the mean chord. Steps 4–5 (flow maps, flow dataset) were made at real size and real speed before 7 Nov (first approach) and are not rebuilt.

**Conclusion.** We look wide but study densely where real wings are. The generator makes the wings; 2-D flow runs on them say which turbulence model and which mesh refinement each wing needs; the tool does the same for any new wing.

## What was run: 2-D, 3-D, and how 2-D becomes 3-D

No 3-D CFD has been run on a wing yet (a first SU2 smoke test ran on 4 Nov on one Stage 2 ring mesh: see At a glance). All flow results on this page come from XFOIL, which solves one 2-D airfoil at a time. Strip theory turns those 2-D answers into wing results: the half wing is cut into strips, each strip is treated as its own airfoil at its own Re and angle, and the strips are added up.

<figure class="fig">
<p><em>[Diagram: What was run. 2-D XFOIL runs on single airfoils: an airfoil study and the section tables, plus direct checks. Strip theory turns the tables into 3-D wing results for the flow maps, the flow dataset and the checks. The geometry generator and the real UAV database feed it. No 3-D CFD on a wing has been run yet.]</em></p>
</figure>

| Study (section of this page) | What ran | Tool | How many |
| --- | --- | --- | --- |
| Design space, Key pairs, Wing families, Sizes | planform maths on sampled design vectors | generator | 1,500–2,000 vectors per type and space; no flow |
| Checks and results | wings built, measured and checked | generator (numpy loft) | 722 wings (7 Nov; 730 before) |
| Nose study (decision 64) | curvature along the arc: raw files against the built sections | script, numpy loft | 10 airfoils; 2,183 database files |
| Real wings | real sizes and speeds against the generated wings (first approach) | database check | 34 wings with an area, 112 full spans |
| Reynolds and Mach | Re = (ρ / μ) · V · chord | formula | no runs |
| Flow phenomena (2-D) | A: free vs tripped airfoils (rerun 7 Nov on the new sections) | XFOIL | 32 polars (0–8°) + 32 runs at exactly 2° |
| Flow maps | strip theory on the section tables (B) | flow-map engine | 1 example + 24 focus maps |
| Flow dataset | strip theory on the section tables (B) | flow-map engine | 201,600 wing cases |
| Flow dataset: sensitivity | statistics on the 201,600 cases | gradient-boosted model | no new flow runs |
| Flow dataset: assumption checks | the same 80 wings with one assumption changed; tables vs direct | engine + XFOIL (C) | 6 × 40,320 cases; 320 direct runs; 3 blend pairs |
| Where the mesh must be fine | rules from Stage 0 and the roadmap (built since in Stage 2) | none | no runs |
| 3-D CFD on a wing | none yet; a first SU2 smoke test (SA and LM) ran on one Stage 2 ring mesh on 4 Nov, not converged | ADflow SA, SU2 SST + LM (planned) | 0 wings |

**What changes (7 Nov 2026).** The geometry now has 722 wings at unit mean chord (7 Nov; 730 at real size before). The nose study (decision 64) is new. The 2-D XFOIL airfoil study (A) was rerun on 7 Nov on the sections of the new nose rule. The section tables (B) were rebuilt on the fixed nose on 7 Nov (no conclusion changes; the maps in this section are from the old tables). The flow maps, the flow dataset and the assumption checks used the first-approach wings and the old tables, and are not rebuilt.

**Conclusion.** No 3-D CFD has been run on a wing yet. Every flow number on this page is 2-D XFOIL, used alone (airfoil study) or added up along the semi-span by strip theory (wing results). These numbers show where to look and which model to use; 3-D CFD must confirm them before they go into the paper (proposal, pending: SU2 SST + LM on about 20 % of the wings first).

## Final ranges and flows

Everything in one table, at unit mean chord. **Bold**: the focus space (realistic, sampled densely). Grey: the full space (supported, sampled sparsely). Chords are in mean chords; the extremes come from all corners of the planform inputs (others mid-range). Study Re levels on the mean chord: 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ (since 8 Nov; were 1.5 × 10⁶ and 3 × 10⁶).

**What changes (7 Nov 2026).** The size rows are gone: no full span or root chord in metres. Chords are in mean chords, the aspect ratio is the full span, and the Re on the mean chord is an input (the four levels) instead of following from real sizes and speeds. The local-Re row gives the smallest tip at the lowest level and the largest root at the top level. First approach (real size and speed): full span about 0.4–7 m (focus), Mach 0.03–0.13 (tailless) or 0.03–0.20 (conventional), Re about 5 × 10⁴ – 3.5 × 10⁶ on the mean chord.

<table class="wide summ">
<colgroup>
<col style="width: 20%" />
<col style="width: 20%" />
<col style="width: 20%" />
<col style="width: 20%" />
<col style="width: 20%" />
</colgroup>
<thead>
<tr class="header">
<th></th>
<th colspan="2">Tailless</th>
<th colspan="2">Conventional</th>
</tr>
<tr class="odd">
<th></th>
<th>BWB</th>
<th>Flying wing</th>
<th>Cranked</th>
<th>Tapered</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td class="what">Shape</td>
<td>Long centre body, strong taper, cranked</td>
<td>Straight edges, moderate taper, swept</td>
<td>Constant-chord centre, tapered outer panels</td>
<td>Straight edges root to tip (rectangular at taper 1)</td>
</tr>
<tr class="even">
<td class="what">Aspect ratio = full span b (in mean chords)</td>
<td><strong>3–9</strong><br />
full 2.5–10</td>
<td><strong>3–13</strong><br />
full 2.5–14</td>
<td><strong>4.5–16.5</strong><br />
full 3–20</td>
<td><strong>4.5–16.5</strong><br />
full 3–20</td>
</tr>
<tr class="odd">
<td class="what">Root chord, mean chords (derived: 1 / K)</td>
<td><strong>1.57–2.83</strong><br />
full 1.32–4.90</td>
<td><strong>1.05–1.54</strong><br />
full 1.00–1.67</td>
<td><strong>1.02–1.37</strong><br />
full 1.00–2.36</td>
<td><strong>1.00–1.43</strong><br />
full 1.00–1.60</td>
</tr>
<tr class="even">
<td class="what">Tip chord, mean chords</td>
<td><strong>0.099–0.511</strong><br />
full 0.055–0.919</td>
<td><strong>0.462–0.947</strong><br />
full 0.333–1.00</td>
<td><strong>0.439–0.883</strong><br />
full 0.234–1.00</td>
<td><strong>0.571–1.00</strong><br />
full 0.400–1.00</td>
</tr>
<tr class="odd">
<td class="what">Overall taper (tip / root)</td>
<td><strong>0.06–0.2</strong><br />
full 0.04–0.25</td>
<td><strong>0.3–0.9</strong><br />
full 0.2–1</td>
<td><strong>0.38–0.85</strong><br />
full 0.17–1</td>
<td><strong>0.4–1</strong><br />
full 0.25–1</td>
</tr>
<tr class="even">
<td class="what">LE sweep (per panel)</td>
<td><strong>15–40 / 15–35 / 5–25°</strong><br />
full 10–60 / 10–60 / 0–60°</td>
<td><strong>10–40°</strong><br />
full 0–60°</td>
<td><strong>−3 to 3 / −5 to 10 / 0–15°</strong><br />
full −15 to 35 / −15 to 35 / −15 to 35°</td>
<td><strong>−5 to 15°</strong><br />
full −15 to 35°</td>
</tr>
<tr class="odd">
<td class="what">Washout (root − tip)</td>
<td><strong>1–9°</strong><br />
full −9 to 16°</td>
<td><strong>0–8°</strong><br />
full −9 to 16°</td>
<td><strong>0–5°</strong><br />
full −9 to 11°</td>
<td><strong>0–5°</strong><br />
full −9 to 11°</td>
</tr>
<tr class="even">
<td class="what">Dihedral (per panel)</td>
<td><strong>0–3 / 0–5 / 0–5°</strong><br />
full −10 to 10°</td>
<td><strong>0–5°</strong><br />
full −10 to 10°</td>
<td><strong>0–5°</strong><br />
full −10 to 10°</td>
<td><strong>0–5°</strong><br />
full −10 to 10°</td>
</tr>
<tr class="odd">
<td class="what">Suggested sections b0–b3</td>
<td>mh104, mh104, mh61, mh61</td>
<td>mh60, mh60, mh45, mh45</td>
<td>naca4415, naca4415, naca4412, naca4412</td>
<td>naca4415, naca4415, naca4412, naca4412</td>
</tr>
<tr class="even">
<td class="what">Re on the mean chord (an input)</td>
<td>1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶: every shape at all four</td>
<td>1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶: every shape at all four</td>
<td>1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶: every shape at all four</td>
<td>1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶: every shape at all four</td>
</tr>
<tr class="odd">
<td class="what">Local Re: smallest tip at 10⁵ · largest root at 4 × 10⁶</td>
<td><strong>9.9 × 10³ · 1.1 × 10⁷</strong><br />
full 5.5 × 10³ · 2.0 × 10⁷</td>
<td><strong>4.6 × 10⁴ · 6.2 × 10⁶</strong><br />
full 3.3 × 10⁴ · 6.7 × 10⁶</td>
<td><strong>4.4 × 10⁴ · 5.5 × 10⁶</strong><br />
full 2.3 × 10⁴ · 9.4 × 10⁶</td>
<td><strong>5.7 × 10⁴ · 5.7 × 10⁶</strong><br />
full 4.0 × 10⁴ · 6.4 × 10⁶</td>
</tr>
<tr class="even">
<td class="what">Mach (CFD)</td>
<td>0.1, with a Prandtl–Glauert correction (check C2)</td>
<td>0.1, with a Prandtl–Glauert correction (check C2)</td>
<td>0.1, with a Prandtl–Glauert correction (check C2)</td>
<td>0.1, with a Prandtl–Glauert correction (check C2)</td>
</tr>
<tr class="odd">
<td class="what">Main flow features</td>
<td>Two regimes on one wing (centre body 5–17× the tip Re); spanwise flow and tip stall from sweep; kinks at b1, b2; thick 15 % centre body</td>
<td>Trim by sweep and washout with reflexed sections; spanwise flow; tip stalls first at high angle</td>
<td>Kinks at the breaks (suction peaks, loading jump); low sweep; at the lowest level (10⁵ on the mean chord) the outer panels run below 10⁵</td>
<td>Smooth loading; low sweep; tips at lower Re as taper grows; tip vortex weaker at high AR</td>
</tr>
<tr class="even">
<td class="what">Mesh must resolve</td>
<td>LE and TE everywhere; a station on each kink; tip; wake and tip vortex; one first cell (the smallest chord sets it), more wall layers at the centre body</td>
<td>LE and TE; tip (stall, vortex); wake behind a swept TE</td>
<td>LE and TE; a station on each break; tip vortex; wake</td>
<td>LE and TE; tip vortex; wake</td>
</tr>
</tbody>
</table>

**Conclusion.** Four types in two families, from one generator, every wing at unit mean chord. The focus aspect ratios run from 3 (tailless) to 16.5 (conventional); the BWB alone has a long root (up to 2.83 mean chords) and a small tip (down to 0.099). Every shape runs at the four Re levels, which cover the real wings (1.22 × 10⁵ – 3.10 × 10⁶). Inside one wing the local Re reaches further: from about 9.9 × 10³ at the smallest BWB tip (lowest level) to 1.1 × 10⁷ at the largest BWB root (top level). Tailless wings are swept and washed out to fly without a tail; conventional wings are nearly straight. Every type needs a fine mesh at the leading and trailing edges, the tip and the wake.

Details: Design space, Shapes, Re and MachGreek UAVs, Flow phenomena, Where to refine.

## Design space: what we support, where real wings are, where we focus

One row per variable, one lane per wing type. **Light bar**: the full space (everything the generator supports; 40 wings + 5 hold-out per type, both corner sets at its edges). **Dark bar**: the focus space (where real wings are; 100 wings + 5 reference + 10 hold-out per type). **Black marks**: real wings and published designs. Rows marked "derived" are computed from the inputs.

**What changes (7 Nov 2026).** The size rows are now in mean chords: the aspect ratio (= the full span), the root chord (derived, 1 / K) and the tip chord (derived). Real wings are marked by their aspect ratio only: their size in metres means nothing for a wing at unit mean chord. The first-approach rows (root chord, full span and mean chord in metres) are gone from this figure, and the focus samples now fill the whole box (no 7 m cap).

<figure class="fig card">
<p><em>[Figure: Every variable: full range, focus range and published values per wing type]</em></p>
<figcaption>Read a row left to right: if the black marks sit inside the dark bar, the focus space covers the real wings; the light bar shows how far beyond them we still promise to work. The first three rows are in mean chords: the aspect ratio (= the full span), the root chord (derived, 1 / K) and the tip chord (derived). Root twist only sets the incidence; washout is what changes the wing. Sources: <code>configs/shape_evidence.yaml</code>, <code>configs/real_uavs.yaml</code>.</figcaption>
</figure>

**Conclusion.** Most real and published values (black marks) sit inside the dark focus bars, so the focus space covers real wings. A few sit only inside the light full-space bars: the lowest real tailless aspect ratio (2.9, just below the focus 3), a second-hand flying-wing washout of 10°, and one published range of the BWB chord at b2. The full space is needed, but rarely.

**What the figure shows honestly.** Shape evidence is thin for conventional wings (Raymer rules, partly second-hand) and for the layout shares (one BWB paper). Aspect ratios are well covered (34 real wings). The full space is our choice, set to the widest value in any source; nothing real sits at its far edges.

## Key pairs

The same three layers in two dimensions, one panel per type. Faint dots: full space. Strong dots: focus space. Black diamonds: real or published wings that give both values.

**What changes (7 Nov 2026).** The size pair (full span against mean chord, in metres) belongs to the first approach: at unit mean chord every wing has a mean chord of 1. It is kept below, marked first approach. The other three pairs have no size; they were redrawn on 7 Nov, with the focus samples filling the whole box (no 7 m cap).

<figure class="fig card">
<p><em>[Figure: First approach: full span against mean chord per type, at real size]</em></p>
<figcaption><strong>Size, first approach</strong> (real size, before 7 Nov): full span b (tip to tip) against mean chord, in metres. Every real Class I–II wing with a published area, against its family (tailless: BWB and flying wing; conventional: cranked and tapered).</figcaption>
</figure>

**Conclusion.** First approach: the focus space covered 32 of the 34 real wings with a published area (a generated wing within 10 % in full span and mean chord); the other two, Hermes 450 and Götten UAV 9, were larger than 7 m and only the full space covered them. Now this pair has no meaning: every wing has a mean chord of 1, and its full span is its aspect ratio (next figure). Size enters only as the Re on the mean chord, and the four levels cover the real wings (see Re and MachGreek UAVs).

<figure class="fig card">
<p><em>[Figure: Aspect ratio against taper per type]</em></p>
<figcaption><strong>Planform</strong>: aspect ratio against overall taper. The BWB lives at very low taper (big centre body), the others at 0.3–1.</figcaption>
</figure>

**Conclusion.** Taper separates the BWB from the rest: only the BWB has a very small tip (4–25 % of the root chord). The other three types overlap (taper 0.2–1), so the type rules use the kink and the root chord, not taper alone.

<figure class="fig card">
<p><em>[Figure: Aspect ratio against sweep per type]</em></p>
<figcaption><strong>Sweep</strong>: aspect ratio against inner-panel leading-edge sweep. Published sweeps given at the quarter chord (marked c/4 in the sources) sit a few degrees below their leading-edge value.</figcaption>
</figure>

**Conclusion.** Sweep separates the families. Tailless wings are swept to fly without a tail (BWB 15–40°, flying wing 10–40°, focus); conventional wings are nearly straight (cranked −3 to 3°, tapered −5 to 15°). The real wings sit inside these ranges.

<figure class="fig card">
<p><em>[Figure: Sweep against washout per type]</em></p>
<figcaption><strong>Trim</strong>: sweep against washout. Tailless wings trim with sweep and washout together; the published tailless wings sit inside the focus space.</figcaption>
</figure>

**Conclusion.** Tailless wings need washout as well as sweep (focus: BWB 1–9°, flying wing 0–8°); conventional wings need little (0–5°). The published tailless wings that give both values sit inside the focus box.

## Wing families

For each type, one variable group at a time goes from the full minimum to the full maximum; all others stay at the focus mid-range. Columns 2–4 (solid) are the focus space; columns 1 and 5 (dashed) are the edges of the full space. Top views are scaled to equal full span so the shape is visible; aspect ratios and chords in mean chords are in Shapes we can make.

**What changes (7 Nov 2026).** Nothing changes in these shapes: they are the same at unit mean chord; only the size is gone.

<figure class="fig card">
<p><em>[Figure: BWB family: one variable group at a time]</em></p>
</figure>

**Conclusion.** BWB: aspect ratio, chords and sweep change the shape most. The solid (focus) shapes look like real BWBs; the dashed full-space edges (AR 2.5, 60° sweep, 16° washout) are extreme, but still valid wings the mesher must handle.

<figure class="fig card">
<p><em>[Figure: Cranked family: one variable group at a time]</em></p>
</figure>

**Conclusion.** Cranked: aspect ratio changes the shape most (stubby AR 4.5 to slender AR 16.5); the crank is mild and the sweep small. The dashed edges (−15° and 35° sweep, AR 20) are there only to test robustness.

<figure class="fig card">
<p><em>[Figure: Tapered family: one variable group at a time]</em></p>
</figure>

**Conclusion.** Tapered: like the cranked wing without the crank. Aspect ratio and taper set the shape; the sweep stays small (−5 to 15°). The dashed edges are there only to test robustness.

<figure class="fig card">
<p><em>[Figure: Flying-wing family: one variable group at a time]</em></p>
</figure>

**Conclusion.** Flying wing: sweep and aspect ratio set the shape (10–40°, AR 3–13). Moving the breaks does not change its outline (straight edges); it only moves where the sections and the twist change.

## Shapes we can make (unit mean chord)

The input ranges are in Parameters. This is what they produce. Every wing has a mean chord of 1, so its area and its full span both equal its aspect ratio; chords are in mean chords.

**What changes (7 Nov 2026).** This section was *Sizes we can make* (true scale, in metres). Since 7 Nov a wing has no size, so it now shows the extreme shapes in mean chords. The first-approach sizes at real scale are kept below as the record.

<figure class="fig">
<p><em>[Figure: Lowest and highest aspect ratio of each type, focus and full space, at unit mean chord]</em></p>
<figcaption>Lowest and highest aspect ratio of each type at the corners of the planform inputs (aspect ratio, chord ratios, panel shares), other inputs at mid-range, at unit mean chord. Solid: focus space. Dashed: full space. A bar of 1 mean chord in each view; the same scale in every frame. The last frame shows the four focus types together.</figcaption>
</figure>

**Conclusion.** At unit mean chord the types differ by shape alone. The aspect ratio runs from 3 to 16.5 in the focus space and from 2.5 to 20 in the full space. The BWB is the extreme one: a root of up to 2.83 mean chords and a tip down to 0.099 in the focus space (4.90 and 0.055 in the full space), up to 17 × from root to tip. The flying wing and the conventional types stay within 0.23–2.36 mean chords, even in the full space.

| Type | Space | Aspect ratio (= full span) | Root chord | Tip chord | Overall taper | Root / tip, at most |
| --- | --- | --- | --- | --- | --- | --- |
| BWB | **focus** | 3 – 9 | 1.572 – 2.831 | 0.099 – 0.511 | 0.06 – 0.20 | 16.7 × |
| BWB | full | 2.5 – 10 | 1.320 – 4.904 | 0.055 – 0.919 | 0.04 – 0.25 | 25.0 × |
| Flying wing | **focus** | 3 – 13 | 1.053 – 1.539 | 0.462 – 0.947 | 0.30 – 0.90 | 3.3 × |
| Flying wing | full | 2.5 – 14 | 1.000 – 1.667 | 0.333 – 1.000 | 0.20 – 1.00 | 5.0 × |
| Cranked | **focus** | 4.5 – 16.5 | 1.015 – 1.369 | 0.439 – 0.883 | 0.38 – 0.85 | 2.6 × |
| Cranked | full | 3 – 20 | 1.000 – 2.361 | 0.234 – 1.000 | 0.17 – 1.00 | 6.0 × |
| Tapered | **focus** | 4.5 – 16.5 | 1.000 – 1.429 | 0.571 – 1.000 | 0.40 – 1.00 | 2.5 × |
| Tapered | full | 3 – 20 | 1.000 – 1.600 | 0.400 – 1.000 | 0.25 – 1.00 | 4.0 × |

Extremes over all corners of the planform inputs (other inputs mid-range), in mean chords. The built sets stay inside them: their chords run 0.062–3.60 mean chords, their aspect ratios 2.5–20. `python scripts/size_extremes.py`.

## First approach: sizes at real scale (30 Oct–6 Nov 2026)

Kept as the record: the wings of the first approach, at real size, in metres. The flow maps and the flow dataset on this page used them.

<figure class="fig">
<p><em>[Figure: First approach: smallest and largest wing of each type, true scale]</em></p>
<figcaption>First approach: smallest and largest wing (least and most area) of each type at the corners of the size inputs (then including the root chord in metres), other inputs at mid-range, true scale. Solid: focus space. Dashed: full space. Left view 0.6 m wide, right view 22 m wide; the same scale in every frame.</figcaption>
</figure>

| Type | Space | Full span b (tip to tip) | Wing area | Mean chord | Root chord | Tip chord |
| --- | --- | --- | --- | --- | --- | --- |
| BWB | **focus** | 0.42 – 6.7 m | 0.060 – 6.4 m² | 0.14 – 0.95 m | 0.40 – 1.79 m | 0.024 – 0.21 m |
| BWB | full | 0.15 – 18.9 m | 0.009 – 35.9 m² | 0.06 – 1.89 m | 0.30 – 2.50 m | 0.012 – 0.62 m |
| Flying wing | **focus** | 0.49 – 6.8 m | 0.079 – 6.6 m² | 0.16 – 0.96 m | 0.25 – 1.02 m | 0.075 – 0.91 m |
| Flying wing | full | 0.22 – 16.8 m | 0.020 – 20.2 m² | 0.09 – 1.20 m | 0.15 – 1.20 m | 0.030 – 1.20 m |
| Cranked | **focus** | 0.43 – 6.5 m | 0.041 – 4.6 m² | 0.09 – 0.71 m | 0.13 – 0.75 m | 0.049 – 0.57 m |
| Cranked | full | 0.10 – 20.0 m | 0.003 – 20.0 m² | 0.03 – 1.00 m | 0.08 – 1.00 m | 0.013 – 1.00 m |
| Tapered | **focus** | 0.41 – 6.8 m | 0.037 – 4.9 m² | 0.09 – 0.72 m | 0.13 – 0.72 m | 0.052 – 0.72 m |
| Tapered | full | 0.15 – 20.0 m | 0.007 – 20.0 m² | 0.05 – 1.00 m | 0.08 – 1.00 m | 0.020 – 1.00 m |

First approach: smallest and largest over all corners of the size inputs (other inputs mid-range). Sampled wings could be a little larger (next table: BWB area up to 6.72 m², cranked up to 4.95 m²). Kept in `docs/first_approach/size_extremes.json`.

## What the focus space made (first approach)

2,000 Latin-hypercube wings per type, at real size, from `scripts/real_uav_check.py` (run before 7 Nov).

| | BWB | Flying wing | Cranked | Tapered |
| --- | --- | --- | --- | --- |
| Full span b | 0.6–7.0 m | 0.6–7.0 m | 0.5–7.0 m | 0.5–7.0 m |
| Mean chord | 0.17–1.05 m | 0.17–0.94 m | 0.10–0.72 m | 0.09–0.71 m |
| Wing area | 0.10–6.72 m² | 0.10–6.03 m² | 0.06–4.95 m² | 0.05–4.52 m² |
| Aspect ratio | 3.0–9.0 | 3.0–13.0 | 4.5–16.5 | 4.5–16.5 |
| Overall taper | 0.06–0.20 | 0.30–0.90 | 0.39–0.83 | 0.40–1.00 |
| Tip chord | 0.025–0.352 m | 0.082–0.883 m | 0.053–0.614 m | 0.056–0.698 m |

**Conclusion.** First approach: true scale showed the spread. Focus wings had a full span of about 0.4–7 m, the full space 0.1–20 m, and the smallest wings had tips of only 2–8 cm, which is why their tips flew at very low Re. The four focus spaces made wings of the same size (full span 0.5–7 m, mean chord 0.1–1 m) but of different shape: the BWB was the low-taper, low-aspect-ratio one (taper 0.06–0.2, AR 3–9); the conventional types were the slender ones (AR 4.5–16.5). Now the same shapes are built at unit mean chord, and the Re level does what the size did.

## Parameters: inputs and derived

The generator samples only the **inputs** below. Everything else is **derived** from them by fixed formulas. Four stations: root b0, breaks b1 and b2, tip b3; three straight panels between them.

### Full space

What we support

Wider ranges and every sourced airfoil. Sampled sparsely: 40 wings per type, plus both corner sets at its edges. Grey line in each cell.

### Focus space

Where real wings are

Shape ranges from real Class I–II wings and papers; suggested airfoils. Sampled densely: 100 wings per type, the reference wings and the hold-out. Bold line in each cell.

### Why two

Wide, but dense where it counts

The mesher must work on anything we claim to support; the studies and the ML spend most runs where real wings are. The focus box lies inside the full box (the YAML refuses it otherwise).

## Inputs (sampled), by wing type

<table class="wide inp" style="width:100%;">
<colgroup>
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
</colgroup>
<thead>
<tr class="header">
<th></th>
<th></th>
<th colspan="2">Tailless</th>
<th colspan="2">Conventional</th>
<th></th>
</tr>
<tr class="odd">
<th>Input</th>
<th>Symbol</th>
<th>BWB</th>
<th>Flying wing</th>
<th>Cranked</th>
<th>Tapered</th>
<th>Why this range (focus)</th>
</tr>
</thead>
<tbody>
<tr class="odd grp">
<td colspan="7">Size</td>
</tr>
<tr class="even">
<td class="what">Aspect ratio (= full span in mean chords)aspect_ratio</td>
<td>AR</td>
<td class="num"><strong>3–9</strong><br />
full 2.5–10</td>
<td class="num"><strong>3–13</strong><br />
full 2.5–14</td>
<td class="num"><strong>4.5–16.5</strong><br />
full 3–20</td>
<td class="num"><strong>4.5–16.5</strong><br />
full 3–20</td>
<td class="src">Real wings: tailless 2.9–8.6 and the ScanEagle 12.4 (NTNU; flying wing only), conventional 4.9–16.0 (<a href="#real">Real wings</a>); flying wing 4.29 (<a href="https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf">Milenković-Babić 2024</a>). checked Panknin's example has AR 10 (a model glider): above the real tailless wings (2.9–8.6), inside the flying-wing focus range (3–13).</td>
</tr>
<tr class="odd grp">
<td colspan="7">Layout</td>
</tr>
<tr class="even">
<td class="what">Outer panel, share of the semi-spanb3_ratio</td>
<td>f<sub>3</sub></td>
<td class="num"><strong>0.4–0.55</strong><br />
full 0.3–0.65</td>
<td class="num"><strong>0.2–0.5</strong><br />
full 0.15–0.6</td>
<td class="num"><strong>0.2–0.5</strong><br />
full 0.15–0.6</td>
<td class="num"><strong>0.2–0.5</strong><br />
full 0.15–0.6</td>
<td class="src">Our choice. With b1 = (1 − f<sub>3</sub>) · s and b2 = 1 − f<sub>3</sub>, the breaks sit at 15–56 % (b1) and 45–80 % (b2) of the semi-span in the focus space, and anywhere in 8–85 % in the full space. BWB: outer panel 0.50 (<a href="https://www.mdpi.com/2226-4310/9/1/36">Wang &amp; Zhou 2022</a>). checked</td>
</tr>
<tr class="odd">
<td class="what">Inner panel, share of the restsplit_ratio</td>
<td>s</td>
<td class="num"><strong>0.4–0.6</strong><br />
full 0.25–0.75</td>
<td class="num"><strong>0.3–0.7</strong><br />
full 0.2–0.8</td>
<td class="num"><strong>0.3–0.7</strong><br />
full 0.2–0.8</td>
<td class="num"><strong>0.3–0.7</strong><br />
full 0.2–0.8</td>
<td class="src">Our choice. BWB: 0.48 (<a href="https://www.mdpi.com/2226-4310/9/1/36">Wang &amp; Zhou 2022</a>). checked</td>
</tr>
<tr class="even grp">
<td colspan="7">Chords</td>
</tr>
<tr class="odd">
<td class="what">Chord at b1c2_ratio</td>
<td>r<sub>1</sub></td>
<td class="num"><strong>0.55–0.8</strong><br />
full 0.45–0.9<br />
× root</td>
<td class="num">derived</td>
<td class="num"><strong>0.95–1</strong><br />
full 0.7–1<br />
× chord inboard</td>
<td class="num">derived</td>
<td class="src">BWB 0.61 (<a href="https://www.mdpi.com/2226-4310/9/1/36">Wang &amp; Zhou 2022</a>), 0.67 (<a href="https://core.ac.uk/download/233235722.pdf">Hainline &amp; Agarwal 2017</a>). checked Cranked: constant-chord centre (0.95–1), tapered outer panels; overall taper 0.38–0.85 (Raymer about 0.4 unswept, <a href="https://computationaldesignlab.github.io/aircraft-design/wing_layout.html">via course page</a>; layout as on Hermes 450 and Heron, from photos). second-hand</td>
</tr>
<tr class="even">
<td class="what">Chord at b2c3_ratio</td>
<td>r<sub>2</sub></td>
<td class="num"><strong>0.3–0.55</strong><br />
full 0.15–0.6<br />
× root</td>
<td class="num">derived</td>
<td class="num"><strong>0.8–1</strong><br />
full 0.6–1<br />
× chord inboard</td>
<td class="num">derived</td>
<td class="src">BWB 0.39 (<a href="https://www.mdpi.com/2226-4310/9/1/36">Wang &amp; Zhou</a>), 0.42 (<a href="https://core.ac.uk/download/233235722.pdf">Hainline</a>). checked</td>
</tr>
<tr class="odd">
<td class="what">Tip chord / taperc4_ratio</td>
<td>r<sub>3</sub>, λ</td>
<td class="num"><strong>0.06–0.2</strong><br />
full 0.04–0.25<br />
× root</td>
<td class="num"><strong>0.3–0.9</strong><br />
full 0.2–1<br />
tip / root (taper λ)</td>
<td class="num"><strong>0.5–0.85</strong><br />
full 0.4–1<br />
× chord inboard</td>
<td class="num"><strong>0.4–1</strong><br />
full 0.25–1<br />
tip / root (taper λ)</td>
<td class="src">BWB 0.14 (<a href="https://www.mdpi.com/2226-4310/9/1/36">Wang &amp; Zhou</a>), 0.13 (<a href="https://core.ac.uk/download/233235722.pdf">Hainline</a>). Tapered: about 0.4 (Raymer, <a href="https://computationaldesignlab.github.io/aircraft-design/wing_layout.html">via course page</a>) to 1 (Pioneer, Shadow: <a href="https://m-selig.ae.illinois.edu/ads/aircraft.html">Lednicer</a>). Flying wing: 0.667 (<a href="https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf">Milenković-Babić</a>), 0.85 (<a href="https://www.b2streamlines.com/Panknin/Panknin.html">Panknin</a>), Aquila 0.58. checked</td>
</tr>
<tr class="even grp">
<td colspan="7">Sweep</td>
</tr>
<tr class="odd">
<td class="what">Leading-edge sweep, panel 1sweep1_deg</td>
<td>Λ<sub>1</sub></td>
<td class="num"><strong>15–40°</strong><br />
full 10–60°</td>
<td class="num"><strong>10–40°</strong><br />
full 0–60°</td>
<td class="num"><strong>−3 to 3°</strong><br />
full −15 to 35°</td>
<td class="num"><strong>−5 to 15°</strong><br />
full −15 to 35°</td>
<td class="src">BWB 15° (<a href="https://www.icas.org/ICAS_ARCHIVE/ICAS2012/PAPERS/675.PDF">Lehmkuehler 2012</a>), 30° c/4 (<a href="https://www.mdpi.com/2226-4310/9/5/275">Suewatanakul 2022</a>). Flying wing 25° (<a href="https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf">Milenković-Babić</a>), Aquila 28°, 35° (<a href="https://www.icas.org/ICAS_ARCHIVE/ICAS2008/PAPERS/335.PDF">PUL-10</a>), 40° (<a href="https://www.mdpi.com/2072-666X/11/6/553">MAV, Shams 2020</a>) agent only. Conventional: near 0° c/4 at low speed (Raymer, <a href="https://computationaldesignlab.github.io/aircraft-design/wing_layout.html">via course page</a>); −5° keeps a small forward-sweep edge case. checked second-hand</td>
</tr>
<tr class="even">
<td class="what">Leading-edge sweep, panel 2sweep2_deg</td>
<td>Λ<sub>2</sub></td>
<td class="num"><strong>15–35°</strong><br />
full 10–60°</td>
<td class="num">derived</td>
<td class="num"><strong>−5 to 10°</strong><br />
full −15 to 35°</td>
<td class="num">derived</td>
<td class="src">As panel 1, a little less outboard on the BWB (sweep falls toward the tip on the BWB papers).</td>
</tr>
<tr class="odd">
<td class="what">Leading-edge sweep, panel 3sweep3_deg</td>
<td>Λ<sub>3</sub></td>
<td class="num"><strong>5–25°</strong><br />
full 0–60°</td>
<td class="num">derived</td>
<td class="num"><strong>0–15°</strong><br />
full −15 to 35°</td>
<td class="num">derived</td>
<td class="src">As panel 2.</td>
</tr>
<tr class="even grp">
<td colspan="7">Twist</td>
</tr>
<tr class="odd">
<td class="what">Twist at the root b0twist0_deg</td>
<td>θ<sub>0</sub></td>
<td class="num"><strong>−1 to 1°</strong><br />
full −2 to 6°</td>
<td class="num"><strong>−1 to 2°</strong><br />
full −2 to 4°</td>
<td class="num"><strong>0–2°</strong><br />
full −2 to 4°</td>
<td class="num"><strong>0–2°</strong><br />
full −2 to 4°</td>
<td class="src">Washout (tip below root). Conventional: at most 5°, Raymer about 3° (<a href="https://computationaldesignlab.github.io/aircraft-design/wing_layout.html">via course page</a>) second-hand. BWB 3° (<a href="https://www.mdpi.com/2226-4310/9/5/275">Suewatanakul</a>), 7° (<a href="https://core.ac.uk/download/233235722.pdf">Hainline</a>) checked. Flying wing 3.2° (<a href="https://www.b2streamlines.com/Panknin/Panknin.html">Panknin</a>) checked.</td>
</tr>
<tr class="even">
<td class="what">Twist at b1twist1_deg</td>
<td>θ<sub>1</sub></td>
<td class="num"><strong>−3 to 0°</strong><br />
full −5 to 5°</td>
<td class="num"><strong>−2 to 1°</strong><br />
full −5 to 5°</td>
<td class="num"><strong>−1 to 2°</strong><br />
full −5 to 5°</td>
<td class="num"><strong>−1 to 2°</strong><br />
full −5 to 5°</td>
<td class="src">Between root and tip twist (see twist at the root).</td>
</tr>
<tr class="odd">
<td class="what">Twist at b2twist2_deg</td>
<td>θ<sub>2</sub></td>
<td class="num"><strong>−5 to −1°</strong><br />
full −5 to 5°</td>
<td class="num"><strong>−4 to 0°</strong><br />
full −5 to 5°</td>
<td class="num"><strong>−2 to 1°</strong><br />
full −5 to 5°</td>
<td class="num"><strong>−2 to 1°</strong><br />
full −5 to 5°</td>
<td class="src">Between root and tip twist (see twist at the root).</td>
</tr>
<tr class="even">
<td class="what">Twist at the tip b3twist3_deg</td>
<td>θ<sub>3</sub></td>
<td class="num"><strong>−8 to −2°</strong><br />
full −10 to 7°</td>
<td class="num"><strong>−6 to −1°</strong><br />
full −12 to 7°</td>
<td class="num"><strong>−3 to 0°</strong><br />
full −7 to 7°</td>
<td class="num"><strong>−3 to 0°</strong><br />
full −7 to 7°</td>
<td class="src">Total washout: conventional 0–5°, flying wing 0–8°, BWB 1–9° (see twist at the root).</td>
</tr>
<tr class="odd grp">
<td colspan="7">Dihedral</td>
</tr>
<tr class="even">
<td class="what">Dihedral, panel 1 (b0–b1)dihedral_p1_deg</td>
<td>Γ<sub>1</sub></td>
<td class="num"><strong>0–3°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="src">"Normally the dihedral is about 0 to 5 degrees or so" (<a href="https://aircraftdesign.com/?p=132">Raymer</a>). BWB 5° (<a href="https://www.mdpi.com/2226-4310/9/5/275">Suewatanakul</a>). Flying wing 4° (<a href="https://www.icas.org/ICAS_ARCHIVE/ICAS2008/PAPERS/335.PDF">PUL-10</a>), 2° (<a href="https://www.mdpi.com/2072-666X/11/6/553">MAV</a>) agent only. checked</td>
</tr>
<tr class="odd">
<td class="what">Dihedral, panel 2 (b1–b2)dihedral_p2_deg</td>
<td>Γ<sub>2</sub></td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="src">Same as panel 1.</td>
</tr>
<tr class="even">
<td class="what">Dihedral, panel 3 (b2–b3)dihedral_p3_deg</td>
<td>Γ<sub>3</sub></td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="num"><strong>0–5°</strong><br />
full −10 to 10°</td>
<td class="src">Same as panel 1.</td>
</tr>
<tr class="odd grp">
<td colspan="7">Fixed per type (not sampled)</td>
</tr>
<tr class="even">
<td class="what">Airfoils b0, b1, b2, b3</td>
<td></td>
<td><strong>mh104, mh104, mh61, mh61</strong><br />
full: mh104/s5010/mh60/naca4415 | mh104/s5010/mh60/naca4415 | mh61/s5010/mh45/naca4412 | mh61/s5010/mh45/naca4412</td>
<td><strong>mh60, mh60, mh45, mh45</strong><br />
full: mh60/mh45/mh104/s5010/naca4415 | mh60/mh45/mh104/s5010/naca4415 | mh45/mh60/mh61/s5010/naca4412 | mh45/mh60/mh61/s5010/naca4412</td>
<td><strong>naca4415, naca4415, naca4412, naca4412</strong><br />
full: naca4415/naca4412/mh104/mh60/s5010 | naca4415/naca4412/mh104/mh60/s5010 | naca4412/naca4415/mh61/mh45/s5010 | naca4412/naca4415/mh61/mh45/s5010</td>
<td><strong>naca4415, naca4415, naca4412, naca4412</strong><br />
full: naca4415/naca4412/mh104/mh60/s5010 | naca4415/naca4412/mh104/mh60/s5010 | naca4412/naca4415/mh61/mh45/s5010 | naca4412/naca4415/mh61/mh45/s5010</td>
<td class="src">BWB: MH 104 body, MH 61 wing (<a href="https://www.mdpi.com/2226-4310/9/5/275">Suewatanakul 2022</a>). Conventional: NACA 4415 on Pioneer and Shadow 200 (<a href="https://m-selig.ae.illinois.edu/ads/aircraft.html">Lednicer</a>). Flying wing: Hepperle tailless sections (<a href="https://www.mh-aerotools.de/airfoils/mh60koo.htm">MH 60</a>: Re ≥ 1.5 × 10⁵, root; <a href="https://www.mh-aerotools.de/airfoils/mh45koo.htm">MH 45</a>: lower Re, tip); MH 60 on <a href="https://www.mas.bg.ac.rs/_media/istrazivanje/fme/vol52/4/4_m._milenkovic_babic_et_al.pdf">Milenković-Babić</a>. checked</td>
</tr>
<tr class="odd">
<td class="what">Sampled variables</td>
<td></td>
<td class="num">16</td>
<td class="num">12</td>
<td class="num">16</td>
<td class="num">12</td>
<td></td>
</tr>
</tbody>
</table>

"derived": that type computes the value (see below). Sweep positive aft; twist positive nose up; dihedral positive tip up. Since 7 Nov every wing is built at unit mean chord, so the root chord is not sampled: 16 / 12 / 16 / 12 inputs (BWB / flying wing / cranked / tapered).

## Derived (computed, never sampled)

| Quantity | Formula | Types |
| --- | --- | --- |
| Panel shares of the semi-span | f<sub>1</sub> = (1 − f<sub>3</sub>) · s, f<sub>2</sub> = 1 − f<sub>1</sub> − f<sub>3</sub> | all |
| Chord ratios r<sub>i</sub> = c<sub>i</sub> / c<sub>r</sub> | BWB: (1, r<sub>1</sub>, r<sub>2</sub>, r<sub>3</sub>). Cranked: (1, r<sub>1</sub>, r<sub>1</sub>r<sub>2</sub>, r<sub>1</sub>r<sub>2</sub>r<sub>3</sub>). Tapered, flying wing: r(y) = 1 + (λ − 1) · y / S, so r<sub>1</sub>, r<sub>2</sub> follow | all |
| Mean chord ratio | K = Σ f<sub>i</sub> · (mean true chord of panel i) / c<sub>r</sub>: (r<sub>i−1</sub> + r<sub>i</sub>) / 2 when the twist does not change along the panel; with a twist change the chord turns and is a little shorter mid-panel (exact, 32-point Gauss) | all |
| Semi-span | S = AR / 2 (in mean chords; every wing at unit mean chord since 7 Nov 2026). First approach: S = AR · c<sub>r</sub> · K / 2, with c<sub>r</sub> sampled in metres | all |
| Root chord | c<sub>r</sub> = 1 / K (in mean chords; no longer sampled) | all |
| Full span, area, mean chord | b = 2S = AR, A = b · c̄ = AR, c̄ = A / b = c<sub>r</sub> K = 1 (unit mean chord: every length in mean chords) | all |
| Mean aerodynamic chord | MAC = ∫c² dy / ∫c dy (exact for straight panels) | all |
| Station positions along the semi-span | y<sub>0</sub> = 0, y<sub>i</sub> = y<sub>i−1</sub> + f<sub>i</sub> S | all |
| Sweeps 2 and 3 | Λ<sub>2</sub> = Λ<sub>3</sub> = Λ<sub>1</sub> (one straight leading edge) | tapered, flying wing |
| Leading-edge positions | x<sub>i</sub> = x<sub>i−1</sub> + tan Λ<sub>i</sub> · f<sub>i</sub> S | all |
| Station heights | z<sub>i</sub> = z<sub>i−1</sub> + tan Γ<sub>i</sub> · f<sub>i</sub> S (sections vertical, root in y = 0) | all |
| Overall taper | λ = c<sub>tip</sub> / c<sub>r</sub> | all |
| Trailing-edge thickness | t = 0.2 % · c (the local chord) on every wing; opened over the last 10 % of chord. First approach: t = max(floor, 0.2 % · c), floor 0.5 mm (Class I) or 1.0 mm (Class II) | all |
| Real size of a published wing | lengths × `real_mean_chord_m` = metres (the copy is built at unit mean chord) | published |

Checked on every built wing: chords (0.1 %), sweeps (0.1°), twists and panel dihedrals (0.2°) and the aspect ratio (0.1 %), measured on the loft against the inputs.

**What changes (7 Nov 2026).** The root chord left the inputs (18 → 17 names; 16 / 12 / 16 / 12 sampled, 17 / 13 / 17 / 13 before). The semi-span is AR / 2 and the root chord 1 / K, in mean chords. The trailing edge is 0.2 % of the local chord on every wing. The airfoil rule changed too (decision 64): see Nose study.

**Conclusion.** 17 numbers and 4 airfoil names describe every wing, at unit mean chord. Everything else is computed from them and checked on the built surface.

## Nose study: the built nose against the airfoil file (decision 64)

The question: is the nose of the built section the nose of the airfoil, at the size of one mesh cell? On 2 Nov the Stage 2 mesher found that the built noses of cambered sections were not round. On 6 Nov a second reading said this was overstated. On 7 Nov the nose was measured again, with one method for every curve, and fixed in the code.

### Method

One curvature, along the arc

Every curve is a smooth spline. Its curvature comes from its own derivatives along its own arc length: no frame, no formula. Curves: the raw file (a cubic spline; a quintic as a check), the built section as the loft holds it (old and new rule), and the NACA 4415 formula.

### Mesh number

T(h): turning per cell

The largest turning a cell of arc length h gets near the nose (within 3 % c of arc), for h = 0.04, 0.10, 0.18, 0.30 and 0.50 % c. Criterion, written before computing: built within 5 % of raw at every h, on all ten suggested airfoils.

### Result

Old rule fails all ten; new rule passes all ten

Old: NACA 4415 +449 % at 0.04 % c, +121 % at 0.18 % c. New: worst −3.9 % (MH 60 at 0.04 % c). Database: 95.6 % pass (old rule 21.0 %).

<figure class="fig card">
<p><em>[Figure: Nose curvature study: the built nose against the raw file, old and new rule]</em></p>
<figcaption>How to read. Top row: curvature (1/c) along the arc from the old leading-edge point (− lower side, + upper side) on four airfoils: the raw file (black), the formula (dotted, NACA 4415 only), the old rule (orange), the new rule (blue dashed). Middle row: the turning per cell T, built against raw, at every h, for the old rule (left) and the new rule (centre; dashed: with only 101 points per side), and the Stage 2 nose solve on a NACA 4415 station (right). Bottom row: the whole database (left: the share of files at or below a miss; the dashed line is 5 %) and the two side effects: how far the leading edge moves (centre) and how much the chord line turns (right).</figcaption>
</figure>

**What it shows.**

- **The old nose had a spike on one side and a flat spot on the other.** On NACA 4415 the upper side curved at 567/c at the old leading edge (radius 0.0018 c), and the lower side was flat there (6.4/c). The raw file and the formula curve at about 40–42/c. Further down, the lower side got its angle back in a false bump (77.5/c at −0.755 % c; raw 41.5/c). So a 0.18 % c nose cell turned 9.47°, where the true shape turns 4.31°.
- **Why.** The old rule put the leading edge at the farthest raw point. The apex of the curve lies between raw points, 0.003–0.210 % c of arc away on the ten, and there the tangent is already turned by 0.05–19.4°. The √x resampling then forced the tangent square to the chord, so that angle was packed into the first gap on one side and taken from the other. PCHIP resampling through coarse files added a second error.
- **The 6 Nov note was wrong.** It read the raw points with a one-sided formula and saw the same split as on the built section. But the built section passes through the raw points, so no formula on those points can see what happens between them. Measured along the arc, the built split was real, and larger at the leading edge than first read (NACA 4415 radius 0.0018 / 0.155 c, not 0.008 / 0.074 c).
- **The new rule follows the file.** All ten are within 5 % at every h (worst −3.9 %). With only 101 points per side the tight MH noses stay 6.3–9.4 % low at 0.04 % c, so the new rule holds 201 points per side.
- **Stage 2's flat nose line stays.** On a NACA 4415 station the largest turning per node stays flat below a nose spacing of 0.2 % c with both rules (6.6–7.4° old, 6.0–6.8° new). The worst node sits 1.8–2.4 % c down the lower side, where the growth law (1.2) sets the cells, not the nose spacing. The 10° target now holds up to a nose spacing of 0.377 % c (0.327 % c with the old rule).
- **The whole database** (2,143 files both rules build and measure): 95.6 % pass the 5 % test at 0.04 and 0.18 % c (old rule 21.0 %); the median worst miss is 0.52 % (old 15.8 %). A gate refuses the 14 files whose nose folds back (the old rule built 45 such hooks). Crossing surfaces: 4 and 4 (they are in the files). Every section the configs name passes (worst 3.89 %, MH 60).
- **Side effects.** The leading edge moves along the nose by a median 0.046 % c (90 %: 0.28 % c; max 1.69 % c, on coarse files of 33–41 points). The chord line turns by a median 0.027° (max 0.96°; over 0.1° on 428 files). On the named sections the largest is NACA 4415: 0.209 % c and 0.12°. Every geometry hash changed; sections have 401 points instead of 201.

| Airfoil | Points | R<sub>min</sub> raw | R<sub>min</sub> old | R<sub>min</sub> new | T old vs raw, % (0.04 / 0.18 % c) | T new vs raw, % (0.04 / 0.18 % c) | Jump old / new | LE move % c / chord turn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NACA 4415 | 199 | 0.0241 | 0.0018 | 0.0241 | +449.2 / +121.0 fail | +0.1 / 0.0 pass | 88 / 1.011 | 0.209 / +0.120° |
| E387 | 61 | 0.0047 | 0.0021 | 0.0048 | +89.2 / +34.0 fail | −2.0 / +0.1 pass | 33 / 1.004 | 0.210 / +0.119° |
| SD7032 | 61 | 0.0048 | 0.0023 | 0.0049 | +107.6 / +79.2 fail | −0.6 / 0.0 pass | 15 / 1.003 | 0.197 / -0.111° |
| MH 104 | 67 | 0.0052 | 0.0046 | 0.0054 | +15.1 / +12.5 fail | −1.5 / +0.3 pass | 5.26 / 1.078 | 0.042 / -0.024° |
| MH 61 | 68 | 0.0021 | 0.0007 | 0.0022 | +23.4 / −6.1 fail | −1.3 / −0.1 pass | 16 / 1.018 | 0.044 / +0.025° |
| MH 45 | 67 | 0.0030 | 0.0027 | 0.0031 | +14.8 / +12.1 fail | −1.9 / +0.2 pass | 6.00 / 1.088 | 0.037 / -0.021° |
| MH 60 | 68 | 0.0028 | 0.0032 | 0.0031 | −8.2 / +0.7 fail | −3.9 / +0.4 pass | 1.17 / 1.115 | 0.003 / -0.002° |
| S5010 | 61 | 0.0049 | 0.0033 | 0.0051 | +51.7 / +44.4 fail | −1.8 / +0.2 pass | 4.39 / 1.020 | 0.126 / -0.072° |
| LA2573A | 101 | 0.0252 | 0.0219 | 0.0254 | +14.4 / +11.7 fail | −0.8 / −0.3 pass | 1.054 / 1.001 | 0.003 / +0.002° |
| NACA 25118 | 401 | 0.0334 | 0.0267 | 0.0334 | +22.6 / +15.0 fail | 0.0 / 0.0 pass | 1.60 / 1.001 | 0.026 / -0.015° |

R<sub>min</sub>: the smallest radius within 3 % c of the leading-edge point, in chords. T: the turning per cell, built against raw. Jump: the curvature of the two built branches at the leading-edge point, larger over smaller (1 = round). LE move and chord turn: what the new rule changes. Is the raw file a fair reference? For NACA 4415 yes: the file sits on the formula within 4.2 × 10⁻⁶ c, and its turning is within 0.7 % of the formula's. The 61-point files (E387, SD7032, S5010) only partly: a quintic spline through the same points gives 13.6–14.9 % less turning at 0.04 % c. Details: `decisions/nose_curvature.md`, `data/studies/nose_curvature.json`, `scripts/nose_curvature.py`.

**Conclusion.** Decision 64 is settled with a fix. The old rule made the built nose turn up to 5.5 × more per small cell than the airfoil (NACA 4415 at 0.04 % c), and the 5 % test failed on all ten suggested airfoils. The new rule (leading edge at the apex of one cubic spline, both sides from that spline, 201 points per side) passes on all ten and on 95.6 % of the database; a gate refuses the 14 files whose nose folds back. The cost: every hash changed, the leading edge moves (median 0.046 % c) and the chord line turns (median 0.027°). Stage 2's flat nose line is not a geometry error: it comes from the growth law.

## Reynolds and Mach numbers

### Study levels (Stage 0)

1 × 10⁵ · 3 × 10⁵ · 1 × 10⁶ · 4 × 10⁶

On the mean chord (area / full span, not the MAC). Since 7 Nov the Re is an input of each solve: every shape runs at all four. Every mesh study runs at these four. Changed on 8 Nov (you): 1 × 10⁶ and 4 × 10⁶ replace 1.5 × 10⁶ and 3 × 10⁶, for the Greek tactical programmes and check C4 (below). 1 × 10⁵ added 30 Oct 2026 for mini Class I wings; it sits 18 % below the slowest real UAV, kept as a margin (you, 7 Nov).

### Real wings fly at

1.22 × 10⁵ – 3.10 × 10⁶

On the mean chord (area / full span), cruise at 3,048 m to top speed at sea level, for the 34 real wings with a published area. Inside the four levels.

### Mach

0.1 (CFD)

Under similarity the CFD runs at Mach 0.1, with a Prandtl–Glauert correction on CL and CM (check C2: 0.05 / 0.1 / 0.2). First approach (the flow data on this page): Mach 0.03–0.20 from the real wings' speeds, well below 0.3, so the air is nearly incompressible. Since 4 Nov 2026 the Mach scope extends toward 0.5, with no supersonic flow. Proposal, pending: core data at Mach ≤ 0.2 now, 0.3–0.5 later with a fast-UAV family (the section tables stop at Mach 0.2).

**What changes (7 Nov 2026).** The Re on the mean chord is now an input of each solve: every shape runs at all four levels. Before, the Re followed from the real size and the real speed of each wing (kept below as the first approach). The real-wing Re (1.22 × 10⁵ – 3.10 × 10⁶) did not change; it is on area / full span, the mean chord the levels use.

## By type and space (unit mean chord)

| Type | Space | Re on the mean chord | Smallest tip chord → tip Re at 1 × 10⁵ | Largest root chord → root Re at 4 × 10⁶ |
| --- | --- | --- | --- | --- |
| BWB | **focus** | 1 × 10⁵ – 4 × 10⁶ | 0.099 → 9.9 × 10³ | 2.831 → 1.1 × 10⁷ |
| BWB | full | 1 × 10⁵ – 4 × 10⁶ | 0.055 → 5.5 × 10³ | 4.904 → 2.0 × 10⁷ |
| Flying wing | **focus** | 1 × 10⁵ – 4 × 10⁶ | 0.462 → 4.6 × 10⁴ | 1.539 → 6.2 × 10⁶ |
| Flying wing | full | 1 × 10⁵ – 4 × 10⁶ | 0.333 → 3.3 × 10⁴ | 1.667 → 6.7 × 10⁶ |
| Cranked | **focus** | 1 × 10⁵ – 4 × 10⁶ | 0.439 → 4.4 × 10⁴ | 1.369 → 5.5 × 10⁶ |
| Cranked | full | 1 × 10⁵ – 4 × 10⁶ | 0.234 → 2.3 × 10⁴ | 2.361 → 9.4 × 10⁶ |
| Tapered | **focus** | 1 × 10⁵ – 4 × 10⁶ | 0.571 → 5.7 × 10⁴ | 1.429 → 5.7 × 10⁶ |
| Tapered | full | 1 × 10⁵ – 4 × 10⁶ | 0.400 → 4.0 × 10⁴ | 1.600 → 6.4 × 10⁶ |

Local Re = Re on the mean chord × local chord (in mean chords). Chords from all corners of the planform inputs (others mid-range). One wing at one level covers a much narrower band than its row.

**Conclusion.** The four study Re levels (10⁵ – 4 × 10⁶) cover the real wings (1.22 × 10⁵ – 3.10 × 10⁶ on the mean chord) and every cruise point of the Greek tactical BWBs (1.4–3.7 × 10⁶). Inside one wing, Re goes further: at the lowest level down to about 9.9 × 10³ at the smallest focus BWB tip (0.099 mean chords), at the top level up to 1.1 × 10⁷ at the largest focus BWB root (2.83 mean chords). The other types stay within about 4.4 × 10⁴ – 6.2 × 10⁶.

## First approach: Re and Mach at real size and speed

| Type | Space | Speed | Mach | Re, mean chord | Re, smallest tip | Re, largest root |
| --- | --- | --- | --- | --- | --- | --- |
| BWB | **focus** | 11.1–44.4 m/s | 0.034–0.13 | 8.4 × 10⁴ – 3.5 × 10⁶ | 1.4 × 10⁴ | 5.5 × 10⁶ |
| BWB | full | 11.1–44.4 m/s | 0.034–0.13 | 3.6 × 10⁴ – 5.8 × 10⁶ | 7.1 × 10³ | 7.6 × 10⁶ |
| Flying wing | **focus** | 11.1–44.4 m/s | 0.034–0.13 | 9.6 × 10⁴ – 3.0 × 10⁶ | 4.5 × 10⁴ | 3.2 × 10⁶ |
| Flying wing | full | 11.1–44.4 m/s | 0.034–0.13 | 5.3 × 10⁴ – 3.6 × 10⁶ | 1.8 × 10⁴ | 3.6 × 10⁶ |
| Cranked | **focus** | 11.1–66.9 m/s | 0.034–0.20 | 5.6 × 10⁴ – 3.4 × 10⁶ | 2.9 × 10⁴ | 3.4 × 10⁶ |
| Cranked | full | 11.1–66.9 m/s | 0.034–0.20 | 2.0 × 10⁴ – 4.6 × 10⁶ | 8.0 × 10³ | 4.6 × 10⁶ |
| Tapered | **focus** | 11.1–66.9 m/s | 0.034–0.20 | 5.4 × 10⁴ – 3.4 × 10⁶ | 3.1 × 10⁴ | 3.4 × 10⁶ |
| Tapered | full | 11.1–66.9 m/s | 0.034–0.20 | 3.0 × 10⁴ – 4.6 × 10⁶ | 1.2 × 10⁴ | 4.6 × 10⁶ |

First approach (before 7 Nov; the flow data on this page). Lowest: smallest chord at the family's lowest cruise speed at 3,048 m. Highest: largest chord at its highest top speed at sea level. Air from Stage 0 (ISA, Sutherland); a = 328.6 m/s at 3,048 m, 340.3 m/s at sea level.

**Conclusion.** First approach: the real-size wings at real speeds reached 5.4 × 10⁴ – 3.5 × 10⁶ on the mean chord in the focus space, down to about 1.4 × 10⁴ at the smallest tips and up to 5.5 × 10⁶ at the largest BWB roots. The similarity form gives a wider local reach at the two end levels, because every shape now runs at both.

## What each Re band means

| Re (on the local chord) | Flow | Who is there | RANS (SA, fully turbulent) |
| --- | --- | --- | --- |
| below 10⁵ | Laminar; long bubbles close to bursting (bubbles appear from about 6 × 10⁴); lower down the flow can separate without reattaching; strong hysteresis | Tips and outer panels at the lowest level (10⁵ on the mean chord) | poor no transition model, results only indicative |
| 10⁵ – 5 × 10⁵ | Laminar separation bubbles, transition on the bubble | The two lowest levels (most Class I wings fly there); outer panels of BWBs | drag too high bubble missed; SA drag error −2 to +77 % (2-D, 2°; near zero only at 10⁵) |
| 5 × 10⁵ – 3 × 10⁶ | Laminar to 30–60 % of chord, then turbulent; short bubbles still form up to about 2 × 10⁶ | The level 1 × 10⁶ (Class II wings in loiter); BWB centre bodies | drag too high the laminar run is missed: the largest SA drag error, +74 to +128 % (2-D, 2°) |
| above 3 × 10⁶ | Shorter laminar run in quiet air | The top level 4 × 10⁶ (Class II at top speed; the Greek tactical BWBs); large roots (up to 1.1 × 10⁷) | drag too high still +74 to +120 % at 3 × 10⁶ in quiet air (2-D); closer in gusty air or on a rough surface |

Bands are approximate (Carmichael 1981; Lissaman 1983; Mueller & DeLaurier 2003). "SA drag error" = profile drag of fully turbulent CFD ÷ profile drag of the real flow − 1, from XFOIL (see Flow phenomena and Flow dataset). Corrected 1 Nov 2026: this table had called SA "good" above 5 × 10⁵; the 2-D runs show the opposite in quiet air. The 2-D numbers were rerun on 7 Nov on the sections of the new nose rule (they moved by at most 4 points).

**Conclusion.** No Re band in our range is safe for fully turbulent SA drag in quiet air: from 10⁵ up it gives too much drag (it misses the laminar run); below 10⁵ it misses the laminar separation. For drag, the model choice matters more than the mesh.

## Greek tactical UAVs and the Re levels (8 Nov 2026)

You asked (8 Nov) that the range include the Greek programmes LOTUS, Archytas and ACTUS. ACTUS is not an aircraft: it is an EDF 2023 project (Intracom Defense, Dec 2024 – 2028) that develops and certifies LOTUS and the Safran Patroller. No wing area is published for any Greek aircraft, so the mean chord comes from an assumed aspect ratio of 8: the AUTh RX-3, which LOTUS is based on, has AR 8 and a 33° sweep (Kapsalis et al. 2025), inside our BWB focus (AR 3–9, sweep 15–40°). Every number with its source, the conflicts between sources and the assumptions: `configs/greek_uavs.yaml`; the numbers: `scripts/greek_uavs.py` (`docs/greek_uavs.json`).

<figure class="fig card">
<p><em>[Figure: Greek tactical UAVs against the Re levels: Re on the mean chord from cruise to top speed]</em></p>
<figcaption>How to read. One bar per aircraft: from cruise at 3,048 m (dot) to top speed at sea level (diamond), on the mean chord. The lighter end is a range of top speeds in the sources. Dashed: the four Re levels since 8 Nov; dotted: 1.5 × 10⁶ and 3 × 10⁶, the levels before. The grey bar on top: the 31 real Class I–II wings with a published area. Shaded: above the top level, where the data are extrapolated.</figcaption>
</figure>

| Aircraft | Full span | Cruise / top speed | Re (mean chord) | Mach at top speed | What is not published |
| --- | --- | --- | --- | --- | --- |
| Archytas (HAI; AUTh aerodynamics; BWB, VTOL) | 6.4 m | 120 / 158 km/h | 1.4 → 2.4 × 10⁶ | 0.13 | wing area; MTOW (180–200 kg on one site) |
| RX-3 (AUTh/DELAER; LOTUS is based on it) | 7.2 m | 180 / 241 km/h | 2.4 → 4.1 × 10⁶ | 0.20 | wing area (a paper airframe like it: 4.9 m², 6.26 m) |
| LOTUS sub-scale demonstrator | about 7 m | the RX-3's | 2.3 → 4.0 × 10⁶ | 0.20 | speeds, area; one source says 6 m and 230 kg |
| LOTUS (EDIDP, then ACTUS; BWB) | 11 m | 180 (assumed) / about 220–240 km/h (planned) | 3.7 → 5.8–6.3 × 10⁶ | 0.18–0.20 | cruise speed, area; weight 500–700 kg |
| Safran Patroller (ACTUS) | 18 m | 92 / 265–314 km/h | 1.3 → 4.9–5.8 × 10⁶ | 0.22–0.26 | area (the Stemme S15 wing used: 17.4 m², AR 18.6) |

**Conclusion.** With the levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶ and 4 × 10⁶, every cruise point of the Greek tactical UAVs is inside (LOTUS 11 m: 2.8 × 10⁶ at 20,000 ft, 3.7 × 10⁶ at 10,000 ft), and so are the 6–7 m versions at top speed (the RX-3 3 % above). LOTUS 11 m flying low and fast (4.7–6.3 × 10⁶) and the Patroller at top speed are extrapolations; they stay so: no 5th level (you, 8 Nov). Every Greek number rests on an assumption (AR 8; AR 6 would raise each Re by a third), and the sources disagree on several values. Mach stays at or below 0.26: the Prandtl–Glauert correction from Mach 0.1 is +1.1 to +2.9 %. The shapes fit the generator: the RX-3 family (AR 8, sweep 33°) sits inside the BWB focus; the Patroller (AR 18.6) only in the full space. LOTUS 11 m (500–700 kg) and the Patroller (1.2 t) are NATO Class III by weight.

## Check C4 on 2-D data: can the data be read between the levels?

Each of the 13 section tables (free transition at N_crit 9, and tripped), at 0, 2, 4 and 6°, Mach 0.1: the drag at every grid Re that is not a level is read by a straight line in log Re and log cd between the two nearest levels (above the top: from the two highest), and compared with the table (`scripts/re_ladder_check.py`, `docs/re_ladder_check.json`).

<figure class="fig card">
<p><em>[Figure: Check C4 on 2-D data: drag read between the Re levels, old against new levels]</em></p>
<figcaption>How to read. Each point: the 90th percentile of the drag error over the 13 sections and 4 angles at that Re. Grey: the levels until 8 Nov; blue: since 8 Nov. No point where the Re is itself a level. Left: with transition; right: fully turbulent (note the different scale).</figcaption>
</figure>

**Conclusion.** With transition, the new levels read drag better where it changes fastest: at 6 × 10⁵ the error falls from 16.9 % to 8.8 % (90th percentile), and above the top (6 × 10⁶) from 12.0 % to 7.8 %. The price: between 1 × 10⁶ and 4 × 10⁶ it rises from 2.5–3.7 % to 6.8–7.0 %. Over 1 × 10⁵ – 4 × 10⁶ the median is 3.0 % (3.3 % before) and the worst 20 % (26 %). Fully turbulent drag reads well with either (median 0.7 %, at most 1.3 % at the 90th percentile). This is a 2-D proxy: check C4 with the solver is still to run, and wing drag also carries induced drag, which does not depend on Re.

## The scope by NATO class (Mitridis et al. 2023)

A peer-reviewed survey of 202 fixed-wing UAVs (AUTh, the group that did the aerodynamics of Archytas and the RX-3), sorted by NATO class. It gives the class limits, full spans and speeds per class. It gives no aspect ratio or wing area (not enough solid data), so it cannot give a Re by itself; with our aspect ratios it supports the range.

| NATO class (by take-off weight) | Altitude | Full span | Median cruise / top speed | Our scope |
| --- | --- | --- | --- | --- |
| Class I micro and mini (below 15 kg) | below 3,000 ft | about 0.7–3.5 m | about 60 / 95 km/h | yes (the 1 × 10⁵ and 3 × 10⁵ levels) |
| Class I small (15–150 kg) | below 5,000 ft | about 1–8 m | about 120 / 160 km/h | yes |
| Class II tactical (150–600 kg) | below 18,000 ft | about 2–16 m | about 180 / 190 km/h | yes (Archytas, RX-3, LOTUS demonstrator) |
| Class III (over 600 kg) | up to 65,000 ft | — | — | only LOTUS 11 m and the Patroller (in cruise) |

Speeds and full spans read from the paper's box and dot plots (2005–2015; about ± 10 %); class limits from its Table 2. Within a class, full span against weight and cruise speed against weight fit poorly (R² \< 0.2, Tables 5 and 9).

**Conclusion.** The paper fits our approach: within one class the spread is wide and the trend lines are weak, so a range sampled across the spread, not a trend line, is the right description of the design space. Its class limits make our scope precise: Class I and Class II up to 600 kg and 18,000 ft, with the Greek tactical BWBs inside and LOTUS 11 m at the Class III edge.

## Flow phenomena you will meet

What the flow does on these wings, at these Re and angles, and whether fully turbulent CFD (ADflow, steady RANS, Spalart–Allmaras) can see it. Since 4 Nov 2026 transition must be captured too, with ADflow and SU2: our ADflow build has SA only, so transition comes from SU2 (SST + LM γ-Reθ).

**What changes (7 Nov 2026).** The Re figures now use the Re levels (an input) instead of real sizes and speeds. The 2-D XFOIL runs below were redone on 7 Nov on the sections of the new nose rule (the numbers moved by at most 4 points). The trailing edge is 0.2 % c on every wing; the CFD runs at Mach 0.1.

<figure class="fig">
<p><em>[Diagram: Reynolds number map at unit mean chord: the four study levels on the mean chord, the local Re of each type from its smallest tip at the lowest level to its largest root at the top level, and the real wings, against the low-Re regime below 5 times 10 to the 5]</em></p>
<figcaption>Where the wings fly, at unit mean chord. Thick bars: the four levels on the mean chord, the same for every type. Thin bars: the local Re along the semi-span, from the smallest tip at the lowest level to the largest root at the top level (focus space). Top lines: the real wings with a published area and speeds, each at its own Re on the mean chord (cruise at 3,048 m to top speed at sea level). The tips go furthest into the low-Re regime, the BWB down to about 9.9 × 10³ (low-Re limit: below 5 × 10⁵, Univ. Waterloo Fluid Mechanics Research Lab; Carmichael 1981).</figcaption>
</figure>

**Conclusion.** At the two lowest levels every type flies in the low-Re regime (below 5 × 10⁵), and the tips go deepest: the BWB down to about 9.9 × 10³ at 10⁵. Low-Re effects are the rule for these wings, not the exception.

<figure class="fig card">
<p><em>[Figure: Local chord Reynolds number along the semi-span of the smallest and largest wing of each type]</em></p>
<figcaption>At unit mean chord: local Re = Re on the mean chord × local chord (in mean chords). Top: each type's focus wing with the smallest tip chord, at the lowest level (1 × 10⁵). Bottom: its focus wing with the largest root chord, at the top level (4 × 10⁶; 3 × 10⁶ until 8 Nov). At the lowest level the outer panels sit below 10⁵ (red) and the BWB carries two regimes at once; at the top level the roots pass 4 × 10⁶ (dark blue).</figcaption>
</figure>

**Conclusion.** One wing can hold two regimes: at the lowest level the focus BWB with the smallest tip runs at 1.6 × 10⁵ at the root and 9.9 × 10³ at the tip, 17 times less (first approach, real size: 2.4 × 10⁵ and 1.4 × 10⁴, 17 times). One flow model may not fit the whole half wing. One first-cell height does (it changes only about 20 % along the semi-span, because Re and chord change together), but the root boundary layer is up to about 10 × thicker and needs more wall layers.

## What fully turbulent CFD would miss: estimated in 2-D with XFOIL (no wing CFD run yet)

No CFD has been run on a wing yet (the 4 Nov SU2 smoke test on one ring mesh did not converge and gives no result). Four airfoils, each on its own (2-D, not a cut of a wing; rerun on 7 Nov 2026 on the sections of the new nose rule), were run in XFOIL (Drela 1989: a panel method coupled to a boundary-layer model, not RANS): MH 104, the BWB centre body (root); MH 61, the BWB outer wing (tip); MH 60, the flying wing; NACA 4415, the conventional wings (root). Each was run twice at the four study Re:

- **Real flow (free transition).** XFOIL lets the boundary layer start laminar at the nose and predicts where it turns turbulent by itself (e<sup>N</sup> method, N<sub>crit</sub> 9 = quiet air), including laminar separation bubbles.
- **Fully turbulent (tripped).** Transition forced at 1 % chord on both surfaces: turbulent from the nose, which is what fully turbulent CFD (ADflow SA) assumes.

The gap between the two is the error that comes from ignoring transition. It is a 2-D proxy: no sweep, no crossflow, no 3-D relief.

<figure class="fig">
<p><em>[Diagram: One airfoil section at an angle of attack: the upper surface is the top side, the suction side with lower pressure; the lower surface is the bottom side, the pressure side; flow comes from the left onto the leading edge (nose) and leaves at the trailing edge]</em></p>
<figcaption>Words used below. An airfoil has two surfaces: the upper (top, suction) side, where the boundary layer first stays laminar and then turns turbulent, and the lower (bottom, pressure) side. This holds at positive angles; at negative angles (now in scope, down to −5°) the two sides swap roles. Each XFOIL run is one such 2-D section on its own, not a cut through a 3-D wing.</figcaption>
</figure>

**Conclusion.** At the positive angles studied here, the laminar run, bubbles and transition that matter happen mostly on the upper surface, so the next figures show that surface.

<figure class="fig card">
<p><em>[Figure: XFOIL upper-surface skin friction, free transition vs tripped, at four Re levels (the study levels until 8 Nov)]</em></p>
<figcaption>2-D airfoil sections in XFOIL, exactly 4°, top (upper) surface only: skin friction from nose (0) to trailing edge (1). Solid: free transition (real quiet air); dashed: tripped at 1 % chord (fully turbulent CFD). At 10⁵ and 3 × 10⁵ the free flow runs laminar to mid-chord, separates (shaded, Cf &lt; 0) and turns turbulent on the bubble. At 1.5–3 × 10⁶ (the two upper study levels until 8 Nov) transition moves forward to 30–45 % chord with no bubble. Tripped: turbulent from the nose, with much higher friction everywhere.</figcaption>
</figure>

**Conclusion.** In quiet real air the flow stays laminar (low friction) over a large part of the chord; fully turbulent CFD puts high friction everywhere. That difference is the extra drag fully turbulent CFD adds.

<figure class="fig card">
<p><em>[Figure: XFOIL profile-drag increase when tripped, and transition position, against Re]</em></p>
<figcaption>Four airfoils, each run alone in 2-D XFOIL (not a cut of a 3-D wing), at exactly 2° and Mach 0. <strong>Light bar</strong>: free transition (e<sup>N</sup>, N<sub>crit</sub> 9): the flow stays laminar from the nose and turns turbulent by itself, as in quiet real air. <strong>Dark bar</strong>: tripped at 1 % chord: turbulent from the nose, which is what fully turbulent CFD (SA) assumes. The % is tripped / free − 1: how much too high fully turbulent CFD puts the profile drag. At Re 10⁵ the two are close because the free flow separates in a long bubble, which is draggy too. At 2°, by Re: 1.0 × 10⁵: −2 to +21 %; 3.0 × 10⁵: +39 to +77 %; 1.5 × 10⁶: +84 to +128 %; 3.0 × 10⁶: +74 to +120 %. Every section has a converged answer at 2° at every Re (on the sections before the nose fix, MH 60 at 1.5 × 10⁶ had none). The section tables cover every angle from −10° to 14° and every Re; their maps are in the Flow dataset section (−6° to 14° shown).</figcaption>
</figure>

**Conclusion.** From Re 3 × 10⁵ up, fully turbulent CFD puts the profile drag +39 to +128 % too high (2-D, 2°; median +81 %). At 10⁵ the gap is small (−2 to +21 %), but only because the real flow has a draggy bubble too: SA is close there by luck, not because it models the flow. On the old sections (before the nose fix) the same runs gave +40 to +128 % and −1 to +21 %; MH 60 at 1.5 × 10⁶ had no converged free answer at 2° then and has one now (+112 %).

<figure class="fig card">
<p><em>[Figure: Where the real flow turns turbulent, per section and Re]</em></p>
<figcaption>2-D airfoil sections in XFOIL, exactly 2°, free transition, top (upper) surface only: where the flow turns turbulent, from nose (left) to trailing edge (right). Light: laminar (low friction); dark: turbulent. Higher Re moves the change toward the nose; the BWB centre-body section (MH 104) turns turbulent earliest.</figcaption>
</figure>

**Conclusion.** Where the flow turns turbulent depends on Re and on the airfoil, so it has to be predicted (a transition model), not assumed (fully turbulent).

| Phenomenon | Where in our ranges | What it does | Does our CFD capture it? | Source |
| --- | --- | --- | --- | --- |
| Laminar flow, transition and laminar separation bubbles | Every type. Re on the mean chord: the four levels 1 × 10⁵ – 4 × 10⁶ (since 8 Nov), an input of each solve since 7 Nov (real Class I–II wings fly at 1.22 × 10⁵ – 3.10 × 10⁶). Our low-Re sections (MH 45, MH 60, MH 61, MH 104) are designed for long laminar runs. First approach (real size and speed): 5.4 × 10⁴ – 3.5 × 10⁶ on the mean chord (focus). | Drag and lift depend on where the boundary layer turns turbulent. A bubble adds drag; at high angle it can burst, giving abrupt stall and hysteresis. Small changes in turbulence or roughness move the result. | ADflow SA: no. Spalart–Allmaras without transition makes the wall flow turbulent from the nose. In 2-D (XFOIL, 2°) that raises profile drag by 39–128 % (median 81 %) at Re ≥ 3 × 10⁵ (7 Nov, new sections). Carried as a model band (Stage 0). Transition must be captured too (decided 4 Nov 2026): our ADflow build has SA only, so it comes from SU2 (SST + LM γ-Reθ). | Carmichael 1981 (NASA CR-165803); Lissaman 1983 (Annu. Rev. Fluid Mech. 15); Mueller & DeLaurier 2003 (Annu. Rev. Fluid Mech. 35); our XFOIL runs (Drela 1989) |
| Very low Re at the tips | At the lowest level (1 × 10⁵ on the mean chord): the smallest BWB tip, 0.099 mean chords (focus; 0.055 full), runs at 9.9 × 10³ (5.5 × 10³); flying-wing, cranked and tapered tips (0.46, 0.44 and 0.57 mean chords) at about 4.4 × 10⁴ – 5.7 × 10⁴. First approach: BWB tips from 2.4 cm, tip Re down to about 1.4 × 10⁴. | Thick laminar boundary layers and early separation at the tip, where the vortex forms. | Weakly. Same model limit as above, at its worst. The first wall cell barely changes along the semi-span (Re and chord change together), but the thicker root boundary layer needs more wall layers. | Same as above; first-cell law: Grand Roadmap R-V.1 |
| Wake behind the trailing edge | Every wing, along the whole trailing edge. At high angle the wake leaves the edge at an angle (angles now run to post-stall); behind a blunt base it starts wide. | A thin sheet of slow air: the boundary layers of both surfaces leave the edge and carry the profile drag downstream. It sets the pressure at the trailing edge and base, and it rolls up toward the tips. | Only if the wake has its own cells. The S8 O-mesh has none: its cells grow fast behind the edge, so the wake smears. In AERIS, refining the near wake alone moved base drag by 23 counts. Plan (decided 6 Nov, decision 73; Stage 3): one matched C-H mesh for both solvers (SU2 has no overset), with wake cells sized for the whole angle range. | Primer section 05; Chan et al. 2002 |
| Tip vortex, roll-up and induced drag | Every wing; strongest at low aspect ratio (BWB down to AR 3 in the focus space, 2.5 in the full space) and high lift. | The wake sheet rolls up into one vortex per tip within about one chord. It causes the downwash and the induced drag, a large share of the total. | Yes, if the vortex keeps fine cells along its path. Plan (decided 6 Nov, decision 73; Stage 3): with one C-H mesh there is no separate vortex tube; the outboard blocks must resolve the vortex. | Primer section 05 |
| Sweep: spanwise flow, tip or root stall, pitch-up | BWB 5–40° and flying wing 10–40° (aft); cranked and tapered −5° to +15° (forward to aft). | Aft sweep pushes the boundary layer outboard, so the tip stalls first and the nose can pitch up. Forward sweep stalls the root first. | Spanwise flow: yes. Stall onset and pitch-up: less reliable with steady RANS near maximum lift; the post-stall part gets its own study (decided 6 Nov 2026). | Standard swept-wing aerodynamics |
| Panel breaks (kinks) at b1 and b2 | Every BWB and cranked wing; tapered and flying wings have no break in the edges. | Local suction peaks and a jump in the spanwise loading at the break; a ruled loft has a slope break there. | Yes: the Stage 2 surface mesher puts a station on every loft station, so one sits exactly on each break (fix 3, done). Without it, flat faces would cut the corner. | Loft decision (kSpan 2) |
| Separation and stall at high angle | High angles up to post-stall (now in scope: −5° to post-stall, decided 6 Nov 2026); already at 8° on thin or strongly cambered sections at low Re. | Trailing-edge or leading-edge separation, unsteady flow, maximum lift. | Steady RANS gives a number but is not reliable near maximum lift; convergence is harder. The post-stall part gets its own study (URANS or DDES on a few wings). | Stage 0 angles 0 / 4 / 8 / 12°; owner decision 6 Nov 2026 (−5° to post-stall) |
| Blunt trailing edge: base flow | Every wing: 0.2 % of the local chord (since 7 Nov 2026; first approach: max(0.5 mm, 0.2 % c) for Class I). Check C3 (CFD, to come): 0.1 / 0.2 / 0.3 % c and the thicker edges of small real wings, about 0.42 % c. | A base pressure drag and, in reality, vortex shedding behind the base. | Partly. Steady RANS damps the shedding. At 0.2 % with 8 cells the base was 2–4 % of pressure drag (measured in AERIS). | Primer section 03; Papadakis & Manolesos 2020 (flatback, RANS damps shedding) |
| Low Mach number | Under similarity the CFD runs at Mach 0.1, with a Prandtl–Glauert correction on CL and CM (check C2: 0.05 / 0.1 / 0.2). First approach: top speed 67 m/s, Mach ≤ 0.20 (tailless ≤ 0.13). Scope since 4 Nov 2026: Mach extends toward 0.5, with no supersonic flow; the data on this page stop at 0.2. | The air is nearly incompressible at these speeds. | The compressible solver needs low-speed preconditioning; without it ADflow did not converge in AERIS. | Primer track 3 |
| Slender, flexible wings | Cranked and tapered aspect ratio up to 16.5. | Long thin wings bend and twist in flight, which changes the spanwise loading. | No. The CFD wing is rigid. Many spanwise stations are needed. | Outside this study (no aeroelasticity) |

**Conclusion.** Most of these wings fly where transition and laminar bubbles set the drag, and fully turbulent SA cannot see them; that is why transition must be captured too (decided 4 Nov 2026). Mesh error can be made small; this model error cannot, so every SA drag number needs its model band. Differences between wings are safer than absolute drag only at a fixed airfoil, and even then not at the 2-count level (see Flow dataset).

## Flow maps

What the tool returns for one wing: the half wing coloured by local Re, the line where the upper surface turns turbulent, laminar bubbles, trailing-edge separation, the phenomena, the proposed model with the size of the SA error, whether the condition is level flight at a real wing loading, where the wing sits in the flow dataset, and the other section sets at the same condition. The 2-D answers come from the section tables (the same engine as the flow dataset; direct XFOIL for sections without a table).

**What changes (7 Nov 2026).** These maps were made on 31 Oct–2 Nov at real size and real speed (the first-approach mid wings) and are not rebuilt. The tool still takes a speed (or Mach) and an altitude, and it now reads a unit-mean-chord wing as a wing with a 1 m mean chord: to set an Re on the mean chord, give the speed V = Re / (ρ/μ) (ρ/μ = 6.85 × 10⁴ s/m² at sea level). Its level-flight flag needs a real size.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Flow map of the BWB mid wing: local Re, transition line, bubbles, phenomena and proposed model]</em></p>
<figcaption>BWB mid wing at 30 m/s, 1,000 m, 6°. The root runs at 6.7 × the tip Re; the upper surface turns turbulent at 33–72 % chord, later toward the tip as Re falls. Fully turbulent SA would raise the profile drag by +96 %: the tool proposes: transition model. Level flight here carries 202 N/m² (within the real band 96–386 N/m² for its full span).</figcaption>
</figure>

**Conclusion.** One run of the tool shows, for one wing at one condition, where the flow is laminar, where bubbles sit and which model to use. On this wing SA would add +96 % profile drag, so the tool proposes a transition model.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Mach by angle sheet of the BWB mid wing]</em></p>
<figcaption>The same wing over Mach × root angle (<code>--sheet</code>): SA error, laminar run, bubble share and trailing-edge separation per condition. Faded: not level flight at a real wing loading for its full span.</figcaption>
</figure>

**Conclusion.** No speed or angle makes SA right on this wing: the error is +41 to +103 % in every cell, and +60 to +101 % in the 9 level-flight cells.

## The focus space, per type: slow and fast, three section sets

Mid wing of each type. Slow: the family's lowest cruise speed at 3,048 m, 5°. Fast: its highest top speed at sea level, 1°. Sets: the suggested one and two sourced alternatives (SD7032 flies on the Puma 3AE, LA2573A on the Dragon Eye: NTNU database).

<table class="wide">
<colgroup>
<col style="width: 12%" />
<col style="width: 12%" />
<col style="width: 12%" />
<col style="width: 12%" />
<col style="width: 12%" />
<col style="width: 12%" />
<col style="width: 12%" />
<col style="width: 12%" />
</colgroup>
<thead>
<tr class="header">
<th>Type</th>
<th>Sections</th>
<th>Slow: Re</th>
<th>Slow: transition (upper)</th>
<th>Slow: SA drag</th>
<th>Fast: Re</th>
<th>Fast: transition (upper)</th>
<th>Fast: SA drag</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>BWB</td>
<td>suggested: MH 104 / MH 61</td>
<td class="num">9.7 × 10⁴ – 6.5 × 10⁵</td>
<td class="num">39–88 %<br />
bubble 33–93 %</td>
<td class="num"><strong>+54 %</strong></td>
<td class="num">5.0 × 10⁵ – 3.3 × 10⁶</td>
<td class="num">37–77 %<br />
bubble 39–79 %</td>
<td class="num"><strong>+53 %</strong></td>
</tr>
<tr class="even">
<td></td>
<td>S5010 (Lehmkuehler BWB)</td>
<td class="num">9.7 × 10⁴ – 6.5 × 10⁵</td>
<td class="num">39–78 %<br />
bubble 39–83 %</td>
<td class="num"><strong>+66 %</strong></td>
<td class="num">5.0 × 10⁵ – 3.3 × 10⁶</td>
<td class="num">41–71 %<br />
bubble 56–73 %</td>
<td class="num"><strong>+46 %</strong></td>
</tr>
<tr class="odd">
<td></td>
<td>NACA 4415 / 4412 (not reflexed)</td>
<td class="num">9.7 × 10⁴ – 6.5 × 10⁵</td>
<td class="num">51–89 %<br />
bubble 42–90 %</td>
<td class="num"><strong>+69 %</strong></td>
<td class="num">5.0 × 10⁵ – 3.3 × 10⁶</td>
<td class="num">49–89 %<br />
bubble 77–91 %</td>
<td class="num"><strong>+57 %</strong></td>
</tr>
<tr class="even">
<td>Flying wing</td>
<td>suggested: MH 60 / MH 45</td>
<td class="num">2.4 × 10⁵ – 3.9 × 10⁵</td>
<td class="num">40–69 %<br />
bubble 30–71 %</td>
<td class="num"><strong>+71 %</strong></td>
<td class="num">1.2 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">46–67 %</td>
<td class="num"><strong>+79 %</strong></td>
</tr>
<tr class="odd">
<td></td>
<td>S5010</td>
<td class="num">2.4 × 10⁵ – 3.9 × 10⁵</td>
<td class="num">40–62 %<br />
bubble 31–64 %</td>
<td class="num"><strong>+63 %</strong></td>
<td class="num">1.2 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">43–60 %<br />
bubble 56–62 %</td>
<td class="num"><strong>+69 %</strong></td>
</tr>
<tr class="even">
<td></td>
<td>MH 104 / MH 61</td>
<td class="num">2.4 × 10⁵ – 3.9 × 10⁵</td>
<td class="num">41–72 %<br />
bubble 30–75 %</td>
<td class="num"><strong>+49 %</strong></td>
<td class="num">1.2 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">38–69 %<br />
bubble 35–69 %</td>
<td class="num"><strong>+67 %</strong></td>
</tr>
<tr class="odd">
<td>Cranked</td>
<td>suggested: NACA 4415 / 4412</td>
<td class="num">1.6 × 10⁵ – 2.6 × 10⁵</td>
<td class="num">53–69 %<br />
bubble 39–73 %</td>
<td class="num"><strong>+56 %</strong></td>
<td class="num">1.2 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">49–66 %</td>
<td class="num"><strong>+65 %</strong></td>
</tr>
<tr class="even">
<td></td>
<td>SD7032 (Puma 3AE)</td>
<td class="num">1.6 × 10⁵ – 2.6 × 10⁵</td>
<td class="num">47–70 %<br />
bubble 32–72 %</td>
<td class="num"><strong>+61 %</strong></td>
<td class="num">1.2 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">46–68 %</td>
<td class="num"><strong>+85 %</strong></td>
</tr>
<tr class="odd">
<td></td>
<td>LA2573A (Dragon Eye)</td>
<td class="num">1.6 × 10⁵ – 2.6 × 10⁵</td>
<td class="num">41–46 %<br />
bubble 29–55 %</td>
<td class="num"><strong>-9 %</strong></td>
<td class="num">1.2 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">38–40 %<br />
bubble 34–42 %</td>
<td class="num"><strong>+28 %</strong></td>
</tr>
<tr class="even">
<td>Tapered</td>
<td>suggested: NACA 4415 / 4412</td>
<td class="num">1.9 × 10⁵ – 2.6 × 10⁵</td>
<td class="num">53–68 %<br />
bubble 39–71 %</td>
<td class="num"><strong>+55 %</strong></td>
<td class="num">1.4 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">49–64 %</td>
<td class="num"><strong>+65 %</strong></td>
</tr>
<tr class="odd">
<td></td>
<td>SD7032 (Puma 3AE)</td>
<td class="num">1.9 × 10⁵ – 2.6 × 10⁵</td>
<td class="num">47–68 %<br />
bubble 32–70 %</td>
<td class="num"><strong>+60 %</strong></td>
<td class="num">1.4 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">46–66 %</td>
<td class="num"><strong>+85 %</strong></td>
</tr>
<tr class="even">
<td></td>
<td>LA2573A (Dragon Eye)</td>
<td class="num">1.9 × 10⁵ – 2.6 × 10⁵</td>
<td class="num">41–45 %<br />
bubble 29–53 %</td>
<td class="num"><strong>-11 %</strong></td>
<td class="num">1.4 × 10⁶ – 2.0 × 10⁶</td>
<td class="num">38–40 %<br />
bubble 34–41 %</td>
<td class="num"><strong>+27 %</strong></td>
</tr>
</tbody>
</table>

"SA drag": how much fully turbulent SA would raise the wing's profile drag (chord-weighted XFOIL strips). Every case gets the same proposal: a transition model (γ-Reθ with SST, SU2) for drag; SA for mesh studies, and as an upper bound for drag except where a long bubble costs more than early turbulence (the negative values: LA2573A, slow).

**Conclusion.** Slow or fast, every type and section set gets about +27 to +85 % profile drag from SA. The one exception is LA2573A at slow speed (−9 to −11 %): its long bubble makes the real flow draggier than SA.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: BWB mid wing flow maps: three section sets, slow and fast]</em></p>
</figure>

**Conclusion.** BWB: +54 to +69 % slow and +46 to +57 % fast, whatever the sections. Changing the airfoils does not fix SA. (The NACA set cannot trim a tailless wing; it is shown for contrast.)

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Flying-wing mid wing flow maps]</em></p>
</figure>

**Conclusion.** Flying wing: +49 to +71 % slow and +67 to +79 % fast, the highest of all types at speed with the suggested sections (SD7032 on the conventional wings reaches +85 %).

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Cranked mid wing flow maps]</em></p>
</figure>

**Conclusion.** Cranked: +56 to +61 % slow with NACA 4415 and SD7032, but −9 % with LA2573A; +28 to +85 % fast. On conventional wings the airfoil changes the error the most.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Tapered mid wing flow maps]</em></p>
</figure>

**Conclusion.** Tapered: as the cranked wing: +55 to +60 % slow (−11 % with LA2573A), +27 to +85 % fast.

**What these maps cannot tell.** Strips are 2-D with one uniform induced angle: no spanwise change of the downwash, no crossflow transition on swept leading edges, no 3-D relief of bubbles. The angle (5° slow, 1° fast) is our choice, not trimmed. Use them to know where to look and which model to pick, not for numbers.

## Flow dataset: every focus wing, four section sets, every speed and angle

First approach, not rebuilt: made at real size and real speed before 7 Nov 2026. 201,600 rows: 400 focus wings (100 per type, the focus sets of 30 Oct–6 Nov at real size, full span ≤ 7 m) × 4 section sets × 7 Mach (0.03–0.2) × 6 root angles (0–10°) × 3 altitudes (0, 1,524, 3,048 m). Each row is one wing at one condition with 10 strips along the half wing, each strip a 2-D section answer from the section tables (XFOIL, free and tripped), with a uniform induced angle. 154,800 rows fly at speeds real wings of the family fly, with a section set that can trim the wing; the statistics below use those, unless marked (the NACA set on tailless wings cannot trim: it is shown, not counted). The scope has since grown: angles −5° to post-stall (decided 6 Nov 2026) and Mach toward 0.5 with no supersonic flow (4 Nov 2026); this dataset covers root angles 0–10° and Mach 0.03–0.2 only.

**What changes (7 Nov 2026).** This dataset was made at real size and real speed before 7 Nov (the 400 first-approach focus wings, full span ≤ 7 m, at speeds, altitudes and angles) and is not rebuilt: it is the first-approach record. In similarity form each shape would run at the four Re levels on the mean chord, at Mach 0.1. Its findings (SA's error, the bubbles, the bands) are statements about those wings at those Re, and they still guide the mesh and the model choice. The level-flight subset needs a real size. The 2-D section tables are size-free and were rebuilt on the fixed nose on 7 Nov: on the 20 reference wings at the four Re levels (0–10°) the SA drag error moves from +58.1 % to +59.0 % (median) and the model category stays the same on 480 of 480 conditions, so these findings stand.

### Rows

201,600

400 wings × 4 section sets × 126 conditions. Built in about two minutes from the section tables.

### SA drag error, median

+62 %

Fully turbulent SA against free transition, profile drag. 10–90 %: +17 % to +91 %. Within ±10 % in 5 % of rows.

### In level flight

+69 %

Median in the 23 % of rows that carry a real wing loading for their size. Within ±10 %: 4 %.

### Below Re 10⁵ somewhere

7 %

Share of rows with part of the half wing below 10⁵, mean of the four types (BWB 19 %, flying wing 2 %, cranked 5 %, tapered 3 %).

**Same assumptions as the flow maps.** 2-D strips along the half wing; local angle = root angle + twist − a uniform induced angle (elliptic, iterated); XFOIL e<sup>N</sup> with N<sub>crit</sub> 9 (quiet air) for free transition, tripped at 1 % chord for fully turbulent (what SA does); Stage 0 air. "SA drag error" = profile drag tripped / free − 1, chord-weighted along the semi-span. A grid point is "level flight" when the lift it makes (the strip lift with the induced angle) carries the wing loading real wings of the same full span carry (fit to 37 real wings, within × / ÷ 2).

**Four words used in every figure below.** **SA drag error**: how much more profile drag fully turbulent CFD (SA) gives than the real flow; +60 % means 1.6 times the real value, 0 means right. **Laminar run**: how far from the nose the flow on the upper surface stays laminar, in % of the chord. **Bubble share**: the share of the half wing with a laminar separation bubble (the figures label it "bubble span" or "span with a bubble": a share of the semi-span). **Level flight**: the wing makes the lift that real wings of its full span carry. Every figure has a *How to read* line and a conclusion box under it.

**Logic check (1 Nov 2026), applied 2 Nov 2026.** An independent review found that the first version left out the induced angle, which put the strips too close to stall at high angle. This version includes it (uniform, elliptic, iterated); every number and figure in this section comes from it. Three earlier findings were artefacts and are gone: the error falling to +20 % at 10° (it is +40 %), trailing-edge separation on 20 % of the half wing at 10° (it is 2 %), and "SA adequate" for flying wings at 10° (never). Also fixed: "beyond 2-D stall" is now "no XFOIL answer" (mostly failed points, not stall); the NACA set on tailless wings cannot trim, so it is shown but not counted; the sensitivity codes airfoil sets by name and is tested on wings it has not seen; a filled table gap never turns a bubble flag into 0.5. Still true and important: between similar wings, SA's error on the drag difference is about 4 counts (median), above the 2-count target in 71 % of pairs.

## What we found, under these assumptions

1.  **Fully turbulent SA overestimates the profile drag on almost every wing and condition.** Median +62 % (10–90 %: +17 % to +91 %); within ±10 % in only 5 % of rows. In level flight at real wing loadings: +69 % (+62 % to +78 % by type), within ±10 % in 4 %. The tool proposes a transition model for 97 % of rows.
2.  **SA's error does not cancel between similar wings.** For 5,759 pairs of wings of the same type and section set at the same speed, altitude and lift, SA's error on the profile-drag difference is 4 counts (median; 90 %: 18), above the 2-count target of Stage 0 in 71 % of pairs; SA ranks 6 % of the pairs the other way round. A drag dataset meant to rank wings needs transition-model results, at least on a calibration subset.
3.  **In level flight the error rises with speed.** +20 % at Mach 0.03, +81 % at Mach 0.14, +63 % at Mach 0.2. In level flight the angle follows the speed, so these are the trends to read; over the whole grid the speed trend is flatter (+44 % → +68 %).
4.  **In this 2-D model, how the wing flies sets most of the error.** Speed, angle and altitude explain 53 % of its spread alone on tailless wings (78 % with interactions), 29 % on conventional ones (75 %). The strips see the shape only through chord, twist and the induced angle, and the shares depend on our grid, which crosses every angle with every speed.
5.  **The error peaks at a moderate angle.** +81 % at 4° root angle, +40 % at 10°: at high angle the real flow turns turbulent near the nose by itself (laminar run 63 % of chord at 0°, 26 % at 10°). Trailing-edge separation stays small: at most 2 % of the half wing at any root angle up to 10°.
6.  **On conventional wings the airfoil changes the error most.** The airfoil set alone explains 11 % of the spread, 54 % with its interactions; on LA2573A the error grows with the angle, on the others it falls. Lowest median: LA2573A (+34 %, its bubbles already cost drag in the real flow); highest: NACA 4415 / 4412 and SD7032 (+67 %). SA would rank airfoils wrongly.
7.  **Below Re 10⁵ the sign flips.** Where most of the half wing is below 10⁵ (1,607 rows), the median error is −4 % and 58 % are negative: long laminar bubbles give the real flow more drag than fully turbulent CFD. Part of the half wing is below 10⁵ in 19 % of BWB rows, 2 % flying wing, 5 % cranked, 3 % tapered. There SA is wrong in sign, XFOIL itself is least reliable, and a transition model must be checked against experiments before it is trusted.
8.  **Laminar bubbles are the normal case, and they move.** On average 52 %–72 % of the half wing has an upper-surface bubble, depending on the angle; 90 % at Mach 0.03, 45 % at Mach 0.2. Bubbles start from about 11 % and end by about 78 % of the chord (30 % of them lie partly outside 30–70 %); the lower surface stays laminar to about 99 % of the chord. A transition-model mesh needs fine streamwise cells over the upper surface from about 10 to 85 % (Stage 2 builds it from the leading edge on every wing) and the lower surface from 60 to 100 %, and y⁺ ≤ 1. These bands hold for root angles 0–10°: at negative angles (now in scope, down to −5°) the lower surface becomes the suction side, so its band must start further forward.
9.  **Size acts through Re; sweep does not enter the strips.** The mean chord is the strongest shape input (larger chord, higher Re, larger SA error up to about Re 10⁶). Aspect ratio acts through the uniform induced angle, washout and taper through the local angle and chord. Sweep scores like dihedral (a built-in placebo): 'not modelled', not 'unimportant'. In 3-D, sweep drives spanwise flow, crossflow and tip stall.
10. **Swept tailless wings may see crossflow transition (rough flag).** 44 % of BWB rows and 17 % of flying-wing rows have a strip swept over 25° with Re normal to its edge above 10⁶ (our threshold, not sourced). Neither XFOIL nor γ-Reθ without a crossflow term sees it; there the transition position is less certain, so on swept panels the mesh transition band starts at the leading edge.
11. **Our assumptions move the numbers, not the sign.** More turbulent air (N<sub>crit</sub> 5) changes the error by −11 points, quieter air (11) by +2; leaving out the induced angle (the old baseline) by −4 (5–95 %: −41 to +15, the big changes at high angle); compressibility by +0.5; the strip count by under 0.1. The tables reproduce direct XFOIL to a median 0.7 % in drag.
12. **In the whole drag the error is smaller, but still large.** With an elliptic induced drag added, fully turbulent SA overestimates the total drag by a median +18 % to +33 % by type: far above the 3-count drag budget of Stage 0.
13. **What this means for the CFD.** Start the mesh studies with SA (ADflow), with its inflow eddy viscosity fixed (ν̃/ν about 3). SA gives an upper bound for drag only where Re is above about 10⁵ and there is no long bubble (below 10⁵, and for LA2573A in slow flight, the real flow has more drag). Make the mesh transition-ready (y⁺ ≤ 1 at each station's Re, fine cells over the whole chord on both sides, as Stage 2 builds since 7 Nov) and repeat a reduced mesh study with the transition model: what a mesh must resolve depends on the model. Transition must be captured (decided 4 Nov 2026): for drag numbers or rankings, run SU2 SST + LM γ-Reθ (proposal, pending: on about 20 % of the wings first; ADflow SA for all mesh studies and the fully turbulent data). Below Re 10⁵, neither is enough. The tool gives the band, the bubble positions and the model for any wing in milliseconds. Stage 2 now uses it: a per-wing refine map reads this dataset to place the band. Cost at the fine level: first estimated at 15.2 M cells (median), 10.9 M with the lighter band (decided 6 Nov, decision 72); measured on 8 Nov (Stage 2 Study 12): 6.73 M median on the reference wings, 5.91 M over every set, largest 10.21 M.

## 1. The 2-D building blocks

Every section, free and tripped, on a grid of 14 Re (1.5 × 10⁴ – 6 × 10⁶) × 3 Mach (0, 0.1, 0.2) × 49 angles (−10° to 14°): 2,408 XFOIL sweeps, made robust (a failing angle is skipped, never hangs). A wing is then evaluated in milliseconds by interpolation. Outside the grid the tool holds Re and Mach at the grid edge (and flags it) and gives no answer for other angles: the full space reaches Re 7.1 × 10³ – 7.6 × 10⁶, and the smallest focus BWB tips (1.4 × 10⁴) sit just below the grid.

<figure class="fig card">
Built before 7 Nov 2026 · size-free · old nose (tables rebuilt 7 Nov: same conclusions)
<p><em>[Figure: Transition maps of the ten sections]</em></p>
<figcaption>How to read. Ten small maps, one per airfoil (2-D XFOIL, free transition, Mach 0.1). In each map, left to right is the angle the airfoil sees (−6° to 14°) and bottom to top is its Re (4 = 10⁴, 5 = 10⁵, 6 = 10⁶). The colour shows where the flow on the upper surface turns turbulent: yellow = near the trailing edge (long laminar run), dark purple = near the nose. Grey: XFOIL gave no answer (near stall, but also at some small angles). Dashed lines: the four study Re levels.</figcaption>
</figure>

**Conclusion.** On every airfoil the laminar run is long at low Re and small angles, and shrinks as Re or the angle grows. Our wings fly mostly at small angles and Re 10⁵ – 3 × 10⁶, where the run is long; fully turbulent CFD throws it away.

<figure class="fig card">
Built before 7 Nov 2026 · size-free · old nose (tables rebuilt 7 Nov: same conclusions)
<p><em>[Figure: Laminar bubble maps of the ten sections]</em></p>
<figcaption>How to read. Same ten maps and axes. Red: XFOIL finds a laminar separation bubble on the upper surface (the laminar flow lifts off, turns turbulent and lands again). White: no bubble. Grey: no answer.</figcaption>
</figure>

**Conclusion.** Every airfoil has bubbles over a wide band, from about Re 6 × 10⁴ to 2 × 10⁶ at small and moderate angles. They change drag and lift, and fully turbulent CFD cannot see them.

<figure class="fig card">
Built before 7 Nov 2026 · size-free · old nose (tables rebuilt 7 Nov: same conclusions)
<p><em>[Figure: Drag ratio tripped over free for the ten sections]</em></p>
<figcaption>How to read. Same maps. The colour is the SA drag error of the airfoil: how much more profile drag it gets when made fully turbulent (tripped) than with real free transition. Red: SA gives too much drag (darkest about +150 %). White: about the same. Blue: the real flow has more drag than SA (a long bubble).</figcaption>
</figure>

**Conclusion.** Fully turbulent CFD gives +50 to +150 % profile drag over most of the useful range (Re 3 × 10⁵ – 3 × 10⁶, small angles). It is close only near stall (white), and below about Re 10⁵ the sign flips (blue).

## The tables rebuilt on the fixed nose (7 Nov 2026)

All 2,408 sweeps were run again on the sections of the new nose rule (decision 64; 40 min on 2 workers). The three maps above are from the old tables (first approach); the code now reads the new ones.

<figure class="fig card">
<p><em>[Figure: Section tables rebuilt on the fixed nose: new minus old, by Re]</em></p>
<figcaption>How to read. New minus old, against the Re on the section chord (log scale), over the 10 sections, angles −10° to 14° and Mach 0, 0.1 and 0.2. Top: change in the transition position (% c), upper side blue, lower side orange; solid = 95th percentile, dotted = median. Middle: change in drag (%), free transition blue, tripped orange. Bottom: XFOIL answers gained (+) and lost (−), as % of the grid points.</figcaption>
</figure>

**Conclusion.** The fixed nose changes the tables little: the upper transition moves a median 0.19 % c (95 % of points within 1.5 % c) and drag a median 0.8 % (95 % within 9.9 %); the larger changes sit near the 2-D stall and at high Re. On the 20 reference wings × 4 Re levels × 0–10° the SA drag error is +59.0 % (median; +58.1 % on the old tables) and the model category is the same on 480 of 480 conditions: no Stage 1 conclusion changes. Weak spot: on single conditions the share of the half wing with an upper bubble can move by up to 37 points (its mean by 0.3).

## 2. Where the wings fly in Re

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Share of the half wing in each Re band against Mach]</em></p>
<figcaption>How to read. One panel per type. Left to right: flight Mach (speed). Bottom to top: share of the half wing, 0–100 %. The coloured layers show how much of the half wing sits in each Re band: red below 10⁵, orange 10⁵ – 5 × 10⁵ (bubbles), light blue 5 × 10⁵ – 3 × 10⁶, dark blue above 3 × 10⁶. At any Mach the layers add up to 100 %. Mean over all focus wings, section sets and altitudes.</figcaption>
</figure>

**Conclusion.** Slow flight puts most of the wing in the bubble band: at Mach 0.03, 67–91 % of the half wing is at Re 10⁵ – 5 × 10⁵ and 2–13 % is below 10⁵. At Mach 0.14 the bubble band shrinks to 3–16 %. Re above 3 × 10⁶ appears only at the highest speeds (a quarter of the BWB half wing at Mach 0.2, faster than real BWBs fly).

## 3. How wrong is fully turbulent SA?

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Distribution of the SA drag error per type and section set]</em></p>
<figcaption>How to read. One panel per type; one violin per section set (* = suggested). A violin is wide where many cases have that SA drag error. Dot and bar: the median and the middle 80 % of cases. White diamond: the median in level flight. Green band: ±10 %, where SA would be good enough. Cases: all focus wings at realistic speeds, all angles and altitudes.</figcaption>
</figure>

**Conclusion.** For every type and section set the median error is +34 to +70 %. Few cases fall in the green band: at most 1 % with the suggested sections, at most 15 % (E387; LA2573A 14–15 %). Changing the airfoil does not make SA right.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: SA drag error against wing mean Re per root angle]</em></p>
<figcaption>How to read. One panel per type (suggested sections). Left to right: the wing's mean Re (log scale: 5 = 10⁵, 6 = 10⁶). Bottom to top: SA drag error. Each coloured line is the median for one root angle (dark purple 0° to yellow 10°); the grey cloud is all cases. Green band: ±10 %. Dotted red line: Re 10⁵.</figcaption>
</figure>

**Conclusion.** The error is largest near Re 10⁶ at 4–6° root angle, up to about +95 %. At 10° it is smaller (about +30 % on flying wings, +40 to +70 % on the others) but never inside ±10 %. On conventional wings it falls toward zero near Re 10⁵ and turns negative below it (bubbles).

| Type | Section set | SA drag error, median | 10–90 % | Within ±10 % | Laminar run, upper | Half wing with a bubble | Half wing with TE separation | Half wing with a 2-D answer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BWB | MH 104 / MH 61 (suggested) | **+65 %** | +40 % to +92 % | 0 % | 49 % | 81 % | 3 % | 99 % |
| | S5010 | **+64 %** | +33 % to +88 % | 0 % | 47 % | 59 % | 1 % | 98 % |
| | MH 60 / MH 45 | **+69 %** | +41 % to +91 % | 0 % | 49 % | 50 % | 3 % | 98 % |
| | NACA 4415 / 4412 (not reflexed) (cannot trim: not counted) | **+65 %** | +36 % to +87 % | 2 % | 59 % | 56 % | 8 % | 98 % |
| Flying wing | MH 60 / MH 45 (suggested) | **+70 %** | +34 % to +95 % | 0 % | 47 % | 48 % | 0 % | 100 % |
| | S5010 | **+65 %** | +36 % to +91 % | 0 % | 45 % | 57 % | 0 % | 100 % |
| | MH 104 / MH 61 | **+64 %** | +38 % to +92 % | 0 % | 49 % | 80 % | 0 % | 100 % |
| | NACA 4415 / 4412 (not reflexed) (cannot trim: not counted) | **+69 %** | +50 % to +88 % | 0 % | 57 % | 62 % | 1 % | 98 % |
| Cranked | NACA 4415 / 4412 (suggested) | **+67 %** | +40 % to +88 % | 1 % | 51 % | 57 % | 2 % | 97 % |
| | SD7032 | **+67 %** | +23 % to +95 % | 2 % | 45 % | 39 % | 1 % | 100 % |
| | LA2573A | **+36 %** | −9 % to +89 % | 14 % | 39 % | 90 % | 2 % | 98 % |
| | E387 (low-Re benchmark) | **+49 %** | +4 % to +94 % | 15 % | 53 % | 80 % | 1 % | 98 % |
| Tapered | NACA 4415 / 4412 (suggested) | **+67 %** | +40 % to +88 % | 1 % | 52 % | 60 % | 2 % | 97 % |
| | SD7032 | **+67 %** | +24 % to +96 % | 2 % | 46 % | 41 % | 1 % | 100 % |
| | LA2573A | **+34 %** | −12 % to +88 % | 15 % | 39 % | 90 % | 2 % | 98 % |
| | E387 (low-Re benchmark) | **+50 %** | +4 % to +94 % | 15 % | 54 % | 82 % | 1 % | 98 % |

Realistic speeds only (tailless Mach ≤ 0.14, the grid level just above their top speed at Mach 0.13; conventional ≤ 0.20), all angles 0–10° and altitudes; every set is shown. Means and medians over rows; each wing counts once per condition. Precision: resampling the 100 wings of a type moves its median SA error by at most ±1.9 points (95 %).

**Conclusion.** Over all cases at realistic speeds SA is within ±10 % only 5 % of the time. The type changes the median little (+59 to +67 %); on conventional wings the airfoil set matters more (+34 to +67 %).

## In level flight only

| Type | Rows in level flight | SA drag error, median | 10–90 % | Within ±10 % | Laminar run, upper | Half wing with a bubble | Half wing with TE separation | Rows with part below Re 10⁵ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BWB | 18 % | **+75 %** | +47 % to +95 % | 0 % | 44 % | 51 % | 1 % | 12 % |
| Flying wing | 19 % | **+78 %** | +40 % to +98 % | 0 % | 44 % | 44 % | 0 % | 1 % |
| Cranked | 29 % | **+64 %** | +17 % to +93 % | 6 % | 46 % | 65 % | 1 % | 3 % |
| Tapered | 28 % | **+62 %** | +16 % to +92 % | 6 % | 46 % | 69 % | 1 % | 2 % |

As a share of the whole drag (profile + an elliptic induced drag, CL from the strips with the induced angle, 20 wings per type): BWB +32 % (profile only +63 %), Flying wing +33 % (profile only +69 %), Cranked +20 % (profile only +60 %), Tapered +18 % (profile only +59 %). By root angle: 0° +39 %, 2° +38 %, 4° +29 %, 6° +20 %, 8° +13 %, 10° +8 %.

**Conclusion.** In level flight (23 % of cases) the error is even larger: median +62 to +78 % by type, within ±10 % in at most 6 %. Counted on the whole drag (profile + induced), fully turbulent CFD is about +18 to +33 % too high.

## 4. Trends

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Trends with flight Mach]</em></p>
<figcaption>How to read. Four columns, one per type. Three rows: SA drag error; laminar run on the upper surface (% of chord); share of the half wing with a bubble. Left to right: flight Mach. Line: median; shaded band: the middle half of the cases; one colour per section set. Grey zone: faster than any real wing of that family.</figcaption>
</figure>

**Conclusion.** Flying faster (higher Re) shortens the laminar run (about 54 → 39 % of chord) and removes bubbles (from 90 % to 45 % of the half wing). The SA error grows from +44 % at Mach 0.03 to about +70 % at Mach 0.11–0.14 and stays near that. In level flight the rise is steeper: +20 % at Mach 0.03, +81 % at 0.14, +63 % at 0.20.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Trends with root angle]</em></p>
<figcaption>How to read. Same layout as above, but left to right is the root angle (0–10°).</figcaption>
</figure>

**Conclusion.** A higher angle moves transition toward the nose (laminar run 63 → 26 % of chord). The error peaks at about 4° (+81 %) and falls to +40 % at 10°. LA2573A is the exception: its error grows with the angle. Trailing-edge separation stays at 1–2 % of the half wing up to 10°.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: SA drag error against single wing inputs]</em></p>
<figcaption>How to read. Six panels, one wing input each: mean chord (size), aspect ratio, washout, sweep, taper, dihedral. Left to right: the input value; bottom to top: SA drag error. Line: median; band: the middle half; one colour per type. Suggested sections, realistic speeds.</figcaption>
</figure>

**Conclusion.** Size acts through Re: bigger wings (larger mean chord) have about 15–22 points more error. With the induced angle, aspect ratio now acts too (flying wings: about −14 points from the lowest to the highest aspect ratio), and more washout lowers the error on flying wings (about −9 points). Sweep and dihedral stay within ±6 points: sweep does not enter the strips, and dihedral is the check that shows the noise level.

## 5. Which model, where

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Proposed model per Mach and angle]</em></p>
<figcaption>How to read. One panel per type (suggested sections). Left to right: flight Mach; bottom to top: root angle. Each cell is one flight condition. Colour: the model the tool proposes for most wings there (green: SA is enough; orange: transition model; red: transition model, part of the half wing below Re 10⁵; grey: no XFOIL answer). Number: the median SA drag error in %. Black frame: half or more of the wings fly level there at a real wing loading.</figcaption>
</figure>

**Conclusion.** Almost every cell is orange: these wings need a transition model for drag; SA is adequate in only 2 % of cases. The BWB is red at the slowest speed (part of its half wing below Re 10⁵). In the framed level-flight cells the median error is +32 to +95 %.

## 6. What drives the flow: sensitivity

The dataset crosses wings, section sets and conditions in full, so the three groups are independent and their shares can be read apart. A gradient-boosted model (test R² in the table) gives each group's share alone and with its interactions (total).

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Variance shares of wing shape, sections and flight condition]</em></p>
<figcaption>How to read. Two panels: tailless and conventional wings. One bar per output (SA drag error, laminar run, bubbles and so on). Each bar splits how much that output varies into what each group explains on its own: blue = wing shape, brown = sections, green = how it flies (speed, angle, altitude); grey = only when the groups act together. On the right, 'total' is each group's share including what it does together with the others.</figcaption>
</figure>

**Conclusion.** In this 2-D model, how the wing flies sets most of the SA error: 53 % on its own for tailless wings (78 % in total). On conventional wings the airfoil matters as much, mostly together with the angle (11 % alone, 54 % in total), so SA would rank airfoils wrongly. The wing shape alone explains 7–8 %. The strips see shape only through chord, twist and the induced angle, and the shares depend on our grid, which crosses every angle with every speed.

| Family | Output | Wing shape alone / total | Sections alone / total | Flight alone / total | Model R² | Strongest inputs (share of importance; ↑ grows with it, ↓ falls) |
| --- | --- | --- | --- | --- | --- | --- |
| **tailless** | SA drag error | 8 / 28 | 1 / 9 | 53 / 78 | 88 % | angle 51 % ↓, Mach 21 % ↑, size (mean chord) 10 % ↑ |
| | laminar run (upper) | 4 / 7 | 0 / 7 | 83 / 92 | 97 % | angle 76 % ↓, Mach 10 % ↓, section set 7 % |
| | half wing with a bubble | 11 / 25 | 15 / 24 | 46 / 63 | 91 % | Mach 43 % ↓, section set 20 %, size (mean chord) 17 % ↓ |
| | half wing with TE separation | 11 / 50 | 1 / 10 | 22 / 63 | 76 % | Mach 32 % ↓, angle 20 % ↓, size (mean chord) 20 % ↓ |
| | half wing below Re 10⁵ | 21 / 70 | 0 / 0 | 19 / 68 | 89 % | Mach 41 % ↓, size (mean chord) 35 % ↓, taper 19 % ↓ |
| **conventional** | SA drag error | 7 / 18 | 11 / 54 | 29 / 75 | 95 % | section set 35 %, angle 33 % ↓, Mach 19 % ↑ |
| | laminar run (upper) | 4 / 6 | 5 / 24 | 68 / 88 | 97 % | angle 65 % ↓, section set 20 %, Mach 9 % ↓ |
| | half wing with a bubble | 7 / 26 | 24 / 56 | 22 / 55 | 91 % | section set 39 %, Mach 31 % ↓, size (mean chord) 18 % ↓ |
| | half wing with TE separation | 6 / 56 | 0 / 38 | 8 / 66 | 73 % | size (mean chord) 28 % ↓, Mach 28 % ↓, section set 19 % |
| | half wing below Re 10⁵ | 11 / 82 | 0 / 0 | 15 / 85 | 96 % | size (mean chord) 47 % ↓, Mach 47 % ↓, altitude 5 % ↑ |

**Conclusion.** For the SA error the strongest inputs are the angle (51 %) and Mach (21 %) on tailless wings, and the airfoil set (35 %) and the angle (33 %) on conventional ones. The share of the half wing below Re 10⁵ depends on speed and size (and taper on tailless wings).

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Permutation importance per input and output]</em></p>
<figcaption>How to read. Two panels (tailless, conventional). Rows: inputs; columns: outputs. A darker cell means that input matters more for that output: it measures how much worse a fitted model predicts when that input is shuffled (each column adds up to 1). + / −: the output grows / falls as the input grows.</figcaption>
</figure>

**Conclusion.** Angle, Mach, size and the airfoil set carry most of the importance. Taper matters for the low-Re tips of tailless wings, washout for where they lose the 2-D answer. Sweep cannot score: the strips do not use it.

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: First-order variance share per input and output]</em></p>
<figcaption>How to read. Same layout, with a simpler measure that needs no model: the share of the variation one input explains on its own (η²). For wing inputs, values up to about 0.05 are noise: dihedral, which cannot change a strip answer, shows that level.</figcaption>
</figure>

**Conclusion.** The simple measure agrees with the model: angle and Mach dominate, size comes next, and the other wing inputs are near noise level, as expected for inputs the 2-D strips barely use.

## 7. How much do our assumptions change the answer?

Each check reruns 20 wings per type with one assumption changed, and compares the same wing, sections and condition (percentage points of the SA drag error, laminar run, bubble share and TE-separation share of the half wing).

<figure class="fig card">
First approach · real size and real speed, before 7 Nov 2026 · not rebuilt
<p><em>[Figure: Assumption checks and table verification]</em></p>
<figcaption>How to read. Left: one box per changed assumption, on the same wings, sections and conditions; it shows how many points the SA drag error moves (line: median; box: the middle half; 0 = no change). Middle: profile drag from the section tables (up) against a direct XFOIL run (across) at 320 random points; dots on the diagonal agree. Right: the same for where the flow turns turbulent.</figcaption>
</figure>

**Conclusion.** Only the turbulence level of the air (N<sub>crit</sub>) moves the headline much: N<sub>crit</sub> 5 lowers the error by 11 points (median). Leaving out the induced angle (the old baseline) changes the median by only −4 points, but by up to −41 points at high angle: that is where the old trends went wrong. More or fewer strips and compressibility change almost nothing, and the tables match direct XFOIL (median drag difference 0.7 %). The main finding, SA gives too much drag, holds in every check.

| Changed | SA error, median change \[points\] | 5–95 % | Laminar run, median change \[points\] | Bubble share, mean size of change \[points\] | TE-separation share, mean size of change \[points\] | Pairs |
| --- | --- | --- | --- | --- | --- | --- |
| N<sub>crit</sub> 5 instead of 9 (air turbulence 0.37 % instead of 0.07 %) | −10.7 | −31.7 to +21.1 | −7.0 | 36.7 | 1.4 | 40,320 |
| N<sub>crit</sub> 11 instead of 9 (0.03 %: very quiet air) | +2.0 | −14.9 to +11.8 | +2.3 | 14.6 | 1.5 | 40,320 |
| No compressibility in 2-D (Mach 0, same Re) | +0.5 | −0.7 to +2.5 | +0.2 | 1.3 | 0.1 | 40,320 |
| 7 strips instead of 10 | −0.1 | −1.2 to +0.6 | 0 | 2.9 | 0.5 | 40,320 |
| 19 strips instead of 10 | +0.1 | −0.3 to +0.6 | 0 | 1.5 | 0.3 | 40,320 |
| Induced angle left out (the old baseline) | −3.8 | −41.1 to +14.7 | −5.5 | 10.1 | 3.4 | 40,320 |
| Section tables instead of direct XFOIL (320 random points) | CD error, median 0.7 % (free), 0.3 % (tripped); 90 % below 4 % | | 0.1 | bubble yes/no agrees 98 % | | 320 |
| Blend rule (average of the two parents) instead of the blended section, 3 pairs | CD error, median 0.0–4.0 % by pair | | 2.1 | | | 2,391 |

**Conclusion.** Bubbles are the most fragile answer: with N<sub>crit</sub> 5 the bubble share changes by 37 points on average, far more than the laminar run (about 7 points). Bubble results need a 3-D or wind-tunnel check before we rely on them.

**Limits of this approach.**

- **2-D strips, not a 3-D flow.** No crossflow transition on swept edges, no spanwise boundary-layer drift, no 3-D relief of bubbles, no tip vortex. The induced angle is one uniform (elliptic) value; its spanwise change is not modelled.
- **XFOIL is a model too.** e<sup>N</sup> with one N<sub>crit</sub> for the whole wing; it is least reliable below Re 5 × 10⁴, in long bubbles and near stall. "Beyond 2-D stall" means no answer, not a measured stall.
- **The grid is a box, not a flight envelope.** Speeds and angles are crossed in full; the level-flight subset uses a wing-loading fit (37 real wings) and a lift estimate, both rough.
- **Statistics describe our ranges.** 100 wings per type, drawn evenly in the focus box, four section sets each. Shares and medians depend on those choices; they are not shares of real aircraft.
- **The error measure is a proxy.** Tripped vs free 2-D profile drag is the part of the SA error that comes from transition. Real 3-D RANS adds its own errors, and a transition model has its own too.

## The tool, updated

    pip install -e CFD_Automation                            # once, from the repo root: the shared cfdauto package (outputs: Stage_1_geometry/docs/)
    tar -xzf data/section_cache.tar.gz -C data              # the raw XFOIL sweeps (in git since 9 Nov): no XFOIL run needed
    python -m cfdauto.flowmap.tables --build                 # section tables (XFOIL, about 40 min on 2 cores; resumable)
    python -m cfdauto.flowmap.dataset                        # the flow dataset (201,600 rows, about 2 min): first approach;
                                                             #   do not rerun as is: it would put every wing at a 1 m mean chord
    python -m cfdauto.flowmap.analysis                       # figures, sensitivity, checks: docs/flow_*.png, docs/flow_analysis.json
    python -m cfdauto.flowmap --type bwb --set reference --index 0 --speed 13.4 --altitude 0 --alpha 4
                                                             # one wing: flow map, model, where it sits in the dataset. The wing is at
                                                             #   unit mean chord and the tool reads it as 1 m: pick the speed for the Re
                                                             #   you want (here Re 9.2e5 at sea level); its level-flight flag needs a real size
    python -m cfdauto.flowmap --type bwb --set reference --index 0 --speed 13.4 --sheet
                                                             # + a Mach × angle sheet: here Mach sets the Re (at a 1 m mean chord,
                                                             #   Mach 0.03–0.20 is Re 7.0 × 10⁵ – 4.7 × 10⁶ at sea level)
    python -m cfdauto.flowmap ... --method xfoil | --ncrit 5 | --no-induced | --strips 5   # direct XFOIL, assumption checks

## Where the mesh must be fine

Each phenomenon above lives in one region of the flow; each region gets its own rule. The rules are the Grand Roadmap recipes (R-S, R-V) and the Stage 0 error budget: the share is how much of the 65 % grid error each direction may use. The last column says what the Stage 2 surface mesher does today (8 Nov 2026: 3,128 of 3,128 builds pass its 13 checks on the 7 Nov wings, numpy loft; Study 12); the volume mesh is Stage 3 and not built, so S8's values stay there for reference. Angles now run from −5° to post-stall (decided 6 Nov 2026), and transition must be captured (decided 4 Nov 2026).

**What changes (7 Nov 2026).** No switch sections (the trailing edge is 0.2 % c everywhere), so the loft stations sit only at b0–b3. The nose is the 7 Nov nose (apex leading edge, 201 points per side); on a NACA 4415 station the 10° target holds up to a nose spacing of 0.377 % c with it (0.327 % c with the old rule). Every wing is at unit mean chord, so the first cell follows from y⁺ = 1 at each case's Re. The Stage 2 values in the last column were measured on the first-approach wings (790 builds).

<figure class="fig">
<p><em>[Diagram: Side view of the mesh zones around one section: wall layers on the whole surface, fine cells at the nose, at the trailing edge and across the blunt base, the near-body mesh reaching about two chords, a tilted wake box with cells of 0.0075 chord to two chords behind the trailing edge then growing to ten chords, and the background box of 0.03 chord. The wake box and the background box are the overset plan, under review: C-H proposal, pending]</em></p>
<figcaption>Side view: fine cells at the wall (all around), at the nose and at the trailing edge, then a wake box that stays fine for 2 chords and coarsens to 10 chords, all inside the background box. The wake box and the background box are the first (overset) plan; since 6 Nov one matched C-H mesh for both solvers replaces them (decision 73; SU2 has no overset; Stage 3 builds it).</figcaption>
</figure>

**Conclusion.** Cells must be small where the flow changes fast: at the wall, the nose, the trailing edge and the near wake. Further away they can grow. The near wake must hold the wake from −5° to post-stall.

<figure class="fig">
<p><em>[Diagram: Top view of the mesh zones: stations nearly even from the root and squeezed toward the tip, a station on each break b1 and b2, outboard blocks reaching 1.5 root chords beyond the tip, the wake box behind the whole trailing edge, and a vortex tube starting about two chords behind the tip. The wake box and the tube are the overset plan, under review: C-H proposal, pending]</em></p>
<figcaption>Top view: stations nearly even from the root, squeezed toward the tip, and one exactly on each break; outboard blocks past the tip; the wake box behind the whole trailing edge; the vortex tube from about 2 chords behind the tip. Since 6 Nov (decision 73, C-H): no wake box and no tube; the outboard blocks resolve the tip vortex (Stage 3).</figcaption>
</figure>

**Conclusion.** Along the semi-span: more stations near the tip, where the flow changes fastest, and one exactly on each break, where the surface has a kink; the Stage 2 surface mesher builds both. The tip vortex needs fine cells along its path: a tube in the first (overset) plan; with C-H (decision 73) the outboard blocks must resolve it.

| Zone | Captures | Rule (starting value) | Budget share | Source | Stage 2 today (6 Nov) |
| --- | --- | --- | --- | --- | --- |
| Wall-normal, every wall | Boundary layer, skin friction, separation and transition (transition must be captured: decided 4 Nov 2026) | First cell from y⁺ ≤ 1 at the Re of each case (law 13 per station; along the semi-span it changes only about 20 %, because Re and chord change together, and the smallest chord sets it); growth ≤ 1.25 inside the boundary layer, ≤ 1.3 outside (about 1.1 with a transition model, decision 57: settled by the levels, 1.25 at VC is 1.107 at F, decision 71); ≥ 30 cells across the boundary layer at every station (on a small BWB the root boundary layer is up to about 10 × thicker than the tip's) | wall-normal 20 % | Roadmap R-V.1, R-V.2 (laws 13, 14); DPW gridding guidelines; Ansys CFX transition-model grid guidance (growth about 1.1) | Volume mesh: Stage 3, not built. Stage 2 uses the tip first cell s0 (y⁺ = 1 at the tip Re) for the last station gap. S8 for reference: one first cell (4.71 µm) for every station; growth 1.253; 29 cells across the boundary layer |
| Leading edge (nose) | Suction peak, start of the laminar run, leading-edge stall (angles now −5° to post-stall) | Chordwise spacing solved so no cell turns the surface by more than 10° at M (16.9 / 13 / 10 / 7.69° at VC / C / M / F; decision 71); nose cells of neighbouring stations differ by at most 15 % | edges and base 15 % (Stage 0 counts the nose cells there) | Roadmap R-S.5, R-S.6 (laws 1, 2) | Built on the first-approach wings: no ring node turns the surface by more than 10° (largest delivered 10.02°); the nose spacing changes by at most 1.15 between stations. Since then the 7 Nov nose (apex leading edge, 201 points per side, decision 64) is meshed: every set at every level, 3,128 of 3,128 pass, the turning inside each level's check limit (Stage 2 Study 12). On a NACA 4415 station the 10° target holds up to a nose spacing of 0.377 % c with the new rule (0.327 % c with the old) |
| Transition band: lower surface 0–100 % chord (7 Nov; first 60–100 %); upper surface 0–100 % chord (8 Nov; first 0–85 %, from the leading edge on every wing) | End of the laminar run and laminar bubbles; they move with the angle (on top from about 11 % to 78 % of the chord at 0–10°), and the lower surface turns turbulent near the trailing edge. At negative angles the lower surface becomes the suction side. On swept panels crossflow transition, which the 2-D strips cannot see, would start at the leading edge | Required (transition must be captured: decided 4 Nov 2026): fine chordwise cells over the band, cell = bubble length / 20 at the fine level F (decided 6 Nov; first: at level C; bubble length from our XFOIL table at the local Re); band cell 0.5 % c at F where the local Re ≥ 4 × 10⁵ (decided 6 Nov); growth along the ring ≤ 1.25 at VC. The upper band written as 0–100 % c (8 Nov; at most +1.1 % cells, Stage 2 Study 12); the band on for every run (decision 81). Candidate: a per-wing band from the refine map (decision 65; run at the four Re levels) | chordwise 35 % | Ansys CFX transition-model grid guidance (about 20 nodes per bubble, growth about 1.1, y⁺ about 1, 75–100 streamwise nodes); band edges from our 2-D strips (root angles 0–10°) | Since 7 Nov: levels VC–F, lower band 0–100 % c (decision 74); at the four Re levels the refine map finds the upper transition past 85 % c at low Re, so since 8 Nov the upper band is written 0–100 % c. First: built at level C, with the upper band from the leading edge on every wing (Stage 2 choice 58). Refine map (decision 65, candidate): on washed-out outboard panels the generic band misses lower-surface transition near the leading edge (by 52–60 % c) and upper transition past 85 % c at low angle (by up to 15 % c); the shortest root bubbles (1.4–10.7 % c) get fewer than 20 cells (1.2–3.6× short) |
| Trailing edge and blunt base | Base drag, base flow, start of the wake | Chordwise spacing 0.1 % of local chord at the edge at M; 8 cells (9 points) across the base at VC (10, 14, 18 at C, M, F) | edges and base 15 % | Roadmap R-S.3, R-S.4 (laws 3, 6); DPW (8/12/16/24 cells), SPICES (≥ 8 at the fine level) | Built: 0.1 % c at the corners at M (0.169 % c at VC, 0.077 % c at F); 8 base cells at VC (10, 14, 18 at C, M, F). First approach: 8 at level C (10, 14, 18 at M, F, FF) |
| Panel breaks b1, b2 | Local suction peak, jump in the spanwise loading, slope break of the loft | A mesh station exactly on every break; spanwise growth ≤ 1.3 away from it. Station count (Stage 2, decisions 72, 77): gap 0.25 × local chord at M, at least 12 gaps per panel at M, growth 1.2 at VC | spanwise 15 % | Fix 3 (done in Stage 2); primer Track 2 (spanwise law with anchors); station count: law 8, our starting values | Built: a station exactly on every loft station (b0–b3; since 7 Nov there is no trailing-edge switch station); growth 1.2 (checked 1.3) |
| Tip and tip cap | Smallest chord and Re, first stall on aft sweep, birth of the vortex | Stations squeezed toward the tip so the last gap equals the cap's first cell; cap first cell = the tip station's first cell (refuse above 3×); outboard blocks 1.5 root chords beyond the tip, growth ≤ 1.15 | spanwise 15 % | Roadmap R-S.1, R-V.3, R-V.5 (laws 9–12) | Built: the last station gap = the tip first wall cell s0 (y⁺ = 1 at the tip Re). Tying the cap's first cell to it is a volume item (Stage 3). With C-H (decided 6 Nov, decision 73) the outboard blocks must also resolve the tip vortex |
| Near wake, trailing edge to 2 chords | Wake sheet (velocity deficit), base flow, start of roll-up | First plan (overset; replaced by C-H on 6 Nov, kept as a fallback): wake box with cells of 0.0075 c (about 20 across the wake), tall and tilted to hold the wake from −5° to post-stall; starts inside the near-body mesh. Now (decision 73, 6 Nov): one matched C-H mesh for both solvers (SU2 has no overset), with the wake band sized for the whole angle range; its wake lines add about +45 % (30–60 %) cells on the wing blocks (rough, not measured) | wake 15 % | Roadmap R-V.6 (laws 17, 18); Chan et al. 2002 | Stage 3, not built (S8 had no designed wake: O-mesh) |
| Far wake, 2 to 10 chords | Downwash, induced drag, wake convection | First plan (overset; replaced by C-H on 6 Nov, kept as a fallback): wake-box cells grow from 0.0075 c to the background size. With C-H (decision 73) the wake lines grow to the far field; Stage 3 sets the rule | wake 15 % | Roadmap R-V.6 | Stage 3, not built |
| Tip vortex core | Roll-up and path of the tip vortex | First plan (overset; replaced by C-H on 6 Nov, kept as a fallback): a tube with 15–20 near-cubic cells across the core, starting about 2 chords behind the tip (the vortex forms within about 1 chord, inside the near-body mesh). With C-H (decision 73) there is no tube: the outboard blocks must resolve the core | wake 15 % | Roadmap R-V.6 (law 19); primer section 05 | Stage 3, not built |
| Overlap between meshes | Nothing leaks: the wake and the boundary layer pass between grids cleanly | First plan (overset; replaced by C-H on 6 Nov, kept as a fallback): ≥ 5 cells from each mesh, cell-size ratio ≤ 1.5, no overlap inside the boundary layer or at the tip, 0 orphan cells. With C-H (decision 73) there is no overlap | — | Roadmap R-V.7 (law 21); Chan et al. 2002; Kenway et al. 2017 | Stage 3 (step M3), not built |
| Background and far field | Domain error | First plan (overset; replaced by C-H on 6 Nov, kept as a fallback): background 0.03 c around the wing, coarsening outward. With C-H (decision 73) the blocks grow outward to the far field from 80 chords (ladder 40 / 80 / 160; unchanged) | domain 10 % (of the total) | Roadmap R-V.6 (laws 15, 16); DPW about 100 chords | Stage 3, not built. S8 for reference: 40 chords; 40 → 60 moved drag 0.6–0.7 counts |
| Every zone together | Grid convergence (the error bar) | Every spacing in every mesh refined by one ratio r ≥ 1.3; distances fixed | — | Roadmap R-V.8 (law 23); Celik et al. 2008 | Surface (Stage 2): every spacing ÷ 1.3 per level (VC, C, M, F; decision 71). Over every set (Study 12): nose cells 1.295–1.304 per step, trailing edge 1.300, band and tip-gap cells 1.269–1.326. Exceptions are whole counts: the base cells 8 / 10 / 14 / 18 (1.25, 1.4, 1.29; decision 61) and the first station gap where the gaps per panel set it (1.12–1.39). Volume: Stage 3. (S8, first approach: the outboard blocks did not refine with the family.) |

Budget shares from Stage 0: chordwise 35 %, spanwise 15 %, wall-normal 20 %, edges and base 15 %, wake 15 % of the grid error; domain 10 % of the total. All values are starting values; the mesh studies (Grand Roadmap stage 4) confirm or replace them.

**Mesh cost (Stage 2).** First estimate (6 Nov): at the fine level median 15.2 M cells with the planned rules; 10.9 M with the lighter band (0.5 % c spacing where the local Re ≥ 4 × 10⁵), decided 6 Nov (decision 72). Measured on 8 Nov (Stage 2 Study 12, wing blocks): F 6.73 M median on the reference wings, 5.91 M over every set, largest 10.21 M, inside the owner's target of about 9–11 M. With C-H (decided 6 Nov, decision 73) the wake lines add a rough +30–60 % cells on the wing blocks (Stage 3 counts them).

**Conclusion.** Each mesh direction gets its share of the allowed grid error. These are starting rules; the mesh studies will confirm or replace them. The first rules cost more than the 9–11 M target; with the lighter band (decision 72) the F meshes measure 6.73 M median, 10.21 M largest (Stage 2 Study 12).

## Open decisions

decide needs your call. act a task with no choice left. Full history: `CFD_Automation/OPEN_DECISIONS.md` (items 67–82 are the 4–9 Nov decisions; 64 and 70 are decided and built, 7 Nov; the 6 Nov note 75 was wrong and is struck through).

**What changes (7 Nov 2026).** Decisions 64 (the nose) and 70 (similarity) left this list: they are decided and built. The trailing-edge floor question is gone (0.2 % c on every wing). New: the similarity checks C1–C4 and the flow dataset in similarity form. The Re levels are kept (you, 7 Nov). The 6 Nov note that the nose finding was overstated (item 75) was wrong.

### Study plan (Stage 0) (5 to decide)

- act **Re levels.** Changed (you, 8 Nov 2026): 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ on the mean chord (area / full span; were 1.5 × 10⁶ and 3 × 10⁶). 4 × 10⁶ takes in every cruise point of the Greek tactical programmes (LOTUS, Archytas, ACTUS); 1 × 10⁶ fills the old ×5 gap (check C4 on 2-D data, below). Same four levels and 8,000 solves. Real Class I–II wings fly at 1.22 × 10⁵ – 3.10 × 10⁶; the lowest level sits 18 % below the slowest real UAV: a margin (7 Nov). Still to run: check C4 with the solver.
- decide **Grid share 65 %.** Of the 3-count drag budget, 65 % goes to the mesh. Keep?
- decide **Iterative error.** ≤ 10 % of the budget is loose; Eça & Hoekstra ask 0.1–1 %. Tighten to 1 %?
- decide **Pitching-moment tolerance 0.002.** Our choice, no source. Keep?
- decide **Turbulence-model source.** Crivellini 2014 is weak support. Find a better source or call it our choice.
- decide **Stage 0 D5.** The Grand Roadmap lists a D5 (prior work, transition route, tunnel, cloud budget). Add it? Its transition route is now partly decided: transition must be captured (4 Nov 2026).
- act **Code-to-code checks.** BlendedNet / BlendedNet++ (FUN3D, SA, fully turbulent, Group 3 BWB, mesh error up to 5 % CL / 8 % CD) and SHIFT-Wing (transonic, CRM-based) are surrogate datasets, not verification data. Use BlendedNet++ only for a few same-model (SA) code-to-code points inside our full space; verify our own meshes by grid convergence (GCI) and NASA TMR cases.

### Flow conditions (3 to decide)

- decide **Transition and solver split.** Decided (4 Nov 2026): transition must be captured, with ADflow and SU2. Our ADflow build has SA only and no transition model, so transition comes from SU2 (SST + LM γ-Reθ). Proposal, pending: ADflow SA for all mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings first. The flow dataset (Flow dataset, first approach) puts the SA profile-drag error at a median +62 % over all focus wings and conditions, +69 % in level flight, within ±10 % in only 5 % of rows; below Re 10⁵ it changes sign. Logic check (1 Nov 2026): what a mesh must resolve depends on the model, so an SA mesh study alone does not qualify the mesh for γ-Reθ: build the mesh transition-ready from the start and repeat a reduced mesh study with γ-Reθ. Fix the SA inflow eddy viscosity (ν̃/ν about 3, Spalart & Rumsey 2007); with a low value SA shows an uncontrolled apparent transition (Crivellini & D'Alessandro 2014). First SU2 smoke test (4 Nov): SU2 ran SA and LM on one Stage 2 ring mesh (a section extruded between two symmetry planes, 97,920 cells, Re 3 × 10⁵, Mach 0.15, 4°); after about 370 iterations, not converged: SA CL 0.860, CD 0.0184; LM CL 0.908, CD 0.0137. It shows the mesh path works; no wing has been run.
- decide **Mach cap.** The Mach scope extends toward 0.5, with no supersonic flow (decided 4 Nov 2026); the cap is open. Under similarity the CFD runs at Mach 0.1 with a Prandtl–Glauert correction (check C2: Mach 0.05 / 0.1 / 0.2; if it fails, Mach becomes an input). The section tables and the flow dataset stop at Mach 0.2. Recommendation (pending): core data at Mach ≤ 0.2 now, Mach 0.3–0.5 later; at Mach 0.5 the angles would be capped near 4° by a supersonic-pocket gate.
- decide **Fast-UAV family.** Proposal, pending: Mach 0.3–0.5 needs a fast-UAV family in Stage 1, with real fast UAVs, thinner sections and section tables up to Mach 0.5. Today fast wings such as the Vindicator and the CPJ 100-LE are left out as 'outside phase 1'.
- act **Data for the new angle range.** Angles now run from −5° to post-stall, plus a separate post-stall study (decided 6 Nov 2026; Stage 0 had 0 / 4 / 8° plus 12° for the nose and wake studies). Missing here: the flow dataset covers root angles 0–10°; the section tables reach −10° and stop at 14°, so stall is never reached.
- done **Transition bands at the Re levels.** Decided (you, 7 Nov 2026; Stage 2 decision 74, option A): the lower band runs 0–100 % c. It costs no cells (one node list for both sides). The refine map at the four Re levels (7 Nov) finds it holds every strip at every level from −5° to 8°. New finding: at low Re the upper transition sits past 85 % c (at Re 10⁵ only 0–31 % of the strips fit 0–85 % c; at −5° the median is 88–100 % c). The built mesh already has about band-size cells to 100 % c on both sides (at F within 0.2 % of the band cell). Writing the upper band as 0–100 % c: decided by you on 8 Nov, built and screened (Stage 2 Study 12). On the 80 reference builds it keeps the counts at VC and adds 2 ring nodes on 42 at F (+0.4 % cells, median), as checked before; on every set it adds 2 ring nodes on VC 44 of 782 and F 383 of 782 meshes, cells at most +1.1 %.
- done **Volume mesh topology.** Decided (you, 6 Nov 2026; decision 73), built in Stage 3: one matched C-H multiblock mesh for both solvers instead of the overset wake box, vortex tube, overlap and background boxes, because SU2 has no overset. The wake band is sized for the whole angle range, the outboard blocks must resolve the tip vortex, and the far field stays at 80 c. Rough cost: the C-H wake lines add about +45 % (30–60 %) cells on the wing blocks (not measured).

### Flow maps (4 to decide)

- act **Sweep and aspect ratio stay in every set.** The 2-D strips do not use sweep or aspect ratio, so the sensitivity study cannot rank them; their low scores mean 'not modelled'. Keep both fully sampled in every CFD and ML set, and justify similarity scaling by dimensional analysis, not by the sensitivity result.
- decide **The SA rule.** The tool proposes SA when fully turbulent SA changes the profile drag by under 10 %, the upper surface turns turbulent near the nose (mean laminar run under 20 % chord; a small drag error with a long laminar run is a coincidence of two different flows) and no strip is below Re 10⁵. Both thresholds are our choice. Tie the first to the drag budget instead (the error in counts)?
- decide **N<sub>crit</sub> of the tool.** Default 9 (quiet air, as in flight at altitude). Low-level flight in gusty air is nearer 5–7; the check shows N<sub>crit</sub> 5 changes the SA error by −11 points. Keep 9 and show 5 as a band? Similarity (decided 6 Nov, built 7 Nov) fixes Tu 0.07 % (N<sub>crit</sub> 9) for the CFD.
- decide **Level-flight band.** First approach only: a grid point counted as level flight when its wing loading was within × / ÷ 2 of the fit to 37 real wings of the same full span (35 of them are). At unit mean chord a wing has no full span in metres and no wing loading. Drop the flag, or keep it only with a real size given per case?
- decide **Flow dataset in similarity form.** The Stage 1 flow dataset was made at real size and real speed (first approach, 30 Oct–2 Nov) and is not rebuilt. In similarity form each shape would run at the four Re levels on the mean chord, not at speeds and altitudes. Redo it at the Re levels, or let the 3-D CFD data replace it?
- act **Checks of the flow results.** Mike, 2 Nov 2026: no check is needed before the mesh stage; the mesh rules come from ranges, which the checks would not move. Since then the ranges have moved (angles −5° to post-stall, Mach toward 0.5: see Flow conditions). Needed before the paper quotes flow numbers: SU2 SST + LM runs (proposal, pending: on about 20 % of the wings first, BWB centre body first), the first runs of the mesh stage; so far only a smoke test on one ring mesh has run (see Transition and solver split). Only if the paper states SA's error as a number: 2-D SA against tripped XFOIL at Re 10⁵, 3 × 10⁵ and 1.5 × 10⁶ (about 1 day). Optional: retry the failed XFOIL points, a hinge-line case, a vortex-lattice spanwise loading, a source for the crossflow threshold, E387 against wind-tunnel data.
- done **Raw XFOIL data.** Done (9 Nov 2026): the raw XFOIL sweeps are in git as `data/section_cache.tar.gz` (2,752 sweeps, 1.4 MB). Unpacked, `tables --assemble` rebuilds the 46 section tables exactly (checked 9 Nov), so no 40-minute XFOIL rebuild is needed. The section tables were rebuilt on the fixed nose on 7 Nov.

### Geometry (2 to decide)

- act **Similarity checks C1–C4.** Similarity is built (7 Nov). Its four CFD checks are still to run: C1 scale (mean chord 0.3 m against 1 m), C2 Mach (0.05 / 0.1 / 0.2; CL and CM after Prandtl–Glauert), C3 trailing edge (0.1 / 0.2 / 0.3 % c and the real floor 0.42 % c), C4 Re levels (interpolation; done on 2-D data on 8 Nov, which added 1 × 10⁶). Limits: Re does not carry roughness or air turbulence; small real wings have thicker trailing edges.
- decide **Full-space edges.** At unit mean chord the full space reaches aspect ratio 20 and root chords up to 4.90 mean chords (a BWB corner), so at the top level the local Re reaches 2.0 × 10⁷ at that root; at the lowest level the smallest tip (0.055 mean chords) runs at 5.5 × 10³. The section tables cover 1.5 × 10⁴ – 6 × 10⁶. Keep, or narrow the full chord ratios?
- decide **Airfoil search order.** Project folder → AERIS database → NACA formula; of 2,183 files, 23 cannot be read (not unit chord) and the nose gate refuses 14. Keep?
- done **pyGeo run.** The nose is decided (64) and similarity is built (70). Every geometry hash changed on 7 Nov, and the sets were rebuilt with the numpy loft (722 of 722 built). pyGeo run on your machine (8 Nov): pyGeo tests 24 of 24 (pyGeo and the numpy loft agree within 10⁻⁶ chord on the 7 published wings), Stage 1 tests 204 (1 skipped), `build --all` with pyGeo 722 of 722, with the same input hashes and pass/fail as the numpy loft (the manifests now say pygeo); the Stage 2 meshes of the 20 reference wings on pyGeo equal the numpy ones (VC, old levels: every check value within 6 × 10⁻¹⁰; new levels, VC and F: the same ring nodes and stations, 80 of 80 each). One label differed: BWB corner1 \#8 was cranked with pyGeo only (its sweep changes by exactly 5°, the kink threshold). Fixed on 8 Nov (decision 79): every input hash changed, the surfaces did not; the pyGeo `build --all` ran again on 11 Nov after the label fix: 722 of 722, the same input hashes, pass flags and labels as the numpy build; Stage 1 tests 203, 3 XFOIL tests skipped; commit de64aa57. Tests: 181 pass, 13 skipped here (12 need pyGeo, 1 needs gmsh; 11 Nov 2026); on Mike's machine with pyGeo and gmsh 203 pass, 3 skipped (XFOIL not installed there; 11 Nov). Stage 2 has screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (every set at VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels), and on 8 Nov every set at every level: 3,128 of 3,128, with no nose repair (one factor per family, Stage 2 decision 80), with the numpy loft.

### Sources (0 to decide)

- act **Second-hand values.** Raymer's taper 0.4, washout 3° and 0° c/4 sweep come from a course page; PUL-10 and the flying-wing MAV were read by the agent only. Check in print.
- act **AUTh BWB papers.** Airfoils and station chords of their BWBs are in paywalled papers (AST 2018, AST 2021, AIAA 2020/2022, ICUAS 2020). Patras library or the authors.
- act **Essari 2015 data.** Hermes 450, Ranger, Seeker, Shadow 600 areas cite unread Jane's-style data; the Hermes 450 entry is inconsistent. Confirm with Jane's.
- act **Database rows (NTNU, CNAS).** Added 31 Oct 2026: 7 NTNU rows with an aspect ratio (set ranges) and 45 rows with only a full span. Families (tailless or conventional) are from photos; aspect ratios and speeds are as the databases list them. Some look wrong (RQ-7A cruise 58 m/s; Aludra MK1 chord). Check the rows you will quote.
- act **Tailless Class II areas.** Fury, Albatroz, Shahed 191 list only a full span; the RX-3 is the one tailless Class II with an area.

### Published wings (4 to decide)

- decide **BlendedNet twist and dihedral.** Set to zero because neither paper states them. Accept?
- decide **Which published wing first.** RIBES is the only in-regime case, and it is tripped at 1.4 % chord, so it checks fully turbulent RANS only: no published case here checks transition (candidate: the E387 wind-tunnel data). M6 and CRM are transonic, and the scope has no supersonic flow (decided 4 Nov 2026): shape and mesh checks only.
- decide **NASA CRM.** Four stations and stand-in sections: a shape check only, or add a many-station mode? With no supersonic flow in the scope it cannot be a validation case.
- decide **RIBES trailing edge.** Fitted section 0.26 %, model 0.38–0.66 %. Rebuild before any drag comparison?
- act **Outside proof.** Only the M6 is checked against its own CAD (needs gmsh; last run 2 Nov, before the two changes). BlendedNet, CRM, RIBES need their surface files; NACA 25118 edge needs a BlendedNet STEP.

### Paper (1 to decide)

- decide **Closest prior work.** Pliakos et al. 2025 (AUTh) automate OpenVSP → ANSA → Fluent for UAV wings (2 panels, M6 only, no transition). State what we add: 4 stations / 3 panels, full and focus spaces, refusing gates, Re bands with a transition check, open tools, similarity (one mesh family per shape), and a nose that follows the airfoil file at mesh scale.

## Design decisions

Every choice behind the generator, with its reason and what it rests on. Details: `Stage_1_geometry/decisions/` and `CFD_Automation/OPEN_DECISIONS.md`.

**What changes (7 Nov 2026).** Decisions 64 (the nose) and 70 (similarity) are decided and built. Rows marked Changed 7 Nov carry the new rule, with the first approach in grey. Three rows are gone and kept for the record: the 7 m cap, the wing class and the switch section. One row is new: the nose gate.

Basis: Your rule 21 · Source 3 · Measured 12 · Our choice 8 · Open needs your call · Changed 7 Nov · Gone 7 Nov kept for the record

| Decision | What we do | Why | Basis |
| --- | --- | --- | --- |
| Inputs | | | |
| D1One generator, one YAML | `wing_type`: a type (`bwb | flying_wing | cranked | tapered`), a family (`tailless | conventional`: its two types) or `mixed` (all four); shares equal (1/4 each). | One design space and one contract. Equal shares keep a mixed set from leaning to one type (decided 29 Oct 2026). | Your rule |
| D2Two families, two types each | Every wing is first **tailless** or **conventional**. A tailless wing must trim itself (reflexed sections, sweep with washout); a conventional wing does not, because the aircraft trims it elsewhere. Tailless: `bwb` (centre body, strong taper, cranked) or `flying_wing` (straight edges, moderate taper, swept). Conventional: `cranked` (constant-chord centre, tapered outer panels) or `tapered` (straight edges, rectangular at taper 1). | Your rule (31 Oct 2026). The family is an input (from the type or the user): whether the wing must trim itself is a property of the aircraft, so it cannot be measured on the wing. Inside a family our rules decide the type: tailless → bwb when the root chord is at least 2.2 × the outer-half mean chord (and at least half the semi-span), else flying_wing; conventional → cranked when the leading edge or the chord breaks (a kink), else tapered. The rules use ratios, so they work the same at unit mean chord. On the focus training sets of 7 Nov the rules return the drawn type for 100 % of flying-wing, cranked and tapered wings and 85 % of BWB wings (15 slim BWBs read as flying wings; 14 before 7 Nov). | Your rule |
| D3Span words | **Full span b** = tip to tip, both halves. **Semi-span S = b / 2** = root to one tip: the half wing we build, mesh and mirror at y = 0. `semi_span_m` is always S. At unit mean chord b equals the aspect ratio (in mean chords). Every table and figure says which one. | Your rule (31 Oct 2026): never write 'span' without saying which. | Your rule |
| D4No full-span cap (was: focus ends at b = 7 m) Gone 7 Nov | None since 7 Nov 2026. At unit mean chord the full span is the aspect ratio, and the aspect ratio has its own range, so the cap went with decision 70. The focus sets keep the same draw: a Latin hypercube of 200 rows, the first 100 kept. So 99 / 90 / 91 / 88 of the 100 focus shapes stay the same (BWB / flying wing / cranked / tapered; the cap had chosen by root chord). First approach (31 Oct–6 Nov): `focus: max_full_span_m: 7.0`; the focus sets kept only wings with full span ≤ 7 m, in draw order. | Your rule (31 Oct 2026) for wings at real size; similarity (6 Nov) made it meaningless. Then: 32 of 34 real wings with an area were in the focus space (Hermes 450, 10.5 m, and Götten UAV 9, 8.7 m, only in the full space). Cost now: a focus set is the first 100 of 200 rows, so its strata are not exactly balanced. | Your rule |
| D5Same 17 variables for every type Changed 7 Nov | Each type samples some and derives the rest (see Inputs and derived): 16 sampled for BWB and cranked, 12 for tapered and flying wing. The root chord left the vector on 7 Nov 2026 (decision 70: 18 → 17 names; 17 / 13 sampled before). Its hypercube column is still drawn and dropped, so the same seeds give the same shapes. | One vector shape for sampling, hashing and ML. | Our choice |
| D6Everything varies | A value is fixed only through `pinned:`. | A study may pin; the default never does. | Your rule |
| D7Size: none, every wing at unit mean chord Changed 7 Nov | `span_mode: aspect_ratio` for every type. Every wing is built at **unit mean chord**: mean chord c̄ = area / full span = 1 (the geometric mean chord, not the MAC). So the aspect ratio is sampled, the semi-span is S = AR / 2 and the root chord is 1 / K (K = mean chord / root chord). Lengths are in mean chords. Size enters only through the Re on the mean chord, an input of each solve (the Stage 0 levels). Mach 0.1 with a Prandtl–Glauert correction on CL and CM is on the solver side. First approach (29 Oct–6 Nov): the root chord was sampled in metres and S = AR · c<sub>root</sub> · K / 2. | Decided 6 Nov 2026 (you), built 7 Nov 2026 (decision 70). One mesh family per shape then serves every size: about 5 × fewer solves (8,000, not 42,000). Drawing the aspect ratio (not the semi-span) still keeps every wing inside the real range by construction, with no refusals (decided 29 Oct 2026). | Your rule |
| D8Chord law | `stations`: c2, c3, c4 as fractions of the root (BWB). `per_panel`: each panel's own taper, at most 1 (cranked). `linear_taper`: one taper, c2 and c3 follow (tapered, flying wing). | Before, 46 of 100 conventional wings got wider toward the tip. With per-panel ratios no chord grows outboard, and the Latin hypercube stays intact. | Your rule |
| D9Sweep law | `panels`: one sweep per panel. `one`: sweep2 = sweep3 = sweep1 (tapered, flying wing). | Straight leading edge for straight-edged wings. Variables a law computes need no range. | Your rule |
| D10Aspect ratios and the Re range from real wings Changed 7 Nov | Aspect ratio: BWB 3–9; flying wing 3–13; conventional (cranked, tapered) 4.5–16.5. Since 7 Nov the real wings set only the aspect ratios and the Re range. Real Class I–II wings fly at Re 1.22 × 10⁵ – 3.10 × 10⁶ on the mean chord (area / full span); the levels 1 × 10⁵ – 4 × 10⁶ cover them (1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ since 8 Nov), and 1 × 10⁵ sits 18 % below the slowest real UAV (kept as a margin: you, 7 Nov 2026). The Greek tactical BWBs (LOTUS, Archytas; 8 Nov) cruise at 1.4–3.7 × 10⁶. First approach: root chord BWB 0.40–1.80 m; cranked and tapered 0.13–0.75 m; flying wing 0.25–1.05 m. | The aspect ratio has no size, so the real wings still bound it: tailless 2.9–12.4 (ScanEagle), conventional 4.9–16.0. First approach (30 Oct–6 Nov): all 34 real wings with a published area had a generated wing within 10 % in full span and mean chord, and all 112 real full spans were inside. At unit mean chord that check compares real wings with wings of a 1 m mean chord, so it means nothing now (see Real wings). | Measured |
| D11Cranked differs from tapered | Cranked focus = constant-chord centre and tapered outer panels: inner chord 0.95–1, middle 0.80–1, outer 0.50–0.85 of the chord inboard; sweep −3–3° inner, −5–10° middle, 0–15° outer. Full space unchanged. | Your remark (30 Oct 2026): the two types looked alike, because the old per-panel ratios (0.85/0.75/0.65–1) made mostly straight-tapered wings with faint breaks. The layout follows Class II UAVs like Hermes 450 and Heron (from photos; no published chord table), so it is our choice. | Our choice |
| D12Shape ranges from sources | Every range has its basis in the Why this range column and in `decisions/shape_ranges.md`. Changed on 29 Oct 2026: conventional sweep −5° to +15° (was −10° to +20°); conventional washout at most 5° (was 7°); dihedral 0–5° for every type (Raymer); flying-wing taper 0.3–0.9 and sweep 10–40°; BWB tip down to 0.06, first sweep from 15°. | Each range now rests on a design rule (Raymer) or on a published small UAV (BWB: Wang & Zhou 2022, Suewatanakul 2022, Lehmkuehler 2012, Hainline 2017; flying wing: Milenković-Babić 2024, Panknin, PUL-10, a flying-wing MAV). Layout shares (b3, split) remain our choice. BlendedNet is a larger Group 3 BWB and is not used for the ranges. | Source |
| D13Two spaces: full and focus | Per type, `ranges` + `airfoils` = the focus space (realistic, suggested); `full_ranges` + `full_airfoils` = the full space (everything supported). The focus box must lie inside the full box, and each suggested section must be a full candidate; the YAML is refused otherwise. | Your rule (30 Oct 2026): design everything, but put the wings and the simulations densely where the real wings are. Full bounds are our choice: the widest value in any source, rounded out (e.g. BlendedNet sweeps 60°, Prandtl-D washout 10°). | Your rule |
| D14No wing class (was: class I \| II) Gone 7 Nov | None since 7 Nov 2026. A config that still has `wing_class`, `max_full_span_m` or `floor_m` is refused, so an old file cannot be misread. First approach: `wing_class: I | II` set the trailing-edge floor (0.5 mm Class I, 1.0 mm Class II). | A wing without size has no millimetres (decision 70). The trailing edge is now 0.2 % of the local chord on every wing (see Trailing edge). | Your rule |
| Planform | | | |
| D15Exact straight panels | Leading and trailing edges are straight lines through b0–b3. Chords and sweeps equal the vector exactly. | The old AERIS spline put the b2 chord up to 20 % off; a 12°/6°/6° wing came out 7.9°/7.9°/6.5°. | Measured |
| D16Signed sweep | Leading-edge sweep, positive aft. Forward sweep is allowed by the ranges, not blocked by code. | Conventional wings need it. | Your rule |
| D17No curved BWB centre body | Not in this stage. To add later with a check that rejects wavy edges. | Straight panels first. So today's BWB is a cranked tailless wing with a long root chord. | Our choice |
| Sections, twist, dihedral | | | |
| D18Vertical sections; root in y = 0 | Every section is parallel to the symmetry plane and only twisted about its leading edge. The validity gate refuses a wing whose root leaves y = 0 by more than 1e-9 mean chords (1e-9 m on the real-size wings before 7 Nov), or any point that crosses y = 0. | The two mirrored halves then meet exactly in the root section and never cross. AERIS (and its AVL path) rolled the root section with the first panel's dihedral, so the halves crossed and the root dihedral had to be pinned at zero. pyGeo only receives our section points, never a dihedral angle. Cost: on a panel with dihedral Γ the true thickness is cos Γ smaller (1.5 % at 10°). | Your rule |
| D19One dihedral per panel | Inputs `dihedral_p1, p2, p3`. Station heights: z<sub>i</sub> = Σ tan(Γ<sub>panel</sub>) · f<sub>panel</sub> S (the panel's share of the semi-span). | Four station values gave only three panel slopes, so one input did nothing (\[0, 3, 3, 6\], \[3, 0, 6, 3\] and \[1.5, 1.5, 4.5, 4.5\] built the same wing). The gate now checks each panel dihedral against the vector. Fixed 29 Oct 2026. | Your rule |
| D20Twist | Exact at the four stations; between them it follows the straight panel. | Straight panels and linear twist cannot both hold. Difference 0.1–0.3 % of chord at the trailing edge. | Measured |
| D21Aspect ratio exact with twist | The mean chord K counts the true chord of a straight panel: where the twist changes, the chord turns and is a little shorter mid-panel (0.6 % for a 13° change). K = Σ f<sub>i</sub> ∫ \|chord vector\| dt, 32-point Gauss. So the built wing has exactly unit mean chord and the aspect ratio asked for. | Found by the full-space sets: with washout up to 12°, 4 wings missed their aspect ratio by 0.11–0.24 % (gate limit 0.1 %). Two causes: K assumed a linear chord, and the extra section at the trailing-edge switch took the linear chord and twist, so it sat off the straight panel. Both fixed 30 Oct 2026 (the switch section went with the floors on 7 Nov). Worst aspect-ratio error on the 722 wings built on 7 Nov: 0.00004 %. | Measured |
| Airfoils | | | |
| D22Supported vs suggested sections | Supported: any section in the AERIS database or in `Stage_1_geometry/airfoils/` that reads and passes the nose gate, or a NACA 4/5-digit formula. Suggested: the per-type list from papers (focus space). The full space draws from every sourced section, on any type. | Your rule (30 Oct 2026). A suggestion must have a source; support needs only a readable file with a round nose. | Your rule |
| D23Any airfoil by name Open | Search order: `Stage_1_geometry/airfoils/` → AERIS database → NACA 4/5-digit formula. Of the 2,183 files on the search path (2,176 database, 7 local), 2,160 read and 2,146 build (23 are not unit chord; the nose gate refuses 14). A station may list candidates; the sampler draws them evenly. One wing may carry its own four names. | BlendedNet (NACA 25118), M6, RIBES and CRM need sections outside the default list. | Our choice |
| D24Default sections | BWB: MH 104 body (15 %), MH 61 wing (10 %). Cranked and tapered: NACA 4415, 4415, 4412, 4412. Flying wing: MH 60 inboard, MH 45 outboard. | BWB pair from a small BWB UAV (Suewatanakul et al. 2022). The old AERIS MH 91 is a paraglider section and NLF(1)-1015 a HALE section (Re 0.7–2 × 10⁶), so both were dropped. NACA 4415 flies on the Pioneer and the Shadow 200 (Lednicer). MH 45 and MH 60 are Hepperle's tailless sections; MH 60 suits Re ≥ 1.5 × 10⁵ (root), MH 45 lower Re (tip). Changed 29 Oct 2026. | Source |
| D25One way to read every file Changed 7 Nov | One cubic spline through the raw points (chord-length parameter, natural ends at the trailing edge). Leading edge = the apex of that spline: its point farthest from the trailing-edge midpoint. Both sides are sampled from the same spline on cosine x, **201 points per side** (401 per section); unit chord. | Changed 7 Nov 2026 (decision 64, see Nose study). The old rule put the leading edge at the farthest *raw point* and resampled each side in √x with a square tangent (PCHIP, 101 points per side). Measured along the arc, that made a curvature spike on one side of the nose and a flat spot on the other, between the raw points, and the built nose failed a 5 % turning-per-cell test on all ten suggested airfoils (NACA 4415: a 0.18 % c nose cell turned 9.47°; the true shape turns 4.31°). The new rule passes on all ten (worst −3.9 %) and on 95.6 % of the database files (old rule 21.0 %). | Measured |
| D26Typo points dropped | A single point that spikes off a smooth line is removed (18 database files, e.g. sc20412 at x/c 0.73). Since 7 Nov this filter runs on the raw points, before the spline. | One bad point would put a bump in the surface. Kept by your decision on 29 Oct 2026; each dropped point is logged. | Your rule |
| D27Nose gate Changed 7 Nov | A section is refused when the cubic spline in s = √x that the loft puts through its points curves back harder than −1000/c anywhere within 3 % c of arc from its leading edge, on either side. The refusal names the side, the place and the value. | Added 7 Nov 2026 (decision 64). A nose that folds back would put a tiny loop in the surface. On the database the gate refuses 14 files (very sharp or flat-faced noses; none is used by a config); no other file changes. A round nose is far from the limit: its smallest curvature is +1.9/c to +19.9/c on the ten study airfoils and the 14 named sections. | Measured |
| Trailing edge | | | |
| D28Thickness rule Changed 7 Nov | **0.2 % of the local chord on every wing** (decision 70, 7 Nov 2026). First approach: Class I max(0.5 mm, 0.2 % c), Class II max(1.0 mm, 0.2 % c). The edges then ran from 0.20 to 4.17 % c, and 370 of the 730 wings had at least one edge set by a floor. | Real wings are blunt. In AERIS, 0.5 % carried about a fifth of the pressure drag; 0.2 % with 8 base cells carried 2–4 %. 0.2 % is also pyGeo's default. A wing without size has no mm floor. Check C3 (CFD, to come): 0.1 / 0.2 / 0.3 % c, and the real floor of small wings, about 0.42 % c. | Measured |
| D29Made in the generator | On the 2-D airfoil, before the loft. Not in the mesher. | AVL, CFD and CAD see one wing. The AERIS mesher made 4.3 mm at one root, 2.4 times the rule, and moved lift 11–30 counts. | Measured |
| D30How it opens | pyGeo's method: linear ramp from x/c = 0.90 to the edge, half up, half down. Camber line unchanged. | Same as `readAirfoilFile(bluntTe=True, bluntThickness=0.002, bluntTaperRange=0.1)`. Replaced the uncited 65 % start in v0.4. Cost: a 0.6° slope change at 90 % chord. | Source |
| D31The rule wins over the file | A file with its own blunt edge is set to the rule (NACA 4415: 0.32 % → rule). Published wings keep theirs (`as_is`). | Sampled wings follow one rule; copies of real wings stay real. | Our choice |
| D32No switch section (was: a section at the switch) Gone 7 Nov | None since 7 Nov 2026. Between two sections the ruled loft blends the chord and the edge gap linearly, so a fraction of the chord holds all along the semi-span, twist or not. First approach: where the chord equalled 0.25 m (Class I) or 0.5 m (Class II), a section was added, so the floor held between the stations. | It existed only because of the mm floors. | Our choice |
| Loft (the surface the mesher reads) | | | |
| D33Straight panels: kSpan = 2 | Sections only at b0–b3 (no switch sections since 7 Nov 2026). | kSpan 3 cut the corners at panel breaks by up to 4.8 % of chord; kSpan 2 is exact. It leaves a sharp kink at b1 and b2; the Stage 2 surface mesher puts a station exactly on each (fix 3, done). | Measured |
| D34Built with pySpline, one parameter s = √(x/c) | Same construction as pyGeo's `liftingSurface`, held in a pyGeo object. | `liftingSurface` split upper and lower 0.2–0.5 % of chord away from the nose. Here the split is exact and u = x/c on every station. | Measured |
| D35Ask, never interpolate | The mesher asks `upper(u, v)` and `lower(u, v)`; a 401-point table maps v to the position along the semi-span. | In AERIS, straight lines between stored sections missed the surface by up to 7.25 % of chord (ADR-0015). | Measured |
| D36Tip | Flat and open (`tip='none'`). | Rounded tips are a later study. | Our choice |
| D37Two backends, one export | pyGeo (production, IGES) and numpy (same surface, no pyGeo). No STEP: pyGeo has no STEP writer. | Tests and pictures run anywhere. | Our choice |
| Measure, label, hash | | | |
| D38Measured on the loft | Chord, twist, LE position, sweep, dihedral, area, semi-span and full span, MAC, AR, thickness, trailing-edge thickness → `measured.json`. Lengths in mean chords (a key ending in `_m` is metres for a 1 m mean chord). The gate checks chords, sweeps, twists, panel dihedrals and the aspect ratio against the vector. | Later stages and any ML model use the measured wing; the vector is only its label. | Your rule |
| D39Labels by rule Changed 7 Nov | First the family (from the input) and the type (by the rules above), then shape labels: swept, cranked, rectangular, straight-tapered, washout, dihedral, aspect ratio. BWB threshold 2.2. A value exactly at a threshold gets the label (tolerance 1e-9 on every rule since 8 Nov 2026, decision 79; the aspect ratio 10⁻⁶ relative, above the area error). | Whether the wing must trim itself is a property of the aircraft, so it cannot be measured on the wing; the family comes from the input (the type or the user). Before 29 Oct 2026 every tailless wing without a centre body was called 'conventional'. The tolerance: 35 wings at exactly 1.0° washout had lost the washout label by rounding. Checked on 20 hand-labelled wings and a flying-wing test. | Your rule |
| D40Hash from the code itself | sha256 of the vector (with its four section names), the type's laws and pinned values (not its ranges), the trailing-edge rule, the airfoil coordinates and the content of every geometry source file. | Any code change changes every input hash, so stored meshes and results are never reused for a wing the code builds differently. A version string set by hand could be forgotten. Fixed 29 Oct 2026. Cost: a pure rename changes every hash too. On 7 Nov 2026 every hash changed again (similarity and the nose rule); the sets were rebuilt with the numpy loft, and on 8 Nov with pyGeo on your machine (722 of 722, the same input hashes). Stage 2 mesh names carry the wing hash (`mesh_<level>_<wing_hash8>_re<Re>`). | Your rule |
| Sets | | | |
| D41Seven sets per type, two spaces Changed 7 Nov | Focus: training 100 (a Latin hypercube of 200 rows, the first 100 kept; seeds 1001–1004), reference 5 (by rule), hold-out 10 (20 rows, the first 10 kept; seeds 2001–2004). Full: training 40 (seeds 1101–1104), hold-out 5 (seeds 2101–2104), corner 1 (each free variable at each full bound: 32 or 24 wings; 34 or 26 before 7 Nov, when the root chord had its two corners) and corner 2 (every pair at all four low/high combinations: 8 or 7). Files: `training_focus`, `reference`, `holdout_focus`, `training_full`, `holdout_full`, `corner1`, `corner2`. | Dense where real wings are, sparse over everything we support; the corners test the edges of what we claim. The hold-outs are the honest tests (opened once on 9 Nov 2026 for the surface mesh, with the surface rules frozen: decision 83, Stage 2 Study 14). Decided 30 Oct 2026. On 7 Nov training_full, holdout_full and corner 2 kept their shapes. | Your rule |
| D42Failures stay in the list | A refused wing keeps its row with the gate and the reason. Corners are never nudged inside. | A failure marks the edge of the space. | Your rule |
| D43Hold-out is never built here | Only the vectors are saved. | It is opened once, after the workflow is frozen. | Your rule |
| D44Reference wings spread well Changed 7 Nov | Rules: mid-range; lowest and highest aspect ratio (before 7 Nov: smallest and largest area; at unit mean chord the area is the aspect ratio); most sweep with the smallest tip (in mean chords); strongest washout. Coverage distance (lower is better) BWB 1.44, Flying wing 1.41, Cranked 1.45, Tapered 1.21, against a median of 1.78 / 1.56 / 1.76 / 1.52 for 1,000 random sets of five. | Five wings must stand for the whole set. On 7 Nov 13 of the 20 reference wings became new picks; 7 are kept (the 4 mid-range wings and 3 of the 4 strongest-washout wings; the new BWB washout pick was the old smallest-area pick). | Measured |

## Fixes: done and left

Done on 29 Oct 2026: the unrealistic conventional set (tapered type and per-panel chords), the dihedral input (three panel values) and the hash (from the code itself). Done on 2 Nov 2026 (fix 3): a mesh station on every break. The Stage 2 surface mesher puts a station exactly on every loft station, so its flat faces never cut a kink; 790 of 790 builds passed its 13 checks on the first-approach wings, and 3,128 of 3,128 on the 7 Nov wings (8 Nov, numpy loft). Done on 7 Nov 2026: the nose shape (decision 64), below. Fixed on 8 Nov: the label rules at a threshold (decision 79); every input hash changed, no surface did. Done on 11 Nov: the pyGeo `build --all` after that fix (722 of 722, the same input hashes, pass flags and labels).

1.  **Done (7 Nov 2026): the nose shape of the built sections (decision 64).**Measured along the arc with one curvature method, the old rule made a curvature spike on one side of the nose and a flat spot on the other, and the built nose failed the 5 % turning-per-cell test on all ten suggested airfoils. The new rule (leading edge at the apex of one cubic spline, both sides from that spline, 201 points per side) passes on all ten and on 95.6 % of the database; a nose gate refuses the 14 files whose nose folds back. See Nose study. Do: nothing left for the nose. The pyGeo `build --all` ran on your machine on 8 Nov: 722 of 722, and ran again on 11 Nov after the label fix: 722 of 722, the same input hashes, pass flags and labels as the numpy build; Stage 1 tests 203, 3 XFOIL tests skipped; commit de64aa57 (the manifests say pygeo).

## One wing, step by step

*\[Figure: Seven-step animation of one wing being built\]*

Seven steps: design vector, planform, sections, twist and dihedral, trailing edge, loft, measure-label-check. Example: a BWB with every variable at mid-range, at unit mean chord (lengths in mean chords).

**What changes (7 Nov 2026).** The GIF is redrawn at unit mean chord: 17 numbers (no root chord), lengths in mean chords, trailing edge 0.2 % of the local chord.

**Conclusion.** The same seven fixed steps make every wing, and two builds of the same vector give the same surface hash: the generator is repeatable.

## Real wings and the Reynolds number

Your rule (29 Oct 2026): take the sizes from real Class I and II UAVs, compute the Re they fly at, and if it does not reach 5 × 10⁶, lower the top Re level instead of stretching the wings. Data and links: `configs/real_uavs.yaml`; check: `scripts/real_uav_check.py`.

**What changes (7 Nov 2026).** The real wings now set the aspect ratios and the Re range only. Every generated wing is at unit mean chord, so the coverage in this section (a generated wing within 10 % in full span and mean chord, in metres) compares real wings with wings of a 1 m mean chord: it means nothing now. It is the first-approach check (30 Oct–6 Nov), kept as the record. `scripts/real_uav_check.py` still runs, but its coverage numbers in metres are meaningless, so it was not rerun. The Re of each real wing (on area / full span) still holds: 1.22 × 10⁵ – 3.10 × 10⁶, inside the four levels.

### Real wings fly at

Re 1.22 × 10⁵ – 3.10 × 10⁶

Lowest: EMT Aladin and Black Swift S0 cruising at 3,048 m. Highest: CTRM Aludra MK1 at its listed top speed, sea level (NTNU; 3.1 × 10⁶, at the top study level). Mean chord = wing area / full span.

### So the top Re level

5 × 10⁶ → 3 × 10⁶ → 4 × 10⁶

No wing of our families reaches 5 × 10⁶. Only the Sperwer (a delta, 6.0 × 10⁶) does; the Vindicator (a target drone above Mach 0.3) comes close (4.8 × 10⁶). Until 8 Nov the levels were 1 × 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶ (3 × 10⁶ was the RUAG Ranger's 2.74 × 10⁶ rounded up; the NTNU Aludra MK1 row since reaches 3.1 × 10⁶). Since 8 Nov (decision 78): 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶, so the Greek tactical UAVs are in (Greek tactical UAVs).

### Generator covered them (first approach)

focus 32 of 34, full 34 of 34 real wings (only in the full space: Elbit Hermes 450, Goetten UAV 9)

First approach (real size): in the full space each real wing with a published area had a generated wing within 10 % in full span and mean chord, and every Class I full span was inside (sourced and HCDI database). Focus space: BWB full span 0.6–7.0 m, mean chord 0.17–1.05 m; flying wing full span 0.6–7.0 m, mean chord 0.17–0.94 m; cranked full span 0.5–7.0 m, mean chord 0.10–0.72 m; tapered full span 0.5–7.0 m, mean chord 0.09–0.71 m. Now this check means nothing: every generated wing has a 1 m mean chord in it.

### Class II

Chords 0.54–0.78 m

13 Class II wings with an area set the aspect ratios and the Re range (first approach: the size ranges): Götten et al. 2021 (5; from images and three-views, about 10–15 %), Essari 2015 (4, Jane's-style: Hermes 450, Ranger, Seeker, Shadow 600), the NTNU RQ-7A Shadow and Aludra MK1 rows, the Pioneer (Bray 1991) and the tailless AUTh RX-3 (4.9 m²). AR 7.0–16. At top speed, where listed, Re 2.0–3.1 × 10⁶. Gap: the RX-3 is the only tailless Class II wing with an area.

<figure class="fig card">
<p><em>[Figure: First approach: real wings against generated wings at real size, full span and mean chord]</em></p>
</figure>

First approach (real size, before 7 Nov). Clouds: 2,000 generated wings per type (tailless panel: green BWB, brown flying wing; conventional panel: blue cranked, light blue tapered). Red: real wings with a published area or aspect ratio. Ticks on the full-span axis: real wings with only a full span listed (brown: sources and the NTNU / CNAS databases; violet: HCDI UAS database).

**Conclusion.** First approach: the generated clouds covered the real wings: in the focus space 32 of the 34 real wings with an area had a generated wing within 10 % in full span and mean chord, and the full space covered all 34. Now the generator has no size, so any real wing whose shape is in the box has a similar generated wing; what must cover the real wings is the Re range, and it does (1.22 × 10⁵ – 3.10 × 10⁶ inside the levels 10⁵ – 4 × 10⁶; 10⁵ – 3 × 10⁶ until 8 Nov).

<table class="wide" style="width:100%;">
<colgroup>
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
</colgroup>
<thead>
<tr class="header">
<th>Aircraft</th>
<th>Family</th>
<th>Class</th>
<th>Full span m</th>
<th>Area m²</th>
<th>Mean chord m</th>
<th>AR</th>
<th>Cruise / max m/s</th>
<th>Re low – high</th>
<th>MTOW kg</th>
<th>HCDI database</th>
<th>Use</th>
<th>Source (type)</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td class="what">AV RQ-12A Wasp AE</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">11.9 / 23.1</td>
<td class="num">—</td>
<td class="num">1.3</td>
<td class="num">—</td>
<td>full span only</td>
<td class="src"><a href="https://www.avinc.com/images/uploads/product_docs/Wasp_Datasheet_07192021.pdf">maker</a></td>
</tr>
<tr class="even">
<td class="what">Black Swift S0</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.39</td>
<td class="num">0.188</td>
<td class="num">0.136</td>
<td class="num">10.2</td>
<td class="num">17.0 / —</td>
<td class="num">1.2e5 – 1.6e5</td>
<td class="num">1.59</td>
<td class="num">—</td>
<td>sets AR, Re<br />
54.6 in; 292 in2</td>
<td class="src"><a href="https://techpartnerships.noaa.gov/wp-content/uploads/2024/01/VTOL-S0-Data-Sheet.pdf">maker</a></td>
</tr>
<tr class="odd">
<td class="what">AV RQ-11B Raven</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.40</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">8.9 / 22.5</td>
<td class="num">—</td>
<td class="num">1.9</td>
<td class="num">—</td>
<td>not used<br />
superseded by the NTNU row with AR; </td>
<td class="src"><a href="https://www.avinc.com/images/uploads/product_docs/Raven_Datasheet_07122021.pdf">maker</a></td>
</tr>
<tr class="even">
<td class="what">AV RQ-11B Raven (NTNU)</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.40</td>
<td class="num">0.327</td>
<td class="num">0.233</td>
<td class="num">6.0</td>
<td class="num">11.6 / 22.5</td>
<td class="num">1.4e5 – 3.6e5</td>
<td class="num">1.9</td>
<td class="num">—</td>
<td>sets AR, Re<br />
NTNU: AR 6, est. chord 0.22 m</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">L-3 Cutlass</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.40</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 43.6</td>
<td class="num">—</td>
<td class="num">6.8</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/cutlass/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">EMT Aladin (NTNU)</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.46</td>
<td class="num">0.266</td>
<td class="num">0.182</td>
<td class="num">8.0</td>
<td class="num">12.5 / 25.0</td>
<td class="num">1.2e5 – 3.1e5</td>
<td class="num">4</td>
<td class="num">—</td>
<td>sets AR, Re<br />
NTNU: AR 8, est. chord 0.18 m</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Raytheon Coyote</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.50</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">28.3 / 36.0</td>
<td class="num">—</td>
<td class="num">5.9</td>
<td class="num">—</td>
<td>full span only<br />
tube-launched, folding wing</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Topcon Sirius Pro</td>
<td>Conventional</td>
<td>I</td>
<td class="num">1.63</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">18.1 / —</td>
<td class="num">—</td>
<td class="num">2.7</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Bayraktar Mini UAV</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">30.9 / —</td>
<td class="num">—</td>
<td class="num">5</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Innocon Micro Falcon LE</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">18.0 / —</td>
<td class="num">—</td>
<td class="num">10</td>
<td class="num">—</td>
<td>full span only<br />
cruise 18-33.4 m/s (lowest)</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Elbit Skylark I-LE</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">7.5</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/elbit-skylark-micro/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Tekever AR4 Evo</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.10</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">15.0 / 15.0</td>
<td class="num">—</td>
<td class="num">4</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Aeromao Aeromapper Avem</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.14</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">16.7 / —</td>
<td class="num">—</td>
<td class="num">2</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Quantum Trinity F90+</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.39</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">17.0 / —</td>
<td class="num">—</td>
<td class="num">5</td>
<td class="num">—</td>
<td>full span only</td>
<td class="src"><a href="https://quantum-systems.com/wp-content/uploads/2023/01/QS_TrinityF90_Overview_220912.pdf">maker</a></td>
</tr>
<tr class="odd">
<td class="what">ST Aerospace Skyblade III</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.60</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">12.9 / 18.0</td>
<td class="num">—</td>
<td class="num">5</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Martin UAV Super Bat DA-50</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.60</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 33.3</td>
<td class="num">—</td>
<td class="num">21</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/super-bat-da-50-uav/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">AV RQ-20B Puma AE</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.80</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">10.3 / 23.1</td>
<td class="num">—</td>
<td class="num">6.3</td>
<td class="num">Class I (Mini)<br />
full span 2.8 m</td>
<td>not used<br />
superseded by the NTNU row with AR; 37-83 km/h envelope</td>
<td class="src"><a href="https://www.avinc.com/images/uploads/product_docs/PumaAE_Datasheet_Web_v1.2.pdf">maker</a></td>
</tr>
<tr class="even">
<td class="what">AV RQ-20 Puma 3AE (NTNU)</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.80</td>
<td class="num">1.06</td>
<td class="num">0.378</td>
<td class="num">7.4</td>
<td class="num">18.0 / 23.0</td>
<td class="num">3.6e5 – 6.0e5</td>
<td class="num">6.8</td>
<td class="num">—</td>
<td>sets AR, Re<br />
NTNU: AR 7.4, est. chord 0.38 m, SD7032</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Aerosonde (Beard &amp; McLain model)</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.90</td>
<td class="num">0.55</td>
<td class="num">0.190</td>
<td class="num">15.2</td>
<td class="num">25.0 / —</td>
<td class="num">2.5e5 – 3.3e5</td>
<td class="num">11</td>
<td class="num">—</td>
<td>not used<br />
textbook simulation model, not manufacturer data</td>
<td class="src"><a href="https://raw.githubusercontent.com/byu-magicc/mavsim_public/main/mavsim_python/parameters/aerosonde_parameters.py">model</a></td>
</tr>
<tr class="even">
<td class="what">AAI Aerosonde (NTNU)</td>
<td>Conventional</td>
<td>I</td>
<td class="num">2.95</td>
<td class="num">0.569</td>
<td class="num">0.193</td>
<td class="num">15.3</td>
<td class="num">31.0 / 41.0</td>
<td class="num">3.2e5 – 5.4e5</td>
<td class="num">25</td>
<td class="num">—</td>
<td>sets AR, Re<br />
NTNU: AR 15.3, est. chord 0.20 m, NACA 4415</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Sunbirds SB4 Phoenix</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.20</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">11.1 / —</td>
<td class="num">—</td>
<td class="num">3.5</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Yakovlev Pchela</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.25</td>
<td class="num">1.83</td>
<td class="num">0.563</td>
<td class="num">5.8</td>
<td class="num">33.4 / 49.9</td>
<td class="num">1.0e6 – 1.9e6</td>
<td class="num">138</td>
<td class="num">—</td>
<td>sets AR, Re<br />
Essari 2015 PhD (Univ. Belgrade) ch. 2, data 'from (1) &amp; (20)' (Jane's-style; refs not identified) §2.16; area printed '1.83 m3 (19.7 sq ft)': unit typo; 65 / 97 kt</td>
<td class="src"><a href="https://phaidrabg.bg.ac.rs/open/o:11738">thesis / report</a></td>
</tr>
<tr class="odd">
<td class="what">Penguin B</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.30</td>
<td class="num">0.79</td>
<td class="num">0.239</td>
<td class="num">13.8</td>
<td class="num">22.0 / 36.0</td>
<td class="num">2.8e5 – 5.9e5</td>
<td class="num">21.5</td>
<td class="num">—</td>
<td>sets AR, Re<br />
datasheet prints '0.79 m' (m2)</td>
<td class="src"><a href="https://www.unmannedsystemstechnology.com/wp-content/uploads/2014/11/Penguin-B-Datasheet.pdf">maker</a></td>
</tr>
<tr class="even">
<td class="what">Goetten UAV 1</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.30</td>
<td class="num">1</td>
<td class="num">0.303</td>
<td class="num">10.9</td>
<td class="num">22.2 / —</td>
<td class="num">3.6e5 – 4.6e5</td>
<td class="num">25</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 25 kg, payload 5 kg, loiter 22.2 m/s, AR 10.9, paper Re 0.5e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="odd">
<td class="what">Delair DT26M</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.30</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">15.8 / —</td>
<td class="num">—</td>
<td class="num">15</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">UAV Factory Penguin C</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.30</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 31.9</td>
<td class="num">—</td>
<td class="num">23</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/uav-fac/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Goetten UAV 2</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.60</td>
<td class="num">1.32</td>
<td class="num">0.367</td>
<td class="num">9.8</td>
<td class="num">27.8 / —</td>
<td class="num">5.5e5 – 7.0e5</td>
<td class="num">50</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 50 kg, payload 8-10 kg, loiter 27.8 m/s, AR 9.8, paper Re 0.6e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="even">
<td class="what">FlyTronic FlyEye</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.60</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 33.3</td>
<td class="num">—</td>
<td class="num">11</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/flytronic-flyeye/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">AAI Aerosonde Mk 4.7</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.60</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 41.1</td>
<td class="num">—</td>
<td class="num">36</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/aerosonde-aerosonde-mark-4-7/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Hydra Ehecatl S4</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.70</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">19.5 / 46.3</td>
<td class="num">—</td>
<td class="num">55</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Lockheed Martin Stalker XE</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.70</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">15.6 / 20.1</td>
<td class="num">—</td>
<td class="num">10.9</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Textron Aerosonde (fixed wing)</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.70</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">23.0 / —</td>
<td class="num">—</td>
<td class="num">45.5</td>
<td class="num">—</td>
<td>full span only<br />
cruise 23-33 m/s (lowest)</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">ST Aerospace Skyblade IV</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.70</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 41.1</td>
<td class="num">—</td>
<td class="num">70</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/skyblade-iv/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Developmental Sciences R-4D Sky Eye</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.71</td>
<td class="num">2.81</td>
<td class="num">0.756</td>
<td class="num">4.9</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td>sets AR, Re<br />
full-scale vehicle in the tunnel; mean aerodynamic chord 0.81 m; modified, armed</td>
<td class="src"><a href="https://ntrs.nasa.gov/api/citations/19790022980/downloads/19790022980.pdf">thesis / report</a></td>
</tr>
<tr class="odd">
<td class="what">AAI RQ-7A Shadow (NTNU)</td>
<td>Conventional</td>
<td>II</td>
<td class="num">3.90</td>
<td class="num">2.17</td>
<td class="num">0.557</td>
<td class="num">7.0</td>
<td class="num">58.0 / —</td>
<td class="num">1.7e6 – 2.2e6</td>
<td class="num">150</td>
<td class="num">—</td>
<td>sets AR, Re<br />
NTNU: AR 7, est. chord 0.55 m, NACA 4415; cruise 58 m/s as listed (looks like a top speed)</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Threod Stream C</td>
<td>Conventional</td>
<td>I</td>
<td class="num">3.90</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">22.0 / 36.0</td>
<td class="num">—</td>
<td class="num">40</td>
<td class="num">—</td>
<td>full span only<br />
cruise 22-28 m/s (lowest)</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">IAI Scout</td>
<td>Conventional</td>
<td>II</td>
<td class="num">4.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">159</td>
<td class="num">—</td>
<td>full span only<br />
final design full span (first design 3.2 m), IAI authors; other sources give 3.6 or 4.96 m</td>
<td class="src"><a href="https://icas.org/ICAS_ARCHIVE/ICAS2004/PAPERS/519.PDF">paper</a></td>
</tr>
<tr class="even">
<td class="what">Aeronautics Aerolight</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">25.6 / 51.4</td>
<td class="num">—</td>
<td class="num">40</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">BlueBird ThunderB</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">21.6 / 37.0</td>
<td class="num">—</td>
<td class="num">32</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Nostromo Yarara W</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">32.0 / 40.3</td>
<td class="num">—</td>
<td class="num">35</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">EMT Luna</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.17</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">19.0 / —</td>
<td class="num">—</td>
<td class="num">40</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Goetten UAV 3</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.20</td>
<td class="num">2.34</td>
<td class="num">0.557</td>
<td class="num">7.5</td>
<td class="num">36.1 / —</td>
<td class="num">1.1e6 – 1.4e6</td>
<td class="num">75</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 75 kg, payload 15-20 kg, loiter 36.1 m/s, AR 7.5, paper Re 1.4e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="odd">
<td class="what">Northrop Grumman Bat</td>
<td>Conventional</td>
<td>II</td>
<td class="num">4.26</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">33.4 / 47.3</td>
<td class="num">—</td>
<td class="num">159</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">AAI RQ-7B Shadow</td>
<td>Conventional</td>
<td>II</td>
<td class="num">4.27</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">30.8 / 53.9</td>
<td class="num">—</td>
<td class="num">170</td>
<td class="num">—</td>
<td>full span only</td>
<td class="src"><a href="https://designation-systems.net/dusrm/app2/q-7.html">secondary</a></td>
</tr>
<tr class="odd">
<td class="what">Goetten UAV 6</td>
<td>Conventional</td>
<td>II</td>
<td class="num">4.30</td>
<td class="num">2.37</td>
<td class="num">0.551</td>
<td class="num">7.8</td>
<td class="num">36.1 / —</td>
<td class="num">1.1e6 – 1.4e6</td>
<td class="num">170</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 170 kg, payload 25 kg, loiter 36.1 m/s, AR 7.8, paper Re 1.2e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="even">
<td class="what">Lipan M3</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.60</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">41.7 / 47.2</td>
<td class="num">—</td>
<td class="num">60</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Threod Eos C</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.76</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">14.0 / 28.0</td>
<td class="num">—</td>
<td class="num">13</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Insitu RQ-21A Blackjack</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.80</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">30.9 / 46.3</td>
<td class="num">—</td>
<td class="num">61</td>
<td class="num">Class I (Small)<br />
payload 18 kg pl<br />
full span 4.9 m</td>
<td>full span only</td>
<td class="src"><a href="https://c-853-20151211-www-insitu-com.i.icims.com/wp-content/uploads/2021/01/RQ-21A_Blackjack_ProductCard_DU011221.pdf">maker</a></td>
</tr>
<tr class="odd">
<td class="what">KAI Doyosae</td>
<td>Conventional</td>
<td>I</td>
<td class="num">4.80</td>
<td class="num">2.84</td>
<td class="num">0.592</td>
<td class="num">8.1</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">130</td>
<td class="num">—</td>
<td>sets AR, Re<br />
Essari 2015 PhD (Univ. Belgrade) ch. 2, data 'from (1) &amp; (20)' (Jane's-style; refs not identified) §2.19; no speeds</td>
<td class="src"><a href="https://phaidrabg.bg.ac.rs/open/o:11738">thesis / report</a></td>
</tr>
<tr class="even">
<td class="what">Goetten UAV 5</td>
<td>Conventional</td>
<td>II</td>
<td class="num">4.90</td>
<td class="num">3.04</td>
<td class="num">0.620</td>
<td class="num">7.9</td>
<td class="num">34.7 / —</td>
<td class="num">1.2e6 – 1.5e6</td>
<td class="num">150</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 150 kg, payload 30 kg, loiter 34.7 m/s, AR 7.9, paper Re 1.5e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="odd">
<td class="what">Goetten UAV 8</td>
<td>Conventional</td>
<td>II</td>
<td class="num">5.10</td>
<td class="num">2.82</td>
<td class="num">0.553</td>
<td class="num">9.2</td>
<td class="num">30.6 / —</td>
<td class="num">9.1e5 – 1.2e6</td>
<td class="num">205</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 205 kg, payload 34 kg, loiter 30.6 m/s, AR 9.4, paper Re 1.1e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="even">
<td class="what">AAI RQ-2A Pioneer</td>
<td>Conventional</td>
<td>II</td>
<td class="num">5.15</td>
<td class="num">2.83</td>
<td class="num">0.549</td>
<td class="num">9.4</td>
<td class="num">33.3 / 56.7</td>
<td class="num">9.8e5 – 2.1e6</td>
<td class="num">190.5</td>
<td class="num">—</td>
<td>sets AR, Re<br />
30.42 ft2, 16.9 ft, mean chord 1.80 ft (Bray 1991, NPS wind-tunnel thesis); speeds designation-systems</td>
<td class="src"><a href="https://de3mirror.flightgear.org/fgdata/fgdata_2020_3/Aircraft-uiuc/models/pioneer/linear.html">thesis / report</a></td>
</tr>
<tr class="odd">
<td class="what">Goetten UAV 7</td>
<td>Conventional</td>
<td>II</td>
<td class="num">5.20</td>
<td class="num">3.13</td>
<td class="num">0.602</td>
<td class="num">8.6</td>
<td class="num">34.7 / —</td>
<td class="num">1.1e6 – 1.4e6</td>
<td class="num">182</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 182 kg, payload 40 kg, loiter 34.7 m/s, AR 8.6, paper Re 1.4e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="even">
<td class="what">Qods Mohajer-4</td>
<td>Conventional</td>
<td>II</td>
<td class="num">5.30</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">50.0 / 55.6</td>
<td class="num">—</td>
<td class="num">175</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">RUAG Ranger</td>
<td>Conventional</td>
<td>II</td>
<td class="num">5.71</td>
<td class="num">3.41</td>
<td class="num">0.597</td>
<td class="num">9.6</td>
<td class="num">49.9 / 66.9</td>
<td class="num">1.6e6 – 2.7e6</td>
<td class="num">275</td>
<td class="num">—</td>
<td>sets AR, Re<br />
Essari 2015 PhD (Univ. Belgrade) ch. 2, data 'from (1) &amp; (20)' (Jane's-style; refs not identified) §2.11; 97 / 130 kt</td>
<td class="src"><a href="https://phaidrabg.bg.ac.rs/open/o:11738">thesis / report</a></td>
</tr>
<tr class="even">
<td class="what">Goetten UAV 4</td>
<td>Conventional</td>
<td>I</td>
<td class="num">6.00</td>
<td class="num">2.63</td>
<td class="num">0.438</td>
<td class="num">13.7</td>
<td class="num">37.5 / —</td>
<td class="num">8.8e5 – 1.1e6</td>
<td class="num">130</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 130 kg, payload 18 kg, loiter 37.5 m/s, AR 13.5, paper Re 1.1e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="odd">
<td class="what">L-3 Viking 400</td>
<td>Conventional</td>
<td>II</td>
<td class="num">6.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 46.4</td>
<td class="num">—</td>
<td class="num">245</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/viking-400/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">ASN-206</td>
<td>Conventional</td>
<td>II</td>
<td class="num">6.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 58.3</td>
<td class="num">—</td>
<td class="num">222</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/asn-206/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">CTRM Aludra MK1 (NTNU)</td>
<td>Conventional</td>
<td>II</td>
<td class="num">6.10</td>
<td class="num">4.52</td>
<td class="num">0.741</td>
<td class="num">8.2</td>
<td class="num">28.3 / 61.1</td>
<td class="num">1.1e6 – 3.1e6</td>
<td class="num">200</td>
<td class="num">—</td>
<td>sets AR, Re<br />
NTNU: AR 8.23, NACA 4415; listed est. chord 0.60 m disagrees with full span / AR = 0.74 m</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Shadow V2</td>
<td>Conventional</td>
<td>II</td>
<td class="num">6.20</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">212</td>
<td class="num">Class II<br />
mtow 243 kg<br />
payload 19.5 kg pl</td>
<td>full span only</td>
<td class="src"><a href="https://www.textronsystems.com/sites/default/files/_documents/TS%20US%20Shadow%20V2%20Datasheet_061119.pdf">maker</a></td>
</tr>
<tr class="odd">
<td class="what">PT DI Wulung</td>
<td>Conventional</td>
<td>I</td>
<td class="num">6.34</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">30.9 / 51.4</td>
<td class="num">—</td>
<td class="num">125</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">DRDO Nishant</td>
<td>Conventional</td>
<td>II</td>
<td class="num">6.57</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">34.7 / 51.4</td>
<td class="num">—</td>
<td class="num">275</td>
<td class="num">—</td>
<td>full span only<br />
cruise 34.7-41.7 m/s (lowest)</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">GIDS Shahpar</td>
<td>Conventional</td>
<td>II</td>
<td class="num">6.60</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">41.7 / —</td>
<td class="num">—</td>
<td class="num">480</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">AAI Shadow 600</td>
<td>Conventional</td>
<td>II</td>
<td class="num">6.83</td>
<td class="num">3.75</td>
<td class="num">0.550</td>
<td class="num">12.4</td>
<td class="num">38.6 / 53.5</td>
<td class="num">1.1e6 – 2.0e6</td>
<td class="num">265</td>
<td class="num">—</td>
<td>sets AR, Re<br />
Essari 2015 PhD (Univ. Belgrade) ch. 2, data 'from (1) &amp; (20)' (Jane's-style; refs not identified) §2.15; 75 / 104 kt</td>
<td class="src"><a href="https://phaidrabg.bg.ac.rs/open/o:11738">thesis / report</a></td>
</tr>
<tr class="odd">
<td class="what">Kentron Seeker</td>
<td>Conventional</td>
<td>II</td>
<td class="num">7.00</td>
<td class="num">4.43</td>
<td class="num">0.632</td>
<td class="num">11.1</td>
<td class="num">33.4 / 48.9</td>
<td class="num">1.1e6 – 2.1e6</td>
<td class="num">240</td>
<td class="num">—</td>
<td>sets AR, Re<br />
Essari 2015 PhD (Univ. Belgrade) ch. 2, data 'from (1) &amp; (20)' (Jane's-style; refs not identified) §2.13; 65 / 95 kt</td>
<td class="src"><a href="https://phaidrabg.bg.ac.rs/open/o:11738">thesis / report</a></td>
</tr>
<tr class="even">
<td class="what">GSE Vindicator</td>
<td>Conventional</td>
<td>II</td>
<td class="num">7.04</td>
<td class="num">4.83</td>
<td class="num">0.686</td>
<td class="num">10.3</td>
<td class="num">43.7 / 102.9</td>
<td class="num">1.6e6 – 4.8e6</td>
<td class="num">476</td>
<td class="num">—</td>
<td>not used<br />
Essari 2015 PhD (Univ. Belgrade) ch. 2, data 'from (1) &amp; (20)' (Jane's-style; refs not identified) §2.18; target drone, top speed 200 kt is above Mach 0.3 (phase 1)</td>
<td class="src"><a href="https://phaidrabg.bg.ac.rs/open/o:11738">thesis / report</a></td>
</tr>
<tr class="odd">
<td class="what">Tekever AR5</td>
<td>Conventional</td>
<td>II</td>
<td class="num">7.30</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">27.8 / —</td>
<td class="num">—</td>
<td class="num">180</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">ASN-209</td>
<td>Conventional</td>
<td>II</td>
<td class="num">7.50</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 50.0</td>
<td class="num">—</td>
<td class="num">320</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/asn-209/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Warrior Gull 68</td>
<td>Conventional</td>
<td>II</td>
<td class="num">7.60</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 51.4</td>
<td class="num">—</td>
<td class="num">250</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/gull-68/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Airbus Atlante</td>
<td>Conventional</td>
<td>II</td>
<td class="num">8.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">37.5 / 55.6</td>
<td class="num">—</td>
<td class="num">570</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">IAI Searcher Mk III</td>
<td>Conventional</td>
<td>II</td>
<td class="num">8.55</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">31.0 / 57.0</td>
<td class="num">—</td>
<td class="num">450</td>
<td class="num">—</td>
<td>full span only<br />
cruise 31-41 m/s (lowest)</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Aeronautics Aerostar</td>
<td>Conventional</td>
<td>II</td>
<td class="num">8.70</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 51.4</td>
<td class="num">—</td>
<td class="num">240</td>
<td class="num">Class II<br />
mtow 240 kg<br />
payload 40 kg pl</td>
<td>full span only</td>
<td class="src"><a href="https://aeronautics-sys.com/wp-content/uploads/2025/10/AEROSTAR_PRINT_22.10.25-1.pdf">maker</a></td>
</tr>
<tr class="odd">
<td class="what">Goetten UAV 9</td>
<td>Conventional</td>
<td>II</td>
<td class="num">8.70</td>
<td class="num">4.74</td>
<td class="num">0.545</td>
<td class="num">16.0</td>
<td class="num">33.3 / —</td>
<td class="num">9.7e5 – 1.2e6</td>
<td class="num">230</td>
<td class="num">—</td>
<td>sets AR, Re<br />
MTOM 230 kg, payload 50 kg, loiter 33.3 m/s, AR 16.0, paper Re 1.2e6</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="even">
<td class="what">Denel Seeker 400</td>
<td>Conventional</td>
<td>II</td>
<td class="num">10.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 61.7</td>
<td class="num">—</td>
<td class="num">450</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/seeker-400/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">Elbit Hermes 450</td>
<td>Conventional</td>
<td>II</td>
<td class="num">10.51</td>
<td class="num">6.9</td>
<td class="num">0.657</td>
<td class="num">16.0</td>
<td class="num">36.0 / 48.9</td>
<td class="num">1.3e6 – 2.2e6</td>
<td class="num">450</td>
<td class="num">Class II<br />
payload 50 kg pl<br />
full span 10 m</td>
<td>sets AR, Re<br />
Essari 2015 PhD (Univ. Belgrade) ch. 2, data 'from (1) &amp; (20)' (Jane's-style; refs not identified) §2.17; constant chord 0.69 m printed (x full span = 7.25 m2, not 6.90: inconsistent); 70 / 95 kt</td>
<td class="src"><a href="https://phaidrabg.bg.ac.rs/open/o:11738">thesis / report</a></td>
</tr>
<tr class="even">
<td class="what">Thales Watchkeeper WK450</td>
<td>Conventional</td>
<td>II</td>
<td class="num">10.90</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">39.6 / —</td>
<td class="num">—</td>
<td class="num">485</td>
<td class="num">—</td>
<td>full span only</td>
<td class="src"><a href="https://www.army.mod.uk/learn-and-explore/equipment/aircraft/watchkeeper">government</a></td>
</tr>
<tr class="odd">
<td class="what">Goetten UAV 10</td>
<td>Conventional</td>
<td>III</td>
<td class="num">12.00</td>
<td class="num">8.7</td>
<td class="num">0.725</td>
<td class="num">16.6</td>
<td class="num">36.1 / —</td>
<td class="num">1.4e6 – 1.8e6</td>
<td class="num">630</td>
<td class="num">—</td>
<td>not used<br />
MTOM 630 kg, payload 55 kg, loiter 36.1 m/s, AR 16.5, paper Re 1.8e6; 630 kg is above Class II</td>
<td class="src"><a href="https://link.springer.com/article/10.1007/s13272-021-00522-w">paper</a></td>
</tr>
<tr class="even">
<td class="what">BAE Systems Herti</td>
<td>Conventional</td>
<td>II</td>
<td class="num">12.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 64.2</td>
<td class="num">—</td>
<td class="num">450</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/herti/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">USMC Exdrone (BQM-147)</td>
<td>Delta</td>
<td>I</td>
<td class="num">2.49</td>
<td class="num">1.97</td>
<td class="num">0.793</td>
<td class="num">3.1</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">29.5</td>
<td class="num">—</td>
<td>not used<br />
delta wing: neither of our families; NASA TM-4200, figures furnished by the USMC; NACA 63(1)A012</td>
<td class="src"><a href="https://ntrs.nasa.gov/api/citations/19900014922/downloads/19900014922.pdf">thesis / report</a></td>
</tr>
<tr class="even">
<td class="what">Sagem Sperwer</td>
<td>Delta</td>
<td>II</td>
<td class="num">4.20</td>
<td class="num">6.6</td>
<td class="num">1.571</td>
<td class="num">2.7</td>
<td class="num">41.7 / 55.6</td>
<td class="num">3.5e6 – 6.0e6</td>
<td class="num">330</td>
<td class="num">—</td>
<td>not used<br />
delta wing with V-tail: neither of our families; area from a secondary site only; speeds disagree between sources</td>
<td class="src"><a href="https://www.redstar.gr/en/greek-aviation/hellenic-aerial-means-af/army-aviation/unmanned-aerial-vehicle-uav/tactical-uav-system-sperwer.html">secondary</a></td>
</tr>
<tr class="odd">
<td class="what">Zala 421-08M</td>
<td>Tailless</td>
<td>I</td>
<td class="num">0.80</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 36.1</td>
<td class="num">—</td>
<td class="num">2.5</td>
<td class="num">—</td>
<td>full span only<br />
CNAS database; max speed converted from km/h</td>
<td class="src"><a href="https://drones.cnas.org/drones/zala-aero-group-zala-421-08m/">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">senseFly eBee</td>
<td>Tailless</td>
<td>I</td>
<td class="num">0.96</td>
<td class="num">0.25</td>
<td class="num">0.260</td>
<td class="num">3.7</td>
<td class="num">11.1 / —</td>
<td class="num">1.5e5 – 2.0e5</td>
<td class="num">0.69</td>
<td class="num">—</td>
<td>sets AR, Re<br />
cruise 40-90 km/h (lowest given)</td>
<td class="src"><a href="https://www.manualslib.com/manual/944170/Sensefly-Ebee.html">maker</a></td>
</tr>
<tr class="odd">
<td class="what">Trimble UX5</td>
<td>Tailless</td>
<td>I</td>
<td class="num">1.00</td>
<td class="num">0.34</td>
<td class="num">0.340</td>
<td class="num">2.9</td>
<td class="num">22.2 / —</td>
<td class="num">4.0e5 – 5.2e5</td>
<td class="num">2.5</td>
<td class="num">—</td>
<td>sets AR, Re<br />
34 dm2; 80 km/h 'flight speed'</td>
<td class="src"><a href="https://www.taketani.co.jp/sys/dat/pdf/to_img0_20160615092951.pdf">maker</a></td>
</tr>
<tr class="even">
<td class="what">Gatewing X100</td>
<td>Tailless</td>
<td>I</td>
<td class="num">1.00</td>
<td class="num">0.23</td>
<td class="num">0.230</td>
<td class="num">4.3</td>
<td class="num">22.2 / —</td>
<td class="num">2.7e5 – 3.5e5</td>
<td class="num">2</td>
<td class="num">—</td>
<td>sets AR, Re<br />
23 dm2; 80 km/h 'flight speed'</td>
<td class="src"><a href="https://www.taketani.co.jp/sys/dat/pdf/to_img0_20160615092951.pdf">maker</a></td>
</tr>
<tr class="odd">
<td class="what">Delair UX11</td>
<td>Tailless</td>
<td>I</td>
<td class="num">1.10</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">15.0 / —</td>
<td class="num">—</td>
<td class="num">1.5</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">AgEagle RX-60</td>
<td>Tailless</td>
<td>I</td>
<td class="num">1.37</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">17.9 / 21.9</td>
<td class="num">—</td>
<td class="num">3.2</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="odd">
<td class="what">C-Astral Atlas C4EYE</td>
<td>Tailless</td>
<td>I</td>
<td class="num">1.55</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">15.0 / 30.0</td>
<td class="num">—</td>
<td class="num">2.7</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Skywalker X8</td>
<td>Tailless</td>
<td>I</td>
<td class="num">2.10</td>
<td class="num">0.75</td>
<td class="num">0.357</td>
<td class="num">5.9</td>
<td class="num">18.0 / —</td>
<td class="num">3.4e5 – 4.4e5</td>
<td class="num">—</td>
<td class="num">—</td>
<td>sets AR, Re<br />
peer-reviewed; mean chord 0.36 m; 18 m/s is the test speed</td>
<td class="src"><a href="https://elib.dlr.de/212985/1/s13272-025-00816-3.pdf">paper</a></td>
</tr>
<tr class="odd">
<td class="what">C-Astral Bramor C4EYE</td>
<td>Tailless</td>
<td>I</td>
<td class="num">2.30</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">16.0 / 22.0</td>
<td class="num">—</td>
<td class="num">4.5</td>
<td class="num">—</td>
<td>full span only<br />
manufacturer calls it a BWB</td>
<td class="src"><a href="https://www.c-astral.com/en/unmanned-systems/bramor-c4eye">maker</a></td>
</tr>
<tr class="even">
<td class="what">DeltaQuad Pro</td>
<td>Tailless</td>
<td>I</td>
<td class="num">2.35</td>
<td class="num">0.9</td>
<td class="num">0.383</td>
<td class="num">6.1</td>
<td class="num">18.0 / 28.0</td>
<td class="num">3.7e5 – 7.3e5</td>
<td class="num">6.2</td>
<td class="num">—</td>
<td>sets AR, Re<br />
90 dm2</td>
<td class="src"><a href="https://www.deltaquad.com/map">maker</a></td>
</tr>
<tr class="odd">
<td class="what">AUTh RX-3 1:3 subscale BWB</td>
<td>Tailless</td>
<td>I</td>
<td class="num">2.40</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">19.4 / —</td>
<td class="num">—</td>
<td class="num">6</td>
<td class="num">—</td>
<td>full span only<br />
Kapsalis et al. 2026: full span 2.4 m, 6 kg, 70 km/h</td>
<td class="src"><a href="https://www.mdpi.com/2673-4591/133/1/95">paper</a></td>
</tr>
<tr class="even">
<td class="what">DeltaQuad Evo TAC</td>
<td>Tailless</td>
<td>I</td>
<td class="num">2.69</td>
<td class="num">0.84</td>
<td class="num">0.312</td>
<td class="num">8.6</td>
<td class="num">16.7 / —</td>
<td class="num">2.8e5 – 3.6e5</td>
<td class="num">11</td>
<td class="num">—</td>
<td>sets AR, Re<br />
84 dm2</td>
<td class="src"><a href="https://docs.deltaquad.com/tac/vehicle-specifications">maker</a></td>
</tr>
<tr class="odd">
<td class="what">Lehmkuehler BWB UAV</td>
<td>Tailless</td>
<td>I</td>
<td class="num">3.00</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">16</td>
<td class="num">—</td>
<td>full span only<br />
ICAS2012-675: 16 kg, 3 m full span, sweep limited to 15 deg</td>
<td class="src"><a href="https://www.icas.org/ICAS_ARCHIVE/ICAS2012/PAPERS/675.PDF">paper</a></td>
</tr>
<tr class="even">
<td class="what">Aerovision Fulmar</td>
<td>Tailless</td>
<td>I</td>
<td class="num">3.10</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">16.7 / 41.7</td>
<td class="num">—</td>
<td class="num">19</td>
<td class="num">—</td>
<td>full span only<br />
60-150 km/h range; paper gives no source</td>
<td class="src"><a href="https://acta-avionica.tuke.sk/ojs/index.php/aavionica/article/download/591/589">secondary</a></td>
</tr>
<tr class="odd">
<td class="what">Insitu ScanEagle (NTNU)</td>
<td>Tailless</td>
<td>I</td>
<td class="num">3.11</td>
<td class="num">0.78</td>
<td class="num">0.251</td>
<td class="num">12.4</td>
<td class="num">25.0 / 41.0</td>
<td class="num">3.4e5 – 7.0e5</td>
<td class="num">20</td>
<td class="num">—</td>
<td>sets AR, Re<br />
NTNU: AR 12.4, est. chord 0.25 m; swept tailless wing with winglet rudders</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Lockheed MQM-105 Aquila</td>
<td>Tailless</td>
<td>I</td>
<td class="num">3.76</td>
<td class="num">2.92</td>
<td class="num">0.775</td>
<td class="num">4.9</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">66.5</td>
<td class="num">—</td>
<td>sets AR, Re<br />
Lockheed final report Table 1(A) p. 39: overall (full) span 12.35 ft, projected area 31.4 ft2 (reference 11.5 ft, 30.2 ft2), MAC 32.26 in, root 40 in, tip 23 in, taper 0.58, AR 4.86, LE sweep 28 deg, NACA 23015 mod.; gross 146.5 lb</td>
<td class="src"><a href="https://apps.dtic.mil/sti/pdfs/ADA068345.pdf">maker</a></td>
</tr>
<tr class="odd">
<td class="what">Aeronautics Orbiter 3</td>
<td>Tailless</td>
<td>I</td>
<td class="num">4.40</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / 36.0</td>
<td class="num">—</td>
<td class="num">30</td>
<td class="num">—</td>
<td>full span only<br />
NTNU database</td>
<td class="src"><a href="https://doi.org/10.18710/L41IGQ">UAV database (NTNU, CNAS)</a></td>
</tr>
<tr class="even">
<td class="what">Lockheed Martin Fury</td>
<td>Tailless</td>
<td>II</td>
<td class="num">5.20</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">—</td>
<td class="num">— / —</td>
<td class="num">—</td>
<td class="num">195</td>
<td class="num">—</td>
<td>full span only<br />
'blended' wing; no speeds published</td>
<td class="src"><a href="https://newatlas.com/lockheed-martin-fury-drone-uas/49263/">secondary</a></td>
</tr>
<tr class="odd">
<td class="what">AUTh RX-3 tactical BWB</td>
<td>Tailless</td>
<td>II</td>
<td class="num">6.26</td>
<td class="num">4.9</td>
<td class="num">0.783</td>
<td class="num">8.0</td>
<td class="num">44.4 / —</td>
<td class="num">1.9e6 – 2.4e6</td>
<td class="num">260</td>
<td class="num">—</td>
<td>sets AR, Re<br />
Antoniou et al. 2025 Table 1: S 4.9 m2, c/4 sweep 33 deg, AR 8, cruise 160 km/h, take-off 108 km/h. Full span = sqrt(AR S) (our calculation); Wikipedia gives 7.2 m, so the AR may refer to part of the planform</td>
<td class="src"><a href="https://www.mdpi.com/2673-4591/90/1/18">paper</a></td>
</tr>
</tbody>
</table>

Re low = cruise at 3,048 m; Re high = top speed (cruise if none) at sea level; air from Stage 0. Family from a text source or, where none says it, from photos (marked K in the YAML). Only wings with a published area set the ranges (since 7 Nov: the aspect ratios and the Re range); they rest on: paper 11, maker 8, thesis / report 8, UAV database (NTNU, CNAS) 7. HCDI database column: the same aircraft in your UAS dashboard, where listed. Notes that say "above Mach 0.3" or "outside phase 1" (Vindicator, CPJ 100-LE) predate 4 Nov 2026: the Mach scope now extends toward 0.5 with no supersonic flow, and such wings wait on a fast-UAV family (proposal, pending).

**Conclusion.** Real Class I–II wings fly at Re 1.2 × 10⁵ – 3.1 × 10⁶ on the mean chord. None of our families reaches 5 × 10⁶, so 3 × 10⁶ was first chosen as the top study level for the core data (Mach ≤ 0.2); on 8 Nov it became 4 × 10⁶ for the Greek tactical UAVs (decision 78). A fast-UAV family (proposal, pending) would reach higher: the Vindicator flies at up to 4.8 × 10⁶.

## Full spans from the HCDI UAS database (v13)

794 entries; 76 fixed-wing Class I–II; 22 give a full span; **none gives a wing area**, so these rows tested the full-span range only ("inside": within 10 % of the focus full-span range of its family, first approach). Every tailless full span was inside, up to 7.3 m. Four conventional Class II wings (8–10 m) were outside the focus space, which stopped at 7 m; the full space covered them. Since 7 Nov there is no full-span range in metres, so this column is first-approach only.

**Database weak points.** No source per row. 28 rows share cruise 35 m/s, endurance 6 h and range 100 km (look like defaults); on 8 rows cruise is above top speed. Orlan-10 is listed as Class II at 18 kg, Puma LE as a flying wing, XQ-58 Valkyrie (a jet) as Class II; Zala Z-16's maker field names a microchip company. Only full span, class, MTOW and payload are used here.

| Aircraft | Family | Class | Full span m | MTOW kg | Payload kg | Role | Full span vs generator (first approach) | Check |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V2U | Conventional | I | 1.2 | 15 | 3.5 | Barrage Munition | inside | |
| Shahed 107 | Conventional | I | 3 | 26 | 20 | ISR | inside | |
| Orlan-10 | Conventional | I | 3.05 | 18 | 5.5 | ISR | inside | database says Class II, but MTOW 18 kg is Class I |
| Orlan-30 | Conventional | I | 3.05 | 30 | 12 | ISTAR | inside | |
| Granat-4 | Conventional | I | 3.35 | 30 | 20 | ISTAR | inside | |
| Puma LE | Conventional | I | 4.6 | — | 2.5 | ISR | inside | database says Flying Wing; the Puma family is a conventional wing |
| Merlin-VR | Conventional | I | 4.9 | 20 | 7 | ISTAR | inside | |
| Corsair | Conventional | II | 6.5 | — | 40 | — | inside | |
| Vestel Karayel | Conventional | II | 8 | — | 50 | — | outside | |
| Ababil-3 | Conventional | II | 8 | — | 40 | — | outside | |
| Hamaseh | Conventional | II | 9 | — | 50 | — | outside | |
| Mohajer-6 | Conventional | II | 10 | — | 150 | — | outside | payload 150 kg; class to verify against MTOW |
| Interceptor-mr | Tailless | I | 0.9 | — | 1 | Interceptor | inside | |
| Zala Z-16 | Tailless | I | 2.815 | 10.5 | 1.8 | ISTAR | inside | manufacturer field reads Nanjing Qinheng Microelectronics (WCH); ZALA Aero is the maker |
| CPJ 100-LE | Tailless | I | 3.05 | — | 4.54 | One-Way Attack | not used | top speed 380 km/h (106 m/s) is above Mach 0.3, outside phase 1 |
| Supercam S350 | Tailless | I | 3.2 | 15.5 | 2.5 | ISTAR | inside | |
| SKAT-350M | Tailless | I | 3.2 | 15 | 2.5 | ISTAR | inside | |
| Gerbera | Tailless | I | 3.5 | 18 | 4.6 | Loitering Munition | inside | |
| Shahed 197 | Tailless | I | 7 | — | — | — | inside | 7 m full span listed as Class I (Small) with no MTOW: class doubtful |
| Albatroz | Tailless | II | 7 | — | 30 | — | inside | |
| Shahed 191 (Saegheh) | Tailless | II | 7.31 | — | 50 | — | inside | |
| XQ-58 Valkyrie | Tailless | II | 8.229 | — | 272.2 | ISR | not used | jet, top 1,050 km/h; listed as Class II but it is far heavier than 600 kg (Class III) |

**Conclusion.** The HCDI database gives full spans only. First approach: every Class I and every tailless full span fitted the focus space; only four conventional Class II wings (8–10 m) needed the full space. Now a full span in metres is only a scale: it sets the Re of a solve, not the wing.

## Checks and results

### Gate 1 · vector → loft

Measured on the loft: chords within 0.1 %, sweeps 0.1°, twist 0.2°, dihedral 0.2°, aspect ratio 0.1 %.

### Gate 2 · trailing edge

Thickness equals the rule (0.2 % of the local chord) at every section, within 1e-6 mean chords (1 µm on the real-size wings before 7 Nov).

### Gate 3 · validity

Sections closed, upper never below lower, root flat in y = 0 within 1e-9 mean chords, chords positive; since 7 Nov also no nose that folds back (the nose gate).

### Gate 4 · repeatability

Two builds give the same surface hash.

A wing that fails any gate is not written; its row keeps the gate and the reason. The fifth check, mesh on the loft within 1e-9, is done in Stage 2: the surface mesher asks every node from the loft and checks that every ring lies in its station plane within 1e-9; 790 of 790 builds pass its 13 checks (numpy loft, on the first-approach wings). On the 7 Nov wings: 1,724 of 1,724 (numpy loft, 7 Nov) and 3,128 of 3,128 (every built set at every level, 8 Nov; Study 12), and on 8 Nov on pyGeo (your machine) the 20 reference wings gave the same meshes as the numpy loft.

**What changes (7 Nov 2026).** 722 wings (730 before): corner 1 has 32 or 24 wings (the two root-chord corners went). The gates read lengths in mean chords; the trailing-edge gate checks 0.2 % c; the validity gate also refuses a nose that folds back. The loft check was rerun on all 722 wings on 7 Nov (numpy loft), and the published-wing check on all 7.

## Sample sets

| Type | Set | Wings | Result | Type by the rules |
| --- | --- | --- | --- | --- |
| BWB | training (focus) | 100 | 100 built, 0 refused | bwb 85, flying wing 15 |
| BWB | training (full) | 40 | 40 built, 0 refused | bwb 31, flying wing 9 |
| BWB | corner 1 (full) | 32 | 32 built, 0 refused | bwb 31, flying wing 1 |
| BWB | corner 2 (full) | 8 | 8 built, 0 refused | bwb 4, flying wing 4 |
| BWB | reference (focus) | 5 | 5 built, 0 refused | bwb 4, flying wing 1 |
| BWB | hold-out (focus) | 10 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |
| BWB | hold-out (full) | 5 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |
| Flying wing | training (focus) | 100 | 100 built, 0 refused | flying wing 100 |
| Flying wing | training (full) | 40 | 40 built, 0 refused | flying wing 39, bwb 1 |
| Flying wing | corner 1 (full) | 24 | 24 built, 0 refused | flying wing 24 |
| Flying wing | corner 2 (full) | 7 | 7 built, 0 refused | flying wing 5, bwb 2 |
| Flying wing | reference (focus) | 5 | 5 built, 0 refused | flying wing 5 |
| Flying wing | hold-out (focus) | 10 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |
| Flying wing | hold-out (full) | 5 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |
| Cranked | training (focus) | 100 | 100 built, 0 refused | cranked 100 |
| Cranked | training (full) | 40 | 40 built, 0 refused | cranked 40 |
| Cranked | corner 1 (full) | 32 | 32 built, 0 refused | cranked 16, tapered 16 |
| Cranked | corner 2 (full) | 8 | 8 built, 0 refused | cranked 5, tapered 3 |
| Cranked | reference (focus) | 5 | 5 built, 0 refused | cranked 5 |
| Cranked | hold-out (focus) | 10 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |
| Cranked | hold-out (full) | 5 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |
| Tapered | training (focus) | 100 | 100 built, 0 refused | tapered 100 |
| Tapered | training (full) | 40 | 40 built, 0 refused | tapered 40 |
| Tapered | corner 1 (full) | 24 | 24 built, 0 refused | tapered 24 |
| Tapered | corner 2 (full) | 7 | 7 built, 0 refused | tapered 7 |
| Tapered | reference (focus) | 5 | 5 built, 0 refused | tapered 5 |
| Tapered | hold-out (focus) | 10 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |
| Tapered | hold-out (full) | 5 | vectors only in Stage 1; opened once for the surface mesh on 9 Nov (decision 83; Stage 2 Study 14) | — |

**Conclusion.** All 722 sampled wings (7 Nov, numpy loft) build and pass the four checks; none is refused. The type rules usually agree with the sampled type, but not always: 15 of the 100 focus BWBs read as flying wings by the rule (14 before 7 Nov), and many corner wings read as the neighbouring type. The Stage 2 surface mesher meshed all 730 first-approach wings (790 builds, with the 20 reference wings at all four Re levels) with 0 refusals; on 7 Nov it screened the 7 Nov wings at every set: 1,724 of 1,724 builds pass (4 F builds after one nose repair), and on 8 Nov every built set at every level: 3,128 of 3,128 with no nose repair (Study 12). Every hash changed on 7 Nov; with pyGeo on your machine (8 Nov) all 722 build too, with the same input hashes, and the reference meshes equal the numpy ones (VC and F). One label of 722 differed between the two lofts (a sweep change of exactly 5°, the kink threshold); fixed on 8 Nov (decision 79), with every input hash new and every surface the same.

## Is the loft the designed wing? (every sampled wing)

Worst value over every training, corner and reference wing (`scripts/verify_sets.py`, numpy loft). Stations, chords, twists, sweeps, panel dihedrals and the straightness of each panel match the inputs to machine precision. AR: the loft measures the true chord, which is a little shorter between two stations of different twist; the aspect ratio still matches within 0.00004 %. Sections: within 0.00036 % of chord on every wing (before 7 Nov up to 0.02 % c, on the smallest corner wings, where the 0.5 mm trailing-edge floor was a large share of the chord; the floor is gone). Root: every point of the root section at y = 0, and no point of a half wing below y = 0, so the mirrored halves meet only there. Lengths in mean chords.

| Type | Wings | Stations % c | Chord % | Twist ° | Sweep ° | Dihedral ° | Straight panels % c | AR % | Sections % c | Ruled % c | Root \|y\| | Min y |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BWB | 185 | 0 | 3e-13 | 3e-14 | 2e-14 | 4e-15 | 3e-13 | 3.6e-05 | 0.00036 | 1e-12 | 0 | 0 |
| Flying wing | 176 | 0 | 2e-13 | 2e-14 | 3e-14 | 5e-15 | 4e-13 | 3e-05 | 0.00036 | 9e-13 | 0 | 0 |
| Cranked | 185 | 0 | 7e-14 | 1e-14 | 1e-14 | 4e-15 | 1e-13 | 2.3e-05 | 0.00036 | 9e-13 | 0 | 0 |
| Tapered | 176 | 0 | 8e-14 | 9e-15 | 1e-14 | 4e-15 | 2e-13 | 2.6e-05 | 0.00036 | 5e-13 | 0 | 0 |

**Conclusion.** The loft is the designed wing: stations, chords, twists, sweeps and dihedrals match the inputs to machine precision, and the sections within 0.00036 % of the chord on every wing (before 7 Nov up to 0.02 %, where the mm floor was large).

## Is the surface the intended wing? (published wings)

Errors in % of local chord. Sections: the loft cut at each station against the original airfoil points (limit 0.01). This compares only at the file's own points, so it cannot see the nose between them: the nose study (decision 64) measured that part, along the arc. Since 7 Nov the check finds the section's frame on its own, as the new rule does. Edges: against the exact straight lines (limit 1e-6). Outside CAD: only the M6 has one (limit 0.05; it needs gmsh, which is not installed here).

| Wing | Sections max | Edges max | Outside CAD | Result |
| --- | --- | --- | --- | --- |
| `onera_m6` | 0.0003 | 3e-14 | not run here (gmsh not installed); 2 Nov run, first approach: max 0.0113 | pass |
| `ribes` | 0.0005 | 2e-14 | no outside file | pass |
| `nasa_crm` | 0.0004 | 2e-13 | no outside file | pass |
| `blendednet_low` | 0.0004 | 6e-14 | no outside file | pass |
| `blendednet_mid` | 0.0004 | 1e-13 | no outside file | pass |
| `blendednet_high` | 0.0004 | 2e-13 | no outside file | pass |
| `blendednetpp_mid` | 0.0004 | 2e-13 | no outside file | pass |

**Conclusion.** Every published wing passes on 7 Nov: sections within 0.00054 % of the chord at the file's points (0.003 % before 7 Nov), edges exact. The ONERA M6 was within 0.011 % of the chord of its CAD model on 2 Nov (first approach); that check was not rerun here (no gmsh), and it now scales the CAD by `real_mean_chord_m`. The nose between the file's points is the nose study's job (decision 64).

## What it cannot make (yet)

- **Straight edges only, three panels at most.** No curved BWB centre body, no elliptic planform, no fourth panel.
- **Airfoil shape is not a variable.** Any named file can be used, and a station can draw from a list, but thickness and camber are not sampled continuously. The default sets use one section per station (t/c 10–15 %).
- **No winglets, rounded or raked tips, fuselage, gaps.** Panel dihedral: focus 0–5°, full ±10°.
- **Some shape sources are thin.** The layout shares (where b1 and b2 sit) are our choice. A few rules are second-hand (Raymer via a course page). BWB shapes rest on four small-UAV papers, two of them larger than Class I.
- **Similarity has limits.** The Re on the mean chord carries the size, but not the roughness or the air turbulence (Tu 0.07 % is fixed), and small real wings have thicker trailing edges (about 0.42 % c) than the 0.2 % c rule. Checks C1–C4 (CFD) are still to run.
- **Class II areas are uncertain.** Most rest on Götten et al. (from photos, about 10–15 %) and a thesis citing unread Jane's-style data. The AUTh RX-3 is the only tailless Class II wing with an area (4.9 m²), and its full span is derived (√(AR · S)). Since 7 Nov they set only aspect ratios and the Re range.
- **0 refusals at the corners** here: 722 of 722 wings built on 7 Nov. The Stage 2 surface mesher passed 790 of 790 builds on the first-approach wings (real size, before 7 Nov); its lowest quad quality (scaled Jacobian 0.09, limit 0.05) was on corner wings with a very narrow first panel (4–6 mm at real size) and a trailing edge swept about 85°. Since 7 Nov it has screened the 7 Nov wings: on 8 Nov every built set at every level, 3,128 of 3,128 builds pass with no nose repair (Study 12; the 20 reference wings at the four Re levels, the rest at 3 × 10⁵); and on 9 Nov the 60 hold-outs, never seen before, opened once with the surface rules frozen: 960 of 960 builds pass (Stage 2 Study 14, decision 83; the tip cap closest, 0.0503 at M against 0.05).
- **Published wings:** M6 and CRM are transonic, and the scope has no supersonic flow (it extends toward Mach 0.5; decided 4 Nov 2026), so they are shape and mesh checks only. RIBES is tripped at 1.4 % chord, so no published case here checks transition (candidate: the E387 wind-tunnel data). CRM is approximate. BlendedNet twist and dihedral are guessed as zero. Every tip is a flat cut, including the M6's rounded one. Like every wing, the copies are built at unit mean chord (`real_mean_chord_m` scales back).
- **Nose.** The nose gate refuses 14 database files (very sharp or flat-faced noses; none is used): they would need more section points near the leading edge. On coarse files (about 61 points) the raw file itself does not settle the nose turning at the smallest cells better than about ±15 % (cubic against quintic spline). One file (nm26-3smoothed) has note lines that the reader takes as points.
- **The flow data are first approach.** The flow maps and the flow dataset were made at real size and speed before 7 Nov and are not rebuilt; the section tables are size-free and were rebuilt on the fixed nose on 7 Nov (no conclusion changes).
- **No fast-UAV family yet.** Mach 0.3–0.5 needs real fast UAVs, thinner sections and section tables up to Mach 0.5 (proposal, pending); the data here stop at Mach 0.2.

**What changes (7 Nov 2026).** New limits since 7 Nov: similarity carries size through Re, but not roughness, air turbulence or the thicker trailing edges of small real wings (checks C1–C4 to run); the nose gate refuses 14 database files; the flow data are first approach.

## Published wings it rebuilds

*\[Figure: Animation of the published wings rebuilt by the generator\]*

Each frame is a wing rebuilt by the same generator, with the same loft and checks as the sampled wings. BlendedNet wings are made directly from the BlendedNet parameters. Like every wing, each copy is built at unit mean chord; the sizes shown are the real ones (lengths × `real_mean_chord_m`).

**What changes (7 Nov 2026).** The YAML keeps each published wing at its real size; the copy is built at unit mean chord, and `meta["real_mean_chord_m"]` scales it back to metres (the M6 CAD check uses it). The pictures and the table show real sizes. Every hash changed on 7 Nov.

**Conclusion.** The same generator rebuilds the ONERA M6, RIBES, NASA CRM and BlendedNet wings, so our meshes and results can be compared with published data.

*\[Figure: Top views of all published wings\]*

**Conclusion.** Scaled by their root chord, the copies show the planforms of the published wings: the conventional M6, RIBES and CRM, and the four BlendedNet BWBs, which differ mostly in the centre-body chords and the outer sweep. The scale does not change the shape, so the unit-mean-chord copies are the same wings.

<table class="wide" style="width:100%;">
<colgroup>
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
</colgroup>
<thead>
<tr class="header">
<th>Wing</th>
<th>Family</th>
<th>Size</th>
<th>What it is for</th>
<th>How close the copy is</th>
<th>Sources</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td class="what">ONERA M6 wing (wind-tunnel model)onera_m6</td>
<td>Conventional</td>
<td class="num">semi-span 1.2 m<br />
AR 3.80<br />
MAC 0.646 m<br />
built at c̄ = 1;<br />
× 0.63 m</td>
<td>Classic transonic validation case (M 0.84, alpha 3.06 deg, Re 11.72e6 on the mean chord). Outside phase 1 (Mach &lt;= 0.3); kept for the transonic stage and as a planform and mesher check.</td>
<td>Planform exact (root 0.806 m, tip 0.453 m, semi-span 1.196 m, LE sweep 30 deg). Section: the published streamwise profile, scaled with the local chord at every station (the wing is conical, so streamwise sections are similar). Trailing edge 0.141 % chord as published. Tip: flat cut, not the model's rounded tip. Check: mean aerodynamic chord 0.6461 m against the published 646.07 mm; aspect ratio 3.80.<br />
Sections: onera_m6</td>
<td class="src">Schmitt &amp; Charpin, Pressure distributions on the ONERA-M6-wing at transonic Mach numbers, AGARD AR-138, 1979<br />
NASA GRC WIND validation archive, m6wing (geometry and streamwise section)</td>
</tr>
<tr class="even">
<td class="what">RIBES wind-tunnel wing (half model)ribes</td>
<td>Conventional</td>
<td class="num">semi-span 1.6 m<br />
AR 6.28<br />
MAC 0.515 m<br />
built at c̄ = 1;<br />
× 0.51 m</td>
<td>In-regime validation: 40 m/s, Re 1.43e6, boundary layer tripped at 1.4 % chord, 3,814 pressure taps over three spanwise sections.</td>
<td>Planform as fitted to the laser scan (root 599.8 mm, tip 419.9 mm, span 1.600 m). Section: median of 17 scanned sections (t/c 11.4 %). Its fitted trailing edge is 0.26 % chord, thinner than the 0.38-0.66 % measured on the model: check this before validating drag.<br />
Sections: ribes</td>
<td class="src">RIBES test report, Clean Sky JTI grant 632556<br />
AERIS ribes_loft.py and external/ribes/ribes_section.dat (laser scan of the manufactured model)</td>
</tr>
<tr class="odd">
<td class="what">NASA Common Research Model wing (approximate)nasa_crm</td>
<td>Conventional</td>
<td class="num">semi-span 29.4 m<br />
AR 8.39<br />
MAC 8.32 m<br />
built at c̄ = 1;<br />
× 7 m</td>
<td>Drag Prediction Workshop transonic airliner wing (M 0.85, CL 0.5). Outside phase 1 (Mach &lt;= 0.3). Approximate copy; see fidelity.</td>
<td>Chords exact at root, side of body, Yehudi break and tip (chord is linear between them on the real wing too). Leading edge taken as one straight line, 37.3 deg (derived). Twist and dihedral are linear between the four stations: twist within 0.51 deg of the published 21-station table, vertical position within 0.09 m (0.3 % of the semi-span). Sections are NASA SC(2) stand-ins: a validation run needs the real CRM sections and more stations. Check: full planform area 411.7 m2 against the published gross area 412.1 m2 (0.1 %).<br />
Sections: sc20414, sc20412, sc20410</td>
<td class="src">Vassberg et al., Development of a Common Research Model for applied CFD validation studies, AIAA 2008-6919<br />
Characterization of the Common Research Model wing, Utah State University (digitalcommons.usu.edu, mae_stures 1029), Table A1<br />
Brooks et al., Benchmark aerostructural models for the study of transonic aircraft wings (uCRM), AIAA J. 2018, doi 10.2514/1.J056603</td>
</tr>
<tr class="even">
<td class="what">BlendedNet design blendednet_lowblendednet_low</td>
<td>Tailless (BWB)</td>
<td class="num">semi-span 0.35 m<br />
AR 2.05<br />
MAC 0.602 m<br />
built at c̄ = 1;<br />
× 0.342 m</td>
<td>BWB dataset design (FUN3D RANS, Spalart–Allmaras), 12,490 published solutions in BlendedNet++.</td>
<td>Planform exact in the BlendedNet parameters (straight panels, as OpenVSP builds them). Airfoils as BlendedNet++ Table 4; NACA 25118 made from the NACA formula. Twist and dihedral zero (not stated in the papers).<br />
Sections: naca25118, sc20412, naca0012</td>
<td class="src">BlendedNet: a blended wing body aircraft dataset and surrogate model for aerodynamic predictions, arXiv 2509.07209 (Table 2)<br />
BlendedNet++: a large-scale blended wing body aerodynamics dataset and benchmark, arXiv 2512.03280 (Tables 3 and 4)</td>
</tr>
<tr class="odd">
<td class="what">BlendedNet design blendednet_midblendednet_mid</td>
<td>Tailless (BWB)</td>
<td class="num">semi-span 0.725 m<br />
AR 4.13<br />
MAC 0.591 m<br />
built at c̄ = 1;<br />
× 0.351 m</td>
<td>BWB dataset design (FUN3D RANS, Spalart–Allmaras), 12,490 published solutions in BlendedNet++.</td>
<td>Planform exact in the BlendedNet parameters (straight panels, as OpenVSP builds them). Airfoils as BlendedNet++ Table 4; NACA 25118 made from the NACA formula. Twist and dihedral zero (not stated in the papers).<br />
Sections: naca25118, sc20412, naca0012</td>
<td class="src">BlendedNet: a blended wing body aircraft dataset and surrogate model for aerodynamic predictions, arXiv 2509.07209 (Table 2)<br />
BlendedNet++: a large-scale blended wing body aerodynamics dataset and benchmark, arXiv 2512.03280 (Tables 3 and 4)</td>
</tr>
<tr class="even">
<td class="what">BlendedNet design blendednet_highblendednet_high</td>
<td>Tailless (BWB)</td>
<td class="num">semi-span 1.1 m<br />
AR 5.66<br />
MAC 0.624 m<br />
built at c̄ = 1;<br />
× 0.389 m</td>
<td>BWB dataset design (FUN3D RANS, Spalart–Allmaras), 12,490 published solutions in BlendedNet++.</td>
<td>Planform exact in the BlendedNet parameters (straight panels, as OpenVSP builds them). Airfoils as BlendedNet++ Table 4; NACA 25118 made from the NACA formula. Twist and dihedral zero (not stated in the papers).<br />
Sections: naca25118, sc20412, naca0012</td>
<td class="src">BlendedNet: a blended wing body aircraft dataset and surrogate model for aerodynamic predictions, arXiv 2509.07209 (Table 2)<br />
BlendedNet++: a large-scale blended wing body aerodynamics dataset and benchmark, arXiv 2512.03280 (Tables 3 and 4)</td>
</tr>
<tr class="odd">
<td class="what">BlendedNet design blendednetpp_midblendednetpp_mid</td>
<td>Tailless (BWB)</td>
<td class="num">semi-span 0.8 m<br />
AR 4.82<br />
MAC 0.572 m<br />
built at c̄ = 1;<br />
× 0.332 m</td>
<td>BWB dataset design (FUN3D RANS, Spalart–Allmaras), 12,490 published solutions in BlendedNet++.</td>
<td>Planform exact in the BlendedNet parameters (straight panels, as OpenVSP builds them). Airfoils as BlendedNet++ Table 4; NACA 25118 made from the NACA formula. Twist and dihedral zero (not stated in the papers).<br />
Sections: naca25118, sc20412, naca0012</td>
<td class="src">BlendedNet: a blended wing body aircraft dataset and surrogate model for aerodynamic predictions, arXiv 2509.07209 (Table 2)<br />
BlendedNet++: a large-scale blended wing body aerodynamics dataset and benchmark, arXiv 2512.03280 (Tables 3 and 4)</td>
</tr>
</tbody>
</table>

The "What it is for" and "How close" texts come from `configs/published_wings.yaml`. Read "outside phase 1" and "kept for the transonic stage" as out of date: the scope has no supersonic flow and extends toward Mach 0.5 (decided 4 Nov 2026), so the M6 and the CRM are shape and mesh checks only. The M6's Re 11.72 × 10⁶ is on its MAC (0.646 m); its mean chord (area / full span) is 0.630 m. RIBES is tripped at 1.4 % chord: it checks fully turbulent RANS, not transition. Its "span 1.600 m" is the semi-span of the half model. Since 7 Nov the YAML keeps every wing at its real size; the copy is built at unit mean chord and `meta["real_mean_chord_m"]` scales it back (the M6 CAD check uses it).

*\[Figure: CRM chord and twist against the published table\]*

NASA CRM against its published 21-station table. Chords match exactly; with four stations the twist is off by at most 0.51°.

**Conclusion.** Four stations give the CRM chords exactly but not its smooth twist (up to 0.51° off): good for mesh tests, not for matching CRM force data exactly.

## Commands

    cd CFD_Automation/Stage_1_geometry
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
    python scripts/make_generator_page.py                                # this page

Generated by `CFD_Automation/Stage_1_geometry/scripts/make_generator_page.py` from `configs/wing.yaml`, the set manifests and `docs/verification.json`. Decision notes: `Stage_1_geometry/decisions/`.
