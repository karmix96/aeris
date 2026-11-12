"""Where an SU2 solve's residual lives (SU2 study of 12 Nov 2026): from a volume CSV written with
VOLUME_OUTPUT= ( COORDINATES, SOLUTION, PRIMITIVE, RESIDUAL, LIMITER ) and the run's wall file.

    python residual_map.py <flow.dat (Tecplot ASCII volume) or flow.csv> <surface_flow.dat> <case.json> [<out.json>]

For each residual field: the share of its sum of squares held by the largest 0.1 %, 1 % and 10 % of the points
(a field-wide plateau spreads it; one bad region concentrates it), and where the largest 1 % sit: by region
(wall-near trailing edge, tip, wake, around the wing, far field) and by span. For each limiter field: the share of
points where it acts (value below 0.99), and the share of the largest-residual points where it acts.
Regions use the wall's own trailing edge at each span station (the largest x of the wall nodes there).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wall_map import read_tecplot                              # noqa: E402


def main() -> int:
    vol, surf, case_json = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    case = json.loads(case_json.read_text())
    semi = case["references"]["semi_span"]
    if vol.suffix == ".dat":                                    # SU2's Tecplot ASCII volume, point data first
        import re
        with open(vol) as f:
            f.readline()
            cols = re.findall(r'"([^"]+)"', f.readline())
            nn = int(re.search(r"NODES=\s*(\d+)", f.readline()).group(1))
        df = pd.read_csv(vol, sep=r"\s+", header=None, names=cols, nrows=nn, skiprows=3, engine="c")
    else:
        df = pd.read_csv(vol)
        df.columns = [c.strip().strip('"') for c in df.columns]
    names, W, _ = read_tecplot(surf)
    c = {n: i for i, n in enumerate(names)}
    wx, wy, wz = W[:, c["x"]], W[:, c["y"]], W[:, c["z"]]
    ys = np.unique(np.round(wy, 6))
    te_x = np.array([wx[np.abs(wy - v) < 1e-6].max() for v in ys])
    le_x = np.array([wx[np.abs(wy - v) < 1e-6].min() for v in ys])
    te_z = np.array([wz[np.abs(wy - v) < 1e-6][np.argmax(wx[np.abs(wy - v) < 1e-6])] for v in ys])
    x, y, z = df["x"].to_numpy(), df["y"].to_numpy(), df["z"].to_numpy()
    yc = np.clip(y, 0.0, semi)
    xte, xle, zte = np.interp(yc, ys, te_x), np.interp(yc, ys, le_x), np.interp(yc, ys, te_z)
    chord = np.maximum(xte - xle, 1e-6)
    near_te = (np.abs(x - xte) < 0.05 * chord) & (np.abs(z - zte) < 0.05 * chord) & (y <= semi)
    tip = (y > semi) & (y < semi + 0.3) & (x > xle - 0.2) & (x < xte + 0.3) & (np.abs(z) < 0.5)
    wake = (x >= xte) & (y <= semi) & ~near_te
    r_from = np.sqrt((x - 1.0) ** 2 + y ** 2 + z ** 2)
    far = r_from > 10.0
    around = ~(near_te | tip | wake | far)
    region = np.select([near_te, tip, wake, far, around],
                       ["trailing-edge corner (5 % of the local chord)", "tip (outside y = s)", "wake (behind the TE)",
                        "far field (more than 10 chords)", "around the wing"], default="other")
    rep = {"points": int(len(df)), "residual_fields": {}, "limiter_fields": {},
           "region_points": {k: int((region == k).sum()) for k in np.unique(region)}}
    res_cols = [k for k in df.columns if k.startswith("Residual_")]
    lim_cols = [k for k in df.columns if k.startswith("Limiter_")]
    for k in res_cols:
        r = np.abs(df[k].to_numpy(float))
        o = np.argsort(r)[::-1]
        ss = float(np.sum(r ** 2)) or 1e-300
        share = {f"top_{p}%": float(np.sum(r[o[: max(1, int(len(r) * p / 100))]] ** 2) / ss) for p in (0.1, 1, 10)}
        top = o[: max(1, len(r) // 100)]
        reg = pd.Series(region[top]).value_counts(normalize=True).round(4).to_dict()
        span = np.histogram(np.clip(y[top] / semi, 0, 1.2), bins=[0, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0, 1.2])[0]
        rep["residual_fields"][k] = {"rms_log10": float(np.log10(np.sqrt(np.mean(r ** 2)) + 1e-300)),
                                     "share_of_sum_of_squares": share, "largest_1%_by_region": reg,
                                     "largest_1%_by_span_y/s_bins_0_.2_.4_.6_.8_.95_1_1.2": span.tolist(),
                                     "largest_10_points": [{"x": float(x[i]), "y": float(y[i]), "z": float(z[i]),
                                                            "region": str(region[i]), "value": float(r[i])} for i in o[:10]]}
    if res_cols:
        rr = np.abs(df[res_cols[0]].to_numpy(float))
        top = np.argsort(rr)[::-1][: max(1, len(rr) // 100)]
        for k in lim_cols:
            lim = df[k].to_numpy(float)
            rep["limiter_fields"][k] = {"acting_share_all_points": float(np.mean(lim < 0.99)),
                                        f"acting_share_at_largest_1%_of_{res_cols[0]}": float(np.mean(lim[top] < 0.99)),
                                        "acting_share_by_region": {g: float(np.mean(lim[region == g] < 0.99))
                                                                   for g in np.unique(region)}}
    if len(sys.argv) > 4:
        Path(sys.argv[4]).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
