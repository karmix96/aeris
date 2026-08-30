# S6 qualification live status

Updated: 2026-08-30

## Current state

- M−1 host/WSL/storage qualification: **verified**.
- WSL Ubuntu: relocated to `D:\WSL\Ubuntu`; effective memory 12.66 GiB;
  swap 8 GiB; 12 logical CPUs.
- Direct-I/O baseline on relocated HDD: 60.5 MB/s write, 73.0 MB/s read.
- Recovery VHD: independently SHA-256 verified and retained.
- M0 scaffold: **implemented locally**.
- M1 geometry semantic audit: **machine-green**; 20 live variables match 20
  snapshot variables with no bound differences.
- Half-domain eligibility audit: **PASS**; six qualification tests pass.
- Holdout `round_c_lhs10_seed42`: **locked**; contents not read.
- Heavy mesh/CFD/canary work: **BLOCKED**.

## Local commits

- `56fd14a` — desktop WSL resource qualification
- `cc9522e` — governed S6 qualification scaffold
- `7fe707b` — expose M1 contract gates
- `b281936` — parser-based geometry semantic audit
- `bd39f9f` — unresolved mission-authority documentation
- `5670b46` — half-domain eligibility gate

## Remaining gates before any canary

1. Identify exactly one authoritative mission configuration and hash it.
2. Freeze the Phase-I geometry manifest after explicit semantic review.
3. Implement 29×75 identity/cache invalidation regression.
4. Implement quarter-MAC/mission-CG references, complete residual and mass
   imbalance contracts, and terminal-state classification separation.
5. Measure actual mesh and canary footprints, then complete the campaign
   storage/resource forecast.
6. Obtain and close the independent Claude M0/M1 adversarial review.

## Resume commands

```bash
cd /home/mike_kara/aeris
.venv/bin/pytest -q AERIS_MESH_STUDY/05_s6_cfd_qualification/tests
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py audit-contract
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py audit-geometry-space
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py check-half-domain
.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py check-holdout-lock
```
