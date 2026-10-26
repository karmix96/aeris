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
8. **Conventional ranges** proposed in `conventional_ranges.md`. Root chord up to 1.35 m so the
   mean chord reaches Re 5 × 10⁶. Keep?
9. **BWB stops at Re ≈ 3 × 10⁶** with the AERIS ranges (MAC ≤ 0.79 m). Widen the BWB size range,
   or run 5 × 10⁶ on BWB as a flow condition only (any wing can be solved at any Re)?
10. **BWB root dihedral** now 0–3° at b0 and b1 (was pinned 0 in AERIS).
11. **`root_chord_fractions` mode:** `semi_span_m` is read as semi-span / root chord (keeps one
    variable list). Conventional uses this mode so the aspect ratio stays in 4–16.5.
12. **Dihedral on straight panels:** each panel gets one dihedral (the mean of the linear law).
    Checks compare panel dihedral. See `root_section.md`.
