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

## Desktop status, 2026-08-24

Stage 0 was attempted and is **blocked on machine memory**: the desktop is WSL2 on
a 16 GB host, capped at 7.7 GiB, and the resource preflight rejects a coarse case
at both the 8 GiB floor and the 70-percent rule.  The toolchain a fresh clone
lacks - `.venv` at the pinned stack, SU2 8.5.0 - is now rebuilt, tests pass 26/26,
and an MPICH/OpenMPI launcher defect that would have produced wrong convergence
histories is fixed.  Read `DESKTOP_STAGE0_STATUS_2026-08-24.md` before resuming.

## Next safe actions

1. Confirm multigrid over a longer run, then amend ADR-0017 with the measurements
   if it reaches the residual gate.
2. Run the remaining 95 coarse meshes on the desktop using `RUNBOOK.md`.
3. Attempt a converged coarse CFD case; budget about 3 GB of RAM per MPI rank.
4. Obtain the independent Claude Opus/max review.

Never touch the hold-out until a superseding decision records that the
development programme, pilots, y+, grid studies, recovery, schemas and
independent review are all complete.
