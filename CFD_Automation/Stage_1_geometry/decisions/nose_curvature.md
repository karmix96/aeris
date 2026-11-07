# Nose curvature: raw files against the built sections (decision 64)

Status (7 Nov 2026): merged into the code; the wing sets were rebuilt with this rule and the similarity change
(722 of 722 built, numpy loft). The 6 Nov note that the nose finding was overstated (OPEN_DECISIONS item 75) was
wrong: see "Why the old rule was off".

Date: 7 Nov 2026. Script: `Stage_1_geometry/scripts/nose_curvature.py` (under 30 s; `--database` adds
about 4 min). Data: `Stage_1_geometry/data/studies/nose_curvature.json`. Figure:
`Stage_1_geometry/docs/nose_curvature.png`.

## What was done

One curvature method, the same code for every curve. No frame and no formula is used to read the
nose. Each curve is a smooth spline. Its curvature kappa comes from its own first and second
derivatives, along its own arc length sigma. sigma = 0 is the raw point farthest from the
trailing-edge midpoint (the old leading-edge point); sigma > 0 on the upper side, < 0 on the lower
side. All lengths are in the chord from that point to the trailing-edge midpoint (c).

Curves:

- **raw**: a cubic interpolating spline (not-a-knot) through the raw file points, x and y against
  the cumulative chord length.
- **raw5**: the same with a quintic spline. It shows how much the reference itself depends on the spline.
- **old**: the section by the rule used before (a frozen copy in the script; it matches the old
  `cfdauto` bit for bit on all 2,158 files it builds). LE at the farthest raw point, each side by
  PCHIP in sqrt(x), 101 points per side.
- **new**: the section by `cfdauto` now (`load_airfoil`, see "The change in cfdauto").
- **new101**: the new rule with 101 points per side.
- **apex + PCHIP** (diagnostic): the LE at the apex, but the sides still by PCHIP as before.
- **exact** (NACA 4415 only): the formula (m 0.04, p 0.4, t 0.15, open trailing edge −0.1015,
  thickness normal to the camber line), with exact derivatives, placed on the file by a
  least-squares similarity fit (111 raw points with x < 0.6).

"Built" means the section as the loft holds it: two copies lofted by
`cfdauto.geometry.loft.build_loft` (numpy backend, the one Stage 2 meshes here; pyGeo is not
installed), then the loft's own B-splines in s = sqrt(x/c). An independent polyline check through
`loft.upper/lower` (the way the mesher samples the loft) gives the same turning to 2e-6°.

The mesh number: **T(h)**, the largest turning a cell of arc length h gets near the nose. It is the
largest integral of kappa over a window of arc length h, over all window positions within 3 % c of
arc from the LE point. h = 0.04, 0.10, 0.18, 0.30, 0.50 % c.

Two more checks: the Stage 2 nose solve (tapered training wing 35, station 21), re-run with Stage 2's
own ring code on the wing built by the old and by the new rule; and the whole airfoil database
(2,183 files), built by both rules, at h = 0.04 and 0.18 % c.

## Criterion (written before computing)

If |T_built(h) − T_raw(h)| / T_raw(h) < 5 % for every h on all ten airfoils, decision 64 closes with
no fix: the built nose is faithful at mesh scale. Otherwise a fix is made, measured the same way, and
the change `cfdauto` needs is described.

## Results

**Verdict.** The old rule failed the 5 % test on all ten airfoils, so decision 64 did not close
without a fix. The fix is now in `cfdauto` (the new rule). It passes on all ten (worst −3.9 %, MH 60
at 0.04 % c). On the database a new gate refuses the 14 files whose nose folds back, and the rule
passes on 95.6 % of the 2,143 files both rules build and measure (old rule: 21.0 %).

Table 1. R_min: smallest radius within 3 % c of the LE point [c], with where it sits (sigma, % c).
T differences in % at h = 0.04 / 0.10 / 0.18 / 0.30 / 0.50 % c. "Jump": the curvature of the two
built branches at the LE point, larger over smaller.

| airfoil | points | R_min raw | R_min old | R_min new | T old vs raw | T new vs raw | jump old / new |
|---|---|---|---|---|---|---|---|
| NACA 4415 | 199 | 0.0241 (−0.94) | 0.0018 (0.00) | 0.0241 (−0.83) | +449.2 / +220.7 / +121.0 / +62.4 / +28.2 | +0.1 / +0.1 / +0.0 / +0.0 / −0.0 | 88 / 1.011 |
| NACA 4415, formula | — | 0.0239 (−0.45) | old vs formula: | | +445.6 / +218.6 / +119.6 / +61.6 / +27.9 | new vs formula: −0.6 / −0.6 / −0.6 / −0.5 / −0.3 | — |
| E387 | 61 | 0.0047 (−0.53) | 0.0021 (0.00) | 0.0048 (−0.55) | +89.2 / +53.1 / +34.0 / +29.0 / +15.5 | −2.0 / −0.6 / +0.1 / +0.0 / −0.0 | 33 / 1.004 |
| SD7032 | 61 | 0.0048 (0.00) | 0.0023 (0.00) | 0.0049 (0.00) | +107.6 / +98.5 / +79.2 / +52.8 / +24.7 | −0.6 / +0.0 / −0.0 / +0.0 / −0.0 | 15 / 1.003 |
| MH 104 | 67 | 0.0052 (−0.15) | 0.0046 (0.00) | 0.0054 (−0.15) | +15.1 / +14.5 / +12.5 / +8.9 / +1.6 | −1.5 / −0.1 / +0.3 / +0.0 / −0.0 | 5.3 / 1.078 |
| MH 61 | 68 | 0.0021 (−0.09) | 0.0007 (0.00) | 0.0022 (−0.10) | +23.4 / −3.5 / −6.1 / +7.1 / +3.0 | −1.3 / +0.5 / −0.1 / +0.1 / +0.0 | 16 / 1.018 |
| MH 45 | 67 | 0.0030 (−0.11) | 0.0027 (0.00) | 0.0031 (−0.12) | +14.8 / +15.2 / +12.1 / +5.6 / −2.7 | −1.9 / +0.0 / +0.2 / +0.1 / −0.0 | 6.0 / 1.088 |
| MH 60 | 68 | 0.0028 (−0.11) | 0.0032 (−0.11) | 0.0031 (−0.11) | −8.2 / −3.4 / +0.7 / +1.0 / −0.1 | −3.9 / −0.6 / +0.4 / −0.0 / +0.1 | 1.17 / 1.115 |
| S5010 | 61 | 0.0049 (0.00) | 0.0033 (−0.01) | 0.0051 (0.00) | +51.7 / +50.6 / +44.4 / +31.8 / +14.1 | −1.8 / −0.6 / +0.2 / +0.0 / +0.0 | 4.4 / 1.020 |
| LA2573A | 101 | 0.0252 (−2.24) | 0.0219 (−2.77) | 0.0254 (−2.16) | +14.4 / +13.3 / +11.7 / +9.3 / +5.3 | −0.8 / −0.6 / −0.3 / −0.1 / +0.0 | 1.05 / 1.001 |
| NACA 25118 | 401 | 0.0334 (−0.42) | 0.0267 (0.00) | 0.0334 (−0.33) | +22.6 / +19.0 / +15.0 / +10.3 / +5.3 | −0.0 / +0.0 / +0.0 / −0.0 / +0.0 | 1.60 / 1.001 |

In degrees, NACA 4415 at the five h: raw 0.95 / 2.38 / 4.28 / 7.14 / 11.88°, old 5.23 / 7.63 / 9.47 /
11.60 / 15.24°, new 0.95 / 2.38 / 4.29 / 7.14 / 11.88°, formula 0.96 / 2.40 / 4.31 / 7.17 / 11.92°. So
at the 0.18 % c nose cell of the NACA 4415 reference wings, a cell turned 9.47° where the true shape
turns 4.31°. At the 0.04 % c cell of the BWB, MH 104 turned 4.90° (raw 4.26°, new 4.19°).

### Is the raw file a fair reference?

- **NACA 4415 (199 points): yes.** The file sits on the formula to 4.2 × 10⁻⁶ c (rms 6.0 × 10⁻⁷ c;
  the worst point is the first lower one). The raw spline's T is within 0.7 % of the formula's at every
  h (−0.66 % at 0.04 % c, −0.28 % at 0.50 % c). Smallest radius 0.0241 c against 0.0239 c.
- **The 61-point files (E387, SD7032, S5010): only partly.** A quintic spline through the same points
  gives 13.6–14.9 % less turning at 0.04 % c, 9.7–13.4 % less at 0.10–0.18 % c, 2.9–4.1 % less at
  0.50 % c. These files do not define the nose turning at the smallest cells better than about ±15 %.
  The old rule's error there (+51.7 to +107.6 % at 0.04 % c) was far outside that.
- **MH files:** cubic and quintic differ by 4.0–4.1 % at 0.04 % c, by at most 1.5 % above.
  LA2573A: 1.35 %. NACA 25118 (formula points): 0.0 %.
- **The formula's radius 1.1019 t² = 0.0248 c is not the shape's curvature.** With the thickness
  normal to the camber line (tilted 11.3°), the curve has R = 0.0243 c at the formula's origin and
  0.0239 c at its tightest point, 0.25 % c up the nose. So "formula 0.0248 c" in decision 64 is 2–4 %
  too large.

### Why the old rule was off

- It put the LE at the farthest **raw point**. The curve's own farthest point (the apex) lies between
  raw points, 0.003–0.210 % c of arc away on the ten (NACA 4415: 0.209 % c, on the lower side). At the
  LE point the curve's tangent is already turned by 0.05–19.4° (NACA 4415 4.9°, MH 61 7.1°, S5010
  13.2°, E387 13.8°, SD7032 19.4°).
- The sqrt(x) section forced the tangent square to the chord at the LE point. So that angle was packed
  into the first gap on one side and taken from the other. NACA 4415: radius 0.0018 c on the upper
  branch at the LE point, 0.155 c on the lower branch, a curvature jump of 88 x, where the raw file
  and the formula are round (about 40–42/c). The new rule: a jump of at most 1.115 x (MH 60).
- A second cause: the PCHIP resampling through coarse raw points. With the LE at the apex but PCHIP
  kept, NACA 4415 and NACA 25118 pass, but LA2573A stays +14.4 % off (its tilt is only 0.05°), S5010
  −9.6 %, E387 +6.9 %, SD7032 −6.6 %. With 101 points per side the MH sections stay at −6.3 to
  −9.4 % at 0.04 % c (too few section points for their tight noses, R 0.002–0.005 c).
- The knot rule does not matter: averaging knots change T by at most 0.00005°.
- **The 6 Nov correction (item 75) does not hold.** The one-sided formula on the raw points gave the
  same split as on the built section because the built section passes through those points. The defect
  sat between the LE point and the first raw points, where no formula on the points can see it.
  Measured frame-free, the built split was real, and larger at the LE point than first read
  (0.0018 / 0.155 c against 0.008 / 0.074 c).

### The bump

- The old NACA 4415 section has two curvature bumps on its lower side that the raw file and the
  formula do not have: 77.5/c at −0.755 % c (raw 41.5/c, formula 41.4/c) and 47.3/c at −1.27 % c (raw
  40.9/c). Just before them the lower side is too flat: 6.4/c at the LE point, 11.4/c at −0.2 % c (raw
  40.7/c). There the lower side gets back the 4.9° the LE point took from it. **So the bump was only in
  the built section.** The new section has none: its peaks are 41.6/c at −0.83 % c and 41.2/c at
  −0.08 % c.
- **But the bump is not what makes Stage 2's line flat.** Re-run with Stage 2's own code (tapered
  training wing 35, station 21: chord 0.2498 m, between two NACA 4415 sections, band cell 0.50 % c):
  below 0.2 % c nose spacing the worst node sits 1.9–2.4 % c down the lower side, past the bump. Its
  cells are 0.37–0.45 % c, set by the growth 1.2, not by the nose spacing. There the old curvature
  equals the raw one within about 2 % (about 30/c). With the new rule the line is still flat: 6.0–6.8°
  instead of 6.6–7.4° (worst node 1.8–2.3 % c down, cells 0.36–0.43 % c). So the flat line comes from
  the growth law on a lower side that still curves at 2 % c. It happens on the true airfoil too. The
  window search in the Stage 2 solve stays needed.
- On that station the 10° target is met up to a nose spacing of 0.377 % c with the new rule, against
  0.327 % c with the old one.

### The change in cfdauto

- `sections.airfoil_from_points` (rule D25, same name and arguments):
  1. Drop the raw points a side must not use (`_clean`): repeats, steps back in x near an edge, and
     single typo points. These are the old filters, now applied before the spline, judged in the frame
     of the farthest raw point, as before.
  2. One cubic spline through the rest, chord-length parameter, natural ends. Its ends are the
     trailing edge; natural ends stop an overshoot at a closed one. The nose does not feel this
     (under 1e-14 c).
  3. LE = the spline point farthest from the trailing-edge midpoint (`_apex`: dense sampling between
     the farthest raw point's neighbours, then the root of (P − TE midpoint) · P′ = 0). The frame
     follows as before: TE midpoint, chord along x, unit chord.
  4. Both sides sampled from the spline at the cosine x (`_resample`: bisection on x(t)). As before,
     the last raw interval of each side is stretched in x so that its end lands on x = 1.
- `sections.N_SIDE`: 100 → 200 (201 points per side, 401 per section).
- `verify._unit_chord`: the same frame, found on its own (dense sampling, no shared code). Without
  it, `section_fidelity` reads the frame change as an error: 0.026 % c on the BlendedNet wings, over
  the 0.01 % c test limit. With it: at most 0.00054 % c.
- The nose gate (`sections.nose_hook`, checked in `airfoil_from_points`): see below.
- Not changed: the TE midpoint rule, the TE rule (`open_te`), the loft, the upper/lower order rule.
- XFOIL takes the 401-point sections (one run checked: NACA 4415, Re 3 × 10⁵, 2°).
- Tests: none changed (none encodes the old LE rule; the one copy of it was `verify._unit_chord`).
  One added: `test_nose_hook_refused_with_reason` (`Stage_1_geometry/tests/geometry/test_build.py`).
  Stage 1: 173 passed, 13 skipped (pyGeo not installed). Stage 2: 14 passed. Before the change:
  172 passed and 13 skipped, and 14 passed.
- The wing sets were not rebuilt. Every geometry hash changes at the rebuild.

### The nose gate

A section is refused when the cubic spline in s = sqrt(x) that the loft puts through its points
curves back harder than −1000/c anywhere within 3 % c of arc from its leading edge, on either side.
The refusal is a `ValueError` with the reason, for example "rc0864c: refused, the nose folds back
(curvature −7.88e+06/c on the lower side, 0.123 % c of arc from the leading edge; limit −1000/c within
3 % c): the nose is too sharp or too flat for 201 points per side (decision 64)". `build` turns it
into a "validity" refusal and writes only `refusal.json`, the same way as for an impossible vector. A
round nose is far from the limit: the smallest nose curvature on the ten study airfoils and the 14
named sections is +1.9/c (S5010 at 101 points per side) to +19.9/c. On the database the gate refuses
14 files, exactly the 14 hooks found without it (DP2,00-8,55_DS, PW51i, PW75, e193gu, eh2510, hm51,
nm-classic, nm-classic-saumon, nm18-s, nm19-s, rc0864c, sp4721bs, tp100plank, wsa828). No other file
changes: the other 2,146 rows of the database table, the ten study airfoils and the Stage 2 line are
the same as before the gate.

### The whole airfoil database

- 2,183 files on the search path (2,176 in the AERIS database, 7 local). 23 cannot be read
  (x outside [0, 1.5]: not unit chord), for both rules.
- Builds: old rule 2,158 (2 fail in PCHIP, "x must be strictly increasing": ah93w480b, mh112); new
  rule 2,146 (14 refused by the nose gate, no other failure).
- Measured by both rules: 2,143. One more file, nm26-3smoothed, gives no turning: two note lines after
  its points carry numbers, and `read_dat` takes them as points. Both rules build garbage there. That
  is a reader problem, not fixed here.
- 5 % test at h = 0.04 and 0.18 % c: old rule 451 pass (21.0 %), new rule 2,048 pass (95.6 %). Worst
  miss per file: old median 15.8 %, 90 % 119 %, 99 % 1,366 %; new median 0.52 %, 90 % 2.44 %,
  99 % 15.1 %, max 216 %.
- **Hooks** (curvature below −1000/c within 3 % c of the LE: a tiny loop or fold at the nose): the old
  rule builds 45. Without the gate the new rule had 14: it removed 37 and added 6 (DP2,00-8,55_DS,
  e193gu, eh2510, hm51, rc0864c, tp100plank); 8 hook under both (PW51i, PW75, nm-classic,
  nm-classic-saumon, nm18-s, nm19-s, sp4721bs, wsa828). The cause: very sharp or flat-faced noses whose
  features sit within 2–3 section points of the LE in s = sqrt(x), where the loft's cubic in s
  overshoots. With the gate none is built. Before the gate they held the ten worst misses (up to
  +7,154 %, sp4721bs).
- The 95 new-rule failures, none a hook. In 36 the cubic and quintic references differ by 5 % or more
  (the file cannot settle T at that scale). In 7 more the new section is within 5 % of the quintic.
  The other 52 are mostly tight noses missed at 0.04 % c. Over the 95: 76 fail at 0.04 % c only;
  median miss 9.1 %.
- The worst ten now: sp4721la +216 % (old +50 %), fx77w258 +138 % (old +75 %), fx77w270 +103 % (old
  +74 %), fx77w270s +96 % (old +85 %), ah88k136 −49 % (old −56 %), phonix10 −36 % (old −51 %),
  mb7136rev −34 % (old −37 %), tp29-9 +33 % (old +2,531 %), tp29-8 +32 % (old +2,382 %), mjp712rev
  −31 % (old −26 %). In the first five the cubic and quintic references differ by 12–17 %.
- Crossing surfaces (upper below lower anywhere inside): old 4, new 4, the same files (hm50, ms3,
  ms4, ms5; the crossing is in the files). In a first pass with not-a-knot spline ends the new rule
  had 7 more, all near a closed trailing edge (vr8: −0.10 % c at x 0.991); the natural ends removed
  them.
- **Every section the configs name passes** (the four families and the published wings: 13 files and
  the NACA 25118 formula). Worst 3.89 % (MH 60). None hooks, none crosses. Under the old rule 9 of the
  13 files failed.

### Side effects

- **The LE moves** (arc from the farthest raw point to the apex): median 0.046 % c, 90 % 0.28 % c,
  99 % 0.71 % c, max 1.69 % c. Over 0.1 % c: 711 files; over 0.2 % c: 366; over 0.5 % c: 63.
- **The chord line turns** by about the same angle (in radians, the move over the chord): |turn|
  median 0.027°, 90 % 0.16°, 99 % 0.40°, max 0.96°. Over 0.05°: 777 files; over 0.1°: 428; over
  0.3°: 58. A section's zero-angle line moves by that much. The largest moves are on coarse files with
  33–41 points (naca23024 1.69 % c and −0.96°, goe777, v43015, naca23021, usa34, goe217, goe518,
  goe570), where the nose between raw points is long.
- On the named sections: NACA 4415 0.209 % c and +0.120°, NACA 4412 0.155 % c and −0.089°, S5010
  0.126 % c and −0.072°, all others under 0.05 % c and 0.03°.
- Every geometry hash changes. Sections have 401 points instead of 201.

### Limits

- pyGeo was not run; the knot check says it should give the same.
- The gate refuses 14 database files (none is used). Their noses would need more section points
  near the leading edge; not done.
- On coarse files the reference itself is uncertain (cubic against quintic up to 15 % at 0.04 % c).
- The trailing-edge end was studied only for crossings. The similarity branch changes the TE
  thickness next.

## Conclusion

Decision 64 is settled with a fix. The old rule put the leading edge at the farthest raw point and
forced the tangent square there. On NACA 4415 this raised the largest turning per cell by +28 to
+449 %, and the 5 % test failed on all ten airfoils. The new rule in `cfdauto` puts the leading edge
at the apex of one cubic spline through the raw points, samples both sides from that spline, and
holds 201 points per side. It passes on all ten (worst −3.9 %) and on 95.6 % of the database files
both rules build (old rule 21.0 %). A gate refuses a section whose nose folds back: 14 database files,
none of them used, and no other file changes. Every section the configs name passes. The lower-side bump of NACA 4415 is gone, but Stage 2's flat
line stays: it comes from the growth law. The cost: every hash changes, the leading edge moves (median
0.046 % c, max 1.69 % c) and the chord line turns (median 0.027°, max 0.96°, over 0.1° on 428 files,
at most 0.12° on the named sections). The wing sets are rebuilt once, after this and the similarity
change are merged.
