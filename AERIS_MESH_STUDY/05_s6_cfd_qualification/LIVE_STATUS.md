# S6 qualification live status

Updated: 2026-09-02T07:19:28+03:00

## Executive state

- **No CFD process is running.**
- The desktop completed the exact 943,104-cell A/C03 ADflow RANS/SA workload
  for 6 h 39 min under the governed watchdog. There was no OOM, no swap
  growth, no watchdog stop, and no abrupt WSL shutdown. Sub-million-cell
  execution on this desktop is therefore demonstrated for this exact
  ILU-fill-1 configuration.
- The terminal status is **`SOLVER_MEASUREMENT_FAILED`**, not an accepted CFD
  result. ADflow exhausted the configured 20,000 total-minor-iteration budget
  after 943 nonlinear rows. Density and energy residuals remained above their
  immutable limits.
- The immutable resource policy also did not pass: measured peak session RSS
  was 9.85504 GiB versus the 9.45 GiB forecast. Minimum available memory was
  2.04647 GiB, only 0.04647 GiB above the 2 GiB watchdog floor.
- Actual ADflow cell-centroid y+ was measured. The global p95 and p99 passed,
  but the global maximum and nine of thirteen wall-region gates failed. Every
  tip/cap region failed; `tip_base` was worst.
- The independent Claude post-run verdict reproduces the evidence and keeps
  the CFD gate closed. **No new CFD, retry, or token reuse is authorized.**
- The development/holdout separation remains intact. The locked holdout was
  not accessed.

## Exact attempt03 identity

- Execution ID: `m2_a_c03_measurement_20260901_003`.
- Launch commit: `579c561368d68aacdda067c978246128b3d27a21`.
- Policy: `policies/m2_a_c03_canary_v4.yaml`.
- Policy SHA-256:
  `95a70fad10e745d6f8f82267bfd887470b38fb8a77301f430b61d6e2272cfb3c`.
- Mesh SHA-256:
  `be2805ff85b6b1043863d7678d1551a52b6e8a65b299534d4ec0aaeffa51aeb4`.
- Mesh: 943,104 cells, zero inversions, `qmin=0.1670988318`.
- Case: geometry A, development index 83, C03, alpha 8 deg, Mach 0.0837,
  Reynolds 1,530,708.1886, temperature 278.4 K.
- Solver: ADflow 2.13.1, RANS/SA, one MPI rank, ANK/NK subspaces 10/20,
  ANK/NK ILU fill 1/1.
- Attempt03 authorization is consumed permanently. Its plaintext execute token
  must never be reconstructed or reused.

## Resource result

- Watchdog elapsed: 23,963.437 s (6 h 39 min).
- ADflow solution elapsed: 22,904.072 s (6 h 22 min).
- Maximum full-session RSS: 10,581,766,144 bytes = 9.855038 GiB.
- GNU-time maximum RSS: 10,322,264 KiB.
- Forecast: 9.45 GiB; underprediction: 0.405038 GiB.
- WSL-visible memory: 12.664684 GiB.
- Minimum `MemAvailable`: 2.046471 GiB.
- Maximum swap growth: zero.
- Kernel OOM kills: zero.
- Watchdog stops: zero.
- Resource samples retained: 11,715.
- Interpretation: the memory correction made the full run executable, but the
  immutable forecast check failed and the margin was too thin for any
  memory-increasing change without a new resource case.

## Solver and residual result

- Complete native monitor history: 944 rows, including row zero.
- Last nonlinear row: 943; last total-minor-iteration count: 20,021.
- ANK rows: 215. NK begins at nonlinear row 216; NK rows: 728.
- Density: `396.301851 -> 1.202361e-4`, 6.518 orders, **FAIL** versus
  `1e-5`.
- Energy: `1388.999836 -> 2.586341e-5`, 7.730 orders, **FAIL** versus
  `1e-5`.
- Momentum maximum: `6.972862e-6`, pass.
- SA: `3.930134e-9`, pass.
- Last-200 force-tail stability passes for CL, CD and CMy. Diagnostic final
  mission-CG coefficients are CL `0.3928887`, CD `0.03887714`, and CMy
  `0.05163649`; these are not accepted aerodynamic results.
- The last-200 NK median linear residual was 0.9775, p95 was 0.997, and 98 of
  200 updates used step 0.01. Density still fell by about 25% over the window,
  so this was slow practical stagnation rather than divergence.
- More cycles alone is not authorized and is not the preferred correction.
  The leading hypothesis is inadequate NK linear preconditioning at ILU fill
  1, but that cause is not uniquely proven by one run.

## y+ and physics QC

- Convention: ADflow y+ at the first off-wall cell centroid.
- Global: p50 `0.2016`, p95 `0.7845`, p99 `1.9907`, maximum `5.8568`;
  97.404% of samples are at or below 1.
- Failed OML blocks: `oml_nose`, `oml_base`.
- Failed tip/cap blocks: `tip_upper_aft`, `tip_upper_fore`, `tip_nose`,
  `tip_lower_fore`, `tip_lower_aft`, `tip_base`, `tip_centre`.
- Worst block: `tip_base`, p95 `5.7930`, p99 `5.8543`, max `5.8568`.
- Cp, Cf and y+ are present and finite: 31,168 values each, zero nonfinite.
- The required signed boundary mass-flux balance was not measured; the
  available continuity-residual surrogate cannot replace it.
- Conformal-interface field-discontinuity QC was not evaluated.
- Therefore C03 cannot support viscous acceptance or grid-independence claims.
  A separately governed tip/cap and narrow-OML wall-normal correction is
  required.

## Evidence retained

Immutable records:

- `reports/m2_a_c03_canary_authorization_consumed_20260901_attempt03.json`
- `reports/m2_a_c03_canary_execution_20260901_attempt03.json`
- `reports/m2_a_c03_solver_postmortem_20260902_attempt03.json`
- `reports/run_canary.json`
- `reviews/claude_m2_c03_ilu1_exact_wiring_review_20260901.json`
- `reviews/claude_m2_a_c03_attempt03_postrun_review_20260902.json`

Complete run logs and residuals are retained under:

`studies/canary/m2_a_c03_measurement_20260901_003/`

- case, requested/effective options, static runner and launch record;
- combined solver stdout/stderr;
- complete native convergence history and normalized solve report;
- complete resource-watchdog JSONL timeline;
- GNU-time verbose record;
- ADflow result JSON;
- surface CGNS with Cp, Cf, y+ and velocity fields.

The surface CGNS is retained locally and SHA-256 bound as
`3abf9350bd92d66933f3a02fabbc84e62291aa2501534ee2d9531ec1818ab973`.
Per repository policy it is hashes-only and must not be committed. No volume or
restart state exists. Nothing may be deleted without explicit human approval.

## Prior attempts and mesh-family state

- V2 and v3 each launched once and ended `RESOURCE_BLOCKED_HOST`; both tokens
  are permanently consumed. Never retry v2/v3 or reinterpret them as mesh
  failures.
- V4 launched once and reached the solver terminal state described above; its
  token is permanently consumed.
- The valid S6 route remains: march a clean S1/Openblademesh volume and apply
  bounded deformation to the exact S6 wall.
- The coupled C01/C02/C03 family remains geometrically valid and inversion
  free. The CFD measurement now reveals a separate C03 near-wall defect at the
  tip/cap and two narrow OML regions.
- C01-to-C02 is not a strong wall-normal refinement step. A three-level
  Richardson or grid-independence claim remains unauthorized even if a solver
  eventually converges.

## Next work — no CFD authorized

1. Commit and push the complete attempt03 evidence, residual/resource logs,
   postmortem, independent review and both live handoffs.
2. Re-anchor any future resource model at no less than the measured 9.855 GiB
   peak and preserve the unchanged 2 GiB watchdog floor.
3. Perform read-only ADflow source/options analysis for one bounded convergence
   lever and for restart/volume-state semantics. Stronger NK ILU, an ANK-biased
   path, subspace changes and continuation must be compared analytically before
   any new policy.
4. Design and independently audit a C03 wall-normal/tip-cap correction using
   the measured per-block y+ evidence. Do not claim mesh independence yet.
5. Attempt a read-only derivation of the governed signed boundary mass balance
   and interface-field QC from retained artifacts.
6. A new heavy action requires a new immutable policy, independent GO, all
   gates green, a fresh one-shot authorization, and explicit user approval.

## Claude continuation order if Codex credits stop

Read `CLAUDE_CODE_HANDOFF.md` and execute only its read-only post-run analysis
order. Preserve all attempt03 evidence and unrelated user changes. Do not run
CFD, do not generate or inspect holdout data, and do not create or reuse an
execute token. Leave both handoffs current with exact file hashes and a clear
`cfd_authorized: false` state.

## Safe resume commands

```bash
cd /home/mike_kara/aeris
git status --short
.venv/bin/python -m pytest -q tests/cfd/test_adflow_adapter.py AERIS_MESH_STUDY/05_s6_cfd_qualification/tests/test_orchestrator.py AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py
```

There is deliberately no CFD execute command or reusable token in this file.
