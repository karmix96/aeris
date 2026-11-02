"""The family rule on the surface (law 23): build C, M and F of each reference wing 0 at Re 3e5 and
measure the ratio of every spacing between levels. Writes data/studies/family_ratios.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.mesh.laws import rules  # noqa: E402
from cfdauto.mesh.surface import build_surface, wing_from_set  # noqa: E402
from cfdauto.paths import STAGE2  # noqa: E402

LEVELS = ("C", "M", "F")


def spacings(m) -> dict[str, float]:
    y = np.array([r["y_m"] for r in m.stations])
    root, tip = m.stations[0], m.stations[-1]
    return {"nose_root": root["h_le_c"], "nose_tip": tip["h_le_c"], "te_root": root["h_te_c_delivered"],
            "band_root": root["band_max_c"], "band_tip": tip["band_max_c"],
            "root_gap": float(np.diff(y)[0]), "tip_gap": float(np.diff(y)[-1]),
            "base_cell": float(np.linalg.norm(m.wing[-1, 0] - m.wing[0, 0]))}


def main() -> None:
    r = rules("C").ratio
    out = {"ratio": r, "re_mean": 3.0e5, "wings": {}}
    for t in ("bwb", "flying_wing", "cranked", "tapered"):
        w = wing_from_set(t, "reference", 0)
        meshes = {lev: build_surface(w.loft, 3.0e5, lev) for lev in LEVELS}
        row = {"passed": {lev: m.passed for lev, m in meshes.items()},
               "failed": {lev: [c.name for c in m.failed()] for lev, m in meshes.items()},
               "counts": {lev: {"n_ring": m.info["n_ring"], "n_span": m.info["n_span"],
                                "quads": m.info["wing_quads"] + m.info["cap_quads"]} for lev, m in meshes.items()},
               "spacings": {lev: spacings(m) for lev, m in meshes.items()}, "ratios": {}}
        for a, b in zip(LEVELS[:-1], LEVELS[1:]):
            row["ratios"][f"{a}/{b}"] = {k: row["spacings"][a][k] / row["spacings"][b][k] for k in row["spacings"][a]}
        out["wings"][t] = row
        print(t, {lev: (m.info["n_ring"], m.info["n_span"], m.passed) for lev, m in meshes.items()})
        for k, v in row["ratios"].items():
            print("  ", k, {kk: round(vv, 3) for kk, vv in v.items()})
    path = STAGE2 / "data" / "studies" / "family_ratios.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
