"""Is the lofted surface the designed wing? Checked on every training, corner and reference wing.

    python scripts/verify_sets.py        # writes docs/verification_sets.json and .md

For each wing, the loft (the surface the mesher will read) is compared with the design vector:
  stations   leading-edge point (x, y, z) at b0-b3 on the loft vs the designed point
  chord      loft chord at b0-b3 vs the vector
  twist      loft twist at b0-b3 vs the vector
  sweep      leading-edge sweep of each panel on the loft vs the vector
  dihedral   dihedral of each panel on the loft vs the vector (dihedral_p1..p3)
  straight   largest gap between the loft leading edge and the straight line through the two
             stations of its panel (the dihedral and sweep are constant along each panel)
  AR         aspect ratio measured on the loft vs the vector
  sections   loft section at each station vs the original airfoil points (ahead of the
             trailing-edge opening at x/c = 0.90)
  ruled      loft inside each panel vs the straight blend of its two sections
  root       largest |y| of the root section; smallest y of the whole half wing (>= 0 means
             the mirrored halves meet only in the symmetry plane)
Errors in % of local chord unless a unit is given.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.geometry import verify  # noqa: E402
from cfdauto.geometry.build import load_set  # noqa: E402
from cfdauto.geometry.loft import build_loft  # noqa: E402
from cfdauto.geometry.measure import measure, table_from_loft  # noqa: E402
from cfdauto.geometry.params import WING_TYPES, load_config, resolve  # noqa: E402
from cfdauto.geometry.sections import build_wing_sections  # noqa: E402

DOCS = ROOT / "docs"
SETS = ("training", "training_full", "corner1", "corner2", "reference")


def check(spec, vec, te) -> dict:
    vec = resolve(spec, vec)
    pf, st = build_wing_sections(spec, vec, te)
    loft = build_loft(st, k_span=2)
    m = measure(table_from_loft(loft), st)
    main = [s for s in st if s.name in ("b0", "b1", "b2", "b3")]
    v_main = [v for s, v in zip(st, loft.station_v) if s.name in ("b0", "b1", "b2", "b3")]
    le = np.array([loft.leading_edge(v) for v in v_main])
    want = np.array([[s.x_le, s.y, s.z_le] for s in main])
    c = np.array([s.chord for s in main])
    out = {
        "stations_pct": float(np.max(np.linalg.norm(le - want, axis=1) / c) * 100),
        "chord_pct": float(np.max(np.abs(np.array(m["stations"]["chord_m"]) / c - 1)) * 100),
        "twist_deg": float(np.max(np.abs(np.array(m["stations"]["twist_deg"]) - [vec[f"twist{i}_deg"] for i in range(4)]))),
        "sweep_deg": float(np.max(np.abs(np.array(m["panels"]["sweep_le_deg"]) - [vec[f"sweep{i}_deg"] for i in (1, 2, 3)]))),
        "dihedral_deg": float(np.max(np.abs(np.array(m["panels"]["dihedral_deg"]) - [vec[f"dihedral_p{i}_deg"] for i in (1, 2, 3)]))),
        "ar_pct": float(abs(m["aspect_ratio"] / vec["aspect_ratio"] - 1) * 100),
    }
    # leading edge straight inside each panel (constant sweep and dihedral)
    worst = 0.0
    for k in range(3):
        for t in np.linspace(0, 1, 9)[1:-1]:
            v = v_main[k] + t * (v_main[k + 1] - v_main[k])
            p = loft.leading_edge(v)
            s = (p[1] - want[k, 1]) / (want[k + 1, 1] - want[k, 1])
            line = want[k] + s * (want[k + 1] - want[k])
            worst = max(worst, np.linalg.norm(p - line) / ((1 - s) * c[k] + s * c[k + 1]) * 100)
    out["straight_pct"] = float(worst)
    out["sections_pct"] = max(r["max_pct_chord"] for r in verify.section_fidelity(loft, st, exclude_aft_of=te.open_from_xc))
    out["ruled_pct"] = float(verify.ruled_panels(loft, st))
    u = np.linspace(0, 1, 201)
    root = np.concatenate([loft.upper(u, np.zeros_like(u)), loft.lower(u, np.zeros_like(u))])
    out["root_y_m"] = float(np.max(np.abs(root[:, 1])))
    vv, uu = np.meshgrid(np.linspace(0, 1, 101), u)
    out["min_y_m"] = float(min(np.min(loft.upper(uu, vv)[..., 1]), np.min(loft.lower(uu, vv)[..., 1])))
    return out


def main() -> None:
    cfg = load_config()
    rows = []
    for t in WING_TYPES:
        for s in SETS:
            for i, vec in enumerate(load_set(t, s)["vectors"]):
                rows.append({"type": t, "set": s, "index": i} | check(cfg.types[t], vec, cfg.te))
    keys = ("stations_pct", "chord_pct", "twist_deg", "sweep_deg", "dihedral_deg", "straight_pct", "ar_pct",
            "sections_pct", "ruled_pct", "root_y_m", "min_y_m")
    summary = {t: {k: (min if k == "min_y_m" else max)(r[k] for r in rows if r["type"] == t) for k in keys} | {
        "wings": sum(1 for r in rows if r["type"] == t)} for t in WING_TYPES}
    (DOCS / "verification_sets.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    lines = ["# Sampled wings: loft vs design", "",
             "Worst value over every training, corner and reference wing of each type (numpy loft).", "",
             "| type | wings | stations % c | chord % | twist ° | sweep ° | dihedral ° | straight panels % c | AR % | sections % c | ruled % c | root y m | min y m |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t, sm in summary.items():
        lines.append(f"| {t} | {sm['wings']} | " + " | ".join(f"{sm[k]:.2g}" for k in keys) + " |")
    (DOCS / "verification_sets.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
