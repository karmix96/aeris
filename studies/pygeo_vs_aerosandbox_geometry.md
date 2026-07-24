# Study — pyGeo vs AeroSandbox geometry realization

Date: 2026-07-24 · Config: `configs/geometry/bwb.yaml` (small BWB ISR UAV) ·
Related: DECISION-0002 (design space), DECISION-0003 (findings) ·
Code: `standalone/pygeo_asb_comparison/` · Evidence:
`configs/geometry/pygeo_asb_comparison_evidence/bwb_pygeo_vs_asb.{md,json}`

## Description

Quantify how the two geometry backends — pyGeo (smooth B-spline loft, the master
geometry) and AeroSandbox (piecewise) — differ when both realize the SAME sampled
design, across the full DoE. Deliverables: (1) confirm pyGeo produces geometry,
(2) compare the two tools over ≥20 designs and document the differences,
(3) interactive side-by-side 3D viewing, (4) reliable geometric metrics.

## Assumptions

- Both backends consume the SAME sampled Aeris sections (same design vector), so any
  metric difference is a TOOL-realization difference, not a different design.
- pyGeo metrics are integrated from the realized loft
  (`realised_reference_metrics` + `_volume_and_wetted_area`); AeroSandbox metrics
  come from its analytic `Wing`. That the two are computed by different means is an
  accepted, documented source of difference.
- The pyGeo loft is the MASTER geometry (prior decision): sub-% shifts vs the
  piecewise ASB realization live in the design space and are not errors.
- Metrics are integrated over the FULL span on both tools (pyGeo extraction margin
  1e-4). A [0.02, 0.98] margin understates the pyGeo span ~4% and biases every
  integral — this trap was found and fixed during the study.
- Geometry only: no CAD / STEP / mesh / file exports (light, in-session).
- Design space: small BWB ISR UAV — full span 1.5–2.5 m, AR 2.6–6.2, fixed station
  airfoils mh91/mh91/e374/nlf1015.

## Method

`standalone/pygeo_asb_comparison/`: `build.py` realizes both backends from one
sample; `metrics.py` extracts a common metric schema (span, planform area, aspect
ratio, MAC, root/tip chord, taper ratio, volume, wetted area); `compare.py` sweeps
N seeded designs and aggregates |pyGeo − ASB|/ASB; `viewer.py` renders an
interactive Plotly side-by-side (pyGeo | ASB | overlay). Sweep: 50 designs, seeds
5000–5049.

## Results

Sweep of 50 designs (seeds 5000–5049), geometry only, re-run 2026-07-24 and
reproducible (deterministic seeds → identical numbers on re-run).

- **Robustness:** 50/50 designs build on BOTH backends, 0 failures.
- **Agreement** (|pyGeo − ASB|/ASB across the DoE):

  | metric | mean | p95 | max |
  |---|---|---|---|
  | span | 0.161% | 0.332% | 0.429% |
  | planform area | 0.118% | 0.206% | 0.278% |
  | aspect ratio | 0.206% | 0.459% | 0.581% |
  | MAC | 0.029% | 0.079% | 0.122% |
  | root chord | 0.032% | 0.036% | 0.037% |
  | tip chord | 0.290% | 0.317% | 0.321% |
  | taper ratio | 0.258% | 0.287% | 0.289% |
  | volume | 0.185% | 0.275% | 0.315% |
  | wetted area | 0.720% | 1.126% | 1.286% |

- **Difference signature:** largest at the tip (tip chord / taper ~0.3%) and in
  wetted area (~0.7%, max 1.3%) — exactly where a smooth loft departs most from a
  piecewise one (tip region + surface curvature). Root chord matches to 0.03%
  (both pin the root). Integrated quantities (span/area/volume) agree to ~0.2%.
- **Interactive viewer:** per-candidate Plotly window with three independently
  rotatable/zoomable scenes (pyGeo | ASB | overlay) + a metric banner; 50-candidate
  batch + index page available via `--save-html`.

## Conclusions

1. The pyGeo backend produces geometry reliably on `bwb.yaml` (50/50) and its
   geometric metrics agree with AeroSandbox to **well under 1%** (worst ~1.3% on
   wetted area) with a clear, explainable difference signature.
2. The two tools realize the same design; they are not two designs. The smooth
   pyGeo loft is the authoritative master geometry, and its metrics are the numbers
   used downstream.
3. Reliable, defensible geometric metrics (span, area, AR, MAC, taper, volume,
   wetted area) are available from both tools in a common schema.
4. Methodological note: full-span extraction is mandatory for any integrated-metric
   comparison — recorded so it can't recur.
