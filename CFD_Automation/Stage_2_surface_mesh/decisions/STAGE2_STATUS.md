# Stage_2 — Surface mesh: status and handover (2 Nov 2026, updated 6 Nov 2026)

Text copy for chats in this project. Repo: karmix96/aeris, branch `stage2-surface-mesh`,
`CFD_Automation/Stage_2_surface_mesh/` (configs, decisions, docs, tests, scripts, studies) and the code in
`CFD_Automation/cfdauto/mesh/`. Read first: the page `Stage_2_surface_mesh/docs/SURFACE_MESH.html` (live: https://claude.ai/artifact/6SXM1yDgwbPvgNRsDb24fi; text copy: 'Stage_2 Surface mesh page'), then `Stage_2_surface_mesh/README.md` (how to run, the rules table,
the checks) and `decisions/surface_rules.md` (why, and what the screen showed). Built and screened here with
the numpy twin of the loft; not yet run with pyGeo (Mike's machine).

> **What was first, and what changes (6 Nov 2026).** Everything below the box was built and screened on 2–3 Nov
> with the **first approach**; it is still what the code does. On 4–6 Nov a **new approach** was decided (owner);
> it is not built yet. Decisions 67–76 in `CFD_Automation/OPEN_DECISIONS.md`.
>
> | What | First (built 2–3 Nov) | New approach | Status |
> | --- | --- | --- | --- |
> | Levels | C, M, F, FF; every rule met at C, the coarsest | VC, C, M, F; hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap), accuracy targets at M (nose 10°, TE 0.1 % c, station gap, largest cell), transition targets at F (20 cells per bubble, wall growth ≈ 1.1); VC on the desktop, C/M/F on the HPC | decided (71), to build |
> | Band cell | bubble length / 20 at C; 0.40 / 0.30 / 0.10 / 0.05 c at local Re 6e4 / 1e5 / 4e5 / 1e6 | bubble length / 20 at F; bubble length floor 0.10 c from local Re 4e5 (0.5 % c at F) | decided (72), to build |
> | Stations, tip | gap 0.2 × chord at C, ≥ 12 per panel; last gap = s0 | gap 0.25 × chord at M, ≥ 12 per panel at M; last gap = 2 × s0 | decided (72), to build |
> | Lower band | 60–100 % c (angles 0–8°) | angles −5° to post-stall: option A lower band from the leading edge (band ≈ 1.5 × longer), option B transition (LM) runs only at ≥ 0° | pending (74): count both on the 20 reference wings |
> | Volume mesh | O-H body mesh + overset wake box + tip-vortex tube (ADflow only) | one matched C-H mesh for ADflow and SU2 (SU2: converted to unstructured hexes); wake lines to the far field; tip vortex in the outboard blocks; the ring and cap unchanged | decided (73), Stage 3 |
> | Similarity | real size; TE max(0.5 / 1.0 mm, 0.2 % c) | unit mean chord; Re an input (4 levels); Mach 0.1 + Prandtl–Glauert; TE 0.2 % c; root chord out (18 → 17) | decided (70); Stage 1 code first (every hash) |
> | Flow model, angles, Mach | ADflow SA; 0–8°; Mach 0.03–0.20 | transition with ADflow and SU2 (67; split pending, 76); −5° to post-stall + post-stall study (69); toward Mach 0.5, no supersonic, core ≤ 0.2 (68) | decided; split and core pending |
> | Nose (64) | "the built nose is not round" | overstated: raw files measured the same way show nearly the same split (NACA 4415 raw 0.0081 / 0.0736 c, built 0.0080 / 0.0741 c); re-measure with one curvature method; fix only if needed (75) | to do next |
> | Fine level | no target | F ≈ 10–11 M cells median (wing blocks): 10.9 M with the lighter band, 15.2 M with the planned rules; C-H wake lines ≈ +45 % (rough, 30–60 %) | estimate, to screen |

## What Stage 2 is

One wing surface (the Stage 1 loft) in, one structured surface mesh out: a closed ring of points around the
section at every spanwise station, root to tip, plus one patch closing the flat tip. Every node is asked from the
loft. The volume mesh, the wake boxes and the CGNS file are Stage 3.

- Name: `mesh_<level>_<wing_hash8>_re<Re>` (the surface depends on the Re on the mean chord: tip gap, band cells).
  New approach: every wing at unit mean chord, so four surfaces per wing and level (one per Re level).
- Files per mesh: `surface.npz`, `surface.xyz` (Plot3D), `stations.csv` (asked and delivered per station),
  `quality.json` (every check), `manifest.json` (hashes). A refused mesh writes only `refusal.json`.
- One mesh takes 4–8 s. Levels C, M, F, FF: every spacing ÷ 1.3 per level, and the growth g becomes g^(1/1.3),
  so a finer level is a true scaled copy (ring nodes and stations both × 1.3; checked on the four reference wings:
  `data/studies/family_ratios.json`).

## The rules, as built (level C; first approach — the new values are in the box above)

| Where | Rule | Source |
| --- | --- | --- |
| Nose | no ring node turns the surface by more than 10°, solved by bisection on the ring as built; away from the nose the same angle caps the cell from the local curvature radius | law 1 (S8) |
| Nose along the semi-span | nose spacing / chord changes by at most 1.15 between stations, only tightening | law 2 (S8) |
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
- **Stage 1 finding (64), first reading (2 Nov; overstated, see the box and 75): the built sections' nose is not round.** NACA 4415: 0.0248 c by formula, built
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
- **The nose (64):** the first reading was overstated (the raw files measured the same way show nearly the same
  split); what may remain sits inside the first raw-point gap (under 0.025 % c on NACA 4415, about 7 × smaller
  than the 0.18 % c nose cell of the NACA 4415 reference wings). Re-measure before any fix.
- **The new approach is not built:** the cell counts (F ≈ 10–11 M, C-H wake lines ≈ +45 %) are estimates, and the
  lighter band gives the shortest high-Re root bubbles (≈ 1.5 % c) only about 3 cells (fine for SA, not for LM).
- The station-count rule (0.2 × chord, 12 per panel) and the 2 % c cap are starting values without a ladder.
- **The generic band is in the wrong place on washed-out panels** (refine map, Study 7): the mesh is fine where
  the 2-D strips say the flow is already turbulent and coarse where they say it transitions. Whether the 3-D
  flow agrees is unknown; the band-cell rule under-resolves the shortest root bubbles by 1.2–3.6 ×.

## Handover to Stage 3 (volume mesh, CGNS)

- Input: `surface.npz` per mesh: `wing (n_ring, n_span, 3)` ring-first, root to tip; `cap (n_chord, n_base, 3)`
  with i × j outboard; `u`, `y`, `v` per node and station; `stations.csv` with the local Re, chord, s0 need.
- The march (Grand Roadmap R-V): first cell s0 from the local Re and y⁺ = 1 per station (law 13; the tip
  value is already in `manifest`/`quality.json` as `s0_tip_m`); growth ≤ 1.25 in the boundary layer;
  ≥ 30 cells across the boundary layer; reach about 2 chords; cap first cell = tip s0 (the surface delivers the
  last station gap = s0, so the cap faces a matching cell). New: y⁺ ≤ 1 and growth 1.25 are hard minimums at
  VC, so F gets y⁺ ≈ 0.46 and growth 1.107, which meets the 1.1 a transition model asks for (57); tip gap 2 × s0.
- The family: every spacing ÷ 1.3 per level and the growth g^(1/1.3), as on the surface, so the volume levels
  are true scaled copies too; the base cells follow 8 / 10 / 14 / 18 (new names VC, C, M, F).
- First plan (replaced): boxes (R-V.6): background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, tube 15–20
  cells across the core from 2 c behind the tip, far field 80 c; overset export and the overlap gate (M3).
- New plan (73): one matched C-H multiblock mesh for ADflow and SU2. The C block wraps the ring (the nose stays a
  spacing request inside it, no collar: S6's 5-point collar was the pressure-peak defect); wake lines from the
  trailing-edge corners and the base to the far field (80 c), fine near the trailing edge (0.0075 c as the
  starting value); the stations go on past the tip into outboard H blocks, growing from the tip gap; the tip
  vortex resolved there by clustering along its path (no tube); the cap is the wall of the first outboard block.
  Structured CGNS for ADflow; a converter to unstructured hexes (.su2) for SU2. Rough cost +30–60 % cells.
- Before any solve: the nose re-measure (64/75), similarity in Stage 1, the new rules and screen, and the
  pyGeo run of the Stage 1 and Stage 2 tests and screens.

## How to run

```
pip install -e CFD_Automation
cd CFD_Automation/Stage_2_surface_mesh
python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5
python -m pytest                       # 14 tests (test_family builds C and M of the BWB: slow)
python scripts/screen.py               # ~1 h on two cores; then scripts/merge_screen.py if run in parts
python scripts/family_check.py; python scripts/make_figures.py; python scripts/nose_radius.py
```
