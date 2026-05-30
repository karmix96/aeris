# AERIS CHECKPOINT 17 — ML Regression and Failure-Mode Tests

## Purpose

This checkpoint adds regression tests around the ML trust chain. The goal is not new functionality. The goal is to prove that the system fails loudly when the trust chain is broken.

## Added coverage

- Model promotion rejects missing diagnostics by default.
- Model promotion rejects force-promoted dataset sources unless explicitly allowed.
- Model promotion rejects missing dataset promotion context.
- Promoted model gate detects artifact hash mismatch after promotion.
- Model promotion requires a model artifact.
- `predict --require-promoted-model` rejects unpromoted model runs.
- `predict --require-promoted-model` rejects tampered promoted model artifacts.
- `predict` rejects input CSVs missing required feature columns.
- `aeris ml tune` accepts `--feature-preset`.
- `aeris ml compare` accepts `--feature-preset`.
- Optuna SQLite storage can resume and append trials.

## Important fix

`aeris ml tune` previously used the internal `feature_preset` variable but did not expose the `--feature-preset` CLI option in the tune command signature. This checkpoint adds that option and verifies it through a CLI regression test.

## Why this matters

A trained model is not automatically trusted. A promoted model is also not trusted forever if its artifacts change. The gate must detect tampering, missing manifests, broken schemas, and bad inputs before downstream optimization or MDAO uses the model.
