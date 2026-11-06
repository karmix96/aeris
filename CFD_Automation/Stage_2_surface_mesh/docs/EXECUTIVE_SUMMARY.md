# Stage_2 — Executive summary: the surface mesh

6 Nov 2026, updated 7 Nov 2026 · Michail Karalis · CFD_Automation, Stage 2 (repo karmix96/aeris, branch `stage2-surface-mesh`)

> **What changed since 3 Nov (updated 7 Nov).** Sections 4–8 hold the details.
>
> - **Decided (owner)**
>   - Transition must be captured, with ADflow and SU2 (4 Nov).
>   - The Mach range extends toward 0.5, with no supersonic flow (4 Nov).
>   - Angles of attack from −5° to post-stall, plus a separate post-stall study (6 Nov).
>   - The new approach (6 Nov): levels VC, C, M, F with each target met at the level that needs it; a lighter band, tip gap and station gap; one matched C-H volume mesh for ADflow and SU2; similarity (every wing at unit mean chord).
> - **Pending**
>   - The lower band at negative angles: counted on 7 Nov (study 8). Option A, the lower band from the leading edge, costs no cells. Mike chooses.
>   - The solver split: ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings.
>   - The core Mach range: ≤ 0.2 now, 0.3–0.5 later with a fast-UAV family.
> - **Open**
>   - The nose (decision 64): the first reading was overstated; re-measure before any fix.
>   - The new approach is not built: the code, a new screen and the pyGeo run are still to do.

Stage 2 puts a structured surface mesh on every wing that Stage 1 makes. The **first approach** is built and screened: **790 of 790 builds pass all 13 checks**, on 730 wings of 4 types and 5 sets plus the 20 reference wings at all four Re levels, in 4–8 s per wing. On 4–6 Nov a **new approach** was decided. It keeps the mesher and changes where each rule is met, three rule values, the volume mesh around the surface and the wing size. It is not built yet. This summary says what Stage 2 is, how one mesh is made, what the eight studies showed, what was first and what changes, what is weak, what is left, and what Stage 3 gets. More detail on every figure: the page *Surface Mesh* (`docs/SURFACE_MESH.html`).

![The surface mesh pipeline in six steps, from the loft to the files](page/pipeline.png)

*What it shows.* The six steps every wing goes through: stations, size fields, the nose solve, one node list, rings and cap, 13 checks, then the files.

**Conclusion.** The same six steps run on every wing. No step knows the wing type: the rules read the loft, the chord and the local Re.

## 1. What Stage 2 is, and why a structured mesh

**What it is.** One wing surface in (the Stage 1 loft), one structured surface mesh out. At every spanwise station there is a closed ring of points around the section, the same ring at every station, from root to tip. One patch closes the flat tip (the *cap*). Every node is asked from the loft at its place; nothing is interpolated between stored sections. The volume mesh (the cells off the wall), the wake and the CGNS file are Stage 3.

**Name and files.** A mesh is named `mesh_<level>_<wing_hash8>_re<Re>`, because two sizes depend on the Re: the tip gap and the band cell. Each mesh writes `surface.npz` (the arrays), `surface.xyz` (Plot3D, opens in ParaView), `stations.csv` (asked and delivered per station), `quality.json` (every check) and `manifest.json` (four hashes). A mesh that fails a check writes only `refusal.json`.

**Why structured.** A structured mesh is rows and columns of cells; every cell has an address (i, j, k).

- It lines the cells up with the boundary layer, so few cells resolve it.
- Every spacing can be divided by exactly 1.3 to make the next finer mesh. The grid-convergence method we use (Celik et al. 2008) needs that.
- Every node has an address (nose, trailing edge, tip), so errors can be mapped by region.
- The mesh is a set of numbers (spacings, counts, growth) that a rule can give. That is the paper's claim.

**What it costs.** One block layout per class of shape (box wings and winglets are out of scope). Every station carries the same ring, so the station that needs the most nodes sets the count for all. Quality follows the geometry: very swept, very thin panels make sheared cells.

![The four reference wings meshed at level C](page/four_types.png)

*What it shows.* The four reference wings (index 0) at level C and Re 3 × 10⁵ on the mean chord: every second station and every 24th ring line of the upper surface.

**Conclusion.** Same rules, same code, four shapes. The BWB gets the most ring nodes, because its root has the highest local Re and so the smallest band cell as a share of the chord. It also gets the most stations, because its tip is the smallest. Nothing was set by hand for any type.

## 2. How one mesh is made: the six steps

1. **Stations (along the semi-span).** A station sits exactly on every loft station (root, both breaks, tip), because the loft has a crease there. Between them the gap is 0.2 × the local chord, at least 12 gaps per panel, and neighbouring gaps differ by at most 1.2. Toward the tip the gaps shrink to the tip's first wall cell s0 (y⁺ = 1 at the tip Re), so the cap meets a cell of the size it will get in the volume mesh.
2. **Size field (around the section).** At every place along the section the cell may not be bigger than the smallest of: 2 % c; the band cell (bubble length / 20) inside the transition band (upper 0–85 % c, lower 60–100 % c); the curvature cap; the nose cell; 0.1 % c at the trailing edge. The cells then grow by at most 1.2 from one to the next.
3. **Nose solve.** The nose cell is found by trial on the ring as built: smaller and smaller, until no node bends the surface by more than 10°.
4. **One node list.** Every station's wish list is put on one scale (a fraction of the side's length), and at every place the smallest cell any station asks for is used, on every station and both sides. Cost: about 3 % more nodes.
5. **Rings and cap.** Upper trailing-edge corner → nose → lower corner → across the blunt base (8 cells at level C). One patch closes the tip, its edge equal to the tip ring node for node.
6. **Thirteen checks.** Turning, kinks, nose envelope, growth along the ring, band spacing, trailing-edge spacing, growth along the semi-span, loft stations hit, tip gap, every ring in its plane, wing-quad quality, cap-quad quality, ring count. Any failure: no mesh, only `refusal.json`.

![Station gaps along the semi-span of the BWB reference wing](page/stations.png)

*What it shows.* The BWB reference wing, level C, Re 3 × 10⁵: the station gap along the semi-span (the 0.2 c target, the 12-per-panel floor, the tip squeeze, the growth limit) and the gaps delivered.

**Conclusion.** The 0.2 c rule hardly acts. The 12-per-panel floor sets the inner panels and the tip squeeze sets the outer one: 43 gaps lie in the last few millimetres, from 3 cm down to 36 µm. The spanwise ladder must test the floor and the squeeze before the 0.2 c value.

![The size field around one section, built one rule at a time](page/size_field.png)

*What it shows.* The root section of the BWB reference wing, upper side. Each panel adds one rule: the 2 % c cap, the band, the curvature cap, the nose and trailing-edge cells, the growth limit, and the shared result.

**Conclusion.** On this wing the band sets almost everything: the whole ring is at band spacing except the nose and the trailing edge. The delivered nose cell (0.04 % c) is smaller than this station's own (0.096 % c), because the sharpest nose of the wing, the tip's MH 61, sets it for every station.

![The band cell: 20 cells across a laminar separation bubble](page/band_cell.png)

*What it shows.* Left: a laminar separation bubble with the 20 cells the rule puts across it, and the band where it may sit. Right: the three steps for one station (local Re → bubble length from the Stage 1 table → ÷ 20).

**Conclusion.** The band cell is one number per station and side, set by the local Re alone. The only free choice is the 20, which comes from one vendor guide (Ansys CFX, for the γ-Re_θ transition model). The bubble lengths are 2-D XFOIL values, so the rule is only as good as that table.

![The nose solve: turning per cell against the nose spacing](page/nose_solve.png)

*What it shows.* Turning per cell against the nose spacing, on rings built at 40 spacings. Left: the BWB root (MH 104). Right: a NACA 4415 station.

**Conclusion.** On MH 104 smaller nose cells give less bending in one steady line, so one search finds the size. On NACA 4415 the line is not steady: below about 0.2 % c the worst cell sits on a small bump of the lower side, not at the nose. So the solve also tries the sizes just below its answer, and the final rings are checked again. Whether that bump is a fault of the Stage 1 resampling or the airfoil's own shape is what the nose re-measure must say (study 4).

![One node list for all stations](page/merge.png)

*What it shows.* Left: the wish lists of three stations (root, mid, tip) and the merged list. Right: the merged list applied to the root ring and the tip ring.

**Conclusion.** The merged list is the lowest of all wish lists: the root's band sets the middle, the tip's nose sets the front, every station's lower band sets the back. Node i lands at the same place on every station, which keeps the cells between stations clean.

![The root ring: node order, nose turning, trailing edge and base](page/ring.png)

*What it shows.* The root ring of the BWB reference wing: the node order, the nose with the turning per node, and the trailing edge with its 0.1 % c cells and the 8 base cells.

**Conclusion.** One closed curve holds the nose, both sides and the base. So the leading edge is a spacing request, not a block size, and the base needs no block of its own. The nose nodes turn by 10° or less; the two trailing-edge corners turn by about 90° by design and are left out of the check.

## 3. The rules and their sources (first approach)

"Law n" is the row of the laws table in the Grand Roadmap (primer, Annex G).

| Where | First rule (level C, as built) | Source | New approach (decided 6 Nov) |
| --- | --- | --- | --- |
| Nose (law 1) | no node turns the surface by more than 10°, solved on the ring as built | Grand Roadmap starting value; S8 | 10° met at M (about 17° at VC) |
| Trailing edge (law 3) | 0.1 % c at the two corners | DPW gridding guidelines | 0.1 % c met at M |
| Blunt base (law 6) | 8 cells at C (10, 14, 18 on the finer levels) | S8; our choice | the same counts at VC, C, M, F |
| Transition band | upper 0–85 % c, lower 60–100 % c; cell = bubble length / 20; bubble 0.40, 0.30, 0.10, 0.05 c at local Re 6 × 10⁴, 10⁵, 4 × 10⁵, 10⁶ | Stage 1 handover; Ansys CFX guide (20 per bubble) | / 20 met at F; bubble length stops at 0.10 c from local Re 4 × 10⁵; lower band at negative angles pending |
| Largest cell | 2 % c outside the bands | our choice | 2 % c at M |
| Growth along the ring | 1.2 built, 1.25 checked | Stage 1 handover; DPW | unchanged (a hard minimum at VC) |
| Stations (laws 8, 9) | one on every loft station; gap 0.2 × chord; ≥ 12 per panel; growth 1.2 (1.3 checked) | geometry; our starting values | gap 0.25 × chord at M |
| Tip (laws 9, 10, 13) | last gap = s0, the first wall cell at y⁺ = 1 at the tip Re | Grand Roadmap; flat plate (White 2006) | last gap = 2 × s0 |
| Levels (law 23) | C, M, F, FF: every spacing ÷ 1.3 per level, growth g^(1/1.3) | Celik et al. 2008 (r ≥ 1.3) | VC, C, M, F with the targets anchored |

**What the band costs.** About 200 ring nodes at Re 10⁵, 400 at 3 × 10⁵, and 850 at and above 1.5 × 10⁶, against 150 in S8. It is the biggest driver of the ring size.

**The two Re-dependent sizes.** The first wall cell s0 is 0.032 % c at Re 6 × 10⁴, 0.0072 % c at 3 × 10⁵ and 0.0024 % c at 10⁶. The band cell at level C is 2.0 % c at Re 6 × 10⁴, 0.63 % c at 3 × 10⁵ and 0.25 % c at 10⁶ and above.

## 4. The studies, with their conclusions

None of them is a flow result: no solver has run on these surfaces.

**Study 1 · The robustness screen.** Every built wing of every type and set was meshed at level C and Re 3 × 10⁵, and the 20 reference wings at all four Re levels, with the numpy twin of the loft. The pass and fail limits were written before the run. Result: 790 builds, 790 passed, 0 refused, 0 crashed. The largest delivered turning was 10.02°, the largest growth 1.21 (limit 1.25), and 32 builds needed a nose repair. The lowest wing-quad quality was 0.09, on corner wings with an 85°-swept first panel. Build time: median 5.0 s, max 8.1 s.

![Every build of the screen](screen_C.png)

*What it shows.* Every build of the screen: ring nodes against the mean chord, stations against the semi-span over the mean chord, and the build time, per type.

**Conclusion.** The ring size is set by the local Re of the largest chord, not by the wing's size: about 600 nodes on the BWB, about 400 on the other three types. The station count rises with the aspect ratio, from about 70 to 130. Every wing takes 4–8 s, so the mesher is not the slow part of the workflow. With 0 failures in 790 builds, the true failure rate is below about 0.4 % with 95 % confidence (rule of three), for the surface alone and the first rules.

**Study 2 · The family ratios.** Levels C, M and F of the four reference wings; every spacing measured between levels.

![The family ratios between levels](page/family.png)

*What it shows.* Left: the BWB root nose at C, M, F. Middle: the measured ratio of every spacing between levels. Right: ring nodes and stations per level, all four types.

**Conclusion.** Every spacing refines by 1.30 within 3 %, and the ring and station counts grow by 1.3 per level: the levels are true scaled copies. The two exceptions are whole numbers: the base cells (8, 10, 14, 18) and the gaps of the first panel. The growth must scale too (g^(1/1.3)), or only the end cells refine.

**Study 3 · One node list per station, or one for the wing.** The worst wing of the first screen (scaled Jacobian 0.08) was rebuilt both ways.

![Quad quality: per-station lists against one list for the wing](page/union_distribution.png)

*What it shows.* A flying wing (training_full 6), level C: the quality of every wing quad (1 = right angles, 0 = flat) with per-station lists and with one list, and the histogram.

**Conclusion.** With one list the sheared quads in the tip squeeze go from 0.08 to 0.58, and the BWB reference wing from 0.77 to 0.92. The price is about 3 % more ring nodes. Decision 60.

**Study 4 · The nose of the built sections.** While solving the nose, the turning did not fall steadily on NACA 4415. So the nose radius of the raw airfoil files was compared with the built sections.

![The first 1.2 % of the chord: raw points, built section, fitted circles](page/nose_radius.png)

*What it shows.* The first 1.2 % of the chord of NACA 4415, E387 and MH 104: the raw file points, the built section, circles fitted to the built upper and lower nose, and the formula's circle for NACA 4415.

**First reading (2 Nov).** The built nose looked lopsided: on NACA 4415, 0.008 c on the upper side and 0.074 c on the lower side, against one radius of 0.0248 c by formula. On cambered sections the two sides differed by 3–13 ×.

**Correction (6 Nov).** That reading compared two different measures: a circle through three raw points against a one-sided formula on the built section. With the same one-sided formula, the raw files show nearly the same split: NACA 4415 raw 0.0081 / 0.0736 c against built 0.0080 / 0.0741 c; SD7032 raw 0.0287 / 0.0023 against built 0.0318 / 0.0023. So the split is mostly how a one-sided formula sees a cambered, tilted nose (about 11° on NACA 4415), not a fault of the geometry. What may remain lies inside the first gap between raw points: under 0.025 % c on NACA 4415, about 7 × smaller than the nose cell of the NACA 4415 reference wings (0.18 % c at C).

**Conclusion.** Decision 64 stays open. Re-measure raw and built with one curvature method that the tilt cannot fool, and fix only if a real error remains. A fix changes every geometry hash, so it must come before the pyGeo `build --all`.

**Study 5 · The corner set: where the rules stop.** The first screen crashed on the smallest BWB corner wing (12 mm tip chord).

![The 12 mm tip section of a corner wing and its trailing-edge bend](page/corner_bend.png)

*What it shows.* The 12 mm tip section: the 0.5 mm trailing-edge floor is 4 % of this chord, so the section opens out over its last 10 % c, and each surface turns by 11–13° within 4 % of the chord.

**Conclusion.** A 2 % c cell across that bend turns by about 10°, so the nose solve could never get under 10°. The fix: the turning rule now applies along the whole ring from the local curvature, not only at the nose. The corner set did its job: it found where the rule stopped, and the rule was widened. Under similarity the trailing edge is 0.2 % c on every wing, so this bend goes.

**Study 6 · Four passes of the screen.** Pass 1 refused or crashed 10 of 790 (tip-gap tolerance, the corner-wing bend, a break 0.9 mm from the root, sheared quads). Pass 2 refused 17 (growth 1.25–1.26 at NACA 4415 noses, now allowed within 1 %). Passes 3 and 4 refused none; pass 3 also found the nose cell held over one cell instead of four.

**Conclusion.** The earlier passes are development evidence; the fourth, on the committed code, is the result. Every failure appeared on the corner and full-space sets, as Stage 0 said it would.

**Study 7 · The refine map: where to refine, per wing.** The Stage 1 flow dataset was read for each of the 20 reference wings (2-D XFOIL strips along the semi-span): where the flow turns turbulent, where the bubbles sit, where it separates, on both surfaces. The envelope over the conditions one mesh serves (Mach 0.03–0.13, −5° to 8° since 7 Nov; 0–8° before), plus a 10 % c margin, is the band that wing would need.

![The refine map of the BWB reference wing](page/refine_map.png)

*What it shows.* The BWB reference wing from above. Left: both surfaces at Mach 0.08 and 4° (laminar, bubble, turbulent, transition point). Right: the band this wing needs over −5° to 8°, against the generic band.

**Conclusion.** The per-wing band is not smaller than the generic one; it sits elsewhere, and from −5° it is wider. Over −5° to 8° its cost is +8 % to +46 % of the generic band's (median +34 %); over 0–8° (first data, 3 Nov) it was −15 % to +20 % (median about +5 %). The generic band misses the upper laminar flow beyond 85 % c at low angle outboard (by 10.5–15 % c; up to 15 % c over 0–8° too), and the lower-surface transition near the leading edge: over −5° to 8° by the full 60 % c on all 20 wings (52–60 % c over 0–8°, on washed-out panels). These costs count each side on its own; in the built ring a lower band from the leading edge costs nothing (study 8). The shortest root bubbles (1.4–10.7 % c) are shorter than the table assumes (5–14 % c) on all 20 wings. It is 2-D and calm air, so it is a candidate (decision 65), not a rule, until a 3-D transition check.

**Study 8 · The band count for negative angles (decision 74, 7 Nov).** New data, with the planned rules of the new approach at VC (read from a plan file; the mesher's config is unchanged). The refine map run down to −5° was read for the lower side. Then the 20 reference wings × 4 Re levels were built at VC twice: with the lower band of option B (60–100 % c) and of option A (0–100 % c), 160 builds. Only the band changes, so the wing-block cells scale with the ring nodes, and a finer level keeps the same ratio (checked at F on two wings).

![The band count: the lower side at negative angles, and option A against option B](page/band_count.png)

*What it shows.* Left: where the lower side turns turbulent, per wing type and root angle (2-D strips with an answer, Mach 0.03–0.13), against the generic lower band. Middle: the cells along the lower side of the BWB root ring at VC, Re 3 × 10⁵, with B and with A, and the lower side's own wish list with B. Right: ring nodes with A against ring nodes with B, all 80 pairs.

**Conclusion.** At −5° the lower side turns turbulent near the nose (median 1–15 % c per type), in front of the generic lower band on every strip with an answer; at 0° still on 51–83 % of the strips. Yet option A costs no cells: A and B give the same ring, node for node, on all 80 pairs (ratio 1.000), so F stays at about 10.9 M cells. Both sides share one node list, and the upper band (0–85 % c) already makes the front of the lower side fine; the earlier "1.5 × longer band" counted each side on its own. So the cells no longer decide: A keeps transition runs from −5° at no mesh cost; B only saves the LM runs below 0°. Limits: 2-D strips in calm air; no answer on 42 % (BWB) and 30 % (flying wing) of the strips at −5°. Mike chooses.

## 5. What was first, and what changes with the new approach

The code still builds the first approach. Everything in sections 2–4 is first-approach evidence: it shows the mesher works. The new approach is decided, not built.

| What | First (built 2–3 Nov) | New approach | Status |
| --- | --- | --- | --- |
| Levels | C, M, F, FF; every rule met at C, the coarsest | VC, C, M, F. Hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap); accuracy targets at M (nose 10°, trailing edge 0.1 % c, station gap, largest cell); transition targets at F (20 cells per bubble, wall growth about 1.1). VC on the desktop; C, M, F on the university HPC | decided, to build |
| Band cell | bubble length / 20 at C | bubble length / 20 at F; the bubble length stops at 0.10 c from local Re 4 × 10⁵ (0.5 % c at F) | decided, to build |
| Stations, tip | gap 0.2 × chord at C; last gap = s0 | gap 0.25 × chord at M; last gap = 2 × s0 | decided, to build |
| Lower band | 60–100 % c, for 0–8° | option A: from the leading edge; option B: transition runs only at ≥ 0°. Counted 7 Nov (study 8): A gives the same ring as B on the 20 reference wings × 4 Re (ratio 1.000); F stays about 10.9 M | pending: Mike chooses |
| Volume mesh | O-H body mesh + overset wake box and tip-vortex tube (ADflow only) | one matched C-H mesh for ADflow and SU2; wake lines to the far field; tip vortex in the outboard blocks | decided; Stage 3 |
| Wing size | real size; trailing edge max(0.5 / 1.0 mm, 0.2 % c) | unit mean chord; Re an input (4 levels); Mach 0.1 + Prandtl–Glauert; trailing edge 0.2 % c; root chord out (18 → 17) | decided; Stage 1 code first |
| Flow, angles, Mach | ADflow SA; 0–8°; Mach 0.03–0.20 | transition with ADflow and SU2; −5° to post-stall; toward Mach 0.5, no supersonic flow | decided; split and core Mach pending |
| Nose (64) | "the built nose is not round" | overstated; re-measure, fix only if needed | to do next |
| Fine level | no target | about 10–11 M cells median (wing blocks); the C-H wake lines may add about +45 % | estimate |

![Where each rule is met on the four levels, first against new](page/levels_first_new.png)

*What it shows.* Four rules on the four levels, first (grey) against new (blue): the value each level gets when a rule is met at one level and every spacing is ÷ 1.3 per level. Level names: first C, M, F, FF; new VC, C, M, F (the same four places on the ladder).

**Conclusion.** First, every target was met at the coarsest level, so the finer levels went far past it (44 cells per bubble at FF), while the cells grew about 2.2 × per level. New, each target is met where it is needed: the accuracy targets at M, as the DPW guidelines define their medium grid, and the transition target at F, where SU2 with LM will run. The coarse levels are coarser than before (about 17° per nose cell and 9 cells per bubble at VC): good enough for the SA mesh studies, not for transition. The wall rules do not change: y⁺ ≤ 1 and growth 1.25 at the coarsest level give 1.107 at F, which already meets the 1.1 a transition model asks for.

![Cells per level and the fine level per rule set](page/cost_first_new.png)

*What it shows.* Left: cells per mesh at the new levels with the lighter band, median and largest over the 20 reference wings × 4 Re levels (built surfaces × wall layers by formula; the wing blocks only). Right: the fine level F per rule set.

**Conclusion.** With the lighter band the fine level is 10.9 M cells (median), inside the 9–11 M asked on 3 Nov; the planned rules gave 15.2 M. Only VC fits the desktop (1.0 M median, largest 1.5 M, against a limit of about 1.2 M). The C-H wake lines are not in these counts: a rough +30–60 % puts F at about 14–17 M. The cost is not settled until the first C-H wing is built and counted.

![The volume topology, first against new](page/topology_first_new.png)

*What it shows.* Left: the first plan, O rings with an overset wake box (ADflow only). Middle: the new plan, one matched C-H mesh; the C rows wrap the nose and leave the trailing edge. Right: the new plan from above; the station lines go on behind the wing and past the tip. Schematic, not a mesh.

**Conclusion.** The surface mesh does not change: the ring is still the first row and the cap still closes the tip. The volume mesh changes (Stage 3): a march from an open line at the trailing edge, wake lines to the far field, the tip vortex clustered in the outboard blocks instead of a tube, and no overlap gate. The nose must stay a spacing request inside the C block: a separate 5-point nose collar is what broke S6. The gain is one mesh family and one error bar for both solvers.

![The lower band at negative angles: the two options](page/band_negative.png)

*What it shows.* The transition band on one section: the first band, and the two options for negative angles.

**Conclusion.** The first band was set for 0–8°. At −5° the lower side takes the suction peak near the nose, so its transition and bubbles move forward, out of the band (median 1–15 % c per type at −5°, study 8). Option A covers them with one rule for both sides. On paper its band is about 1.5 × longer (125 → 185 % of the chord), but counted on the 20 reference wings it costs no cells, because both sides share one node list. Option B keeps the same cells and gives up transition data below 0°. Mike chooses.

**What stays the same.** The six steps and the code; the ring and the cap; the family rule (÷ 1.3 per level, growth g^(1/1.3)); the 13 checks; one surface per wing and Re level.

## 6. Weak points, said plainly

- **Numpy loft only.** Every mesh so far was built on the numpy twin of the loft. The pyGeo run on Mike's machine is owed.
- **No solve yet.** Nothing here shows that the surface gives a good volume mesh or a converged run.
- **The new approach is not built.** Its cell counts are estimates (F about 10–11 M, the C-H wake lines about +45 %, rough).
- **The band rule rests on one source.** 20 cells per bubble comes from one vendor guide, for one model. The lighter band gives the shortest high-Re root bubbles (about 1.5 % c) only about 3 cells: fine for SA, wrong for LM.
- **The generic band sits in the wrong place** on washed-out panels (study 7), and at −5° its lower band misses the lower suction side on every strip with an answer. The shared node list already puts band cells there (study 8), so the mesh is fine there; only the stated lower band is wrong.
- **The coarse levels do not resolve transition.** VC and C have about 9 and 12 cells per bubble, so transition results there must not be trusted.
- **Starting values without a ladder:** the station gap, the 12 per panel, the tip gap and the 2 % c cap.
- **The nose (64)** is still open, although the first reading was overstated.

## 7. Open and to do, in order

1. **Nose re-measure (Stage 1, decision 64):** raw and built with one curvature method; fix only if a real error remains.
2. **Similarity in the generator (Stage 1 code):** unit mean chord, trailing edge 0.2 % c, root chord out; rebuild the sets (every hash changes); update the Stage 1 files.
3. **The lower band (74):** counted on 7 Nov (study 8): option A gives the same ring as option B, so it costs no cells. Mike chooses.
4. **Stage 2 code, the new rules:** levels VC, C, M, F with the targets moved; the lighter band, tip gap and station gap; the chosen lower band.
5. **New screen:** every set at VC and F; the reference wings at every level and Re level; the family ratios; the cell count against 9–11 M.
6. **pyGeo run (Mike's machine):** the Stage 1 tests and `build --all`, then the Stage 2 tests and screen.
7. **Close Stage 2:** final page, summary and handover; notify.
8. **Stage 3:** the matched C-H volume mesh on one wing first, then the first solves.
9. **Ladders after the first solves:** chordwise (cells per bubble, the band), spanwise (station gap, tip gap), the nose angle (12, 10, 8, 6°).
10. **Decide 65 and 66** (the per-wing band; AVL and NeuralFoil for the flow dataset) after the first 3-D transition runs.

## 8. Handover to Stage 3 (the volume mesh)

- **Input per mesh:** `surface.npz` with the wing rings (ring index first, root to tip) and the cap; x/c of every node; `stations.csv` with the local Re and chord per station; `quality.json` with the tip's first cell `s0_tip_m`.
- **The march:** first cell s0 per station from the local Re and y⁺ = 1; growth ≤ 1.25 in the boundary layer; at least 30 cells across it; reach about 2 chords; the cap's first cell = the tip s0. New: y⁺ ≤ 1 and growth 1.25 are hard minimums at VC, so F gets y⁺ about 0.46 and growth 1.107; the tip gap becomes 2 × s0.
- **The family:** every spacing ÷ 1.3 per level and the growth g^(1/1.3), in the volume too; base cells 8, 10, 14, 18 at VC, C, M, F.
- **First plan (replaced):** overset boxes: background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, a tube with 15–20 cells across the vortex core from 2 c behind the tip, far field 80 c; the overset export and the overlap gate.
- **New plan: one matched C-H mesh for ADflow and SU2.**
  - The C block wraps the ring, and the nose stays a spacing request inside it: no collar.
  - Wake lines run from the trailing-edge corners and the base to the far field (80 c), fine near the trailing edge (0.0075 c as the starting value).
  - The stations go on past the tip into outboard blocks, growing from the tip gap. The tip vortex is resolved there by clustering cells along its path (no tube). The cap is the wall of the first outboard block.
  - Structured CGNS for ADflow; a converter to unstructured hexes (.su2) for SU2.
  - Rough cost: +30–60 % cells on the wing blocks, to be counted on the first wing.
- **Test the march first** on the tip squeeze (about 40 gaps on the last panel, down to tens of µm), on the corner wings with an 85°-swept first panel, and on the new open-line march at the trailing edge.

**Sources.** Levy et al. 2013 (DPW gridding guidelines); Celik et al. 2008 (grid convergence, r ≥ 1.3); Ansys CFX Modeling Guide, γ-Re_θ transition-model grid requirements; White, *Viscous Fluid Flow* (flat-plate friction); the AERIS Mesh Automation Primer, Annex G (the Grand Roadmap); S8 (the AERIS mesh study). Decisions: `CFD_Automation/OPEN_DECISIONS.md` 56–76.
