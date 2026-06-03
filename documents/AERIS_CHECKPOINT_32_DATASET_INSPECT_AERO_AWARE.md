# AERIS CHECKPOINT 32 — Dataset Inspect Aero-Aware Summary

## What changed

`aeris dataset inspect` now understands both geometry-only datasets and unified aero datasets.

Before this slice, `inspect_dataset(...)` assumed a geometry dataset layout:

```text
dataset_manifest.json
metadata.csv
failures.csv
geometry/
```

That was too narrow because AERIS now produces aero dataset roots with:

```text
aero_dataset_manifest.json
final_run_summary.json
aero_dataset.csv
aero_failures.csv
curated_aero_dataset.csv
rejected_aero_rows.csv
curation_report.json
promotion_manifest.json
```

## New behavior

`inspect_dataset(...)` auto-detects dataset type:

- `dataset_type = geometry` for geometry datasets
- `dataset_type = aero` for unified aero datasets

Aero inspection reports:

- aero row counts
- failure row counts
- curated/rejected row counts when present
- unique geometry counts
- manifest/final-summary/curation/promotion consistency checks
- QC and promotion context
- flight-condition coverage
- target metrics for scalar aero columns
- artifact availability

## Boundary

This slice is inspection/reporting only. It does not run solvers, QC, curation, promotion, or ML.

## Validation

Focused tests:

```bash
pytest -q tests/dataset/test_inspect.py tests/commands/test_dataset_cli.py
```

Real smoke:

```bash
aeris dataset inspect --dataset data/datasets/bwb_training_v1_canary_n5
```
