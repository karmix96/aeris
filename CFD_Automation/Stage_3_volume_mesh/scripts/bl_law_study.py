"""V0 measurement: which boundary-layer thickness the 30-cell rule should cross, and at which level (decision 86).

Counts only: no volume mesh is built or judged. For every reference wing at the four Re levels, on its Stage 2 surface
at VC, the wall-layer count the station distribution needs (the most over the stations) under five variants of the
rule; the growth inside delta that the variant asks (1.25 at VC is the cap); and the cells the variant puts across
the boundary layer at the stations where it binds. Writes data/studies/bl_law.json.

    python scripts/bl_law_study.py
"""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import build_surface, wing_from_set          # noqa: E402
from cfdauto.paths import re_levels                                  # noqa: E402
from cfdauto.volume import march as mr, plane as pl                  # noqa: E402
from cfdauto.volume.laws import VolumeRules, rules                   # noqa: E402

VARIANTS = {
    "turb_TE_VC": {"law": "turbulent", "x_c": 1.0, "at": "VC"},
    "turb_mid_VC": {"law": "turbulent", "x_c": 0.5, "at": "VC"},
    "lam_mid_VC": {"law": "laminar", "x_c": 0.5, "at": "VC"},
    "turb_TE_M": {"law": "turbulent", "x_c": 1.0, "at": "M"},
    "lam_mid_M": {"law": "laminar", "x_c": 0.5, "at": "M"},
}


def variant_rules(base: VolumeRules, v: dict) -> VolumeRules:
    raw = copy.deepcopy(base.raw)
    raw["wall"]["delta"] = {"law": v["law"], "x_c": v["x_c"]}
    raw["wall"]["bl_cells"] = {"value": 30, "at": v["at"], "why": "variant"}
    return VolumeRules(base.level, base.k, base.ratio, raw, base.config)


def count(surface, rl: VolumeRules) -> dict:
    n_side = surface.info["n_side"]
    out = []
    for r in surface.stations:
        s0 = rl.first_cell(r["re_local"], r["chord_m"])
        delta = rl.delta(r["re_local"], r["chord_m"])
        g_bl = float(mr.bl_growth(np.array([s0]), np.array([delta]), rl.bl_cells, rl.wall_growth)[0])
        st = pl.Station(0, r["y_m"], None, r["chord_m"], r["re_local"], s0, delta, g_bl)
        sp = pl.station_spec(st, 85.0, rl)
        n = float(mr.min_cells(**{k: np.array([v]) for k, v in sp.items()})[0])
        out.append({"layers": n, "g_bl": g_bl, "delta_over_s0": delta / s0})
    j = int(np.argmax([o["layers"] for o in out]))
    return {"layers": out[j]["layers"], "station": j, "g_bl_min": float(min(o["g_bl"] for o in out)),
            "delta_over_s0_min": float(min(o["delta_over_s0"] for o in out)),
            "bl_binds_stations": int(sum(o["g_bl"] < rl.wall_growth - 1e-9 for o in out)), "stations": len(out)}


def main() -> None:
    base = rules("VC")
    rows = []
    t0 = time.time()
    for typ in ("bwb", "flying_wing", "cranked", "tapered"):
        for idx in range(5):
            w = wing_from_set(typ, "reference", idx)
            for re in re_levels():
                sm = build_surface(w.loft, re, "VC")
                row = {"type": typ, "index": idx, "re": re}
                for name, v in VARIANTS.items():
                    row[name] = count(sm, variant_rules(base, v))
                rows.append(row)
                print(f"{typ} {idx} {re:.0e}: " + ", ".join(f"{k} {row[k]['layers']:.1f}" for k in VARIANTS), flush=True)
    summ = {}
    for name in VARIANTS:
        for re in re_levels():
            vals = [r[name]["layers"] for r in rows if r["re"] == re]
            gb = [r[name]["g_bl_min"] for r in rows if r["re"] == re]
            summ[f"{name}@{re:.0e}"] = {"layers_median": float(np.median(vals)), "layers_max": float(np.max(vals)),
                                        "g_bl_min": float(np.min(gb))}
    out = HERE / "data" / "studies" / "bl_law.json"
    out.write_text(json.dumps({"what": "V0: wall-layer count at VC (the most over the stations, straight lines to "
                                       "85 c, the station distribution with the wake band) for five variants of "
                                       "the 30-cell rule; counts only, no mesh judged",
                               "variants": VARIANTS, "summary": summ, "rows": rows,
                               "seconds": round(time.time() - t0, 1)}, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
