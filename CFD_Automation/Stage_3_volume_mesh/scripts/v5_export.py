"""V5: the solver files of one mesh and check 15 on them; this mesh is also the V7 solver case.

    python scripts/v5_export.py                     # BWB reference wing 0, VC, Re 3e5 -> data/meshes/<name>/

Writes blocks.npz, quality.json, manifest.json, volume.cgns (ADflow) and volume.su2 (SU2) into data/meshes/<name>/
(not in git: 0.8 GB) and the check-15 record into data/studies/v5_export.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import _jsonable, build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume, mesh_name, write           # noqa: E402


def main(wing_type: str = "bwb", index: int = 0, re: float = 3e5, level: str = "VC") -> dict:
    w = wing_from_set(wing_type, "reference", index)
    t0 = time.time()
    vm = build_volume(build_surface(w.loft, re, level))
    t1 = time.time()
    name = mesh_name(vm, w)
    out = write(vm, w, HERE / "data" / "meshes" / name, formats=("npz", "cgns", "su2"))
    t2 = time.time()
    q = json.loads((out / ("quality.json" if vm.passed else "refusal.json")).read_text())
    rec = {"mesh": name, "wing": f"{wing_type} reference {index}", "level": level, "re": re, "outcome": vm.outcome,
           "cells": vm.cells, "nodes": vm.nodes, "seconds_build": round(t1 - t0, 1), "seconds_write": round(t2 - t1, 1),
           "check15": [c for c in q["checks"] if c["n"] == 15][0], "exports": q.get("exports", {}),
           "files": {p.name: p.stat().st_size for p in sorted(out.iterdir())}}
    (HERE / "data" / "studies" / "v5_export.json").write_text(json.dumps(_jsonable(rec), indent=1))
    print(json.dumps(_jsonable({k: rec[k] for k in ("mesh", "outcome", "cells", "check15", "files")}), indent=1))
    return rec


if __name__ == "__main__":
    main()
