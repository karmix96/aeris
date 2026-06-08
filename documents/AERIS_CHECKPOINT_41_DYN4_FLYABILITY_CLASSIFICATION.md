# AERIS Checkpoint 41 — DYN-4 Flyability Classification Infrastructure

## Purpose

DYN-4 adds real classification infrastructure for flyability/red-flag labels.
Before this slice, binary flyability labels could be pushed through the regression
pipeline as numeric proxies. That was acceptable for plumbing, but ugly for
science and wrong for later PhD/MDAO claims.

## Added

- `src/aeris/ml/classification.py`
- `aeris ml classify`
- `aeris ml compare-classifiers`
- classifier tests and CLI smoke tests

## Supported initial classifiers

```text
logistic_regression
random_forest_classifier
extra_trees_classifier
gradient_boosting_classifier
hist_gradient_boosting_classifier
```

## Metrics

For each target and partition, AERIS writes:

- accuracy
- balanced accuracy
- weighted and macro precision/recall/F1
- class counts
- confusion matrix
- ROC AUC when binary and valid

## Boundary

This slice does not run solvers, nonlinear trim, dynamics simulation, or MIL-STD
classification. It consumes promoted/curated tabular datasets and trains one
classifier per requested target column.

## Typical usage

```bash
aeris ml classify \
  --dataset data/datasets/<flyability_ml_dataset> \
  --feature-set bwb_control_physics_v1 \
  --targets longitudinal_basic_flyable_int,red_flag_int \
  --classifier-type random_forest_classifier \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/flyability_rf_classifier
```

```bash
aeris ml compare-classifiers \
  --dataset data/datasets/<flyability_ml_dataset> \
  --feature-set bwb_control_physics_v1 \
  --targets longitudinal_basic_flyable_int,red_flag_int \
  --classifiers logistic_regression,random_forest_classifier,extra_trees_classifier \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/flyability_classifier_compare
```

## Operator warning

Metrics from tiny smoke datasets are not scientific model-quality evidence.
DYN-4 proves the classifier infrastructure and report artifacts. Real evaluation
requires a larger, more balanced flyability-labeled campaign.
