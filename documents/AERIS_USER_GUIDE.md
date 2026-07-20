# AERIS User Guide

**Current scope:** AERIS is a modular, CLI-driven aircraft design and analysis platform for deterministic geometry generation, aerodynamic evaluation, dataset production, QC/curation/promotion, scalar ML surrogate modeling, model trust gates, and scalar multifidelity delta learning.

AERIS is **not** a loose folder of scripts. It is an engineering pipeline with explicit interfaces, registries, structured artifacts, manifests, and command-line control.

---

## 1. What AERIS currently does

AERIS currently supports this production-style chain:

```text
geometry generation
→ geometry dataset generation
→ AVL/AeroSandbox aero runs and sweeps
→ unified aero datasets
→ QC
→ curation
→ dataset promotion
→ ML training/tuning/comparison
→ model promotion
→ guarded inference
→ LF/HF delta dataset construction
→ delta-model training
→ multifidelity evaluation
```

The current aerodynamic solver path is AVL through AeroSandbox. This means AERIS currently provides **linear/panel-method aerodynamic evaluation around operating points**, not CFD and not a flight simulator.

### Current strong capabilities

- Deterministic BWB geometry generation via `bwb_segmented_v1`.
- Modular dataset sampling: `lhs_v1`, `random_v1`.
- Single aero cases and aero sweeps.
- Unified aero dataset generation.
- Geometry and aero QC presets.
- Aero dataset curation and promotion.
- ML training on promoted datasets only.
- Feature presets and schema validation.
- Model comparison, seed-stability comparison, tuning, and Optuna tuning.
- Model promotion and promoted-model gate.
- Inference-envelope guard.
- Multifidelity LF/HF pairing, delta-model training, and correction evaluation.

### Not solved yet

- Full CFD execution inside AERIS.
- XFOIL / SU2 / OpenFOAM operational adapters.
- Field prediction, Cp prediction, mesh learning, GNNs, or neural operators.
- Active learning campaign orchestration.
- Full MDAO loop.
- Full nonlinear trim and eigenvalue flight dynamics.

Do not confuse “pipeline spine exists” with “all physics are solved.” That is how software starts lying to its owner.

---

## 2. Project layout

Typical repo structure:

```text
configs/                  YAML experiment/config templates
data/                     generated outputs, datasets, runs, processed ML artifacts
src/aeris/                AERIS package source
tests/                    unit and CLI tests
documents/                checkpoints, guides, roadmap notes
scripts/                  debugging / campaign helpers, not primary production API
codebase.txt              generated source snapshot for review
```

Important source areas:

```text
src/aeris/commands/       Typer CLI command groups
src/aeris/common/         shared config/path/logging helpers
src/aeris/geometry/       geometry framework / registry / generic geometry logic
src/aeris/generators/     concrete geometry family implementations
src/aeris/dataset/        dataset generation, QC, curation, promotion, training-data helpers
src/aeris/aero/           aero models, solvers, views, runs, sweeps, inspection
src/aeris/dynamics/       mass/CG/static-margin/trim foundation
src/aeris/ml/             scalar ML, tuning, trust gates, prediction, multifidelity
src/aeris/pipeline/       workflow orchestration such as geometry and smoke runs
```

### Design rule

Production execution should go through the CLI:

```bash
aeris <group> <command> [options]
```

Scripts are useful for debugging and one-off campaigns, but they should not become the main operating surface.

---

## 3. Basic commands

### Check installation

```bash
aeris version
```

### Show help

```bash
aeris --help
aeris geometry --help
aeris dataset --help
aeris aero --help
aeris dynamics --help
aeris ml --help
aeris pipeline --help
```

---

# 4. Geometry commands

## 4.1 `aeris geometry info`

Checks that the geometry command group is available.

```bash
aeris geometry info
```

## 4.2 `aeris geometry generate`

Generates one deterministic geometry from a YAML config.

```bash
aeris geometry generate -c configs/geometry/baseline_bwb.yaml
```

or:

```bash
aeris geometry generate --config configs/geometry/wing_bwb.yaml
```

Outputs a run folder under:

```text
data/runs/<timestamp>_geometry_<name>/
```

Typical artifacts:

```text
input_config.yaml
manifest.json
logs/app.log
artifacts/geometry/geometry_summary.json
artifacts/geometry/control_points.csv
artifacts/geometry/planform_sections.csv
artifacts/geometry/section_3d.csv
artifacts/geometry/planform.png
```

## 4.3 `aeris geometry visualize`

Generates/visualizes one geometry case with optional plot and AeroSandbox 3D draw.

```bash
aeris geometry visualize \
  -c configs/geometry/wing_bwb.yaml \
  --seed 123 \
  --save-plot \
  --build-aerosandbox \
  --output-dir data/debug/visualization_runs/wing_debug \
  --show-plot \
  --draw-3d
```

Useful options:

```text
--seed
--save-plot / --no-save-plot
--build-aerosandbox / --no-build-aerosandbox
--output-dir
--show-plot / --no-show-plot
--draw-3d / --no-draw-3d
```

Use visualization for inspection, not large production campaigns.

---

# 5. Dataset commands

## 5.1 `aeris dataset generate`

Generates a geometry-only dataset.

```bash
aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 100 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --name wing_bwb_geom_n100 \
  --no-save-plot \
  --build-aerosandbox \
  --qc-preset production
```

Important options:

```text
--config, -c
--n
--sampler
--sampler-seed
--name
--save-plot / --no-save-plot
--build-aerosandbox / --no-build-aerosandbox
--run-qc / --no-run-qc
--qc-profile
--qc-preset
--fail-on-qc-error / --allow-qc-errors
```

Recommended production habit:

```bash
--no-save-plot
```

Plots are expensive. They are for inspection, not data factories.

## 5.2 `aeris dataset inspect`

Inspects a dataset root.

```bash
aeris dataset inspect --dataset data/datasets/wing_bwb_geom_n100
```

## 5.3 `aeris dataset qc`

Runs geometry QC on an existing geometry dataset.

```bash
aeris dataset qc \
  --dataset data/datasets/wing_bwb_geom_n100 \
  --profile basic
```

## 5.4 `aeris dataset aero-generate`

Generates geometries and runs aero sweeps for each geometry, producing a unified aero dataset.

```bash
aeris dataset aero-generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 50 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --name bwb_aero_n50_v1 \
  --no-save-plot \
  --build-aerosandbox \
  --alpha-values -2,0,2,4,6 \
  --beta-values 0 \
  --velocity-values 20,28,35 \
  --altitude-values 1500 \
  --p-values 0 \
  --q-values 0 \
  --r-values 0 \
  --control-input-values -5,0,5 \
  --solver aerosandbox_avl \
  --timeout-sec 180 \
  --spanwise-resolution 4 \
  --chordwise-resolution 8 \
  --retain-aero-runs failures_only \
  --qc-preset production
```

Important options:

```text
--alpha-values
--beta-values
--velocity-values
--altitude-values
--p-values
--q-values
--r-values
--control-input-values
--solver
--avl-command
--timeout-sec
--spanwise-resolution
--chordwise-resolution
--spanwise-spacing
--chordwise-spacing
--save-surface-forces
--save-element-forces
--max-cases
--keep-geometry-dataset / --delete-geometry-dataset
--retain-aero-runs all|failures_only|none
--run-geometry-qc / --no-run-geometry-qc
--run-aero-qc / --no-run-aero-qc
--qc-preset
```

Main outputs:

```text
data/datasets/<name>/aero_dataset.csv
data/datasets/<name>/aero_failures.csv
data/datasets/<name>/aero_dataset_manifest.json
data/datasets/<name>/final_run_summary.json
```

## 5.5 `aeris dataset aero-qc`

Runs aero QC on an existing aero dataset.

```bash
aeris dataset aero-qc \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --profile basic
```

## 5.6 `aeris dataset curate-aero`

Curates an aero dataset into ML-ready rows.

```bash
aeris dataset curate-aero \
  --dataset data/datasets/bwb_aero_n50_v1
```

Default behavior rejects:

```text
incomplete sweep groups
geometries with failed aero cases
non-finite targets
control diagnostic failures
```

Useful toggles:

```text
--reject-incomplete-groups / --keep-incomplete-groups
--reject-groups-with-failures / --keep-groups-with-failures
--reject-nonfinite-targets / --keep-nonfinite-targets
--reject-control-diagnostic-failures / --keep-control-diagnostic-failures
--json
```

Outputs:

```text
curated_aero_dataset.csv
rejected_aero_rows.csv
curation_report.json
```

## 5.7 `aeris dataset promote-aero`

Promotes a curated aero dataset for trusted downstream use.

```bash
aeris dataset promote-aero \
  --dataset data/datasets/bwb_aero_n50_v1
```

Force promotion, only when you really mean it:

```bash
aeris dataset promote-aero \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --force
```

Outputs:

```text
promotion_manifest.json
```

Rule:

```text
ML should consume promoted datasets, not raw or merely curated datasets.
```

## 5.8 `aeris dataset require-promoted-aero`

Checks whether a dataset is promoted and usable downstream.

```bash
aeris dataset require-promoted-aero \
  --dataset data/datasets/bwb_aero_n50_v1
```

Allow forced promotions explicitly:

```bash
aeris dataset require-promoted-aero \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --allow-forced
```

## 5.9 `aeris dataset training-data`

Loads promoted dataset columns for ML training readiness checks.

```bash
aeris dataset training-data \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm
```

## 5.10 `aeris dataset split-training-data`

Creates deterministic train/validation/test splits.

```bash
aeris dataset split-training-data \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --method grouped \
  --group-column geometry_id \
  --train-fraction 0.70 \
  --val-fraction 0.15 \
  --test-fraction 0.15 \
  --random-seed 123
```

Use grouped splitting when multiple rows come from the same geometry. Otherwise you get leakage, and leakage is not “good performance”; it is cheating with extra steps.

---

# 6. Aero commands

## 6.1 `aeris aero run`

Runs one aero case.

Fresh geometry from config:

```bash
aeris aero run \
  -c configs/geometry/baseline_bwb_25.yaml \
  --alpha 4 \
  --beta 0 \
  --velocity 28 \
  --altitude 1500 \
  --control-input-deg 0 \
  --solver aerosandbox_avl \
  --spanwise-resolution 4 \
  --chordwise-resolution 8 \
  --output-name baseline_aero_a4
```

Existing run directory:

```bash
aeris aero run \
  --run-dir data/runs/<geometry_run> \
  --generator-id bwb_segmented_v1 \
  --alpha 4 \
  --velocity 28 \
  --altitude 1500
```

Existing dataset geometry:

```bash
aeris aero run \
  --dataset data/datasets/<dataset_name> \
  --geometry-id geom_00001 \
  --generator-id bwb_segmented_v1 \
  --alpha 4 \
  --velocity 28 \
  --altitude 1500
```

Important options:

```text
--config, -c
--run-dir
--dataset
--geometry-id
--geometry-source auto|native|reconstruct
--generator-id
--alpha
--beta
--velocity
--altitude
--mach
--p
--q
--r
--control-input-deg
--solver
--avl-command
--timeout-sec
--spanwise-resolution
--chordwise-resolution
--spanwise-spacing
--chordwise-spacing
--save-surface-forces
--save-element-forces
--seed
--output-name
```

## 6.2 `aeris aero inspect`

Inspects a saved single aero result.

```bash
aeris aero inspect --run-dir data/runs/<aero_run>
```

JSON:

```bash
aeris aero inspect --run-dir data/runs/<aero_run> --json
```

## 6.3 `aeris aero sweep`

Runs an aero sweep for one geometry source.

```bash
aeris aero sweep \
  -c configs/geometry/baseline_bwb_25.yaml \
  --alpha-values -2,0,2,4,6 \
  --beta-values 0 \
  --velocity-values 20,28,35 \
  --altitude-values 1500 \
  --control-input-values -5,0,5 \
  --solver aerosandbox_avl \
  --spanwise-resolution 4 \
  --chordwise-resolution 8 \
  --max-cases 100 \
  --output-name baseline_sweep
```

Use `--max-cases` when experimenting. It is a cheap seatbelt.

## 6.4 `aeris aero sweep-inspect`

Inspects a sweep summary.

```bash
aeris aero sweep-inspect --run-dir data/runs/<sweep_run>
```

## 6.5 `aeris aero sweep-case-inspect`

Inspects one case from a sweep.

```bash
aeris aero sweep-case-inspect \
  --run-dir data/runs/<sweep_run> \
  --case-index 0
```

or:

```bash
aeris aero sweep-case-inspect \
  --run-dir data/runs/<sweep_run> \
  --case-label <exact_case_label>
```

---

# 7. Dynamics commands

The dynamics layer is a foundation layer. It computes mass/CG/static-margin related artifacts from aero results. It is **not** a full flight simulator.

## 7.1 `aeris dynamics build`

Builds dynamics foundation artifacts from a saved aero run.

```bash
aeris dynamics build \
  --run-dir data/runs/<aero_run> \
  --mass-config configs/mass/baseline_uav.yaml
```

With explicit mass and CG:

```bash
aeris dynamics build \
  --run-dir data/runs/<aero_run> \
  --mass-kg 12.5 \
  --x-cg-m 0.40 \
  --y-cg-m 0.0 \
  --z-cg-m 0.0 \
  --ixx-kg-m2 0.80 \
  --iyy-kg-m2 1.50 \
  --izz-kg-m2 2.10
```

## 7.2 `aeris dynamics inspect`

```bash
aeris dynamics inspect --run-dir data/runs/<aero_run>
```

## 7.3 `aeris dynamics cg-sweep`

Runs a CG sweep and static-margin diagnostic.

```bash
aeris dynamics cg-sweep \
  --run-dir data/runs/<aero_run> \
  --mass-config configs/mass/baseline_uav.yaml \
  --cg-min-m 0.30 \
  --cg-max-m 0.70 \
  --n 21
```

## 7.4 `aeris dynamics cg-sweep-inspect`

```bash
aeris dynamics cg-sweep-inspect --run-dir data/runs/<aero_run>
```

## 7.5 `aeris dynamics trim`

Runs a first-order longitudinal trim diagnostic.

```bash
aeris dynamics trim --run-dir data/runs/<aero_run>
```

This is a linearized diagnostic based on current `Cm`, `Cma`, and alpha. It is not full nonlinear trim and not control-surface trim.

---

# 8. ML commands

The ML layer is designed around trust gates:

```text
promoted aero dataset
→ schema validation
→ train/tune/compare
→ model promotion
→ promoted-model gate
→ inference-envelope guard
→ guarded prediction
```

## 8.1 Feature presets

### `aeris ml feature-presets`

Lists available named feature presets.

```bash
aeris ml feature-presets
```

Current practical preset:

```text
bwb_control
```

which expands to typical BWB scalar-surrogate features:

```text
c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg
```

## 8.2 `aeris ml validate-schema`

Validates that a promoted dataset has required features, targets, and group columns.

```bash
aeris ml validate-schema \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --group-column geometry_id
```

Equivalent explicit feature version:

```bash
aeris ml validate-schema \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --group-column geometry_id
```

## 8.3 `aeris ml train`

Trains one scalar surrogate model.

```bash
aeris ml train \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --random-seed 123 \
  --output-dir data/processed/ml_runs/et_bwb_v1
```

Supported model types currently include:

```text
linear_regression
ridge
elastic_net
random_forest
extra_trees
gradient_boosting
hist_gradient_boosting
```

Useful options:

```text
--config, -c
--dataset
--features
--feature-preset
--targets
--model-type
--split-method grouped|random
--group-column
--train-fraction
--val-fraction
--test-fraction
--random-seed
--allow-forced
--model-params-json
--output-dir
```

## 8.4 `aeris ml compare`

Compares multiple model types on the same split.

```bash
aeris ml compare \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --models linear_regression,ridge,random_forest,gradient_boosting,extra_trees,hist_gradient_boosting \
  --split-method grouped \
  --group-column geometry_id \
  --random-seed 123 \
  --output-dir data/processed/ml_runs/compare_bwb_v1
```

Outputs include comparison summaries and rankings.

## 8.5 `aeris ml tune`

Tunes one model type.

### AERIS backend

Deterministic grid/random tuning:

```bash
aeris ml tune \
  --backend aeris \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type random_forest \
  --param-space-json configs/ml/tune_random_forest_space.json \
  --strategy random \
  --max-trials 20 \
  --split-method grouped \
  --group-column geometry_id \
  --random-seed 123 \
  --output-dir data/processed/ml_runs/tune_rf_bwb_v1
```

### Optuna backend

Advanced tuning with persistent studies:

```bash
aeris ml tune \
  --backend optuna \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --param-space-json configs/ml/tune_extra_trees_optuna_space.json \
  --n-trials 50 \
  --optuna-sampler tpe \
  --storage sqlite:///data/processed/ml_runs/optuna_studies/aeris.db \
  --study-name et_bwb_v1 \
  --load-if-exists \
  --split-method grouped \
  --group-column geometry_id \
  --selection-metric val.rmse_mean \
  --minimize \
  --output-dir data/processed/ml_runs/tune_et_bwb_v1
```

Useful tuning options:

```text
--backend aeris|optuna
--param-space-json
--strategy grid|random
--max-trials
--n-trials
--tuning-random-seed
--optuna-sampler tpe|random
--study-name
--storage
--load-if-exists / --no-load-if-exists
--selection-metric
--minimize / --maximize
--fail-policy continue|raise
```

## 8.6 `aeris ml compare-seeds`

Checks model stability across multiple split seeds.

```bash
aeris ml compare-seeds \
  --dataset data/datasets/bwb_aero_n50_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --models linear_regression,ridge,random_forest,gradient_boosting,extra_trees,hist_gradient_boosting \
  --seeds 101,202,303,404,505 \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/compare_seed_stability_bwb_v1
```

This answers:

```text
Did the model win consistently, or did it just get lucky once?
```

## 8.7 `aeris ml compare-tuning-runs`

Compares completed tuning campaigns.

```bash
aeris ml compare-tuning-runs \
  --runs data/processed/ml_runs/tune_gb_v1,data/processed/ml_runs/tune_rf_v1,data/processed/ml_runs/tune_et_v1 \
  --selection-metric val.rmse_mean \
  --minimize \
  --output-dir data/processed/ml_runs/compare_tuning_v1
```

## 8.8 `aeris ml promote-model`

Promotes a trained model for trusted downstream use.

```bash
aeris ml promote-model \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --max-test-rmse-mean 0.001 \
  --min-test-r2-mean 0.99
```

Useful options:

```text
--max-val-rmse-mean
--max-test-rmse-mean
--min-test-r2-mean
--require-diagnostics / --no-require-diagnostics
--allow-forced-dataset
--notes
```

Outputs:

```text
model_promotion_manifest.json
model_card.json
training_envelope.json
```

## 8.9 `aeris ml inspect-model`

```bash
aeris ml inspect-model \
  --model-run-dir data/processed/ml_runs/et_bwb_v1
```

## 8.10 `aeris ml require-promoted-model`

Checks that a model has approved promotion status and untampered artifacts.

```bash
aeris ml require-promoted-model \
  --model-run-dir data/processed/ml_runs/et_bwb_v1
```

Skip hash verification only for debugging:

```bash
aeris ml require-promoted-model \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --no-verify-hashes
```

## 8.11 `aeris ml check-inference-inputs`

Checks whether an input CSV is inside the promoted model's training envelope.

```bash
aeris ml check-inference-inputs \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --input-csv data/processed/ml_runs/et_bwb_v1/train_rows.csv
```

Strict mode:

```bash
aeris ml check-inference-inputs \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --input-csv new_candidates.csv \
  --fail-on-violations
```

Important behavior:

```text
The training envelope is based on train_rows.csv, not the full curated dataset.
```

So validation/test rows can legitimately sit outside the train envelope.

## 8.12 `aeris ml predict`

Runs scalar model prediction.

```bash
aeris ml predict \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --input-csv data/processed/ml_runs/et_bwb_v1/train_rows.csv \
  --require-promoted-model \
  --enforce-envelope \
  --output-dir data/processed/ml_runs/et_bwb_v1/inference/guarded_train_rows
```

Useful options:

```text
--require-promoted-model
--enforce-envelope
--envelope-tolerance
--include-truth-if-available / --no-include-truth-if-available
```

If you predict on training rows, expect nearly perfect metrics. That proves the gate works; it does not prove generalization.

---

# 9. Multifidelity ML commands

The current multifidelity layer is scalar and data-product based. It does **not** run CFD. It consumes LF/HF scalar CSVs and learns corrections.

## 9.1 `aeris ml build-delta-dataset`

Pairs LF/HF rows and computes deltas.

```bash
aeris ml build-delta-dataset \
  --lf-csv data/processed/multifidelity/lf.csv \
  --hf-csv data/processed/multifidelity/hf.csv \
  --pair-keys geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --output-dir data/processed/multifidelity/delta_v1
```

Creates:

```text
delta_dataset.csv
delta_dataset_report.json
```

Columns include:

```text
lf__cl, hf__cl, delta__cl
lf__cd, hf__cd, delta__cd
lf__cm, hf__cm, delta__cm
```

## 9.2 `aeris ml train-delta-model`

Trains a model to predict deltas.

```bash
aeris ml train-delta-model \
  --delta-dataset data/processed/multifidelity/delta_v1 \
  --features c1_m,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm \
  --base-targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --random-seed 123 \
  --output-dir data/processed/ml_runs/delta_et_v1
```

It trains:

```text
features → delta__cl, delta__cd, delta__cm
```

## 9.3 `aeris ml predict-delta-model`

Applies the learned correction.

```bash
aeris ml predict-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_v1 \
  --input-csv data/processed/ml_runs/delta_et_v1/test_rows.csv \
  --output-dir data/processed/ml_runs/delta_et_v1/delta_inference/test
```

Produces corrected columns:

```text
pred__delta__cl
pred_corrected__cl = lf__cl + pred__delta__cl
```

and equivalent columns for `cd`, `cm`, etc.

## 9.4 `aeris ml evaluate-delta-model`

Evaluates whether multifidelity correction improved over the LF baseline.

```bash
aeris ml evaluate-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_v1 \
  --partitions train,val,test \
  --output-dir data/processed/ml_runs/delta_et_v1/multifidelity_evaluation
```

Outputs:

```text
multifidelity_evaluation_report.json
multifidelity_evaluation_rows.csv
```

It compares:

```text
LF baseline:      lf__target vs hf__target
Corrected output: pred_corrected__target vs hf__target
```

This is the command that answers:

```text
Did the correction actually help?
```

---

# 10. Pipeline command

## `aeris pipeline smoke`

Runs a lightweight sanity workflow.

```bash
aeris pipeline smoke -c configs/smoke/dev.yaml
```

Bad-config check:

```bash
aeris pipeline smoke -c configs/smoke/bad.yaml
```

Smoke is not full validation. It is a quick health check.

---

# 11. GUI command

## `aeris gui run`

Runs the experimental GUI.

```bash
aeris gui run
```

The GUI is not the trusted production interface yet. The CLI remains the serious operator surface.

---

# 12. End-to-end workflows

## 12.1 Geometry-only dataset workflow

```bash
aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 500 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --name geom_n500_v1 \
  --no-save-plot \
  --qc-preset production


aeris dataset inspect --dataset data/datasets/geom_n500_v1
```

## 12.2 Full 3D AVL scalar ML workflow

```bash
# 1. Generate aero dataset
aeris dataset aero-generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 100 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --name bwb_aero_ml_v1 \
  --no-save-plot \
  --build-aerosandbox \
  --alpha-values -2,0,2,4,6 \
  --velocity-values 20,28,35 \
  --altitude-values 1500 \
  --control-input-values -5,0,5 \
  --solver aerosandbox_avl \
  --retain-aero-runs failures_only \
  --qc-preset production

# 2. Curate
aeris dataset curate-aero \
  --dataset data/datasets/bwb_aero_ml_v1

# 3. Promote dataset
aeris dataset promote-aero \
  --dataset data/datasets/bwb_aero_ml_v1

# 4. Validate schema
aeris ml validate-schema \
  --dataset data/datasets/bwb_aero_ml_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --group-column geometry_id

# 5. Compare models
aeris ml compare-seeds \
  --dataset data/datasets/bwb_aero_ml_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --models linear_regression,ridge,random_forest,gradient_boosting,extra_trees,hist_gradient_boosting \
  --seeds 101,202,303,404,505 \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/compare_seed_bwb_aero_ml_v1

# 6. Train chosen model
aeris ml train \
  --dataset data/datasets/bwb_aero_ml_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/et_bwb_aero_ml_v1

# 7. Promote model
aeris ml promote-model \
  --model-run-dir data/processed/ml_runs/et_bwb_aero_ml_v1 \
  --max-test-rmse-mean 0.001 \
  --min-test-r2-mean 0.99

# 8. Guarded prediction
aeris ml predict \
  --model-run-dir data/processed/ml_runs/et_bwb_aero_ml_v1 \
  --input-csv data/processed/ml_runs/et_bwb_aero_ml_v1/train_rows.csv \
  --require-promoted-model \
  --enforce-envelope \
  --output-dir data/processed/ml_runs/et_bwb_aero_ml_v1/inference/guarded_train
```

## 12.3 Multifidelity scalar workflow

```bash
# 1. Build paired delta dataset
aeris ml build-delta-dataset \
  --lf-csv data/processed/multifidelity/lf.csv \
  --hf-csv data/processed/multifidelity/hf.csv \
  --pair-keys geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --output-dir data/processed/multifidelity/delta_v1

# 2. Train delta model
aeris ml train-delta-model \
  --delta-dataset data/processed/multifidelity/delta_v1 \
  --features c1_m,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm \
  --base-targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/delta_et_v1

# 3. Predict corrected outputs
aeris ml predict-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_v1 \
  --input-csv data/processed/ml_runs/delta_et_v1/test_rows.csv \
  --output-dir data/processed/ml_runs/delta_et_v1/delta_inference/test

# 4. Evaluate correction benefit
aeris ml evaluate-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_v1 \
  --partitions train,val,test \
  --output-dir data/processed/ml_runs/delta_et_v1/multifidelity_evaluation
```

---

# 13. QC presets

Use presets instead of manually reassembling QC behavior every time.

```text
off               no QC, useful only for quick debugging
debug             run QC but do not block
production        normal trusted workflow; QC failure blocks
promotion_strict  stricter promotion/release mode
```

Practical rule:

```text
debug             development visibility
production        normal dataset runs
promotion_strict  final promotion/release-quality datasets
```

---

# 14. Common shell helpers

Latest dataset:

```bash
latest_dataset="$(ls -td data/datasets/* | head -n 1)"
echo "$latest_dataset"
```

Count geometry folders:

```bash
find "$latest_dataset/geometry" -maxdepth 1 -type d | wc -l
```

Inspect row counts:

```bash
wc -l "$latest_dataset/metadata.csv"
wc -l "$latest_dataset/failures.csv"
```

Tail dataset log:

```bash
tail -n 50 "$latest_dataset/logs/dataset.log"
```

Regenerate `codebase.txt` snapshot with only `.py`, `.txt`, and `.yaml`:

```bash
find . \
  \( -path './.git' -o -path './.venv' -o -path './__pycache__' -o -path './.pytest_cache' -o -path './data' -o -path './src/*.egg-info' \) -prune -o \
  -type f \
  \( -name '*.py' -o -name '*.txt' -o -name '*.yaml' \) \
  ! -name 'codebase.txt' \
  -print0 \
| sort -z \
| while IFS= read -r -d '' file; do
    echo "# =================================================="
    echo "# FILE: ${file#./}"
    echo "# =================================================="
    echo
    cat "$file"
    echo
    echo
  done > codebase.txt
```

---

# 15. Testing commands

Run all ML tests:

```bash
pytest tests/ml tests/commands/test_ml*.py
```

Run focused groups:

```bash
pytest tests/ml/test_inference_guard.py
pytest tests/ml/test_multifidelity_delta_dataset.py
pytest tests/ml/test_multifidelity_delta_model.py
pytest tests/ml/test_multifidelity_evaluation.py
```

Run command tests:

```bash
pytest tests/commands
```

Run everything:

```bash
pytest
```

---

# 16. Git workflow

After a successful slice:

```bash
git status
pytest tests/ml tests/commands/test_ml*.py
git add src tests configs documents codebase.txt
git commit -m "Describe the completed slice"
git push origin main
```

Use small, meaningful commits. Massive mystery commits are future self-sabotage.

---

# 17. Operator rules

1. Use the CLI as the control surface.
2. Use `--no-save-plot` for serious dataset generation.
3. Use grouped splits by `geometry_id` for aero datasets.
4. Do not train from unpromoted datasets.
5. Do not use unpromoted models for downstream prediction.
6. Use inference envelope checks before optimization/MDAO use.
7. Treat forced promotion as an exception, not a lifestyle.
8. Treat multifidelity evaluation as mandatory. A delta model that does not improve error is decoration.
9. Keep solver execution out of `ml/`. ML consumes trusted data products; aero/dataset layers produce them.
10. Keep `codebase.txt` updated after meaningful architecture changes.

---

# 18. Current milestone summary

AERIS is currently a **production-shaped scalar aero/ML platform** for BWB/wing-style 3D AVL datasets.

The trusted scalar ML chain is now:

```text
promoted aero dataset
→ schema validation
→ train / tune / compare
→ model promotion
→ inference guard
→ guarded prediction
```

The scalar multifidelity chain is now:

```text
LF scalar CSV + HF scalar CSV
→ paired delta dataset
→ delta model
→ corrected prediction
→ correction evaluation
```

The next major technical phases should be chosen deliberately:

```text
active learning foundation
CFD/XFOIL data production adapters
field/GNN dataset infrastructure
cluster/cloud execution layer
MDAO/optimization loop
```

Do not start all of them at once. That is how architectures become pasta.


---

# 19. CFD suite (`aeris cfd`)

One-stop pre-process → mesh → solve → post-process pipeline (package
`aeris.cfd`, standalone-capable). Every run resolves its options through
provenance-tracked layers and records everything needed to reproduce it.

## 19.1 The option model (full authority)

Resolution order, recorded per key in `*_effective_options.json`:

    tool default < aeris default < level/preset < topology hints
                 < config overrides < CLI flags < raw pass-through

- **Curated options** (typed, documented, cited) cover the validated knobs.
- **Raw pass-through** reaches ANY native tool option verbatim:
  - case YAML: `pyhyp_options:`, `adflow_options:`, `su2_options:`
  - CLI: `aeris mesh pyhyp --pyhyp-option KEY=VALUE`,
    `aeris cfd solve --solver-option KEY=VALUE` (repeatable)
  - Raw keys win over everything but are flagged in the provenance
    manifest (`overridden_curated_keys`) — full authority, traceable.
- **Presets are data** (`src/aeris/cfd/presets/data/*.yaml`), curated keys
  only, each with a citation. `aeris cfd presets list|show NAME`.

## 19.2 Case specs

One YAML (`schema: aeris.cfd.case.v1`) describes a whole run:

```yaml
schema: aeris.cfd.case.v1
case:
  name: my_case
  geometry:            # exactly ONE of:
    airfoil: naca0012            # 2-D (or a Selig .dat path)
    # cad: my_aircraft.step                                # 3-D CAD solid
    # aeris_config: configs/geometry/baseline_bwb_25.yaml  # AERIS wing
    # surface_dir: data/meshes/bwb_smoke/surface           # pre-built
  surface_mesh:
    topology: airfoil_ogrid_v1   # see `aeris cfd topologies`
    preset: smoke                # or overrides: {...}
  volume_mesh:                   # omit for final-mesh topologies (gmsh)
    preset: smoke                # level/march policy; overrides + pyhyp_options
  solve:
    solver: adflow               # or su2
    preset: rans_ank_nk_v1
    flow: {alpha: 2.0, mach: 0.2, reynolds: 1.0e+6}
    area_ref: 1.094              # HALF-model area for symmetry meshes
    chord_ref: 0.8774
    mpi_np: 4
  post: {reports: [forces]}
```

Run per-stage or end-to-end:

```bash
aeris cfd run case.yaml --stage surface --stage volume --stage solve --stage post
aeris cfd run case.yaml --dry-run     # prepare everything, execute nothing
```

Artifacts per stage land in the workdir with a chained
`case_manifest.json` (sha256 links). Solves also write
`solve_report.json` (normalized across solvers) and `verification.json`
(iterative convergence + mesh QC + hash chain).

## 19.3 Topologies

`aeris cfd topologies` lists the registry. Currently:

| id                    | type | notes |
|-----------------------|------|-------|
| `wing_mid4_v1`        | 3-D structured | coarse screening (pyHyp coarsen=4) |
| `wing_split8_v1`      | 3-D structured | doubled LE/TE blocks |
| `wing_cap4_v1`        | 3-D structured | DSE grid-convergence family |
| `airfoil_ogrid_v1`    | 2-D structured | pyHyp O-grid, NASA TMR validation |
| `airfoil_gmsh_tri_v1` | 2-D unstructured | Gmsh tri + quad BL, SU2 only |
| `cad_gmsh_tet_v1`     | 3-D unstructured | STEP/BREP/IGES solid → farfield-cut tets, SU2 only (tet tier: Euler/wall-function) |

Topologies carry their solver requirements as hints in the surface report
(`pyhyp_hints`, `adflow_hints`) — e.g. the airfoil strip sets
`lift_index: 2` automatically; explicit overrides always win.

## 19.4 Solvers

- **ADflow** (mach-aero conda env, `MACH_AERO_CONDA_PREFIX`): structured
  RANS, `mpirun` MPI, live residual streaming. Strategy preset
  `rans_ank_nk_v1` (single grid + ANK→NK).
  NOTE (this machine, 16 GB): the NK phase OOMs on ~1M-cell meshes —
  use ≤4 ranks and/or `--solver-option useNKSolver=false`.
- **SU2** (own conda env `su2`, `AERIS_SU2_CONDA_PREFIX` /
  `AERIS_SU2_BIN`): consumes the SAME grids — structured CGNS is
  auto-converted to native `.su2` with the node set preserved
  (cross-solver verification stays a same-grid claim). Markers are read
  from the mesh itself. Strategy preset `su2_rans_sa_v1`.
- Standalone single-point solve (replaces `scripts/adflow_smoke.py`):

```bash
aeris cfd solve --grid mesh.cgns -o out --area-ref 1.094 --chord-ref 0.8774 \
    --alpha 2 --mach 0.2 --reynolds 1e6 --np 4 [--solver su2]
```

## 19.5 Post-processing and verification

```bash
aeris cfd summary run1/solve run2/solve      # cross-solver/fidelity table
aeris cfd gci fine/solve med/solve coarse/solve --quantity cl --ratio 1.4
```

`gci` implements the Celik et al. (2008) / ASME V&V 20 three-grid
procedure (observed order, Richardson extrapolation, GCI). The cap4
family and the 2-D O-grid ladder were designed at r ≈ 1.4 for exactly
this.

## 19.6 CFD → ML trust chain

- `aeris.cfd.post.dataset.collect_cfd_dataset(case_dirs, out)` — one row
  per solve with per-row verification gating (converged, valid march,
  ≥4 orders dropped, finite targets) → `cfd_dataset.csv` +
  `cfd_rejected.csv` + gate report.
- `aeris.ml.conformal.fit_conformal_grouped(...)` — per-fidelity
  (Mondrian) conformal intervals so coverage holds within each fidelity.
- `aeris.ml.active_learning.emit_cfd.emit_cfd_cases(ranked_csv,
  template_case, out_dir)` — recommended candidates become runnable case
  YAMLs with the AI's choice recorded as provenance in the case itself.
- `aeris.cfd.post.dataset.trust_chain_artifacts(case_dir)` — the artifact
  chain for `build_evidence_package(extra_artifacts=...)`.

## 19.7 Validation anchor

`configs/cfd/validation_naca0012_tmr.yaml`: NACA 0012 (TMR closed-TE
geometry) at α=10°, M=0.15, Re=6e6 vs the NASA Turbulence Modeling
Resource CFL3D reference (CL 1.0909, CD 0.01231). The config documents
the measured force-vs-residual ladder and the achievable convergence
target for this grid family.

---

## CLI quick reference

For a compact command sheet, see `documents/AERIS_CLI_QUICK_REFERENCE.md`.
