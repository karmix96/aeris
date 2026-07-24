# pyGeo config-frame validation — GATE PASS

- config: `configs/geometry/paper1_bwb_pygeo.yaml`
- generated: 2026-07-24T08:33:58.714608+00:00
- k_span=3  frame_mode=asb_frame  stations=17
- gate checks: 4/4 pass (frame reconstruction, reference area/span/AR, control invariance)
- loft-smoothing envelope (characterization, NOT gated): chord ≤1.18%, twist ≤0.40°, LE ≤8.4 mm

## Stations — config SET vs intended vs realized

| station | af | y (m) | chord SET | chord intended | chord realized | twist SET | twist intended | twist realized |
|---|---|---|---|---|---|---|---|---|
| b0(root) | naca23012 | 0.0000 | 1.6005 | 1.6009 | 1.6018 | 0.001 | 0.000 | 0.299 |
| b1 | naca23012 | 0.3393 | 0.8811 | 0.9524 | 0.9606 | -2.000 | -1.884 | -1.537 |
| b2 | naca4412 | 0.7635 | 0.6090 | 0.6449 | 0.6449 | -3.000 | -2.917 | -2.558 |
| b3(tip) | naca0012 | 1.6001 | 0.1929 | 0.1931 | 0.1929 | -4.000 | -4.000 | -4.315 |

## Panels — sweep / dihedral (config SET vs intended vs realized)

| panel | sweep SET | sweep intended | sweep realized | dihedral intended | dihedral realized |
|---|---|---|---|---|---|
| b0(root)->b1 | 40.001 | 39.021 | 38.856 | 0.000 | -0.532 |
| b1->b2 | 25.001 | 26.321 | 26.440 | 1.100 | 0.940 |
| b2->b3(tip) | 10.000 | 11.057 | 11.163 | 3.209 | 2.863 |

## GATE checks (physically required — set overall PASS/FAIL)

| check | measured | reference | delta | tol | pass |
|---|---|---|---|---|---|
| frame_reconstruction_error | 6.59195e-16 | 0 | 6.59e-16 | 1e-06 | OK |
| ref.area | 2.23723 | 2.23718 | 5.69e-05 | 0.0112 | OK |
| ref.span | 3.20033 | 3.2002 | 0.000135 | 0.0032 | OK |
| ref.aspect_ratio | 4.57803 | 4.57776 | 0.00027 | 0.0229 | OK |

## Characterization (smooth-loft vs authored stations — NOT gated)

The kSpan B-spline loft approximates the authored stations; these deviations quantify that smoothing and belong in the design-variable space.

| metric | measured | (envelope tol) | within |
|---|---|---|---|
| loft.max_chord_rel_err | 0.0117967 | 0.005 | no |
| loft.max_twist_err | 0.397771 | 0.05 | no |
| loft.max_x_le_err | 0.00670862 | 0.002 | no |
| loft.max_z_le_err | 0.00836665 | 0.002 | no |
| b0(root).chord_SET | 1.60177 | 0.008 | yes |
| b0(root).twist_SET | 0.299255 | 0.05 | no |
| b1.chord_SET | 0.96061 | 0.00441 | no |
| b1.twist_SET | -1.53671 | 0.05 | no |
| b2.chord_SET | 0.644853 | 0.00304 | no |
| b2.twist_SET | -2.55845 | 0.05 | no |
| b3(tip).chord_SET | 0.192919 | 0.000964 | yes |
| b3(tip).twist_SET | -4.31483 | 0.05 | no |
| panel0.sweep_vs_intended | 38.8563 | 0.15 | no |
| panel0.dihedral_vs_intended | -0.531695 | 0.15 | no |
| panel1.sweep_vs_intended | 26.4396 | 0.15 | yes |
| panel1.dihedral_vs_intended | 0.939849 | 0.15 | no |
| panel2.sweep_vs_intended | 11.1633 | 0.15 | yes |
| panel2.dihedral_vs_intended | 2.86305 | 0.15 | no |

## Control-surface invariance of neutral loft

- max neutral-station deviation (controls on vs off): 0 m (tol 0.002) — **PASS**
