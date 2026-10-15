# Read-only campaign operations

## Status contract

The monitor discovers directories containing a result, log, memory record, or
surface field beneath each configured `--run-root`.

- `RUNNING`: evidence is partial and either the live campaign lock identifies
  the run, an explicit running marker exists, or files changed within the stale
  interval.
- `FAILED`: the solver reports failure/non-convergence, the gate rejects the
  run, the memory watcher aborted it, JSON is invalid, identities disagree, or
  the surface evidence is ambiguous/corrupt.
- `INCOMPLETE`: stale evidence is missing a result, gate, dataset row, resource
  record, log, or surface field.
- `FINAL_ACCEPTED`: the solver converged without routine failure; the gate says
  `passes: true` and `ACCEPTED`; row/result/gate identities agree; resource
  records and an ADflow history exist; and the surface payload has a stable
  SHA-256.

Exit status is neither read nor used as completion evidence.

## Monitoring

One snapshot:

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py monitor
```

Continuous observation, stopped with Ctrl-C:

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py monitor --watch --interval 60
```

Additional roots are explicit and repeatable:

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py monitor \
  --run-root /path/to/campaign-a \
  --run-root /path/to/campaign-b
```

The monitor writes `status.json`, `status.csv`, `alerts.json`, and
`restart_recommendations.json`. Recommendations are advisory; no job action is
implemented in this package.

## Releases

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py release
```

The release identifier is a hash of accepted rows, solver results, gate records,
resource/log evidence, and surface payloads. Re-running with unchanged evidence
validates and reuses the existing release. A changed or additional accepted run
creates a new release instead of mutating an old one.

Each release contains a qualification-compatible `dataset/` tree and an empty
`reports/` directory. Surface payloads are copied and deterministically gzipped;
result, gate, memory, and log evidence are retained. Every released run is
independently reclassified before publication.

## Incremental refresh

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py refresh
```

The default refresh performs monitoring, release creation, Paper 1 generation,
canonical HDF5 generation, POD, and scientific audits. Products are keyed by the
release and settings hashes. An identical second refresh validates and reuses
the product.

Predictive training is explicit:

```bash
.venv/bin/python AERIS_RESEARCH_PIPELINE/run.py refresh \
  --train --latent-dim 16 --epochs 250 --seed 42
```

This trains POD-coefficient ridge and regularized nonlinear encoder-decoder
models with train/validation/test groups separated strictly by geometry. It
also produces local leading/trailing-edge errors, pressure-integrated lift and
pitching moment errors, and learning curves.

## Scientific audits

The refresh runs four destructive-in-intent, read-only audits:

1. Coordinate axes, alpha rotation, lift index, domain side, normals, reference
   dimensions, and moment convention.
2. Pressure integration rebuilt from coordinates/connectivity, including
   reversed-normal and doubled-symmetry counterfactuals.
3. Node/cell key uniqueness, structured quad connectivity, topology-family
   separation, and cross-geometry node identity.
4. Holdout identifiers, source manifests, geometry/design aliases, and model
   split intersections. Only the governed lock report is opened; holdout design
   data are not read.

The reports live in the product's `audits/` directory. Any audit failure prevents
the incremental product from being published.
