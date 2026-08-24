# AERIS Mesh/CFD Project Handoff

Last updated: 2026-08-21 (Europe/Athens)

This folder is the restart point when a Codex or Claude session loses context.
It summarizes the current state; the linked source reports remain authoritative.

## Read in this order

1. `LIVE_STATE.md` - newest result, active process, and exact next command.
2. `S7_RELOAD_AND_CLAUDE_HANDOFF_2026-08-21.md` - unstructured route state,
   evidence boundary, and exact safe continuation.
3. `CURRENT_STATUS.md` - what is running and what has actually passed.
4. `DECISIONS.md` - frozen technical choices and strategy status.
5. `RISKS_AND_OPEN_GATES.md` - what is not yet proved.
6. `NEXT_ACTIONS.md` - exact continuation order and commands.
7. `EVIDENCE_INDEX.md` - canonical artifacts and obsolete files.
8. `CONTEXT.md` - goal, architecture, papers, and future work.
9. `CLAUDE_REVIEW.md` - independent Claude Code assessment.
10. `CLAUDE_CONTINUATION.md` - safe work Claude can continue while Codex reloads.
11. `CLAUDE_WORK_LOG.md` - append-only record of temporary Claude work.
12. `RELOAD_PROMPT.md` - prompt for a new coding-agent session.

## One-line state

S6 is not campaign-ready. The final 21-template mesh atlas passed the independent
100/100 production-resolution audit and is a frozen candidate. Production CFD,
y+, grid convergence, and hold-out validation remain open. S7 now has a complete
Gmsh/SU2 software path with 24 passing focused tests, but no real BWB mesh or SU2
result; its hold-out is also locked.

## Canonical project files

- `../04_strategy_studies/S6_bounded_mesh_atlas/ROADMAP.md`
- `../04_strategy_studies/S6_bounded_mesh_atlas/POLICY.yaml`
- `../04_strategy_studies/S6_bounded_mesh_atlas/STUDY.md`
- `../04_strategy_studies/S6_bounded_mesh_atlas/RESEARCH.md`
- `../04_strategy_studies/S6_bounded_mesh_atlas/README.md`
- `../04_strategy_studies/S7_unstructured_gmsh_su2/HANDOFF.md`
- `../04_strategy_studies/S7_unstructured_gmsh_su2/POLICY.yaml`
- `../04_strategy_studies/S7_unstructured_gmsh_su2/README.md`
- `../../memories/memories.md`

Do not treat this handoff as a substitute for JSON evidence, source hashes, or
governance ADRs. Update it after every material validation result or decision.
