# ADR-0002 - Stage 00 Audit Corrections

Status: Proposed for Stage 00 approval
Date: 2026-08-11
Amended by: ADR-0003. The restore action below stands, but the file now lives at
`00_governance/historical_reference_inputs/bwb_explore_wide.yaml`, its use is limited to
qualitative historical regression, and `epsE_common_start` is calibrated on the current
design space instead.

## Decision

Accept the Claude audit findings as valid Stage 00 approval-readiness issues
and fix them additively:

- Restore `configs/geometry/bwb_explore_wide.yaml` from git history as a
  reproducibility input for the old cap4 campaign.
- Treat the old cap4 evidence as 6/10 clean under the current quality policy,
  not 7/10, because seed 6 carried negative-quality layers.
- Record `RESULTS_ARCHIVE.md`, `RETENTION.md`, `NEXT_STEPS.md`, `STATUS.md`,
  and the CFD evidence JSONs in the Stage 00 reference package.
- Replace raw CGNS byte identity with HDF5 dataset-content identity for volume
  CGNS determinism checks.
- Add dependency status for S0-S5 and mark S2 blocked until a cross-field and
  quad-extraction dependency or in-house implementation decision is made.
- Add a source-aware geometry-fidelity gate resolution.
- Add a proposed LHS authority: `lhs_v1`, seed 42, N=100 for the full geometry
  set, plus N=10 for the Round C tournament sample.

## Consequences

Stage 01 can start after Stage 00 approval because its first work is TMR and
cap4 control reproduction. S2 must not be executed as a cross-field candidate
until its missing dependency decision is resolved.

Approval of Stage 00 also approves the proposed LHS seed and sample tables
unless the user asks for a different seed before approval.
