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
- C03 repair search (nine controlled marches on the byte-identical surface):
  `nConstantStart` has no material effect; `epsE` at the frozen ceiling 3.0
  reduces but does not clear the fold (`qmin=-0.0948`); normal-layer count is
  not the driver (N=73 still folds); wall spacing is. At N=97 the fold clears
  only when the first-cell fraction is relaxed from `3.6e-6` to `6.1e-6`, which
  deforms to the exact C03 wall with **zero inverted cells, `qmin=+0.1267`**,
  and moves the worst cell off the tip cap. That relaxation inverts the
  ladder's wall-spacing ordering, so it is a governed y+ decision and is **not**
  applied. Evidence: `reports/m2_c03_tipcap_diagnosis_20260830.json`.
- Open review findings from this pass: **F1 (HIGH)** the committed C01 rung was
  marched at `s0_frac=3.6e-6` instead of the frozen `6.1e-6`, so the A-family
  C01/C02/C03 sequence is not a coupled grid-plus-wall-spacing ladder;
  **F2 (MEDIUM)** the affine map scales wall-normal spacing, so B/C/E C02 land
  about 18 percent below the template first-cell height and per-geometry y+
  must be closed before the canary.
- CFD canary: **blocked** pending the roadmap's independent review gate and a
  governed decision on the C03 finest-level diagnostic.
- Focused verification: **73 passed** across S6 atlas, qualification
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
- `studies/grid/m2_20260830/` (local run records; large CGNS files remain
  ignored and must not be committed)

## Next authorized work

Use the proven S1-volume → S6 exact-wall deformation route for the remaining
M2 resolution/geometry campaign, with a new versioned experiment identity.
Preserve every failed direct-march attempt and do not weaken the zero-inversion
acceptance gate. A CFD canary remains unauthorized until the required nominal
family screens and independent review gate are closed.

Three decisions are now waiting on human governance, in this order:

1. C03: accept the relaxed `6.1e-6` wall spacing at the finest level (and state
   why a coarser wall spacing at the finest grid is acceptable), repair C03 some
   other way, or formally retire the C03 rung and declare C02 the production
   resolution.
2. F1: re-march the C01 rung at its frozen `6.1e-6` fraction, or record that the
   family is deliberately a fixed-wall-spacing sequence and drop any coupled
   refinement claim.
3. F2: close per-geometry first-cell height / y+ before the canary, since the
   affine map rescales wall spacing with the geometry.

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
