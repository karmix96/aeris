# AERIS CLI Quick Reference

Compact command sheet for day-to-day AERIS operation.

Use this when you already know the workflow and just need the command. For deeper explanation, use `documents/AERIS_USER_GUIDE.md`.

---

## 1. General

```bash
aeris version
aeris --help
aeris geometry --help
aeris dataset --help
aeris aero --help
aeris dynamics --help
aeris ml --help
```

---

## 2. Geometry

Generate one deterministic geometry from config:

```bash
aeris geometry generate -c configs/geometry/baseline_bwb.yaml
```

Generate one sampled BWB geometry:

```bash
aeris geometry generate -c configs/geometry/wing_bwb.yaml
```

---

## 3. Geometry Dataset

Small LHS geometry dataset:

```bash
aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 20 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --no-save-plot \
  --name geom_lhs20_v1
```

Random sampler check:

```bash
aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 20 \
  --sampler random_v1 \
  --sampler-seed 123 \
  --no-save-plot \
  --name geom_random20_v1
```

Inspect dataset:

```bash
aeris dataset inspect --dataset data/datasets/geom_lhs20_v1
```

---

## 4. Aero Single Run

Fresh geometry from config:

```bash
aeris aero run \
  --config configs/geometry/baseline_bwb_25.yaml \
  --alpha 4 \
  --beta 0 \
  --velocity 28 \
  --altitude 1500 \
  --solver aerosandbox_avl \
  --output-name aero_single_baseline
```

From existing geometry run:

```bash
aeris aero run \
  --run-dir data/runs/<geometry_run_dir> \
  --alpha 4 \
  --beta 0 \
  --velocity 28 \
  --altitude 1500 \
  --solver aerosandbox_avl
```

Inspect aero result:

```bash
aeris aero inspect --run-dir data/runs/<aero_run_dir>
```

---

## 5. Aero Sweep

```bash
aeris aero sweep \
  --config configs/geometry/baseline_bwb_25.yaml \
  --alpha-values -2,0,2,4,6 \
  --beta-values 0 \
  --velocity-values 28 \
  --altitude-values 1500 \
  --control-input-values -5,0,5 \
  --solver aerosandbox_avl \
  --output-name aero_sweep_baseline
```

Inspect sweep:

```bash
aeris aero sweep-inspect --sweep-dir data/runs/<sweep_run_dir>
```

Inspect one sweep case:

```bash
aeris aero sweep-case-inspect \
  --sweep-dir data/runs/<sweep_run_dir> \
  --case-id case_0000
```

---

## 6. Unified Aero Dataset

Generate geometry + aero dataset:

```bash
aeris dataset aero-generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 50 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --name bwb_aero_v1 \
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

Curate aero dataset:

```bash
aeris dataset curate-aero --dataset data/datasets/bwb_aero_v1
```

Promote aero dataset:

```bash
aeris dataset promote-aero --dataset data/datasets/bwb_aero_v1
```

Require promoted dataset gate:

```bash
aeris dataset require-promoted-aero --dataset data/datasets/bwb_aero_v1
```

Run post-hoc aero QC:

```bash
aeris dataset aero-qc \
  --dataset data/datasets/bwb_aero_v1 \
  --profile basic
```

---

## 7. Dynamics

Build dynamics foundation:

```bash
aeris dynamics build \
  --run-dir data/runs/<aero_run_dir> \
  --mass-config configs/mass/baseline_uav.yaml
```

Inspect dynamics:

```bash
aeris dynamics inspect --run-dir data/runs/<aero_run_dir>
```

CG sweep:

```bash
aeris dynamics cg-sweep \
  --run-dir data/runs/<aero_run_dir> \
  --mass-config configs/mass/baseline_uav.yaml \
  --x-cg-min 0.30 \
  --x-cg-max 0.70 \
  --n 21
```

Trim diagnostic:

```bash
aeris dynamics trim --run-dir data/runs/<aero_run_dir>
```

---

## 8. ML Schema and Feature Presets

List feature presets:

```bash
aeris ml feature-presets
```

Validate promoted dataset schema:

```bash
aeris ml validate-schema \
  --dataset data/datasets/bwb_aero_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --group-column geometry_id
```

---

## 9. ML Training

Train with explicit features:

```bash
aeris ml train \
  --dataset data/datasets/bwb_aero_v1 \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/et_bwb_v1
```

Train with feature preset:

```bash
aeris ml train \
  --dataset data/datasets/bwb_aero_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/et_bwb_v1
```

---

## 10. ML Model Comparison

Compare models on one split:

```bash
aeris ml compare \
  --dataset data/datasets/bwb_aero_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --models linear_regression,ridge,random_forest,gradient_boosting,extra_trees,hist_gradient_boosting \
  --split-method grouped \
  --group-column geometry_id \
  --random-seed 123 \
  --output-dir data/processed/ml_runs/compare_bwb_v1
```

Compare across seeds:

```bash
aeris ml compare-seeds \
  --dataset data/datasets/bwb_aero_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --models linear_regression,ridge,random_forest,gradient_boosting,extra_trees,hist_gradient_boosting \
  --seeds 101,202,303,404,505 \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/compare_seed_stability_bwb_v1
```

---

## 11. ML Tuning

AERIS built-in tuner:

```bash
aeris ml tune \
  --backend aeris \
  --dataset data/datasets/bwb_aero_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --param-space-json configs/ml/tune_extra_trees_optuna_space.json \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/tune_et_aeris_v1
```

Optuna tuner:

```bash
aeris ml tune \
  --backend optuna \
  --dataset data/datasets/bwb_aero_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --param-space-json configs/ml/tune_extra_trees_optuna_space.json \
  --n-trials 50 \
  --optuna-sampler tpe \
  --split-method grouped \
  --group-column geometry_id \
  --random-seed 123 \
  --selection-metric val.rmse_mean \
  --minimize \
  --output-dir data/processed/ml_runs/tune_et_optuna_v1
```

Persistent Optuna study:

```bash
aeris ml tune \
  --backend optuna \
  --storage sqlite:///data/processed/ml_runs/optuna_studies/aeris.db \
  --study-name et_bwb_v1 \
  --dataset data/datasets/bwb_aero_v1 \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --param-space-json configs/ml/tune_extra_trees_optuna_space.json \
  --n-trials 50 \
  --output-dir data/processed/ml_runs/tune_et_optuna_v1
```

Compare tuning runs:

```bash
aeris ml compare-tuning-runs \
  --runs data/processed/ml_runs/tune_gb_v1,data/processed/ml_runs/tune_rf_v1,data/processed/ml_runs/tune_et_optuna_v1 \
  --selection-metric val.rmse_mean \
  --minimize \
  --output-dir data/processed/ml_runs/compare_tuning_runs_v1
```

---

## 12. ML Model Promotion and Prediction

Promote model:

```bash
aeris ml promote-model \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --max-test-rmse-mean 0.001 \
  --min-test-r2-mean 0.99
```

Inspect model:

```bash
aeris ml inspect-model --model-run-dir data/processed/ml_runs/et_bwb_v1
```

Require promoted model gate:

```bash
aeris ml require-promoted-model --model-run-dir data/processed/ml_runs/et_bwb_v1
```

Check inference inputs against training envelope:

```bash
aeris ml check-inference-inputs \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --input-csv data/processed/ml_runs/et_bwb_v1/train_rows.csv
```

Guarded prediction:

```bash
aeris ml predict \
  --model-run-dir data/processed/ml_runs/et_bwb_v1 \
  --input-csv data/processed/ml_runs/et_bwb_v1/train_rows.csv \
  --require-promoted-model \
  --enforce-envelope \
  --output-dir data/processed/ml_runs/et_bwb_v1/inference/guarded_train_rows
```

---

## 13. Multifidelity ML

Build LF/HF delta dataset:

```bash
aeris ml build-delta-dataset \
  --lf-csv data/processed/multifidelity/lf.csv \
  --hf-csv data/processed/multifidelity/hf.csv \
  --pair-keys geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --output-dir data/processed/multifidelity/delta_v1
```

Train delta model:

```bash
aeris ml train-delta-model \
  --delta-dataset data/processed/multifidelity/delta_v1 \
  --features c1_m,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm \
  --base-targets cl,cd,cm \
  --model-type extra_trees \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_runs/delta_et_v1
```

Predict corrected outputs:

```bash
aeris ml predict-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_v1 \
  --input-csv data/processed/ml_runs/delta_et_v1/test_rows.csv \
  --output-dir data/processed/ml_runs/delta_et_v1/delta_inference/test
```

Evaluate whether correction helped:

```bash
aeris ml evaluate-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_v1 \
  --output-dir data/processed/ml_runs/delta_et_v1/multifidelity_evaluation
```

---

## 14. Testing

Focused ML tests:

```bash
pytest tests/ml tests/commands/test_ml*.py
```

Full test suite:

```bash
pytest
```

---

## 15. Codebase Snapshot

Generate `codebase.txt` from `.py`, `.txt`, and `.yaml` files only:

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

## 16. Git

```bash
git status
git add <files>
git commit -m "Message"
git push origin main
```

---

## Operator rules

- Use `--no-save-plot` for production dataset generation.
- Use grouped ML splits by `geometry_id` to avoid leakage.
- Do not train ML on raw or curated-only datasets; use promoted datasets.
- Do not trust a trained model until it is promoted.
- Use `--require-promoted-model` and `--enforce-envelope` before downstream use.
- Multifidelity tools consume LF/HF scalar products; they do not run CFD or XFOIL.
