# Stage_3 — Mesh flowchart (text copy, 10 Nov 2026)

Text copy of `CFD_Automation/Stage_3_volume_mesh/docs/MESH_FLOWCHART.html` (the artifact *Volume Mesh Flowchart*). Rule set 2 as it stands (decisions 107–111). On the page the values change with the level picked; here they are a table, and the steps show the VC values.

## The values per level

| value | VC | C | M | F |
| --- | --- | --- | --- | --- |
| y⁺ | 1.00 | 0.77 | 0.59 | 0.46 |
| wall growth | 1.250 | 1.187 | 1.141 | 1.107 |
| cells across the boundary layer | 17.8 | 23.1 | 30 | 39 |
| far growth, built | 1.220 | 1.165 | 1.125 | 1.095 |
| far growth, checked | 1.300 | 1.224 | 1.168 | 1.127 |
| band cell at the trailing edge | 1.27 % c | 0.975 % c | 0.75 % c | 0.577 % c |
| cells across the −5° to +10° fan | 7.1 | 9.23 | 12 | 15.6 |
| outboard growth | 1.300 | 1.224 | 1.168 | 1.127 |
| base cells | 8 | 10 | 14 | 18 |
| cells, median (20 reference wings, Re 3e5) | 2.08 M | 4.43 M | 9.53 M | 20.7 M |
| cells, largest | 2.58 M | 5.54 M | 11.8 M | 25.7 M |
| ADflow RAM, median (S8's two laws) | 18–21 GiB | 35–43 GiB | 72–92 GiB | 152–197 GiB |
| built here | built on 20: 20 pass; all sets: 721 of 722 | built on 20: 20 pass | built on 4: 4 pass | built on 1: 1 pass |

## The steps

CFD_Automation · Stage 3 · the volume mesh · rule set 2 · 10 Nov 2026

# From one surface to its volume mesh

What the volume mesher does with one Stage 2 surface, step by step: the rule behind each step (law), the decision that set it (D = decision in `OPEN_DECISIONS.md`), the checks, and the value at the level you pick. Every check and limit was written before any mesh was judged (V0) and none changed. **This is rule set 2 (D107, D111): M about 10 M cells, one mesh for angles −5° to +10°. The first rule set (M 20.8 M, F 45 M) is on the Volume Mesh page.**

*Input · the surface (Stage 2, frozen)*

## One Stage 2 surface

One wing at one Re and level: the ring at every station, the base, the tip cap. The band is on. Every wall node of the volume mesh is one of these nodes, never moved.

\[D81: band on for every run\] \[D82: surface rules frozen\]

`build_surface(loft, re, level)`

*Input · the rules*

## The volume rules at this level

At **VC**: y⁺ 1.00 · wall growth 1.250 · ≥ 17.8 cells across the boundary layer · far growth 1.220 built (checked 1.300) · band cell 1.27 % c · 7.1 cells across the −5° to +10° fan · outboard growth 1.300 · 8 base cells · far field 80 c

\[Law 23: r = 1.3 per level\] \[D85: far growth\] \[D86: boundary layer\] \[D87: wake band\] \[D107: rule set 2: M about 10 M\] \[D111: angles −5° to +10°\]

`configs/volume.yaml` → `laws.rules(level)`

**Step 1**

## Stations, far field, wake

One planar station (y = const) per Stage 2 station. The far field: a half circle in front, lines above and below, the outflow 80 c behind the most aft trailing edge, every wall node ≥ 80 c inside. The wake centre line leaves each base along its normal and turns to +x over 0.5 local chord; the wake nodes have one count for all stations.

\[Law 15: 80 c\] \[D89: planar stations\] \[D107: behind the base: the wing's last chordwise cell\] \[D91: far field shared by every station\]

**Step 2**

## The C line and the line shapes

The C line: upper wake line, the ring, lower wake line. One front moved the same distance everywhere from it, smoothed over its distance from the wall (κ = 1: square to the wall), out to 2 local chords; then straight to the shared far-field nodes.

\[D84: the march (0 folds in 501 planes)\] \[Law 20: fine zone 2 local c\]

**Step 3**

## One wall-normal distribution per station

First cell s0 (law 13), ≥ the boundary-layer cells across δ (turbulent flat plate at the TE), the wall growth to 2 local chords, the wake band as an envelope in height, then the far growth. The band is a fan of straight rays from the base (−5° to +10°, 0.05 c margin, 2 local chords long); the envelope is exact for it whatever the wake line does, and each cell takes the limit at its centre. One count for every station: each station's growth (never the band cell) is scaled down to fit.

\[Law 13: y⁺ per level\] \[Law 14: boundary-layer cells\] \[Laws 17, 18: wake band\] \[D96, D97: count factor; band release\] \[D108: exact band envelope\] \[D109: limit at the cell centre\]

**Step 4**

## Line up the stations far out

The far layers and far wake nodes of every station first move toward the average of its neighbours within about 0.25 c along the semi-span, as far as its growth limit allows and alike for neighbours, then toward the mean of all stations, so neighbouring planes line up and the cells between them stay square. The near field (fine zone and band) is never moved. The base block fills the space between the two wake lines.

\[D84: outer blend\] \[D110: neighbours lined up\] \[D98: far zone built at 1.22 for the blend\]

Did any cell fold in a station plane?

If yes: every station again with more smoothing, κ = 1.5, 2, 3 (never needed so far)

## Next rung

Rebuilt with more smoothing; the mesh is flagged "needs review" (R1).

D92

**Step 5**

## Stack the planes; outboard; the cap

The planes stacked root to tip; past the tip the tip plane swept out to 80 c, the first gap = the wing's last gap, growth 1.300 to 2 c past the tip, then the far growth. The tip cap swept outboard is the CAP block. 13 blocks, right-handed, k = +y; every face a boundary or matched node to node.

\[Law 12: outboard growth\] \[D88: outboard and the tip vortex\] \[D73: one matched C-H mesh\]

**Step 6**

## Checks 1–14

Wall on the surface · no folded cell · scaled Jacobian ≥ 0.05 · in-plane wall angle ≤ 5° · first cell within 1 % · growth ≤ limit × 1.01 · ≥ the boundary-layer cells · interfaces node to node · symmetry plane · far field ≥ 80 c · wake · outboard · (13: the family, between levels) · cells and RAM.

\[Checks 1–14: written in V0\] \[D101: the cap's two nose corners exempt, as Stage 2\]

Did a refusing check fail?

If yes: only refusal.json (which check, its value, its limit). It stays in every count.

## Refused

`refusal.json`

V6: 1 of 722 refused (BWB corner2 6, cell quality 0.032)

**Step 7**

## The files, and check 15

`blocks.npz`, `quality.json`, `manifest.json`; `volume.cgns` (ADF, read by ADflow) and `volume.su2` (SU2), both read back: the CGNS exactly, also by the CGNS library; the `.su2` with every face welded and no inside-out cell.

At **VC**, 20 reference wings at Re 3 × 10⁵: 2.08 M cells median (largest 2.58 M) · ADflow 18–21 GiB (S8's two laws) · built on 20: 20 pass; all sets: 721 of 722

\[Check 15: export round trip\] \[D99: the solver files\] \[D93: names and files\]

`write(vm, wing, out, formats=("npz", "cgns", "su2"))`

Sources: `CFD_Automation/Stage_3_volume_mesh/decisions/volume_rules.md`, `configs/volume.yaml`, `data/studies/` (repo karmix96/aeris, branch `stage3-volume-mesh`). The cells at M and F are counted, not built (except M on four wings and F on one). RAM: S8's laws for ADflow, ANK only and ANK then NK (two-point fits; V7 measures).
