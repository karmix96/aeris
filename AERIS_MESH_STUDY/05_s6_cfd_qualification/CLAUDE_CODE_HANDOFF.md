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

- Do not launch CFD or a canary until the redesigned coupled family receives
  the required independent GO. The direct-march NO-GO remains historical.
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
- R1-R3 are mechanically closed by the coupled re-spec, synchronized candidate
  registries, a regression test, and A/B/C/E written-CGNS evidence. They still
  require independent review of the new evidence.
- Flat-plate preflight y+ remains a high risk: estimated C03 all-wall p95 is
  1.68-2.17 and maximum 9.98-14.59. This is not measured y+; only one governed
  C03 canary can qualify it.
- Two automated Claude Opus review attempts for `a92bf10` timed out with zero
  tokens. No independent GO exists; see
  `reviews/claude_a92bf10_review_attempts_20260831.json`.
- Three authenticated Claude Code review attempts timed out with zero model
  tokens. No independent GO exists; see `reviews/claude_m0_m1_review_attempt0*.json`.

## Execute next, in order

1. Inspect git status and preserve the three pre-existing unrelated user
   changes. Do not stage them.
2. Independently reproduce `m2_coupled_family_respec_20260831.json`, including
   the target-specific C/C03 route and exact output hashes.
3. Verify candidate spacing registries agree and the 5/6/7 collar plus
   5.0/4.7/3.6e-6 spacing ladders are monotonic.
4. Review the preflight y+ calculation as an estimate only; do not treat it as
   measured acceptance evidence.
5. If no HIGH finding remains, issue the M2 independent GO for one A/C03
   canary. Do not authorize C01/C02 CFD until that canary is classified.
8. Run focused qualification/meshing tests after every governed change. The
   repository-wide suite currently cannot collect in this WSL environment
   because optional project dependencies such as `aerosandbox` are absent.
9. Update `LIVE_STATUS.md`, retain small evidence, and commit only governed
   files. Never commit CGNS/restart/field artifacts; do not push without the
   user's instruction.

## Claude review order

When Claude service transport works, first perform a read-only Opus adversarial
review of commit `752852c` and the M2 terminal evidence. Challenge geometry
identity, moment/reference semantics, residual normalization, immutable
classification, ADF audit independence, and the decision to stop before CFD.
Record model, version, prompt scope, commit, result, and findings under
`reviews/`. Do not claim GO until all HIGH findings are closed. If transport
fails again, retain the failure and preserve the review gate.

## Continuation behavior

Continue this order until the redesigned nominal family is independently
volume-valid or a new governed NO-GO is established. If the Codex session ends,
start here and work independently within these constraints.
