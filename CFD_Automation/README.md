# CFD_Automation

Automated CFD workflow — **geometry → mesh → solver → judgement** — for Class I and Class II
UAV wings, tailless (BWB, flying wing) and conventional (cranked, tapered), over angles of attack
and Reynolds numbers. Subsonic first. Open-source tools: pyGeo, ADflow, SU2.

Standalone; merged into AERIS when finished.

- **Stage 0** (done): starting values — `Stage_0_decisions/` (open `decisions.html` for the readable version).
- **Stage 1** (done): the wing generator and the flow dataset — `Stage_1_geometry/` (see its `README.md`).
- **Stage 2** (new rules built and screened on 7 Nov 2026; every set at every level on 8 Nov: 3,128 of 3,128 builds pass, 0 nose repairs; ready to close): the surface mesh —
  `Stage_2_surface_mesh/` (see its `README.md`).
- **Stage 3** (built 9–10 Nov 2026, branch `stage3-volume-mesh`; the first solves V7 and the hold-outs V8 still to
  run): the volume mesh, one matched C-H mesh per wing, Re and level, CGNS for ADflow and `.su2` for SU2 —
  `Stage_3_volume_mesh/` (start with `decisions/STAGE3_STATUS.md`; the page `docs/VOLUME_MESH.html`). Rule set 2: M
  about 9.5 M cells; one mesh for −5° to +10°; every built set at VC: 721 of 722 meshes pass.
- **The approach in seven pictures** (7 Nov 2026, Stage 3 added 10 Nov): `overview/APPROACH_MAP.html`, built by
  `overview/make_approach_map.py`.
- **Run it locally** (Stage 1 to Stage 3, the app, V7): `RUN_LOCAL.md`.
- **The app** (10 Nov 2026): load or create a wing, build its surface and volume meshes, look at them in 3-D and plane
  by plane: `streamlit run CFD_Automation/app/app.py` (`app/README.md`).

```
cfdauto/                           the code of every stage (one Python package)
  paths.py                         where each stage's configs and data live
  geometry/  flowmap/              Stage 1
  mesh/                            Stage 2 (surface; frozen: its files make the surface code hash)
  volume/                          Stage 3 (the volume mesh, CGNS and .su2 writers, the checks)
pyproject.toml                     install once: pip install -e CFD_Automation
OPEN_DECISIONS.md                  still to decide, every stage (one list)
Stage_0_decisions/
  values.yaml                      Stage 0 values
  decisions.md                     value, why, source
  decisions.html                   the same, as one readable page
Stage_1_geometry/                  Stage 1: configs, data, docs, tests, scripts
  decisions/*.md                   Stage 1 notes (trailing edge, loft, root section, ranges, flow maps, ...)
Stage_2_surface_mesh/              Stage 2: configs/surface.yaml, decisions/, docs/, tests/, scripts/, data/studies/
Stage_3_volume_mesh/               Stage 3: configs/volume.yaml, decisions/, docs/, tests/, scripts/, solve/, data/studies/
app/                               the app: app.py (Streamlit), core.py, figures.py, tests/
overview/                          the approach map (one page, drawn from the generator)
references/                        sources (REFERENCES.md, references.bib)
```

## Names

- One folder per stage: `Stage_<N>_<topic>` (no spaces). The claude.ai project docs use the same
  `Stage_<N>` prefix.
- Wing sets: `training_focus`, `holdout_focus`, `reference` (realistic wings);
  `training_full`, `holdout_full`, `corner1`, `corner2` (everything the generator supports).
- Meshes: `mesh_<level>_<wing_hash8>_re<Re>` (the Re on the mean chord: the surface depends on it). "Family" is kept
  for the wing families (tailless, conventional).
- Code: one package, `cfdauto/`, with one subpackage per job (`geometry`, `flowmap`, then `mesh`, `solver`).
  Data, configs, docs and tests stay in their stage folder; `cfdauto/paths.py` says where.
