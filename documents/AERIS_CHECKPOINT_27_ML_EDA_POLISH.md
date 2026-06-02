# AERIS Checkpoint 27 — ML EDA Constant-Column Polish

## What changed

This slice hardens the `aeris ml eda` reporting layer around constant columns and undefined correlations.

## Added

- Warning-safe Pearson/Spearman correlation helpers.
- Explicit `correlation.skipped_columns` diagnostics in `eda_report.json`.
- Nonlinearity scan entries now mark undefined constant-column pairs as `status: skipped` instead of triggering NumPy RuntimeWarnings.
- Correlation plots now use only non-constant numeric columns and record skipped-column diagnostics.
- Regression tests verifying EDA no longer emits NumPy `RuntimeWarning` for constant columns.

## Why this matters

Small smoke datasets often contain fixed values such as velocity, altitude, or control deflection. Those columns are valid campaign metadata, but their correlations are mathematically undefined. AERIS should report this explicitly instead of letting NumPy produce warnings during every test run.

## Boundary

This slice does not change training, comparison, tuning, promotion, prediction, active learning, solvers, or dataset generation. It is purely EDA/reporting polish.
