# Stage 01 Gate Report

Result: PASS_WITH_FINDINGS
State after gate: AWAITING_USER_APPROVAL
Required next user token: `APPROVE STAGE 01`
Stage 02 authorized: no
Generated: 2026-08-12

## Summary

Stage 01 established the trusted solver anchor, characterised the `cap4`
control, and built the harness. It did not produce `epsE_common_start`, because
the `cap4` control surface is itself defective. That is recorded as a tournament
result rather than repaired, and the common start value moves to Stage 02.

## What Passed

- **TMR anchor.** 13/13 checks in solve mode. `surface.fmt` SHA-256 matched the
  reference exactly; volume audit clean; ADflow forces matched the recorded
  anchor (CL 1.0917740093456412, CD 0.013164679005086222). This is reproduction
  of AERIS's own historical values, not validation against NASA CFL3D
  (1.0909 / 0.01231); the CD offset of 8.5 counts is known and documented.
- **Locked surfaces.** All ten seed-7 current-design-space cap4 L3 surfaces
  generated with deterministic `surface.fmt` hashes. Note this was
  `mode: dry-run` packaging: 30 remarch rows, all `stage_status: dry_run`, all
  volume metrics null.
- **Strategy interface.** `04_strategy_prototypes/strategy_interface.py` defines
  the S0-S5 ids, required artifact names, stable hashing and connectivity
  manifest helpers.
- **Surface validity gate implemented.** `min_scaled_jacobian > 0.0` is now a
  hard pre-pyHyp failure, enforced end to end: export raises `MeshBuildError`
  and writes no CGNS. 182 tests pass across `tests/mesh` and `tests/cfd`.

## What Failed, and Why It Is a Result Rather Than a Blocker

No `epsE` candidate survives on the `cap4` control. At L3 on `lhs7_00`:

| epsE | inverted cells | low/negative-quality layers | min quality |
| ---: | ---: | ---: | ---: |
| 1.5 | 10 | 53 | -1.0 |
| 2.0 | 4 | 53 | -1.0 |
| 3.0 | 0 | 53 | -0.90808 |

Three surface-only probes established the cause.

**The defect is structural.** Across all ten locked geometries the surface
`min_shape_metric` and `min_scaled_jacobian` agree to 11-12 significant figures,
with `tip_center_0` the worst block every time. These metrics are
scale-invariant, so the worst cell has the same shape regardless of aircraft
size. Prevalence is 10/10 by construction, which is why the 30-run campaign was
cancelled rather than run.

**The geometry is clean.** The `lhs7_00` tip-station section has 61 points, zero
collapsed segments below 1e-9, minimum segment 3.728e-03, median 3.852e-02, and
a maximum turning angle of 41.96 degrees at the leading edge. No cusp. S1-S5 do
not inherit the defect.

**The corner cannot be tuned away.** The airfoil-face cap takes its corners from
the cap4 OML block splits. Every split lands on a smooth part of the contour, so
the meeting edges are collinear and the corner is ~180 degrees by construction:

| `split_x_fore` / aft | min shape | worst tip corner |
| --- | ---: | ---: |
| 0.10 / 0.90 | 3.7160e-04 | 179.737 deg |
| 0.20 / 0.80 | 3.7160e-04 | 179.737 deg |
| 0.35 / 0.65 | 3.7160e-04 | 179.737 deg |

Swapping the tip block topology does not help: `cgrid_face` matches
`airfoil_face` to 11 significant figures with slightly worse skew and scaled
Jacobian. Coarsening does not help either: L1 and L2 at epsE 1.5 produce zero
inverted cells but still 60/128 and 55/128 low-quality layers against L3's
53/128.

**All three legacy tip closures are affected; cap4 is least bad.** `mid4` is
rejected for a folded `tip_ring_2` (`positive_scaled_jacobian` -6.898e-02,
alignment -1.0); `split8` for `tip_ring_5` (-2.838e-01, alignment -1.0) plus an
open boundary off the root plane. Both were caught by the scaled-Jacobian gate
added mid-stage; before that fix they would have been accepted and marched.

## Decisions

- **ADR-0006** - S0/`cap4` is recorded as failing the volume gate and is not
  repaired. RUNBOOK Section 1 makes `cap4` the control case, not the assumed
  answer; repairing it now would mean investing in the topology the tournament
  exists to replace. S0 stays in as a documented regression baseline per
  RUNBOOK Section 6.
- **ADR-0007** - `epsE_common_start` is re-based. It will be calibrated in
  Stage 02 on the first strategy that passes all hard surface gates on all ten
  calibration geometries, in an implementation order fixed in advance so the
  host cannot be selected after seeing results.

## Open Items Carried Into Stage 02

- The 30-row L3 sweep was never run; marching evidence rests on `lhs7_00`. This
  is sufficient because the surface defect is identical across all ten
  geometries to 11-12 significant figures.
- The prepared L1 prevalence and L3 overnight campaigns are cancelled, not held.
- `test_surface_qc_rejects_negative_scaled_jacobian` is a mocked unit test;
  `tip_smooth_iters=20` does not fold the synthetic geometry, so no end-to-end
  regression covers the real folding path.
- The cap4 historical regression remains qualitative only, per ADR-0003.

## Recommendation

Approve Stage 01 and proceed to Stage 02 with S1 and S3 first. Both anchor their
tip blocks on genuine geometric features rather than arbitrary x/c splits, which
is exactly the failure mode identified here. S2 remains blocked on its
cross-field/quad-extraction dependency per the Stage 00 dependency audit.

Do not begin Stage 02 until the user explicitly replies `APPROVE STAGE 01`.
