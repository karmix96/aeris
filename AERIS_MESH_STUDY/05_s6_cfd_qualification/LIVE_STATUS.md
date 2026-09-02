# S6 qualification live status

Updated: 2026-09-02T22:53:26+03:00

## Six-rank attempt04 launch state

**RUNNING. Do not launch another CFD process.** The one-shot token was consumed
at 2026-09-02T19:50:42Z and POSIX process session 84539 started. Six-rank MPI
readiness had passed on ranks 0 through 5. At elapsed 154 s the full-session
RSS was 9.11 GiB, MemAvailable was 2.88 GiB, swap growth was zero, and ADflow
was advancing in ANK on the corrected mesh. The combined log had reached at
least nonlinear iteration 15 / total minor iteration 128 with linear residuals
near 0.05. Monitor the existing attempt; never reconstruct the token or retry.

- The principal investigator explicitly directed one immediate CFD run on the
  corrected mesh with six MPI ranks and waived the pending Claude audit. The
  waiver is retained honestly in
  `reviews/human_m2_a_c03_six_rank_override_20260902.json`; it does not claim
  that Claude's findings were closed.
- New immutable policy: `policies/m2_a_c03_canary_v5.yaml`. It binds attempt
  `m2_a_c03_measurement_20260902_004`, corrected mesh SHA-256
  `0fe4a4c00bbed1e47fcdaa46b60d00334d48c0cfe9b617cb2a3b0ec51cbd7ced`,
  six MPI ranks, ANK-only RANS/SA, complete residual/log/resource retention,
  final surface output and final double-precision volume output.
- Periodic SIGUSR1 checkpoints are disabled for this attempt because their
  collective semantics have not been validated for six ranks. This avoids
  signaling only one member of an MPI collective. No automatic retry exists.
- Non-CFD identity, environment, RAM, swap and disk preflight passed. At the
  recorded preflight, MemAvailable was 11.6673 GiB, the 9.45 GiB forecast plus
  2 GiB headroom passed by 0.2173 GiB, existing swap was 0.2138 GiB, and free
  disk was 940.6 GiB. The six-rank memory increment is explicitly unmeasured;
  the live 2 GiB watchdog floor remains authoritative.
- The next action is commit the governed policy/orchestrator, run the real
  six-rank MPI readiness probe, consume the fresh token once, and launch.

## Immediate continuation checkpoint

- Claude Opus completed the requested read-only recovery audit. Its historical
  verdict is **`NO_GO_DESKTOP_RECOVERY_CANARY`** with four HIGH findings; the
  compact retained review is
  `reviews/claude_m2_a_c03_desktop_recovery_review_20260902.json`.
- H1 ("forced checkpoint filename is not wired") is contradicted by the exact
  installed ADflow 2.13.1 source: `pyADflow.__call__` invokes
  `_setForcedFileNames()` after `setAeroProblem()`, and that method assigns
  `inputio.forcedvolumefile` to
  `<outputDirectory>/<aeroProblem.name>_forced_vol.cgns`. For this governed
  runner that is exactly `aeris_cfd_forced_vol.cgns`. Preserve H1 in the
  historical review, record the source proof, and require Claude to reconsider
  it in the next independent review.
- H2-H4 are accepted for correction: validate the CGNS `ReferenceState`, keep
  resource sampling alive during checkpoint I/O, itemize the checkpoint memory
  allowance and MemAvailable bound, bind checkpoints to live solver state, and
  define a measured convergence-stagnation outcome.
- Codex attempted to delegate those bounded implementation/test tasks to
  Claude Opus. Claude stopped before editing any implementation file with
  `You've hit your session limit · resets 12:20am (Europe/Athens)`. The
  Claude continuation order remains ready below for execution after that
  reset; there is no partial Claude code to reconcile.
- **No CFD process is running and `cfd_authorized` remains false.**

## CPU-parallelism finding

- Attempt03 did **not** use the whole desktop CPU. Its immutable command was
  `mpirun -np 1 ... run_adflow.py`; GNU time reports 22,857 s user time versus
  22,909 s user+system and 6:21:49 wall time, or 99% of one logical CPU.
- WSL exposes an Intel i5-10400 with 6 physical cores / 12 logical CPUs. The
  run therefore left roughly eleven logical CPUs unused; this materially
  explains why the 943,104-cell case took more than six hours compared with a
  Fluent run partitioned across the desktop.
- One rank was a deliberate memory-safety choice, not an ADflow speed optimum.
  Before another multi-hour canary, add a separately governed 1/2/4/6-rank
  scaling-and-memory qualification design. Do not assume 12 ranks are best:
  MPI halo/partition and per-rank solver structures can increase total memory,
  and the six physical cores are the first meaningful ceiling to test.
- The current one-rank recovery plan remains unchanged until that design is
  source-reviewed and resource-bounded; no MPI scaling CFD is authorized yet.

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
- The post-run failure has now been converted into a bounded recovery design:
  one deterministic wall-normal correction, one low-memory ANK-only solver
  change, final double-precision volume output, and native SIGUSR1 checkpoints.
- The correction has passed mesh-only qualification on development geometries
  A/B/C/E, and 79 focused tests pass. It has not yet been independently
  reviewed. **No new CFD, retry, or token reuse is currently authorized.**
- The development/holdout separation remains intact. The locked holdout was
  not accessed.
- The recovery commits are local but not pushed because this WSL session
  has no GitHub HTTPS credential helper or usable SSH key. No work is lost;
  retry `git push origin main` after GitHub authentication is restored.

## Recovery implementation awaiting independent review

- Family evidence:
  `reports/m2_c03_wall_normal_recovery_family_20260902.json`, SHA-256
  `392ef9850de8e7795c35ef50082a3583bc1ed21855668e16b59b925e2dfa65e9`.
- Recovery plan:
  `reports/m2_a_c03_desktop_recovery_plan_20260902.json`, SHA-256
  `e1eaea665ff8df4b04507f5cd3dfa2d44db1a170244cb7dbb8d3294c7e8bc17b`.
- Independent review target commit:
  `21ec3ef35fe48c3c7965f7b91cd98e5274047688`.
- The same dimensionless layer law was applied to all 13 blocks on A/B/C/E.
  Every output retains 943,104 cells, zero inversions, exact wall and
  farfield, 20 conformal paired interfaces, and `qmin=0.1251...0.1955`.
- All per-block realized first-cell medians are now within
  `4.05e-6...5.06e-6 m`. The old A tip-base median was `1.5505e-4 m`.
- A facewise diagnostic using the actual attempt03 y+ and exact local height
  ratios projects p95 `0.2366`, p99 `0.2682`, max `0.2932`, with no failed
  region. This is screening evidence only; actual CFD y+ remains mandatory.
- The proposed retry keeps one MPI rank and ILU/subspaces 1/1 and 10/20, but
  disables the failed NK end game (`useNKSolver=false`) so the healthy ANK
  solver continues. The previous ANK phase peaked near 8.317 GiB; the proposed
  conservative forecast is 9.2 GiB, below the existing 75% WSL-memory cap.
- The retry is capped at 27,000 seconds and 20,000 minor iterations. It writes
  the final volume solution in double precision and adds `rho` plus vector Cf
  to the retained surface fields.
- Measured late-ANK fits showed that the old `L2Convergence=1e-8` could stop
  while density was still `4.41e-5...6.70e-5`, above its unchanged `1e-5`
  limit. The candidate now uses `1e-11`; the same four fits project density
  `6.79e-7...1.81e-6` in about 3.11...3.52 hours. This is an engineering
  forecast, not a substitute for the actual run.
- Every 1,800 seconds the watchdog will signal only the exact MPI Python rank
  with ADflow's native SIGUSR1. A checkpoint is not published merely because
  its size is stable: all 13 zones must reopen with three coordinate arrays
  and complete finite Density/Velocity/Pressure/SA fields. Source and staged
  copy hashes must match, the copy is reopened again, and only then is it
  atomically linked and directory-fsynced as an immutable numbered checkpoint.
  Positive signal/copy and invalid-checkpoint nonpublication tests pass.
- The next attempt, policy and token do not yet exist. Claude must independently
  reproduce this evidence and return an explicit GO with no unresolved HIGH
  finding before those are created.

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
- Therefore the old C03 cannot support viscous acceptance or grid-independence
  claims. The separately governed correction candidate is now implemented and
  mesh-qualified above, but still requires independent review and actual CFD.

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

## Next work — audit first; no CFD currently authorized

1. Ask Claude Code to independently audit immutable implementation commit
   `21ec3ef35fe48c3c7965f7b91cd98e5274047688`: re-open all four meshes and
   reproduce hashes, QC, y+ projection, NK diagnosis, option wiring, memory
   arithmetic and the real SIGUSR1 checkpoint test. Claude must not run CFD or
   inspect holdout.
2. Resolve every HIGH finding. If the verdict is GO, freeze policy v5 against
   the reviewed commit and exact A mesh; run dry identity/resource/MPI gates.
3. Only after all gates are green, consume one fresh token and launch one
   measurement-only A/C03 run. Preserve every residual, log, resource sample,
   forced/final surface, forced/final volume and checkpoint.
4. Postprocess actual residuals, forces, y+, resources and field presence. Do
   not claim acceptance or grid independence; signed boundary flux and seam QC
   remain separate required work unless implemented and measured.

## Claude continuation order if Codex credits stop

Read `CLAUDE_CODE_HANDOFF.md` and execute its current independent recovery
audit. Preserve all attempt03 and mesh-recovery evidence plus unrelated user
changes. Do not run CFD, do not inspect holdout, and do not create or reuse an
execute token. Leave an explicit `cfd_authorized: false` state unless Codex has
subsequently committed a Claude GO, immutable policy v5 and green preflight.

## Safe resume commands

```bash
cd /home/mike_kara/aeris
git status --short
.venv/bin/python -m pytest -q AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py AERIS_MESH_STUDY/05_s6_cfd_qualification/tests
```

There is deliberately no CFD execute command or reusable token in this file.
