# ADR-0019 — S8: the lift axis was wrong, and the leading-edge spacing is not spanwise-smooth

- Status: accepted
- Date: 2026-09-04
- Amends ADR-0018. Does not supersede it: the topology decision stands.
- Retires nothing.

## Context

Two defects were found by auditing the first S8 CFD point rather than by any
run failing. Neither is a mesh topology problem, so ADR-0018's decision is
untouched; both change what that CFD point is allowed to claim.

### Defect 14 — angle of attack was applied as sideslip

`solve_s8.py` constructs `ADFLOW(options={...})` by hand and never set
`liftIndex`, so it ran at ADflow's default of **2**. AERIS meshes span **+y**.
At `liftIndex 2` ADflow rotates alpha about **z**, which moves the freestream
in the x–y plane — into the spanwise direction, against a root symmetry plane
that forbids spanwise crossflow.

Every S8 run therefore solved sideslip rather than incidence, and measured lift
along the span.

Established three ways, in `reports/s8_lift_index_defect_20260904.json`:

1. The alpha 8 surface file carries `VelocityUnitVector`
   `(0.990268, 0.139173, 0)`. That is sin(8 deg) in the spanwise component.
2. ADflow's option table reads `"liftIndex": [int, [2, 3]]`, whose first entry
   is the default, and `src/utils/flowUtils.F90:getDirVector` rotates alpha
   about z at 2 and about y at 3.
3. `verify_lift_index.py` constructs the solver at both settings with
   `nCycles 0` and reads the direction arrays back. It reproduces the corrupted
   vector exactly at 2 and returns `(0.990268, 0, 0.139173)` at 3.

The root cause is the bypass, not the missing line.
`src/aeris/cfd/solvers/adflow/options_schema.py` carries `lift_index = 3` as an
AERIS-wide default with the citation "AERIS meshes span +y, lift +z", and the
governed C03 canary went through that layer: its `adflow_options.json` records
`liftIndex 3`. S8 did not. **ADR-0018's statement that the S8 result is
"directly comparable" with C03 was therefore not true of the forces.** A second
divergence rode along: `NKSwitchTol` took ADflow's default of 1e-5 against the
governed 1e-6, handing the flow to Newton–Krylov ten times earlier than policy.

Integrating `-cp n dA` over the alpha 0 wall returns 0.012494 in x, equal to
ADflow's reported CDp to six decimals, so the integration is exact. Its
components:

| | value | |
|---|---|---|
| x, drag | +0.012494 | equals reported CDp |
| y, span | +0.029155 | **reported as CL (0.032301)** |
| z, lift | **−0.160694** | never reported |

Negative lift at alpha 0 is physical, not a further defect: `bwb.yaml` sets
washout (`twist_b2` −5..−1 deg, `twist_b3` −8..−2 deg), and the measured cp puts
the suction side at −z at mid-span.

### Defect 15 — the leading-edge spacing steps 2.6x between adjacent stations

ADR-0018's central claim is that leading-edge resolution is requested in degrees
of turning per cell and solved for. It is, and it is delivered: 10.00 degrees at
every one of the 49 stations.

What is not controlled is how that spacing varies along the span. Read off the
delivered mesh, the leading-edge cell as a fraction of local chord is flat at
0.001521 for stations 0–10, then **0.000463 at station 12** — a 2.59x drop in
one station — then flat again to station 19, then a smooth recovery.

`ring_for_target_turning` bisects each station in isolation against a target
defined as the **maximum turning over a six-segment window** at the nose. A
maximum over a discrete set is piecewise in `ds_le`, so as the section changes
along the span the bisection settles on a different branch and the solved
spacing steps discontinuously where the loft is smooth.

It was invisible because the acceptance metric is
`worst_le_turn_per_cell_deg`, every station met it, and the per-station `ds_le`
that would have shown the step was computed inside `build_oml_ring` and
discarded. **That is the same failure ADR-0018 was written to fix — a quantity
that matters going uncontrolled because the acceptance metric cannot see it —
one level down.** It is present at every level: 3.34x at `oh_probe`.

### The residual cp excess is two defects, not one

`reports/s8_cp_excess_diagnosis_20260904.json`. Of the 30 over-bound cells:

| cluster | cells | peak excess | share of CDp |
|---|---|---|---|
| blunt trailing-edge corners, outer 2.5 % of span | 19 | 0.1011 | **0.01 %** |
| leading edge, at the spacing step and the root | 11 | 0.1706 | **9.8 %** |

The trailing-edge corner absorbs **86 to 106 degrees of turning in one cell**
against the 10 the leading edge is held to — four times worse per cell than the
C-family collar S8 exists to replace. It is a C0 kink, so refinement cannot
reduce it, and "degrees of turning per cell" is the wrong instrument there. It
is also aerodynamically irrelevant: those cells' normals are nearly streamwise.

Clipping every over-bound cp to the physical bound moves CDp by **−0.727 %**,
which is 0.42 % of total CD. C03's contaminated collar supplied roughly 80 % of
pressure drag.

## Decision

**1. The lift axis is fixed, and checked rather than set.** `solve_s8.py` now
carries the governed option set including `liftIndex 3` and `NKSwitchTol 1e-6`,
and `verify_flow_directions()` reads `velDirFreeStream` and `liftDirection` back
out of ADflow after `setAeroProblem` and before the solve, refusing to run
unless they equal `(cos a, 0, sin a)` and `(-sin a, 0, cos a)` to 1e-9. It fails
closed if the arrays cannot be read at all, because an unverifiable freestream
is exactly the state this defect lived in. The realised directions are written
into `result.json`, so every future run carries its own evidence.

Setting the option is one line and one line can be dropped again.

**2. The leading-edge spacing is smoothed in span.** `smooth_le_spacing()` takes
the per-station solved spacings, normalises by local chord so the wing's taper
is not mistaken for a discontinuity, and sweeps a minimum envelope outboard and
then inboard at `le_span_growth_max = 1.15` per station. Only the stations the
envelope moves are rebuilt.

The envelope **only ever reduces a spacing**, enforced by an elementwise minimum
against the input rather than by tolerance. A smaller leading-edge cell absorbs
less turning, so no station can come out worse than the target it was solved
for, and `all_stations_met_target` cannot be broken by smoothing.

Delivered on `oh_L3`, verified node by node against the pre-fix wall:

| | before | after |
|---|---|---|
| worst spanwise step in LE spacing | 2.589 | **1.151** |
| worst LE turning per cell, deg | 10.019 | 10.019 |
| LE turning at station 10, deg | 10.001 | **3.136** |
| cells | 567 256 | 567 256 |
| min cell / `s0` | 19.308 | 19.308 |
| inverted cells | 0 | 0 |
| trailing-edge corner turning, deg | 103.39 | 103.39 |

Cost is zero: `n_side` is fixed, so a smaller end spacing redistributes a
section's existing points. The inboard half of the wing gains 1.6x to 3.2x finer
leading-edge resolution because those points were previously spent on chord the
section did not need.

**3. The trailing-edge corner is recorded as measured and benign, and left
alone.** Rounding the blunt base would change DECISION-0004 geometry to recover
0.01 % of pressure drag. That trade is not worth making on this evidence. It is
now a known, quantified property of the topology rather than an unexamined one.

**4. `build_volume.py` records `le_spacing_smoothing` and the full per-station
block in every summary.** The step was invisible because the number that would
have shown it was thrown away.

## What is withdrawn, and what stands

Withdrawn:

- `CL = 0.032301` in `reports/s8_oh_first_cfd_point_20260904.json`. It is the
  spanwise force. True lift is about −0.161.
- ADR-0018's "directly comparable" claim, for forces only.
- `artifacts/s8_cfd/oh_L3_a8_nCycles4000_unconverged/` in full.
- `artifacts/s8_cfd/oh_L3_a8/` in full.

Stands, because at alpha 0 the freestream is `(1,0,0)` at either `liftIndex` and
the solved field is identical:

- The verdict `IMPROVED_NOT_ELIMINATED` and its 25.4x and 68x margins over C03.
- CD 0.021416, CDp 0.012494, CDv 0.008922. `dragDirection` is the freestream
  direction at either setting.
- CMy 0.001085. `surfaceIntegrations.F90` assigns
  `costFuncMomYCoef = cMoment(2)`, the moment about y, with no `liftDirection`
  term, and pitching moment is about y on this mesh.
- Every y+ measurement, on the OML and on the tip cap.
- Every mesh-quality result in ADR-0018. No mesh was touched by defect 14, and
  the defect 15 fix leaves cell count, marchability floor and inverted-cell
  count unchanged.

## Consequences

- **The alpha 8 stall is not explained, only implicated.** The freestream
  carried `v_y = 0.139 V` into an impermeable root symmetry plane, and a
  symmetry plane and a spanwise crossflow cannot both hold, so the discrete
  problem had no consistent steady solution. That is a strong hypothesis for a
  residual that froze at 13.4682379 to eight significant figures over 340
  iterations. It is not proven. The test is to re-run alpha 8 at `liftIndex 3`.
- **The two fixes are not separable in one run.** The next alpha 0 solve carries
  both the corrected lift axis and the smoothed leading edge, so its cp result
  cannot attribute improvement to either alone. Separating them needs a third
  run and is not worth the machine time unless the combined result is
  ambiguous.
- **Re-running needs authorization.** `POLICY.yaml`'s `run-s8-first-point`
  exception was written for one alpha 0 point and has been consumed. The
  corrected sweep is new heavy work.
- **Every other hand-rolled ADflow driver in the tree should be audited for the
  same omission.** `preflight_adflow.py` also omits `liftIndex`, which is
  harmless there because it runs `nCycles 0` and never solves, but the pattern
  is the defect.
- Whether `1.15` is the right growth limit is unswept. It is the value that
  removes this step at a cost of zero.
