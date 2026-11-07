# Stage_2 — Executive summary: the surface mesh

6 Nov 2026, updated 7 Nov 2026 (evening) · Michail Karalis · CFD_Automation, Stage 2 (repo karmix96/aeris, branch `stage2-surface-mesh`)

> **What changed since 3 Nov (updated 7 Nov, evening).** Sections 4–8 hold the details.
>
> - **Built on 7 Nov**
>   - The new surface rules (decisions 71, 72, 74): levels VC, C, M, F with each target met at the level that needs it; the lighter band, tip gap and station gap; the lower band from the leading edge (option A, chosen by Mike on 7 Nov). The first approach is kept in `configs/surface_first.yaml`.
>   - In Stage 1: the nose fix (decision 64; the defect was real, the 6 Nov correction was wrong) and similarity (decision 70: every wing at unit mean chord; the sets rebuilt, 722 of 722).
>   - The new screen (study 9): 1,724 of 1,724 builds pass, at all four levels; F has 6.9 M cells median on the wing blocks (an estimate; the C-H wake lines add a rough +30–60 %), below the 9–11 M asked.
>   - The refine map at the Re levels (study 11): the lower band holds every strip; the upper band as written (0–85 % c) misses the upper transition at low Re, but the built mesh has band-size cells there.
>   - The nose solved at every level, the strictest wins (Mike's answer, 7 Nov): first it was solved at VC and F only, and M needed a repair (nose × 0.9) on all 20 flying-wing reference builds (nose cell C/M 1.44, M/F 1.17 instead of 1.3). Now: 0 repairs on the reference builds, and the family rule is exact; 4 of 782 F builds of the full sets still needed one round.
> - **Decided (owner)**
>   - Transition must be captured, with ADflow and SU2 (4 Nov). The Mach range extends toward 0.5, with no supersonic flow (4 Nov). Angles of attack from −5° to post-stall, plus a separate post-stall study (6 Nov). One matched C-H volume mesh for ADflow and SU2 (6 Nov; Stage 3).
>   - The Re levels stay 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶; 10⁵ is 18 % below the slowest real UAV, kept as a margin (7 Nov).
> - **Pending**
>   - Two builder choices in the built rules, both stricter than decided, for Mike to confirm (decision 77): the growth limits by the family rule; the station growth kept at 1.2 (17 % more stations than the plan file).
>   - The upper band: kept at 0–85 % c as written; as built the upper side has band-size cells to the trailing edge anyway. Writing 0–100 % c is Mike's choice: the same mesh at VC, 2 more ring nodes at F on 42 of 80 reference builds (+0.39 % cells), and a re-run of the screen (study 11).
>   - The solver split (ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings) and the core Mach range (≤ 0.2 now, 0.3–0.5 later).
> - **Open**
>   - The pyGeo run on Mike's machine; then close Stage 2 and start Stage 3.

Stage 2 puts a structured surface mesh on every wing that Stage 1 makes. The **first approach** was built and screened on 2–3 Nov: 790 of 790 builds passed all 13 checks, on 730 wings of 4 types and 5 sets plus the 20 reference wings at all four Re levels. On 4–6 Nov a **new approach** was decided, and on **7 Nov it was built and screened**: 1,724 of 1,724 builds pass, on the rebuilt sets (unit mean chord, the true nose), at all four levels VC, C, M and F. It keeps the mesher and changes where each rule is met, three rule values, the lower band, the volume mesh around the surface (Stage 3) and the wing size. This summary says what Stage 2 is, how one mesh is made, what the eleven studies showed, what was first and what changed, what is weak, what is left, and what Stage 3 gets. Studies 1–7 are first-approach evidence, on the geometry of before 7 Nov; studies 8–11 are new. More detail on every figure: the page *Surface Mesh* (`docs/SURFACE_MESH.html`).

![The surface mesh pipeline in six steps, from the loft to the files](page/pipeline.png)

*What it shows.* The six steps every wing goes through: stations, size fields, the nose solve, one node list, rings and cap, 13 checks, then the files.

**Conclusion.** The same six steps run on every wing, in both approaches. No step knows the wing type: the rules read the loft, the chord and the local Re.

## 1. What Stage 2 is, and why a structured mesh

**What it is.** One wing surface in (the Stage 1 loft), one structured surface mesh out. At every spanwise station there is a closed ring of points around the section, the same ring at every station, from root to tip. One patch closes the flat tip (the *cap*). Every node is asked from the loft at its place; nothing is interpolated between stored sections. The volume mesh (the cells off the wall), the wake and the CGNS file are Stage 3.

**Name and files.** A mesh is named `mesh_<level>_<wing_hash8>_re<Re>` (for example `mesh_VC_…`), because two sizes depend on the Re: the tip gap and the band cell. Each mesh writes `surface.npz` (the arrays), `surface.xyz` (Plot3D, opens in ParaView), `stations.csv` (asked and delivered per station), `quality.json` (every check, and every rule value with its anchor level and reason) and `manifest.json` (hashes, and the rules file). A mesh that fails a check writes only `refusal.json`.

**Why structured.** A structured mesh is rows and columns of cells; every cell has an address (i, j, k).

- It lines the cells up with the boundary layer, so few cells resolve it.
- Every spacing can be divided by exactly 1.3 to make the next finer mesh. The grid-convergence method we use (Celik et al. 2008) needs that.
- Every node has an address (nose, trailing edge, tip), so errors can be mapped by region.
- The mesh is a set of numbers (spacings, counts, growth) that a rule can give. That is the paper's claim.

**What it costs.** One block layout per class of shape (box wings and winglets are out of scope). Every station carries the same ring, so the station that needs the most nodes sets the count for all. Quality follows the geometry: very swept, very thin panels make sheared cells.

![The four reference wings meshed at level C](page/four_types.png)

*What it shows.* First approach, on the geometry of before 7 Nov: the four reference wings (index 0) at level C and Re 3 × 10⁵ on the mean chord, every second station and every 24th ring line of the upper surface.

**Conclusion.** Same rules, same code, four shapes. The BWB gets the most ring nodes, because its root has the highest local Re and so the smallest band cell as a share of the chord. It also gets the most stations, because its tip is the smallest. Nothing was set by hand for any type.

## 2. How one mesh is made: the six steps

The steps are the same in both approaches; the numbers here are the first approach's (level C). The new values per level are in section 3.

1. **Stations (along the semi-span).** A station sits exactly on every loft station (root, both breaks, tip), because the loft has a crease there. Between them the gap is 0.2 × the local chord, at least 12 gaps per panel, and neighbouring gaps differ by at most 1.2. Toward the tip the gaps shrink to the tip's first wall cell s0 (y⁺ = 1 at the tip Re), so the cap meets a cell of the size it will get in the volume mesh. New: 0.25 × the local chord at M, and the last gap 2 × s0.
2. **Size field (around the section).** At every place along the section the cell may not be bigger than the smallest of: 2 % c; the band cell (bubble length / 20) inside the transition band (upper 0–85 % c, lower 60–100 % c, new: 0–100 % c); the curvature cap; the nose cell; 0.1 % c at the trailing edge. The cells then grow by at most 1.2 from one to the next.
3. **Nose solve.** The nose cell is found by trial on the ring as built: smaller and smaller, until no node bends the surface by more than 10°. New: each level has its own angle (16.9° at VC down to 7.69° at F); the nose is solved at every level, and the strictest spacing wins.
4. **One node list.** Every station's wish list is put on one scale (a fraction of the side's length), and at every place the smallest cell any station asks for is used, on every station and both sides. Cost: about 3 % more nodes.
5. **Rings and cap.** Upper trailing-edge corner → nose → lower corner → across the blunt base (8 cells at level C; 8, 10, 14, 18 at VC, C, M, F). One patch closes the tip, its edge equal to the tip ring node for node.
6. **Thirteen checks.** Turning, kinks, nose envelope, growth along the ring, band spacing, trailing-edge spacing, growth along the semi-span, loft stations hit, tip gap, every ring in its plane, wing-quad quality, cap-quad quality, ring count. Any failure: no mesh, only `refusal.json`. New: each level is checked against its own limits.

![Station gaps along the semi-span of the BWB reference wing](page/stations.png)

*What it shows.* First approach: the BWB reference wing, level C, Re 3 × 10⁵: the station gap along the semi-span (the 0.2 c target, the 12-per-panel floor, the tip squeeze, the growth limit) and the gaps delivered.

**Conclusion.** The 0.2 c rule hardly acts. The 12-per-panel floor sets the inner panels and the tip squeeze sets the outer one: 43 gaps lie in the last few millimetres, from 3 cm down to 36 µm. The spanwise ladder must test the floor and the squeeze before the gap value.

![The size field around one section, built one rule at a time](page/size_field.png)

*What it shows.* First approach: the root section of the BWB reference wing, upper side. Each panel adds one rule: the 2 % c cap, the band, the curvature cap, the nose and trailing-edge cells, the growth limit, and the shared result.

**Conclusion.** On this wing the band sets almost everything: the whole ring is at band spacing except the nose and the trailing edge. The delivered nose cell (0.04 % c) is smaller than this station's own (0.096 % c), because the sharpest nose of the wing, the tip's MH 61, sets it for every station.

![The band cell: 20 cells across a laminar separation bubble](page/band_cell.png)

*What it shows.* Left: a laminar separation bubble with the 20 cells the rule puts across it, and the band where it may sit. Right: the three steps for one station (local Re → bubble length from the Stage 1 table → ÷ 20).

**Conclusion.** The band cell is one number per station and side, set by the local Re alone. The only free choice is the 20, which comes from one vendor guide (Ansys CFX, for the γ-Re_θ transition model). The bubble lengths are 2-D XFOIL values, so the rule is only as good as that table. New: the 20 is met at F (9.1 at VC), and the bubble length stops at 0.10 c from local Re 4 × 10⁵.

![The nose solve: turning per cell against the nose spacing](page/nose_solve.png)

*What it shows.* First approach, on the old sections: turning per cell against the nose spacing, on rings built at 40 spacings. Left: the BWB root (MH 104). Right: a NACA 4415 station.

**Conclusion.** On MH 104 smaller nose cells give less bending in one steady line, so one search finds the size. On NACA 4415 the line is not steady: below about 0.2 % c the worst node sits 1.9–2.4 % c down the lower side, where the growth limit sets the cells, so the line goes flat at about 7°. The old section also had a bump on its lower side; it was a Stage 1 defect, now fixed (study 4), but it is not what makes the line flat: the true airfoil does the same (6.0–6.8°). So the solve also tries the sizes just below its answer, and the final rings are checked again.

![One node list for all stations](page/merge.png)

*What it shows.* Left: the wish lists of three stations (root, mid, tip) and the merged list. Right: the merged list applied to the root ring and the tip ring.

**Conclusion.** The merged list is the lowest of all wish lists: the root's band sets the middle, the tip's nose sets the front, every station's lower band sets the back. Node i lands at the same place on every station, which keeps the cells between stations clean.

![The root ring: node order, nose turning, trailing edge and base](page/ring.png)

*What it shows.* The root ring of the BWB reference wing: the node order, the nose with the turning per node, and the trailing edge with its 0.1 % c cells and the 8 base cells.

**Conclusion.** One closed curve holds the nose, both sides and the base. So the leading edge is a spacing request, not a block size, and the base needs no block of its own. The nose nodes turn by 10° or less; the two trailing-edge corners turn by about 90° by design and are left out of the check.

## 3. The rules and their sources

"Law n" is the row of the laws table in the Grand Roadmap (primer, Annex G). The new values are built (7 Nov): `configs/surface.yaml`, read by `laws.py`, which moves each value from its anchor level by the family rule (÷ 1.3 per finer level for spacings and angles, × 1.3 for counts, g^(1/1.3) for growth).

| Where | First rule (level C, built 2–3 Nov) | Source | New (built 7 Nov): VC / C / M / F |
| --- | --- | --- | --- |
| Nose (law 1) | no node turns the surface by more than 10°, solved on the ring as built | Grand Roadmap starting value; S8 | 10° at M: 16.9 / 13 / 10 / 7.69°; solved at every level, the strictest spacing wins |
| Trailing edge (law 3) | 0.1 % c at the two corners | DPW gridding guidelines | 0.1 % c at M: 0.169 / 0.130 / 0.100 / 0.077 % c |
| Blunt base (law 6) | 8 cells at C (10, 14, 18 on the finer levels) | S8; our choice | 8 / 10 / 14 / 18 (≥ 8 at VC) |
| Transition band | upper 0–85 % c, lower 60–100 % c; cell = bubble length / 20; bubble 0.40, 0.30, 0.10, 0.05 c at local Re 6 × 10⁴, 10⁵, 4 × 10⁵, 10⁶ | Stage 1 handover; Ansys CFX guide (20 per bubble) | upper 0–85 % c (as built band-size cells to the trailing edge; 0–100 % c is Mike's choice), lower 0–100 % c (74, A); cell = bubble / 9.1 / 11.8 / 15.4 / 20; bubble 0.40, 0.30, 0.10, 0.10 c |
| Largest cell | 2 % c outside the bands | our choice | 2 % c at M: 3.38 / 2.60 / 2.00 / 1.54 % c |
| Growth along the ring | 1.2 built, 1.25 checked | Stage 1 handover; DPW | built 1.2 / 1.15 / 1.11 / 1.087; checked 1.25 / 1.19 / 1.14 / 1.107 |
| Stations (laws 8, 9) | one on every loft station; gap 0.2 × chord; ≥ 12 per panel; growth 1.2 (1.3 checked) | geometry; our starting values | gap 0.4225 / 0.325 / 0.25 / 0.192 × chord; ≥ 8 / 10 / 12 / 16 per panel; growth 1.2 at VC (checked 1.3 / 1.22 / 1.17 / 1.13) |
| Tip (laws 9, 10, 13) | last gap = s0, the first wall cell at y⁺ = 1 at the tip Re | Grand Roadmap; flat plate (White 2006) | last gap = 2 × s0; y⁺ 1 / 0.77 / 0.59 / 0.46 |
| Levels (law 23) | C, M, F, FF: every spacing ÷ 1.3 per level, growth g^(1/1.3) | Celik et al. 2008 (r ≥ 1.3) | VC, C, M, F: hard minimums at VC, accuracy targets at M, transition targets at F |

**What the band costs.** First approach: about 200 ring nodes at Re 10⁵, 400 at 3 × 10⁵, and 850 at and above 1.5 × 10⁶, against 150 in S8. New: 120–220–240 ring nodes at VC and 254–474–514 at F (study 9).

**The two Re-dependent sizes.** The first wall cell s0 is 0.032 % c at Re 6 × 10⁴, 0.0072 % c at 3 × 10⁵ and 0.0024 % c at 10⁶ (y⁺ = 1). The band cell at the first level C is 2.0 % c at Re 6 × 10⁴, 0.63 % c at 3 × 10⁵ and 0.25 % c at 10⁶ and above; new at F: 0.5 % c from local Re 4 × 10⁵ up.

## 4. The studies, with their conclusions

None of them is a flow result: no solver has run on these surfaces. Studies 1–7 are first-approach evidence, on the geometry of before 7 Nov (real size, the old nose rule, the old 20 reference wings, 13 of which were replaced on 7 Nov). Studies 8–11 are new.

**Study 1 · The robustness screen (first approach).** Every built wing of every type and set was meshed at level C and Re 3 × 10⁵, and the 20 reference wings at all four Re levels, with the numpy twin of the loft. The pass and fail limits were written before the run. Result: 790 builds, 790 passed, 0 refused, 0 crashed. The largest delivered turning was 10.02°, the largest growth 1.21 (limit 1.25), and 32 builds needed a nose repair. The lowest wing-quad quality was 0.09, on corner wings with an 85°-swept first panel. Build time: median 5.0 s, max 8.1 s.

![Every build of the screen](screen_C.png)

*What it shows.* Every build of the first screen: ring nodes against the mean chord, stations against the semi-span over the mean chord, and the build time, per type.

**Conclusion.** The ring size is set by the local Re of the largest chord, not by the wing's size: about 600 nodes on the BWB, about 400 on the other three types. The station count rises with the aspect ratio, from about 70 to 130. Every wing takes 4–8 s, so the mesher is not the slow part of the workflow. With 0 failures in 790 builds, the true failure rate is below about 0.4 % with 95 % confidence (rule of three), for the surface alone and the first rules.

**Study 2 · The family ratios (first approach).** Levels C, M and F of the four reference wings; every spacing measured between levels.

![The family ratios between levels](page/family.png)

*What it shows.* Left: the BWB root nose at C, M, F. Middle: the measured ratio of every spacing between levels. Right: ring nodes and stations per level, all four types.

**Conclusion.** Every spacing refines by 1.30 within 3 %, and the ring and station counts grow by 1.3 per level: the levels are true scaled copies. The two exceptions are whole numbers: the base cells (8, 10, 14, 18) and the gaps of the first panel. The growth must scale too (g^(1/1.3)), or only the end cells refine. The new rules show the same on all four levels (study 9).

**Study 3 · One node list per station, or one for the wing (first approach).** The worst wing of the first screen (scaled Jacobian 0.08) was rebuilt both ways.

![Quad quality: per-station lists against one list for the wing](page/union_distribution.png)

*What it shows.* A flying wing (training_full 6), level C: the quality of every wing quad (1 = right angles, 0 = flat) with per-station lists and with one list, and the histogram.

**Conclusion.** With one list the sheared quads in the tip squeeze go from 0.08 to 0.58, and the BWB reference wing from 0.77 to 0.92. The price is about 3 % more ring nodes. Decision 60.

**Study 4 · The nose of the built sections.** While solving the nose, the turning did not fall steadily on NACA 4415. So the nose radius of the raw airfoil files was compared with the built sections.

![The first 1.2 % of the chord: raw points, built section, fitted circles](page/nose_radius.png)

*What it shows.* First approach, the old sections: the first 1.2 % of the chord of NACA 4415, E387 and MH 104: the raw file points, the built section, circles fitted to the built upper and lower nose, and the formula's circle for NACA 4415.

**First reading (2 Nov).** The built nose looked lopsided: on NACA 4415, 0.008 c on the upper side and 0.074 c on the lower side, against one radius of 0.0248 c by formula. On cambered sections the two sides differed by 3–13 ×. The likely cause named then: the leading edge is taken at the raw point farthest from the trailing edge, not at the nose apex.

**Correction (6 Nov), withdrawn on 7 Nov: it was wrong.** It said: with the same one-sided formula the raw files show nearly the same split (NACA 4415 raw 0.0081 / 0.0736 c against built 0.0080 / 0.0741 c), so the split is mostly how a one-sided formula sees a tilted nose. But it compared built and raw only at the raw points, where they agree by construction; the defect sat between them.

**Second correction (7 Nov): the defect is real; fixed in Stage 1.** Stage 1 measured raw and built with one curvature method that no frame or formula can fool (each curve a smooth spline, its curvature from its own derivatives along its own arc), and the largest turning a cell of 0.04–0.50 % c gets near the nose, against a 5 % test written before the run.

![The nose defect and its fix](page/nose_fixed.png)

*What it shows.* Left: the curvature around the NACA 4415 nose: the true shape, the old built section and the new one. Second: the worst error of the turning per cell on the ten airfoils, old rule against new, against the 5 % test. Third: the Stage 2 nose solve on a NACA 4415 station, old section against new. Right: the nose cell the mesher delivers at level C (first rules) on the same 20 shapes at unit mean chord, old section against new.

**Conclusion.** The defect was real, and the 2 Nov cause was right. The old rule put the leading edge at the farthest raw point, not at the curve's apex, and forced the tangent square there, so one side got a spike of curvature and the other a flat spot, between the raw points. On NACA 4415 a 0.18 % c cell turned 9.47° built against 4.31° true (+121 %; +449 % at 0.04 % c), and the old rule failed the 5 % test on all ten airfoils. The new rule (one cubic spline, the leading edge at its apex, 201 points per side) passes on all ten (worst −3.9 %, MH 60) and on 95.6 % of the database (21.0 % before); a gate refuses 14 files whose nose folds back (none is used). Mike decided the fix on 7 Nov (decision 64); it is built and the sets were rebuilt. For the mesh: at the same 10° the NACA 4415 / 4412 reference wings now get a nose cell of 0.245–0.265 % c instead of 0.178 % c; the MH wings change little (0.036–0.052 → 0.041–0.056 % c). The flat part of the nose solve stays (growth law, true airfoil too: 6.0–6.8°), so the window search stays.

**Study 5 · The corner set: where the rules stop (first approach).** The first screen crashed on the smallest BWB corner wing (12 mm tip chord).

![The 12 mm tip section of a corner wing and its trailing-edge bend](page/corner_bend.png)

*What it shows.* The 12 mm tip section: the 0.5 mm trailing-edge floor is 4 % of this chord, so the section opens out over its last 10 % c, and each surface turns by 11–13° within 4 % of the chord.

**Conclusion.** A 2 % c cell across that bend turns by about 10°, so the nose solve could never get under 10°. The fix: the turning rule now applies along the whole ring from the local curvature, not only at the nose. The corner set did its job: it found where the rule stopped, and the rule was widened. Under similarity (built 7 Nov) the trailing edge is 0.2 % c on every wing, so this bend is gone.

**Study 6 · Four passes of the screen (first approach).** Pass 1 refused or crashed 10 of 790 (tip-gap tolerance, the corner-wing bend, a break 0.9 mm from the root, sheared quads). Pass 2 refused 17 (growth 1.25–1.26 at NACA 4415 noses, now allowed within 1 %). Passes 3 and 4 refused none; pass 3 also found the nose cell held over one cell instead of four.

**Conclusion.** The earlier passes are development evidence; the fourth, on the committed code, is the result. Every failure appeared on the corner and full-space sets, as Stage 0 said it would.

**Study 7 · The refine map: where to refine, per wing.** The Stage 1 flow dataset was read for each of the 20 reference wings (2-D XFOIL strips along the semi-span): where the flow turns turbulent, where the bubbles sit, where it separates, on both surfaces. The envelope over the conditions one mesh serves (Mach 0.03–0.13, −5° to 8° since 7 Nov; 0–8° before), plus a 10 % c margin, is the band that wing would need.

![The refine map of the BWB reference wing](page/refine_map.png)

*What it shows.* The BWB reference wing from above (the old reference wing, at real size). Left: both surfaces at Mach 0.08 and 4° (laminar, bubble, turbulent, transition point). Right: the band this wing needs over −5° to 8°, against the first generic band.

**Conclusion.** The per-wing band is not smaller than the generic one; it sits elsewhere, and from −5° it is wider. Over −5° to 8° its cost is +8 % to +46 % of the generic band's (median +34 %); over 0–8° (first data, 3 Nov) it was −15 % to +20 % (median about +5 %). The first generic band missed the upper laminar flow beyond 85 % c at low angle outboard (by 10.5–15 % c), and the lower-surface transition near the leading edge: over −5° to 8° by the full 60 % c on all 20 wings. The new lower band (0–100 % c) covers that at no cost (study 8). The shortest root bubbles (1.4–10.7 % c) are shorter than the table assumes (5–14 % c) on all 20 wings. It is 2-D and calm air, on the old reference wings at real size, so it is a candidate (decision 65), not a rule, until a 3-D transition check.

**Study 8 · The band count for negative angles (decision 74, 7 Nov, before the build).** New data, with the planned rules of the new approach at VC read from a plan file, on the old reference wings. The refine map run down to −5° was read for the lower side. Then the 20 reference wings × 4 Re levels were built at VC twice: with the lower band of option B (60–100 % c) and of option A (0–100 % c), 160 builds.

![The band count: the lower side at negative angles, and option A against option B](page/band_count.png)

*What it shows.* Left: where the lower side turns turbulent, per wing type and root angle (2-D strips with an answer, Mach 0.03–0.13), against the first lower band. Middle: the cells along the lower side of the BWB root ring at VC, Re 3 × 10⁵, with B and with A, and the lower side's own wish list with B. Right: ring nodes with A against ring nodes with B, all 80 pairs.

**Conclusion.** At −5° the lower side turns turbulent near the nose (median 1–15 % c per type), in front of the first lower band on every strip with an answer; at 0° still on 51–83 % of the strips. Yet option A costs no cells: A and B give the same ring, node for node, on all 80 pairs (ratio 1.000). Both sides share one node list, and the upper band (0–85 % c) already makes the front of the lower side fine. So Mike chose A on 7 Nov, and it is built: transition runs can start at −5°.

**Study 9 · The new screen: the built rules on every wing (7 Nov).** The rules built on 7 Nov, on the rebuilt sets (unit mean chord, the nose fix; 722 wings), numpy loft. Every set at VC and at F (all sets at Re 3 × 10⁵, the 20 reference wings at all four Re levels: 782 builds per level), and the 20 reference wings at C and M (80 builds each). The nose is solved at every level. Each level refuses at its own limits. Per build: every check's value, limit and margin, ring nodes, stations, quads, time, which solve set the nose, and the reasons. The cells of the wing blocks are estimated (the count the pages use, because it can be redone): n = the largest over the stations of ceil(ln(1 + (g − 1) D / s0) / ln g) wall layers, cells = (ring nodes − 1)(stations − 1) n + cap quads × n, with g the level's wall growth (1.25 at VC to 1.107 at F), s0 the level's first wall cell at the local Re and D = 2 local chords.

| Level | Builds | Passed | Ring nodes | Stations | Cells [M], 20 reference wings × 4 Re: median (max) |
| --- | --- | --- | --- | --- | --- |
| VC (every set) | 782 | 782 | 120–220–240 | 51–63–84 | 0.70 (0.99) |
| C (reference wings) | 80 | 80 | 154–284–306 | 66–85–102 | 1.50 (2.09) |
| M (reference wings) | 80 | 80 | 198–366–396 | 82–107–130 | 3.19 (4.52) |
| F (every set) | 782 | 782 | 254–474–514 | 106–131–177 | 6.92 (9.74) |

![Ring nodes, stations and cells per level and type](page/screen_new_counts.png)

*What it shows.* The 20 reference wings × 4 Re at VC, C, M and F, per wing type: ring nodes, stations, and the cells of the wing blocks (log scale) against the 9–11 M asked for F, the desktop today and with +36 GB.

**Conclusion.** Each level has about 1.3 × the ring nodes and stations of the one below, and about 2.2 × the cells. The BWB has the most ring nodes. The ring stops growing above Re 1.5 × 10⁶, where the bubble-length floor sets the band cell.

![How close each check came to its limit, and which solve set the nose](page/screen_new_checks.png)

*What it shows.* Left: for every check, how much of the room to its limit the worst build used (1 = at the limit). Right: which solve set the nose of the stations, and the largest turning delivered per level.

**Conclusion.** No check was crossed. The one that comes close by itself is the cap quality: 0.075 at VC, 0.057 at M and 0.061 at F, against the refusal limit 0.05. What set the nose, over 167,473 stations: F's solve 150,453 (89.8 %), M's 17,020 (10.2 %). So VC turns 14.6–16.1° instead of 16.9°, and F 7.21–7.71° (angle 7.69°).

**The nose at every level (Mike's answer, 7 Nov).** The first build solved the nose at VC and at F only. M then needed one repair (nose × 0.9) on all 20 flying-wing reference builds: F's spacing × 1.3 turned those noses just past M's 10.02°. Solved at every level, against that first build: 80 of 320 reference builds changed, all of them flying-wing builds (the BWB, cranked and tapered builds are the same node for node); ring nodes changed by VC 0; C 0 to +2 (median 0); M −2 to 0 (median −2); F 0; nose repairs 20 → 0.

![The family ratios between the four levels](page/screen_new_family.png)

*What it shows.* Left: every spacing between neighbouring levels, coarser / finer, median and range over the 80 pairs of each step; red ×: the flying wings' nose cell in the first build (nose at VC and F only). Right: the counts (ring cells, station gaps, wall layers, cells), finer / coarser.

**Conclusion.** The levels are true scaled copies: the nose, trailing-edge, band and tip-gap cells refine by 1.269–1.321 per step. In the first build (nose at VC and F only) the flying wings' nose cell stepped by 1.44 (C/M) and 1.17 (M/F); solving the nose at every level fixed that. The other exceptions are whole numbers: the base cells (1.25, 1.4, 1.29) and the first station gap where the gaps per panel set it (1.25, 1.2, 1.33). The cells grow by 2.12, 2.13, 2.17 per step (median), close to 1.3³ = 2.2.

![Cells per level against the 9–11 M asked and the desktop limits](page/screen_new_cells.png)

*What it shows.* Left: cells per mesh per level (this count), median and largest, with the RAM ADflow needs (1.51 GiB + 9.46 GiB per million cells). Right: the fine level F: the first estimate (6 Nov, rule not recorded), this count, and this count with a rough +30–60 % for the C-H wake lines.

**Conclusion.** The built rules mesh every wing: 1,724 of 1,724 builds passed, 0 crashed; build time median 4.3 s at VC and 8.9 s at F. F has 6.9 M cells median (2.3–9.7 M), below the 9–11 M asked.

| Cells of the wing blocks | First estimate (6 Nov) | This count (7 Nov; the pages use it) |
| --- | --- | --- |
| Wall-layer rule | not recorded (surface × wall layers, about 1.30 × the layers per level) | n = the largest over the stations of ceil(ln(1 + (g − 1) D / s0) / ln g); D = 2 local chords; g = 1.25, 1.187, 1.141, 1.107 at VC, C, M, F; s0 from y⁺ = 1, 0.77, 0.59, 0.46 at each station's local Re |
| Wings | the first-approach reference wings, plan-file surfaces | the rebuilt reference wings (13 of 20 new), built surfaces |
| F, median | 10.9 M (15.2 M with the planned rules) | 6.9 M (2.3–9.7 M) |
| Can it be redone? | no | yes |

The pages use this count because it can be redone. The surfaces are not why the two differ (the built ones have about 17 % more stations); the wall-layer rule and the wings are. Both count the wing blocks only: with the C-H wake lines F is about 9–11 M. Stage 3 sets the real wall-layer rule. The desktop today (16 GB: about 1.2 M cells) takes all of the VC meshes; with +36 GB (about 5.0 M) it takes all at VC, all at C and all at M; F needs the HPC.

**Study 10 · The similarity check (7 Nov).** The 20 reference shapes of before similarity were built again at unit mean chord and meshed with the first rules at level C at the four Re levels: with the code of the similarity merge (the new size and trailing edge, the old nose) and with today's code (also the nose fix), against their first meshes at real size.

![Old against new reference meshes, and the Re levels against the real UAVs](page/similarity_check.png)

*What it shows.* The 80 meshes at real size against unit mean chord: ring nodes, stations (arrows: the wings that lost their switch section), the cap quality; and the four Re levels against the Re range of the real UAVs that set the Stage 1 ranges.

**Conclusion.** Size changes nothing in the ring: the same ring nodes on 80 of 80 meshes. The stations drop by 6–27 on the 8 wings that had a switch section (the extra loft station the old trailing-edge floor made); nothing else changes. The cap quality falls on 34 of 80 meshes, most 0.345 → 0.133 (BWB 1 at Re 10⁵): the old floor had made the trailing edge of small tips thicker. The lowest stays 0.112, above the limit 0.05. The nose fix on top changes the rings by −4 to 0 nodes. The four Re levels cover the real UAVs (1.22 × 10⁵ to 3.10 × 10⁶); 10⁵ is 18 % below the slowest, kept as a margin (Mike, 7 Nov).

**Study 11 · The refine map at the Re levels (7 Nov).** The refine map of study 7 in its new Re mode: the 20 new reference wings at the four Re levels on the mean chord, root angles −5° to 12°, unit mean chord, the section tables rebuilt on the fixed nose. Per strip and side: where transition sits from −5° to 8°, the band it needs, and whether the bands hold it. Details: the refine page (`docs/REFINE_MAP.html`, first section) and `decisions/refine_map_re.md`.

![Upper side: the strips whose band fits the written upper band, per type and Re](page/refine_re_coverage.png)

*What it shows.* Per type and Re level, −5° to 8°: the share of strips whose band fits inside the written upper band 0–85 % c (bars), the share whose transition itself fits (ticks), and how far the band's aft end goes past 85 % c.

**Conclusion.** The lower band (0–100 % c) holds every strip. The upper band as written (0–85 % c) misses the upper transition on most strips at 10⁵ and 3 × 10⁵ (0–49 % fit, short by up to 15 % c, to the trailing edge) and on 3–68 % at 1.5 × 10⁶ and 3 × 10⁶. As built this is no gap: the shared node list and the lower band give the upper side band-size cells to the trailing edge (0.950–0.995 × the band cell on 16 surfaces at VC). Written 0–100 % c, the mesh is the same at VC (to round-off) but has 2 more ring nodes at F on 42 of 80 reference builds (+0.39 % cells), so it stays 0–85 % c until Mike decides. Only the tailless wings lose XFOIL answers in numbers, at negative root angles (up to 46 % of the BWB strips at −5°).

## 5. What was first, and what changed with the new approach

Everything in sections 2 and studies 1–7 is first-approach evidence: it shows the mesher works. The new approach was built on 7 Nov and has its own screen (study 9).

| What | First (built 2–3 Nov) | New approach | Status |
| --- | --- | --- | --- |
| Levels | C, M, F, FF; every rule met at C, the coarsest | VC, C, M, F. Hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap); accuracy targets at M (nose 10°, trailing edge 0.1 % c, station gap, largest cell); transition targets at F (20 cells per bubble; wall growth 1.107, just above the 1.1 a transition model asks for). VC on the desktop; C, M, F on the university HPC | built 7 Nov; screened (study 9); the nose solved at every level (7 Nov); two builder choices for Mike to confirm |
| Band cell | bubble length / 20 at C | bubble length / 20 at F; the bubble length stops at 0.10 c from local Re 4 × 10⁵ (0.5 % c at F) | built 7 Nov |
| Stations, tip | gap 0.2 × chord at C; last gap = s0 | gap 0.25 × chord at M; last gap = 2 × s0; station growth 1.2 kept (+17 % stations against the plan file) | built 7 Nov |
| Lower band | 60–100 % c, for 0–8° | 0–100 % c (option A, Mike, 7 Nov); costs no cells (study 8) | built 7 Nov |
| Volume mesh | O-H body mesh + overset wake box and tip-vortex tube (ADflow only) | one matched C-H mesh for ADflow and SU2; wake lines to the far field; tip vortex in the outboard blocks | decided; Stage 3 |
| Wing size | real size; trailing edge max(0.5 / 1.0 mm, 0.2 % c) | unit mean chord (area / full span); Re an input (4 levels); Mach 0.1 + Prandtl–Glauert; trailing edge 0.2 % c; root chord out (18 → 17) | built in Stage 1 7 Nov; sets rebuilt; study 10 |
| Flow, angles, Mach | ADflow SA; 0–8°; Mach 0.03–0.20 | transition with ADflow and SU2; −5° to post-stall; toward Mach 0.5, no supersonic flow | decided; split and core Mach pending |
| Nose (64) | "the built nose is not round" | real; fixed in Stage 1 (apex leading edge, one cubic spline, 201 points per side, a nose gate) | built in Stage 1 7 Nov; study 4 |
| Fine level | no target | F 6.9 M cells median (wing blocks; this count, it can be redone), below the 9–11 M asked; the first estimate (6 Nov, rule not recorded) 10.9 M; the C-H wake lines add a rough +30–60 %; Stage 3 sets the real wall-layer rule | counted 7 Nov |

![Where each rule is met on the four levels, first against new](page/levels_first_new.png)

*What it shows.* Five rules on the four levels, first (grey) against new (blue, built 7 Nov), read from the code (`laws.py` with each config); green bars: the largest turning each level delivered in the new screen. Level names: first C, M, F, FF; new VC, C, M, F (the same four places on the ladder).

**Conclusion.** First, every target was met at the coarsest level, so the finer levels went far past it (44 cells per bubble at FF), while the cells grew about 2.2 × per level. New, each target is met where it is needed: the accuracy targets at M, as the DPW guidelines define their medium grid, and the transition target at F, where SU2 with LM will run. The coarse levels are coarser than before (16.9° per nose cell and 9.1 cells per bubble at VC): good enough for the SA mesh studies, not for transition. The wall rules do not change: y⁺ ≤ 1 and growth 1.25 at the coarsest level give 1.107 at F, just above the 1.1 a transition model asks for (1.23 at VC would give exactly 1.1).

![Cells per level and the fine level per rule set (6 Nov estimate)](page/cost_first_new.png)

*What it shows.* The estimate of 6 Nov, before the build. Left: cells per mesh at the new levels with the lighter band, median and largest over the 20 reference wings × 4 Re levels (surfaces from the plan file × wall layers by formula; the wing blocks only). Right: the fine level F per rule set.

**Conclusion.** This first estimate put F at 10.9 M cells (median), inside the 9–11 M asked; the planned rules gave 15.2 M. Its wall-layer rule was not recorded, and it used the first-approach reference wings. The pages now use the count of study 9 (F 6.9 M median), because its rule is written down and it can be redone. Both leave out the C-H wake lines (a rough +30–60 %). Stage 3 sets the real wall-layer rule.

![The volume topology, first against new](page/topology_first_new.png)

*What it shows.* Left: the first plan, O rings with an overset wake box (ADflow only). Middle: the new plan, one matched C-H mesh; the C rows wrap the nose and leave the trailing edge. Right: the new plan from above; the station lines go on behind the wing and past the tip. Schematic, not a mesh.

**Conclusion.** The surface mesh does not change: the ring is still the first row and the cap still closes the tip. The volume mesh changes (Stage 3, not built): a march from an open line at the trailing edge, wake lines to the far field, the tip vortex clustered in the outboard blocks instead of a tube, and no overlap gate. The nose must stay a spacing request inside the C block: a separate 5-point nose collar is what broke S6. The gain is one mesh family and one error bar for both solvers.

![The lower band at negative angles: the two options](page/band_negative.png)

*What it shows.* The transition band on one section: the first band, and the two options for negative angles. Option A was chosen and built.

**Conclusion.** The first band was set for 0–8°. At −5° the lower side takes the suction peak near the nose, so its transition and bubbles move forward, out of the band (median 1–15 % c per type at −5°, study 8). Option A covers them with one rule for both sides, and it costs no cells, because both sides share one node list. Mike chose A on 7 Nov.

**What stays the same.** The six steps and the code (one change: the nose is solved at every level, and the strictest spacing wins); the ring and the cap; the family rule (÷ 1.3 per level, growth g^(1/1.3)); the 13 checks; one surface per wing and Re level.

## 6. Weak points, said plainly

- **Numpy loft only.** Every mesh so far, first and new, was built on the numpy twin of the loft. The pyGeo run on Mike's machine is owed.
- **No solve yet.** Nothing here shows that the surface gives a good volume mesh or a converged run.
- **The cap quads come close to the limit:** 0.075 at VC and 0.061 at F, against 0.05 (study 9). Similarity made some caps worse (study 10).
- **The stations are 17 % more than the plan.** The decided station growth 1.2 and 12 gaps per panel at M give 7–14 more stations than the plan file's 1.25 and 7 gaps per panel, so about 17 % more cells than the plan's rules would give. If the plan file's values were meant, they need a decision.
- **The cell count is an estimate, and it hangs on the wall-layer rule.** This count: F 6.9 M (one layer count per block, 2 chords deep). The first estimate of 6 Nov: 10.9 M, its rule not recorded. Both leave out the wake lines and the outboard blocks. Stage 3 sets the real rule.
- **The coarse levels get a finer nose than they ask.** The nose is solved at every level and the strictest wins, so VC turns 14.6–16.1° against 16.9°: the price of an exact family rule.
- **The coarse levels do not resolve transition.** VC and C have 9.1 and 11.8 cells per bubble, so transition results there must not be trusted.
- **The band rule rests on one source.** 20 cells per bubble comes from one vendor guide, for one model. The lighter band gives the shortest high-Re root bubbles (about 1.5 % c) only about 3 cells: fine for SA, wrong for LM.
- **The band count (study 8) still reads the flow at real size**, per flight speed; the refine map now runs at the Re levels (study 11).
- **The upper band as written misses the upper transition at low Re** (0–49 % of the strips fit at 10⁵ and 3 × 10⁵). The built mesh has band-size cells there anyway; writing 0–100 % c would change F a little (2 more ring nodes on 42 of 80 reference builds).
- **No XFOIL answer on many tailless strips at −5°** (up to 46 % BWB, 43 % flying wing): the band there rests on the other angles.
- **Studies 1–8 used the old 20 reference shapes**, 13 of which were replaced on 7 Nov.
- **Starting values without a ladder:** the station gap, the 12 per panel, the tip gap and the 2 % c cap.

## 7. Open and to do, in order

1. ~~Nose re-measure (decision 64)~~ — done 7 Nov: real; fixed in Stage 1.
2. ~~Similarity in the generator~~ — done 7 Nov: sets rebuilt, 722 of 722.
3. ~~The lower band (74)~~ — done 7 Nov: option A, from the leading edge.
4. ~~Stage 2 code, the new rules~~ — done 7 Nov.
5. ~~New screen~~ — done 7 Nov (study 9).
6. ~~The nose at M (decision 77, point 2)~~ — done 7 Nov: solved at every level, the strictest wins.
7. ~~The refine map at the Re levels~~ — done 7 Nov (study 11): the lower band holds every strip; the upper band as written does not at low Re, but the built mesh has band-size cells there.
8. **Mike: confirm or change the two builder choices left** (decision 77): the growth limits by the family rule; the station growth 1.2; and choose the upper band (0–85 % c as now, or 0–100 % c with the screen re-run).
9. **pyGeo run (Mike's machine):** the Stage 1 tests and `build --all`, then the Stage 2 tests (41) and screen.
10. **Close Stage 2:** final page, summary and handover; notify.
11. **Stage 3:** the matched C-H volume mesh on one wing first, count its cells, then the first solves.
12. **Ladders after the first solves:** chordwise (cells per bubble, the band), spanwise (station gap, tip gap), the nose angle (12, 10, 8, 6°).
13. **Decide 65 and 66** (the per-wing band; AVL and NeuralFoil for the flow dataset) after the first 3-D transition runs, with the flow dataset per Re level at unit mean chord.

## 8. Handover to Stage 3 (the volume mesh)

- **Input per mesh:** `surface.npz` with the wing rings (ring index first, root to tip) and the cap; x/c of every node; `stations.csv` with the local Re and chord per station; `quality.json` with the tip's first cell `s0_tip_m` and every rule value with its reason. The wings are at unit mean chord; one surface per wing, level (VC, C, M, F) and Re level.
- **The march:** first cell s0 per station from the local Re and y⁺ (1 at VC, 0.46 at F); growth ≤ 1.25 at VC in the boundary layer (1.107 at F, just above the 1.1 a transition model asks for); at least 30 cells across it; reach about 2 chords; the last station gap at the tip is 2 × s0. Study 9 counted the wing blocks with this march: F 6.9 M cells median.
- **The family:** every spacing ÷ 1.3 per level and the growth g^(1/1.3), in the volume too; base cells 8, 10, 14, 18 at VC, C, M, F.
- **First plan (replaced):** overset boxes: background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, a tube with 15–20 cells across the vortex core from 2 c behind the tip, far field 80 c; the overset export and the overlap gate.
- **New plan: one matched C-H mesh for ADflow and SU2.**
  - The C block wraps the ring, and the nose stays a spacing request inside it: no collar.
  - Wake lines run from the trailing-edge corners and the base to the far field (80 c), fine near the trailing edge (0.0075 c as the starting value).
  - The stations go on past the tip into outboard blocks, growing from the tip gap. The tip vortex is resolved there by clustering cells along its path (no tube). The cap is the wall of the first outboard block.
  - Structured CGNS for ADflow; a converter to unstructured hexes (.su2) for SU2.
  - Rough cost: +30–60 % cells on the wing blocks, to be counted on the first wing.
- **Test the march first** on the tip squeeze, on the caps whose quads come closest to the limit (study 9), on the corner wings, and on the new open-line march at the trailing edge.

**Sources.** Levy et al. 2013 (DPW gridding guidelines); Celik et al. 2008 (grid convergence, r ≥ 1.3); Ansys CFX Modeling Guide, γ-Re_θ transition-model grid requirements; White, *Viscous Fluid Flow* (flat-plate friction); the AERIS Mesh Automation Primer, Annex G (the Grand Roadmap); S8 (the AERIS mesh study); AERIS ADR-0020 (ADflow memory: 1.51 GiB + 9.46 GiB per million cells). Decisions: `CFD_Automation/OPEN_DECISIONS.md` 56–77.
