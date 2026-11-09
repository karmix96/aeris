"""The cost of the volume mesh and what would lower it: cells counted (not built) on the 20 reference wings, Re 3e5,
at every level, for the decided rules and for options that Mike would have to approve (none is applied).

    python scripts/cost_options.py                    # VC and F -> data/studies/cost_options.json
    python scripts/cost_options.py --levels VC C M F  # every level (about 2 x the time)

Options (each one changes one rule; "band off" is the Stage 2 option of decision 81, the surface without the
transition band):
    base          the decided rules
    out125        outboard growth 1.25 at VC instead of 1.15 (the station gaps past the tip grow faster)
    out130        outboard growth 1.30 at VC (= the far limit: no outboard fine zone)
    bl30M         30 cells across the boundary layer at M instead of at VC (17.8, 23.1, 30, 39)
    out125_bl30M  both
    band_off      the decided volume rules on the band-off surface
    band_off_all  band off, outboard 1.25, 30 cells at M
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import build_family, wing_from_set          # noqa: E402
from cfdauto.volume.laws import CONFIG                                # noqa: E402
from cfdauto.volume.volume import count_volume                        # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
LEVELS = tuple(sys.argv[sys.argv.index("--levels") + 1:]) if "--levels" in sys.argv else ("VC", "F")


def variant(text: str, outboard: float | None = None, bl_at: str | None = None) -> str:
    if outboard is not None:
        text, n = re.subn(r"(outboard:.*?\n\s+growth: \{value: )1\.15", rf"\g<1>{outboard:.2f}", text, flags=re.S)
        assert n == 1
    if bl_at is not None:
        text, n = re.subn(r"(bl_cells: \{value: 30, at: )VC", rf"\g<1>{bl_at}", text)
        assert n == 1
    return text


OPTIONS = {"base": ({}, True), "out125": ({"outboard": 1.25}, True), "out130": ({"outboard": 1.30}, True),
           "bl30M": ({"bl_at": "M"}, True), "out125_bl30M": ({"outboard": 1.25, "bl_at": "M"}, True),
           "band_off": ({}, False), "band_off_all": ({"outboard": 1.25, "bl_at": "M"}, False)}


def main(re_mean: float = 3e5) -> None:
    base = Path(CONFIG).read_text()
    tmp = Path(tempfile.mkdtemp())
    cfg = {}
    for name, (kw, _) in OPTIONS.items():
        p = tmp / f"volume_{name}.yaml"
        p.write_text(variant(base, **kw))
        cfg[name] = p
    rows = []
    t0 = time.time()
    for t in TYPES:
        for i in range(5):
            w = wing_from_set(t, "reference", i)
            fams = {True: build_family(w.loft, re_mean, levels=LEVELS),
                    False: build_family(w.loft, re_mean, levels=LEVELS, band=False)}
            for name, (kw, band) in OPTIONS.items():
                for lev in LEVELS:
                    c = count_volume(fams[band][lev], lev, re_mean, cfg[name])
                    rows.append({"type": t, "index": i, "option": name, "level": lev, "cells": c["cells"],
                                 "ram_gib": c["ram_gib_adflow"], "n_layers": c["n_layers"], "n_out": c["n_out"],
                                 "n_c": c["n_c"], "n_span": c["n_span"], "n_wake": c["n_wake"]})
            print(t, i, round(time.time() - t0), "s", flush=True)
    import numpy as np
    summ = {}
    for name in OPTIONS:
        summ[name] = {}
        for lev in LEVELS:
            v = np.array([r["cells"] for r in rows if r["option"] == name and r["level"] == lev], float)
            b = np.array([r["cells"] for r in rows if r["option"] == "base" and r["level"] == lev], float)
            summ[name][lev] = {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max()),
                               "vs_base_median": float(np.median(v / b))}
    out = {"re": re_mean, "wings": 20, "options": {k: v[0] | {"band": v[1]} for k, v in OPTIONS.items()},
           "summary": summ, "rows": rows}
    (HERE / "data" / "studies" / "cost_options.json").write_text(json.dumps(out, indent=1))
    for name in OPTIONS:
        print(name, {lev: f"{summ[name][lev]['median'] / 1e6:.2f} M ({summ[name][lev]['vs_base_median']:.2f})"
                     for lev in LEVELS})


if __name__ == "__main__":
    main()
