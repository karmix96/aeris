# Open decisions

1. **Grid share 65 %** (= 100 − 10 − 10 − 15). Keep?
2. ~~**Reynolds low end.**~~ **Decided 30 Oct 2026:** 1 × 10⁵ added (see 48).
3. **Pitching moment 0.002** — our choice, no source. Keep?
4. **Iterative error ≤ 10 %** is loose; Eça & Hoekstra ask 0.1–1 %. Tighten to 1 %?
5. **Turbulence-model source is weak.** Crivellini 2014 found standard SA did fairly well on
   laminar bubbles. Find a better source or call it our choice.
6. **Grand Roadmap Stage 0 has a D5** (prior work, transition route, tunnel, cloud budget). Add?

## Stage 1 (geometry) — choices I made

7. **Folder.** Stage 1 lives in `CFD_Automation/Stage_1_geometry/` (config, tests, data, docs). Run from
   there: `python -m cfdauto.geometry.build …`. No `src/` level. **2 Nov 2026:** the code moved to one shared
   package, `CFD_Automation/cfdauto/` (`geometry`, `flowmap`; later `mesh`, `solver`), installed once with
   `pip install -e CFD_Automation`; stage folders keep configs, data, docs and tests (`cfdauto/paths.py`).
8. ~~**Conventional ranges**~~ **Decided 29 Oct 2026:** size ranges come from a sourced table of
   real Class I–II wings (`Stage_1_geometry/configs/real_uavs.yaml`), not from a target Re. Root chord
   0.13–0.60 m for conventional and tapered; see `Stage_1_geometry/decisions/conventional_ranges.md`.
9. ~~**BWB stops at Re ≈ 3 × 10⁶**~~ **Decided 29 Oct 2026:** BWB sizes come from real tailless
   wings too (root chord 0.40–0.80 m, semi-span 0.75–2.2 root chords). The top Re level is lowered
   to 3 × 10⁶ for every type, because no real wing of our families reaches 5 × 10⁶ (highest 2.74 × 10⁶, RUAG Ranger).
10. **BWB root dihedral** now 0–3° at b0 and b1 (was pinned 0 in AERIS).
11. **`root_chord_fractions` mode:** `semi_span_m` is read as semi-span / root chord (keeps one
    variable list). Conventional uses this mode so the aspect ratio stays in 4–16.5.
12. ~~**Dihedral on straight panels**~~ **Decided 29 Oct 2026:** one dihedral per panel
    (`dihedral_p1..p3_deg`); the root section stays vertical in y = 0. See
    `Stage_1_geometry/decisions/root_section.md`.
13. **Loft built with pySpline, not `liftingSurface` itself.** Same construction, but one section
    parameter, so the nose split is exact (`liftingSurface` missed it by 0.2–0.5 % chord). The
    surfaces sit in a pyGeo object (IGES works). See `Stage_1_geometry/decisions/loft.md`.
14. **Twist between stations is not exactly linear** on straight panels (trailing edge differs by
    0.1–0.3 % chord from a linear-twist section). Straight panels win. See `Stage_1_geometry/decisions/loft.md`.
15. **Tip left open** (no cap surface), as `tip='none'`. **No STEP export** (pyGeo has none).
16. **BWB label threshold** root / outer-half mean chord lowered from **2.5 to 2.2**. Why: 2 of 1,500
    random BWB-range wings (the wide corner, root 1.1 m on 0.75 m semi-span) measure 2.39–2.5 with
    only 17–20 % root loss, so they failed both tests. Conventional wings reach at most 1.84;
    2.2 sits in the gap.
17. **Label rule details I fixed:** "sweep" for rectangular / straight tapered = quarter-chord
    sweep root to tip; a chord-slope kink also needs |dc/dy| · S / c_root ≥ 0.1 (else a flat
    chord counts as no slope); local dihedral from 200 even span steps; area = 2 ∫ c dy with the
    3-D chord.
18. **Hand-labelled set:** 20 wings in `geometry/tests/geometry/hand_labelled.yaml`. Two of my
    first vectors were wrong (aspect ratio 8.75, not < 8; outer sweep −7°, not 0); I fixed the
    vectors, not the labeller.
19. ~~**Every conventional training wing is "cranked"** (100/100).~~ **Decided 29 Oct 2026:** the
    generator must make tapered wings. New wing type `tapered` (one taper ratio, one sweep: straight
    edges, rectangular at taper 1). The cranked `conventional` type now reads its chord ratios per
    panel (`chord_law: per_panel`), so no chord is wider than the one inboard of it.
    See `Stage_1_geometry/decisions/planform_laws.md`. Open: the mixed shares (now BWB 0.5, cranked 0.25,
    tapered 0.25).
20. **3 BWB training wings are "forward swept"** (outer quarter-chord sweep ≤ −5°): leading edge
    aft, but the strong outer taper pulls the quarter-chord line forward. Real geometry, not a bug.
21. **Reference wing 5 = strongest washout** (Stage 1 brief); Stage 0 said "strongest twist".
    Same idea; Stage 0 text could be aligned.
22. **Set builds skip IGES** (46 MB instead of ~550 MB for 298 wings). Single builds write it.
    Built wing folders are not tracked; vectors and manifests are.
23. **Seeds:** training 1001 (BWB) / 1002 (conventional); hold-out 2001 / 2002; coverage 3001.

## Stage 1 additions — airfoil database and published wings

24. **Airfoil search order:** `Stage_1_geometry/airfoils/`, then the AERIS database, then the NACA
    4/5-digit formula. 2,159 of the 2,181 database files load; 22 are refused with a reason
    (odd formats). Keep this order?
25. **NACA 25118 is made from the formula** (classic open trailing edge, 0.38 % chord). BlendedNet
    built it in OpenVSP, which may close the edge differently. Confirm when the BlendedNet STEP
    files are available.
26. **NASA CRM is approximate:** four stations give chords exactly but twist only within 0.51°,
    and the sections are SC(2) stand-ins. A drag validation needs the real CRM sections and a
    mode with more stations. Add that mode, or leave CRM as a shape check only?
27. **BlendedNet twist and dihedral set to zero** (not stated in either paper).
28. **ONERA M6 and CRM are transonic** (Mach 0.84–0.85), outside phase 1. RIBES is the
    in-regime case (40 m/s, Re 1.43e6). Which wings to validate against first?
29. **RIBES section trailing edge** is 0.26 % chord after the fit, thinner than the 0.38–0.66 %
    measured on the model. Rebuild the section with the measured edge before a drag comparison?
30. ~~**Typo points in airfoil files are dropped**~~ **Decided 29 Oct 2026:** keep the automatic
    delete (one point off a smooth line; 18 database files, e.g. sc20412 lower x/c 0.73, about
    0.09 % chord off). Each dropped point is logged.
31. **Exact match to BlendedNet / CRM / RIBES is not proven yet.** The generator is proven to
    build exactly what its parameters say (errors < 0.003 % chord), and the M6 matches its CATIA
    model (max 0.011 % chord). For the others we need their own surface (one BlendedNet++ case
    STEP/VTK, CRM IGES, RIBES STEP) and run `verify.compare_points`.
32. **TE opening now follows pyGeo** (linear ramp over the last 10 % of chord, half up, half down,
    as `readAirfoilFile(bluntTe=True, bluntTaperRange=0.1)`). Replaces the uncited 65 % start.
    The sample sets in `data/sets/` must be rebuilt with pyGeo (`--all`): surfaces changed aft of 90 %.
33. **Middle Re level.** Levels now 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶. Move the middle level to about
    9.5 × 10⁵ (log-middle of 3 × 10⁵ and 3 × 10⁶), or keep 1.5 × 10⁶? Mini Class I wings fly at 1.2–2 × 10⁵ (eBee,
    Black Swift S0), below the low level: this is item 2 with numbers now.
34. **Class II, partly closed (29 Oct 2026).** Götten et al. 2021 (CEAS Aeronaut. J., Table 2) give
    wing areas for five Class II wings (150–230 kg; anonymised; from images and three-views, about
    10–15 % accuracy): mean chord 0.55–0.62 m, AR 7.8–16, Re ≤ 1.5 × 10⁶ at loiter. Conventional and
    tapered sizes widened to root chord 0.13–0.75 m, semi-span 2–7.5 root chords: every real wing with
    a tail, Class I and II, is now inside (span up to 11 m). Still open: tailless Class II (Fury 5.2 m,
    Albatroz 7 m, Shahed 191 7.3 m) have no area and stay outside.
35. ~~**Label for tailless wings without a centre body.**~~ **Decided 29 Oct 2026:** labelled
    `flying_wing` (tailless type, no measured centre body). Previously: All flying-wing-type wings and 17 % of
    bwb-type wings are labelled "conventional" (= no centre body). Previously: With the BWB span set in root chords (0.75–2.2), 14 % of
    bwb-type wings are slim flying wings that the label rule calls "conventional". Rename to
    "flying wing" for tailless types?
36. ~~**Aspect ratio of wings with a tail.**~~ **Decided 29 Oct 2026:** the aspect ratio is
    sampled (4.5–16.5 with a tail, 3–9 tailless); the semi-span is derived. Previously: Generated AR reaches 21 (99 % below 20); real wings with a
    known area reach 16.5. Cap AR (a gate, or narrower span ratio with taper), or accept?
37. **NTNU UAV database** (Hann & Wallisch, DataverseNO doi:10.18710/L41IGQ, CC0): 93 UAVs with span,
    AR and estimated chord. Blocked from the cloud workspace; attach 02_Database.csv to add it.
38. ~~**Moderate-taper swept flying wings are not covered.**~~ **Decided 29 Oct 2026:** new type
    `flying_wing`; the Aquila is now covered. Previously: The Lockheed Aquila (3.76 m span, mean
    chord 0.78 m, taper 0.58, LE sweep 28°, AR 4.9) fits neither type: the bwb type always tapers
    strongly (tip 8–20 % of the root), and the tapered type sweeps at most 20°. Add a swept flying-wing
    option (tapered type with sweep to about 30°, used with reflexed sections), or leave it out?
39. **Essari 2015 data source.** Hermes 450, Ranger, Seeker, Shadow 600, Doyosae and Pchela areas come
    from a PhD thesis whose chapter 2 data is "from (1) & (20)"; those references could not be read
    (Jane's-style). Hermes 450 is internally inconsistent (constant chord 0.69 m × 10.51 m = 7.25 m²,
    listed 6.90 m²). Confirm with Jane's before quoting in the paper.
40. **Unread leads.** Gundlach 2004 Virginia Tech dissertation, Table 10-7 "Shadow 200 Geometry
    Characteristics" (p. 166); Bray 1991 NPS thesis (Pioneer). Both need a manual download.
41. **Hash from the code (decided 29 Oct 2026).** The input hash uses the content of every geometry
    source file instead of the hand-set version string.
42. **Mixed shares (decided 29 Oct 2026).** Equal, 1/4 per type.
43. ~~**Smallest generated wings.**~~ **Decided 29 Oct 2026:** kept (micro Class I). Spans start at 0.4–0.6 m (small root chord with low AR); the
    smallest real wing with an area is 0.96 m; the Wasp (0.33 m, designation-systems.net) and Black Widow (0.15 m, AIAA 2001-0127) are smaller.
44. **pyGeo run pending.** Sets built with the numpy loft in the cloud; run `pytest` and
    `build --all` with pyGeo locally before Stage 2.
45. **Shape ranges from sources (decided 29 Oct 2026).** Every shape range and airfoil now has its source
    (`Stage_1_geometry/decisions/shape_ranges.md`). BWB airfoils MH 104 / MH 61 (was MH 91 / E374 / NLF1015);
    tailed sweep −5…15°, washout ≤ 5°, dihedral 0–5°. Open: check Raymer's taper and washout values
    in print; read PUL-10 and the flying-wing MAV papers directly. Layout shares remain our choice.
46. **Two spaces (decided 30 Oct 2026).** Full space = everything supported (sparse: 40 + 5 + corners
    per type); focus space = realistic (dense: 100 + 5 + 10). Full bounds from Pliakos et al. 2025 and
    the widest sourced values. Open: the full space reaches 20 m span and Re 7.6 × 10⁶ (BWB root):
    keep or cap?
47. **Closest prior work.** Pliakos et al. 2025 (AUTh) automate OpenVSP → ANSA → Fluent for UAV wings.
    The paper must state our difference. Their BWB airfoils and chords are paywalled.
48. **Re level 1 × 10⁵ (decided 30 Oct 2026).** Added below 3 × 10⁵ for mini Class I wings and outer
    panels. Open: the transition check (SU2 γ-Reθ on a few reference wings at 1 × 10⁵ and 3 × 10⁵)
    and the stricter mesh it needs (y+ ≤ 1, finer chordwise cells over the bubble).
49. **NTNU and CNAS databases added (31 Oct 2026).** NTNU (Hann et al., DataverseNO doi:10.18710/L41IGQ, CC0;
    file attached by Mike): 7 rows with an aspect ratio set ranges (area = span²/AR), 31 span-only rows.
    CNAS / Bard College Drone Database (drones.cnas.org): 14 span-only rows (no wing area there).
    Excluded: rotorcraft and tail-sitters, MTOW > 600 kg, jets and targets, munitions, parafoils, HAPS,
    and aircraft whose layout we could not tell from photos. Result: ScanEagle (tailless, AR 12.4) was
    outside, so the flying-wing focus AR is now 3–13 (full 2.5–14); real Re now 1.2 × 10⁵ – 3.1 × 10⁶
    (Aludra MK1 at its listed top speed). All 34 range wings covered, all 112 spans inside.
50. **Families and the focus cap (decided 31 Oct 2026).** Families tailless (bwb, flying_wing) and
    conventional (cranked, tapered); the type is set by our rules inside the family. Span words:
    full span b (tip to tip), semi-span S = b/2. Focus space capped at b = 7 m.
    See `Stage_1_geometry/decisions/families_and_span.md`. Open: cap the full space too?
51. **Flow dataset and the model rule (31 Oct 2026).** `cfdauto/flowmap`: XFOIL section tables
    (10 sections, free N_crit 9 and tripped, 14 Re × 3 Mach × 49 angles, 2,408 robust sweeps), one engine
    for the tool and the dataset, the dataset (400 focus wings × 4 section sets × 126 conditions = 201,600
    rows) and its analysis (trends, sensitivity, checks). Fully turbulent SA overestimates the profile drag
    by a median +55 % (10–90 %: +8 to +90 %), within ±10 % in 10 % of rows; in
    level flight +65 %. Below Re 1e5 the sign flips. The angle and speed set most of it;
    N_crit, induced angle, compressibility and strip count move the numbers, not the conclusion. See
    `Stage_1_geometry/decisions/flow_maps.md`. Open: transition model in the pipeline (SU2 γ-Reθ for drag, ADflow
    SA for mesh studies); the SA rule (|error| < 10 % and laminar run < 20 % chord, our choice); the tool's
    default N_crit; the level-flight band; a 3-D check of the strips before quoting numbers in the paper.
52. **Logic check of the geometry and flow work (1 Nov 2026).** Decide before the mesh module: (a) the model plan.
    What a mesh must resolve depends on the turbulence model, so "SA for mesh studies, the model does not matter"
    was wrong: start with SA (ADflow) on a transition-ready mesh (y+ <= 1 per station, fine chordwise cells over
    30–70 % chord) and repeat a reduced mesh study with the transition model on 2–3 reference wings. (b) The SA
    inflow eddy viscosity (nu~/nu about 3), so SA is really fully turbulent. Also: sweep and aspect ratio do not
    enter the 2-D strips, so keep them fully sampled; the SA error is an upper bound for real (rough, gusty,
    propeller-washed) wings; SA mis-ranks airfoils. See `Stage_1_geometry/decisions/flow_maps.md`, "Logic check". Independent review
    (same day) added: (c) make the induced angle the baseline of the flow tool and re-run (the baseline's high-angle
    trends, TE separation at 10 deg and "SA adequate at 10 deg" were artefacts); (d) D1 (2 counts) is a numerical
    target only: SA's error on drag differences between similar wings is 4-5 counts median, so a drag dataset meant to
    rank wings needs transition-model results at least on a calibration subset; (e) the mesh transition band is upper
    10-85 % c and lower 60-100 % c, not 30-70 %.
53. **Flow baseline corrected (2 Nov 2026).** The flow tool and dataset now include a uniform (elliptic)
    induced angle (`engine.evaluate`, default; `--no-induced` is the old check). Also: "no XFOIL answer" instead
    of "beyond 2-D stall"; the NACA set on tailless wings tagged (cannot trim) and left out of the statistics;
    sections coded by airfoil set and a test split by wing in the sensitivity; bubble flags never averaged.
    New numbers: SA profile-drag error median +62 % (level flight +69 %, within +-10 % in 4 %), +40 % at 10 deg;
    TE separation 1-2 % of the half wing up to 10 deg; SA adequate 2 % of rows; similar-wing pairs: 4 counts
    median error on the drag difference, above 2 counts in 71 %. Open: retry failed XFOIL points; a
    vortex-lattice span loading instead of the uniform downwash; decisions 52 (a)-(e) stand.
54. **Model plan deferred (Mike, 2 Nov 2026).** The turbulence-model choice (52 a) and the SA inflow value (52 b)
    are made in a later stage. Until then the mesh is built transition-ready (y+ <= 1 per station, transition
    band upper 10-85 % c, lower 60-100 % c), so both options stay open. Mike also owes: the pyGeo tests and set
    rebuild on his machine; push the raw XFOIL data (33 MB) or accept the 40-minute rebuild.
55. **Checks of the flow results (Mike, 2 Nov 2026).** None is needed before the mesh stage: the mesh rules come from
    ranges (0-10 deg, all section sets), which the checks would not move. Needed before the paper quotes flow numbers:
    the 3-D transition-model check on 2-3 reference wings (BWB centre body first), the first runs of the mesh stage.
    Only if the paper states SA's error as a number: 2-D SA against tripped XFOIL (Re 1e5, 3e5, 1.5e6; about 1 day).
    Optional: retry the failed XFOIL points (0.4 % of cases), the hinge-line case, a vortex-lattice span loading, a
    source for the crossflow threshold, E387 against wind-tunnel data. Mesh rule added: on swept panels the upper
    transition band starts at the leading edge (crossflow transition, which the 2-D strips cannot see, starts there).
    Also corrected (L14): the first wall cell is set from each case's speed and changes only about 20 % along the
    span; the per-station need is enough wall layers at the root. Handover to the surface-mesh stage: summary
    section 9 and the project doc "Stage_1 Handover to the surface mesh".

## Stage 2 (surface mesh) — choices I made (2 Nov 2026)

56. **Cells per bubble: 20 at level C** (Ansys CFX Modeling Guide, gamma-Re_theta grid requirements: at least
    20 nodes across a laminar separation bubble; 75–100 streamwise nodes; y+ about 1; wall-normal growth about
    1.1). Bubble length from the Stage 1 XFOIL table at the local Re (0.40 c at 6e4 ... 0.05 c at and above 1e6).
    Cost: ring of about 200 nodes at Re 1e5, 400 at 3e5, 850 at and above 1.5e6 (S8: 150). Open: whether the
    coarse level needs the full 20 (the T6 chordwise ladder decides); the bubble length above 1e6 is a floor
    (Stage 1 says "under 0.05 c"). See `Stage_2_surface_mesh/decisions/surface_rules.md`.
57. **Wall-normal growth for a transition model: 1.1, not 1.25.** The same guide says 1.2 already moves
    transition a little upstream. Stage 0 and the handover say 1.25. Decide in Stage 3 (volume mesh); it changes
    the layer count, not the surface.
58. **The upper transition band starts at the leading edge on every wing** (Stage 1: from 10 % c, from the
    leading edge on panels swept over about 25°). One rule, about 10 % of the chord more at band spacing.
59. **One surface per wing and Re level**; the mesh name is `mesh_<level>_<wing_hash8>_re<Re>` (the Stage 0
    name plus the Re on the mean chord). The tip gap (s0) and the band cell depend on Re. Building one takes
    3–6 s.
60. **Both sides of a ring share one node distribution** (in arc fraction; the stricter side wins), so the tip
    cap's cross lines stay upright. Different distributions per side collapsed the cap quads (scaled Jacobian
    0.03). About 5–10 % more ring nodes.
61. **Base cells per level: 8, 10, 14, 18** (even, so the cap's nose arc stays centred): ratios 1.25, 1.4,
    1.29 instead of 1.3. The one spacing that does not follow the family ratio exactly; reported, not hidden.
62. **Station gap 0.2 × local chord, at least 12 gaps per panel, growth 1.2 inside a panel** (checked limit
    1.3 between any two gaps, because each panel holds a whole number of gaps). Our starting values, to be
    tested in the spanwise ladder (law 8).
63. **Largest cell outside the bands 2 % c** (our choice). On most stations the band covers so much of the
    ring that it hardly applies (upper 85–100 % c only).
64. **Stage 1 finding (from the mesher, 2 Nov 2026): the nose of the built sections is not round.** The
    resampled sections' nose radius differs between the upper and lower side by 3-13 x on cambered sections
    with small noses (NACA 4415: formula 0.0248 c, built 0.008 c upper / 0.074 c lower; E387 0.0102 c raw,
    0.0028 / 0.0353 built), within the first ~0.1 % of the chord. The mesh follows the loft, so the surface
    mesh is right for the wing as built; the wing's nose is not the airfoil's. Decide: fix in Stage 1
    (resample the nose in arc length or fit the apex from the raw points; every geometry hash changes) before
    the first solves, or carry it as a stated geometry deviation. See
    `Stage_2_surface_mesh/decisions/surface_rules.md`, section 10, and `data/studies/nose_radius.json`.
65. **Per-wing transition band from the flow dataset (candidate, 3 Nov 2026).** `cfdauto/mesh/refine_map.py`
    reads the Stage 1 section tables through the flow-map engine for one wing on a Mach × angle grid and builds,
    per strip and side, the envelope of (bubble start … bubble end, transition ± margin, separation start)
    over the conditions the mesh must serve. Interactive page: `Stage_2_surface_mesh/docs/REFINE_MAP.html`
    (`scripts/refine_map_data.py`, `scripts/make_refine_page.py`). What the 20 reference wings show at
    Mach 0.03–0.13, 0–8°, margin 10 % c: the per-wing band is about as many cells as the generic one (the BWB
    reference wing 0: 5,655 against 5,627 at Mach 0.08), but sits elsewhere: on washed-out outboard panels
    the upper-surface transition lies beyond 85 % c at low angle and the lower surface transitions near the
    leading edge, which the generic band misses (BWB 0: 15 % c on the upper side, 60 % c on the lower).
    The dataset's shortest root bubbles (about 1.5 % c at Re above 10⁶) are shorter than the band-cell
    table assumes (5 % c), so 20 cells per bubble is not met at the root by either band. Decide: keep the
    generic band (cheap, covers crossflow at the leading edge, no 3-D check needed) or switch to the
    per-wing envelope with a margin after a 3-D transition check (γ-Re_θ in SU2 on a few wings). Not a rule yet.
66. **Upgrade the flow dataset with AVL and NeuralFoil (proposal, 3 Nov 2026).** Today: 2-D XFOIL strips with
    one uniform induced angle (elliptic) for the whole wing, section tables with trilinear lookup, blends
    of the parents' answers between sections, 1.5–4 % failed XFOIL points filled. AVL would give the
    spanwise lift distribution (local angle per strip with sweep, taper and twist) in seconds; NeuralFoil
    would give each strip's 2-D answer in milliseconds on the exact blended section, never failing, with
    the transition location (MAE 0.007–0.044 x/c against XFOIL) and the boundary-layer shape factor at 64
    points per surface, from which separation and reattachment can be read. Neither adds 3-D transition
    physics (crossflow, tip relief); NeuralFoil inherits XFOIL's model and adds a fit error, and its 64 points
    (1.6 % c apart) cannot measure bubbles shorter than about 3 % c. Decide: build the quasi-3D loop
    (AVL downwash ↔ NeuralFoil strip lift) as flow-map method "avl+nf", validate against the existing tables
    on a sample and against a few 3-D transition RANS runs, then revisit decision 65.

## The new approach — decided 4–6 Nov 2026 (owner), not built yet

What was first is items 56–66 (every surface rule met at level C). Pages: `Stage_2_surface_mesh/docs/SURFACE_MESH.html`
(section "What was first, and what changes"), `Stage_2_surface_mesh/decisions/STAGE2_STATUS.md`.

67. **Transition must be captured, with ADflow and SU2** (owner, 4 Nov). Stage 1: SA overpredicts the profile
    drag by a median +62 %. Which solver does what: 76.
68. **Mach toward 0.5, no supersonic flow** (owner, 4 Nov). The Stage 1 data stop at Mach 0.2. Pending: core
    Mach ≤ 0.2 now, 0.3–0.5 later with a fast-UAV family. Under similarity (70) the dataset runs at Mach 0.1.
69. **Angles of attack −5° to post-stall** (owner, 6 Nov), plus a separate post-stall study (URANS or DDES on a
    few wings); steady RANS up to stall onset. The Stage 1 dataset covers root angles 0–10°.
70. **Similarity** (owner, 6 Nov): every wing at unit mean chord; the Re on the mean chord is an input (4 levels);
    Mach 0.1 with a Prandtl–Glauert correction on CL and CM; trailing edge 0.2 % c; the root chord leaves the
    vector (18 → 17 numbers). About 5 × fewer solves (8,000, not 42,000). Checks C1 (scale), C2 (Mach), C3
    (trailing edge, with the real floor 0.42 % c), C4 (Re levels). Stage 1 code first; every hash changes.
71. **Levels VC, C, M, F with the targets anchored** (owner, 6 Nov): hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25,
    base ≥ 8, no kinks, tip gap); accuracy targets at M (nose 10°, trailing edge 0.1 % c, station gap, largest
    cell), as DPW defines its medium grid; transition targets at F (20 cells per bubble; wall growth ≈ 1.1).
    VC on the desktop (about 1.0 M cells median, desktop limit about 1.2 M); C, M, F on the university HPC.
    Replaces "at level C" in 56 and settles 57 at F (1.25 at VC is 1.107 at F).
72. **Lighter rules** (owner, 6 Nov): the bubble-length table stops at 0.10 c from local Re 4 × 10⁵ up (band cell
    0.5 % c at F); tip gap 2 × s0; station gap 0.25 × local chord at M (replaces 62's 0.2 × chord at C).
    Fine level about 10–11 M cells median on the wing blocks (10.9 M with the band change alone; 15.2 M with
    the planned rules). Cost of the choice: the shortest high-Re root bubbles (about 1.5 % c) get about 3 cells.
73. **One matched C-H volume mesh for ADflow and SU2** (owner, 6 Nov), instead of the overset wake box and the
    tip-vortex tube. SU2 8.6.0 has no overset and refuses structured CGNS (structured meshes converted to
    unstructured hexes run). The ring and the cap of Stage 2 stay; Stage 3: open-line march, wake lines to the
    far field (rough +30–60 % cells on the wing blocks), tip vortex in the outboard blocks, no overlap gate.
74. **Lower band at negative angles** (pending): option A, the lower band from the leading edge (band length
    125 → 185 % of the chord, each side counted alone); option B, keep 60–100 % c and run transition (LM) only at
    angles ≥ 0°. **Counted on 7 Nov** (Stage 2 Study 8; `scripts/band_count.py`, `data/studies/band_count.json`):
    the 20 reference wings × 4 Re levels at VC with the planned rules (`configs/surface_plan_VC.yaml`), 160 builds.
    A and B give the same ring, node for node (ratio A / B 1.000, median and max; the same at F on two wings), so
    F stays at about 10.9 M cells (median, wing blocks) with A. Why: both sides share one node list (60), and the
    upper band (0–85 % c) already makes the front of the lower side fine. A per-wing lower band from the refine map
    (A′, −5° to 8°, 10 % c margin) is the same as A: its union over the strips starts at 0 % c on all 20 wings.
    The refine map from −5° puts the lower transition at a median of 1–15 % c per type at −5°, in front of 60 % c
    on every strip with an answer (at 0° on 51–83 %); 42 % (BWB) and 30 % (flying wing) of the strips have no
    answer at −5°. The cells no longer decide: A keeps transition runs from −5° at no mesh cost; B only saves the
    LM runs below 0°. Still pending: the owner chooses.
75. **Nose (64), corrected** (6 Nov): the first reading was overstated (raw files measured the same way show
    nearly the same split). Re-measure raw and built with one curvature method; fix only if a real error remains,
    before the pyGeo `build --all` (a fix changes every hash). Plan agreed 6 Nov.
76. **Solver split** (proposal, pending): ADflow SA for the mesh studies and the fully turbulent data; SU2 SST +
    LM on about 20 % of the wings. Needs an ADflow against SU2 SA code-to-code check and the SU2 cost per solve.

