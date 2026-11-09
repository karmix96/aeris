# V7 runbook: the first solves on one Stage 3 mesh

**State on 9 Nov 2026.** Not run. This session has no ADflow and no SU2, 2 cores and 7 GB of RAM; the mesh needs
about 48 GiB for ADflow. Mike runs these on the 52 GB desktop (16 GB + 36 GB) or the HPC.

The case (fixed by the brief): **BWB reference wing 0, VC, Re 3 × 10⁵, α 4°, Mach 0.1, transition band on.**
Three runs: **ADflow SA**, **SU2 SA**, **SU2 SST + LM** (SU2 8.6.0).

| | |
|---|---|
| mesh | `volume_VC_e32d995a_re3e5`: 4,930,448 cells, 13 blocks, every check passed (V1, V5) |
| files | `volume.cgns` (123.5 MB, ADflow), `volume.su2` (693.6 MB, SU2), from `scripts/v5_export.py` |
| ADflow RAM | 1.51 + 9.46 GiB per M cells = **48.2 GiB** (ANK only); does not fit 16 GB |
| ADflow time | 35.7 min per M cells on 6 ranks ≈ **2.9 h** (S8 law; this mesh is not S8's, so a guide only) |
| units | lengths in mean chords; Re on the mean chord (1 mesh unit); span +y, lift +z |

## 0. Make the mesh and the case (any machine with the repo, no solver needed)

```bash
cd CFD_Automation/Stage_3_volume_mesh
python scripts/v5_export.py                       # data/meshes/volume_VC_e32d995a_re3e5/ (about 1 min, 0.9 GB)
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
- It does not answer: grid convergence (needs C and M, 10.5 M and 22.8 M cells on this wing; M needs about 217 GiB
  for ADflow, so the HPC), the hold-outs (V8), or anything against experiment.
- Send back: `runs/v7_a4/` without the volume solutions (`result.json`, `history.csv`, `forces_breakdown.dat`,
  `log.txt`, the surface files). Then V7 can be closed with the numbers.
