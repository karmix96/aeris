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
| ... built | 1.25 at VC | 1.25 | 1.187 | 1.141 | 1.107 | built at the wall growth, as Stage 2 builds 1.2 and checks 1.25; the far-field blend may raise it |
| Far field | 80 mean chords | same | | | | law 15; 40 / 80 / 160 is Stage 4 (T2) |
| Wake band: angles | −5° to 20°, margin 0.05 c | same | | | | the brief: −5° to post-stall; decision 87 |
| Wake band: length | 2 local chords behind the trailing edge | same | | | | law 20 (the fine zone) |
| Wake band: cell at the trailing edge | 0.0075 c at M | 1.27 % c | 0.98 % c | 0.75 % c | 0.58 % c | Primer section 05 (about 20 cells across a 0.15 c wake) |
| Wake band: cells across the fan | 40 at M | 23.7 | 30.8 | 40 | 52 | decision 87: the cell grows with the distance so the fan keeps this many cells |
| Wake band: streamwise cell | ≤ 4 × the band cell | same | | | | decision 87 |
| Wake: first cell behind the base | s0 of the station | | | | | the base is a wall (decision 90) |
| Outboard: first gap | the wing's last gap (2 s0 at the tip) | | | | | law 10 / 12 |
| Outboard growth, to 2 c past the tip | 1.15 at VC | 1.15 | 1.114 | 1.086 | 1.066 | the brief's starting value (law 12) |
| ... beyond, to 80 c past the tip | the far growth | | | | | decision 88 |
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

## 7. What changed while V1 was being built (the construction, never a limit)

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

After these, BWB reference wing 0 at VC passes every check (V1).
