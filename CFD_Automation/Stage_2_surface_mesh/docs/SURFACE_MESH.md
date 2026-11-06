# Stage_2 — Surface mesh page (text copy, 2 Nov 2026, updated 7 Nov 2026)

Text copy for chats in this project of `CFD_Automation/Stage_2_surface_mesh/docs/SURFACE_MESH.html` (repo karmix96/aeris,
branch `stage2-surface-mesh`). The figures are in the HTML page and on the artifact; here each one is a *[Figure: ...]*
line with its caption. Since 6 Nov 2026 the page says what was first (built and screened 2–3 Nov) and what the new
approach changes (decided 4–6 Nov, not built yet): the section "What was first, and what changes", and a
"What changes" note in every section it touches. Companion files: 'Stage_2 Executive summary', 'Stage_2 Status and
handover' (short), 'Stage_1 Handover to the surface mesh' (the input). If this copy and the repository ever differ,
the repository wins.

CFD_Automation · Stage 2 · surface mesh · cfdauto 0.7.0 · 2 Nov 2026 · updated 7 Nov 2026

# Surface Mesh

What Stage 2 is, what was built and how it works, what was studied, what it assumes, what the primer asked, what is open, and whether it is finished. Every number of the first approach is read from the study files; every picture of it is drawn from the mesh arrays. Since 6 Nov the page also says what was first and what the new approach changes: the section [What was first, and what changes](#change), and an amber *What changes* box in every section it touches. The new approach is decided, not built. On 7 Nov the refine map was run down to −5° and the lower band at negative angles was counted with the planned rules ([Study 8](#study8)).

## At a glance

### Is the surface mesh finished?

**First approach: built and screened. New approach: decided, not built.**

The mesher builds every wing by the first rules and refuses what it cannot check. On 6 Nov a new approach was decided: levels VC–F with each target at the level that needs it, lighter rules, one C-H volume mesh for both solvers, similarity. It is the next build. Still owed: the nose re-measure (64), the choice of the lower band (74: counted on 7 Nov, option A costs no cells; Mike chooses), the new screen, the pyGeo run on Mike's machine, then Stage 3.

### The screen (first rules)

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

Rings are 3–6 × S8's 150 nodes because of 20 nodes per bubble at the coarsest level (one vendor source; the new approach moves it to F). The nose finding (64) was overstated and is being re-measured. Nothing proves yet that the volume march accepts these surfaces.

### Where

**branch stage2-surface-mesh**

`CFD_Automation/cfdauto/mesh/` (code), `Stage_2_surface_mesh/` (config, decisions, docs, tests, scripts, studies). Project docs: Stage_2 Executive summary, Stage_2 Status and handover.

### The new approach

**VC · C · M · F, matched C-H, unit chord**

Fine level about 10–11 M cells (median, wing blocks) with the lighter band, against 15.2 M with the planned rules; the C-H wake lines may add about +45 % (rough). See [What was first, and what changes](#change).

## What was first, and what changes with the new approach

Stage 2 was built and screened on 2–3 Nov with the first approach. On 4–6 Nov a new approach was decided. The code still builds the first approach, so everything measured on this page (790 of 790 builds, Studies 1–7) is first-approach evidence: it shows the mesher works. Study 8 (7 Nov) is new: the same code with the planned rules at VC, read from a plan file, to count the lower band (decision 74). The new approach is decided, not built; building it and screening it again is the next step. The table says what was first and what changes; the four figures show the four main changes. In every section below, an amber box *What changes* says what the new approach changes there.

| What                               | First (built and screened 2–3 Nov)                                                                                                                                 | New approach                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Decided                               | Built?                                                        |
|------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------|---------------------------------------------------------------|
| Levels, and where each target sits | C, M, F, FF. Every rule met at C, the coarsest level: each finer level only went past the targets, at about 2.2 × the cells per level.                             | VC, C, M, F. Hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap); accuracy targets at M (nose 10°, trailing edge 0.1 % c, station gap, largest cell), as the DPW guidelines define their medium grid; transition targets at F (20 cells per bubble, wall growth about 1.1). VC on the desktop; C, M, F on the university HPC.                                                                                                                                                                                                                       | decided 6 Nov                         | <span class="flag chg">to build</span>                        |
| Transition band cell               | bubble length / 20 at C; bubble 0.40 / 0.30 / 0.10 / 0.05 c at local Re 6 × 10⁴ / 10⁵ / 4 × 10⁵ / 10⁶.                                                             | bubble length / 20 at F; the bubble length stops at 0.10 c from local Re 4 × 10⁵ up, so the cell is 0.5 % c at F there (the shortest high-Re root bubbles, about 1.5 % c, then get about 3 cells: fine for SA, not for LM).                                                                                                                                                                                                                                                                                                                                              | decided 6 Nov                         | <span class="flag chg">to build</span>                        |
| Stations and tip                   | gap 0.2 × local chord at C, at least 12 per panel; last gap at the tip = s0.                                                                                       | gap 0.25 × local chord at M, at least 12 per panel at M; last gap at the tip = 2 × s0. Estimated −7 % and −8 % cells.                                                                                                                                                                                                                                                                                                                                                                                                                                                    | decided 6 Nov                         | <span class="flag chg">to build</span>                        |
| Lower band                         | 60–100 % c, set for angles 0–8°.                                                                                                                                   | Angles now run from −5°: at −5° the lower side takes the suction peak near the nose. Option A: lower band from the leading edge. Option B: keep it, and run transition (LM) only at angles ≥ 0°. Counted on 7 Nov (Study 8): A costs no cells. On the 20 reference wings × 4 Re levels A and B give the same ring, node for node (ratio 1.000), because both sides share one node list and the upper band (0–85 % c) already makes the front of the lower side fine; F stays at about 10.9 M with A. The earlier “band about 1.5 × longer” counted each side on its own. | pending: Mike chooses (counted 7 Nov) | <span class="flag part">to choose</span>                      |
| Volume mesh (Stage 3)              | O-H body mesh (S8) with an overset wake box and a tip-vortex tube; ADflow only (SU2 has no overset).                                                               | One matched C-H multiblock mesh for ADflow and SU2 (SU2 reads it converted to unstructured hexes). Wake lines from the trailing edge to the far field; the tip vortex resolved in the outboard blocks; no overlap gate. The ring and the cap of Stage 2 stay as they are.                                                                                                                                                                                                                                                                                                | decided 6 Nov                         | <span class="flag s3">Stage 3</span>                          |
| Wing size and Re (similarity)      | Wings at real size; Re 3 × 10⁵ on the mean chord for the screen, 4 Re levels on the reference wings; trailing edge max(0.5 mm Class I / 1.0 mm Class II, 0.2 % c). | Every wing at unit mean chord; the Re on the mean chord is an input (the same 4 levels); Mach 0.1 with a Prandtl–Glauert correction on CL and CM; trailing edge 0.2 % c; the root chord leaves the vector (18 → 17 numbers). About 5 × fewer solves (8,000, not 42,000).                                                                                                                                                                                                                                                                                                 | decided 6 Nov                         | <span class="flag chg">Stage 1 code first (every hash)</span> |
| Flow model                         | Fully turbulent ADflow SA planned; the turbulence model left to a later stage.                                                                                     | Transition must be captured, with ADflow and SU2 (4 Nov). Split, proposal (pending): ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings.                                                                                                                                                                                                                                                                                                                                                                               | decided 4 Nov; split pending          | —                                                             |
| Angles of attack                   | 0–8° (12° for the nose and wake studies).                                                                                                                          | −5° to post-stall; steady RANS up to stall onset; a separate post-stall study (URANS or DDES on a few wings).                                                                                                                                                                                                                                                                                                                                                                                                                                                            | decided 6 Nov                         | —                                                             |
| Mach                               | 0.03–0.13 tailless, 0.03–0.20 conventional.                                                                                                                        | Toward 0.5, no supersonic flow (4 Nov). Core Mach ≤ 0.2 now; 0.3–0.5 later with a fast-UAV family (pending). Under similarity the dataset runs at Mach 0.1.                                                                                                                                                                                                                                                                                                                                                                                                              | decided 4 Nov; core pending           | —                                                             |
| Nose shape (64)                    | First reading: the built nose is not round (upper and lower radius 3–13 × apart on cambered noses).                                                                | Overstated: measured the same way, the raw files show nearly the same split (NACA 4415 raw 0.0081 / 0.0736 c, built 0.0080 / 0.0741 c). Re-measure raw and built with one curvature method; fix only if a real error remains.                                                                                                                                                                                                                                                                                                                                            | plan agreed 6 Nov                     | <span class="flag chg">to do next</span>                      |
| Mesh size, fine level              | No target.                                                                                                                                                         | F about 10–11 M cells (median, wing blocks): 10.9 M with the lighter band, against 15.2 M with the planned rules. The C-H wake lines may add about +45 % (rough, 30–60 %).                                                                                                                                                                                                                                                                                                                                                                                               | estimate (6 Nov)                      | <span class="flag chg">to screen</span>                       |

*\[Figure: Four rules on the four levels, first (grey) against new (blue): the value each level gets when a rule is met at one level and every spacing is ÷ 1.3 per level. Level names: first C, M, F, FF; new VC, C, M, F (the same four places on the ladder).\]*

**Conclusion.** First, every target was met at the coarsest level, so the finer levels went far past it (44 cells per bubble at FF) while the cost grew about 2.2 × per level. New, each target is met where it is needed: the accuracy targets (nose 10°, trailing edge 0.1 % c, station gap) at M, as the DPW guidelines define their medium grid, and the transition target (20 cells per bubble) at F, where SU2 with LM will run. The coarse levels are coarser than before (about 17° per nose cell and 9 cells per bubble at VC): good enough for the SA mesh studies, not for transition. The wall rules do not change: y⁺ ≤ 1 and growth 1.25 at the coarsest level give 1.107 at F, which already meets the 1.1 a transition model asks for.

*\[Figure: Left: cells per mesh at the new levels with the lighter band: median and largest over the 20 reference wings × 4 Re levels (built surfaces × wall layers by formula; the wing blocks only). Right: the fine level F per rule set.\]*

**Conclusion.** With the lighter band the fine level is 10.9 M cells (median), inside the 9–11 M asked on 3 Nov; the planned rules gave 15.2 M. Only VC fits the desktop (1.0 M median, largest 1.5 M, against a limit of about 1.2 M), so the largest high-Re VC meshes go to the HPC too. The C-H wake lines are not in these counts: a rough +30–60 % puts F at about 14–17 M. The cost is not settled until the first C-H wing is built and counted (Stage 3).

*\[Figure: Left: the first plan: O rings around the section with an overset wake box (ADflow only). Middle: the new plan: one matched C-H mesh; the C rows wrap the nose and leave the trailing edge, the H blocks behind carry the wake to the far field. Right: the new plan from above: the station lines go on behind the wing and past the tip into the outboard blocks, where the tip vortex is resolved. Schematic, not a mesh.\]*

**Conclusion.** The surface mesh does not change: the ring is still the first row and the cap still closes the tip. What changes is the volume mesh (Stage 3): a march that starts from an open line at the trailing edge, wake lines to the far field (about +45 % cells, rough), the tip vortex clustered in the outboard blocks instead of a tube, and no overlap gate. The nose must stay inside the C block's ring direction, a spacing request and not a block dimension: a separate nose collar with 5 points is what broke S6. The gain: one mesh family and one error bar for both solvers.

*\[Figure: The transition band on one section: the first band, and the two options for negative angles.\]*

**Conclusion.** The first band (lower side 60–100 % c) was set for 0–8°. At −5° the lower side becomes the suction side near the nose, so its transition and bubbles move forward, out of the band: the refine map, now run down to −5° (the section tables reach −10°), puts the lower transition at a median of 1–15 % c per wing type at −5°. Option A covers them with one rule for both sides. On paper its band is about 1.5 × longer (125 → 185 % of the chord), but counted on the 20 reference wings it costs no cells: the ring is the same, node for node, because both sides share one node list and the upper band already makes the front of the lower side fine (Study 8). Option B keeps the same cells and gives up transition data below 0°. Still pending: Mike chooses.

### What stays the same

- The pipeline and the code: stations, size fields, the nose solve, one node list, rings and cap, the 13 checks, the files. The new approach changes values in the YAML and where each rule is met, not the steps.
- The ring and the tip cap, the family rule (every spacing ÷ 1.3 per level and the growth g^(1/1.3)), the base counts 8, 10, 14, 18.
- One surface per wing and Re level (decision 59); under similarity, one per Re level of the unit-chord wing.
- The first-approach evidence on this page: it shows the mesher works on every wing. The new rules need a new screen before they are evidence.

## Why a structured mesh, and why this one

A mesh is the set of small cells the solver computes on. There are two ways to build one. A **structured** mesh is rows and columns: every cell has an address (i, j, k), its neighbours are the next addresses, and the rows follow the surface. An **unstructured** mesh is a list of cells of any shape (triangles, tetrahedra, polyhedra) joined by a table of who touches whom. Both solve the same equations; they differ in what they make easy and what they make hard.

*\[Figure: The BWB root section meshed both ways, for the picture only: left, rows of quads that follow the surface (the ring of Stage 2 is the first row; the layers are drawn by a plain offset here, the real march is Stage 3); right, triangles from a Delaunay triangulation of points around the same section.\]*

**Conclusion.** The structured mesh puts long, thin cells along the surface where the flow changes little along the wall and much across it; the unstructured one needs many more cells for the same resolution near the wall, and its cells have no rows to refine by a fixed ratio.

### What a structured mesh gives us

- **Cells aligned with the flow.** The boundary layer is thin and changes fast across, slowly along; rows of high-aspect-ratio quads resolve it with few cells and low numerical error. The DPW guidelines and most published wing CFD use structured near-wall grids for this reason.
- **An exact refinement family.** Celik's grid-convergence method (Stage 0, D3) needs meshes that are true scaled copies with r ≥ 1.3. With rows, every spacing can be divided by r; a triangle mesh can only be "about" 1.3 × finer.
- **Addresses.** Every node has (i, j): the nose is a known index, the trailing edge another, the tip a known station. Error maps by region (Grand Roadmap T3), ablations by direction (T6) and the laws (stage 5) all need that.
- **The solver.** ADflow is a structured multiblock solver; overset lets us add the wake and tip-vortex boxes without one giant block.
- **Rules, not hand work.** With one topology for every wing, the mesh is a set of numbers (spacings, counts, growth) that a law can give. That is the paper's claim.

### What it costs

- **One topology per class of shape.** The O ring around the section with an H cap on the tip fits wings with a flat tip and a blunt trailing edge. A winglet, a box wing or a fuselage would need a new block layout, by hand. (That is why box wings are out of scope.)
- **Counts are shared.** Every station carries the same ring, so the station that needs most nodes sets the count for all; the tip, which needs about a third, gets the full ring. Cells cannot be added in one place only; refinement where the flow asks for it comes from the overset boxes (Stage 3), not from the near-body mesh.
- **Quality follows the geometry.** Where the trailing edge sweeps at 85° over a 4 mm panel (corner set), the quads between stations shear; where two built noses differ (finding 64), the two sides fight. An unstructured mesh would not care.
- **The cap has corners.** Closing a ring with one H patch leaves two cells with three corners on the smooth nose; a polyhedral cap would not.
- **No wake in the O mesh.** An O ring cannot set the spacing along the wake (a layer is a quarter chord thick one chord behind); the wake box and the tip tube of Stage 3 carry it.

**What changes (decided 6 Nov 2026).** ADflow and SU2 will both run one matched C-H mesh (SU2 reads it converted to unstructured hexes; it has no overset). In the C-H mesh the wake has its own rows, so two of the costs above go: the wake no longer needs an overset box, and the refinement behind the wing comes from the wake lines, not from boxes. The nose finding (64) used in the list above was overstated (Study 4).

### O, C or H around the section, and why O-H

Three ways to wrap rows around a section: **O** (closed rings), **C** (rows that wrap the nose and run off behind the trailing edge, so the wake has rows), **H** (rows above and below, a collapsed line at the nose). The mesh study (S0–S8, in the AERIS_MESH_STUDY folder) tried six strategies and settled on S8, an O ring with an H cap on the tip: the O ring puts the nose and the base inside one closed curve, so leading-edge resolution is a spacing request, not a block dimension (the C-family's nose collar capped it at 5 points, which was the whole source of the pressure-peak defect); the H cap is the one patch that closes the ring without a collapsed edge. The price, no rows in the wake, is paid with overset boxes (Stage 3).

*\[Figure: Left, side view: the ring (Stage 2) and a sketch of the O layers the march will add (Stage 3), with the wake box behind the trailing edge. Right, top view: the half wing with its stations, the tip cap and the outboard blocks, the wake box and the tip-vortex tube of the overset plan.\]*

**Conclusion.** Stage 2 builds only the first row (the ring at every station) and the patch on the tip. Everything that reaches into the air, the layers, the outboard blocks, the boxes, is Stage 3 and uses this surface as its wall.

**What changes (decided 6 Nov 2026).** The volume topology is now **C-H, matched, for both solvers**. Why: SU2 has no overset (cutting holes and interpolating between overlapping meshes is solver code, not a file format), and one matched family gives one error bar for both solvers. The O-H argument above still holds for the nose: the nose must stay a spacing request inside the C block's ring direction; a separate 5-point nose collar (S6) is what made the pressure-peak defect. The ring and the cap of this stage are the same in both plans; the change is in Stage 3 ([figure above](#change)).

### What the surface mesh must get right (from Stage 1)

The flow study of Stage 1 said where the baseline must be fine before any refinement: the nose (the suction peak; transition reaches it at high angle), a wide transition band (upper 10–85 % c, lower 60–100 % c). The band is not where transition is at one condition: at one angle and Re the flow turns turbulent over a short stretch, the bubble, 0.05–0.4 c long. The band is where that stretch can land over everything one mesh must serve: at a given Re the same mesh is run over the whole angle range, now −5° up to stall onset (it was 0–10° root angle). Over 0–10° Stage 1 found the upper surface turning turbulent anywhere from about 11 % c (high angle) to 78 % c (low angle, low Re), and the lower surface staying laminar to about 99 % c. Below 0° the lower side turns turbulent near the nose instead: at −5° at a median of 1–15 % c over the strips (2-D strips, Study 8). A mesh that is fine only where transition sits at one angle would be wrong at the next. A mesh per angle is possible (solution-adaptive meshing does exactly that) but we chose not to: Stage 0's rule for a mesh study is one change per run, so the results at 0°, 4° and 8° must come from the same mesh family to be compared; a per-angle mesh needs to know where transition will sit before the solve, which only the 2-D strips can say today; and it would multiply the mesh count by the number of angles. If the chordwise ladder (T6) shows the band is the cost that matters, a narrower band per angle is the first thing to revisit (Study 7 shows what a per-wing band looks like today). The other places where the baseline must be fine: the trailing edge and its blunt base, every break of the planform (a kink in the loft), the tip (smallest chord, lowest Re, the vortex), and enough stations along the semi-span. How many is set by how long the half wing is measured in its own chords, not by a fixed number: a slender wing (long semi-span, short chord) is many chords long and needs more slices than a stubby one. The rule here: a station every 0.2 of the local chord (a half wing 10 chords long gets about 50), at least 12 per panel, and extra ones squeezed in toward the tip. The wall and the wake belong to Stage 3. Every one of these became a rule below.

**What changes (decided 6 Nov 2026).** The angles now run from −5° to post-stall (steady RANS up to stall onset; a separate post-stall study). At negative angles the lower side becomes the suction side, so the lower band (60–100 % c) must reach forward (option A), or transition runs stop at 0° (option B): pending (74), figure in [What changes](#change). Counted on 7 Nov: A costs no cells, because the shared node list already makes the front of the lower side fine ([Study 8](#study8)); Mike chooses. Under similarity every wing is built at unit mean chord, and the Re on the mean chord is an input.

## What Stage 2 is

Stage 1 made the wing: one exact loft per design vector, with measured values and a hash. Stage 2 puts a structured surface mesh on that loft: a closed ring of points around the section at every spanwise station, root to tip, the same ring at every station, plus one patch that closes the flat tip. Every node is asked from the loft at (x/c, v); nothing is interpolated between stored sections. The volume mesh (the march off the wall), the wake boxes and the CGNS file are Stage 3. The mesh name carries the level and the Re: `mesh_<level>_<wing_hash8>_re<Re>`, because the tip gap and the band cells depend on the Re.

*\[Figure: the pipeline: loft → stations → size fields → nose solve → one distribution → rings + cap → 13 checks → files\]*

**Conclusion.** Six steps, the same for every wing: stations, size fields, the nose solve, one node list, rings and cap, checks. No step knows the wing type; the rules read the loft, the chord and the local Re. Every box of this figure has its own visual below, under the same number, in the section [The steps, one by one](#how).

The Grand Roadmap's recipe R-S (one closed ring per station) and its step M1 (every surface constant into one module of laws) are what this stage implements. The volume recipe R-V and steps M2–M5 (first-cell law, march, boxes, overset export, driver) are Stage 3.

**What changes (decided 6 Nov 2026).** Under similarity every wing is built at unit mean chord, so a mesh is set by its shape, its level and its Re level: four surfaces per wing and level, one per Re level. In Stage 3 the boxes and the overset export (R-V.6, M3) are replaced by the matched C-H mesh.

## What the primer and the Stage 1 handover ask from Stage 2

The AERIS Mesh Automation Primer (Annex G, the Grand Roadmap) gives the surface mesh as recipe R-S.1–R-S.9 and the code step M1, with the family rule M4. The Stage 1 handover adds where the baseline must be fine per family. Item by item, with what was built and the evidence:

| Item              | What the primer / handover asks                                                                                                                                                                                                                                                                                               | Status                                               | What was built, and the evidence                                                                                                                                                                                                                                                                                                                                |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| R-S.1             | Station positions along the semi-span: count from the semi-span in local chords; nearly even from the root, squeezed toward the tip so the last gap equals the cap's first cell; set in metres, then converted to v.                                                                                                          | <span class="flag ok">done</span>                    | Gap = 0.2 × local chord (law 8 as a chord rule, not a count), at least 12 per panel, growth 1.2; last gap = s0 at the tip Re; a station exactly on every loft station (added: the ruled loft has a crease there). Check `tip_gap`, `loft_stations_hit`, `span_growth`.                                                                                          |
| R-S.2             | Sample the section densely from the loft (1,601 points at C).                                                                                                                                                                                                                                                                 | <span class="flag ok">done</span>                    | 6,001 points per side, cosine in x/c; the dense curve only turns arc length into u; every node is evaluated on the loft.                                                                                                                                                                                                                                        |
| R-S.3             | One ring per station: TE upper corner → nose → lower corner → across the base; n_side 75, n_base 9 at C; Vinokur two-sided stretching per side; the base even.                                                                                                                                                                | <span class="flag chg">changed</span>                | Same ring order and the same 2·n_side + n_base − 3 nodes. Vinokur stretching is replaced by a size field + equidistribution, because the transition band needs a set cell size in the middle of a side, which a two-sided stretching cannot give. n_side is no longer a constant (75): it follows from the rules (≈180–430 at C).                               |
| R-S.4             | Trailing-edge spacing 0.1 % of local chord (law 3).                                                                                                                                                                                                                                                                           | <span class="flag ok">done</span>                    | Check `te_spacing` (delivered ≤ asked within 1 %).                                                                                                                                                                                                                                                                                                              |
| R-S.5             | Solve the nose spacing by bisection until the largest nose-cell turning is 10° ± 0.02° (law 1).                                                                                                                                                                                                                               | <span class="flag ok">done, widened</span>           | Bisection on the ring as built; the check covers every ring node, not the nose ± 3 (on cambered noses the sharpest cell sat a few cells onto the lower surface); away from the nose the same angle caps the cell from the curvature; the solve walks down until a window \[0.77 h, h\] passes (the built noses are not monotone, decision 64).                  |
| R-S.6             | Spanwise envelope on the nose spacing: at most 1.15 between neighbouring stations, only tightening (law 2).                                                                                                                                                                                                                   | <span class="flag ok">by construction</span>         | One distribution for the whole wing makes the nose spacing / chord the same at every station; the check `nose_envelope` stays (reads ≈ 1.00).                                                                                                                                                                                                                   |
| R-S.7             | Apply the family's refinement factor to the end spacings: every spacing ÷ r per level, not only the counts.                                                                                                                                                                                                                   | <span class="flag ok">done, widened</span>           | Every spacing ÷ 1.3 per level and the growth g^(1/1.3), so the stretched parts refine too; verified on the four reference wings at C, M, F (ratios 1.30 ± 3 %).                                                                                                                                                                                                 |
| R-S.8             | Evaluate every node on the loft; never interpolate (wall within 1e-9 m).                                                                                                                                                                                                                                                      | <span class="flag ok">done</span>                    | Test `test_every_node_is_on_the_loft` (max distance 0 to machine precision).                                                                                                                                                                                                                                                                                    |
| R-S.9             | Per-station table and checks: turning met, envelope clamps, nose spacing, scaled Jacobian of every quad, perimeter count; refuse to write otherwise.                                                                                                                                                                          | <span class="flag ok">done</span>                    | `stations.csv` (asked and delivered per station), `quality.json` (13 checks with value and limit), refusal writes only `refusal.json`.                                                                                                                                                                                                                          |
| M1                | Every surface constant into one module with a stated input list (mesh_laws.py): n_side, n_base, n_span, station positions, nose target, TE spacing, envelope; n_base 9; cap first cell = tip s0 (refuse above 3 ×); per-station table with the nose aspect ratio and the mid-chord growth.                                    | <span class="flag part">done, partly</span>          | `cfdauto/mesh/laws.py` reads `configs/surface.yaml`: one function per rule, with the level in. Not done: the nose aspect ratio column (needs the first wall cell, Stage 3); the bit-identical rebuild test of g83 does not apply (no AERIS wings in CFD_Automation); the mesh is rebuilt bit-identically for the same input (test `test_same_input_same_mesh`). |
| M4 (surface part) | One function makes any level from the baseline; a test that the ratio of every spacing equals r within 1 %.                                                                                                                                                                                                                   | <span class="flag ok">done (3 %)</span>              | `rules(level)` + `scripts/family_check.py`; ratios within 3 % (1 % is not reachable with whole numbers of gaps per panel and even base counts).                                                                                                                                                                                                                 |
| Stage 1 handover  | Fine at the nose, over a wide transition band (upper 10–85 % c, from the leading edge on swept panels; lower 60–100 % c), at the trailing edge (0.1 % c, 8 base cells), on every break, toward the tip (cap first cell = tip first cell), station count scaling with semi-span / mean chord; cells per bubble: no source yet. | <span class="flag chg">done, with two changes</span> | The upper band starts at the leading edge on every wing (decision 58); the cells-per-bubble rule now has a source (20, decision 56). The wall and wake rows of the handover are Stage 3.                                                                                                                                                                        |

Two things in the primer are not in this stage on purpose: the constants it names (n_side 75, n_span 49, 1,601 dense points) were S8's values for one wing; here every count follows from a rule, so it changes with the wing and the Re. And the primer's M1 asks for a bit-identical rebuild of g83; CFD_Automation has no AERIS wings, so the equivalent test is a bit-identical rebuild of the same input (it passes).

**What changes (decided 6 Nov 2026).** The primer's overset plan (R-V.6 and M3: boxes, overset export, overlap gate) is replaced by the matched C-H mesh. R-S.4 (trailing edge 0.1 % c) and R-S.5 (nose 10°) become accuracy targets met at M, so they hold on M and F and are looser on VC and C.

## The steps, one by one, with their visuals

One wing, one level, one Re. The numbering is the pipeline figure's: IN, steps 1 to 6, OUT. Every figure is from the BWB reference wing (index 0, level C, Re 3 × 10⁵) unless said otherwise.

### IN · The loft in, and the dense section the mesher reads from it

At a station v the loft gives the upper and lower surface at any x/c. The mesher samples each side at 6,001 points, cosine in x/c (dense at the nose and the trailing edge), and keeps a table of arc length against x/c per side. That table turns a cell size in metres into a position on the loft; the dense points themselves are never nodes. The same dense curve gives the radius of curvature along the section (right panel), used by the curvature cap and the kink check.

*\[Figure: BWB reference wing, root section (MH 104). Left: the dense sample at the nose (the first 120 of 6,001 points per side). Middle: arc length against x/c per side. Right: radius of curvature of the built section along the chord.\]*

**Conclusion.** Six thousand points per side resolve the nose to 3 × 10⁻⁵ c of arc, finer than any cell asked for. The curvature of the built section is not the same on the two sides at the leading edge (0.024 c against 0.005 c): finding 64, below (a first reading; Study 4 says why it is now in doubt).

### Step 1 · Where the stations go

A station sits exactly on every loft station (b0–b3 and the trailing-edge switch station some BWBs have), because the ruled loft has a crease there. Between them the target gap is 0.2 × the local chord, at least 12 gaps per panel, and the gaps may change by at most 1.2 from one to the next. Toward the tip the gaps shrink to the tip first cell s0: the height of the first layer of cells the volume mesh (Stage 3) will put on the wall, set by y⁺ = 1 at the tip Re (explained under Step 2), so the cap faces a cell of the size it will get in the volume mesh. Each panel gets a whole number of gaps, placed so each holds the same share of ∫dy/h. Where each number comes from: a station on every loft station is geometry (the ruled loft has a crease there); the last gap = s0 is the Grand Roadmap (laws 9, 10: the cap's first cell must match the tip's); the growth limit 1.3 is the Stage 1 handover, and we build at 1.2 to leave room for whole numbers; the 0.2 × chord gap and the 12 per panel are our starting values, not derived from a study: 0.2 c gives surface cells about 50 × longer along the semi-span than along the chord, usual for wing meshes, and 12 is the smallest whole number for which a break between two panels cannot step the gap by more than 1.2 × (1 + 1/12) ≈ 1.3. Both are open decision 62, for the spanwise ladder to test.

*\[Figure: BWB reference wing, level C, Re 3 × 10⁵. Left: the station gap along the semi-span: the 0.2 c target, the size field after the 12-per-panel rule, the tip squeeze and the growth limit, and the gaps delivered. Middle: every station as a chord line. Right: the last 12 mm before the tip.\]*

**Conclusion.** The 0.2 c rule hardly acts: the 12-per-panel floor sets the inner panels and the tip squeeze sets the outer one (43 of its gaps lie in the last few millimetres, from 3 cm down to 36 µm). The station count is therefore mostly a count of panels and of the squeeze, not of the chord; the spanwise ladder must test both.

**What changes (decided 6 Nov 2026).** Station gap 0.25 × local chord met at M (0.42 c at VC), at least 12 per panel at M; the last gap at the tip = 2 × s0, with s0 from y⁺ = 1 at VC. The tip squeeze then needs fewer stations (estimated −8 % cells; the station gap about −7 %).

### Step 1, the rules one by one, and which one sets each gap

### The five rules, and where each comes from

- **A station on every loft station** (b0, b1, b2, b3 and the trailing-edge switch station). Geometry: the loft is straight between them and has a crease at each, so a station there follows the kink. <span class="flag ok">source: geometry; Stage 1 handover</span>
- **At least 12 gaps per panel.** A panel gets a whole number of gaps, so the gap size can jump at a break by up to 1/n; 12 is the smallest n for which 1.2 × (1 + 1/12) stays under the 1.3 limit below. <span class="flag chg">our choice, derived from the 1.3 limit; open decision 62</span>
- **A gap of 0.2 × the local chord** where the panel is long enough for it (longer than 2.4 chords). On the reference wings it never acts: the 12-per-panel floor and the tip squeeze set every gap. <span class="flag chg">our choice, no source; open decision 62</span>
- **Neighbouring gaps differ by at most 1.2** (built) and **1.3** (checked). The 1.3 is the Stage 1 handover's limit on spanwise growth (the DPW guidelines give the same kind of limit for growth in general); 1.2 is what we build at, to leave room for the whole-number jumps at the breaks. <span class="flag ok">source: Stage 1 handover; DPW (Levy et al. 2013)</span> <span class="flag chg">1.2: our choice</span>
- **The last gap at the tip = s0**, the first wall cell the volume mesh will put on the tip cap (y⁺ = 1 at the tip Re). From the last panel's gap down to s0 at 1.2 per step takes about 40 stations. <span class="flag ok">source: Grand Roadmap, laws 9 and 10 (our own primer); s0 from the flat-plate law, White 2006</span>

### Two different 1.3s on this page

- **Growth 1.3 between neighbouring station gaps** (and 1.25 between neighbouring cells along the ring): how fast cells may change size next to each other, inside one mesh. Source: the Stage 1 handover and the DPW guidelines.
- **The family ratio r = 1.3 between levels C, M, F**: every spacing of the whole mesh divided by 1.3 to make the next finer mesh, for the grid-convergence estimate. Source: Celik et al. 2008 (r ≥ 1.3).
- They are unrelated numbers that happen to be equal. The station rules above come from the first (growth), not from the family ratio; the only numbers derived from a growth limit are the 12 per panel (so the jump at a break stays under 1.3) and the about 40 stations of the tip squeeze.

*\[Figure: Every station gap of two reference wings as a bar, coloured by the rule that set it: the BWB (semi-span 3 chords) and the most slender tapered reference wing (7 chords). Black lines: the loft stations.\]*

**Conclusion.** On real wings of our focus space the 0.2 × chord rule never acts: every gap is set either by the 12-per-panel floor (the straight runs) or by the growth limit (the tip squeeze from millimetres down to tens of µm, and the step between two panels whose floors differ). So the station count is mostly 12 × the number of panels plus about 40 for the squeeze; the spanwise ladder should test the floor and the squeeze before the 0.2 c value.

*\[Figure: The four reference wings (index 0) at level C, Re 3 × 10⁵ on the mean chord: every second station and every 24th ring line of the upper surface.\]*

**Conclusion.** Same rules, same code, four shapes: the BWB gets the most ring nodes (its root carries the highest local Re, so the smallest band cell as a fraction of the chord) and the most stations (its tip is the smallest). Nothing was set by hand for any type.

### Step 2 · The size field around the section: how big a cell may be at every place

Per station and side, the target cell size along the arc is the smallest of every rule that applies there: the largest cell (2 % c), the transition band (bubble length / 20 at the local Re; upper 0–85 % c, lower 60–100 % c), the curvature cap (cell ≤ R × 10° away from the nose), the nose cell held over four cells, the trailing-edge cell (0.1 % c), then a growth limit of 1.2 per cell. Points are then placed so each cell holds the same share of ∫ds/h: the same tool as along the semi-span.

*\[Figure: The root section of the BWB reference wing, upper side, built one rule at a time: each panel adds one rule to the previous result (grey). 1: no cell larger than 2 % c. 2: the transition band. 3: the curvature cap. 4: the nose and trailing-edge cells. 5: growth ≤ 1.2 turns the jumps into ramps: the station's own wish list. 6: what is delivered after the list is shared with the lower side and the other stations (dots).\]*

**Conclusion.** On this wing the band sets almost everything: with the upper band to 85 % c and the lower band from 60 % c shared through the one distribution, the whole ring is at band spacing except the nose and the trailing edge. The curvature cap never acts here (panel 3 equals panel 2). The delivered nose cell (0.04 % c, panel 6) is smaller than this station's own 0.096 % c (panel 4) because the sharpest nose of the wing, the tip's MH 61, sets it for every station.

### Step 2, continued: the two sizes that depend on the Reynolds number

Two sizes: the band cell (bubble length / 20 at the local Re) and the tip first cell s0 (y⁺ = 1). So one wing has one surface per Re level; building one takes seconds.

### What s0 is

- s0 is the **first wall cell**: the height of the very first layer of cells that the volume mesh (Stage 3) will grow from the wing surface into the air. It is a volume-mesh size, not a surface-mesh size.
- The surface mesh uses it in one place: the last station gap at the tip is set to s0, so the tip cap meets a cell of the same size as the first volume layer there (Grand Roadmap, laws 9 and 10). From the last panel's gap down to s0 takes about 40 stations at 1.2 per step: that is the "tip squeeze".
- It is not a free choice: it follows from y⁺ = 1. y⁺ is the distance from the wall measured in the flow's own wall units; the turbulence model wants the first cell inside the thin layer right at the wall, which means y⁺ about 1 (Stage 0 budget, row 1c, after the DPW gridding guidelines; Grand Roadmap law 13).

### Where its formula comes from

- **s0 / c = y⁺ / (Re √(Cf / 2))**, with Cf = 0.026 Re^(−1/7): the friction law of a turbulent flat plate (White, Viscous Fluid Flow). Why: y⁺ = y u_τ / ν, the friction velocity is u_τ = U √(Cf / 2), so y = y⁺ ν / (U √(Cf / 2)); divide by the chord and ν / (U c) = 1 / Re.
- Only the Re changes it, so it is one number per station, like the band cell: 0.032 % c at Re 6 × 10⁴, 0.0072 % c at 3 × 10⁵, 0.0024 % c at 10⁶ (middle panel of the figure below).
- Example: the BWB reference wing at Re 3 × 10⁵ on the mean chord has a tip chord of 14 cm at a tip Re of 8 × 10⁴, so s0 = 0.025 % × 14 cm = 36 µm: the last station gap at its tip.
- A flat plate is an estimate; the real wall friction differs along the chord. The volume mesh uses the same law per station, and the first solve audits y⁺ (assumption A4).

### What the band cell is

- At our Reynolds numbers the flow on the wing starts laminar, lifts off the surface, becomes turbulent in the air just above it, and lands again. The pocket of slow air between lift-off and landing is the **laminar separation bubble**. It changes the drag and where the flow turns turbulent, so the mesh must resolve it.
- The bubble is long at low Re and short at high Re: 0.40 c at Re 6 × 10⁴, 0.05 c at Re 10⁶ and above. These lengths come from the Stage 1 XFOIL table (2-D, calm air, N_crit 9); nothing else in the project says how long a bubble is.
- Where the bubble sits depends on the angle of attack, which changes from run to run. So one cell size is set over the whole stretch where it can sit, the **transition band** (upper side 0–85 % c, lower side 60–100 % c): that cell size is the band cell.

### Where the formula comes from

- **band cell = bubble length / 20**, in three steps per station: ① local Re = Re on the mean chord × local chord / mean chord; ② bubble length from the table at that Re; ③ divide by 20.
- The 20 is not ours: the Ansys CFX guide for the γ-Re_θ transition model asks for at least 20 nodes across a bubble, or the model puts transition in the wrong place. The Stage 1 rule had no source; this is the only one found (decision 56). One vendor, one model: the T6 ladder (20 → 13 → 8) must test it.
- Example at Re 3 × 10⁵: bubble 0.126 c → cell 0.63 % c → about 135 cells over the upper band. At Re 10⁵: 0.30 c → 1.5 % c → about 57 cells. A long root chord has a higher local Re, so a shorter bubble and a smaller cell as a fraction of its chord.

*\[Figure: Left: a laminar separation bubble on the upper side of a section, with the 20 cells the rule puts across it (red ticks) and the band where it may sit (blue). Right: the three steps for one station at Re 3 × 10⁵: the local Re, the bubble length read from the Stage 1 table, and the division by 20.\]*

**Conclusion.** The band cell is one number per station and side, set by the local Re alone: the rule has no free choice except the 20, which comes from one vendor guide. The bubble lengths are 2-D XFOIL values, so the rule is as good as that table; 3-D effects, sweep and roughness move bubbles and are not in it.

**What changes (decided 6 Nov 2026).** Band cell = bubble length / 20 met at F, so about bubble length / 9 at VC. The bubble length stops at 0.10 c from local Re 4 × 10⁵ up: the cell is 0.5 % c at F there, twice the first approach's 0.25 % c at high Re (table under [The rules](#rules)). The price: the shortest high-Re root bubbles (about 1.5 % c) get about 3 cells, fine for SA and wrong for LM; the 3-D check on the BWB centre body decides whether a local band is needed. The lower band at negative angles is pending (74); counted on 7 Nov, the lower band from the leading edge costs no cells (Study 8).

### How XFOIL gives the bubble length

- XFOIL computes the thin layer of air on the surface (the boundary layer) along the section and writes, at every point of the surface, the wall friction coefficient Cf: how hard the air rubs on the wall, and in which direction.
- Where the flow has lifted off, the air at the wall runs backwards and Cf is negative. So a bubble is read as a stretch of Cf \< 0 on one surface: it starts where Cf crosses zero (separation) and ends where Cf comes back above zero (reattachment). Its length is end − start, in chords.
- Two rules keep it honest: a Cf \< 0 stretch that reaches past 95 % c is trailing-edge separation, not a bubble; stretches shorter than 0.5 % c are ignored. If a surface has several, the longest counts. Transition itself is XFOIL's e^N method with N_crit 9 (calm air). Code: Stage 1 `cfdauto/flowmap/xfoil.py`, `features()`.

### From the runs to the table

- Stage 1 ran this on the 10 airfoils of the section sets at 14 Re, 3 Mach and 49 angles (2,408 sweeps). The Stage 2 table takes the upper-surface bubbles at Mach 0.1, 0–8°, and reads the typical length per Re: 0.45 c at 6 × 10⁴, 0.31 c at 10⁵, 0.11 c at 4 × 10⁵, 0.055 c at 10⁶ (medians), rounded to 0.40, 0.30, 0.10 and 0.05.
- The length changes with the angle of attack and the airfoil: the middle half of the bubbles sits within about 10–40 % of the median, depending on Re. The table is at or just under the median, so about half the bubbles get 20 cells or more; the shortest quarter gets 14–18.
- Below Re 4 × 10⁴ XFOIL finds no bubble (open separation); above 1.5 × 10⁶ only a few airfoils keep one (MH 104, LA2573A). The table stays at 0.05 c there, which is "under 0.05 c" in the Stage 1 handover.

*\[Figure: Left: a sketch of the wall friction Cf along the upper surface of one XFOIL run, and how the bubble is read from it. Right: every upper-surface bubble length in the Stage 1 tables (10 airfoils, free transition N_crit 9, Mach 0.1, 0–8°) per Re as a box (middle half) and whiskers (the rest), with the share of cases that have a bubble, and the Stage 2 table on top.\]*

**Conclusion.** The table follows the medians of the Stage 1 runs within rounding. It is one length per Re, while the real bubbles at one Re spread by tens of per cent with angle and airfoil, so the 20-cells rule holds for the typical bubble, not the shortest one. Everything here is 2-D XFOIL in calm air; a 3-D check of bubble lengths is still owed (A2).

*\[Figure: Left: the bubble-length table from Stage 1. Middle: the band cell and s0 against the local Re at level C. Right: ring nodes of the reference wings against the Re on the mean chord; S8's 150 for comparison.\]*

**Conclusion.** The ring grows with Re until the bubble-length floor (0.05 c, band cell 0.25 % c) is reached at about Re 10⁶, then stays at about 850 nodes. At 10⁵ it is about 200: the rule follows the physics (long bubbles need few cells per chord), not a fixed count. Every Re level needs its own surface.

### Step 3 · The nose: solved on the ring as built

S8 found that a nose-radius estimate gave 20° per cell when 6° was asked, so the nose spacing is solved: build the ring, measure the largest turning at any node, bisect the nose spacing until the turning is 10° ± 0.02°. The check covers every ring node except the two trailing-edge corners, because on cambered noses the sharpest cell sits a few cells onto the lower surface. The built noses are not monotone (right panel; finding 64), so the solve walks down until every spacing in \[0.77 h, h\] passes, and a station that still lands above the target after the shared distribution tightens the nose spacing of the whole wing by 10 %.

*\[Figure: Turning per cell against the nose spacing, measured on rings built at 40 spacings. Left: the BWB root (MH 104). Right: a NACA 4415 station of a tapered training wing.\]*

**Conclusion.** What the search does: it makes the nose cells smaller step by step until no cell bends the surface by more than 10°. Left (MH 104): smaller nose cells give less bending, in one steady line, so one search finds the right size. Right (NACA 4415): the line is not steady. The built nose has a small bump on its lower side (first read as a Stage 1 defect, finding 64; now being re-measured, Study 4). Below about 0.2 % c the worst cell is no longer at the nose but on that bump, and the nose size does not change it, so the line goes flat at about 7°. The small up-and-down comes from counting: each new size changes the number of nodes on the side, every node moves a little, and so the worst one changes. What this means for the code: a plain search can land on a size that passes by luck and fails as soon as the nodes move. So the solve also tries the sizes just below its answer (the window), and the final rings are checked again. The flat part at the far right of the left plot is another rule (the curvature cap) limiting the cells, not the nose rule.

**What changes (decided 6 Nov 2026).** The 10° target is met at M (about 17° at VC, 13° at C, 7.7° at F). The solve itself does not change. Whether the bump on the NACA 4415 lower side is a fault of the Stage 1 resampling or the airfoil's own curvature is what the nose re-measure must say (Study 4).

### Step 4 · One node list for all stations

### Why one list

- A structured mesh needs the same ring at every station: the same number of nodes, at the same relative places, so that node i of one station joins node i of the next in a clean four-sided cell.
- Step 2 gave every station its own wish list of cell sizes along the section, and the lists differ: the root has the highest local Re (small band cells), the tip has the sharpest nose (small nose cells), the lower side has its band at the back.
- With a list per station, node i drifted along the chord from one station to the next; where the stations are tens of µm apart at the tip, that drift sheared the cells (scaled Jacobian 0.08, Study 3).

### How the lists are merged

- Every side of every station is measured as a fraction of its own length, 0 at the nose and 1 at the trailing edge, so all lists sit on one scale whatever the chord.
- At each fraction the smallest wished cell of any station or side is taken. Example on the BWB reference wing: nose, root wants 0.10 % of the side, tip wants 0.03 %, everyone gets 0.03 %; band, root wants 0.37 %, tip 1.7 %, everyone gets 0.37 %.
- Nodes are placed once on the merged list, and that list is used on every station and both sides. Nobody gets a coarser cell than it wished; the cost is about 3 % more nodes. The sharpest nose and the finest band of the wing are everywhere.

*\[Figure: Left: the wish lists of three stations of the BWB reference wing (root, mid-span, tip; solid upper side, dashed lower side) on the common scale, and the merged list in black. Right: the merged list applied to the root ring and the tip ring, both drawn at unit chord, with every 30th node pair joined.\]*

**Conclusion.** The merged list is the lower envelope of all wish lists: the root's band sets the middle, the tip's nose sets the front, the lower band of every station sets the back. On the rings, node i lands at the same place on the root and the tip, which is what makes the cells between stations clean.

### Step 4, before and after: what the one list fixed

The first version gave each station its own list; the screen then showed surface quads with a scaled Jacobian down to 0.08: node i drifted along the chord between neighbouring stations (a different nose spacing, band cell or count), and where the stations are squeezed to tens of µm at the tip, a drift of a fraction of a cell shears the quad. Now the size fields of all stations and both sides are put on one grid of arc fraction, the strictest wins at every place, and that one distribution serves every station.

*\[Figure: Flying wing, training_full 6, level C: the scaled Jacobian of every wing quad (1 = right angles, 0 = flat), per-station distributions against the one distribution, and the histogram of all quads.\]*

**Conclusion.** With one distribution node i sits at the same arc fraction on every station: the sheared band at station 65 (0.08) is gone and the worst quad is 0.58, the sweep of the wing. The cost is about 3 % more ring nodes and the sharpest nose and finest band of the wing everywhere; the gain is a clean structured surface for the march, and the spanwise envelope (law 2) holds by construction.

### Step 5 · The rings and the tip cap

Upper trailing-edge corner → nose → lower trailing-edge corner → across the blunt base; 2 n_side + n_base − 3 unique nodes, the same at every station; n_base = 9 points (8 cells) at C. The base nodes are straight between the two corners. Every node is evaluated on the loft at its (x/c, v).

*\[Figure: The root ring of the BWB reference wing: node order (left), the nose with the turning per node (middle), and the trailing edge with its 0.1 % c cells and the 8 base cells (right).\]*

**Conclusion.** One closed curve holds the nose, both sides and the base, so the leading edge is a spacing request in metres and the base needs no block of its own. The turning at the nose nodes is at or below 10°; the two trailing-edge corners turn by about 90° by design and are left out of the check.

### Step 5, the cap

Ported from S8: one H patch whose edge is the tip ring node for node (checked to 1e-12 m), xi along the chord from a short nose arc to the base, eta across the thickness, 400 Laplacian sweeps with the edge held, oriented so that i × j points outboard. With one distribution for both sides its cross lines join upper and lower nodes at the same arc fraction and stay upright; with a different distribution per side they slanted across the thin trailing-edge region and the cells collapsed (scaled Jacobian 0.03 on the BWB reference wings at Re 3 × 10⁶).

*\[Figure: The tip cap of the BWB reference wing (top) and the scaled Jacobian of its cells (bottom), chordwise cell against cell across the thickness.\]*

**Conclusion.** The cap is a clean patch of upright quads over the whole chord; the only weak cells are the two where the nose arc meets the sides, whose three corners lie on the smooth ring (corner angle 180° minus the ring's turning). They are reported apart and refused only if folded. The real test of the cap is the march off it (Stage 3), where it is a viscous wall facing along the semi-span.

### Step 6 · The thirteen checks, then OUT · the files

A build writes a mesh only if every check passes; otherwise it writes `refusal.json` with the failed checks and their values. A violation is reported per station, never averaged away (`stations.csv`). The files: `surface.npz` (the arrays), `surface.xyz` (Plot3D, opens in ParaView), `stations.csv`, `quality.json`, `manifest.json` with four hashes (wing input, loft surface, mesh code, mesh nodes).

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

**Conclusion.** Thirteen checks, each with a number and a limit, written before the results (Stage 0, D4). They are what makes the screen a result and not a hope: a wing that passes has met every rule, and a wing that fails says which.

## The rules and their sources

Level C values from `configs/surface.yaml`. "Law n" is the row of the laws table in the Grand Roadmap. The second table gives the two Re-dependent sizes at the Re levels of the study (and 6 × 10⁴ and 5.5 × 10⁶, the extremes a station can see).

| Where                                                  | Law            | First: rule at level C (as built)                                                                                                                                                                                    | New approach (decided 6 Nov, to build)                                                                                                                                                                                                                     | Source                                                                                                                                                                                                                                                                                                                                                                                |
|--------------------------------------------------------|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Nose turning<span class="id">law 1</span>              | law 1          | no ring node turns the surface by more than 10° (± 0.02); solved by bisection on the ring as built; away from the nose the same angle caps the cell from the local curvature radius (cell ≤ R × 10°, x/c \> 0.5 %)   | 10° met at **M** (an accuracy target): about 17° at VC, 13° at C, 7.7° at F                                                                                                                                                                                | 10° is the Grand Roadmap's starting value (law 1), not a derived number; the primer plans a ladder 12 / 10 / 8 / 6° in T6 to test it. Meaning: a straight cell that turns the surface by θ misses the curve by about R θ² / 8, 0.4 % of the local radius at 10°, and a half-round nose gets 18 cells. S8: measured on the built ring, because a radius estimate gave 20° for 6° asked |
| Nose, along the semi-span<span class="id">law 2</span> | law 2          | nose spacing / chord changes by at most 1.15 between stations                                                                                                                                                        | unchanged                                                                                                                                                                                                                                                  | S8; holds by construction with one distribution for the wing                                                                                                                                                                                                                                                                                                                          |
| Trailing edge<span class="id">law 3</span>             | law 3          | 0.1 % of the local chord at the two corners                                                                                                                                                                          | 0.1 % c met at **M**: 0.17 % c at VC, 0.077 % c at F                                                                                                                                                                                                       | DPW gridding guidelines (Levy et al. 2013)                                                                                                                                                                                                                                                                                                                                            |
| Blunt base<span class="id">law 6</span>                | law 6          | 8 cells across the base at C (even, so the cap's nose arc is centred): 10, 14, 18 at M, F, FF                                                                                                                        | the same counts under the new names: 8, 10, 14, 18 cells at VC, C, M, F (≥ 8 is a hard minimum)                                                                                                                                                            | S8 (base cells 4/6/8 ladder); our choice                                                                                                                                                                                                                                                                                                                                              |
| Transition band<span class="id">Stage 1</span>         | Stage 1        | upper surface 0–85 % c, lower 60–100 % c; cell = bubble length / 20; bubble length from the local Re: 0.4 c at 6e+04, 0.3 c at 1e+05, 0.1 c at 4e+05, 0.05 c at 1e+06 (log-log between the points, constant outside) | cell = bubble length / 20 met at **F** (about / 9 at VC); the bubble length stops at 0.10 c from local Re 4 × 10⁵ up, so the cell is 0.5 % c at F there (decision 72). Lower band at negative angles: pending (74; counted 7 Nov: option A costs no cells) | Stage 1 handover (band, bubble lengths from 2-D XFOIL, N_crit 9); Ansys CFX Modeling Guide, γ-Re_θ transition model: at least 20 nodes across a bubble                                                                                                                                                                                                                                |
| Largest cell<span class="id">own</span>                | own            | 2 % c outside the bands                                                                                                                                                                                              | 2 % c at M                                                                                                                                                                                                                                                 | our choice (starting value)                                                                                                                                                                                                                                                                                                                                                           |
| Growth along the ring<span class="id">DPW</span>       | DPW            | 1.2 per cell used to build the size field; checked ≤ 1.25 (within 1 %)                                                                                                                                               | unchanged: ≤ 1.25 at VC (a hard minimum), so tighter on the finer levels                                                                                                                                                                                   | Stage 1 handover; DPW                                                                                                                                                                                                                                                                                                                                                                 |
| Stations<span class="id">laws 8, 9</span>              | laws 8, 9      | one exactly on every loft station; gap = 0.2 × local chord, at least 12 gaps per panel; growth 1.2 (checked ≤ 1.3)                                                                                                   | gap 0.25 × local chord at **M** (0.42 c at VC), at least 12 per panel at M; growth unchanged                                                                                                                                                               | our starting values; the spanwise ladder decides                                                                                                                                                                                                                                                                                                                                      |
| Tip<span class="id">laws 9, 10, 13</span>              | laws 9, 10, 13 | stations squeezed so the last gap = 1 × the tip first cell s0; s0 / c = y⁺ / (Re √(Cf/2)), Cf = 0.026 Re^(−1/7) at y⁺ = 1                                                                                            | last gap = **2 × s0**; s0 from y⁺ = 1 at VC (a hard minimum; y⁺ 0.46 at F)                                                                                                                                                                                 | Grand Roadmap (cap first cell = tip s0); turbulent flat plate (White 2006)                                                                                                                                                                                                                                                                                                            |
| Levels<span class="id">law 23</span>                   | law 23         | C, M, F, FF: every spacing ÷ 1.3^k, the growth g^(1 / 1.3^k) so each level is a true scaled copy                                                                                                                     | **VC, C, M, F**: VC on the desktop, C, M and F on the university HPC; hard minimums at VC, accuracy targets at M, transition targets at F (decision 71)                                                                                                    | Celik et al. 2008 (r ≥ 1.3)                                                                                                                                                                                                                                                                                                                                                           |

| Local Re | First: bubble length | First: band cell (C) | New: bubble length | New: band cell at F | New: band cell at VC | First wall cell s0, y⁺ = 1 (both: at the coarsest level) |
|----------|----------------------|----------------------|--------------------|---------------------|----------------------|----------------------------------------------------------|
| 6e+04    | 0.400 c              | 2.00 % c             | 0.400 c            | 2.00 % c            | 4.39 % c             | 0.0321 % c                                               |
| 1e+05    | 0.300 c              | 1.50 % c             | 0.300 c            | 1.50 % c            | 3.30 % c             | 0.0200 % c                                               |
| 3e+05    | 0.126 c              | 0.63 % c             | 0.126 c            | 0.63 % c            | 1.38 % c             | 0.0072 % c                                               |
| 1e+06    | 0.050 c              | 0.25 % c             | 0.100 c            | 0.50 % c            | 1.10 % c             | 0.0024 % c                                               |
| 3e+06    | 0.050 c              | 0.25 % c             | 0.100 c            | 0.50 % c            | 1.10 % c             | 0.0008 % c                                               |
| 6e+06    | 0.050 c              | 0.25 % c             | 0.100 c            | 0.50 % c            | 1.10 % c             | 0.0005 % c                                               |

The family (C, M, F, FF) is checked in Study 2 below. What the band rule costs: about 200 ring nodes at Re 10⁵, 400 at 3 × 10⁵, 850 at and above 1.5 × 10⁶, against 150 in S8. The chordwise direction holds 35 % of the mesh budget (Stage 0, D1), so this rule is the first thing the chordwise ladder (Grand Roadmap T6) must test; if 20 nodes per bubble is more than the drag needs, the coarse level can be relaxed. The whole ring is in practice at band spacing (upper 0–85 % c and lower 60–100 % c, shared through the one distribution), except the nose and the trailing edge, which are finer.

**What changes (decided 6 Nov 2026).** The New column is decided, not built: `configs/surface.yaml` and `laws.py` still hold the first values. The four levels keep their places on the ladder and change their names: the first C, M, F, FF sit where the new VC, C, M, F sit.

## The studies, with their conclusions

Seven studies were run while building the mesher, and an eighth on 7 Nov for decision 74. Each one says what was done, what the figure shows, and what we conclude. None of them is a flow result: no solver has run on these surfaces.

### Study 1 · The robustness screen

**What was done.** Every built wing of every type and set (730 wings: reference, training_focus, training_full, corner1, corner2) meshed at level C and Re 3 × 10⁵ on the mean chord, and the 20 reference wings at all four Re levels, with the numpy twin of the loft. Pass/fail limits were written before the run (the 13 checks). Failures stay in every count.

**Result.** 790 builds, 790 passed every check, 0 refused, 0 crashed. Largest delivered turning 10.02° (target 10 ± 0.02), largest chord growth 1.208 (limit 1.25), a nose repair on 32 builds. Lowest wing-quad quality 0.09, lowest cap quality 0.11. Build time median 5.0 s, max 8.1 s.

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

*\[Figure: Every build of the screen: ring nodes against the mean chord, stations against semi-span / mean chord, and build time, per type.\]*

**Conclusion.** Ring size is set by the local Re of the largest chord, not by the wing's size: the BWB sits at about 600 nodes, the three other types at about 400, whatever the chord. The station count rises with the aspect ratio (semi-span in chords) as the law intends, from about 70 to 130. Build time is 4–8 s for every wing; the mesher is not the bottleneck of the workflow.

*\[Figure: Distributions over the screen at Re 3 × 10⁵: ring nodes and stations per type, and the lowest scaled Jacobian of the wing quads and of the cap quads per wing, per type (dashed: the refusal limit 0.05).\]*

**Conclusion.** The wing quads are good on all types (median 0.82–0.98); the few wings below 0.3 are corner wings with an 85°-swept first panel. The cap quads are the weaker part (median 0.19–0.43): the H patch is squeezed between a thin section and the many chordwise cells. Both are far from the refusal limit; the march will say whether the cap quality matters.

**Conclusion.** The mesher is robust on the sets we have: 0 refusals in 790 builds at level C, so, by the rule of three (Stage 0, D2), the true failure rate on this design space is below about 0.4 % with 95 % confidence, for the surface alone. What the screen does not show: whether the volume march accepts these surfaces, whether 20 nodes per bubble is the right coarse level, and anything about the flow. It was run on the numpy loft; the pyGeo run is owed.

**What changes (decided 6 Nov 2026).** This screen used the first rules. The new rules need a new screen: every set at VC and F (C and M follow from the family rule), and the 20 reference wings at all four levels and Re levels. Under similarity the sets are rebuilt at unit mean chord first (new hashes).

### Study 2 · The family ratios (C, M, F)

**What was done.** Levels C, M, F of the four reference wings at Re 3 × 10⁵; the ratio of every spacing between levels measured on the built meshes (nose cells at the root and the tip, the trailing-edge cell, the band cell at the root and the tip, the first and last station gap, a base cell), and the counts.

*\[Figure: Left: the nose of the BWB root ring at C, M, F. Middle: the measured ratio of every spacing between levels on the BWB reference wing (dashed: 1.3). Right: ring nodes and stations per level for all four types.\]*

**Conclusion.** Every spacing refines by 1.30 within 3 %, and the counts (rings and stations) grow by 1.3 per level: the levels are true scaled copies, as Celik's method needs. The two exceptions are whole numbers: the base cells (8, 10, 14, 18: 1.25, 1.4, 1.29) and the gaps of the first panel (12, 16, 21). A first version with the same growth at every level refined only the end spacings and grew the station count by 1.2, not 1.3; the growth must scale too.

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

**Conclusion.** The family rule (law 23) holds on the surface for all four types. The primer asks for 1 %; 3 % is what whole numbers allow and it is reported, not hidden. The same rule, every spacing ÷ 1.3 and the growth g^(1/1.3), must be carried into the march and the boxes in Stage 3.

**What changes (decided 6 Nov 2026).** The ratios hold whatever level a target is met at: they come from ÷ 1.3 per level. Under the new names the measured C/M and M/F ratios are VC/C and C/M. In Stage 3 the rule goes into the march and the C-H blocks (there are no boxes).

### Study 3 · One distribution per station, or one for the wing

**What was done.** The first screen (per-station distributions) was read for the lowest wing-quad quality; the worst wing (flying wing, training_full 6, 0.08) was rebuilt both ways and the scaled Jacobian of every quad compared (figure in section 5 above). Then the whole screen was rerun with one distribution.

**Conclusion.** One distribution for the wing: the sheared quads in the tip squeeze go from 0.08 to 0.58, the BWB reference wing from 0.77 to 0.92, and no wing of the sets falls below 0.09 (the 85°-sweep corner wings, a property of those wings). The price is about 3 % more ring nodes and the sharpest nose of the wing at every station. Decision 60.

### Study 4 · The nose radius of the built sections (a Stage 1 finding, corrected 6 Nov)

**What was done.** While solving the nose spacing the turning did not fall steadily as the spacing was reduced (section 4). The raw airfoil files of the ten suggested sections were compared with the Stage 1 resampled sections: nose radius from y ≈ √(2 R x) at the first cosine point (x = 2.5 × 10⁻⁴ c) on each side, and a circle through three raw points at the leading edge; for NACA 4415 also the formula (R = 1.1019 t²).

*\[Figure: The first 1.2 % of the chord of NACA 4415, E387 and MH 104: the raw file points, the built section, circles fitted to the built upper and lower nose, and (NACA 4415) the formula's circle.\]*

**Conclusion.** First reading (2 Nov): the built nose is not the airfoil's nose. NACA 4415 has one nose of 0.0248 c by formula; the built section shows 0.008 c on the upper side and 0.074 c on the lower side at the leading-edge point. E387: 0.0102 c raw, 0.0028 / 0.035 c built. The round-nosed LA2573A and NACA 25118 are fine. The error lives in the first about 0.1 % of the chord.

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

**First reading and open decision (2 Nov).** The likely cause: Stage 1 takes the leading edge at the raw point farthest from the trailing edge and interpolates each side in √x from there; when that point is not exactly the nose apex, the two branches are not √x-symmetric. The mesh follows the loft as built, so the surface mesh is right for the wing we have; the wing's nose is not the airfoil's. It matters for the suction peak at high angle and for any law that reads a nose radius (law 1 measures the turning instead, so it adapts). Open decision 64: fix in Stage 1 (every geometry hash changes) or carry as a stated deviation. Mike decides.

**Correction (6 Nov 2026).** The first reading compared two different measures: a circle through three raw points against a one-sided formula on the built section. Measured the same one-sided way, the raw files show nearly the same split: NACA 4415 raw 0.0081 / 0.0736 c against built 0.0080 / 0.0741 c; SD7032 raw 0.0287 / 0.0023 against built 0.0318 / 0.0023. So the split is mostly how a one-sided formula sees a cambered, tilted nose (the nose circle's centre lies on the camber slope, about 11° on NACA 4415), not a fault of the geometry. What may remain: the leading-edge rule can change the shape only inside the first gap between raw points, under 0.025 % c on NACA 4415, about 7 × smaller than the nose cell the mesher delivers on the NACA 4415 reference wings (0.18 % c at C). Decision 64 stays open: re-measure raw and built with one curvature method that the tilt cannot fool, and fix only if a real error remains. A fix changes every geometry hash, so it goes before the pyGeo build --all.

### Study 5 · The corner set: where the rules stop

**What was done.** The first screen crashed on the smallest BWB corner wing (12 mm tip chord). Its tip section was examined: the trailing-edge thickness floor of 0.5 mm is 4 % of that chord, and the opening of the trailing edge over the aft part of the section makes a bend of about 10° at its start; the band cell there (2 % c at that tip's Re) could not follow it, so the nose solve could never bring the largest turning under 10°.

*\[Figure: BWB corner wing 0, tip station (chord 12 mm). Left: the section in its true shape, every ring node. Middle: the trailing edge zoomed. The base of this tiny section must be at least 0.5 mm thick (the Stage 1 floor), which is 4 % of its chord, so the section opens out over its last 10 % c: that is the widening, and it is geometry, not a mesh fault. Where the opening starts (88–92 % c, shaded) each surface turns by 11–13° within 4 % of the chord. Right: the cell sizes on the upper side: this station's own wish list (band cell 2 % c at its tiny Re), the curvature cap R × 10° that cuts the list at the bend, and what the wing's shared list delivers (0.25 % c, set by the root).\]*

**Conclusion.** A 2 % c cell across that bend turns by about 10° in one cell: that is why the first screen could not bring the largest turning under 10° on this wing. The fix: the turning rule now applies along the whole ring from the local curvature radius, not only at the nose, so the station's own list already shrinks at the bend (to about 1.2 % c, 8° per cell). On the finished wing the shared list makes the cells 0.25 % c there and the bend costs 2° per cell. A true kink (a dense step turning more than 1°) would be reported apart as a geometry fault; none was found in the sets. The corner set did its job: it found the limit of the rule and the rule was widened.

**What changes (decided 6 Nov 2026).** Under similarity the trailing edge is 0.2 % c on every wing: the 0.5 mm floor that made this 12 mm tip 4 % c thick goes, and with it this bend. The curvature cap stays, and check C3 still runs thicker real trailing edges (about 0.42 % c).

### Study 6 · Three passes of the screen: what each one found

| Pass      | Code state                 | Refused or crashed | What it found, and the fix                                                                                                                                                                                                                                                                                                                              |
|-----------|----------------------------|--------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1         | a distribution per station | 10 of 790          | Tip gap 0.1 % above the asked value (whole numbers of gaps: tolerance 0.8–1.01); the nose solve crashed on the smallest corner wing (the 10° bend: curvature cap along the ring, kinks reported apart); a break 0.9 mm from the root broke the spanwise grid (dense grid per panel); the lowest wing-quad quality 0.08 in the tip squeeze (Study 3).    |
| 2         | one distribution           | 17 of 790          | Chord growth 1.25–1.26 at NACA 4415 noses, where the two built sides differ most (the lower side follows the upper side's arc fraction): the growth check allows 1 %, as the other delivered-against-asked checks do.                                                                                                                                   |
| 3         | growth tolerance           | 0 of 790           | Clean. While drawing the size-field figure for this page the reported nose spacing did not match the delivered cells: the helper that holds a size over a length took the length as the size, so the nose cell was 4 × the asked size (the solve compensated, so the turning was right). Fixed; the nose is now held over four cells of the asked size. |
| 4 (final) | as committed               | 0 of 790           | The numbers on this page. The largest growth fell to 1.21.                                                                                                                                                                                                                                                                                              |

**Conclusion.** Four passes, each on the whole set, were needed to get from the first working mesher to the one that passes every wing. The earlier passes are development evidence, not results; the fourth, on the committed code, is the result. The corner and full-space sets are where every failure appeared, as Stage 0 said they would.

### Study 7 · Where to refine, per wing: the refine map (3 Nov 2026, run again from −5° on 7 Nov)

**What was done.** The transition band is generic (upper 0–85 % c, lower 60–100 % c, every wing). To see what a per-wing band would be, the Stage 1 flow dataset (2-D XFOIL section tables, read through the flow-map engine as strips along the semi-span with one induced angle) was read out for each of the 20 reference wings on a grid of Mach 0.03–0.20 × root angle −5…12° at sea level, 3 strips per panel (the grid started at −2° until 7 Nov): where the flow turns turbulent, where the bubbles sit and where it separates, on both surfaces. The envelope over the conditions one mesh must serve (Mach 0.03–0.13, −5° to 8° since 7 Nov; 0–8° before), plus a margin of 10 % c around the transition point, is the band that wing would need. Interactive page with every wing, slider for Mach, angle, ranges and margin: [Where To Refine](https://claude.ai/artifact/KXra2FWoVEFYLHCoafhgye) (`docs/REFINE_MAP.html`; code `cfdauto/mesh/refine_map.py`).

*\[Figure: BWB reference wing 0, half wing from above, root on the left, leading edge up. Left: both surfaces at Mach 0.08 and 4° at the root, one bar per strip: laminar (blue), the bubble (amber), turbulent (grey), the transition point (line). Right: the band this wing needs over Mach 0.03–0.13 and −5° to 8° with a 10 % c margin (tan), against the generic band (dashed).\]*

**Conclusion.** The per-wing band is not smaller than the generic one; it sits elsewhere, and from −5° it is wider. Over the 20 reference wings and −5° to 8° its band-cell cost is +8 % to +46 % of the generic band's (median +34 %); over 0–8° (first data, 3 Nov) it was −15 % to +20 % (median about +5 %). The generic band is wrong in place on every wing: at low angle the upper surface stays laminar beyond 85 % c on the outboard panels (missed by 10.5–15 % c per wing; up to 15 % c over 0–8° too), and the lower surface transitions near the leading edge, where the generic band starts at 60 % c: over −5° to 8° that stretch is missed by the full 60 % c on all 20 wings (52–60 % c over 0–8°, on washed-out panels). These costs count each side on its own; the built ring shares one node list for both sides, so a lower band from the leading edge costs no cells there (Study 8). The shortest root bubbles the dataset predicts (1.4–10.7 % c) are shorter than the band-cell table assumes at the root's Re (5–14 % c) on all 20 wings, so the 20-cells-per-bubble rule is not met at the root by either band; the negative angles do not change this. All of this is 2-D XFOIL in calm air with one induced angle for the whole wing; no crossflow transition, no 3-D relief, no tip effects. The per-wing band is a candidate (decision 65), not a rule, until a 3-D transition check says the strips are right; what would make the map better (AVL for the local angle, NeuralFoil for the 2-D answer) is decision 66.

**Updated 7 Nov 2026.** Done on 7 Nov: the map now runs from −5° (the section tables reach −10°) and its envelope is −5° to 8°; the numbers above are the new ones, with the first ones (0–8°) beside them. The generic lower band (60–100 % c) was set for positive angles; how much a lower band from the leading edge costs is Study 8 (decision 74, pending: Mike chooses). Still to do: under similarity the map is read per Re level on the mean chord at Mach 0.1, not per flight speed.

### Study 8 · The band count for negative angles (decision 74, 7 Nov 2026)

**What was done.** New data, not first-approach evidence: the same code with the planned rules of the new approach at the coarsest level VC, read from a plan file (`configs/surface_plan_VC.yaml`: the lighter band, tip gap 2 × s0, station gap 0.25 c at M); the mesher's own config is unchanged. First, the refine map run down to −5° (Study 7) was read for the lower side: per wing type, where it turns turbulent and where its bubbles sit at −5°, −2° and 0°, over every strip of the 5 wings and Mach 0.03–0.13, and how far that lies in front of the generic lower band (60 % c). Then the count: the 20 reference wings × 4 Re levels on the mean chord (10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶), built at VC once with the lower band of option B (60–100 % c) and once with option A (0–100 % c): 160 builds, about 4 s each. Only the band changes, so the stations and the wall layers are the same, and the wing-block cells scale with the ring nodes. A finer level has every VC spacing ÷ 1.3 per level, so the ratio A / B at F equals the ratio at VC up to whole-number rounding; two wings were also built at F to check it (the same mesh on both). Option A′, a per-wing lower band from the refine map (−5° to 8°, 10 % c margin), needs no build: one node list serves the whole wing, so its band is the union over the strips, and that union starts at 0 % c on 20 of the 20 wings, so A′ = A. Code: `scripts/band_count.py`; data: `data/studies/band_count.json`.

**Result, the lower side (2-D strips).** At −5° the lower side turns turbulent close to the nose on every type, and its transition or bubble sits in front of 60 % c on every strip that has an answer. At −2° that holds on 81–100 % of the strips, and at 0° still on 51–83 %: the generic lower band is in the wrong place already at 0°. The cranked and tapered wings have a lower bubble near the nose on almost every strip at −5°. On the BWBs and flying wings many outboard strips (MH 61, MH 45, at local angles −6° to −11°) have no answer at −5°, so their numbers rest on the other strips.

| Type        | Root angle | Strips × Mach values with an answer | Lower transition x/c: median (range) | Lower bubble: share of strips; start x/c median (range) | Transition or bubble in front of 60 % c | Missed by the generic lower band: median / max |
|-------------|------------|-------------------------------------|--------------------------------------|---------------------------------------------------------|-----------------------------------------|------------------------------------------------|
| BWB         | −5°        | 190 of 325                          | 15 % (0 %–50 %)                      | 33 %; 18 % (0 %–33 %)                                   | 100 %                                   | 45 / 60 % c                                    |
| BWB         | −2°        | 253 of 325                          | 31 % (0 %–77 %)                      | 46 %; 0 % (0 %–58 %)                                    | 96 %                                    | 30 / 60 % c                                    |
| BWB         | 0°         | 287 of 325                          | 44 % (0 %–91 %)                      | 31 %; 0 % (0 %–76 %)                                    | 82 %                                    | 18 / 60 % c                                    |
| flying wing | −5°        | 229 of 325                          | 1 % (0 %–58 %)                       | 72 %; 0 % (0 %–30 %)                                    | 100 %                                   | 60 / 60 % c                                    |
| flying wing | −2°        | 309 of 325                          | 30 % (0 %–100 %)                     | 38 %; 0 % (0 %–40 %)                                    | 81 %                                    | 32 / 60 % c                                    |
| flying wing | 0°         | 320 of 325                          | 59 % (0 %–100 %)                     | 20 %; 0 % (0 %–37 %)                                    | 51 %                                    | 1 / 60 % c                                     |
| cranked     | −5°        | 325 of 325                          | 10 % (3 %–25 %)                      | 97 %; 5 % (1 %–12 %)                                    | 100 %                                   | 55 / 59 % c                                    |
| cranked     | −2°        | 325 of 325                          | 21 % (5 %–65 %)                      | 76 %; 11 % (2 %–26 %)                                   | 100 %                                   | 47 / 58 % c                                    |
| cranked     | 0°         | 325 of 325                          | 37 % (9 %–100 %)                     | 30 %; 15 % (3 %–29 %)                                   | 77 %                                    | 29 / 57 % c                                    |
| tapered     | −5°        | 322 of 325                          | 9 % (3 %–24 %)                       | 98 %; 4 % (1 %–13 %)                                    | 100 %                                   | 56 / 59 % c                                    |
| tapered     | −2°        | 325 of 325                          | 18 % (6 %–72 %)                      | 84 %; 8 % (2 %–26 %)                                    | 100 %                                   | 49 / 58 % c                                    |
| tapered     | 0°         | 325 of 325                          | 32 % (12 %–100 %)                    | 41 %; 14 % (5 %–29 %)                                   | 83 %                                    | 35 / 55 % c                                    |

| Type (5 wings)          | Re 10⁵: ring nodes B / A (median)                                                   | Re 3 × 10⁵: ring nodes B / A (median) | Re 1.5 × 10⁶: ring nodes B / A (median) | Re 3 × 10⁶: ring nodes B / A (median) | Ratio A / B: median / max |
|-------------------------|-------------------------------------------------------------------------------------|---------------------------------------|-----------------------------------------|---------------------------------------|---------------------------|
| BWB                     | 168 / 168                                                                           | 236 / 236                             | 236 / 236                               | 236 / 236                             | 1.000 / 1.000             |
| flying wing             | 138 / 138                                                                           | 222 / 222                             | 232 / 232                               | 232 / 232                             | 1.000 / 1.000             |
| cranked                 | 122 / 122                                                                           | 202 / 202                             | 222 / 222                               | 222 / 222                             | 1.000 / 1.000             |
| tapered                 | 124 / 124                                                                           | 206 / 206                             | 222 / 222                               | 222 / 222                             | 1.000 / 1.000             |
| All 80 pairs            | the same mesh, node for node, on 80 of 80 pairs; 160 of 160 builds pass every check |                                       |                                         |                                       | 1.000 / 1.000             |
| Fine level F (estimate) | wing blocks, median: 10.9 M cells with B × the median ratio                         |                                       |                                         |                                       | 10.9 M with A             |

*\[Figure: Left: where the lower side turns turbulent, per wing type and root angle (every strip of the 5 reference wings with an answer, Mach 0.03–0.13), against the generic lower band (60–100 % c); at the right of each row, the share of strips whose transition or bubble lies in front of 60 % c. Middle: the cell size along the lower side of the BWB root ring at VC, Re 3 × 10⁵: what option B delivers (line), what option A delivers (circles), and the lower side's own wish list with B (dashed). Right: ring nodes with A against ring nodes with B, all 80 pairs.\]*

**Conclusion.** The lower band of option B is in the wrong place at negative angles (and on many strips already at 0°), but option A costs nothing: the ring is the same, node for node, on every pair. The lower side never uses its own wish list: both sides share one node list (decision 60, needed by the tip cap), so at every place the finer side wins, and the upper band (0–85 % c) already puts band cells on the front 85 % of the lower side; the lower band covers the back. With A the band check also covers the front of the lower side, and it passes, because the cells are already there.

**Conclusion.** Option A costs no cells: ratio A / B = 1.000 (median) and 1.000 (max) over the 80 pairs, the same at F, so the fine level stays at about 10.9 M cells (median, wing blocks) with A. The earlier “1.5 × longer band” (125 → 185 % of the chord) counted each side on its own; the built ring takes the finer side at every place. So the cells no longer decide between A and B. A keeps transition runs (SU2 LM) from −5° at no mesh cost. B only saves the LM runs below 0°, and its lower band does not match where the lower side turns turbulent, even at 0°. Limits: 2-D XFOIL strips in calm air with one induced angle; no answer on 42 % (BWB) and 30 % (flying wing) of the strips at −5°; planned rules at VC from a plan file, not the built config. Decision 74 stays pending: Mike chooses.

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

**5 · spanwise**

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

Per-station node distributions. Found: a tip-gap tolerance (integer counts), a crash on the corner set (a ~10° bend at the trailing-edge opening of 12 mm chords), a break 0.9 mm from the root that broke the spanwise grid, and the lowest wing-quad quality of 0.08 in the tip squeeze.

**10 · fix**

### One distribution for the wing

The strictest station and side at every arc fraction: node i sits at the same arc fraction on every station. Quads 0.08 → 0.58 on the worst wing; the envelope holds by construction; +3 % nodes.

**11 · screen 2**

### Second screen: what it found

Chord growth 1.25–1.26 on NACA 4415 noses (the lower side follows the upper side's arc fraction; where the two built noses differ, its first cells grow a little faster). Allowed within 1 %, like the other delivered-against-asked checks.

**12 · fix**

### The nose held over four cells

The helper that holds a size over a length took the length as the size, so the nose cell came out 4 × the asked size and the solve compensated. Fixed; the delivered turning was right all along, the reported asked spacing was not. The largest growth fell from 1.26 to 1.21.

**13 · screens 3, 4**

### The last two screens

The third pass was clean but the size-field figure of this page exposed the nose held over one cell instead of four (step 12); the fourth, on the committed code, gives the numbers on this page: 790 of 790.

**14 · studies**

### Family ratios, nose radius, figures, docs

C, M, F on the four reference wings; raw against built nose radius of the ten suggested airfoils; this page; the decisions note; open decisions 56–64; the branch pushed.

**15 · 6 Nov**

### The new approach decided

Levels VC, C, M, F with each target at the level that needs it; the lighter band, tip gap and station gap; one matched C-H volume mesh for ADflow and SU2; similarity; angles −5° to post-stall; transition with ADflow and SU2. This page, the refine map, the status and the decisions updated (67–76); the code not yet.

**16 · 7 Nov**

### The band count

The refine map run down to −5°; the lower side read at −5°, −2° and 0°; options A and B built at VC with the planned rules on the 20 reference wings × 4 Re (160 builds): the same ring on every pair (Study 8).

## Assumptions

| \#  | Assumption                                                                                                                                    | Why                                                                                                  | What it leaves out / risk                                                                                                                                    |
|-----|-----------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A1  | The loft is the geometry; the numpy twin of the pyGeo loft gives the same surface.                                                            | Stage 1 tests compare the two backends; pyGeo is not installed here.                                 | The pyGeo run on Mike's machine is owed before any mesh is trusted.                                                                                          |
| A2  | Bubble lengths from the Stage 1 XFOIL table (2-D, calm air, N_crit 9), constant at 0.05 c above Re 10⁶.                                       | The only source we have for where the band must be fine.                                             | 3-D, sweep and roughness move bubbles; "under 0.05 c" is taken as 0.05 c.                                                                                    |
| A3  | 20 nodes across a bubble, at level C (new: at F).                                                                                             | Ansys CFX guide for the γ-Re_θ model.                                                                | One vendor source, one model; may be more than the drag needs; the T6 ladder decides.                                                                        |
| A4  | The tip first cell s0 from a turbulent flat plate at the tip Re, y⁺ = 1.                                                                      | Standard estimate; the volume mesh will use the same law per station.                                | Checked only after the first solve (y⁺ audit).                                                                                                               |
| A5  | Station gap 0.2 × local chord, at least 12 per panel, growth 1.2; largest ring cell 2 % c (new: gap 0.25 × chord at M; tip gap 2 × s0).       | Starting values.                                                                                     | No ladder yet; the spanwise ladder (laws 8, 9) will move them.                                                                                               |
| A6  | The turning rule (10° per cell) applies along the whole ring from the local curvature.                                                        | Needed on the corner set; the same number as at the nose.                                            | The curvature is read from the dense polyline (smoothed over 5 steps).                                                                                       |
| A7  | One distribution for the wing: the sharpest nose and the finest band everywhere.                                                              | Clean quads between stations; simpler.                                                               | About 3 % more nodes; the root gets the tip's nose cell.                                                                                                     |
| A8  | Checks with 1 % tolerance on delivered-against-asked spacings; tip gap 0.8–1.01 × s0.                                                         | Whole numbers of cells and gaps.                                                                     | A real violation is far larger than 1 % (1.55 and 7.4 were seen and fixed).                                                                                  |
| A9  | The surface is built per Re level; the name carries the Re (new: per Re level of the unit-chord wing).                                        | The tip gap and the band cell depend on Re.                                                          | More meshes to manage; seconds each.                                                                                                                         |
| A10 | The flat tip with sharp edges (Stage 1 geometry) and its H cap.                                                                               | Hoerner: sharp side edges beat rounded tips for induced drag; the baseline of the roadmap.           | The rounded-tip sensitivity (T8) is still to be run.                                                                                                         |
| A11 | **New:** every wing at unit mean chord; the Re on the mean chord an input; Mach 0.1 with Prandtl–Glauert; trailing edge 0.2 % c (similarity). | At low Mach, shape, Re and angle fix the flow (dimensional analysis); 5 × fewer solves.              | Re does not carry roughness or air turbulence; small real wings have thicker trailing edges (check C3); if check C2 fails, Mach becomes an input.            |
| A12 | **New:** hard minimums at VC, accuracy targets at M, transition targets at F.                                                                 | DPW defines its spacings on the medium grid; the transition model needs its cells where it runs (F). | VC and C do not resolve bubbles (about 9 and 12 cells): their transition results are not to be trusted; the LM error bar needs M, F (and FF on a few wings). |

## What was found and decided

All logged in `CFD_Automation/OPEN_DECISIONS.md` (56–66; the new approach 67–76) and explained in `Stage_2_surface_mesh/decisions/surface_rules.md`.

| \#  | Decision or finding                                                                                                                                                                                                                                                        | Why                                                                                                                                                                                       | Open part                                                                                                                                                                                                                                       |
|-----|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 56  | Cells per bubble = 20 at level C.                                                                                                                                                                                                                                          | The Stage 1 rule had no source; the Ansys CFX transition-model guide asks for at least 20.                                                                                                | Whether the coarse level needs the full 20 (T6). Costs 400–850 ring nodes against S8's 150. New (71): 20 at F, not at the coarsest level.                                                                                                       |
| 57  | Wall-normal growth 1.1 for a transition model (Stage 3).                                                                                                                                                                                                                   | The same guide: 1.2 already moves transition upstream; Stage 0 says 1.25.                                                                                                                 | Decide in Stage 3; it changes the layer count, not the surface. New (71): growth 1.25 at VC is 1.107 at F, which meets it there.                                                                                                                |
| 58  | The upper band starts at the leading edge on every wing.                                                                                                                                                                                                                   | One rule instead of a sweep threshold; costs about 10 % of the chord.                                                                                                                     | —                                                                                                                                                                                                                                               |
| 59  | One surface per wing and Re level; the name carries the Re.                                                                                                                                                                                                                | The tip gap and the band cell depend on Re; seconds each.                                                                                                                                 | —                                                                                                                                                                                                                                               |
| 60  | Both sides and all stations share one node distribution.                                                                                                                                                                                                                   | The cap cells collapsed (0.03) and the quads between tip stations sheared (0.08) with separate distributions.                                                                             | —                                                                                                                                                                                                                                               |
| 61  | Base cells 8, 10, 14, 18 per level.                                                                                                                                                                                                                                        | Even counts keep the cap's nose arc centred.                                                                                                                                              | Ratios 1.25, 1.4, 1.29 instead of 1.3: the one spacing that does not follow r exactly.                                                                                                                                                          |
| 62  | Station gap 0.2 × chord, 12 per panel, growth 1.2.                                                                                                                                                                                                                         | Starting values.                                                                                                                                                                          | The spanwise ladder. New (72): 0.25 × chord at M.                                                                                                                                                                                               |
| 63  | Largest cell 2 % c outside the bands.                                                                                                                                                                                                                                      | Our choice.                                                                                                                                                                               | Hardly applies: the bands cover most of the ring.                                                                                                                                                                                               |
| 64  | **Stage 1 finding: the built sections' nose is not round.** NACA 4415: 0.0248 c by formula, built 0.008 / 0.074 c.                                                                                                                                                         | Found by the nose solve; measured on the ten suggested airfoils.                                                                                                                          | Overstated (75): re-measure first, raw and built with one method; fix only if a real error remains (every hash changes).                                                                                                                        |
| 65  | **Per-wing transition band from the flow dataset** (candidate): the envelope of bubbles, transition ± margin and separation over the conditions one mesh serves, per strip and side.                                                                                       | Study 7, the refine map: the generic band is mis-placed on washed-out panels (lower surface near the leading edge, upper surface beyond 85 % c at low angle); the cost is about the same. | Keep the generic band or switch after a 3-D transition check (γ-Re_θ in SU2 on a few wings). Not a rule yet.                                                                                                                                    |
| 66  | **Upgrade the flow dataset with AVL and NeuralFoil** (proposal): AVL for the local angle per strip (sweep, taper, twist), NeuralFoil for the 2-D answer per strip (milliseconds, exact blended section, transition, boundary-layer shape factor at 64 points per surface). | Today one induced angle serves the whole wing, and the tables blend the parents' answers between sections.                                                                                | Build the quasi-3D loop as a flow-map method, check it against the tables on a sample and against a few 3-D runs; neither adds 3-D transition physics. Then revisit 65.                                                                         |
| 67  | **Transition must be captured, with ADflow and SU2** (owner, 4 Nov).                                                                                                                                                                                                       | Laminar runs and bubbles: SA overpredicts the profile drag by a median +62 % (Stage 1).                                                                                                   | Which solver does what (76).                                                                                                                                                                                                                    |
| 68  | **Mach toward 0.5, no supersonic flow** (owner, 4 Nov).                                                                                                                                                                                                                    | Faster UAVs.                                                                                                                                                                              | Core Mach ≤ 0.2 now; 0.3–0.5 later with a fast-UAV family (pending).                                                                                                                                                                            |
| 69  | **Angles −5° to post-stall**, plus a separate post-stall study (owner, 6 Nov).                                                                                                                                                                                             | The whole polar, both signs.                                                                                                                                                              | The lower band (74); steady RANS up to stall onset.                                                                                                                                                                                             |
| 70  | **Similarity** (owner, 6 Nov): unit mean chord, Re an input, Mach 0.1 with Prandtl–Glauert, trailing edge 0.2 % c, root chord out (18 → 17).                                                                                                                               | About 5 × fewer solves (8,000, not 42,000); every shape at all 4 Re levels.                                                                                                               | Stage 1 code first (every hash changes); checks C1–C4.                                                                                                                                                                                          |
| 71  | **Levels VC, C, M, F** (owner, 6 Nov): hard minimums at VC, accuracy targets at M, transition targets at F; VC on the desktop, C, M, F on the HPC.                                                                                                                         | Each target met where it is needed; F near the 9–11 M cells asked.                                                                                                                        | To build.                                                                                                                                                                                                                                       |
| 72  | **Lighter rules** (owner, 6 Nov): bubble length floor 0.10 c from local Re 4 × 10⁵ (band cell 0.5 % c at F); tip gap 2 × s0; station gap 0.25 × chord at M.                                                                                                                | F median 10.9 M instead of 15.2 M with the band alone; about −8 % and −7 % for the other two (estimates).                                                                                 | The shortest high-Re root bubbles get about 3 cells: fine for SA, not for LM (3-D check).                                                                                                                                                       |
| 73  | **One matched C-H volume mesh for ADflow and SU2** (owner, 6 Nov), instead of the overset wake box and tube.                                                                                                                                                               | SU2 has no overset; one family, one error bar.                                                                                                                                            | Stage 3: open-line march, wake lines (about +45 % cells, rough), tip vortex in the outboard blocks.                                                                                                                                             |
| 74  | **Lower band at negative angles** (pending; counted 7 Nov, Study 8).                                                                                                                                                                                                       | At −5° the lower side becomes the suction side: its transition sits at a median of 1–15 % c per type (2-D strips), in front of 60 % c on every strip with an answer.                      | Counted: option A (lower band from the leading edge) gives the same ring as option B (transition runs at ≥ 0° only) on all 20 reference wings × 4 Re (ratio 1.000; F stays about 10.9 M), because both sides share one node list. Mike chooses. |
| 75  | **Nose (64), corrected** (6 Nov): the first reading was overstated.                                                                                                                                                                                                        | Measured the same way, the raw files show nearly the same split.                                                                                                                          | Re-measure raw and built with one curvature method; fix only if needed, before the pyGeo build --all.                                                                                                                                           |
| 76  | **Solver split** (proposal, pending): ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings.                                                                                                                                | ADflow is fast and robust; SU2 has transition models.                                                                                                                                     | An ADflow against SU2 SA code-to-code check; SU2 cost per solve at full size.                                                                                                                                                                   |

## Open, to do, and is it finished?

### Finished (first approach)

**the mesher, its rules, its checks, the screen**

Every wing of the built sets meshes at level C and the reference wings at every Re level; the family rule holds at C, M, F; 14 tests; the decisions and this page.

### Not finished

**the new approach, then the stage**

Decided on 6 Nov, not built: levels VC–F with the targets moved, the lighter rules, similarity (Stage 1 code first). Also owed: the nose re-measure (64), the choice of the lower band (74, counted 7 Nov), the new screen, the pyGeo run on Mike's machine.

### Not known

**anything about the flow**

No solve has been run. Whether the surface gives a good C-H volume mesh and a converged run is Stage 3's first result. The cell counts of the new approach are estimates until a C-H wing is built and counted.

### To do, in order

1.  **Nose re-measure (64, Stage 1):** raw and built with one curvature method; fix only if a real error remains.
2.  **Similarity in the generator (Stage 1 code):** unit mean chord, trailing edge 0.2 % c, root chord out; rebuild the sets (every hash changes); update the Stage 1 page and summary.
3.  **The lower band (74):** counted on 7 Nov with the refine map run down to −5° (Study 8): option A gives the same ring as option B on the 20 reference wings. Mike chooses.
4.  **Stage 2 code, the new rules:** levels VC, C, M, F with the targets moved (71); the lighter band, tip gap and station gap (72); the chosen lower band; the YAML and the laws.
5.  **New screen:** every set at VC and F; the reference wings at every level and Re level; the family ratios; the cell count against the 9–11 M target.
6.  **pyGeo run (Mike's machine):** `pip install -e CFD_Automation`; the Stage 1 tests and `build --all`; then in `Stage_2_surface_mesh`: `python -m pytest` and `python scripts/screen.py`; compare with the branch (counts should match to the node; the loft hash will differ from the numpy one).
7.  **Stage 2 docs final, close, notify.** Then Stage 3: the matched C-H volume mesh on one wing first (open-line march, wake lines to the far field, outboard blocks and the tip vortex, far field 80 c; CGNS for ADflow, a converter to .su2 for SU2), and the first solves.
8.  **Ladders after the first solves:** chordwise (T6: cells per bubble, the band), spanwise (station gap, 12 per panel, tip gap), the nose angle (12 / 10 / 8 / 6°).
9.  **Decide 65 and 66** (the per-wing band, the AVL + NeuralFoil upgrade) after the first 3-D transition runs (SU2 LM on the BWB centre body first).
10. Open from Stage 0 still: the grid share, the pitching-moment budget, the iteration share.

## Handover to Stage 3 (volume mesh, CGNS)

What Stage 3 gets from this stage, and what it must build. The first plan (overset) is kept for the record; the new plan (one matched C-H mesh, decided 6 Nov) replaces it.

- **Input per mesh:** `surface.npz` with `wing (n_ring, n_span, 3)` ring index first, root to tip; `cap (n_chord, n_base, 3)` with i × j outboard; `u` (x/c of every node, NaN on the base), `y`, `v` per station; `stations.csv` with the local Re and chord per station; `quality.json` with `s0_tip_m`, `re_tip`, `mean_chord_m`.
- **The march (recipe R-V):** first cell s0 per station from the local Re and y⁺ = 1 (law 13; `laws.first_cell_c`); growth ≤ 1.25 in the boundary layer; ≥ 30 cells across the boundary layer; reach about 2 chords; cap first cell = tip s0 (the last station gap already equals it). New: y⁺ ≤ 1 and growth 1.25 are hard minimums at VC, so F gets y⁺ about 0.46 and growth 1.107, which meets the transition model's 1.1 (decision 57); the tip gap becomes 2 × s0.
- **The family:** every spacing ÷ 1.3 per level and the growth g^(1/1.3), as on the surface, so the volume levels are true scaled copies; base cells 8 / 10 / 14 / 18 (new names: VC, C, M, F).
- **First plan (replaced):** overset boxes (R-V.6): background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, tube 15–20 cells across the core from 2 c behind the tip, far field 80 c (T2 decides); overset export and the overlap gate (M3).
- **New plan: one matched C-H mesh for ADflow and SU2.** The C block wraps the ring (the nose stays a spacing request inside it, no collar); wake lines from the trailing-edge corners and the base to the far field (80 c), fine near the trailing edge (the first plan's 0.0075 c wake spacing is the starting value); the stations go on past the tip into outboard H blocks, growing from the tip gap; the tip vortex is resolved there by clustering along its path (no tube); the cap is the wall of the first outboard block. Structured CGNS for ADflow; a converter to unstructured hexes (.su2) for SU2. Rough cost: +30–60 % cells on the wing blocks, to be counted on the first wing.
- **Where the march will be tested first:** the tip squeeze (about 40 gaps on the last panel, down to tens of µm; fewer with the tip gap at 2 × s0), the corner wings with an 85°-sweep first panel, and (new) the open-line march at the trailing edge.

## Files and commands

    pip install -e CFD_Automation
    cd CFD_Automation/Stage_2_surface_mesh
    python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5   # one mesh
    python -m pytest                       # 14 tests (test_family builds C and M of the BWB: slow)
    python scripts/screen.py               # every built wing; ~1 h on two cores (parts: scripts/merge_screen.py)
    python scripts/family_check.py         # data/studies/family_ratios.json
    python scripts/nose_radius.py          # data/studies/nose_radius.json
    python scripts/page_figures.py; python scripts/change_figures.py; python scripts/make_figures.py; python scripts/make_stage2_page.py
    python scripts/refine_map_data.py; python scripts/make_refine_page.py   # the refine map (docs/REFINE_MAP.html)
    python scripts/page_figures.py refine_map   # only the refine-map figure of Study 7
    python scripts/band_count.py           # Study 8: the band count (decision 74), about 10 min

| Where                   | What                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
|-------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `cfdauto/mesh/`         | `laws.py` (one function per rule), `spacing.py` (the spacing tool), `ring.py` (section, size fields, nose solve, one distribution, rings), `stations.py`, `cap.py`, `checks.py`, `surface.py` (the build, the checks, the files), `figures.py`, `refine_map.py` (the per-wing band from the flow dataset), `__main__.py`                                                                                                                                    |
| `Stage_2_surface_mesh/` | `configs/surface.yaml`, `decisions/surface_rules.md`, `decisions/STAGE2_STATUS.md`, `docs/` (this page, the refine map `REFINE_MAP.html`, the executive summary `EXECUTIVE_SUMMARY.md` / `.html`, pictures), `tests/mesh/`, `scripts/`, `data/studies/` (`screen_C.json`, `family_ratios.json`, `nose_radius.json`, `refine_map_reference.json`, `band_count.json`); `configs/surface_plan_VC.yaml` (the planned rules at VC, read only by `band_count.py`) |
| one mesh folder         | `surface.npz`, `surface.xyz` (Plot3D), `stations.csv`, `quality.json`, `manifest.json` (wing input hash, loft surface hash, mesh code hash, mesh node hash); refused: `refusal.json` only                                                                                                                                                                                                                                                                   |

Stage 2 of CFD_Automation (karmix96/aeris, branch stage2-surface-mesh). Built and screened with the numpy twin of the loft on 2 Nov 2026 (first approach); updated 6 Nov 2026 with the new approach (decided, not built) and 7 Nov 2026 with the refine map from −5° and the band count (Study 8); cfdauto 0.7.0; screen mesh code hash 8883e200bbbd. Sources: Levy et al. 2013 (DPW gridding guidelines); Celik et al. 2008 (GCI, r ≥ 1.3); Ansys CFX Modeling Guide, γ-Re_θ transition model grid requirements; White, Viscous Fluid Flow (flat-plate friction); the AERIS Mesh Automation Primer, Annex G; S8 (section_o.py, strategy_s8.py).
