# Evidence — native pyGeo→AVL vs AeroSandbox AVL across the DoE (Task 3)

Backs `decision/0007-native-avl-is-the-production-lowfi-solver.md` and
`studies/pygeo_native_vs_asb_avl_doe.md`. Rescued out of `data/` (regenerable).

30 DoE samples (seeds 7000–7029) of `configs/geometry/bwb.yaml`, 120 AVL runs
(120/120 OK), both solvers driven from identical pyGeo sections.
α = 6°, β = 0°, δe = 4°, V = 28 m/s, 25 sections, 8×4 panels, viscous on and off.
Design space covered: AR 3.11–6.62, full span 1.52–2.49 m.

| file | what it is |
|---|---|
| `doe_report.txt` | Per-field agreement statistics (median / p95 / max) for forces, all stability- and body-axis derivatives, split by viscous state, plus the common-scale analysis, the control-bias test and the design-space-dependence check. |
| `doe_summary.json` | Same, machine-readable, including `analysis.scaled_by_clp`, `analysis.control_bias` and `analysis.design_space_dependence`. |

Per-sample raw rows (`doe_rows.json`, ~1 MB) are not rescued; regenerate with
`python standalone/lowfi_avl_study/doe_native_vs_asb.py --n-samples 30`, or
re-summarise saved rows with `--analyse-only`.

## Headline numbers

- Equivalent design-space-wide (max over 30): CL 1.04 %, L/D 1.25 %, CD 1.92 %,
  CLα 0.203 %, Cmα 0.070 %, Xnp 7.3e-5, cd_profile 0.111 %.
- No AR dependence: corr(AR, CL error) = −0.287, not significant at n = 30.
- All 135 %-scale relative errors are near-zero derivatives; largest absolute
  difference among them is 6.5e-4 = 0.18 % of |Clp|.
- **Open item:** speed derivatives Cmu / CZu differ 10.3 % / 4.2 % (all other
  well-conditioned derivatives ≤1.7 %). Mach explanations experimentally ruled out.
- Elevon authority: systematic **+5.89 % ± 0.39 %** ASB bias, same sign in all 30.
