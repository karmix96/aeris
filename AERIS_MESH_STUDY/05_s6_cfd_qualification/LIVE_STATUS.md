# S6 qualification live status

Updated: 2026-08-30

## Current state

- M-1 host/WSL/storage qualification: **verified**.
- WSL Ubuntu: relocated to `D:\WSL\Ubuntu`; effective memory 12.66 GiB;
  swap 8 GiB; 12 logical CPUs.
- Direct-I/O baseline on relocated HDD: 60.5 MB/s write, 73.0 MB/s read.
- Recovery VHD: independently SHA-256 verified and retained.
- M0/M1 contracts: **complete and committed** (`752852c`); geometry identity,
  moment-reference, CFD residual/mass-imbalance, immutable classification,
  mission-authority, and frozen-design-space audits are machine-green.
- Geometry semantic audit: **PASS**; 20 live variables match 20 frozen
  variables with no bound differences.
- Half-domain, schema, policy, execution-state, mission, moment-reference, CFD
  contract, geometry-freeze, and holdout-lock audits: **PASS**.
- Holdout `round_c_lhs10_seed42`: **locked and untouched**; contents were not
  read, parsed, copied, visualized, or hashed.
- Independent Claude review: **not obtained**. Three authenticated Claude Code
  requests (Opus twice, Sonnet once) timed out with zero model tokens; failure
  records are retained under `reviews/` and no Claude GO is claimed.
- M2 direct-march candidate family: **terminal NO-GO for that route**. The coupled
  `17x43x61 -> 23x57x73 -> 29x75x97` refinement and resource screens pass, but
  independently reopened written ADF-CGNS meshes contain inverted cells.
- This does **not** invalidate proven S6: its successful production path reuses
  a valid S1/Openblademesh volume and applies bounded deformation to the exact
  S6 wall. The failed experiment remarched the exact wall directly.
- Best controlled C03 result: six inverted cells, minimum signed volume
  `-3.670179816350609e-12`, and `qmin=-0.3114098210`.
- Proven-route recovery: **C02 production family PASS**. Geometry A C01 and
  C02 and independent B/C/E C02 deformations all reopen with zero inverted
  cells and minimum scaled quality in `[0.1545, 0.1754]`. Evidence is in
  `reports/m2_proven_route_family_20260830.json`.
- Missing C01 screens are now complete: B and E pass the 0.10 production
  floor; C has zero inversions but `qmin=0.0840`, below that floor.
- C03 finest diagnostic: **NO-GO** for this bounded map (4 inverted cells in
  the tip-cap block, `qmin=-0.2468`). It is retained as a diagnostic and does
  not invalidate the passing C02 production family.
- The governed C01 ladder value is now `s0_fraction=5.0e-6`; its A/B/C/E
  probe passed with zero inversions and `qmin >= 0.1091`. C03 is governed at
  `6.1e-6` using the repaired tip-cap template. Independent review remains
  required before CFD (`reports/m2_c01_ladder_probe_20260830.json`).
- Independent review of that policy (`ab5e83e`, `8ffa83f`) is now on record:
  `reviews/claude_m2_spacing_policy_review_20260830.json`. The probe itself
  reproduces exactly - A/B/C/E at `5.0e-6` give zero inversions and
  `qmin` 0.1091..0.1497, every recorded hash matches - and the repaired C03
  mesh for geometry A reproduces at `qmin=+0.1267` with an exact wall. The
  review is **not** a GO: it returns two HIGH findings.
- **R1 (HIGH)**: the non-monotone fraction policy does *not* produce physically
  ordered wall spacing. On the five OML blocks the realized first-cell median
  is C01 `6.47e-6..7.29e-6` m, C02 `6.38e-6..8.04e-6` m, C03
  `8.37e-6..1.08e-5` m, so C03 is 1.3-1.5x **coarser** at the aerodynamic wall
  than C01, not finer. The whole-mesh percentile that suggested otherwise is
  dominated by the tip-cap blocks, where realized spacing is 24-48x the nominal
  `s0`. The characteristic length is identical at every level, so nominal
  spacing is strictly C02 `6.177e-6` < C01 `6.571e-6` < C03 `8.016e-6` m.
- **R2 (HIGH)**: `resolution.py` and `src/aeris/cfd/meshing/pyhyp_options.py`
  `GRID_LEVELS` now disagree (`c01` 5.0e-6 vs 6.1e-6, `c03` 6.1e-6 vs 3.6e-6,
  `production` 3.6e-6 vs 4.4e-6). `build_pyhyp_options` falls back to
  `GRID_LEVELS` whenever a caller omits `s0_fraction_override`, which
  `march_s1.prepare` does, so an S1-entry march silently uses `3.6e-6` at C03 -
  the configuration proven to fold.
- **R3 (MEDIUM)**: repaired C03 is screened on geometry A only; B/C/E have not
  been marched or deformed at C03.
- Adding normal layers is not an alternative C03 repair: at `3.6e-6` on the C03
  surface the fold deepens monotonically (N=73 `-0.2192`, N=97 `-0.2448`,
  N=129 `-0.3350` with 7 inversions, N=257 `-0.5290` with 15). The
  production-configuration recovery mesh marches the same geometry at `3.6e-6`
  with 257 layers cleanly (`qmin=0.2383`), so the ceiling belongs to the C03
  candidate cap surface, not to the fraction itself.
- C02 family evidence: **independently reproduced**. All six recorded
  `output_sha256` values match the on-disk artifacts, and an independent ADF
  reopen plus repository volume QC reproduces every inverted-cell count,
  `min_scaled_quality`, and exact-wall error.
- C03 tip-cap failure is **attributed to the S1 template march, not to the
  deformation**. The C03 template volume itself fails the hard gate before any
  deformation (4 inverted cells, `qmin=-0.2448`, 20 negative scaled-Jacobian
  cells in `domain.00012` / surface block `tip_base`, wall layers k=4..14 at
  one corner). The bounded deformation moves that block minimum by 0.002
  (`-0.2448 -> -0.2469`) and creates no new inversion; the C01 and C02
  templates are clean.
- C03 is repaired without coarsening the wall: the tip-cap collar ladder is
  re-specified from `5/7/9` to `5/6/7`, while the wall-spacing ladder is
  `5.0e-6/4.7e-6/3.6e-6`. The resulting cell counts are
  `191,520/422,352/943,104`, with effective ratios `1.3016/1.3071`.
- The redesigned family passes A/B/C/E at every level after written-CGNS
  reopen: zero inversions and `qmin >= 0.1091`. C/C03 uses the governed
  target-specific S1 template fallback with the same global settings.
- `screen-grid-family` is now **CONDITIONAL** with every mesh and resource
  check green. The old direct-march NO-GO remains retained as historical route
  evidence and no longer vetoes the proven route.
- Conservative flat-plate y+ preflight remains a high risk: estimated C03
  all-wall p95 is `1.68-2.17` and maximum `9.98-14.59`; only measured CFD can
  qualify it. CFD remains blocked pending independent review.
- Two Claude Opus review attempts for `a92bf10` timed out with zero tokens; an
  interactive Opus/max review of `dbf918f` also stalled without a result. A
  completed independent Claude Code review of `dbf918f` is now on record:
  `reviews/claude_m2_coupled_family_review_20260831.json`.
- That review **closes R1, R2 and R3** against independently reproduced
  evidence. All twelve claimed family meshes reopen with zero inversions,
  every `output_sha256` and `target_surface_sha256` matches on disk, every
  `qmin` matches to full precision, walls are exact to `<= 3.5e-18` m, and all
  interfaces stay conformal at 20 pairs with `<= 3.6e-15` m mismatch. Realized
  OML first-cell medians now order C01 `6.47-7.29e-6` > C02 `6.37-7.83e-6` >
  C03 `4.90-6.20e-6` m for geometry A, with the same ordering for B/C/E, and
  the tip cap orders `3.13e-4 > 2.22e-4 > 1.55e-4` m.
- The review issues an explicit **GO for exactly one measurement-only A/C03
  canary**, bound to
  `m2_coupled_family_20260831/candidate_c03/lhs100_seed42_083/wing_vol_deformed.cgns`
  (`sha256 be2805ff...`, 943,104 cells, `qmin=0.1671`). Conditions: the result
  may not be classified ACCEPTED until a numeric y+ limit and its wall-distance
  convention enter the immutable policy; the y+ convention must be stated when
  reporting; the run needs a memory watchdog; one run only; and wiring
  `run-canary` is itself a governed change that must keep the other heavy
  commands blocked.
- The y+ preflight reproduces exactly from the meshes, but it uses the **full
  first-cell height**. ADflow reports y+ at the first cell centroid, which
  halves every published number: A/C03 then reads OML p95 `0.74`, p99 `1.82`,
  with about 3 percent of OML wall nodes above `y+ = 1` and the large tail on
  the tip cap. Its limits `{p95 1.0, p99 2.0, max 5.0}` are in no governed
  policy file, and its generator is not in the repository.
- Residual non-blocking findings: C01 to C02 is not a wall-normal refinement
  step (6 percent nominal, slightly reversed in the realized upper OML
  median), C/C03 needs a geometry-specific template (the A-template route
  lands at `qmin=0.0886`), the y+ preflight is unreproducible and ungoverned,
  two `grid_screen` gate defaults are permissive, and the memory forecast
  `9.35 x cells / finest_cells` cannot fail on the finest level.
- Focused verification: **74 passed** across S6 atlas, qualification
  orchestrator, ADflow contract, and SU2 contract tests.
- Repository-wide pytest: collection is environment-blocked by absent optional
  project packages (first root cause: `aerosandbox`; 102 collection errors),
  not by a failing governed S6 test.

## Local commits

- `56fd14a` — desktop WSL resource qualification
- `cc9522e` — governed S6 qualification scaffold
- `7fe707b` — expose M1 contract gates
- `b281936` — parser-based geometry semantic audit
- `bd39f9f` — unresolved mission-authority documentation
- `5670b46` — half-domain eligibility gate
- `031db63` — versioned execution and verdict schemas
- `f7c7cb2` — versioned classification threshold policy
- `a79c1eb` — immutable execution terminal-state validator
- `752852c` — complete M1 scientific and classification contracts

## Terminal evidence

- `reports/m2_grid_screen_terminal_report.json`
- `reports/m2_grid_screen_terminal_report.md`
- `reports/screen_grid_family.json`
- `reports/s6_recovery_deformation_20260830.json`
- `reports/m2_proven_route_family_20260830.json`
- `reports/m2_c03_tipcap_diagnosis_20260830.json`
- `reports/m2_coupled_family_respec_20260831.json`
- `reports/m2_wall_spacing_yplus_preflight_20260831.json`
- `reviews/claude_m2_spacing_policy_review_20260830.json`
- `reviews/claude_m2_coupled_family_review_20260831.json`
- `studies/grid/m2_20260830/` (local run records; large CGNS files remain
  ignored and must not be committed)

## Next authorized work

Obtain an independent Opus review of the redesigned coupled-family report and
spacing preflight. If it closes all HIGH findings, authorize exactly one
one-rank A/C03 CFD canary under `/usr/bin/time -v`; classify its measured y+,
resource, convergence and force evidence before any C01/C02 CFD launch.

## Resume commands

```bash
cd /home/mike_kara/aeris
.venv/bin/pytest -q AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py AERIS_MESH_STUDY/05_s6_cfd_qualification/tests tests/cfd/test_adflow_adapter.py tests/cfd/test_su2_adapter.py
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py audit-contract
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py audit-geometry-space
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py check-half-domain
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py check-holdout-lock
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py screen-grid-family
```
