# AERIS Research Pipeline

This folder contains read-only post-processing and AI preparation for the frozen
Paper-1 CFD campaign. It is intentionally separate from mesh generation, ADflow
configuration, convergence gates, and campaign execution.

## Recommended command

From the repository root:

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py refresh
```

`refresh` performs one read-only campaign scan, creates or reuses an immutable
accepted-only release, rebuilds Paper 1 and the canonical AI dataset, computes
POD, and runs all scientific audits. It does not train predictive models unless
`--train` is explicitly supplied.

The command creates `AERIS_RESEARCH_PIPELINE/build/` with:

- `monitor/`: live status, alerts, and advisory-only restart recommendations;
- `releases/release-<hash>/`: deterministic copies of accepted evidence;
- `products/release-<hash>-<settings>/`: immutable paper, HDF5, POD, and audit
  products for that release;
- `paper/`: CSV and LaTeX tables, PNG and SVG figures, a source-hash ledger, and
  an explicit limitations summary when the archive-only `all` command is used;
- `ai_surface_fields.h5`: canonical wall coordinates, quad connectivity,
  normals, area, `Cp`, skin-friction magnitude, `y+`, design/flow inputs,
  geometry and topology hashes, and run/gate status;
- `ai_surface_fields.topology_audit.json`: the node-identity proof by topology
  family;
- `baselines/`: POD reconstruction model and curves, plus geometry-disjoint
  POD-ridge and regularized nonlinear encoder-decoder evaluation once at least
  three geometries exist.

Individual products can be rebuilt independently:

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py monitor
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py release
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py refresh
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py refresh --train
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py paper
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py dataset
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py baseline
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py audit
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py audit-science
```

Use `--help` on a command to change inputs, outputs, topology family, latent
dimension, or seed.

## Scientific guardrails

- A run is final only when `result.json` says the routine did not fail and did
  converge, `gate.json` passes with verdict `ACCEPTED`, and the decompressed CGNS
  payload matches its recorded SHA-256. Exit status is never used as acceptance.
- Input evidence is hashed on first read and checked again before a build is
  published. Output guards reject the qualification, strategy-study, and CFD
  artifact trees.
- Monitoring never acquires the campaign lock, launches a process, edits a run,
  or acts on a restart recommendation. A live lock or recent partial output is
  `RUNNING`; a stale partial record is `INCOMPLETE`.
- Releases contain only `FINAL_ACCEPTED` records. Surface fields are copied into
  deterministic gzip archives and reclassified independently before the
  content-addressed release is published.
- The current archive has only two grid levels. Outputs therefore say
  `TREND_NOT_GCI`; observed order, Richardson extrapolation, and formal GCI are
  left blank.
- The holdout contents remain unread. Its output row says
  `LOCKED_NOT_ACCESSED` until governed evidence exists.
- Surface snapshots are partitioned by derived topology hash. Integer node `n`
  always maps to the stored `(zone, i, j)` key; different topology families can
  never be stacked into one training matrix.
- Model evaluation splits by geometry, never by snapshot. If there are fewer
  than three geometries, predictive scores are skipped rather than leaked.
- The manifest distinguishes a timestamped HDF5 container SHA-256 from a
  deterministic logical hash over topology and snapshot identities.

## Current evidence

The frozen qualification archive covers one geometry at multiple angles and two
mesh levels. The read-only monitor also discovers the completed pilot artifacts:
the current release has 34 accepted snapshots across 10 geometries. Its coarse
surface family therefore exercises the cross-geometry topology contract and is
ready for geometry-disjoint predictor training. Rejected pilot solutions remain
visible in monitor reports but are excluded from releases and training.

The 100-geometry mesh report contains three volume block-shape families because
the outboard far-field depth varies. The physical wall shapes are nevertheless
invariant: `(93, 49)` on the OML and `(43, 5)` on the tip. The dataset manifest
records this as a preflight inference; each future CGNS file must still pass the
derived topology audit before stacking.

## Tests

```bash
.venv/bin/python -m pytest -q AERIS_RESEARCH_PIPELINE/tests
```

The LaTeX fragments use `booktabs`; wide tables also use `graphicx` for
`\resizebox`.

See [OPERATIONS.md](OPERATIONS.md) for status semantics, release rules, output
layout, and safe monitoring examples.
