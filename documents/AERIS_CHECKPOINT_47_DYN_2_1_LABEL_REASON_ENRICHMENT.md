# AERIS Checkpoint 47 — DYN-2.1 Flyability Label Reason Enrichment

## Purpose

This checkpoint makes the DYN-2 flyability labels easier to audit.

DYN-2 already computed first-order symmetric-elevon control derivatives and trim/flyability labels. The weakness was that a failed label required manual inspection of several columns to understand why it failed.

DYN-2.1 adds explicit failure-reason columns.

## Added to `flyability_labels.csv`

```text
red_flag
red_flag_reasons
trim_failure_reason
pitch_authority_failure_reason
pitch_control_sign_failure_reason
alpha_trim_warning_reason
pitch_stability_warning_reason
label_failure_stage
trim_delta_e_limit_deg
```

## Added to reports

```text
red_flag_count
red_flag_reason_counts
trim_failure_reason_counts
label_failure_stage_counts
```

The batch report also carries these counts into `dynamics_label_run_report.json`.

## Boundary

This does not change the physics.

It remains:

```text
control-aware aero dataset
→ finite-difference Cm_delta_e
→ first-order elevon trim estimate
→ basic longitudinal flyability label
```

It is not:

```text
full nonlinear trim
MIL-STD compliance
6-DOF simulation
certified aircraft validation
```

## Why this matters

For PhD and MDAO use, a failed label must explain itself. A future optimizer or ML classifier needs to know whether a candidate failed because of poor control authority, bad control sign, excessive trim deflection, missing data, or optional stability warnings.
