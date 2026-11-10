"""What if the domain were smaller? Cells (counted) and the outcome (built) for a few far-field sizes.

    python scripts/far_field_study.py            # the 20 reference wings, Re 3e5: counts at VC, C, M, F; builds at VC

A scenario is (front, aft) in mean chords: `front` sets the half circle ahead (and so above and below) and the
distance past the tip, exactly as far.distance_c does today; `aft` sets the outflow behind the most aft trailing edge.
Today both are 80 (law 15). The mesher is the real one: the rules file is copied with far.distance_c = front, and the
outflow is moved to `aft` behind the trailing edge (`plane.domain` with x_out changed; nothing else). A what-if study:
the rules are not changed. Check 10 then asks for `front` from every wall node.
-> data/studies/far_field_scenarios.json
"""

from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))
from cfdauto.mesh.surface import build_surface, wing_from_set   # noqa: E402
from cfdauto.volume import plane as pl                            # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume     # noqa: E402

SCENARIOS = [(10, 20), (20, 40), (40, 40), (40, 80), (80, 80)]   # (front, aft) in mean chords; (80, 80) is today
LEVELS = ("VC", "C", "M", "F")
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
RE = 3e5
RULES = HERE / "configs" / "volume.yaml"
_DOMAIN = pl.domain


def _config(front: float) -> Path:
    text = RULES.read_text()
    old = "  distance_c: 80.0 "
    assert text.count(old) == 1, "far.distance_c not found"
    p = Path(tempfile.gettempdir()) / f"volume_front{front:g}.yaml"
    p.write_text(text.replace(old, f"  distance_c: {float(front)} "))
    return p


def _set_aft(aft: float | None) -> None:
    """The outflow `aft` mean chords behind the most aft trailing edge (+1 c, as today's x_te + far + 1)."""
    if aft is None:
        pl.domain = _DOMAIN
        return

    def domain(rings, n_side, rl):
        d = _DOMAIN(rings, n_side, rl)
        return dataclasses.replace(d, x_out=d.x_b + float(aft) + 1.0)
    pl.domain = domain


def one_wing(job: tuple[str, int]) -> list[dict]:
    t, i = job
    w = wing_from_set(t, "reference", i)
    rows = []
    for level in LEVELS:
        sm = build_surface(w.loft, RE, level)
        for front, aft in SCENARIOS:
            _set_aft(aft)
            c = count_volume(sm, config=_config(front))
            rows.append({"type": t, "index": i, "level": level, "front": front, "aft": aft, "cells": c["cells"],
                         "n_layers": c["n_layers"], "n_wake": c["n_wake"], "n_out": c["n_out"], "n_span": c["n_span"]})
            if level == "VC":                                     # does the mesh still build and pass?
                t0 = time.time()
                vm = build_volume(sm, config=_config(front))
                rows[-1] |= {"outcome": vm.outcome, "failed": [x.name for x in vm.failed()],
                             "built_cells": vm.cells, "seconds": round(time.time() - t0, 1),
                             "domain": vm.info["domain"]}
        _set_aft(None)
    return rows


def dist(v) -> dict:
    v = np.asarray(v, float)
    return {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max()), "n": int(v.size)}


def main() -> None:
    jobs = [(t, i) for t in TYPES for i in range(5)]
    with Pool(2) as p:
        rows = [r for part in p.map(one_wing, jobs) for r in part]
    out = {"what": "cells (counted) for smaller far fields, the 20 reference wings, Re 3e5; outcome built at VC",
           "scenarios": [{"front_c": f, "aft_c": a} for f, a in SCENARIOS], "rows": rows, "summary": {}}
    for f, a in SCENARIOS:
        key = f"front {f} / aft {a}"
        s = {}
        for level in LEVELS:
            rr = [r for r in rows if r["level"] == level and (r["front"], r["aft"]) == (f, a)]
            today = {(r["type"], r["index"]): r["cells"] for r in rows if r["level"] == level and (r["front"], r["aft"]) == (80, 80)}
            s[level] = {"cells": dist([r["cells"] for r in rr]),
                        "vs_today": dist([r["cells"] / today[(r["type"], r["index"])] for r in rr]),
                        "n_layers": dist([r["n_layers"] for r in rr]), "n_wake": dist([r["n_wake"] for r in rr]),
                        "n_out": dist([r["n_out"] for r in rr])}
        vc = [r for r in rows if r["level"] == "VC" and (r["front"], r["aft"]) == (f, a)]
        s["VC_built"] = {"passed": sum(r["outcome"] == "passed" for r in vc), "of": len(vc),
                         "failed": sorted({x for r in vc for x in r["failed"]}),
                         "same_as_count": all(r["built_cells"] == r["cells"] for r in vc)}
        out["summary"][key] = s
    (HERE / "data" / "studies" / "far_field_scenarios.json").write_text(json.dumps(out, indent=1))
    for key, s in out["summary"].items():
        print(key, {L: (round(s[L]["cells"]["median"] / 1e6, 2), round(s[L]["vs_today"]["median"], 3)) for L in LEVELS},
              s["VC_built"])


if __name__ == "__main__":
    main()
