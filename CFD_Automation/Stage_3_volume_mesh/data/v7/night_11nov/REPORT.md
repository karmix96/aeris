# V7 night run, 11–12 Nov 2026: the first solves on Stage 3 meshes

Claude Code, alone on Mike's desktop, following `solve/NIGHT_11NOV.md`. **In progress.** This file is rewritten after
every finished run. Last update: 11 Nov, 23:56 (A1 running).

One wing: BWB reference wing 0, Re 3 × 10⁵ on the mean chord, Mach 0.1, the transition band on.

## 1. Machine

| | |
| --- | --- |
| CPU | Intel Core i5-10400, 2.90 GHz: **6 physical cores**, 12 threads |
| RAM, host | **15.86 GiB** (2 × 8 GB). Not the 48–52 GB of the record. |
| RAM, WSL | 13.65 GiB total, 12.65 GiB available at the start; swap 8 GiB |
| WSL limit | `C:\Users\mike\.wslconfig`: `memory=14GB`, `swap=8GB`, `autoMemoryReclaim=gradual`. Not changed. |
| Host pagefile | 5,120 MB allocated, 0.07 GiB in use at the start |
| Disk | 918 GB free |
| ADflow | 2.13.1, MACH-Aero env `/home/mike_kara/miniconda3/envs/mach-aero`; Open MPI 5.0.10, PETSc 3.21.6, CGNS 4.5.2 (ADF only) |
| ADflow launcher | the env's own `mpirun` (Open MPI 5.0.10); the log says "parallel executable running on 6 processors" |
| SU2 | **8.5.0**, not 8.6.0: `AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD`, a static build with MPICH inside |
| SU2 launcher | MPICH 5.0.1 `mpiexec.hydra` (`/home/mike_kara/miniconda3/pkgs/mpich-5.0.1-hfbb40bb_4/bin/`) |
| Repo env | `.venv` (a conda env): Python 3.13.9, pyGeo 1.17.0, pySpline 1.5.4, cfdauto 0.7.0 |
| Commit | `f5ea83c2` at the start; Stage 3 tests 45 passed |

The host has 16 GB, so the plan's side-by-side lines cannot run. Every run goes alone, in the plan's order.

## 2. The runs

| Run | Mesh | Cells | Solver, model | State |
| --- | --- | --- | --- | --- |
| A1 | today VVC | 1,075,074 | ADflow SA | running since 23:51 |

## 3. The answers

**Q6, the pyGeo meshes.** 20 of 20 meshes are the same on both lofts and pass on both. The largest node difference is
4.2 × 10⁻¹¹ mean chords in the volume and 4.6 × 10⁻¹⁴ on the surface. The meshes on the pyGeo loft are the meshes
that were checked on the numpy loft.

The three meshes of step 2 have exactly the plan's cell counts on pyGeo: 1,075,074 (VVC), 2,324,016 (VC) and
1,475,376 (light VC). The what-if path gives today's VC to 5.0 × 10⁻¹² (`--check-production`).

Q1–Q5 and Q7: waiting for the runs.

## 4. What failed

1. **A1, attempt 1: the plan's command does not start.** `--set-option timeLimit=10800` reaches ADflow as an int,
   and ADflow refuses it. Command and error:

   ```
   mpirun -np 6 python solve/run_adflow.py --case runs/n11_today_VVC_a4 --set-option timeLimit=10800 \
       --lift-distribution 150 --slices 0.5,0.8,0.9,0.95,0.98
   Error: Datatype for option timeLimit is not valid. Expected data type <class 'float'>.
   Received data type is <class 'int'>.
   ```

   Fix: `timeLimit=10800.0`, the same value. No iteration was lost: the error comes before the first one.
2. **`run_adflow.py` wrote its records from every rank.** The preflight's `preflight.json` came out with two stray
   bytes after rank 0's record, so it did not parse. Five of the six records said `"ranks": 1`. `result.json` is
   written the same way, so a non-root rank could leave its own memory as the run's. Fixed before the solve: one
   writer, rank 0 (`tools/run_adflow_rank0.patch`). The file is changed in this checkout and not committed: the plan
   names only this folder.
3. **SU2 under Open MPI runs as separate copies.** Found in a test before any SU2 run. `SU2_CFD` 8.5.0 here is a
   static MPICH build. Under the MACH-Aero `mpirun` (Open MPI), `-np 2` printed two banners, did no partitioning
   and exited 0. Under MPICH's `mpiexec.hydra` it printed one banner and partitioned with ParMETIS (136 edge cuts).
   S8's SU2 runs show the same two-banner signature (`runs/su2_validation/e387_sa_lm/run.log`), so they ran as
   two serial copies.

## 5. Solver options changed from the case files

- `timeLimit` as a float (see 4.1). Nothing else so far.

## 6. Choices made tonight

- **One run at a time.** Fewer than 12 physical cores, and RAM for one ADflow VVC run only.
- **A host-side memory log with every run** (`tools/host_watch.py`): Windows free memory, pagefile in use and the WSL
  VM's size every 60 s. WSL cannot see the host paging, so `rss_watch.py` cannot either. It stops a run only if the
  host pagefile nears full: 2.5 GiB over its start, about 4.5 of the 5 GiB. My first rule, 2 GiB over the start, would have
  killed A1 at its third sample: the pagefile grew by 1.99 GiB while WSL's swap stayed at 0.001 GiB. It was replaced
  at 23:53, before it acted (both records are kept).
- **A hard stop at the cap + 30 min** around each ADflow run, as a safety net only. ADflow's own `timeLimit` ends
  the run at the cap first.
- **The run wrappers** are `tools/run_adflow_night.sh` and `tools/run_su2_night.sh`: the plan's commands, the plan's
  watchdog, the host log and `timing.json` (start, end, exit code).

## 7. What this does not show

Written at the end.
