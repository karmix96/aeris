# Stage 3 — volume mesh: the plan, the rules and the checks (V0, 9 Nov 2026)

Branch `stage3-volume-mesh` (from `stage2-surface-mesh`: Stage 2 is not merged into main yet). Code:
`CFD_Automation/cfdauto/volume/`. Rules: `configs/volume.yaml`. Decisions 84–93 in `CFD_Automation/OPEN_DECISIONS.md`.

## 0. In one breath

- One matched C-H multiblock mesh on the frozen Stage 2 surface (decision 73), for ADflow (structured CGNS) and SU2
  (the same mesh as unstructured hexes, `.su2`).
- Every wall node is a Stage 2 node. The volume code is new (`cfdauto/volume/`); `cfdauto/mesh/` is not touched.
- In each station plane (y = const) a C around the ring and the wake, out to the far field. The planes are stacked
  root to tip; past the tip the tip plane is swept outboard, and the tip cap with it.
- Every check and its limit is in this file and in `configs/volume.yaml`. They were written before any mesh was
  judged and have not changed since.

## 1. The plan

| Step | What | Ends with |
| --- | --- | --- |
| V0 | rules, checks and limits; how to build a station plane (measured); the boundary-layer law (measured) | this file; Mike's word on the checks |
| V1 | BWB reference wing 0, VC, Re 3 × 10⁵: the 13 blocks, every check, slices, cells against Stage 2 | a conclusion |
| V2 | wall layers, fine zone, far field on the 20 reference wings at VC; orthogonality at the nose and the base | a conclusion |
| V3 | the cap block and the outboard H blocks; the tip-vortex rule; cap and outboard quality on every reference wing | a conclusion |
| V4 | the family VC, C, M, F (as memory allows; F counted if it does not fit); every spacing ratio | a conclusion |
| V5 | CGNS writer and reader (ADflow), `.su2` converter (SU2); round trips; tests | tests pass |
| V6 | the screen: every built set at VC (not the hold-outs), C and M where memory allows, F counted | pass / refuse / review |
| V7 | first solves: ADflow SA, SU2 SA, SU2 SST + LM on one wing (here: run scripts and a runbook) | smoke test |
| V8 | the hold-outs, once, rules frozen, with Mike's OK | the result as it is |
| V9 | page, summary, status, handover to Stage 4 | Mike closes Stage 3 |

## 2. The C-H layout: 13 blocks

In one station plane, six blocks; every block is right-handed with k along +y (root → tip).

| Block | i runs | j runs | Wall | Far field | Matched |
| --- | --- | --- | --- | --- | --- |
| WU (upper wake) | outflow → trailing edge along the upper wake line | up to the far field | — | iMin (outflow), jMax | iMax = CU iMin; jMin = B iMax |
| CU (upper side) | ring 0 (upper TE corner) → start of the cap's nose arc | out to the far field | jMin (wing) | jMax | iMax = CN iMin |
| CN (nose arc) | the n_base ring nodes of the cap's nose arc | out | jMin | jMax | iMax = CL iMin |
| CL (lower side) | end of the nose arc → ring 2 n_side − 2 (lower TE corner) | out | jMin | jMax | iMax = WL iMin |
| WL (lower wake) | trailing edge → outflow along the lower wake line | down to the far field | — | iMax (outflow), jMax | jMin = B iMin |
| B (base) | across the base, lower → upper wake line | along the wake to the outflow | jMin (the base) | jMax (outflow) | iMin = WL jMin; iMax = WU jMin |

- `*_in`: these six from the root (kMin: symmetry, y = 0) to the tip (kMax = `*_out` kMin).
- `*_out`: the same six from the tip to the far field past the tip (kMax: far field). Their jMin faces (CU, CN, CL)
  and B's jMin are matched to the sides of the cap block.
- `CAP`: the Stage 2 tip cap (n_chord × n_base) swept outboard. kMin = the cap (wall), kMax far field; its four sides
  are matched to CU_out, CN_out, CL_out (jMin) and B_out (jMin).
- Every face is one boundary condition or matched node to node with one face of one other block (no partial faces).
  The table is `cfdauto/volume/topology.py`.

## 3. The rules (anchors as in Stage 2; r = 1.3)

| Rule | Anchor value | VC | C | M | F | Why |
| --- | --- | --- | --- | --- | --- | --- |
| First wall cell s0 (law 13) | y⁺ 1 at VC | y⁺ 1 | 0.77 | 0.59 | 0.46 | Stage 2's law, per station at its local Re; the same s0 off the base and off the cap |
| Wall growth, inside the fine zone | 1.25 at VC | 1.25 | 1.187 | 1.141 | 1.107 | decision 71 (DPW) |
| Cells across the boundary layer | 30 at VC | 30 | 39 | 50.7 | 65.9 | Annex G: ≥ 30 at the baseline; decision 86 |
| Boundary-layer thickness δ | turbulent flat plate at the trailing edge, from the local Re | | | | | decision 86 (measured, section 6.2) |
| Fine zone | 2 local chords | same | | | | law 20; the depth Stage 2's estimate used |
| Growth beyond the fine zone, checked | 1.30 at VC | 1.30 | 1.224 | 1.168 | 1.127 | Annex G: ≤ 1.3 anywhere outside the boundary layer; decision 85 |
| ... built | 1.22 at VC | 1.22 | 1.165 | 1.125 | 1.095 | built below the limit, as Stage 2 builds the ring at 1.2 and checks 1.25: the far-field blend raises it (section 7, changes 5 and 10) |
| Far field | 80 mean chords | same | | | | law 15; 40 / 80 / 160 is Stage 4 (T2) |
| Wake band: angles | −5° to 20°, margin 0.05 c | same | | | | the brief: −5° to post-stall; decision 87 |
| Wake band: length | 2 local chords behind the trailing edge | same | | | | law 20 (the fine zone) |
| Wake band: cell at the trailing edge | 0.0075 c at M | 1.27 % c | 0.98 % c | 0.75 % c | 0.58 % c | Primer section 05 (about 20 cells across a 0.15 c wake) |
| Wake band: cells across the fan | 40 at M | 23.7 | 30.8 | 40 | 52 | decision 87: the cell grows with the distance so the fan keeps this many cells |
| Wake band: streamwise cell | ≤ 4 × the band cell | same | | | | decision 87 |
| Wake: first cell behind the base | s0 of the station | | | | | the base is a wall (decision 90) |
| Outboard: first gap | the wing's last gap (2 s0 at the tip) | | | | | law 10 / 12 |
| Outboard growth, to 2 c past the tip | 1.15 at VC | 1.15 | 1.114 | 1.086 | 1.066 | the brief's starting value (law 12) |
| ... beyond, to 80 c past the tip | the far growth: 1.3 at VC (the checked value; a 1-D spacing, no blend) | 1.3 | 1.224 | 1.168 | 1.127 | decision 88 (section 7, change 9) |
| Base cells | Stage 2: 8 / 10 / 14 / 18 | | | | | Stage 2 decision 61 (frozen) |

How a station plane is built (decision 84, section 6.1):
1. The C line: upper wake line (outflow → corner), the Stage 2 ring from the upper to the lower corner, the lower wake
   line (corner → outflow). The wake centre line leaves the base along its normal and turns to +x over 0.5 local chord;
   the two wake lines are parallel to it, the base height apart.
2. The line shapes: one front moved the same distance everywhere from the C line, smoothed along itself over a width
   κ × its distance from the wall (κ = 1; at the wall no smoothing, so the lines leave square to it), through the fine
   zone; then a straight piece to the far-field node. The far-field nodes are the mean over the stations of where the
   lines would land, so the far field is one grid extruded along the semi-span.
3. The nodes: one wall-normal distribution per station (s0, the boundary-layer zone, the fine zone, the wake band as an
   envelope in height, the far growth), the same count for every station; each line keeps it near the wall and shortens
   only its outer part to its own length. The wake lines keep the wall spacing along the cut (as classic C meshes do).
   To give every station the same count, its growth (never the band cell) is scaled down by one factor; past the band
   the envelope keeps rising at the growth law's own rate (g − 1), so the cells leave the band smoothly (section 7,
   changes 7 and 8).
4. The outer layers of every station move toward the station mean (smoothstep from the first layer past every
   station's fine zone and band, to the far field), and the far wake nodes toward the station-mean x: neighbouring
   stations then line up far out, and the cells between them stay square.
5. The base block between the two wake lines by transfinite interpolation.
6. If a cell folds, every station is rebuilt with the next smoothing (κ = 1, 1.5, 2, 3); the rung is stored.

The tip vortex (law 19): its path from the tip trailing edge at −5° to 20° lies inside the wake band (in the plane);
along the semi-span it is held by the tip squeeze inboard (Stage 2: last gap 2 s0, growth 1.2) and by the outboard
stations (first gap the same, growth 1.15). No other clustering (decision 88). V3 measures the cells at the path.

## 4. The checks and their limits

Written before any mesh was judged (`configs/volume.yaml`, `checks:`). A mesh refuses if any refusing check fails
(it writes only `refusal.json`: which check, its value, its limit).

| # | Check | What is measured | Limit | Refuses | Why |
| --- | --- | --- | --- | --- | --- |
| 1 | Wall on the surface | every wall node (wing, base, cap) against the Stage 2 node | ≤ 1e−12 c | yes | decision 82: the surface is frozen |
| 2 | No folded cell | the Jacobian at every corner of every cell | > 0 | yes | a folded cell stops the solver or gives nonsense |
| 3 | Cell quality | the smallest corner scaled Jacobian of every cell | ≥ 0.05 | yes | Stage 2's limit for the surface quads; the cap's cells inherit it |
| 4 | Wall orthogonality | in the station plane, the angle between the first grid line and the ring normal (bisector), every wall node but the two trailing-edge corners | ≤ 5° | yes | the boundary layer needs lines square to the wall; the 3-D angle is reported (decision 89) |
| 5 | First cell | the first cell of every wing and base line against the station's s0 | within 1 % | yes | law 13; y⁺ ≤ 1 is a hard minimum |
| 6 | Growth | along every wall-normal line: inside the fine zone against the wall growth, beyond against the far growth | ≤ limit × 1.01 | yes | DPW; Annex G |
| 7 | Cells across the boundary layer | cells between the wall and δ (turbulent flat plate at the trailing edge, local Re) | ≥ 30 at VC (39, 50.7, 65.9) | yes | Annex G; decision 86 |
| 8 | Interfaces | every matched pair of faces, node to node; no open face | ≤ 1e−10 c | yes | a gap is a hole in the domain |
| 9 | Symmetry plane | y on every root face | \|y\| ≤ 1e−12 c | yes | ADflow and SU2 need a true plane |
| 10 | Far field | the distance from every far-field node to the nearest wall node | ≥ 80 c | yes | law 15 |
| 11 | Wake | the streamwise growth along the wake lines (wall growth inside the band length, far growth beyond); every cell inside the band against the band cell | ≤ limit × 1.01 | yes | laws 17, 18 |
| 12 | Outboard | the first gap past the tip against the wing's tip gap; the growth (1.15 to 2 c, the far growth beyond) | 1 %; × 1.01 | yes | law 12 |
| 13 | Family ratios | between neighbouring levels: s0 per station, the wall growth limit, the band cell, the first outboard gap, the first wake cell, the cell at 1 local chord from the root's wall and behind the root's trailing edge | 1.3 within 3 % | yes (V4) | law 23; exceptions named: the base cells 8 / 10 / 14 / 18 (Stage 2) and the whole-number counts (layers, wake nodes, outboard stations) |
| 14 | Cells and RAM | cells; RAM = 1.51 GiB + 9.46 GiB per million cells (ADflow, ANK only) | information | no | where a mesh fits: desktop 16 GB ≈ 1.2 M cells; + 36 GB ≈ 5 M; F on the HPC |
| 15 | Export round trip | the CGNS file read back against the arrays; the `.su2` file: nodes, cells, markers, no inside-out cell | exact (CGNS); counts equal (`.su2`) | yes (V5) | the solvers must see the mesh that was checked |

Three outcomes:
- **passed**: every refusing check passes and no review flag is raised;
- **refused**: a refusing check fails (`refusal.json`);
- **needs review**: every check passes, but R1 is raised: the plane grid needed a smoothing rung above the first
  (κ > 1), so a human looks at the far field before it is used.
- A failure stays in every count.

Also reported (not checked): the 3-D angle between the first line and the surface normal (median, 95th percentile,
largest); the in-plane angle at the two trailing-edge corners; the smallest scaled Jacobian per block; the spacing
jump across the trailing-edge line (the last chordwise cell of the wing, Stage 2's 0.1 % c at M, against the first
cell behind the base, s0); the smoothing rung; the build time.

## 5. Planar stations and the 3-D wall angle (decision 89)

- Every Stage 2 ring lies in its plane y = const (measured: within 4e−15 c). The volume lines stay in that plane.
- So the lines are square to the wall in the plane, but not in 3-D where the surface is swept or has dihedral: at a
  swept nose the angle between the line and the surface normal is the sweep. The cell is then sheared, not folded;
  its first cell is s0 · cos(angle) along the normal, so y⁺ falls.
- The refusing check (4) is the in-plane angle, which the mesher controls. The 3-D angle is reported on every mesh.
  A 3-D march would bend the station planes near the wall; near the tip, where the stations are 2 s0 apart, they
  would cross. Not built unless a solver result shows a problem.

## 6. The V0 measurements

### 6.1 How to build a station plane (`scripts/plane_method_study.py`, `data/studies/plane_method.json`)

The same inputs for three methods: the same C line, far-field nodes and node distribution. Every station plane of 8
reference wings (2 per type) at VC, Re 3 × 10⁵: 501 planes. No volume mesh was judged.

| Method | Planes with a folded quad | Smallest scaled Jacobian (median of the planes) | Largest in-plane wall angle | Growth / limit | Time |
| --- | --- | --- | --- | --- | --- |
| march (front with smoothing, then straight; the nodes placed along the lines) | 0 of 501 | 0.626 (0.927) | 0.05° | 0.997 | 6.6 s |
| algebraic (cubic lines from the wall normal to the far-field node) | 501 of 501 | −1.0 | 0.00004° | 0.998 | 5.8 s |
| elliptic (the algebraic grid + 300 Winslow sweeps past the fine zone) | 501 of 501 | −1.0 | 0.00004° | 15.4 | 231 s |

- What it shows: the algebraic lines cross at the two trailing-edge corners, where the C line turns inward by about
  half the trailing-edge wedge angle (cranked wing 0, station 10: 314 folded quads of 29,520, all near the corners,
  from 0.0004 c out to the far field). 300 Winslow sweeps do not untangle them and destroy the growth outside the
  held fine zone.
- Conclusion: **the march** (decision 84). The options are not close, so this is not a question for Mike.
- A 3-D march is not needed for validity: with planar stations a stacked cell can only fold if neighbouring plane
  grids differ in shape; V1 shows this happens far out unless the far field is shared (section 3, step 4).

### 6.2 Which boundary-layer thickness the 30 cells cross (`scripts/bl_law_study.py`, `data/studies/bl_law.json`)

Counts only (no mesh): the wall-layer count each variant needs at VC (the most over the stations), the 20 reference
wings × 4 Re levels.

| Variant | Layers at VC, median (largest) at Re 1e5 / 3e5 / 1e6 / 4e6 | Smallest growth it needs inside δ |
| --- | --- | --- |
| turbulent, at the trailing edge, 30 at VC | 88.9 (92.3) / 89.3 (93.3) / 89.8 (94.2) / 90.7 (97.2) | 1.022 at Re 1e5 |
| turbulent, at mid-chord, 30 at VC | 93.3 (96.4) / 92.9 (97.1) / 93.0 (97.2) / 93.3 (98.1) | 1.000: infeasible at Re 1e5 |
| laminar (Blasius), at mid-chord, 30 at VC | 99.7 (104.2) / 100.7 (105.3) / 102.2 (107.2) / 104.2 (109.2) | 1.000: infeasible at Re 1e5 |
| turbulent, at the trailing edge, 30 at M | 75.2 (81.7) / 79.8 (86.2) / 84.8 (91.2) / 90.7 (97.2) | 1.094 |
| laminar, at mid-chord, 30 at M | 82.8 (87.3) / 84.3 (89.3) / 86.2 (91.2) / 90.7 (97.2) | 1.029 |

- What it shows: at Re 10⁵ the small tips have a layer thinner than 30 first cells at mid-chord (laminar or
  turbulent), so 30 cells at VC cannot be met there by any growth. At the trailing edge the turbulent layer always
  fits 30 cells. The rule costs little: the wake band and the fine zone already set most of the layers (88–97).
- Conclusion: **δ = turbulent flat plate at the trailing edge (0.37 x Re_x^−1/5, x = the local chord), from the local
  Re; 30 cells at VC, × 1.3 per level** (decision 86). Weak point: the laminar layer at mid-chord gets fewer cells at
  VC; the family gives it more at F (growth 1.107, y⁺ 0.46).

## 7. What changed while V1–V4 were built (the construction, never a limit)

The checks and limits above were written in `configs/volume.yaml` before the first mesh was built, and have not
changed. Building V1 (BWB reference wing 0, VC, Re 3 × 10⁵), the construction changed five times after checks failed:

1. Marching the nodes themselves layer by layer folded (1,000+ quads per plane): the lines have different node
   distributions (wall lines, wake lines), so each layer tilted across the trailing edge. Now the line shapes come
   from one front, and the nodes are placed along them (decision 84).
2. Per-line distributions made slivers where the lines behind the trailing edge bunch (they keep the wake's
   streamwise clustering, s0, up to the far field). Now one distribution per station for every line, the band as an
   envelope in height, the wall spacing kept along the cut, the wake lines parallel.
3. The fill of the count by one factor stalled at zone boundaries (the growth limit jumped there, so the count jumped).
   Now every change of limit ramps over 25 % of its distance past the boundary (the limit holds up to it).
4. The stacked cells were sheared to a scaled Jacobian of 0.001 between neighbouring stations: the far-field nodes moved
   with the local chord much faster than the stations are apart near the tip (2 s0). Now the outer layers and the far
   wake nodes move to the station mean (section 3, step 4).
5. That move raised the growth 3 % above 1.3 on the root's wake lines. Now the far zone is built at the wall growth
   (1.25 at VC) and checked at 1.3, as Stage 2 builds the ring at 1.2 and checks 1.25.

After these, BWB reference wing 0 at VC passes every check (V1). Five more changes came in V2 and V4; again no limit
changed, and every V2–V7 number in this file is from the code after all of them:

6. **Check 10 compared floats exactly (V2).** The outboard far field is placed exactly 80 c past the tip, so the
   distance is 80 c to round-off. On the first screen 6 of the 80 reference meshes read 79.99999999999999 c and were
   refused (flying wing 2 at Re 10⁶ and 4 × 10⁶; tapered 4 at all four Re). The check now allows 1e−9 c of round-off;
   the limit stays 80 c. Rebuilt, all 6 pass. The first screen is kept in `data/studies/old/`.
7. **The count factor scaled the band cell too (V4).** One factor per station (λ ≤ 1) fits every station to the same
   layer count. It scaled the growth and the band cap together, so where a station had spare layers its band cells were
   smaller than the rule, by a different amount at each level: on BWB reference wing 0 the band cell at 0.5 local chord
   behind the root fell to 91 % of the rule at VC and 95 % at C, so VC/C = 1.24 (check 13 asks 1.3 ± 3 %). Now λ scales
   the growth only; the band cell is the rule at every station and level (VC/C = 1.292). Tried first and dropped: λ
   only past 2 local chords. Checks 3 and 6 refused it on the same wing (scaled Jacobian 0.014, growth 1.05 × the
   limit): neighbouring stations then differed too much in their outer layers.
8. **The cells left the band abruptly (V4).** Past the band height the cap rose by 10 × the distance, so the cells
   jumped from the band cell to free growth at whichever node came first past it. That node falls in a different place
   at each level, so the cell 1 local chord from the root's wall was off: VC/C 1.232–1.259 on 4 of the first 9
   families (limit 1.3 ± 3 %). Now the cap keeps rising past the band at the growth law's own rate (a geometric line
   has dh/dx = g − 1), so the cells leave the band smoothly: 1.265–1.289 on the same wings.
9. **Decision 88's text said the outboard far growth is built at 1.25 (V2).** The code builds the station gaps past the
   outboard fine zone at the checked value 1.3: they are a 1-D spacing with no blend, so no margin is needed, and check 12
   holds them at ≤ 1.3 × 1.01. The text is corrected; no mesh changed.
10. **The far-field blend pushed one root over the growth limit (V2, second screen).** After change 8, BWB reference wing 4
    at Re 4 × 10⁶ was refused by check 6: growth 1.313 against 1.3 × 1.01 (1.0100 × the limit), on a root wake line at
    layer 85, where the outer layers start moving to the station mean (the move adds its own stretch where the root's
    line differs most from the mean). Now the far zone is built at 1.22 at VC (1.165, 1.125, 1.095 at C, M, F), not at
    the wall growth 1.25: the worst growth on that mesh falls to 0.993 × the limit, in the boundary layer. Cost: one
    more layer on that wing (99 → 100). The first two screens are kept in `data/studies/old/`.

With all ten changes, V1 (BWB reference wing 0, VC, Re 3 × 10⁵) was rebuilt: 4,930,448 cells (it had 4,853,800):
95 layers, 74 wake nodes, 377 C-line nodes, 61 + 75 stations; every check passes; ADflow RAM 48.2 GiB (7.59 × Stage 2's
estimate). `data/studies/v1.json` and `docs/page/v1_slices.png` are the rebuilt ones.

## 8. V2: wall layers, fine zone and far field (the 20 reference wings × 4 Re, VC)

`scripts/screen.py --sets reference --re 1e5 3e5 1e6 4e6` (two halves, tags `ref_VC_a`, `ref_VC_b`), then
`scripts/v23_study.py` → `data/studies/v23.json`, `docs/page/v2_wall.png`. 80 meshes, built with every change of section 7.

![V2: the wall layers on the 80 reference meshes](../docs/page/v2_wall.png)

*What it shows.* One dot per mesh, by wing type; light to dark from Re 10⁵ to 4 × 10⁶. (a) cells; (b) cells across the
boundary layer at the worst station; (c) the largest in-plane angle between the first line and the wall normal; (d) the
95th percentile of the 3-D angle to the surface normal (reported, not judged); (e) the worst cell next to the base and
the trailing-edge corners; (f) the wing's last chordwise cell over the first cell behind the base.

| What | Measured (80 meshes) | Limit |
| --- | --- | --- |
| Outcome | 80 passed, 0 refused, 0 review (smoothing rung 0 on all) | |
| Cells | 2.71–6.87 M (median 5.02 M); Re 10⁵ 2.7–3.7 M, 3 × 10⁵ 4.1–5.1 M, 10⁶ 4.9–5.9 M, 4 × 10⁶ 5.7–6.9 M | |
| ADflow RAM | 27–67 GiB; fit 16 GB: 0 of 80; fit 52 GB: 40 of 80 | information |
| Layers · wake nodes · stations · outboard stations | 91–100 · 66–86 · 51–82 · 67–92 | |
| Cells across the boundary layer (worst station) | 30.39–32.69 | ≥ 30 |
| First cell against s0 | ≤ 0.028 % | ≤ 1 % |
| Growth / its limit | 0.9915–0.9960 | ≤ 1.01 |
| Wall angle in the plane (nose; off the base) | ≤ 0.18° (0.18°; 0.0095°) | ≤ 5° |
| The two trailing-edge corners | 2.7–8.8° | not judged |
| 3-D angle to the surface normal: median, 95th percentile, largest | 1.1–5.2°, 4–37°, 6–40° | reported (decision 89) |
| Cells next to the base; at the TE corners (smallest scaled Jacobian) | 0.57–1.00; 0.57–0.99 | ≥ 0.05 |
| Spacing jump across the trailing-edge line | Re 10⁵ 10–17; 3 × 10⁵ 26–48; 10⁶ 81–148; 4 × 10⁶ 293–537 | reported (decision 90) |
| Far field | 80.0 c | ≥ 80 c |
| Wake: growth and band cells / limit | ≤ 1.0009 | ≤ 1.01 |
| Smallest scaled Jacobian of the mesh | 0.062–0.097 (always the cap) | ≥ 0.05 |

**Conclusion.** All 80 pass. The wall rules hold on every wing at every Re: at least 30.39 cells across the boundary
layer, first cells within 0.03 %, growth at most 0.996 × its limit, square to the wall in the plane (≤ 0.18°), the
far field at 80 c. The base and the trailing-edge corners have good cells (≥ 0.57). The weak points are four: (1) cost,
no mesh fits the 16 GB desktop and only 40 of 80 fit 52 GB; (2) the planar stations shear the first cells at swept
noses, up to 40° off the surface normal in 3-D (y⁺ only falls); (3) the spacing jump across the trailing-edge line
reaches 537 at Re 4 × 10⁶, because the base is a wall at y⁺ 1 next to the wing's last chordwise cell; (4) the
tightest checks are the growth (0.996 × its limit at the most) and the band cells (1.0009 × the band cell at the most;
both limits allow 1.01).

## 9. V3: the cap, the outboard blocks and the tip vortex (the same 80 meshes)

![V3: the cap, the vortex path and the outboard share](../docs/page/v3_tip.png)

*What it shows.* (a) the worst cell of the CAP block per mesh; (b) the cells on the tip-vortex path at 4°, 0.5, 1 and 2
local chords behind the tip trailing edge (median, and the range over the 80 meshes), across the wake (z) and along it;
(c) the share of the cells in the outboard blocks.

| What | Measured (80 meshes) | Limit |
| --- | --- | --- |
| Cap block, smallest scaled Jacobian | 0.0617–0.0971: the worst part of all 80 meshes | ≥ 0.05 |
| Outboard blocks · inboard blocks, smallest scaled Jacobian | 0.77–0.97 · 0.18–0.88 | ≥ 0.05 |
| Outboard: first gap against the tip gap; growth | exact; within its limits (check 12 on all 80) | 1 %; × 1.01 |
| Share of the cells outboard | 51–56 % (median 54 %) | |
| Vortex path at 4°, across / along, 0.5 c | 0.0037 / 0.082 c (median) | |
| ... 1 c | 0.0110 / 0.118 c | |
| ... 2 c | 0.0167 / 0.243 c | |
| ... at 20°, 2 c (the band's edge) | 0.080 (largest 0.138) / 0.243 c | |
| Station gap next to the tip (largest of the 30 either side) | 0.0019–0.0709 c | |

**Conclusion.** The cap and the outboard blocks pass on all 80. The cap's cells are the worst cells of every mesh
(0.062 at the lowest): they are the Stage 2 cap quads swept outboard, so a better cap belongs to the frozen surface. The
outboard blocks are good (≥ 0.77) but hold 51–56 % of the cells: in a matched mesh every outboard station carries the
whole plane. The tip-vortex path is fine across the wake (0.004–0.017 c at 4°) and coarse along it (0.08–0.24 c, the
band allows 4 × the cross cell); at 20° and 2 c it sits at the band's edge (0.08 c). Enough to carry the vortex, not to
resolve its core. Whether that matters is a solver question (V7, then the mesh study of Stage 4).

## 10. V5: the solver files and check 15

`cfdauto/volume/cgns.py` and `cfdauto/volume/su2.py`; `write(vm, wing, out, formats=("npz", "cgns", "su2"))` writes
them and runs check 15 (`export()`); `scripts/v5_export.py` → `data/studies/v5_export.json` for the V7 mesh.

- **CGNS for ADflow, in pure Python.** Mike's CGNS 4.5.2 (the one ADflow links) was built without HDF5 and reads only
  ADF (S8, `cgns_read.py`), and building libcgns here was not allowed. So the file is written in ADF (version A02011,
  every header in ASCII hex), following the CGNS source (`ADF_internals.c`). The tree: one base, 13 structured zones,
  coordinates in double precision (i fastest), one `BC_t` per boundary face (BCWallViscous, BCFarfield,
  BCSymmetryPlane, each with its `FamilyName`), one `GridConnectivity1to1_t` per matched face on both sides (the
  transform from the face orientation, not from a nearest-node search), three `Family_t` with their `FamilyBC`.
- **Read back two ways.** By this package's reader, and by the CGNS library itself: the copy VTK ships
  (`libvtkcgns.so`, pip `vtk` 9.7.2; the same CGNS code, ADF included, 64-bit sizes), through `cg_open`, `cg_zone_read`,
  `cg_coord_read`, `cg_boco_info`, `cg_1to1_read`, `cg_family_read`, which are the calls ADflow makes.
- **.su2 for SU2.** The blocks as hexahedra (VTK 12), the nodes of every matched face welded by the topology (and then
  checked against the distances), boundary quads (VTK 9) in three markers: `wall`, `symmetry`, `farfield`, ordered to
  face out of the domain.

| BWB reference wing 0, VC, Re 3 × 10⁵ (4,930,448 cells) | Result |
| --- | --- |
| `volume.cgns` | 123.5 MB; own reader: every coordinate exact, 13 zones, 44 1-to-1 records, every transform maps its range onto its donor node for node, every BC with its type, family and range |
| ... by the CGNS library (VTK's copy) | the same: exact, no problem; version 3.4 |
| `volume.su2` | 693.6 MB; 5,013,600 points (from 5,099,248 block nodes), 4,930,448 hexahedra; markers wall 15,168, symmetry 36,304, farfield 114,108 quads |
| ... read back | every point the block node, exactly; no two points closer than 1e−12 c; smallest corner Jacobian 2.9e−13 (> 0: no inside-out cell); 0 boundary quads facing in, 0 bounding no cell |
| Time | build 15 s; all files and check 15: 56 s |

Tests (`tests/test_cgns.py`, `tests/test_su2.py`): a two-block box matched with a transposed, reversed index order
(the transform, the donor range, the ADF layout, a wrong transform caught, the library read), and the VC mesh.

**Conclusion.** ADflow and SU2 get the mesh that was checked, node for node, in the formats they read. The CGNS file is
written without libcgns and still read exactly by libcgns. Not shown yet: that ADflow and SU2 accept it and converge
(V7). Weak point: the library check here is VTK's copy of CGNS, not Mike's 4.5.2 build; `cgns.libcgns_check` runs with
Mike's library too (`CGNS_LIB=...`).
