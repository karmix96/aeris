# Evidence Index

Paths are relative to repository root.

## Canonical S7 source and current evidence boundary

- Strategy: `AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/`
- Policy: `AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/POLICY.yaml`
- Governance: `AERIS_MESH_STUDY/00_governance/decisions/ADR-0017-s7-unstructured-gmsh-su2-preregistration.md`
- Reload handoff: `AERIS_MESH_STUDY/PROJECT_HANDOFF/S7_RELOAD_AND_CLAUDE_HANDOFF_2026-08-21.md`
- Failed first Claude review record:
  `AERIS_MESH_STUDY/artifacts/strategy_studies/S7_unstructured_gmsh_su2/claude/implementation_audit_20260821_01/`
- Synthetic optimizer/mapping diagnostics:
  `AERIS_MESH_STUDY/artifacts/strategy_studies/S7_unstructured_gmsh_su2/laptop_smoke/`

The S7 suite currently passes 24 focused tests and Ruff. The artifacts listed above
are synthetic/failed-review history under older source digests. There is no real S7
BWB mesh, SU2, y+, force, grid, TE, hold-out, or campaign evidence yet.

## Canonical S6 inputs and source

- Strategy: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/`
- Policy: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/POLICY.yaml`
- Roadmap: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/ROADMAP.md`
- Study argument: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/STUDY.md`
- Literature notes: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/RESEARCH.md`
- Atlas logic: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/atlas.py`
- Deformation: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/deform.py`
- Campaign runner: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py`
- CFD gates: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/cfd_qc.py`
- Tests: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py`
- Grid/TE plan and laptop runner:
  `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/qualification.py`

## Canonical result artifacts

- Initial maximin atlas:
  `artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json`
- Smoke-enriched manifest used to start production:
  `artifacts/s6_bounded_mesh_atlas/atlas_manifest_smoke_enriched_v3.json`
- Full 100-target maximin smoke report:
  `artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_smoke/atlas_validation_report.json`
- Qualified 16/16 production seed report:
  `AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production/seed_build_report.json`
- Qualified development manifest, not frozen:
  `artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified16_eps15_s0p3p6_v5.json`
- Campaign-equivalent written-CGNS canary:
  `artifacts/s6_bounded_mesh_atlas/development_atlas_production_written_canary_v2/atlas_validation_report.json`
- Complete first production development audit (99/100, not accepted):
  `artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_production_written_v2/atlas_validation_report.json`
- Independent audit of that report (integrity passed, campaign failed):
  `artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_production_written_v2/independent_report_audit.json`
- Enriched 22-seed report (21 passed, seed 007 rejected):
  `AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production/seed_build_enriched22_report.json`
- Qualified 21-template pre-validation manifest:
  `artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified21_eps15_s0p3p6_v7.json`
- Final enriched 100-target production report (100/100):
  `artifacts/s6_bounded_mesh_atlas/development_atlas_qualified21_production_written_v3/atlas_validation_report.json`
- Independent final report audit (integrity and campaign acceptance passed):
  `artifacts/s6_bounded_mesh_atlas/development_atlas_qualified21_production_written_v3/independent_report_audit.json`
- Source provenance captured before that run:
  `artifacts/s6_bounded_mesh_atlas/development_atlas_qualified21_production_written_v3/implementation_provenance_at_start.json`
- Final post-validation atlas manifest (`freeze_ready=true` for membership only):
  `artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_postvalidation_v8.json`
- Portable hash-bound 21-template registry (`frozen_candidate`):
  `artifacts/s6_bounded_mesh_atlas/template_registry_qualified21_production_portable_v9.json`
- Independent 63-asset registry audit:
  `artifacts/s6_bounded_mesh_atlas/template_registry_qualified21_production_portable_v9_audit.json`
- Laptop-prepared ten-case HPC pilot package:
  `artifacts/s6_bounded_mesh_atlas/hpc_pilot_package_v9/`
- Independent fidelity evidence:
  `AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/fidelity_reaudit_v2/lhs100_seed42_000/surface_report.json`
- Coarse converged CFD/y+ rejection:
  `artifacts/s6_bounded_mesh_atlas/cfd_pilot_083_n65_lowmem/pilot_acceptance_audit.json`
- Preserved v1 policy snapshot, written after the pilots and not preregistration evidence:
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/qualification_plan_pre_laptop_20260820.json`
- Final independently reviewed v3 qualification plan:
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/qualification_plan.json`
- Hash-bound audit of the three legacy N65 pilot runs:
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/laptop_cfd/legacy_evidence_audit.json`
- Historical pre-fingerprint three-case N65 laptop CFD summary:
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/laptop_cfd/laptop_summary.json`
- Current-code collector output; all three historical rows correctly marked stale:
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/laptop_cfd/laptop_summary_current.json`
- Human-readable result and Claude review resolution:
  `AERIS_MESH_STUDY/PROJECT_HANDOFF/QUALIFICATION_UPDATE_2026-08-21.md`
- Claude Opus/max review record:
  `AERIS_MESH_STUDY/PROJECT_HANDOFF/CLAUDE_OPUS_MAX_REVIEW_2026-08-21.md`
- 10,000-design preflight inputs:
  `artifacts/s6_bounded_mesh_atlas/campaign_preflight_10000/`
- Slurm scripts:
  `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/slurm_run_design_array.sh`
  and `slurm_collect.sh`.

## Governance and cross-strategy evidence

- Independent strategy rules and hold-out governance:
  `AERIS_MESH_STUDY/00_governance/decisions/ADR-0011-independent-strategy-studies.md`
- S2 reinstatement before measurement:
  `AERIS_MESH_STUDY/00_governance/decisions/ADR-0012-s2-reinstated.md`
- S3 controlled scope:
  `AERIS_MESH_STUDY/00_governance/decisions/ADR-0013-s3-scoped-as-a-sweep-experiment.md`
- Non-pyHyp gate:
  `AERIS_MESH_STUDY/00_governance/decisions/ADR-0014-non-pyhyp-volume-gate.md`
- Exact-z and arbitrary-station proposal, still not globally accepted:
  `AERIS_MESH_STUDY/00_governance/decisions/ADR-0015-exact-sections-at-arbitrary-stations.md`
- S6 campaign quality and freeze policy:
  `AERIS_MESH_STUDY/00_governance/decisions/ADR-0016-s6-campaign-quality-and-freeze-policy.md`
- Shared brief and known instrumentation defects:
  `AERIS_MESH_STUDY/04_strategy_studies/COMMON_BRIEF.md`
- Project ledger: `AERIS_MESH_STUDY/status`

## Obsolete or non-production artifacts

`artifacts/s6_bounded_mesh_atlas/atlas_manifest_frozen_candidate_v3.json` is
obsolete. It was generated before the code was corrected to prevent smoke-level
validation from setting `freeze_ready=true`. Never use it for hold-out or CFD.

`artifacts/s6_bounded_mesh_atlas/template_registry_maximin16_smoke_v5.json`, if
present, is a development-only registry under an older schema. Use only the
portable qualified-21 production registry listed above for development CFD.

Older `development_atlas_*`, `coarse_*`, and pilot folders are diagnostic history.
Do not silently combine their numbers with production evidence.

## Evidence interpretation rule

Use the JSON report, its recorded configuration, and source/implementation hashes
together. A directory name or terminal line alone is not sufficient evidence.
