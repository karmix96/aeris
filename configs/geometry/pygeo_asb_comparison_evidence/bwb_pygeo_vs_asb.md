# pyGeo vs AeroSandbox geometry comparison

- config: `configs/geometry/bwb.yaml`
- generated: 2026-07-24T20:09:28.301378+00:00
- samples: 50/50 built, 0 failed (seeds 5000..5049)

Both backends realize the SAME sampled design, so these are tool-realization differences (smooth pyGeo B-spline loft vs AeroSandbox piecewise), not different designs.

## |pyGeo − ASB| / ASB across the DoE

| metric | mean | p95 | max |
|---|---|---|---|
| span_m | 0.161% | 0.332% | 0.429% |
| planform_area_m2 | 0.118% | 0.206% | 0.278% |
| aspect_ratio | 0.206% | 0.459% | 0.581% |
| mean_aerodynamic_chord_m | 0.029% | 0.079% | 0.122% |
| root_chord_m | 0.032% | 0.036% | 0.037% |
| tip_chord_m | 0.290% | 0.317% | 0.321% |
| taper_ratio | 0.258% | 0.287% | 0.289% |
| volume_m3 | 0.185% | 0.275% | 0.315% |
| wetted_area_m2 | 0.720% | 1.126% | 1.286% |

## Sample absolute values (first 3 seeds)

| seed | metric | pyGeo | ASB | rel Δ |
|---|---|---|---|---|
| 5000 | span_m | 2.2808 | 2.2821 | -0.06% |
| 5000 | planform_area_m2 | 1.1149 | 1.1157 | -0.07% |
| 5000 | aspect_ratio | 4.6661 | 4.6681 | -0.04% |
| 5000 | volume_m3 | 0.0619 | 0.0618 | +0.19% |
| 5000 | taper_ratio | 0.1629 | 0.1633 | -0.27% |
| 5001 | span_m | 2.0540 | 2.0585 | -0.22% |
| 5001 | planform_area_m2 | 0.9612 | 0.9624 | -0.12% |
| 5001 | aspect_ratio | 4.3892 | 4.4029 | -0.31% |
| 5001 | volume_m3 | 0.0537 | 0.0536 | +0.19% |
| 5001 | taper_ratio | 0.1797 | 0.1802 | -0.28% |
| 5002 | span_m | 1.9587 | 1.9638 | -0.26% |
| 5002 | planform_area_m2 | 0.8702 | 0.8717 | -0.18% |
| 5002 | aspect_ratio | 4.4091 | 4.4243 | -0.34% |
| 5002 | volume_m3 | 0.0412 | 0.0411 | +0.18% |
| 5002 | taper_ratio | 0.1972 | 0.1978 | -0.27% |
