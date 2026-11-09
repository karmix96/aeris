"""What the wake fan costs: cells counted (not built) at M, Re 3e5, on wing 0 of each reference type, for the
rule-set-2 fan and for smaller fans (none is applied; Mike decides). Every option keeps the angle per fan cell
(1.25 deg at M), so a narrower fan has fewer cells across it, not coarser ones.

    python scripts/fan_options.py      -> data/studies/r2_fan_options.json

Options:
    base       -5 .. +20 deg, 2 local chords (rule set 2)
    to15       -5 .. +15 deg
    to12       -5 .. +12 deg
    to10       -5 .. +10 deg (attached-flow angles only)
    len1       -5 .. +20 deg, 1 local chord
    one_angle  -2.5 .. +2.5 deg: a fan that follows the flow at one angle (alpha = 0); the cheapest per-angle mesh
    none       no fan: the 0.05 c margin only (the floor; what the fan costs in all)
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruleset import CONFIG, PREFIX                       # noqa: E402
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import build_surface, wing_from_set     # noqa: E402
from cfdauto.volume.laws import CONFIG as DEFAULT_CONFIG            # noqa: E402
from cfdauto.volume.volume import count_volume                    # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
T = lambda d: np.tan(np.radians(d))                               # noqa: E731
OPTIONS = {"base": (-5.0, 20.0, 2.0), "to15": (-5.0, 15.0, 2.0), "to12": (-5.0, 12.0, 2.0), "to10": (-5.0, 10.0, 2.0),
           "len1": (-5.0, 20.0, 1.0), "one_angle": (-2.5, 2.5, 2.0), "none": (-0.01, 0.01, 2.0)}


def variant(text: str, lo: float, hi: float, length: float) -> str:
    n = 20.0 * (T(hi) - T(lo)) / (T(20.0) - T(-5.0))             # same angle per fan cell
    for key, val in (("alpha_lo_deg", lo), ("alpha_hi_deg", hi), ("length_local_c", length)):
        text, m = re.subn(rf"({key}: )[-0-9.]+", rf"\g<1>{val}", text)
        assert m == 1, key
    text, m = re.subn(r"(fan_cells: \{value: )20(,)", rf"\g<1>{n:.6f}\g<2>", text)
    assert m == 1
    return text


def main() -> None:
    base = Path(CONFIG or DEFAULT_CONFIG).read_text()
    tmp = Path(tempfile.mkdtemp())
    cfg = {}
    for name, opt in OPTIONS.items():
        p = tmp / f"volume_fan_{name}.yaml"
        p.write_text(variant(base, *opt))
        cfg[name] = p
    rows, t0 = [], time.time()
    for t in TYPES:
        sm = build_surface(wing_from_set(t, "reference", 0).loft, 3e5, "M")
        for name in OPTIONS:
            c = count_volume(sm, "M", 3e5, cfg[name])
            rows.append({"type": t, "option": name, "cells": c["cells"], "n_layers": c["n_layers"],
                         "n_wake": c["n_wake"]})
        print(t, round(time.time() - t0), "s", flush=True)
    summ = {}
    for name in OPTIONS:
        r = [x for x in rows if x["option"] == name]
        b = [x for x in rows if x["option"] == "base"]
        summ[name] = {"cells_M_median": float(np.median([x["cells"] for x in r])),
                      "vs_base": [x["cells"] / y["cells"] - 1.0 for x, y in zip(r, b)],
                      "layers": [x["n_layers"] for x in r], "wake_nodes": [x["n_wake"] for x in r]}
    out = {"what": "the wake fan's cost, counted at M, Re 3e5, wing 0 of each reference type (rule set 2)",
           "options": {k: {"alpha_lo_deg": v[0], "alpha_hi_deg": v[1], "length_local_c": v[2]} for k, v in OPTIONS.items()},
           "rows": rows, "summary": summ}
    (HERE / "data" / "studies" / f"{PREFIX}fan_options.json").write_text(json.dumps(out, indent=1))
    for k, v in summ.items():
        print(k, round(v["cells_M_median"] / 1e6, 2), [f"{x:+.1%}" for x in v["vs_base"]], v["layers"], v["wake_nodes"])


if __name__ == "__main__":
    main()
