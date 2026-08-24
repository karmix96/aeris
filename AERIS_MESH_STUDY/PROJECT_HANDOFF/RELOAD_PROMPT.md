# Reload Prompt

Paste the following into a new Codex/Claude coding session:

```text
Continue the AERIS automated mesh/CFD project from the repository root.

First read every file in AERIS_MESH_STUDY/PROJECT_HANDOFF, then read the canonical
S6 and S7 ROADMAP.md, POLICY.yaml, STUDY.md, README.md, RESEARCH.md, the latest JSON
reports listed in EVIDENCE_INDEX.md, ADR-0011, ADR-0016, ADR-0017, and
COMMON_BRIEF.md.

Check running processes and read QUALIFICATION_UPDATE_2026-08-21.md before
launching anything. Mesh qualification is complete. The N65 laptop pilot finished
3/3 converged, but its coarse y+ screen passed 0/3 and cannot decide the production
wall law. Read its separate `legacy_evidence_audit.json`; the reports are
hash-audited history but are not current-cache compatible. No HPC is currently
available. The next heavy action is one P0 N257 wall-normal canary on at
least 64 GB; measure memory and y+ before more submissions. Do not repeat
completed jobs without invalidating evidence.

Do not use atlas_manifest_frozen_candidate_v3.json: it is obsolete because smoke
validation incorrectly marked it freeze-ready. Do not release or inspect the
locked hold-out until the final production atlas, wall law, CFD policy, fallback,
and gates are frozen. Do not tune on hold-out results. Do not run production
ADflow locally on the 16 GB machine; prepare it for >=64 GB HPC. Never revert or
overwrite unrelated dirty worktree changes.

Be strict about claims: 100/100 production meshes do not prove CFD campaign
readiness, a converged coarse pilot failed y+, and the `3.6e-6` first-cell law
plus numerical TE floor still need production CFD/sensitivity validation. Run
focused tests and independent review after changes. Keep answers brief and in
simple words, but do the engineering
work end-to-end.

S7 Gmsh prism/tetra+SU2 software is now implemented; do not repeat that task. Its
24 focused tests and Ruff pass, but only the Gmsh fixture/fake restart are proved.
`SU2_CFD` is absent and the real BWB smoke was blocked before launch, not failed by
Gmsh. Read S7_RELOAD_AND_CLAUDE_HANDOFF_2026-08-21.md and finish the Opus/max audit
before one bounded real development smoke. Do not run production S7 on this laptop
or touch `round_c_lhs10_seed42`.

After both S6 and S7 have comparable numerical evidence, implement the governed
AERIS structured/unstructured/auto/compare modes, then the AI-assisted mesh research
pipeline described in ROADMAP.md and FUTURE_EXTENSIONS.md.
```
