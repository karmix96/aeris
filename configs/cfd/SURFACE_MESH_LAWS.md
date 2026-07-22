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
