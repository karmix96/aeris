"""One volume mesh: one wing of a set, one level, one Re (rule set 2 unless STAGE3_RULESET=1).

    python scripts/one_mesh.py --type bwb --set reference --index 0 --level VC --re 3e5
    python scripts/one_mesh.py --type cranked --set training_focus --index 12 --level M --re 1e6 --formats npz cgns su2
    python scripts/one_mesh.py --type tapered --set reference --index 3 --level F --count     # cells and RAM, no build

Writes data/meshes/<name>/ (not in git): blocks.npz, quality.json, manifest.json and the solver files asked for
(volume.cgns for ADflow, volume.su2 for SU2; check 15 reads them back); a refused mesh writes only refusal.json.
(The volume.py docstring names `python -m cfdauto.volume`: that entry does not exist; this script is it. It lives here
because a new file in cfdauto/volume/ would change the volume code hash of every mesh.)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruleset import CONFIG  # noqa: E402
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume, mesh_name, write   # noqa: E402


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="The volume mesh of one wing (Stage 3).")
    p.add_argument("--type", required=True, choices=["bwb", "flying_wing", "cranked", "tapered"])
    p.add_argument("--set", required=True, help="reference, training_focus, training_full, corner1, corner2")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--level", default="VC", choices=["VC", "C", "M", "F"])
    p.add_argument("--re", type=float, default=3e5, help="Re on the mean chord (1e5, 3e5, 1e6, 4e6)")
    p.add_argument("--formats", nargs="+", default=["npz"], choices=["npz", "cgns", "su2"])
    p.add_argument("--count", action="store_true", help="count the cells and the RAM only (no build)")
    p.add_argument("--out", default=None, help="default: data/meshes/<name>/")
    a = p.parse_args(argv)
    t0 = time.time()
    w = wing_from_set(a.type, a.set, a.index)          # refuses the hold-out sets
    sm = build_surface(w.loft, a.re, a.level)
    if not sm.passed:
        raise SystemExit(f"the surface mesh was refused: {', '.join(c.name for c in sm.failed())}")
    if a.count:
        c = count_volume(sm, config=CONFIG)
        print(json.dumps({k: c[k] for k in ("level", "cells", "ram_gib_adflow", "n_layers", "n_span", "n_out")}))
        return
    vm = build_volume(sm, config=CONFIG)
    out = Path(a.out) if a.out else HERE / "data" / "meshes" / mesh_name(vm, w)
    write(vm, w, out, formats=tuple(a.formats))
    print(f"{out}\n  {vm.outcome}; {vm.cells:,} cells; "
          + ("every check passed" if vm.passed else "refused by " + ", ".join(c.name for c in vm.failed()))
          + f"; {time.time() - t0:.0f} s")
    for f in sorted(out.iterdir()):
        print(f"  {f.name}  {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
