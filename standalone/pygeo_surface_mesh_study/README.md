# pyGeo-native BWB surface-mesh study

This package prepares a reproducible geometry-sensitivity and adaptive
surface-mesh campaign. It uses the realised pyGeo loft directly through
`PyGeoSurfaceGeometry`; no AeroSandbox wing or airfoil object participates in
the mesh construction.

## What was verified before designing the study

The repository's pyGeo geometry path is valid and executable:

1. `BWBDesignSample` drives the existing deterministic segmented-BWB planform
   and section builders.
2. Those authored sections are converted to pyGeo station frames and lofted by
   `build_pygeo`.
3. `extract_sections` slices the realised B-spline upper/lower surfaces at
   physical span fractions, planarises each slice, and carries both its direct
   coordinates and local 3-D frame.
4. `PyGeoSectionOmlSource` maps those realised coordinates into the structured
   `cap4` surface topology without constructing AeroSandbox geometry.

Focused geometry tests, neutral-frame validation, a wide-bound neutral DoE,
and a full STEP/volume realization all pass in the installed environment. The
important mesh-study defect was not pyGeo geometry generation: the
production-feature extraction can place two sections almost at the same span
fraction (`~0.49985` and `0.5`). That produces a technically connected but very
poor surface mesh. This study therefore extracts exactly 14 uniformly spaced
*realised-surface* sections for every geometry and verifies their physical
spacing before meshing.

The current pyGeo-native mesher supports `cap4` only. This is explicit in the
study config and is not silently changed during retries.

## Experimental design

The canonical baseline is intentionally neutral:

- fixed MH-91, MH-91, E374, and NLF1015 airfoils at b0–b3;
- zero sweep, twist, and dihedral;
- 1.6 m semispan split into three equal panels;
- root chord 1.60 m and chord ratios 0.75, 0.50, 0.25;
- no control surfaces and no physical-CAD split.

The campaign has four stages:

1. **Baseline** — establishes all reference metrics.
2. **OFAT** — four normalized deltas per variable (`-1`, `-0.5`, `+0.5`,
   `+1`) for all 17 active BWB variables. A duplicate baseline-side point is
   omitted for sweep because the baseline is also its lower bound.
3. **Ranked pairwise corners** — the six variables with the largest
   limit-normalized OFAT response are combined at low/high corners, capped at
   60 cases.
4. **Multi-variable LHS** — 64 deterministic Latin-hypercube cases quantify
   multiway association and expose combinations missed by OFAT.

The initial plan contains 1 baseline, 62 unique OFAT cases, and 64 LHS cases.
The pairwise plan is intentionally generated only after OFAT ranking. The full
campaign is at most 187 geometries with the shipped settings.

### Avoiding mesh-resolution confounding

Every geometry is always evaluated on **L3**, the common reference mesh.
Geometry sensitivity, response fits, interaction residuals, and rankings use
only L3 metrics.

Adaptive acceptance is a separate question. The runner also searches the
five-level family from coarse to fine and selects the coarsest observed level
inside every configured limit:

| level | chord points | span panels/interval | wrap points | tip radial |
|---|---:|---:|---:|---:|
| L1 | 25 | 8 | 11 | 5 |
| L2 | 33 | 12 | 15 | 7 |
| L3 | 49 | 16 | 21 | 9 |
| L4 | 65 | 24 | 29 | 13 |
| L5 | 97 | 32 | 43 | 17 |

Resolution roughly doubles the surface-cell count at each step
(`r_linear ≈ 1.42`). Seam location, topology, 0.5%-chord blunt trailing edge,
tip smoothing, and allocation policy remain fixed so refinement does not
change the geometry or blocking.

If L5 still misses a limit, the case is recorded as `limits_unresolved`.
Limits are never relaxed automatically. Pass/fail reversals at finer levels
are reported as non-monotone because shape, skewness, and aspect ratio do not
necessarily improve with pure refinement.

## Insert the acceptance limits

Edit:

```text
configs/cfd/pygeo_surface_mesh_study.yaml
```

Under `acceptance.metrics`, replace each `limit: null` with the desired value.
For a metric that should be reported but not gate acceptance, set
`enabled: false`. The immutable construction gates still require:

- matched block connectivity;
- a surface closed everywhere except the symmetry root;
- an exactly planar root;
- positive cell area;
- non-folded quads.

A full run refuses to start while any enabled limit remains null.
`--allow-unset-limits` exists for development only and should not be used for
the scientific campaign.

## Commands

Run from the repository root.

Validate schema and geometry wiring (null limits are reported but allowed):

```bash
PYTHONPATH=src .venv/bin/python \
  -m standalone.pygeo_surface_mesh_study.run_study \
  validate --config configs/cfd/pygeo_surface_mesh_study.yaml
```

Require all metric limits to be filled:

```bash
PYTHONPATH=src .venv/bin/python \
  -m standalone.pygeo_surface_mesh_study.run_study \
  validate --require-limits \
  --config configs/cfd/pygeo_surface_mesh_study.yaml
```

Write the deterministic initial plan without building geometry:

```bash
PYTHONPATH=src .venv/bin/python \
  -m standalone.pygeo_surface_mesh_study.run_study \
  plan --config configs/cfd/pygeo_surface_mesh_study.yaml \
  --output /tmp/pygeo_surface_case_plan.json
```

Exercise one baseline pyGeo geometry and one L1 mesh despite null limits:

```bash
PYTHONPATH=src .venv/bin/python \
  -m standalone.pygeo_surface_mesh_study.run_study \
  smoke --config configs/cfd/pygeo_surface_mesh_study.yaml \
  --workdir /tmp/pygeo_surface_smoke
```

Run the complete staged campaign after inserting limits:

```bash
PYTHONPATH=src .venv/bin/python \
  -m standalone.pygeo_surface_mesh_study.run_study \
  run --config configs/cfd/pygeo_surface_mesh_study.yaml \
  --workdir artifacts/pygeo_surface_mesh_study/run_001 \
  --stage all
```

Stages may be run separately as `baseline`, `ofat`, `pairwise`, or `lhs`.
Completed cases are resumed only when the study config, geometry config, mesh
implementation, pyGeo adapter, and analysis-source hashes match. A changed
source state must use a new work directory, preventing accidental mixing.

Rebuild analysis without remeshing:

```bash
PYTHONPATH=src .venv/bin/python \
  -m standalone.pygeo_surface_mesh_study.run_study \
  analyze --config configs/cfd/pygeo_surface_mesh_study.yaml \
  --workdir artifacts/pygeo_surface_mesh_study/run_001
```

## Outputs

The work directory contains:

```text
study_manifest.json
case_plan.json
pairwise_plan.json                  # after OFAT ranking
study_report.json
study_report.csv
mesh_analysis.json
sensitivity_ranking.csv
candidate_mesh_laws.md
cases/<case_id>/
  case.json
  geometry.json
  result.json
  attempts/<level>/
    surface_report.json
    surface.fmt
    surface.vtk
    surface_blocks.npz
    attempt_result.json
```

For the selected mesh, 500 deterministic OML nodes are projected to the exact
upper/lower pySpline patches. RMS, p95, and maximum distances are reported in
metres, millimetres, and reference-chord fractions. This diagnostic includes
the deliberate 0.5%-chord CFD trailing-edge opening, so it is not an
acceptance gate by default.

## Extracted laws

The analyzer produces:

- a limit-normalized variable sensitivity ranking;
- per-variable linear/quadratic response fits in normalized delta;
- tested passing intervals and maximum required mesh level;
- pairwise non-additivity residuals;
- LHS Spearman rank correlations;
- conditional pass rates and metric changes across observed mesh transitions;
- explicit non-monotonicity and unresolved-case lists.

These are labeled **candidate empirical laws**. They are valid only over the
configured variable domain, and OFAT fits apply only with every other variable
at baseline. The pairwise and LHS stages test how those single-variable laws
break under combinations.

One geometry caveat is preserved in every report: because
`enforce_flat_root_panel` is disabled to study `dihedral_b1_deg`, non-zero
inboard-dihedral cases are valid half-wing surface-mesh diagnostics but require
a separate mirrored-root/physical-CAD review before production use.
