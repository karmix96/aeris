# Stage_3 — Volume mesh page (text copy, 11 Nov 2026)

Text copy for chats in this project of `CFD_Automation/Stage_3_volume_mesh/docs/VOLUME_MESH.html` (repo karmix96/aeris,
branch `main`). The figures are in the HTML page and on the artifact; here each one is a *[Figure: ...]*
line with its caption. Companion files: 'Stage_3 Executive summary', 'Stage_3 Volume mesh status and handover',
'Stage_3 Mesh flowchart'. If this copy and the repository ever differ, the repository wins.

CFD_Automation · Stage 3 · volume mesh · cfdauto 0.7.0 · 11 Nov 2026

# Volume Mesh

One matched C-H mesh per wing, Re and level (VC, C, M, F), on the frozen Stage 2 surface: structured CGNS for ADflow, the same cells as `.su2` for SU2. What it is, how one is built, every check, what was measured, what is weak and what is left. Every check and limit was written before the first mesh was judged (V0) and none changed; the construction changed ten times, each after a check failed ([What changed](#changes)). The first rule set worked but cost too much (M 20.8 M, F 45 M cells). On 9 Nov Mike set the target, M about 10 M with F above it, and rule set 2 (decision 107) meets it with the volume rules alone: its results come first, the first rule set's follow as the record ([Cost](#cost) has the packages that were counted). On 10–11 Nov the size was studied ([The size](#size)): what drives it, which rules are stricter than the published guides, and a lighter ladder that is not decided yet (decision 114). Step by step from a surface to its volume mesh, with the rule, the decision and the value per level: the <a href="https://claude.ai/artifact/EWgreAJioSL4yNMwoGFUpD" target="_blank" rel="noopener">flowchart</a>.

## At a glance

### Where it stands

**Rule set 2: M about 10 M cells**

Rule set 1 worked but cost too much (M 20.8 M, F 45 M). Mike set the target on 9 Nov: M about 10 M, F may be above; and the angles: −5° to +10°. Rule set 2 (decisions 107, 111) meets it with the volume rules alone; the surface, its band and the levels are unchanged. Left: the first solves (V7), the hold-outs (V8, not yet). In main on GitHub since 10 Nov, with an app to load or make a wing and look at its meshes (`CFD_Automation/app`).

### The size, studied (11 Nov)

**M 5.5–6.4 M possible · not decided**

Today M is 9.5 M at Re 3 × 10⁵ and 13.5 M at 4 × 10⁶. Three rules are stricter than the published guides: the tip gap (36–1,100 × finer than DPW), the wall-normal growth and the station growth. Loosened together: M 5.5 and 6.4 M with the band kept, and each level becomes about as big as the level below it today. It gives up the wall-resolved tip cap and needs one solver check and Mike's word (decision 114). [The size](#size).

### Rule set 2: the screens

**80 of 80 reference · 721 of 722 all sets**

V2/V3: the 20 reference wings × 4 Re at VC. V4: the family, check 13 20 of 20. V6: every built set at VC (not the hold-outs); refused: BWB corner2 wing 6 (cell quality 0.032, limit 0.05).

### Rule set 2: the cost

**M 9.5 M · F 20.7 M**

Median on the 20 reference wings at Re 3 × 10⁵ (M 8.6–11.8 M; F 18.7–25.7 M). VC 2.08 M, about 18–21 GiB for ADflow (S8's two laws: ANK only, ANK then NK): every reference VC mesh fits the 52 GB desktop, none the 16 GB one. M: 72–92 GiB (a cluster job). Rule set 1: M 20.8 M, F 45.4 M ([Cost](#cost)).

### Solver files (V5)

**CGNS exact · .su2 checked**

The CGNS (ADF, the format Mike's CGNS 4.5.2 reads) is read back exactly by this package and by the CGNS library itself; the `.su2` has every face welded, no inside-out cell, every boundary face facing out. The V7 mesh (rule set 2): 2.32 M cells, 19–23 GiB for ADflow.

### Weak points

**no solve yet · coarser wake and tip vortex**

No solver has run on a Stage 3 mesh, so where the wake goes is not checked. Rule set 2 resolves the wake band and the tip vortex more coarsely than rule set 1, the fan ends at +10°, and the base is no longer at y⁺ 1. Very close stations with fast-changing chords sit nearest the cell-quality limit; one corner wing is refused (BWB corner2 6). The cap's two nose-corner cells are exempt (decision 101), not fixed. Planar stations: square in the plane, up to 40° off the surface normal in 3-D at swept noses (74° on the most swept corner wing). All in [Weak points](#weak).

### Rules, checks, code

**15 checks · 45 tests**

Rules in `configs/volume.yaml` (rule set 1 kept in `configs/volume_rules1.yaml`); checks and limits in `decisions/volume_rules.md`; code in `cfdauto/volume/` (Stage 2's `cfdauto/mesh/` untouched); decisions 84–114 in `OPEN_DECISIONS.md`.

## Rule set 2 (decisions 107–111): M about 10 M cells, angles −5° to +10°

Mike, 9 Nov 20:30: "make medium around 10 million; the fine family can be over this limit". Of the counted packages ([Cost](#cost)), P2 meets it with the volume rules alone (M median 11.1 M counted, with the fan to +20°), so it became rule set 2. Mike, 22:04: "I want to run from −5 to 10 AoA. You adjust the wake fan accordingly", so the fan now ends at +10° (decision 111). The surface, its band, the levels, y⁺ 1 on the wing and the far field are unchanged. The rules and their limits were written before each rebuild.

| rule (the check that reads it)                          | rule set 1: VC / C / M / F                  | rule set 2: VC / C / M / F                   |
|---------------------------------------------------------|---------------------------------------------|----------------------------------------------|
| cells across the boundary layer (check 7)               | 30 / 39 / 50.7 / 65.9                       | 17.8 / 23.1 / 30 / 39                        |
| outboard growth to 2 c past the tip (check 12)          | 1.15 / 1.114 / 1.086 / 1.066                | 1.3 / 1.224 / 1.168 / 1.127                  |
| the wake fan: freestream directions it holds (check 11) | −5° to +20°                                 | −5° to +10° (decision 111)                   |
| cells across the wake fan (check 11)                    | 23.7 / 30.8 / 40 / 52 (0.63° per cell at M) | 7.1 / 9.23 / 12 / 15.6 (1.25° per cell at M) |
| streamwise cell in the band, × the band cell (check 11) | 4                                           | 8                                            |
| first cell behind the base (check 5)                    | s0 (y⁺ 1)                                   | the wing's last chordwise cell               |

**What it costs, named before the results:** the base is no longer at y⁺ 1 (its first cell is the trailing-edge chordwise cell), but the spacing jump across the trailing-edge line is gone; the wake band has half the cells per degree of its fan (1.25° per cell at M) and streamwise cells up to 8 × its cross cell; above +10° the wake leaves the fine cells (post-stall gets its own mesh, decision 69); VC has 17.8 cells across the boundary layer; the tip vortex gets coarser spanwise cells (outboard growth 1.3).

### The wake fan: one mesh for −5° to +10°

- **One mesh serves every steady angle,** so it has no refinement per angle. Each station plane has a fixed fan of fine cells behind the trailing edge: from −5° to +10°, 0.05 c above and below at the trailing edge, 2 local chords long.
- **Why one mesh for all angles:** one mesh instead of about eight per wing and Re; the same mesh error at every angle, so the lift slope and the polar shape are clean; one family check per wing.
- **Why +10° and no more:** steady RANS serves −5° to +10° here; post-stall is a separate study with its own mesh from the same code (the two angles are inputs of the mesher). The fan to +20° cost 11–14 % of the cells; at +10° the fan costs none (the same count as no fan: top at +20° 10.5 M, +15° 9.8 M, +12° 9.3 M, +10° 9.0 M, no fan 9.0 M at M, the median of wing 0 of each type).
- **No extra angle on top of the 0.05 c:** the downwash turns the wake below the freestream direction; the cells do not jump at the fan's edge. Not measured yet: where the wake goes in a solution (V7 checks −5° and +10°).

*\[Figure: BWB reference wing 0 at VC, Re 3 × 10⁵, rule set 2. (a) One station plane: the fan (blue), its edges at −5° and +10°, its end 2 local chords behind the trailing edge; dashed: the freestream directions at −5°, 0°, 5°, 10°. (b) The trailing edge close up. (c) The cell height along the vertical line 1 local chord behind the trailing edge; red: the band cell there. (d) Top view: the fan behind every station.\]*

**Conclusion.** Every freestream direction from −5° to +10° lies inside the fan, and every cell inside it is no larger than the band cell.

### Three faults the first builds found, and their fixes (no check limit changed)

| decision | what failed                                                                                | cause                                                                                                                                        | fix (construction)                                                                                                                                                                                                                                        |
|----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 108      | check 11 on 9 of the first 13 full-space wings (band cells up to 1.07 × the band cell)     | the fan is straight from the base, the mesh's wake line falls up to 0.12 c behind a BWB centre body; the cells were sized from the wake line | the exact envelope of the straight fan around the bent line, per station                                                                                                                                                                                  |
| 109      | check 13 on 11 of 20 reference wings (ratios 1.247–1.285, limit 1.3 ± 3 %)                 | each cell took the band limit at its start, so the coarser level lagged more                                                                 | each cell takes the limit at its own centre: the band cells of two levels are 1.300 apart                                                                                                                                                                 |
| 110      | check 3 on 6 full-space BWB wings over three versions of the fix (0.024–0.050; limit 0.05) | stations 0.0001–0.05 c apart whose far nodes sat far apart (the near field is sized in local chords)                                         | the far part of each station moves toward its neighbours' average, as far as its growth limit allows, neighbours alike, with the ramp that leaves the least shear; the near part is never moved (0.052–0.093 after; BWB corner2 6 stays refused at 0.032) |

**Conclusion.** The three faults were in how the mesh is built, not in the rules; one was my incomplete fix of decision 106, and decision 110 took three versions, each found by a screen. No limit changed. The screens below were rerun with the final construction and count every wing. Very close stations with fast-changing chords stay the weakest place of the mesh.

### The results

- **V1** (BWB reference wing 0, VC, Re 3 × 10⁵): passed; 2,324,016 cells (rule set 1: 4,930,448); 62 layers, 53 wake nodes, 335 C-line nodes, 61 + 49 stations; ADflow 23.5 GiB.
- **V2/V3** (the 20 reference wings × 4 Re at VC): 80 of 80 pass; cells 1.16–3.36 M (median 2.42 M); fit 16 GB: 2, fit 52 GB: 80; cap 0.062 (the two nose-corner columns, exempt); growth ≤ 0.9964 × its limit; wake ≤ 0.9969.
- **V4** (the family, Re 3 × 10⁵): check 13 20 of 20 (worst 2.0 %: bwb 4: cell_1c_wake VC/C = 1.2734); cells, median (range): VC 2.08 M, C 4.43 M, **M 9.53 M (8.6–11.8)**, F 20.7 M (18.7–25.7); M and F built: flying_wing 0 M: 9.20 M, passed; cranked 0 M: 8.70 M, passed; tapered 0 M: 8.77 M, passed; bwb 0 M: 10.61 M, passed; bwb 0 F: 23.10 M, passed.
- **V5** (the V7 mesh, rule set 2): 2,324,016 cells; check 15 passed; CGNS 59 MB (libcgns: exact), .su2 323 MB.
- **V6** (every built set at VC, Re 3 × 10⁵, with the 20 reference wings): 721 of 722 pass; refused: BWB corner2 wing 6 (cell quality 0.032); cells 1.75–2.95 M (median 2.10 M); M counted on 94 wings: 8.2–12.8 M (median 9.6 M); F counted on 94 wings: 17.7–27.8 M (median 20.7 M).

*\[Figure: Rule set 2 as built: BWB reference wing 0 at VC, Re 3 × 10⁵, one colour per block. The station planes at the root, mid semi-span and the tip; the root's trailing edge close up (the base block in orange); the root plane out to the far field; a plane across the wake just behind the wing (dashed: the tip).\]*

**Conclusion.** One C per station, square to the wall, with the wake fan behind the trailing edge and the base block between the two wake lines; 2,324,016 cells (wing stations 1,267,440, past the tip 1,013,952, cap 42,624). In the last panel the station planes crowd at the tip: the tip gap is 2 × the first wall cell ([The size](#size)).

*\[Figure: Rule set 2, the 80 reference meshes at VC (light to dark: Re 10⁵ to 4 × 10⁶). (a) The worst cell of the CAP block. (b) The cells on the tip-vortex path at 4°, 0.5, 1 and 2 local chords behind the tip trailing edge: across the wake and along it (median and range). (c) The share of the cells in the blocks past the tip.\]*

**Conclusion.** The cap passes on all 80 (0.062–0.097; limit 0.05) and is the part nearest its limit on the BWB and flying wing. The blocks past the tip hold 41–46 % of the cells. The vortex path is fine across the wake (0.0056, 0.014, 0.029 c at 0.5, 1, 2 c) and coarse along it (0.10, 0.19, 0.37 c): enough to carry a vortex, not to resolve its core.

*\[Figure: Rule set 2. (a) Check 13: every judged spacing, coarse over fine, between neighbouring levels (green: 1.3 ± 3 %). (b) Cells per level on the 20 reference wings: VC and C built, M and F counted; the target at M; grey: what 48 GB holds for ADflow by S8's two laws.\]*

**Conclusion.** Check 13 passes on 20 of 20 families (worst 2.0 % off; 11 of 20 failed before the fix of decision 109). M is 9.5 M cells (median; 8.6–11.8 M), the target Mike set; F is 20.7 M. By S8's laws for ADflow only VC and C fit 48 GB; M needs 72–92 GiB (decision 113: V7 measures it).

*\[Figure: Rule set 2, the 80 reference meshes at VC: cells; cells across the boundary layer (limit 17.8 at VC); the in-plane wall angle; the 3-D angle (reported); the cells at the base and the TE corners; the spacing jump across the trailing edge (now about 1).\]*

**Conclusion.** All 80 reference meshes pass every check with the fan to +10° and the fixes of decisions 108–110, at 0.48 × the cells of rule set 1 (median 2.42 M; 2.08 M at Re 3 × 10⁵). The spacing jump across the trailing-edge line is gone (1.02–1.03; rule set 1: up to 537). The costs show where they were named: 18–29 cells across the boundary layer at VC, coarser cells on the tip-vortex path, station gaps up to 0.54 c 30 stations past the tip.

*\[Figure: Rule set 2, every screened mesh at VC, Re 3 × 10⁵, by wing type (the bar at the median): cells; the worst cell; the growth over its limit.\]*

**Conclusion.** 721 of 722 meshes pass; refused: BWB corner2 wing 6 (cell quality 0.032; limit 0.05). The focus set, where most runs go, passes 400 of 400. Thin margins: 3 meshes have their worst cell under 0.06 (limit 0.05). M on the 94 counted wings: 8.2–12.8 M (median 9.6 M).

**Conclusion.** Rule set 2 as it stands meets Mike's targets for the cells (M 9.5 M median) and the angles (one mesh for −5° to +10°): 80 of 80 reference meshes, 20 of 20 families and 721 of 722 screened meshes pass, after three construction faults were fixed and no limit changed. It does not make M fit 48 GB for ADflow (by S8's laws, 72–92 GiB); the first solves measure that, and where the wake goes.

## The size of the mesh: what drives it, and what can be loosened (10–11 Nov)

Mike, 10–11 Nov: how big is the domain, what makes the mesh big, and what can be loosened without losing accuracy ("for a structured mesh, pre-stall, above 10 M is too much"). Every study here is a what-if: the rules files are copied and changed, the rules themselves are not (they stay frozen). They count cells and run the mesh checks; none is a solver result. The record: `decisions/volume_rules.md`, sections 18–21.

### 1. The wing and the flow set every count

| count (the same in every station plane) | range, 702 wings | it follows                         | correlation |
|-----------------------------------------|------------------|------------------------------------|-------------|
| stations along the semi-span            | 52–84            | the semi-span in local chords      | +0.75       |
| nodes around the section                | 269–347          | the taper (tip chord / root chord) | −0.91       |
| wake nodes, base to outflow             | 46–60            | the smallest chord                 | −0.96       |
| wall-normal layers                      | 59–71            | the largest chord                  | +0.62       |
| stations past the tip                   | 48–49            | the same on every wing at one Re   | —           |

*\[Figure: (a) The cells at VC against Re, one line per reference wing (band on). (b)–(d) A count of the mesh against the wing quantity its rule uses, one marker per wing: the 702 built wings at VC, Re 3 × 10⁵.\]*

**Conclusion.** The mesh is set by the wing and the Re. Every count changes from wing to wing and follows what its rule computes it from; the counts multiplied give the cells (correlation 0.995). The aspect ratio alone hardly matters (−0.16); the chords do. Each wing has its own Re curve (× 1.72–2.40 from Re 10⁵ to 4 × 10⁶). The angle of attack is not an input: one mesh serves −5° to +10°, and the fan for it costs no cells (a fan to +20° would add 13–17 %).

### 2. Re and the transition band

*\[Figure: The cells at VC against Re, with the band (as every run has it) and without: the median of the 20 reference wings and their range.\]*

**Conclusion.** From Re 10⁵ to 4 × 10⁶ the mesh grows × 2.3 with the band and × 1.6 without it. The band costs × 1.05 at 10⁵ and × 1.46–1.50 from 3 × 10⁵ up (decision 81 keeps it on for every run).

| median at VC, 20 reference wings | Re 10⁵ | Re 3 × 10⁵ | Re 10⁶ | Re 4 × 10⁶ |
|----------------------------------|--------|------------|--------|------------|
| cells, band on                   | 1.33 M | 2.08 M     | 2.53 M | 3.03 M     |
| cells, band off                  | 1.27 M | 1.43 M     | 1.69 M | 2.03 M     |
| nodes around the section         | 219    | 306        | 314    | 314        |
| wall-normal layers               | 58     | 60         | 65     | 71         |
| stations along the semi-span     | 56     | 61.5       | 68     | 75         |
| stations past the tip            | 45     | 48.5       | 53     | 58         |
| wake nodes                       | 48     | 48         | 48     | 48         |

**Conclusion.** Three counts grow with Re: the nodes around (the band switches on), the layers (a thinner first cell) and the stations, along the wing and past the tip. The stations grow only because the tip gap is 2 × the first wall cell, which shrinks with Re.

### 3. The domain: what a smaller far field saves

*\[Figure: The cells at M for five far-field sizes (ahead / behind the wing, in mean chords): the median of the 20 reference wings and their range, Re 3 × 10⁵. Today is 80 / 80. The VC meshes were also built and checked.\]*

**Conclusion.** The domain costs few cells, because the cells grow by up to 1.3 per cell away from the wing (10 / 20: −25 %; 20 / 40: −17 %; 40 / 40: −10 %; 40 / 80: −8 %). At 10 / 20 14 of 20 VC meshes are refused (growth, wake). What a smaller domain costs in lift and drag is not measured: Stage 4's far-field study (40 / 80 / 160) does that. Keep 80.

### 4. The general rules, one loosened at a time

*\[Figure: One bar per rule: the change in cells at M when only that rule is loosened (the median of wing 0 of each type, Re 3 × 10⁵; today 9.07 M). Hatched: a mesh fails a check, named beside the rule. Checked: the 20 reference surfaces at VC, 4 at M, and 4 volume builds at VC per rule.\]*

**Conclusion.** Three rules make most of the size: the tip gap (2 × the first wall cell), the band and the cells per bubble, 25–34 % each. The growth rates and the far field are worth 5–11 % each. Eight rules cost nothing, and a ninth only on the BWB: another rule sets their count. The tip cap is the weak place: the band off, a coarser trailing-edge cell or a faster growth around the section can push it below its limit.

| rule, loosened alone                                                                                                                                                                                                                                                                                                                   | cells at M               | checks                                                                                 |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------|----------------------------------------------------------------------------------------|
| tip gap 100 x s0 (not 2)                                                                                                                                                                                                                                                                                                               | −34 %                    | all pass                                                                               |
| transition band off                                                                                                                                                                                                                                                                                                                    | −31 %                    | **fails:** the tip-cap cells (BWB 0) at M                                              |
| band: 10 cells per bubble at F (not 20)                                                                                                                                                                                                                                                                                                | −25 %                    | all pass                                                                               |
| tip gap 20 x s0 (not 2)                                                                                                                                                                                                                                                                                                                | −20 %                    | all pass                                                                               |
| far field 40 mean chords (not 80)                                                                                                                                                                                                                                                                                                      | −11 %                    | all pass                                                                               |
| wall-normal growth 1.30 at VC (not 1.25)                                                                                                                                                                                                                                                                                               | −10 %                    | all pass                                                                               |
| far growth built 1.28 at VC (not 1.22)                                                                                                                                                                                                                                                                                                 | −6 %                     | **fails:** the wake growth (a VC build)                                                |
| station growth 1.25 at VC (not 1.20)                                                                                                                                                                                                                                                                                                   | −6 %                     | all pass                                                                               |
| trailing-edge cell 0.2 % c at M (not 0.1 %)                                                                                                                                                                                                                                                                                            | −4 %                     | **fails:** the tip-cap cells (BWB 0) at M                                              |
| 8 station gaps per panel at M (not 12)                                                                                                                                                                                                                                                                                                 | −4 %                     | **fails:** the station growth (BWB 3) at VC                                            |
| chordwise growth 1.25 at VC (not 1.20)                                                                                                                                                                                                                                                                                                 | −2 %                     | passes at Re 3 × 10⁵; at 10⁵ the tip cap fails on the BWB and flying wings (package A) |
| nose turning 13 deg at M (not 10)                                                                                                                                                                                                                                                                                                      | −1 %                     | all pass                                                                               |
| 20 cells across the boundary layer at M (not 30)                                                                                                                                                                                                                                                                                       | 0 % (the BWB only: −4 %) | all pass                                                                               |
| largest chordwise cell 3 % c at M (not 2 %); station gap 0.35 local c at M (not 0.25); wall fine zone 1 local chord (not 2); wake band cell 1.5 % c at M (not 0.75 %); 8 cells across the wake fan at M (not 12); wake band cell aspect up to 16 (not 8); outboard fine zone 1 mean chord (not 2); wake fan 1 local chord long (not 2) | 0 % each                 | all pass: another rule sets that count                                                 |

Against the published guides (DPW-4 and HiLiftPW-1 gridding guidelines, DLR's DPW-4 grids, the Ansys CFX guide for the transition model):

| rule                       | ours: VC / C / M / F                                                                                  | the guides (their medium grid unless said)                                                                                                                                                | ours is                                                                 |
|----------------------------|-------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| first cell                 | y⁺ 1 / 0.77 / 0.59 / 0.46                                                                             | DPW-4, HiLiftPW-1: y⁺ 1 / 2⁄3 / 4⁄9 (coarse / medium / fine)                                                                                                                              | the same                                                                |
| wall-normal growth         | 1.25 / 1.19 / 1.14 / 1.11                                                                             | DPW-4, HiLiftPW-1: below 1.25 on every grid; DLR's DPW-4 family: 1.30 / 1.20 / 1.135; Ansys CFX (transition model): 1.05 and 1.1 no effect, 1.2 and 1.4 move transition a little upstream | about one level stricter than DPW, so that F meets the transition guide |
| leading and trailing edge  | LE 0.04–0.26 % local c at M (median 0.06 %, from the 10° turning); TE 0.1 % local c at M              | DPW-4: about 0.1 % local chord at both                                                                                                                                                    | finer at the LE on most wings; the same at the TE                       |
| blunt trailing edge        | 8 / 10 / 14 / 18 cells                                                                                | DPW-4: at least 12 (medium), 16 (fine)                                                                                                                                                    | the same                                                                |
| **station gap at the tip** | 2 × s0: 0.0028 % of the semi-span at Re 10⁵, 0.0011 % at 3 × 10⁵, 0.00009 % at 4 × 10⁶ (medians at M) | DPW-4, HiLiftPW-1: about 0.1 % of the local semi-span                                                                                                                                     | **36–1,100 × finer**                                                    |
| far field                  | 80 mean chords + the wing                                                                             | DPW-4, HiLiftPW-1: about 100 reference chords                                                                                                                                             | a little closer                                                         |
| cells per bubble           | 9.1 / 11.8 / 15.4 / 20                                                                                | Ansys CFX: at least 20 nodes over the bubble                                                                                                                                              | meets it at F only                                                      |
| the medium mesh            | M 9.1–13.5 M cells for a wing alone                                                                   | DPW-4: about 8 M (CRM wing-body), 10 M (wing-body-tail)                                                                                                                                   | as big as a whole aircraft's                                            |

**Conclusion.** One rule is far stricter than the guides: the station gap at the tip. Ours is 2 × the first wall cell, because the tip cap is a wall reached along the stations (the blocks past the tip), so its first wall cell sets the gap; in DPW's meshes the tip has its own wall layers. The wall-normal growth is one level stricter than DPW. The cells per bubble, the trailing edge, the first cell and the far field sit at the guides or below them: not to loosen.

### 5. The loosened rules together

*\[Figure: The cells at M of wing 0 of each type (median) at Re 3 × 10⁵ and 4 × 10⁶: today, and with rules loosened together. The dashed line is 10 M. Hatched: a check fails.\]*

**Conclusion.** Today M is 9.1 M at Re 3 × 10⁵ but 13.5 M at 4 × 10⁶. Two growth rates and the tip gap at DPW's value bring it to 5.1 and 6.2 M with the band kept and every check of that run passing (but see the negative finding below), and the stations stop growing with Re. Without the band it would be 3.5–4.0 M, but the BWB tip cap fails at M.

| rules                                                     | M at Re 3 × 10⁵ | M at Re 4 × 10⁶  | checks (every counted surface; 8 volume builds at VC) |
|-----------------------------------------------------------|-----------------|------------------|-------------------------------------------------------|
| today (rule set 2)                                        | 9.07 M          | 13.48 M          | all pass                                              |
| A2: wall-normal growth 1.30 and station growth 1.25 at VC | 7.67 M (× 0.85) | 11.20 M (× 0.83) | all pass                                              |
| A2 + tip gap 100 × s0                                     | 5.11 M (× 0.57) | 8.12 M (× 0.60)  | all pass                                              |
| **A2 + tip gap 0.1 % of the semi-span at M (DPW)**        | 5.07 M (× 0.56) | 6.17 M (× 0.46)  | all pass                                              |
| A2 + DPW tip gap + band off (fully turbulent runs only)   | 3.47 M (× 0.38) | 4.02 M (× 0.30)  | **fails:** the BWB tip cap at M                       |

**Negative finding.** Found later the same day, when all 20 reference wings were built at VC (part 6): with the wall-normal growth at 1.30 and the other two changes, BWB reference wing 3 is refused by the growth check (1.0105 × its limit; 1.01 is allowed). Each change alone and each pair pass. At 1.30 the wall growth equals the far limit, so nothing is left for the far-field blend. With 1.28 the mesh passes (0.992) and has 2 % more cells: part 6 uses 1.28.

The tip gap at DPW's value is 13–2,204 × the first wall cell, so the cap's first cell sits at about y⁺ 50–800 at M: the cap is then no longer a wall-resolved wall. It is a small part of the wall, but what that does to lift, drag and the tip vortex needs one solver check (the same wing with both tip gaps). The way without that cost is a tip wrapped by the wall-normal lines (an O-type cap): a large change to Stages 2 and 3.

### 6. The ladder: today, lighter, and one more coarse level

Mike, 11 Nov: change only the too-strict things, or make today's M the new F, and "start from 800k". The lighter rules here: wall-normal growth 1.28 at VC (1.21, 1.16, 1.12 at C, M, F), station growth 1.25 at VC, the tip gap at DPW's 0.1 % of the semi-span at M. Counted on the 20 reference wings at Re 3 × 10⁵ and on wing 0 of each type at 4 × 10⁶, with five levels: VVC is one step (1.3) under VC, every anchor left where it is, so VVC is past the hard minimums (y⁺ 1.3).

*\[Figure: Cells per level (log scale) at Re 3 × 10⁵ and 4 × 10⁶, the median of wing 0 of each type: today's rules (grey, dashed) and the three too-strict rules loosened (blue). Open markers: VVC, past the hard minimums. The dashed red line is 10 M.\]*

**Conclusion.** With the three too-strict rules loosened every level is about as big as the level below it is today: the new F (12.0–13.9 M) is today's M (9.53–13.5 M), the new M (5.53–6.41 M) is today's C, and VC starts at 1.25–1.46 M. No accuracy target moves: M keeps DPW's medium values and F the transition guide's. Renaming today's levels one step down would give the same sizes with every level one step coarser on the wing. What the lighter rules give up is the wall-resolved tip cap. Not decided (decision 114); not a solver result.

| level                            | today, Re 3 × 10⁵ (the 20 reference wings: median, range) | today, Re 4 × 10⁶ | lighter rules, Re 3 × 10⁵ | lighter rules, Re 4 × 10⁶ | lighter rules: ADflow RAM (S8's ANK-only law) and where it fits |
|----------------------------------|-----------------------------------------------------------|-------------------|---------------------------|---------------------------|-----------------------------------------------------------------|
| **VVC** (new: one step under VC) | 0.98 M (0.89–1.21)                                        | 1.38 M            | **0.58 M** (0.52–0.75)    | **0.67 M**                | 7–8 GiB: 16 GB desktop                                          |
| **VC**                           | 2.08 M (1.87–2.58)                                        | 2.97 M            | **1.25 M** (1.14–1.60)    | **1.46 M**                | 12–13 GiB: 16 GB desktop at Re 3 × 10⁵, 48 GB at 4 × 10⁶        |
| **C**                            | 4.46 M (4.04–5.54)                                        | 6.31 M            | **2.63 M** (2.38–3.37)    | **3.04 M**                | 22–25 GiB: 48 GB                                                |
| **M**                            | 9.53 M (8.56–11.8)                                        | 13.5 M            | **5.53 M** (4.99–7.12)    | **6.41 M**                | 43–49 GiB: 48 GB at Re 3 × 10⁵, HPC at 4 × 10⁶                  |
| **F**                            | 20.7 M (18.7–25.7)                                        | 29.4 M            | **12.0 M** (10.8–15.6)    | **13.9 M**                | 90–103 GiB: HPC                                                 |

The same cells, spent differently:

| about this many cells | today's rules give                                                   | the lighter rules give                                                        |
|-----------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------|
| 1.25–1.46 M           | VVC: y⁺ 1.3, nose 22° per cell, TE cell 0.22 % c, 7 cells per bubble | **VC**: y⁺ 1, nose 16.9°, TE cell 0.17 % c, 9.1 cells per bubble              |
| 2.63–3.04 M           | VC: y⁺ 1, nose 16.9°, TE 0.17 % c, 9.1 per bubble                    | **C**: y⁺ 0.77, nose 13°, TE 0.13 % c, 11.8 per bubble                        |
| 5.53–6.41 M           | C: y⁺ 0.77, nose 13°, TE 0.13 % c, 11.8 per bubble                   | **M**: y⁺ 0.59, nose 10°, TE 0.10 % c, 15.4 per bubble (DPW's medium values)  |
| 12.0–13.9 M           | M: y⁺ 0.59, nose 10°, TE 0.10 % c, 15.4 per bubble                   | **F**: y⁺ 0.46, nose 7.7°, TE 0.077 % c, 20 per bubble (the transition guide) |

- **Checks:** every one of the 360 counted surfaces passes its checks; the volume was built at VVC and VC (both rule sets) and at C (lighter rules): all 180 builds pass.
- **Built as a family** (BWB reference wing 0, Re 3 × 10⁵, the lighter rules): VVC 0.70 M, passed; VC 1.48 M, passed; C 3.11 M, passed; M 6.62 M, passed. Check 13 (every spacing 1.3 between neighbouring levels, within 3 %): passes, worst 2.0 % (the band cell, VVC / VC 1.275).
- **Counted, not built, at M and F** (and at C with today's rules): the count can run one layer high (today's built C median is 4.43 M against 4.46 M counted).
- **Which level is the production mesh** is not a naming choice: Stage 4's grid study gives the error of each level, and the coarsest level inside the Stage 0 error budget is the one to run.

**Open.** Proposed, not decided (decision 114): a rule set 3 with the three too-strict rules loosened (the tip gap needs a new Stage 2 law, so Mike's word and a re-screen), checked by one solver run on both meshes before it is frozen. Until then rule set 2 stands.

## Rule set 1: the first build (V0–V7, the record)

Everything below was built and measured with rule set 1 (`configs/volume_rules1.yaml`). It works and passes its checks, but costs about twice what Mike asked for at M; its numbers stay here as the record and as the baseline of the cost study.

## What Stage 3 is

- **In:** the Stage 2 surface of one wing at one Re and level (the ring at every station, the base, the tip cap). **Out:** one matched multiblock volume mesh, 13 blocks, every wall node the Stage 2 node.
- **Each station plane** (y = const) holds a C around the ring and the wake, out to the far field: six blocks (upper wake, upper side, nose, lower side, lower wake, base). The planes are stacked root to tip; past the tip the tip plane is swept out to 80 c, and the tip cap with it (the CAP block).
- **One mesh for both solvers** (decision 73): ADflow reads it as structured CGNS; SU2 reads the same cells as unstructured hexahedra.
- **Three outcomes:** passed, refused (only `refusal.json` is written), needs review (every check passed, but the plane needed more smoothing). Failures stay in every count.

*\[Figure: The 13 blocks by name, on BWB reference wing 0 at VC, Re 3 × 10⁵ (rule set 2). (a) One station plane, the root: six blocks around the section. (b) The same plane out to the far field. (c) From above: every line is one station plane; the wing-station blocks (\*\_in) run root to tip, the outboard blocks (\*\_out) from the tip to the far field, and the CAP block sits on the tip cap.\]*

**Conclusion.** Six blocks per station plane, twice (along the wing, past the tip), plus the cap block: 13. The station planes crowd at the tip, where the gap is 2 × the first wall cell: the place the size study found too strict.

*\[Figure: Rule set 1 (the first build). BWB reference wing 0 at VC, Re 3 × 10⁵: the station planes at the root, mid semi-span and the tip; the root's trailing edge close up; the root plane out to the far field; the wake in the y–z plane behind the wing.\]*

**Conclusion.** One C per station, square to the wall, the wake band behind the trailing edge, the base block between the two wake lines, the outboard planes past the tip. 4,930,448 cells; every check passes (V1).

## How a station plane is built

1.  **The C line:** the upper wake line, the Stage 2 ring from the upper to the lower trailing-edge corner, the lower wake line. The wake leaves the base along its normal and turns to +x over 0.5 local chord; the two wake lines are parallel, the base height apart.
2.  **The line shapes:** one front moved the same distance everywhere from the C line, smoothed along itself over its distance from the wall (κ = 1: no smoothing at the wall, so the lines leave square to it), out to 2 local chords; then straight to far-field nodes that every station shares.
3.  **The nodes:** one wall-normal distribution per station: first cell s0, the level's cells across the boundary layer (30 at M), the wall growth out to 2 local chords, the wake band as an envelope in height (the exact envelope of the straight fan, whatever the wake line does; each cell takes the limit at its centre), then the far growth. Every station gets the same count: its growth (never the band cell) is scaled down to fit.
4.  **Far out,** every station's far layers and far wake nodes first move toward the average of its neighbours within about 0.25 c along the semi-span (as far as the growth limit allows, neighbours alike), then toward the mean of all stations, so neighbouring planes line up and the cells between them stay square. The near field (fine zone and band) is never moved.
5.  **The base block** fills the space between the two wake lines.
6.  **If a cell folds,** every station is rebuilt with more smoothing (κ = 1.5, 2, 3); a mesh that needed it is "needs review". No mesh built so far needed it.

## The rules, per level

Each rule is met at its anchor level; every spacing is ÷ 1.3 per finer level, every growth g^(1/1.3), every count × 1.3; distances stay. Read from `configs/volume.yaml`.

| rule                                                  | VC         | C             | M             | F             |
|-------------------------------------------------------|------------|---------------|---------------|---------------|
| y⁺ of the first cell (law 13)                         | 1          | 0.769         | 0.592         | 0.455         |
| wall growth, boundary layer and fine zone (2 local c) | 1.25       | 1.187         | 1.141         | 1.107         |
| cells across the boundary layer (at least)            | 17.8       | 23.1          | 30            | 39            |
| far growth: checked / built                           | 1.3 / 1.22 | 1.224 / 1.165 | 1.168 / 1.125 | 1.127 / 1.095 |
| wake band cell at the TE \[% c\]                      | 1.27       | 0.975         | 0.75          | 0.577         |
| cells across the −5° to +10° fan                      | 7.1        | 9.23          | 12            | 15.6          |
| outboard growth to 2 c past the tip                   | 1.3        | 1.224         | 1.168         | 1.127         |
| base cells (Stage 2)                                  | 8          | 10            | 14            | 18            |
| far field                                             | 80 c       | 80 c          | 80 c          | 80 c          |

## The checks and their limits

Written in V0, before any mesh was judged, and approved by Mike. A refusing check that fails refuses the mesh.

| \#  | check                           | what is measured                                                                                                                             | limit                       |
|-----|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------|
| 1   | Wall on the surface             | every wall node is the Stage 2 node (wing, base, cap)                                                                                        | ≤ 1e−12 c                   |
| 2   | No folded cell                  | the Jacobian at every corner of every cell                                                                                                   | \> 0                        |
| 3   | Cell quality                    | the smallest corner scaled Jacobian of every cell but the cap's two nose-corner columns (reported on their own, as in Stage 2: decision 101) | ≥ 0.05                      |
| 4   | Wall orthogonality              | in the station plane, the first line against the wall normal (but the 2 TE corners)                                                          | ≤ 5°                        |
| 5   | First cell                      | the first cell of every wing and base line against the station's s0                                                                          | within 1 %                  |
| 6   | Growth                          | along every wall-normal line, against the wall limit in the fine zone and the far limit beyond                                               | ≤ limit × 1.01              |
| 7   | Cells across the boundary layer | turbulent flat plate at the TE, local Re                                                                                                     | ≥ 30 at VC (39, 50.7, 65.9) |
| 8   | Interfaces                      | every matched pair of faces, node to node; no open face                                                                                      | ≤ 1e−10 c                   |
| 9   | Symmetry plane                  | y on every root face                                                                                                                         | ≤ 1e−12 c                   |
| 10  | Far field                       | from every far-field node to the nearest wall node                                                                                           | ≥ 80 c                      |
| 11  | Wake                            | streamwise growth along the wake; every cell in the band against the band cell                                                               | ≤ limit × 1.01              |
| 12  | Outboard                        | first gap past the tip = the tip gap; the growth                                                                                             | 1 %; × 1.01                 |
| 13  | Family                          | s0 per station, wall growth, band cell, first outboard gap, first wake cell, the cells 1 local c from the root's wall and behind its TE      | 1.3 within 3 %              |
| 14  | Cells and RAM                   | RAM = 1.51 + 9.46 GiB per M cells (ADflow, S8's law for ANK then NK; ANK only, as run here: 2.69 + 7.23; decision 112)                       | information                 |
| 15  | Export round trip               | CGNS read back exactly (own reader, CGNS library); .su2 counts, welds, no inside-out cell                                                    | exact; equal                |

## V0: the plane method and the boundary-layer law (measured before V1)

| method                        | planes with a fold | smallest scaled Jacobian (median) | wall angle | growth / limit | time  |
|-------------------------------|--------------------|-----------------------------------|------------|----------------|-------|
| march (chosen)                | 0 of 501           | 0.626 (0.927)                     | 0.05°      | 0.997          | 6.6 s |
| algebraic                     | 501 of 501         | folded                            | —          | —              | 5.8 s |
| elliptic (300 Winslow sweeps) | 501 of 501         | folded                            | —          | 15.4           | 231 s |

*\[Figure: The three ways to build a station plane, on the same 501 station planes of 8 wings at VC (V0), one dot per plane. Left: the smallest scaled Jacobian of the plane (below 0 is a folded cell; dashed: the limit 0.05). Right: the largest angle between the first line and the wall normal (dashed: the limit 5°).\]*

**Conclusion.** The march folds no plane; the other two fold every plane, at the concave trailing-edge corners. Not close, so Mike was not asked (decision 84).

Layers at VC, median (largest) over the 20 reference wings, for five boundary-layer laws:

| law                                     | Re 1e5                  | Re 3e5        | Re 1e6        | Re 4e6        |
|-----------------------------------------|-------------------------|---------------|---------------|---------------|
| turbulent, at the TE, 30 at VC (chosen) | 88.9 (92.3)             | 89.3 (93.3)   | 89.8 (94.2)   | 90.7 (97.2)   |
| turbulent, mid-chord, 30 at VC          | 93.3 (96.4) infeasible  | 92.9 (97.1)   | 93.0 (97.2)   | 93.3 (98.1)   |
| laminar, mid-chord, 30 at VC            | 99.7 (104.2) infeasible | 100.7 (105.3) | 102.2 (107.2) | 104.2 (109.2) |
| turbulent, at the TE, 30 at M           | 75.2 (81.7)             | 79.8 (86.2)   | 84.8 (91.2)   | 90.7 (97.2)   |
| laminar, mid-chord, 30 at M             | 82.8 (87.3)             | 84.3 (89.3)   | 86.2 (91.2)   | 90.7 (97.2)   |

**Conclusion.** The turbulent layer at the trailing edge always fits 30 cells at VC; the mid-chord layers do not at Re 10⁵ (the small tips would need growth 1.000). Chosen: turbulent at the TE, 30 at VC (decision 86). Weak point: a laminar layer at mid-chord gets fewer cells at VC; the family gives it more at F.

## V1: BWB reference wing 0, VC, Re 3 × 10⁵

- Every check passes. 4,930,448 cells: inboard 2,178,240, outboard 2,686,496, cap 65,712; the wake blocks hold 1,936,836.
- Counts: 95 layers, 74 wake nodes, 377 C-line nodes, 61 stations, 75 outboard stations.
- Against Stage 2's estimate (649,644 cells, 43 wall layers, the wing blocks only): 7.59 ×. The difference: 94 layers, not 43 (the boundary layer, the band, the far field), the wake blocks and the outboard blocks.
- ADflow RAM by the law: 48.2 GiB: not the 16 GB desktop; the 52 GB one.

**Conclusion.** The matched C-H mesh works on the reference BWB: 13 blocks, every face either a boundary or matched node to node, every check met. Its cost is 7.5 × what Stage 2 estimated.

## V2: wall layers, fine zone and far field: 20 reference wings × 4 Re at VC

*\[Figure: One dot per mesh (80): by wing type, light to dark from Re 10⁵ to 4 × 10⁶. (a) cells; (b) cells across the boundary layer at the worst station; (c) the largest angle between the first line and the wall normal in the station plane; (d) the 95th percentile of the 3-D angle to the surface normal (reported, not judged); (e) the worst cell next to the base and the trailing-edge corners; (f) the wing's last chordwise cell over the first cell behind the base.\]*

**Conclusion.** 80 of 80 pass. The wall rules hold on every wing at every Re: 30.39–32.69 (median 30.72) cells across the boundary layer (≥ 30), first cells within 0.028 %, growth ≤ 0.9960 × its limit, the far field at 80 c, in-plane angle ≤ 0.18° (nose 0.18°, off the base 0.0095°). The cells at the base and the trailing-edge corners are good (0.57–1.00 at the base). Weak: the 3-D angle reaches 40° at swept noses (planar stations, decision 89), and the spacing jump across the trailing-edge line reaches 537 at Re 4 × 10⁶ (the base is a wall at y⁺ 1, decision 90).

| what                                               | measured (80 meshes)                                           | limit       |
|----------------------------------------------------|----------------------------------------------------------------|-------------|
| cells                                              | 2.71–6.87 (median 5.02) M                                      | —           |
| ... by Re                                          | 1e5: 2.7–3.7 M; 3e5: 4.1–5.1 M; 1e6: 4.9–5.9 M; 4e6: 5.7–6.9 M | —           |
| ADflow RAM                                         | 27–67 (median 49) GiB; fit 16 GB: 0, 52 GB: 40                 | information |
| layers · wake nodes · stations · outboard stations | 91–100 · 66–86 · 51–82 · 67–92                                 | —           |
| cells across the boundary layer                    | 30.39–32.69 (median 30.72)                                     | ≥ 30        |
| growth / limit                                     | 0.9915–0.9960 (median 0.9936)                                  | ≤ 1.01      |
| wall angle in the plane                            | 8.72e-05–0.181 (median 0.000676)°                              | ≤ 5°        |
| the two TE corners (not judged)                    | 2.7–8.8 (median 6.2)°                                          | reported    |
| 3-D angle to the surface normal, largest           | 6–40 (median 18)°                                              | reported    |
| TE spacing jump                                    | 1e5: 10–17; 3e5: 26–48; 1e6: 81–148; 4e6: 293–537              | reported    |

## V3: the cap, the outboard blocks and the tip vortex

*\[Figure: (a) the worst cell of the CAP block per mesh; (b) the cells on the tip-vortex path at 4°, 0.5, 1 and 2 local chords behind the tip trailing edge (median and range over the 80 meshes), across the wake and along it; (c) the share of the cells in the outboard blocks.\]*

**Conclusion.** The cap and the outboard blocks pass on all 80. The cap's cells are the worst of every mesh (0.062–0.097): they are the Stage 2 cap quads swept outboard, so a better cap belongs to the frozen surface. The outboard blocks are good (0.77–0.97) but hold 51–56 % of the cells: in a matched mesh every outboard station carries the whole plane. The vortex path is fine across the wake (median 0.0037, 0.011, 0.017 c at 0.5, 1, 2 c) and coarse along it (0.08, 0.12, 0.24 c; the band allows 4 × the cross cell). Enough to carry a vortex, not to resolve its core; at 20° and 2 c the cross cell is 0.08 c (the band's edge). A solve must show whether that is enough (V7).

## V4: the family VC, C, M, F (20 reference wings, Re 3 × 10⁵)

*\[Figure: (a) check 13: every judged spacing, coarse over fine, between neighbouring levels: one dot per wing for VC/C; diamonds for C/M and M/F where M and F were built; the green band is 1.3 ± 3 %. (b) cells per level for the 20 reference wings: VC and C built, M and F counted, against the 16 GB and 52 GB desktops and the 9–11 M asked for at F.\]*

**Conclusion.** Check 13 passes on 20 of 20 families at VC/C (worst 2.3 %: bwb 2: cell_1c_wall VC/C = 1.2696) and on BWB reference wing 0 from VC to F: the family is a true 1.3-scaled copy, after two construction changes found by this check (changes 7 and 8). Honest negatives. (1) At M and F the CAP block's two columns over the cap's nose-corner quads fall below 0.05 on the BWB and flying wing (0.045 and 0.037 on BWB 0); Stage 2 exempts exactly these quads (three corners on the smooth ring), every other cell is ≥ 0.077, and Mike decided the same exemption for check 3 (decision 101): then every M and F mesh built passes. (2) The cost: F is 45.35 M median, 50.71 M largest, against 9–11 M asked (decision 102: Mike to think it over). Built here: bwb 0 M: 22,691,330 cells, passed, 46 s, 2.2 GiB peak; flying_wing 0 M: 20,432,678 cells, passed, 70 s, 1.1 GiB peak; cranked 0 M: 19,128,524 cells, passed, 47 s, 1.1 GiB peak; tapered 0 M: 19,406,008 cells, passed, 81 s, 1.1 GiB peak; bwb 0 F: 49,093,520 cells, passed, 110 s, 2.2 GiB peak.

| judged spacing                      | VC / C (20 wings) | C / M, M / F                           |
|-------------------------------------|-------------------|----------------------------------------|
| s0 per station                      | 1.3000–1.3001     | C/M: 1.3000–1.3000; M/F: 1.3000–1.3000 |
| wall growth (ln g)                  | 1.3000–1.3000     | C/M: 1.3000–1.3000; M/F: 1.3000–1.3000 |
| band cell                           | 1.2923–1.2924     | C/M: 1.2941–1.2941; M/F: 1.2954–1.2954 |
| first outboard gap                  | 1.2758–1.3137     | C/M: 1.3010–1.3090; M/F: 1.2861–1.2861 |
| first wake cell                     | 1.3000–1.3000     | C/M: 1.3000–1.3000; M/F: 1.3000–1.3000 |
| cell 1 local c from the root's wall | 1.2696–1.2959     | C/M: 1.2794–1.2933; M/F: 1.2834–1.2834 |
| cell 1 local c behind the root's TE | 1.2890–1.2890     | C/M: 1.2914–1.2914; M/F: 1.2934–1.2934 |
| count: n_layers                     | 1.283–1.295       | named exception (whole numbers)        |
| count: n_wake                       | 1.270–1.300       | named exception (whole numbers)        |
| count: n_out                        | 1.280–1.297       | named exception (whole numbers)        |
| count: n_c                          | 1.281–1.296       | named exception (whole numbers)        |
| count: cells                        | 2.112–2.162       | named exception (whole numbers)        |

| level | cells, median | largest | ADflow RAM, median | here    |
|-------|---------------|---------|--------------------|---------|
| VC    | 4.55 M        | 5.12 M  | 45 GiB             | built   |
| C     | 9.73 M        | 10.97 M | 94 GiB             | built   |
| M     | 20.79 M       | 23.48 M | 198 GiB            | counted |
| F     | 45.35 M       | 50.71 M | 431 GiB            | counted |

## V5: the solver files

- **CGNS for ADflow:** written by `cfdauto/volume/cgns.py` in pure Python, in ADF (version A02011). Mike's CGNS 4.5.2 was built without HDF5 and reads only ADF (S8). 13 structured zones, coordinates in double precision, one BC per boundary face (BCWallViscous, BCFarfield, BCSymmetryPlane, each with its family), 1-to-1 connectivity on both sides with its transform.
- **Read back** on BWB reference wing 0, VC (4,930,448 cells, 124 MB): by this package, every coordinate exact and every match node for node (44 1-to-1 records); by the CGNS library itself (the copy VTK ships, CGNS with ADF, 64-bit sizes): exact, no problem.
- **.su2 for SU2:** `cfdauto/volume/su2.py`: the blocks as hexahedra, nodes welded along every matched face by the topology, markers `wall`, `symmetry`, `farfield`. Read back: 5,013,600 points, 4,930,448 hexahedra, {'wall': 15168, 'symmetry': 36304, 'farfield': 114108}; no two points closer than 1e−12 c, no inside-out hexahedron, every boundary quad faces out (694 MB).
- Check 15 runs every time a mesh is written with its solver files; tests cover a two-block box with a transposed, reversed match and the VC mesh.

**Conclusion.** ADflow and SU2 get the mesh that was checked, node for node. Not yet shown: that ADflow and SU2 accept it and converge (V7).

## V6: the built sets at VC, stopped at 427 of 702 wings (decision 105)

Started on the 702 built wings outside the reference set (VC, Re 3 × 10⁵). Stopped on 9 Nov at 20:09 when Mike decided the cells must drop (the rules will change): all 400 of the focus set, 24 full-space BWB and 3 full-space cranked wings were done; with the 20 reference wings, 447 meshes.

*\[Figure: Every screened mesh at VC, Re 3 × 10⁵, by wing type, the bar at the median: (a) cells; (b) the worst cell of the mesh; (c) the largest growth over its limit.\]*

**Conclusion.** 426 of 447 pass as screened; with decision 101 (it came while the screen ran) 427 pass and 20 are refused, all by the wake check on full-space wings. The focus set, where most runs go, passes 400 of 400. F counted on 63 wings: 39.1–51.1 (median 44.3) M cells.

| set            | BWB                           | flying wing            | cranked                     | tapered                |
|----------------|-------------------------------|------------------------|-----------------------------|------------------------|
| reference      | 5 pass (5 of 5)               | 5 pass (5 of 5)        | 5 pass (5 of 5)             | 5 pass (5 of 5)        |
| training_focus | 100 pass (100 of 100)         | 100 pass (100 of 100)  | 100 pass (100 of 100)       | 100 pass (100 of 100)  |
| training_full  | 5 pass, 19 refused (24 of 40) | not screened (0 of 40) | 1 pass, 2 refused (3 of 40) | not screened (0 of 40) |
| corner1        | not screened (0 of 32)        | not screened (0 of 24) | not screened (0 of 32)      | not screened (0 of 24) |
| corner2        | not screened (0 of 8)         | not screened (0 of 7)  | not screened (0 of 8)       | not screened (0 of 7)  |

- **Weak point: the wake band on full-space wings (decision 106).** Check 11 refuses 18 of 24 full-space BWB and 2 of 3 full-space cranked wings: band cells up to 7.8 % over the band cell (the growth part stays ≤ 0.99). Cause, measured on BWB full-space wing 13 (the worst): the wake leaves the base pointing down (−6.9° to −2.0°), 0.068 c below a straight line at 2 local chords, so the band's upper edge lies above the envelope height, where the cells grow freely. The reference and focus wings leave level or upward and pass. Fix, for the redesign: add the wake's downward offset to the envelope height.
- Thin margins, all on full-space BWB wings: inboard cells down to 0.053 (limit 0.05), base and trailing-edge corner cells down to 0.21, the 3-D wall angle up to 60°.

## The cost, and the packages that cut it (decision 105: Mike to choose)

Where the cells are, on BWB reference wing 0 at VC (4.93 M): every station plane holds 377 × 95 ≈ 36,000 cells, and there are 136 planes, 61 along the wing and 75 past the tip. The blocks past the tip hold 54 % of the cells, the wake blocks 39 % (the two overlap). The 75 outboard planes grow from the tip gap (2 s0, about 10⁻⁴ c: the cap is a resolved wall) at 1.15, and still number about 49 at 1.3; the wake lines start from s0 at the base (starting from the wing's last chordwise cell saves 17 of 74 nodes per line); the wake band is applied to every line of a plane and takes about a third of the 95 layers (half its fan cells saves 15).

One change at a time (counted on the 20 reference wings, Re 3 × 10⁵, median; the ratio to the decided rules):

| option                                          | VC            | F              |
|-------------------------------------------------|---------------|----------------|
| the decided rules                               | 4.55 M (1.00) | 45.35 M (1.00) |
| outboard growth 1.25 (not 1.15)                 | 3.88 M (0.85) | 38.26 M (0.84) |
| outboard growth 1.30 (no outboard fine zone)    | 3.67 M (0.81) | 36.38 M (0.80) |
| 30 cells across the boundary layer at M, not VC | 4.12 M (0.90) | 40.65 M (0.89) |
| both                                            | 3.50 M (0.77) | 34.27 M (0.76) |
| the band off (Stage 2 option, decision 81)      | 3.28 M (0.73) | 32.30 M (0.72) |
| band off + outboard 1.25 + 30 cells at M        | 2.52 M (0.56) | 24.45 M (0.55) |

Packages (each builds on the one before; counted, not built, on the 20 reference wings at Re 3 × 10⁵; median cells per level, the largest at F, F against today, ADflow RAM at VC and how many VC meshes fit the 16 GB desktop):

| package                                                   | reopens                                                   | VC     | C      | M       | F       | F largest | F / today | VC: RAM; fit 16 GB |
|-----------------------------------------------------------|-----------------------------------------------------------|--------|--------|---------|---------|-----------|-----------|--------------------|
| **P0** the decided rules                                  | —                                                         | 4.55 M | 9.77 M | 20.79 M | 45.35 M | 50.7 M    | 1.00      | 45 GiB; 0 of 20    |
| **P1** lighter volume rules                               | volume rules (laws 12, 14); decision 90 (the base y⁺)     | 3.03 M | 6.44 M | 13.70 M | 29.71 M | 34.2 M    | 0.66      | 30 GiB; 0 of 20    |
| **P2** P1 + a coarser wake band                           | \+ the wake band rule (decision 87)                       | 2.45 M | 5.23 M | 11.09 M | 24.18 M | 27.9 M    | 0.53      | 25 GiB; 0 of 20    |
| **P3** P2 + the tip cap not wall-resolved (tip gap 10 s0) | \+ the frozen surface (Stage 2 law 9/10: tip gap)         | 2.13 M | 4.51 M | 9.56 M  | 20.74 M | 24.0 M    | 0.45      | 22 GiB; 0 of 20    |
| **P4** P2 + the surface band off                          | \+ decision 81 (the band on for every run)                | 1.68 M | 3.53 M | 7.51 M  | 16.28 M | 19.2 M    | 0.36      | 17 GiB; 0 of 20    |
| **P5** P2 + tip gap 10 s0 + the surface band off          | \+ both Stage 2 changes                                   | 1.45 M | 3.06 M | 6.43 M  | 13.99 M | 16.5 M    | 0.31      | 15 GiB; 0 of 20    |
| **P6** P5 + far field 40 c + 30 boundary-layer cells at F | \+ the far-field distance (law 15) and the 30-cell anchor | 1.31 M | 2.76 M | 5.79 M  | 12.54 M | 14.8 M    | 0.28      | 14 GiB; 1 of 20    |

**Conclusion.** With four levels no package brings F to 9–11 M: the volume rules alone (P2) give F 24.2 M (median), the two Stage 2 changes on top 14.0 M (P5), everything counted 12.5 M (P6). What is left is the plane (about 210–310 C-line nodes × 70 layers) times the stations (53–62 along the wing, 40–48 past the tip); the surface band and the tip squeeze are Stage 2's. Mike's target (9 Nov, 20:30) is M about 10 M with F above it: P2 meets it with the volume rules alone (M 11.1 M median, 10.0–13.0 M; F 24.2 M; VC 2.45 M, 25 GiB for ADflow, every VC mesh fits the 52 GB desktop), so P2 became rule set 2 (decision 107). If M must come lower, the next step is the tip gap (P3: M 9.6 M), which changes the frozen surface. No package lets a VC mesh fit the 16 GB desktop but one (P6, 1 of 20).

## V7: the first solves (not run here)

- The case: BWB reference wing 0, VC, Re 3 × 10⁵, α 4°, Mach 0.1, band on. ADflow SA; SU2 SA; SU2 SST + LM (8.6.0).
- This session has no ADflow and no SU2, 2 cores and 7 GB. The mesh (rule set 2) has 2.32 M cells and needs about 19–23 GiB for ADflow (S8's two laws): more than the 16 GB desktop, inside 48 GB. Ready: `solve/case.py` (conditions, reference area and moment point from the mesh, ADflow options, two SU2 configs), `solve/run_adflow.py` (S8's safeguards: the lift axis read back before the solve, the true residual, implausible forces refused; the peak memory of every rank), `solve/read_results.py` (the acceptance rule, written before any run), `solve/RUNBOOK.md`.
- **V7 also measures the memory (decision 113).** The plan assumed 10 M cells in 48 GB; S8's laws (two-point fits at 0.57 and 1.11 M cells) say 48 GB holds 4.6–5.9 M. The runbook measures ADflow as run, ADflow with a leaner preconditioner, and SU2. Until then: VC and C on the desktop, M and F on the HPC.
- **V7 also checks where the wake goes (decision 111):** two more points, α −5° and +10°, with the volume solution kept. The script that reads the wake against the fan's edges is not written: it needs a real solution file.
- Known risk from S8: on E387, SST + LM gave no laminar bubble and drag 37 counts high, where SA + LM matched. The brief fixes SST + LM, so this is a flag, not a change.

**Conclusion.** Not done. Where the solves run: Mike (decision 103).

## V8: the hold-outs

Not opened (Mike, 9 Nov: not yet; decision 104). They are run once, at the end, with the volume rules frozen and Mike's OK, and never used to tune anything.

## What changed while building (the construction, never a limit)

1.  V1: a layer-by-layer march folded; now the line shapes come from one front and the nodes are placed along them.
2.  V1: per-line distributions made slivers behind the trailing edge; now one distribution per station, the band as an envelope, the wall spacing along the cut, parallel wake lines.
3.  V1: the count fill stalled at zone changes; now every limit ramps over 25 %.
4.  V1: cells sheared between stations near the tip (scaled Jacobian 0.001); now the outer layers move to the station mean.
5.  V1: that move raised the far growth 3 % over 1.3; the far zone is built below the limit.
6.  V2: check 10 compared floats exactly (79.99999999999999 c); now it allows 1e−9 c of round-off.
7.  V4: the count factor scaled the band cell (VC/C 1.24); now it scales the growth only.
8.  V4: cells left the band abruptly (the cell at 1 c: VC/C 1.23); now the cap rises at the growth law's rate.
9.  V2: a text said the outboard far growth is built at 1.25; the code builds 1.3 (no blend there). Text fixed.
10. V2: the far-field blend pushed one root to 1.0100 × the growth limit; the far zone is now built at 1.22.
11. V6: the wake band missed wakes that leave the base pointing down (20 refusals); the envelope's top was raised by the wake line's fall (decision 106), which was not enough:
12. Rule set 2: the band's cells were still sized from the wake line (9 of 13 full-space wings refused); now the exact envelope of the straight fan around the bent line (decision 108).
13. Rule set 2: each cell took the band limit at its start (check 13 failed on 11 of 20 wings; band cell VC/C 1.285); now at its centre (1.300; decision 109).
14. Rule set 2: cells sheared between very close stations on steep BWB centre bodies, kinks and tapered tips (0.024–0.050); now the far parts of neighbouring stations are lined up along the semi-span, each as far as its growth limit allows, with the ramp that leaves the least shear (decision 110, three versions). BWB corner2 wing 6 stays refused (0.032).

## Weak points and open items

- **Cost and memory.** Rule set 2: M about 9.5 M cells, F about 21 M (rule set 1: 45 M at F). The plan assumed 10 M cells in 48 GB; by S8's laws 48 GB holds 4.6–5.9 M, so VC and C fit and M and F need the HPC. The laws are two-point fits at 0.57 and 1.11 M cells: V7 measures (decisions 112, 113).
- **The mesh grows with Re, and the tip gap is why** (11 Nov, [The size](#size)): M is 9.1 M at Re 3 × 10⁵ and 13.5 M at 4 × 10⁶ on wing 0 of each type. The last station gap at the tip is 2 × the first wall cell (36–1,100 × finer than DPW's guide), because the tip cap is a wall reached along the stations; with the gap at 100 × the first wall cell a third of the cells go. A lighter rule set is proposed, not decided (decision 114).
- **The tip cap is fragile to any change of the ring:** with the band off, a coarser trailing-edge cell or a faster growth around the section, the BWB or flying-wing cap falls below its limit (0.05).
- **The count runs one layer high** on about a fifth of the meshes (`count_volume` against the built mesh: 1.5–1.8 % more cells, never fewer); the counted M and F cells can be that much high. Not fixed.
- **The fan ends at +10°** (decision 111). Above it the wake leaves the fine cells; post-stall needs its own mesh. Where the wake really goes at −5° and +10° is not measured (V7).
- **Very close stations with fast-changing chords sit nearest the cell-quality limit** (decision 110): steep BWB centre bodies, kinks, corner wings. One wing is refused: BWB corner2 wing 6 (0.032; limit 0.05), whose chord halves within 0.14 c of the semi-span; a fix would space the far wake by x for every station at once (a redesign, not built). In the screen: 3 of 722 meshes have their worst cell under 0.06.
- **No solve yet** on a Stage 3 mesh (V7 needs Mike's machine). Accepting the files is shown; converging is not.
- **Built here on the numpy twin of the loft.** Every Stage 3 mesh here sits on surfaces from the numpy loft; the production loft is pyGeo. On the 20 reference wings the two give the same surface meshes to round-off (Stage 2, 8 Nov), and the pyGeo build of 11 Nov (Mike's machine, 722 of 722) has the same input hashes, pass flags and labels. No volume mesh has been built on pyGeo yet: V7 on Mike's machine will be the first.
- **Planar stations**: square in the plane, sheared in 3-D at swept noses: up to 40° on the reference wings, 74° on the most swept corner wing (reported, no limit; y⁺ only falls; a 3-D march would cross near the tip).
- **The cap cells** are the worst of most meshes (0.062–0.097 on the reference wings; limit 0.05), set by the frozen surface.
- **The base is not at y⁺ 1** in rule set 2 (its first cell is the wing's last chordwise cell); in exchange the spacing jump across the trailing-edge line fell from up to 537 to about 1.03.
- **The tip vortex** is carried, not resolved: coarse along its path; a tube would be a new rule.
- **The cap's two nose-corner columns** fall below 0.05 at M and F on the BWB and flying wing (0.045 and 0.037 on BWB 0; every other cell ≥ 0.077): exempt as in Stage 2 (decision 101, Mike), not fixed; a better cap belongs to the frozen surface.
- **Margins (rule set 2, reference wings):** growth at most 0.996 × its limit (the check allows 1.01); wake and band at most 0.997; check 13 at most 2.0 % off (allows 3 %); cells across the boundary layer at least 17.92 (limit 17.75).
- **C was built only on the 20 reference wings, M on four (wing 0 of each type), F on one**; elsewhere M and F are counted (time on 2 cores, not memory).
- **V0's two studies** ran on the V0 construction; the later changes do not touch what they compare.

## Next, and the handover to Stage 4

- **Next:** Mike's word on the lighter rule set (decision 114); V7 on Mike's machine: the three solves, the memory (decision 113), the wake at −5° and +10° (decision 111) and, if rule set 3 is built, the same wing on both meshes. Then the hold-outs (V8) when Mike says, with the rules frozen.
- **Stage 4 gets:** per wing, Re and level, a folder `volume_<level>_<hash8>_re<Re>/` with `blocks.npz`, `quality.json` (every check, the info), `manifest.json` (hashes of the code, the rules and the nodes; the BCs; the interfaces), `volume.cgns`, `volume.su2`; a refused mesh only `refusal.json`.
- **Build:** `build_volume(surface)` then `write(vm, wing, out, formats=("npz", "cgns", "su2"))`; cost first with `count_volume(surface)`.
- **First:** run V7 and read it with `solve/read_results.py`; send back the memory numbers; then the hold-outs (V8) with the rules frozen.
- **For the solves:** the semi-span along +y, lift +z (ADflow liftIndex 3); lengths in mean chords; Re on the mean chord; the band on; angles −5° to +10° on this mesh.

## Files and commands

    CFD_Automation/cfdauto/volume/     laws, march, plane, topology, volume, checks, family, cgns, su2
    CFD_Automation/Stage_3_volume_mesh/
      configs/volume.yaml               the rules and the check limits
      decisions/volume_rules.md         the plan, rules, checks, V0 measurements, what changed
      decisions/STAGE3_STATUS.md        status and the handover to Stage 4
      scripts/one_mesh.py               one wing's volume mesh (any set, level, Re; --count)
      scripts/screen.py                 the screen (one JSON row per mesh)
      scripts/v23_study.py v4_study.py v6_study.py cost_options.py v5_export.py   the studies
      scripts/far_field_study.py size_factors.py size_drivers.py knob_study.py light_set.py ladder_study.py
                                        the size studies of 10-11 Nov; size_figures.py, blocks_figure.py: their figures
      solve/                            the V7 case, ADflow run, results reader, runbook
      tests/                            pytest (Stage_3_volume_mesh/tests)
    CFD_Automation/app/                the app: load or make a wing, build and look at its meshes
    CFD_Automation/RUN_LOCAL.md        every command, Stage 1 to V7

CFD_Automation Stage 3 · built by scripts/make_stage3_page.py from configs/volume.yaml and data/studies/\*.json · 11 Nov 2026
