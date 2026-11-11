# The night run of 11–12 Nov 2026: the first solves on Stage 3 meshes (V7)

For a Claude Code agent on Mike's desktop, working alone (Mike is asleep). Take the most reasonable reading, write
every choice down, keep every failure in the record with its exact command and error. Measure, don't guess.
The solver commands are explained in `RUNBOOK.md` (same folder); this file says what to run tonight, in which
order, and what to send back.

## What tonight answers

No solver has run on a Stage 3 mesh yet. One wing: **BWB reference wing 0, Re 3 × 10⁵ on the mean chord, Mach 0.1,
the transition band on.**

| # | Question | Serves |
| --- | --- | --- |
| Q1 | Do ADflow and SU2 read our meshes and converge on them? | V7 |
| Q2 | How much memory and time per million cells, really (ADflow and SU2)? | decision 113 (where M runs), the Stage 4 budget |
| Q3 | Do ADflow SA and SU2 SA agree on one grid? | decision 76 (the solver split) |
| Q4 | How much do the light rules change the answer at VC, at the tip above all? | decision 114 (open) |
| Q5 | Does the wake stay inside the mesh's wake fan at −5° and +10°? | decision 111 |
| Q6 | Are the meshes on the pyGeo loft the same as on the numpy loft they were checked on? | the weak point of 11 Nov |
| Q7 | What y⁺ does the first cell really get? | the wall rule (y⁺ 1 at VC) |

## Hard rules

- **Never pass `--open-holdouts`.** Use only BWB reference wing 0 (and the 20 reference wings in step 1).
- **Do not edit** anything under `CFD_Automation/cfdauto/`, nor `configs/surface.yaml` or `configs/volume.yaml`. The
  light rules exist only as what-if copies (`scripts/whatif_mesh.py`). Do not change the acceptance rule in
  `solve/read_results.py`.
- **Git:** never `git add -A` or `git commit -a` (1,622 files show as deleted in this checkout; leave them alone).
  Add only the files and folders this plan names. Never commit `.cgns`, `.su2`, `.npz`, `.vtu`, `.plt`, restart,
  volume or surface solution files, or anything in `runs/` or `data/meshes/`: the small files of step 6 are copied
  into the night folder and committed from there.
- **Memory:** every solve runs with the watchdog `solve/rss_watch.py` (it kills a run before the machine runs out of
  memory; on WSL an out-of-memory can take the whole session down). If a run swaps, it is killed: record it.
- **Solver options:** run the case files as written first. To make a run work you may change solver options, at most
  two tries per run, each one recorded (ADflow: `--set-option`; SU2: a copy of the `.cfg` with a new name). Never
  change the mesh to make a solver work: if a solver cannot read a mesh or reports bad cells, record it exactly and
  go on to the next run.
- **Time:** stop starting new runs at 06:00 local time. By 07:30 the report is complete and pushed.

## 0. Set up and record the machine (about 30 min)

```bash
cd <the aeris repo>
git checkout main && git pull --ff-only
conda activate <repo>/.venv                     # a conda env (pyGeo 1.17.0, pySpline 1.5.4)
pip install -e CFD_Automation                   # only if cfdauto is missing or older than this checkout
cd CFD_Automation/Stage_3_volume_mesh
python -m pytest -q                             # 45 tests
```

Find and record (into the report, section "Machine"):

- **ADflow:** the MACH-Aero env (the S8 runbook used `/home/mike/miniconda3/envs/mach-aero`). Set
  `P=<that env>/bin` and check `$P/python -c "import adflow, baseclasses; print(adflow.__file__)"`.
- **SU2:** `which SU2_CFD`; the version it prints when it starts (8.6.0 expected); which MPI it was built with
  (`ldd $(which SU2_CFD) | grep -i mpi`): use the `mpirun` of that MPI for SU2 (call it `MPI_SU2`), and `$P/mpirun`
  for ADflow. Mixing them is a classic failure.
- **Hardware:** `lscpu` (physical cores), `free -g`, `df -h .`. The record says 48–52 GB of RAM on this desktop,
  but **WSL may see only part of it**: if `/proc/version` says Microsoft, read `C:\Users\<you>\.wslconfig`
  (`/mnt/c/Users/<you>/.wslconfig`) and report the limit. Do not change it tonight (that restarts WSL and ends
  this session).

## 1. The pyGeo mesh check (about 15 min; Q6)

```bash
python scripts/pygeo_mesh_check.py        # the 20 reference wings, VC, Re 3e5 -> data/studies/pygeo_mesh_check.json
```

Expected: `same 20`, `both_passed 20`, nodes apart by round-off (below 10⁻⁶ mean chords). If not, record which
wings and how, and go on: tonight's meshes are built on pyGeo anyway (the production loft).

## 2. The meshes (about 5 min)

```bash
N=data/v7/night_11nov && mkdir -p $N
python scripts/v5_export.py | tee $N/v5_export_printout.txt   # today's VC: the V7 mesh, on pyGeo
cp data/studies/r2_v5_export.json $N/r2_v5_export_pygeo.json   # v5_export rewrites its record: keep the copy here,
git checkout -- data/studies/r2_v5_export.json                 #   and leave the committed record as it was
python scripts/whatif_mesh.py --pack today --level VVC --type bwb --index 0 --re 3e5 --formats cgns su2
python scripts/whatif_mesh.py --pack light --level VC  --type bwb --index 0 --re 3e5 --formats cgns su2
python scripts/whatif_mesh.py --pack today --level VC  --type bwb --index 0 --check-production   # same shapes, nodes ~1e-11 apart
```

| Mesh folder (`data/meshes/`) | What | Cells (built here on the numpy loft) | ADflow RAM, S8 law (ANK only) | ADflow time, S8 law (6 ranks) |
| --- | --- | --- | --- | --- |
| `whatif_today_VVC_e32d995a_re3e5` | today's rules, one level under VC (y⁺ 1.3: a preview level) | 1,075,074 | 10.5 GiB | 38 min |
| `volume_VC_e32d995a_re3e5` | today's VC: the V7 mesh | 2,324,016 | 19.5 GiB | 83 min |
| `whatif_light_VC_e32d995a_re3e5` | the light rules at VC (decision 114, not decided) | 1,475,376 | 13.4 GiB | 53 min |

The counts on pyGeo should be the same; if a count differs, record it. The names carry the wing's input hash
(`e32d995a`): use the folder names the scripts print. S8's laws are two-point fits at 0.57 and 1.11 M cells, not
measured at these sizes: tonight measures them.

## 3. The cases (seconds)

```bash
M=data/meshes
python solve/case.py --mesh $M/whatif_today_VVC_e32d995a_re3e5 --alpha 4  --out runs/n11_today_VVC_a4
python solve/case.py --mesh $M/volume_VC_e32d995a_re3e5        --alpha 4  --out runs/n11_today_VC_a4
python solve/case.py --mesh $M/whatif_light_VC_e32d995a_re3e5  --alpha 4  --out runs/n11_light_VC_a4
python solve/case.py --mesh $M/whatif_today_VVC_e32d995a_re3e5 --alpha -5 --out runs/n11_today_VVC_am5
python solve/case.py --mesh $M/whatif_today_VVC_e32d995a_re3e5 --alpha 10 --out runs/n11_today_VVC_a10
```

(Mach 0.1 and Re 3e5 are the defaults.) `case.py` and `read_results.py` run in the repo `.venv`; `run_adflow.py`
runs in the MACH-Aero env.

## 4. The runs

Two lines of runs, 6 ranks each (S8's laws are for 6 ranks):

| Line | Run | Case | Solver | Cap | Answers |
| --- | --- | --- | --- | --- | --- |
| A | A1 | `n11_today_VVC_a4` | ADflow SA | 3 h | Q1, Q2 |
| A | A2 | `n11_today_VC_a4` | ADflow SA | 3 h | Q1, Q2 (the V7 case; the 2nd memory point) |
| A | A3 | `n11_light_VC_a4` | ADflow SA | 3 h | Q4 (against A2) |
| A | A4, A5 | `n11_today_VVC_am5`, `n11_today_VVC_a10` | ADflow SA, volume solution kept | 2 h each | Q5 |
| B | B1 | `n11_today_VVC_a4` | SU2 SA | 2.5 h | Q1, Q2, Q3 (against A1), Q7 |
| B | B2 | `n11_today_VVC_a4` | SU2 SST + LM | 2.5 h | Q1, Q2 (SA against LM) |
| extra | X1 | `n11_today_VC_a4` | SU2 SA | 3 h | V7's SU2 case on VC |
| extra | X2 | `n11_today_VC_a4` | ADflow SA, `--set-option ANKPCILUFill=0 --set-option outputDirectory=runs/n11_today_VC_a4/adflow_fill0` | 3 h | Q2: a leaner preconditioner (RUNBOOK section 5) |

- **With at least 12 physical cores and the RAM for both**, run line A and line B side by side. **Otherwise one at a
  time, in this order:** A1, B1, A2, A3, A4, A5, B2, then X1, X2.
- **A1 goes first, alone.** It is the first time ADflow reads one of our meshes.
- **Before A2:** predict its peak from A1's measured memory, scaled by the cells (2,324,016 / 1,075,074: an upper
  bound). Start A2 only if that is below 80 % of `MemAvailable` (less whatever a side-by-side run uses). If not,
  skip A2 and say why; run A3 (1.48 M cells) if it fits.
- A run that does not converge inside its cap stays in the record ("not converged at the cap", with its residual
  drop and its last forces). Move on.

### One ADflow run (example: A1)

```bash
C=runs/n11_today_VVC_a4
$P/mpirun -np 6 $P/python solve/run_adflow.py --case $C --preflight > $C/adflow_preflight_log.txt 2>&1
python solve/rss_watch.py --match run_adflow.py --out $C/adflow/rss.csv > $C/adflow_rss_log.txt 2>&1 &
$P/mpirun -np 6 $P/python solve/run_adflow.py --case $C --set-option timeLimit=10800 \
    --lift-distribution 150 --slices 0.5,0.8,0.9,0.95,0.98 > $C/adflow_log.txt 2>&1
wait
python solve/read_results.py --case $C
```

- The preflight reads the grid and checks the families and the flow direction: if it fails, nothing heavy was spent.
- `--lift-distribution` and `--slices` are new (11 Nov) and **not yet tested on ADflow**. They run after
  `result.json` is written, so they cannot lose the solve; if they fail, the error is in `result.json["extras"]`.
  Use them on A1, A2 and A3 (A3 against A2 is the tip comparison of Q4).
- A4 and A5: the same, with `--set-option timeLimit=7200` and without the two new flags; the volume solution is
  written by default (`writeVolumeSolution` is true in `adflow_options.json`): keep it for step 5.

### One SU2 run (example: B1)

```bash
C=runs/n11_today_VVC_a4
mkdir -p $C/su2_sa && cd $C/su2_sa
python ../../../solve/rss_watch.py --match SU2_CFD --out rss.csv > rss_log.txt 2>&1 &
timeout 150m $MPI_SU2 -np 6 SU2_CFD ../su2_sa.cfg > log.txt 2>&1
wait
cd ../../..
python solve/read_results.py --case $C
```

B2: the same in `$C/su2_sst_lm` with `../su2_sst_lm.cfg`. `read_results.py` reads `adflow/`, `su2_sa/` and
`su2_sst_lm/` of one case folder together, so A1, B1 and B2 land in one table.

## 5. Read each run

For every run, from its files (never from memory):

- converged, settled, accepted (the verdict of `read_results.py`), iterations, residual drop, wall time,
  seconds per iteration;
- peak memory: ADflow `result.json["memory"]` (summed over the ranks) and `rss.json` (the watchdog); SU2 `rss.json`;
  GiB per million cells;
- CL, CD in counts (1 count = 0.0001), CDp, CDv, CMy;
- **y⁺ (Q7):** from SU2's `surface_flow.csv` (the column with `Y_Plus`): the largest, the 99th percentile and the
  median over the wall, and where the largest sits (x/c and y / semi-span). The design value is 1.3 at VVC, 1 at VC.
  For ADflow, y⁺ is in its surface solution (`surfaceVariables` has `yplus`): report it only if you can read the file.
- **The tip (Q4), A3 against A2:** from `lift_distribution.dat` the sectional lift over the outer 10 % of the
  semi-span (the largest difference, and at which y), and from `slices.dat` the largest Cp difference at 0.9, 0.95
  and 0.98 of the semi-span. Put both lift distributions in one figure (`tip_lift_A2_A3.png`).
- **The wake (Q5), A4 and A5:** on the station plane nearest mid semi-span (the stations are exact planes y = const:
  one k-index of the mesh), find the wake centre (the lowest velocity magnitude) on vertical lines at d = 0.25, 0.5, 1
  and 2 local chords behind the trailing edge, and compare it with the band the mesh was built for
  (`configs/volume.yaml`, `wake.band`): z_TE + d tan(−5°) − 0.05 c ≤ z_wake ≤ z_TE + d tan(10°) + 0.05 c, with c the
  local chord and z_TE the middle of the two trailing-edge corners of the wall at that station (the wall points
  with the largest x on the upper and the lower side; from `blocks.npz`). To read ADflow's
  volume file, try the repo's own ADF reader first (`from cfdauto.volume.cgns import read_adf, rdata`), else
  ParaView's `pvpython` if it is installed. If it works, keep it as a new script `solve/wake_check.py` (outside
  `cfdauto/`). If nothing reads the file within 45 minutes, keep the two volume files and say so.

## 6. The report

Folder `CFD_Automation/Stage_3_volume_mesh/data/v7/night_11nov/`, updated after every finished run (so a crash at
05:00 loses nothing):

- `REPORT.md`, in short plain sentences:
  1. **Machine:** cores, RAM seen, the WSL limit, the versions (ADflow, SU2, MPI, pyGeo), the commit.
  2. **The runs:** one table, a row per run: run, mesh, cells, solver and model, ranks, side by side with what,
     wall time, iterations, residual drop, verdict, peak RAM (GiB), GiB per M cells, CL, CD (counts), CDp, CDv, CMy,
     y⁺ (largest, 99 %).
  3. **The answers Q1–Q7**, each: the numbers, then one sentence. Q2: the measured memory against both S8 laws, and a
     straight line through ADflow's measured points (GiB = a + b × M cells); what that gives for M (about 9.5 M
     cells) and for the light M (about 5.5 M); the time in minutes per M cells against S8's 35.7. Q3: ΔCL in %, ΔCD in
     counts, ΔCM. Q4: ΔCL, ΔCD, ΔCM and the tip numbers above. Q6: the summary of `pygeo_mesh_check.json`.
  4. **What failed:** each failure with its command, its error and what was tried.
  5. **Every solver option changed** from the case files, with why.
  6. **What this does not show:** no grid convergence (VVC and VC only); VVC is a preview level (y⁺ 1.3); LM on VVC
     and VC under-resolves the bubbles (about 7 and 9 cells per bubble); one wing, one Re, one angle for Q1–Q4; the
     light rules change three things at once.
- `summary.json`: every number of the report, by run.
- One folder per run with its small files only: `case.json`, `adflow/result.json`, `adflow/preflight.json`,
  `adflow/rss.json`, `adflow/lift_distribution.dat`, `adflow/slices.dat`, `adflow_log.txt` (the last 300 lines),
  `su2_*/history.csv`, `su2_*/forces_breakdown.dat`, `su2_*/rss.json`, `su2_*/log.txt` (the first 150 and the last
  300 lines), `results.json`, `results.md`. Figures as `.png` (they are allowed in this folder). Keep the folder
  under 50 MB, no file over 10 MB.

## 7. Commit and push (after every finished run, and at the end)

```bash
cd <the aeris repo>
git pull --ff-only
git add CFD_Automation/Stage_3_volume_mesh/data/v7/night_11nov
git add CFD_Automation/Stage_3_volume_mesh/data/studies/pygeo_mesh_check.json     # after step 1
git add CFD_Automation/Stage_3_volume_mesh/solve/wake_check.py                    # only if you wrote it
git diff --cached --stat                           # check: only these files are staged
git commit -m "V7 night run: <what is in>"
git push origin main
```

Never `git add -A`, never `git commit -a`. If `git pull --ff-only` refuses, stop committing and say so in the
report; do not force anything.
