# Stage 1 — Geometry

One design vector in, one exact wing surface out, with measured values, labels and a hash.
Every later stage (mesh, solver, data) reads only this surface.

Run from this folder with the AERIS `.venv` (pyGeo 1.17.0, pySpline 1.5.4). The code is the shared
`cfdauto` package in `../cfdauto/`; install it once with `pip install -e ..` (tests find it without).

```
python -m cfdauto.geometry.sample                                   # write the sets
python -m cfdauto.geometry.build --type bwb --set training_focus --index 7 # one wing
python -m cfdauto.geometry.build --all                              # every training, corner, reference wing
python -m cfdauto.geometry.published_wings --list                   # published wings it rebuilds
python -m cfdauto.geometry.published_wings --build all              # M6, RIBES, CRM, BlendedNet (pyGeo)
python scripts/plot_reference_wings.py                              # figures/reference_wings.png
python scripts/make_generator_visuals.py                            # docs/*.gif, docs/*.png (no pyGeo)
python scripts/make_generator_page.py                               # docs/GEOMETRY_GENERATOR.html
python scripts/summary_figs.py                                      # docs/summary_*.png (executive summary figures)
python scripts/loft_kspan_study.py                                  # data/studies/loft_kspan.json
python -m pytest                                                    # all tests
python -m pytest -m "not pygeo"                                     # without pyGeo
```

```
configs/wing.yaml          the one YAML (both wing types)
configs/published_wings.yaml  ONERA M6, RIBES, NASA CRM, BlendedNet: values, sources, how close
airfoils/                  project sections (M6, RIBES, copies); the AERIS database is searched too
docs/                      GEOMETRY_GENERATOR.html (open this first), GIFs, pictures
../cfdauto/geometry/      (the code; shared package, see ../README.md)
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

Decision notes: `decisions/` (trailing_edge, loft, root_section, conventional_ranges, shape_ranges, families_and_span). Types: bwb, flying_wing (family tailless); cranked, tapered (family conventional).
Open decisions: `../OPEN_DECISIONS.md`.

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

## Flow maps and the flow dataset (`../cfdauto/flowmap`)

What the flow will do on a wing, where, and which turbulence model to use, from 2-D strips
(XFOIL, free transition N_crit 9 and tripped at 1 % chord) with a uniform (elliptic) induced angle;
`--no-induced` gives the old baseline as a check. Needs `xfoil` only to build the tables.

```
python -m cfdauto.flowmap.tables --build     # section tables: 10 sections x 14 Re x 3 Mach x 49 angles (resumable)
python -m cfdauto.flowmap.dataset            # data/flowdata/dataset.csv.gz: 400 focus wings x 4 section sets x 126 conditions
python -m cfdauto.flowmap.analysis           # docs/flow_*.png, docs/flow_analysis.json, docs/flow_summary.json
python -m cfdauto.flowmap --type bwb --set reference --index 0 --mach 0.08 --alpha 4 [--sheet]
```

```
../cfdauto/flowmap/
  xfoil.py      robust XFOIL sweeps (a failing angle is skipped, never hangs); features: transition, bubbles, TE separation
  tables.py     section tables and their NaN-aware interpolation; the blend rule for strips between two sections
  engine.py     wing strips x conditions -> strip answers and wing metrics (vectorized; tool and dataset share it)
  dataset.py    the flow dataset; level flight against real wing loadings (configs/flowmap.yaml)
  analysis.py   trends, statistics, sensitivity (eta^2, gradient-boosting importance, grouped variance), checks
  core.py       one wing: flow map, phenomena, proposed model, level flight, place in the dataset, Mach x angle sheet
configs/flowmap.yaml   section sets per type, condition grid, realistic speeds, level-flight fit, thresholds
data/section_tables/   the tables (tracked); data/section_cache/, data/flowdata/, data/flowmaps/ are not
```

The tool and the dataset use the same engine, so a wing gives the same numbers in both (test
`test_tool_equals_dataset`). Assumptions and limits: `decisions/flow_maps.md`.

## Is the surface the intended wing? (verification)

Pictures are not proof. `python scripts/verify_geometry.py` measures every published wing and
writes `docs/verification.md` / `.json` (exit code 1 on a fail):

| check | what it compares | limit (% local chord) |
|---|---|---|
| sections | the loft cut at each station vs the ORIGINAL airfoil file/formula points | 0.01 |
| edges | leading and trailing edge vs the exact straight lines through the stations | 1e-6 |
| ruled | each panel vs the straight blend of its two sections | 1e-6 |
| outside CAD | ONERA M6 loft vs the CATIA model `AileM6_with_sharp_TE.igs` (needs gmsh) | 0.05 |

`verify.compare_points(loft, pts)` compares any outside surface (STEP/IGES via
`verify.cad_points`, scan, VTK points) the same way; use it for BlendedNet, CRM and RIBES once
their surface files are in the repo.

Two lofts: `build_loft(..., backend="pygeo")` (production, writes IGES) and `backend="numpy"`
(same construction with scipy; runs where pyGeo is not installed). On a machine with pyGeo,
`pytest -m pygeo tests/geometry/test_verify.py` checks that both give the same points (1e-6 chord).

Typo points: a single point off a smooth line in an airfoil file is dropped before building
(`airfoils.suspect_points`). 18 of the ~2,180 database files have one, e.g. `sc20412`
(lower surface, x/c 0.73).
