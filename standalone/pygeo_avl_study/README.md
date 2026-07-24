# Standalone pyGeo -> NeuralFoil -> AVL study

This directory is an isolated feasibility implementation. It reads Aeris
configuration and reusable data structures so that the comparison is
representative, but it does not register a generator or modify `src/aeris`.
Every run creates a new timestamped directory under
`artifacts/pygeo_avl_study`.

## Implemented chain

```text
Aeris design sample
  -> pyGeo B-spline lifting-surface loft
  -> physical-semispan surface extraction
  -> local planarization and CST reconstruction
  -> NeuralFoil section polars at local Reynolds number
  -> AVL section CDCL records
  -> actual AVL execution
  -> independent strip-area profile-drag integration
```

The extractor samples the realised pyGeo surface, not just its authored
stations. This distinction matters for `kSpan > 2`, where interior spanwise
curves are B-spline control data rather than guaranteed interpolation sections.

## Run

From the repository root:

```bash
# Short validation
.venv/bin/python standalone/pygeo_avl_study/run_study.py \
  --quick --doe-samples 6 --label quick_validation

# Full baseline, convergence sweep, and 24-case wide-bound DOE
.venv/bin/python standalone/pygeo_avl_study/run_study.py \
  --doe-samples 24 --label full_study
```

The default output root is project-local:

```text
artifacts/pygeo_avl_study/<label>_<timestamp>/
```

No existing output is overwritten. AVL case directories are absolute and must
be empty when created, which prevents stale files and AeroSandbox `AFILE`
double-resolution.

Useful options:

- `--config PATH`: baseline geometry configuration.
- `--doe-config PATH`: wide-bound DOE configuration.
- `--velocity-mps VALUE` and `--altitude-m VALUE`: flow condition.
- `--model-size VALUE`: NeuralFoil model size.
- `--skip-doe`: run all deterministic studies without the DOE.
- `--output-root PATH`: choose another output root explicitly.

## Outputs

Each run contains:

- `REPORT.md`: numerical decision, caveats, and links to all evidence.
- `geometry/`: IGES/Tecplot exports, sampled surfaces, metrics, and overlays.
- `cst_neuralfoil/`: CST-order errors, direct-versus-CST polars,
  confidence values, and CDCL-fit audit.
- `avl_comparison/`: AeroSandbox production/intended and pyGeo `kSpan=2/3/4`
  cases, raw AVL files, strip loads, and corrected drag.
- `section_convergence/`: constant-panel-count 5/9/17/33-section sweep.
- `implementation_audit/`: Mach, Reynolds batching, airfoil assignment,
  CDCL semantics, and relative-`AFILE` checks.
- `doe_stress/`: geometry and aerodynamic robustness across wide design bounds.
- `summary.json` and `environment.json`: machine-readable provenance.

## Modules

- `geometry_bridge.py`: station frames, pyGeo construction, span inversion,
  surface slicing, planarization, CST fitting, CAD export, and AeroSandbox
  serialization geometry.
- `polar_bridge.py`: direct/extended NeuralFoil calls, confidence retention,
  CDCL fits, and Reynolds-aware live strip queries.
- `avl_bridge.py`: safe case directories, CDCL injection, actual AVL execution,
  strip parsing, and independent viscous-drag integration.
- `case_factory.py`: production-as-is and configured-intent Paper 1 cases.
- `plotting.py`: project-local visual evidence.
- `run_study.py`: reproducible orchestration and report generation.

## Tests

```bash
.venv/bin/pytest -q standalone/pygeo_avl_study/test_bridge.py
```

The focused tests cover exact AeroSandbox-compatible station frames, endpoint
geometry, physical-span inversion, section mapping, and AVL CDCL interpolation.
The full runner is the integration test because it invokes pyGeo, NeuralFoil,
AeroSandbox serialization, and the installed AVL executable.

## Recommended research boundary

Use pyGeo as the master outer-mould-line/CAD model and keep AeroSandbox as a
complementary AVL serializer and maintained NeuralFoil interface. Use
`kSpan=3`, the exact AeroSandbox-compatible station frame, CST order 8, and at
least 17 extracted AVL sections as the initial baseline; retain a 33-section
reference in convergence evidence.

Treat `CDind_AVL + CDprofile_NeuralFoil` as a geometry-consistent engineering
correction, not as nonlinear viscous AVL. CDCL changes profile drag only; it
does not add separation, stall, or viscous feedback to AVL circulation.

The standalone audit deliberately does not repair the existing Aeris path. It
records the integration issues that should be fixed in a later, explicitly
authorized Aeris change:

1. configured station airfoils are not currently applied by the production
   section builder;
2. the production AVL `v` keystroke turns profile forces off;
3. relative working directories can break `AFILE` resolution;
4. the raw NeuralFoil core ignores Mach;
5. the production batch query collapses strip Reynolds numbers to one median;
6. confidence is recorded but not used as a quality gate.
