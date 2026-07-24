# pyGeo vs AeroSandbox geometry comparison

- config: `configs/geometry/bwb.yaml`
- generated: 2026-07-24T19:46:32.043276+00:00
- samples: 50/50 built, 0 failed (seeds 5000..5049)

Both backends realize the SAME sampled design, so these are tool-realization differences (smooth pyGeo B-spline loft vs AeroSandbox piecewise), not different designs.

## |pyGeo − ASB| / ASB across the DoE

| metric | mean | p95 | max |
|---|---|---|---|
| span_m | 0.172% | 0.353% | 0.444% |
| planform_area_m2 | 0.137% | 0.248% | 0.316% |
| aspect_ratio | 0.208% | 0.462% | 0.572% |
| mean_aerodynamic_chord_m | 0.033% | 0.081% | 0.116% |
| root_chord_m | 0.032% | 0.036% | 0.036% |
| tip_chord_m | 0.297% | 0.320% | 0.323% |
| taper_ratio | 0.265% | 0.290% | 0.292% |
| volume_m3 | 0.217% | 0.305% | 0.328% |
| wetted_area_m2 | 0.403% | 0.672% | 0.755% |

## Sample absolute values (first 3 seeds)

| seed | metric | pyGeo | ASB | rel Δ |
|---|---|---|---|---|
| 5000 | span_m | 5.1616 | 5.1644 | -0.05% |
| 5000 | planform_area_m2 | 2.1579 | 2.1595 | -0.07% |
| 5000 | aspect_ratio | 12.3465 | 12.3506 | -0.03% |
| 5000 | volume_m3 | 0.0976 | 0.0974 | +0.21% |
| 5000 | taper_ratio | 0.2036 | 0.2042 | -0.27% |
| 5001 | span_m | 4.7084 | 4.7188 | -0.22% |
| 5001 | planform_area_m2 | 1.9065 | 1.9091 | -0.13% |
| 5001 | aspect_ratio | 11.6279 | 11.6637 | -0.31% |
| 5001 | volume_m3 | 0.0865 | 0.0863 | +0.26% |
| 5001 | taper_ratio | 0.2246 | 0.2252 | -0.29% |
| 5002 | span_m | 4.5178 | 4.5306 | -0.28% |
| 5002 | planform_area_m2 | 1.7075 | 1.7112 | -0.21% |
| 5002 | aspect_ratio | 11.9529 | 11.9952 | -0.35% |
| 5002 | volume_m3 | 0.0657 | 0.0656 | +0.19% |
| 5002 | taper_ratio | 0.2465 | 0.2472 | -0.28% |
