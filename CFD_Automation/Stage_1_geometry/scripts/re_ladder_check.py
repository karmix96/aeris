"""Check C4 on 2-D data (8 Nov 2026): how well do the Re levels let the data be read between them?

    python scripts/re_ladder_check.py     # seconds: writes docs/re_ladder_check.json and docs/re_ladder_check.png

For every section table (free transition at N_crit 9 and tripped; Mach 0.1) and the angles 0, 2, 4 and 6 deg: read the
drag at the grid Re that are not levels by straight-line interpolation in log Re and log cd between the two nearest
levels (above the top level: extrapolation from the two highest), and compare it with the table's own value there.
Lift likewise (linear in log Re; only where |cl| > 0.2). The ladders: the levels until 8 Nov (1e5, 3e5, 1.5e6, 3e6),
the levels since 8 Nov (Stage 0 values.yaml) and two others the owner weighed. A 2-D proxy for check C4: the solver's
3-D answer may differ, and wing drag also carries induced drag, which does not depend on Re.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from cfdauto.paths import re_levels  # noqa: E402

DOCS = ROOT / "docs"
TABLES = ROOT / "data" / "section_tables"
ALPHAS = (0.0, 2.0, 4.0, 6.0)
TESTS = (1.5e5, 2.5e5, 4e5, 6e5, 1e6, 1.5e6, 2.5e6, 4e6, 6e6)
LADDERS = {"until 8 Nov": (1e5, 3e5, 1.5e6, 3e6), "since 8 Nov": re_levels(),
           "1e5, 3e5, 1e6, 3e6, 6e6 (5 levels)": (1e5, 3e5, 1e6, 3e6, 6e6),
           "1e5, 3e5, 1.5e6, 6e6": (1e5, 3e5, 1.5e6, 6e6)}
INK, MUTED, GREY, NEW = "#142230", "#566573", "#9AA6B2", "#0C5EA8"
L = np.log


def table_at(d, fld: str, re_: float, im: int) -> np.ndarray:
    """The table's values at one Re (log-linear between grid rows when re_ is not a grid row)."""
    re = d["re"]
    k = int(np.searchsorted(re, re_))
    if k < len(re) and np.isclose(re[k], re_):
        return d[fld][k, im, :]
    w = (L(re_) - L(re[k - 1])) / (L(re[k]) - L(re[k - 1]))
    return (1 - w) * d[fld][k - 1, im, :] + w * d[fld][k, im, :]


def errors(mode: str, levels) -> dict:
    lv = sorted(levels)
    out = {}
    for f in sorted(glob.glob(str(TABLES / f"*__{mode}__n9.npz"))):
        d = np.load(f)
        im = list(d["mach"]).index(0.1)
        j = [int(np.argmin(abs(d["alpha"] - a))) for a in ALPHAS]
        for R in TESTS:
            if any(np.isclose(R, x) for x in lv):
                continue
            lo, hi = (lv[-2], lv[-1]) if R > lv[-1] else (lv[int(np.searchsorted(lv, R)) - 1], lv[int(np.searchsorted(lv, R))])
            w = (L(R) - L(lo)) / (L(hi) - L(lo))
            a, b, t = table_at(d, "cd", lo, im), table_at(d, "cd", hi, im), table_at(d, "cd", R, im)
            ca, cb, ct = table_at(d, "cl", lo, im), table_at(d, "cl", hi, im), table_at(d, "cl", R, im)
            e = out.setdefault(f"{R:.3g}", {"cd": [], "cl": []})
            for k in j:
                if np.isfinite([a[k], b[k], t[k]]).all():
                    e["cd"].append(float(np.exp((1 - w) * L(a[k]) + w * L(b[k])) / t[k] - 1))
                if np.isfinite([ca[k], cb[k], ct[k]]).all() and abs(ct[k]) > 0.2:
                    e["cl"].append(float(((1 - w) * ca[k] + w * cb[k]) / ct[k] - 1))
    return out


def stats(v) -> dict:
    v = np.abs(np.asarray(v, float)) * 100
    return {"n": int(v.size), "median_pct": float(np.median(v)), "p90_pct": float(np.percentile(v, 90)),
            "worst_pct": float(v.max())} if v.size else {}


def main() -> None:
    res = {"what": "drag (and lift) read between the Re levels against the 2-D section tables; |error| in %",
           "date": "2026-11-08", "alphas_deg": list(ALPHAS), "mach": 0.1, "tests": list(TESTS),
           "sections": len(glob.glob(str(TABLES / "*__free__n9.npz"))), "ladders": {}}
    for name, lv in LADDERS.items():
        res["ladders"][name] = {"levels": list(lv)}
        for mode in ("free", "trip"):
            e = errors(mode, lv)
            inside = [x for R, v in e.items() if float(R) <= max(lv) * 1.0001 for x in v["cd"]]
            res["ladders"][name][mode] = {"per_re": {R: {"cd": stats(v["cd"]), "cl": stats(v["cl"])} for R, v in e.items()},
                                          "up_to_top": stats(inside),
                                          "up_to_4e6": stats([x for R, v in e.items() if float(R) <= 4e6 for x in v["cd"]])}
    (DOCS / "re_ladder_check.json").write_text(json.dumps(res, indent=1))
    for name, d in res["ladders"].items():
        f, t = d["free"]["up_to_4e6"], d["trip"]["up_to_4e6"]
        print(f"{name:36s} transition: median {f['median_pct']:.1f} p90 {f['p90_pct']:.1f} worst {f['worst_pct']:.0f} %  "
              f"| turbulent: median {t['median_pct']:.1f} p90 {t['p90_pct']:.1f} worst {t['worst_pct']:.0f} %")
    plot(res, DOCS / "re_ladder_check.png")


def plot(res: dict, path: Path) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK})
    fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.3), dpi=150)
    show = (("until 8 Nov", GREY, "o"), ("since 8 Nov", NEW, "s"))
    for ax, mode, title in zip(axs, ("free", "trip"), ("with transition (N_crit 9)", "fully turbulent (tripped)")):
        for name, col, mk in show:
            d = res["ladders"][name][mode]["per_re"]
            xs = sorted(float(r) for r in d)
            ys = [d[f"{x:.3g}"]["cd"]["p90_pct"] for x in xs]
            ax.plot(xs, ys, color=col, marker=mk, lw=2, ms=6, label=f"levels {name}: "
                    + ", ".join({1e5: "10⁵", 3e5: "3×10⁵", 1e6: "10⁶", 1.5e6: "1.5×10⁶", 3e6: "3×10⁶", 4e6: "4×10⁶"}
                                [x] for x in res["ladders"][name]["levels"]))
            for x in res["ladders"][name]["levels"]:
                ax.axvline(x, color=col, lw=1, ls="--" if name == "since 8 Nov" else ":", zorder=0)
        ax.set_xscale("log")
        ax.set_xlim(8e4, 8e6)
        ax.set_ylim(0, None)
        ax.set_xlabel("Re on the chord where the drag is read (2-D)")
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.grid(axis="y", color="#E3E8EE", lw=0.8)
    axs[0].set_ylabel("drag read between the levels:\n90th percentile of |error| [%]")
    h, lab = axs[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=2, fontsize=8.5, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(f"Check C4 on 2-D data: {res['sections']} sections, angles 0–6°, Mach 0.1. Points right of the top level are "
                 "extrapolated.", x=0.01, ha="left", fontsize=10.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.93))
    fig.savefig(path, facecolor="white")


if __name__ == "__main__":
    main()
