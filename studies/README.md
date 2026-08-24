# AERIS studies

## Active

- **`PLAN_avl_panelling_study.md`** — why the AVL panelling study is designed the
  way it is. Read this first.
- **`RUNBOOK_avl_panelling_for_codex.md`** — the execution specification. 1,041
  runs, stage-gated, hand to Codex.

## Standing

- `native_avl_output_and_fidelity.md` — DECISION-0005
- `native_avl_physics_validation.md` — DECISION-0008
- `pygeo_native_vs_asb_avl_doe.md` — DECISION-0007
- `pygeo_vs_aerosandbox_geometry.md` — DECISION-0003
- `trailing_edge_thickness.md` — DECISION-0004

## Superseded and removed 2026-07-28

All panelling and section-placement studies, DECISIONs 0009–0014, their evidence
folders and raw runs were deleted. They were mutually inconsistent, and a
re-analysis showed their rankings inverted under any reasonable change of score.
Summaries are preserved in `archive/superseded_avl_studies_2026-07-28.tar.gz`;
tracked files remain recoverable from git history.

**The settings currently in `configs/geometry/bwb.yaml` are therefore PROVISIONAL
and carry no written justification until the panelling study completes.** They
still run correctly; they are simply not yet defended.
