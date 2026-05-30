# AERIS CHECKPOINT 16 — ML Model Promotion and Trust Gate

AERIS now has a formal model-promotion layer. A trained model is no longer assumed to be usable just because training completed.

New module:

```text
src/aeris/ml/model_promotion.py
```

New commands:

```bash
aeris ml promote-model
aeris ml inspect-model
aeris ml require-promoted-model
```

`aeris ml predict` now supports:

```bash
--require-promoted-model
```

Model promotion writes:

```text
model_promotion_manifest.json
model_card.json
training_envelope.json
```

The gate checks saved run artifacts, dataset-promotion provenance, metrics, diagnostics, and artifact hashes.

Typical usage:

```bash
aeris ml promote-model \
  --model-run-dir data/processed/ml_runs/et_preset_test \
  --max-test-rmse-mean 0.001 \
  --min-test-r2-mean 0.99
```

Next step: inference envelope / OOD checks using `training_envelope.json`.
