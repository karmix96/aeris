# V7 night run, 11–12 Nov 2026: the first solves on Stage 3 meshes

Claude Code, alone on Mike's desktop, following `solve/NIGHT_11NOV.md`. **In progress.** This file is rewritten after
every finished run. Last update: 12 Nov, 04:35 (all runs done but B2b, SU2 SST + LM, running since 04:18; it stops by 06:30).

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
| A4 | today VVC | 1,075,074 | ADflow SA, `ANKUseTurbDADI=false` | −5° | 63.8 min | 239 | 6.00 | **converged** (9.99 × 10⁻⁷); the rule says "forces not settled": see below | 10.99 | 10.23 | −0.4484 | 336.5 | 0.02422 | 0.00944 | 0.03344 | |
| A5 | today VVC | 1,075,074 | ADflow SA, `ANKUseTurbDADI=false` | +10° | 27.5 min | 136 | 6.02 | **converged** (9.65 × 10⁻⁷); the rule: "too short to judge" | 10.99 | 10.23 | 0.6253 | 416.9 | 0.03054 | 0.01115 | −0.01459 | |
| B1b | today VVC | 1,075,074 | SU2 SA, `LINEAR_SOLVER_ITER= 30` | 4° | 15.4 min | 117 | 2.4 | not accepted: not converged; stopped, see 6 | 9.25 | 8.60 | 0.1980 | 65.9 | −0.00479 | 0.01139 | 0.00831 | |
| B1c | today VVC | 1,075,074 | SU2 SA, 30 linear iterations + `LOW_MACH_CORR= YES` | 4° | 47.3 min | 434 | 2.28 | not accepted: not converged; stopped, see 6 | 9.37 | 8.72 | 0.1982 | 143.6 | 0.00388 | 0.01048 | 0.00766 | 4.61, 3.91 (first node) |
| B2, try 1 | today VVC | 1,075,074 | SU2 SST + LM, 30 linear iterations + low-Mach correction | 4° | 0.7 min | 3 | | **killed by the watchdog** at 32 s: 11.96 GiB, 0.92 GiB available, swap +0.64 GiB | ≥ 11.96 | ≥ 11.1 | | | | | | |
| B2b, try 2 | today VVC | 1,075,074 | SU2 SST + LM, low-Mach correction, 10 linear iterations | 4° | running since 04:18 | | | | 9.18 (plateau) | 8.54 | | | | | | |

**A1b converged and its forces are settled, but the plan's rule cannot say so.** `read_results.py` needs at least
225 iterations before it judges "settled" (the last 20 %, at least 200, plus 25); A1b converged in 153. Measured from
ADflow's own log: since iteration 100, CD moved 0.0096 counts and CL 0.008 % (the rule allows 0.5 counts and
0.1 %). A1: since iteration 100, 0.04 counts and 0.009 %. A5 converged in 136 iterations, too short again; its forces moved 0.09 counts and 0.023 % since iteration 100.
A4 (239 iterations) is long enough to judge, and the rule says "forces not settled": its
200-iteration window (iterations 40 to 239) still holds the start-up (CD moved 14.1 counts in it). Over its last 50
iterations CD moved 0.12 counts and CL 0.044 %. So for a converged ADflow run the rule either cannot judge (fewer
than 225 iterations) or judges the start-up. The rule is unchanged; Mike decides whether ADflow needs a shorter
window (for example the last 20 % with no 200-iteration minimum). (A1 and A1b also lost their history from `result.json`: section 4.3. The numbers here are from
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

**Q2, what that gives for M and the light M (decision 113).** One mesh size cannot give the plan's straight line
`GiB = a + b × M cells`. Two bounds instead: all memory proportional to the cells (an upper bound: some memory is
fixed), and S8's fixed part (2.69 GiB, the ANK-only law) with tonight's slope.

| Run | GiB per M cells | M, 9.5 M cells | light M, 5.5 M cells |
| --- | --- | --- | --- |
| ADflow, as written (A1) | 9.57 | 70–91 GiB | 42–53 GiB |
| ADflow, `ANKUseTurbDADI=false` (A1b) | 10.22 | 76–97 GiB | 45–56 GiB |
| SU2 SA, as written (B1) | 6.81 | 44–65 GiB | 26–37 GiB |
| SU2 SA, 30 linear iterations (B1b) | 8.60 | 61–82 GiB | 36–47 GiB |
| SU2 SA, 30 linear iterations + low-Mach correction (B1c) | 8.71 | 62–83 GiB | 37–48 GiB |
| SU2 SST + LM, low-Mach correction, 10 linear iterations (B2b) | 8.54 | 60–81 GiB | 36–47 GiB |
| SU2 SST + LM, 30 linear iterations (B2 try 1, killed: a lower bound) | ≥ 11.1 | ≥ 85 GiB | ≥ 50 GiB |
| S8's laws (ANK only; ANK then NK) | | 71; 91 GiB | 43; 54 GiB |

On 48 GB, ADflow's M does not fit by either bound; the light M fits only by the lower bound, without margin. SU2
SA as written fits the light M; with the linear-solver fix it needs 37–48 GiB for the light M and 62–83 GiB for M.
SST + LM costs 25 % more than SA at the same settings (9.18 against 7.32 GiB) and with 30 linear iterations did not
fit 16 GB at VVC. These are extrapolations from 1.08 M cells:
the second point (VC, 2.3 M cells) needs a machine with more than 16 GB.

**Q2, ADflow time.** A1b converged in 31.2 min on 6 ranks: **29.0 min per million cells** (S8's law: 35.7). Linear in
the cells, that is about 4.6 h for M and 2.7 h for the light M on 6 ranks (more in practice: iterations grow with
the cells). A1
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
falling 15 counts per 100 iterations. B1b (try 1 of 2) gives the linear solver 30 iterations: the linear solves now converge (to 10⁻⁴ at CFL 30 to
500), the CFL reached 419 by iteration 25 and the density residual 10⁻⁸·² (B1 needed 470 iterations for that). But
then the density residual stayed at 10⁻⁸·¹ from iteration 25 to 117, the CFL was still reset every few dozen
iterations, and the forces drifted (CL +0.0003 per iteration). So the stall is not the linear solver: it is the
nonlinear iteration (the slope limiter is the usual cause) or the pressure field below.

**Q3, ADflow SA against SU2 SA on one grid: they agree in Cp once SU2 has its low-Mach correction; SU2 does not
converge here, so the drag comparison stays open.**

| | ADflow SA (A1b, converged) | SU2 SA as written (B1, 582 it.) | + 30 linear its (B1b, 117 it.) | + low-Mach correction (B1c, 434 it.) |
| --- | --- | --- | --- | --- |
| CL | 0.1907 | 0.1883 | 0.1980 | 0.1982 (+3.9 %) |
| CD (counts) | 185.5 | 67.7 | 65.9 | 143.6 (−41.9) |
| CDp (counts) | 67.6 | −62.1 | −47.9 | +38.8 (−28.8) |
| CDv (counts) | 117.8 | 129.8 | 113.9 | 104.8 (−13.0) |
| CMy | 0.00984 | 0.01246 | 0.00831 | 0.00766 (−0.0022) |
| largest wall Cp (isentropic: 1.0025) | 1.17 (20 cells at the nose) | 1.94 at mid-span, 2.25 at the tip | 2.26 (192 nodes) | **1.03 (6 nodes)** |
| density residual drop | 6.0 orders | 2.8 | 2.4 | 2.3 |

- **As written, SU2's pressure field is wrong**, and wrong the same way on two CFL paths (B1, B1b): the stagnation
  pressure overshoots along the whole leading edge, the suction peak is about 30 % too high, and the pressure drag
  comes out negative (a thrust), which a wing in steady subsonic flow cannot have. It is not SU2's force integration
  and not the face orientation: integrating SU2's own wall Cp by hand gives the same number (−65.7 against −65.5
  counts at iteration 500), and the wall's area vectors close to 6 × 10⁻¹⁶ in x and z
  (`tools/su2_surface_forces.py`).
- **The cause is the compressible Roe scheme at Mach 0.1.** B1c changes only `LOW_MACH_CORR= YES` (Rieper's
  correction for Roe at low Mach) against B1b: the overshoot is gone (largest Cp 1.03), the pressure drag is
  positive (+38.8 counts; by hand +38.6), and the Cp agrees with ADflow's along the span
  (`B1c_today_VVC_a4_lmc_su2_sa/su2_sa/cp_against_adflow_A1b.png`; B1b's is beside it in its folder). S8's SU2 report
  already said that the incompressible solver is the one for this regime ("AERIS flies at Mach 0.084 — effectively
  incompressible — so the INC_RANS cases are the ones in our regime"). The case files use `SOLVER= RANS` without it.
- **SU2 does not converge on this mesh** with the case's numerics, nor with either fix: 2.3 to 2.8 orders, the CFL
  still reset to 1 every few dozen iterations, the forces still drifting (B1c: CD −2 counts per 100 iterations at
  the end). So the remaining 42-count drag difference (29 pressure, 13 friction) is not a measurement of the codes;
  ADflow's 185.5 is a converged number, SU2's 143.6 is not.
- The two codes also run different SA variants: ADflow's default `useft2SA = True`, SU2's log says
  "Spalart-Allmaras-noft2".
- **For the case files (decision 76):** `case.py`'s SU2 configurations need the low-Mach correction (or `INC_RANS`),
  and more than 10 linear iterations; and SU2 still needs a convergence fix on these meshes (the slope limiter is
  the usual cause of such a stall; untested tonight: two tries per run).

**Q7, y⁺ on SU2 (design 1.3 at VVC).** B1c, the physical SU2 solution (not converged): wing-surface nodes largest
4.61, 99 % 3.91, median 1.39; 60 % above 1.3. B1 (the overshooting one): largest 4.82, 99 % 3.88, median 1.55. SU2 reports y⁺ at the first node off the wall, ADflow at the first cell centre, half as far, so
ADflow's median 0.74 corresponds to about 1.48 at the first node. **Both say the first cell is 7 to 14 % taller than
the y⁺ 1.3 design in the median (1.39 SU2, 1.48 ADflow), and up to 3.9 at the 99th percentile**: more at the nose
and on the tip cap, where the friction is highest.

**Q5, the wake against the fan: inside it at −5° and at +10°, with at least 0.067 c to spare.** On the station plane nearest mid semi-span (station 11,
y/s 0.481, local chord 0.941), the wake centre is the lowest velocity magnitude on vertical lines behind the trailing
edge (`solve/wake_check.py`). Heights are from the middle of the two trailing-edge corners, in local chords.

| α | d behind the TE | Wake centre | Band (the mesh's fan) | Wake angle | Margin to the nearest edge | Velocity deficit |
| --- | --- | --- | --- | --- | --- | --- |
| −5° (A4) | 0.25 c | −0.004 c | −0.073 to +0.097 c | −0.9° | 0.070 c | 36 % |
| −5° | 0.5 c | −0.007 c | −0.097 to +0.144 c | −0.8° | 0.090 c | 27 % |
| −5° | 1 c | −0.008 c | −0.143 to +0.237 c | −0.5° | 0.135 c | 18 % |
| −5° | 2 c | −0.038 c | −0.236 to +0.425 c | −1.1° | 0.198 c | 11 % |
| +10° (A5) | 0.25 c | +0.030 c | −0.073 to +0.097 c | 6.9° | 0.067 c | 32 % |
| +10° | 0.5 c | +0.048 c | −0.097 to +0.144 c | 5.5° | 0.095 c | 20 % |
| +10° | 1 c | +0.092 c | −0.143 to +0.237 c | 5.2° | 0.146 c | 11 % |
| +10° | 2 c | +0.223 c | −0.236 to +0.425 c | 6.4° | 0.202 c | 5 % |
| 4° (A1b, a test of the script) | 0.25 / 0.5 / 1 / 2 c | +0.015 / +0.030 / +0.052 / +0.092 c | | 3.5° / 3.4° / 3.0° / 2.6° | ≥ 0.08 c | 22 % at 0.5 c |

At −5° the wake does not follow the freestream: it leaves the trailing edge at about −1°, turned up by the upwash of
the negative lift (CL −0.45). It is inside the fan everywhere, at least 0.07 c from its edge. At +10° it leaves at 5 to 7°, held below the
freestream by the downwash of CL 0.63, at least 0.067 c below the fan's upper edge. At 4° it leaves at 3.5° and
bends down to 2.6°. **The fan's +10° edge is not reached at +10°** (decision 111): the closest the wake comes to an
edge is 0.067 c, at 0.25 c behind the trailing edge at +10°. One station only (y/s 0.48); the wake check reads any
station (`--y-frac`). Figures:
`A4_today_VVC_am5/adflow/wake_check.png`, `A5_today_VVC_a10/adflow/wake_check.png`, `A1b_today_VVC_a4_turbksp/adflow/wake_check_a4_test.png`.

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
5. **B2, try 1: killed by the watchdog**, as the plan's rule says. SU2 SST + LM with 30 linear iterations and the
   low-Mach correction grew to 11.96 GiB in 32 s; `MemAvailable` fell to 0.92 GiB, below the watchdog's 8 % of
   13.7 GiB, and the swap grew by 0.64 GiB. Command and the watchdog's line:

   ```
   timeout 150m mpiexec.hydra -np 6 SU2_CFD ../su2_sst_lm_lin30_lmc.cfg
   rss_watch: killed SU2_CFD (available 0.9 GiB < 8% of 13.7)
   ```

   SU2 caught the SIGTERM, saved its files and printed "Exit Success": exit 0 again. Try 2 (B2b) keeps the low-Mach
   correction and goes back to the case's 10 linear iterations (9.18 GiB).
6. **SU2 under Open MPI runs as separate copies.** Found in a test before any SU2 run. `SU2_CFD` 8.5.0 here is a
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
- A4 and A5: `ANKUseTurbDADI=false`, as A1b. Why: on the same mesh and solver, A1 showed that the case's
  turbulence update stalls and A1b that this one option converges; running A4 and A5 as written first would have
  cost two stalled runs.
- B1b, B1's first retry of two allowed: `su2_sa_lin30.cfg`, a copy of `su2_sa.cfg` with `LINEAR_SOLVER_ITER= 30`
  (was 10) and `LINSOL` added to `HISTORY_OUTPUT` (output only: the linear residual in the history). Why: B1's
  adaptive CFL collapsed (Q1). Cost: 1.9 GiB more (9.25 GiB) and about 5.5 s per iteration instead of 3.0 s.
- B1c, B1's second and last retry: `su2_sa_lin30_lmc.cfg`, B1b's file with `LOW_MACH_CORR= YES`. Why: the stagnation
  overshoot and the negative pressure drag (Q3). It removed both; it did not make SU2 converge.
- B2 (SST + LM), try 1: `su2_sst_lm_lin30_lmc.cfg`, the case file with `LINEAR_SOLVER_ITER= 30`, `LOW_MACH_CORR= YES`
  and `LINSOL` in the history: B1's two lessons applied at once (two changes; running the case file as written would
  have repeated B1's CFL collapse and B1's overshoot). Killed for memory (section 4).
- B2b, try 2: `su2_sst_lm_lmc.cfg`, the case file with `LOW_MACH_CORR= YES` and `LINSOL` only.

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
- **B1b was stopped at 15 min** (the stall above), and **B1's second try waits until after A4 and A5.** The plan's
  order is B1's tries, then A4, A5, B2. A4 and A5 (ADflow with A1b's option, about 31 min each) answer Q5 for
  certain; B1's second try may not converge, so it goes after them. B1c is B1b plus `LOW_MACH_CORR= YES` (Roe's
  low-Mach correction): it tests the pressure overshoot, the larger of B1's two problems for Q3.
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

- **No grid convergence.** Only VVC ran (one level), not VVC and VC: VC needs about 22 GiB for ADflow.
- **VVC is a preview level** (y⁺ 1.3 by design, wall-normal growth 1.34, past the hard minimums), and it measures
  above its own design (Q7).
- **One wing, one Re, one angle** for Q1–Q3 and Q7 (BWB reference wing 0, Re 3 × 10⁵, α 4°).
- **Q4 (the light rules) is not answered:** A2 and A3 do not fit 16 GB. The light rules also change three things at
  once, so even A2 against A3 would not say which one matters.
- **Memory and time from one mesh size**: the M and light-M numbers are extrapolations (Q2).
- **SU2 8.5.0, not 8.6.0**, and SA-noft2 against ADflow's SA with ft2.
- **LM on VVC under-resolves the bubbles** (about 7 cells per bubble), so B2's drag is not a transition answer.
