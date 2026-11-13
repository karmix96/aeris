# SU2 on the Stage 3 mesh, and which transition model works: 12 Nov 2026

Asked by Mike on 12 Nov, after the V7 night run (`../night_11nov/REPORT.md`): "make SU2 work. Find the transition model
that works in our cases. Remove the time limiter, just monitor the convergence."

Case: BWB reference wing 0, today's VVC mesh (`whatif_today_VVC_e32d995a_re3e5`, 1,075,074 cells), Re 3 × 10⁵ on the
mean chord, Mach 0.1, α 4°: the case of the night's A1b (ADflow SA, converged: CL 0.1907, CD 185.5 counts) and of
B1–B2b (SU2, none converged). SU2 8.5.0, 6 ranks under MPICH's `mpiexec.hydra`.

Status at 07:35 on 13 Nov: SU2 converges (R1f, SA, accepted); the acceptance rule changed (below); R2 (SA + LM) running

## Why these runs, in this order

The night's four SU2 tries all used SU2's compressible solver (Roe) and stalled at 2.1 to 2.8 orders. S8's SU2 work
(`AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/docs/SU2_REPORT_2026-09-18.md`) holds two facts that set the
order here:

- Its verified low-speed cases (TMR NACA 0012 to 0.9 % on CL and 0.2 % on friction drag; the flat plates to under 1 %)
  run on SU2's **incompressible** solver, FDS scheme, **no flow limiter**. The compressible E387 tutorial case (Roe,
  Venkatakrishnan 0.05, like our case files) never converged in 40,181 iterations.
- On E387 at Re 2 × 10⁵ (laminar separation bubble, measured by McGhee), **SA + LM** came within the measurement
  uncertainty on drag and produced a bubble in the measured region; **SST + LM** produced no bubble, came out 37
  counts high and diverged. Our case files use SST + LM.

| Run | What it is | One change from | The question | The decision it changes |
| --- | --- | --- | --- | --- |
| R1 | SA, incompressible solver, S8's incompressible numerics | the case file `su2_sa.cfg` (the solver path, taken with its limiter setting as S8 verified them) | Does SU2 converge on our mesh at all? | SU2's base configuration for `case.py`; whether a transition run can mean anything |
| R2 | SA + LM | R1 (`KIND_TRANS_MODEL= LM`) | Does S8's best transition model converge here, and where does it put transition? | The transition model for SU2 runs |
| R3 | SA + BCM (algebraic intermittency, no extra equations) | R1 (`SA_OPTIONS= BCM`) | Does the cheaper model converge, and does it agree with R2? | The fallback if LM does not converge |
| R4 | SST + LM | R2 (SA → SST) | The case file's model on the solver that works | Whether `su2_sst_lm` stays in `case.py` |

No time limit. Each run is watched by `tools/monitor.py`: it stops a run only when `solve/read_results.py`'s rule
holds (6 orders of the residual and settled forces), with that file's own code. A stall is judged by hand, from the
record, and written down here. `solve/rss_watch.py` runs with every solve.

**The stall rule, fixed at 08:45 before it was applied to any run:** a run is stopped as stalled when, over its last
500 iterations, the residual set no new minimum (by 0.1 orders) and its rate fitted over those 500 iterations is
slower than 1 order per 1,000 iterations. A run that keeps converging, however slowly, runs on.

## Start-up tests (3 iterations each)

Before any long run: does SU2 8.5.0 accept the transition models on the incompressible solver, on this mesh?
(`startup_tests/`, R1's file with `ITER= 3` and the model lines.)

| Test | SU2's own line | Seconds per iteration | Peak memory (6 ranks) |
| --- | --- | --- | --- |
| SA + LM | "Transition model: Langtry and Menter's 4 equation model (2009)", "Spalart-Allmaras-noft2" | 3.1 | 6.04 GiB |
| SA-BCM | "Turbulence model: Spalart-Allmaras-noft2-BCM" | 2.4 | 5.31 GiB |

Both log "Angle of attack (deg): 4, computed using the initial velocity" and "Reynolds number per meter: 300000".
For comparison, the night's compressible SST + LM peaked at 9.38 GiB.

## Runs

| Run | Setup | Iterations | Wall time | Outcome | Peak memory |
| --- | --- | --- | --- | --- | --- |
| R1 | SA, incompressible, no flow limiter, the case file's adaptive CFL (1 to 1,000) | 64 | 4.2 min | **diverged** (section "What failed") | 6.98 GiB |
| R1b | R1 + the case file's limiter (Venkatakrishnan 0.05) | 1,150 | 62.8 min | **stable; forces settled, residual 3.45 orders and slowing**; stopped at 09:13 on Mike's choice, continued as R1c | 7.14 GiB |

**R1b, the incompressible solver with the case file's numerics, is stable where the compressible one stalled.** The
pressure residual fell 1.7 orders in 166 iterations, then slowed (rate fitted over 200 iterations: 10.5, 3.2, 1.5,
0.8 orders per 1,000 at iterations 166, 364, 556, 1,120). The cause is the CFL control, not the linear solver: SU2's
adaptive CFL doubles each iteration and is cut by 10 when the residual flip-flops; with the limiter the pressure
residual swings ±0.3 orders between iterations, so the CFL spent long stretches at its floor of 1 (iterations 170 to
230 and 270 to 330, with the linear solves converging in 3 iterations; median CFL 1.1 over iterations 165 to 365).
The forces settled long before the residual: from iteration 923 the rule's force window holds (CD within 0.5 counts,
CL within 0.1 %), and over its last 500 iterations CD moved 0.88 counts.

At 1,120 iterations it was 3.2 orders down at under 1 order per 1,000 iterations, about 3 hours from the 6-order
target. Mike chose to stop it and continue from its state at a fixed CFL (R1c), one change, measured against R1b's
own rate from the same state.

R1b against ADflow's converged SA on the same mesh (the night's A1b), not yet a converged comparison:

| | SU2 R1b (3.45 orders) | ADflow A1b (6 orders) | SU2 − ADflow |
| --- | --- | --- | --- |
| CL | 0.1958 | 0.1907 | +2.7 % |
| CD (counts) | 167.9 | 185.5 | −17.6 |
| pressure drag | 63.8 (by hand from the wall Cp: 63.6) | 67.6 | −3.8 |
| friction drag | 104.0 | 117.8 | −13.8 (−12 %) |
| CMy | 0.0070 | 0.0098 | −0.0028 |
| y⁺ median, wing surface | 1.38 (first node) | 1.48 (first cell centre × 2) | |

The friction gap is the night's too: the compressible B1c had 104.8 counts. The two codes run different SA forms
(SU2: "Spalart-Allmaras-noft2"; ADflow: with ft2) and store the wall differently (SU2 at the nodes, ADflow at the cell
centres); which of these makes the 12 % is not measured here.

| Run | Setup | Iterations | Wall time | Outcome | Peak memory |
| --- | --- | --- | --- | --- | --- |
| R1c | R1b continued from its state at a fixed CFL of 25 (one change) | 597 (after R1b's 1,150) | 39.9 min | **stalled by the rule** at its iteration 590; stopped 10:00 | 7.14 GiB |
| D1 | diagnostic: 3 iterations from R1c's state writing every point's residual and limiter | 3 | 0.6 min | `D1_residual_map/residual_map.json` | |

**R1c: the CFL was not the brake.** At a fixed CFL of 25 (the linear solves reached −4.3 in their 10 iterations)
the pressure residual went from −8.20 to −8.42 in 597 iterations, best −8.47, at 4.0 s per iteration; R1b's was
falling 0.8 orders per 1,000 iterations at the same state with its CFL at 1. The stall rule, applied to the whole
record (R1b + R1c, 1,741 iterations): the best of the last 500 iterations, −8.465, was 0.096 orders below the best
before them (−8.369), short of the rule's 0.1, at −0.06 orders per 1,000 iterations. The new-minimum half was close;
the rate half was not. The forces did not move: CD 167.79 counts, within 0.075 counts over the last 500 iterations;
CL 0.19581.

**D1: the residual that holds is on about 100 points, at two leading-edge corners.** Of the pressure residual's sum
of squares, the largest 0.1 % of the points (1,107) hold 98.9 %, the largest 100 points 90 %, the largest 10 41 %.
Those 10 are on the symmetry plane at the root leading edge (y = 0; x −0.002 to 0.16, on the stagnation point and
just above the nose) and at x 0.79 to 0.81, y = 1.575, just above the leading edge (x 0.777) of the planform kink
there: the leading-edge sweep changes from 25° to 15° (slope 0.466 to 0.268), and the spanwise station spacing
changes with it. The momentum and turbulence residuals are smaller in their own terms and sit elsewhere: in the wake
just behind the root (station y = 0.131, x 5 to 8) and in the tip vortex 25 to 66 chords downstream, where it leaves
through the far-field boundary. The limiter acts (value below 0.99) at 12 to 22 % of all points and at 19 to 30 % of
the largest-residual ones: not much more often, so "the limiter acts there" does not explain it; a limiter that
switches between iterations at a corner would, and that is what R1d tests.

| Run | Setup | Iterations | Wall time | Outcome | Peak memory |
| --- | --- | --- | --- | --- | --- |
| R1d | R1c continued with the limiter frozen after 20 iterations (`LIMITER_ITER= 20`, one change) | 189 | 11.9 min | **the plateau is the limiter**: −8.34 to −9.37 in the 40 iterations after the freeze, then smooth at 0.8 orders per 1,000; stopped 10:23 to test the adaptive CFL (R1e) | 7.1 GiB |

**R1d: freezing the limiter removes the plateau.** Until iteration 20 (limiter still updated) the pressure
residual moved as in R1c (−8.44 to −8.34). Once frozen it fell to −9.37 by iteration 60, an order in 40 iterations,
and then went on falling smoothly, without the iteration-to-iteration swings: −9.47 at 188, 4.74 orders below the
record's start. The momentum residuals fell smoothly too (rms[U] −7.32 to −7.46). The forces did not move (CL
0.19580 to 0.19581, CD 167.78 to 167.79 counts). So R1b and R1c were held by the limiter switching at the two
leading-edge corners, and R1b's adaptive CFL sat at its floor because of the same swings.

| Run | Setup | Iterations | Wall time | Outcome | Peak memory |
| --- | --- | --- | --- | --- | --- |
| R1e | R1d continued with the case file's adaptive CFL back (1 to 1,000; limiter frozen after 20 iterations; one change) | 148 | 8.4 min | **the adaptive CFL cycles on the linear solver**: momentum faster, pressure residual noisy at −9.3; stopped 10:34 | 7.13 GiB |

**R1e: with 10 linear iterations SU2 cannot hold a CFL above about 50.** The CFL doubled each iteration to 100 to
220, the linear solve then missed its target (LinSolRes −3.1 to −3.8 after 10 iterations, against −4.0 to −4.4 at
CFL 25 to 55) and the CFL was cut by 10: 23 cuts in 100 iterations, a cycle of three doublings and a cut, and a reset
to 1 at iteration 100. The higher mean CFL sped the momentum residual (rms[U] 1.6 orders per 1,000 iterations
against R1d's 0.7) but each cut kicked the pressure residual (−9.20 to −8.83 in 4 iterations at 62 to 66), which
gained nothing in 100 iterations.

**The recipe, from these measurements** (R1f tests it from the freestream, before any transition run):
incompressible solver, FDS, MUSCL, Venkatakrishnan 0.05 **frozen after the start-up** (`LIMITER_ITER= 500`),
adaptive CFL from 1 **capped at 50** (`CFL_ADAPT_PARAM= ( 0.1, 2.0, 1.0, 50 )`), the case file's linear solver.

| Run | Setup | Iterations | Wall time | Outcome | Peak memory |
| --- | --- | --- | --- | --- | --- |
| R1f | SA, the recipe, from the freestream | 1,133 | 80 min | killed at 11:57 on 12 Nov with everything else in WSL (below) at 4.69 orders | 7.14 GiB |
| R1f-cont | R1f continued from its restart at iteration 1,000 (`LIMITER_ITER= 20`: a restart counts from 0) | 266 | 18.6 min | **accepted** under the adopted rule (whole record); stopped 07:27 on 13 Nov | 7.14 GiB |

**R1f: the recipe converges SU2 from the freestream, without hand-steering.** The CFL sat at its cap of 50 with no
cuts after the start-up (5 in the first 100 iterations). The pressure residual fell 1.8 orders by iteration 99, 3.3
by 500 (the freeze), 4.1 by 702, 4.7 by 1,132, with no plateau; it ran ahead of R1b at every iteration (−7.08
against −6.55 at 200). CL reached its final value by iteration 400 and CD was within 0.5 counts of it by 400.

**WSL shut down at 11:57:54 on 12 Nov.** Every process received SIGTERM at once (SU2's six ranks logged "Interrupt
signal (15)"); the watchdogs died before writing their records. Memory was not the cause: SU2 at 7.14 GiB with 5.6
GiB available and no swap at the last sample. The WSL kernel was 6.18.54 before and 6.18.58 after, so a WSL or
Windows update most likely restarted the Linux VM. SU2's save on SIGTERM did not finish; its last restart was the
regular one at iteration 1,000, from which R1f-cont continued at 07:09 on 13 Nov.

**The SU2 SA answer on the VVC mesh (R1f + R1f-cont, 4.83 orders, accepted): CL 0.19580, CD 167.79 counts, CMy
0.00702.** The hand-steered chain R1b to R1e gave the same to 0.02 counts.

## The acceptance rule, changed on 13 Nov (Mike's decision)

The rule of the V7 plan (6 orders; forces settled over the last 20 % with at least 200 iterations) was replaced in
`solve/read_results.py`, after the evidence below, by a Fluent/CFX good-practice analogue:

1. continuity residual at least 4 orders down (SU2 rms[P] or rms[Rho]; ADflow relative total residual 10⁻⁴);
2. every momentum residual at least 2 orders down; turbulence and transition residuals not rising;
3. forces flat over the last 20 % of the record, at least 30 iterations: CD within 0.5 counts, CL within 0.1 %,
   CMy within 0.0005, and no drift (fitted CD drift over the window, carried over one more, under 0.5 counts);
4. forces that swing without drifting never pass: labelled oscillating, mean and band reported.

Why 4 orders: on R1f, CD was 9.5 counts from its final value at 2 orders, 0.46 at 3, 0.18 at 3.5, **0.07 at 4**, 0.02
at 4.5; ADflow A1, stopped at 4.2 orders, had CD within 0.02 counts of its 6-order value. The momentum residuals
fall about half as far as the continuity one (2.4 orders when it reached 4), so a per-equation 3-order test, as
Fluent's default, would reject converged runs. The 30-iteration minimum: with 100, ADflow's converged runs (137 to 240
iterations) fail because their window still holds the start-up.

The new rule applied to every run so far (`tools/accept_v2.py`, `accept_v2_applied.json`): accepted are ADflow A1,
A1b, A4, A5 and SU2 R1d, R1e, R1f (whole records); not accepted are every compressible SU2 run of the night (B1, B1b,
B1c, B2b: 2.1 to 2.8 orders, momentum under 1.2, B2b's turbulence residuals rising), R1 (diverged), R1b and R1c
(3.45 and 3.7 orders, forces already final to 0.05 counts: the rule is conservative there). The run monitor
(`tools/monitor.py`) uses the same code.

## The transition runs

Queue (`queue.sh`, detached, one run at a time, no time limit): R2 SA + LM, R3 SA-BCM, R4 SST + LM, each one change
from R1f's recipe. R2 started 07:29 on 13 Nov.

## What failed

1. **R1 diverged in its start-up.** The momentum residual rose from the start (rms[U] −4.8 at iteration 2, −2.2 at
   34) while the adaptive CFL cycled between 1 and about 100 (cut by 10 whenever the 10 linear iterations missed
   their target, doubled otherwise). CL was already 3.3 at iteration 6 and 6.8 at 37. From iteration 41 the solution
   grew without bound (CL −4 × 10¹⁶ at 64) as the CFL reached its ceiling of 1,000, and SU2 stopped after iteration
   64 with exit 1 and no message:

   ```
   mpiexec.hydra -np 6 SU2_CFD case.cfg          (runs/su2t_VVC_a4/R1_inc_sa; case.cfg = inc_sa.cfg)
   |          64|    3.740103|  3.6852e+00|    5.410215|    1.013491|-42902992559444944.000000|19132498271273272.000000|
   exit 1
   ```

   R1 was not S8's verified incompressible set throughout: S8's NACA 0012 ran at a fixed CFL of 25, and R1 kept the
   case file's adaptive CFL up to 1,000 with no limiter. The next run (R1b) puts the case file's limiter back, one
   change; a fixed CFL is the other candidate.
2. **R1c, attempt 1: SU2 aborted while loading R1b's restart**, on all six ranks, 12 s after the start:

   ```
   mpiexec.hydra -np 6 SU2_CFD case.cfg      (SOLUTION_FILENAME= /home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/runs/su2t_VVC_a4/R1b_inc_sa_venk/restart.dat)
   Initialize Jacobian structure (SA model).
   *** buffer overflow detected ***: terminated        (six times; exit 134)
   ```

   The path was 101 characters. With the same restart copied into the run folder as `r1b_restart.dat`, attempt 2
   loaded it and started at R1b's last forces (CL 0.19583, CD 167.89 counts). SU2 8.5.0's binary restart reader
   appears to hold the file name in a 100-character buffer: **a restart path must stay under 100 characters.** The
   mesh path (111 characters) is read by other code and works.

## Files
