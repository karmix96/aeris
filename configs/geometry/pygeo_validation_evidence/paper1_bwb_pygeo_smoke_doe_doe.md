# pyGeo wide-bound smoke DoE — PASS

- config: `configs/geometry/paper1_bwb_pygeo_smoke_doe.yaml`
- generated: 2026-07-24T09:45:29.291381+00:00
- samples: 24/24 built, 24/24 gate-pass, 0 failed (seeds 3000..3023)

## Reference-metric reproduction across the DoE

- area relative error: p95 2.87e-04, max 3.99e-04
- span relative error: max 1.84e-04

## Smooth-loft characterization envelope (NOT gated)

| metric | p50 | p95 | max |
|---|---|---|---|
| chord rel err | 0.01127 | 0.01679 | 0.01876 |
| twist err (deg) | 0.4086 | 0.4911 | 0.5486 |
| x_LE err (m) | 0.005525 | 0.009445 | 0.01203 |
| z_LE err (m) | 0.008105 | 0.009781 | 0.01044 |
