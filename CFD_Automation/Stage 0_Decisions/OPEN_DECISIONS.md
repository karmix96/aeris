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
8. **Conventional ranges** proposed in `geometry/decisions/conventional_ranges.md`. Root chord up to 1.35 m so the
   mean chord reaches Re 5 × 10⁶. Keep?
9. **BWB stops at Re ≈ 3 × 10⁶** with the AERIS ranges (MAC ≤ 0.79 m). Widen the BWB size range,
   or run 5 × 10⁶ on BWB as a flow condition only (any wing can be solved at any Re)?
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
19. **Every conventional training wing is "cranked"** (100/100). The three chord ratios and three
    sweeps vary independently, so a straight taper almost never comes out. If straight-tapered
    and rectangular wings must be in the training set: use `chord_law: linear_taper` for part of
    the set, or pin sweep2 = sweep3 = sweep1. Decide.
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
