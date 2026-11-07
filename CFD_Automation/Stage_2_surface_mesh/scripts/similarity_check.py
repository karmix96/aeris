"""Similarity check (decision 70, 7 Nov 2026): the 20 reference shapes of before similarity, meshed again at unit
mean chord, against their first meshes at real size (data/studies/screen_C.json, the first approach's screen).

    python scripts/similarity_check.py                  # this code: similarity and the nose fix (decision 64)
    python scripts/similarity_check.py --code <CFD_Automation of commit 9472830c> --tag similarity_only

The old shapes are Stage_1_geometry/data/sets/<type>/reference.json at commit 7bcb7067 (before similarity), read with
git; the root chord is dropped (18 -> 17 numbers) and the semi-span follows from the aspect ratio at unit mean chord.
Rules: the first approach at level C (configs/surface_first.yaml here; at 9472830c its own configs/surface.yaml, the
same rules), at the four Re levels on the mean chord. Commit 9472830c is the similarity merge: unit mean chord and
trailing edge 0.2 % c, but the old nose rule; this code has both. So "similarity_only" against the old screen shows
what the size change does, and this code against "similarity_only" shows what the nose fix does.
Writes data/studies/similarity_check.json (one block per --tag; the old meshes are read from screen_C.json).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
STAGE2_HERE = HERE.parents[1]
REPO = HERE.parents[3]
OLD_REV = "7bcb7067"                     # the last commit with the sets before similarity
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
RE_LEVELS = (1.0e5, 3.0e5, 1.5e6, 3.0e6)
SHAPE_KEYS_DROP = ("root_chord_m", "semi_span_m")


def old_vectors(wing_type: str) -> list[dict]:
    path = f"CFD_Automation/Stage_1_geometry/data/sets/{wing_type}/reference.json"
    txt = subprocess.run(["git", "-C", str(REPO), "show", f"{OLD_REV}:{path}"], capture_output=True, text=True,
                         check=True).stdout
    return json.loads(txt)["vectors"]


def shape(v: dict) -> dict:
    return {k: v[k] for k in v if k not in SHAPE_KEYS_DROP}


def same_shape(a: dict, b: dict) -> bool:
    a, b = shape(a), shape(b)
    if set(a) != set(b):
        return False
    return all(a[k] == b[k] if isinstance(a[k], list) else abs(float(a[k]) - float(b[k])) < 1e-9 for k in a)


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--code", default=str(HERE.parents[2]), help="the CFD_Automation folder whose cfdauto builds")
    p.add_argument("--tag", default="similarity_and_nose")
    p.add_argument("--types", nargs="+", default=list(TYPES))
    a = p.parse_args(argv)
    code = Path(a.code).resolve()
    sys.path.insert(0, str(code))
    from cfdauto.geometry.build import load_set
    from cfdauto.geometry.loft import build_loft
    from cfdauto.geometry.params import load_config, resolve
    from cfdauto.geometry.sections import build_wing_sections
    from cfdauto.mesh.surface import build_surface, mesh_code_hash

    first = code / "Stage_2_surface_mesh" / "configs" / "surface_first.yaml"
    config = first if first.exists() else code / "Stage_2_surface_mesh" / "configs" / "surface.yaml"
    cfg = load_config()
    rows = []
    for t in a.types:
        spec = cfg.types[t]
        new_ref = load_set(t, "reference")["vectors"]
        for i, v_old in enumerate(old_vectors(t)):
            vec = resolve(spec, {k: v for k, v in v_old.items() if k != "root_chord_m"})
            _, stations = build_wing_sections(spec, vec, cfg.te)
            loft = build_loft(stations, 2, None)
            for re in RE_LEVELS:
                t0 = time.time()
                m = build_surface(loft, re, "C", str(config))
                ch = {c.name: float(c.value) for c in m.checks}
                h = [r["h_le_c"] for r in m.stations]
                rows.append({"wing_type": t, "index": i, "re_mean": re, "passed": m.passed,
                             "failed": [c.name for c in m.failed()], "n_ring": m.info["n_ring"],
                             "n_span": m.info["n_span"], "n_panels": len(m.info["cells_per_panel"]),
                             "cells_per_panel": m.info["cells_per_panel"], "cap_quads_J": ch["cap_quads"],
                             "wing_quads_J": ch["wing_quads"], "nose_turning": ch["nose_turning"],
                             "nose_h_le_c": [float(min(h)), float(max(h))],
                             "airfoils": list(vec.get("airfoils") or []),
                             "same_pick": same_shape(v_old, new_ref[i]) if i < len(new_ref) else False,
                             "in_new_set": any(same_shape(v_old, w) for w in new_ref),
                             "mean_chord_m": m.info["mean_chord_m"], "tip_chord_m": m.info["tip_chord_m"],
                             "node_hash": m.node_hash(), "seconds": round(time.time() - t0, 2)})
                r = rows[-1]
                print(f"{t:12s} {i} Re {re:7.1e} ring {r['n_ring']:4d} x {r['n_span']:3d} panels {r['n_panels']} "
                      f"cap {r['cap_quads_J']:.3f} nose {100 * r['nose_h_le_c'][0]:.3f} % c  {r['seconds']:.1f} s "
                      f"{'ok' if r['passed'] else r['failed']}", flush=True)
    out = STAGE2_HERE / "data" / "studies" / "similarity_check.json"
    doc = json.loads(out.read_text()) if out.exists() else {}
    if "old" not in doc:                                     # the first meshes at real size (the first screen)
        scr = json.loads((STAGE2_HERE / "data" / "studies" / "screen_C.json").read_text())
        doc["old"] = {"source": "data/studies/screen_C.json (first approach, level C, real size, old nose rule)",
                      "mesh_code_hash": scr["mesh_code_hash"],
                      "rows": [{"wing_type": r["wing_type"], "index": r["index"], "re_mean": r["re_mean"],
                                "passed": r["passed"], "n_ring": r["n_ring"], "n_span": r["n_span"],
                                "n_panels": len(r["cells_per_panel"]), "cells_per_panel": r["cells_per_panel"],
                                "cap_quads_J": r["checks"]["cap_quads"], "wing_quads_J": r["checks"]["wing_quads"],
                                "nose_turning": r["checks"]["nose_turning"], "mean_chord_m": r["mean_chord_m"],
                                "tip_chord_m": r["tip_chord_m"], "seconds": r["seconds"]}
                               for r in scr["rows"] if r["set"] == "reference" and r["built"]]}
    rev = subprocess.run(["git", "-C", str(code), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    doc[a.tag] = {"code": rev, "config": config.name, "mesh_code_hash": mesh_code_hash(), "old_shapes_from": OLD_REV,
                  "rows": rows}
    out.write_text(json.dumps(doc, indent=1))
    print(f"wrote {out.name} [{a.tag}]: {sum(r['passed'] for r in rows)} of {len(rows)} passed")


if __name__ == "__main__":
    main()
