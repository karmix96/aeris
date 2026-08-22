# Stage 01 Pre-Replan Commands

Generated: 2026-08-11T21:16:07+03:00

These commands are prepared only. Codex did not launch them.

Current status: HOLD after the Claude/Codex threshold audit and corrected surface re-audit. Do not launch either command unless a Stage 01 replan explicitly reauthorizes it. The referenced Stage 01 recipes now use the restored study values min_shape_metric > 1.0e-6 and max_adjacent_normal_angle_deg <= 180.0, plus the hard min_scaled_jacobian > 0.0 validity floor.

## L1 Prevalence Pass

Purpose: run all 10 locked seed-7 geometries at L1 with one epsE value to test whether the lhs7_00 quality-only failure is local or prevalent.

```bash
.venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/run_epse_calibration.py --mode full --limit 10 --eps 1.5 --surface-recipe pygeo_study_l1_reference --reuse-existing --workdir AERIS_MESH_STUDY/artifacts/stage01/epse_calibration_l1_prevalence_eps15 --report-json AERIS_MESH_STUDY/03_cap4_epse/epse_calibration_l1_prevalence_eps15_report.json
```

Runtime estimate: lhs7_00 L1 epsE=1.5 took 76.28 s. Ten serial geometries estimate to about 12.7 min of pyHyp time; budget 15-20 min including surface generation and filesystem overhead.

Reporting note: run_epse_calibration.py now writes layer_count and low_quality_layer_fraction for each real remarch row. The previous lhs7_00 L1 trial was 60/128 low-quality layers = 0.46875.

Operational note: the command may exit nonzero if the prevalence pass fails the Stage 01 clean rule; the JSON/Markdown report should still be written before exit.

## L3 Overnight Campaign

Purpose: run the full 30-row L3 campaign separately for overnight evidence, not for Stage 02 authorization.

```bash
.venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/run_epse_calibration.py --mode full --eps 1.5 2.0 3.0 --surface-recipe pygeo_study_l3_reference --reuse-existing --workdir AERIS_MESH_STUDY/artifacts/stage01/epse_calibration_l3_full30_overnight --report-json AERIS_MESH_STUDY/03_cap4_epse/epse_calibration_l3_full30_overnight_report.json
```

Runtime estimate: lhs7_00 L3 real marches took 648.85 s at epsE=1.5, 896.69 s at epsE=2.0, and 925.23 s at epsE=3.0, or 41.18 min for one geometry across all three epsE values. Ten geometries estimate to about 6.9 h serial; budget 7-9 h with overhead and sample variability.

Stage rule: Stage 02 remains unauthorized until a revised Stage 01 gate passes and the user explicitly approves it.

