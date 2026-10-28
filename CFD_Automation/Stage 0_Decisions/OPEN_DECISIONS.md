# Open decisions

1. **Grid share 65 %** (= 100 − 10 − 10 − 15). Keep?
2. **Reynolds low end.** Mini/micro Class I sit below 3 × 10⁵ (Raven ≈ 1 × 10⁵). Add 1 × 10⁵,
   or leave mini/micro out?
3. **Pitching moment 0.002** — our choice, no source. Keep?
4. **Iterative error ≤ 10 %** is loose; Eça & Hoekstra ask 0.1–1 %. Tighten to 1 %?
5. **Turbulence-model source is weak.** Crivellini 2014 found standard SA did fairly well on
   laminar bubbles. Find a better source or call it our choice.
6. **Grand Roadmap Stage 0 has a D5** (prior work, transition route, tunnel, cloud budget). Add?

## Stage 1 (geometry) — choices I made

7. **Folder.** Stage 1 lives in `CFD_Automation/geometry/` (config, `cfdauto` package, tests,
   data). Run from there: `python -m cfdauto.geometry.build …`. No `src/` level.
8. ~~**Conventional ranges**~~ **Decided 29 Oct 2026:** size ranges come from a sourced table of
   real Class I–II wings (`geometry/configs/real_uavs.yaml`), not from a target Re. Root chord
   0.13–0.60 m for conventional and tapered; see `geometry/decisions/conventional_ranges.md`.
9. ~~**BWB stops at Re ≈ 3 × 10⁶**~~ **Decided 29 Oct 2026:** BWB sizes come from real tailless
   wings too (root chord 0.40–0.80 m, semi-span 0.45–1.40 m). The top Re level is lowered to
   2 × 10⁶ for every type, because no real wing of our families reaches 5 × 10⁶.
10. **BWB root dihedral** now 0–3° at b0 and b1 (was pinned 0 in AERIS).
11. **`root_chord_fractions` mode:** `semi_span_m` is read as semi-span / root chord (keeps one
    variable list). Conventional uses this mode so the aspect ratio stays in 4–16.5.
12. **Dihedral on straight panels:** each panel gets one dihedral (the mean of the linear law).
    Checks compare panel dihedral. See `geometry/decisions/root_section.md`.
13. **Loft built with pySpline, not `liftingSurface` itself.** Same construction, but one section
    parameter, so the nose split is exact (`liftingSurface` missed it by 0.2–0.5 % chord). The
    surfaces sit in a pyGeo object (IGES works). See `geometry/decisions/loft.md`.
14. **Twist between stations is not exactly linear** on straight panels (trailing edge differs by
    0.1–0.3 % chord from a linear-twist section). Straight panels win. See `geometry/decisions/loft.md`.
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
    See `geometry/decisions/planform_laws.md`. Open: the mixed shares (now BWB 0.5, cranked 0.25,
    tapered 0.25).
20. **3 BWB training wings are "forward swept"** (outer quarter-chord sweep ≤ −5°): leading edge
    aft, but the strong outer taper pulls the quarter-chord line forward. Real geometry, not a bug.
21. **Reference wing 5 = strongest washout** (Stage 1 brief); Stage 0 said "strongest twist".
    Same idea; Stage 0 text could be aligned.
22. **Set builds skip IGES** (46 MB instead of ~550 MB for 298 wings). Single builds write it.
    Built wing folders are not tracked; vectors and manifests are.
23. **Seeds:** training 1001 (BWB) / 1002 (conventional); hold-out 2001 / 2002; coverage 3001.

## Stage 1 additions — airfoil database and published wings

24. **Airfoil search order:** `geometry/airfoils/`, then the AERIS database, then the NACA
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
33. **The two upper Re levels are now close** (1.5 × 10⁶ and 2 × 10⁶). Move the middle level to
    about 6 × 10⁵ (between 3 × 10⁵ and 2 × 10⁶ on a log scale)? Mini Class I wings fly at
    1.2–2 × 10⁵ (eBee, Black Swift S0), below the low level: this is item 2 with numbers now.
34. **Class II wing areas missing.** Hermes 450, Watchkeeper, Aerostar, Shadow and Ranger have
    published spans (4.3–10.9 m) but no wing area. Until they are found (Jane's, papers), the size
    ranges stop at the Pioneer (5.15 m span); the generator covers Class I and small Class II only.
35. **Slim tailless wings are labelled "conventional".** With real flying-wing sizes, about a quarter
    of the bwb-type wings have no centre body; the label rule calls them "conventional", which
    reads like "has a tail". Rename that label to "flying wing" for tailless types?
