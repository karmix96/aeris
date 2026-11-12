# V7 night run, 11–12 Nov 2026: the first solves on Stage 3 meshes

Claude Code, alone on Mike's desktop, following `solve/NIGHT_11NOV.md`. This file is rewritten after every finished
run. Last update: 12 Nov, 04:50 (every run done but B2b, SU2 SST + LM, running since 04:18; it stops by 06:30).

One wing: BWB reference wing 0, Re 3 × 10⁵ on the mean chord, Mach 0.1, the transition band on. One mesh level ran:
today's VVC (1,075,074 cells). This desktop has 16 GB, not 48–52 GB, and VC does not fit.

## In brief

- **ADflow converges on the Stage 3 mesh, with one option changed.** As written, the SA residual stalls (A1). With
  `ANKUseTurbDADI: False` the relative residual reaches 10⁻⁶ in 136 to 239 iterations at −5°, 4° and +10°
  (A1b, A4, A5), 31 min at 4°: **29 min per million cells on 6 ranks**.
- **SU2 8.5.0 reads the `.su2` mesh but does not converge** with the case's numerics or with the fixes tried
  (2.1 to 2.8 orders). As written its compressible Roe scheme at Mach 0.1 overshoots the stagnation pressure
  (wall Cp to 2.3, isentropic 1.0025) and gives a negative pressure drag. **`LOW_MACH_CORR= YES` removes both**, and
  then SU2's Cp agrees with ADflow's (Q3).
- **The wake stays inside the fan at −5° and at +10°**, at least 0.067 local chords from its edges (Q5, decision 111).
- **Memory at VVC: ADflow 9.6 to 10.2 GiB per million cells** (S8's ANK-only law within 5 %), SU2 6.8 to 8.7. The M
  level (9.5 M cells) needs 70 to 97 GiB for ADflow, so not 48 GB; the light M (5.5 M) 45 to 56 GiB (Q2).
- **The first cell is 7 to 14 % taller than the y⁺ 1.3 design** in the median, more at the nose and on the tip cap
  (Q7).
- **The pyGeo meshes are the numpy meshes**: 20 of 20, nodes 4 × 10⁻¹¹ apart (Q6).
- **Q4 is not answered**: A2 and A3 (VC and light VC) do not fit 16 GB.
- **The acceptance rule cannot accept a converged ADflow run here.** It needs at least 225 iterations to judge
  "settled", and then judges the start-up; ADflow converged in 136 to 239. The rule is unchanged (section 2).
- **Three faults in `solve/run_adflow.py` found and fixed** (every rank wrote the records; the force history was
  lost; ADflow 2.13.1's lift-distribution writer has a bug). The fixes are in this checkout, not committed:
  `tools/run_adflow_night_fixes.patch`.

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

The host has 16 GB and 6 cores, so the plan's two lines could not run side by side. Every run went alone, in the
plan's order, except B1's second try, which went after A4 and A5 (section 7).

## 2. The runs

All on 6 ranks, one at a time. `run_table.md` is the same table built from the run folders by `tools/collect.py`;
every number is read from the copied files. Wall times are on the monotonic clock. y⁺ is over the wing surface
(upper, lower, nose), without the trailing-edge base and the tip cap; SU2's is at the first node off the wall,
ADflow's at the first cell centre (Q7).

| Run | Solver, model, change from the case file | α | Wall time | Iterations | Residual drop (orders) | Verdict of `read_results.py` | Peak RAM (GiB) | GiB per M cells | CL | CD (counts) | CDp | CDv | CMy | y⁺ largest, 99 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1, attempt 1 | ADflow SA, as written | 4° | 0 | 0 | | failed to start (4.1) | | | | | | | | |
| A1 | ADflow SA, as written | 4° | 30.2 min | 182 | 4.21 | not accepted: not converged (stopped, section 7) | 10.28 | 9.57 | 0.1906 | 185.5 | 0.00676 | 0.01178 | 0.00984 | 2.92, 1.92 |
| A1b | ADflow SA, `ANKUseTurbDADI=false` | 4° | 31.2 min | 153 | 6.01 | not accepted: "no force history in result.json" (4.3); with it, 153 iterations would be too short; **converged**, 9.76 × 10⁻⁷ | 10.99 | 10.22 | 0.1907 | 185.5 | 0.00676 | 0.01178 | 0.00984 | 2.92, 1.92 |
| A4 | ADflow SA, `ANKUseTurbDADI=false` | −5° | 63.8 min | 239 | 6.00 | not accepted: forces not settled; **converged**, 9.99 × 10⁻⁷ | 10.99 | 10.23 | −0.4484 | 336.5 | 0.02421 | 0.00944 | 0.03344 | |
| A5 | ADflow SA, `ANKUseTurbDADI=false` | +10° | 27.5 min | 136 | 6.02 | not accepted: too short to judge; **converged**, 9.65 × 10⁻⁷ | 10.99 | 10.23 | 0.6253 | 416.9 | 0.03054 | 0.01115 | −0.01459 | |
| B1 | SU2 SA, as written | 4° | 29.3 min | 582 | 2.83 | not accepted: not converged, forces not settled (stopped) | 7.32 | 6.81 | 0.1883 | 67.7 | −0.00621 | 0.01298 | 0.01246 | 4.82, 3.88 |
| B1b | SU2 SA, `LINEAR_SOLVER_ITER= 30` | 4° | 15.4 min | 117 | 2.07 | not accepted: not converged (stopped) | 9.25 | 8.60 | 0.1980 | 65.9 | −0.00479 | 0.01138 | 0.00831 | 4.81, 3.85 |
| B1c | SU2 SA, 30 linear iterations + `LOW_MACH_CORR= YES` | 4° | 47.6 min | 436 | 2.16 | not accepted: not converged (stopped) | 9.37 | 8.72 | 0.1982 | 143.6 | 0.00388 | 0.01048 | 0.00766 | 4.61, 3.91 |
| B2, try 1 | SU2 SST + LM, 30 linear iterations + low-Mach correction | 4° | 0.7 min | 3 | | **killed by the watchdog** at 32 s (4.5) | ≥ 11.96 | ≥ 11.1 | | | | | | |
| B2b, try 2 | SU2 SST + LM, low-Mach correction | 4° | running since 04:18 | | | | 9.18 | 8.54 | | | | | | |

**The acceptance rule and ADflow.** `read_results.py` judges "settled" over the last 20 % of the record, at least
200 iterations, and needs 25 more before it judges at all: 225. A1b (153 iterations) and A5 (136) are too short.
A4 (239) is long enough, and its window (iterations 40 to 239) holds the start-up: CD moved 14.1 counts in it. From
ADflow's own logs (`adflow/history_from_log.json`), the forces of the converged runs were settled well inside the
rule's 0.5 counts and 0.1 %:

| Run | Since iteration | CD moved (counts) | CL moved |
| --- | --- | --- | --- |
| A1b | 100 | 0.010 | 0.008 % |
| A4 | 189 (the last 50) | 0.12 | 0.044 % |
| A5 | 100 | 0.088 | 0.023 % |
| A1 (not converged) | 100 | 0.042 | 0.009 % |

So for a converged ADflow run here the rule either cannot judge or judges the start-up. The rule is unchanged; a
window of the last 20 % without the 200-iteration minimum would judge these runs. That is Mike's decision.

## 3. The answers

### Q1. Do ADflow and SU2 read our meshes and converge on them?

**ADflow: yes, with one option.** It reads the CGNS, finds the families `wall`, `farfield` and `symmetry`, and builds
the freestream exactly (velocity and lift direction errors 0.0).

- As written (A1) it does not converge. The relative residual fell 4.2 orders in 182 iterations, at 0.0026 orders per
  iteration and slower every 30 iterations. Between iterations 50 and 170 the density residual fell 2.3 orders and
  the SA residual only from 2.1 × 10⁻⁶ to 8.5 × 10⁻⁷. With the case's settings ADflow updates the turbulence by one
  DADI sweep per ANK step, and never switches to its coupled or second-order modes (both tolerances default to
  10⁻¹⁶).
- With `ANKUseTurbDADI=false` (the turbulence by its own Krylov solve) it converges: A1b in 153 iterations, A4 in 239,
  A5 in 136. A1b's SA residual was 3.6 × 10⁻⁸ at iteration 29 and 1.8 × 10⁻¹⁰ at 150. Its forces equal A1's to four
  digits (CL 0.19065 against 0.19064; CD 185.49 against 185.47 counts).
- For `case.py`: `"ANKUseTurbDADI": False` in the ADflow options. It costs 0.7 GiB on VVC (6.8 %) and 22 % more time
  per iteration (12.2 s against 10.0 s), and removes the stall.

**SU2: it reads the mesh, but does not converge on it.** SU2 8.5.0 reads the `.su2` file (1,107,836 points,
1,075,074 hexahedra), partitions it on 6 ranks (38,022 edge cuts) and accepts every option of both case files.

- As written (B1) the adaptive CFL collapses. SU2 cuts it by 10 whenever the linear solver misses the accepted
  linear residual (10⁻³) in its 10 iterations, and doubles it otherwise, so it cycled between 1 and 86. In 582
  iterations the density residual fell 2.8 orders; the momentum residual stalled at 10⁻⁷·³ from iteration 120.
- With 30 linear iterations (B1b) the linear solves converge (10⁻⁴ at CFL 30 to 500) and the CFL reached 419 by
  iteration 25, but the density residual then stayed at 10⁻⁸·¹ and the CFL was still reset every few dozen
  iterations. So the stall is in the nonlinear iteration. The usual cause is the slope limiter
  (`VENKAT_LIMITER_COEFF= 0.05`); it was not tested, as B1's two tries went to the CFL and to the pressure field.
- With the low-Mach correction as well (B1c): 2.2 orders in 436 iterations, the CFL still reset to 1 at times, CD
  still moving 0.8 counts per 100 iterations at the end.
- SST + LM (B2b): see the run table; running.

### Q2. How much memory and time per million cells, really?

**ADflow memory: one mesh size, and S8's law holds.**

| | Cells | Peak (GiB, 6 ranks) | GiB per M cells | S8 law, ANK only | S8 law, ANK then NK |
| --- | --- | --- | --- | --- | --- |
| A1, as written | 1,075,074 | 10.28 | 9.57 | 10.46 (+1.7 %) | 11.68 |
| A1b, A4, A5: turbulence by Krylov | 1,075,074 | 10.99 | 10.22 | 10.46 (−4.8 %) | 11.68 |

The largest rank held 1.81 GiB (A1) and 1.93 GiB (A1b). The watchdog's sampled peaks agree to 0.01 GiB. WSL never
swapped (0.022 GiB at most). The host paged up to 2.1 GiB into its pagefile and Windows went down to 0.41 GiB free
(A5); nothing slowed or failed.

**What that gives for M and the light M (decision 113).** One mesh size cannot give the plan's straight line
`GiB = a + b × M cells`. Two bounds instead: all memory proportional to the cells (an upper bound: some of it is
fixed), and S8's fixed part (2.69 GiB, the ANK-only law) with tonight's slope.

| Run | GiB per M cells | M, 9.5 M cells | light M, 5.5 M cells |
| --- | --- | --- | --- |
| ADflow, as written (A1) | 9.57 | 70–91 GiB | 42–53 GiB |
| ADflow, `ANKUseTurbDADI=false` (A1b) | 10.22 | 76–97 GiB | 45–56 GiB |
| SU2 SA, as written (B1) | 6.81 | 44–65 GiB | 26–37 GiB |
| SU2 SA, 30 linear iterations (B1b) | 8.60 | 61–82 GiB | 36–47 GiB |
| SU2 SA, 30 linear iterations + low-Mach correction (B1c) | 8.71 | 62–83 GiB | 37–48 GiB |
| SU2 SST + LM, low-Mach correction (B2b) | 8.54 | 60–81 GiB | 36–47 GiB |
| SU2 SST + LM, 30 linear iterations (B2 try 1, killed: a lower bound) | ≥ 11.1 | ≥ 85 GiB | ≥ 50 GiB |
| S8's laws (ANK only; ANK then NK) | | 71; 91 GiB | 43; 54 GiB |

On 48 GB, ADflow's M does not fit by either bound, and the light M fits only by the lower bound, without margin.
SU2 SA as written fits the light M; with 30 linear iterations it needs 37 to 48 GiB for it. SST + LM costs 25 % more
than SA at the same settings (9.18 against 7.32 GiB). These are extrapolations from 1.08 M cells: the second point
(VC, 2.3 M cells) needs a machine with more than 16 GB.

**ADflow time.** A1b converged in 31.2 min on 6 ranks: **29.0 min per million cells** (S8's law: 35.7). A4 at −5°
took 63.8 min and A5 at +10° 27.5 min. Linear in the cells, M is about 4.6 h and the light M 2.7 h on 6 ranks (more
in practice: the iterations grow with the cells). A1 averaged 10.0 s per iteration and A1b 12.2 s; the later
iterations were slower as the linear solves grew (A1: from 20 to 33 inner iterations per step).

**SU2 time.** No SU2 run converged, so there is no time to converge. Per iteration on 6 ranks: SA 3.0 s as written,
about 8 s with 30 linear iterations (B1b) and 6.5 s with the low-Mach correction too (B1c); SST + LM 4.3 s (B2b).

### Q3. Do ADflow SA and SU2 SA agree on one grid?

**In Cp, yes, once SU2 has the low-Mach correction. In drag it stays open: SU2 does not converge here.**

| | ADflow SA (A1b, converged) | SU2 SA as written (B1, 582 it.) | + 30 linear iterations (B1b, 117 it.) | + low-Mach correction (B1c, 436 it.) |
| --- | --- | --- | --- | --- |
| CL | 0.1907 | 0.1883 | 0.1980 | 0.1982 (+3.9 %) |
| CD (counts) | 185.5 | 67.7 | 65.9 | 143.6 (−41.9) |
| CDp (counts) | 67.6 | −62.1 | −47.9 | +38.8 (−28.8) |
| CDv (counts) | 117.8 | 129.8 | 113.8 | 104.8 (−13.0) |
| CMy | 0.00984 | 0.01246 | 0.00831 | 0.00766 (−0.0022) |
| largest wall Cp (isentropic: 1.0025) | 1.17 (20 cells, all at the nose) | 2.25 (195 nodes, all at x/c ≤ 0.004) | 2.26 (192 nodes) | **1.03 (6 nodes)** |
| density residual drop | 6.0 orders | 2.8 | 2.1 | 2.2 |

- **As written, SU2's pressure field is wrong**, the same way on two CFL paths (B1, B1b). The stagnation pressure
  overshoots along the whole leading edge, the suction peak at mid-span is about 30 % higher than ADflow's, and the
  pressure drag comes out negative (a thrust), which a wing in steady subsonic flow cannot have (the induced drag
  alone is about +21 counts).
- **It is not SU2's force integration and not the face orientation.** Integrating SU2's own wall Cp over its quads by
  hand gives the same pressure drag (−65.7 against SU2's −65.5 counts at iteration 500), and the wall's area vectors
  close to 6 × 10⁻¹⁶ of the area in x and z (`tools/su2_surface_forces.py`).
- **It is the compressible Roe scheme at Mach 0.1.** B1c differs from B1b only by `LOW_MACH_CORR= YES` (Rieper's
  low-Mach correction for Roe). The overshoot is gone (largest Cp 1.03), the pressure drag is positive (+38.8 counts;
  by hand +38.6), and the Cp agrees with ADflow's along the span (`B1c_today_VVC_a4_lmc_su2_sa/su2_sa/
  cp_against_adflow_A1b.png`; B1's and B1b's are in their folders). S8's SU2 report already said the incompressible
  solver is the one for this regime ("AERIS flies at Mach 0.084 — effectively incompressible — so the INC_RANS cases
  are the ones in our regime"). The case files use `SOLVER= RANS` without a low-Mach treatment.
- **The 42-count drag difference that remains is not a measurement of the codes**: ADflow's 185.5 is converged,
  SU2's 143.6 is not (2.2 orders, still drifting).
- The two codes also run different SA variants: ADflow's default `useft2SA = True`, SU2's log says
  "Spalart-Allmaras-noft2".
- **For `case.py`'s SU2 configurations (decision 76):** a low-Mach treatment (`LOW_MACH_CORR= YES`, or `INC_RANS`),
  more than 10 linear iterations, and a convergence fix still to be found (the slope limiter first).

### Q4. How much do the light rules change the answer at VC?

**Not answered: A2 and A3 do not fit this machine.** The plan's rule for A2: A1's measured peak scaled by the cells
must be below 80 % of `MemAvailable` (12.6 GiB, so 10.1 GiB). A2: 10.28 × 2,324,016 / 1,075,074 = 22.2 GiB. A3:
10.28 × 1,475,376 / 1,075,074 = 14.1 GiB, more than all of WSL's 13.65 GiB. X1 (SU2 on VC) and X2 (ADflow on VC
with fill 0) are on the same 2.3 M-cell mesh, so they were not run either. The tip tools for A2 against A3 are ready
and tested on A1b: `--lift-distribution` and `--slices` now work (4.4), and `tools/plot_lift_cp.py` draws them
(`A1b_today_VVC_a4_turbksp/adflow_extras/lift_and_cp.png`).

### Q5. Does the wake stay inside the mesh's wake fan at −5° and +10°?

**Yes, at both, with at least 0.067 local chords to spare.** On the station plane nearest mid semi-span (station 11,
y/s 0.481, local chord 0.941), the wake centre is the lowest velocity magnitude on vertical lines behind the
trailing edge (`solve/wake_check.py`, written tonight). Heights are from the middle of the two trailing-edge
corners, in local chords.

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
| 4° (A1b, the script's test) | 0.25 / 0.5 / 1 / 2 c | +0.015 / +0.030 / +0.052 / +0.092 c | | 3.5° / 3.4° / 3.0° / 2.6° | ≥ 0.08 c | 22 % at 0.5 c |

At −5° the wake does not follow the freestream: it leaves the trailing edge at about −1°, turned up by the upwash of
the negative lift (CL −0.45). At +10° it leaves at 5 to 7°, held below the freestream by the downwash of CL 0.63.
**The fan's +10° edge is not reached at +10°** (decision 111): the closest the wake comes to an edge is 0.067 c, at
0.25 c behind the trailing edge at +10°. One station only; the script reads any (`--y-frac`). Figures:
`A4_today_VVC_am5/adflow/wake_check.png`, `A5_today_VVC_a10/adflow/wake_check.png`.

### Q6. Are the meshes on the pyGeo loft the same as on the numpy loft?

**Yes.** 20 of 20 reference meshes (VC, Re 3 × 10⁵) are the same on both lofts and pass on both. The largest node
difference is 4.2 × 10⁻¹¹ mean chords in the volume and 4.6 × 10⁻¹⁴ on the surface
(`data/studies/pygeo_mesh_check.json`, 8 min 41 s). The three meshes of step 2 have exactly the plan's cell counts on
pyGeo (1,075,074; 2,324,016; 1,475,376), and the what-if path gives today's VC to 5.0 × 10⁻¹²
(`--check-production`).

### Q7. What y⁺ does the first cell really get?

**About 7 to 14 % above the design y⁺ 1.3 of VVC in the median, more at the nose and on the tip cap.** SU2 reports y⁺
at the first node off the wall; ADflow at the first cell centre, half as far, so ADflow's numbers double to compare.

| | Largest | 99 % | Median | Above 1.3 |
| --- | --- | --- | --- | --- |
| SU2, B1c (physical pressure field, not converged), wing-surface nodes | 4.61 | 3.91 | 1.39 | 60 % |
| ADflow, A1b (converged), wing-surface faces, ×2 | 5.83 | 3.84 | 1.48 | |
| ADflow, A1b, as reported (cell centre) | 2.92 | 1.92 | 0.74 | 10.6 % above 1.3 |

ADflow by zone (as reported, cell centre):

| Zone | Largest | 99 % | Median | Faces above 1.3 |
| --- | --- | --- | --- | --- |
| upper side | 2.92 | 1.83 | 0.74 | 9.5 % |
| lower side | 2.73 | 1.83 | 0.72 | 9.0 % |
| nose | 2.92 | 2.66 | 1.27 | 48 % |
| tip cap | 3.76 | 3.08 | 1.62 | 99.8 % |
| trailing-edge base | 9.54 | 8.67 | 2.12 | 67 % |

The nose (where the friction peaks) and the tip cap are the zones above the rest. The base is a separated region;
its y⁺ is not a wall-resolution measure. The largest SU2 value sits at the tip (y/s 1.0).

## 4. What failed

1. **A1, attempt 1: the plan's command does not start.** `--set-option timeLimit=10800` reaches ADflow as an int,
   and ADflow refuses it:

   ```
   mpirun -np 6 python solve/run_adflow.py --case runs/n11_today_VVC_a4 --set-option timeLimit=10800 \
       --lift-distribution 150 --slices 0.5,0.8,0.9,0.95,0.98
   Error: Datatype for option timeLimit is not valid. Expected data type <class 'float'>.
   Received data type is <class 'int'>.
   ```

   Fix: `timeLimit=10800.0`, the same value. The error comes before the first iteration.
2. **`run_adflow.py` wrote its records from every rank.** The preflight's `preflight.json` came out with two stray
   bytes after rank 0's record, so it did not parse, and five of the six printed records said `"ranks": 1`.
   `result.json` is written the same way, so a non-root rank could have left its own memory as the run's. Fixed
   before A1's solve: one writer, rank 0.
3. **`run_adflow.py` kept no force history.** ADflow's history keys are its CGNS monitor names (`CoefLift`,
   `CoefDrag`, `CoefPressureDrag`, `CoefViscousDrag`, `CoefMomentY`, `RSDMassRMS`, `totalR`); the filter knew only
   `cl`, `cd`, ... and kept nothing, so `read_results.py` said "no force history in result.json" for A1 and A1b.
   Fixed after A1: the names are mapped. A4 and A5 have their history (`cl`, `cd`, `cdp`, `cdv`, `cmy`, `resrho`,
   `totalres`, `iter`). For A1 and A1b the history is read from ADflow's log (`tools/adflow_log_history.py`).
4. **`--lift-distribution` and `--slices` failed on ADflow** (A1 and A1b; new on 11 Nov):
   `ValueError: invalid literal for int() with base 10: 'allSurfaces'`, in `result.json["extras"]`. It is ADflow
   2.13.1's own bug: `writeLiftDistributionFile` and `writeSlicesFile` pass the group name `"allSurfaces"` where
   `tecplotio.writetecplot` needs the family list; `writeSolution` does it right. Fixed the way `writeSolution` does
   it, and tested at 00:57 on a zero-iteration restart of A1b: both files were written, and the restart's forces equal
   A1b's to every printed digit. The solves were not affected.
5. **B2, try 1: killed by the watchdog**, as the plan's rule says. SU2 SST + LM with 30 linear iterations grew to
   11.96 GiB in 32 s; `MemAvailable` fell to 0.92 GiB, below the watchdog's 8 % of 13.7 GiB, and the swap grew by
   0.64 GiB:

   ```
   timeout 150m mpiexec.hydra -np 6 SU2_CFD ../su2_sst_lm_lin30_lmc.cfg
   rss_watch: killed SU2_CFD (available 0.9 GiB < 8% of 13.7)
   ```

   SU2 caught the SIGTERM, saved its files and printed "Exit Success": exit 0. Try 2 (B2b) went back to the case's 10
   linear iterations (9.18 GiB).
6. **SU2 under Open MPI runs as separate copies.** Found in a test before any SU2 run: `SU2_CFD` 8.5.0 here is a
   static MPICH build. Under the MACH-Aero `mpirun` (Open MPI), `-np 2` printed two banners, did no partitioning and
   exited 0. Under MPICH's `mpiexec.hydra` it printed one banner and partitioned with ParMETIS. S8's SU2 runs show
   the two-banner signature (`runs/su2_validation/e387_sa_lm/run.log`), so they ran as two serial copies.
7. **Exit codes said nothing.** B1, B1b, B1c and the killed B2 all exited 0 (SU2 saves and exits on SIGTERM), and
   A1 exited 0 after SIGUSR2. Every verdict here is from the records, never from an exit code.

## 5. Every solver option changed from the case files

- `timeLimit` as a float (4.1), the same value.
- **A1b** (A1's first try of two): `ANKUseTurbDADI=false`. Why: A1's SA residual stalled. It worked.
- **A4, A5**: `ANKUseTurbDADI=false`, as A1b. Why: on the same mesh and solver A1 showed the stall and A1b the fix;
  running A4 and A5 as written first would have cost two stalled runs.
- **B1b** (B1's first try): `su2_sa_lin30.cfg`, the case file with `LINEAR_SOLVER_ITER= 30` (was 10) and `LINSOL` in
  `HISTORY_OUTPUT` (output only: the linear residual in the history). Why: B1's adaptive CFL collapsed. Cost:
  1.9 GiB.
- **B1c** (B1's second and last try): `su2_sa_lin30_lmc.cfg`, B1b's file with `LOW_MACH_CORR= YES`. Why: the
  stagnation overshoot and the negative pressure drag. It removed both; it did not make SU2 converge.
- **B2, try 1**: `su2_sst_lm_lin30_lmc.cfg`, the case file with `LINEAR_SOLVER_ITER= 30`, `LOW_MACH_CORR= YES` and
  `LINSOL`: B1's two lessons at once, two changes (as written it would have repeated B1's CFL collapse and B1's
  overshoot). Killed for memory.
- **B2b, try 2**: `su2_sst_lm_lmc.cfg`, the case file with `LOW_MACH_CORR= YES` and `LINSOL`.

Each changed `.cfg` is in its run folder here, with a comment line at the top that says what changed and why.

## 6. What this does not show

- **No grid convergence.** One level (VVC) only; VC needs about 22 GiB for ADflow.
- **VVC is a preview level** (y⁺ 1.3 by design, wall-normal growth 1.34, past the hard minimums), and it measures
  above its own y⁺ design (Q7).
- **One wing, one Re, one angle** for Q1–Q3 and Q7 (BWB reference wing 0, Re 3 × 10⁵, α 4°); one station for Q5.
- **Q4 is not answered.** The light rules also change three things at once, so even A2 against A3 would not say
  which one matters.
- **Memory and time from one mesh size**: the M and light-M numbers are extrapolations (Q2).
- **No converged SU2 solution**, so no SU2 drag to compare and no SU2 time to converge. SU2 8.5.0, not 8.6.0, and
  SA-noft2 against ADflow's SA with ft2.
- **LM on VVC under-resolves the bubbles** (about 7 cells per bubble), so B2b's drag is not a transition answer.

## 7. Choices made tonight

- **One run at a time**: fewer than 12 physical cores, and RAM for one ADflow VVC run only.
- **Stops before the caps.** The plan's caps (A1, B1, A4, A5 and B2 alone add up to 12 h) do not fit the night on
  this machine, so a run that had shown, by measurement, that it could not converge in its cap was stopped and kept
  in the record: A1 at 30 min (residual decay falling every 30 iterations: 0.0048, 0.0044, 0.0036, 0.0029 orders per
  iteration), B1 at 29 min, B1b at 15 min, B1c at 48 min. ADflow was stopped with SIGUSR2, its own "write and quit"
  (it does not catch SIGTERM), so `result.json` and the solution files were written as at a normal end. SU2 8.5.0
  catches SIGTERM and writes all its files ("Interrupt signal (15) received, saving files and exiting").
- **B1's second try went after A4 and A5.** A4 and A5 (ADflow with A1b's option) answered Q5 for certain; B1's second
  try might not converge, so it waited.
- **SU2 runs would end at the plan's acceptance rule** (`tools/su2_accept_stop.py`, applying `read_results.py`'s own
  code): the case files stop SU2 only at an absolute density residual of 10⁻¹² or the budget. No SU2 run met the
  rule, so it never acted.
- **A host-side memory log with every run** (`tools/host_watch.py`): Windows free memory, pagefile and the WSL VM's
  size every 60 s. WSL cannot see the host paging, so `rss_watch.py` cannot either. It stops a run only if the host
  pagefile nears full (2.5 GiB over its start, about 4.5 of the 5 GiB). My first rule (2 GiB over the start) would
  have killed A1 at its third sample, while WSL's swap stayed at 0.001 GiB; it was replaced at 23:53, before it
  acted. It never acted.
- **A hard stop at the cap + 30 min** around each ADflow run, as a safety net. It never acted.
- **The run wrappers** (`tools/run_adflow_night.sh`, `tools/run_su2_night.sh`) run the plan's commands with the
  plan's watchdog, the host log and `timing.json`. From 00:22 they time on the monotonic clock: the WSL clock stepped
  by about 90 s three times tonight (one `date` read 92 s ahead at 23:53; A5's preflight logged 02:54 and its solve
  02:52; SU2 printed a negative iteration time at 03:23).
- **Light work ran beside the solves** (copying, git, this report). Nothing that reads a volume file ran beside an
  ADflow solve: its memory margin was below 2 GiB.

## 8. Files

- This folder: `REPORT.md`, `summary.json` (every number, by run), `run_table.md`, one folder per run with its small
  files, the step-1 and step-2 records (`pygeo_mesh_check_*.txt`, `v5_export_printout.txt`,
  `r2_v5_export_pygeo.json`, `whatif_*_printout.txt`), and `tools/`.
- `solve/wake_check.py` (new, committed) and `data/studies/pygeo_mesh_check.json` (committed).
- **Not committed:** `solve/run_adflow.py` with the three fixes (the plan names only this folder):
  `git apply data/v7/night_11nov/tools/run_adflow_night_fixes.patch` on a clean checkout, or keep this checkout's copy.
  The solutions and meshes stay in `runs/` and `data/meshes/` (1.6 GB, ignored by git); ADflow's volume files for
  A4 and A5 are `runs/n11_today_VVC_am5/adflow/v7_a-5_000_vol.cgns` and `runs/n11_today_VVC_a10/adflow/v7_a10_000_vol.cgns`.
- The 1,622 deleted files the plan mentions are not in this checkout: it was clean at the start, and only
  `solve/run_adflow.py` is changed now.
