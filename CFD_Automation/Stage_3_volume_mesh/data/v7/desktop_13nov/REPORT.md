# Desktop runs from 13 Nov 2026: what the mesh rules cost in the answer, the code gap, the measured case

Following `solve/DESKTOP_13NOV.md` in its order of worth (G1, M1, M2, E1, E2, M5, W1–W3, Q1–Q3, S1, S2, M3, M4, F1,
F2, G2, E3), with Mike's instruction of 13 Nov: E387 for SA + LM and SA-BCM both, on the recipe, after G1, M1, M2.
The machine: 16 GB (WSL 13.65 GiB), 6 cores, one run at a time, `solve/rss_watch.py` with every run, SU2 under
MPICH's `mpiexec.hydra`. Baseline for G and M: the night's A1b (today VVC: CL 0.1907, CD 185.5 counts, pressure
67.6, friction 117.8, CMy 0.00984), not rerun.

Status: step 0 done; G1 (accepted), M1, M2 done; E1 accepted (it corrects the SU2 study's stall verdicts); E2 accepted; queue B (section 0b) running since 23:10: M5, W1, W2 done (accepted), W3 running.

## 0. Step 0: DECISIONS O1 to O3 (Mike's yes, 13 Nov)

| Item | Commit | Change | Test (3 iterations, today VVC) |
| --- | --- | --- | --- |
| O1 | c5c8cdb2 | `case.py`: `"ANKUseTurbDADI": False` in the ADflow options | ADflow printed `'ANKUseTurbDADI': False` among its options |
| O2 | 882f07b7 | `run_adflow.py`: the three night fixes (rank-0 writer, the history keys, the lift-distribution and slice writer) | one `result.json` with all 6 ranks' memory and the history cl, cd, cdp, cdv, cmy, resrho, totalres; `lift_distribution.dat` and `slices.dat` written |
| O3 | edbbcf6d | `case.py`: the SU2 recipe (incompressible, FDS, Venkatakrishnan 0.05 frozen after 500 iterations, CFL capped at 50); Tu 0.07 % (decision 70); the V7 compressible template kept, unused | the SA file equals R1f's `inc_sa_recipe.cfg` line for line (comments aside); SA and SST + LM files ran 3 iterations; SA's first iterations equal R1f's (rms[P] −4.734098, CL 0.122551) |

Records: `step0/`. Since O1 every ADflow run has `ANKUseTurbDADI=False` from the case file, not from the command line.

## 0b. Three decisions, 13 Nov 22:30 (Mike: "I leave it up to you all 3 decisions. Implement them all")

1. **The 3-D transition runs are continued** from their restarts at their stops (R2 SA + LM VVC → R2c, R4 SST + LM →
   R4c, R6 SA + LM light VC → R6c), `LIMITER_ITER= 20` (a restart counts iterations from 0), otherwise unchanged;
   judged on the joined record (first leg + continuation: `monitor.py --prev-history`), stopped by the acceptance rule
   or by **the stall rule with a 4,000-iteration window** (`--stall-window 4000`). Why 4,000: on E1's record a
   500-iteration window fires at iteration 1,425, 2,000 at 3,809, 3,000 and 4,000 never; E1's plateau lasted 3,000.
2. **ADflow stops at `L2Convergence` 10⁻⁷ where runs are compared below a count**: M3, M4, M5, F1, F2, and M2b, a
   rerun of M2 as F's baseline at the same stop. W, Q and G2 keep the case file's 10⁻⁶. Why: M1 and M2 stopped at
   10⁻⁶ with CD still rising 0.4 to 0.6 counts per 30 iterations; F's budget is 0.3 counts.
3. **The rest of the plan is queued** (`tools/d13_queue_B.sh`) after E2, in this order: M5, W1–W3, Q1–Q3 (the plan's
   next by worth, about 3 hours), R2c (it decides the transition model), S1, S2, R4c, M3, M4, M2b, F1, F2, G2, R6c,
   E3. All meshes are built and match the plan's cell counts.

## 1. The run table

| Run | Mesh | Cells | Solver | Iterations | Residual drop | Verdict | Wall time | Peak RAM | CL | CD (counts) | Pressure | Friction | CMy | y⁺ median, 99 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1b (night, baseline) | today VVC | 1,075,074 | ADflow SA | 153 | 6.01 | converged | 31.2 min | 10.99 GiB | 0.1907 | 185.5 | 67.6 | 117.8 | 0.00984 | 1.48, 3.84 (× 2) |
| G1 | today VVC, `vis4=0.0078` | 1,075,074 | ADflow SA | 106 | 6.03 | **accepted** | 26.7 min | 10.99 GiB | 0.1910 | 176.9 | 63.0 | 113.8 | 0.00995 | 1.45, 4.09 (× 2) |
| M1 | tip gap only (`--tip-dpw`) | 738,612 | ADflow SA | 93 | 6.01 | not accepted: CL moved 0.14 % in the last 30 iterations (limit 0.1 %) | 15.6 min | 7.72 GiB | 0.1908 | 185.7 | 68.0 | 117.8 | 0.00979 | 1.45, 3.52 (× 2) |
| M2 | light (`--pack light`: tip gap, wall growth 1.28, station growth 1.25) | 700,654 | ADflow SA | 94 | 6.03 | not accepted: CD moved 0.56 counts in the last 30 iterations (rule label "oscillating"; in fact a monotonic creep, below) | 15.3 min | 7.38 GiB | 0.1908 | 186.9 | 68.6 | 118.3 | 0.00971 | 1.46, 3.54 (× 2) |
| M5 | band off (`--knobs band_off`) | 747,474 | ADflow SA, `L2Convergence` 10⁻⁷ | 200 | 7.01 | **accepted** | 37.6 min | 7.89 GiB | 0.1903 | 189.7 | 71.7 | 118.0 | 0.00966 | 1.58, 4.15 (× 2) |
| W1 | cranked 0, today VVC | 900,168 | ADflow SA | 156 | 6.00 | **accepted** | 35.7 min | 9.33 GiB | 0.6319 | 318.8 | 198.0 | 120.7 | −0.07430 | 1.55, 3.28 (× 2) |
| W2 | flying wing 0, today VVC | 940,974 | ADflow SA | 154 | 6.01 | **accepted** | 25.1 min | 9.72 GiB | 0.2997 | 190.6 | 71.6 | 119.0 | 0.02821 | 1.50, 3.75 (× 2) |
| E1 | E387 2-D, S8's O-grid | 147,496 points | SU2 SA + LM (recipe) | 7,827 | 6.15 | **accepted** | 37.0 min | 0.85 GiB | 0.5906 | 112.8 | 51.2 | 61.5 | CM −0.0776 (c/4) | |
| E2 | E387 2-D, S8's O-grid | 147,496 points | SU2 SA-BCM (recipe) | 13,077 | 6.08 | **accepted** | 51.1 min | 0.71 GiB | 0.5921 | 112.9 | 53.5 | 59.4 | CM −0.0781 (c/4) | |

## 2. The blocks

### G: is the 18-count ADflow-SU2 gap ADflow's own dissipation?

| | ADflow A1b (vis4 0.0156, the default) | ADflow G1 (vis4 0.0078) | G1 − A1b | SU2 R1f (the recipe) |
| --- | --- | --- | --- | --- |
| CL | 0.19065 | 0.19096 | +0.00031 (+0.16 %) | 0.19580 |
| CD (counts) | 185.49 | 176.86 | **−8.63** | 167.79 |
| pressure drag | 67.65 | 63.02 | −4.63 | 63.82 |
| friction drag | 117.84 | 113.84 | −4.00 | 103.97 |
| CMy | 0.00984 | 0.00995 | +0.00012 | 0.00702 |
| iterations, residual | 153, 9.76 × 10⁻⁷ | 106, 9.30 × 10⁻⁷ | | 4.83 orders |

**Half of the gap is ADflow's dissipation: halving vis4 takes 8.6 of the 17.7 counts away, all of the pressure part
(G1's pressure drag is 0.8 counts below SU2's) and 4.0 of the 13.9 counts of friction.** Friction stays 9.9 counts
(9.5 %) above SU2's, and the lift gap (SU2 2.5 % higher) does not move. S8 measured the same direction on its own
coarse level (−20.6 counts for the same halving). One mesh only: whether vis4 = 0.0078 is closer to the grid-converged
answer, or only to SU2, needs a finer level, which does not fit this machine for ADflow.

### M: what each light rule changes in the answer

Against A1b (today VVC, 1,075,074 cells), ADflow SA, α 4°. "Outer 10 %": the sum of ADflow's sectional lift over
η ≥ 0.9 (150 segments), and the largest difference in the normalised sectional lift there.

| Rule | Run | Cells saved | ΔCL | ΔCD (counts) | ΔCMy | Outer 10 % lift | Largest Δ normalised lift (where) | Cp at y/s 0.9–0.98 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tip gap 0.1 % (DPW) | M1 | 336,462 (31.3 %) | +0.07 % | +0.26 (p +0.32, f −0.06) | −0.00005 | +8.0 % | 0.093 at η 1.000 (A1b 0.010) | largest \|ΔCp\| 0.008 (upper, x/c 0.92, y/s 0.98) |
| all three (light) | M2 | 374,420 (34.8 %) | +0.07 % | +1.44 (p +0.95, f +0.49) | −0.00013 | +8.5 % | 0.093 at η 1.000 (A1b 0.010) | largest \|ΔCp\| 0.007 |
| wall + station growth (M2 − M1) | | 37,958 more (5.1 % of M1) | +0.00 % | +1.18 (p +0.63, f +0.55) | −0.00008 | +0.5 % | 0.003 at η 0.906 | |
| transition band off | M5 | 327,600 (30.5 %) | −0.17 % | **+4.21** (p +4.10, f +0.11) | −0.00018 | −0.46 % | 0.001 at η 1.000 | |

M1 converged (relative residual 9.7 × 10⁻⁷ in 93 iterations) but is not accepted by the rule: CL still moved 0.14 % in
its last 30 iterations and CD 0.43 counts (drift 0.39); ADflow stops on its residual (10⁻⁶, the case file's) before
the forces are flat to the rule. So M1's +0.26 counts are inside its own remaining drift: **the tip-gap rule saves 31 %
of the cells and moves neither the lift (0.07 %) nor the drag (under its 0.4-count drift); it changes the load on
the last segment at the tip** (the normalised sectional lift at η = 1 goes from 0.010 to about 0.10), which adds
8 % to the outer 10 % of the lift, with Cp at the tip slices unchanged to 0.008. `M1/m1_vs_a1b.png`, `.json`.

**M2: the light pack saves 35 % of the cells for about 1.4 counts of drag and nothing in the lift**; of it, the tip gap
is 31 of the 35 % and next to nothing in drag; the wall and station growth together add the 1.2 counts (pressure
+0.6, friction +0.55) for 5 % more cells saved. `M2/m2_vs_a1b.png`, `M2/m2_vs_m1.png`.

**M5: a fully turbulent answer needs the band.** Switching the transition band off (decision 81) saves 30.5 % of
the cells and costs **4.2 counts of drag, all of it pressure drag** (+4.10; friction +0.11), with lift −0.17 % and the
tip loading unchanged (outer 10 % −0.46 %). M5 ran to 10⁻⁷ (decision 2 of section 0b) and its forces were flat to
0.0003 counts, so the 4.2 counts are the mesh, not the stop. The band's chordwise refinement resolves the pressure
recovery the coarser spacing smears; whether band-on is the closer of the two to the grid-converged answer needs a
finer level, but its effect is larger than any light rule's (M1: under 0.4, M2: 1.4 counts).

**The limit of these differences: ADflow's 10⁻⁶ stop leaves M1's and M2's forces still creeping.** In their last 30
iterations CD rose in 29 of 29 steps, by 0.43 (M1) and 0.56 counts (M2), and CL by 0.13 and 0.20 %; the rule fails
them on that, and labels M2 "oscillating" because its range (0.56) exceeds 0.5 counts while its fitted drift (0.48)
does not: the label misfires on a monotonic creep (rule 4 as adopted; not changed here). A1b, on the today mesh,
was flat to 0.008 counts already at 10⁻⁵. So M1's +0.26 and M2's +1.44 counts are lower bounds by a few tenths,
and a difference below about 1 count is not resolved by a 10⁻⁶ stop on these meshes. For the far-field block (its
budget is 0.3 counts) that matters: those runs would need to run on until the forces are flat (one option,
`L2Convergence` 10⁻⁷), which the plan has at the case file's 10⁻⁶. For Mike.

### W: do ADflow and the mesh hold on the other three wing types?

ADflow SA, α 4°, Re 3 × 10⁵, today VVC, `ANKUseTurbDADI=False` from the case file, nothing else changed.
"Residual last": the largest 100 cells of ResDensity in the volume file (`tools/adflow_residual_where.py`).

| Wing | Cells | Verdict | Iterations | CL | CD (counts) | y⁺ median, 99 % (× 2) | Residual last (largest 100 cells hold) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BWB 0 (A1b, night) | 1,075,074 | converged | 153 | 0.1907 | 185.5 | 1.48, 3.84 | the tip near its trailing edge (42 %) |
| cranked 0 (W1) | 900,168 | **accepted** | 156 | 0.6319 | 318.8 | 1.55, 3.28 | the tip, y/s 1.0, x 0.32 to 0.99 (51 %) |
| flying wing 0 (W2) | 940,974 | **accepted** | 154 | 0.2997 | 190.6 | 1.50, 3.75 | the tip, y/s 1.0, x 2.06 to 2.62 (33 %) |

### E: Eppler 387 against McGhee (2-D)

Reference (NASA TM-4062, as S8 recorded it, `S8_oh_structured/reports/s8_su2_validation.json`): α 2.04° measured
(run at 2°, as S8), Re 2 × 10⁵, CL 0.574, CD 0.0118 (± 2.6 counts), CM −0.0794 about the quarter chord (nose down
negative), laminar separation at x/c 0.43, turbulent reattachment at 0.67 (oil flow, table III). Freestream turbulence:
S8's value, 0.1 %, the SU2 tutorial's, not a measured value for the tunnel. Grid: S8's (SU2's tutorial O-grid,
147,496 points). Mach 0.06 as S8, on the incompressible solver.

| | E1: SU2 SA + LM (recipe) | McGhee, TM-4062 | E1 − McGhee |
| --- | --- | --- | --- |
| verdict | **accepted**: 6.15 orders, momentum 5.5, transition equations 4.0 and 4.8 orders; CD within 0.14 counts and CL within 0.09 % over the last 1,565 iterations | | |
| CL | 0.5906 | 0.574 (at α 2.04°; the run is at 2.0°) | +0.017 (+2.9 %; about +3.7 % at matched α, the lift slope being about 0.11 per degree) |
| CD (counts) | 112.8 (pressure 51.2, friction 61.5) | 118 ± 2.6 | **−5.2**, twice the measurement uncertainty |
| CM about c/4 (nose down negative) | −0.0776 | −0.0794 | +0.0018 (2.3 % less nose down) |
| bubble, upper side | separation 0.463; reattachment 0.707 with gaps of up to 2 nodes bridged (length 0.244), 0.608 strictly contiguous (0.146) | 0.43 to 0.67 (0.240, oil flow) | separation 0.033 c late; length 0.244 against 0.240 (bridged) |

**SA + LM on the recipe converges on E387 and comes within 5 counts of the drag, 3 % of the lift and 2 % of the
moment, with a bubble of the measured length starting 0.03 c late.** S8's compressible runs of the same case never
converged (an 85-count swing over 40,000 iterations). The bubble's aft part, where the friction is near zero,
alternates in sign node to node, so its end is 0.61 (contiguous) or 0.71 (bridged); the measured 0.67 lies between.

**E2: SA-BCM on E387 is accepted too, and equals SA + LM there.** 6.08 orders in 13,077 iterations (momentum 5.3; CD
within 0.28 counts and CL within 0.02 % over the last 2,615); like E1 it passed through a long plateau first.

| | E1 SA + LM | E2 SA-BCM | McGhee |
| --- | --- | --- | --- |
| CL | 0.5906 | 0.5921 | 0.574 (α 2.04°) |
| CD (counts) | 112.8 | 112.7 (mean of the window) | 118 ± 2.6 |
| CM (c/4, nose down negative) | −0.0776 | −0.0781 | −0.0794 |
| separation | 0.463 | 0.459 | 0.43 |
| reattachment, bridged (contiguous) | 0.707 (0.608) | 0.725 (0.608) | 0.67 |

**Block E's answer: on the one measured case both SA-based transition models converge on the recipe and agree with
each other to 0.2 counts, 0.3 % in lift and 0.0005 in moment; both are 5 counts below McGhee's drag (twice its
uncertainty), about 3 % above in lift, 2 % short in moment, and separate 0.03 c late with a bubble of about the
measured length.** Neither oscillates in 2-D, so a swing is not built into either model on the recipe. In 3-D they
differed by about 10 counts on VVC (BCM 130.0, LM 137 to 143 while it ran): that difference belongs to the 3-D case,
or to LM's early stop; R2c tells which. E3 (SST + LM) is queued last.

**E1 corrects the SU2 study's verdict on SA + LM and SST + LM.** E1's residual stood still at 3.8 to 4.0 orders from
iteration 1,000 to 4,000 while its drag moved 104 → 121 → 113 counts, then fell to 6 orders by 7,000. The stall rule
of the SU2 study (no new low by 0.1 orders in 500 iterations, slower than 1 order per 1,000) would have stopped E1 at
iteration 1,425, at 3.9 orders and CD 104.5 counts, 8 counts away from its converged value; it did not only because
the first watch on E1 did not apply it. The 3-D transition runs were stopped by that rule at the same stage: R2 (SA +
LM, VVC) at 1,423, R6 (light VC) at 1,604, R4 (SST + LM) at 1,606 iterations. **So "SA + LM and SST + LM oscillate;
only SA-BCM converges" is not established: those runs may have been in the long transient E1 went through.** The
500-iteration stall window is too short for transition runs; their restarts are on disk (`runs/su2t_VVC_a4/R2_sa_lm/
restart.dat`, R4, R6), so they can be continued. For Mike.

### From files already on the desktop (plan section 3, no solver)

**ADflow's friction is higher than SU2's almost uniformly, by 12 to 15 %** (`section3/cf_adflow_vs_su2.png`,
`.json`; `tools/cf_compare.py`). Friction magnitude along the chord, ADflow A1b against SU2 R1f on the same today
VVC mesh, integrated over chord bands, ADflow / SU2:

| Station (SU2; ADflow's face strip) | upper, whole chord | lower, whole chord | range over the bands 0–5, 5–30, 30–70, 70–100 % |
| --- | --- | --- | --- |
| y/s 0.263 (0.284) | 1.137 | 1.141 | 1.12 to 1.23 |
| y/s 0.481 (0.503) | 1.120 | 1.153 | 1.11 to 1.18 |
| y/s 0.820 (0.839) | 1.129 | 1.152 | 1.10 to 1.19 |

The excess is a little larger at the nose (0–5 % of the chord: 1.12 to 1.23) and otherwise flat: an offset in the
whole turbulent wall layer, not one region. ADflow's friction is at its face centres and SU2's at its nodes, and
ADflow's strip sits half a station (0.02 s) outboard of SU2's station.

**ADflow's residual sits last at the tip, not at SU2's two leading-edge corners** (`section3/adflow_residual_A1b.txt`,
A1b's `ResDensity` per cell): the largest 100 of 1,075,074 cells hold 42 % of the sum of squares (the largest 10,
20 %), all at x ≈ 1.42, y = 3.0, z ≈ 0.14, on the tip near its trailing edge, where the tip vortex forms; none on
the symmetry plane, at the planform kink (y 1.575) or at the root nose, where SU2's sat (D1 of the SU2 study).

## 3. What failed

## 4. What this does not show

## Files
