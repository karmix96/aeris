| Run | Mesh | Cells | Solver, model | α | Ranks | Wall time | Iterations | Residual drop | Verdict | Peak RAM (GiB) | GiB per M cells | CL | CD (counts) | CDp | CDv | CMy | y⁺ largest, 99 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1_attempt1_failed | today VVC | 1,075,074 | ADflow SA | 4° | 6 | 0.0 min |  |  | failed to start (exit 1; see REPORT.md section 4) |  |  |  |  |  |  |  |  |
| A1_today_VVC_a4 | today VVC | 1,075,074 | ADflow SA | 4° | 6 | 30.2 min | 182 | 4.21 | not accepted | 10.28 | 9.57 | 0.1906 | 185.5 | 0.00676 | 0.01178 | 0.00984 | 2.92, 1.92 |
| A1b_today_VVC_a4_turbksp | today VVC | 1,075,074 | ADflow SA | 4° | 6 | 31.2 min | 153 | 6.01 | not accepted | 10.99 | 10.22 | 0.1907 | 185.5 | 0.00676 | 0.01178 | 0.00984 | 2.92, 1.92 |
| A4_today_VVC_am5 | today VVC | 1,075,074 | ADflow SA | -5° | 6 | 63.8 min | 239 | 6.00 | not accepted | 10.99 | 10.23 | -0.4484 | 336.5 | 0.02421 | 0.00944 | 0.03344 |  |
| A5_today_VVC_a10 | today VVC | 1,075,074 | ADflow SA | 10° | 6 | 27.5 min | 136 | 6.02 | not accepted | 10.99 | 10.23 | 0.6253 | 416.9 | 0.03054 | 0.01115 | -0.01459 |  |
| B1_today_VVC_a4_su2_sa | today VVC | 1,075,074 | SU2 SA | 4° | 6 | 29.3 min | 582 | 2.83 | not accepted | 7.32 | 6.81 | 0.1883 | 67.7 | -0.00621 | 0.01298 | 0.01246 | 4.82, 3.88 |
| B1b_today_VVC_a4_lin30_su2_sa | today VVC | 1,075,074 | SU2 SA | 4° | 6 | 15.4 min | 117 | 2.07 | not accepted | 9.25 | 8.60 | 0.1980 | 65.9 | -0.00479 | 0.01138 | 0.00831 | 4.81, 3.85 |
| B1c_today_VVC_a4_lmc_su2_sa | today VVC | 1,075,074 | SU2 SA | 4° | 6 | 47.6 min | 436 | 2.16 | not accepted | 9.37 | 8.72 | 0.1982 | 143.6 | 0.00388 | 0.01048 | 0.00766 | 4.61, 3.91 |
| B2_attempt1_killed | today VVC | 1,075,074 | SU2 SST+LM | 4° | 6 | 0.7 min |  |  | killed by the watchdog at 32 s (available 0.9 GiB < 8% of 13.7) | 11.96 | 11.12 |  |  |  |  |  |  |
