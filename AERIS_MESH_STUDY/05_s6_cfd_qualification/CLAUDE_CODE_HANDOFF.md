# Claude Code continuation order — S6 qualification

You are continuing the AERIS S6 automated CFD qualification study in a shared
Linux-native repository. Read these files first, in order:

1. `MASTER_EXECUTION_GUIDE.md`
2. `SESSION_RESUME.md`
3. `LIVE_STATUS.md`
4. `POLICY.yaml`
5. `reports/m1_contract_status.md`
6. `reports/audit_geometry_space.json`
7. `host/m1_20260830/m1_gate.json`
8. `reports/m2_grid_screen_terminal_report.md`
9. `reports/m2_grid_screen_terminal_report.json`
10. `reports/m2_coupled_family_respec_20260831.json`
11. `reports/m2_wall_spacing_yplus_preflight_20260831.json`

## Non-negotiable safety order

- The coupled family has an independent GO for exactly one measurement-only
  A/C03 canary. Do not launch it until the exact launcher commit receives a
  read-only wiring review and its fresh preflight passes. The direct-march
  NO-GO remains historical.
- Do not inspect, parse, sample, visualize, copy, or hash the locked holdout
  sample contents. Only use its lock metadata.
- Do not alter the live geometry YAML, governance snapshots, unrelated user
  changes, WSL registration, VHDs, or backup files.
- Do not delete or clean broad directories. The policy is
  `explicit_human_approval_only`.
- Keep every generated result immutable and small; never commit CGNS, restart,
  field, or other large solver artifacts.

## Current terminal state

- M0/M1 deterministic work is complete at commit `752852c`.
- The redesigned coupled family uses collar counts `5 -> 6 -> 7`, wall-spacing
  fractions `5.0e-6 -> 4.7e-6 -> 3.6e-6`, and 191,520 -> 422,352 -> 943,104
  cells (`r_eff=1.3016, 1.3071`).
- Independent ADF-CGNS reopening and repository-authority volume QC reject the
  direct-march nominal mesh. The best C03 attempt still has six inverted cells
  and `qmin=-0.3114098210`.
- Proven S6 remains the route: valid S1/Openblademesh volume followed by exact
  S6-wall deformation. C01/C02/C03 now pass the production floor on A/B/C/E;
  C03 geometry C uses the governed target-specific S1 fallback with identical
  global settings. Evidence: `reports/m2_coupled_family_respec_20260831.json`.
- The C02 family evidence has been independently reproduced (hashes plus a
  fresh ADF reopen and volume QC of all six meshes).
- The old C03 fold is attributed to its 9-point tip-cap collar. Re-specifying
  the coupled collar ladder to `5/6/7` removes the fold while retaining the
  finer 3.6e-6 C03 wall-spacing fraction; the rejected 6.1e-6 path is retained.
- R1-R3 are closed by the coupled re-spec, synchronized candidate registries,
  regression coverage, A/B/C/E written-CGNS evidence, and the independent
  review in `reviews/claude_m2_coupled_family_review_20260831.json`.
- Flat-plate preflight y+ used full first-cell height and is not acceptance
  evidence. ADflow uses the first-cell centroid, so the expected values are
  about half; only the governed canary can measure them.
- Earlier Claude review attempts timed out and are retained as transport
  history. A later independent review completed and issued the bounded GO.
- An independent Claude Code review of `dbf918f` is now COMPLETE and closes
  R1/R2/R3: `reviews/claude_m2_coupled_family_review_20260831.json`. All twelve
  claimed family meshes were reopened and reproduce exactly; realized OML
  first-cell medians order C01 > C02 > C03 for every geometry, and the cap
  orders too. It issues a **GO for exactly one measurement-only A/C03 canary**
  on `m2_coupled_family_20260831/candidate_c03/lhs100_seed42_083/wing_vol_deformed.cgns`
  (`be2805ff...`, 943,104 cells, `qmin=0.1671`).
- GO conditions, all binding: no ACCEPTED classification until a numeric y+
  limit and its wall-distance convention are in the immutable policy; state the
  y+ convention when reporting, because ADflow's cell-centred y+ reads about
  half the preflight numbers (A/C03 OML p95 `0.74`, not `1.47`); run under a
  memory watchdog (forecast 9.35 GiB against 11.47 GiB available, 0.12 GiB of
  margin); one run, geometry A, development set, holdout untouched; and wiring
  `run-canary` is itself a governed change that must keep every other heavy
  command blocked.
- Non-blocking findings carried forward: C01 to C02 is not a wall-normal
  refinement step; C/C03 needs a geometry-specific template; the y+ preflight
  has no committed generator and ungoverned limits; two `grid_screen` gate
  defaults are permissive; the memory forecast cannot fail on the finest level.
- The one-shot launcher now binds the exact reviewed mesh/flow/reference
  contract, freezes numeric cell-centroid y+ gates, keeps all other heavy work
  blocked, consumes authorization before process start, forbids retry and
  ACCEPTED, and uses a memory/swap/disk/OOM watchdog.
- It retains every CFD log and evidence artifact except the volume solution,
  which stays disabled under the reviewed resource envelope. Native histories
  include density, x/y/z momentum, energy, SA, CL/CD/CMy and CDp/CDv.
- The acceptance contract remains honestly CONDITIONAL because the current
  continuity-residual ratio is not the governed signed boundary-flux mass
  balance. The canary is measurement-only, so this gap cannot be hidden by an
  ACCEPTED verdict.
- Latest focused verification: 73 passed. Zero-launch preflight passes 43
  identity/governance checks, 18 solver-environment checks, and all resource
  checks. No CFD has been launched; the one-shot authorization is unconsumed.
- Commit `e660899` is retained. A post-commit audit found that the legacy
  solver resolver defaulted to nonexistent `/home/mike/...`; it was caught
  before any CFD launch or authorization consumption. Immutable canary policy
  v1 remains unchanged. Policy v2 supersedes it and binds the real
  `/home/mike_kara/miniconda3/envs/mach-aero` environment, exact versions and
  hashes, explicit RANS/SA/history/output controls, and a pre-consumption
  one-rank non-CFD MPI readiness probe.
- The static v2 environment/import audit is green, exact prepare-only coverage
  is green, and an out-of-sandbox probe returned `AERIS_MPI_READY 0 1`.
- A read-only Opus/max review of `e660899` timed out with no verdict and no
  workspace mutation. Do not mistake that transport failure for a NO-GO or GO.

## Execute next, in order

1. Inspect the current commit and working tree. Preserve the three unrelated
   user changes and do not stage them.
2. Perform a read-only adversarial review of the exact current launcher commit. Verify
   all reviewed caps, mesh/mission/reference hashes, full residual/log capture,
   one-shot consumption, no-retry behavior, watchdog termination, and the
   impossibility of ACCEPTED classification. Do not run CFD during the review.
3. Return an explicit `GO_ONE_MEASUREMENT_CANARY` or `NO_GO`, with severity and
   file/line evidence. Record the review under `reviews/`.
4. If and only if GO, run the focused suite and `run-canary --dry-run` again.
5. Execute the one-shot token exactly once, monitor it, retain all artifacts,
   and do not retry under any outcome. Never touch the holdout.
6. Postprocess and report the result as measurement-only. Do not authorize
   C01/C02, broader campaigns, grid independence, or ACCEPTED.
7. Update `LIVE_STATUS.md`, retain small evidence, and commit only governed
   files. Never commit CGNS/restart/field artifacts; do not push without the
   user's instruction.

## Claude review order

Perform a read-only Opus/max adversarial review of the exact current launcher
commit and the bound M2 GO. Challenge identity, moment/reference and Reynolds
semantics, native residual naming/normalization, immutable classification,
complete artifact retention, one-shot durability, watchdog safety, and the
honest boundary-flux gap. Record model, version, scope, commit, result, and
findings under `reviews/`. Do not launch CFD in the review process.

## Continuation behavior

Continue this order through the sole measurement result or a governed NO-GO.
If the Codex session ends, start here and work independently within these
constraints; never consume the token twice.
