"""The spanwise lift and the Cp slices of one ADflow solution (lift_distribution.dat, slices.dat: Tecplot ASCII as
ADflow writes them), with SU2's Cp on the same slices if a surface_flow.csv is given (wall nodes within half a
station spacing of each slice plane).

    python plot_lift_cp.py <adflow folder with lift_distribution.dat, slices.dat> <out.png> [<su2 surface_flow.dat|.csv> [label]]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np


def lift(path: Path) -> dict:
    txt = path.read_text().split("\n")
    names = re.findall(r'"([^"]+)"', next(l for l in txt if l.startswith("Variables")))
    n = int(re.search(r"I=\s*(\d+)", "\n".join(txt)).group(1))
    vals = [float(v) for l in txt if re.match(r"^\s*[-+0-9.]", l) and "=" not in l for v in l.split()]
    return {k: np.array(vals[i * n:(i + 1) * n]) for i, k in enumerate(names)}


def slices(path: Path) -> list[dict]:
    txt = path.read_text().split("\n")
    names = re.findall(r'"([^"]+)"', next(l for l in txt if l.startswith("Variables")))
    out, i = [], 0
    while i < len(txt):
        m = re.match(r'Zone T= ".* y = ([-0-9.Ee+]+)"', txt[i].strip())
        if m:
            nn = int(re.search(r"Nodes\s*=\s*(\d+)", txt[i + 1]).group(1))
            rows = [list(map(float, txt[i + 3 + j].split())) for j in range(nn)]
            out.append({"y": float(m.group(1)), **{k: np.array([r[c] for r in rows]) for c, k in enumerate(names)}})
            i += 3 + nn
        else:
            i += 1
    return out


def main() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    su2 = None
    if len(sys.argv) > 3:
        import pandas as pd
        if sys.argv[3].endswith(".dat"):                            # SU2's Tecplot surface file: it has Cp and y+
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from su2_surface_forces import read_tecplot
            names, D, _ = read_tecplot(Path(sys.argv[3]))
            su2 = pd.DataFrame(D, columns=names)
        else:
            su2 = pd.read_csv(sys.argv[3])
            su2.columns = [c.strip().strip('"') for c in su2.columns]
    label = sys.argv[4] if len(sys.argv) > 4 else "SU2 SA"
    L, S = lift(folder / "lift_distribution.dat"), slices(folder / "slices.dat")
    fig, ax = plt.subplots(1, 1 + len(S), figsize=(4.2 * (1 + len(S)), 3.8))
    ax[0].plot(L["eta"], L["Normalized Lift"], label="ADflow SA")
    ax[0].plot(L["eta"], L["Elliptical"], "--", lw=1, label="elliptical")
    ax[0].set_xlabel("η = y / semi-span")
    ax[0].set_ylabel("normalised sectional lift")
    ax[0].set_title("spanwise lift")
    ax[0].legend(fontsize=8)
    semi = float(L["CoordinateY"].max()) if "CoordinateY" in L else 3.0
    for a, s in zip(ax[1:], S):
        a.plot(s["XoC"], -s["CoefPressure"], ".", ms=2, label="ADflow SA")
        if su2 is not None:
            yy = su2["y"].to_numpy(float)
            near = np.abs(yy - s["y"]) <= 0.02 * semi
            if near.any():
                x = su2["x"].to_numpy(float)[near]
                xle, xte = x.min(), x.max()
                a.plot((x - xle) / (xte - xle), -su2["Pressure_Coefficient"].to_numpy(float)[near], ".", ms=2, alpha=0.6,
                       label=f"{label} (nodes within 2 % of s)")
        a.set_title(f"y = {s['y']:.2f} (y/s {s['y'] / semi:.2f})")
        a.set_xlabel("x / c")
        a.set_ylabel("−Cp")
        a.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
