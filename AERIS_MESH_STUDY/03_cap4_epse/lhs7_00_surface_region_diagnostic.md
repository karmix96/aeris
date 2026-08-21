# lhs7_00 Surface Region Diagnostic

Result: surface-only diagnostic complete

## Inputs

- Sample dir: `/home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY/artifacts/stage01/epse_calibration/surfaces/lhs7_00`
- Surface NPZ SHA-256: `65d97e8c044049bef7907eb06f82771ee2721dae2412012e1e31dbc9d4488f0c`
- Topology contract: `/home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY/00_governance/geometry_topology_contract.json`
- Region band: 0.0023519106 m

## Finding

- Worst shape metric is owned by `tip_cap`.
- Worst equiangle skewness is owned by `tip_cap`.
- In this diagnostic, both global worst cells are in the physical tip-cap block, not the root, TE crown, or b1/b2 planform breaks.

## Station Map

- b0_root: 0 m
- b1_planform_break: 0.24721067 m
- b2_planform_airfoil_break: 0.578346731 m
- b3_tip: 1.18311074 m

## Worst Shape Cells

| rank | value | block | i | j | region | y | nearest station |
|---:|---:|---|---:|---:|---|---:|---|
| 1 | 0.000371596736 | tip_center_0 | 0 | 0 | tip_cap | 1.18256372 | b3_tip |
| 2 | 0.00109747127 | tip_center_0 | 47 | 0 | tip_cap | 1.18303685 | b3_tip |
| 3 | 0.00247555737 | tip_center_0 | 1 | 0 | tip_cap | 1.18257533 | b3_tip |
| 4 | 0.0031169856 | tip_center_0 | 47 | 7 | tip_cap | 1.18180124 | b3_tip |
| 5 | 0.00341601946 | tip_center_0 | 46 | 0 | tip_cap | 1.18301622 | b3_tip |
| 6 | 0.00410920799 | tip_center_0 | 0 | 7 | tip_cap | 1.1815907 | b3_tip |
| 7 | 0.00501732453 | tip_center_0 | 0 | 3 | tip_cap | 1.18210216 | b3_tip |
| 8 | 0.00547134332 | tip_center_0 | 2 | 0 | tip_cap | 1.18258653 | b3_tip |
| 9 | 0.005816904 | tip_center_0 | 46 | 7 | tip_cap | 1.18179442 | b3_tip |
| 10 | 0.00669133098 | tip_center_0 | 45 | 0 | tip_cap | 1.18299703 | b3_tip |
| 11 | 0.00692621637 | tip_center_0 | 1 | 7 | tip_cap | 1.18159614 | b3_tip |
| 12 | 0.00949893861 | tip_center_0 | 45 | 7 | tip_cap | 1.18178779 | b3_tip |

## Worst Equiangle-Skew Cells

| rank | value | block | i | j | region | y | nearest station |
|---:|---:|---|---:|---:|---|---:|---|
| 1 | 0.997081745 | tip_center_0 | 0 | 0 | tip_cap | 1.18256372 | b3_tip |
| 2 | 0.995665358 | tip_center_0 | 0 | 3 | tip_cap | 1.18210216 | b3_tip |
| 3 | 0.991236028 | tip_center_0 | 47 | 0 | tip_cap | 1.18303685 | b3_tip |
| 4 | 0.982702891 | tip_center_0 | 1 | 0 | tip_cap | 1.18257533 | b3_tip |
| 5 | 0.980318023 | tip_center_0 | 1 | 3 | tip_cap | 1.18211622 | b3_tip |
| 6 | 0.975801788 | tip_center_0 | 46 | 0 | tip_cap | 1.18301622 | b3_tip |
| 7 | 0.975074848 | tip_center_0 | 47 | 7 | tip_cap | 1.18180124 | b3_tip |
| 8 | 0.967682057 | tip_center_0 | 0 | 7 | tip_cap | 1.1815907 | b3_tip |
| 9 | 0.966028277 | tip_center_0 | 2 | 0 | tip_cap | 1.18258653 | b3_tip |
| 10 | 0.962501307 | tip_center_0 | 2 | 3 | tip_cap | 1.18212943 | b3_tip |
| 11 | 0.958629718 | tip_center_0 | 46 | 7 | tip_cap | 1.18179442 | b3_tip |
| 12 | 0.95801811 | tip_center_0 | 45 | 0 | tip_cap | 1.18299703 | b3_tip |

## Region Summary

| region | cells | min shape | max skew |
|---|---:|---:|---:|
| le_crown | 2013 | 0.0937943647 | 0.436026471 |
| lower_mid_oml | 12096 | 0.275661857 | 0.228120097 |
| planform_break_b1 | 112 | 0.136551111 | 0.300089578 |
| planform_break_b2 | 112 | 0.254487732 | 0.22507988 |
| te_crown | 2016 | 0.0975515818 | 0.316665945 |
| tip_cap | 387 | 0.000371596736 | 0.997081745 |
| upper_mid_oml | 12096 | 0.275310046 | 0.22642006 |
