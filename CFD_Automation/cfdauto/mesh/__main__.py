"""python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5
python -m cfdauto.mesh --type bwb --set reference --index 0 --family --re 3e5     # every level, one nose factor

The first approach (2-3 Nov 2026): add --config configs/surface_first.yaml (its levels are C, M, F, FF).
A single level can still need a nose repair round of its own (recorded: info["nose_repair"]); --family builds every
level with one nose factor, so the ratio between levels stays exactly 1.3 (owner, 8 Nov 2026).
--band off builds without the transition band (fully turbulent runs; the mesh name ends in _noband); the default is
the config's chord.transition_band (on). The band and the solver are chosen together, right before the runs."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from ..paths import STAGE2
from .laws import CONFIG, rules
from .surface import build_family, build_surface, mesh_name, wing_from_set, write


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Surface mesh of one Stage 1 wing.")
    p.add_argument("--type", required=True, choices=["bwb", "flying_wing", "cranked", "tapered"])
    p.add_argument("--set", required=True, help="training_focus, training_full, corner1, corner2, reference")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--level", default=None, help="a level of the config: VC, C, M, F (default: the coarsest, VC)")
    p.add_argument("--family", action="store_true", help="every level of the config with one nose factor")
    p.add_argument("--re", type=float, default=3.0e5, help="Re on the mean chord (Stage 0 levels: 1e5, 3e5, 1e6, 4e6 since 8 Nov 2026)")
    p.add_argument("--band", choices=["on", "off"], default=None,
                   help="the transition band (default: the config's, on): off for fully turbulent runs")
    p.add_argument("--config", default=None, help="rules file (default configs/surface.yaml; the first approach: "
                                                   "configs/surface_first.yaml)")
    p.add_argument("--out", default=None, help="default: Stage_2_surface_mesh/data/meshes/<type>/<set>/<index>/<name> "
                                               "(data/meshes/<config name>/... for another config)")
    a = p.parse_args(argv)
    band = None if a.band is None else a.band == "on"
    rl = rules(a.level, a.config, band)           # refuses a level the config does not have
    t0 = time.time()
    wing = wing_from_set(a.type, a.set, a.index)
    meshes = (build_family(wing.loft, a.re, None, a.config, band) if a.family
              else {rl.level: build_surface(wing.loft, a.re, rl.level, a.config, band=band)})
    root = STAGE2 / "data" / "meshes"
    if a.config and Path(a.config).resolve() != CONFIG.resolve():
        root = root / Path(a.config).stem
    for mesh in meshes.values():
        out = (Path(a.out) / mesh_name(mesh, wing) if a.family else Path(a.out)) if a.out else \
            root / a.type / a.set / f"{a.index:03d}" / mesh_name(mesh, wing)
        write(mesh, wing, out)
        i = mesh.info
        state = "passed" if mesh.passed else "REFUSED by " + ", ".join(c.name for c in mesh.failed())
        print(f"{out}\n  {state}; ring {i['n_ring']} x {i['n_span']} stations, cap {i['cap']['shape']}; "
              f"nose repair: {i['nose_repair']['label']}; transition band: {'on' if rl.transition_band else 'off'}")
    print(f"{time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
