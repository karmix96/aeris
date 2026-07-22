# Surface Mesh Laws — cap4 wing topology (BWB segmented v1)

**Status: SKELETON, not yet populated.** This document exists so every
"law" below is filled in from a real `surface_option_sweep_report.json`
(20 fixed Latin-hypercube geometries, one-factor-at-a-time per option —
see `configs/cfd/RUNBOOK.md` section 5), never a single-baseline guess.
Each entry: the tested range, the observed safe range, the failure mode
outside it, and the report file it came from (so every law is traceable
back to raw data, not asserted).

## What's already known (single-baseline, pre-dates this format)
From `src/aeris/mesh/DSE_READINESS.md` (2026-07-17), on ONE baseline
geometry (seed 100), not yet generalized across a design-space sample:
- `cap_wrap_x`: 0.03 fails (single cell absorbs both TE corner turns at the
  root); 0.015 fixed it. **Needs the 20-geometry sweep to confirm this
  holds design-space-wide, not just for seed 100.**
- `cap_wrap_points`: 9 -> 143 deg corner fold (fails); 17 is the validated
  value.
- `cap_width_frac`: 0.15 -> 1.5e-7 sliver cells + NaN at march layer 5
  (fails); 0.5 is the validated value.
- `split_x_fore`, `points_per_side`, `spanwise_panels`: the cap4 family
  (smoke/fine/production presets) already validates one specific ratio
  progression, not an independent sweep of `split_x_fore` alone.

## Laws (fill in per option once its sweep report exists)

### topology (`sweep_topology/surface_option_sweep_report.json`)
- Tested: cap4, mid4, split8
- Safe range / verdict: _pending_
- Failure mode outside safe range: _pending_

### split_x_fore (`sweep_split_x_fore/...`)
- Tested: 0.10, 0.15, 0.20, 0.25, 0.30, 0.35
- Safe range: _pending_
- Failure mode: _pending_

### points_per_side (`sweep_points_per_side/...`)
- Tested: 25, 33, 49, 65, 97
- Safe range: _pending_
- Failure mode: _pending_

### spanwise_panels (`sweep_spanwise_panels/...`)
- Tested: 2, 4, 8, 12, 16
- Safe range: _pending_
- Failure mode: _pending_

### tip_radial_points (`sweep_tip_radial_points/...`)
- Tested: 3, 9, 17
- Safe range: _pending_
- Failure mode: _pending_

### cap_width_frac (`sweep_cap_width_frac/...`)
- Tested: 0.15, 0.3, 0.5
- Safe range: _pending_ (prior single-baseline: 0.15 fails, 0.5 works)
- Failure mode: _pending_

### cap_wrap_points (`sweep_cap_wrap_points/...`)
- Tested: 9, 17, 25
- Safe range: _pending_ (prior single-baseline: 9 fails, 17 works)
- Failure mode: _pending_

### cap_wrap_x (`sweep_cap_wrap_x/...`)
- Tested: 0.015, 0.03
- Safe range: _pending_ (prior single-baseline: 0.03 fails, 0.015 works)
- Failure mode: _pending_

## The n=10 volume-march failure mode — LOCALIZED AND EXPLAINED (2026-07-22)

Previously logged as "3 of 10 geometries fail the pyHyp march, cause
unknown (not `split_ratio`)". It is no longer unknown. Re-derived from the
retained artifacts in `data/cfd_cases/mesh_robustness_n10_cap4/` — no new
compute — by recomputing signed cell volumes from the written CGNS
(`aeris.cfd.meshing.volume_audit`, added 2026-07-22).

**Established facts.**

1. **pyHyp did not fail on any of the 10.** All ten ran to completion —
   exit 0, all 129 layers, `pyHyp done`, final min quality ~0.405 and
   positive final min volume. The "70% success rate" was AERIS's verdict,
   not pyHyp's.
2. **7 of 10 written meshes are geometrically clean** (zero negative-volume
   cells out of 1,703,936). 3 contain inverted cells.
3. **Every inverted cell in all 3 failures is in the same place**:

   | seed | inverted cells | fraction | block | i (chordwise) | j (spanwise) | layers |
   |---|---|---|---|---|---|---|
   | 1 | 53 | 0.0031% | domain.00003 | 7-8 | 0 (root) | 25-51 |
   | 3 | 100 | 0.0059% | domain.00003 | 6-9 | 0 (root) | 15-57 |
   | 4 | 14 | 0.0008% | domain.00003 | 7-8 | 94-95 (tip) | 1-6 |

   `domain.00003` is the aft block that wraps the trailing edge; i=7-8 is
   exactly the blunt-TE crown (verified against wall coordinates — the
   failing nodes sit at x = root chord, y ≈ 0). **The defect is always the
   blunt-TE crown cells at a spanwise extremity** — the root symmetry plane
   or the tip-cap junction, i.e. where the marching front has no spanwise
   relief on one side. Never mid-span, never elsewhere on the section.
4. **Extent is tiny**: 14-100 cells out of 1.7M, spanning 2-4 chordwise
   cells at a single spanwise station.

**What this rules out.**

- *Not* a global geometry-space limit. The march is sound everywhere except
  one topological corner.
- *Not* predicted by the existing surface QC gate.
  `min_scaled_corner_jacobian` is **0.01674 for 9 of the 10 geometries** —
  identical to five significant figures, because it is measured at a
  topology-fixed cap corner whose shape barely depends on the sampled
  planform. It cannot discriminate and must not be relied on as a
  pre-march predictor.
- *Not* explained by `max_adjacent_normal_angle_deg` either: the failures
  (72.9-80.9 deg) sit inside the passing range (71.8-92.8 deg), and the
  geometry with the *worst* angle (seed 6, 92.8 deg) passed.
- *Not* trailing-edge thickness: failures (0.00226-0.00350 at the root) lie
  inside the passing range (0.00217-0.00255).

**Second defect found in the same data.** Seed 6 was scored `ok` while
carrying **30 consecutive layers of negative scaled quality** (min -0.373,
layers 3-32). It has zero inverted cells, so the mesh is not folded — but
it is severely skewed, and the campaign recorded it identically to a
pristine mesh. Under the documented policy (negative quality with positive
volume = warning) that is technically correct and practically misleading:
the `quality_warning` boolean never reaches the campaign summary. Fixed by
carrying `low_quality_layers` and the audit classification onto every
campaign row.

### RESOLVED: the cause is `epsE`, and the default was too high

Controlled re-march experiment, 2026-07-22 (`aeris cfd campaign remarch`,
15 marches). The three failing surface meshes were held byte-identical and
only one pyHyp option was varied at a time, so every difference below is
attributable to that option alone. The control re-marched to the *exact*
original failure — 53 / 100 / 14 inverted cells at identical block, index
and layer ranges — confirming the pipeline is deterministic.

| variant | clean | total inverted cells |
|---|---|---|
| `baseline` (`epsE=6.0`, the shipped default) | 0/3 | 167 |
| `theta=5.0` | 0/3 | 184 |
| `nConstantStart=10` | 0/3 | 164 |
| `cMax=0.25` | 0/3 | 161 |
| **`eps_lo` (`epsE=3.0`, `epsI=6.0`)** | **2/3** | **2** |

**Law (cap4 wing topology, blunt TE): explicit smoothing `epsE` must be
LOWERED, not raised, to eliminate trailing-edge cell inversion.** The
default `epsE=6.0` *causes* the defect. Halving it to 3.0 clears two of
the three failures outright and reduces the third from 14 inverted cells
to 2. `theta`, `nConstantStart` and `cMax` have no useful effect.

Confirmed monotone on a single axis — seed 4, inverted cells vs `epsE`:

    epsE = 3.0  ->   2 cells
    epsE = 6.0  ->  14 cells   (default)
    epsE = 12.0 ->  79 cells, spreading from layers 1-6 to layers 1-41

This is a dose-response, not a spot check: more explicit smoothing
monotonically produces more inversion at the blunt-TE crown. The physical
reading is that the smoothing operator drags the TE crown nodes laterally
where the marching front has no spanwise relief (root symmetry plane or
tip-cap junction), folding cells that would otherwise march cleanly.

**Not yet closed:** seed 4 still has 2 inverted cells at `epsE=3.0`. The
next step is `epsE=1.5` and `epsE=2.0` (~4 min, seed 4 only) to find the
floor, and to check the lower bound does not degrade quality elsewhere —
`epsE` exists to keep the front smooth, so it cannot go to zero for free.
Once a value clears all three, it becomes the curated cap4 default and the
option sweeps can run against a sound baseline.

---

# Surface-mesh strategy study — mid4 (2026-07-22)

Fixed baseline wing (`configs/geometry/baseline_bwb_25.yaml`, seed 100,
pinned bounds) so every difference is the recipe, not the shape. Surface
only, ~1 s per candidate. 54 strategies over three rounds; scripts in
`scripts/surface_strategy_round{1,2,3}*.sh`.

`mid4` was selected over `cap4` on visual inspection (Mike, round 1).

## Law 1 — score the OML and the tip cap separately

Whole-mesh extrema are meaningless here. The tip collar's near-degenerate
skewness (0.91-0.98) swamps every aggregate, so a strategy that genuinely
improves the wing surface scores identically to one that does nothing. Per
block on the round-1 `mid4` pick: `oml_1`/`oml_3` already *passed* the
industry targets (jac 0.22, skew 0.48, AR 8.3, angle 1-8 deg) while
`oml_2` — the trailing-edge block — carried jac 0.076, AR 25, growth 1.98,
angle 121 deg. Three of four OML blocks were fine all along.

## Law 2 — the wing surface and the tip cap are independent

Across round 2, every tip parameter (`tip_radial_points`,
`tip_inner_scale`, `tip_dome_scale`, `tip_conformal_ring`) left the OML
numbers **identical to four decimals** (jac 0.0757, AR 25.0). They can be
tuned separately without interaction.

## Law 3 — spanwise resolution is the dominant OML lever, and it is monotone

`spanwise_panels` at fixed 49 chordwise points, mid4:

    panels    8      16      24      32
    jac    0.076   0.151   0.224   0.296
    AR      25.0    12.6     8.5     6.4

The shipped recipe used 8. It is simply spanwise-starved. This single
change takes the OML from failing to passing the Jacobian target.

## Law 4 — `tip_radial_points` is the dominant tip lever, also monotone

    points     5       9      13      17
    tip jac 0.016   0.033   0.048   0.060
    tip AR    75.2    47.3    34.3    26.8

`tip_inner_scale=0.70` improves tip AR further (47 -> 38 at 9 points).

## Law 5 — two tip options are dead ends

* `tip_conformal_ring=true`: **degenerate**, tip skew 1.000, jac 0.0003,
  fails QC outright. Do not use.
* `tip_dome_scale`: moves tip skew by 0.006 (0.948 -> 0.942). It is not
  the tip fix it was hoped to be, and it is incompatible with coarsen=4.

## Law 6 — the trailing edge is a genuine trade-off, not a tuning bug

Two levers act on the TE block, in opposite directions:

* `split_x_fore` 0.30-0.35 gives the best cell shape (jac 0.34, AR 5.6)
  but pushes the TE normal rotation to 136-141 deg.
* `chordwise_distribution=cluster_center` (added for this study, because
  mid4 puts the LE and TE in block *interiors* where end-clustering cannot
  reach) softens the turn to 88-103 deg but costs Jacobian and aspect
  ratio, which more spanwise panels then have to repay.

## Best recipes found

    R2_span24_sp035  spanwise_panels=24, tip_radial_points=17,
                     tip_inner_scale=0.70, split_x_fore=0.35
                     OML jac 0.341  AR 5.6  | tip jac 0.081  AR 18.6
                     best cell shape; TE turn 141 deg

    S1_span32_sp030_ctr  as above + spanwise 32, split 0.30,
                     cluster_center beta=1.0
                     OML jac 0.214  AR 9.0  | tip jac 0.051  AR 20.5
                     TE turn 88 deg -- the gentlest trailing edge found

Versus the round-1 pick (`spanwise_panels=8, tip_radial_points=9`):
OML Jacobian 0.076 -> 0.341 (4.5x), OML AR 25.0 -> 5.6 (4.5x better),
tip Jacobian 0.033 -> 0.081, tip AR 47.3 -> 18.6.

## Three metrics that never pass, and why

* **OML skewness pinned at 0.634-0.639** across all 54 strategies —
  resolution, clustering, split location, topology, none of it moves it.
  Structural: on a swept, tapered planform the chordwise and spanwise grid
  families are not orthogonal, and refinement cannot change an angle. Note
  0.638 is "fair" on the standard scale and is acceptable for RANS — the
  <0.5 target used in the harness is too strict for a swept wing.
* **Growth ratio** bottoms out at 1.508 (target 1.2).
* **TE normal rotation** bottoms out at ~67-88 deg (target 40). A blunt
  trailing edge has to turn a large corner; this is geometry, not mesh
  quality. The target is the wrong yardstick for this block.

## OPEN — the constraint that decides whether any of this is usable

`mid4` is documented as **requiring pyHyp `coarsen=4`** (see
`aeris.mesh.topologies` and `DSE_READINESS.md`): the volume mesher
decimates the surface 4x in-plane. If that still holds, a 65k-cell refined
surface is thrown away at the volume stage and every gain above is
cosmetic. The stated *reason* mid4 needed coarsen=4 was the tip cap — the
exact thing laws 4 and 5 just improved. **Next test: march
`R2_span24_sp035` and `S1_span32_sp030_ctr` at coarsen=1.** If they march
clean, mid4 becomes strictly better than cap4 for this geometry. If they
do not, the choice reverts to cap4 and this study must be repeated there.

## Law 7 — the tip cap is downstream of the OML's per-side point counts

The `mid4` wing + `cap4` tip hybrid (added 2026-07-22 as `tip_topology`)
built and ran, but was a **wash**: tip jac 0.064 vs the tuned ring's 0.075,
AR 23.3 vs 19.8. The block shapes explain why — `_build_tip_cap4` produced
a **33x33** centre patch, identical in form to the ring's Coons patch.

cap4's cap is only good when the OML hands it *unequal* side counts (49
chord x 17 wrap), giving an anisotropic rectangle that matches a slender
airfoil. `mid4` gives every side the same count, so the cap degenerates to
the same square-patch-on-a-postage-stamp. **Tip quality cannot be fixed at
the tip; it is set by the OML blocking.**

## Law 8 — `cap_wrap_x` is a mid-chord seam control, not a crown band

Widening cap4's wrap improves the tip and the OML together, monotonically,
until it doesn't:

    cap_wrap_x   0.015   0.060   0.100   0.150   0.250   0.350   0.450
    OML jac      0.084   0.199   0.218   0.196   0.124   0.090   0.071
    OML AR        23.0     9.9     9.0     9.2    15.4    21.8    28.0
    tip jac      0.017   0.036   0.034   0.115   0.100   0.090   0.082
    tip AR        38.4    24.1    21.0     9.2     7.8     9.0    10.6

**0.15 is the optimum.** Past it the OML degrades with no further tip gain.
The old 0.01-0.15 validation ceiling assumed this parameter meant a
razor-thin band hugging the crown; it is really the seam location, and the
bound was raised to 0.45 (matching `split_x_fore`) to permit this study.

This is the "mid-chord O-type" idea, realised inside cap4's anisotropic
structure rather than as a new topology.

## SELECTED BASELINE RECIPE (2026-07-22)

    topology            cap4
    points_per_side     49
    spanwise_panels     24
    cap_wrap_x          0.15
    cap_wrap_points     17
    tip_radial_points   9

                      OML                          tip
              jac    skew    AR   growth  angle |  jac    skew    AR    cells
    selected  0.259  0.631   6.9  1.508   153.7 | 0.129  0.917  10.9   41728
    mid4 best 0.288  0.634   6.7  1.606   142.6 | 0.075  0.943  19.8   42496
    original  0.076  0.636  25.0  1.981   121.0 | 0.033  0.948  47.3   23808

Versus the recipe this study started from: **OML Jacobian 3.4x better, OML
aspect ratio 3.6x better, tip Jacobian 3.9x better, tip aspect ratio 4.3x
better**, at 1.75x the cell count. Versus the best `mid4` variant it trades
~10% of OML Jacobian for a 1.8x better tip -- the tip being the thing the
project lead rejected on visual inspection.

A cheaper variant, `points_per_side=33` (31232 cells, OML jac 0.248, AR
7.9, tip jac 0.120, AR 12.3), is the natural smoke-level member.

**Unverified:** none of this has been marched. The next step is a pyHyp
canary (3 layers) then a full extrusion, with `epsE=3.0` per the earlier
law.

## Law 9 — trailing-edge thickness: 0.5% chord, and why (2026-07-22)

AeroSandbox hands the mesher a **0.2519% chord** trailing edge. That is not
an artifact: it is the canonical NACA 4-digit TE, which does not close to
zero. (The NASA TMR validation case used the *closed*-TE variant.)

`te_thickness` opens it. Selected value **0.005 (0.5% chord)**, on three
independent grounds:

1. **Practice.** Real transport wings carry ~0.2-0.5%c for structural and
   manufacturing reasons; blunt TEs of this order are standard on
   drag-prediction-workshop geometries. 0.5% is more physically honest than
   a sharp idealisation, not less.
2. **This aircraft's Reynolds number.** At Re 1e6 (root) to 1.2e5 (tip) the
   turbulent boundary layer at the TE is 2.3-3.6% of chord, so a 0.5% base
   sits at h/delta = 0.14-0.21 — buried well inside the boundary layer,
   which is the regime where base drag is cheap. A transport wing at
   Re 4e7 has delta ~0.6%c and the same 0.5% base would be comparable to
   the boundary layer and genuinely costly. **The low Reynolds number of a
   small BWB UAV is what makes this affordable.** Estimated penalty ~4
   drag counts over the 0.252% baseline, ~1.5% of the measured C_D.
3. **Manufacturing.** 0.5%c is 8.0 mm at the root and **1.0 mm at the
   tip** — about the thinnest edge that can actually be built, and the
   centrebody needs that depth for elevon hinges anyway.

2% chord was tested and rejected: it gave the best TE-angle metric (81.5
deg) and that is exactly why it is the wrong objective — it optimises the
mesh, not the aircraft.

## Law 10 — a resolved TE base needs an absolute floor, not a fixed count

`te_base_points` pins the two ~90 deg corners of the blunt base (see the
commit "pin the blunt-TE base corners"), and it works: the TE normal
rotation drops to 87.9 deg and stays there regardless of how many base
points are used, because the turn is captured exactly rather than smeared.

But it currently **degrades the OML**, and more wrap points do not help --
`cap_wrap_points` 17/21/25 give identical results (jac 0.068, AR 29.2).
Per-block localisation shows the damage is confined to `oml_2`, and the
cause is the tip: 0.5%c is 8.0 mm at the root but 0.96 mm at the tip, so a
fixed 5 points across the base makes 0.24 mm slivers outboard.

**A constant point count across a base whose physical size varies 8x is
wrong.** The fix is an absolute minimum thickness alongside the percentage
(real aircraft do exactly this -- you cannot build a 0.5 mm edge), which
would disproportionately thicken the tip where the meshing pain and the
earlier volume-march inversion both concentrate. Until then
`te_base_points` defaults to 0 and is not part of the selected recipe.

## Selected recipe, locked 2026-07-22

    oml_topology       cap4
    points_per_side    49
    spanwise_panels    24
    cap_wrap_x         0.15
    cap_wrap_points    17
    tip_radial_points  9
    te_thickness       0.005
    (volume)  epsE 3.0, epsI 6.0

              OML                            tip
      jac    skew   AR   growth  angle |  jac    skew   AR    cells
      0.259  0.631  6.9  1.508   146.0 | 0.134  0.914  10.3  41728

Not yet added to the mesh_family presets: those share one family-wide march
policy by design (C1/C2, no per-case tuning), and epsE 6.0 -> 3.0 must move
for the whole family at once, after the march below validates it.

## Law 11 — spanwise panels must be allocated by segment LENGTH, not per section

The growth ratio sat frozen at **1.508** across ~90 strategies — every
resolution, distribution, split location, wrap width and topology. It was
never a chordwise or trailing-edge effect.

`spanwise_panels_per_section` gave every geometry section the same panel
count regardless of its physical extent. On the baseline BWB the 13 section
intervals are not equally spaced: sections 0-8 span 106.7 mm, sections 9-12
span 160.0 mm. Equal panels therefore produced 4.44 mm cells inboard and
6.67 mm cells outboard —

    6.67 / 4.44 = 1.50   <- exactly the frozen growth ratio

`spanwise_allocation="proportional"` spends the same total budget in
proportion to each interval's spanwise extent (the per-segment `nSpan` list
in pyGeo's `createMidsurfaceMesh`). Measured on `oml_1`:

    spanwise cell size ratio   uniform 1.500  ->  proportional 1.016

and the worst growth block moves from `oml_0` (spanwise) to `oml_2` (the TE
wrap), i.e. the remaining 1.407 is a *different*, chordwise problem that was
previously masked.

It also frees resolution. With proportional allocation the same recipe at
**16** panels beats the old 24:

               OML jac   OML AR   growth   cells
    uniform 24   0.259      6.9    1.508   41728
    prop 24      0.294      6.1    1.407   41856
    prop 16      0.426      4.0    1.407   28672

`prop 16` is the best OML measured in this entire study — Jacobian 2.1x the
target with 31% fewer cells than the previously selected recipe.

Also adopted from the same pyGeo routine: `cosine_blend`, a continuous
uniform-to-cosine distribution whose strength is a single float in [0, 1]
(`chordCosSpacing` there), rather than discrete named modes.

**Not adopted:** `createMidsurfaceMesh` itself. It builds a mean-camber
*sheet* for VLM/OpenAeroStruct by projecting onto a triangulated surface and
taking upper/lower midpoints — no closed OML, no tip cap, no blunt TE, so it
cannot be extruded by pyHyp. Different purpose.
