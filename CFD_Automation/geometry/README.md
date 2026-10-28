# Stage 1 — Geometry

One design vector in, one exact wing surface out, with measured values, labels and a hash.
Every later stage (mesh, solver, data) reads only this surface.

Run from this folder with the AERIS `.venv` (pyGeo 1.17.0, pySpline 1.5.4).

```
python -m cfdauto.geometry.sample                                   # write the sets
python -m cfdauto.geometry.build --type bwb --set training --index 7 # one wing
python -m cfdauto.geometry.build --all                              # every training, corner, reference wing
python -m cfdauto.geometry.published_wings --list                   # published wings it rebuilds
python -m cfdauto.geometry.published_wings --build all              # M6, RIBES, CRM, BlendedNet (pyGeo)
python scripts/plot_reference_wings.py                              # figures/reference_wings.png
python scripts/make_generator_visuals.py                            # docs/*.gif, docs/*.png (no pyGeo)
python scripts/make_generator_page.py                               # docs/GEOMETRY_GENERATOR.html
python scripts/loft_kspan_study.py                                  # data/studies/loft_kspan.json
python -m pytest                                                    # all tests
python -m pytest -m "not pygeo"                                     # without pyGeo
```

```
configs/wing.yaml          the one YAML (both wing types)
configs/published_wings.yaml  ONERA M6, RIBES, NASA CRM, BlendedNet: values, sources, how close
airfoils/                  project sections (M6, RIBES, copies); the AERIS database is searched too
docs/                      GEOMETRY_GENERATOR.html (open this first), GIFs, pictures
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
  airfoils.py    find a section: project files, AERIS database, NACA 4/5-digit formula
  published_wings.py  published wings in the generator's variables; BlendedNet converter
  preview.py     the surface without pyGeo (pictures only)
tests/geometry/            tests (+ hand_labelled.yaml)
data/sets/<type>/          vectors and manifests (tracked)
data/wings/                built wing folders (not tracked; rebuild with --all)
```

A wing folder: `vector.json`, `stations.json`, `sections/*.dat`, `measured.json`, `labels.json`,
`gates.json`, `span_table.csv`, `summary.json`, and `wing.igs` for single builds. A refused wing
has only `refusal.json`. The hold-out set is never built here.

Decision notes: `decisions/` (trailing_edge, loft, root_section, conventional_ranges).
Open decisions: `../Stage 0_Decisions/OPEN_DECISIONS.md`.

## Airfoils

A station takes any section by name. The name is looked up in `airfoils/`, then in the
AERIS database (`../../data/airfoil_database/`, about 2,180 files; set `CFDAUTO_AIRFOIL_DB`
to use another folder), then as a NACA 4/5-digit formula (`naca25118`). In `configs/wing.yaml`
a station may list several candidates; the sampler then draws them evenly. One wing may carry
its own four names in its vector (`"airfoils": [...]`).

## Published wings

`configs/published_wings.yaml` rebuilds the ONERA M6, the RIBES wind-tunnel wing, an
approximate NASA CRM wing, and BlendedNet designs (any BlendedNet or BlendedNet++ design via
`published_wings.blendednet(...)`). They keep their own blunt trailing edge
(`trailing_edge: as_is`). Read each wing's `fidelity` before using it for validation.
