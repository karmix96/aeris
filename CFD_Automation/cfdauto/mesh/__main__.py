"""python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5

The first approach (2-3 Nov 2026): add --config configs/surface_first.yaml (its levels are C, M, F, FF)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from ..paths import STAGE2
from .laws import CONFIG, rules
from .surface import build_surface, mesh_name, wing_from_set, write


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Surface mesh of one Stage 1 wing.")
    p.add_argument("--type", required=True, choices=["bwb", "flying_wing", "cranked", "tapered"])
    p.add_argument("--set", required=True, help="training_focus, training_full, corner1, corner2, reference")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--level", default=None, help="a level of the config: VC, C, M, F (default: the coarsest, VC)")
    p.add_argument("--re", type=float, default=3.0e5, help="Re on the mean chord (Stage 0 levels: 1e5, 3e5, 1e6, 4e6 since 8 Nov 2026)")
    p.add_argument("--config", default=None, help="rules file (default configs/surface.yaml; the first approach: "
                                                   "configs/surface_first.yaml)")
    p.add_argument("--out", default=None, help="default: Stage_2_surface_mesh/data/meshes/<type>/<set>/<index>/<name> "
                                               "(data/meshes/<config name>/... for another config)")
    a = p.parse_args(argv)
    rl = rules(a.level, a.config)                 # refuses a level the config does not have
    t0 = time.time()
    wing = wing_from_set(a.type, a.set, a.index)
    mesh = build_surface(wing.loft, a.re, rl.level, a.config)
    root = STAGE2 / "data" / "meshes"
    if a.config and Path(a.config).resolve() != CONFIG.resolve():
        root = root / Path(a.config).stem
    out = Path(a.out) if a.out else root / a.type / a.set / f"{a.index:03d}" / mesh_name(mesh, wing)
    write(mesh, wing, out)
    i = mesh.info
    state = "passed" if mesh.passed else "REFUSED by " + ", ".join(c.name for c in mesh.failed())
    print(f"{out}\n  {state}; ring {i['n_ring']} x {i['n_span']} stations, cap {i['cap']['shape']}, {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
