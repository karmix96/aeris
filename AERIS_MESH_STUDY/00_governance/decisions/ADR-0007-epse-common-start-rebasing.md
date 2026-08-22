# ADR-0007 - Re-basing epsE_common_start off the cap4 Control

Date: 2026-08-12
Status: Proposed for Stage 01 approval
Amends: ADR-0003 (which moved epsE calibration onto the current design space),
gate `cap4_current_control_and_epse_common_start`

## Context

RUNBOOK Section 4.2 defines `epsE_common_start` as the highest `epsE` in
`{1.5, 2.0, 3.0}` that marches cleanly on ten locked geometries, and makes it
the trusted starting point for every pyHyp strategy in the tournament.

ADR-0003 correctly moved that calibration from the superseded historical
airframe onto the current design space. ADR-0006 now records that the `cap4`
surface those ten geometries produce is itself defective, so no `epsE` can pass
on it. The calibration has lost its basis.

Leaving it undefined is not acceptable: S1, S3 and S5 are pyHyp candidates and
would each start from an unstated marching configuration, which would make the
tournament unfair and its comparisons meaningless.

## Decision

`epsE_common_start` is calibrated on the **first strategy that produces a clean
surface**, not on `cap4`.

Procedure, frozen here before any Stage 02 result is seen:

1. A strategy qualifies as a calibration host when it produces surfaces passing
   every hard surface gate - watertight, conformal interfaces,
   `min_scaled_jacobian > 0.0`, correct boundary labels - on all ten geometries
   in `00_governance/epse_calibration_lhs10_seed7_samples.csv`.
2. The first strategy to qualify, in the Stage 02 implementation order recorded
   in the Stage 02 plan, becomes the calibration host. Order is fixed in advance
   so the host cannot be chosen after seeing marching results.
3. On that host, sweep `epsE = {1.5, 2.0, 3.0}` to completion on all ten
   geometries. Select the highest value passing all ten and freeze it as
   `epsE_common_start` in the Stage 02 ADR.
4. If no value passes on the first qualifying host, move to the next qualifying
   strategy in the fixed order and repeat. Record every attempt.
5. If no strategy qualifies, RUNBOOK Section 16 applies: stop and report.

Unchanged from the existing policy:

- Per-strategy `epsE` may still be re-calibrated in Round B against the same
  three-value budget, and frozen before Round C.
- **No `epsE` tuning is permitted** on `round_c_lhs10_seed42_samples.csv` or on
  the Round C extremes.
- Both `epsE_common_start` and each frozen per-strategy value are stored.

## Rationale

The common start value exists to give every pyHyp candidate the same trusted
launch point. Nothing in RUNBOOK Section 4.2 requires that point to come from
`cap4` specifically; it requires that it come from a clean surface on the ten
locked geometries. `cap4` was the natural host only while it was assumed
healthy.

Fixing the host-selection order in advance is what keeps this honest. Choosing
the host after seeing which one marches best would be selecting a numerical
constant from its own answer, which RUNBOOK Section 2 forbids.

## Consequences

- Stage 01 closes without `epsE_common_start`. This is expected, not a failure
  of the stage.
- Stage 02 gains one extra deliverable: the frozen `epsE_common_start` plus the
  record of which strategy hosted it and why.
- The gate `cap4_current_control_and_epse_common_start` is split. The cap4
  control reproduction part is satisfied and closed by ADR-0006. The
  `epsE_common_start` part moves its `freeze_stage` from `01` to `02`.
