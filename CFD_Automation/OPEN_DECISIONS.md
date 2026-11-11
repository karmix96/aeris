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
33. ~~**Middle Re level.** Levels now 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶. Move the middle level to about
    9.5 × 10⁵ (log-middle of 3 × 10⁵ and 3 × 10⁶), or keep 1.5 × 10⁶? Mini Class I wings fly at 1.2–2 × 10⁵ (eBee,
    Black Swift S0), below the low level: this is item 2 with numbers now.~~ **Decided 8 Nov 2026 (78):** 1 × 10⁶.
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
44. **pyGeo run: done on Mike's machine (8 Nov).** pyGeo tests 24 of 24 (the pyGeo and numpy lofts agree within
    10⁻⁶ chord on the 7 published wings), Stage 1 tests 204 (1 skipped), `build --all` with pyGeo 722 of 722 (same
    input hashes and pass/fail as the numpy loft; manifests pushed, they now say pygeo), Stage 2 tests 41. Meshes of
    the 20 reference wings on the pyGeo loft: at VC, old levels, the same counts and every check value within
    6 × 10⁻¹⁰ (`Stage_2_surface_mesh/data/studies/screen_VC_pygeo_oldlevels.json`); at the new levels, VC and F,
    80 of 80 pass each with the same ring nodes and stations. The node hashes differ (round-off). One label differed
    (79, fixed 8 Nov; that fix changed every input hash, so the manifests were the numpy rebuild until Mike's next
    pyGeo `build --all`: done 11 Nov, see 79).
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
    rebuild on his machine (done 8 Nov, see 44); push the raw XFOIL data (33 MB) or accept the 40-minute rebuild. **Done 9 Nov:** the 2,752 sweeps are in git as
    `Stage_1_geometry/data/section_cache.tar.gz` (1.4 MB); unpacked, `tables --assemble` rebuilds the 46 tables exactly.
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
    (Stage 1 says "under 0.05 c"). See `Stage_2_surface_mesh/decisions/surface_rules.md`. **Replaced by 71 and 72
    (built 7 Nov):** 20 at F (9.1 at VC), and the bubble length stops at 0.10 c from local Re 4e5.
57. **Wall-normal growth for a transition model: 1.1, not 1.25.** The same guide says 1.2 already moves
    transition a little upstream. Stage 0 and the handover say 1.25. Decide in Stage 3 (volume mesh); it changes
    the layer count, not the surface. **Settled by 71:** 1.25 at VC is 1.107 at F, just above the 1.1 (1.23 at VC
    would give exactly 1.1).
58. **The upper transition band starts at the leading edge on every wing** (Stage 1: from 10 % c, from the
    leading edge on panels swept over about 25°). One rule, about 10 % of the chord more at band spacing.
    **7 Nov:** it is written 0–85 % c, but as built the upper side gets band-size cells to the trailing edge too
    (one node list, 60, and the lower band 0–100 % c, 74); at the Re levels the upper transition sits past 85 % c at
    low Re (65). Writing it as 0–100 % c is for the owner to decide: the same mesh at VC to round-off (80 of 80
    reference builds), 2 more ring nodes at F on 42 of 80 (+0.39 % cells median), and a re-run of the screen (about
    1.5 h; `Stage_2_surface_mesh/data/studies/upper_band_check.json`). **8 Nov: written 0–100 % c (owner)**; Study 12
    confirms it on the reference wings and finds, on every set, 2 more ring nodes on VC 44 of 782 and F 383 of 782
    meshes, cells at most +1.1 %.
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
    tested in the spanwise ladder (law 8). **Replaced by 72 (built 7 Nov):** 0.25 × local chord at M, at least 12
    gaps per panel at M; the growth 1.2 kept (see 77).
63. **Largest cell outside the bands 2 % c** (our choice). On most stations the band covers so much of the
    ring that it hardly applies (first: upper 85–100 % c only; with the lower band 0–100 % c and one node list, only
    where the band cell is coarser than it, at low local Re).
64. **Stage 1 finding (from the mesher, 2 Nov 2026): the nose of the built sections is not round.** The
    resampled sections' nose radius differs between the upper and lower side by 3-13 x on cambered sections
    with small noses (NACA 4415: formula 0.0248 c, built 0.008 c upper / 0.074 c lower; E387 0.0102 c raw,
    0.0028 / 0.0353 built), within the first ~0.1 % of the chord. The mesh follows the loft, so the surface
    mesh is right for the wing as built; the wing's nose is not the airfoil's. Decide: fix in Stage 1
    (resample the nose in arc length or fit the apex from the raw points; every geometry hash changes) before
    the first solves, or carry it as a stated geometry deviation. See
    `Stage_2_surface_mesh/decisions/surface_rules.md`, section 10, and `data/studies/nose_radius.json`.
    **Decided 7 Nov 2026 (owner): fixed in Stage 1.** A study with one curvature method
    (`Stage_1_geometry/decisions/nose_curvature.md`, `data/studies/nose_curvature.json`, `docs/nose_curvature.png`)
    found the defect real: the old rule put the leading edge at the farthest raw point and made a curvature spike
    on one side and a flat spot on the other, between the raw points; on NACA 4415 a 0.18 % c nose cell turned
    9.47° built against 4.31° true; the old built nose failed a 5 % test on all ten suggested airfoils. New rule:
    one cubic spline, the leading edge at its apex, 201 points per side; a gate refuses 14 database files whose
    nose folds back; 95.6 % of the database passes (21.0 % before). Built; the sets rebuilt (every hash changed).
    The 6 Nov correction (75) was wrong. In the mesh (Stage 2 Study 4, first rules at C, the same shapes): the
    NACA 4415 / 4412 wings get a nose cell of 0.245–0.265 % c instead of 0.178 % c. The flat part of the nose solve
    at about 7° stays (growth-limited cells 1.9–2.4 % c down the lower side; the true airfoil does the same,
    6.0–6.8°), so the window search stays.
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
    **7 Nov: the refine map at the Re levels** (similarity; `Stage_2_surface_mesh/decisions/refine_map_re.md`,
    `scripts/refine_map_re.py`, `data/studies/refine_map_re.json`; Stage 2 Study 11): the 20 new reference wings at
    the four Re levels, −5° to 12°, the section tables rebuilt on the fixed nose. The lower band 0–100 % c holds every
    strip. The upper band as written (0–85 % c) holds only 0–49 % of the strips at Re 10⁵ and 3 × 10⁵, short by up to
    15 % c (the transition itself, never a bubble or separation), and 32–97 % at 1.5 × 10⁶ and 3 × 10⁶. As built this
    is no gap: on 16 built surfaces at VC the largest upper cell over 85–99.5 % c is 0.950–0.995 × the band cell (one
    node list, 60). The written band stays 0–85 % c (58). No XFOIL answer only on the tailless wings at negative root
    angles (up to 46 % BWB and 43 % flying-wing strips at −5°). Still a candidate: the 3-D check comes first.
    **8 Nov (owner): the upper band is written 0–100 % c** (`configs/surface.yaml`), so the written rule says what the
    mesh does; the cost was measured on 7 Nov (the same mesh at VC, +2 ring nodes at F on 42 of 80 reference builds,
    +0.39 % cells). Built and screened in the family screen (80; Stage 2 Study 12): on every set, 2 more ring nodes
    on VC 44 of 782 and F 383 of 782 meshes (the reference wings as measured on 7 Nov), cells at most +1.1 %.
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

## The new approach — decided 4–7 Nov 2026 (owner); the surface rules, the nose fix and similarity built 7 Nov

What was first is items 56–66 (every surface rule met at level C). Pages: `Stage_2_surface_mesh/docs/SURFACE_MESH.html`
(section "What was first, and what changes"), `Stage_2_surface_mesh/decisions/STAGE2_STATUS.md`. Built on 7 Nov:
64 (Stage 1), 70 (Stage 1), 71, 72 and 74 (Stage 2, `Stage_2_surface_mesh/decisions/surface_rules.md` section 13);
screened (Stage 2 Study 9). Not built: 73 (Stage 3).

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
    **Built in Stage 1 on 7 Nov:** unit mean chord (area / full span), 17 numbers, trailing edge 0.2 % c, no 7 m full-span cap;
    the sets rebuilt (722 of 722); 13 of the 20 reference wings are new picks. Stage 2 check (Study 10): the 20 old
    reference shapes at unit mean chord, 80 of 80 meshed; the same ring nodes on 80 of 80 (size changes nothing);
    6–27 fewer stations on the 8 wings that had a switch section; the cap quality falls where the old floor had
    thickened small tips (most 0.345 → 0.133; lowest 0.112, limit 0.05). The Re levels stay 1e5, 3e5, 1.5e6, 3e6:
    1e5 is 18 % below the slowest real UAV (1.22e5 on area / full span), kept as a margin (owner, 7 Nov).
71. **Levels VC, C, M, F with the targets anchored** (owner, 6 Nov): hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25,
    base ≥ 8, no kinks, tip gap); accuracy targets at M (nose 10°, trailing edge 0.1 % c, station gap, largest
    cell), as DPW defines its medium grid; transition targets at F (20 cells per bubble; wall growth 1.107 at F,
    just above the 1.1 a transition model asks for). VC on the desktop (16 GB: about 1.2 M cells; VC has 0.70 M
    median on the wing blocks in Study 9); C, M, F on the university HPC. Replaces "at level C" in 56 and settles 57
    at F (1.25 at VC gives 1.107 at F).
    **Built 7 Nov** (`configs/surface.yaml`, `cfdauto/mesh/laws.py`; the first approach kept in
    `configs/surface_first.yaml`); screened on the rebuilt sets (Stage 2 Study 9): 1,724 of 1,724 builds
    passed; F 6.9 M cells median on the wing blocks (20 reference wings × 4 Re), below the 9–11 M asked. On 8 Nov
    every set at every level (Study 12): 3,128 of 3,128; F 6.73 M median on the reference wings at the new Re levels.
    The pages use this count, because its rule is written down and it can be redone (n = the largest over the
    stations of ceil(ln(1 + (g − 1) D / s0) / ln g); D = 2 local chords; g = 1.25, 1.187, 1.141, 1.107 at VC, C, M, F;
    s0 from y⁺ = 1, 0.77, 0.59, 0.46 at each station's local Re). The first estimate (6 Nov) gave 10.9 M; its
    wall-layer rule was not recorded, and it used the first-approach reference wings. Both leave out the C-H wake
    lines (a rough +30–60 %); Stage 3 sets the real wall-layer rule. The nose: solved at every level, the strictest
    wins (owner, 7 Nov). Two builder choices left: 77.
72. **Lighter rules** (owner, 6 Nov): the bubble-length table stops at 0.10 c from local Re 4 × 10⁵ up (band cell
    0.5 % c at F); tip gap 2 × s0; station gap 0.25 × local chord at M (replaces 62's 0.2 × chord at C).
    Fine level about 10–11 M cells median on the wing blocks (10.9 M with the band change alone; 15.2 M with
    the planned rules; the first estimates, 6 Nov, wall-layer rule not recorded; the count of the built rules: 71).
    Cost of the choice: the shortest high-Re root bubbles (about 1.5 % c) get about 3 cells. **Built 7 Nov**; measured F: see 71.
73. **One matched C-H volume mesh for ADflow and SU2** (owner, 6 Nov), instead of the overset wake box and the
    tip-vortex tube. SU2 8.6.0 has no overset and refuses structured CGNS (structured meshes converted to
    unstructured hexes run). The ring and the cap of Stage 2 stay; Stage 3: open-line march, wake lines to the
    far field (rough +30–60 % cells on the wing blocks), tip vortex in the outboard blocks, no overlap gate.
    **Owner, 9 Nov 2026: the overset plan is kept** as a fallback (ADflow only, if a C-H mesh cannot pass its
    checks on a wing; SU2 has no overset) and for future work (several bodies, moving parts). Not built; its
    values stay in the Primer and Annex G as the fallback's starting values.
74. **Lower band at negative angles — decided 7 Nov 2026 (owner): option A, from the leading edge (0–100 % c); built
    in `configs/surface.yaml`.** It costs no cells (both sides of a ring share one node list). The record: option A,
    the lower band from the leading edge (band length
    125 → 185 % of the chord, each side counted alone); option B, keep 60–100 % c and run transition (LM) only at
    angles ≥ 0°. **Counted on 7 Nov** (Stage 2 Study 8; `scripts/band_count.py`, `data/studies/band_count.json`):
    the 20 reference wings × 4 Re levels at VC with the planned rules (`configs/surface_plan_VC.yaml`), 160 builds.
    A and B give the same ring, node for node (ratio A / B 1.000, median and max; the same at F on two wings), so
    F stays at about 10.9 M cells (median, wing blocks; the 6 Nov estimate) with A. Why: both sides share one node list (60), and the
    upper band (0–85 % c) already makes the front of the lower side fine (and the lower band, in turn, gives the upper
    side band-size cells over 85–100 % c: 58). A per-wing lower band from the refine map
    (A′, −5° to 8°, 10 % c margin) is the same as A: its union over the strips starts at 0 % c on all 20 wings.
    The refine map from −5° puts the lower transition at a median of 1–15 % c per type at −5°, in front of 60 % c
    on every strip with an answer (at 0° on 51–83 %); 42 % (BWB) and 30 % (flying wing) of the strips have no
    answer at −5°. The cells no longer decide: A keeps transition runs from −5° at no mesh cost; B only saves the
    LM runs below 0°. The owner chose A on 7 Nov.
75. ~~**Nose (64), corrected** (6 Nov): the first reading was overstated (raw files measured the same way show
    nearly the same split).~~ **Superseded 7 Nov: the correction was wrong.** It compared built and raw only at the
    raw points, where they agree by construction; the defect sat between them. The re-measure with one curvature
    method (the plan agreed on 6 Nov) found it real, and it was fixed (64).
76. **Solver split** (proposal, pending): ADflow SA for the mesh studies and the fully turbulent data; SU2 SST +
    LM on about 20 % of the wings. Needs an ADflow against SU2 SA code-to-code check and the SU2 cost per solve.
    **The band stays on for both solvers (81; owner, 9 Nov 2026):** the fully turbulent runs use the same meshes as
    the transition runs (about 1.8–1.9 × the cells they would need at Re ≥ 3 × 10⁵).
77. **Builder choices in the built rules (7 Nov).** All are stricter than decided; numbered as in
    `Stage_2_surface_mesh/decisions/surface_rules.md`, section 13. (1) The growth limits follow the family rule:
    along the ring 1.25 at VC (decided) gives 1.107 at F; between station gaps 1.3 at VC (not in 71–72) gives 1.127
    at F; the kink check uses each level's turning limit. **Confirmed by the owner (8 Nov).** (2) **The nose — answered
    7 Nov (owner): solved at every level, the strictest wins.** First it was solved at VC and at F only, and the
    smaller spacing won. On the rebuilt sets M then needed one repair (nose × 0.9) on all 20 flying-wing reference
    builds, because F's spacing × 1.3 turned those noses just past M's 10.02°; the nose cell then stepped by 1.44
    from C to M and 1.17 from M to F instead of 1.3. Now each level solves its own angle on its own ring, the
    finest first; a coarser level is solved only where the finer answer misses its angle; the smallest spacing wins,
    and every level takes it ÷ 1.3^k. On the 20 reference wings × 4 Re × 4 levels (Stage 2 Study 9): 80 of 320
    builds changed, all of them flying-wing builds (the BWB, cranked and tapered builds are the same node for node); nose repairs 20
    → 0 (on the full sets 4 of 782 F builds still needed one round: the solve measures each
    station's own ring, the check the shared node list); the nose cell refines by 1.297–1.302 per step. The cost: VC, C and M get a finer nose than
    their own angle asks (VC 14.6–16.1° against 16.9°). (3) The station growth stays 1.2 and the gaps per panel 12
    at M (8 at VC), as decided; the plan file of Study 8 used 1.25 and 7 gaps per panel, so the built rules have
    7–14 more stations (about +17 %, so about 17 % more cells). If the plan file's values were meant, they need a
    decision. **Confirmed by the owner (8 Nov): the decided values stand** (growth 1.2, at least 12 gaps per panel at
    M). See `surface_rules.md`, sections 13–14.
78. **Re levels 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶** (owner, 8 Nov 2026; were 1 × 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶).
    (1) The Greek tactical BWB programmes are in scope (LOTUS, Archytas, and ACTUS, the EDF project that develops
    LOTUS and the Safran Patroller): 4 × 10⁶ covers all their cruise points and the 6–7 m versions at top speed;
    LOTUS 11 m and the Patroller at top speed (4.9–6.3 × 10⁶) are extrapolations; no wing area is published, so
    their Re rests on AR 8 (`Stage_1_geometry/configs/greek_uavs.yaml`, `scripts/greek_uavs.py`). (2) Check C4 on
    2-D data (`Stage_1_geometry/scripts/re_ladder_check.py`): with transition, drag read between the levels is off by
    8.8 % instead of 16.9 % at 6 × 10⁵ (90th percentile), but 6.8–7.0 % instead of 2.5–3.7 % between 1 × 10⁶ and
    4 × 10⁶; fully turbulent 0.4–0.8 % throughout. (3) Same 8,000 solves; screened on 8 Nov (320 of 320 reference
    builds pass): at F −0.7 % cells on the two moved levels; the largest F wing-block mesh 10.17 M cells (was 9.74 M),
    1.7 % above 10 M. The 2-D section tables gain the rows 1 × 10⁷ and 1.5 × 10⁷.
    Closes 33 and the 2-D part of C4 (70); the solver check of C4 is still to run. The code reads the levels from
    Stage 0 `values.yaml` (`cfdauto.paths.re_levels()`); the studies run at the old levels keep their own as records.
    (4) No 5th level (Mike, 8 Nov): the levels stay as they are; LOTUS 11 m and the Patroller at top speed stay
    extrapolations.
79. **Label rules at a threshold (Mike: fix it; built 8 Nov 2026).** The pyGeo and numpy lofts give the same labels on 721 of 722
    wings. BWB corner1 #8 changes its leading-edge sweep by exactly 5° at the outer break (35° → 30°), the kink
    threshold: the numpy loft measures 4.999999999999993° (no kink, no "cranked" label), pyGeo gives the label. The two
    kink tests (sweep change, chord slope) have no tolerance, unlike the twist, sweep and dihedral rules (EPS 10⁻⁹: a
    designed value at a threshold must get the label). On the numpy loft 29 wings sit on the kink-sweep threshold and
    7 on the kink-chord threshold (margins about ±10⁻¹⁴), so round-off decides their label. And the flying-wing
    reference wing 0, designed at AR exactly 8, misses "high_aspect_ratio" on both lofts: its measured AR is
    7.99999998 (area error about 3 × 10⁻⁹), beyond EPS. Effect: labels only (no type changes, no geometry, no mesh).
    Proposed fix: EPS on the two kink tests, a tolerance of 10⁻⁶ (relative) on the AR tests. Checked on the numpy
    loft: it changes 2 labels (corner1 #8 gains "cranked", as with pyGeo; reference wing 0 gains
    "high_aspect_ratio"). Every geometry hash changes with it: one more `build --all` on both machines; the meshes
    stay the same. **Built (8 Nov):** EPS on every label threshold (the kink, BWB, straight and rectangular tests had
    none), AR_TOL 10⁻⁶ on the AR tests; `test_measure_labels.py` pins both wings (it fails on the old rule). Rebuilt
    with the numpy loft: 722 of 722; the code hash aa6ccb5d → 51e670d2, so every input hash changed; the surface
    hashes equal the 7 Nov build on all 722; the labels changed on exactly the 2 wings (now equal to pyGeo's on 721,
    and on the 722nd pyGeo gets the same new label). The meshes are the same: the mesher reads only the loft (5 builds
    re-meshed at VC, both relabelled wings among them: the same node hashes). **Done on Mike's machine, 11 Nov
    (commit de64aa57):** pyGeo `build --all` 722 of 722; against the numpy manifests only two things changed, the
    backend label and the surface hash (it includes the backend name): the input hashes, the pass flags and the labels
    are equal on all 722, so the label fix holds on both lofts. Stage 1 tests 203 passed, 3 skipped (XFOIL not
    installed; every pyGeo test ran). The hold-outs got the label only, none built.
80. **The nose repair belongs to the family (owner, 8 Nov 2026).** The ratio between levels stays exactly 1.3, also
    when a nose repair is needed, and a repaired mesh is labelled. Built: a repair round (every station's nose spacing
    × 0.9) is needed only where a ring turns past its level's check limit (the angle + 0.2°; before, the solve's own
    tolerance of 0.02°, which triggered 4 of 782 F builds at 0.003–0.006° over); `build_family` builds every level of
    one wing at one Re with one factor (0.9^n, n the most rounds any level needed), so every spacing refines by
    exactly 1.3; every mesh carries `nose_repair` and `nose_family` (the factor, the rounds, the levels that needed
    them, the label) in `quality.json` and `manifest.json`. A test forces a repair and checks that the factor goes
    on every level with the ratio exact. Screened: Stage 2 Study 12 (the family screen, every set at VC, C, M, F):
    3,128 of 3,128 builds pass (782 families × 4 levels), 0 families needed a repair, every family carries one factor
    at every level, all labelled "none"; the largest turning stays inside every check limit (M 10.02°, F 7.72°).
    The upper band at 0–100 % c added 2 ring nodes on some meshes (VC 44 of 782, F 383 of 782; cells at most +1.1 %).
81. **The transition band is an option (owner, 9 Nov 2026), chosen right before the runs together with the solver
    (76).** On: the band cells everywhere (0–100 % c on both sides), for runs with a transition model (SU2 SST + LM).
    Off: no band, the largest-cell rule only, for fully turbulent runs (ADflow SA); every other rule the same. Built:
    `chord.transition_band` in `configs/surface.yaml` (default true), `--band on|off` on `python -m cfdauto.mesh` and
    `scripts/screen.py`; with the band off the mesh name ends in `_noband` and the manifest says
    `transition_band: false`; 2 tests. Measured (Stage 2 Study 13, the 20 reference wings × 4 Re × VC, C, M, F, one
    nose factor per family): cells with the band ÷ without = 1.08–1.09 at Re 1e5, 1.79–1.83 at 3e5, 1.87–1.91 at 1e6
    and 4e6 (median per level); largest F 10.21 M on, 5.60 M off. The band-on meshes are unchanged (the same nodes).
    **Weak point: with the band off, every BWB reference wing fails at M** (20 of 320 builds; the tip cap, scaled
    Jacobian 0.0495 against the limit 0.05; 0.057–0.077 with the band on). More cap smoothing does not help (the worst cell
    sits on the cap's edge near the trailing edge). To fix before any run with the band off.
    **Then decided (owner, 9 Nov 2026): the band stays on for every run, SA and LM alike.** One mesh family for both
    solvers, so the SA mesh study also speaks for the LM runs; the price is about 1.8–1.9 × the cells for the SA runs
    at Re ≥ 3 × 10⁵ (compute, not accuracy). The switch stays in the code, default on, not used; no cap change (the
    band-on caps pass, lowest 0.057).
82. **The surface rules are frozen (owner, 9 Nov 2026).** A question gets a measurement first; a rule changes only
    when a check fails or a solver result shows a problem. (Why: on 9 Nov a question led to a new option and talk of a
    cap change without a real need; changes to screened rules risk what is built.)
83. **The hold-outs opened once for the surface mesh (owner, 9 Nov 2026).** The 60 sealed hold-out wings (15 per type:
    holdout_focus 10, holdout_full 5) are built and meshed with the frozen surface rules (82), every level and the four
    Re levels (Stage 2 Study 14; `scripts/screen.py --open-holdouts`, the seal lifted in that process only). No rule
    changes from it. The Grand Roadmap's A3 (the hold-out once with every law frozen) still applies to the volume mesh
    and the solves.

## Stage 3 (volume mesh) — choices I made (9 Nov 2026)

Rules, checks and the measurements behind them: `Stage_3_volume_mesh/decisions/volume_rules.md`; values in
`Stage_3_volume_mesh/configs/volume.yaml`; code in `cfdauto/volume/`.

84. **The station-plane grid: a march (decided by the V0 measurement, 9 Nov 2026).** The line shapes come from one front
    moved the same distance everywhere from the C line, smoothed along itself over its distance from the wall (κ = 1),
    through the fine zone, then straight to far-field nodes shared by all stations; the nodes are then placed along each
    line by one wall-normal distribution per station; the outer layers and the far wake nodes move to the station mean.
    Measured on 501 station planes (8 reference wings at VC): the march 0 folded planes (smallest scaled Jacobian 0.63,
    wall angle ≤ 0.05°); algebraic lines 501 of 501 folded, at the concave trailing-edge corners; the same + 300 Winslow
    sweeps 501 of 501 folded and the growth 15 × its limit. Not close, so not asked. A 3-D march is not needed for
    validity (planar stations; decision 89).
85. **Growth beyond the fine zone: checked at 1.3 at VC (Annex G, "≤ 1.3 anywhere outside the boundary layer"), built at
    1.22** (1.165 / 1.125 / 1.095 at C / M / F), as Stage 2 builds the ring at 1.2 and checks 1.25. The far-field blend
    (84) raises it: by 3 % on V1 when built at 1.3; to 1.313 (1.0100 × the limit, refused) on BWB reference wing 4 at
    Re 4 × 10⁶ when built at the wall growth 1.25 (decision 98).
86. **Cells across the boundary layer: 30 at VC (× 1.3 per level), across the turbulent flat-plate layer at the trailing
    edge, δ = 0.37 c Re_c^−1/5, from the station's local Re** (Annex G: "≥ 30 at the baseline"). Measured (counts only, the
    20 reference wings × 4 Re): at Re 10⁵ the small tips have a layer thinner than 30 first cells at mid-chord, laminar or
    turbulent, so those variants cannot be met at VC; at the trailing edge the turbulent layer always fits 30 cells; the
    layers at VC are then 88.9–90.7 median, 97.2 largest (the wake band and the fine zone set most of them). Weak point:
    the laminar layer at mid-chord gets fewer cells at VC (the family gives it more at F).
87. **The wake band (laws 17, 18).** The freestream fan from −5° to 20° from the trailing edge, plus 0.05 c above and below,
    2 local chords long. Its cross cell is 0.0075 c at M next to the trailing edge (Primer: about 20 cells across a
    0.15 c wake) and grows with the distance so that the fan keeps 40 cells at M (23.7 at VC, 52 at F; 0.63° each at M).
    It is applied to every line of a station as an envelope in height (a cell at height h is at most the band cell of the
    farthest band point at that height), so the C lines above the aft wing get it too; streamwise ≤ 4 × the band cell.
    The wake lines keep the wall spacing along the cut, are parallel (the base height apart), leave along the base normal
    and turn to +x over 0.5 local chord. A constant 0.0075 c band cell over the whole band (the overset plan's wake box) would
    need 1.50–1.93 × the layers (counted on BWB and tapered reference wing 0 at VC and M, Re 3 × 10⁵; not built).
88. **Outboard (law 12) and the tip vortex (law 19).** First gap = the wing's last gap (2 s0 at the tip); growth 1.15 at VC
    to 2 c past the tip, then the far growth 1.3 (the checked value: the station gaps are a 1-D spacing with no blend, so
    no margin is needed; this text said "built 1.25" until V2, the code always built 1.3) to 80 c past the tip. The vortex path from the tip
    trailing edge at −5° to 20° lies inside the wake band; along the semi-span it is held by the tip squeeze (Stage 2) and
    the outboard stations. No other clustering.
89. **Planar stations; the orthogonality check is in the station plane.** The rings are planar (4e−15 c), so the lines stay
    in y = const: square to the wall in the plane, but at a swept nose the 3-D angle to the surface normal is the sweep
    (the cell is sheared; its first cell along the normal is s0 · cos, so y⁺ falls). The 3-D angle is reported on every
    mesh, not refused. A 3-D march would bend the station planes; near the tip they are 2 s0 apart and would cross.
90. **The base is a wall: the first cell behind the base is s0** (y⁺ ≤ 1 on every wall). This carries the wake's
    streamwise clustering (s0) through the wake blocks to the far field (about 20 wake nodes at VC), and puts a spacing
    jump across the trailing-edge line: the wing's last chordwise cell (Stage 2: 0.169 % c at VC) next to s0 (about 20×
    at Re 3 × 10⁵, 250× at 4 × 10⁶). Named and reported, not refused.
91. **The far field.** A half circle in front, centred at the most aft trailing edge, lines above and below, the outflow
    80 c behind the most aft trailing edge, and 80 c past the tip; the radius is 80 c + the wing's extent + 1 c, so every
    wall node is at least 80 c inside. The far-field nodes are shared by every station (a pure extrusion along the
    semi-span).
92. **The smoothing ladder:** κ = 1, 1.5, 2, 3; above the first rung the mesh is "needs review" (R1).
93. **Names and files.** `volume_<level>_<wing_hash8>_re<Re>`; `blocks.npz`, `quality.json`, `manifest.json`,
    `volume.cgns`, `volume.su2`; a refused mesh writes only `refusal.json`.
94. **Branch.** Stage 2 is not merged into main yet (`stage2-surface-mesh` is 105 commits ahead), so `stage3-volume-mesh`
    starts from `stage2-surface-mesh`. Push access was not granted in this session: the branch is committed here and
    handed over as a git bundle (or pushed once access is granted).
    **10 Nov 2026 (Mike): everything in main.** Push access granted; main fast-forwarded to `stage3-volume-mesh`
    (main ← `stage2-surface-mesh` ← `stage3-volume-mesh`, no merge commit); both branches stay on GitHub.
95. **Check 10 allows round-off (V2, 9 Nov 2026).** The outboard far field sits exactly 80 c past the tip, so the distance
    is 80 c to round-off; 6 of 80 meshes read 79.99999999999999 c and were refused on the first screen. The comparison
    now allows 1e−9 c (`checks.far_tol_c`); the limit stays 80 c.
96. **The count factor scales the growth only, never the band cell (V4, 9 Nov 2026).** One factor per station fits every
    station to the same layer count; it scaled the band cap too, so the band cell VC/C was 1.24 on BWB reference wing 0
    (check 13: 1.3 ± 3 %). Now the band cell is the rule at every station and level (1.292). Tried and dropped: the
    factor only past 2 local chords (checks 3 and 6 refused it: scaled Jacobian 0.014, growth 1.05 × the limit).
97. **Past the band the cap rises at the growth law's rate, g − 1 (V4, 9 Nov 2026).** It rose by 10 × the distance, so
    the cells left the band at whichever node came first past it, a different place at each level: the cell 1 local
    chord from the root's wall had VC/C 1.232–1.259 on 4 of 9 families. Now 1.265–1.289 on the same wings.
98. **The far zone is built at 1.22 at VC (V2, 9 Nov 2026)** (decision 85): built at 1.25, the blend to the station mean
    raised one root's growth to 1.0100 × the limit. Cost: one layer on that wing.
99. **The solver files (V5, 9 Nov 2026).** CGNS in ADF (A02011), written by our own writer (`cfdauto/volume/cgns.py`):
    Mike's CGNS 4.5.2 reads ADF only (no HDF5; S8), and building libcgns here was not allowed. Checked by our reader and
    by the CGNS library itself (VTK's copy, `libvtkcgns.so`): exact on the V7 mesh. The `.su2`: hexahedra, nodes welded
    by the topology, markers `wall`, `symmetry`, `farfield`, quads facing out. Check 15 runs on every export.
100. **V7 is written, not run (9 Nov 2026).** No ADflow or SU2 here (2 cores, 7 GB; the V7 mesh needs about 48 GiB for
    ADflow). `solve/`: the case (reference area = the half planform area, reference chord = the mean chord, moment
    point = the quarter point of the mean aerodynamic chord), the ADflow run with S8's safeguards (liftIndex 3 read
    back, totalrfinal / totalr0), the SU2 configs (SU2's own Langtry-Menter tutorial numerics, as S8), the acceptance
    rule (converged and settled), the runbook. Where it runs: Mike (ask item 3).
101. **The cap's two nose-corner columns: exempt from check 3, as in Stage 2 (Mike, 9 Nov 2026).** Check 3 (every cell
    ≥ 0.05, written in V0) refused BWB 0 at M (0.0447) and F (0.0367) and flying wing 0 at M (0.0458) and F (0.0380): the
    CAP block's two columns over the cap's two nose-corner quads, which Stage 2 exempts from the same limit (three
    corners on the smooth ring; the angle is 180° minus the ring's turning, so it falls with the level). Every other
    cell ≥ 0.077; every other check passed. Now check 3 judges every cell but these two columns; they are reported on
    their own (`cap_nose_corner_min_sj`), and a folded cell there still refuses the mesh (check 2). The 0.05 limit is
    unchanged.
102. **The cost: needs more thought (Mike, 9 Nov 2026).** F is 45.4 M cells (median; 41.3–50.7 M) on the 20 reference
    wings at Re 3 × 10⁵, against 9–11 M asked; M about 21 M. Counted options, F median (VC median): outboard growth
    1.25 38.3 M (3.88 M); 1.30 36.4 M (3.67 M); 30 boundary-layer cells at M 40.7 M (4.12 M); both 34.3 M (3.50 M); the
    band off 32.3 M (3.28 M); all three 24.5 M (2.52 M), and then M about 11 M (F ÷ 2.2, not counted)
    (`data/studies/cost_options.json`). No rule changed.
103. **Where the solves run: needs further thinking (Mike, 9 Nov 2026).** V7 stays written, not run. The V7 mesh (4.93 M
    cells, about 48.2 GiB for ADflow) is at the edge of the 52 GB desktop (about 5.0 M cells, Stage 2's figure).
104. **The hold-outs for the volume mesh: not yet (Mike, 9 Nov 2026).** V8 waits; they stay sealed for the volume mesh.
105. **The cells must drop drastically (Mike, 9 Nov 2026, 20:01).** F at about 45 M cells (VC about 4.5 M, 38–67 GiB
    for ADflow) is not usable. The rules will change, so: the V6 screen stopped at 427 of 702 wings (kept as the
    record); V7 (the first solves) and V8 (the hold-outs) wait for the new rules; packages of changes counted on the 20
    reference wings for Mike to choose (`data/studies/cell_packages.json`, `volume_rules.md` section 14). Until then the
    rules of V0–V5 stand, unchanged, as the baseline. Option built for the count (default off): `wake.first_cell:
    te_cell` (the first cell behind the base = the wing's last chordwise cell; check 5 refuses it while decision 90
    stands).
106. **The wake-band envelope misses wakes that leave downward (V6 finding, 9 Nov 2026; to fix in the redesign).** Check
    11 refused 18 of 24 full-space BWB and 2 of 3 full-space cranked wings screened (band cells up to 1.078 × the band
    cell; the growth part ≤ 0.99). The envelope height assumes a wake line straight from the trailing edge; where the
    base normal points down (−6.9° to −2.0° on BWB full-space wing 13; the centre line 0.068 c low at 2 local chords),
    the band's upper edge lies above the envelope. Fix: add the centre line's downward offset at the band length to the
    envelope height. Not built yet: the rules change first.
107. **Rule set 2 (Mike, 9 Nov 2026, 20:30: "make medium around 10 million; the fine family can be over this
    limit").** Package P2 of decision 105 is the lightest that meets it without touching Stage 2 (counted M median about
    11 M on the 20 reference wings at Re 3 × 10⁵, against 20.7 M): outboard growth 1.3 at VC (was 1.15; law 12);
    ≥ 30 cells across the boundary layer at M (was VC; 17.8 / 23.1 / 30 / 39); the first cell behind the base = the
    wing's last chordwise cell (was s0; changes decision 90: no spacing jump across the trailing-edge line, the base no
    longer at y⁺ 1); the wake band 20 cells across its fan at M (was 40; decision 87) and streamwise cells up to 8 × the
    band cell (was 4); plus the fix of decision 106. Unchanged: the surface and its band, the levels and the ratio,
    y⁺ 1 on the wing, the far field, the C-H topology. The check limits read the rules; check 5's base part follows the
    new first cell. Rule set 1 kept in `configs/volume_rules1.yaml` (the V0–V6 record); the study scripts build rule
    set 2 by default and prefix its files `r2_`. Written before the rule-set-2 screens (one probe build: BWB reference
    wing 0, VC, every check passed, 2,720,808 cells).

108. **The wake band is sized from the straight fan, not from the cut line (9 Nov 2026, 21:30; completes 106).** The
    first rule-set-2 full-space screen was stopped after 13 wings: check 11 refused 9 (6 BWB, 3 cranked; band cells
    1.010–1.070 × the band cell, the same wings as in rule set 1: 1.017–1.074). Cause: decision 106 raised the
    envelope's top, but its cells still began to grow at the margin above the *cut line*. The band (law 18) is a fan of
    straight rays from the base mid-point; where the cut line falls behind the base (0.116 c at the root of BWB
    full-space wing 0, 4.5 % of its local chord) the cells just under the fan's upper edge were sized for a point
    farther back. Fix (construction, no limit changed): `plane.band_envelope` gives each station the exact envelope as
    a table: at height x above a line's start, the band cell at the nearest distance behind the base at which the
    band reaches x, for the upper and the lower lines, whatever the cut line does. On the refused wings the band part of
    check 11 is now 0.998–0.999.
109. **Each cell takes the band limit at its own centre (9 Nov 2026, 21:40).** Check 13 failed on 11 of the 20
    reference wings in the first rule-set-2 family run: the cell 1 local chord off the root wall was 1.247–1.261 × the
    next level's (limit 1.3 ± 3 %), and the band cell 1.285 × on every wing. Cause: the distribution took the limit
    at the cell's start, so a cell lagged the limit by 1 / (1 + slope / 2), more on the coarser level (its slope is
    larger). Fix (construction): the limit at the cell's centre (`march._walk`). Measured after: the band cell
    1.300 ×, the cell at 1 local chord 1.275 × (BWB reference wing 1, the worst before) and 1.280 × (cranked 4).
    Tried first and dropped: giving a station's spare layers to its far part only (the growth scale fell to 0.41 on
    some stations and the outer blend then broke the growth limit: 1.39 against 1.3).
110. **The far cells of very close stations are lined up along the semi-span (9 Nov 2026, 22:00; redone 22:55 and
    23:55).** With 108 and 109 in, check 3 refused 2 of 12 full-space wings probed: BWB wing 3 (0.044: at its kink the
    chord goes 0.74 → 0.58 → 0.42 c over stations 0.05 c apart, and their wake nodes sat 1.1 c apart in x 24 c behind
    the wing) and BWB wing 0 (0.049: a centre body whose chord goes 2.57 → 2.44 → 2.30 c over stations 0.023 c apart).
    Cause: the near field of a station is sized in local chords (fine zone, band), so the far nodes of neighbouring
    stations sit at different distances; where the station gap is tiny the cells between them shear. Fix
    (construction): `volume.span_smooth` moves the far part of each station's wall-normal distribution, and of its wake
    nodes in x, toward the Gaussian average of the stations within about 0.25 c along the semi-span; the near part (to
    the end of the fine zone and the band) is never moved. Each station moves by the largest fraction that keeps every
    growth ratio of its far part under the limit (exact: the conditions are linear in the fraction), lowered so the
    fraction changes by at most 1 per 0.5 c along the semi-span (neighbours move alike). One ramp for every station:
    the one that leaves the smallest largest offset between neighbouring stations per unit of their gap (what check 3
    sees), of ramps 1 to 32 start distances long. Three versions, each found by a screen:
    - **22:00** moved every station fully or none: one station that could not take it stopped all (BWB full-space
      wing 30: 0.028, at a tip whose chord falls to 0.06 c, stations 0.00012 c apart).
    - **22:55** per-station fractions, but the ramp was chosen by the largest smallest fraction, which favoured ramps
      so long that nothing moved where it mattered: the full-space screen refused BWB corner2 wings 0 (0.041) and 6
      (0.024), 300 of 302 passed.
    - **23:55** the ramp chosen by the shear left. Ramps shorter than one start distance are out: they broke the
      growth limit after the outer blend (1.032 on BWB full-space wing 3).
    Measured (smallest scaled Jacobian, limit 0.05), BWB full-space 0 · 3 · 30 · 31, corner2 0 · 6: before 110
    0.049 · 0.044 · — · — · — · —; 22:00 0.049 · 0.083 · 0.028 · — · — · —; 22:55 0.061 · 0.088 · 0.089 · 0.050 · 0.041 ·
    0.024; 23:55 0.062 · 0.088 · 0.093 · 0.056 · 0.052 · **0.032 (still refused)**. Tried and dropped: the mean of all
    stations as the target (0.030–0.046 on wing 30). **Not fixed: BWB corner2 wing 6** (its chord falls from 2.45 to
    1.13 c within 0.14 c of the semi-span, its trailing edge moves 0.145 c forward per station 0.0137 c apart); a fix
    would space the far wake by x for every station at once (a redesign, not built). The screens of section 17 of
    `volume_rules.md` were rerun with the 23:55 version: every built set at VC, 721 of 722 meshes pass; corner2 wing 6
    is the one refused (section 17.4).
111. **Angles of attack −5° to +10° for this mesh; the wake fan follows (Mike, 9 Nov 2026, 21:53 and 22:04: "I want to
    run from −5 to 10 AoA. You adjust the wake fan accordingly. If you think a margin is needed, let it be so").** The
    fan was −5° to +20° (decision 87), sized for post-stall, which decision 69 already gives to a separate study
    (URANS or DDES on a few wings) with its own mesh. Now: `alpha_hi_deg` 10, 12 cells across the 15° fan at M (1.25°
    per cell, as 20 across 25° before), the 0.05 c margin above and below, no extra angle (the downwash turns the wake
    below the freestream direction; at −5° the 0.05 c covers about 1.4° at the fan's end; and the cells do not jump at
    the fan's edge: at +10° the fan no longer costs a cell). Counted at M, Re 3 × 10⁵, wing 0 of each reference type
    (`scripts/fan_options.py`, `data/studies/r2_fan_options.json`): top at 20° 10.5 M cells, 15° 9.8 M, 12° 9.3 M,
    10° 9.0 M, no fan 9.0 M. One mesh still serves every steady angle (one mesh per wing, Re and level; the same mesh
    error at every angle; one family check per wing). The angle range is an input of the mesher (two numbers in
    `configs/volume.yaml`): a post-stall study sets its own. Not measured yet: where the wake goes in a solution; V7
    checks it at −5° and +10°.
112. **The RAM law of check 14 was mislabelled (found 9 Nov 2026, 22:14, on Mike's question "why do 5 million cells
    need 90 GB?").** Check 14 reports 1.51 GiB + 9.46 GiB per million cells and the configs called it "ANK only". It is
    S8's law for ANK then NK (ADR-0020). The runs here are ANK only (`solve/case.py`, as the S8 campaign), for which
    S8 measured 2.69 + 7.23: about 20 % less at these sizes (M at 9.4 M cells: 71 GiB, not 90). Both are two-point
    fits at 0.57 and 1.11 M cells; at M they are extrapolated 8 ×. Kept: check 14 goes on reporting the higher law
    (the list Mike approved; it is information, not a pass limit); the labels are corrected and the documents show
    both. Why it is so much per cell: the implicit solver keeps, per cell, the matrix to its 6 neighbours, a factored
    copy of it and the Krylov vectors, about 1,000 numbers (the split is an estimate; the totals are S8's
    measurements). V7 gives a third point (2.3 M cells) and the first SU2 number.
113. **48 GB: keep the mesh, measure the memory in V7 (Mike, 9 Nov 2026, 22:20).** Mike: "all this time we planned
    with 10 M cells fit inside a 48 GB RAM". The record says otherwise (Stage 2: "+36 GB about 5.0 M cells; F needs the
    HPC"; 9 Nov: "+32 GB about 4.6 M cells per run; M stays on the HPC"), and when Mike set "M about 10 M" (107) the
    package table showed the RAM at VC only: that was the gap. By S8's two laws 48 GB (about 45 usable) holds 4.6–5.9 M
    cells: VC (about 2.1 M) and C (about 4.4 M) fit, M (about 9.4 M, 71–90 GiB) and F do not. Asked which must fit,
    Mike chose: keep the mesh; VC and C on the desktop, M and F on the HPC; V7 measures the real memory (ADflow as
    run, ADflow with a leaner preconditioner, SU2) before any new cut. Not chosen: cutting M to 5–6 M cells now (it
    needs the surface band off and the tip cap not wall-resolved: decision 81 and the frozen surface).
    `solve/run_adflow.py` now writes the peak memory of every rank into `result.json`.
114. **Lighter meshes: a rule set 3? Open, for Mike (11 Nov 2026, on Mike's question "above 10 M is too much").**
    Measured (`Stage_3_volume_mesh/decisions/volume_rules.md`, section 20; what-if copies of the rules files, nothing
    changed): today M is 9.1 M at Re 3 × 10⁵ and 13.5 M at 4 × 10⁶ (the 4 wings 0). Three changes bring it to 5.1 and
    6.2 M with every check passing and the band kept: the wall-normal growth 1.30 at VC (1.17 at M) and the station
    growth 1.25 at VC (both inside DPW's guides), and the tip gap at DPW's 0.1 % of the semi-span at M instead of
    2 × s0 (36–1,100 × finer than DPW today; it makes the stations grow with Re). This sharpens 113: 5–6 M does not
    need the band off, only the tip cap not wall-resolved (or a wrapped, O-type tip). Not advised: 10 cells per bubble
    (half the transition guide), a coarser trailing-edge cell or ring growth (they break the tip cap), the far field
    below 80 c̄ before Stage 4. The band off for the fully turbulent runs would give 3.5–4 M but breaks the BWB cap.
    To decide: take the package (a Stage 2 change: a new tip-gap law; then a re-screen), check it with one solver run
    first, or keep rule set 2.
    **The same evening (section 21; Mike: "only the too strict things, or make the current M the Fine ... start from
    800k"):** the ladder counted with five levels (VVC one step under VC) on the 20 reference wings and at the four Re.
    (a) With the wall-normal growth at 1.30 the three changes together are refused on BWB reference wing 3 at VC (growth
    check 1.0105 against 1.01): the package is taken with **1.28** (every mesh built passes: 180 of 180; the family
    check 13 passes on BWB 0, VVC to M). (b) The light rules move every level one step down in size: 20 reference wings
    at Re 3 × 10⁵, median: VC 2.08 → 1.25 M, C 4.46 → 2.63 M, M 9.53 → 5.53 M, F 20.7 → 12.0 M; at 4 × 10⁶ (wing 0 of
    each type) M 13.5 → 6.4 M, F 29.4 → 13.9 M. (c) Renaming today's levels one step down gives the same sizes with
    every level one step coarser on the wing: not advised. (d) VVC (0.4–0.7 M light) is past the hard minimums
    (y⁺ 1.3): a preview level only. Proposed: rule set 3 = the light rules with levels VC, C, M, F; the production level
    chosen by Stage 4's grid study. Still Mike's to decide.

