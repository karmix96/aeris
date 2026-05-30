# AERIS CHECKPOINT 11 — ML Config-Driven Training Slice

## What changed

This checkpoint adds the next ML foundation slice after reproducibility and diagnostics.

AERIS ML now supports:

- YAML-driven single-model training via `aeris ml train --config ...`
- model constructor parameters from YAML configs
- optional JSON parameter override via `--model-params-json`
- comparison-level per-model JSON params via `aeris ml compare --model-params-json ...`
- source config path/hash recorded in `train_config.json`
- source config path/hash recorded in `ml_run_manifest.json`

## Why this matters

Large campaigns cannot be controlled by fragile CLI monsters. Config-driven ML runs are required for:

- reproducibility
- hyperparameter tuning
- cloud/cluster execution
- repeated comparison across models/seeds
- airfoil campaigns with XFOIL/CFD datasets
- later multi-fidelity and GNN workflows

## New files

- `configs/ml/model_params_gradient_boosting.json`
- `configs/ml/compare_model_params.json`
- `tests/ml/test_config_driven_train.py`
- `documents/AERIS_CHECKPOINT_11_ML_CONFIG_DRIVEN_TRAINING.md`

## Patched files

- `src/aeris/ml/config.py`
- `src/aeris/ml/train.py`
- `src/aeris/commands/ml.py`
- `tests/commands/test_ml_cli.py`

## Example commands

Train from YAML:

```bash
aeris ml train --config configs/ml/tabular_baseline.yaml
```

Train from YAML but override output dir:

```bash
aeris ml train \
  --config configs/ml/tabular_baseline.yaml \
  --output-dir data/processed/ml_runs/test_config_run
```

Train from CLI with model parameters JSON:

```bash
aeris ml train \
  --dataset data/datasets/<promoted_dataset> \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --model-type gradient_boosting \
  --model-params-json configs/ml/model_params_gradient_boosting.json \
  --split-method grouped
```

Compare models with per-model params:

```bash
aeris ml compare \
  --dataset data/datasets/<promoted_dataset> \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --models random_forest,gradient_boosting \
  --model-params-json configs/ml/compare_model_params.json \
  --split-method grouped
```

## Validation commands

```bash
pytest tests/ml/test_config_driven_train.py
pytest tests/ml/test_train.py::test_train_linear_regression_grouped
pytest tests/ml/test_train.py::test_train_random_forest_random_split
pytest tests/ml/test_train.py::test_train_ridge_writes_coefficients
pytest tests/commands/test_ml_cli.py
```

## Next slice

Next should be ML tuning infrastructure:

- `src/aeris/ml/tune.py`
- tuning search spaces
- grouped CV / repeated grouped split
- trial manifests
- best model export
- compare across seeds and hyperparameters
