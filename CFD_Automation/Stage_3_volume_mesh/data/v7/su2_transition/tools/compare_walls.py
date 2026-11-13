"""Cp and the streamwise wall friction along the chord at a few span stations, one line per run, from SU2's Tecplot
wall files (SU2 study of 12 Nov 2026): where each transition model puts its laminar run, separation and
reattachment, against fully turbulent SA.

    python compare_walls.py <out.png> <case.json> "SA (R1f)=<surface_flow.dat>" "SA + LM (R2)=<surface_flow.dat>" ...
        [--stations 0.26,0.48,0.82,0.95]

Rows: -Cp, then Skin_Friction_Coefficient_x (negative = reversed flow). Columns: span stations. Colour = run, in the
fixed categorical order of the reference palette (slot 1 blue, 2 orange, 3 aqua, 4 yellow); line style = side
(upper solid, lower dashed). One y-scale per row, shared across stations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wall_map import read_tecplot                              # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]   # categorical slots 1-6, light mode
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def station(W, c, frac, semi):
    x, y, z = W[:, c["x"]], W[:, c["y"]], W[:, c["z"]]
    ys = np.unique(np.round(y, 6))
    yy = ys[np.argmin(np.abs(ys / semi - frac))]
    m = np.abs(y - yy) < 1e-6
    xs, zs = x[m], z[m]
    ile, ite = int(np.argmin(xs)), int(np.argmax(xs))
    xc = (xs - xs[ile]) / (xs[ite] - xs[ile])
    up = zs >= zs[ile] + (zs[ite] - zs[ile]) * xc
    cp, cf = W[m, c["Pressure_Coefficient"]], W[m, c["Skin_Friction_Coefficient_x"]]
    out = {}
    for side, s in (("upper", up), ("lower", ~up)):
        o = np.argsort(xc[s])
        out[side] = (xc[s][o], cp[s][o], cf[s][o])
    return yy / semi, out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("out", type=Path)
    p.add_argument("case", type=Path)
    p.add_argument("runs", nargs="+", help='"label=path to surface_flow.dat"')
    p.add_argument("--stations", default="0.26,0.48,0.82,0.95")
    a = p.parse_args(argv)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    semi = json.loads(a.case.read_text())["references"]["semi_span"]
    fr = [float(f) for f in a.stations.split(",")]
    runs = []
    for item in a.runs:
        label, _, path = item.partition("=")
        names, W, _ = read_tecplot(Path(path))
        runs.append((label, W, {n: i for i, n in enumerate(names)}))
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                         "ytick.color": INK2, "text.color": INK, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE})
    fig, ax = plt.subplots(2, len(fr), figsize=(3.2 * len(fr), 6.2), sharex=True, sharey="row", squeeze=False)
    for j, f in enumerate(fr):
        for k, (label, W, c) in enumerate(runs):
            ys, st = station(W, c, f, semi)
            for side, ls in (("upper", "-"), ("lower", "--")):
                xc, cp, cf = st[side]
                ax[0, j].plot(xc, -cp, ls, color=SERIES[k], lw=1.5, label=label if (j == 0 and side == "upper") else None)
                ax[1, j].plot(xc, cf, ls, color=SERIES[k], lw=1.5)
        ax[0, j].set_title(f"y/s = {ys:.2f}", color=INK)
        ax[1, j].axhline(0.0, color=INK2, lw=0.8)
        ax[1, j].set_xlabel("x / c")
        for r in (0, 1):
            ax[r, j].grid(True, color=GRID, lw=0.6)
            ax[r, j].set_axisbelow(True)
            for s in ("top", "right"):
                ax[r, j].spines[s].set_visible(False)
    ax[0, 0].set_ylabel("−Cp")
    ax[1, 0].set_ylabel("streamwise skin friction, Cf_x")
    ax[1, 0].set_ylim(-0.004, 0.012)
    h, l = ax[0, 0].get_legend_handles_labels()
    from matplotlib.lines import Line2D
    h += [Line2D([], [], color=INK2, lw=1.5, ls="-"), Line2D([], [], color=INK2, lw=1.5, ls="--")]
    l += ["upper side", "lower side"]
    fig.legend(h, l, loc="upper center", ncol=len(h), frameon=False, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(a.out, dpi=130)
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
