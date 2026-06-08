# AERIS DYN-3 — Flyability ML Dataset Bridge

## What this slice adds

AERIS can now turn a promoted aero dataset plus DYN-2/DYN-2.1 flyability labels into a promoted-like ML dataset product.

New command:

```bash
aeris dynamics build-ml-dataset \
  --dataset data/datasets/<promoted_aero_dataset> \
  --source curated
```

Output dataset root defaults to:

```text
data/datasets/<promoted_aero_dataset>__flyability_ml/
```

It writes:

```text
curated_aero_dataset.csv
flyability_ml_dataset.csv
flyability_ml_dataset_report.json
promotion_manifest.json
curation_report.json
final_run_summary.json
```

## What the dataset contains

One row per geometry/condition group, anchored at the zero symmetric-elevon aero row, joined with flyability labels.

Typical ML targets include:

```text
Cm_delta_e_per_rad
trim_delta_e_required_deg
trim_delta_e_margin_to_limit_deg
longitudinal_basic_flyable_int
red_flag_int
label_longitudinal_basic_flyable_int
```

## Boundary

This slice does not run AVL, CFD, nonlinear trim, MIL-STD classification, or new physics.
It is a data-product bridge so existing AERIS ML commands can learn from DYN-2 labels.
