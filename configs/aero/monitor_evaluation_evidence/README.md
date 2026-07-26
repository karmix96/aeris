# Curvature Monitor Aero Study

Native AVL comparison against a finer 49-section reference with the same hard feature pins.

This study measures AVL discretisation error only. The reference is not wind-tunnel or CFD truth.

## Ranking

| rank | policy | max control err | mean control err | max all err | CL_de wins | control wins |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `proposed_sqrt_sum_w3_gap15` | 2.80% | 0.75% | 2.80% | 1 | 2 |
| 2 | `proposed_sqrt_sum_w1` | 3.45% | 0.70% | 3.90% | 0 | 2 |
| 3 | `proposed_sqrt_sum_w0` | 4.14% | 1.57% | 7.68% | 0 | 0 |
| 4 | `proposed_sqrt_sum_w3_no_thickness` | 4.35% | 0.68% | 4.35% | 1 | 1 |
| 5 | `proposed_max_channel_w3_no_thickness` | 4.35% | 0.73% | 4.35% | 2 | 1 |
| 6 | `proposed_max_channel_w3` | 4.35% | 0.74% | 4.35% | 1 | 1 |
| 7 | `proposed_sqrt_sum_w3` | 4.35% | 0.82% | 4.35% | 1 | 2 |
| 8 | `current_sum_sqrt_w3` | 4.35% | 0.85% | 4.35% | 0 | 0 |
| 9 | `uniform_pinned25` | 4.35% | 1.21% | 4.35% | 4 | 1 |

Selected by this study: **`proposed_sqrt_sum_w3_gap15`**.

## What Was Tested

- `uniform_pinned25`: 25 sections, uniform first guess, then exact hard pins.
- `current_sum_sqrt_w3`: current AERIS sum-of-square-roots monitor, control weight 3.
- `proposed_sqrt_sum_w3`: additive interpolation-error monitor, control weight 3.
- `proposed_max_channel_w3`: worst-channel monitor, control weight 3.
- `proposed_sqrt_sum_w3_no_thickness`: additive monitor with thickness dropped.
- `proposed_max_channel_w3_no_thickness`: worst-channel monitor with thickness dropped.
- `proposed_sqrt_sum_w1`: additive monitor, control weight 1.
- `proposed_sqrt_sum_w0`: additive monitor, no control-gain channel, but edges still pinned.
- `proposed_sqrt_sum_w3_gap15`: additive monitor plus a simple max-gap repair.

All non-reference policies keep the same 25-section budget. Hard pins are root, tip, the two BWB planform/airfoil break stations, and the elevon start/end edges.

## Complexity Plots

The `complexity/` directory contains one PNG per geometry. The plotted value is relative monitor density: 1 means average spanwise difficulty; higher means the geometry/control surface needs closer AVL sections there.

## Important Limits

- Channel terms are made dimensionless before addition: lengths/root chord, twist/10 deg, thickness/0.1, camber/0.1, control gain/1.
- Thickness is tested both on and off. AVL's vortex-lattice core is a mean-surface method, but the AERIS native path also writes CLAF/CDCL corrections from realised section polars, so thickness is not assumed irrelevant without testing.
- Goal-oriented adaptation would refine directly against CL, CDi, Cm, or control derivatives. This study is cheaper: it tests monitor-function placement against those aero outputs after the fact.
- All runs use one operating point: alpha 6 deg, beta 0 deg, velocity 28 m/s.
