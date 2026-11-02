"""kSpan = 2 against kSpan = 3 (and extra sections), on the three G3 test wings.

Also measures how far pyGeo's own liftingSurface puts its upper/lower split
from the true nose. Writes data/studies/loft_kspan.json.

    python scripts/loft_kspan_study.py
"""

import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "geometry"))

from cfdauto.geometry import params  # noqa: E402
from cfdauto.geometry.loft import build_loft, edge_error_pct, section_points  # noqa: E402
from cfdauto.geometry.sections import build_wing_sections, insert_sections  # noqa: E402
from test_loft import three_wings  # noqa: E402


def lifting_surface_nose_error(stations, tmp: Path) -> float:
    """Largest distance [% chord] from liftingSurface's split point to the true nose."""
    from pygeo import pyGeo
    paths, te = [], []
    for i, st in enumerate(stations):
        p = tmp / f"sec{i}.dat"
        np.savetxt(p, st.airfoil.selig(), fmt="%.15e", header=st.name, comments="")
        r = np.loadtxt(p, skiprows=1)
        paths.append(str(p))
        te.append(float(r[0, 1] - r[-1, 1]))
    with contextlib.redirect_stdout(io.StringIO()):
        g = pyGeo("liftingSurface", xsections=paths,
                  x=[s.x_le for s in stations], y=[s.y for s in stations], z=[s.z_le for s in stations],
                  scale=[s.chord for s in stations], offset=np.zeros((len(stations), 2)),
                  rotX=[90.0] * len(stations), rotY=[s.twist_deg for s in stations],
                  rotZ=[0.0] * len(stations), kSpan=2, bluntTe=True, teHeightScaled=te, tip="none")
    from pyspline import Curve
    v = Curve(X=np.array([[s.x_le, s.y, s.z_le] for s in stations]), k=2).s
    worst = 0.0
    for st, vi in zip(stations, v):
        nose = section_points(st)[0][0]
        worst = max(worst, np.linalg.norm(np.asarray(g.surfs[0](1.0, vi)) - nose) / st.chord * 100)
    return float(worst)


def main() -> None:
    cfg = params.load_config()
    out_dir = ROOT / "data" / "studies"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_tmp_sections"
    tmp.mkdir(exist_ok=True)
    result = {}
    for name, (spec, vec) in three_wings().items():
        _, st = build_wing_sections(spec, vec, cfg.te)
        row = {}
        for label, k, extra in [("k2", 2, 0), ("k3", 3, 0), ("k3_plus1", 3, 1), ("k3_plus3", 3, 3), ("k2_plus3", 2, 3)]:
            secs = insert_sections(st, extra, cfg.te) if extra else st
            row[label] = edge_error_pct(build_loft(secs, k_span=k), st)
        row["liftingSurface_nose_split_error_pct"] = lifting_surface_nose_error(st, tmp)
        result[name] = row
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    (out_dir / "loft_kspan.json").write_text(json.dumps(result, indent=2))
    for name, row in result.items():
        print(name)
        for k, v in row.items():
            print(f"  {k:38s} {v if isinstance(v, float) else {kk: round(vv, 5) for kk, vv in v.items()}}")


if __name__ == "__main__":
    main()
