# ADR-0005: Stage 01 Surface Validity Enforcement

Date: 2026-08-11
Amended: 2026-08-12
Status: Accepted for scaled-Jacobian enforcement; shape/angle tightening rescinded

## Context

The lhs7_00 tip-topology probe found that tip_smooth_iters: 20 can produce a folded surface cell with negative scaled Jacobian while the surface was still reported as accepted_pre_pyhyp: True.

Stage 00 surface_validity already required no folded or negative surface cells. The implementation reported min_scaled_jacobian but did not use it as an acceptance check.

A first Codex follow-up also changed Stage 01 cap4 min_shape_metric from 1.0e-6 to 3.0e-2 and max_adjacent_normal_angle from 180.0 to 170.0. Claude audit rejected those two numeric thresholds because they were selected after seeing the failed surfaces and had no calibration source.

## Decision

The general surface builder treats min_scaled_jacobian <= 0.0 as a hard surface QC failure with check id positive_scaled_jacobian. This is a mathematical validity floor: zero or negative signed scaled Jacobian means a degenerate or folded surface cell.

The unsupported Stage 01 cap4 recipe threshold changes are rescinded:

- min_shape_metric is restored to the prior study value 1.0e-6.
- max_adjacent_normal_angle is restored to the prior study value 180.0 deg.
- No new hard shape or adjacent-normal-angle threshold is adopted without a registered derivation in gate_registry.yaml.

This ADR updates the implementation of the Stage 00 surface_validity gate. It does not authorize Stage 02.

## Consequences

With the rescinded thresholds, the ten locked L3 cap4 surfaces are not blocked at surface generation by minimum_shape_metric; they remain relevant volume-gate evidence. The Stage 01 blocker is still the cap4/pyHyp volume failure and the upstream tip-station boundary defect at leading_edge_shoulder_lower_side.

The regression test for positive_scaled_jacobian is a mocked unit test that verifies the acceptance path. It does not yet reproduce the real BWB tip_smooth_iters: 20 folding path end to end. The real folding case is documented by 03_cap4_epse/tip_topology_probe_report.json and should be promoted to a geometry-backed regression once a stable test fixture is approved.
