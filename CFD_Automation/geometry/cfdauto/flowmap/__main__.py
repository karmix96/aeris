"""Flow map of one wing.

    python -m cfdauto.flowmap --type bwb --set reference --index 0 --speed 25 --altitude 1000 --alpha 3
    python -m cfdauto.flowmap --type cranked --vector my_wing.json --family conventional --speed 30
    (add --airfoils mh61 mh61 mh45 mh45 to try other sections)

Writes <out>.png and <out>.json (default data/flowmaps/<type>_<set>_<index>).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..geometry.build import load_set
from ..geometry.params import FAMILIES, GEOMETRY_ROOT, TAILLESS_TYPES, WING_TYPES, load_config
from .core import flow_map, plot


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--type", choices=WING_TYPES, required=True, help="generator type whose laws read the vector")
    p.add_argument("--set"); p.add_argument("--index", type=int); p.add_argument("--vector")
    p.add_argument("--family", choices=tuple(FAMILIES), help="tailless or conventional (default: from the type)")
    p.add_argument("--speed", type=float, required=True, help="m/s")
    p.add_argument("--altitude", type=float, default=0.0, help="m")
    p.add_argument("--alpha", type=float, default=2.0, help="deg at the root section")
    p.add_argument("--airfoils", nargs=4)
    p.add_argument("--out")
    a = p.parse_args(argv)
    cfg = load_config()
    vec = json.loads(Path(a.vector).read_text()) if a.vector else load_set(a.type, a.set)["vectors"][a.index]
    tailless = (a.family == "tailless") if a.family else a.type in TAILLESS_TYPES
    fm = flow_map(cfg.types[a.type], vec, tailless, a.speed, a.altitude, a.alpha, a.airfoils)
    out = Path(a.out) if a.out else GEOMETRY_ROOT / "data" / "flowmaps" / f"{a.type}_{a.set or Path(a.vector).stem}_{a.index or 0}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(fm, indent=1, default=float))
    plot(fm, out.with_suffix(".png"))
    print(f"{fm['family']} / {fm['type']}: {fm['model']['model']}\n  -> {out.with_suffix('.png')}")


if __name__ == "__main__":
    main()
