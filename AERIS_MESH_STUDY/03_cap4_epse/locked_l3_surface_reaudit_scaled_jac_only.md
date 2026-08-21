# Locked L3 Surface Re-Audit, Corrected Gate

Result: 0 of 10 locked surfaces fail the corrected Stage 01 surface gate.

Policy: min_shape_metric > 1.0e-6, min_scaled_jacobian > 0.0, max_adjacent_normal_angle_deg <= 180.0.

This supersedes locked_l3_surface_reaudit_fixed_gate.* because the earlier 3.0e-2 shape floor and 170 deg angle limit were not derived.

| sample | old accepted | current accepted | min shape | min scaled jac | max normal angle | failures |
|---|---:|---:|---:|---:|---:|---|
| lhs7_00 | True | True | 0.00037159673582 | 0.00458396861508 | 165.284602131 | none |
| lhs7_01 | True | True | 0.000371596735819 | 0.00458396861506 | 165.535479852 | none |
| lhs7_02 | True | True | 0.000371596735821 | 0.0045839686151 | 164.738482756 | none |
| lhs7_03 | True | True | 0.000371596735817 | 0.00458396861505 | 165.263242919 | none |
| lhs7_04 | True | True | 0.00037159673582 | 0.00458396861508 | 165.532332014 | none |
| lhs7_05 | True | True | 0.000371596735821 | 0.00458396861509 | 163.380542151 | none |
| lhs7_06 | True | True | 0.00037159673582 | 0.00458396861509 | 165.522684243 | none |
| lhs7_07 | True | True | 0.000371596735818 | 0.00458396861506 | 165.580464555 | none |
| lhs7_08 | True | True | 0.00037159673582 | 0.00458396861508 | 164.035762184 | none |
| lhs7_09 | True | True | 0.000371596735819 | 0.00458396861506 | 165.45997153 | none |

## Probe Variants

| variant | accepted | min shape | min scaled jac | max normal angle | failures |
|---|---:|---:|---:|---:|---|
| A_baseline | True | 0.00037159673582 | 0.00458396861508 | 165.284602131 | none |
| B_smooth20 | False | 0.00037159673582 | -0.419135573558 | 165.284602131 | positive_scaled_jacobian |
| C_cgrid | True | 0.000371596735823 | 0.00273384851437 | 165.284602131 | none |
| D_cgrid_smooth20 | True | 0.000371596735823 | 0.00458396861512 | 165.284602131 | none |
