# Stage_2 — Surface mesh: status and handover (2 Nov 2026)

Text copy for chats in this project. Repo: karmix96/aeris, branch `stage2-surface-mesh`,
`CFD_Automation/Stage_2_surface_mesh/` (configs, decisions, docs, tests, scripts, studies) and the code in
`CFD_Automation/cfdauto/mesh/`. Read first: the page `Stage_2_surface_mesh/docs/SURFACE_MESH.html` (live: https://claude.ai/artifact/6SXM1yDgwbPvgNRsDb24fi; text copy: 'Stage_2 Surface mesh page'), then `Stage_2_surface_mesh/README.md` (how to run, the rules table,
the checks) and `decisions/surface_rules.md` (why, and what the screen showed). Built and screened here with
the numpy twin of the loft; not yet run with pyGeo (Mike's machine).

## What Stage 2 is

One wing surface (the Stage 1 loft) in, one structured surface mesh out: a closed ring of points around the
section at every span station, root to tip, plus one patch closing the flat tip. Every node is asked from the
loft. The volume mesh, the wake boxes and the CGNS file are Stage 3.

- Name: `mesh_<level>_<wing_hash8>_re<Re>` (the surface depends on the Re on the mean chord: tip gap, band cells).
- Files per mesh: `surface.npz`, `surface.xyz` (Plot3D), `stations.csv` (asked and delivered per station),
  `quality.json` (every check), `manifest.json` (hashes). A refused mesh writes only `refusal.json`.
- One mesh takes 4–8 s. Levels C, M, F, FF: every spacing ÷ 1.3 per level, and the growth g becomes g^(1/1.3),
  so a finer level is a true scaled copy (ring nodes and stations both × 1.3; checked on the four reference wings:
  `data/studies/family_ratios.json`).

## The rules, as built (level C)

| Where | Rule | Source |
| --- | --- | --- |
| Nose | no ring node turns the surface by more than 10°, solved by bisection on the ring as built; away from the nose the same angle caps the cell from the local curvature radius | law 1 (S8) |
| Nose along the span | nose spacing / chord changes by at most 1.15 between stations, only tightening | law 2 (S8) |
| Trailing edge | 0.1 % of local chord at the corners; 8 cells across the base (10, 14, 18 at M, F, FF) | laws 3, 6 (DPW; S8) |
| Transition band | upper 0–85 % c, lower 60–100 % c; cell = bubble length / 20, bubble length from the local Re (Stage 1 table: 0.40 c at 6 × 10⁴, 0.30 at 10⁵, 0.10 at 4 × 10⁵, 0.05 at and above 10⁶) | Stage 1 handover; Ansys CFX transition-model grid guide (≥ 20 nodes per bubble) |
| Elsewhere | cells grow by at most 1.2 (checked 1.25), never above 2 % c | DPW; handover |
| Stations | one exactly on every loft station (b0–b3 and the trailing-edge switch station); gap = 0.2 × local chord, at least 12 per panel; growth 1.2 (checked 1.3) | laws 8, 9 (our starting values) |
| Tip | stations squeezed so the last gap = the tip first cell s0 (y⁺ = 1 at the tip Re, turbulent flat plate) | laws 9, 10, 13 |

Both sides of a ring share one node distribution (in arc fraction; the stricter side wins), so the tip cap's
cross lines stay upright. One point count per side for the whole wing: the station that needs most (usually
the root) sets it; the others put their spare points in their largest cells, never coarser than asked.

Cost of the band rule: about 200 ring nodes at Re 10⁵, 400 at 3 × 10⁵, 850 at and above 1.5 × 10⁶ (S8: 150).
This is the first thing the chordwise ladder (Grand Roadmap T6) must test.

## Checks that refuse (13)

nose turning, geometry kinks, nose envelope, chord growth, band spacing, trailing-edge spacing, span growth,
loft stations hit, tip gap, every ring in its station plane, wing quads (scaled Jacobian ≥ 0.05), cap quads
(≥ 0.05; the two nose-corner cells reported apart, refused only if folded), ring count. A refused mesh writes
only `refusal.json`. Tests: 14 (`tests/mesh/`), including the family ratio test.

## The screen (level C, numpy loft)

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
The lowest wing-quad quality (0.09) is on corner wings whose first panel is 4–6 mm wide with a 50 mm chord
drop (an 85° trailing-edge sweep): a property of those wings. Three earlier passes of the screen were development
evidence: they found and fixed the tip-gap tolerance, kinked noses on the corner set, a 0.9 mm panel, sheared
quads in the tip squeeze (0.08), the 1.25–1.26 growth on NACA 4415 noses and a nose held over one cell instead of four.

## What was found and decided (OPEN_DECISIONS 56–66; `decisions/surface_rules.md`)

- **Cells per bubble = 20 at level C** (Ansys CFX transition-model grid guide; the Stage 1 rule had no source).
  Costs 400–850 ring nodes against S8's 150. Open: whether the coarse level needs the full 20 (T6 decides).
- **Wall-normal growth 1.1 for a transition model** (same guide; Stage 0 says 1.25): a Stage 3 decision.
- **Upper band from the leading edge on every wing** (not only on swept panels): one rule, ~10 % c more.
- **One surface per wing and Re level**; the name carries the Re.
- **One node distribution for the whole wing** (not per station): the per-station version sheared the quads
  where the tip stations are tens of µm apart (scaled Jacobian 0.08 → 0.58 on the worst wing). +3 % nodes.
- **Base cells 8, 10, 14, 18 per level** (even, so the cap's nose arc stays centred): ratios 1.25, 1.4, 1.29.
- **Stage 1 finding (64): the built sections' nose is not round.** NACA 4415: 0.0248 c by formula, built
  0.008 c (upper) / 0.074 c (lower) at the leading edge; E387: 0.0102 raw → 0.0028 / 0.035; MH 104: 0.0084 →
  0.018 / 0.0048 (`data/studies/nose_radius.json`). Within the first ~0.1 % c. The mesh follows the loft as
  built. It matters for the suction peak and for a nose-radius law. Fix in Stage 1 (changes every hash) or
  carry as a stated deviation: Mike decides.
- **The refine map (65, 66; 3 Nov 2026).** `cfdauto/mesh/refine_map.py` reads the Stage 1 flow dataset for one
  wing and gives, per strip and side, the envelope of bubbles, transition ± margin and separation over the
  conditions one mesh serves: the band that wing would need. Interactive page `docs/REFINE_MAP.html`
  (https://claude.ai/artifact/KXra2FWoVEFYLHCoafhgye); Study 7 on the Stage 2 page. On the 20 reference wings
  (Mach 0.03–0.13, 0–8°, margin 10 % c) the per-wing band costs −15 % to +20 % of the generic one (median
  about +5 %): not smaller, elsewhere. The generic band is mis-placed on every wing: the upper surface stays
  laminar beyond 85 % c at low angle outboard (missed by up to 15 % c), the lower surface transitions near the
  leading edge on washed-out panels (missed by 52–60 % c). The shortest root bubbles (1.4–10.7 % c) are shorter
  than the band-cell table assumes (5–14 % c) on all 20 wings. Candidate, not a rule (65): needs a 3-D
  transition check first. Proposal (66): AVL for the local angle per strip, NeuralFoil for the 2-D answer.

## Weak points, said plainly

- Built and screened with the **numpy twin of the loft**, not pyGeo: the pyGeo run on Mike's machine is owed
  (the loft surfaces are the same construction; the tests compare the two backends in Stage 1).
- **The band rule is a cost jump** (×3–6 ring nodes against S8) with one source (a vendor guide for one
  transition model); it is the first thing the chordwise ladder must test, and the coarse level may relax.
- **No solve yet.** Nothing here says the surface gives a good volume mesh or a converged ADflow run; the
  tip squeeze (about 40 gaps on the last panel, down to tens of µm) and the 85°-sweep corner wings are where
  the march will be tested first.
- **The nose artefact (64)** is in every mesh of every wing; the mesher adapts, the geometry is wrong.
- The station-count rule (0.2 × chord, 12 per panel) and the 2 % c cap are starting values without a ladder.
- **The generic band is in the wrong place on washed-out panels** (refine map, Study 7): the mesh is fine where
  the 2-D strips say the flow is already turbulent and coarse where they say it transitions. Whether the 3-D
  flow agrees is unknown; the band-cell rule under-resolves the shortest root bubbles by 1.2–3.6 ×.

## Handover to Stage 3 (volume mesh, wake boxes, CGNS)

- Input: `surface.npz` per mesh: `wing (n_ring, n_span, 3)` ring-first, root to tip; `cap (n_chord, n_base, 3)`
  with i × j outboard; `u`, `y`, `v` per node and station; `stations.csv` with the local Re, chord, s0 need.
- The march (Grand Roadmap R-V): first cell s0 from the local Re and y⁺ = 1 per station (law 13; the tip
  value is already in `manifest`/`quality.json` as `s0_tip_m`); growth ≤ 1.25 in the boundary layer, or 1.1 if
  the transition model is kept open (decision 57); ≥ 30 cells across the boundary layer; reach about 2 chords;
  cap first cell = tip s0 (the surface delivers the last station gap = s0, so the cap faces a matching cell).
- The family: every spacing ÷ 1.3 per level and the growth g^(1/1.3), as on the surface, so the volume levels
  are true scaled copies too; the base cells follow 8 / 10 / 14 / 18.
- Boxes (R-V.6): background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, tube 15–20 cells across the core
  from 2 c behind the tip, far field 80 c (T2 decides); overset export and the overlap gate (M3).
- Before any solve: decide 64 (the nose), and run the Stage 2 tests and screen with pyGeo.

## How to run

```
pip install -e CFD_Automation
cd CFD_Automation/Stage_2_surface_mesh
python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5
python -m pytest                       # 14 tests (test_family builds C and M of the BWB: slow)
python scripts/screen.py               # ~1 h on two cores; then scripts/merge_screen.py if run in parts
python scripts/family_check.py; python scripts/make_figures.py; python scripts/nose_radius.py
```
