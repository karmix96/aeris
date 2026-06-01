# NEXT CHAT PROMPT — AERIS GUI UPDATED, ML + MULTIFIDELITY FOUNDATION COMPLETE

Use this prompt to continue development in the next chat.

## Context

We are building **AERIS**, a modular aircraft design and analysis platform. It is not a pile of scripts. It is a CLI-first, config-driven, reproducible engineering pipeline for:

- deterministic BWB geometry generation,
- geometry and aero dataset generation,
- AVL/AeroSandbox aerodynamic sweeps,
- QC, curation, and dataset promotion,
- scalar ML surrogate modeling,
- model promotion and guarded inference,
- scalar multifidelity delta learning.

The current project root is:

```bash
~/Desktop/Start_Up/Code/v.0.1_Project
```

The GitHub repository is expected to remain the source of truth. Keep changes small, test-backed, and patch-based.

## Critical project rules

1. Always read the latest `codebase.txt` before proposing code changes.
2. Do not bypass the CLI architecture. The GUI is only a cockpit over existing CLI commands, not a second backend.
3. Do not mix solver execution into `src/aeris/ml/`.
4. ML must consume promoted/curated data products, not raw solver junk.
5. Keep everything reproducible: manifests, configs, run folders, report JSONs, deterministic seeds.
6. Prefer boring, explicit, testable code over clever magic.
7. If a feature changes CLI behavior, add CLI tests.
8. If a feature creates data products, write reports and hashes where practical.

## Current completed capabilities

### Geometry

- `aeris geometry info`
- `aeris geometry generate`
- `aeris geometry visualize`

Active generator:

- `bwb_segmented_v1`

### Dataset and aero dataset pipeline

- `aeris dataset generate`
- `aeris dataset aero-generate`
- `aeris dataset inspect`
- `aeris dataset qc`
- `aeris dataset aero-qc`
- `aeris dataset curate-aero`
- `aeris dataset promote-aero`
- `aeris dataset require-promoted-aero`
- `aeris dataset training-data`
- `aeris dataset split-training-data`

QC presets:

- `off`
- `debug`
- `production`
- `promotion_strict`

### Aero

- `aeris aero run`
- `aeris aero inspect`
- `aeris aero sweep`
- `aeris aero sweep-inspect`
- `aeris aero sweep-case-inspect`

Current solver:

- `aerosandbox_avl`

Aero supports scalar coefficients, stability derivatives, rate derivatives, control inputs, AVL paneling, and structured output artifacts.

### Dynamics

- `aeris dynamics build`
- `aeris dynamics inspect`
- `aeris dynamics cg-sweep`
- `aeris dynamics cg-sweep-inspect`
- `aeris dynamics trim`
- `aeris dynamics trim-inspect`

This is a foundation layer, not a full nonlinear simulator.

### ML scalar surrogate pipeline

- `aeris ml feature-presets`
- `aeris ml validate-schema`
- `aeris ml train`
- `aeris ml compare`
- `aeris ml tune`
- `aeris ml compare-seeds`
- `aeris ml compare-tuning-runs`
- `aeris ml promote-model`
- `aeris ml inspect-model`
- `aeris ml require-promoted-model`
- `aeris ml check-inference-inputs`
- `aeris ml predict`

Important ML additions completed:

- feature presets,
- schema validation,
- Optuna backend,
- seed-stability comparison,
- model promotion,
- model-card/training-envelope artifacts,
- guarded prediction with `--require-promoted-model`,
- inference envelope guard with `--enforce-envelope`.

### Multifidelity scalar ML

Completed commands:

- `aeris ml build-delta-dataset`
- `aeris ml train-delta-model`
- `aeris ml predict-delta-model`
- `aeris ml evaluate-delta-model`

Completed data flow:

```text
LF CSV + HF CSV
→ paired delta_dataset.csv
→ delta model
→ corrected prediction
→ LF-vs-corrected evaluation report
```

This does not run CFD or XFOIL. It only consumes scalar LF/HF data products.

### GUI

The GUI is launched via:

```bash
aeris gui run
```

or:

```bash
aeris gui run --host localhost --port 8501
```

The updated GUI lives in:

```text
src/aeris/gui/app.py
```

It is a Streamlit operator cockpit over the CLI. It now covers:

- Overview / health checks,
- Config Lab,
- Geometry,
- Dataset / QC / Promotion,
- Aero,
- Dynamics,
- ML + Multifidelity,
- Artifacts browser,
- CLI Console.

It must remain a front-end wrapper. Do not duplicate domain logic inside the GUI.

## What was done at the end of the previous chat

1. The codebase snapshot was updated.
2. The user guide and README were updated.
3. A CLI quick-reference document was attempted and fixed with a pure Bash patch.
4. The GUI was upgraded to a much more complete Streamlit cockpit.
5. This next-chat prompt was created.

## Recommended next development slices

Do not start all of these at once. Pick one slice, patch it, test it, commit it.

### Slice 11 — Active learning foundation

Purpose:

```text
trained model + candidate pool
→ score uncertainty / novelty / expected improvement
→ recommend next geometries or flight conditions to simulate
```

Likely location:

```text
src/aeris/ml/active_learning/
```

Possible command:

```bash
aeris ml suggest-samples
```

### Slice 12 — Uncertainty / confidence layer

Purpose:

```text
model prediction
→ uncertainty estimate
→ warning / escalation / active-learning score
```

Start simple:

- ensemble variance,
- tree-model spread,
- conformal intervals.

### Slice 13 — Experiment/run registry

Purpose:

```text
all datasets, ML runs, promoted models, delta runs
→ searchable index
```

Possible commands:

```bash
aeris runs list
aeris runs inspect
aeris runs find --type ml
aeris runs find --tag promoted
```

### Slice 14 — Solver campaign execution foundation

Purpose:

```text
parallel case execution
resume
failure tracking
timeouts
Windows/Linux-safe paths
memory-conscious batches
```

This should probably come before serious XFOIL/CFD automation.

### Slice 15 — Airfoil scalar schema integration

Purpose:

```text
airfoil_id + CST features + alpha/Re/Mach + cl/cd/cm
→ ML-ready schema/presets
```

Do not implement XFOIL execution here.

### Slice 16 — XFOIL adapter

Purpose:

```text
airfoil geometry
→ XFOIL polar run
→ structured scalar aero rows
```

### Slice 17 — CFD adapter skeleton

Purpose:

```text
prepared CFD case
→ run solver
→ parse coefficients/fields
→ structured artifacts
```

Do not overbuild before the meshing workflow is stable.

### Slice 18 — Field/GNN dataset contract

Purpose:

```text
mesh nodes + edges + node features + Cp/field targets
→ split-safe graph/field dataset product
```

Do not start with the GNN model. Start with the dataset contract.

## First action in the next chat

Ask the assistant to:

1. read `codebase.txt`,
2. verify the GUI patch and docs are reflected,
3. inspect the current `git status` if provided,
4. recommend the exact next slice,
5. produce one patch only.

Suggested opening message:

```text
Read the updated codebase.txt. We stopped after completing ML multifidelity evaluation and upgrading the GUI. Verify current architecture and propose the next single slice. Do not build multiple things at once. I want production-ready, reproducible, test-backed changes.
```
