# AERIS Checkpoint 33 — Generic Model Promotion Gate Configs

## What this slice adds

AERIS model promotion can now use generic, target-discovered, scale-aware gate configs.

New command:

```bash
aeris ml suggest-promotion-gates \
  --model-run-dir data/processed/ml_runs/<run> \
  --profile normal
```

It writes:

```text
promotion_gate_suggestions.json
promotion_gates_template.yaml
```

Promotion can now consume the reviewed gate template:

```bash
aeris ml promote-model \
  --model-run-dir data/processed/ml_runs/<run> \
  --gate-config data/processed/ml_runs/<run>/promotion_gate_suggestions/promotion_gates_template.yaml
```

## Design rule

The gate system is target-agnostic. It does not hardcode `cm`, `cl`, `cd`, or any future target.
It discovers targets from the model run and writes per-target thresholds that the operator can review.

## Supported gate fields

Global gates:

```yaml
global:
  max_val_rmse_mean: null
  max_test_rmse_mean: null
  min_test_r2_mean: null
```

Per-target gates:

```yaml
targets:
  target_name:
    required: true
    max_rmse: 0.01
    max_mae: 0.008
    max_nrmse_iqr: 0.10
    max_nrmse_range: null
    max_abs_error: null
    max_error_p95: null
    min_r2: 0.90
```

## Why this matters

A global average model score can hide a weak target. That is dangerous for stability-critical or mission-critical targets.
The correct approach is not hardcoded special treatment, but explicit per-target engineering gates.

## GUI note

The GUI should later become an editor over this YAML template:

```text
model run selector -> detected targets -> editable thresholds -> promote with --gate-config
```

The CLI/data layer remains the source of truth.
