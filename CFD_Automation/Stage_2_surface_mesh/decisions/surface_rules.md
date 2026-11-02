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

## 5. One point count per side for the whole wing

A structured mesh needs the same ring at every station. The station that needs most nodes (the root,
usually: the largest chord at the highest local Re gets the smallest band cell as a fraction of the
chord) sets the count; every other station puts its spare points in its largest cells first, so no
cell anywhere is coarser than its rule asks. On the BWB reference wing at Re 3 × 10⁵ the tip needs
85 of the root's 295 points per side.

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
passes can fail once the envelope tightens it by 1.15. The solve therefore walks down until every
spacing in [0.77 h, h] passes. A station that still lands above the target after the envelope is
scanned down on its own ring, 10 % a step, and the envelope is applied again (0 repairs on the BWB
and flying-wing reference wings, 2 on the cranked, up to about 30 on NACA 4415 wings, whose built
nose is the most distorted).

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

Counts for the reference wings at Re 3 × 10⁵ (ring nodes × stations): BWB 590 × 82 (C), 766 × 107 (M),
996 × 139 (F); flying wing 426 × 74, 552 × 96, 718 × 125; cranked 392 × 75, 510 × 98, 662 × 127;
tapered 402 × 75, 522 × 98, 678 × 127.

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
size is held over the first four cells, and a station whose turning lands above the target after the
envelope gets a 10 % smaller nose spacing until it passes (0 repairs needed on the reference wings).

## 11. The screen

See `data/studies/screen_C.json` and the figure `docs/screen_C.png`; the numbers are in the Stage 2
summary in the project docs.
