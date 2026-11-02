# Stage 2 decisions — the surface mesh (2 Nov 2026)

What was decided while building the surface mesher, why, and what the first screen showed.
The values are in `configs/surface.yaml`; the rules table is in `README.md`.

## 1. One spacing tool for everything

The ring (around the section) and the stations (along the span) use the same three steps: a target
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

## 10. Finding for Stage 1: the nose of the built sections is not round

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
numpy twin of the loft; the pyGeo run is still owed.

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
