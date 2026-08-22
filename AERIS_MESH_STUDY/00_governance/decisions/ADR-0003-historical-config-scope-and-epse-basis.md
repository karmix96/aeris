# ADR-0003 - Historical Config Scope and epsE Calibration Basis

Status: Proposed for Stage 00 approval
Date: 2026-08-11
Supersedes: the `restore the historical config` clause of ADR-0002 (that action stands;
its scope is narrowed here)

## Context

ADR-0002 restored `bwb_explore_wide.yaml` from git history so the July 2026 cap4
campaign would have its missing geometry input again, and the revised gate registry
routed the Stage 01 `epsE` sweep through it.

A second audit parsed the restored file. It is not a narrower version of the current
design space. It is the pre-rescale airframe that DECISION-0002 explicitly replaced:
root chord 1.2-2.0 m against 0.70-1.10 m, full span 2.4-4.0 m against 1.5-2.5 m,
`naca4412` across the whole wing instead of mh91/mh91/e374/nlf1015, `dihedral_b1_deg`
free to 5 degrees instead of pinned at zero, and 17 active design variables instead of
20.

Two of those conflict with invariants this study already froze in
`geometry_topology_contract.json`: the station airfoil assignment and the
flat-root-panel rule. Seed 0 under the historical config produces a root panel canted
3.65 degrees.

RUNBOOK Section 4.2 makes the `epsE` selected on the locked ten geometries the
`epsE_common_start` for every pyHyp strategy in the tournament. Calibrating it on the
historical config would freeze a production constant derived from a different
aircraft.

## Decision

1. The historical config is a **historical regression input only**. It moves to
   `00_governance/historical_reference_inputs/bwb_explore_wide.yaml`, out of
   `configs/geometry/`, so DECISION-0001's single-live-config rule stays intact. It is
   never authoritative for a current-design-space result or a production constant.

2. The Stage 00 `cap4_reproduction` gate splits in two:
   - `cap4_historical_regression` - qualitative. Reproduce the trailing-edge-crown
     inversion mechanism and region. Numerical equality is not required and must not be
     claimed.
   - `cap4_current_control_and_epse_common_start` - quantitative. Generate ten
     geometries from the current design space, freeze their surface hashes, sweep
     `epsE={1.5, 2.0, 3.0}` to completion, and select `epsE_common_start`.

3. The epsE calibration set is `00_governance/epse_calibration_lhs10_seed7_samples.csv`:
   `lhs_v1`, seed 7, N=10, drawn from `configs/geometry/bwb.yaml`. Seed 7 is arbitrary.
   What matters is that it is predeclared and frozen before any result is seen, and
   that it is disjoint from the Round C hold-out, because RUNBOOK Section 7 forbids
   epsE tuning on the held-out LHS geometries. Disjointness is re-asserted on every run
   of `make_lhs_sets.py`.

4. A locked geometry set is identified by the quadruple (sampler, seed, n,
   geometry-config sha256). A seed alone is not an identifier: seed 42 at N=100 and
   seed 42 at N=10 share zero rows.

5. Historical geometry-level reproduction is recorded as unverifiable. The July
   campaign report stores no per-sample design variables, and eight commits touched the
   generator between that config's last version and HEAD.

## Consequences

Stage 01 runs the historical check first as a mechanism sanity test, then calibrates
`epsE_common_start` on the ten current-design-space geometries and freezes it in the
Stage 01 ADR. If no value in `{1.5, 2.0, 3.0}` passes all ten, RUNBOOK Section 16
applies: stop and repair the TE-crown mechanism before the tournament.

The historical 6/10-clean figure stays in the record as context for the failure
mechanism. It is not a baseline the current aircraft must match.

## Evidence

- `00_governance/reference_package_manifest.yaml`, key `historical_config_divergence`
- `00_governance/lhs_authority.yaml`, keys `set_identity_rule` and `set_relationships`
- `01_references/repository_audit.md`, section `Second Audit Correction`
- `00_governance/make_lhs_sets.py --check` regenerates every locked table and verifies
  disjointness
