"""V4: the family. Per wing, the Stage 2 surface family (VC, C, M, F), the volume built at the levels that fit here and
counted at the rest; check 13 on the built levels; one JSON row per wing.

    python scripts/family_study.py --types bwb flying_wing --levels VC C --tag ref_a         # 2 x 5 wings
    python scripts/family_study.py --types bwb --indices 0 --levels VC C M --tag m_bwb       # M where memory allows

Rows go to data/studies/family_<tag>.jsonl (--resume skips wings already there). Every level not built is counted
(count_volume); F is never built here (48 M cells on BWB reference wing 0; this machine has 7 GB).
"""

from __future__ import annotations

import argparse
import gc
import json
import resource
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruleset import CONFIG, PREFIX  # noqa: E402
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import _jsonable, build_family, wing_from_set      # noqa: E402
from cfdauto.volume.family import check13, measures                          # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume                 # noqa: E402

LEVELS = ("VC", "C", "M", "F")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--types", nargs="+", default=["bwb", "flying_wing", "cranked", "tapered"])
    p.add_argument("--indices", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    p.add_argument("--levels", nargs="+", default=["VC", "C"])
    p.add_argument("--re", type=float, default=3e5)
    p.add_argument("--tag", required=True)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    out = HERE / "data" / "studies" / f"family_{PREFIX}{a.tag}.jsonl"
    done = set()
    if a.resume and out.exists():
        done = {(r["type"], r["index"]) for r in map(json.loads, out.read_text().splitlines())}
    f = open(out, "a")
    for t in a.types:
        for i in a.indices:
            if (t, i) in done:
                continue
            row = {"type": t, "set": "reference", "index": i, "re": a.re, "levels": {}}
            t0 = time.time()
            try:
                w = wing_from_set(t, "reference", i)
                row["hash8"] = w.input_hash[:8]
                fam = build_family(w.loft, a.re)
            except Exception as e:
                row |= {"outcome": "crashed", "stage": "surface", "error": repr(e)}
                f.write(json.dumps(_jsonable(row)) + "\n")
                f.flush()
                continue
            meas = {}
            for lev in LEVELS:
                if lev in a.levels:
                    try:
                        vm = build_volume(fam[lev], config=CONFIG)
                        meas[lev] = measures(vm)
                        row["levels"][lev] = {"built": True, "outcome": vm.outcome, "review": vm.review,
                                              "failed": [c.name for c in vm.failed()], "cells": vm.cells,
                                              "ram_gib": vm.info["ram_gib_adflow"], "seconds": vm.info["seconds_total"],
                                              "bl_cells_min": vm.info["bl_cells_min"],
                                              "cap_nose_corner_min_sj": vm.info.get("cap_nose_corner_min_sj"),
                                              "min_sj_but_cap_nose_corners": vm.info.get("min_sj_but_cap_nose_corners"),
                                              "checks": {c.name: c.value for c in vm.checks},
                                              "measures": meas[lev]}
                        del vm
                        gc.collect()
                    except Exception as e:
                        row["levels"][lev] = {"built": True, "outcome": "crashed", "error": repr(e),
                                              "trace": traceback.format_exc()[-2000:]}
                else:
                    row["levels"][lev] = {"built": False, "outcome": "counted"} | count_volume(fam[lev], config=CONFIG)
            if len(meas) >= 2:
                c, table = check13(meas)
                row["check13"] = {"passed": c.passed, "value": c.value, "limit": c.limit, "where": c.note,
                                  "ratios": table}
            row["seconds"] = round(time.time() - t0, 1)
            row["max_rss_gib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 20
            f.write(json.dumps(_jsonable(row)) + "\n")
            f.flush()
            c13 = row.get("check13", {})
            print(t, i, {k: (v["outcome"], v["cells"]) for k, v in row["levels"].items()},
                  "check13", c13.get("passed"), f"{c13.get('value', 0):.4f}", c13.get("where"),
                  f"rss {row['max_rss_gib']:.2f} GiB", flush=True)
    f.close()


if __name__ == "__main__":
    main()
