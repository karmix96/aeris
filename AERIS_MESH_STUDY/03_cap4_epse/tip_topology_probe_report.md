# lhs7_00 Tip-Topology Probe

Surface-only. No pyHyp march, no solver. Everything except the tip
treatment is held at the Stage 01 L3 recipe.

| variant | topology | min shape | max skew | min scaled jac | worst tip block | accepted |
| --- | --- | ---: | ---: | ---: | --- | --- |
| A_baseline | wing_cap4_v1 | 3.7160e-04 | 0.9971 | 4.5840e-03 | tip_center_0 | True |
| B_smooth20 | wing_cap4_v1 | 3.7160e-04 | 0.9979 | -4.1914e-01 | tip_center_0 | True |
| C_cgrid | wing_cap4_cgrid_face_v1 | 3.7160e-04 | 0.9983 | 2.7338e-03 | tip_center_0 | True |
| D_cgrid_smooth20 | wing_cap4_cgrid_face_v1 | 3.7160e-04 | 0.9971 | 4.5840e-03 | tip_center_0 | True |

## Validation of the probe

Variant A reproduces the Stage 01 `lhs7_00` values exactly
(`min_shape_metric` 0.00037159673582016757, skew 0.997081744723563,
`min_scaled_jacobian` 0.004583968615083045), so the probe reproduces the control
before varying anything. The topology override took effect: A/B report
`tip_topology: airfoil_face` with one `tip_center_0` block, C/D report
`cgrid_face` with `tip_center_0` and `tip_center_1`.

## Findings

1. **The C-grid tip face is not a fix.** `min_shape_metric` agrees with the
   airfoil-face cap to 11 significant figures (…82016757 vs …82306787), skew is
   slightly worse (0.9983 vs 0.9971) and surface scaled Jacobian is worse
   (2.73e-03 vs 4.58e-03). Swapping the tip block topology does not move the
   defect, so the degenerate corner is inherited from upstream of the cap
   construction, not created by it.

2. **`tip_smooth_iters: 20` is actively harmful.** On the airfoil-face cap it
   drives surface `min_scaled_jacobian` to **-0.419** — a folded surface cell.
   The `mesh_family_v2_*` recipes in `run_epse_calibration.py` set this value, so
   reaching for that recipe would make the mesh worse, not better.

3. **The surface acceptance check can accept a folded mesh.** Variant B has a
   negative scaled Jacobian and still returned `accepted_pre_pyhyp: True`. The
   acceptance path tests `minimum_shape_metric` (1e-6) and
   `maximum_adjacent_normal_angle_deg` (180 deg) only; it never tests the sign of
   the scaled Jacobian. Stage 00 gate `surface_validity` requires "no folded or
   negative surface cells", so the gate is currently unenforced in code.

## Consequence for the Stage 01 replan

Do not spend the replan on alternative tip-cap block topologies; that hypothesis
is tested and rejected. The two actionable items are enforcing the surface
validity gate in code, and locating the upstream source of the degenerate corner
cell, which survives a full tip-topology swap.
