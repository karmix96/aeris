# S6 qualification live status

Updated: 2026-09-01T07:17:48+03:00

## Executive state

- No CFD process is running.
- The only authorized A/C03 measurement canary was launched exactly once and
  ended as **`RESOURCE_BLOCKED_HOST`**. This is a host-memory outcome, not a
  mesh verdict.
- The one-shot authorization is permanently consumed. **Do not retry it**, do
  not reuse its execute token, and do not launch C01, C02, a holdout case, or a
  campaign under that authorization.
- The result is measurement-only and not accepted. It did not converge and did
  not reach surface-output finalization, so measured y+ is unavailable.
- The development-set/holdout separation remains intact. Holdout
  `round_c_lhs10_seed42` is locked and its contents remain untouched.
- WSL/storage qualification remains verified: Ubuntu is registered at
  `D:\WSL\Ubuntu`, with a 13 GB WSL cap (12.66 GiB visible), 8 GiB swap,
  12 logical CPUs, and a verified recovery VHD.

## Exact canary outcome

- Execution ID: `m2_a_c03_measurement_20260831_001`.
- Bound code: `e4829b0f327e2a6dd199d8c87d84217c36a8ccda`.
- Bound mesh:
  `m2_coupled_family_20260831/candidate_c03/lhs100_seed42_083/wing_vol_deformed.cgns`.
- Mesh SHA-256:
  `be2805ff85b6b1043863d7678d1551a52b6e8a65b299534d4ec0aaeffa51aeb4`.
- Mesh size/quality: 943,104 cells, zero inversions, independently reproduced
  `qmin=0.1671`.
- Solver: ADflow 2.13.1, RANS/SA, one MPI rank, geometry A, development index
  83, alpha 8 degrees, Mach 0.0837, Reynolds 1,530,708.1886, temperature
  278.4 K.
- Preflight passed all 43 identity/governance checks, all 19 solver-environment
  checks, the real one-rank non-CFD MPI probe, and the prelaunch resource gate.
- Authorization was consumed at `2026-08-31T22:11:16.533348Z`, before process
  start, as required.
- The watchdog terminated the process after 339.6016 s when available memory
  fell to 1.964928 GiB, below the governed 2.0 GiB floor.
- Forecast peak use was 9.35 GiB. The observed available-memory drop was
  9.864723 GiB, so the forecast underpredicted this run by 0.514723 GiB.
- There was no kernel OOM event and no material swap growth. The watchdog
  performed its intended controlled stop; blind retry is forbidden.
- ADflow completed monitor iteration 15 (16 rows including iteration 0) before
  termination. It had not converged and did not write the requested surface
  solution.

## Diagnostic solver history

The raw native log retains every completed expanded monitor row: density,
x/y/z momentum, energy and SA residuals plus CL, CD, CDp, CDv and CMy.

- Density residual: `396.30185 -> 0.0636363` (3.794 orders).
- Energy residual: `1388.99984 -> 0.248184` (3.748 orders).
- Total residual: `1.409082e6 -> 2361.3372` (2.776 orders).
- Final completed-row forces were CL `0.418634`, CD `0.0811233`, CDp
  `0.0598966`, CDv `0.0212267`, CMy `0.0242157`.
- These values are transient diagnostics only. They are not converged
  aerodynamic results and must not be used for acceptance or design ranking.

The parser was corrected after the run to recognize both legacy and expanded
ADflow monitor layouts without positional shifts. The structured postmortem
re-parses the immutable raw log and records all 16 rows. This post-run parser
change does not alter the code identity or outcome of the launched solve.

## Retained evidence

Immutable/governed records:

- `reports/m2_a_c03_canary_authorization_consumed_20260831.json`
- `reports/m2_a_c03_canary_execution_20260831.json`
- `reports/m2_a_c03_resource_blocked_postmortem_20260901.json`
- `reports/run_canary.json`
- `reviews/claude_m2_coupled_family_review_20260831.json`

Complete small run artifacts are retained under:

`studies/canary/m2_a_c03_measurement_20260831_001/`

- `launch_record.json`
- `adflow_case.json`
- `adflow_options.json`
- `adflow_effective_options.json`
- `run_adflow.py`
- `adflow_run.log`
- `resource_watchdog.jsonl`
- `solve_report.json`
- `time_verbose.txt`

No surface CGNS, restart, volume field, or other large solver artifact exists:
the controlled stop occurred before final output. The execution record hashes
the raw solver log, watchdog timeline, solve report, and GNU-time file.

## Mesh-family state

- The original exact-wall direct-march route remains historical NO-GO because
  reopened meshes contained inverted cells.
- The proven S6 route remains valid: march a clean S1/Openblademesh volume,
  then apply bounded deformation to the exact S6 wall.
- The redesigned coupled family uses collar counts `5/6/7`, wall-spacing
  fractions `5.0e-6/4.7e-6/3.6e-6`, and
  `191,520/422,352/943,104` cells.
- A/B/C/E reopen cleanly at all three levels with zero inversions and
  `qmin >= 0.1091`; C/C03 uses its governed geometry-specific template.
- Independent review `5f17ceb` closed R1-R3 and authorized only the consumed
  A/C03 measurement canary.
- C01 to C02 is not a strong wall-normal refinement step, so a three-level
  Richardson/grid-independence claim is still not authorized. Grid independence
  requires converged, comparable solutions and a separately governed ladder.
- The resource-stopped A/C03 solve neither validates nor invalidates the mesh
  aerodynamically. C02 remains the screened production mesh family; no C02 CFD
  has been authorized here.

## Verification

- Focused post-run verification: **77 passed** across the S6 atlas,
  qualification orchestrator, and ADflow adapter suites.
- Ruff and `git diff --check`: pass.
- The consumed-state regression test now requires `run-canary --dry-run` to
  return BLOCKED with no process launch and preserves the terminal run summary.
- Repository-wide pytest remains collection-blocked by absent optional project
  packages (first root cause previously observed: `aerosandbox`), not by the
  governed focused suite.

## Next authorized work

Continue with read-only resource diagnosis only:

1. Reproduce all evidence hashes and the 16-row postmortem from the raw log.
2. Measure Windows physical memory, current WSL limits, swap and available
   headroom.
3. Audit ADflow/PETSc memory-reduction choices and improve the forecast using
   this measured 9.864723 GiB drop.
4. Produce a resource plan that distinguishes a host-RAM increase from a
   solver-memory reduction.

Before any additional CFD, require a new immutable one-shot policy, a fresh
independent review, demonstrated headroom, and explicit user authorization.
Never infer permission to retry from the previous GO.

## Safe resume commands

```bash
cd /home/mike_kara/aeris
.venv/bin/python -m pytest -q tests/cfd/test_adflow_adapter.py AERIS_MESH_STUDY/05_s6_cfd_qualification/tests/test_orchestrator.py AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py
git status --short
```

There is deliberately no CFD execute command or reusable token in this file.
