"""The level ladder, today and lighter, with one more coarse level (Mike, 11 Nov 2026: "start from 800k ... and
gradually move to the F mesh"). A what-if study: the rules files are copied and changed; the rules are unchanged.

    python scripts/ladder_study.py              (wing 0 of each type at the 4 Re levels; about 15 min on 2 cores)
    python scripts/ladder_study.py --ref20      (the 20 reference wings at Re 3e5; about 30 min)
    (--light-only with either: count the light rules again and keep today's rows from the file)
    python scripts/ladder_study.py --family     (the light rules built on BWB reference wing 0: VVC to M, check 13)
    python scripts/ladder_study.py --why130     (why the wall growth is 1.28: BWB 3 at VC, every subset; 2 min)
    python scripts/size_figures.py              (docs/page/ladder.png from the json)

Two rule sets on the same wings (wing 0 of each type, the 4 Re levels):
    today    rule set 2 as it is
    light    the three too-strict rules loosened (volume_rules.md, section 20): wall-normal growth 1.28 at VC, station
             growth 1.25 at VC, the tip gap 0.1 % of the semi-span at M (DPW's value) instead of 2 x s0
Five levels: VVC (one step coarser than VC: every anchor stays where it is, so VVC is past the hard minimums, y+ 1.3),
VC, C, M, F. Counted at every level; the surface checks of every counted mesh; the volume built and checked at VVC and
VC (both sets) and at C (light).
-> data/studies/ladder.json, ladder_ref20.json (+ *_rows.jsonl while they run), ladder_family.json
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import sys
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from knob_study import KNOBS, SURFACE, VOLUME, TYPES          # noqa: E402
sys.path.insert(0, str(HERE.parent))
import cfdauto.volume.laws as volume_laws                      # noqa: E402
from cfdauto.mesh.laws import rules as mesh_rules               # noqa: E402
from cfdauto.mesh.surface import build_family, build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume     # noqa: E402

STUDIES = HERE / "data" / "studies"
LEVELS = ("VVC", "VC", "C", "M", "F")
LEVEL_K = {lev: k - 1 for k, lev in enumerate(LEVELS)}           # VC = 0, as in the rules today
RES = (3e5, 4e6, 1e5, 1e6)
# wall-normal growth 1.28, not 1.30: at 1.30 it equals the far limit and, with the other two changes, BWB reference wing
# 3 at VC is refused by the growth check (1.0105 against the 1.01 allowed; the first run, kept in ladder_wall130*.json)
KNOBS = KNOBS | {"wall_g128": ("volume", [('  growth: {value: 1.25, at: VC, why: "hard minimum, decision 71; DPW"}',
                                           '  growth: {value: 1.28, at: VC, why: "hard minimum, decision 71; DPW"}')],
                               "wall-normal growth 1.28 at VC (not 1.25)")}
PACKS = {"today": ([], False, "rule set 2 as it is"),
         "light": (["wall_g128", "span_g125"], True,
                   "wall-normal growth 1.28 and station growth 1.25 at VC; tip gap 0.1 % of the semi-span at M")}
BUILD = {"today": ("VVC", "VC"), "light": ("VVC", "VC", "C")}
_CUR = {"surface": None}


def _surface_rules(level):
    """The surface rules the volume laws read (y+ of the level): from the what-if copy, which knows VVC."""
    return mesh_rules(level, _CUR["surface"])


volume_laws.surface_rules = _surface_rules                       # a what-if hook; the package is not changed


def configs(pack: str, tip_s0: float | None) -> tuple[Path, Path]:
    """(surface file, volume file) of one rule set with five levels. The file name carries a hash of the text: the
    rules loaders cache a file by its name."""
    knobs, dpw, _ = PACKS[pack]
    out = []
    for which, src in (("surface", SURFACE), ("volume", VOLUME)):
        reps = [("  names: [VC, C, M, F] ", "  names: [VVC, VC, C, M, F] ")]
        reps += [rep for k in knobs if KNOBS[k][0] == which for rep in KNOBS[k][1]]
        if which == "surface" and dpw:
            reps.append(("  tip_gap_in_s0: 2.0 ", f"  tip_gap_in_s0: {tip_s0:.1f} "))
        text = src.read_text()
        for old, new in reps:
            assert text.count(old) == 1, (pack, old)
            text = text.replace(old, new)
        tag = hashlib.sha1(text.encode()).hexdigest()[:10]
        p = Path(tempfile.gettempdir()) / f"ladder_{os.getpid()}_{pack}_{tag}_{src.name}"
        p.write_text(text)
        out.append(p)
    return out[0], out[1]


def tip_dpw_in_s0(sm, level: str) -> float:
    """0.1 % of the semi-span at M, in s0 of this wing and Re (the same number at every level: s0 follows y+)."""
    s0_m = sm.info["s0_tip_m"] * 1.3 ** (LEVEL_K[level] - LEVEL_K["M"])
    return 0.001 * sm.info["semi_span_m"] / s0_m


def one(job) -> list[dict]:
    t, i, re = job
    w = wing_from_set(t, "reference", i)
    s0_cfg, _ = configs("today", None)
    _CUR["surface"] = s0_cfg
    tip_s0 = tip_dpw_in_s0(build_surface(w.loft, re, "VC", config=s0_cfg), "VC")
    rows = []
    for pack in _CUR.get("packs", PACKS):
        s_cfg, v_cfg = configs(pack, tip_s0)
        _CUR["surface"] = s_cfg
        for lev in LEVELS:
            t0 = time.time()
            sm = build_surface(w.loft, re, lev, config=s_cfg)
            c = count_volume(sm, config=v_cfg)
            rl = volume_laws.rules(lev, v_cfg)
            r = {"pack": pack, "type": t, "index": i, "re": re, "level": lev, "cells": c["cells"],
                 "n_layers": c["n_layers"], "n_c": c["n_c"], "n_span": c["n_span"], "n_wake": c["n_wake"],
                 "n_out": c["n_out"], "surface_passed": bool(sm.passed),
                 "surface_failed": [x.name for x in sm.failed()], "yplus": float(rl.yplus),
                 "wall_growth": float(rl.setting("wall_growth")),
                 "tip_gap_in_s0": float(sm.info["tip_gap_asked_m"] / sm.info["s0_tip_m"]),
                 "seconds_count": round(time.time() - t0, 1)}
            if lev in BUILD[pack] and sm.passed:
                t0 = time.time()
                vm = build_volume(sm, config=v_cfg)
                r |= {"outcome": vm.outcome, "failed": [x.name for x in vm.failed()], "built_cells": vm.cells,
                      "min_sj": vm.info.get("min_sj_but_cap_nose_corners"), "bl_cells_min": vm.info.get("bl_cells_min"),
                      "seconds_build": round(time.time() - t0, 1)}
                del vm
                gc.collect()
            elif lev in BUILD[pack]:
                r |= {"outcome": "surface refused", "failed": r["surface_failed"]}
            rows.append(r)
            del sm
    with open(STUDIES / _CUR.get("rows", "ladder_rows.jsonl"), "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows


def dist(v) -> dict:
    v = np.asarray(v, float)
    return {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max()), "n": int(v.size)}


def summarize(rows: list[dict]) -> dict:
    s = {}
    for pack in PACKS:
        s[pack] = {"words": PACKS[pack][2], "by_re": {}}
        for re in sorted({r["re"] for r in rows}):
            d = {}
            for lev in LEVELS:
                rr = [r for r in rows if r["pack"] == pack and r["re"] == re and r["level"] == lev]
                if not rr:
                    continue
                built = [r for r in rr if "outcome" in r]
                d[lev] = {"cells": dist([r["cells"] for r in rr]), "yplus": rr[0]["yplus"],
                          "wall_growth": rr[0]["wall_growth"],
                          "counts": {k: float(np.median([r[k] for r in rr]))
                                     for k in ("n_layers", "n_c", "n_span", "n_wake", "n_out")},
                          "surfaces": {"passed": sum(r["surface_passed"] for r in rr), "of": len(rr),
                                       "failed": sorted({f"{x} ({r['type']})" for r in rr for x in r["surface_failed"]})},
                          "built": {"passed": sum(r["outcome"] == "passed" for r in built), "of": len(built),
                                    "failed": sorted({f"{x} ({r['type']})" for r in built for x in r["failed"]})}}
            s[pack]["by_re"][f"{re:.0e}"] = d
    return s


def main(ref20: bool = False) -> None:
    name = "ladder_ref20" if ref20 else "ladder"
    _CUR["rows"] = f"{name}_rows.jsonl"
    (STUDIES / _CUR["rows"]).unlink(missing_ok=True)
    jobs = [(t, i, 3e5) for i in range(5) for t in TYPES] if ref20 else [(t, 0, re) for re in RES for t in TYPES]
    old = []
    if "--light-only" in sys.argv:                       # today's rows are kept from the file (rule set 2 is unchanged)
        old = [r for r in json.loads((STUDIES / f"{name}.json").read_text())["rows"] if r["pack"] == "today"]
        _CUR["packs"] = ["light"]
    with Pool(2) as p:
        rows = old + [r for part in p.imap_unordered(one, jobs, chunksize=1) for r in part]
    what = "the 20 reference wings at Re 3e5" if ref20 else "wing 0 of each reference type at the 4 Re levels"
    out = {"what": f"the level ladder (VVC, VC, C, M, F) of {what}: rule set 2 "
                   "as it is (today) and with three rules loosened (light); cells counted, every surface checked, the "
                   "volume built at VVC and VC (and C, light)", "packs": {k: v[2] for k, v in PACKS.items()},
           "summary": summarize(rows), "rows": rows}
    (STUDIES / f"{name}.json").write_text(json.dumps(out, indent=1))
    (STUDIES / _CUR["rows"]).unlink(missing_ok=True)
    for pack, s in out["summary"].items():
        for re, d in s["by_re"].items():
            print(f"{pack:6s} Re {re}  " + "  ".join(
                f"{lev} {v['cells']['median'] / 1e6:.2f} M (s {v['surfaces']['passed']}/{v['surfaces']['of']}"
                f" b {v['built']['passed']}/{v['built']['of']})" for lev, v in d.items()))


def family() -> None:
    """The light rules built on BWB reference wing 0 at Re 3e5: one surface family, the volume at VVC, VC, C and M,
    every check of each mesh, and check 13 between neighbouring levels."""
    from cfdauto.volume.family import check13, measures
    w = wing_from_set("bwb", "reference", 0)
    s0_cfg, _ = configs("today", None)
    _CUR["surface"] = s0_cfg
    tip_s0 = tip_dpw_in_s0(build_surface(w.loft, 3e5, "VC", config=s0_cfg), "VC")
    s_cfg, v_cfg = configs("light", tip_s0)
    _CUR["surface"] = s_cfg
    levels = [lev for lev in LEVELS if lev != "F"]
    fam = build_family(w.loft, 3e5, levels=levels, config=s_cfg)
    meas, out = {}, {"wing": "bwb reference 0", "re": 3e5, "pack": "light", "tip_gap_in_s0": tip_s0, "levels": {}}
    for lev in levels:
        t0 = time.time()
        vm = build_volume(fam[lev], config=v_cfg)
        meas[lev] = measures(vm)
        out["levels"][lev] = {"outcome": vm.outcome, "failed": [c.name for c in vm.failed()], "cells": vm.cells,
                              "checks": {c.name: {"passed": bool(c.passed), "value": c.value} for c in vm.checks},
                              "nose_family": fam[lev].info["nose_family"]["label"],
                              "seconds": round(time.time() - t0, 1)}
        print(lev, vm.outcome, vm.cells, [c.name for c in vm.failed()], flush=True)
        del vm
        gc.collect()
    c, table = check13(meas)
    out["check13"] = {"passed": bool(c.passed), "value": c.value, "where": c.note, "ratios": table}
    print("check 13", c.passed, f"{c.value:.4f}", c.note)
    (STUDIES / "ladder_family.json").write_text(json.dumps(out, indent=1, default=float))


def why130() -> None:
    """Why the wall-normal growth is 1.28 and not 1.30: BWB reference wing 3 at VC, Re 3e5, built with every subset of
    the three changes at 1.30 and with the light rules (1.28); the growth check of each (limit: 1.01 x its growth)."""
    KNOBS["wall_g130"] = ("volume", [('  growth: {value: 1.25, at: VC, why: "hard minimum, decision 71; DPW"}',
                                      '  growth: {value: 1.30, at: VC, why: "hard minimum, decision 71; DPW"}')], "")
    sub = {"wall 1.30": (["wall_g130"], False), "stations 1.25": (["span_g125"], False), "tip gap DPW": ([], True),
           "wall 1.30 + stations": (["wall_g130", "span_g125"], False), "wall 1.30 + tip gap": (["wall_g130"], True),
           "stations + tip gap": (["span_g125"], True), "all three, wall 1.30": (["wall_g130", "span_g125"], True),
           "all three, wall 1.28 (light)": (["wall_g128", "span_g125"], True)}
    w = wing_from_set("bwb", "reference", 3)
    s0_cfg, _ = configs("today", None)
    _CUR["surface"] = s0_cfg
    tip_s0 = tip_dpw_in_s0(build_surface(w.loft, 3e5, "VC", config=s0_cfg), "VC")
    out = {"wing": "bwb reference 3", "level": "VC", "re": 3e5, "cases": {}}
    for name, (knobs, dpw) in sub.items():
        PACKS[name] = (knobs, dpw, name)
        s_cfg, v_cfg = configs(name, tip_s0)
        _CUR["surface"] = s_cfg
        vm = build_volume(build_surface(w.loft, 3e5, "VC", config=s_cfg), config=v_cfg)
        g = next(c for c in vm.checks if c.name == "growth")
        out["cases"][name] = {"outcome": vm.outcome, "failed": [c.name for c in vm.failed()], "cells": vm.cells,
                              "growth_over_limit": float(g.value), "where": g.note}
        print(f"{name:30s} {vm.outcome:8s} growth / limit {float(g.value):.4f}  cells {vm.cells:,}", flush=True)
        del vm
        gc.collect()
    (STUDIES / "ladder_wall130_why.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    if "--why130" in sys.argv:
        why130()
    elif "--family" in sys.argv:
        family()
    else:
        main(ref20="--ref20" in sys.argv)
