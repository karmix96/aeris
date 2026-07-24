# pyGeo vs AeroSandbox comparison + metrics + viewer

Tooling for DECISION-0003. Both backends realize the SAME sampled design from
`configs/geometry/bwb.yaml`, so any difference is the two tools, not the design.

## Reliable geometric metrics (task 4)

`metrics.py` — common schema for both backends: span, planform area, aspect ratio,
MAC, root/tip chord, taper ratio, volume, wetted area. pyGeo integrates the realized
loft; ASB uses its analytic Wing.

## Compare over a DoE (tasks 1 + 2)

```bash
PYTHONPATH=src .venv/bin/python -m standalone.pygeo_asb_comparison.compare \
  --config configs/geometry/bwb.yaml --n 50 --base-seed 5000 \
  --report-dir configs/geometry/pygeo_asb_comparison_evidence
```

Result: 50/50 build on both backends; metrics agree to <1% (tip/taper ~0.3%, wetted
~0.4–0.8% — where a smooth loft departs most from piecewise). Geometry only, no
CAD/mesh/exports — light. See `configs/geometry/pygeo_asb_comparison_evidence/`.

## Interactive side-by-side 3D (task 3)

```bash
# one candidate -> opens a browser window (pyGeo | ASB | Overlay), rotate/zoom
PYTHONPATH=src .venv/bin/python -m standalone.pygeo_asb_comparison.viewer \
  --config configs/geometry/bwb.yaml --seed 5000

# sweep 50 candidates (Enter between each)
PYTHONPATH=src .venv/bin/python -m standalone.pygeo_asb_comparison.viewer \
  --config configs/geometry/bwb.yaml --n 50 --base-seed 5000

# write interactive HTML files instead of opening windows (~1.4 MB each)
... --n 50 --save-html data/runs/pygeo_asb_views
```

Nothing is saved unless `--save-html` is passed.

## Important: full-span extraction

Integrated-metric comparisons MUST extract pyGeo sections over the FULL span
(`build_both` uses margin 1e-4). Extracting [0.02, 0.98] understates the pyGeo span
by ~4% and biases every integral — a trap caught during DECISION-0003.
