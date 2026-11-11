# V7 runbook: the first solves on one Stage 3 mesh

**State on 9 Nov 2026.** Not run. This session has no ADflow and no SU2, 2 cores and 7 GB of RAM. The mesh is built
with rule set 2 as it stands (decisions 107–111: the wake fan −5° to +10°) and needs about 20–24 GiB for ADflow: more
than the 16 GB desktop, well inside 48 GB. Where it runs: Mike (decision 103). **V7 also measures the memory**
(decision 113) and **where the wake goes** at −5° and +10° (decision 111): sections 5 and 6.

**11–12 Nov: the night run on Mike's desktop: `NIGHT_11NOV.md`** (what runs tonight, in which order, and what to send
back: today's VVC and VC and the light VC of decision 114, ADflow SA, SU2 SA and SST + LM, the wake at −5° and +10°,
the pyGeo mesh check). New for it: `scripts/whatif_mesh.py` (what-if meshes with solver files),
`scripts/pygeo_mesh_check.py`, the memory watchdog `solve/rss_watch.py`, and `run_adflow.py --lift-distribution N
--slices F1,F2,...` (after the solve; not yet tested on ADflow).

The case (fixed by the brief): **BWB reference wing 0, VC, Re 3 × 10⁵, α 4°, Mach 0.1, transition band on.**
Three runs: **ADflow SA**, **SU2 SA**, **SU2 SST + LM** (SU2 8.6.0).

| | |
|---|---|
| mesh | `volume_VC_e32d995a_re3e5`, rule set 2: 2,324,016 cells, 13 blocks, every check passed (V1, V5) |
| files | `volume.cgns` (59.0 MB, ADflow), `volume.su2` (322.8 MB, SU2), from `scripts/v5_export.py` |
| ADflow RAM | S8's laws (two-point fits at 0.57 and 1.11 M cells): ANK only, as run here, 2.69 + 7.23 GiB per M cells = **19.5 GiB**; ANK then NK 1.51 + 9.46 = 23.5 GiB (decision 112) |
| ADflow time | 35.7 min per M cells on 6 ranks ≈ **1.4 h** (S8 law; this mesh is not S8's, so a guide only) |
| units | lengths in mean chords; Re on the mean chord (1 mesh unit); the semi-span along +y, lift +z |

## 0. Make the mesh and the case (any machine with the repo, no solver needed)

```bash
cd CFD_Automation/Stage_3_volume_mesh
python scripts/v5_export.py                       # data/meshes/volume_VC_e32d995a_re3e5/ (about 1 min, 0.5 GB)
python solve/case.py --mesh data/meshes/volume_VC_e32d995a_re3e5 --alpha 4 --mach 0.1 --re 3e5 --out runs/v7_a4
```

`case.py` writes `case.json` (every number of the case: conditions, reference area = the half wing's planform area,
reference chord 1, moment point = the quarter point of the mean aerodynamic chord), `adflow_options.json`,
`su2_sa.cfg` and `su2_sst_lm.cfg`. The mesh folder's `manifest.json` carries the node hash and the code hashes; check
15 (`quality.json`, `exports`) says both files were read back exactly (the CGNS also by the CGNS library itself).

## 1. ADflow SA (MACH-Aero environment)

```bash
cd CFD_Automation/Stage_3_volume_mesh
P=/home/mike/miniconda3/envs/mach-aero/bin                # the MACH-Aero env of the S8 runbook; adjust
$P/mpirun -np 6 $P/python solve/run_adflow.py --case runs/v7_a4 --preflight    # seconds: reads the grid
$P/mpirun -np 6 $P/python solve/run_adflow.py --case runs/v7_a4                # the solve
```

- The preflight reads and partitions the grid, resolves the families (`wall`, `farfield`, `symmetry`) and checks the
  freestream direction. If it fails, nothing heavy has been spent.
- `run_adflow.py` refuses to iterate unless ADflow built velDir = (cos 4°, 0, sin 4°) (S8 defect 14: liftIndex 2 made
  α into sideslip). Settings: SA, eddyVisInfRatio 0.21 (TMR, χ = 3), ANK only, stop at relative residual 1e-6.
  `--set-option KEY=VALUE` changes anything else and is recorded.
- Out: `runs/v7_a4/adflow/result.json` (forces, residual, iterations, the options read back, the history).

## 2. SU2 SA and SST + LM (SU2 8.6.0)

```bash
cd CFD_Automation/Stage_3_volume_mesh/runs/v7_a4
mkdir -p su2_sa su2_sst_lm
(cd su2_sa     && mpirun -np 6 SU2_CFD ../su2_sa.cfg     > log.txt 2>&1)
(cd su2_sst_lm && mpirun -np 6 SU2_CFD ../su2_sst_lm.cfg > log.txt 2>&1)
```

- Numerics: SU2's own Langtry–Menter tutorial set (E387), as S8 ran it: Roe, MUSCL, Venkatakrishnan, implicit,
  adaptive CFL. Markers: `wall` (no-slip, adiabatic), `symmetry`, `farfield`.
- SST + LM: freestream turbulence 0.1 %, viscosity ratio 10 (the tutorial values). Known risk from S8: on E387, SST + LM
  gave no laminar bubble and drag 37 counts high, SA + LM matched; the brief fixes SST + LM, so this is a flag, not a
  change.
- SU2 reorients boundary faces itself if needed; this file's faces already face out (check 15).

## 3. Read and compare

```bash
cd CFD_Automation/Stage_3_volume_mesh
python solve/read_results.py --case runs/v7_a4          # -> results.json, results.md
```

The acceptance rule is in `read_results.py`, written before any run: **converged** (ADflow: relative residual
≤ 1e-6, ≥ 10 iterations, plausible forces; SU2: 6 orders of density residual or 1e-12) **and settled** (over the last
20 % of the record, at least 200 iterations: CD within 0.5 counts, CL within 0.1 %). Anything else is "not accepted"
with its reason, and stays in the record.

## 4. What this answers, and what it does not

- It answers: ADflow reads the CGNS and converges on it; SU2 reads the `.su2` and converges on it, with SA and with
  SST + LM; the two codes' SA forces on one grid.
- It does not answer: grid convergence (needs C and M, 4.9 M and 10.7 M cells on this wing; M needs about 80–103 GiB
  for ADflow by S8's laws, so the HPC), the hold-outs (V8), or anything against experiment.
- Send back: `runs/v7_a4/` without the volume solutions (`result.json`, `history.csv`, `forces_breakdown.dat`,
  `log.txt`, the surface files). Then V7 can be closed with the numbers.

## 5. Measure the memory (decision 113)

Why: the plan assumed 10 M cells in 48 GB; S8's laws say 71–90 GiB for the M level (9–11 M cells). The laws are
two-point fits at 0.57 and 1.11 M cells, so this mesh (2.32 M) is the third point, and the first one for SU2.

- **ADflow as run** (section 1): `result.json` has `"memory"`: the peak resident memory summed over the ranks, GiB per
  million cells, and the two laws' predictions. Nothing more to do.
- **ADflow with a leaner preconditioner** (one extra run; a memory test first, a result only if it also converges):

```bash
$P/mpirun -np 6 $P/python solve/run_adflow.py --case runs/v7_a4 --set-option ANKPCILUFill=0 \
    --set-option outputDirectory=runs/v7_a4/adflow_fill0
```

  Compare `memory.gib_per_million_cells`, the iterations and the time of the two runs. 10 M cells in 45 GiB need about
  4.2 GiB per million cells.
- **SU2** (sections 2): wrap each rank so it reports its own peak, then add them up:

```bash
(cd su2_sa && mpirun -np 6 /usr/bin/time -v SU2_CFD ../su2_sa.cfg > log.txt 2> time.txt)
grep "Maximum resident" su2_sa/time.txt | awk '{s += $6} END {printf "%.1f GiB\n", s / 1024 / 1024}'
```

- Send back the three numbers with the rank count. They decide whether M can run on 48 GB or stays on the HPC.

## 6. Where the wake goes at −5° and +10° (decision 111)

The mesh's wake fan holds the freestream directions −5° to +10° plus 0.05 c. Whether the real wake stays inside it is
not measured. Two more ADflow points on the same mesh, keeping the volume solution:

```bash
python solve/case.py --mesh data/meshes/volume_VC_e32d995a_re3e5 --alpha -5 --mach 0.1 --re 3e5 --out runs/v7_am5
python solve/case.py --mesh data/meshes/volume_VC_e32d995a_re3e5 --alpha 10 --mach 0.1 --re 3e5 --out runs/v7_a10
$P/mpirun -np 6 $P/python solve/run_adflow.py --case runs/v7_am5 --set-option writeVolumeSolution=true
$P/mpirun -np 6 $P/python solve/run_adflow.py --case runs/v7_a10 --set-option writeVolumeSolution=true
```

Send back the two volume files (or a y-slice at the mid semi-span with the total pressure). The script that reads
the wake centre against the fan's edges is **not written yet**: it needs a real solution file to be tested on. If
the wake leaves the fan, the fan's top is one number (`alpha_hi_deg`; +12° costs about 2 % more cells).

