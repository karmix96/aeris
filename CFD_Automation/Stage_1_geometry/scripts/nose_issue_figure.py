"""A simple picture of the nose issue (decision 64): docs/nose_issue.png.

    python scripts/nose_issue_figure.py

Reads data/studies/nose_curvature.json (written by scripts/nose_curvature.py); computes nothing new.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "studies" / "nose_curvature.json"
OUT = ROOT / "docs" / "nose_issue.png"

INK, MUTED, GRID = "#142230", "#5A6878", "#E3E8EE"
OLD, NEW = "#E0702F", "#2B78D4"
H = [0.04, 0.10, 0.18, 0.30, 0.50]   # cell arc lengths of the study [% c]


def main() -> None:
    d = json.load(open(DATA))
    a = d["airfoils"]["naca4415"]
    prof = a["profile_kappa"]
    s = np.linspace(-2.0, 2.0, len(prof["raw"]))
    T = {k: a["curves"][k]["T_deg"] for k in ("exact", "old", "new")}
    db = d["database"]

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK})
    fig = plt.figure(figsize=(13.0, 5.0), dpi=150)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.55, 1.0, 0.9], wspace=0.32, left=0.055, right=0.985, top=0.83, bottom=0.30)

    # 1. curvature around the nose
    ax = fig.add_subplot(gs[0])
    ax.plot(s, prof["raw"], color=INK, lw=2.2, label="true shape (raw file, smooth spline)")
    ax.plot(s, prof["old"], color=OLD, lw=2.0, label="built, old rule")
    ax.plot(s, prof["new"], color=NEW, lw=2.0, ls=(0, (5, 3)), label="built, new rule")
    ax.set_xlim(-2, 2)
    ax.set_ylim(0, 120)
    ax.set_xlabel("distance along the surface from the old leading edge [% c]\n(− lower side, + upper side)")
    ax.set_ylabel("curvature [1/c]  (high = sharp)")
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.annotate("old: a sharp spot on top\n(567/c, radius 0.0018 c)", xy=(0.03, 118), xytext=(0.35, 96),
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=1), fontsize=9.5)
    k0 = float(np.interp(-0.03, s, prof["old"]))
    ax.annotate("old: almost flat\njust below the nose", xy=(-0.03, k0), xytext=(-1.95, 4.0),
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=1), fontsize=9.5, va="bottom")
    ax.text(0.72, 55, "true and new: one round nose\n(about 41/c, radius 0.024 c)", fontsize=9.5, color=INK)
    ax.text(-0.75, 81, "old: a bump", fontsize=9.5, color=INK, ha="center")
    ax.legend(loc="upper left", frameon=False, fontsize=9, bbox_to_anchor=(0.0, 1.0))
    ax.set_title("1. The shape at the nose (NACA 4415)", loc="left", fontsize=12, fontweight="bold")

    # 2. turning per cell
    ax = fig.add_subplot(gs[1])
    idx = [H.index(0.04), H.index(0.18)]
    x = np.arange(2)
    w = 0.26
    for j, (k, col, lab) in enumerate((("exact", INK, "true"), ("old", OLD, "old"), ("new", NEW, "new"))):
        v = [T[k][i] for i in idx]
        bars = ax.bar(x + (j - 1) * w, v, w * 0.92, color=col, label=lab, zorder=3)
        for b, val in zip(bars, v):
            ax.text(b.get_x() + b.get_width() / 2, val + 0.18, f"{val:.2f}°", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_xticks(x, ["0.04 % c cell", "0.18 % c cell"])
    ax.set_ylabel("largest bend of the surface\nacross one cell [°]")
    ax.set_ylim(0, 11)
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_title("2. What one mesh cell feels", loc="left", fontsize=12, fontweight="bold")

    # 3. the database
    ax = fig.add_subplot(gs[2])
    n = db["summary"]["measured_both"]
    vals = [21.0, 95.6]
    ax.barh([1, 0], vals, 0.55, color=[OLD, NEW], zorder=3)
    for yv, val in zip([1, 0], vals):
        ax.text(val + 2, yv, f"{val:.1f} %", va="center", fontsize=10.5, color=INK)
    ax.set_yticks([1, 0], ["old rule", "new rule"])
    ax.set_xlim(0, 115)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("files that pass the 5 % test [%]")
    ax.grid(axis="x", color=GRID, lw=0.8, zorder=0)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title(f"3. All {n:,} airfoil files", loc="left", fontsize=12, fontweight="bold")

    fig.text(0.055, 0.935, "The nose issue (decision 64): the old rule made a false sharp spot; the new rule follows the airfoil",
             fontsize=13.5, fontweight="bold", color=INK)
    fig.text(0.055, 0.045,
             "Why: the old rule put the leading edge on the file point farthest from the trailing edge and made the surface square to the chord there.\n"
             "The real tip of the curve lies between two file points (0.21 % c away on NACA 4415), so the built nose got a sharp spot on one side and a flat spot\n"
             "on the other. Fix (7 Nov 2026): one smooth spline through all the points, the leading edge at its real tip, 201 points per side; a gate refuses 14 bad files.",
             fontsize=9.6, color=MUTED, linespacing=1.45)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor="white")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
