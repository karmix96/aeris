# Stage 1 — Geometry

One design vector in, one exact wing surface out, with measured values, labels and a hash.
Every later stage (mesh, solver, data) reads only this surface.

Run from this folder with the AERIS `.venv` (pyGeo 1.17.0, pySpline 1.5.4).

```
python -m cfdauto.geometry.sample                                   # write the sets
python -m cfdauto.geometry.build --type bwb --set training --index 7 # one wing
python -m cfdauto.geometry.build --all                              # every training, corner, reference wing
python scripts/plot_reference_wings.py                              # figures/reference_wings.png
python scripts/loft_kspan_study.py                                  # data/studies/loft_kspan.json
python -m pytest                                                    # all tests
python -m pytest -m "not pygeo"                                     # without pyGeo
```

```
configs/wing.yaml          the one YAML (both wing types)
airfoils/                  section files (copied from AERIS data/airfoil_database)
cfdauto/geometry/
  params.py      read and check the YAML; the design vector
  planform.py    exact panels: leading/trailing edge, chords, stations
  sections.py    twist, dihedral, airfoils, trailing-edge opening
  loft.py        the loft; upper/lower surface at (u = x/c, v)
  measure.py     measure the built wing on the loft
  labels.py      labels by rule
  gates.py       the four checks that refuse
  build.py       vector -> wing folder; --all builds the sets
  sample.py      Latin hypercube, corner sets, reference, hold-out
tests/geometry/            tests (+ hand_labelled.yaml)
data/sets/<type>/          vectors and manifests (tracked)
data/wings/                built wing folders (not tracked; rebuild with --all)
```

A wing folder: `vector.json`, `stations.json`, `sections/*.dat`, `measured.json`, `labels.json`,
`gates.json`, `span_table.csv`, `summary.json`, and `wing.igs` for single builds. A refused wing
has only `refusal.json`. The hold-out set is never built here.

Decision notes: `decisions/` (trailing_edge, loft, root_section, conventional_ranges).
Open decisions: `../Stage 0_Decisions/OPEN_DECISIONS.md`.
