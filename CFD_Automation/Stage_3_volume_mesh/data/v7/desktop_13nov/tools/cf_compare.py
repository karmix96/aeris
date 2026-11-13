"""DESKTOP_13NOV section 3: the wall friction along the chord, ADflow against SU2 on the same mesh. Is ADflow's
friction higher everywhere by about 12 %, or only in a region?

    python cf_compare.py <ADflow surf.cgns> <SU2 surface_flow.dat> <case.json> <out.png> <out.json> [--stations 0.26,0.48,0.82]

ADflow: SkinFrictionMagnitude at the wall faces' centres (NSWall zones, rind stripped). SU2: the magnitude of the
three Skin_Friction_Coefficient components at the wall nodes. A station takes SU2's nodes on the nearest span station
and ADflow's faces in the strip whose centres lie nearest it (half a station spacing apart: noted). Side: above or
below the chord line from the leading edge to the trailing edge. The ratio is reported per chord band, from the two
curves interpolated on a common x/c, integrated over the band (so a band's ratio is its friction-drag ratio there).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[5]))                            # CFD_Automation
sys.path.insert(0, str(HERE.parents[1] / "../su2_transition/tools"))
from cfdauto.volume.cgns import rdata, read_adf                     # noqa: E402
from wall_map import read_tecplot                                   # noqa: E402

SERIES = {"ADflow SA (A1b)": "#2a78d6", "SU2 SA (R1f)": "#eb6834"}
BANDS = [(0.0, 0.05), (0.05, 0.3), (0.3, 0.7), (0.7, 1.0)]


def adflow_faces(path: Path):
    root, raw = read_adf(path)
    out = []
    for base in (n for n in root.children if n.label == "CGNSBase_t"):
        for z in (n for n in base.children if n.label == "Zone_t" and n.name.startswith("NSWall")):
            fs = next(n for n in z.children if n.label == "FlowSolution_t")
            rind = next((rdata(n, raw) for n in fs.children if n.label == "Rind_t"), np.zeros(4, int))
            r = [int(v) for v in np.ravel(rind)]
            cf = rdata(next(n for n in fs.children if n.name == "SkinFrictionMagnitude"), raw)
            cf = cf[r[0]: cf.shape[0] - r[1], r[2]: cf.shape[1] - r[3]]
            gc = next(n for n in z.children if n.label == "GridCoordinates_t")
            X = [rdata(next(n for n in gc.children if n.name == f"Coordinate{c}"), raw) for c in "XYZ"]
            c = [0.25 * (a[:-1, :-1] + a[1:, :-1] + a[:-1, 1:] + a[1:, 1:]) for a in X]
            out.append(np.stack([c[0].ravel(), c[1].ravel(), c[2].ravel(), cf.ravel()], 1))
    return np.concatenate(out)


def split(x, z, f):
    ile, ite = int(np.argmin(x)), int(np.argmax(x))
    xc = (x - x[ile]) / (x[ite] - x[ile])
    up = z >= z[ile] + (z[ite] - z[ile]) * xc
    res = {}
    for name, s in (("upper", up), ("lower", ~up)):
        o = np.argsort(xc[s])
        res[name] = (xc[s][o], f[s][o])
    return res


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("adflow", type=Path); p.add_argument("su2", type=Path); p.add_argument("case", type=Path)
    p.add_argument("png", type=Path); p.add_argument("json", type=Path)
    p.add_argument("--stations", default="0.26,0.48,0.82")
    a = p.parse_args()
    semi = json.loads(a.case.read_text())["references"]["semi_span"]
    A = adflow_faces(a.adflow)
    names, W, _ = read_tecplot(a.su2)
    c = {n: i for i, n in enumerate(names)}
    sx, sy, sz = W[:, c["x"]], W[:, c["y"]], W[:, c["z"]]
    scf = np.sqrt(sum(W[:, c[f"Skin_Friction_Coefficient_{k}"]] ** 2 for k in "xyz"))
    ys_su2 = np.unique(np.round(sy, 6))
    ys_adf = np.unique(np.round(A[:, 1], 6))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fr = [float(f) for f in a.stations.split(",")]
    fig, ax = plt.subplots(1, len(fr), figsize=(4.2 * len(fr), 3.8), sharey=True, squeeze=False)
    rep = {"note": __doc__.split("\n\n")[2].replace("\n", " "), "stations": []}
    for j, f in enumerate(fr):
        y2 = ys_su2[np.argmin(np.abs(ys_su2 / semi - f))]
        ya = ys_adf[np.argmin(np.abs(ys_adf - y2))]
        m2, ma = np.abs(sy - y2) < 1e-6, np.abs(A[:, 1] - ya) < 1e-6
        s2 = split(sx[m2], sz[m2], scf[m2])
        sa = split(A[ma, 0], A[ma, 2], A[ma, 3])
        st = {"y_over_s_su2": float(y2 / semi), "y_over_s_adflow_strip": float(ya / semi), "bands": {}}
        for side, ls in (("upper", "-"), ("lower", "--")):
            ax[0, j].plot(*sa[side], ls, color=SERIES["ADflow SA (A1b)"], lw=1.5, label="ADflow SA (A1b)" if (j == 0 and side == "upper") else None)
            ax[0, j].plot(*s2[side], ls, color=SERIES["SU2 SA (R1f)"], lw=1.5, label="SU2 SA (R1f)" if (j == 0 and side == "upper") else None)
            g = np.linspace(0.005, 0.995, 400)
            fa, fs = np.interp(g, *sa[side]), np.interp(g, *s2[side])
            for b0, b1 in BANDS:
                k = (g >= b0) & (g < b1)
                st["bands"][f"{side} {b0:.2f}-{b1:.2f}"] = float(np.trapezoid(fa[k], g[k]) / np.trapezoid(fs[k], g[k]))
            st["bands"][f"{side} whole chord"] = float(np.trapezoid(fa, g) / np.trapezoid(fs, g))
        rep["stations"].append(st)
        ax[0, j].set_title(f"y/s = {y2 / semi:.2f}")
        ax[0, j].set_xlabel("x / c"); ax[0, j].grid(True, color="#e4e3df", lw=0.6)
        for s in ("top", "right"):
            ax[0, j].spines[s].set_visible(False)
    ax[0, 0].set_ylabel("skin friction magnitude, |Cf|"); ax[0, 0].set_ylim(0, 0.014)
    from matplotlib.lines import Line2D
    h, l = ax[0, 0].get_legend_handles_labels()
    h += [Line2D([], [], color="#52514e", ls="-"), Line2D([], [], color="#52514e", ls="--")]; l += ["upper side", "lower side"]
    fig.legend(h, l, loc="upper center", ncol=4, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.9)); fig.savefig(a.png, dpi=130)
    a.json.write_text(json.dumps(rep, indent=1))
    for st in rep["stations"]:
        print(f"y/s {st['y_over_s_su2']:.3f} (ADflow strip {st['y_over_s_adflow_strip']:.3f}):",
              ", ".join(f"{k} {v:.3f}" for k, v in st["bands"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
