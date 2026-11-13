# Desktop runs from 13 Nov 2026: what the mesh rules cost in the answer, the code gap, the measured case

For the Claude Code agent on Mike's desktop (16 GB, 6 cores, one run at a time). It follows the night run
(`data/v7/night_11nov/REPORT.md`) and the SU2 study (`data/v7/su2_transition/REPORT.md`). Stage 3's mesh rules are
not final (decision 114 is open), so these runs are there to give the rules evidence, not to produce data.
Every mesh is a what-if at VVC size: no rule file, nothing in `cfdauto/` or `configs/` changes.

## The questions

| Block | Question | Decides |
| --- | --- | --- |
| G | Is the 18-count ADflow against SU2 gap ADflow's own dissipation on a coarse mesh? | the solver split (76), DECISIONS O7 |
| M | What does each light rule change in the answer (the tip gap, the wall growth, the station growth)? What does the transition band change in a fully turbulent run? | decision 114; the band (81) |
| W | Do ADflow and the mesh hold on the other three wing types? | the claim "any wing" |
| Q | Do they hold at the four Re levels, and what y⁺ does the first cell get at each? | the first-cell rule |
| F | How much does the far-field distance move the forces (40, 80, 160 mean chords)? | the Stage 4 domain study, early |
| S | How far is VVC from VC in SU2 (one true family step), and is the code gap the same on a second mesh? | how much a coarse level can be trusted |
| E | On the one measured case (E387, McGhee), which transition model is right on the working numerics, and is the swing still there in 2-D? | the transition model (DECISIONS O4) |

Why G: S8 measured it already on its own meshes (`AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/policies/
s8_campaign_v1.yaml`, `settings_decision`): halving ADflow's `vis4` moved drag −20.6 counts on its coarse level and
−12.0 on its medium one. Why E: S8's E387 runs used the compressible solver and S8's own report says neither
converged (SA + LM swung over 84.7 counts with a mean 4.3 counts below the measurement; its bubble was 3.5 × too
short), so "SA + LM is validated on E387" does not stand yet.

## Hard rules (as the night run)

- Never `--open-holdouts`. Only the reference wings named here.
- No edits under `cfdauto/` or to `configs/*.yaml`.
- Git: never `git add -A` or `git commit -a`; add only named files; `git pull --ff-only` first; never commit meshes
  or solution files. Small files go to `data/v7/desktop_13nov/` and are committed from there.
- One run at a time, each with `solve/rss_watch.py`. A killed run stays in the record.
- SU2: MPICH's `mpiexec.hydra`; a restart path under 100 characters; the recipe of the SU2 study.
- ADflow: `ANKUseTurbDADI=false`; `L2Convergence` as in the case file (10⁻⁶: the far-field block compares runs to a
  few tenths of a count).
- Stop a run only by the stall rule of the SU2 study or the acceptance rule in `solve/read_results.py`.
- At most two option changes per run to make it work, each recorded. Never change a mesh to make a solver work.

## 0. First

1. `git pull --ff-only` (main at this file's commit or later).
2. DECISIONS O1 to O3, **only if Mike confirms them when he hands you this plan** (this session's advice is yes to
   all three): O1, put `"ANKUseTurbDADI": False` into the ADflow options of `solve/case.py`; O2, commit the three
   `solve/run_adflow.py` fixes; O3, for the numerics only, make the SU2 recipe `case.py`'s SU2 configuration (the
   incompressible solver, FDS, the limiter frozen after the start-up, the CFL capped at 50), keeping the old
   compressible text in the record. The transition models in `case.py` wait for block E. With O3, set
   `FREESTREAM_TURBULENCEINTENSITY` to 0.0007 (0.07 %, N_crit 9: the value similarity fixed in decision 70; the case
   files had 0.1 %). One commit per item, each tested with a 3-iteration run. Without Mike's yes, pass the options on
   the command line as before and leave `case.py` and `run_adflow.py` uncommitted.

## 1. The meshes (seconds each; all built here on the numpy loft, every check passed)

BWB reference wing 0, Re 3 × 10⁵, VVC unless said. `W="python scripts/whatif_mesh.py --formats cgns su2"`.

| Tag | Command (after `$W`) | Folder in `data/meshes/` | Cells | ADflow RAM (10.2 GiB per M, measured) |
| --- | --- | --- | --- | --- |
| today | `--pack today --level VVC --type bwb --index 0` | `whatif_today_VVC_e32d995a_re3e5` (exists) | 1,075,074 | 11.0 GiB (measured) |
| light | `--pack light --level VVC --type bwb --index 0` | `whatif_light_VVC_e32d995a_re3e5` | 700,654 | 7.2 |
| tip gap only | `--level VVC --type bwb --index 0 --tip-dpw` | `whatif_k-tipdpw_VVC_e32d995a_re3e5` | 738,612 | 7.5 |
| wall growth only | `--level VVC --type bwb --index 0 --knobs wall_g128` | `whatif_k-wall_g128_VVC_e32d995a_re3e5` | 1,036,894 | 10.6 |
| station growth only | `--level VVC --type bwb --index 0 --knobs span_g125` | `whatif_k-span_g125_VVC_e32d995a_re3e5` | 1,024,194 | 10.5 |
| band off | `--level VVC --type bwb --index 0 --knobs band_off` | `whatif_k-band_off_VVC_e32d995a_re3e5` | 747,474 | 7.6 |
| cranked 0 | `--pack today --level VVC --type cranked --index 0` | `whatif_today_VVC_16e322f1_re3e5` | 900,168 | 9.2 |
| flying wing 0 | `--pack today --level VVC --type flying_wing --index 0` | `whatif_today_VVC_1c2c23c5_re3e5` | 940,974 | 9.6 |
| tapered 0 | `--pack today --level VVC --type tapered --index 0` | `whatif_today_VVC_e60bb903_re3e5` | 899,886 | 9.2 |
| light, Re 10⁵ | `--pack light --level VVC --type bwb --index 0 --re 1e5` | `whatif_light_VVC_e32d995a_re1e5` | 559,578 | 5.7 |
| light, Re 10⁶ | `... --re 1e6` | `whatif_light_VVC_e32d995a_re1e6` | 714,990 | 7.3 |
| light, Re 4 × 10⁶ | `... --re 4e6` | `whatif_light_VVC_e32d995a_re4e6` | 772,334 | 7.9 |
| light, far field 40 | `--level VVC --type bwb --index 0 --knobs wall_g128 span_g125 far_40 --tip-dpw` | `whatif_k-wall_g128-span_g125-far_40-tipdpw_VVC_e32d995a_re3e5` | 611,640 | 6.3 |
| light, far field 160 | `... far_160 --tip-dpw` | `whatif_k-wall_g128-span_g125-far_160-tipdpw_VVC_e32d995a_re3e5` | 774,010 | 7.9 |
| light VC | `--pack light --level VC --type bwb --index 0` | `whatif_light_VC_e32d995a_re3e5` (exists) | 1,475,376 | too large for ADflow; SU2 SA about 9.8 GiB |

`--knobs wall_g128 span_g125 --tip-dpw` is the light pack spelled out, so the two far-field meshes differ from
"light" only in the far field. The tip gap is nearly all of the light saving here: tip gap only 738,612 cells,
all three rules 700,654. `python scripts/whatif_mesh.py --list-knobs` lists every rule that can be changed.

## 2. The runs, in this order

ADflow SA, α 4°, Mach 0.1, 6 ranks, `--set-option ANKUseTurbDADI=false` (or the new default), with
`--lift-distribution 150 --slices 0.5,0.8,0.9,0.95,0.98`. By the night's 29 min per million cells each takes 16 to
35 minutes. The baseline for G and M is the night's **A1b** (today VVC: CL 0.1907, CD 185.5 counts, pressure 67.6,
friction 117.8, CMy 0.00984); do not rerun it.

| # | Run | Mesh | One change from | Reads |
| --- | --- | --- | --- | --- |
| 1 | G1 | today | A1b: `--set-option vis4=0.0078` (half) | Does CD fall toward SU2's 167.8? Which part moves, pressure or friction? |
| 2 | M1 | tip gap only | A1b: the mesh | ΔCL, ΔCD, ΔCMy; the lift over the outer 10 % of the semi-span; Cp at 0.9, 0.95, 0.98 |
| 3 | M2 | light | A1b: the mesh | the same; M2 against M1 is the wall and station growth together |
| 4 | M3 | wall growth only | A1b: the mesh | the same |
| 5 | M4 | station growth only | A1b: the mesh | the same |
| 6 | M5 | band off | A1b: the mesh | does a fully turbulent answer need the band? |
| 7–9 | W1–W3 | cranked 0, flying wing 0, tapered 0 | the wing | converged? iterations, y⁺, where the residual sits last |
| 10–12 | Q1–Q3 | light at Re 10⁵, 10⁶, 4 × 10⁶ (with M2 at 3 × 10⁵) | the Re (`case.py --re`) | converged? y⁺ median and 99 % against the design 1.3, by zone |
| 13–14 | F1, F2 | light with far field 40 and 160 | M2: the far field | CL, CD, CMy against M2 (80): the domain error; the Stage 0 budget for it is 0.3 counts |
| 15 | G2 | today | A1b: `--set-option "discretization=central plus matrix dissipation"` | one try; S8 could not converge it. If it stalls, record and stop |

Then SU2 SA on the recipe (`data/v7/su2_transition/inc_sa_recipe.cfg`, the mesh path changed), watched by
`tools/monitor.py`:

| # | Run | Mesh | Reads |
| --- | --- | --- | --- |
| 16 | S1 | light VVC | against M2: the code gap on a second mesh (CL, CD, pressure, friction) |
| 17 | S2 | light VC (about 9.8 GiB) | against S1: one true family step (every spacing ÷ 1.3): how much the forces move |

Then the measured case, 2-D, on the recipe (S8's E387 grid and reference: `AERIS_MESH_STUDY/04_strategy_studies/
S8_oh_structured/runs/su2_validation/e387_sa_lm/` and `docs/SU2_REPORT_2026-09-18.md`, section 5.2: α 2°,
Re 2 × 10⁵, McGhee NASA TM-4062, CD ± 2.6 counts, bubble 0.240 c long):

| # | Run | Model | Reads |
| --- | --- | --- | --- |
| 18 | E1 | SA + LM | accepted, or oscillating with which band? CL, CD, CM against the measurement; the bubble's start, end and length against the oil flow |
| 19 | E2 | SA-BCM | the same |
| 20 | E3 | SST + LM (if time) | the same |

E387's freestream turbulence: S8's value for that tunnel; say which. If a model oscillates in 2-D on the recipe,
the swing is in the model or the flow, not in our 3-D mesh.

If time is short, the order of worth is: G1, M1, M2, E1, E2, M5, W1–W3, Q1–Q3, S1, S2, M3, M4, F1, F2, G2, E3.

## 3. Also from files already on the desktop (no solver)

- **Cf along the chord** at y/s 0.26, 0.48, 0.82: ADflow A1b against SU2 R1f, upper and lower side, one figure. Is
  ADflow's friction higher everywhere by about 12 %, or only in a region?
- **Where ADflow's residual sits last** on A1b (if its volume file holds the residual): the same two leading-edge
  corners as SU2's (the root on the symmetry plane and the planform kink at y/s 0.525), or elsewhere?

## 4. The report

`data/v7/desktop_13nov/REPORT.md`, rewritten after every run, with `summary.json` and one folder of small files per
run, as the night folder. In this order:

1. The run table: run, mesh, cells, solver, iterations, residual drop, verdict, wall time, peak RAM, CL, CD
   (counts), pressure, friction, CMy, y⁺ median and 99 %.
2. One table per block with the differences against its baseline, then one sentence that answers the block's
   question, with the number. For M: a table "rule, cells saved (%), ΔCL (%), ΔCD (counts), ΔCMy, the largest
   difference in the lift over the outer 10 % of the semi-span".
3. What failed, each with its command and error. Every option changed.
4. What this does not show (one wing for G, M, F, S; VVC is past the hard minimums; fully turbulent only except E).

Commit and push after every finished run, as in `NIGHT_11NOV.md` section 7, with `data/v7/desktop_13nov` in place
of the night folder.
