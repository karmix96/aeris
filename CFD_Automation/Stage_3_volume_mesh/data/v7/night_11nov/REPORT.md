# V7 night run, 11–12 Nov 2026: the first solves on Stage 3 meshes

Claude Code, alone on Mike's desktop, following `solve/NIGHT_11NOV.md`. **In progress.** This file is rewritten after
every finished run. Last update: 12 Nov, 00:35 (A1 done; A1b, A1's first retry, running).

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

All on 6 ranks, one at a time (nothing side by side). The table is `run_table.md`, built from the run folders by
`tools/collect.py`; every number is read from the copied files.

| Run | Mesh | Cells | Solver, model | α | Wall time | Iterations | Residual drop | Verdict | Peak RAM (GiB) | GiB per M cells | CL | CD (counts) | CDp | CDv | CMy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | today VVC | 1,075,074 | ADflow SA | 4° | 30.2 min | 182 | 4.21 | not accepted: not converged (stopped, see 6) | 10.28 | 9.57 | 0.1906 | 185.5 | 0.00676 | 0.01178 | 0.00984 |
| A1b | today VVC | 1,075,074 | ADflow SA, `ANKUseTurbDADI=false` | 4° | running since 00:22 | | | | | | | | | | |

A1's forces were steady long before the stop: since iteration 80, CD moved 0.14 counts and CL 0.036 %; since
iteration 100, 0.04 counts and 0.009 %. The plan's settled rule could not judge A1: it needs at least 225
iterations, and A1 has 182 (`A1_today_VVC_a4/adflow/history_from_log.json`).

## 3. The answers

**Q1, ADflow (so far).** ADflow reads the Stage 3 CGNS, finds the families `wall`, `farfield` and `symmetry`, and
builds the freestream exactly (velocity and lift direction errors 0.0). As written, it does not converge on VVC: the
relative residual fell 4.2 orders in 182 iterations and was still falling only 0.0026 orders per iteration.

The cause is measured: the turbulence equation. Between iterations 50 and 170 the density residual fell 2.3 orders
(4.9 × 10⁻⁴ to 2.6 × 10⁻⁶) while the SA residual fell from 2.1 × 10⁻⁶ to 8.5 × 10⁻⁷. With the case's settings ADflow
updates the turbulence by one DADI sweep per ANK step, and never switches to its coupled or second-order modes
(both switch tolerances default to 10⁻¹⁶). A1b changes only that (`ANKUseTurbDADI=false`: a Krylov solve for the
turbulence).

**Q2, ADflow memory (one point).** A1 peaked at **10.28 GiB** over the 6 ranks (largest rank 1.81 GiB):
**9.57 GiB per million cells**. S8's laws gave 10.46 GiB (ANK only) and 11.68 GiB (ANK then NK): the ANK-only law is
1.7 % high. The watchdog's sampled peak agrees (10.285 GiB). WSL never swapped (0.001 GiB). The host's pagefile grew
by 2.0 GiB in the first minute and then held; Windows stayed above 1.7 GiB free.

**Q2, ADflow time.** 10 s per iteration early, 15 s by iteration 180 as the linear solves grew from 20 to 33 inner
iterations: 1,815 s for 182 iterations. In 30 min the run had not converged, so the plan's "time to converge" is not
measured yet: it is more than 28 min per million cells (S8's law: 35.7).

**Q6, the pyGeo meshes.** 20 of 20 meshes are the same on both lofts and pass on both. The largest node difference is
4.2 × 10⁻¹¹ mean chords in the volume and 4.6 × 10⁻¹⁴ on the surface. The meshes on the pyGeo loft are the meshes
that were checked on the numpy loft.

The three meshes of step 2 have exactly the plan's cell counts on pyGeo: 1,075,074 (VVC), 2,324,016 (VC) and
1,475,376 (light VC). The what-if path gives today's VC to 5.0 × 10⁻¹² (`--check-production`).

**A2, A3, X1, X2: they do not fit this machine.** The plan's rule for A2: A1's measured peak scaled by the cells
must be below 80 % of `MemAvailable` (12.6 GiB, so 10.1 GiB). A2: 10.28 × 2,324,016 / 1,075,074 = 22.2 GiB. A3:
10.28 × 1,475,376 / 1,075,074 = 14.1 GiB, more than all of WSL's 13.65 GiB. X2 (ADflow on VC with fill 0) and X1
(SU2 on VC) are on the same 2.3 M-cell mesh. So **Q4 cannot be answered on this desktop**, and Q2 gets one ADflow mesh
size, not two.

Q3, Q5 and Q7: waiting for the runs.

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
   written the same way, so a non-root rank could leave its own memory as the run's. Fixed before A1's solve: one
   writer, rank 0.
3. **`run_adflow.py` kept no force history.** ADflow's history keys are its CGNS monitor names (`CoefLift`,
   `CoefDrag`, `CoefPressureDrag`, `CoefViscousDrag`, `CoefMomentY`, `RSDMassRMS`, `totalR`); the filter knew only
   `cl`, `cd`, ... and kept nothing. So `read_results.py` said "no force history in result.json" for A1, and it would
   call even a converged run "not accepted". Fixed after A1 (A1 and A1b were already running the old code): the
   names are mapped. For A1 and A1b the history is read from ADflow's own log (`tools/adflow_log_history.py`).
4. **`--lift-distribution` and `--slices` failed on ADflow** (A1; new on 11 Nov, untested until tonight):
   `ValueError: invalid literal for int() with base 10: 'allSurfaces'` (in `result.json["extras"]`). It is ADflow
   2.13.1's own bug: `writeLiftDistributionFile` and `writeSlicesFile` pass the group name `"allSurfaces"` where
   `tecplotio.writetecplot` wants the family list; `writeSolution` does it right. Fixed after A1 the way
   `writeSolution` does it. The solve was not affected.
5. **SU2 under Open MPI runs as separate copies.** Found in a test before any SU2 run. `SU2_CFD` 8.5.0 here is a
   static MPICH build. Under the MACH-Aero `mpirun` (Open MPI), `-np 2` printed two banners, did no partitioning
   and exited 0. Under MPICH's `mpiexec.hydra` it printed one banner and partitioned with ParMETIS (136 edge cuts).
   S8's SU2 runs show the same two-banner signature (`runs/su2_validation/e387_sa_lm/run.log`), so they ran as
   two serial copies.

The three `run_adflow.py` fixes are in `tools/run_adflow_night_fixes.patch`. The file is changed in this checkout
and not committed: the plan names only this folder.

## 5. Solver options changed from the case files

- `timeLimit` as a float (4.1), the same value.
- A1b (A1's first retry, of two allowed): `ANKUseTurbDADI=false`. Why: A1's turbulence residual stalled (3).

## 6. Choices made tonight

- **One run at a time.** Fewer than 12 physical cores, and RAM for one ADflow VVC run only.
- **A1 was stopped at 30 min, before its 3 h cap.** At 00:21 it had settled forces and a residual falling 0.0026
  orders per iteration, slower every 30 iterations (0.0048, 0.0044, 0.0036, 0.0029). At its best measured rate, 1e-6
  was more than 3 h away. The night cannot hold the plan's caps on this machine: A1, B1, A4, A5 and B2 at their caps
  are 12 h. It was stopped with SIGUSR2, ADflow's own "write and quit", so `result.json` and the solution files were
  written as at a normal end. ADflow does not catch SIGTERM.
- **SU2 runs end when the plan's acceptance rule is met** (`tools/su2_accept_stop.py`): the case files stop SU2 only at
  an absolute density residual of 10⁻¹² or the budget, so a run that meets the rule would still use its whole cap.
  The watcher applies `read_results.py`'s rule with its own code, waits for SU2's next output write, then stops
  the run. No solver setting changes.
- **A host-side memory log with every run** (`tools/host_watch.py`): Windows free memory, pagefile in use and the WSL
  VM's size every 60 s. WSL cannot see the host paging, so `rss_watch.py` cannot either. It stops a run only if the
  host pagefile nears full: 2.5 GiB over its start, about 4.5 of the 5 GiB. My first rule, 2 GiB over the start, would have
  killed A1 at its third sample: the pagefile grew by 1.99 GiB while WSL's swap stayed at 0.001 GiB. It was replaced
  at 23:53, before it acted (both records are kept).
- **A hard stop at the cap + 30 min** around each ADflow run, as a safety net only.
- **The run wrappers** are `tools/run_adflow_night.sh` and `tools/run_su2_night.sh`: the plan's commands, the plan's
  watchdog, the host log and `timing.json` (start, end, exit code, and from 00:22 the monotonic clock: one `date`
  read at 23:53 came back 92 s ahead).
- **Light work ran beside the solves** (copying files, git, this report). Nothing that reads a volume file ran beside
  a solve: the memory margin was below 2 GiB.

## 7. What this does not show

Written at the end.
