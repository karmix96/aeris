# AERIS

AERIS is a modular aircraft-design and analysis platform for deterministic geometry generation, aerodynamic evaluation, dataset production, ML surrogate training, and multifidelity scalar correction workflows.

It is not a folder of research scripts. The project is organized as a reproducible engineering pipeline with CLI commands, typed modules, structured artifacts, manifests, QC gates, dataset promotion, model promotion, and inference guards.

## Current scope

AERIS currently supports:

- deterministic BWB/wing geometry generation through `bwb_segmented_v1`
- geometry dataset generation using modular samplers such as `lhs_v1` and `random_v1`
- AVL/AeroSandbox-based 3D aerodynamic runs and sweeps
- aero dataset generation, QC, curation, and promotion
- scalar ML training, tuning, model comparison, Optuna tuning, and seed-stability checks
- model promotion and promoted-model prediction gates
- inference-envelope checks for guarded prediction
- scalar multifidelity workflows: LF/HF pairing, delta datasets, delta-model training, corrected predictions, and evaluation

AERIS does **not yet** provide production CFD automation, GNN mesh-field prediction, active learning, full MDAO, or a certified flight-dynamics simulator. Those are future phases.

## Documentation

Start here:

```text
documents/AERIS_USER_GUIDE.md
```

The user guide contains the full operator explanation, CLI command reference, and end-to-end workflows.

Useful checkpoint documents are also stored under `documents/`, but checkpoints are historical development records. The user guide is the main operational document.

## Repository layout

```text
configs/                 YAML configuration files
  geometry/              geometry configs
  mass/                  dynamics/mass-property configs
  ml/                    ML training/tuning templates
  smoke/                 smoke-test configs

data/                    generated outputs; usually not committed
  datasets/              geometry/aero datasets
  processed/             ML runs and postprocessed products
  runs/                  single geometry/aero/dynamics runs

documents/               guides, checkpoints, architecture notes
scripts/                 developer diagnostics and campaign helpers
src/aeris/               AERIS package source
tests/                   unit and CLI tests
```

## Install for development

From the repository root:

```bash
python -m pip install -e .
```

For advanced ML tuning:

```bash
python -m pip install optuna
```

For GUI experiments, install the GUI requirements only when needed:

```bash
python -m pip install -r requirements-gui.txt
```

## Basic sanity checks

```bash
aeris version
aeris --help
pytest tests/ml tests/commands/test_ml*.py
```

## Common workflows

### Generate one geometry

```bash
aeris geometry generate -c configs/geometry/baseline_bwb.yaml
```

### Generate a geometry dataset

```bash
aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 50 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --no-save-plot \
  --name bwb_geom_demo_v1
```

### Run one aero case

```bash
aeris aero run \
  -c configs/geometry/baseline_bwb.yaml \
  --alpha 4 \
  --beta 0 \
  --velocity 28 \
  --altitude 1500 \
  --solver aerosandbox_avl \
  --spanwise-resolution 4 \
  --chordwise-resolution 8
```

### Build an aero dataset for ML

```bash
aeris dataset aero-generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 50 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --name bwb3d_aero_ml_v1 \
  --no-save-plot \
  --build-aerosandbox \
  --alpha-values -2,0,2,4,6 \
  --beta-values 0 \
  --velocity-values 28 \
  --altitude-values 1500 \
  --control-input-values -5,0,5 \
  --solver aerosandbox_avl \
  --retain-aero-runs failures_only \
  --qc-preset production
```

Then curate and promote:

```bash
aeris dataset curate-aero --dataset data/datasets/bwb3d_aero_ml_v1
aeris dataset promote-aero --dataset data/datasets/bwb3d_aero_ml_v1
```

### Train a scalar ML model

```bash
aeris ml train \
  --dataset data/datasets/bwb3d_aero_ml_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/et_bwb3d_v1
```

### Promote and guard a model

```bash
aeris ml promote-model \
  --model-run-dir data/processed/ml_runs/et_bwb3d_v1 \
  --max-test-rmse-mean 0.001 \
  --min-test-r2-mean 0.99

aeris ml predict \
  --model-run-dir data/processed/ml_runs/et_bwb3d_v1 \
  --input-csv data/processed/ml_runs/et_bwb3d_v1/train_rows.csv \
  --require-promoted-model \
  --enforce-envelope \
  --output-dir data/processed/ml_runs/et_bwb3d_v1/inference/guarded_train_rows
```

### Build and evaluate a multifidelity scalar correction

```bash
aeris ml build-delta-dataset \
  --lf-csv path/to/low_fidelity.csv \
  --hf-csv path/to/high_fidelity.csv \
  --pair-keys geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --output-dir data/processed/multifidelity/demo_delta_v1

aeris ml train-delta-model \
  --delta-dataset data/processed/multifidelity/demo_delta_v1 \
  --features c1_m,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm \
  --base-targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/delta_et_demo_v1

aeris ml predict-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_demo_v1 \
  --input-csv data/processed/ml_runs/delta_et_demo_v1/test_rows.csv \
  --output-dir data/processed/ml_runs/delta_et_demo_v1/delta_inference/test

aeris ml evaluate-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_demo_v1 \
  --output-dir data/processed/ml_runs/delta_et_demo_v1/multifidelity_evaluation
```

## Trust-chain rule

For serious usage, the intended flow is:

```text
raw aero dataset
→ QC
→ curation
→ dataset promotion
→ schema validation
→ train/tune/compare
→ model promotion
→ promoted-model gate
→ inference-envelope guard
→ prediction
```

Do not train production ML from raw or curated-only datasets. Use promoted datasets.

## Development rule

Use the CLI for production workflows. Keep scripts as diagnostics, migration references, or campaign helpers. If a workflow becomes important and repeatable, it should eventually become a proper AERIS command.

## Documentation

- Full user guide: `documents/AERIS_USER_GUIDE.md`
- CLI quick reference: `documents/AERIS_CLI_QUICK_REFERENCE.md`
