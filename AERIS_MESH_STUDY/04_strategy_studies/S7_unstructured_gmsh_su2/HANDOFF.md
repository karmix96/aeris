# S7 reload and handoff

Snapshot: 2026-08-21. Status: preregistered development; no accepted real S7 result.

## Reload order

Read these files completely before changing or executing S7:

1. repository `memories/memories.md`;
2. everything under `AERIS_MESH_STUDY/PROJECT_HANDOFF/`;
3. S6 strategy/policy/research/tests plus ADR-0016;
4. `AERIS_MESH_STUDY/04_strategy_studies/COMMON_BRIEF.md`;
5. ADR-0017, then this directory's `POLICY.yaml`, `README.md`, `RESEARCH.md`,
   `STUDY.md`, and `ROADMAP.md`;
6. all S7 Python, shell, prompt, and test files.

The locked set is `round_c_lhs10_seed42`. Its state is `forbidden`. Do not construct
it, mesh it, solve it, inspect its values/plots, or add a bypass.

## Verified local state

- `.venv/bin/python -m pytest -q <S7 directory>`: 24 passed.
- `.venv/bin/python -m ruff check <S7 directory>`: all checks passed.
- Pinned local stack observed earlier in this session: Python 3.13.9, Gmsh 4.15.2,
  NumPy 2.5.1, SciPy 1.18.0, pyGeo 1.17.0, pyspline 1.5.4.
- `SU2_CFD` is absent.
- The Gmsh test is a synthetic closed tetrahedral wall, not a BWB.
- The restart test uses a fake solver, not SU2.
- The real BWB laptop smoke was blocked before launch by Codex sandbox/usage
  approval. Do not label it a mesh failure or attempt an indirect workaround.
- Retained synthetic optimizer diagnostics are older-source evidence and are never
  accepted campaign artifacts.
- The prior Claude Opus/max attempt is retained under
  `AERIS_MESH_STUDY/artifacts/strategy_studies/S7_unstructured_gmsh_su2/claude/implementation_audit_20260821_01/`;
  it hit the session limit and is not a completed review.

## Important implementation invariants

- The pyGeo wall is full-wing, independently triangulated, and fixed inside every
  retry. Gmsh surface algorithms do not remesh it.
- The numerical-TE baseline is 1.0 mm with fixed 0.5 and 1.5 mm sensitivity members.
- Node and facet-centroid fidelity, closure/orientation/intersections, exact labels,
  zero inverted/zero-volume cells, prism coverage/schedule, face/cell quality, and
  TE/tip prism-to-core continuity all fail closed.
- Post-generation relocation is disabled because it altered prism layers.
- Flow is exactly the frozen cruise mapping; supplied values and full-wing reference
  quantities must equal the canonical pyGeo values.
- Attempts are immutable. A stale/incomplete/tampered artifact is investigated or a
  new output root is used; it is never repaired in place.
- `mesh` and `cruise` case identities are separate. `accepted` is scoped technical
  acceptance; `campaign_ready` stays false.
- Qualification accepts only adjacent digest-verified case terminals for fixed
  indices 0/24/49/74/99, matching design/flow/reference identity and current source,
  policy, and software preflight.

## Next safe actions

1. Finish a successful read-only Claude audit using
   `/home/mike/.local/bin/claude --model opus --effort max`; preserve command,
   reported model usage, output, errors, and terminal hashes.
2. On a later authorized local run, execute exactly one `laptop_smoke` BWB case and
   inspect geometry/TE/tip behavior. Do not run all 100 on this laptop merely to
   produce a count.
3. Install/pin SU2 8.5.0 on a qualified desktop/HPC environment and perform one
   bounded development solver smoke.
4. Use Slurm arrays for production-resolution development meshes, then the fixed
   10–20 pilots and five grid/TE groups.
5. Keep the hold-out locked until a new explicit governance decision.

Exact commands and evidence interpretation are in `README.md`. Any common Gmsh
failure triggers a superseding ADR, not gate weakening. Preserve failed attempts as
scientific evidence and clearly distinguish implementation proof from numerical
qualification.
