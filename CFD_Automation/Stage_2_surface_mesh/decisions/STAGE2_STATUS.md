# Stage_2 — Surface mesh: status and handover (2 Nov 2026, updated 7 Nov 2026, evening)

Text copy for chats in this project. Repo: karmix96/aeris, branch `stage2-surface-mesh`,
`CFD_Automation/Stage_2_surface_mesh/` (configs, decisions, docs, tests, scripts, studies) and the code in
`CFD_Automation/cfdauto/mesh/`. Read first: the page `Stage_2_surface_mesh/docs/SURFACE_MESH.html` (live: https://claude.ai/artifact/6SXM1yDgwbPvgNRsDb24fi; text copy: 'Stage_2 Surface mesh page'), then `Stage_2_surface_mesh/README.md` (how to run, the rules table,
the checks) and `decisions/surface_rules.md` (why, and what the screens showed). Built and screened here with
the numpy twin of the loft; not yet run with pyGeo (Mike's machine).

> **What was first, and what changed (7 Nov 2026).** The **first approach** was built and screened on 2–3 Nov (the
> sections below the box). On 4–6 Nov a **new approach** was decided (owner), and on **7 Nov it was built**: the surface
> rules in Stage 2 (`configs/surface.yaml`; the first approach kept in `configs/surface_first.yaml`), the nose fix and
> similarity in Stage 1. The **new screen** (Study 9): @@OK_NEW@@ of @@N_NEW@@ builds passed. Decisions 64, 67–77 in
> `CFD_Automation/OPEN_DECISIONS.md`.
>
> | What | First (built 2–3 Nov) | New approach | Status |
> | --- | --- | --- | --- |
> | Levels | C, M, F, FF; every rule met at C, the coarsest | VC, C, M, F; hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap), accuracy targets at M (nose 10°, TE 0.1 % c, station gap, largest cell), transition targets at F (20 cells per bubble; wall growth 1.107, just above the 1.1 a transition model asks for); VC on the desktop, C/M/F on the HPC | built 7 Nov (71); screened |
> | Band cell | bubble length / 20 at C; 0.40 / 0.30 / 0.10 / 0.05 c at local Re 6e4 / 1e5 / 4e5 / 1e6 | bubble length / 20 at F (9.1 at VC); bubble length floor 0.10 c from local Re 4e5 (0.5 % c at F) | built 7 Nov (72) |
> | Stations, tip | gap 0.2 × chord at C, ≥ 12 per panel; last gap = s0 | gap 0.25 × chord at M, ≥ 12 per panel at M (8 at VC, 16 at F); last gap = 2 × s0; station growth 1.2 kept | built 7 Nov (72) |
> | Lower band | 60–100 % c (angles 0–8°) | 0–100 % c (option A, chosen by Mike on 7 Nov): no extra cells, because both sides share one node list (Study 8) | built 7 Nov (74) |
> | Volume mesh | O-H body mesh + overset wake box + tip-vortex tube (ADflow only) | one matched C-H mesh for ADflow and SU2 (SU2: converted to unstructured hexes); wake lines to the far field; tip vortex in the outboard blocks; the ring and cap unchanged | decided (73), Stage 3 |
> | Similarity | real size; TE max(0.5 / 1.0 mm, 0.2 % c) | unit mean chord (area / full span); Re an input (4 levels; 1e5 is 18 % below the slowest real UAV, kept as a margin); Mach 0.1 + Prandtl–Glauert; TE 0.2 % c; root chord out (18 → 17); no 7 m full-span cap | built in Stage 1 7 Nov (70); sets rebuilt (722 of 722); 13 of 20 reference wings new; Study 10 |
> | Flow model, angles, Mach | ADflow SA; 0–8°; Mach 0.03–0.20 | transition with ADflow and SU2 (67; split pending, 76); −5° to post-stall + post-stall study (69); toward Mach 0.5, no supersonic, core ≤ 0.2 (68) | decided; split and core pending |
> | Nose (64) | "the built nose is not round" | real: the old rule made a curvature spike on one side and a flat spot on the other, between the raw points (NACA 4415: a 0.18 % c cell turned 9.47° built against 4.31° true). The 6 Nov "overstated" correction (75) was wrong. New rule: one cubic spline, the LE at its apex, 201 points per side; a gate refuses 14 database files; 95.6 % of the database passes (21.0 % before) | built in Stage 1 7 Nov; Study 4 |
> | Fine level | no target | F @@F_MED@@ M cells median on the wing blocks (20 reference wings × 4 Re; max @@F_MAX@@ M), @@ASKED@@ the 9–11 M asked; 6 Nov estimate 10.9 M (plan-file surfaces, another wall-layer count); C-H wake lines ≈ +45 % (rough, 30–60 %) | screened 7 Nov (Study 9) |
> | Builder choices (77) | — | all stricter than decided: the nose solved at VC and at F (the smaller wins: VC turns @@VC_TURN@@° instead of 16.9°); the ring and station growth limits follow the family rule (1.107 / 1.127 at F); the kink check uses each level's turning limit; station growth 1.2 kept (+17 % stations against the plan file's 1.25 and 7 gaps per panel) | pending: Mike confirms |

## What Stage 2 is

One wing surface (the Stage 1 loft) in, one structured surface mesh out: a closed ring of points around the
section at every spanwise station, root to tip, plus one patch closing the flat tip. Every node is asked from the
loft. The volume mesh, the wake and the CGNS file are Stage 3.

- Name: `mesh_<level>_<wing_hash8>_re<Re>` (the surface depends on the Re on the mean chord: tip gap, band cells),
  with the levels VC, C, M, F. Every wing is at unit mean chord, so four surfaces per wing and level (one per Re level).
- Files per mesh: `surface.npz`, `surface.xyz` (Plot3D), `stations.csv` (asked and delivered per station; which
  solve set the nose), `quality.json` (every check; every rule value with its anchor level and reason),
  `manifest.json` (hashes; the rules file and its hash). A refused mesh writes only `refusal.json`.
- One mesh takes @@TIME_VC@@ s at VC and @@TIME_F@@ s at F (median). Every spacing ÷ 1.3 per finer level, the growth g
  becomes g^(1/1.3), counts × 1.3: a finer level is a true scaled copy (checked on the 20 reference wings × 4 Re at all
  four levels: Study 9; first approach: `data/studies/family_ratios.json`).

## The rules, as built (new approach, 7 Nov; values from `laws.py`)

| Where | Rule (anchor level) | VC | C | M | F |
| --- | --- | --- | --- | --- | --- |
| Nose | no ring cell turns the surface by more than 10° at M; solved at VC and at F, the smaller spacing wins; away from the nose the same angle caps the cell from the local curvature | 16.9° | 13° | 10° | 7.69° |
| Nose along the semi-span | nose spacing / chord changes by at most 1.15 between stations | 1.15 | 1.15 | 1.15 | 1.15 |
| Trailing edge | 0.1 % of local chord at the corners (M); cells across the base (VC, even) | 0.169 % c; 8 | 0.130 % c; 10 | 0.100 % c; 14 | 0.077 % c; 18 |
| Transition band | upper 0–85 % c, lower 0–100 % c; cell = bubble length / 20 at F; bubble 0.40, 0.30, 0.10, 0.10 c at local Re 6e4, 1e5, 4e5, 1e6 | / 9.10 | / 11.8 | / 15.4 | / 20 |
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
between station gaps 1.3 / 1.22 / 1.17 / 1.13). A refused mesh writes only `refusal.json`. Tests: 35 (`tests/mesh/`),
including the family test and a test of every value per level (`test_laws.py`).

## The new screen (7 Nov; new rules, rebuilt sets, numpy loft)

Every set at VC and at F (training_focus, training_full, corner1, corner2 at Re 3 × 10⁵; the 20 reference wings at all
four Re levels: 782 builds per level), and the 20 reference wings at C and M (80 builds each): **@@OK_NEW@@ of
@@N_NEW@@ builds passed, @@CRASH_NEW@@ crashed** (`data/studies/screen_VC.json`, `screen_F.json`,
`screen_reference_new.json`, `screen_new_summary.json`; `scripts/screen.py`, `scripts/screen_study.py`).

| Level | Builds | Passed | Ring nodes min–median–max | Stations | Cells [M], 20 reference wings × 4 Re: median (max) |
| --- | --- | --- | --- | --- | --- |
| VC (every set) | @@VC_N@@ | @@VC_OK@@ | @@VC_RING@@ | @@VC_SPAN@@ | @@REF_CELLS_VC@@ |
| C (reference) | @@C_N@@ | @@C_OK@@ | @@C_RING@@ | @@C_SPAN@@ | @@REF_CELLS_C@@ |
| M (reference) | @@M_N@@ | @@M_OK@@ | @@M_RING@@ | @@M_SPAN@@ | @@REF_CELLS_M@@ |
| F (every set) | @@F_N@@ | @@F_OK@@ | @@F_RING@@ | @@F_SPAN@@ | @@REF_CELLS_F@@ |

- Every station took its nose from the F solve (@@ST_F@@ of @@ST_ALL@@): largest turning @@VC_TURN@@° at VC,
  @@C_TURN@@° at C, @@M_TURN@@° at M, @@F_TURN@@° at F. Nose repairs (× 0.9, one round): @@REP_TXT@@; there F's spacing
  × 1.3 turned the surface just past M's 10.02°, and the nose cell breaks the family rule at M (@@FAM_REP@@ instead of
  1.3). Solving at all four levels would remove it.
- Largest growth along the ring @@VC_CG@@ (VC) and @@F_CG@@ (F); between station gaps @@VC_SG@@ and @@F_SG@@. Lowest
  cap-quad quality @@CAP_VC@@ at VC, @@CAP_F@@ at F (limit 0.05); lowest wing-quad quality @@WQ_MIN@@.
- Family ratios (80 pairs per step): nose, trailing-edge, band and tip-gap cells @@FAM_SP@@ per step on the pairs
  without a repair (the repaired noses @@FAM_REP@@); cells
  @@FAM_CELLS@@ per step (medians); base cells and first-panel gaps by whole numbers (1.25 / 1.4 / 1.29 and
  1.25 / 1.2 / 1.33).
- Cells (estimate, wing blocks): n = max over the stations of ceil(ln(1 + (g − 1) D / s0) / ln g), cells =
  (ring − 1)(stations − 1) n + cap quads × n; g the level's wall growth (1.25 at VC … 1.107 at F), s0 the level's first
  cell at the local Re, D = 2 local chords. F @@F_MED@@ M median (@@F_MIN@@–@@F_MAX@@ M): @@ASKED@@ the 9–11 M asked;
  @@F_VS6@@ × the 6 Nov estimate (10.9 M), although the stations are about 17 % more than in its plan file: the two counts
  differ in their wall layers (here @@F_LAYERS@@ at F; the 6 Nov rule is not written down). With the C-H wake lines
  about @@F_WAKE@@ M.
- RAM for ADflow 1.51 GiB + 9.46 GiB per million cells: the desktop today (about 1.2 M cells) takes @@DESK_VC@@ of the VC
  meshes and @@DESK_C@@ at C; with +32 GB (about 4.6 M) @@DESK32_VC@@ at VC, @@DESK32_C@@ at C, @@DESK32_M@@ at M; F on the HPC.

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

## What was found and decided (OPEN_DECISIONS 56–77; `decisions/surface_rules.md`)

- **Cells per bubble = 20** (Ansys CFX transition-model grid guide; the Stage 1 rule had no source): at C in the first
  approach, at F now (9.1 at VC). Open: whether the coarse level needs it (T6 decides).
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
  floor had thickened small tips (most 0.345 → 0.133; lowest 0.112, limit 0.05). The Re levels stay (Study 10).
- **The refine map (65, 66; 3 Nov 2026, from −5° on 7 Nov).** `cfdauto/mesh/refine_map.py` reads the Stage 1 flow
  dataset for one wing and gives, per strip and side, the envelope of bubbles, transition ± margin and separation over
  the conditions one mesh serves: the band that wing would need. Interactive page `docs/REFINE_MAP.html`
  (https://claude.ai/artifact/KXra2FWoVEFYLHCoafhgye); Study 7 on the Stage 2 page. On the old 20 reference wings
  (Mach 0.03–0.13, −5° to 8°, margin 10 % c) the per-wing band costs +8 % to +46 % (median +34 %) of the first generic
  one; the first generic lower band missed the full 60 % c in front of it on all 20 wings (the new lower band covers
  it); the shortest root bubbles (1.4–10.7 % c) are shorter than the band-cell table assumes (5–14 % c). Candidate, not
  a rule (65): needs a 3-D transition check first. Proposal (66): AVL for the local angle per strip, NeuralFoil for
  the 2-D answer.

## Weak points, said plainly

- Built and screened with the **numpy twin of the loft**, not pyGeo: the pyGeo run on Mike's machine is owed.
- **No solve yet.** Nothing here says the surface gives a good volume mesh or a converged run.
- **The cap quads come close to the 0.05 limit** (@@CAP_VC@@ at VC, @@CAP_F@@ at F); similarity made some caps worse.
- **The stations are 17 % more than the plan file** (station growth 1.2 and 12 gaps per panel at M, as decided, against
  1.25 and 7), so about 17 % more cells than the plan's rules. If the plan file's values were meant, they need a decision.
- **The cell count depends on the wall-layer rule** (here one count per block, 2 chords deep; the 6 Nov rule is not
  written down); the real number comes with the march.
- **The nose is solved at VC and at F:** VC, C and M get a finer nose than their own angle asks, and M still needed a
  repair on @@REP_TXT@@ (the nose cell then breaks the family rule at M).
- **The coarse levels do not resolve transition** (9.1 and 11.8 cells per bubble at VC and C).
- **The band rule rests on one source**, and the lighter band gives the shortest high-Re root bubbles (≈ 1.5 % c)
  only about 3 cells (fine for SA, not for LM).
- **The Stage 1 flow dataset is still at real size** (the refine map, the band count).
- **Studies 1–8 used the old 20 reference shapes**, 13 of which were replaced on 7 Nov.
- **The cell count is an estimate** (one wall-layer count per block, 2 chords deep, no wake lines).
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
- First plan (replaced): boxes (R-V.6): background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, tube 15–20
  cells across the core from 2 c behind the tip, far field 80 c; overset export and the overlap gate (M3).
- New plan (73): one matched C-H multiblock mesh for ADflow and SU2. The C block wraps the ring (the nose stays a
  spacing request inside it, no collar: S6's 5-point collar was the pressure-peak defect); wake lines from the
  trailing-edge corners and the base to the far field (80 c), fine near the trailing edge (0.0075 c as the
  starting value); the stations go on past the tip into outboard H blocks, growing from the tip gap; the tip
  vortex resolved there by clustering along its path (no tube); the cap is the wall of the first outboard block.
  Structured CGNS for ADflow; a converter to unstructured hexes (.su2) for SU2. Rough cost +30–60 % cells.
- Before any solve: Mike's three confirmations (77) and the pyGeo run of the Stage 1 and Stage 2 tests and screens.

## How to run

```
pip install -e CFD_Automation
cd CFD_Automation/Stage_2_surface_mesh
python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5    # levels VC, C, M, F
python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5 --config configs/surface_first.yaml
python -m pytest                       # 35 tests (test_family is slow)
python scripts/screen.py --level VC    # and --level F; --sets reference --level C / M; --resume <part>.jsonl
python scripts/screen_study.py         # merge the parts; data/studies/screen_*.json; docs/page/screen_new_*.png
python scripts/similarity_check.py; python scripts/built_figures.py
python scripts/change_figures.py; python scripts/make_stage2_page.py; python scripts/page_to_markdown.py; python scripts/make_summary_page.py
```
