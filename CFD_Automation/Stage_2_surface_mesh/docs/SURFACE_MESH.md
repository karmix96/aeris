# Stage_2 — Surface mesh page (text copy, 2 Nov 2026)

Text copy for chats in this project of `CFD_Automation/Stage_2_surface_mesh/docs/SURFACE_MESH.html` (repo karmix96/aeris,
branch `stage2-surface-mesh`). The 14 figures are in the HTML page and on the artifact; here each one is a *[Figure: ...]*
line with its caption. Companion files: 'Stage_2 Surface mesh status and handover' (short), 'Stage_1 Handover to the surface
mesh' (the input). If this copy and the repository ever differ, the repository wins.

CFD_Automation · Stage 2 · surface mesh · cfdauto 0.7.0 · 2 Nov 2026

# Surface Mesh

What Stage 2 is, what was built and how it works, what was studied, what it assumes, what the primer asked, what is open, and whether it is finished. Every number on this page is read from the study files; every picture is drawn from the mesh arrays.

## At a glance

### Is the surface mesh finished?

**Code and screen: yes. The stage: not closed.**

The mesher builds every wing we can make and refuses what it cannot check. Still owed: the run with pyGeo on Mike's machine, the first volume march and solve (Stage 3), the chordwise ladder that tests the band rule (T6), and decision 64 on the built nose.

### The screen

**790 of 790 builds passed**

730 wings of 4 types and 5 sets at level C, Re 3 × 10⁵; the 20 reference wings at all four Re levels. 0 crashes. Build time median 5.0 s, max 8.1 s.

### The mesh

**one ring per station + a tip cap**

Ring of 186–866 nodes (level C), 66–134 stations, 13k–102k quads. BWB reference wing at Re 3 × 10⁵: 604 × 82 (C), 782 × 107 (M), 1016 × 139 (F).

### Rules and checks

**10 rules · 13 checks · 14 tests**

Every rule in one YAML with its source; every check with a value and a limit; a refused mesh writes only `refusal.json`.

### Weak points

**numpy loft, no solve, one source for the band rule**

Rings are 3–6 × S8's 150 nodes because of 20 nodes per bubble (one vendor source). The built airfoil noses are not round (a Stage 1 defect, decision 64). Nothing proves yet that the volume march accepts these surfaces.

### Where

**branch stage2-surface-mesh**

`CFD_Automation/cfdauto/mesh/` (code), `Stage_2_surface_mesh/` (config, decisions, docs, tests, scripts, studies). Project doc: Stage_2 Surface mesh status and handover.

## What Stage 2 is

Stage 1 made the wing: one exact loft per design vector, with measured values and a hash. Stage 2 puts a structured surface mesh on that loft: a closed ring of points around the section at every span station, root to tip, the same ring at every station, plus one patch that closes the flat tip. Every node is asked from the loft at (x/c, v); nothing is interpolated between stored sections. The volume mesh (the march off the wall), the wake boxes and the CGNS file are Stage 3. The mesh name carries the level and the Re: `mesh_<level>_<wing_hash8>_re<Re>`, because the tip gap and the band cells depend on the Re.

*\[Figure: the pipeline: loft → stations → size fields → nose solve → one distribution → rings + cap → 13 checks → files\]*

*\[Figure: The four reference wings (index 0) at level C, Re 3 × 10⁵ on the mean chord: every second station and every 24th ring line of the upper surface. Same rules, same code, four shapes.\]*

The Grand Roadmap's recipe R-S (one closed ring per station) and its step M1 (every surface constant into one module of laws) are what this stage implements. The volume recipe R-V and steps M2–M5 (first-cell law, march, boxes, overset export, driver) are Stage 3.

## What the primer and the Stage 1 handover ask from Stage 2

The AERIS Mesh Automation Primer (Annex G, the Grand Roadmap) gives the surface mesh as recipe R-S.1–R-S.9 and the code step M1, with the family rule M4. The Stage 1 handover adds where the baseline must be fine per family. Item by item, with what was built and the evidence:

| Item              | What the primer / handover asks                                                                                                                                                                                                                                                                                          | Status                                               | What was built, and the evidence                                                                                                                                                                                                                                                                                                                                |
|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| R-S.1             | Station positions along the span: count from the semi-span in local chords; nearly even from the root, squeezed toward the tip so the last gap equals the cap's first cell; set in metres, then converted to v.                                                                                                          | <span class="flag ok">done</span>                    | Gap = 0.2 × local chord (law 8 as a chord rule, not a count), at least 12 per panel, growth 1.2; last gap = s0 at the tip Re; a station exactly on every loft station (added: the ruled loft has a crease there). Check `tip_gap`, `loft_stations_hit`, `span_growth`.                                                                                          |
| R-S.2             | Sample the section densely from the loft (1,601 points at C).                                                                                                                                                                                                                                                            | <span class="flag ok">done</span>                    | 6,001 points per side, cosine in x/c; the dense curve only turns arc length into u; every node is evaluated on the loft.                                                                                                                                                                                                                                        |
| R-S.3             | One ring per station: TE upper corner → nose → lower corner → across the base; n_side 75, n_base 9 at C; Vinokur two-sided stretching per side; the base even.                                                                                                                                                           | <span class="flag chg">changed</span>                | Same ring order and the same 2·n_side + n_base − 3 nodes. Vinokur stretching is replaced by a size field + equidistribution, because the transition band needs a set cell size in the middle of a side, which a two-sided stretching cannot give. n_side is no longer a constant (75): it follows from the rules (≈180–430 at C).                               |
| R-S.4             | Trailing-edge spacing 0.1 % of local chord (law 3).                                                                                                                                                                                                                                                                      | <span class="flag ok">done</span>                    | Check `te_spacing` (delivered ≤ asked within 1 %).                                                                                                                                                                                                                                                                                                              |
| R-S.5             | Solve the nose spacing by bisection until the largest nose-cell turning is 10° ± 0.02° (law 1).                                                                                                                                                                                                                          | <span class="flag ok">done, widened</span>           | Bisection on the ring as built; the check covers every ring node, not the nose ± 3 (on cambered noses the sharpest cell sat a few cells onto the lower surface); away from the nose the same angle caps the cell from the curvature; the solve walks down until a window \[0.77 h, h\] passes (the built noses are not monotone, decision 64).                  |
| R-S.6             | Spanwise envelope on the nose spacing: at most 1.15 between neighbouring stations, only tightening (law 2).                                                                                                                                                                                                              | <span class="flag ok">by construction</span>         | One distribution for the whole wing makes the nose spacing / chord the same at every station; the check `nose_envelope` stays (reads ≈ 1.00).                                                                                                                                                                                                                   |
| R-S.7             | Apply the family's refinement factor to the end spacings: every spacing ÷ r per level, not only the counts.                                                                                                                                                                                                              | <span class="flag ok">done, widened</span>           | Every spacing ÷ 1.3 per level and the growth g^(1/1.3), so the stretched parts refine too; verified on the four reference wings at C, M, F (ratios 1.30 ± 3 %).                                                                                                                                                                                                 |
| R-S.8             | Evaluate every node on the loft; never interpolate (wall within 1e-9 m).                                                                                                                                                                                                                                                 | <span class="flag ok">done</span>                    | Test `test_every_node_is_on_the_loft` (max distance 0 to machine precision).                                                                                                                                                                                                                                                                                    |
| R-S.9             | Per-station table and checks: turning met, envelope clamps, nose spacing, scaled Jacobian of every quad, perimeter count; refuse to write otherwise.                                                                                                                                                                     | <span class="flag ok">done</span>                    | `stations.csv` (asked and delivered per station), `quality.json` (13 checks with value and limit), refusal writes only `refusal.json`.                                                                                                                                                                                                                          |
| M1                | Every surface constant into one module with a stated input list (mesh_laws.py): n_side, n_base, n_span, station positions, nose target, TE spacing, envelope; n_base 9; cap first cell = tip s0 (refuse above 3 ×); per-station table with the nose aspect ratio and the mid-chord growth.                               | <span class="flag part">done, partly</span>          | `cfdauto/mesh/laws.py` reads `configs/surface.yaml`: one function per rule, with the level in. Not done: the nose aspect ratio column (needs the first wall cell, Stage 3); the bit-identical rebuild test of g83 does not apply (no AERIS wings in CFD_Automation); the mesh is rebuilt bit-identically for the same input (test `test_same_input_same_mesh`). |
| M4 (surface part) | One function makes any level from the baseline; a test that the ratio of every spacing equals r within 1 %.                                                                                                                                                                                                              | <span class="flag ok">done (3 %)</span>              | `rules(level)` + `scripts/family_check.py`; ratios within 3 % (1 % is not reachable with whole numbers of gaps per panel and even base counts).                                                                                                                                                                                                                 |
| Stage 1 handover  | Fine at the nose, over a wide transition band (upper 10–85 % c, from the leading edge on swept panels; lower 60–100 % c), at the trailing edge (0.1 % c, 8 base cells), on every break, toward the tip (cap first cell = tip first cell), station count scaling with span / mean chord; cells per bubble: no source yet. | <span class="flag chg">done, with two changes</span> | The upper band starts at the leading edge on every wing (decision 58); the cells-per-bubble rule now has a source (20, decision 56). The wall and wake rows of the handover are Stage 3.                                                                                                                                                                        |

Two things in the primer are not in this stage on purpose: the constants it names (n_side 75, n_span 49, 1,601 dense points) were S8's values for one wing; here every count follows from a rule, so it changes with the wing and the Re. And the primer's M1 asks for a bit-identical rebuild of g83; CFD_Automation has no AERIS wings, so the equivalent test is a bit-identical rebuild of the same input (it passes).

## What was done, step by step

In the order it happened. Three passes of the screen were needed; the first two are development evidence, the third is the result.

**1 · inputs**

### Read the handover and the primer

Stage 0 values, the Stage 1 handover table (where the mesh must be fine), Annex G recipe R-S and step M1, and the S8 surface code (section_o.py, strategy_s8.py: the ring, the turning solve, the tip cap).

**2 · one tool**

### The spacing tool

One function set for both directions: a target cell size along a line, a growth limit, and points placed so every cell holds the same share of ∫ds/h. S8's two-sided tanh stretching could only set the two end cells; the band needs a set size in the middle of a side.

**3 · rules**

### The laws and the YAML

`configs/surface.yaml` holds every value with its source; `laws.py` turns each into a function of the level. The cells-per-bubble rule got its source (Ansys CFX transition-model guide: 20 nodes per bubble).

**4 · ring**

### The ring at one station

Size field per side (nose, band, trailing edge, largest cell, growth), the nose solve by bisection on the ring as built, the base across the blunt trailing edge.

**5 · span**

### The stations

On every loft station; gap 0.2 × chord, at least 12 per panel; squeezed to the tip first cell s0 at the tip Re.

**6 · tip**

### The cap, ported from S8

One H patch whose edge is the tip ring node for node, Laplacian smoothing with the edge held, oriented outboard.

**7 · gates**

### Checks, files, command line

13 checks that refuse; `surface.npz`, Plot3D, `stations.csv`, `quality.json`, `manifest.json` with four hashes; `python -m cfdauto.mesh`.

**8 · tests**

### 14 tests

Spacing tool, every node on the loft, turning at every station, band and trailing-edge spacing, stations on every loft station and the tip gap, cap edge = tip ring, same input → same mesh, sealed sets refused, writer and refusal, and the family ratio test (C against M).

**9 · screen 1**

### First screen: what it found

Per-station node distributions. Found: a tip-gap tolerance (integer counts), a crash on the corner set (a ~10° bend at the trailing-edge opening of 12 mm chords), a break 0.9 mm from the root that broke the span grid, and the lowest wing-quad quality of 0.08 in the tip squeeze.

**10 · fix**

### One distribution for the wing

The strictest station and side at every arc fraction: node i sits at the same arc fraction on every station. Quads 0.08 → 0.58 on the worst wing; the envelope holds by construction; +3 % nodes.

**11 · screen 2**

### Second screen: what it found

Chord growth 1.25–1.26 on NACA 4415 noses (the lower side follows the upper side's arc fraction; where the two built noses differ, its first cells grow a little faster). Allowed within 1 %, like the other delivered-against-asked checks.

**12 · fix**

### The nose held over four cells

The helper that holds a size over a length took the length as the size, so the nose cell came out 4 × the asked size and the solve compensated. Fixed; the delivered turning was right all along, the reported asked spacing was not.

**13 · screen 3**

### The final screen

Every built wing of every type and set at level C, Re 3 × 10⁵; the reference wings at all four Re levels. The numbers on this page.

**14 · studies**

### Family ratios, nose radius, figures, docs

C, M, F on the four reference wings; raw against built nose radius of the ten suggested airfoils; this page; the decisions note; open decisions 56–64; the branch pushed.

## How the surface mesh works

### 1. The loft in, the dense section

At a station v the loft gives the upper and lower surface at any x/c. The mesher samples each side at 6,001 points, cosine in x/c (dense at the nose and the trailing edge), and keeps a table of arc length against x/c per side. That table turns a cell size in metres into a position on the loft; the dense points themselves are never nodes. The same dense curve gives the radius of curvature along the section (right panel), used by the curvature cap and the kink check.

*\[Figure: BWB reference wing, root section (MH 104). Left: the dense sample at the nose. Middle: arc length against x/c per side. Right: radius of curvature of the built section: the two sides differ at the leading edge (finding 64).\]*

### 2. Where the stations go

A station sits exactly on every loft station (b0–b3 and the trailing-edge switch station some BWBs have), because the ruled loft has a crease there. Between them the target gap is 0.2 × the local chord, at least 12 gaps per panel, and the gaps may change by at most 1.2 from one to the next. Toward the tip the gaps shrink to the tip first cell s0 (y⁺ = 1 at the tip Re), so the cap faces a cell of the size it will get in the volume mesh: about 40 of the last panel's gaps lie in the last few millimetres.

*\[Figure: BWB reference wing, level C, Re 3 × 10⁵. Left: the station gap along the span: the 0.2 c target, the size field after the 12-per-panel rule, the tip squeeze and the growth limit, and the gaps delivered. Middle: every station as a chord line. Right: the last 12 mm before the tip.\]*

### 3. The size field around the section

Per station and side, the target cell size along the arc is the smallest of every rule that applies there: the largest cell (2 % c), the transition band (bubble length / 20 at the local Re; upper 0–85 % c, lower 60–100 % c), the curvature cap (cell ≤ R × 10° away from the nose), the nose cell held over four cells, the trailing-edge cell (0.1 % c), then a growth limit of 1.2 per cell. Points are then placed so each cell holds the same share of ∫ds/h.

*\[Figure: The root section of the BWB reference wing, upper side: the six layers of the size field and the cells delivered. Because both sides share one distribution, the lower side's band (60–100 % c) also sets the upper side's cells there, and the sharpest nose of the wing (the tip's MH 61) sets the nose cell of every station.\]*

### 4. The nose: solved, not estimated

S8 found that a nose-radius estimate gave 20° per cell when 6° was asked, so the nose spacing is solved: build the ring, measure the largest turning at any node, bisect the nose spacing until the turning is 10° ± 0.02°. The check covers every ring node except the two trailing-edge corners, because on cambered noses the sharpest cell sits a few cells onto the lower surface. The built noses are not monotone (right panel; finding 64), so the solve walks down until every spacing in \[0.77 h, h\] passes, and a station that still lands above the target after the shared distribution tightens the nose spacing of the whole wing by 10 %.

*\[Figure: Turning per cell against the nose spacing. Left: the BWB root, smooth. Right: a NACA 4415 station of a tapered training wing, not monotone: the built nose radius changes within the first cells.\]*

### 5. One node distribution for the whole wing

A structured mesh needs the same ring at every station. The first version gave each station the same count but its own distribution; the screen then showed surface quads with a scaled Jacobian down to 0.08: node i drifted along the chord between neighbouring stations (a different nose spacing, band cell or count), and where the stations are squeezed to tens of µm at the tip, a drift of a fraction of a cell shears the quad. Now the size fields of all stations and both sides are put on one grid of arc fraction, the strictest wins at every place, and that one distribution serves every station: node i sits at the same arc fraction everywhere, no cell is coarser than its station asks, and the spanwise envelope holds by construction. Cost: about 3 % more ring nodes, and the sharpest nose and the finest band of the wing everywhere.

*\[Figure: Flying wing, training_full 6, level C: the scaled Jacobian of every wing quad, per-station distributions against the one distribution, and the histogram of all quads.\]*

### 6. The ring

Upper trailing-edge corner → nose → lower trailing-edge corner → across the blunt base; 2 n_side + n_base − 3 unique nodes, the same at every station; n_base = 9 points (8 cells) at C. The base nodes are straight between the two corners.

*\[Figure: The root ring of the BWB reference wing: node order, the nose with the turning per node, and the trailing edge with its 0.1 % c cells and the 8 base cells.\]*

### 7. The tip cap

Ported from S8: one H patch whose edge is the tip ring node for node (checked to 1e-12 m), xi along the chord from a short nose arc to the base, eta across the thickness, 400 Laplacian sweeps with the edge held, oriented so that i × j points outboard. With one distribution for both sides its cross lines join upper and lower nodes at the same arc fraction and stay upright; with a different distribution per side they slanted across the thin trailing-edge region and the cells collapsed (scaled Jacobian 0.03 on the BWB reference wings at Re 3 × 10⁶). The two cells where the nose arc meets the sides have three corners on the smooth ring, so their corner angle is 180° minus the ring's turning there; they are reported apart and refused only if folded.

*\[Figure: The tip cap of the BWB reference wing and the scaled Jacobian of its cells.\]*

### 8. What depends on the Reynolds number

Two sizes: the band cell (bubble length / 20 at the local Re) and the tip first cell s0 (y⁺ = 1). So one wing has one surface per Re level; building one takes seconds. The ring grows with Re until the bubble-length floor of 0.05 c (band cell 0.25 % c) is reached, at about Re 10⁶.

*\[Figure: Left: the bubble length table. Middle: the band cell and s0 against Re. Right: ring nodes of the reference wings against the Re on the mean chord; S8's 150 for comparison.\]*

### 9. The checks

A build writes a mesh only if every check passes; otherwise it writes `refusal.json` with the failed checks and their values. A violation is reported per station, never averaged away (`stations.csv`).

| Check               | What it measures                                                                         | Limit                   |
|---------------------|------------------------------------------------------------------------------------------|-------------------------|
| `nose_turning`      | largest turning at any ring node (not the two TE corners, not geometry kinks)            | ≤ 10.2°                 |
| `geometry_kinks`    | a kink of the section itself (a dense step turning \> 1°), which no cell size can reduce | ≤ 10.2°                 |
| `nose_envelope`     | nose spacing / chord between neighbouring stations                                       | ≤ 1.15                  |
| `chord_growth`      | neighbouring cells along the ring                                                        | ≤ 1.25 (within 1 %)     |
| `band_spacing`      | largest cell inside the band / the band target                                           | ≤ 1.01                  |
| `te_spacing`        | trailing-edge cell / 0.1 % c                                                             | ≤ 1.01                  |
| `span_growth`       | neighbouring station gaps                                                                | ≤ 1.3                   |
| `loft_stations_hit` | distance from the nearest station to every loft station                                  | 0 m                     |
| `tip_gap`           | last station gap / tip first cell                                                        | 0.8 … 1.01              |
| `planar_stations`   | every ring in its station plane (y = const)                                              | ≤ 1e-9 m                |
| `wing_quads`        | smallest scaled Jacobian of the wing quads                                               | ≥ 0.05                  |
| `cap_quads`         | smallest scaled Jacobian of the cap quads, the two nose-corner cells apart               | ≥ 0.05                  |
| `cap_nose_corners`  | the two cap cells with three corners on the smooth nose                                  | \> 0 (not folded)       |
| `ring_count`        | unique ring nodes                                                                        | = 2 n_side + n_base − 3 |

## The rules and their sources

Level C values from `configs/surface.yaml`. "Law n" is the row of the laws table in the Grand Roadmap. The second table gives the two Re-dependent sizes at the Re levels of the study (and 6 × 10⁴ and 5.5 × 10⁶, the extremes a station can see).

| Where                                             | Law            | Rule at level C                                                                                                                                                                                                      | Source                                                                                                                                                 |
|---------------------------------------------------|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| Nose turning<span class="id">law 1</span>         | law 1          | no ring node turns the surface by more than 10° (± 0.02); solved by bisection on the ring as built; away from the nose the same angle caps the cell from the local curvature radius (cell ≤ R × 10°, x/c \> 0.5 %)   | S8 (measured on the built ring, because a radius estimate gave 20° for 6° asked)                                                                       |
| Nose, along the span<span class="id">law 2</span> | law 2          | nose spacing / chord changes by at most 1.15 between stations                                                                                                                                                        | S8; holds by construction with one distribution for the wing                                                                                           |
| Trailing edge<span class="id">law 3</span>        | law 3          | 0.1 % of the local chord at the two corners                                                                                                                                                                          | DPW gridding guidelines (Levy et al. 2013)                                                                                                             |
| Blunt base<span class="id">law 6</span>           | law 6          | 8 cells across the base at C (even, so the cap's nose arc is centred): 10, 14, 18 at M, F, FF                                                                                                                        | S8 (base cells 4/6/8 ladder); our choice                                                                                                               |
| Transition band<span class="id">Stage 1</span>    | Stage 1        | upper surface 0–85 % c, lower 60–100 % c; cell = bubble length / 20; bubble length from the local Re: 0.4 c at 6e+04, 0.3 c at 1e+05, 0.1 c at 4e+05, 0.05 c at 1e+06 (log-log between the points, constant outside) | Stage 1 handover (band, bubble lengths from 2-D XFOIL, N_crit 9); Ansys CFX Modeling Guide, γ-Re_θ transition model: at least 20 nodes across a bubble |
| Largest cell<span class="id">own</span>           | own            | 2 % c outside the bands                                                                                                                                                                                              | our choice (starting value)                                                                                                                            |
| Growth along the ring<span class="id">DPW</span>  | DPW            | 1.2 per cell used to build the size field; checked ≤ 1.25 (within 1 %)                                                                                                                                               | Stage 1 handover; DPW                                                                                                                                  |
| Stations<span class="id">laws 8, 9</span>         | laws 8, 9      | one exactly on every loft station; gap = 0.2 × local chord, at least 12 gaps per panel; growth 1.2 (checked ≤ 1.3)                                                                                                   | our starting values; the spanwise ladder decides                                                                                                       |
| Tip<span class="id">laws 9, 10, 13</span>         | laws 9, 10, 13 | stations squeezed so the last gap = 1 × the tip first cell s0; s0 / c = y⁺ / (Re √(Cf/2)), Cf = 0.026 Re^(−1/7) at y⁺ = 1                                                                                            | Grand Roadmap (cap first cell = tip s0); turbulent flat plate (White 2006)                                                                             |
| Levels<span class="id">law 23</span>              | law 23         | C, M, F, FF: every spacing ÷ 1.3^k, the growth g^(1 / 1.3^k) so each level is a true scaled copy                                                                                                                     | Celik et al. 2008 (r ≥ 1.3)                                                                                                                            |

| Local Re | Bubble length | Band cell (level C) | First wall cell s0, y⁺ = 1 |
|----------|---------------|---------------------|----------------------------|
| 6e+04    | 0.400 c       | 2.00 % c            | 0.0321 % c                 |
| 1e+05    | 0.300 c       | 1.50 % c            | 0.0200 % c                 |
| 3e+05    | 0.126 c       | 0.63 % c            | 0.0072 % c                 |
| 1e+06    | 0.050 c       | 0.25 % c            | 0.0024 % c                 |
| 3e+06    | 0.050 c       | 0.25 % c            | 0.0008 % c                 |
| 6e+06    | 0.050 c       | 0.25 % c            | 0.0005 % c                 |

What the band rule costs: about 200 ring nodes at Re 10⁵, 400 at 3 × 10⁵, 850 at and above 1.5 × 10⁶, against 150 in S8. The chordwise direction holds 35 % of the mesh budget (Stage 0, D1), so this rule is the first thing the chordwise ladder (Grand Roadmap T6) must test; if 20 nodes per bubble is more than the drag needs, the coarse level can be relaxed. The whole ring is in practice at band spacing (upper 0–85 % c and lower 60–100 % c, shared through the one distribution), except the nose and the trailing edge, which are finer.

## The family: C, M, F, FF

Every spacing (nose, trailing edge, band, station gaps, and the cells in the stretched parts between them) at level M is the C value divided by 1.3; the growth used to build the size field is g^(1/1.3) per level (1.2 at C, 1.15 at M, 1.11 at F). With the same growth at every level the end spacings refine but the stretched parts do not, and the station count grew by only 1.2 per level. Measured on the four reference wings at Re 3 × 10⁵:

*\[Figure: Left: the nose of the BWB root ring at C, M, F. Middle: the measured ratio of every spacing between levels on the BWB reference wing (dashed: 1.3). Right: ring nodes and stations per level, all four types.\]*

| Spacing                      | BWB C/M                           | BWB M/F | flying wing C/M                 | flying wing M/F | cranked C/M                     | cranked M/F | tapered C/M                     | tapered M/F |
|------------------------------|-----------------------------------|---------|---------------------------------|-----------------|---------------------------------|-------------|---------------------------------|-------------|
| nose cell, root              | 1.323                             | 1.299   | 1.300                           | 1.299           | 1.300                           | 1.299       | 1.300                           | 1.299       |
| nose cell, tip               | 1.322                             | 1.301   | 1.299                           | 1.299           | 1.300                           | 1.300       | 1.299                           | 1.300       |
| trailing-edge cell           | 1.300                             | 1.300   | 1.299                           | 1.300           | 1.299                           | 1.300       | 1.299                           | 1.300       |
| band cell, root              | 1.300                             | 1.300   | 1.300                           | 1.300           | 1.300                           | 1.300       | 1.298                           | 1.300       |
| band cell, tip               | 1.293                             | 1.309   | 1.300                           | 1.300           | 1.300                           | 1.300       | 1.298                           | 1.300       |
| first station gap            | 1.333                             | 1.312   | 1.333                           | 1.313           | 1.333                           | 1.313       | 1.333                           | 1.313       |
| last station gap (tip)       | 1.304                             | 1.289   | 1.287                           | 1.305           | 1.302                           | 1.295       | 1.302                           | 1.295       |
| base cell                    | 1.250                             | 1.400   | 1.250                           | 1.400           | 1.250                           | 1.400       | 1.250                           | 1.400       |
| ring × stations at C / M / F | 604 × 82 / 782 × 107 / 1016 × 139 |         | 430 × 74 / 556 × 96 / 720 × 125 |                 | 398 × 75 / 514 × 98 / 668 × 127 |             | 408 × 75 / 526 × 98 / 684 × 127 |             |

Two whole numbers keep the ratio from being exactly 1.3: the base cells (8, 10, 14, 18: ratios 1.25, 1.4, 1.29) and the gaps per panel (12, 16, 21: 1.33, 1.31). Both are reported, not hidden. The primer asks for 1 %; 3 % is what whole numbers allow.

## The studies

### 1. The robustness screen

Every built wing of every type and set (730 wings: reference, training_focus, training_full, corner1, corner2) at level C and Re 3 × 10⁵ on the mean chord, and the 20 reference wings at all four Re levels: **790 builds, 790 passed every check, 0 refused, 0 crashed.** With the numpy twin of the loft. Largest delivered turning 10.02° (target 10 ± 0.02), largest chord growth 1.208 (limit 1.25 within 1 %), a nose repair needed on 32 builds. Lowest wing-quad quality 0.09: on corner wings whose first panel is 4–6 mm wide with a 50 mm chord drop (a trailing edge swept at about 85°), a property of those wings. Lowest cap quality 0.11.

| Type (builds)     | Ring nodes min–median–max | Stations  | Quads        | Build time \[s\] | Wing quads J min / median | Cap quads J min / median | Passed    |
|-------------------|---------------------------|-----------|--------------|------------------|---------------------------|--------------------------|-----------|
| BWB (202)         | 486–614–860               | 71–83–134 | 36k–52k–101k | 4.2–5.3–8.1      | 0.09 / 0.82               | 0.19 / 0.34              | 202 / 202 |
| flying wing (193) | 370–430–528               | 66–76–116 | 28k–34k–58k  | 4.0–4.8–7.0      | 0.48 / 0.88               | 0.15 / 0.19              | 193 / 193 |
| cranked (202)     | 364–410–594               | 69–78–119 | 27k–36k–72k  | 4.0–4.9–7.6      | 0.40 / 0.98               | 0.15 / 0.43              | 202 / 202 |
| tapered (193)     | 364–420–506               | 69–79–116 | 28k–34k–55k  | 3.7–4.9–7.8      | 0.56 / 0.98               | 0.15 / 0.43              | 193 / 193 |

| Re on the mean chord | BWB: ring × stations (5 wings) | flying wing: ring × stations (5 wings) | cranked: ring × stations (5 wings) | tapered: ring × stations (5 wings) |
|----------------------|--------------------------------|----------------------------------------|------------------------------------|------------------------------------|
| 1.0e+05              | 280–310 × 72–97                | 218–234 × 68–91                        | 198–206 × 69–75                    | 192–208 × 67–85                    |
| 3.0e+05              | 568–638 × 77–103               | 416–458 × 74–96                        | 384–404 × 75–81                    | 368–412 × 73–91                    |
| 1.5e+06              | 860–860 × 85–111               | 844–844 × 82–104                       | 848–848 × 83–89                    | 848–848 × 81–99                    |
| 3.0e+06              | 858–860 × 89–114               | 844–844 × 85–108                       | 848–848 × 86–92                    | 848–848 × 85–102                   |

*\[Figure: The screen: ring nodes against the mean chord, stations against semi-span / mean chord, and build time, per type.\]*

*\[Figure: The screen: distributions of ring nodes and stations per type, and the lowest scaled Jacobian of the wing and cap quads per type (dashed: the refusal limit 0.05).\]*

What the screen does not show: whether the volume march accepts these surfaces, whether 20 nodes per bubble is the right coarse level, and anything about the flow. The two earlier passes were development evidence: the first found the tip-gap tolerance, the kinked noses of the corner set, the 0.9 mm panel and the 0.08 quads; the second found the 1.25–1.26 growth on NACA 4415 noses.

### 2. The family ratios

C, M, F of the four reference wings at Re 3 × 10⁵ (section above): every spacing 1.30 between levels within 3 %, ring nodes and stations × 1.3.

### 3. The nose radius of the built sections (a Stage 1 finding)

While solving the nose spacing the turning did not fall steadily as the spacing was reduced. The cause is in the loft: the curvature at the leading edge differs between the upper and lower side. The raw airfoil files against the Stage 1 resampled sections, nose radius from y ≈ √(2 R x) at the first cosine point (x = 2.5 × 10⁻⁴ c):

*\[Figure: The first 1.2 % of the chord: the raw file points, the built section, circles fitted to the built upper and lower nose, and (NACA 4415) the formula's circle.\]*

| Section   | Raw file: R/c at the leading-edge point | Built: upper side | Built: lower side | Ratio built / raw |
|-----------|-----------------------------------------|-------------------|-------------------|-------------------|
| naca4415  | 0.0246                                  | 0.0080            | 0.0741            | 0.3 × / 3.0 ×     |
| e387      | 0.0102                                  | 0.0028            | 0.0353            | 0.3 × / 3.5 ×     |
| sd7032    | 0.0077                                  | 0.0318            | 0.0023            | 4.1 × / 0.3 ×     |
| mh104     | 0.0084                                  | 0.0183            | 0.0048            | 2.2 × / 0.6 ×     |
| mh61      | 0.0041                                  | 0.0023            | 0.0053            | 0.6 × / 1.3 ×     |
| mh45      | 0.0051                                  | 0.0124            | 0.0028            | 2.4 × / 0.5 ×     |
| mh60      | 0.0050                                  | 0.0070            | 0.0037            | 1.4 × / 0.7 ×     |
| s5010     | 0.0077                                  | 0.0146            | 0.0033            | 1.9 × / 0.4 ×     |
| la2573a   | 0.0322                                  | 0.0325            | 0.0331            | 1.0 × / 1.0 ×     |
| naca25118 | 0.0339                                  | 0.0388            | 0.0296            | 1.1 × / 0.9 ×     |

On cambered sections with a small nose radius the two sides are off by up to 3–13 × in opposite directions, within the first about 0.1 % of the chord. The likely cause: the leading edge is taken at the raw point farthest from the trailing edge, and each side is interpolated in √x from that point; when that point is not exactly the nose apex, the two branches are not √x-symmetric. The mesh follows the loft as built, so the surface mesh is right for the wing we have; the wing's nose is not the airfoil's. It matters for the suction peak at high angle and for a nose-radius law (law 1 measures the turning, so it adapts). Logged as open decision 64.

### 4. The corner set: where the rules stop

The corner wings push every variable to its bounds. The smallest BWB corner wing has a 12 mm tip chord; the 0.5 mm trailing-edge floor is 4 % of it, and the opening of the trailing edge over the aft part of the section is a tight bend of about 10°. The band cell (2 % c at that tip's Re) could not follow it, so the turning rule now caps the cell from the local curvature along the whole ring. A true kink (a dense step turning more than 1°) would be reported apart; none was found in the sets.

*\[Figure: BWB corner wing 0, tip station (chord 12 mm, trailing edge 4 % thick): the ring and the cells along the upper side with the curvature cap.\]*

## Assumptions

| \#  | Assumption                                                                                              | Why                                                                                        | What it leaves out / risk                                                             |
|-----|---------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| A1  | The loft is the geometry; the numpy twin of the pyGeo loft gives the same surface.                      | Stage 1 tests compare the two backends; pyGeo is not installed here.                       | The pyGeo run on Mike's machine is owed before any mesh is trusted.                   |
| A2  | Bubble lengths from the Stage 1 XFOIL table (2-D, calm air, N_crit 9), constant at 0.05 c above Re 10⁶. | The only source we have for where the band must be fine.                                   | 3-D, sweep and roughness move bubbles; "under 0.05 c" is taken as 0.05 c.             |
| A3  | 20 nodes across a bubble, at level C.                                                                   | Ansys CFX guide for the γ-Re_θ model.                                                      | One vendor source, one model; may be more than the drag needs; the T6 ladder decides. |
| A4  | The tip first cell s0 from a turbulent flat plate at the tip Re, y⁺ = 1.                                | Standard estimate; the volume mesh will use the same law per station.                      | Checked only after the first solve (y⁺ audit).                                        |
| A5  | Station gap 0.2 × local chord, at least 12 per panel, growth 1.2; largest ring cell 2 % c.              | Starting values.                                                                           | No ladder yet; the spanwise ladder (laws 8, 9) will move them.                        |
| A6  | The turning rule (10° per cell) applies along the whole ring from the local curvature.                  | Needed on the corner set; the same number as at the nose.                                  | The curvature is read from the dense polyline (smoothed over 5 steps).                |
| A7  | One distribution for the wing: the sharpest nose and the finest band everywhere.                        | Clean quads between stations; simpler.                                                     | About 3 % more nodes; the root gets the tip's nose cell.                              |
| A8  | Checks with 1 % tolerance on delivered-against-asked spacings; tip gap 0.8–1.01 × s0.                   | Whole numbers of cells and gaps.                                                           | A real violation is far larger than 1 % (1.55 and 7.4 were seen and fixed).           |
| A9  | The surface is built per Re level; the name carries the Re.                                             | The tip gap and the band cell depend on Re.                                                | More meshes to manage; seconds each.                                                  |
| A10 | The flat tip with sharp edges (Stage 1 geometry) and its H cap.                                         | Hoerner: sharp side edges beat rounded tips for induced drag; the baseline of the roadmap. | The rounded-tip sensitivity (T8) is still to be run.                                  |

## What was found and decided

All logged in `CFD_Automation/OPEN_DECISIONS.md` (56–64) and explained in `Stage_2_surface_mesh/decisions/surface_rules.md`.

| \#  | Decision or finding                                                                                                | Why                                                                                                           | Open part                                                                                                                          |
|-----|--------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| 56  | Cells per bubble = 20 at level C.                                                                                  | The Stage 1 rule had no source; the Ansys CFX transition-model guide asks for at least 20.                    | Whether the coarse level needs the full 20 (T6). Costs 400–850 ring nodes against S8's 150.                                        |
| 57  | Wall-normal growth 1.1 for a transition model (Stage 3).                                                           | The same guide: 1.2 already moves transition upstream; Stage 0 says 1.25.                                     | Decide in Stage 3; it changes the layer count, not the surface.                                                                    |
| 58  | The upper band starts at the leading edge on every wing.                                                           | One rule instead of a sweep threshold; costs about 10 % of the chord.                                         | —                                                                                                                                  |
| 59  | One surface per wing and Re level; the name carries the Re.                                                        | The tip gap and the band cell depend on Re; seconds each.                                                     | —                                                                                                                                  |
| 60  | Both sides and all stations share one node distribution.                                                           | The cap cells collapsed (0.03) and the quads between tip stations sheared (0.08) with separate distributions. | —                                                                                                                                  |
| 61  | Base cells 8, 10, 14, 18 per level.                                                                                | Even counts keep the cap's nose arc centred.                                                                  | Ratios 1.25, 1.4, 1.29 instead of 1.3: the one spacing that does not follow r exactly.                                             |
| 62  | Station gap 0.2 × chord, 12 per panel, growth 1.2.                                                                 | Starting values.                                                                                              | The spanwise ladder.                                                                                                               |
| 63  | Largest cell 2 % c outside the bands.                                                                              | Our choice.                                                                                                   | Hardly applies: the bands cover most of the ring.                                                                                  |
| 64  | **Stage 1 finding: the built sections' nose is not round.** NACA 4415: 0.0248 c by formula, built 0.008 / 0.074 c. | Found by the nose solve; measured on the ten suggested airfoils.                                              | Mike decides: fix in Stage 1 (resample the nose in arc length or fit the apex; every hash changes) or carry as a stated deviation. |

## Open, to do, and is it finished?

### Finished

**the mesher, its rules, its checks, the screen**

Every wing of the built sets meshes at level C and the reference wings at every Re level; the family rule holds at C, M, F; 14 tests; the decisions and this page.

### Not finished

**the stage, until these are done**

The pyGeo run (tests + screen) on Mike's machine; decision 64 (the nose); the first volume march on these surfaces; the chordwise ladder (T6) on the band rule.

### Not known

**anything about the flow**

No solve has been run. Whether the surface gives a good volume mesh and a converged run is Stage 3's first result.

### To do, in order

1.  **pyGeo run (Mike's machine):** `pip install -e CFD_Automation`, then in `Stage_2_surface_mesh`: `python -m pytest` and `python scripts/screen.py`; compare `screen_C.json` with the one on the branch (counts should match to the node; the loft hash will differ from the numpy one).
2.  **Decide 64** (the built nose). If fixed in Stage 1, rebuild the sets, re-hash, rerun the Stage 2 screen (the nose spacings will change; the rules will not).
3.  **Stage 3:** the volume march from these rings (first cell s0 per station from the local Re, growth 1.25 or 1.1 per decision 57, ≥ 30 cells across the boundary layer, reach about 2 chords), the cap swept outboard, the boxes, the overset export, the overlap gate; then the first solve on a reference wing.
4.  **T6 chordwise ladder** on the band rule (20 → 13 → 8 nodes per bubble, or the reverse) before any production level is named.
5.  **Spanwise ladder** on the station rule (0.2 c; 12 per panel; the tip squeeze with 1 × or 3 × s0).
6.  Open from Stage 0 still: the grid share, the pitching-moment budget, the iteration share, the turbulence-model plan (gate G0).

## Handover to Stage 3 (volume mesh, wake boxes, CGNS)

- **Input per mesh:** `surface.npz` with `wing (n_ring, n_span, 3)` ring index first, root to tip; `cap (n_chord, n_base, 3)` with i × j outboard; `u` (x/c of every node, NaN on the base), `y`, `v` per station; `stations.csv` with the local Re and chord per station; `quality.json` with `s0_tip_m`, `re_tip`, `mean_chord_m`.
- **The march (recipe R-V):** first cell s0 per station from the local Re and y⁺ = 1 (law 13; `laws.first_cell_c`); growth ≤ 1.25 in the boundary layer, or 1.1 if the transition model is kept open (decision 57); ≥ 30 cells across the boundary layer; reach about 2 chords; cap first cell = tip s0 (the last station gap already equals it).
- **The family:** every spacing ÷ 1.3 per level and the growth g^(1/1.3), as on the surface, so the volume levels are true scaled copies; base cells 8 / 10 / 14 / 18.
- **Boxes (R-V.6):** background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, tube 15–20 cells across the core from 2 c behind the tip, far field 80 c (T2 decides); overset export and the overlap gate (M3).
- **Where the march will be tested first:** the tip squeeze (about 40 gaps on the last panel, down to tens of µm) and the corner wings with an 85°-sweep first panel.

## Files and commands

    pip install -e CFD_Automation
    cd CFD_Automation/Stage_2_surface_mesh
    python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5   # one mesh
    python -m pytest                       # 14 tests (test_family builds C and M of the BWB: slow)
    python scripts/screen.py               # every built wing; ~1 h on two cores (parts: scripts/merge_screen.py)
    python scripts/family_check.py         # data/studies/family_ratios.json
    python scripts/nose_radius.py          # data/studies/nose_radius.json
    python scripts/page_figures.py; python scripts/make_figures.py; python scripts/make_stage2_page.py

| Where                   | What                                                                                                                                                                                                                                                          |
|-------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `cfdauto/mesh/`         | `laws.py` (one function per rule), `spacing.py` (the spacing tool), `ring.py` (section, size fields, nose solve, one distribution, rings), `stations.py`, `cap.py`, `checks.py`, `surface.py` (the build, the checks, the files), `figures.py`, `__main__.py` |
| `Stage_2_surface_mesh/` | `configs/surface.yaml`, `decisions/surface_rules.md`, `decisions/STAGE2_STATUS.md`, `docs/` (this page, pictures), `tests/mesh/`, `scripts/`, `data/studies/` (`screen_C.json`, `family_ratios.json`, `nose_radius.json`)                                     |
| one mesh folder         | `surface.npz`, `surface.xyz` (Plot3D), `stations.csv`, `quality.json`, `manifest.json` (wing input hash, loft surface hash, mesh code hash, mesh node hash); refused: `refusal.json` only                                                                     |

Stage 2 of CFD_Automation (karmix96/aeris, branch stage2-surface-mesh). Built and screened with the numpy twin of the loft on 2 Nov 2026; cfdauto 0.7.0; screen mesh code hash 8883e200bbbd. Sources: Levy et al. 2013 (DPW gridding guidelines); Celik et al. 2008 (GCI, r ≥ 1.3); Ansys CFX Modeling Guide, γ-Re_θ transition model grid requirements; White, Viscous Fluid Flow (flat-plate friction); the AERIS Mesh Automation Primer, Annex G; S8 (section_o.py, strategy_s8.py).
