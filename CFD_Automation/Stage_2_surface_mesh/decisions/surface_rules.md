# Stage 2 decisions — the surface mesh (2 Nov 2026, updated 7 Nov 2026)

What was decided while building the surface mesher, why, and what the screens showed.
Sections 1–11 are the first approach (values in `configs/surface_first.yaml`); section 13 is the new rules as built
(values in `configs/surface.yaml`); section 14 is the new screen; section 15 what similarity and the nose fix (Stage 1,
7 Nov) do to the meshes. The rules table is in `README.md`.

## 1. One spacing tool for everything

The ring (around the section) and the stations (along the semi-span) use the same three steps: a target
cell size along the line (the smallest of every rule that applies there), a growth limit, and points
placed so every cell holds the same share of ∫ ds / h. S8 used a two-sided tanh stretching per side,
which can set only the two end cells; the transition band needs a set size in the middle of the side.

Growth: a size field with slope ln(g) per unit length gives neighbouring cells in the ratio g. The
first version used slope g − 1, which delivered 1.25 for 1.2 asked; the check caught it.

## 2. The transition band: 20 nodes per bubble

The Stage 1 handover left the cells-per-bubble rule without a source. The Ansys CFX Modeling Guide
(gamma-Re_theta transition model, grid requirements) asks for at least 20 nodes across a laminar
separation bubble, about 75–100 streamwise nodes from leading to trailing edge for a grid-independent
transition location, y+ about 1, and a wall-normal growth of about 1.1 (1.2 already moves transition a
little upstream). We use 20 nodes per bubble at level C, with the bubble length from the Stage 1 XFOIL
table at the station's local Re (0.40 c at 6 × 10⁴, 0.30 c at 10⁵, 0.10 c at 4 × 10⁵, 0.05 c at and
above 10⁶; log-log between the points). Weak points: the table is 2-D, calm air, N_crit 9; the length
above 10⁶ is "under 0.05 c" in Stage 1, taken as 0.05 c here; and the wall-normal growth of 1.1 is
tighter than the 1.25 in Stage 0 and the handover — that is a Stage 3 (volume) decision, noted in
`OPEN_DECISIONS.md`.

What it costs: the band cell is 2.0 % c at Re 6 × 10⁴, 0.63 % c at 3 × 10⁵ and 0.25 % c at and above
10⁶. With the upper band over 0–85 % c, the ring has about 200 nodes at Re 10⁵, 400 at 3 × 10⁵ and
850 at 1.5 × 10⁶ and above, against 150 in S8. At level F (×1.69) that is about 1,400 ring nodes.
This is the rule the T6 ladder of the Grand Roadmap must test first (the chordwise direction holds
35 % of the mesh budget); if 20 nodes per bubble turns out to be more than the drag needs, the
coarse level can be relaxed.

## 3. The upper band starts at the leading edge on every wing

Stage 1 asks for the upper band from 10 % c, from the leading edge on panels swept over about 25°
(crossflow transition). One rule for every wing is simpler and costs about 10 % of the chord at band
spacing; the nose cells are finer than the band anyway on most stations.

## 4. Both sides share one distribution

The upper band sits at the front, the lower band at the back, so the two sides of a ring would get
very different node distributions. The tip cap joins upper node i to lower node i; with different
distributions its cross lines slanted across the thin trailing-edge region and the cap quads collapsed
(scaled Jacobian 0.03 on the BWB reference wings at Re 3 × 10⁶). Now the size field is the stricter of
the two sides at the same fraction of the side's arc length, and both sides get the same distribution
in arc fraction. Sharing x/c instead did not work: on a cambered nose the arc per x/c differs between
the sides right at the leading edge (the lower first cell came out 2.5 × the upper one). Cost: about
5–10 % more ring nodes. Cap quality on the reference wings: scaled Jacobian 0.11–0.45 (was 0.02–0.13).

The two cap cells where the nose arc meets the sides have three corners on the smooth ring, so their
corner angle is 180° minus the ring's turning there, whatever the smoothing does. They are reported on
their own and refused only if folded.

## 5. One node distribution for the whole wing

A structured mesh needs the same ring at every station. The first version gave every station the
same count but its own distribution (the station that needs most sets the count, the others put
their spare points in their largest cells). The screen then showed surface quads with a scaled
Jacobian down to 0.08: node i drifted along the chord between neighbouring stations (a different
nose spacing, band cell or count), and where the stations are squeezed to tens of µm at the tip, a
drift of a fraction of a cell shears the quad. Now there is one node distribution in arc fraction for
the whole wing: at every place the strictest station wins (the sharpest nose, the finest band). Node
i sits at the same arc fraction on every station, so the quads between stations are clean (0.08 →
0.58 on the worst flying wing; 0.77 → 0.92 on the BWB reference wing), no cell is coarser than its
station asks, the spanwise envelope (law 2) holds by construction and no repair was needed on any
reference wing. Cost: about 3 % more ring nodes (BWB reference wing 590 → 610). On the BWB reference
wing at Re 3 × 10⁵ the tip alone would need 85 of the 305 points per side.

The lowest wing-quad quality left (0.09–0.13) sits on corner wings whose first panel is 4–6 mm wide
with a 50 mm chord drop: a trailing edge swept at about 85°, a property of those wings.

## 6. The turning rule holds at every ring node, and the nose solve must survive the envelope

S8 measured the turning over the leading edge ± 3 nodes. On the cranked and tapered reference wings
the largest turning sat a few cells onto the lower surface (cambered nose) and 10.2–10.4° were
delivered for 10 asked. The check now takes every node but the two trailing-edge corners. Away from
the nose (x/c > 0.5 %) the same angle also caps the size field from the local curvature radius
(cell ≤ R × 10°): the start of the trailing-edge opening on very small chords (0.5 mm floor on a
12 mm chord, corner set) is a bend of about 10° that the band cell could not follow. A true kink of
the section (a dense step turning more than 1°) is reported apart (`geometry_kinks` check) and its
two nearest nodes are left out of the turning check: no cell size can reduce it.

Because the turning is not quite monotone in the nose spacing (section 10), a solved spacing that
passes can fail once a tighter distribution moves the nodes. The solve therefore walks down until
every spacing in [0.77 h, h] passes, and the turning is measured again on the rings as built; if a
station still lands above the target, the nose spacing of the whole wing is tightened by 10 % and
the rings are rebuilt (0 repairs on the reference wings).

## 7. Stations

A station sits exactly on every loft station (b0–b3 and the trailing-edge switch station some BWBs
have), because the ruled loft has a crease there. Each panel gets a whole number of gaps, so the gaps
on the two sides of a break can differ by up to 1/12 with at least 12 gaps per panel; with growth 1.2
inside a panel the worst step stays at 1.2 × 1.08 ≈ 1.3, the checked limit. The tip squeeze goes from
0.2 × chord down to s0 (tens of µm): about 40 gaps on the last panel. The dense span grid has 4,001
points per panel, not per wing: a break can sit under 1 mm from the root (tapered training wing 35,
b1 at 0.9 mm), and the station placement integrates on that grid. Such a panel still gets its 12
stations; that is the rule, and it is cheap.

## 8. The surface depends on the Reynolds number

The tip gap (s0 at the tip Re) and the band cell (bubble length at the local Re) change with Re, so one
wing has one surface per Re level. Building one takes 3–6 s, so this costs nothing in time, but the
mesh name now carries the Re (`mesh_<level>_<hash8>_re<Re>`), and the Stage 0 naming rule is
extended, not changed. Alternative, not taken: one surface per wing built for the highest Re level
(finer than needed at the lower levels, and the family rule then no longer holds per level).

## 9. The family rule

Every spacing (nose, trailing edge, band, tip gap, station gaps, and the cells in the stretched parts
between them) at level M is the C value divided by 1.3, within 3 % (test `test_family.py`;
`data/studies/family_ratios.json` for the four reference wings at C, M, F). For that the growth used to
build the size field is also scaled: g at level k is g_C^(1 / r^k) (1.2 at C, 1.15 at M, 1.11 at F). With
the same g at every level the end spacings refine by r but the stretched parts do not, and the station
count grew by only 1.2 per level instead of 1.3. The one exception is the base: 8 cells at C become 10
at M, 14 at F, 18 at FF (even counts, so the cap's nose arc stays centred), ratios 1.25, 1.4, 1.29. The
first panel's gap count is an integer too (12, 16, 21: ratios 1.33, 1.31).

Counts for the reference wings at Re 3 × 10⁵ (ring nodes × stations): BWB 604 × 82 (C), 782 × 107 (M),
1016 × 139 (F); flying wing 430 × 74, 556 × 96, 720 × 125; cranked 398 × 75, 514 × 98, 668 × 127;
tapered 408 × 75, 526 × 98, 684 × 127.

## 10. Finding for Stage 1: the nose of the built sections is not round (first reading, 2 Nov; the cause below was right; fixed in Stage 1 on 7 Nov, section 15)

While solving the nose spacing, the turning did not fall steadily as the nose spacing was reduced
(10.0° → 10.3° → 9.5° for spacings × 1, 0.9, 0.8 on BWB training wing 36). The cause is in the loft:
its curvature at the leading edge differs between the upper and lower side. `scripts/nose_radius.py`
(`data/studies/nose_radius.json`) compares the raw airfoil files with the Stage 1 resampled sections
(nose radius from y ≈ √(2 R x) at the first cosine point, x = 2.5 × 10⁻⁴ c):

| Section | raw R/c at the leading edge | resampled, upper | resampled, lower |
| --- | --- | --- | --- |
| NACA 4415 (formula: 1.1019 t² = 0.0248) | 0.0246 | 0.0080 | 0.0741 |
| E387 | 0.0102 | 0.0028 | 0.0353 |
| SD7032 | 0.0077 | 0.0318 | 0.0023 |
| MH 104 | 0.0084 | 0.0183 | 0.0048 |
| MH 61 | 0.0041 | 0.0023 | 0.0053 |
| LA2573A, NACA 25118 (round noses) | 0.032, 0.034 | 0.033, 0.039 | 0.033, 0.030 |

On cambered sections with a small nose radius the two sides are off by up to 3–13 × in opposite
directions, within the first about 0.1 % of the chord. The likely cause: the leading edge is taken at
the raw point farthest from the trailing edge, and each side is then interpolated in √x from that
point; when that point is not exactly the nose apex, the two branches are not √x-symmetric. The mesh
follows the loft as built, so the surface mesh is right for the wing we have; the wing's nose is not
the airfoil's. It matters for the suction peak at high angle and for the nose spacing law (law 1
measures the turning, so it adapts, but a law "spacing from nose radius" would read the wrong radius).
A Stage 1 fix (resample the nose in arc length, or fit the apex from the raw points) changes every
geometry hash; it is logged as open decision 64 for Mike. The mesher is made robust meanwhile: the nose
size is held over the first four cells (the first version held a size of four cells over one cell, a bug in
the helper that the solve compensated for and the third screen exposed through the reported asked spacing),
and a station whose turning lands above the target after the shared distribution tightens the whole wing's
nose spacing by 10 % until it passes (32 of 790 builds, one round each).

## 11. The screen

Every built wing of every type and set (730: reference, training_focus, training_full, corner1, corner2)
at level C and Re 3 × 10⁵ on the mean chord, and the 20 reference wings at all four Re levels: 790 builds,
790 passed every check, 0 refusals, 0 crashes (`data/studies/screen_C.json`, `docs/screen_C.png`). With the
numpy twin of the loft. The pyGeo check came later, on the new rules (Mike's machine, 8 Nov: the same ring
nodes and stations on the 80 reference builds at VC, old Re levels).

| Type (builds) | Ring nodes min–median–max | Stations | Quads | Build time [s] | Wing quads J min / median | Cap quads J min / median |
| --- | --- | --- | --- | --- | --- | --- |
| BWB (202) | 486–614–860 | 71–83–134 | 36k–52k–101k | 4.2–5.3–8.1 | 0.09 / 0.82 | 0.19 / 0.34 |
| Flying wing (193) | 370–430–528 | 66–76–116 | 28k–34k–58k | 4.0–4.8–7.0 | 0.48 / 0.88 | 0.15 / 0.19 |
| Cranked (202) | 364–410–594 | 69–78–119 | 27k–36k–72k | 4.0–4.9–7.6 | 0.40 / 0.98 | 0.15 / 0.43 |
| Tapered (193) | 364–420–506 | 69–79–116 | 28k–34k–55k | 3.7–4.9–7.8 | 0.56 / 0.98 | 0.15 / 0.43 |

Reference wings by Re level (ring nodes, stations): 10⁵: 192–310, 67–97; 3 × 10⁵: 368–638, 73–103;
1.5 × 10⁶ and 3 × 10⁶: 844–860, 81–114. The largest delivered turning is 10.02° (target 10 ± 0.02), the largest
chord growth 1.21 (limit 1.25), and a nose repair (the whole wing's nose spacing tightened by 10 %) was needed on
32 of 790 builds, one round each. What the screen does not show: whether the volume
march (Stage 3) accepts these surfaces, and whether 20 nodes per bubble is the right coarse level (T6).

The three earlier passes of the screen are development evidence, not results: the first (per-station
distributions) found the tip-gap tolerance, the kinked noses of the corner set, the 0.9 mm panel and the
0.08 quads; the second (one distribution) found the 1.25–1.26 growth on NACA 4415 noses; the third ran before
the flat-nose fix (section 6). With the nose held over four cells the largest growth fell to 1.21.

## 12. The new approach (decided 4–6 Nov 2026; built 7 Nov, section 13)

What was first is sections 1–11: every rule met at level C, the coarsest of C, M, F, FF. The owner decided a new
approach on 4–6 Nov; `CFD_Automation/OPEN_DECISIONS.md` 67–76 has each item with its reason.

- **Levels VC, C, M, F (71).** Hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap);
  accuracy targets at M (nose 10°, trailing edge 0.1 % c, station gap, largest cell 2 % c), as the DPW
  guidelines define their medium grid; transition targets at F (20 cells per bubble; wall growth 1.25 at VC is
  1.107 at F, just above the 1.1 of the transition-model guide: 1.23 at VC would give exactly 1.1). The four levels
  keep their places on the ladder;
  the first C, M, F, FF sit where VC, C, M, F sit. VC (about 1.0 M cells median) is the desktop level.
- **Lighter rules (72).** The bubble-length table stops at 0.10 c from local Re 4 × 10⁵ up (band cell 0.5 % c at
  F); tip gap 2 × s0; station gap 0.25 × local chord at M. Fine level about 10–11 M cells median on the wing
  blocks (10.9 M with the band change alone, 15.2 M with the planned rules); the shortest high-Re root bubbles
  (about 1.5 % c) get about 3 cells: fine for SA, not for LM, so the 3-D check decides whether a local band is needed.
- **Lower band at negative angles (74; decided 7 Nov: option A).** Angles now run from −5° (69). Option A: the lower
  band from the leading edge (one rule for both sides; band length 125 → 185 % of the chord). Option B: keep
  60–100 % c and run transition (LM) only at angles ≥ 0°. Counted on the 20 reference wings with the refine map run to
  −5° (Study 8): A gives the same ring as B. The owner chose A; it is built (section 13).
- **Matched C-H for ADflow and SU2 (73).** The surface ring and the cap stay; Stage 3 builds the C-H blocks
  (open-line march, wake lines to the far field, tip vortex in the outboard blocks) instead of the overset boxes.
- **Similarity (70; built in Stage 1 on 7 Nov).** Every wing at unit mean chord, Re an input, Mach 0.1, trailing
  edge 0.2 % c: the 0.5 mm floor that made the corner set's 12 mm tip 4 % c thick (section 6) is gone (section 15).
- **The nose, "corrected" (75; superseded on 7 Nov: the correction was wrong, see section 15).** The first reading
  compared a circle through three raw points with a one-sided
  formula on the built section. Measured the same one-sided way, the raw files show nearly the same split (NACA
  4415 raw 0.0081 / 0.0736 c, built 0.0080 / 0.0741 c; SD7032 raw 0.0287 / 0.0023, built 0.0318 / 0.0023): mostly
  how the formula sees a cambered, tilted nose. What may remain lies inside the first raw-point gap (under
  0.025 % c on NACA 4415, about 7 × smaller than the 0.18 % c nose cell of the NACA 4415 reference wings at C).
  Re-measure raw and built with one curvature method; fix only if a real error remains.


## 13. The new rules, built (7 Nov 2026)

Decisions 71, 72 and 74 (option A, decided 7 Nov) are now in the code. Sections 1–11 are the first approach. It is
kept in `configs/surface_first.yaml` and rebuilds the same meshes node for node (BWB reference wing 0, Re 3 × 10⁵,
level C: the same node hash before and after the change).

**What changed in the code.**

- `configs/surface.yaml`: levels VC, C, M, F. Every value that changes with the level carries its anchor level, for
  example `nose_turning_deg: {value: 10.0, at: M, why: "accuracy target, decision 71"}`. The lower band is 0–100 % c
  (decision 74, option A); the upper band stayed 0–85 % c as written (as built the upper side got band-size cells
  to the trailing edge too, through the one node list; section 16) until 8 Nov: now 0–100 % c (owner; section 19). The first config is `configs/surface_first.yaml`, unchanged,
  with a header that says how to use it.
- `laws.py` moves each value from its anchor level a to level k in whole steps of r = 1.3: spacings and turning angles
  × r^(a − k); counts (cells per bubble, base cells, gaps per panel) × r^(k − a); growth ratios, built and checked, to
  the power r^(a − k). The power is a whole number, so a value is exact at its anchor (10° at M is 10.0). Whole numbers
  are rounded as before: the base to the nearest even count, the gaps per panel up. A plain number keeps its first
  meaning: set at the coarsest level; the spacings ÷ r^k, the counts × r^k, the growth g^(1/r^k); the nose angle, the
  growth limits and the tolerances the same at every level. So `surface_first.yaml` and `surface_plan_VC.yaml` still
  build as before.
- `Rules.reason(name)` says in one line where each value comes from, for example "law 1: largest turning per ring cell
  [deg]: 10 at M (accuracy target, decision 71); VC is 2 levels coarser: x 1.3^2 = 16.9". Each mesh writes every value,
  anchor and reason to `quality.json`, and the rules file name and hash to `manifest.json`.
- The 13 checks read the level's own values. The turning limit is the level's angle + 0.2°: 17.1° at VC, 13.2° at C,
  10.2° at M, 7.89° at F (the first approach checked every level against 10.2°). The geometry-kink check uses the same
  limit. The growth along the ring is checked against 1.25, 1.19, 1.14, 1.11 (within 1 %), the growth between station
  gaps against 1.3, 1.22, 1.17, 1.13. The band, trailing-edge and tip-gap checks compare with what the level asked. No
  tolerance changed. The nose repair (the whole wing's nose spacing × 0.9) also reads the level's own angle.
- `build_surface`, `python -m cfdauto.mesh` and `scripts/screen.py` take a rules file (`config`, `--config`). The
  default level is the coarsest, VC. The screen writes `screen_<level>.json` and refuses to overwrite `screen_C.json`
  (the first approach's screen) unless `--out` names it. Mesh names keep `mesh_<level>_<hash8>_re<Re>`, with the new
  level names (`mesh_VC_…`).

**The values at each level** (from `laws.py`; `tests/mesh/test_laws.py` checks every one).

| Rule | Anchor | VC | C | M | F |
| --- | --- | --- | --- | --- | --- |
| Nose: largest turning per ring cell (law 1) | 10° at M (accuracy) | 16.9° | 13.0° | 10.0° | 7.69° |
| Turning check (the angle + 0.2°) | | 17.1° | 13.2° | 10.2° | 7.89° |
| Trailing-edge cell (law 3) | 0.1 % c at M (accuracy) | 0.169 % c | 0.130 % c | 0.100 % c | 0.077 % c |
| Largest ring cell | 2 % c at M (accuracy) | 3.38 % c | 2.60 % c | 2.00 % c | 1.54 % c |
| Cells per bubble | 20 at F (transition) | 9.10 | 11.83 | 15.38 | 20 |
| Band cell at local Re 10⁵ (bubble 0.30 c) | | 3.30 % c | 2.54 % c | 1.95 % c | 1.50 % c |
| Band cell at local Re 3 × 10⁵ (bubble 0.126 c) | | 1.38 % c | 1.06 % c | 0.82 % c | 0.63 % c |
| Band cell at local Re 4 × 10⁵ and above (bubble 0.10 c) | | 1.10 % c | 0.85 % c | 0.65 % c | 0.50 % c |
| Base cells (law 6) | 8 at VC (hard minimum) | 8 | 10 | 14 | 18 |
| Growth along the ring, built | 1.2 at VC (hard minimum) | 1.200 | 1.151 | 1.114 | 1.087 |
| Growth along the ring, checked (within 1 %) | 1.25 at VC (hard minimum) | 1.250 | 1.187 | 1.141 | 1.107 |
| Station gap / local chord (law 8) | 0.25 at M (accuracy) | 0.4225 | 0.325 | 0.25 | 0.192 |
| Gaps per panel, at least | 12 at M (accuracy) | 8 | 10 | 12 | 16 |
| Growth between station gaps, built | 1.2 at VC | 1.200 | 1.151 | 1.114 | 1.087 |
| Growth between station gaps, checked | 1.3 at VC | 1.300 | 1.224 | 1.168 | 1.127 |
| y⁺ of the first wall cell (law 13) | 1 at VC (hard minimum) | 1.00 | 0.77 | 0.59 | 0.46 |
| Tip gap (law 10) | 2 × s0 at every level (decision 72) | 2 × s0 | 2 × s0 | 2 × s0 | 2 × s0 |

The same at every level: the bands (upper 0–85 % c until 8 Nov, now 0–100 % c; lower 0–100 % c; through the one
node list the upper side already got band-size cells over 85–100 % c, section 16), the bubble table (0.40, 0.30, 0.10, 0.10 c at
local Re 6 × 10⁴, 10⁵, 4 × 10⁵, 10⁶; log-log between the points, constant outside), the nose envelope (1.15), the
turning tolerance (0.02°) and every check tolerance. At local Re 6 × 10⁴ the band cell is the largest cell on every
level (0.40 c / 9.10 = 4.4 % c at VC is above 3.38 % c). The two counts are whole numbers, so they do not refine by
exactly 1.3: the base 8, 10, 14, 18 (ratios 1.25, 1.4, 1.29), the gaps per panel 8, 10, 12, 16 (ratios 1.25, 1.2, 1.33).
On a short panel whose gaps are set by the count, the gap refines by that ratio (1.25 from VC to C on the BWB root
panel); `test_family.py` expects that ratio there.

**The nose is solved at every level; the strictest wins** (the owner's answer to point (2) below, 7 Nov). How it got
there. The first code solved the nose spacing at the coarsest level and gave each
finer level that spacing ÷ 1.3^k. With each level checked against its own angle, that failed. On BWB reference wing 0
at Re 3 × 10⁵, the VC spacing ÷ 1.3^k turned the surface by 16.9°, 13.5° and 10.8° at VC, C and M (the angles: 16.9°,
13°, 10°). C needed a repair (nose × 0.9), which broke the family rule there (VC / C = 1.44, not 1.3); `test_family.py`
caught it. The cause is the built nose. On this section the lower side turns by about 35° between x/c ≈ 0.006 % and
0.1 %, and the curvature has a peak at x/c ≈ 0.01 % (radius 0.31 % c, against about 0.52 % c around it). VC has about
3 cells across that bend and averages it out. Each finer level resolves more of the peak, so the largest turning falls by about 1.25 per
level, not 1.3. The first approach never showed this, because its finer levels were checked against C's 10°. Holding
the nose cell over the same length on every level did not help (13.51° at C instead of 13.52°).

Then the nose spacing was solved twice at every station: at F for 7.69° on the F ring, then at VC for 16.9° on the VC
ring, starting from F's answer × 1.3³. When VC's turning there is already within 16.9°, that takes one measure and no
bisection. The smaller spacing, written at VC, wins, and every level takes it ÷ 1.3^k, so the family rule stays exact.
F wins on noses like this one. VC wins on round noses, where a cell's turning grows a little faster than the cell (on a
circle, 7.69° at F is 16.95° at VC, above VC's repair limit of 16.92°). On BWB reference wing 0 at Re 3 × 10⁵ this costs:
a VC nose cell of 0.060 % c instead of 0.079 % c, a largest VC turning of 13.4° instead of 16.9°, a ring of 240 nodes
instead of 236, no repair at VC, C or M, and no extra build time (4.1 s at VC). `stations.csv` says which level set
each station's nose (`nose_solved_at`). (These numbers are on the geometry of before 7 Nov.) On the rebuilt sets this
left M short: M needed one repair (nose × 0.9) on all 20 flying-wing reference builds, because F's spacing × 1.3
turned those noses just past M's 10.02°, so the nose cell stepped by 1.44 from C to M and 1.17 from M to F
instead of 1.3 (section 14). **Now the nose is solved at every level** (owner, 7 Nov): F for 7.69° on the F ring, then
M for 10°, C for 13° and VC for 16.9°, each on its own ring, starting from the finer answer × 1.3. Where the finer
answer already meets the level's angle, that level takes one measure and no bisection. The smallest spacing, written
at VC, wins, and every level takes it ÷ 1.3^k, so every level meets its own angle without a repair and the family
rule stays exact. The repair loop stays as a guard (the solve uses each station's ring, the check the shared node
list). The config key is `chord.nose_solved_at: [VC, C, M, F]`; without it (the first approach, the plan file) the
nose is solved at the coarsest level only, as before.

**Light check (7 Nov; on the geometry of before similarity and the nose fix; the full screen on the rebuilt sets is
section 14).** The 20 reference
wings × the four Re levels (10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶) at VC: 80 builds, 80 passed every check, 0 refused,
0 crashed, no nose repair. Ring nodes 120–224–240 (min–median–max), stations 54–70–96, surface quads
6,890–16,288–23,696, build time 3.2–4.2–5.8 s. By Re: 10⁵, ring 120–178; 3 × 10⁵, 192–240; 1.5 × 10⁶ and 3 × 10⁶,
224–240 (the same rings: the 0.10 c floor of the bubble table). Every station of the 80 builds took its nose from the
F solve (5,554 of 5,554), so the largest VC turning is 13.4–14.8°, not 16.9°. Largest growth along the ring 1.201
(limit 1.25 within 1 %), between station gaps 1.223 (limit 1.3); tip gap 0.97–1.00 × 2 s0; wing quads ≥ 0.57; cap
quads ≥ 0.070; no geometry kinks. Two wings at F, both passed every check with no repair. BWB reference wing 0 at
Re 3 × 10⁶: 514 ring nodes × 158 stations, 85,000 quads, 9.3 s; turning 7.67° (limit 7.89°); growth 1.090 along the
ring (limit 1.107 within 1 %) and 1.089 between station gaps (limit 1.127). Flying-wing reference wing 0 at Re 10⁵:
296 × 113, 35,492 quads, 6.9 s; turning 7.69°; growth 1.088 and 1.089; cap quads 0.064 (limit 0.05). (Study 8 built
the same two wings at F with the plan file: 508 × 142 and 292 × 102.) With the nose solved at VC only, the same BWB
wing at Re 3 × 10⁶ passes C only after one repair and F only after three (nose × 0.9³), which breaks the family rule.
To rerun: `python scripts/screen.py --sets reference --out <file>` (the default level is VC).

**The plan file, built the same way.** `configs/surface_plan_VC.yaml` at its coarsest level, the same 80 builds,
through the new code: the same meshes as Study 8, node for node (80 of 80 node hashes equal; the old code built
those). Against the new rules, the ring has 2–4 more nodes on every build (median 2; ratio 1.013 median, 1.025 max)
and 7–14 more stations (+17 % median; surface quads +17.5 %). The ring difference comes from the nose solve at F:
with the nose solved at VC only, the new rules give the plan's ring on 73 of 80 builds, and 2 more nodes on 7
flying-wing builds (230 → 232), from 16.9° against the plan's 17.0° and 9.10 against 9.1 cells per bubble. The lower
band (0–100 % c against 60–100 % c) changes nothing, as Study 8 found. The stations differ because the plan file
builds the station gaps with growth 1.25 and 7 gaps per panel; the decided rules keep growth 1.2 and give 8 (12 at M
÷ 1.69, rounded up). Neither 1.25 nor 7 is in a decision.

**Three points for the owner.** All make the rules stricter than the first code, never looser. Point (2) is
answered (7 Nov); (1) and (3) wait for the owner.
(1) The growth limits follow the family rule. Decision 71 lists growth ≤ 1.25 along the ring as a hard minimum at VC.
The limit of 1.3 between station gaps is not in decisions 71–72; it is anchored at VC the same way (1.13 at F).
(2) The nose. **Answered 7 Nov (owner): solved at every level, the strictest wins.** First it was solved at VC and at
F, as above: on the old geometry every level met its own angle and the family rule stayed exact (VC 13.4–14.8° against
16.9° on the 80 builds of the light check; 2–4 ring nodes at VC). On the rebuilt sets M needed a repair (× 0.9) on all
20 flying-wing reference builds, which broke the family rule for the nose cell (C/M 1.44, M/F 1.17 instead
of 1.3). Solved at every level: 0 repairs on the reference builds (4 of the 782 F builds of the full
sets still needed one round, because the solve measures each station's own ring and the check the shared node list),
and the nose cell refines by 1.297–1.302 per step (section 14).
The cost: VC, C and M get a finer nose than their own angle asks (VC 14.6–16.1° against 16.9°).
(3) The station rules: built as decided (growth 1.2, at least 12 gaps per panel at M), they give 17 % more stations
than the plan file (growth 1.25, 7 gaps per panel at VC). If the plan file's values were meant, they need a decision.


## 14. The new screen (7 Nov 2026)

The rules of section 13 on the rebuilt sets (similarity and the nose fix, section 15; 722 wings, new hashes), numpy
loft, one build at a time. Every set at VC and at F: training_focus, training_full, corner1 and corner2 at Re 3 × 10⁵
on the mean chord, and the 20 reference wings at all four Re levels (782 builds per level); the 20 reference wings
also at C and M at the four Re levels (80 builds each). The nose is solved at every level (section 13, point 2).
Each level refuses at its own limits (section 13). Per build:
every check's value, limit and margin, ring nodes, stations, quads, time, which solve set each station's nose, and
the reasons (`data/studies/screen_VC.json`, `screen_F.json`, `screen_reference_new.json`; the numbers:
`screen_new_summary.json`; `scripts/screen.py`, `scripts/screen_study.py`; Study 9 on the page).

**Result.** 1,724 of 1,724 builds passed every check, 0 crashed (VC 782 of 782, C 80 of
80, M 80 of 80, F 782 of 782). Nose repairs: 4 at F (one round, nose × 0.9; BWB, flying-wing, cranked, tapered, all training_full wings at Re 3 × 10⁵).

**The nose at every level, against the first build** (nose at VC and F only; the 20 reference wings × 4 Re × 4
levels; `data/studies/nose_levels_check.json`). The first build passed every check, but only after one repair (the
whole wing's nose spacing × 0.9) at M on all 20 flying-wing reference builds: F's spacing × 1.3 had turned those noses
just past M's 10.02°. Solved at every level: 80 of 320 builds changed, all of them flying-wing builds; the BWB, cranked and tapered builds
are the same node for node. Ring nodes changed by VC 0; C 0 to +2 (median 0); M −2 to 0 (median −2); F 0 (per level). Nose repairs 20 → 0.
What set the nose, over 167,473 stations of every build: F's solve 150,453 (89.8 %), M's 17,020 (10.2 %). The largest turning is 14.6–16.1° at VC
(angle 16.9°), 12.1–12.7° at C (13°), 9.80–10.01° at M (10°) and 7.21–7.71° at F (7.69°). On the old geometry (the light check, section 13) VC turned
13.4–14.8°: the true nose (section 15) is rounder, so F's answer is only a little finer than VC's own (on a circle
VC would set it). Largest growth along the ring
1.202 at VC (limit 1.25 within 1 %), 1.088 at F (1.107); between station gaps 1.233 at VC (1.3), 1.107 at F
(1.127). Lowest cap-quad quality 0.075 at VC and 0.061 at F (limit 0.05); lowest wing-quad quality 0.09.
Build time median 4.3 s at VC, 8.9 s at F (max 15.9 s).

| Level | Ring nodes min–median–max | Stations | Cells [M], 20 reference wings × 4 Re: median (max) | Cells [M], every set at Re 3 × 10⁵: median (max) |
| --- | --- | --- | --- | --- |
| VC | 120–220–240 | 51–63–84 | 0.70 (0.99) | 0.59 (0.88) |
| C | 154–284–306 | 66–85–102 | 1.50 (2.09) | — |
| M | 198–366–396 | 82–107–130 | 3.19 (4.52) | — |
| F | 254–474–514 | 106–131–177 | 6.92 (9.74) | 5.89 (8.84) |

(ring nodes and stations: VC and F over every set and Re level; C and M over the reference wings.)

**The cell estimate** of the wing blocks (the count the pages use, because its rule is written down and it can be
redone): n = max over the stations of ceil(ln(1 + (g − 1) D / s0) / ln g), cells =
(ring nodes − 1)(stations − 1) n + cap quads × n, with g the level's wall growth (1.25 at VC; 1.187, 1.141, 1.107), s0
the level's first wall cell at the station's local Re (y⁺ 1, 0.77, 0.59, 0.46) and D = 2 local chords; no C-H wake
lines. F is 6.9 M cells median on the 20 reference wings × 4 Re (2.3–9.7 M; 78–98–115 layers):
below the 9–11 M asked.

| Cells of the wing blocks | First estimate (6 Nov) | This count (7 Nov; the pages use it) |
| --- | --- | --- |
| Wall-layer rule | not recorded (surface × wall layers, about 1.30 × the layers per level) | the formula above |
| Surfaces | the plan file, on the first-approach reference wings (13 of the 20 replaced on 7 Nov) | the built rules on the rebuilt reference wings |
| VC / C / M / F, median (max) [M] | 1.0 (1.5) / 2.3 (3.3) / 5.0 (7.2) / 10.9 (15.9) | 0.70 (0.99) / 1.50 (2.09) / 3.19 (4.52) / 6.92 (9.74) |
| F | 10.9 M median (15.2 M with the planned rules) | 6.9 M median (2.3–9.7 M), 0.64 × the first |
| Can it be redone? | no | yes (`scripts/screen.py`, `scripts/screen_study.py`) |

The surfaces are not why the two differ (the built ones have about 17 % more stations than the plan file): they differ
in the wall-layer rule and in the wings. Both count the wing blocks only; with the C-H wake lines (+30–60 %, rough) F
is about 9–11 M. Stage 3 sets the real wall-layer rule, and with it the real count. RAM for ADflow (1.51 GiB +
9.46 GiB per million cells): the desktop today (16 GB: about 1.2 M cells) takes all of the 80 VC meshes and
28 of 80 at C; with +36 GB (about 5.0 M) all at VC, all at C and all at M; F needs the HPC.

**The family ratios** on the 20 reference wings × 4 Re (80 pairs per step): the nose, trailing-edge, band and tip-gap
cells refine by 1.269–1.321 per step (the first build, nose at VC and F only: the flying wings' nose cell C/M 1.44,
M/F 1.17); the base cells by 1.25, 1.4, 1.29 and the first station gap, where the gaps per
panel set it, by 1.25, 1.2, 1.33 (whole numbers); ring cells by 1.29, 1.29, 1.29, station gaps by 1.28, 1.27, 1.30, wall layers
by 1.29, 1.29, 1.30 and cells by 2.12, 2.13, 2.17 per step (medians).

**What it shows, and what not.** The built rules mesh every wing on all four levels, and, with the nose solved at
every level, the levels are true scaled copies. The cell count depends on the wall-layer rule more than on the surface; the stations add about 17 % against the plan
file (point 3 of section 13). The cap quads come
closest to a limit. Not shown: whether the march accepts these surfaces, whether the coarse levels are good enough for
the drag, the pyGeo loft.

## 15. Similarity and the nose fix, seen from the mesh (7 Nov 2026)

Both were built in Stage 1 on 7 Nov (decisions 70 and 64; `Stage_1_geometry/decisions/nose_curvature.md`) and the
sets rebuilt (722 of 722; 13 of the 20 reference wings are new picks). `scripts/similarity_check.py`
(`data/studies/similarity_check.json`; Study 10 on the page) builds the 20 reference shapes of before (Stage 1 sets at
commit 7bcb7067) again at unit mean chord and meshes them with the first rules at level C at the four Re levels:
once with the code of the similarity merge (commit 9472830c: the new size and trailing edge, the old nose rule) and
once with today's code (also the nose fix), against their first meshes at real size (`screen_C.json`).

- **Similarity alone:** 80 of 80 passed. The same ring nodes on 80 of 80 meshes: size changes nothing, as it should.
  The stations drop by 6–27 on the 8 wings that had a switch section (BWB 0, 1, 3, 4; flying wing 1, 3; cranked 4;
  tapered 4), the extra loft station the old trailing-edge floor made; nothing else changes. The cap quality falls on
  34 of 80 meshes (11 wings), most on BWB 1 at Re 10⁵ (0.345 → 0.133): the old floor had made the trailing edge of
  small tips thicker. The lowest stays 0.112 (flying wing 2 at Re 10⁵), above the limit 0.05.
- **The nose fix on top:** 80 of 80 passed; the rings change by −4 to 0 nodes; stations and caps do not change. At
  the same 10° the NACA 4415 / 4412 wings (cranked and tapered) get a nose cell of 0.245–0.265 % c instead of
  0.178 % c: the old spike had forced it down. The MH wings: 0.036–0.052 → 0.041–0.056 % c.
- **The nose defect was real; the 6 Nov correction (section 12, item 75) was wrong.** It compared built and raw only at
  the raw points, where they agree by construction; the defect sat between them. Measured with one curvature method,
  the old rule failed the 5 % turning test on all ten suggested airfoils (NACA 4415: +449 % at 0.04 % c, +121 % at
  0.18 % c; a 0.18 % c nose cell turned 9.47° built against 4.31° true). The new rule passes on all ten (worst −3.9 %,
  MH 60) and on 95.6 % of the database (21.0 % before); a gate refuses 14 files whose nose folds back. The cause the
  first reading named (section 10: the leading edge at the farthest raw point) was right.
- **The flat part of the nose solve stays** (section 6): on NACA 4415 the bump was only in the old section, but the
  flat line at about 7° below 0.2 % c comes from growth-limited cells 1.9–2.4 % c down the lower side, and the true
  airfoil does the same (6.0–6.8° with the fix). So the window search stays.
- **Re levels:** 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶ on the mean chord (area / full span). The real UAVs that set the
  Stage 1 ranges run from 1.22 × 10⁵ to 3.10 × 10⁶; 10⁵ is 18 % below the slowest and kept as a margin (owner, 7 Nov).
  Changed on 8 Nov to 10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶ (section 17).


## 16. The upper band as built, and the refine map at the Re levels (7 Nov 2026)

The refine map in its Re mode (`decisions/refine_map_re.md`, Study 11 on the page): the 20 new reference wings at the
four Re levels, −5° to 12°, the section tables rebuilt on the fixed nose. The lower band (0–100 % c) holds every
strip. The upper band as written (0–85 % c) holds only 0–49 % of the strips at Re 10⁵ and 3 × 10⁵ and 32–97 % at
1.5 × 10⁶ and 3 × 10⁶; the cause is always the transition itself (+ 10 % c), at low Re and low angle.

As built this is no gap. Both sides of a ring share one node list (section 4) and the lower band is 0–100 % c, so the
lower side's band cells set the upper side's aft part too: on 16 built surfaces at VC the largest upper cell over
85–99.5 % c is 0.950–0.995 × the band cell.

**The upper band written as 0–100 % c** (`data/studies/upper_band_check.json`): the 20 reference wings × 4 Re rebuilt
and compared with the screen (section 14).

| Level | Same ring and station counts | Same node hash | Ring nodes added | Cells |
| --- | --- | --- | --- | --- |
| VC | 80 of 80 | 17 of 80 (the rest round-off: no node moved more than 3.0 × 10⁻¹³ c; the hash rounds to 10⁻¹² c) | 0 | the same |
| F | 38 of 80 | 11 of 80 | +2 on 42 of 80 (BWB 16, cranked 12, tapered 13, flying wing 1) | +0.39 % median, +0.55 % max |

At F the upper cells over 85–100 % c can sit a little above the band cell with 0–85 % c, inside the 1 % check (BWB
reference wing 0 at Re 3 × 10⁵: 0.00501 c against 0.0050 c); written 0–100 % c, each side gets one more node. So the
written band stays 0–85 % c, and this note says what the built mesh does. Writing it as 0–100 % c is for the owner to
decide: the cost is the numbers above and a re-run of the screen (about 1.5 h on two cores).


## 17. The Re levels 10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶ (owner, 8 Nov 2026; decision 78)

The owner moved two Re levels: 10⁶ and 4 × 10⁶ replace 1.5 × 10⁶ and 3 × 10⁶ (Stage 0, D3). 4 × 10⁶ takes in every
cruise point of the Greek tactical BWB programmes (LOTUS, Archytas, and ACTUS, which develops LOTUS and the Safran
Patroller; `Stage_1_geometry/configs/greek_uavs.yaml`); 10⁶ fills the old ×5 gap between 3 × 10⁵ and 1.5 × 10⁶
(check C4 on 2-D data, `Stage_1_geometry/scripts/re_ladder_check.py`). The code reads the levels from Stage 0
(`cfdauto.paths.re_levels()`); the rules did not change.

**The reference wings at the new levels** (`scripts/screen.py --sets reference`, at VC, C, M and F; merged by
`scripts/screen_study.py`): 320 of 320 builds pass every check, 0 repairs. The 160 builds at 10⁵ and 3 × 10⁵ have the
very same nodes as on 7 Nov: the mesh code changed only in `cfdauto/mesh/refine_map.py` and a help text, which the
surface mesher does not use, so the 7 Nov builds of the other sets (at 3 × 10⁵) stand, and the merge records the two
code hashes with this check.

| Level | Cells [M], 20 reference wings × 4 Re: median (max) | At 10⁶ (median) | At 4 × 10⁶ (median) | 7 Nov: median (max) |
| --- | --- | --- | --- | --- |
| VC | 0.68 (1.02) | 0.75 | 0.93 | 0.70 (0.99) |
| C | 1.46 (2.19) | 1.59 | 1.98 | 1.50 (2.09) |
| M | 3.07 (4.69) | 3.41 | 4.19 | 3.19 (4.52) |
| F | 6.70 (10.17) | 7.43 | 9.19 | 6.92 (9.74) |

- The ring nodes do not change from 10⁶ up (the band cell is held from local Re 4 × 10⁵ up): VC 220–238, F 474–510.
- At F the two moved levels together have 0.7 % fewer cells (332.1 M against 334.4 M over the 20 wings): 10⁶ saves
  what 4 × 10⁶ adds. The largest mesh, BWB reference wing 3 at 4 × 10⁶, has 3 more wall layers (118 against 115) and 3
  more stations (162 against 159: the last tip gap is 2 × s0, and s0 shrinks with Re) than at 3 × 10⁶: 10.17 M, 1.7 %
  above 10 M (wing blocks only).
- Memory (ADflow, 1.51 GiB + 9.46 GiB per million cells): the desktop today (about 1.2 M cells) still takes every VC
  mesh (largest 1.02 M); with +36 GB (about 5.0 M) every C and M mesh (largest M 4.69 M); F needs the HPC.
- The refine map and its as-built check at the new levels: `decisions/refine_map_re.md` (update of 8 Nov).


## 18. The pyGeo loft on Mike's machine (8 Nov 2026)

Run by Mike with pyGeo installed. Stage 1 (on commit 25cbfea0; the geometry code is unchanged since): pyGeo tests 24
of 24 (pyGeo and the numpy twin agree within 10⁻⁶ chord on the 7 published wings), all Stage 1 tests 204 (1 skipped),
`build --all` 722 of 722. Against the numpy manifests: the same input hashes and the same pass/fail on all 722; the
surface hashes differ on all 722 (round-off between the two lofts); the labels on 721 (decision 79). Stage 2 tests 41.

The 20 reference wings meshed on the pyGeo loft, against the numpy screens:

| Run | Builds | Passed | Same ring nodes and stations | Other counts (quads, wall layers, cells) | Check values |
| --- | --- | --- | --- | --- | --- |
| VC, old levels (10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶), full record | 80 | 80 | 80 | equal on 80 | within 6 × 10⁻¹⁰ (nose turning, degrees); relative ≤ 4 × 10⁻¹¹ |
| VC, new levels (10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶), printout | 80 | 80 | 80 | cells within 0.005 M (print rounding) | not printed |
| F, new levels, printout | 80 | 80 | 80 | cells within 0.005 M; median 6.70 M, largest 10.17 M (as numpy) | not printed |

The node hashes differ (0 of 80 equal): the nodes move by round-off when the loft changes. Record:
`data/studies/screen_VC_pygeo_oldlevels.json`. Median build time at VC 2.85 s (cloud 4.98 s); at F 10.25 s (cloud
10.1 s).

**Conclusion.** The numpy twin stands for the production loft: on the reference wings it gives the same meshes as
pyGeo, to round-off. The full sets were not meshed on pyGeo.

**Then (8 Nov): the label fix in Stage 1 (decision 79).** Every wing's input hash changed (the geometry code hash
aa6ccb5d → 51e670d2); no surface did (the same surface hash on all 722). The mesher reads only the loft, so every
mesh and screen above stands; 5 builds re-meshed at VC (the two relabelled wings among them) have the same node hashes.


## 19. The family screen (8 Nov 2026; decision 80 and the upper band 0–100 % c)

**What was decided (owner, 8 Nov).** Decision 77 confirmed (the growth limits by the family rule; the station growth
1.2 with at least 12 gaps per panel at M). The upper band written 0–100 % c (was 0–85 % c, decision 58). The ratio
between levels stays exactly 1.3, also with a nose repair, and a repaired mesh is labelled (decision 80).

**What was built.** A repair round (every station's nose spacing × 0.9) is needed only where a ring turns past its
level's check limit: the angle + 10 × the solve's tolerance, 0.2° (`REPAIR_TOL_STEPS`). Before, 0.02° past the angle
was enough, and 4 of 782 F builds took a round for 0.003–0.006°. `build_family` builds all four levels of one wing
at one Re with one nose factor 0.9^n (n the most rounds any level needed), so every asked spacing still refines by
exactly 1.3; every mesh carries `nose_repair` (its own rounds, the family factor, the label) and `nose_family` (the
levels, the factor, the rounds, which levels needed them) in `quality.json` and `manifest.json`. Tests: a forced
repair goes on every level with the ratio exact; no repair gives the label "none" (43 tests).

**The screen.** Every set at VC, C, M and F for the first time: the 702 wings of training_focus, training_full,
corner1 and corner2 at Re 3 × 10⁵, and the 20 reference wings at the four Re levels: 782 families × 4 levels =
3,128 builds (numpy loft; two processes, about 2.9 h each). Code: `scripts/screen.py --family`,
`scripts/screen_study.py --family`; data: `data/studies/screen_family_*.json`; figures `docs/page/family_*.png`.

| Level | Builds | Passed | Ring nodes | Stations | Cells [M] min–median–max | Largest turning (check limit) | Lowest cap quad | Build time [s] median (max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VC | 782 | 782 | 120–220–240 | 51–63–84 | 0.24–0.60–1.02 | 16.11° (17.1°) | 0.075 | 4.5 (6.9) |
| C | 782 | 782 | 154–284–308 | 65–80–108 | 0.51–1.26–2.19 | 12.77° (13.2°) | 0.080 | 5.7 (8.1) |
| M | 782 | 782 | 198–368–398 | 82–100–136 | 1.07–2.70–4.69 | 10.02° (10.2°) | 0.057 | 7.2 (10.2) |
| F | 782 | 782 | 254–476–514 | 106–131–177 | 2.28–5.91–10.21 | 7.72° (7.89°) | 0.061 | 9.3 (13.8) |

- **The nose repair:** 0 of 782 families needed one; every family carries one factor at every level (782 of 782);
  the label is "none" on all 3,128 meshes. A few rings pass their angle by up to 0.03° (M 10.02°, F 7.72°), inside
  the check limits.
- **The family rule over all 782 families:** the delivered nose and trailing-edge cells refine by 1.295–1.304 per
  step, the band and tip-gap cells by 1.269–1.326 (whole cells per band and gap), the cells by 2.12, 2.13 and 2.18
  (medians).
- **Against the screens it replaces** (the sets of 7 Nov at VC and F, the reference wings of 8 Nov at every level):
  the same counts on VC 738 of 782, C 77 of 80, M 56 of 80, F 396 of 782. The upper band added 2 ring nodes on VC 44,
  C 3, M 24 and F 383 meshes (cells at most +1.1 %); 3 F meshes have 2 fewer: 3 of the 4 builds with a nose repair
  on 7 Nov, which need none now. Node positions moved on most meshes (the same node hash on VC 50 of 782, F 22 of
  782): the band now runs to the trailing edge on the upper side.
- **Cells,** every set at Re 3 × 10⁵, F median (largest): BWB 6.55 (8.87) M, flying wing 5.73 (6.91), cranked 5.51
  (8.14), tapered 5.55 (7.45). The reference wings × 4 Re: F 6.73 M median, largest 10.21 M (BWB reference wing 3 at
  4 × 10⁶; 10.17 M before the band change).

**Conclusion.** The rules mesh every wing at every level: 3,128 of 3,128 builds pass, so the failure rate per level
is below about 0.38 % (rule of three, 95 % confidence), for the surface alone. The family rule holds by construction,
also for the nose, and no family needed a repair. The upper band at 0–100 % c costs at most +1.1 % cells. Not shown:
the volume mesh (Stage 3), the solver, and pyGeo on the full sets (checked on the reference wings only).


## 20. The transition band as an option (9 Nov 2026; decision 81, Study 13)

**What was decided (owner, 9 Nov).** The band is an option, chosen right before the runs together with the solver
(decision 76): on for runs with a transition model (SU2 SST + LM), off for fully turbulent runs (ADflow SA).

**What was built.** `chord.transition_band: true` in `configs/surface.yaml` (the default); `rules(level, config,
band)` and `build_surface` / `build_family(..., band=...)`; `--band on|off` on `python -m cfdauto.mesh` and on
`scripts/screen.py`. Off: the band windows are empty and the band cell is the largest cell, so the ring follows the
nose, trailing-edge and largest-cell rules only; every other rule is the same, and the family rule holds (the asked
nose spacing × 1.3 per step; delivered at the root 1.299–1.300). The mesh name ends in `_noband`; the manifest says
`transition_band: false`; the band check says "option off". The band-on meshes are unchanged (the same node hash).
Tests: the rules with the band off; a VC and C family at Re 10⁶ with fewer ring nodes, the same stations and the
ratio kept (45 tests).

**Study 13.** The 20 reference wings × 4 Re × VC, C, M, F built with the band off (`scripts/screen.py --family
--sets reference --band off`), against the family screen (Study 12, band on); `scripts/band_option.py`,
`data/studies/band_option.json`, `docs/page/band_option.png`.

| Level | Cells on ÷ off, Re 10⁵ | 3 × 10⁵ | 10⁶ | 4 × 10⁶ | Largest on / off [M] | Passed, band off |
| --- | --- | --- | --- | --- | --- | --- |
| VC | 1.09 | 1.79 | 1.87 | 1.87 | 1.02 / 0.57 | 80 of 80 |
| C | 1.08 | 1.81 | 1.88 | 1.88 | 2.19 / 1.21 | 80 of 80 |
| M | 1.09 | 1.82 | 1.90 | 1.90 | 4.69 / 2.59 | 60 of 80 |
| F | 1.08 | 1.83 | 1.91 | 1.91 | 10.21 / 5.60 | 80 of 80 |

- At Re 10⁵ the band cell is about the largest cell, so the band costs almost nothing; from 3 × 10⁵ the bubble is
  short (the 0.10 c floor from local Re 4 × 10⁵) and the band nearly doubles the ring.
- Hardware (wing blocks, the reference wings): with the band off, 78 of 80 C meshes fit the desktop today (28 with
  the band), and 72 of 80 F meshes fit with +36 GB (21 with the band).
- **Weak point: 20 of 320 builds fail with the band off, all of them the BWB reference wings at M** (every Re): the
  tip cap, scaled Jacobian 0.0495 against the limit 0.05 (0.057–0.078 with the band on). The five BWB reference tips
  give the same value. More smoothing does not help (400 to 3,200 sweeps: 0.0495 to 0.0490); the worst cell sits on
  the cap's edge at 88 % of the tip chord, where the section is under 1 mm thick. The same cell is 0.0775 with the
  band on: the coarser ring changes the cap's interior, not its edge spacing there.

**Conclusion.** The option works and is cheap to choose: the band nearly doubles the cells at Re ≥ 3 × 10⁵ and
costs almost nothing at 10⁵. With the band off the BWB tip cap fails at M, so the cap must be fixed before any run
with the band off. Not shown: the full sets with the band off.

**Then decided (owner, 9 Nov).** The band stays on for every run, SA and LM alike: one mesh family for both solvers,
so the SA mesh study also speaks for the LM runs; the price is about 1.8–1.9 × the cells for the SA runs at
Re ≥ 3 × 10⁵ (compute, not accuracy). The switch stays in the code, default on, not used; no cap change (the band-on
caps pass, lowest 0.057 at M). **The surface rules are frozen (decision 82):** a question gets a measurement first; a
rule changes only when a check fails or a solver result shows a problem.
