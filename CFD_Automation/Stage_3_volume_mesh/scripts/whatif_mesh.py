"""One what-if volume mesh with its solver files, for the solver tests (solve/NIGHT_11NOV.md): today's rules or the
light rules of decision 114 (not decided), at any of five levels VVC, VC, C, M, F. A what-if: the rules files are
copied and changed as in scripts/ladder_study.py; configs/*.yaml and cfdauto/ are not touched.

    python scripts/whatif_mesh.py --pack today --level VVC --type bwb --index 0 --re 3e5 --formats cgns su2
    python scripts/whatif_mesh.py --pack light --level VC  --type bwb --index 0 --re 3e5 --formats cgns su2
    python scripts/whatif_mesh.py --pack today --level VC  --type bwb --index 0 --check-production
        (today's VC through the what-if copy must give the same nodes as one_mesh.py's VC: the what-if path is checked)

    today    rule set 2 as it is, with one more level VVC in front (one step coarser than VC: past the hard minimums,
             y+ 1.3, wall-normal growth 1.34: a preview level only)
    light    wall-normal growth 1.28 and station growth 1.25 at VC; tip gap 0.1 % of the semi-span at M (DPW)

Writes data/meshes/whatif_<pack>_<level>_<hash8>_re<Re>/ (not in git): the folder write() makes (blocks.npz,
quality.json, manifest.json, volume.cgns, volume.su2), the two what-if rules files, and whatif.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE.parent))
import cfdauto.volume.laws as volume_laws                      # noqa: E402

PRODUCTION_SURFACE_RULES = volume_laws.surface_rules           # kept before ladder_study puts in its what-if hook
import ladder_study as L                                       # noqa: E402
from ruleset import CONFIG                                     # noqa: E402
from cfdauto.mesh.surface import _jsonable, build_surface, fmt_re, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume, write          # noqa: E402


def whatif_rules(w, pack: str, re: float) -> tuple[Path, Path, float]:
    """(surface file, volume file, tip gap in s0) of one pack for this wing and Re, as ladder_study.one() makes them."""
    s0_cfg, _ = L.configs("today", None)
    L._CUR["surface"] = s0_cfg
    tip_s0 = L.tip_dpw_in_s0(build_surface(w.loft, re, "VC", config=s0_cfg), "VC")
    s_cfg, v_cfg = L.configs(pack, tip_s0)
    L._CUR["surface"] = s_cfg
    return s_cfg, v_cfg, tip_s0


def build(pack: str, level: str, wing_type: str, set_name: str, index: int, re: float):
    w = wing_from_set(wing_type, set_name, index)               # refuses the hold-out sets
    s_cfg, v_cfg, tip_s0 = whatif_rules(w, pack, re)
    sm = build_surface(w.loft, re, level, config=s_cfg)
    if not sm.passed:
        raise SystemExit(f"the what-if surface was refused: {', '.join(c.name for c in sm.failed())}")
    vm = build_volume(sm, config=v_cfg)
    return w, sm, vm, s_cfg, v_cfg, tip_s0


def check_production(wing_type: str, set_name: str, index: int, re: float, level: str) -> dict:
    """Today's rules through the what-if copy against the production build (one_mesh.py) at one of VC, C, M, F."""
    if level == "VVC":
        raise SystemExit("--check-production needs a production level (VC, C, M, F)")
    _, _, vw, *_ = build("today", level, wing_type, set_name, index, re)
    volume_laws.surface_rules = PRODUCTION_SURFACE_RULES       # the production path, no hook
    try:
        w = wing_from_set(wing_type, set_name, index)
        vp = build_volume(build_surface(w.loft, re, level), config=CONFIG)
    finally:
        volume_laws.surface_rules = L._surface_rules
    same_shapes = {k: list(b.shape) for k, b in vw.blocks.items()} == {k: list(b.shape) for k, b in vp.blocks.items()}
    diff = max(float(np.abs(vw.blocks[k] - vp.blocks[k]).max()) for k in vw.blocks) if same_shapes else None
    return {"level": level, "cells_whatif": vw.cells, "cells_production": vp.cells, "same_block_shapes": same_shapes,
            "max_node_difference": diff, "same_node_hash": vw.node_hash() == vp.node_hash(),
            "whatif_passed": vw.passed, "production_passed": vp.passed}


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pack", required=True, choices=list(L.PACKS))
    p.add_argument("--level", default="VC", choices=list(L.LEVELS))
    p.add_argument("--type", required=True, choices=list(L.TYPES))
    p.add_argument("--set", default="reference")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--re", type=float, default=3e5)
    p.add_argument("--formats", nargs="+", default=["npz", "cgns", "su2"], choices=["npz", "cgns", "su2"])
    p.add_argument("--out", default=None, help="default: data/meshes/whatif_<pack>_<level>_<hash8>_re<Re>/")
    p.add_argument("--check-production", action="store_true",
                   help="build today's rules at a production level both ways and compare the nodes; writes nothing")
    a = p.parse_args(argv)
    if a.check_production:
        if a.pack != "today":
            raise SystemExit("--check-production compares today's rules only")
        print(json.dumps(check_production(a.type, a.set, a.index, a.re, a.level), indent=1))
        return
    t0 = time.time()
    w, sm, vm, s_cfg, v_cfg, tip_s0 = build(a.pack, a.level, a.type, a.set, a.index, a.re)
    name = f"whatif_{a.pack}_{a.level}_{w.input_hash[:8]}_{fmt_re(a.re)}"
    out = Path(a.out) if a.out else HERE / "data" / "meshes" / name
    write(vm, w, out, formats=tuple(a.formats))
    shutil.copy(s_cfg, out / "whatif_surface.yaml")
    shutil.copy(v_cfg, out / "whatif_volume.yaml")
    knobs, dpw, words = L.PACKS[a.pack]
    info = {"name": name, "pack": a.pack, "what": words, "knobs": knobs, "tip_gap_dpw": dpw,
            "tip_gap_in_s0": float(sm.info["tip_gap_asked_m"] / sm.info["s0_tip_m"]),
            "tip_gap_dpw_in_s0": float(tip_s0), "level": a.level,
            "yplus": float(volume_laws.rules(a.level, v_cfg).yplus),
            "wall_growth": float(volume_laws.rules(a.level, v_cfg).setting("wall_growth")),
            "wing": f"{a.type} {a.set} {a.index}", "re": a.re, "loft_backend": w.loft.backend,
            "cells": vm.cells, "outcome": vm.outcome, "failed": [c.name for c in vm.failed()],
            "note": "what-if rules (scripts/ladder_study.py); not a rule set; decision 114 is open"}
    (out / "whatif.json").write_text(json.dumps(_jsonable(info), indent=1))
    mf = out / ("manifest.json" if vm.passed else "refusal.json")
    man = json.loads(mf.read_text())
    man |= {"name": name, "production_name": man["name"], "whatif": info}   # case.py names the case after this
    mf.write_text(json.dumps(_jsonable(man), indent=1))
    print(f"{out}\n  {vm.outcome}; {vm.cells:,} cells; y+ {info['yplus']:.3g}; wall growth {info['wall_growth']:.4g}; "
          f"tip gap {info['tip_gap_in_s0']:.1f} x s0; loft {w.loft.backend}; "
          + ("every check passed" if vm.passed else "refused by " + ", ".join(info["failed"]))
          + f"; {time.time() - t0:.0f} s")
    for f in sorted(out.iterdir()):
        print(f"  {f.name}  {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
