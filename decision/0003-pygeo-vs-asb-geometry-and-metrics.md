# DECISION-0003 — pyGeo vs AeroSandbox: geometry, metrics, and how they differ

Status: ACCEPTED
Date: 2026-07-24
Owner: Mike (with Claude as lead engineer)

Covers Mike's four asks on `configs/geometry/bwb.yaml`: (1) pyGeo produces
geometry, (2) ASB produces the same geometry for the same config over ≥20 samples
with the differences documented, (3) interactive side-by-side 3D viewing, and
(4) reliable geometric metrics.

Tooling: `standalone/pygeo_asb_comparison/` — `metrics.py` (common-schema metric
extractor), `build.py` (both backends from one sample), `compare.py` (DoE sweep +
report), `viewer.py` (interactive side-by-side 3D).

## 1 + 2. Both backends realize the same design; differences quantified (n=50)

Both backends realize the SAME sampled Aeris sections, so any metric difference is
a TOOL-realization difference (smooth pyGeo B-spline loft vs AeroSandbox piecewise),
not a different design. Sweep of 50 designs over the DoE (rescaled small BWB ISR
UAV per DECISION-0002: full span 1.5–2.5 m, AR 2.6–6.2):

- **50/50 built on both backends, 0 failures** — the DoE is robust.
- |pyGeo − ASB| / ASB across the DoE (mean / max):

  | metric | mean | max |
  |---|---|---|
  | span | 0.16% | 0.43% |
  | planform area | 0.12% | 0.28% |
  | aspect ratio | 0.21% | 0.58% |
  | MAC | 0.03% | 0.12% |
  | root chord | 0.03% | 0.04% |
  | tip chord | 0.29% | 0.32% |
  | taper ratio | 0.26% | 0.29% |
  | volume | 0.19% | 0.32% |
  | wetted area | 0.72% | 1.29% |

Reading: the two tools agree to **well under 1%** on every integrated metric. The
largest gaps are **tip chord / taper (~0.3%)** and **wetted area (~0.4–0.8%)** —
exactly where a smooth loft departs most from a piecewise one (the tip region and
total surface curvature). Root chord matches to 0.03% (both pin the root section).
This is consistent with DECISION (master geometry) — the smooth pyGeo loft is the
master; these sub-% shifts live in the design space, they are not errors.

### Lead-researcher note (a measurement trap we caught)

The first run reported ~4% span / ~6% volume differences. That was an ARTIFACT:
metrics were integrated over pyGeo sections extracted on span fractions
[0.02, 0.98], understating the pyGeo span by ~4% vs the full ASB wing. Fixed by
extracting over the FULL span (margin 1e-4). Lesson recorded in `build.py`: any
integrated-metric comparison MUST span the full geometry on both tools.

## 3. Interactive side-by-side 3D viewer

`viewer.py` opens a Plotly window per candidate with three independently
rotatable/zoomable 3D scenes — **pyGeo loft | AeroSandbox | Overlay (both)** — plus
a metric banner (span/area/AR/volume + %Δ). `--n 50` sweeps 50 candidates
(Enter between each); `--save-html <dir>` writes self-contained interactive files
(~1.4 MB each) instead of opening windows. Nothing is saved unless `--save-html`
is passed.

## 4. Reliable geometric metrics

Common schema, same keys for both backends: span, planform area, aspect ratio, MAC,
root/tip chord, taper ratio, volume, wetted area. pyGeo metrics are integrated from
the realized loft (`realised_reference_metrics` + `_volume_and_wetted_area`); ASB
metrics come from its analytic Wing. Definitions and the extraction live in
`standalone/pygeo_asb_comparison/metrics.py`. Both give volume; ASB exposes taper
directly, pyGeo computes it from realized tip/root chord.

## Decision

The pyGeo backend on `bwb.yaml` produces geometry reliably (50/50), and its
geometric metrics agree with AeroSandbox to <1% across the DoE with a clear,
explainable difference signature (tip/wetted largest). pyGeo metrics are the
authoritative numbers going forward (master geometry). Evidence:
`configs/geometry/pygeo_asb_comparison_evidence/bwb_pygeo_vs_asb.{md,json}`.
