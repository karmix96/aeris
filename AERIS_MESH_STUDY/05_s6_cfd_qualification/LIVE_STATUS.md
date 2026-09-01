# S6 qualification live status

Updated: 2026-09-01T07:40:41+03:00

## Executive state

- No CFD process is running.
- The v2 A/C03 measurement canary was launched exactly once and
  ended as **`RESOURCE_BLOCKED_HOST`**. This is a host-memory outcome, not a
  mesh verdict.
- The v2 one-shot authorization is permanently consumed. **Do not retry it**, do
  not reuse its execute token, and do not launch C01, C02, a holdout case, or a
  campaign under that authorization.
- The user has explicitly authorized engineering one fresh resource-corrected
  A/C03 attempt today. Policy v3 is fail-closed pending independent resource
  review; no new CFD has launched yet.
- The result is measurement-only and not accepted. It did not converge and did
  not reach surface-output finalization, so measured y+ is unavailable.
- The development-set/holdout separation remains intact. Holdout
  `round_c_lhs10_seed42` is locked and its contents remain untouched.
- WSL/storage qualification remains verified: Ubuntu is registered at
  `D:\WSL\Ubuntu`, with a 13 GB WSL cap (12.66 GiB visible), 8 GiB swap,
  12 logical CPUs, and a verified recovery VHD.

## Active resource correction

- Exact ADflow 2.13.1 source proves that the ungoverned default
  `ANKSubspaceSize=-1` becomes `ANKMaxIter=40`. The v2 policy constrained only
  the later `NKSubspaceSize=20`.
- The completed v2 steps needed at most 8 linear iterations. Policy v3 proposes
  an explicit `ANKSubspaceSize=10`, retains `NKSubspaceSize=20`, and changes no
  mesh, flow, RANS/SA physics, reference quantity, ILU fill, or rank count.
- One five-state flow vector is 37,724,160 bytes. Removing 30 ANK basis vectors
  therefore saves at least 1.0540 GiB. Subtracting that from the measured
  9.864723 GiB drop gives 8.810722 GiB.
- The governed proposal forecasts 9.25 GiB, retaining 0.439278 GiB uncertainty
  above that calculation. With 11.742 GiB currently available, it passes the
  75-percent-WSL gate and leaves 2.492 GiB projected total headroom.
- Windows has 16 GB physical RAM in two 8 GB modules, four reported slots, and
  a 64 GB board limit. The 13 GB WSL cap remains unchanged; increasing it was
  rejected before correcting the hidden solver allocation.
- The watchdog now measures the full POSIX process session. The v2
  process-group metric saw only the time wrapper because OpenMPI changed process
  groups; system `MemAvailable`, which triggered the safe stop, was valid.
- Evidence: `reports/m2_a_c03_memory_correction_plan_20260901.json` and proposed
  `policies/m2_a_c03_canary_v3.yaml`.
- The seven resource-review checks are intentionally red until an independent
  Claude review is recorded and hash-bound. Every other identity, solver,
  resource, and one-shot preflight check is green.

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

- Focused post-run verification: **78 passed** across the S6 atlas,
  qualification orchestrator, and ADflow adapter suites.
- Ruff and `git diff --check`: pass.
- The one-shot regression test now reflects both prelaunch and consumed states,
  always launches nothing, and preserves the terminal v2 run summary.
- Repository-wide pytest remains collection-blocked by absent optional project
  packages (first root cause previously observed: `aerosandbox`), not by the
  governed focused suite.

## Next authorized work

1. Independently review commit `539a5d9` and the exact v3 solver/resource
   wiring. Bind a real review record in place of the two `PENDING` values.
2. Commit the reviewed v3 policy and code, rerun all 78 focused tests, the real
   one-rank MPI probe, and every identity/resource gate.
3. If and only if every gate is green, consume the new v3 one-shot before
   launch and run exactly one A/C03 attempt under the unchanged watchdog.
4. Retain all logs, residuals, watchdog samples, surface/y+ output and terminal
   records. Never retry v3 automatically under any outcome.

The user has explicitly authorized that single new run after these gates. The
old v2 GO/token never authorizes it.

GitHub push status: local evidence commits `826c64a` and `539a5d9` are ready,
but this desktop has neither an HTTPS GitHub credential, `gh`, nor an SSH key.
The remote push requires one user authentication step; no evidence is lost.

## Safe resume commands

```bash
cd /home/mike_kara/aeris
.venv/bin/python -m pytest -q tests/cfd/test_adflow_adapter.py AERIS_MESH_STUDY/05_s6_cfd_qualification/tests/test_orchestrator.py AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py
git status --short
```

There is deliberately no CFD execute command or reusable token in this file.
