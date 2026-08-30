# S6 CFD qualification orchestrator

`run.py` is the single, audit-first entry point required by the master guide.
It emits immutable JSON records under `reports/`, supports `--dry-run`, and
keeps all mesh/CFD/holdout commands blocked until the M0–M2 gates are green.

Run from the repository root with `.venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py audit-all --dry-run`.
