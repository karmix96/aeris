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

## Non-negotiable safety order

- Do not launch CFD, mesh generation, parallel heavy jobs, or canary runs.
- Do not inspect, parse, sample, visualize, copy, or hash the locked holdout
  sample contents. Only use its lock metadata.
- Do not alter the live geometry YAML, governance snapshots, unrelated user
  changes, WSL registration, VHDs, or backup files.
- Do not delete or clean broad directories. The policy is
  `explicit_human_approval_only`.
- Keep every generated result immutable and small; never commit CGNS, restart,
  field, or other large solver artifacts.

## Execute next, in order

1. Inspect the current git status and preserve the three pre-existing unrelated
   user changes. Do not stage them.
2. Strengthen M1 tests and schemas using existing AERIS backends rather than
   duplicating QC. Implement safe, read-only checks for:
   - deterministic geometry identity/cache invalidation, including the 29x75
     identity regression;
   - explicit moment references (quarter-MAC and mission CG);
   - residual fields (momentum, energy, SA) and normalized mass imbalance;
   - terminal-state and classification-policy separation.
3. Extend `run.py` with only audit/dry-run handlers until all M0–M2 gates are
   machine-green. Heavy handlers must continue returning `BLOCKED`.
4. Add focused pytest tests for each new invariant. Run:
   `.venv/bin/pytest -q AERIS_MESH_STUDY/05_s6_cfd_qualification/tests`
5. Run `audit-contract`, `audit-geometry-space`, `check-half-domain`, and
   `check-holdout-lock`; save small JSON evidence under `reports/`.
6. Update `LIVE_STATUS.md` with the new commit, test result, and remaining
   gates. Commit only governed qualification files with a descriptive message.
7. Attempt no push unless credentials are already available; report push as
   pending if authentication fails.

## Claude review order

When Claude authentication/session transport works, perform a read-only Opus
adversarial review of the M0/M1 diff and evidence. Record the exact model,
version, prompt scope, commit, result, and any findings under `reviews/`.
Do not claim GO until all HIGH findings are closed. If transport fails, record
the failure and continue with deterministic local tests.

## Continuation behavior

Continue this order until the next safe gate is complete or an external choice
is required (mission authority, geometry freeze, or credentials). If the Codex
session ends, start here and work independently within these constraints.
