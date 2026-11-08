# Stage_1 — Handover to the surface mesh (Stage 2 input; updated 8 Nov 2026)

Input for the surface/volume-mesh chat: where the baseline mesh must be fine, per family, before the whole mesh is
refined by r ≥ 1.3, and what the two Stage 1 changes of 7 Nov 2026 change for the mesh. Source: Stage 1 (geometry +
flow study). Read with 'Stage_1 Executive summary' (sections 8–9: reasons, figures as text) and, for details, the
Wing Generator page (`Stage_1_geometry/docs/GEOMETRY_GENERATOR.html`, section "What was first, and what changes").
Live pages of 6 Nov (before the two changes): summary https://claude.ai/artifact/T9JDcKBSfzty7CeFGDnGPx, page
https://claude.ai/artifact/3wwq8Fjj61ETYNzRFjMNw7. Repo: karmix96/aeris, `CFD_Automation/Stage_1_geometry`
(commit cae32b7 or later: the sets rebuilt with both changes).

> **What changed on 7 Nov 2026 (both built; code, tests and sets done).**
> - **Similarity (decision 70; decided by Mike on 6 Nov).** Every wing is built at **unit mean chord**: mean chord
>   = area / full span = 1 (the geometric mean chord, not the MAC; on a BWB the MAC is 1.09–2.06 × larger). A wing
>   has no size: every length is in mean chords (a key ending in `_m` is metres for a 1 m mean chord). The root
>   chord left the vector: 18 → 17 names (c2_ratio, c3_ratio, c4_ratio, semi_span_m, aspect_ratio, b3_ratio,
>   split_ratio, sweep1–3_deg, twist0–3_deg, dihedral_p1–3_deg, plus 4 airfoils); 16 sampled for bwb and cranked,
>   12 for tapered and flying_wing. Semi-span = AR / 2; root chord = 1 / K. The Re on the mean chord is an input of
>   each solve: the four Stage 0 levels, since 8 Nov 1 × 10⁵, 3 × 10⁵, 1 × 10⁶, 4 × 10⁶ (were 1.5 × 10⁶ and
>   3 × 10⁶; decision 78: the Greek tactical BWBs LOTUS and Archytas in cruise, and check C4 on 2-D data). Real Class I–II wings fly at
>   1.22 × 10⁵ – 3.10 × 10⁶ (on area / full span), so 1 × 10⁵ sits 18 % below the slowest real UAV: kept as a
>   margin (Mike, 7 Nov). Mach 0.1 with a Prandtl–Glauert correction on CL and CM is on the solver side.
> - **Trailing edge: 0.2 % of the local chord on every wing.** The floors (0.5 mm Class I, 1.0 mm Class II), the
>   wing class and the switch section are gone. First-approach edges ran from 0.20 to 4.17 % c; 370 of the 730
>   wings had an edge set by a floor. Check C3 (CFD): 0.1 / 0.2 / 0.3 % c and the real floor of small wings,
>   about 0.42 % c.
> - **No 7 m full-span cap** (at unit mean chord the full span is the aspect ratio).
> - **Sets: 722 of 722 built** (7 Nov, numpy loft; 730 before). Corner 1 has 32 / 24 wings (was 34 / 26);
>   training_full, holdout_full and corner 2 keep their shapes; training_focus keeps 99 / 90 / 91 / 88 of its 100
>   shapes (bwb / flying wing / cranked / tapered; the old cap chose by root chord). **13 of the 20 reference wings
>   are new picks** (7 kept: the 4 mid-range wings and 3 of the 4 strongest-washout wings): the reference rules
>   smallest / largest area became lowest / highest aspect ratio. Chords 0.062–3.60 mean chords; aspect ratio =
>   full span in mean chords, 2.5–20. Labels: a value exactly at a threshold now gets the label (tolerance 1e-9;
>   35 wings at exactly 1.0° washout had lost it).
> - **Nose fix (decision 64; Mike, 7 Nov).** One curvature method along the arc showed that the old rule
>   (leading edge at the farthest raw point; each side resampled in √x with a square tangent; PCHIP) made a
>   curvature spike on one side and a flat spot on the other, between the raw points. The built nose failed a 5 %
>   turning-per-cell test on all ten suggested airfoils (NACA 4415: a 0.18 % c nose cell turned 9.47°, the true
>   shape 4.31°). New rule: one cubic spline through the raw points (natural ends at the trailing edge); leading
>   edge = the spline point farthest from the trailing-edge midpoint (its apex); both sides sampled from that
>   spline; **201 points per side**. Database (2,183 files): the 5 % test passes on 95.6 % (old 21.0 %); a gate
>   refuses 14 files whose nose folds back (curvature below −1000/c within 3 % c of arc; none is used). Side
>   effects: leading-edge move median 0.046 % c (max 1.69 % c); chord-line turn median 0.027° (max 0.96°; NACA 4415
>   0.12°). **The 6 Nov note that the nose finding was "overstated" (item 75) was wrong**: the one-sided formula on
>   the raw points saw the same split because the built section passes through those points; the defect sat
>   between them.
> - **Every geometry hash changed.** The pyGeo `build --all` ran on Mike's machine on 8 Nov: 722 of 722 (pyGeo tests 24
>   of 24; the manifests now say pygeo; the reference meshes on pyGeo equal the numpy ones; one label differed from
>   the numpy loft; fixed 8 Nov, decision 79, which changed every input hash but no surface).
> - **Not rebuilt: the Stage 1 flow dataset and flow maps** (`cfdauto/flowmap`). They were made at real size and
>   real speed (first approach) and stay the record. The 2-D section tables are size-free and were rebuilt on
>   the fixed nose (7 Nov; no Stage 1 conclusion changes: `decisions/flow_maps.md`).
>
> Earlier (2–6 Nov, unchanged): Stage 2 surface mesh works (790 of 790 builds pass 13 checks, on the first-approach
> wings; a station on every break; tip squeeze and band built; upper band from the leading edge on every wing).
> Transition must be captured, with ADflow and SU2 (4 Nov). Angles −5° to post-stall, plus a post-stall study
> (6 Nov). Mach scope extends toward 0.5, no supersonic flow (4 Nov); the Stage 1 data stop at Mach 0.2 and at root
> angles 0–10°. Proposals (pending): one matched C-H volume mesh for both solvers (SU2 has no overset); ADflow SA for
> mesh studies and fully turbulent data, SU2 SST + LM on about 20 % of the wings; relaxed band (0.5 % c where local
> Re ≥ 4 × 10⁵); fine level 15.2 M cells median with the planned rules, 10.9 M with the relaxed band; core Mach
> ≤ 0.2 now. Open: one more pyGeo `build --all` (the label fix of 8 Nov, decision 79, changed every input hash); push the raw
> XFOIL data.

## What the two changes mean for the mesh (Stage 2)

- **Mesh at unit mean chord, one mesh per wing and Re level.** Lengths in the loft are in mean chords. The surface
  mesher works in the loft's own length unit and in ratios of the chord (local Re = Re on the mean chord × local
  chord / mean chord), so the same code meshes a unit-mean-chord wing; where its labels say [m], read mean chords.
  The mesh name carries the Re (`mesh_<level>_<wing_hash8>_re<Re>`). The tip gap (s0) and the band cell depend on
  the Re level, not on a size.
- **Every mesh name changes** (every wing hash changed). The 790-build screen ran on the first-approach wings:
  re-screen on the 722 wings of 7 Nov (and on the 20 new reference wings × 4 Re levels).
- **Loft stations only at b0–b3.** No trailing-edge switch section any more, so no station is placed there.
- **Trailing edge 0.2 % c everywhere.** The base is the same fraction of the chord on every wing and every
  station: 8 base cells across 0.2 % c at the coarse level (10, 14, 18 finer), 0.1 % c chordwise spacing at the
  edge.
- **The nose is now the airfoil's nose.** Sections have 401 points (201 per side). On a NACA 4415 station
  (tapered training wing 35, station 21) the 10° nose target holds up to a nose spacing of 0.377 % c with the new
  rule (0.327 % c with the old). **The flat nose line stays**: below 0.2 % c nose spacing the largest turning per
  node is 6.0–6.8° (old 6.6–7.4°); the worst node sits 1.8–2.3 % c down the lower side, where the growth law (1.2)
  sets the cells. It happens on the true airfoil too, so the window search in the Stage 2 nose solve stays needed.
- **The refine map (decision 65, candidate) now runs at the Re levels (7 Nov).** `cfdauto/mesh/refine_map.py`
  has a Re mode: the condition is the Re on the mean chord (speed = Re / (ρ/μ) / mean chord), the tables are read
  at Mach 0.1. On the 20 reference wings, −5° to 8° (`Stage_2_surface_mesh/decisions/refine_map_re.md`): the lower
  band 0–100 % c holds every strip at every level; the upper transition sits past 85 % c at low Re (at 10⁵ only
  0–31 % of the strips fit 0–85 % c). As built there was no gap: band cells reached 100 % c on both sides (one node
  list, lower band 0–100 % c); since 8 Nov the upper band is written 0–100 % c (owner). First: a Mach × angle × altitude grid with the chords read as metres; at unit mean
  chord it missed the two lowest levels (1 × 10⁵, 3 × 10⁵).

## Repo layout (renamed 2 Nov 2026)

Older project docs (Wing Generator page, Executive summary) still show the old names; read them with this map.

| Old | New |
| --- | --- |
| `CFD_Automation/geometry/` | `CFD_Automation/Stage_1_geometry/` |
| `geometry/cfdauto/` (the code) | `CFD_Automation/cfdauto/` |
| `Stage 0_Decisions/` | `Stage_0_decisions/` |
| `STAGE0_DECISIONS.md / .html`, `stage0_values.yaml` | `decisions.md / .html`, `values.yaml` |
| `Stage 0_Decisions/OPEN_DECISIONS.md` | `CFD_Automation/OPEN_DECISIONS.md` (one list, every stage) |
| sets `training`, `holdout` | `training_focus`, `holdout_focus` (`_full` sets, `corner1/2`, `reference` unchanged) |
| mesh name `<family>_<level>_<wing_hash8>` | `mesh_<level>_<wing_hash8>` ("family" = tailless / conventional) |

- New stage folders: `Stage_<N>_<topic>`; Stage 2 goes in `CFD_Automation/Stage_2_surface_mesh/`.
- Code: one shared package, `CFD_Automation/cfdauto/` (`geometry`, `flowmap`; Stage 2 adds `cfdauto/mesh/`),
  installed once with `pip install -e CFD_Automation`. Stage folders keep configs, data, docs and tests;
  `cfdauto/paths.py` says where (commit 69085a4).
- First-approach pictures and data kept as the record: `Stage_1_geometry/docs/first_approach/` (real size, before
  7 Nov).
- The rename changed the geometry code hash, so every input hash changed; on 7 Nov every hash changed again. The
  pyGeo `build --all` of 8 Nov (Mike's machine, 722 of 722) refreshed the manifests; the label fix of 8 Nov (decision 79)
  changed every input hash again (no surface), so the manifests are the numpy rebuild until the next pyGeo build.

## The wings

- One 17-number vector + 4 airfoils (18 before 7 Nov): 4 stations, 3 straight panels, kinks at b1 and b2, blunt
  trailing edge (0.2 % c). Every wing at unit mean chord.
- Families: tailless (bwb, flying_wing; swept 10–40°, washout) and conventional (cranked, tapered; nearly
  straight).
- Focus space: the shapes of Class I and small Class II wings; aspect ratio 3–9 (bwb), 3–13 (flying wing), 4.5–16.5
  (cranked, tapered). Full space: aspect ratio 2.5–20. First approach: full span ≤ 7 m, Mach 0.03–0.13 (tailless),
  0.03–0.20 (conventional).
- Chords (corners of the planform inputs, others mid-range, in mean chords): BWB root up to 2.83 (focus; 4.90
  full), tip down to 0.099 (focus; 0.055 full), up to 17 × from root to tip (focus); the flying wing and the
  conventional types stay within 0.23–2.36 even in the full space.
- Local Re: at the lowest level (1 × 10⁵ on the mean chord) the smallest focus BWB tip runs at about 9.9 × 10³ (full
  space 5.5 × 10³); at the top level (4 × 10⁶ since 8 Nov) the largest focus BWB root at 1.13 × 10⁷ (full space
  1.96 × 10⁷; at 3 × 10⁶ they were 8.5 × 10⁶ and 1.5 × 10⁷). The other types stay within about 4.4 × 10⁴ – 6.2 × 10⁶
  (focus). The section tables reach 1.5 × 10⁷ since 8 Nov (rows 1 × 10⁷ and 1.5 × 10⁷ added). First approach (real size and speed): 1.4 × 10⁴
  (smallest tips, slowest) to 5.5 × 10⁶ (largest BWB roots); up to 17 × from root to tip on a BWB.

## Where the baseline must be fine

| Where | Rule from G1 | Differs by family? | How sure |
| --- | --- | --- | --- |
| Chord: leading edge | no cell turns the surface by more than 10° (law 1); since 7 Nov the nose follows the airfoil file (201 points per side) | no | geometry rule; nose checked along the arc |
| Chord: transition band | fine cells, growth along the surface ≤ 1.25; upper from the leading edge on every wing (written 0–100 % c since 8 Nov, owner; 0–85 % c before, with band cells to 100 % c as built), lower 0–100 % c (decision 74, 7 Nov; first 60–100 % c); a per-wing band from the refine map is a candidate (decision 65; now at the Re levels) | at the Re levels the refine map finds the upper transition past 85 % c at low Re (10⁵: 0–31 % of strips fit 0–85 % c); the lower band 0–100 % c holds every strip | 2-D, calm air; 3-D check pending |
| Chord: bubbles in the band | resolve the bubble: about 0.4 c long at Re 6 × 10⁴, 0.1 c at 4 × 10⁵, down to about 0.015 c at roots above 10⁶ | long on small tips / at the lowest level; short on large roots / at the top level | XFOIL lengths; about 20 cells per bubble (Ansys CFX guidance), proposed as a fine-level target (pending); not met at the shortest root bubbles |
| Chord: trailing edge | 0.1 % c spacing; 8 cells across the blunt base (0.2 % c on every wing since 7 Nov) | no | rule |
| Spanwise: breaks | a station exactly on b1 and b2; spanwise growth ≤ 1.3 (done in Stage 2: a station on every loft station; since 7 Nov the loft stations are b0–b3 only) | all; on the BWB b1 is the centre-body edge | geometry |
| Spanwise: tip | stations squeezed toward the tip; cap first cell = tip first cell (done in Stage 2) | smallest tips on the BWB (down to 0.099 mean chords in the focus space; Re below 10⁵ at the lowest level) | geometry and Re |
| Spanwise: station count | scale with semi-span over mean chord, not a fixed count (Stage 2: gap 0.2 × local chord, at least 12 per panel, growth 1.2); at unit mean chord the semi-span is AR / 2 mean chords | aspect ratio 2.5 to 20 | geometry; proposal |
| Off the wall | first cell from y⁺ ≤ 1 at each case's Re (changes only about 20 % along the semi-span; the smallest chord sets it); growth ≤ 1.25 (1.1 with a transition model: Stage 3 decides, decision 57); ≥ 30 cells across the boundary layer at every station | BWB: root boundary layer up to about 10 × thicker than the tip's, so more layers there | flat-plate estimate; check y⁺ after one solve |
| Around the wing | far field 80 c. The overset wake box (0.0075 c to 2 c, then growing to 10 c) and tip-vortex tube are under review: proposal (pending) is one matched C-H mesh for both solvers, with the wake band sized for −5° to stall and the tip vortex resolved by the outboard blocks | no | roadmap starting values; C-H cost not yet counted |

## Where bubbles appear (upper surface, 2-D XFOIL, N_crit 9, 0–8°)

- Re < 4 × 10⁴: none (open laminar separation). 4 × 10⁴ – 10⁵: starting, long (0.4–0.6 c).
- 1–4 × 10⁵: almost always (93–99 %). 5 × 10⁵ – 1.5 × 10⁶: fading (64 → 26 %). Above: rare (MH 104, LA2573A only).
  (From the section tables built before the nose fix; rebuilt 7 Nov with no conclusion changes.)
- At unit mean chord: local Re = Re on the mean chord × local chord (in mean chords). First approach, in Mach terms:
  Re ≈ 2.3 × 10⁷ × Mach × chord [m] at sea level (1.75 × 10⁷ at 3,000 m).
- 2-D drag gap rerun on 7 Nov on the new sections (XFOIL, 2°): fully turbulent is +39 to +128 % above free
  transition at Re ≥ 3 × 10⁵ (median +81 %), −2 to +21 % at 10⁵.
- At negative angles (now in scope) the lower surface becomes the suction side; the flow dataset covers root angles
  0–10° only (the section tables reach −10° and stop at 14°, before stall).

## Tests, refinement, laws

- Test each baseline at its family's extremes: the lowest and highest aspect ratio, the smallest tip and the
  largest root (in mean chords), at the lowest and the top Re level; −5°, 4° and the highest steady angle.
- Refinement family: the same r ≥ 1.3 along the chord, along the semi-span and off the wall, including the first
  cell and the band spacing (roadmap law 23); y⁺ ≤ 1 on the coarsest level; at least 3 levels.
- Proposal: one set of laws for all types with family parameters (band start, wall layers at the root, tip squeeze,
  station count); a separate BWB rule only if the 3-D check shows the centre body needs one.
- Similarity checks (CFD, to run): C1 scale (mean chord 0.3 m against 1 m), C2 Mach (0.05 / 0.1 / 0.2; CL and CM
  after Prandtl–Glauert), C3 trailing edge (0.1 / 0.2 / 0.3 % c and the real floor 0.42 % c), C4 Re levels
  (interpolation; done on 2-D data on 8 Nov, which added the 1 × 10⁶ level: `scripts/re_ladder_check.py`).

## Decided at the close of G1

- Turbulence-model choice: superseded on 4 Nov: transition must be captured, with ADflow and SU2. Proposed split
  (pending): ADflow SA for mesh studies and fully turbulent data; SU2 SST + LM on about 20 % of the wings. SA inflow
  value (ν̃/ν about 3): fix before the first ADflow solve.
- No flow check before meshing; the first runs of the mesh stage include a 3-D transition-model check (BWB centre
  body first), needed before the paper quotes flow numbers.
- 7 Nov: similarity (decision 70) and the nose rule (decision 64) are decided and built.

## Weak points

- All flow positions are 2-D, calm-air XFOIL strips with a uniform downwash: crossflow, tip stall and the BWB
  centre-body 3-D flow are unknown until the 3-D check. The flow dataset is first approach (real size and speed).
- Real skins and gusts move transition forward; the CFD reference is a smooth wing in calm air. Similarity carries
  size through Re, but not roughness or air turbulence (Tu 0.07 % is fixed), and small real wings have thicker
  trailing edges (about 0.42 % c) than the 0.2 % c rule.
- Cells per bubble now has a source (Ansys CFX guidance, about 20); the shortest root bubbles (about 1.5 % c) are
  shorter than the band-cell table assumes, so 20 cells are not met at roots.
- Nose: settled (decision 64). The gate refuses 14 database files (very sharp or flat-faced noses; none used). On
  coarse files (about 61 points) the raw file itself does not settle the nose turning at the smallest cells better
  than about ±15 %.
- The pyGeo build ran on 8 Nov (722 of 722; Mike's machine). Stage 2 screened the 7 Nov wings on 7 Nov: 1,724 of 1,724 builds pass (every set at
  VC and F at Re 3 × 10⁵; the 20 reference wings at all four levels and Re levels); on 8 Nov every set at every level:
  3,128 of 3,128, with no nose repair (one factor per family, Stage 2 decision 80).
