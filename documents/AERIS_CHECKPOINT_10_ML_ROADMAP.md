# AERIS CHECKPOINT 10 — ML ROADMAP FOR PRODUCTION, MULTI-FIDELITY, ACTIVE LEARNING, AND FIELD/GNN SURROGATES

## Context

AERIS already has a working baseline ML spine:

```text
promoted aero dataset
→ training-data loading
→ grouped/random split
→ model registry
→ train
→ compare
→ predict
```

This checkpoint defines the next ML architecture so the system can grow from baseline scalar sklearn surrogates into a production-grade, multi-fidelity, 2D/3D, field-prediction, active-learning platform without collapsing into script chaos.

## Non-negotiable principles

1. **ML never trains from raw untrusted solver output.** Inputs must pass dataset QC, curation, and promotion unless a deliberately marked experimental mode is used.
2. **ML operates on schemas and dataset products, not generator internals.** BWB, 2D airfoils, 3D wings, AVL, XFOIL, SU2, OpenFOAM, and future solvers must all feed standardized dataset products.
3. **Splits must prevent leakage.** For airfoils: group by `airfoil_id` or `geometry_id`. For 3D geometries: group by `geometry_id`. For field datasets: split by geometry/case, not by random mesh node.
4. **Every ML run must be reproducible.** Save config, seeds, dataset hash, split hash, model params, environment, code version, metrics, residuals, and artifacts.
5. **Do not put solver execution inside `src/aeris/ml/`.** XFOIL/CFD runners belong in solver/external-tool or aero/dataset layers. ML consumes curated products.
6. **Local laptop, PC, cluster, and cloud must use the same artifacts.** Paths must be portable, manifests must be resumable, and parallel jobs must be shardable.
7. **Memory discipline is a feature, not an optimization later.** Field/GNN datasets must use chunked/on-disk formats and lazy loading.
8. **Advanced ML comes after trustworthy scalar baselines.** Neural operators and GNNs are not magic; if the scalar data pipeline is dirty, the GNN becomes an expensive blender.

---

# Target ML folder architecture

Recommended future structure:

```text
src/aeris/ml/
    __init__.py
    config.py
    schemas.py
    fingerprints.py
    manifest.py
    registry.py                  # eventually replaces/extends model_registry.py
    model_registry.py             # current sklearn registry; keep for compatibility
    metrics.py
    diagnostics.py
    preprocessing.py
    features.py
    targets.py
    splits.py                     # wrapper around dataset.splitting if needed
    train.py                      # current scalar trainer; evolve carefully
    compare.py
    predict.py
    tune.py
    cross_validation.py
    experiment.py
    artifacts.py
    io.py
    memory.py

    tabular/
        __init__.py
        trainers.py
        models.py
        pipelines.py
        param_spaces.py

    multifidelity/
        __init__.py
        pairing.py
        delta.py
        residuals.py
        hierarchy.py
        calibration.py

    active_learning/
        __init__.py
        candidate_pool.py
        acquisition.py
        diversity.py
        batch_selection.py
        loop_state.py

    field/
        __init__.py
        schema.py
        mesh_dataset.py
        graph_builder.py
        normalization.py
        dataloaders.py
        metrics.py
        surface_integration.py

    field/gnn/
        __init__.py
        base.py
        meshgraphnet.py
        pointnet.py
        losses.py
        trainer.py

    field/operators/
        __init__.py
        fno.py
        deeponet.py
        trainer.py

    distributed/
        __init__.py
        executor.py
        local.py
        multiprocessing.py
        slurm.py
        cloud.py
        resume.py
```

Some of this may later move to `src/aeris/execution/`, `src/aeris/field/`, or `src/aeris/dataset/builders/`. That is acceptable. The important thing is to keep the interfaces clean.

---

# Phase 10.0 — Immediate ML hardening

Priority: **do before serious training.**

## 10.0.1 Training-data path correctness

Current risk: the promotion gate resolves the promoted/curated dataset, but training loading should use the curated path returned by the promotion context, not assume `dataset_root / curated_aero_dataset.csv` forever.

Tasks:

- Use the promotion context as the source of truth for the curated CSV path.
- Add tests for non-default curated paths.
- Add tests for missing curated CSV, unpromoted dataset, and forced-promotion rejection.

## 10.0.2 ML run manifest

Create:

```text
src/aeris/ml/manifest.py
```

Every training run should write:

```text
ml_run_manifest.json
```

Required fields:

- run ID
- dataset path
- curated CSV path
- dataset hash
- promotion manifest hash
- feature columns
- target columns
- model type
- model params
- split method
- split seed
- split hashes
- Python version
- platform
- package versions where possible
- git commit if available
- artifacts written
- status / failure reason

## 10.0.3 Dataset fingerprinting

Create:

```text
src/aeris/ml/fingerprints.py
```

Functions:

- `file_sha256(path)`
- `dataframe_schema_fingerprint(df)`
- `training_dataset_fingerprint(dataset_root, curated_csv, promotion_manifest)`
- `split_fingerprint(train_rows, val_rows, test_rows)`

## 10.0.4 Config-driven ML experiments

Create:

```text
src/aeris/ml/config.py
configs/ml/tabular_baseline.yaml
```

Support:

```yaml
experiment:
  name: airfoil_xfoil_scalar_baseline
  task_type: tabular_regression

data:
  dataset: data/datasets/<promoted_dataset>
  allow_forced: false
  feature_columns: []
  target_columns: []

split:
  method: grouped
  group_column: geometry_id
  train_fraction: 0.70
  val_fraction: 0.15
  test_fraction: 0.15
  random_seed: 123

model:
  type: gradient_boosting
  params: {}

outputs:
  output_dir: data/processed/ml_runs/<name>
```

Add CLI support later:

```bash
aeris ml train --config configs/ml/tabular_baseline.yaml
```

Keep existing CLI column-based mode for quick experiments.

## 10.0.5 Stronger metrics and diagnostics

Create:

```text
src/aeris/ml/metrics.py
src/aeris/ml/diagnostics.py
```

Add metrics:

- RMSE
- MAE
- R²
- normalized RMSE
- max absolute error
- p50/p90/p95/p99 absolute error
- per-target metrics
- per-regime metrics: alpha bins, Reynolds bins, Mach bins, control bins, fidelity bins

Artifacts:

- `prediction_vs_truth_train.csv`
- `prediction_vs_truth_val.csv`
- `prediction_vs_truth_test.csv`
- `residuals_test.csv`
- `diagnostics_summary.json`

## 10.0.6 Preprocessing pipelines

Create:

```text
src/aeris/ml/preprocessing.py
```

Support:

- no preprocessing
- standard scaling
- robust scaling
- target scaling / inverse transform
- full sklearn `Pipeline` save/load

Linear/ridge/elastic-net should use scaling by default. Tree models can skip scaling.

## 10.0.7 Model params via config/JSON

Add:

```bash
aeris ml train --model-params-json configs/ml/gb_params.json
```

or through YAML config.

---

# Phase 10.1 — Serious model comparison and tuning

Priority: **before claiming “best model.”**

## 10.1.1 Repeated split comparison

The system should compare:

- model A vs model B on identical split
- model A vs itself across multiple seeds
- model A sensitivity to hyperparameters
- model A stability across airfoil/geometry groups

Artifacts:

- `comparison_summary.csv`
- `comparison_summary.json`
- `per_seed_comparison.csv`
- `model_stability_summary.json`

## 10.1.2 Hyperparameter tuning

Create:

```text
src/aeris/ml/tune.py
src/aeris/ml/tabular/param_spaces.py
```

Minimum backend:

- sklearn `ParameterGrid` / `ParameterSampler`

Later backends:

- Optuna
- Ray Tune
- Dask/Ray distributed tuning

Required rules:

- grouped CV only by default
- never tune on final test set
- save every trial
- save failed trials
- save best model separately
- support resume

## 10.1.3 Cross-validation layer

Create:

```text
src/aeris/ml/cross_validation.py
```

Support:

- grouped k-fold
- repeated grouped k-fold
- temporal / campaign split later
- fidelity-aware split later

---

# Phase 10.2 — Airfoil scalar surrogate pipeline for next week

Priority: **urgent for 1000 airfoils with XFOIL + automated CFD.**

This is not only an ML-folder problem. The solver automation belongs outside ML, but ML must be ready to consume the dataset.

## Dataset schema for 2D airfoil scalar learning

Required identifiers:

- `airfoil_id`
- `case_id`
- `geometry_family`
- `geometry_parameterization`: CST, coordinates, NACA, etc.
- `solver_id`: xfoil, openfoam, su2, etc.
- `fidelity_level`: low, high, experimental
- `run_status`
- `converged`
- `failure_reason`

Required operating-condition columns:

- `alpha_deg`
- `reynolds`
- `mach`
- `ncrit` if XFOIL
- `transition_model` if available
- `turbulence_model` if CFD

Geometry features:

- CST coefficients upper/lower
- thickness metrics
- camber metrics
- leading-edge radius if available
- trailing-edge thickness if available
- optional coordinate embedding later

Targets:

- `cl`
- `cd`
- `cm`
- optional `cp_min`
- optional transition location
- optional separation/convergence flags

Immediate ML tasks:

- feature presets for airfoils
- grouped split by `airfoil_id`
- baseline model comparison on XFOIL labels
- residual diagnostics by alpha/Re/Mach
- promotion policy for XFOIL datasets
- later XFOIL→CFD delta model

---

# Phase 10.3 — Multi-fidelity ML

Priority: **after LF/HF datasets exist.**

Create:

```text
src/aeris/ml/multifidelity/
    pairing.py
    delta.py
    residuals.py
    hierarchy.py
    calibration.py
```

Supported approaches, in order:

1. **Delta learning**

```text
target_delta = high_fidelity - low_fidelity
prediction = low_fidelity + ML_delta
```

2. **Stacked features**

Use LF outputs as features:

```text
features = geometry + operating_condition + xfoil_cl + xfoil_cd + xfoil_cm
outputs = cfd_cl, cfd_cd, cfd_cm
```

3. **Residual correction with uncertainty**

Use GP / ensemble / conformal residual intervals.

4. **Co-kriging / autoregressive multi-fidelity**

Later, not first.

Required artifacts:

- `fidelity_pairing_report.json`
- `paired_lf_hf_dataset.csv`
- `delta_dataset.csv`
- `multifidelity_model_manifest.json`

Important rule:

Do not train multi-fidelity models until LF/HF case matching is explicit and auditable.

---

# Phase 10.4 — Active learning

Priority: **after baseline + uncertainty exist.**

Create:

```text
src/aeris/ml/active_learning/
    candidate_pool.py
    acquisition.py
    diversity.py
    batch_selection.py
    loop_state.py
```

Candidate pool:

- generated airfoil/BWB designs
- operating conditions
- solver budget
- excluded failed cases
- already evaluated cases

Acquisition strategies:

- uncertainty sampling
- expected improvement
- max error proxy
- diversity-aware uncertainty
- Pareto/budget-aware selection
- boundary-focused sampling near stall/trim/control limits

Loop artifacts:

- `active_learning_state.json`
- `candidate_pool.parquet`
- `selected_batch.csv`
- `selection_report.json`
- `budget_report.json`

Cluster/cloud readiness:

- selected batch must be shardable into job arrays
- every selected case must have stable `case_id`
- failed solver cases must be requeueable

---

# Phase 10.5 — Field prediction and GNN support

Priority: **after scalar ML and solver artifact schemas are stable.**

Create:

```text
src/aeris/ml/field/
    schema.py
    mesh_dataset.py
    graph_builder.py
    normalization.py
    dataloaders.py
    metrics.py
    surface_integration.py

src/aeris/ml/field/gnn/
    base.py
    meshgraphnet.py
    pointnet.py
    losses.py
    trainer.py
```

2D airfoil field dataset:

- mesh nodes: x, y
- edges / cells
- boundary tags
- geometry coordinates or CST coefficients
- operating condition: alpha, Re, Mach
- targets: Cp, pressure, velocity components, wall shear if available

3D field dataset:

- surface nodes: x, y, z
- normals
- panel/cell area
- connectivity
- boundary/surface region
- operating condition
- targets: Cp, pressure, shear, velocity if available

Graph features:

Node features:

- coordinates
- normals
- local curvature if available
- boundary/surface tags
- global condition broadcast: alpha, beta, Re/Mach, velocity

Edge features:

- relative displacement
- distance
- normalized direction
- optional face relation

Memory strategy:

- store raw mesh/field data in HDF5/Zarr/Parquet, not thousands of loose CSVs
- lazy load graphs
- cache processed graph tensors
- support float32 by default
- chunk large cases
- avoid loading all meshes into RAM

Metrics:

- node-wise RMSE/MAE
- area-weighted Cp error
- integrated CL/CD/CM error from predicted pressure
- per-region error: LE, TE, suction side, pressure side, tip/root

Important rule:

A GNN field model must be judged not only by Cp error but also by whether integrated forces/moments make physical sense.

---

# Phase 10.6 — Parallel, cloud, and cluster execution

This should probably become a shared AERIS execution layer, but ML must be compatible with it.

Create later or coordinate with:

```text
src/aeris/execution/
    base.py
    local.py
    multiprocessing.py
    slurm.py
    cloud.py
    resume.py
```

ML-facing requirements:

- training/tuning trials can be parallelized
- active-learning selected cases can be sharded
- model comparison can run independent models in parallel
- GNN preprocessing can process graph cases in chunks
- all jobs write status manifests
- all jobs are resumable
- no absolute path assumptions
- Windows/Linux path safety via `pathlib`

For next week’s 1000-airfoil campaign:

- run XFOIL cases as shardable batches
- run CFD cases as separate HF queue
- create LF and HF dataset manifests
- use promotion gates before ML
- keep failed cases, do not delete them
- never let solver failure silently become NaN target rows

---

# Immediate build order

## Build Slice 1 — ML reproducibility hardening

Files:

```text
src/aeris/ml/fingerprints.py
src/aeris/ml/manifest.py
src/aeris/ml/config.py
configs/ml/tabular_baseline.yaml
tests/ml/test_fingerprints.py
tests/ml/test_ml_config.py
```

## Build Slice 2 — train.py upgrade

Modify:

```text
src/aeris/ml/train.py
```

Add:

- ML manifest writing
- dataset/promoted-manifest hashes
- prediction-vs-truth CSVs
- residual CSVs
- normalized/error percentile metrics
- full sklearn pipeline object save

## Build Slice 3 — compare/tune upgrade

Modify/add:

```text
src/aeris/ml/compare.py
src/aeris/ml/tune.py
src/aeris/ml/cross_validation.py
```

Add:

- repeated grouped split comparison
- self-comparison across seeds
- grid/random search tuning
- trial manifests
- failed trial handling

## Build Slice 4 — airfoil dataset compatibility

Add:

```text
src/aeris/ml/features.py
src/aeris/ml/targets.py
configs/ml/airfoil_xfoil_baseline.yaml
```

Add feature presets:

- `airfoil_cst_basic`
- `airfoil_operating_basic`
- `airfoil_xfoil_scalar`
- `bwb_geometry_basic`
- `bwb_aero_condition_basic`

## Build Slice 5 — multi-fidelity foundation

Add:

```text
src/aeris/ml/multifidelity/pairing.py
src/aeris/ml/multifidelity/delta.py
```

## Build Slice 6 — field/GNN foundation

Add:

```text
src/aeris/ml/field/schema.py
src/aeris/ml/field/mesh_dataset.py
src/aeris/ml/field/graph_builder.py
```

Only after this should GNN model files be added.

---

# Operator warning

Do not start with GNN code.

Start with:

```text
trusted scalar data → reproducible train/compare/tune → diagnostics → multi-fidelity pairing → active learning → field dataset → GNN
```

That path wins. The opposite path gives you beautiful neural-network code trained on questionable soup.
