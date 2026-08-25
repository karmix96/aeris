# S7 solver tuning matrix

2026-08-25 | SU2 8.5.0 Harrier, RANS-SA | 42,745 cells, `half_wing_symmetry_y0` | 6000 iterations | tier `laptop_diagnostic`, campaign claims forbidden

Ten solver configurations on one mesh, every variant carrying multigrid and adding
one thing on top.  `CONV_RESIDUAL_MINVAL` was set to -12.0 for the matrix,
below the acceptance bar, so each variant could reach whatever it was capable of
rather than halting on the gate itself.

Gates: drop >= 6.0 orders AND final <= -8.0, plus the force tail.

| variant | added to multigrid | wall s | drop | final rms | min at iter | monotonic | gates |
|---|---|---|---|---|---|---|---|
| `I_combined` | NK + ILU/25 + CFL 25 | 4802 | 6.906 | -9.508 | 5999 | yes | **pass** |
| `J_nk_no_mg` | NK + ILU/25 + CFL 25, no multigrid | 5067 | 6.906 | -9.508 | 5999 | yes | **pass** |
| `G_nk_cfl` | NK + CFL 25 | 4158 | 6.363 | -8.966 | 5999 | yes | **pass** |
| `F_nk_linear` | NK + ILU/25 | 4569 | 6.265 | -8.868 | 5999 | yes | **pass** |
| `B_newton_krylov` | NK alone | 4671 | 5.954 | -8.556 | 5999 | yes | fail by 0.046 |
| `D_high_cfl` | CFL 25 | 3142 | 1.798 | -4.401 | 927 | no | fail |
| `C_strong_linear` | ILU/25 | 3708 | 1.465 | -4.068 | 953 | no | fail |
| `A_baseline` | nothing | 2913 | 1.082 | -3.685 | 3604 | no | fail |
| `E_quasi_newton` | QUASI_NEWTON_NUM_SAMPLES | 2976 | 1.082 | -3.685 | 3604 | no | fail |
| `H_linear_cfl` | ILU/25 + CFL 25 | 4440 | 1.036 | -3.639 | 5961 | no | fail |

All ten ran the full 6 000 iterations; none stopped early.

## Forces

| variant | CL | CD | CMy | accepted |
|---|---|---|---|---|
| `I_combined` | 0.018883 | 0.087040 | -0.006617 | yes |
| `J_nk_no_mg` | 0.018883 | 0.087040 | -0.006617 | yes |
| `G_nk_cfl` | 0.018883 | 0.087040 | -0.006617 | yes |
| `F_nk_linear` | 0.018883 | 0.087040 | -0.006617 | yes |
| `B_newton_krylov` | 0.018882 | 0.087041 | -0.006617 | no |
| `D_high_cfl` | 0.019238 | 0.086840 | -0.006937 | no |
| `C_strong_linear` | 0.018811 | 0.087093 | -0.006777 | no |
| `A_baseline` | 0.019888 | 0.087070 | -0.007543 | no |
| `E_quasi_newton` | 0.019888 | 0.087070 | -0.007543 | no |
| `H_linear_cfl` | 0.019429 | 0.087381 | -0.006912 | no |

The four accepted variants agree on all three coefficients to within 5e-7 no
matter how the solver reached them.  The five rejected ones spread 5.54 % in CL,
0.62 % in CD and 10.74 % in CMy.  The gate separates exactly what it was written
to separate.

## Conclusions

1. **Newton-Krylov is the discriminating ingredient.**  Every variant carrying it
   is monotonic and still descending at the iteration cap; every variant without
   it limit-cycles, and none exceeds 3.02 orders of best drop.
2. **Necessary but not sufficient**: alone it reaches 5.954 orders and misses the
   gate by 0.046.  It needs the stronger linear solve or the higher CFL to clear
   six orders within 6 000 iterations; both together are fastest.
3. **The accelerators are coupled, not additive.**  CFL 25 is the worst variant
   without Newton-Krylov (`D_high_cfl`, 2.041 best drop) and the second best with
   it (`G_nk_cfl`, 6.363).
4. `QUASI_NEWTON_NUM_SAMPLES` is a **no-op**: `A_baseline` and `E_quasi_newton`
   differ by that one line and their 6 000-row histories are byte-identical.
5. Multigrid is **bypassed** under `NEWTON_KRYLOV`: `I_combined` and `J_nk_no_mg`
   differ by seven `MG*` options and their histories are byte-identical.
6. SU2 8.5.0 **never logs** Newton-Krylov activation - "Newton" and "Krylov"
   appear zero times in a run with `NEWTON_KRYLOV= YES`.  Only the residual
   history shows whether it took effect.

## Scope

This selects a solver configuration at 42 745 cells on a laptop.  It does **not**
establish convergence at production resolution: the coarse level is 1.55 M cells
and the matrix must be repeated there before any convergence claim.
`round_c_lhs10_seed42` was not touched.

The matrix also exposed a defect in the residual gate itself - the solver was
being stopped at the acceptance bar, capping the achievable drop at 5.42 orders
against a gate asking 6.0.  See the 2026-08-25 residual-gate amendment in
ADR-0017 and defect 11 in `STUDY.md`.
