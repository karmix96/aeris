# ADR-0006 - S0/cap4 Fails the Volume Gate and Is Recorded, Not Repaired

Date: 2026-08-12
Status: **SUPERSEDED by ADR-0011 (2026-08-14)**
Supersedes the "repair before tournament" reading of ADR-0004

> **Superseded.** ADR-0011 §3.1 reverses this ADR's *decision* not to repair S0. Under
> ADR-0011 every strategy, S0 included, is developed to its best achievable state and
> then judged; declining to develop an entrant because it is expected to lose makes the
> expected outcome unfalsifiable. Two facts made the reversal material: S0 is the only
> strategy that has ever produced a complete valid volume march (`passed: True`, min
> volume +2.11e-11), and ADR-0010 later established that the metric on which S0 was
> ranked worst — minimum scaled Jacobian — does not predict marchability.
>
> **The measurements below stand.** The 179.737 degree tip corner is real, structural,
> invariant to `split_x_fore`, and present on all ten geometries; `mid4` and `split8`
> are genuinely worse. What is withdrawn is the decision not to attempt a repair.

## Context

RUNBOOK Section 4.2 asks Stage 01 to reproduce the `cap4` control and calibrate
`epsE_common_start` on it. Section 16 says to stop if no `epsE` in
`{1.5, 2.0, 3.0}` passes, and Section 4.2 adds "repair the underlying TE-crown /
spanwise-spacing mechanism before the tournament".

Stage 01 found that no candidate passes. On `lhs7_00` at L3:

| epsE | inverted cells | low/negative-quality layers | min quality |
| ---: | ---: | ---: | ---: |
| 1.5 | 10 | 53 | -1.0 |
| 2.0 | 4 | 53 | -1.0 |
| 3.0 | 0 | 53 | -0.90808 |

The runbook anticipated a TE-crown or spanwise-spacing cause. Three diagnostics
show the real cause is neither, and that "repair before the tournament" is the
wrong instruction here.

## Evidence

**1. The defect is structural, not geometry dependent.** Across all ten locked
seed-7 geometries the surface `min_shape_metric` and `min_scaled_jacobian` agree
to 11-12 significant figures, with `tip_center_0` the worst block every time.
These are scale-invariant metrics, so the worst cell has the same *shape*
regardless of aircraft size. Prevalence is 10/10 by construction.

**2. The geometry handed to the mesher is clean.** The `lhs7_00` tip-station
section has 61 points, **zero** collapsed segments below 1e-9, minimum segment
length 3.728e-03, median 3.852e-02, and a maximum turning angle of 41.96 degrees
at the leading edge. No cusp, no degenerate segment. S1-S5 do not inherit a
broken OML.

**3. The bad corner cannot be tuned away, and it is not unique to cap4.** The
airfoil-face cap takes its corners from the cap4 OML block splits. Every split
lands on a smooth part of the airfoil contour, so the two edges meeting at the
corner are collinear and the corner angle is ~180 degrees by construction:

| `split_x_fore` / aft | min shape | worst tip corner |
| --- | ---: | ---: |
| 0.10 / 0.90 | 3.7160e-04 | 179.737 deg |
| 0.20 / 0.80 | 3.7160e-04 | 179.737 deg |
| 0.35 / 0.65 | 3.7160e-04 | 179.737 deg |

Swapping the tip block topology does not help either: `cgrid_face` matches
`airfoil_face` to 11 significant figures with slightly worse skew and scaled
Jacobian. And the two other legacy OML topologies are worse - `mid4` and
`split8` are both rejected outright for folded tip cells
(`positive_scaled_jacobian` -6.898e-02 and -2.838e-01, alignment -1.0).

## Decision

S0/`cap4` is recorded as **failing the volume gate**. It is not repaired.

This is a legitimate tournament outcome, not a prerequisite. RUNBOOK Section 1
states that `cap4` "is now the control case, not the assumed final answer", and
Section 7 requires the winner to be chosen on evidence. All three of AERIS's
legacy tip closures fail at the tip; `cap4` merely fails less visibly. Repairing
it now would mean investing in the topology the tournament exists to replace.

S0 remains in the tournament as a documented regression baseline, with its known
weak region visible rather than averaged away, exactly as RUNBOOK Section 6
requires.

## Consequences

- Stage 01 closes as PASS_WITH_FINDINGS: the TMR anchor passed, the control was
  characterised, and the harness exists. It did not produce `epsE_common_start`.
- `epsE_common_start` is re-based; see ADR-0007.
- Stage 02 should start with S1 and S3. Both anchor tip blocks on genuine
  geometric features rather than arbitrary x/c splits, which is precisely the
  failure mode identified here. S2 stays blocked on its cross-field dependency
  per the Stage 00 dependency audit.
- The prepared L1 prevalence and L3 overnight campaigns stay cancelled. Both
  would characterise a topology being replaced.

## Evidence Files

- `03_cap4_epse/tip_corner_origin_probe_report.md` and `.json`
- `03_cap4_epse/tip_topology_probe_report.md` and `.json`
- `03_cap4_epse/lhs7_00_surface_region_diagnostic.md`
- `03_cap4_epse/epse_calibration_l3_probe_report.json` and the eps20/eps30 probes
- `reports/stage_01_report.md`
