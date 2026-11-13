"""Block M (and G): one ADflow run against its baseline: the forces, the lift over the outer 10 % of the semi-span, and
Cp at the tip slices (DESKTOP_13NOV section 2: "the lift over the outer 10 % of the semi-span; Cp at 0.9, 0.95, 0.98").

    python m_compare.py <base folder> <run folder> <base label> <run label> <out.png> <out.json>

Each folder holds result.json, lift_distribution.dat and slices.dat (run_adflow.py --lift-distribution 150
--slices 0.5,0.8,0.9,0.95,0.98). The lift distribution is ADflow's, 150 segments along y: "Lift" per segment; the
outer 10 % is eta >= 0.9, its sum compared directly; the largest difference in the normalised sectional lift there is
taken on the base's eta (the run interpolated). Cp per slice: the largest |delta Cp| over the upper and the lower side
at a common x/c (both interpolated), and where it sits.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "../night_11nov/tools"))
from plot_lift_cp import lift, slices                               # noqa: E402

COL = {"base": "#2a78d6", "run": "#eb6834"}


def sides(s):
    x, z, cp = s["CoordinateX"], s["CoordinateZ"], s["CoefPressure"]
    ile, ite = int(np.argmin(x)), int(np.argmax(x))
    xc = (x - x[ile]) / (x[ite] - x[ile])
    up = z >= z[ile] + (z[ite] - z[ile]) * xc
    out = {}
    for nm, m in (("upper", up), ("lower", ~up)):
        o = np.argsort(xc[m])
        out[nm] = (xc[m][o], cp[m][o])
    return out


def main() -> int:
    bf, rf, bl, rl, png, js = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], Path(sys.argv[5]), Path(sys.argv[6])
    rb, rr = (json.loads((f / "result.json").read_text()) for f in (bf, rf))
    cb, cr = rb["coefficients"], rr["coefficients"]
    rep = {"base": bl, "run": rl, "forces": {
        "dCL_pct": 100 * (cr["cl"] / cb["cl"] - 1), "dCD_counts": (cr["cd"] - cb["cd"]) * 1e4,
        "dCDp_counts": (cr["cdp"] - cb["cdp"]) * 1e4, "dCDv_counts": (cr["cdv"] - cb["cdv"]) * 1e4,
        "dCMy": cr["cmy"] - cb["cmy"], "base": cb, "run": cr,
        "converged": {"base": rb.get("converged"), "run": rr.get("converged"), "run_iterations": rr.get("iterations")}}}
    Lb, Lr = lift(bf / "lift_distribution.dat"), lift(rf / "lift_distribution.dat")
    ob, orr = Lb["eta"] >= 0.9, Lr["eta"] >= 0.9
    rep["outer_10pct"] = {"lift_base": float(Lb["Lift"][ob].sum()), "lift_run": float(Lr["Lift"][orr].sum())}
    rep["outer_10pct"]["dlift_pct"] = 100 * (rep["outer_10pct"]["lift_run"] / rep["outer_10pct"]["lift_base"] - 1)
    nl_r = np.interp(Lb["eta"], Lr["eta"], Lr["Normalized Lift"])
    d = np.abs(nl_r - Lb["Normalized Lift"])[ob]
    k = int(np.argmax(d))
    rep["outer_10pct"]["max_dnormlift"] = float(d[k]); rep["outer_10pct"]["at_eta"] = float(Lb["eta"][ob][k])
    rep["outer_10pct"]["normlift_base_there"] = float(Lb["Normalized Lift"][ob][k])
    Sb, Sr = slices(bf / "slices.dat"), slices(rf / "slices.dat")
    semi = float(max(Lb["CoordinateY"].max(), 1e-9)) if "CoordinateY" in Lb else None
    rep["slices"] = []
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tips = [i for i, s in enumerate(Sb) if semi is None or s["y"] / semi >= 0.85]
    fig, ax = plt.subplots(1, 1 + len(tips), figsize=(3.6 * (1 + len(tips)), 3.6), squeeze=False)
    ax[0, 0].plot(Lb["eta"], Lb["Normalized Lift"], color=COL["base"], lw=1.5, label=bl)
    ax[0, 0].plot(Lr["eta"], Lr["Normalized Lift"], color=COL["run"], lw=1.5, label=rl)
    ax[0, 0].axvline(0.9, color="#9a998f", lw=0.8, ls=":"); ax[0, 0].set_xlabel("eta = y / semi-span"); ax[0, 0].set_title("normalised sectional lift")
    for j, (sb, sr) in enumerate(zip(Sb, Sr)):
        A, B = sides(sb), sides(sr)
        g = np.linspace(0.01, 0.99, 300)
        dmax = {}
        for nm in ("upper", "lower"):
            dd = np.abs(np.interp(g, *B[nm]) - np.interp(g, *A[nm]))
            dmax[nm] = {"max_dcp": float(dd.max()), "at_xc": float(g[int(np.argmax(dd))])}
        rep["slices"].append({"y": sb["y"], "y_run": sr["y"], **dmax})
        if j in tips:
            a = ax[0, 1 + tips.index(j)]
            for nm, ls in (("upper", "-"), ("lower", "--")):
                a.plot(A[nm][0], -A[nm][1], ls, color=COL["base"], lw=1.4)
                a.plot(B[nm][0], -B[nm][1], ls, color=COL["run"], lw=1.4)
            a.set_title(f"y = {sb['y']:.3f}" + (f" (y/s {sb['y'] / semi:.2f})" if semi else "")); a.set_xlabel("x / c"); a.set_ylabel("−Cp")
    for a in ax[0]:
        a.grid(True, color="#e4e3df", lw=0.6)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    fig.legend(*ax[0, 0].get_legend_handles_labels(), loc="upper center", ncol=2, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.9)); fig.savefig(png, dpi=130)
    js.write_text(json.dumps(rep, indent=1, default=float))
    F, O = rep["forces"], rep["outer_10pct"]
    print(f"{rl} - {bl}: dCL {F['dCL_pct']:+.2f} %, dCD {F['dCD_counts']:+.2f} counts (p {F['dCDp_counts']:+.2f}, f {F['dCDv_counts']:+.2f}), dCMy {F['dCMy']:+.5f}; "
          f"outer 10 % lift {O['dlift_pct']:+.2f} %, max d(norm lift) {O['max_dnormlift']:.4f} at eta {O['at_eta']:.3f} (base {O['normlift_base_there']:.3f})")
    for s in rep["slices"]:
        print(f"  slice y {s['y']:.3f} (run {s['y_run']:.3f}): max |dCp| upper {s['upper']['max_dcp']:.3f} at x/c {s['upper']['at_xc']:.2f}, lower {s['lower']['max_dcp']:.3f} at {s['lower']['at_xc']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
