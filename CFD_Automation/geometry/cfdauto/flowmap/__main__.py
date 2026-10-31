"""Flow map of one wing.

    python -m cfdauto.flowmap --type bwb --set reference --index 0 --speed 25 --altitude 1000 --alpha 3
    python -m cfdauto.flowmap --type cranked --vector my_wing.json --family conventional --mach 0.1
    python -m cfdauto.flowmap --type bwb --set reference --index 0 --mach 0.08 --sheet --machs 0.03 0.06 0.09 0.12 --alphas 0 2 4 6 8
    (add --airfoils mh61 mh61 mh45 mh45 to try other sections; --method xfoil to run XFOIL directly;
     --ncrit 5 or 11, --induced, --strips 5 for the assumption checks)

Writes <out>.png and <out>.json (default data/flowmaps/<type>_<set>_<index>); with --sheet,
<out>_sheet.png and <out>_sheet.json (Mach x angle maps from the section tables).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..geometry.build import load_set
from ..geometry.params import FAMILIES, GEOMETRY_ROOT, TAILLESS_TYPES, WING_TYPES, load_config
from .core import flow_map, plot, plot_sheet, sweep_sheet


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--type", choices=WING_TYPES, required=True, help="generator type whose laws read the vector")
    p.add_argument("--set"); p.add_argument("--index", type=int); p.add_argument("--vector")
    p.add_argument("--family", choices=tuple(FAMILIES), help="tailless or conventional (default: from the type)")
    sp = p.add_mutually_exclusive_group()
    sp.add_argument("--speed", type=float, help="m/s")
    sp.add_argument("--mach", type=float, help="flight Mach (instead of --speed)")
    p.add_argument("--altitude", type=float, default=0.0, help="m")
    p.add_argument("--alpha", type=float, default=2.0, help="deg at the root section")
    p.add_argument("--airfoils", nargs=4)
    p.add_argument("--method", choices=("auto", "tables", "xfoil"), default="auto",
                   help="2-D answers from the section tables (auto when all sections have one) or direct XFOIL")
    p.add_argument("--ncrit", type=float, default=9.0, choices=(5.0, 9.0, 11.0), help="e^N N_crit (5, 11: checks only)")
    p.add_argument("--induced", action="store_true", help="subtract a uniform induced angle CL/(pi AR) (check only)")
    p.add_argument("--strips", type=int, default=2, help="strips inside each panel (default 2 = 10 per half wing)")
    p.add_argument("--sheet", action="store_true", help="also a Mach x angle sheet from the section tables")
    p.add_argument("--machs", type=float, nargs="+", default=[0.03, 0.05, 0.08, 0.11, 0.14, 0.17, 0.20])
    p.add_argument("--alphas", type=float, nargs="+", default=[0, 2, 4, 6, 8, 10])
    p.add_argument("--out")
    a = p.parse_args(argv)
    if a.speed is None and a.mach is None:
        p.error("give --speed or --mach")
    cfg = load_config()
    vec = json.loads(Path(a.vector).read_text()) if a.vector else load_set(a.type, a.set)["vectors"][a.index]
    tailless = (a.family == "tailless") if a.family else a.type in TAILLESS_TYPES
    spec = cfg.types[a.type]
    fm = flow_map(spec, vec, tailless, a.speed, a.altitude, a.alpha, a.airfoils, method=a.method, mach=a.mach,
                  ncrit=a.ncrit, n_per_panel=a.strips, induced=a.induced)
    out = Path(a.out) if a.out else GEOMETRY_ROOT / "data" / "flowmaps" / f"{a.type}_{a.set or Path(a.vector).stem}_{a.index or 0}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(fm, indent=1, default=float))
    plot(fm, out.with_suffix(".png"))
    b = fm["model"]["sa_drag_bias"]
    print(f"{fm['family']} / {fm['type']} ({fm['method']}): {fm['model']['model']}"
          + (f"\n  SA profile-drag bias {100 * b:+.0f} %" if b is not None else "") + f"\n  -> {out.with_suffix('.png')}")
    if a.sheet:
        sh = sweep_sheet(spec, vec, a.machs, a.alphas, a.altitude, a.airfoils, a.ncrit, a.strips)
        f = out.parent / f"{out.name}_sheet"
        f.with_suffix(".json").write_text(json.dumps(sh, indent=1, default=float))
        plot_sheet(sh, f.with_suffix(".png"))
        print(f"  sheet -> {f.with_suffix('.png')}")


if __name__ == "__main__":
    main()
