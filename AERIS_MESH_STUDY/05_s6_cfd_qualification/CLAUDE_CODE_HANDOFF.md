# Claude Code continuation order — S6 qualification

This is the live handoff for continuing the AERIS S6 automated CFD
qualification study. Work in the existing Linux-native repository and preserve
the evidence chain.

Read these files first, in order:

1. `MASTER_EXECUTION_GUIDE.md`
2. `SESSION_RESUME.md`
3. `LIVE_STATUS.md`
4. `POLICY.yaml`
5. `reviews/claude_m2_coupled_family_review_20260831.json`
6. `reviews/claude_m2_c03_resource_plan_review_20260901.json`
7. `reports/m2_coupled_family_respec_20260831.json`
8. `reports/m2_a_c03_canary_authorization_consumed_20260831.json`
9. `reports/m2_a_c03_canary_execution_20260831.json`
10. `reports/m2_a_c03_resource_blocked_postmortem_20260901.json`
11. `reports/m2_a_c03_memory_correction_plan_20260901.json`
12. `policies/m2_a_c03_canary_v3.yaml`
13. `studies/canary/m2_a_c03_measurement_20260831_001/launch_record.json`
14. `studies/canary/m2_a_c03_measurement_20260831_001/adflow_run.log`
15. `studies/canary/m2_a_c03_measurement_20260831_001/resource_watchdog.jsonl`

## Non-negotiable safety state

- The v2 measurement-only A/C03 canary has already run. Its authorization is
  consumed permanently. **Never launch or retry v2.**
- Never reuse or reconstruct the old execute token.
- The user explicitly authorized one fresh resource-corrected A/C03 attempt.
  Policy v3 now hash-binds the independent `GO_RESOURCE_PLAN`; do not launch if
  any exact-commit, MPI, identity, resource, environment or one-shot preflight
  gate is red.
- Do not run C01, C02, another C03, TMR, wall/TE/farfield studies, development
  campaigns, or holdout cases without a new immutable authorization and
  explicit user approval.
- Do not inspect, parse, sample, visualize, copy, or hash the locked holdout
  contents. Its lock metadata is the only permitted holdout input.
- Do not classify this result ACCEPTED. It is measurement-only,
  non-converged, and has no surface/y+ output.
- Do not alter live geometry YAML, governance snapshots, WSL registration,
  VHDs, backup files, or unrelated user work.
- Never delete or broadly clean results. Keep the existing evidence immutable.

## Terminal outcome to reproduce

- Execution: `m2_a_c03_measurement_20260831_001`.
- Bound commit: `e4829b0f327e2a6dd199d8c87d84217c36a8ccda`.
- Mesh SHA-256:
  `be2805ff85b6b1043863d7678d1551a52b6e8a65b299534d4ec0aaeffa51aeb4`.
- Solver: ADflow 2.13.1, one MPI rank, RANS/SA, A/C03, development index 83.
- Terminal status: **`RESOURCE_BLOCKED_HOST`**.
- Elapsed time: 339.6016 s.
- Watchdog trigger: available memory 1.964928 GiB below the governed 2.0 GiB
  floor.
- Forecast: 9.35 GiB. Measured available-memory drop: 9.864723 GiB.
  Underprediction: 0.514723 GiB.
- No OOM kill and no material swap growth.
- Sixteen native monitor rows exist, through completed iteration 15.
- Density fell `396.30185 -> 0.0636363`; total residual fell
  `1.409082e6 -> 2361.3372`. This was not convergence.
- No surface solution was written, so no measured cell-centroid y+ exists.
- The outcome is a host-resource finding, not a mesh-quality verdict.

## Evidence-retention state

The complete small attempt directory is retained at:

`studies/canary/m2_a_c03_measurement_20260831_001/`

It contains the case, launch record, requested and effective options, static
runner, combined solver log, complete watchdog timeline, solve report, and
GNU-time file. No large surface/volume/restart artifact was produced.

The post-run parser now supports both legacy and expanded ADflow monitor rows
and retains every component without positional shifts. Its regression test uses
the actual final completed row. The structured postmortem contains all 16
re-parsed rows.

Focused verification is **78 passed**. The one-shot dry-run test must reflect
the current v3 state, launch nothing, and preserve the v2 terminal summary.

## Resource-corrected v3 state

- The desktop has 16 GB physical RAM, four reported slots, two installed 8 GB
  modules, and a 64 GB board limit. WSL remains capped at 13 GB with 8 GB swap.
- Exact ADflow source maps default `ANKSubspaceSize=-1` to
  `ANKMaxIter=40`. The v2 policy constrained `NKSubspaceSize=20` but left this
  earlier ANK allocation unbounded.
- The v2 log used at most 8 linear iterations per nonlinear step. V3 sets
  `ANKSubspaceSize=10` and retains `NKSubspaceSize=20` and ILU fill 2.
- Thirty removed five-state basis vectors are a lower-bound 1.0540 GiB saving.
  The v3 forecast is 9.25 GiB: 0.4393 GiB above the vector-subtraction estimate
  and 73.04 percent of WSL-visible RAM.
- Current preflight leaves about 0.49 GiB beyond the mandatory 2 GiB headroom.
- The watchdog now sums RSS by POSIX session, because OpenMPI descendants did
  not remain in the time wrapper's process group during v2.
- Claude Sonnet 5 returned `GO_RESOURCE_PLAN` with no HIGH findings. Its review
  is committed at `591bf90`, hash-bound into v3, and all dry identity/resource/
  environment/one-shot checks are green. No v3 CFD has launched or consumed
  authorization.

## Execute next, in order

1. Inspect `git status`. Preserve these unrelated user changes if still
   present:
   - `AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/campaign.py`
   - `configs/aero/section_study/stage1_reference_subset.json`
   - `configs/aero/section_study/stage1_summary_subset.txt`
2. Verify the committed resource-review binding and perform a final read-only
   exact-commit wiring review. Any HIGH finding closes the launch gate.
3. Run the focused suite and a dry preflight. The exact expected state before
   launch is: every identity/resource/environment check green; v3 consumed
   record absent; v3 attempt directory absent; process not launched.
4. If and only if all gates are green, execute exactly one v3 A/C03 process
   under the existing watchdog. Authorization must be consumed before process
   start. Do not retry under any terminal outcome and never touch the holdout.
5. Retain and hash every small log, residual history, watchdog sample, options
   file, surface/y+ result and terminal record. Never commit CGNS, restart,
   surface/volume field, or other large artifacts.
6. Update both handoffs and commit only governed study work. GitHub push remains
   separately blocked until the user authenticates this desktop.

## Review questions

Return a severity-ranked, evidence-backed answer to:

1. Did the watchdog stop occur exactly under policy, without OOM or swap-growth
   ambiguity?
2. Is the 9.864723 GiB available-memory drop a sound peak anchor, or do the raw
   samples justify a higher value?
3. How much total WSL-visible memory is required to preserve at least 2 GiB
   headroom plus forecast uncertainty?
4. Which exact ADflow/PETSc options can reduce peak memory without changing the
   turbulence model, mesh, flow point, convergence semantics, or one-rank
   identity?
5. Is the Windows host physically capable of a safe larger WSL allocation?

Do not treat the resource review alone as a scientific GO. The existing mesh
GO, the new resource review, green exact preflight, and the user's explicit
one-run instruction are all required together.

## Continuation behavior

If Codex runs out of credits, continue the ordered review and v3 gate closure
above and leave both status files current. Do not wait for Codex while useful
evidence work remains. The only permitted heavy action is the one v3 A/C03 run
after every listed gate is green; under any ambiguity stop with no CFD. Never
touch the holdout or perform destructive cleanup.
