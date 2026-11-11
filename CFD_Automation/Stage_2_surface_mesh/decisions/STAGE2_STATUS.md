# Stage_2 — Surface mesh: status and handover (2 Nov 2026, updated 11 Nov 2026)

Text copy for chats in this project. Repo: karmix96/aeris, branch `stage2-surface-mesh`,
`CFD_Automation/Stage_2_surface_mesh/` (configs, decisions, docs, tests, scripts, studies) and the code in
`CFD_Automation/cfdauto/mesh/`. Read first: the page `Stage_2_surface_mesh/docs/SURFACE_MESH.html` (live: https://claude.ai/artifact/6SXM1yDgwbPvgNRsDb24fi; text copy: 'Stage_2 Surface mesh page'), then `Stage_2_surface_mesh/README.md` (how to run, the rules table,
the checks) and `decisions/surface_rules.md` (why, and what the screens showed). Built and screened here with
the numpy twin of the loft; on Mike's machine (8 Nov) the 20 reference wings on the pyGeo loft gave the same meshes
(VC and F: the same ring nodes and stations, 80 of 80 each; VC: every check value within 6 × 10⁻¹⁰).

> **What was first, and what changed (7 Nov 2026).** The **first approach** was built and screened on 2–3 Nov (the
> sections below the box). On 4–6 Nov a **new approach** was decided (owner), and on **7 Nov it was built**: the surface
> rules in Stage 2 (`configs/surface.yaml`; the first approach kept in `configs/surface_first.yaml`), the nose fix and
> similarity in Stage 1. The **new screen** (Study 9): 1,724 of 1,724 builds passed. **8 Nov:** the Re levels are
> 10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶ (decision 78); the 20 reference wings screened again at them, 320 of 320 pass, and the
> refine map redone. The owner's choices of 8 Nov built: decision 77 confirmed, the upper band 0–100 % c, a nose
> repair belongs to the family (80). **The family screen** (Study 12, 8 Nov): every set at every level, 3,128 of
> 3,128 builds pass, 0 nose repairs. **9 Nov:** the band's cost measured (Study 13: it nearly doubles the cells at
> Re ≥ 3 × 10⁵); the band stays on for every run, SA and LM alike (81; a switch to turn it off exists, unused: with it
> off the BWB tip cap fails at M); the surface rules are frozen (82). **Study 14:** the 60 hold-outs, never seen, opened once
> (83): 960 of 960 builds pass with the rules frozen; the tip cap came within 0.5 % of its limit at M (0.0503). The overset
> plan is kept as a fallback (73, 9 Nov). Decisions 64, 67–83 in `CFD_Automation/OPEN_DECISIONS.md`.
>
> | What | First (built 2–3 Nov) | New approach | Status |
> | --- | --- | --- | --- |
> | Levels | C, M, F, FF; every rule met at C, the coarsest | VC, C, M, F; hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap), accuracy targets at M (nose 10°, TE 0.1 % c, station gap, largest cell), transition targets at F (20 cells per bubble; wall growth 1.107, just above the 1.1 a transition model asks for); VC on the desktop, C/M/F on the HPC | built 7 Nov (71); screened |
> | Band cell | bubble length / 20 at C; 0.40 / 0.30 / 0.10 / 0.05 c at local Re 6e4 / 1e5 / 4e5 / 1e6 | bubble length / 20 at F (9.1 at VC); bubble length floor 0.10 c from local Re 4e5 (0.5 % c at F) | built 7 Nov (72) |
> | Stations, tip | gap 0.2 × chord at C, ≥ 12 per panel; last gap = s0 | gap 0.25 × chord at M, ≥ 12 per panel at M (8 at VC, 16 at F); last gap = 2 × s0; station growth 1.2 kept | built 7 Nov (72) |
> | Upper band | 0–85 % c | 0–100 % c (owner, 8 Nov). At the Re levels the upper transition sits past 85 % c at low Re (0–49 % of the strips fit 0–85 % c at 10⁵ and 3 × 10⁵; Study 11); the built mesh already had band-size cells there (one node list and the lower band 0–100 % c). The cost (Study 12): 2 more ring nodes on VC 44 of 782, C 3 of 80, M 24 of 80 and F 383 of 782 meshes; cells at most +1.1 % | decided and built 8 Nov |
> | Lower band | 60–100 % c (angles 0–8°) | 0–100 % c (option A, chosen by Mike on 7 Nov): no extra cells, because both sides share one node list (Study 8) | built 7 Nov (74) |
> | Volume mesh | O-H body mesh + overset wake box + tip-vortex tube (ADflow only) | one matched C-H mesh for ADflow and SU2 (SU2: converted to unstructured hexes); wake lines to the far field; tip vortex in the outboard blocks; the ring and cap unchanged | decided (73), Stage 3 |
> | Similarity | real size; TE max(0.5 / 1.0 mm, 0.2 % c) | unit mean chord (area / full span); Re an input (4 levels: 1e5, 3e5, 1e6, 4e6 since 8 Nov (78), were 1.5e6 and 3e6; 1e5 is 18 % below the slowest real UAV, kept as a margin); Mach 0.1 + Prandtl–Glauert; TE 0.2 % c; root chord out (18 → 17); no 7 m full-span cap | built in Stage 1 7 Nov (70); sets rebuilt (722 of 722); 13 of 20 reference wings new; Study 10 |
> | Flow model, angles, Mach | ADflow SA; 0–8°; Mach 0.03–0.20 | transition with ADflow and SU2 (67; split pending, 76); −5° to post-stall + post-stall study (69); toward Mach 0.5, no supersonic, core ≤ 0.2 (68) | decided; split and core pending |
> | Nose (64) | "the built nose is not round" | real: the old rule made a curvature spike on one side and a flat spot on the other, between the raw points (NACA 4415: a 0.18 % c cell turned 9.47° built against 4.31° true). The 6 Nov "overstated" correction (75) was wrong. New rule: one cubic spline, the LE at its apex, 201 points per side; a gate refuses 14 database files; 95.6 % of the database passes (21.0 % before) | built in Stage 1 7 Nov; Study 4 |
> | Fine level | no target | F 6.73 M cells median on the wing blocks (20 reference wings × 4 Re; 5.91 M over every set; max 10.21 M, BWB reference wing 3 at 4 × 10⁶; 6.70 M and 10.17 M before the upper band change; 6.9 M and 9.7 M at the old levels), below the 9–11 M asked (this count: its rule is written down, so it can be redone); the first estimate (6 Nov) 10.9 M, its wall-layer rule not recorded, on the first-approach reference wings; the C-H wake lines add a rough +30–60 %; Stage 3 sets the real wall-layer rule | counted 7 Nov (Study 9); every set at every level 8 Nov (Study 12) |
> | Builder choices (77) | — | all stricter than decided: (1) the ring and station growth limits follow the family rule (1.107 / 1.127 at F); the kink check uses each level's turning limit; (2) the nose: solved at every level, the strictest wins (first at VC and F only, and M then needed a repair on all 20 flying-wing reference builds; then 0 repairs on the reference builds and 4 of 782 F builds of the full sets; with decision 80 none of 782 families; VC turns 14.6–16.1° instead of 16.9°); (3) station growth 1.2 kept (+17 % stations against the plan file's 1.25 and 7 gaps per panel) | (2) decided 7 Nov (owner); (1), (3) confirmed by Mike 8 Nov |
> | Nose repair (80) | one round on the whole wing at the level that needed it (it broke the 1.3 step there) | a round only past the level's check limit (angle + 0.2°); a repair belongs to the family: one factor at every level, so every spacing still refines by exactly 1.3; every mesh labelled (`nose_repair`, `nose_family`) | decided and built 8 Nov (owner); Study 12: 0 of 782 families needed one |
> | Transition band (81) | the band always on | on for every run, SA and LM alike (owner, 9 Nov): one mesh family for both solvers; a switch to turn it off exists, unused (off: 1.8–1.9 × fewer cells at Re ≥ 3 × 10⁵, but the BWB tip cap fails at M, 0.0495 against 0.05; Study 13) | decided 9 Nov (owner); no change to the meshes |
> | Rules frozen (82) | — | a question gets a measurement first; a rule changes only when a check fails or a solver result shows a problem | decided 9 Nov (owner) |

## What Stage 2 is

One wing surface (the Stage 1 loft) in, one structured surface mesh out: a closed ring of points around the
section at every spanwise station, root to tip, plus one patch closing the flat tip. Every node is asked from the
loft. The volume mesh, the wake and the CGNS file are Stage 3.

- Name: `mesh_<level>_<wing_hash8>_re<Re>` (the surface depends on the Re on the mean chord: tip gap, band cells),
  with the levels VC, C, M, F. Every wing is at unit mean chord, so four surfaces per wing and level (one per Re level).
- Files per mesh: `surface.npz`, `surface.xyz` (Plot3D), `stations.csv` (asked and delivered per station; which
  solve set the nose), `quality.json` (every check; every rule value with its anchor level and reason),
  `manifest.json` (hashes; the rules file and its hash). A refused mesh writes only `refusal.json`.
- One mesh takes 4.5 s at VC and 9.3 s at F (median, Study 12). Every spacing ÷ 1.3 per finer level, the growth g
  becomes g^(1/1.3), counts × 1.3: a finer level is a true scaled copy (checked on the 20 reference wings × 4 Re at all
  four levels: Study 9; on all 782 families: Study 12; first approach: `data/studies/family_ratios.json`).

## The rules, as built (new approach, 7 Nov; values from `laws.py`)

| Where | Rule (anchor level) | VC | C | M | F |
| --- | --- | --- | --- | --- | --- |
| Nose | no ring cell turns the surface by more than 10° at M; solved at every level for its own angle, the strictest spacing wins; away from the nose the same angle caps the cell from the local curvature | 16.9° | 13° | 10° | 7.69° |
| Nose along the semi-span | nose spacing / chord changes by at most 1.15 between stations | 1.15 | 1.15 | 1.15 | 1.15 |
| Trailing edge | 0.1 % of local chord at the corners (M); cells across the base (VC, even) | 0.169 % c; 8 | 0.130 % c; 10 | 0.100 % c; 14 | 0.077 % c; 18 |
| Transition band | upper 0–100 % c (since 8 Nov; 0–85 % c before), lower 0–100 % c; cell = bubble length / 20 at F; bubble 0.40, 0.30, 0.10, 0.10 c at local Re 6e4, 1e5, 4e5, 1e6 | / 9.10 | / 11.8 | / 15.4 | / 20 |
| Elsewhere | largest cell 2 % c at M; growth built 1.2, checked 1.25 at VC | 3.38 % c; 1.2 / 1.25 | 2.60 % c; 1.15 / 1.19 | 2.00 % c; 1.11 / 1.14 | 1.54 % c; 1.087 / 1.107 |
| Stations | one on every loft station; gap / local chord (M); gaps per panel at least (M); growth 1.2 built, 1.3 checked at VC | 0.4225; 8 | 0.325; 10 | 0.25; 12 | 0.192; 16 |
| Tip | last gap = 2 × s0; s0 from y⁺ (VC) | y⁺ 1 | 0.77 | 0.59 | 0.46 |

The first approach (level C of C, M, F, FF; every rule at C): nose 10°, trailing edge 0.1 % c, base 8, band = bubble
/ 20 with the bubble 0.05 c above local Re 1e6, lower band 60–100 % c, growth 1.2 / 1.25, station gap 0.2 c with 12
per panel, last gap = s0 (`configs/surface_first.yaml`).

Both sides of a ring share one node distribution (in arc fraction; the stricter side wins), so the tip cap's
cross lines stay upright, and the upper band already makes the front of the lower side fine. One node list for the
whole wing: at every place the strictest station wins.

## Checks that refuse (13)

nose turning, geometry kinks, nose envelope, chord growth, band spacing, trailing-edge spacing, growth between station gaps,
loft stations hit, tip gap, every ring in its station plane, wing quads (scaled Jacobian ≥ 0.05), cap quads
(≥ 0.05; the two nose-corner cells reported apart, refused only if folded), ring count. Each level is checked against
its own limits (turning 17.1 / 13.2 / 10.2 / 7.89°; growth along the ring 1.25 / 1.19 / 1.14 / 1.11 within 1 %;
between station gaps 1.3 / 1.22 / 1.17 / 1.13). A refused mesh writes only `refusal.json`. Tests: 45 (`tests/mesh/`),
including the family test and a test of every value per level (`test_laws.py`).

## The hold-outs (9 Nov; Study 14; decision 83)

The 60 sealed hold-out wings (15 per type: holdout_focus 10, holdout_full 5) opened once, with the surface rules frozen
(82): Stage 1 gates 60 of 60; every level and the four Re levels, 960 builds (`scripts/screen.py --open-holdouts`,
`scripts/holdout_study.py`; `data/studies/holdout_screen.json`, `docs/page/holdout_screen.png`).

| Level | Passed | Cells, median (largest) [M] | Reference wings, same 4 Re | Largest nose turning | Worst tip cap (Study 12) |
| --- | --- | --- | --- | --- | --- |
| VC | 240 of 240 | 0.68 (1.08) | 0.68 (1.02) | 16.11° (limit 17.1°) | 0.0664 (0.0749) |
| C | 240 of 240 | 1.45 (2.29) | 1.46 (2.19) | 12.77° (limit 13.2°) | 0.0728 (0.0804) |
| M | 240 of 240 | 3.07 (4.91) | 3.08 (4.69) | 10.01° (limit 10.2°) | 0.0503 (0.0573) |
| F | 240 of 240 | 6.68 (10.69) | 6.73 (10.21) | 7.71° (limit 7.89°) | 0.0543 (0.0607) |

- 960 of 960 pass, 0 crash, 0 nose repairs; the nose step 1.296–1.303 per level, the trailing edge 1.300.
- How sure: 0 failures on 60 unseen wings puts the surface-mesh failure rate below 4.9 % (95 % confidence); 0 of 782 with
  every set (below 0.4 %), but 722 of them helped set the rules.
- Weak point: the tip cap at M, 0.0503 (flying wing holdout_full 1) and 0.0506 (cranked holdout_full 2), both at Re 10⁵,
  against 0.05; 5 of 240 M meshes below the worst cap seen before. The largest F mesh is now 10.69 M (cranked
  holdout_full 0 at 4 × 10⁶; before 10.21 M). No rule changes (82).

## The band option (9 Nov; Study 13)

The owner made the transition band an option (81): on for transition runs (SU2 SST + LM), off for fully turbulent
runs (ADflow SA), chosen right before the runs with the solver (76). Built: `chord.transition_band` (default true),
`--band on|off`; off = no band windows, the largest-cell rule only; the mesh name ends in `_noband`; the band-on
meshes are unchanged. The 20 reference wings × 4 Re × VC, C, M, F with the band off, against Study 12 (band on):

| Level | Cells on ÷ off at Re 10⁵ / 3 × 10⁵ / 10⁶ / 4 × 10⁶ | Largest on / off [M] | Passed, band off |
| --- | --- | --- | --- |
| VC | 1.09 / 1.79 / 1.87 / 1.87 | 1.02 / 0.57 | 80 of 80 |
| C | 1.08 / 1.81 / 1.88 / 1.88 | 2.19 / 1.21 | 80 of 80 |
| M | 1.09 / 1.82 / 1.90 / 1.90 | 4.69 / 2.59 | 60 of 80 |
| F | 1.08 / 1.83 / 1.91 / 1.91 | 10.21 / 5.60 | 80 of 80 |

- **Weak point:** with the band off, all 20 BWB reference builds at M fail the tip cap (scaled Jacobian 0.0495
  against 0.05; 0.057–0.077 with the band on). More smoothing does not help. Fix the cap before any band-off run.
- Hardware, the reference wings, band off: 78 of 80 C meshes fit the desktop today (28 with the band); 72 of 80 F
  meshes fit with +36 GB (21 with the band).
- `scripts/band_option.py`, `data/studies/band_option.json`, `docs/page/band_option.png`; `surface_rules.md` §20.
- **Decided (owner, 9 Nov): the band stays on for every run**, SA and LM alike; the switch stays in the code, unused;
  no cap change; the surface rules are frozen (82).

## The family screen (8 Nov; every set at every level; Study 12)

The owner's choices of 8 Nov, built: a nose repair belongs to the family (80: a round only where a ring turns past
its level's check limit, the angle + 0.2°, then one factor on all four levels of that wing and Re; every mesh
labelled `nose_repair`, `nose_family`), and the upper band written 0–100 % c. Then every set at VC, C, M and F: the
702 wings of training_focus, training_full, corner1 and corner2 at Re 3 × 10⁵ and the 20 reference wings at the four
Re levels, 782 families × 4 levels: **3,128 of 3,128 builds passed, 0 crashed, 0 families needed a nose repair**
(`data/studies/screen_family_VC.json` … `screen_family_F.json`, `screen_family_summary.json`; `scripts/screen.py
--family`, `scripts/screen_study.py --family`; two processes, about 2.9 h each, numpy loft).

| Level | Builds | Passed | Ring nodes min–median–max | Stations | Cells [M] every set: min–median–max | Reference wings × 4 Re: median (max) | Largest turning (check limit) | Lowest cap quad |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VC | 782 | 782 | 120–220–240 | 51–63–84 | 0.24–0.60–1.02 | 0.68 (1.02) | 16.11° (17.1°) | 0.075 |
| C | 782 | 782 | 154–284–308 | 65–80–108 | 0.51–1.26–2.19 | 1.46 (2.19) | 12.77° (13.2°) | 0.080 |
| M | 782 | 782 | 198–368–398 | 82–100–136 | 1.07–2.70–4.69 | 3.08 (4.69) | 10.02° (10.2°) | 0.057 |
| F | 782 | 782 | 254–476–514 | 106–131–177 | 2.28–5.91–10.21 | 6.73 (10.21) | 7.72° (7.89°) | 0.061 |

- The family rule over all 782 families: the asked nose spacing refines by exactly 1.3 per step; the delivered nose
  and trailing-edge cells by 1.295–1.304, the band and tip-gap cells by 1.269–1.326 (whole cells); the cells by 2.12,
  2.13, 2.18 per step (medians). Every family has one nose factor at every level (782 of 782), all labelled "none".
- Against the screens it replaces (the same wing, Re and level): the same ring nodes, stations and cells on VC 738 of
  782, C 77 of 80, M 56 of 80, F 396 of 782; the rest gained 2 ring nodes from the upper band (VC 44, C 3, M 24,
  F 383; cells at most +1.1 %), except 3 F meshes with 2 fewer: 3 of the 4 builds that had a nose repair on 7 Nov
  (0.003–0.006° past the old trigger), which need none now. The largest F mesh is 10.21 M (BWB reference wing 3 at
  4 × 10⁶; 10.17 M before).
- Every set at Re 3 × 10⁵, F median (largest): BWB 6.55 (8.87) M, flying wing 5.73 (6.91), cranked 5.51 (8.14),
  tapered 5.55 (7.45).
- RAM for ADflow: the desktop today (about 1.2 M cells) takes every VC mesh and 264 of 782 C meshes; with +36 GB
  (about 5.0 M) every C and M mesh and 75 of 782 F meshes; F on the HPC.

## The new screen (7 Nov; new rules, rebuilt sets, numpy loft)

Every set at VC and at F (training_focus, training_full, corner1, corner2 at Re 3 × 10⁵; the 20 reference wings at all
four Re levels: 782 builds per level), and the 20 reference wings at C and M (80 builds each): **1,724 of
1,724 builds passed, 0 crashed** (`data/studies/screen_VC.json`, `screen_F.json`,
`screen_reference_new.json`, `screen_new_summary.json`; `scripts/screen.py`, `scripts/screen_study.py`).

| Level | Builds | Passed | Ring nodes min–median–max | Stations | Cells [M], 20 reference wings × 4 Re: median (max) |
| --- | --- | --- | --- | --- | --- |
| VC (every set) | 782 | 782 | 120–220–240 | 51–63–84 | 0.68 (1.02) |
| C (reference) | 80 | 80 | 154–284–306 | 66–82–104 | 1.46 (2.19) |
| M (reference) | 80 | 80 | 198–366–396 | 82–104–133 | 3.07 (4.69) |
| F (every set) | 782 | 782 | 254–474–514 | 106–131–177 | 6.70 (10.17) |

The reference wings at the Re levels since 8 Nov (10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶; decision 78): screened again at VC,
C, M and F on 8 Nov, 320 of 320 pass; the 160 builds at 10⁵ and 3 × 10⁵ have the very same nodes as on 7 Nov (the
mesh code changed only in `refine_map.py` and a help text, which the surface mesher does not use), so the 7 Nov set
builds stand. At F the two moved levels have 0.7 % fewer cells; the largest F mesh is 10.17 M (BWB reference wing 3 at
4 × 10⁶: 3 more wall layers and 3 more stations than at 3 × 10⁶), 1.7 % above 10 M. The 7 Nov numbers (at 1.5 × 10⁶
and 3 × 10⁶) in the table were 0.70 (0.99), 1.50 (2.09), 3.19 (4.52), 6.92 (9.74).

- The nose at every level (owner, 7 Nov): against the first build (nose at VC and F only), 80 of 320 reference
  builds changed, all of them flying-wing builds (the BWB, cranked and tapered builds are the same node for node); ring nodes changed by
  VC 0; C 0 to +2 (median 0); M −2 to 0 (median −2); F 0; nose repairs 20 → 0 (`data/studies/nose_levels_check.json`). What set the nose,
  over 167,399 stations: F's solve 150,379 (89.8 %), M's 17,020 (10.2 %). Largest turning 14.6–16.1° at VC, 12.1–12.7° at C, 9.80–10.01° at M,
  7.21–7.71° at F.
- Largest growth along the ring 1.202 (VC) and 1.088 (F); between station gaps 1.233 and 1.107. Lowest
  cap-quad quality 0.075 at VC, 0.061 at F (limit 0.05); lowest wing-quad quality 0.09.
- Family ratios (80 pairs per step): nose, trailing-edge, band and tip-gap cells 1.269–1.321 per step (the first
  build, nose at VC and F: the flying wings' nose cell C/M 1.44, M/F 1.17); cells
  2.12, 2.13, 2.17 per step (medians); base cells and first-panel gaps by whole numbers (1.25 / 1.4 / 1.29 and
  1.25 / 1.2 / 1.33).
- Cells (this count, the one the pages use; an estimate of the wing blocks only): n = max over the stations of
  ceil(ln(1 + (g − 1) D / s0) / ln g), cells = (ring − 1)(stations − 1) n + cap quads × n; g the level's wall growth
  (1.25 at VC, 1.187, 1.141, 1.107 at F), s0 the level's first cell at each station's local Re (y⁺ 1 … 0.46),
  D = 2 local chords. F 6.70 M median (2.28–10.17 M): below the 9–11 M asked (6.9 M and 2.3–9.7 M at the old levels).
  The first estimate (6 Nov): F 10.9 M median (15.2 M with the planned rules), surface × wall layers, about 1.30 ×
  the layers per level, on the first-approach reference wings; its wall-layer rule was not recorded, so it cannot be
  redone. With the C-H wake lines (+30–60 %, rough) F is about 9–11 M. Stage 3 sets the real wall-layer rule.
- RAM for ADflow 1.51 GiB + 9.46 GiB per million cells: the desktop today (16 GB: about 1.2 M cells) takes all
  of the VC meshes and 28 of 80 at C; with +36 GB (about 5.0 M) all at VC, all at C, all
  at M; F on the HPC.

## The first screen (2–3 Nov; first approach, level C, the geometry of before 7 Nov)

Every built wing of every type and set (730: reference, training_focus, training_full, corner1, corner2) at
Re 3 × 10⁵ on the mean chord, and the 20 reference wings at all four Re levels: **790 builds, 790 passed, 0
refusals, 0 crashes** (`data/studies/screen_C.json`, `docs/screen_C.png`).

| Type (builds) | Ring nodes min–median–max | Stations | Quads | Build time [s] | Wing quads J min / median | Cap quads J min / median |
| --- | --- | --- | --- | --- | --- | --- |
| BWB (202) | 486–614–860 | 71–83–134 | 36k–52k–101k | 4.2–5.3–8.1 | 0.09 / 0.82 | 0.19 / 0.34 |
| Flying wing (193) | 370–430–528 | 66–76–116 | 28k–34k–58k | 4.0–4.8–7.0 | 0.48 / 0.88 | 0.15 / 0.19 |
| Cranked (202) | 364–410–594 | 69–78–119 | 27k–36k–72k | 4.0–4.9–7.6 | 0.40 / 0.98 | 0.15 / 0.43 |
| Tapered (193) | 364–420–506 | 69–79–116 | 28k–34k–55k | 3.7–4.9–7.8 | 0.56 / 0.98 | 0.15 / 0.43 |

Reference wings by Re (ring nodes, stations): 10⁵: 192–310, 67–97; 3 × 10⁵: 368–638, 73–103; 1.5 × 10⁶ and
3 × 10⁶: 844–860, 81–114. Largest delivered turning 10.02°; largest growth 1.21 (limit 1.25); a nose repair on 32 builds.
The lowest wing-quad quality (0.09) was on corner wings whose first panel is 4–6 mm wide with a 50 mm chord
drop (an 85° trailing-edge sweep), from the old trailing-edge floor. Three earlier passes of the screen were development
evidence: they found and fixed the tip-gap tolerance, kinked noses on the corner set, a 0.9 mm panel, sheared
quads in the tip squeeze (0.08), the 1.25–1.26 growth on NACA 4415 noses and a nose held over one cell instead of four.

## What was found and decided (OPEN_DECISIONS 56–80; `decisions/surface_rules.md`)

- **Cells per bubble = 20** (Ansys CFX transition-model grid guide; the Stage 1 rule had no source): at C in the first
  approach, at F now (9.1 at VC; decision 71). Settled for the mesh; the solver test T6 will show whether the coarse
  levels need more.
- **Wall-normal growth for a transition model 1.1** (same guide): settled by the levels, 1.25 at VC is 1.107 at F, just
  above it (1.23 at VC would give exactly 1.1).
- **Upper band from the leading edge on every wing**; **lower band from the leading edge** (74, option A, 7 Nov).
- **One surface per wing and Re level**; the name carries the Re.
- **One node distribution for the whole wing** (not per station): the per-station version sheared the quads
  where the tip stations are tens of µm apart (scaled Jacobian 0.08 → 0.58 on the worst wing). +3 % nodes.
- **Base cells 8, 10, 14, 18 per level** (even, so the cap's nose arc stays centred): ratios 1.25, 1.4, 1.29.
- **The nose (64): real, fixed in Stage 1 on 7 Nov.** First reading (2 Nov): the built sections' nose is not round
  (NACA 4415: 0.0248 c by formula, built 0.008 c upper / 0.074 c lower). The 6 Nov correction (75, "overstated") was
  wrong: it compared built and raw only at the raw points. Measured with one curvature method, the old rule failed a
  5 % turning test on all ten suggested airfoils; the new rule passes on all ten and on 95.6 % of the database. In the
  mesh: the NACA 4415 / 4412 reference wings get a nose cell of 0.245–0.265 % c instead of 0.178 % c (first rules at C);
  the flat part of the nose solve at about 7° stays (growth law; the true airfoil does the same, 6.0–6.8°).
- **Similarity (70): built in Stage 1 on 7 Nov.** On the same 20 shapes (first rules at C): the same ring nodes on 80
  of 80 meshes; 6–27 fewer stations on the 8 wings that had a switch section; the cap quality falls where the old
  floor had thickened small tips (most 0.345 → 0.133; lowest 0.112, limit 0.05). The Re levels stayed (Study 10, 7 Nov); changed on 8 Nov (78).
- **The refine map (65, 66; 3 Nov 2026, from −5° on 7 Nov).** `cfdauto/mesh/refine_map.py` reads the Stage 1 flow
  dataset for one wing and gives, per strip and side, the envelope of bubbles, transition ± margin and separation over
  the conditions one mesh serves: the band that wing would need. Interactive page `docs/REFINE_MAP.html`
  (https://claude.ai/artifact/KXra2FWoVEFYLHCoafhgye); Study 7 on the Stage 2 page. On the old 20 reference wings
  (Mach 0.03–0.13, −5° to 8°, margin 10 % c) the per-wing band costs +8 % to +46 % (median +34 %) of the first generic
  one; the first generic lower band missed the full 60 % c in front of it on all 20 wings (the new lower band covers
  it); the shortest root bubbles (1.4–10.7 % c) are shorter than the band-cell table assumes (5–14 % c). Candidate, not
  a rule (65): needs a 3-D transition check first. Proposal (66): AVL for the local angle per strip, NeuralFoil for
  the 2-D answer.
- **The refine map at the Re levels (7 Nov; Study 11, `decisions/refine_map_re.md`).** The map's Re mode on the new
  20 reference wings at the four Re levels, −5° to 12°, the section tables rebuilt on the fixed nose. The lower band
  (0–100 % c) holds every strip. The upper band as written (0–85 % c) holds only 0–49 % of the strips at Re 10⁵ and
  3 × 10⁵ (31 % BWB, 0 % the others at 10⁵), short by up to 15 % c, and 12–100 % at 10⁶ and 4 × 10⁶ (redone 8 Nov; 32–97 % at
  1.5 × 10⁶ and 3 × 10⁶ on 7 Nov); the cause is
  always the transition itself. As built this is no gap: on 16 built surfaces at VC the largest upper cell over
  85–99.5 % c is 0.950–0.995 × the band cell (one node list, lower band 0–100 % c). Written 0–100 % c it is the same
  mesh at VC to round-off (80 of 80), but 2 more ring nodes at F on 42 of 80 reference builds (+0.39 % cells median;
  `data/studies/upper_band_check.json`); the owner chose 0–100 % c on 8 Nov (Study 12). No XFOIL answer on up
  to 46 % (BWB) and 42 % (flying wing; 43 % on 7 Nov) of the strips at −5°.

## Weak points, said plainly

- Built and screened with the **numpy twin of the loft**; on pyGeo (Mike's machine, 8 Nov) only the 20 reference
  wings, with the same meshes (VC and F). The full sets were not meshed on pyGeo.
- **No solve yet.** Nothing here says the surface gives a good volume mesh or a converged run.
- **The cap quads come close to the 0.05 limit** (lowest 0.075 at VC, 0.080 at C, 0.057 at M, 0.061 at F, every set; Study 12);
  closer on the hold-outs: 0.0503 at M and 0.0543 at F, full-space wings at Re 10⁵ (Study 14). Similarity made some
  caps worse.
- **The stations are 17 % more than the plan file** (station growth 1.2 and 12 gaps per panel at M, as decided, against
  1.25 and 7), so about 17 % more cells than the plan's rules. Confirmed by the owner on 8 Nov (decision 77).
- **The cell count is an estimate and hangs on the wall-layer rule** (this count: one layer count per block, 2 chords
  deep; the first estimate of 6 Nov: rule not recorded); no wake lines, no outboard blocks. Stage 3 sets the real rule.
- **The coarse levels get a finer nose than they ask** (solved at every level, the strictest wins: VC turns
  14.6–16.1° against 16.9°): the price of an exact family rule.
- **The coarse levels do not resolve transition** (9.1 and 11.8 cells per bubble at VC and C).
- **The band rule rests on one source**, and the lighter band gives the shortest high-Re root bubbles (≈ 1.5 % c)
  only about 3 cells (fine for SA, not for LM).
- **The band count (Study 8) still reads the flow dataset at real size**; the refine map now runs at the Re levels
  (Study 11).
- ~~**The upper band as written missed the upper transition at low Re**~~ (0–49 % of the strips fit 0–85 % c at 10⁵ and
  3 × 10⁵): written 0–100 % c on 8 Nov (owner); 2 more ring nodes on some meshes, cells at most +1.1 % (Study 12).
- **No XFOIL answer on many tailless strips at −5°** (up to 46 % BWB, 42 % flying wing; 43 % on 7 Nov).
- **Studies 1–8 used the old 20 reference shapes**, 13 of which were replaced on 7 Nov.
- The station rules, the tip gap and the 2 % c cap are starting values without a ladder.

## Handover to Stage 3 (volume mesh, CGNS)

- Input: `surface.npz` per mesh: `wing (n_ring, n_span, 3)` ring-first, root to tip; `cap (n_chord, n_base, 3)`
  with i × j outboard; `u`, `y`, `v` per node and station; `stations.csv` with the local Re, chord, s0 need. Wings at
  unit mean chord; levels VC, C, M, F.
- The march (Grand Roadmap R-V): first cell s0 from the local Re and the level's y⁺ per station (law 13; 1 at VC,
  0.46 at F; the tip value is in `quality.json` as `s0_tip_m`); growth 1.25 at VC in the boundary layer (1.107 at F,
  just above the 1.1 a transition model asks for; decision 57); ≥ 30 cells across the boundary layer; reach about
  2 chords; the last station gap at the tip is 2 × s0, so the cap's first cell is chosen against it.
- The family: every spacing ÷ 1.3 per level and the growth g^(1/1.3), as on the surface, so the volume levels
  are true scaled copies too; the base cells follow 8 / 10 / 14 / 18.
- First plan (replaced on 6 Nov; kept as a fallback and for future work, owner 9 Nov; not built): boxes (R-V.6): background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, tube 15–20
  cells across the core from 2 c behind the tip, far field 80 c; overset export and the overlap gate (M3).
- New plan (73): one matched C-H multiblock mesh for ADflow and SU2. The C block wraps the ring (the nose stays a
  spacing request inside it, no collar: S6's 5-point collar was the pressure-peak defect); wake lines from the
  trailing-edge corners and the base to the far field (80 c), fine near the trailing edge (0.0075 c as the
  starting value); the stations go on past the tip into outboard H blocks, growing from the tip gap; the tip
  vortex resolved there by clustering along its path (no tube); the cap is the wall of the first outboard block.
  Structured CGNS for ADflow; a converter to unstructured hexes (.su2) for SU2. Rough cost +30–60 % cells.
- Before any solve: the pyGeo `build --all` after the label fix (done on Mike's machine on 11 Nov, commit de64aa57:
  722 of 722, the same input hashes, pass flags and labels as the numpy build) and the owner's word to close Stage 2
  (still open). The band stays on for every run (81); the solver split (76) is
  decided right before the runs; the surface rules are frozen (82). Decided on 8 Nov: 77 confirmed, the upper band 0–100 % c, a nose
  repair per family (80). The pyGeo run is done (8 Nov).
- Stage 1's label fix (decision 79, 8 Nov) changed every wing's input hash, not its surface (the same surface hash on
  all 722): every mesh and screen here stands (5 builds re-meshed: the same node hashes); mesh names
  (`mesh_<level>_<hash8>_…`) take the new hashes.

## How to run

```
pip install -e CFD_Automation
cd CFD_Automation/Stage_2_surface_mesh
python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5    # levels VC, C, M, F
python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5 --config configs/surface_first.yaml
python -m pytest                       # 45 tests (test_family is slow)
python scripts/screen.py --level VC    # and --level F; --sets reference --level C / M; --resume <part>.jsonl
python scripts/screen_study.py         # merge the parts; data/studies/screen_*.json; docs/page/screen_new_*.png
python scripts/screen.py --family --types bwb cranked --tag bwb_cranked   # every level, one nose factor per family
python scripts/screen_study.py --family   # data/studies/screen_family_*.json; docs/page/family_*.png (Study 12)
python scripts/screen.py --family --sets reference --band off --types bwb cranked   # the band option off (Study 13)
python scripts/band_option.py          # Study 13: data/studies/band_option.json, docs/page/band_option.png
python scripts/holdout_study.py --gates   # Study 14: build and gate the 60 hold-outs (Stage 1, numpy loft)
python scripts/screen.py --family --open-holdouts --sets holdout_focus holdout_full --types bwb cranked --re 1e5 3e5 1e6 4e6 --tag holdout_bwb_cranked
python scripts/holdout_study.py        # Study 14: data/studies/holdout_screen.json, docs/page/holdout_screen.png
python scripts/similarity_check.py; python scripts/built_figures.py
python scripts/change_figures.py; python scripts/make_stage2_page.py; python scripts/page_to_markdown.py; python scripts/make_summary_page.py
```
