# S6 Qualification Update

Updated: 2026-08-21, Europe/Athens

## Status

No mesh or CFD process is active. The locked hold-out remains untouched. S6 is
still a candidate, not campaign-ready.

## Laptop CFD evidence

Three development meshes were generated from governed N65 template routes and
passed written-CGNS wall, interface, volume, and quality checks.

| Case | Template | Cells | qmin | Residual drop | CL | CD | CMy | y+ p95 / p99 / max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 042 | 042 | 692,480 | 0.237942 | 7.5088 | 0.070474 | 0.030765 | -0.033266 | 1.100 / 2.854 / 6.309 |
| 095 | 095 | 776,960 | 0.163062 | 7.7394 | 0.109657 | 0.031723 | -0.060400 | 1.369 / 3.246 / 4.566 |
| 007 | 095 | 776,960 | 0.167151 | 7.5067 | 0.107726 | 0.031603 | -0.076818 | 1.252 / 3.147 / 4.580 |

All three solvers converged and passed residual, finite-force, plausibility, and
force-tail gates. All three failed the strict N65 y+ screen. This proves the
local mesh-to-ADflow path and rejection logic. It does not test production-grid
y+, force accuracy, TE sensitivity, or grid convergence. Do not tune or reject
the production wall law from N65 values.

Case 007 used two MPI processes instead of the planned four to avoid laptop
memory exhaustion. The deviation is recorded in the machine-readable summary.

These runs predate the final cache fingerprints. Their bytes are preserved and
bound by `legacy_evidence_audit.json`: all assets exist and all declared hashes
match, but `current_cache_compatible=false`. A rerun is required only to claim
exact current-code provenance, not to retain the limited historical smoke result.

## Grid and TE policy

The existing P0 atlas candidate is smoke tangential resolution, N257, epsE 1.5,
and first-cell fraction 3.6e-6. It is now explicitly separate from the true grid
family:

P0 span resolution follows the selected frozen template; it is not fixed at 89.
The registry range is 60-98 span cells (template 042: 75; template 095: 85).

- G1: smoke, N129, first-cell fraction 7.2e-6.
- G2: medium, N193, first-cell fraction 5.1e-6.
- G3: fine, N257, first-cell fraction 3.6e-6.
- TE screen on G2: max(0.5 mm, 0.25%c), max(1.0 mm, 0.50%c), and
  max(1.5 mm, 0.75%c); confirm the selected option on the selected final grid.

First run the N257 P0 wall-normal canary using development cases. P0 still uses
smoke tangential spacing, so a y+ pass is not grid convergence. Calibrate wall
spacing only if P0 fails, then run TE and true all-direction grid studies. Use
GCI only for monotonic, asymptotic-looking sequences; otherwise report the raw
grid envelope.

## Independent review and fixes

Three Claude Opus review passes ran with maximum effort. The first found three
high-severity risks: historical-summary overwrite, incomplete production CFD
cache identity, and incomplete mesh fingerprints. All were fixed. The second
found no critical or high issue; its two remaining medium fingerprint gaps
(surface ingestion and LHS sampling) were also closed. The third narrow pass
found that the ingestion module was a shim; the real `src/aeris/mesh/surface.py`
implementation is now included in the fingerprint. Span extraction is
order-independent, G2 refines tip endpoints, and P0 limits are machine-readable.

Verification: 41 focused S6 tests passed; 51 passed with the ADflow adapter tests.
Ruff and formatting checks passed.

## Canonical evidence

- Preserved v1 policy snapshot (written after the pilots; not preregistration
  evidence): `artifacts/s6_bounded_mesh_atlas/qualification_v1/qualification_plan_pre_laptop_20260820.json`
  (sha256 `3f8f05cd792a5e3b704b5b1b86e46ca979d5349a96ba226de5bacf25c3160954`).
- Final v3 plan: `artifacts/s6_bounded_mesh_atlas/qualification_v1/qualification_plan.json`
  (sha256 `407b409df7aadd3baec41912dc5a0ec4c8bcedb17b788ac30b156e76b1f1cddc`).
- Legacy pilot integrity audit:
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/laptop_cfd/legacy_evidence_audit.json`
  (sha256 `7fc88eccf2c07720cbbb081bdf38a4d67845ea054a8691fb516c67a23736b878`).
- Historical pre-fingerprint laptop summary:
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/laptop_cfd/laptop_summary.json`
  (sha256 `88c745656afe218a1a6bd031c931b9d6c380debb3fb19657f1a08cd18d1889b8`).
- Current-code collector result (3 stale, historical file preserved):
  `artifacts/s6_bounded_mesh_atlas/qualification_v1/laptop_cfd/laptop_summary_current.json`
  (sha256 `c58747e4ecc123eebf5e68e6a2fc86036301b57bf8c30cdfeb12d99218ece79b`).
- Runner: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/qualification.py`
  (sha256 `72a5e73cd019171daf6591004b3309442d9c2294a2a510db5210cf0592d31d7f`).
- Campaign runner: `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py`
  (sha256 `67750031019877673ebb724380f87e07c024039d0b8cb17f8d894e84529c6c97`).

## Exact next action

On hardware with at least 64 GB RAM, run the first P0 N257 wall-normal case from
`hpc_pilot_package_v9`: geometry 007, the hardest known routing case. Measure
peak memory and y+. It is useful for a memory ceiling, but its y+ is not
representative of the median. Then run two representative cases. Do not open the
hold-out. Size the true G2/G3 studies from the first P0 run before submission.
