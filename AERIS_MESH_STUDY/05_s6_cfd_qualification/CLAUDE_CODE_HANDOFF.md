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

## Non-negotiable safety order

- Do not launch CFD or a canary. The direct-march M2 experiment is terminal
  NO-GO because every written nominal mesh tested has inverted cells.
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
- The candidate `17x43x61 -> 23x57x73 -> 29x75x97` family passes coupled
  refinement and desktop resource gates.
- Independent ADF-CGNS reopening and repository-authority volume QC reject the
  direct-march nominal mesh. The best C03 attempt still has six inverted cells
  and `qmin=-0.3114098210`.
- Proven S6 remains the preferred route: reuse a valid S1/Openblademesh volume
  and apply bounded exact-wall deformation. The C02 production family now
  passes: geometry A plus independent B/C/E all have zero inverted cells and
  `qmin >= 0.1545`. Evidence: `reports/m2_proven_route_family_20260830.json`.
- C03 finest remains a diagnostic NO-GO (4 tip-cap inversions,
  `qmin=-0.2468`); do not weaken the zero-inversion gate or call it production.
- The C02 family evidence has been independently reproduced (hashes plus a
  fresh ADF reopen and volume QC of all six meshes).
- The C03 failure is now attributed: the S1 C03 template volume already fails
  the hard gate before deformation (`qmin=-0.2448`, same 20 negative cells in
  `tip_base`). The bounded deformation is exonerated. A nine-march controlled
  search found one clean C03 route - relax the finest-level first-cell fraction
  from `3.6e-6` to `6.1e-6`, which deforms to the exact wall with zero
  inversions and `qmin=+0.1267` - but that inverts the ladder's wall-spacing
  ordering and has NOT been adopted. Evidence:
  `reports/m2_c03_tipcap_diagnosis_20260830.json`.
- Two open review findings must be closed before the canary: F1 (the committed
  C01 rung was marched off the frozen wall-spacing ladder) and F2 (the affine
  map rescales wall-normal spacing, so per-geometry y+ is not preserved).
- C01 B/C/E screens are complete; B and E pass the production floor, while C
  is positive-volume but below the `qmin=0.10` production floor (`qmin=0.0840`).
- The resolution policy now records C01=`5.0e-6` and repaired C03=`6.1e-6`.
  The C01 probe passes A/B/C/E (`qmin >= 0.1091`, zero inversions). Review
  this non-monotone fraction/physical-spacing rationale before CFD; do not run
  CFD yet.
- That review is done and is NOT a GO
  (`reviews/claude_m2_spacing_policy_review_20260830.json`). The probe numbers
  and the repaired C03 mesh reproduce exactly, but the non-monotone rationale
  fails on the aerodynamic wall: realized OML first-cell spacing is coarser at
  C03 than at C01 (medians `8.37e-6..1.08e-5` m against `6.47e-6..7.29e-6` m);
  only the tip-cap blocks get finer. Two HIGH findings are open - R1 (ladder
  coarsens the wall as it refines the grid) and R2 (`GRID_LEVELS` in
  `src/aeris/cfd/meshing/pyhyp_options.py` still holds the retired fractions
  and is the silent fallback for callers that omit `s0_fraction_override`,
  including `march_s1.prepare`). R3 records that repaired C03 has geometry A
  only. Close R1-R3 and compute realized y+ before any canary.
- CFD canary remains blocked pending independent review and a governed decision
  on whether C02 is the production resolution or C03 is repaired.
- Three authenticated Claude Code review attempts timed out with zero model
  tokens. No independent GO exists; see `reviews/claude_m0_m1_review_attempt0*.json`.

## Execute next, in order

1. Inspect git status and preserve the three pre-existing unrelated user
   changes. Do not stage them.
2. Treat `reports/m2_grid_screen_terminal_report.json` as the governing M2
   diagnosis. Verify its hashes and attempt records before changing topology.
3. Retain the successful geometry-A recovery evidence and locate/regenerate the
   remaining proven S1/Openblademesh template volumes; bind each by hashes and
   a new experiment identity.
4. Build the exact S6 target surface, then use bounded S1-volume-to-S6-wall
   deformation. Do not direct-march the exact wall as the first recovery route.
5. Start with cheap surface/interface checks, then independently close, reopen,
   and audit each written deformed CGNS. Geometry A is the reference recovery.
6. The C02 production family is valid for A/B/C/E; C03 is retained as a
   diagnostic failure requiring either repair or explicit governed waiver.
   Do not adopt the relaxed `6.1e-6` C03 wall spacing without a human decision,
   and do not present it as a repair of the frozen C03 rung.
7. Keep CFD and the canary blocked until nominal A and the required geometry
   screens all satisfy the roadmap gates.
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
