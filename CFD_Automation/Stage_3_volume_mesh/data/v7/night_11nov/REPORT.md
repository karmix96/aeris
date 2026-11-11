# V7 night run, 11–12 Nov 2026: the first solves on Stage 3 meshes

Claude Code, alone on Mike's desktop, following `solve/NIGHT_11NOV.md`. **In progress.** This file is rewritten after
every finished run. Last update: 12 Nov, 01:45 (A1, A1b, B1 done; B1b, SU2 SA with 30 linear iterations, running since 01:31).

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
`tools/collect.py`; every number is read from the copied files. y⁺ is over the wing surface (upper, lower, nose),
without the trailing-edge base and the tip cap (section 3, Q7).

| Run | Mesh | Cells | Solver, model | α | Wall time | Iterations | Residual drop (orders) | Verdict of `read_results.py` | Peak RAM (GiB) | GiB per M cells | CL | CD (counts) | CDp | CDv | CMy | y⁺ largest, 99 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | today VVC | 1,075,074 | ADflow SA, as written | 4° | 30.2 min | 182 | 4.21 | not accepted: not converged; stopped, see 6 | 10.28 | 9.57 | 0.1906 | 185.5 | 0.00676 | 0.01178 | 0.00984 | 2.92, 1.92 |
| A1b | today VVC | 1,075,074 | ADflow SA, `ANKUseTurbDADI=false` | 4° | 31.2 min | 153 | 6.01 | **converged** (9.76 × 10⁻⁷); the rule says "not accepted": see below | 10.99 | 10.22 | 0.1907 | 185.5 | 0.00676 | 0.01178 | 0.00984 | 2.92, 1.92 |
| B1 | today VVC | 1,075,074 | SU2 SA, as written | 4° | 29.3 min | 582 | 2.83 | not accepted: not converged, forces not settled; stopped, see 6 | 7.32 | 6.81 | 0.1883 | 67.7 | −0.00621 | 0.01298 | 0.01246 | 4.82, 3.88 (first node) |
| B1b | today VVC | 1,075,074 | SU2 SA, `LINEAR_SOLVER_ITER= 30` | 4° | running since 01:31 | | | | 9.25 (plateau) | 8.60 | | | | | | |

**A1b converged and its forces are settled, but the plan's rule cannot say so.** `read_results.py` needs at least
225 iterations before it judges "settled" (the last 20 %, at least 200, plus 25); A1b converged in 153. Measured from
ADflow's own log: since iteration 100, CD moved 0.0096 counts and CL 0.008 % (the rule allows 0.5 counts and
0.1 %). A1: since iteration 100, 0.04 counts and 0.009 %. The rule is unchanged; Mike decides whether ADflow needs a
shorter window. (A1 and A1b also lost their history from `result.json`: section 4.3. The numbers here are from
`adflow/history_from_log.json`.)

## 3. The answers

**Q1, ADflow: yes, with one option.** ADflow reads the Stage 3 CGNS, finds the families `wall`, `farfield` and
`symmetry`, and builds the freestream exactly (velocity and lift direction errors 0.0).

- **As written (A1), it does not converge on VVC.** The relative residual fell 4.2 orders in 182 iterations and was
  falling only 0.0026 orders per iteration, slower every 30 iterations. The cause is the turbulence equation:
  between iterations 50 and 170 the density residual fell 2.3 orders, the SA residual from 2.1 × 10⁻⁶ to
  8.5 × 10⁻⁷. With the case's settings ADflow updates the turbulence by one DADI sweep per ANK step.
- **With `ANKUseTurbDADI=false` (A1b: the turbulence by its own Krylov solve), it converges:** 9.76 × 10⁻⁷ in 153
  iterations, 31.2 min. The SA residual was 3.6 × 10⁻⁸ at iteration 29 and 1.8 × 10⁻¹⁰ at 150. The forces are the
  same as A1's to 4 digits: CL 0.19065 against 0.19064, CD 185.49 against 185.47 counts.
- **For the case files:** `ANKUseTurbDADI: False` is one line in `case.py`'s ADflow options. It costs 0.7 GiB on
  VVC (6.8 %) and 22 % more time per iteration (12.2 s against 10.0 s), and saves the stall.

**Q2, ADflow memory: one mesh size, and the law holds.**

| | Cells | Peak (GiB, 6 ranks) | GiB per M cells | S8 law, ANK only | S8 law, ANK then NK |
| --- | --- | --- | --- | --- | --- |
| A1, as written | 1,075,074 | 10.28 | 9.57 | 10.46 (+1.7 %) | 11.68 |
| A1b, turbulence by Krylov | 1,075,074 | 10.99 | 10.22 | 10.46 (−4.8 %) | 11.68 |

The largest rank held 1.81 GiB (A1) and 1.93 GiB (A1b). The watchdog's sampled peaks agree to 0.01 GiB. WSL never
swapped (0.019 GiB at most). The host paged up to 2.1 GiB into its pagefile and Windows went down to 0.88 GiB free;
nothing slowed or failed.

**Q2, ADflow time.** A1b converged in 31.2 min on 6 ranks: **29.0 min per million cells** (S8's law: 35.7). A1
averaged 10.0 s per iteration and A1b 12.2 s; in both, the later iterations were slower as the linear solves grew
(A1: 20 to 33 inner iterations per step).

**Q6, the pyGeo meshes.** 20 of 20 meshes are the same on both lofts and pass on both. The largest node difference is
4.2 × 10⁻¹¹ mean chords in the volume and 4.6 × 10⁻¹⁴ on the surface. The meshes on the pyGeo loft are the meshes
that were checked on the numpy loft.

The three meshes of step 2 have exactly the plan's cell counts on pyGeo: 1,075,074 (VVC), 2,324,016 (VC) and
1,475,376 (light VC). The what-if path gives today's VC to 5.0 × 10⁻¹² (`--check-production`).

**Q7, y⁺ on ADflow (A1b, VVC, design 1.3).** Over the wing surface: largest 2.92, 99 % 1.92, median 0.74; 10.6 % of
the faces above 1.3. By zone:

| Zone | Largest | 99 % | Median | Faces above 1.3 |
| --- | --- | --- | --- | --- |
| upper side | 2.92 | 1.83 | 0.74 | 9.5 % |
| lower side | 2.73 | 1.83 | 0.72 | 9.0 % |
| nose | 2.92 | 2.66 | 1.27 | 48 % |
| tip cap | 3.76 | 3.08 | 1.62 | 99.8 % |
| trailing-edge base | 9.54 | 8.67 | 2.12 | 67 % |

The wall rule holds on most of the wing. It is exceeded at the nose, where the skin friction peaks, and on the tip
cap. The base is a separated region; its y⁺ is not a wall-resolution measure. SU2's y⁺ (B1) is the second reading.

**A2, A3, X1, X2: they do not fit this machine.** The plan's rule for A2: A1's measured peak scaled by the cells
must be below 80 % of `MemAvailable` (12.6 GiB, so 10.1 GiB). A2: 10.28 × 2,324,016 / 1,075,074 = 22.2 GiB. A3:
10.28 × 1,475,376 / 1,075,074 = 14.1 GiB, more than all of WSL's 13.65 GiB. X2 (ADflow on VC with fill 0) and X1
(SU2 on VC) are on the same 2.3 M-cell mesh. So **Q4 cannot be answered on this desktop**, and Q2 gets one ADflow mesh
size, not two.

**Q1, SU2 (so far): it reads the mesh; as written it does not converge.** SU2 8.5.0 reads the `.su2` file
(1,107,836 points, 1,075,074 hexahedra), partitions it on 6 ranks and accepts every option of the case file. As
written (B1), the adaptive CFL collapses: SU2 cuts it ×0.1 whenever the linear solver misses the accepted linear
residual of 10⁻³ in its 10 iterations, and doubles it otherwise, so it cycled between 1 and 86. In 582 iterations
the density residual fell 2.8 orders and the momentum residual stalled at 10⁻⁷·³ from iteration 120; CD was still
falling 15 counts per 100 iterations. B1b (try 1 of 2) gives the linear solver 30 iterations: the CFL reached 419
by iteration 25 and the density residual 10⁻⁸·² (B1 needed 470 iterations for that).

**Q3, ADflow SA against SU2 SA (provisional: SU2 not converged).** At B1's last iteration the lift agrees within
1.2 % (0.1883 against 0.1907) and the friction drag is 10 % higher (SU2 129.8 counts, ADflow 117.8), but the
pressure drag does not agree: **SU2 −62.1 counts, ADflow +67.6.** A negative pressure drag is not physical here (the induced drag
alone is about +21 counts).

- It is not SU2's integration and not the face orientation: integrating SU2's own wall Cp by hand over its quads
  gives the same number (−65.7 against SU2's −65.5 counts at iteration 500), and the wall's area vectors close to
  6 × 10⁻¹⁶ in x and z (`tools/su2_surface_forces.py`).
- It is the leading edge. SU2's suction peak is about 30 % higher than ADflow's at mid-span
  (`B1_today_VVC_a4_su2_sa/su2_sa/cp_against_adflow_A1b_it500.png`), and its stagnation pressure overshoots: wall
  Cp up to 1.9 along the whole leading edge and 2.25 at the tip, against the isentropic 1.0025 at Mach 0.1 (195 nodes
  above it, all at x/c ≤ 0.004). ADflow overshoots too, but to 1.17 (20 cells, all at the nose).
- Two readings, not separated tonight: SU2 is far from converged; and SU2's compressible Roe scheme at Mach 0.1,
  without a low-Mach correction, overshoots the stagnation pressure (a known property of upwind schemes at low Mach).
  S8's SU2 report already says the incompressible solver is the one for this regime ("AERIS flies at Mach 0.084 —
  effectively incompressible — so the INC_RANS cases are the ones in our regime"). The case files use `SOLVER= RANS`.
- The two codes also run different SA variants: ADflow's default `useft2SA = True`, SU2's log says
  "Spalart-Allmaras-noft2".

**Q7, y⁺ on SU2 (B1, not converged; design 1.3 at VVC).** Wing-surface nodes: largest 4.82, 99 % 3.88, median 1.55;
91 % above 1.3. SU2 reports y⁺ at the first node off the wall, ADflow at the first cell centre, half as far, so
ADflow's median 0.74 corresponds to about 1.48 at the first node. **Both say the first cell is about 20 % taller
than the y⁺ 1.3 design over most of the wing**, more at the nose and the tip cap.

Q5: waiting for A4 and A5.

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
   `cl`, `cd`, ... and kept nothing. So `read_results.py` said "no force history in result.json" for A1 and A1b.
   Fixed after A1 (A1 and A1b were already running the old code): the names are mapped. Tested at 00:57 on a
   zero-iteration restart of A1b: the history has `cl`, `cd`, `cdp`, `cdv`, `cmy`, `resrho`, `totalres`, `iter`.
4. **`--lift-distribution` and `--slices` failed on ADflow** (A1 and A1b; new on 11 Nov, untested until tonight):
   `ValueError: invalid literal for int() with base 10: 'allSurfaces'` (in `result.json["extras"]`). It is ADflow
   2.13.1's own bug: `writeLiftDistributionFile` and `writeSlicesFile` pass the group name `"allSurfaces"` where
   `tecplotio.writetecplot` wants the family list; `writeSolution` does it right. Fixed after A1 the way
   `writeSolution` does it. Tested on the same restart: `lift_distribution.dat` and `slices.dat` were written, and the
   restart's forces equal A1b's to every printed digit. The solves were not affected.
5. **SU2 under Open MPI runs as separate copies.** Found in a test before any SU2 run. `SU2_CFD` 8.5.0 here is a
   static MPICH build. Under the MACH-Aero `mpirun` (Open MPI), `-np 2` printed two banners, did no partitioning
   and exited 0. Under MPICH's `mpiexec.hydra` it printed one banner and partitioned with ParMETIS (136 edge cuts).
   S8's SU2 runs show the same two-banner signature (`runs/su2_validation/e387_sa_lm/run.log`), so they ran as
   two serial copies. B1 runs under `mpiexec.hydra`: one banner, ParMETIS, 38,022 edge cuts.

The three `run_adflow.py` fixes are in `tools/run_adflow_night_fixes.patch`. The file is changed in this checkout
and not committed: the plan names only this folder.

## 5. Solver options changed from the case files

- `timeLimit` as a float (4.1), the same value.
- A1b, A1's first retry of two allowed: `ANKUseTurbDADI=false`. Why: A1's turbulence residual stalled (Q1). It worked;
  no second try was needed.
- B1b, B1's first retry of two allowed: `su2_sa_lin30.cfg`, a copy of `su2_sa.cfg` with `LINEAR_SOLVER_ITER= 30`
  (was 10) and `LINSOL` added to `HISTORY_OUTPUT` (output only: the linear residual in the history). Why: B1's
  adaptive CFL collapsed (Q1). Cost: 1.9 GiB more (9.25 GiB) and about 5.5 s per iteration instead of 3.0 s.

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
- **B1 was stopped at 29 min, before its 2.5 h cap**, for the same reason as A1: the CFL collapse was measured and
  explained, and at its rate it could not converge in the cap. SU2 8.5.0 catches SIGTERM and writes all its output
  files ("Interrupt signal (15) received, saving files and exiting"), so B1's files are at its last iteration, 582.
- **A hard stop at the cap + 30 min** around each ADflow run, as a safety net only.
- **The run wrappers** are `tools/run_adflow_night.sh` and `tools/run_su2_night.sh`: the plan's commands, the plan's
  watchdog, the host log and `timing.json` (start, end, exit code, and from 00:22 the monotonic clock: one `date`
  read at 23:53 came back 92 s ahead).
- **`solve/wake_check.py` is written** (Q5) and was tested on A1b's 4° solution before B1 (in the run folder as
  `wake_check_a4_test.*`): the wake centre leaves the trailing edge at 3.5° and bends down to 2.6° by 2 chords,
  below the freestream as the downwash should make it, and inside the band at every line.
- **Light work ran beside the solves** (copying files, git, this report). Nothing that reads a volume file ran beside
  an ADflow solve: the memory margin was below 2 GiB.

## 7. What this does not show

Written at the end.
