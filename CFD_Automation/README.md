# CFD_Automation

Automated CFD workflow — **geometry → mesh → solver → judgement** — for Class I and Class II
UAV wings, tailless (BWB, flying wing) and conventional (cranked, tapered), over angles of attack
and Reynolds numbers. Subsonic first. Open-source tools: pyGeo, ADflow, SU2.

Standalone; merged into AERIS when finished.

- **Stage 0** (done): starting values — `Stage_0_decisions/` (open `decisions.html` for the readable version).
- **Stage 1** (done): the wing generator and the flow dataset — `Stage_1_geometry/` (see its `README.md`).
- Next: **Stage 2**, the surface mesh — `Stage_2_surface_mesh/` (made when the work starts).

```
OPEN_DECISIONS.md                  still to decide, every stage (one list)
Stage_0_decisions/
  values.yaml                      Stage 0 values
  decisions.md                     value, why, source
  decisions.html                   the same, as one readable page
Stage_1_geometry/                  Stage 1: config, code, tests, sets, flow dataset
  decisions/*.md                   Stage 1 notes (trailing edge, loft, root section, ranges, flow maps, ...)
references/                        sources (REFERENCES.md, references.bib)
```

## Names

- One folder per stage: `Stage_<N>_<topic>` (no spaces). The claude.ai project docs use the same
  `Stage_<N>` prefix.
- Wing sets: `training_focus`, `holdout_focus`, `reference` (realistic wings);
  `training_full`, `holdout_full`, `corner1`, `corner2` (everything the generator supports).
- Meshes: `mesh_<level>_<wing_hash8>`. "Family" is kept for the wing families (tailless, conventional).
- Open before Stage 2 code: the `cfdauto` package sits inside `Stage_1_geometry/`. Decide where the
  shared package lives before the mesh code adds to it, so there are never two packages of one name.
