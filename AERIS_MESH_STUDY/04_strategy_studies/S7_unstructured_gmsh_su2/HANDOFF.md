# S7 reload and handoff

Snapshot: 2026-08-22.  Status: `preregistered_development_no_results`; meshing
works across the development set, no CFD result is accepted.

## Reload order

1. repository `memories/memories.md`
2. everything under `AERIS_MESH_STUDY/PROJECT_HANDOFF/`
3. S6 strategy, policy, research and tests, plus ADR-0016
4. `AERIS_MESH_STUDY/04_strategy_studies/COMMON_BRIEF.md`
5. ADR-0017, then this directory's `POLICY.yaml`, `README.md`, `STUDY.md`,
   `RESEARCH.md`, `ROADMAP.md`, `RUNBOOK.md`
6. all S7 Python, shell and test files

The locked set is `round_c_lhs10_seed42`, state `forbidden`.  Do not construct,
mesh, solve, inspect or add a bypass for it.

## Verified local state

- `pytest -q <S7 directory>`: 26 passed, about 12 s.
- `ruff check <S7 directory>`: clean.
- Python 3.13.9, Gmsh 4.15.2, NumPy 2.5.1, SciPy 1.18.0, pyGeo 1.17.0,
  pyspline 1.5.4.
- **SU2 8.5.0 "Harrier"** in `AERIS_MESH_STUDY/tools/su2_8.5.0/bin`, symlinked
  into `.venv/bin`.  Self-contained: no sudo, no `LD_LIBRARY_PATH`.  It is
  gitignored as a reproducible download; re-fetch from the official release if
  the tree is cleaned.
- Evidence lives under the gitignored `artifacts/` tree, so the numbers that
  matter are transcribed into `STUDY.md` and `README.md`.

## Invariants worth knowing before editing

- The pyGeo wall is full-wing, independently triangulated, and fixed inside every
  retry; Gmsh surface algorithms do not remesh it.
- The tip cap is planar Delaunay over the perimeter nodes, with the conformal
  ladder as a verified fallback.  Both a centre fan and a rigid ladder were tried
  and failed; see `STUDY.md`.
- Post-generation optimisation is Netgen scoped to the core volume only, with
  automatic rollback if it increases invalid cells.  Relocate3D must never be
  used: it destroys the prism schedule.
- Cell validity uses the isoparametric Jacobian, never a sub-volume decomposition.
- Face quality is split by element family; gates read the core and its interface,
  the prism interior is reported.
- Distribution-quality gates are enforced from the development tier upward and
  reported below it.  Binary correctness is gated at every tier.
- Wall y+ comes from the surface Paraview file, not the CSV, because SU2 8.5 omits
  every PRIMITIVE field from the CSV.
- Attempts are immutable.  A stale or partial artifact is investigated or a new
  output root is used; it is never repaired in place.

## Next safe actions

1. Confirm multigrid over a longer run, then amend ADR-0017 with the measurements
   if it reaches the residual gate.
2. Run the remaining 95 coarse meshes on the desktop using `RUNBOOK.md`.
3. Attempt a converged coarse CFD case; budget about 3 GB of RAM per MPI rank.
4. Obtain the independent Claude Opus/max review.

Never touch the hold-out until a superseding decision records that the
development programme, pilots, y+, grid studies, recovery, schemas and
independent review are all complete.

## The half domain

S7 meshes y >= 0, closed at the root by a cap labelled `symmetry`, and this is the
declared domain.  Things to know before changing any of it:

- The prism layer is **marched here, not extruded by Gmsh** (`prism_layer.py`).
  Gmsh offers no way to constrain its extrusion direction, and at the root the
  wall does not meet the plane perpendicularly, so its layer leaves the domain -
  measured at 0.705 mm against a 15.449 mm layer.
- Vertex normals are **angle-weighted, not area-weighted**.  Area weighting lets
  the large flat tip-cap faces steer the direction and drops prism quality from
  0.3795 to 0.0311, below the 0.05 gate.
- **Do not scale the step to mitre corners.**  It raises quality and lifts the
  first cell off the wall by up to a factor of two, which is what sets y+: the
  relative error went from zero to 0.9977 against a 0.05 limit.  It was tried,
  measured and deleted.
- The core needs **both** the background size field and the optimisation passes.
  With neither, tet quality was 0.0076 against a 0.025 gate; the field alone gave
  0.0117 and the passes took it to 0.0774.
- `REF_AREA` is **halved** for a half mesh.  The reference values describe the
  whole wing whatever is meshed, so leaving it alone reports CL and CD at half
  their true value on a run that looks entirely healthy.
- `symmetry` is not a wall label.  It carries no prisms, and `WALL_LABELS` rather
  than `LABELS` is what the audit, the wall mapping and the solver config iterate.

