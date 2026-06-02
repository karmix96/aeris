# AERIS CHECKPOINT 22 — ML EDA CLI Operator Layer

## What this slice adds

AERIS now exposes promoted-dataset exploratory data analysis through the CLI:

```bash
aeris ml eda --dataset <promoted_dataset> --feature-preset bwb_control --targets cl,cd,cm
```

The command writes:

```text
eda_report.json
eda_summary.md
plots/   # optional with --plots
```

## Why this matters

This is the missing pre-training operator step. Before training, tuning, or promoting models, AERIS can now inspect the promoted curated dataset for constant columns, duplicates, outliers, feature/target statistics, per-geometry coverage, alpha/control coverage, correlations, and nonlinearity signals.

## Design rule

EDA is leakage-safe: it does not fit a model, does not split data, and does not use validation/test statistics to train anything. It is an audit/reporting layer over the promoted curated dataset.

## Example

```bash
aeris ml eda   --dataset data/datasets/<promoted_aero_dataset>   --feature-preset bwb_control   --targets cl,cd,cm   --plots
```

## Next slice

Next should be the feature-set registry and feature-engineering CLI so AERIS can compare raw vs physics-engineered inputs before model selection.
