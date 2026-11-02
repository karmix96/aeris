"""Merge screen parts (screen_C_part*.json, run per type on separate cores) into screen_C.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.paths import STAGE2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen import summarise  # noqa: E402

STUDIES = STAGE2 / "data" / "studies"

parts = sorted(STUDIES.glob("screen_C_part*.json"))
rows, heads = [], []
for p in parts:
    d = json.loads(p.read_text())
    heads.append({k: d[k] for k in ("code_version", "mesh_code_hash", "level")})
    rows.extend(d["rows"])
if len({h["mesh_code_hash"] for h in heads}) != 1:
    raise SystemExit("the parts were run with different mesh code; rerun the screen")
rows.sort(key=lambda r: (r["wing_type"], r["set"], r["index"], r["re_mean"]))
out = heads[0] | {"parts": [p.name for p in parts], "summary": summarise(rows), "rows": rows}
(STUDIES / "screen_C.json").write_text(json.dumps(out, indent=1))
for p in parts:
    p.unlink()
print(json.dumps(out["summary"], indent=1))
