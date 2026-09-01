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
6. `reports/m2_coupled_family_respec_20260831.json`
7. `reports/m2_a_c03_canary_authorization_consumed_20260831.json`
8. `reports/m2_a_c03_canary_execution_20260831.json`
9. `reports/m2_a_c03_resource_blocked_postmortem_20260901.json`
10. `studies/canary/m2_a_c03_measurement_20260831_001/launch_record.json`
11. `studies/canary/m2_a_c03_measurement_20260831_001/adflow_run.log`
12. `studies/canary/m2_a_c03_measurement_20260831_001/resource_watchdog.jsonl`

## Non-negotiable safety state

- The one authorized measurement-only A/C03 canary has already run. Its
  authorization is consumed permanently. **Do not launch or retry CFD.**
- Never reuse or reconstruct the old execute token.
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

Focused verification is **77 passed**. The consumed-state dry-run test must
remain permanently blocked and launch nothing.

## Execute next, in order

1. Inspect `git status`. Preserve these unrelated user changes if still
   present:
   - `AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/campaign.py`
   - `configs/aero/section_study/stage1_reference_subset.json`
   - `configs/aero/section_study/stage1_summary_subset.txt`
2. Independently recompute the hashes of every retained canary artifact and
   compare them with the immutable execution and postmortem records.
3. Independently parse all 16 expanded monitor rows and audit the watchdog
   samples. Report any mismatch with exact file/line evidence. Do not run CFD.
4. Perform a read-only Windows/WSL resource audit: physical RAM, WSL cap, swap,
   current headroom, and whether raising the WSL cap is safe for the Windows
   host.
5. Review ADflow/PETSc memory controls against the exact solver version and
   current options. Separate evidence-backed reductions from speculation. Do
   not change the governed solver policy during the audit.
6. Replace the old 9.35 GiB anchor with a proposed conservative model based on
   the observed 9.864723 GiB drop plus explicit safety headroom.
7. Write a short resource recommendation with alternatives:
   - add/allocate more physical RAM;
   - reduce solver memory while retaining the same mesh and scientific
     contract;
   - or declare this host unsuitable for C03 and defer.
8. Update `LIVE_STATUS.md` and this handoff with findings. Commit only small,
   governed evidence/code; never commit CGNS, restart, surface/volume field, or
   other large artifacts.
9. Stop before any CFD. A future solve requires a new immutable one-shot policy,
   fresh independent review, demonstrated memory headroom, and explicit user
   authorization.

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

Do not turn a resource audit into a scientific GO. No prior review authorizes a
second launch.

## Continuation behavior

If Codex runs out of credits, continue the ordered read-only audit above and
leave both status files current. Do not wait for Codex if useful read-only
evidence work remains. Stop at the authorization boundary: no CFD, no holdout,
no policy mutation, and no destructive cleanup.
