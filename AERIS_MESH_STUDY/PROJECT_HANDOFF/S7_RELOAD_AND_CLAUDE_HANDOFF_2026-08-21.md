# S7 unstructured reload and Claude handoff — 2026-08-21

## Objective and authority

S7 is the governed unstructured sibling of S6 in the same `AERIS_MESH_STUDY`.
It targets approximately 100 active-learning high-fidelity cases using a fixed
Gmsh triangular-wall/prism-layer/tet-core mesh and SU2 8.5 RANS-SA solver. ADR-0017
and the adjacent S7 `POLICY.yaml` were created before any real BWB result.

The user authorized cost-aware GPT routing and cooperative Claude Code review.
Use lower-cost models for mechanical tests/documentation, a balanced coding model
for bounded implementation audits, and reserve frontier/max reasoning for hard
integration decisions. Claude review must use `--model opus --effort max` and remain
read-only.

## Exact current boundary

- Complete pipeline code exists from pyGeo geometry through method-neutral
  acceptance/qualification reports.
- 24 focused unit/synthetic tests pass; Ruff passes.
- Local pinned stack: Python 3.13.9, Gmsh 4.15.2, NumPy 2.5.1, SciPy 1.18.0,
  pyGeo 1.17.0, pyspline 1.5.4.
- `SU2_CFD` is absent.
- Real Gmsh evidence is limited to a synthetic closed tetrahedral wall fixture.
- Restart/recovery evidence is limited to a fake solver fixture.
- A real pyGeo BWB smoke was requested but blocked by the Codex sandbox/usage
  approval before launch. Do not misclassify it as a mesh failure and do not try an
  indirect execution workaround in the same blocked environment.
- No real S7 BWB mesh, solver, y+, force, grid, TE, hold-out, or campaign result has
  been accepted.
- `round_c_lhs10_seed42` is forbidden. There is no bypass flag.

## Critical implementation facts

- The wall triangulation is independently sampled from canonical pyGeo, mirrored,
  TE/tip closed, orientation propagated, and checked at exact nodes and all OML
  facet centroids. It is fixed across retries.
- Gmsh 2-D retry algorithms apply only to generated outer surfaces. Core retries
  use Delaunay/HXT. Post-extrusion optimization is disabled because retained
  synthetic diagnostics showed layer corruption.
- Gmsh and native SU2 meshes are independently reconstructed. Every boundary face,
  label, tet/prism count, prism column, layer height/growth, cell/face metric, and
  TE/tip prism-core interface is fail-closed.
- Flow and full-wing force references are exact canonical values. CMy is moment
  about y.
- SU2 allows free stream plus one hash-verified restart; process, density residual,
  CL/CD/CMy tail, restart, wall-point y+, and provenance must all pass.
- Qualification reads only current, adjacent digest-verified case terminals for
  indices 0/24/49/74/99 and uses actual coupled counts plus corrected unequal-grid
  Richardson/GCI.

## Claude continuation

Run the S7 peer-review wrapper only after the source/docs are stable. It preserves
the prompt, exact command, reported model usage, stdout/stderr, review text, source
and policy hashes, and terminal manifest. The prior `_01` attempt reached a Claude
session limit and is not review evidence.

Claude must not edit files, inspect/construct hold-out data, launch pyGeo/Gmsh BWB
jobs, run SU2, or start production work. It should audit implementation defects and
return Critical/High/Medium/Low findings with file/line references. Resolve serious
findings and re-review; never call a failed/limited response acceptance.

## Next numerical work

After a completed audit, the next safe action is one real `lhs100_seed42` index-0
`laptop_smoke` case when local execution is authorized. It uses a reduced farfield
and 40%-of-available-RAM refusal limit and cannot support campaign claims. Real SU2
work waits for pinned 8.5.0. Coarse/medium/fine work waits for resource-qualified
desktop/HPC nodes meeting the 48 GiB available RAM and 100 GiB disk floors.

Never use the hold-out until a superseding explicit unlock decision records that
100/100 development meshes, 10–20 unattended pilots, production y+, five grid
studies, recovery, schemas/settings, and independent review are complete.
