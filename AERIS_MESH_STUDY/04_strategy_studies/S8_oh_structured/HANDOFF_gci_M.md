# Resume here: the gci_M attempt

**Written 2026-09-06.** Everything below is state, not plan. The plan is
`PLAN_desktop_campaign.md`; this says where execution stopped and what to type.

## Why the session restarted

`.wslconfig` was raised from `memory=13GB` to **14GB** so that `gci_M` fits.
That needs `wsl --shutdown`, which ends the session. Backup of the old file is
at `C:\Users\mike\.wslconfig.bak-13GB`.

**First thing to do: confirm the cap actually took.**

```bash
free -g | awk '/^Mem:/ {printf "total %s GiB, AVAILABLE %s GiB\n", $2, $7}'
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/select_levels.py
```

Expect available near **12.7 GiB**, against `gci_M`'s predicted 12.02. If it
still reads ~11.8, the .wslconfig edit did not apply -- check that the file has
CRLF line endings (it is a Windows file, and a plain `sed 's/$/x/'` will not
match) and that `wsl --shutdown` really ran.

## What is done

| | |
|---|---|
| authorization | `POLICY.yaml` `run-s8-campaign`, `policies/s8_campaign_v1.yaml`, ADR-0020, signed 2026-09-06 |
| `gci_C` + `gci_M` meshes | built, `artifacts/s8_gci83/`, 0 folded, wall error 2.22e-16 m |
| PLAN 3.2 regression | **PASSED**, CD moved 1.5e-05 |
| PLAN 3.3 at `gci_C` | **all four angles complete** |
| AVL on index 83 | four angles, agrees to 2.0 % on CL and 3.7 % of MAC on x_np |
| figure | `05_s6_cfd_qualification/viz/s8_gci_C_sweep_20260906.png`, 10 panels |

`gci_C` results, from `reports/s8_gci_gate.json`:

| alpha | verdict | orders | iters | CL | CD | CMy |
|---|---|---|---|---|---|---|
| -2 | ACCEPTED | 8.00 | 212 | -0.29812 | 0.02599 | -0.00598 |
| 0 | ACCEPTED | 8.03 | 277 | -0.15969 | 0.02082 | +0.00125 |
| 4 | **ACCEPTED_SOLVER_FROZEN** | 6.59 | 1338 | +0.12053 | 0.01986 | +0.01535 |
| 8 | ACCEPTED | 6.92 | 1223 | +0.40210 | 0.03092 | +0.02850 |

## What to run next

**`gci_M`, four angles.** The mesh already exists; only the solves are missing.
The driver skips anything with a `result.json`, so this resumes rather than
restarts, and it will not redo `gci_C`.

```bash
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/run_campaign.py \
    sweep --levels gci_M --watch-memory
```

`gci_M_a-2` has a partial `run.log` and no `result.json` from the killed
attempt, so it will be re-run from scratch. That is correct: a run killed at
iteration 301 is not a restartable state.

**Watch the ANK -> NK switch.** That is the whole question. The killed attempt
died in ANK at a 3.2e-05 residual and never reached NK, so it never tested the
memory peak -- the 12.02 GiB figure is a WITH-NK measurement. NK engages at
`NKSwitchTol` 1e-6, which on `gci_C` was around iteration 200-280.

```bash
tail -f AERIS_MESH_STUDY/artifacts/s8_cfd/gci_M_a-2/memory_watch.json
```

The watchdog now flushes samples to disk as it takes them. In the first attempt
it only wrote at the end, so when the parent was killed the entire memory record
died with it and there is no curve for what happened -- PLAN 0.4, one level up.

Then, with two levels finally in hand:

```bash
S=AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
R=AERIS_MESH_STUDY/05_s6_cfd_qualification/reports
.venv/bin/python $S/convergence_gate.py --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*' --out $R/s8_gci_gate.json
for A in -2 0 4 8; do
  .venv/bin/python $S/gci.py --runs "AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a${A}" \
      --two-level-trend --gate $R/s8_gci_gate.json --out $R/s8_gci_a${A}.json
done
.venv/bin/python $S/stability_convergence.py --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*' \
    --gate $R/s8_gci_gate.json --out $R/s8_stability_convergence.json
.venv/bin/python $S/analyse_refinement.py --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*' \
    --gate $R/s8_gci_gate.json --out $R/s8_refinement_analysis.json
.venv/bin/python $S/mass_balance.py --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*' --out $R/s8_mass_balance.json
```

## Traps specific to this host

1. **The plan's interpreter paths are wrong here.** It says
   `/home/mike/miniconda3/...`; this host is `/home/mike_kara/miniconda3/...`.
   Use `env_s8.py`, which resolves them and also picks the MACH-Aero env's OWN
   `mpirun` -- the one on `$PATH` is a different OpenMPI, and mixing runtimes
   gives six rank-0 processes that all believe they are alone.
2. **ADflow writes ADF, not HDF5.** The linked CGNS 4.5.2 has no HDF5 support,
   so `h5py` cannot open any solution file. Use `cgns_read.py`. Anything reading
   solutions through h5py silently gets nothing, which is how the cp panel came
   out blank rather than wrong.
3. **`*.png` is gitignored.** Figures need `git add -f`.
4. **Work on `main`.** No feature branches in this repo.
5. **Two levels is a TREND, not a GCI.** `gci_F` needs 22.5 GiB and the Windows
   host has 15.86 GiB in total, so no `.wslconfig` value reaches it. Say so in
   anything that reports the result. `gci.py` refuses a band from two levels
   unless `--two-level-trend` is passed, and says why.
6. **alpha 4 is `ACCEPTED_SOLVER_FROZEN`** and `gci.py` excludes it. Expect the
   trend at alpha 4 to be unavailable, and expect the stall to recur at `gci_M`
   -- whether it does is itself a result (PLAN 4.3).

## Still open

- **PLAN 2.2** far-field sensitivity: `run_campaign.py farfield`. One run, ~25 min.
- **PLAN 3.5** choose the campaign level: `analyse_refinement.py --choose <level> --reason '...'`.
- **PLAN 4.2** the ten-geometry pilot: ~40 runs, ~17 h. Set is fixed in
  `reports/s8_pilot_geometries.json`; schema is fixed by `dataset_row.py`.
- **PLAN 5** ONERA M6: BLOCKED, no published grid family exists at any route.
  See `reports/s8_tmr_onera_m6_grid_availability.json`. The experiment is
  archived in `05_s6_cfd_qualification/external/onera_m6/`.

## Restore the memory cap when done

```
C:\Users\mike\.wslconfig      memory=14GB   (raised 2026-09-06 for gci_M)
C:\Users\mike\.wslconfig.bak-13GB           the original
```
Windows has 15.86 GiB total, so at 14GB it keeps about 1.9 GiB. That is enough
for a machine only hosting WSL and is thin for anything else.
