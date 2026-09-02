# Claude Code continuation order — S6 qualification

Updated: 2026-09-02T07:19:28+03:00

This is the live post-run handoff for the AERIS S6 automated CFD qualification
study. Preserve the evidence chain. **No CFD is currently authorized.**

## Read first, in order

1. `MASTER_EXECUTION_GUIDE.md`
2. `LIVE_STATUS.md`
3. `policies/m2_a_c03_canary_v4.yaml`
4. `reports/m2_a_c03_canary_authorization_consumed_20260901_attempt03.json`
5. `reports/m2_a_c03_canary_execution_20260901_attempt03.json`
6. `reports/m2_a_c03_solver_postmortem_20260902_attempt03.json`
7. `reviews/claude_m2_a_c03_attempt03_postrun_review_20260902.json`
8. `studies/canary/m2_a_c03_measurement_20260901_003/adflow_effective_options.json`
9. `studies/canary/m2_a_c03_measurement_20260901_003/solve_report.json`
10. `studies/canary/m2_a_c03_measurement_20260901_003/adflow_run.log`
11. `studies/canary/m2_a_c03_measurement_20260901_003/resource_watchdog.jsonl`

Do not read or inspect the locked holdout contents.

## Terminal attempt03 outcome

- Execution: `m2_a_c03_measurement_20260901_003`.
- Bound launch commit: `579c561368d68aacdda067c978246128b3d27a21`.
- Policy SHA-256:
  `95a70fad10e745d6f8f82267bfd887470b38fb8a77301f430b61d6e2272cfb3c`.
- Mesh SHA-256:
  `be2805ff85b6b1043863d7678d1551a52b6e8a65b299534d4ec0aaeffa51aeb4`.
- Case: A/C03, development index 83, 943,104 cells, one rank, ADflow
  2.13.1 RANS/SA, ANK/NK subspaces 10/20, ILU fill 1/1.
- Terminal status: **`SOLVER_MEASUREMENT_FAILED`**.
- Attempt03 launched exactly once. Its authorization is consumed permanently.
  Never reconstruct or reuse its execute token.
- The host completed the workload: 6 h 39 min watchdog elapsed, no OOM, no
  swap growth, no watchdog stop, and surface output written.
- Peak full-session RSS: 9.855038 GiB. Forecast: 9.45 GiB. Minimum available
  memory: 2.046471 GiB versus the 2 GiB floor. Physical executability was
  demonstrated, but the immutable resource forecast check failed.
- ADflow completed 944 native monitor rows through nonlinear row 943 and total
  minor iteration 20,021, then returned `solve_failed=true`.
- Density `1.202361e-4` and energy `2.586341e-5` failed their `1e-5` limits;
  momentum and SA passed. Force-tail stability passed but is diagnostic only.
- NK practical stagnation: last-200 median linear residual 0.9775, p95 0.997,
  and 98/200 steps at 0.01. The tail decreased slowly and did not diverge.
- y+ failed globally by absolute maximum and in 9/13 regions. All seven
  tip/cap blocks failed; `tip_base` reached p95 5.79 and max 5.86.
- Signed boundary mass balance and interface-field continuity remain unproven.
- Independent post-run review verdict: faithful evidence, desktop execution
  proven, resource/convergence/y+ gates failed, no new CFD authorized.

## Non-negotiable state

- V2, v3 and v4 authorizations are all consumed. Never retry or reuse any of
  them.
- Do not launch ADflow, MPI, a preconditioner build, a short CFD probe, C01,
  C02, C03, a campaign, or a holdout case.
- A "memory probe" that initializes or advances ADflow is a governed heavy
  action and is not authorized by a review alone.
- Do not classify the diagnostic forces as accepted or use them for design
  ranking.
- Do not claim grid independence. C01-to-C02 is not a strong wall-normal step,
  and C03 now has measured local y+ failures.
- Do not change flow physics, turbulence model, mesh identity, mission
  references, convergence limits, watchdog floor, or WSL configuration.
- Do not delete, clean, truncate, regenerate or overwrite any attempt
  directory or immutable record.
- Preserve unrelated user work:
  - `AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/campaign.py`
  - `configs/aero/section_study/stage1_reference_subset.json`
  - `configs/aero/section_study/stage1_summary_subset.txt`

## Evidence retention

The complete attempt directory is:

`studies/canary/m2_a_c03_measurement_20260901_003/`

Retain the case, requested/effective options, static runner, launch record,
combined solver log, ADflow JSON, all 944 residual rows, solve report, all
11,715 watchdog samples, GNU-time output and surface CGNS. The surface file is
retained locally with SHA-256
`3abf9350bd92d66933f3a02fabbc84e62291aa2501534ee2d9531ec1818ab973`;
repository policy permits its hash but not the CGNS file itself to be committed.
No volume or restart state exists.

## Continuation order while Codex is unavailable

Work through these read-only/analysis tasks without waiting for Codex:

1. Inspect `git status` and verify the exact hashes in the postmortem. Preserve
   every unrelated change and every attempt03 artifact.
2. Read the locally installed ADflow 2.13.1 Python and Fortran sources plus its
   shipped documentation. Build a source-cited option map for:
   - NK and ANK preconditioner fill and subspace memory behavior;
   - NK linear tolerances, Jacobian/preconditioner lag and globalization;
   - ANK-to-NK switching and an ANK-biased/ANK-only path;
   - multigrid behavior;
   - restart/volume-solution write and warm-start semantics;
   - any way to compute signed boundary mass flux from retained surface data.
3. Rank candidate numerical fixes by expected convergence benefit, peak-memory
   risk, equation/physics equivalence, need for a cold start and evidence
   strength. Treat stronger NK ILU as a hypothesis, not a proven unique cause.
4. Analyze the retained y+ region map and the S6 surface/volume generator.
   Propose the smallest separately governed wall-normal change that corrects
   `oml_nose`, `oml_base` and all tip/cap blocks while preserving positive
   volume quality. Quantify its expected cell and memory impact. Do not march a
   mesh unless a later human instruction expressly authorizes it.
5. Determine whether signed boundary mass balance and interface discontinuity
   can be computed read-only from the retained surface CGNS. If the necessary
   mass-flux fields are absent, record that fact; do not invent a pass.
6. Draft, but do not activate, a bounded next-action proposal. It must use the
   measured 9.855 GiB peak as a lower-bound memory anchor, preserve a 2 GiB
   floor, require restart/volume-state insurance, change only one numerical
   lever per isolation attempt, and state that no launch is authorized.
7. Update this handoff and `LIVE_STATUS.md` with exact evidence and leave an
   explicit `cfd_authorized: false` statement.

## Required output from the continuation analysis

Return a severity-ranked report answering:

1. Which solver mechanism most likely caused the near-unit NK linear residual,
   and what local source evidence supports that conclusion?
2. What is the lowest-memory option change most likely to clear density and
   energy below `1e-5`?
3. Can it fit while keeping `MemAvailable >= 2 GiB`, using 9.855 GiB—not the
   failed 9.45 GiB forecast—as the baseline?
4. How will the next run retain a valid restart so six hours of work cannot be
   lost again?
5. What minimal local wall-spacing/collar change fixes all measured y+ failures,
   and what cell/memory penalty does it imply?
6. Can the required conservation and interface checks be recovered from the
   retained fields?

Separate measured facts, source-backed behavior, engineering estimates and
untested hypotheses. No review may authorize CFD by itself.

## Gate for any future heavy action

A future CFD or ADflow initialization requires all of the following:

1. new immutable policy and unique attempt ID;
2. corrected resource model and safe live preflight;
3. one isolated numerical or mesh change with source-backed rationale;
4. restart/output retention policy;
5. independent review with no unresolved HIGH finding;
6. green identity/environment/one-shot tests;
7. fresh one-shot token consumed before launch; and
8. explicit human authorization after reviewing the exact proposal.

Until then, `cfd_authorized: false`.

There is deliberately no execute command or reusable token in this handoff.
