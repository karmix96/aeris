# Desktop runs from 13 Nov 2026: what the mesh rules cost in the answer, the code gap, the measured case

Following `solve/DESKTOP_13NOV.md` in its order of worth (G1, M1, M2, E1, E2, M5, W1–W3, Q1–Q3, S1, S2, M3, M4, F1,
F2, G2, E3), with Mike's instruction of 13 Nov: E387 for SA + LM and SA-BCM both, on the recipe, after G1, M1, M2.
The machine: 16 GB (WSL 13.65 GiB), 6 cores, one run at a time, `solve/rss_watch.py` with every run, SU2 under
MPICH's `mpiexec.hydra`. Baseline for G and M: the night's A1b (today VVC: CL 0.1907, CD 185.5 counts, pressure
67.6, friction 117.8, CMy 0.00984), not rerun.

Status: step 0 done; G1 done (accepted); M1 running since 21:02; M2, then E1, E2 queued.

## 0. Step 0: DECISIONS O1 to O3 (Mike's yes, 13 Nov)

| Item | Commit | Change | Test (3 iterations, today VVC) |
| --- | --- | --- | --- |
| O1 | c5c8cdb2 | `case.py`: `"ANKUseTurbDADI": False` in the ADflow options | ADflow printed `'ANKUseTurbDADI': False` among its options |
| O2 | 882f07b7 | `run_adflow.py`: the three night fixes (rank-0 writer, the history keys, the lift-distribution and slice writer) | one `result.json` with all 6 ranks' memory and the history cl, cd, cdp, cdv, cmy, resrho, totalres; `lift_distribution.dat` and `slices.dat` written |
| O3 | edbbcf6d | `case.py`: the SU2 recipe (incompressible, FDS, Venkatakrishnan 0.05 frozen after 500 iterations, CFL capped at 50); Tu 0.07 % (decision 70); the V7 compressible template kept, unused | the SA file equals R1f's `inc_sa_recipe.cfg` line for line (comments aside); SA and SST + LM files ran 3 iterations; SA's first iterations equal R1f's (rms[P] −4.734098, CL 0.122551) |

Records: `step0/`. Since O1 every ADflow run has `ANKUseTurbDADI=False` from the case file, not from the command line.

## 1. The run table

| Run | Mesh | Cells | Solver | Iterations | Residual drop | Verdict | Wall time | Peak RAM | CL | CD (counts) | Pressure | Friction | CMy | y⁺ median, 99 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1b (night, baseline) | today VVC | 1,075,074 | ADflow SA | 153 | 6.01 | converged | 31.2 min | 10.99 GiB | 0.1907 | 185.5 | 67.6 | 117.8 | 0.00984 | 1.48, 3.84 (× 2) |
| G1 | today VVC, `vis4=0.0078` | 1,075,074 | ADflow SA | 106 | 6.03 | **accepted** | 26.7 min | 10.99 GiB | 0.1910 | 176.9 | 63.0 | 113.8 | 0.00995 | 1.45, 4.09 (× 2) |

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

### E: Eppler 387 against McGhee (2-D)

Reference (NASA TM-4062, as S8 recorded it, `S8_oh_structured/reports/s8_su2_validation.json`): α 2.04° measured
(run at 2°, as S8), Re 2 × 10⁵, CL 0.574, CD 0.0118 (± 2.6 counts), CM −0.0794 about the quarter chord (nose down
negative), laminar separation at x/c 0.43, turbulent reattachment at 0.67 (oil flow, table III). Freestream turbulence:
S8's value, 0.1 %, the SU2 tutorial's, not a measured value for the tunnel. Grid: S8's (SU2's tutorial O-grid,
147,496 points). Mach 0.06 as S8, on the incompressible solver.

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
