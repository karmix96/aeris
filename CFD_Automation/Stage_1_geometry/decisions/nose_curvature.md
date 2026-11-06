# Nose curvature: raw files against the built sections (open decision 64)

Date: 7 Nov 2026. Script: `Stage_1_geometry/scripts/nose_curvature.py` (under 30 s).
Data: `Stage_1_geometry/data/studies/nose_curvature.json`. Figure: `Stage_1_geometry/docs/nose_curvature.png`.

## What was done

One curvature method, the same code for every curve. No frame and no formula is used to read the
nose. Each curve is a smooth spline. Its curvature kappa comes from its own first and second
derivatives, along its own arc length sigma. sigma = 0 is the Stage 1 leading-edge point (rule D25:
the raw point farthest from the trailing-edge midpoint); sigma > 0 on the upper side, < 0 on the lower
side. All lengths are in the D25 chord of the raw file (c).

Curves:

- **raw**: a cubic interpolating spline (not-a-knot) through the raw file points, x and y against
  the cumulative chord length.
- **raw5**: the same with a quintic spline. It shows how much the reference itself depends on the spline.
- **built**: the Stage 1 section as the loft holds it. `load_airfoil(name)`, two copies lofted by
  `cfdauto.geometry.loft.build_loft` (numpy backend, the one Stage 2 meshed here; pyGeo is not
  installed), then the loft's own B-splines in s = sqrt(x/c). An independent polyline check through
  `loft.upper/lower` (the way the mesher samples the loft) gives the same turning to 0.004°.
- **built_avg**: the same points with averaging knots (the other usual knot rule).
- **exact** (NACA 4415 only): the formula (m 0.04, p 0.4, t 0.15, open trailing edge −0.1015,
  thickness normal to the camber line), exact derivatives, placed on the file by a least-squares
  similarity fit (111 raw points with x < 0.6).
- **fix** (prototype, in the script only): the LE at the apex of the raw spline, both sides sampled
  from that spline; 101 points per side (as now) and 201 points per side.
- **apex + PCHIP** (diagnostic): the LE at the apex, but the sides still resampled by PCHIP as now.

The mesh number: **T(h)**, the largest turning a cell of arc length h gets near the nose. It is the
largest integral of kappa over a window of arc length h, over all window positions within 3 % c of
arc from the LE point. h = 0.04, 0.10, 0.18, 0.30, 0.50 % c.

Stage 2 check: the nose solve of the Stage 2 page (tapered training wing 35, station 21), re-run with
Stage 2's own ring code, with the built and with the fixed NACA 4415 (swapped in at run time).

## Criterion (written before computing)

If |T_built(h) − T_raw(h)| / T_raw(h) < 5 % for every h on all ten airfoils, decision 64 closes with
no fix: the built nose is faithful at mesh scale. Otherwise a fix is tried inside the study script
only (never in `cfdauto/`), measured the same way, and the change `cfdauto` would need is described.

## Results

**Verdict: decision 64 does not close without a fix.** The built nose fails the 5 % test on all ten
airfoils. The prototype fix passes on all ten with 201 points per side.

Table 1. R_min: smallest radius within 3 % c of the LE point [c], with where it sits (sigma, % c).
"Built R at LE": the radius of each built branch at the LE point itself. T differences in %.

| airfoil | points | first raw gaps up / lo [% c] | R_min raw (at) | R_min built (at) | R_min fix 201 (at) | built R at LE, up / lo | T built vs raw, h = 0.04 / 0.10 / 0.18 / 0.30 / 0.50 % c | fix vs raw, worst: 101 / 201 points |
|---|---|---|---|---|---|---|---|---|
| NACA 4415 | 199 | 0.203 / 0.611 | 0.0241 (−0.94) | 0.0018 (0.00) | 0.0241 (−0.83) | 0.0018 / 0.1553 | +449.2 / +220.7 / +121.0 / +62.4 / +28.2 | −0.1 / +0.1 |
| NACA 4415, formula | — | — | 0.0239 (−0.45) | — | — | — | built vs formula: +445.6 / +218.7 / +119.6 / +61.6 / +27.9 | fix 201 vs formula: −0.6 |
| E387 | 61 | 0.855 / 0.534 | 0.0047 (−0.53) | 0.0021 (0.00) | 0.0048 (−0.55) | 0.0021 / 0.0683 | +89.2 / +53.1 / +34.0 / +29.0 / +15.5 | −2.5 / −2.0 |
| SD7032 | 61 | 0.689 / 0.702 | 0.0048 (0.00) | 0.0023 (0.00) | 0.0049 (+0.00) | 0.0352 / 0.0023 | +107.6 / +98.5 / +79.2 / +52.8 / +24.7 | −2.7 / −0.6 |
| MH 104 | 67 | 0.160 / 0.147 | 0.0052 (−0.15) | 0.0046 (0.00) | 0.0054 (−0.15) | 0.0240 / 0.0046 | +15.1 / +14.5 / +12.5 / +8.9 / +1.6 | −6.3 / −1.5 |
| MH 61 | 68 | 0.110 / 0.095 | 0.0021 (−0.10) | 0.0007 (0.00) | 0.0022 (−0.10) | 0.0007 / 0.0102 | +23.4 / −3.5 / −6.1 / +7.1 / +3.0 | −7.2 / −1.3 |
| MH 45 | 67 | 0.120 / 0.108 | 0.0030 (−0.11) | 0.0027 (0.00) | 0.0031 (−0.12) | 0.0161 / 0.0027 | +14.8 / +15.2 / +12.1 / +5.6 / −2.7 | −7.1 / −1.9 |
| MH 60 | 68 | 0.120 / 0.106 | 0.0028 (−0.11) | 0.0032 (−0.11) | 0.0031 (−0.11) | 0.0056 / 0.0047 | −8.2 / −3.4 / +0.7 / +1.0 / −0.1 | −9.4 / −3.9 |
| S5010 | 61 | 0.704 / 0.668 | 0.0049 (0.00) | 0.0033 (−0.01) | 0.0051 (+0.00) | 0.0144 / 0.0033 | +51.7 / +50.6 / +44.4 / +31.8 / +14.1 | −3.9 / −1.8 |
| LA2573A | 101 | 0.758 / 0.757 | 0.0252 (−2.24) | 0.0219 (−2.77) | 0.0254 (−2.16) | 0.0332 / 0.0350 | +14.4 / +13.3 / +11.7 / +9.3 / +5.3 | −1.5 / −0.8 |
| NACA 25118 | 401 | 0.211 / 0.210 | 0.0334 (−0.42) | 0.0267 (0.00) | 0.0334 (−0.33) | 0.0427 / 0.0267 | +22.6 / +19.0 / +15.0 / +10.3 / +5.3 | −0.0 / −0.0 |

In degrees, NACA 4415: raw 0.95 / 2.38 / 4.28 / 7.14 / 11.88°, built 5.23 / 7.63 / 9.47 / 11.60 / 15.24°,
formula 0.96 / 2.40 / 4.31 / 7.17 / 11.92°. So at the 0.18 % c nose cell of the NACA 4415 reference
wings, a built cell turns 9.47° where the true shape turns 4.31°. At the 0.04 % c cell of the BWB,
MH 104 turns 4.90° built against 4.26° raw.

### Is the raw file a fair reference?

- **NACA 4415 (199 points): yes.** The file sits on the formula to 4.2 × 10⁻⁶ c (rms 6.0 × 10⁻⁷ c;
  the worst point is the first lower one). The raw spline's T is within 0.7 % of the formula's at every
  h (−0.66 % at 0.04 % c, −0.28 % at 0.50 % c). Smallest radius 0.0241 c against 0.0239 c.
- **The 61-point files (E387, SD7032, S5010): only partly.** A quintic spline through the same points
  gives 13.6–14.9 % less turning at 0.04 % c, 9.7–13.4 % less at 0.10–0.18 % c, 2.9–4.1 % less at
  0.50 % c. These files do not define the nose turning at the smallest cells better than about ±15 %.
  The built error there (+51.7 to +107.6 % at 0.04 % c) is still far outside that.
- **MH files:** cubic and quintic differ by 4.0–4.1 % at 0.04 % c, by at most 1.5 % above.
  LA2573A: 1.35 %. NACA 25118 (formula points): 0.0 %.
- **The formula's radius 1.1019 t² = 0.0248 c is not the shape's curvature.** With the thickness
  normal to the camber line (tilted 11.3°), the curve has R = 0.0243 c at the formula's origin and
  0.0239 c at its tightest point, 0.25 % c up the nose. So "formula 0.0248 c" in decision 64 is 2–4 %
  too large.

### Why the built nose is off

- Rule D25 puts the LE at the farthest **raw point**. The curve's own farthest point (the apex) lies
  between raw points, 0.003–0.210 % c of arc away (NACA 4415: 0.209 % c, on the lower side). At the LE
  point the curve's tangent is already turned by 0.05–19.4° (NACA 4415 4.9°, MH 61 7.1°, S5010 13.2°,
  E387 13.8°, SD7032 19.4°).
- The sqrt(x) section forces the tangent square to the chord at the LE point. So that angle is packed
  into the first gap on one side and taken from the other. NACA 4415: radius 0.0018 c on the upper
  branch at the LE point, 0.155 c on the lower branch. The curvature jumps 88 x across the LE point,
  where the raw file and the formula are round (about 40–42/c).
- A second cause: PCHIP resampling through coarse raw points. With the LE at the apex but PCHIP
  kept, NACA 4415 and NACA 25118 pass, but LA2573A stays +14.4 % off (its tilt is only 0.05°), S5010
  −9.6 %, E387 +6.9 %, SD7032 −6.6 %. The MH sections stay at −6.3 to −8.2 % at 0.04 % c (too few
  section points, see the fix).
- The knot rule does not matter: averaging knots change T by at most 0.0007°.
- **The 6 Nov correction (item 75) does not hold.** The one-sided formula on the raw points gave the
  same split as on the built section because the built section passes through those points. The defect
  sits between the LE point and the first raw points, where no formula on the points can see it.
  Measured frame-free, the built split is real, and larger at the LE point than first read
  (0.0018 / 0.155 c against 0.008 / 0.074 c).

### The bump

- The built NACA 4415 section has two curvature bumps on its lower side that the raw file and the
  formula do not have: 77.5/c at −0.755 % c (raw 41.5/c, formula 41.4/c) and 47.3/c at −1.27 % c (raw
  40.9/c). Just before them the built lower side is too flat: 6.4/c at the LE point, 11.4/c at
  −0.2 % c (raw 40.7/c). There the lower side gets back the 4.9° the LE point took from it.
  **So the bump is only in the built section.**
- **But the bump is not what makes Stage 2's line flat.** Re-run with Stage 2's own code (tapered
  training wing 35, station 21: chord 0.2498 m, between two NACA 4415 sections, band cell 0.50 % c):
  below 0.2 % c nose spacing the worst node sits 1.9–2.4 % c down the lower side, past the bump. Its
  cells are 0.37–0.45 % c, set by the growth 1.2, not by the nose spacing. There the built curvature
  equals the raw one within about 2 % (about 30/c). With the fix the line is still flat: 6.0–6.8°
  instead of 6.6–7.4°. So the flat line comes from the growth law on a lower side that still curves at
  2 % c. It would happen on the true airfoil too. The window search in the Stage 2 solve stays needed.
- On that station the 10° target is met up to a nose spacing of 0.377 % c with the fix, against
  0.327 % c with the built section.

### The fix (prototype, in the script only)

1. Spline the raw points (cubic, chord-length parameter).
2. Put the LE at the spline point farthest from the trailing-edge midpoint (the apex). There the
   tangent is square to the chord, as the sqrt(x) section assumes.
3. Sample both sides from that spline at the cosine x (no PCHIP).
4. Use 201 points per side instead of 101.

With steps 1–3 and 101 points per side: passes on six of ten. It misses only at h = 0.04 % c, on
MH 104 (−6.3 %), MH 61 (−7.2 %), MH 45 (−7.1 %) and MH 60 (−9.4 %), whose tight noses (R 0.002–0.005 c)
fall between the first section points. With 201 points per side: passes on all ten. Worst −3.9 %
(MH 60 at 0.04 % c), all others within ±2.0 %. NACA 4415 against the formula: −0.6 % to −0.3 %.

Side effects: the LE moves by up to 0.21 % c along the nose, and the chord turns by up to 0.12°
(NACA 4415 +0.120°, E387 +0.119°, SD7032 −0.111°, S5010 −0.072°, the others under 0.03°). So the
section's zero-angle line moves by up to 0.12°. Every geometry hash changes.

### What `cfdauto` would need (not done here; the owner decides)

- `sections.airfoil_from_points`: drop duplicate and suspect raw points first (the typo filter);
  spline the raw points by chord length; LE = the spline apex (the root of (P − TE midpoint) · P′ = 0
  between the raw neighbours of the farthest raw point); the frame from that LE.
- `sections._resample`: sample each side of that spline at the cosine x (root of x(t) = x_i)
  instead of PCHIP in sqrt(x); keep the trailing-edge end rule (last point at x = 1).
- `sections.N_SIDE`: 100 → 200 (or a nose-clustered x with the same first spacing). The loft keeps
  s = sqrt(x/c).
- Before adoption: run it on the whole airfoil database (about 2,180 files): apex found between the
  neighbours, x increasing on each side, no new loops at the trailing edge. Then new hashes and the
  Stage 1 checks.

### Limits

- Built = the numpy loft. pyGeo was not run; the knot check says it should give the same.
- The fix's trailing-edge end was not studied (it is clamped).
- On the 61-point files the reference is uncertain by about 15 % at 0.04 % c (see above). On E387 the
  built section and the quintic spline both show a small concave spot on the lower side (−11/c at
  −1.23 % and −1.92 % c); the cubic spline does not. 61 points cannot settle it.

## Conclusion

Decision 64 stays open: it does not close without a fix. Measured one way on every curve, the built
nose is not faithful at mesh scale. The largest turning per cell differs from the raw file by +28 to
+449 % on NACA 4415 and fails the 5 % test on all ten airfoils, worst at the smallest cells. The cause
is in Stage 1: the LE is put at the farthest raw point, not at the curve's apex, and the section then
forces a square tangent there; with the apex alone, the PCHIP resampling still leaves 6.6–14.4 % on the
coarse files. The lower-side bump of
NACA 4415 is a built artifact, but Stage 2's flat line comes from the growth law, not from the bump.
The prototype fix (apex LE, both sides from one spline, 201 points per side) brings all ten within
3.9 % of the raw file and NACA 4415 within 0.6 % of the formula. It changes every hash, moves the LE by
up to 0.21 % c and turns the chord by up to 0.12°. It should go into `cfdauto` before the pyGeo
`build --all`, after a run over the whole database.
