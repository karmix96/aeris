"""What makes the mesh big: the Re level and the transition band, counted on rule set 2 (the other factors are in
r2_v4.json (levels), r2_v6.json (wing shape), r2_fan_options.json (the fan), cost_options.json (rule set 1's growth
and boundary-layer options) and far_field_scenarios.json (the domain)).

    python scripts/size_factors.py        # the 20 reference wings at VC, 4 Re, band on and off: counts only

-> data/studies/size_factors.json
"""

from __future__ import annotations

import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))
from cfdauto.mesh.surface import build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import count_volume                   # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
RES = (1e5, 3e5, 1e6, 4e6)


def one(job):
    t, i = job
    w = wing_from_set(t, "reference", i)
    rows = []
    for re in RES:
        for band in (True, False):
            sm = build_surface(w.loft, re, "VC", band=band)
            c = count_volume(sm)
            rows.append({"type": t, "index": i, "re": re, "band": band, "cells": c["cells"], "n_layers": c["n_layers"],
                         "n_c": c["n_c"], "n_span": c["n_span"], "n_wake": c["n_wake"], "n_out": c["n_out"],
                         "surface_nodes": int(sm.wing.shape[0] * sm.wing.shape[1])})
    return rows


def med(v):
    return float(np.median(np.asarray(v, float)))


def main():
    with Pool(2) as p:
        rows = [r for part in p.map(one, [(t, i) for t in TYPES for i in range(5)]) for r in part]
    s = {}
    for re in RES:
        on = {(r["type"], r["index"]): r for r in rows if r["re"] == re and r["band"]}
        off = {(r["type"], r["index"]): r for r in rows if r["re"] == re and not r["band"]}
        s[f"Re {re:.0e}"] = {"cells_band_on": med([r["cells"] for r in on.values()]),
                             "cells_band_off": med([r["cells"] for r in off.values()]),
                             "on_over_off": med([on[k]["cells"] / off[k]["cells"] for k in on]),
                             "on_over_off_range": [float(min(on[k]["cells"] / off[k]["cells"] for k in on)),
                                                   float(max(on[k]["cells"] / off[k]["cells"] for k in on))],
                             "n_c_on": med([r["n_c"] for r in on.values()]), "n_c_off": med([r["n_c"] for r in off.values()]),
                             "n_layers_on": med([r["n_layers"] for r in on.values()]),
                             "n_layers_off": med([r["n_layers"] for r in off.values()]),
                             "n_span": med([r["n_span"] for r in on.values()])}
    out = {"what": "cells counted at VC, the 20 reference wings, rule set 2: 4 Re levels, band on and off",
           "summary": s, "rows": rows}
    (HERE / "data" / "studies" / "size_factors.json").write_text(json.dumps(out, indent=1))
    for k, v in s.items():
        print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})


if __name__ == "__main__":
    main()
