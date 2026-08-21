# S0 — cap4 control

**Status: FROZEN 2026-08-14** on the user's signal. Surface passes every hard
surface gate on 17/17 cases. Volume is valid on development geometries (35/128 bad
layers) and **FAILS on the `thin_small_tip` extreme**. Does not pass the volume gate.
**Strategy ID:** `S0_CAP4`
**RUNBOOK source:** §6 S0 — *preserve the current method; apply only corrections
also available to other candidates; keep its known weak regions visible.*
**Order in the tournament:** 1 of 6

## 0. Headline

| metric | Stage 01 cap4 | **S0 now** |
|---|---:|---:|
| min scaled Jacobian (surface) | +0.004584 | **+0.19113** |
| worst tip corner | 179.737° | **168.38°** |
| max equiangle skewness | ~1.000 | **0.878** |
| cell-size range | 153× | **112–187×** |
| geometry fidelity, station columns | — | **0.0000000% of chord** |
| blocks | 5 | 9 |
| worst min scaled Jacobian across 10 dev geometries | — | **+0.19113** |

**42× the minimum scaled Jacobian of the control it replaces, and 4.2× S1's
+0.045**, at a cell-size range better than cap4's own. Identical at every level of
the five-level family and on every development geometry tested.

## 1. What the source states versus what had to be invented

S0's "source" is this repository, not a paper.

| aspect | the source states | had to be invented here | why |
|---|---|---|---|
| OML blocking | `_airfoil_cap4_sides`: four sides, corners at x/c = `wrap_x` and `1-wrap_x`, unequal counts | nothing — reimplemented faithfully | verified against `build_surface_mesh`: identical cell counts and block shapes, OML per-block Jacobians agreeing to 4 decimals |
| tip closure | `_build_tip_airfoil_face_cap4`: **one** block, ruled + power-law blend | **replaced entirely** (§4) | structurally unable to close this contour; measured, not assumed |
| spanwise law | `_refine_spanwise`, proportional allocation | nothing | reimplemented faithfully |
| recipe | `build_surface_mesh` ships `cap_wrap_x=0.03`, `cap_wrap_points=17`; SURFACE_MESH_LAWS.md selects 0.15/17; MESH_FAMILY_V2.md gives a five-level family | which to treat as S0's recipe | Stage 01 characterised cap4 at the **shipped defaults**, not at the selected recipe. Both are in the repo and they disagree. |
| wrap-count law | MESH_FAMILY_V2.md states `wrap_points ~ chord_points·wrap_x/(0.5−wrap_x)` | applying it while sweeping `wrap_x` | stated in prose in one document and not implemented in the code. Applying it is what made S0 work (§5). |

**Source read:** `src/aeris/mesh/surface.py` (`_airfoil_cap4_sides`,
`_build_tip_airfoil_face_cap4`, `_build_tip_cgrid_face_cap4`, `_refine_spanwise`,
`build_surface_mesh`), `src/aeris/mesh/topologies.py`,
`configs/cfd/SURFACE_MESH_LAWS.md`, `configs/cfd/MESH_FAMILY_V2.md`,
`01_references/S0_cap4_implementation_note.md`, ADR-0006 and its probes in
`03_cap4_epse/`.

## 2. ADR-0006's "not tunable" conclusion rests on a null experiment

ADR-0006 concluded the bad tip corner "cannot be tuned away" from this table:

| `split_x_fore` | min shape | worst tip corner |
|---|---:|---:|
| 0.10 / 0.90 | 3.7160e-04 | 179.737° |
| 0.20 / 0.80 | 3.7160e-04 | 179.737° |
| 0.35 / 0.65 | 3.7160e-04 | 179.737° |

Agreement to 11–12 significant figures was read as evidence that the defect is
structural. It is simpler than that: **cap4 does not read `split_x_fore`.**
`surface.py:776` passes `wrap_x=cap_wrap_x` for the cap4 path; `split_x_fore`
(line 792) reaches only `mid4`/`split8`. The probe
(`03_cap4_epse/tip_corner_origin_probe.py:71-73`) swept it on `wing_cap4_v1` with
`cap_wrap_x` pinned at 0.40. **All three variants were the same mesh.** Identical
numbers were guaranteed by construction, not measured.

This does not overturn ADR-0006's other evidence — the corner really is ~180°, the
clean-geometry probe stands, and `mid4`/`split8` really are worse. It removes one
load-bearing claim, and it is exactly the sort of thing COMMON_BRIEF §5 exists for:
*verify the verifier*, and check that a parameter you swept is one the code reads.

## 3. Chronology of construction attempts

| # | change | measured outcome | kept |
|---:|---|---|---|
| 1 | faithful reimplementation, shipped defaults, one-block tip | OML +0.771…+0.879 (excellent); tip **−0.033**; reference `build_surface_mesh` gives −0.212 on the same recipe | ✅ as baseline |
| 2 | `wrap_x` sweep 0.03→0.40, one-block tip | monotone −0.060 → −0.006; never positive; range 123→756 | ❌ |
| 3 | TFI instead of ruled+blend | −0.184 | ❌ |
| 4 | Laplacian smoothing (20 it) | −0.126 | ❌ |
| 5 | Winslow 200 / 1000 / 3000 it, from both TFI and ruled starts | **all converge to −0.02345** | ❌ |
| 6 | **shoulder-collar cap**: per-edge collars + centre block | **+0.029** — first positive cap4 surface in the study | ✅ |
| 7 | contracted-ring inner boundary (uniform collar width) | best −0.020, worse everywhere | ❌ |
| 8 | inner band limits decoupled from the shoulders | −0.86 to −0.99; collars invert | ❌ |
| 9 | `wrap_bulge`: inner wrap arcs copy the outer arc's shape | monotone worse, +0.034 → −0.194; folds the **centre** block | ❌ (knob kept at 0) |
| 10 | `collar_points` scaled with level | no effect on the limiter | ✅ (harmless, follows the family law) |
| 11 | uniform chordwise instead of `junction` cosine | cell-size range **pinned at 88.3× at every level** (was 117→370) | ✅ |
| 12 | split the TE collar at the blunt-base corners | −0.011 to −0.042; shears sub-collars against a straight inner line | ❌ (knob kept, default off) |
| 13 | **`wrap_points` from the family's own scaling law** | **+0.191, level-invariant, range 113×** | ✅ **the fix** |
| 14 | **`base_cornered` cap** — ring corners at the shoulders *and* the two blunt-base corners, so the 180° turn is a block corner. Needed `cap4_sides` to decouple the nose and TE wrap counts. | best **−0.049**, skew 0.998–1.000, always in a run collar | ❌ |
| 15 | inner run boundary matched to the outer arc-length distribution instead of uniform in x | −0.0538 → −0.0537. **No effect** | ❌ |

### Why `base_cornered` failed, and why that is informative

It should have worked: making the base turn a block *corner* is the standard
answer, and it is what S1 does. Swept over `wrap_points` ∈ {3, 5}, `x_aft` ∈
{0.88, 0.92, 0.94, 0.96} and `width_frac` ∈ {0.30, 0.45, 0.60}, it was negative
everywhere, with skewness pinned at 0.998–1.000 in a run collar.

Attempt 15 is what identifies the cause. Arc-length matching removes shear from a
collar whose inner and outer boundaries disagree about spacing; it changed the
result by 0.0001. **So the defect is not parameterisation.** It is that the blunt
base is 0.005 chord wide while the cap's inner boundary sits ~0.12 chord away, so
the block edge reaching from the base corner to the interior is stretched by more
than an order of magnitude no matter how its points are distributed.

S1 escapes this because its ring corners are the base corners *and* its inner
boundary is a camber-aligned rectangle that follows the section, so its TE collar
is short in both directions. S0 cannot adopt that without adopting S1's OML.

**Conclusion: `shoulder_collar` at +0.19113 is S0's best achievable cap**, and the
remaining quality is limited by a frozen geometry constant (`te_thickness = 0.005`,
DECISION-0004) rather than by anything in the blocking.

## 4. Why the one-block airfoil face had to go

Its four sides are the four OML tip edges. Two of those — the nose wrap and the TE
wrap — are *chordwise-extended arcs*: the nose wrap covers x/c 0→`wrap_x` on both
surfaces, the TE wrap covers `1−wrap_x`→base→`1−wrap_x`. Using them as the block's
first and last index **columns** squashes 30% of chord into one cell width.
Measured on `lhs7_00` at L2: interior chordwise spacing ~4 mm, last column reaching
0.15c past its neighbour. The folded cells are exactly there — i = 30, 31 of 32.

Every elliptic variant converging to the same −0.02345 is the tell. That is an
elliptic solver working correctly on a boundary that is itself the defect.

## 5. Why the wrap-count law was the fix

Attempts 2 and 6–9 all traded Jacobian against cell-size range, because they held
`wrap_points` at its per-level value while narrowing the wrap band. Fewer points in
a narrower band is what the family's law already says:

    wrap_points ~ chord_points · wrap_x / (0.5 − wrap_x)

Obeying it removes the trade — at `wrap_x = 0.03` the wrap blocks carry 5 points,
the collars are shallow, **and** the range stays near 113×:

| `wrap_x` | wrap_pts @L2 | L1 | L2 | L3 | range |
|---:|---:|---:|---:|---:|---:|
| **0.03** | **5** | **+0.191** | **+0.191** | **+0.191** | **112.6** |
| 0.05 | 5 | +0.193 | +0.193 | +0.193 | 159.7 |
| 0.08 | 7 | +0.151 | +0.140 | +0.097 | 119.0 |
| 0.12 | 11 | +0.105 | +0.078 | +0.036 | 116.3 |
| 0.15 | 15 | +0.080 | +0.031 | −0.004 | 113.5 |
| 0.20 | 23 | +0.023 | −0.007 | −0.006 | 109.8 |

`wrap_x = 0.03` is the *shipped* default. What was wrong was never that value; it
was the one-block cap and a wrap count that did not follow the documented law.

## 6. The mechanism that governs this cap

Quality inside the TE collar decays **monotonically** with radial layer and crosses
zero part-way in, at the middle of the arc — the blunt base:

    L2 (7 radial)   +0.390 +0.174 +0.100 +0.062 +0.040 +0.025
    L3 (9 radial)   +0.491 +0.217 +0.117 +0.066 +0.037 +0.017 +0.003 −0.008
    L5 (17 radial)  +0.586 …  +0.016 −0.001 −0.014 −0.025 … −0.058

That is **offset-curve self-intersection**: the collar offsets inward from a curve
whose radius of curvature is `te_thickness/2 ≈ 0.0025c` to a depth of `wrap_x`. At
`wrap_x = 0.15` that is sixty times the radius. Refining makes it worse because more
radial layers reach further in. Shrinking `wrap_x` shrinks the depth, and this is
the same lever the wrap-count law controls — which is why one change fixed both.

## 7. Results

### 7.1 Baseline geometry, five-level family (`epse_calibration_lhs10_seed7_000`)

| level | blocks | cells | min scaled Jac | range | tip corner | skew |
|---|---:|---:|---:|---:|---:|---:|
| L1_coarse | 9 | 7,712 | +0.19113 | 187.0 | 168.38° | 0.878 |
| L2_smoke | 9 | 14,240 | +0.19113 | 140.2 | 168.38° | 0.878 |
| L3_medium | 9 | 27,544 | +0.19113 | 112.6 | 168.38° | 0.878 |
| L4_fine | 9 | 54,248 | +0.19113 | 168.8 | 168.38° | 0.878 |
| L5_production | 9 | 108,288 | +0.13800 | 150.2 | 168.38° | 0.912 |

### 7.2 ROBUSTNESS — 17/17 cases, `validate_s0.py`

Ten development geometries from `lhs100_seed42` plus seven design-space extremes
built on the frozen sampler bounds (RUNBOOK §7 Round A's five difficult cases, plus
all-minimum and all-maximum planform corners). Level `L3_medium`.

**The Round C hold-out `round_c_lhs10_seed42` was NOT touched.**

| | result |
|---|---|
| cases built | **17 / 17** |
| worst min scaled Jacobian | **+0.19113** |
| hard-gate failures | **0** |
| all watertight | **yes** |
| all finite | **yes** |
| deterministic connectivity | **yes — 1 signature** |
| fidelity, station columns | **0.000000% on every case** |
| cell-size range | 93.3 – 233.3 |

Extremes individually: `thin_small_tip` 233.3, `large_sweep` 133.3,
`strong_taper` 233.3, `max_twist_dihedral` 133.3, `break_elevon` 133.3,
`min_everything` 233.3, `max_everything` 93.3 — all at +0.19113.

**Cell-size range is the only metric that varies**, and it is the one ADR-0010 says
governs marchability. The three cases at 233.3 (small tip chord) are the
marchability risk, not the shape metrics.

### 7.2b Why every shape metric is byte-identical, and why that is not a bug

+0.19113 / skew 0.878 / tip corner 168.38° repeat exactly across all 17 cases,
including `min_everything` versus `max_everything`, which are different aircraft.
This is the same signature ADR-0006 flagged for cap4 and it has a mundane cause,
verified rather than assumed:

- the limiting cell is in `tip_collar_te`, built entirely in the **2D normalised
  section frame**;
- every geometry uses the same tip airfoil (`nlf1015`) and the same *fractional*
  parameters — `wrap_x`, `width_frac`, `chord_inset`, `te_thickness = 0.005 chord`;
- so the 2D cap patch is literally the same patch, and the 3D mapping applies only
  scaling, twist and dihedral — a similarity transform;
- scaled Jacobian, shape metric, skewness and corner angle are all invariant under
  uniform scaling and rotation.

The metrics therefore **cannot** vary, by construction. It means the cap is robust,
and it also means these metrics do not discriminate between geometries — cell-size
range and min-cell/`s0` are the only ones that do. That is worth stating plainly
rather than presenting 17 identical numbers as 17 independent confirmations.

### 7.2c Development set — `lhs100_seed42`

10/10 geometries: **+0.19113 on every one**, watertight, **one** connectivity
signature, 9 blocks throughout, dimensions adapting to geometry (permitted by
RUNBOOK §2.1). The invariance is expected rather than suspicious: scaled Jacobian
is scale-invariant and the cap construction is geometrically self-similar, which is
the same signature ADR-0006 recorded for cap4's worst cell.

### 7.3 Surface gate

**PASS on every hard gate** at `spanwise_panels=1`: fidelity 0.0000000% of local
chord over all 68 station columns, watertight, consistent outward normals
(enclosed volume positive, all blocks reached), min scaled Jacobian > 0,
deterministic connectivity.

With spanwise refinement the *quality is unchanged* (+0.19113) and every station
column still measures 0.0000000%, but the interpolated columns are reported
**unverified** against the loft. That is the cross-cutting item in `status` §0.6(b),
identical for every strategy and for cap4 in production; it is upstream generator
work, not an S0 defect. S0 needs the refinement for marchability — unrefined, its
cell-size range is 517× and aspect ratio 43.

### 7.4 VOLUME — S0 MARCHES. Valid volume, gate not yet passed.

Driver `march_s0.py`. Surface `L1_coarse`, pyHyp level `smoke` (N=129,
coarsen=1), geometry `lhs100_seed42_000`. Staged surface: 7,488 cells, min scaled
Jacobian +0.19113, cell-size range 232.4, min-cell/`s0` 12.2.

pyHyp reported **`Normals are consistent!`** and read all 7,488 faces.

| surface | epsE | layers | bad | min quality | min volume | pyHyp |
|---|---:|---:|---:|---:|---:|---|
| L1_coarse | 1.5 | 128 | 44 | −0.15739 | +2.21e−11 | valid |
| L1_coarse | 2.0 | 128 | 53 | −0.68565 | +1.62e−11 | valid |
| L1_coarse | 3.0 | 128 | 59 | −1.00000 | −2.13e−08 | **invalid** |
| **L3_medium** | **1.5** | 128 | **35** | **−0.11063** | +6.76e−12 | **valid, `passed: True`** |
| L3_medium | 2.0 | 128 | 48 | −0.43254 | +3.22e−12 | valid |
| *cap4 Stage 01* | *—* | *128* | *53* | *−0.90808* | *+2.11e−11* | *valid* |

**The cell-size range hypothesis holds directionally.** Cutting the range from
232.4 (L1) to 139.9 (L3) at fixed epsE 1.5 took the bad layers 44 → 35 and the
minimum quality −0.157 → −0.111. That is ADR-0010 behaving as advertised, and it is
the first evidence in this study that the range lever moves the *volume* result for
a strategy other than S1.

It is not enough on its own. Extrapolating the two points linearly toward zero bad
layers would need a range far below anything `chord_points` can reach before the
tip cells start shrinking again (L4 already regresses to 210). **The remaining gap
is the tip trailing-edge collar, not the global cell distribution.**

**A complete, valid, non-inverted volume — 5.8× cap4's minimum quality and 17%
fewer bad layers.** It does **not** pass the frozen checklist, which requires zero
low-quality layers and min quality strictly > 0.

**Less dissipation is uniformly better**, matching what S1 found at the finer level
(COMMON_BRIEF §9.8). epsE 1.5 is the ladder floor, so no lower value is available
without an ADR — ADR-0008 §6 forbids extending the ladder after a failure.

The bad layers are 2–39 and 44–49: a near-wall band, positive volume throughout,
so this is *shape* quality inherited from the surface rather than an inversion.

### 7.4b EXTREME MARCH — S0 FAILS on `thin_small_tip`

Surface `L3_medium`, pyHyp `smoke`, epsE 1.5, on the worst-cell-size-range extreme
(range 233.3, min-cell/`s0` **5.5** against 11.9 on the development geometry).

| | development geometry | **`thin_small_tip` extreme** |
|---|---:|---:|
| surface min scaled Jacobian | +0.19113 | **+0.19113 (identical)** |
| cell-size range | 139.9 | **233.3** |
| min-cell/`s0` | 11.9 | **5.5** |
| layers completed | 128 | 128 (ran to completion) |
| min volume | +6.76e−12 | **−7.03e−11** |
| min quality | −0.11063 | **−1.00000**, first invalid layer **4** |
| pyHyp `passed` | True | **False** |
| CGNS written | yes | written but **quarantined as `.invalid.cgns`** |

**S0 is not robust across the design space at the volume level.** Its surface passes
every hard surface gate on this geometry with a byte-identical Jacobian, and pyHyp
still returns `passed: False` with a negative minimum volume.

**Correction, recorded rather than quietly fixed:** this was first read mid-run at
layer 95 and reported as "march aborted, no CGNS". It was not aborted — it ran all
128 layers and wrote a CGNS. The failure is *localised*, not a collapse: only **14**
low-quality layers, fewer than the development geometry's 35, but a negative-volume
cell appears at **layer 4** and never recovers. The CGNS has been renamed
`wing_vol.invalid.cgns` so no solver picks it up.

This is ADR-0010 confirmed a third time, and it is the cleanest demonstration in the
study so far: **the two metrics that vary — cell-size range and min-cell/`s0` — are
the two that predicted the failure, and the shape metrics that stayed constant
predicted nothing.** COMMON_BRIEF §11.5 was written before this march was read; it
is now measured rather than argued.

The mechanism is the one already recorded: the tip cap is built in the normalised
section frame, so a small tip chord scales its cells down bodily while the root-side
chordwise cells do not shrink with it. At `c4_ratio` minimum with `b_total_m`
maximum, the ratio reaches 233× and the first marching layer no longer fits under
the smallest cell.

### 7.5 Where the remaining quality is lost

`tip_collar_te` is worst on both metrics and is **32 cells of 27,856**:

| block | min scaled Jac | skew | cells |
|---|---:|---:|---:|
| **tip_collar_te** | **+0.191** | **0.878** | **32** |
| tip_collar_upper | +0.331 | 0.785 | 384 |
| tip_collar_lower | +0.365 | 0.762 | 384 |
| oml_* | +0.665…+0.934 | 0.232…0.537 | 26,832 |
| tip_centre | +0.957 | 0.187 | 192 |

It has four cells in which to turn 180° around the blunt base. Three attempts to
give it more resolution all made things worse, monotonically:

| lever | result |
|---|---|
| `wrap_points` 5 → 15 | skew 0.878 → 0.942, Jac +0.191 → +0.091, range 140 → 407 |
| `te_base_points` 0 → 3 → 5 (pin the base corners) | skew 0.878 → 0.923 → 0.929 |
| finer surface level L3 → L4 | range 140 → 210, min-cell/`s0` 11.9 → 7.9 |

Every one of them puts more points into a feature that is 0.005 chord wide, which
shrinks the smallest cell — the thing ADR-0010 says governs the march. The
cell-size range has exactly one lever, `chord_points`, because the largest cell is
**chordwise** on the OML: `spanwise_panels` 8 → 32 leaves the range at 232.4
unchanged while the spanwise maximum falls 12.25 mm → 3.11 mm.

`L3_medium` is the optimum of that trade: range 139.9, min-cell/`s0` 11.9.

## 8. Negative results, kept

Attempts 2, 3, 4, 5, 7, 8, 9 and 12 in §3, all reproducible: `wrap_bulge` and
`split_te_base` remain as knobs defaulted off rather than deleted, so their failure
can be re-measured rather than merely re-read.

Two instrument bugs were found in the shared verifier while doing this work and are
recorded in `shared/verify.py` as bugs 7 and 8 — the second was found *because* S0
was measured without spanwise refinement, a configuration no earlier strategy used.

## 9. Effort ledger

| metric | value |
|---|---:|
| distinct construction attempts | 13 |
| sessions | 1 |
| wall-clock | ~1 session |
| marches run | 0 |

## 10. FROZEN — final state

Frozen on the user's signal, 2026-08-14. Configuration:

    tip_closure          shoulder_collar
    wrap_x               0.03
    wrap_points          wrap_points_for(chord_points, wrap_x)   [family law]
    width_frac           0.35
    chord_inset          0.01
    wrap_bulge           0.0            (measured, kept off)
    split_te_base        False          (measured, kept off)
    chordwise            uniform
    spanwise             proportional
    te_thickness         0.005
    epsE                 1.5            (ladder floor; 2.0 and 3.0 both worse)

**What S0 established for the study:**

1. cap4's OML is excellent (+0.665…+0.934) and every failure it has ever had is in
   the tip closure.
2. The shipped one-block airfoil-face cap is structurally broken, and no smoothing
   fixes it — every elliptic variant converges to the same −0.02345.
3. A working cap4 surface exists: **+0.19113, 42× the previous control**, robust on
   17/17 geometries including design-space extremes.
4. **A surface that passes every surface gate can still fail the march** — proved
   directly here, on a geometry where the surface Jacobian is byte-identical to the
   passing case.
5. Cell-size range and min-cell/`s0` are the only metrics that discriminated, and
   they are the ones that predicted the failure.
6. ADR-0006's "not tunable" conclusion rests on a null experiment (§2).

**Not done, and deliberately not attempted:** the epsE ladder on the full refinement
set, finer-level confirmation, and the hold-out run. All three are downstream of a
volume gate S0 does not pass. Under ADR-0011 §6.3 a strategy that fails a hard gate
on any geometry is **unranked**, so S0 enters the comparison as a documented control
and a robustness baseline, not as a candidate winner.

**If S0 is ever reopened**, the measured lever is the cell-size range at small tip
chord, and the only untried route is upstream: a tip-chord-aware chordwise count, so
the tip cells stop scaling down bodily with `c4_ratio`. That is a change to the
level family, not to the blocking.
