# Claude Continuation Note

Use this when Codex credits are exhausted and Claude Code must continue the work
until Codex reloads.

## Prompt to give Claude Code

```text
Act as the temporary lead engineer for the AERIS automated mesh/CFD project.
Start at repository root and read LIVE_STATE.md first, then every file in
AERIS_MESH_STUDY/PROJECT_HANDOFF. Then read the canonical S6 ROADMAP.md,
POLICY.yaml, STUDY.md, README.md, RESEARCH.md, ADR-0011, COMMON_BRIEF.md, and the
latest JSON artifacts in EVIDENCE_INDEX.md.

Check running processes and checkpoints before starting commands. Continue only
the next incomplete item in NEXT_ACTIONS.md. Work end-to-end: inspect evidence,
make closely scoped fixes if needed, add tests, run verification, and update the
handoff files. Record every command/result and code change in
AERIS_MESH_STUDY/PROJECT_HANDOFF/CLAUDE_WORK_LOG.md so Codex can audit and resume.

Immediate priority: read QUALIFICATION_UPDATE_2026-08-21.md, then follow the
exact next action in LIVE_STATE.md. Mesh-atlas qualification is complete, and the
N65 laptop pilot finished 3/3 converged with 0/3 strict coarse y+ passes. This
proves the local solver/rejection path only. The next CFD action is one P0 N257
wall-normal development canary on hardware with at least 64 GB RAM;
measure memory and y+ before submitting more cases. Do not run the ten-case helper
unchanged for the first canary. Do not inspect the locked hold-out or run
production ADflow on this 16 GB machine.

Read CLAUDE_OPUS_MAX_REVIEW_2026-08-21.md for the completed independent review
findings and their closure. Do not reopen fixed findings without new evidence.

Read `artifacts/s6_bounded_mesh_atlas/qualification_v1/laptop_cfd/legacy_evidence_audit.json`
before using the N65 evidence. The old reports are integrity-checked history, not
current-cache-compatible results. When Codex invokes Claude for review, the user
requires the latest Opus model with maximum effort: `--model opus --effort max`.
The preserved v1 plan was written after the pilots and is not preregistration
evidence. Use the final v3 plan. Production cache identity must include MPI and
the solver-artifact hashes; do not weaken this.

Do not use the obsolete atlas_manifest_frozen_candidate_v3.json. Do not relax
quality, y+, fidelity, convergence, or force gates to make results pass. Do not
change the TE law, production wall law, atlas membership, fallback order, or CFD
policy without recording a reason and marking prior evidence stale. Preserve all
failed attempts and unrelated dirty worktree changes. Never claim campaign
readiness from smoke evidence.

Before stopping, update LIVE_STATE.md, CURRENT_STATUS.md, NEXT_ACTIONS.md, EVIDENCE_INDEX.md,
RISKS_AND_OPEN_GATES.md, memories/memories.md, and CLAUDE_WORK_LOG.md. State what
is proved, what failed, what changed, test results, active process IDs/checkpoint
paths, and the exact next command. Leave no required process unmonitored.
```

## Work Claude may do

- Verify final artifacts and improve laptop-safe HPC preparation or recovery.
- Diagnose development-set failures and correct real implementation defects.
- Add focused tests and strengthen provenance, recovery, or validation logic.
- Analyze reports and update status/evidence documents.
- Prepare production HPC jobs and dry-run manifests without pretending they ran.
- Prepare true grid-family and TE-sensitivity inputs without claiming CFD results.
- Independently challenge S6 logic and paper alignment with file-level evidence.

## Work Claude must not do

- Open, generate, route, or tune against the locked hold-out.
- Lower a gate or hide a failed attempt to obtain a pass.
- Use smoke meshes in a production registry.
- Run the memory-heavy P0 N257 ADflow case on this local machine.
- Start the Gmsh/SU2 or AI phase while an S6 production blocker is unresolved,
  unless the user explicitly changes priority.
- Delete historical artifacts or revert unrelated user changes.

## Handoff back to Codex

Claude should create or append `CLAUDE_WORK_LOG.md` with:

- timestamp and scope;
- commands run and exit state;
- files changed;
- artifact paths and source hashes;
- exact numerical results and failures;
- tests/lint run;
- policy or evidence invalidated;
- running jobs/checkpoints;
- one exact next action.

Codex should audit that log and the underlying JSON/code before accepting any
claim. Claude's prose is review input, not primary evidence.
