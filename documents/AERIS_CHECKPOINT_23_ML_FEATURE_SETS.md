# AERIS CHECKPOINT 23 — ML Feature-Set Registry

## What this slice adds

AERIS now has a formal ML feature-set registry:

```text
src/aeris/ml/feature_sets.py
```

New CLI commands:

```bash
aeris ml feature-sets
aeris ml describe-feature-set --feature-set bwb_control_raw
aeris ml validate-feature-set --dataset <promoted_dataset> --feature-set bwb_control_raw
```

## Initial feature sets

```text
bwb_control_raw
bwb_control_physics_v1
```

`bwb_control_raw` is intentionally the current raw BWB control feature set:

```text
c1_m
b_total_m
sw1_deg
alpha_deg
velocity_mps
altitude_m
control_input_deg
```

No Reynolds, Mach, qbar, trigonometric, squared, or interaction terms are hidden inside the raw set.

`bwb_control_physics_v1` declares explicit feature-engineering transforms and expected engineered columns. Validation applies those transforms in memory only. It does not materialize an engineered dataset yet.

## What this does not do

This slice does not integrate `--feature-set` into train/compare/tune/predict yet.
It also does not add the `feature-engineer` command. Those are later slices.

## Why this matters

AERIS can now name and validate ML input representations before model selection. This prevents fake model comparisons where one model quietly receives engineered features while another receives raw columns.
