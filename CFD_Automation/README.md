# CFD_Automation

Automated CFD workflow — **geometry → mesh → solver → judgement** — for Class I and Class II
UAV wings, tailless (BWB, flying wing) and conventional (cranked, tapered), over angles of attack
and Reynolds numbers. Subsonic first. Open-source tools: pyGeo, ADflow, SU2.

Standalone; merged into AERIS when finished.

- **Stage 0** (done): starting values — `Stage_0_decisions/` (open `decisions.html` for the readable version).
- **Stage 1** (done): the wing generator and the flow dataset — `Stage_1_geometry/` (see its `README.md`).
- Next: **Stage 2**, the surface mesh — `Stage_2_surface_mesh/` (made when the work starts).

```
cfdauto/                           the code of every stage (one Python package)
  paths.py                         where each stage's configs and data live
  geometry/  flowmap/              Stage 1 (later: mesh/, solver/, ...)
pyproject.toml                     install once: pip install -e CFD_Automation
OPEN_DECISIONS.md                  still to decide, every stage (one list)
Stage_0_decisions/
  values.yaml                      Stage 0 values
  decisions.md                     value, why, source
  decisions.html                   the same, as one readable page
Stage_1_geometry/                  Stage 1: configs, data, docs, tests, scripts
  decisions/*.md                   Stage 1 notes (trailing edge, loft, root section, ranges, flow maps, ...)
references/                        sources (REFERENCES.md, references.bib)
```

## Names

- One folder per stage: `Stage_<N>_<topic>` (no spaces). The claude.ai project docs use the same
  `Stage_<N>` prefix.
- Wing sets: `training_focus`, `holdout_focus`, `reference` (realistic wings);
  `training_full`, `holdout_full`, `corner1`, `corner2` (everything the generator supports).
- Meshes: `mesh_<level>_<wing_hash8>`. "Family" is kept for the wing families (tailless, conventional).
- Code: one package, `cfdauto/`, with one subpackage per job (`geometry`, `flowmap`, then `mesh`, `solver`).
  Data, configs, docs and tests stay in their stage folder; `cfdauto/paths.py` says where.
