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
- M2 candidate family: **terminal NO-GO**. The coupled
  `17x43x61 -> 23x57x73 -> 29x75x97` refinement and resource screens pass, but
  independently reopened written ADF-CGNS meshes contain inverted cells.
- Best controlled C03 result: six inverted cells, minimum signed volume
  `-3.670179816350609e-12`, and `qmin=-0.3114098210`.
- Geometry B/C/E screens and CFD canary: **not run; forbidden by the governed
  zero-inversion gate**. This is a deliberate terminal stop, not unfinished
  execution.
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
- `studies/grid/m2_20260830/` (local run records; large CGNS files remain
  ignored and must not be committed)

## Next authorized work

Create a new, versioned tip/collar block-topology design and re-enter M2 with a
new family identifier. Preserve every failed attempt and do not weaken the
zero-inversion acceptance gate. A CFD canary remains unauthorized until a
nominal finest written mesh passes independent zero-inversion validation and
the independent review gate is closed.

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
