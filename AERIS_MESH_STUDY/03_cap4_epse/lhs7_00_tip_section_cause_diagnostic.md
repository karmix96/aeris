# lhs7_00 Tip-Section Cause Diagnostic

Result: upstream surface-only diagnosis complete

The global worst surface cell is inherited from the tip-station boundary curves. It is at the lower leading-edge shoulder of tip_center_0, where the lower chord-side boundary from oml_1 and nose-wrap boundary from oml_0 meet at an almost degenerate angle. The blunt trailing-edge shoulder is also present in the top offenders, but it is not the global worst cell.

## Worst Cell

- Block: tip_center_0
- Index: i=0, j=0
- Category: leading_edge_shoulder_lower_side
- Shape metric: 0.00037159673582
- Scaled Jacobian: 0.00458396861508
- Equiangle skewness: 0.997081744724

## Worst Corner

- Corner: p00
- Label: lower leading-edge shoulder: lower chord edge meets nose wrap
- Corner angle: 179.737357 deg
- Edge lengths: 0.000651509169 m and 0.0160474128 m

## Top-20 Worst-Shape Category Counts

- leading_edge_shoulder_lower_side: 1
- leading_edge_shoulder_mid_thickness: 1
- leading_edge_shoulder_upper_side: 1
- mid_chord_lower_side: 4
- mid_chord_upper_side: 3
- near_le_lower_side: 2
- near_le_upper_side: 2
- near_te_lower_side: 2
- near_te_upper_side: 2
- trailing_edge_shoulder_lower_side: 1
- trailing_edge_shoulder_upper_side: 1

## Boundary Match Evidence

- p00 nearest: oml_1[0] d=0.000e+00; oml_2[8] d=0.000e+00; oml_3[48] d=2.045e-02
- p10 nearest: oml_1[1] d=0.000e+00; oml_2[8] d=6.515e-04; oml_3[48] d=2.054e-02
- p11 nearest: oml_2[7] d=2.452e-03; oml_1[0] d=1.362e-02; oml_3[48] d=2.287e-02
- p01 nearest: oml_2[7] d=0.000e+00; oml_1[0] d=1.605e-02; oml_3[48] d=2.440e-02

## Replan Guidance

Do not spend the next replan only on alternate tip caps or only on blunt trailing-edge thickening. The cap topology swap preserved the defect; the bad angles are already present in the tip-station OML boundary correspondence, especially the leading-edge shoulder and secondarily the trailing-edge shoulder.
