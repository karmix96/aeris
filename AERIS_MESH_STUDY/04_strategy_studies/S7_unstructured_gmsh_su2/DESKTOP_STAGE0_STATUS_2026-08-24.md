# S7 Stage 0 on the desktop - 2026-08-24

Attempted the multigrid confirmation per `RUNBOOK.md` "Confirm multigrid".  It did
not run.  Stage 0 is **blocked on machine memory**, and nothing about the study
itself changed.  No gate was moved, no result is claimed.

## What the desktop actually is

The "desktop" is a WSL2 instance on a **16 GB Windows host** with no `.wslconfig`,
so WSL takes the 50 percent default: **7.7 GiB total, 6.5-6.7 GiB available**.
It is not a larger machine than the laptop the study was written on; it is the
same class, seen through a hypervisor that hides half the RAM.

## The blocker, in the policy's own words

    resource preflight failed: available_ram_below_production_floor,
                               estimated_memory_exceeds_70_percent_available

Both arms of `resource_safety` reject a coarse case here:

| rule | requires | this machine |
|---|---|---|
| `production_min_available_ram_gib` | 8.00 GiB available | 6.47 GiB |
| estimate <= 70 percent of available | 8.47 GiB available | 6.47 GiB |

The estimate is 2 549 227 cells x 2 500 B/cell = **6.37 GB**, so the 70 percent
rule binds slightly harder than the floor.  Clearing both needs about **8.5 GiB
available**, i.e. a WSL allocation of roughly **11 GiB**, which the 16 GB host can
give while leaving Windows about 5 GB.

This is the floor working.  It was not lowered and must not be.

## Prerequisites that were missing and are now built

A fresh clone has none of the toolchain; all of it is gitignored and was rebuilt
from source rather than worked around.

- **`.venv` did not exist.**  Rebuilt at the pinned stack: Python **3.13.9**,
  NumPy **2.5.1**, SciPy **1.18.0**, gmsh **4.15.2**, pyspline **1.5.4**,
  pyGeo **1.17.0**.  pyspline's Fortran extension was recompiled for cp313 with
  gfortran 13.3.0 from `.deps/mdolab/pyspline`; mpi4py 4.1.2 rebuilt against the
  local OpenMPI 5.0.10.
- **SU2 8.5.0 "Harrier"** re-fetched to `AERIS_MESH_STUDY/tools/su2_8.5.0/bin`
  and version-verified.
- `pytest -q` **26 passed**, `ruff check` clean, under the rebuilt `.venv`.

The conda `aeris` env cannot be used for S7: it is Python 3.11.15 / NumPy 2.4.6 /
SciPy 1.17.1 and the software preflight rejects it by exact version match.  That
preflight is provenance, not pedantry, and was left alone.

## A real defect found on the way: the MPI launcher

The linux64 SU2 release is **statically linked against MPICH**.  The only
`mpirun` on this machine is **OpenMPI 5.0.10** (from the MACH-Aero build).

Launching an MPICH binary under OpenMPI does not fail.  Each process
singleton-inits as rank 0 of its own world, so `mpirun -np N SU2_CFD` silently
runs **N duplicate serial solves racing on one `history.csv`** instead of one
N-rank job.  Measured: OpenMPI `-np 2` emits two independent SU2 error banners;
MPICH's hydra emits one.

`convergence_matrix.py` hardcoded `"mpirun"`, so it would have produced
convincing, wrong convergence histories.  Fixed by pinning the launcher:

- MPICH installed at `AERIS_MESH_STUDY/tools/mpich` (gitignored).
- `convergence_matrix.py` now reads **`SU2_MPI_LAUNCHER`**, defaulting to
  `mpirun` so no other machine changes behaviour.

Numerics, variants and gates are untouched.

## Scope note for whoever runs this next

Even once memory is raised, this host is a 16 GB machine.  The RUNBOOK's `2 3`
(six ranks, ~18 GB) needs 32 GiB and is **not** available here.  Use the RUNBOOK's
own 16 GiB guidance - `2 1`, two ranks, variants serial - and expect three
sequential 6 000-iteration runs.

## To resume

1. On Windows, create `%USERPROFILE%\.wslconfig` with `memory=11GB`, then
   `wsl --shutdown` and reopen.  Confirm `free -g` shows >= 9 GiB available.
2. Build the coarse mesh:

        .venv/bin/python \
          AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/run_s7.py \
          --index 0 --level coarse --te-variant te_1p0mm \
          --output <artifacts_root> --execute

3. Run the multigrid matrix against the mesh it writes:

        export PATH="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin:$PATH"
        export SU2_RUN="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin"
        export SU2_MPI_LAUNCHER="$PWD/AERIS_MESH_STUDY/tools/mpich/bin/mpiexec"
        .venv/bin/python \
          AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/convergence_matrix.py \
          <mesh>.su2  6000  2  1  round-two

## Documentation defects found

- `RUNBOOK.md` and `VALIDATION_PROGRAMME.md` both invoke
  `production_desktop.sh` (and `production_hpc_slurm.sh`).  **Neither file exists,
  and neither appears anywhere in git history.**  The working entry point is
  `run_s7.py`.
- `VALIDATION_PROGRAMME.md`'s claim that the campaign "will refuse to start"
  below 8 GiB available **holds** and was observed doing so.  Worth knowing why,
  because the reported tier misleads: a case at a grid-family level reports
  `evidence_tier: development`, but `campaign.py:455` promotes it to `production`
  for the resource check.  `enforce_resource_safety` has arms only for
  `laptop_smoke` and `production`, so a bare `development` tier would pass
  unchecked - it just never reaches the guard that way from a grid level.
