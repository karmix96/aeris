"""Single place that knows where things live."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]          # AERIS_MESH_AGENT
REPO_ROOT = PACKAGE_ROOT.parent                              # project root
ATLAS_ARTIFACTS = REPO_ROOT / "artifacts" / "s6_bounded_mesh_atlas"
STUDY_SHARED = REPO_ROOT / "AERIS_MESH_STUDY" / "04_strategy_studies"

TABLES = PACKAGE_ROOT / "tables"
FIGURES = PACKAGE_ROOT / "figures"
RESULTS = PACKAGE_ROOT / "results"

#: Development geometry set (ADR-0011). The hold-out set is deliberately absent:
#: `round_c_lhs10_seed42` is guarded by a tripwire in
#: AERIS_MESH_STUDY/04_strategy_studies/shared/geometry_sets.py and is run once,
#: after the freeze signal. No code in this package may reference it.
DEVELOPMENT_SET = "lhs100_seed42"

for _directory in (TABLES, FIGURES, RESULTS):
    _directory.mkdir(parents=True, exist_ok=True)
