"""The figures of the size studies that had none (10-11 Nov 2026), drawn from the study files.

    python scripts/size_figures.py

    far_field.png      what a smaller domain saves          <- data/studies/far_field_scenarios.json
    size_factors.png   the cells against Re, band on / off   <- data/studies/size_factors.json
    ladder.png         the level ladder, today and lighter   <- data/studies/ladder.json
-> docs/page/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import ACCENT, INK, LIMIT, LINE, MUTED, RAMP4, plt, save   # noqa: E402

STUDIES, PAGE = HERE / "data" / "studies", HERE / "docs" / "page"
RE_WORDS = {"1e+05": "Re 10⁵", "3e+05": "Re 3 × 10⁵", "1e+06": "Re 10⁶", "4e+06": "Re 4 × 10⁶"}


def far_field() -> None:
    d = json.loads((STUDIES / "far_field_scenarios.json").read_text())
    s = d["summary"]
    keys = list(s)
    fig, a = plt.subplots(figsize=(7.4, 3.9))
    for x, k in enumerate(keys):
        c = s[k]["M"]["cells"]
        b = s[k]["VC_built"]
        ok = b["passed"] == b["of"]
        a.bar(x, c["median"] / 1e6, width=0.62, color=ACCENT if ok else "white", edgecolor=ACCENT if ok else MUTED,
              hatch=None if ok else "////", lw=0.9, zorder=3)
        a.plot([x, x], [c["min"] / 1e6, c["max"] / 1e6], color=INK, lw=1.0, zorder=4)
        v = 100 * (s[k]["M"]["vs_today"]["median"] - 1)
        a.annotate(f"{c['median'] / 1e6:.1f} M" + (f"\n{v:+.0f} %" if abs(v) > 0.5 else "\ntoday"),
                   (x, c["max"] / 1e6), xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                   fontsize=8.2, color=INK)
        if not ok:
            a.annotate(f"{b['of'] - b['passed']} of {b['of']} VC meshes\nrefused", (x, c["median"] / 2e6), ha="center",
                       va="center", fontsize=7.8, color=INK, bbox=dict(fc="white", ec="none", pad=1.5), zorder=5)
    a.set_xticks(range(len(keys)), [k.replace("front ", "").replace(" / aft ", " / ") for k in keys])
    a.set_xlabel("far field: ahead / behind the wing (mean chords)")
    a.set_ylabel("cells at M (millions)")
    a.set_ylim(0, 1.22 * max(s[k]["M"]["cells"]["max"] for k in keys) / 1e6)
    a.grid(axis="y", color=LINE, lw=0.5, zorder=0)
    a.set_title("A smaller domain: the cells at M (bar: the median of the 20 reference wings; line: their range)",
                fontsize=9.5)
    fig.text(0.01, 0.005, "Rule set 2, Re 3 × 10⁵, counted; the VC meshes also built. Hatched: a check fails.",
             fontsize=7.6, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, PAGE / "far_field.png")


def re_band() -> None:
    rows = json.loads((STUDIES / "size_factors.json").read_text())["rows"]
    res = sorted({r["re"] for r in rows})
    fig, a = plt.subplots(figsize=(6.6, 3.9))
    for band, col, ls, name in ((True, ACCENT, "-", "band on (every run)"), (False, MUTED, "--", "band off")):
        v = np.array([[r["cells"] for r in rows if r["re"] == re and r["band"] == band] for re in res]) / 1e6
        med = np.median(v, axis=1)
        a.fill_between(res, v.min(axis=1), v.max(axis=1), color=col, alpha=0.13, lw=0, zorder=2)
        a.plot(res, med, ls, color=col, lw=2, marker="o", ms=5.5, mec="white", mew=0.8, zorder=3)
        for x, y in zip(res, med):
            a.annotate(f"{y:.2f}", (x, y), xytext=(0, 7 if band else -13), textcoords="offset points", ha="center",
                       fontsize=8, color=INK)
        a.annotate(name, (res[-1], med[-1]), xytext=(9, 0), textcoords="offset points", va="center", fontsize=8.5,
                   color=INK)
    a.set_xscale("log")
    a.set_xlim(res[0] / 1.35, res[-1] * 4.2)
    a.set_xticks(res, ["10⁵", "3 × 10⁵", "10⁶", "4 × 10⁶"])
    a.minorticks_off()
    a.set_xlabel("Re on the mean chord")
    a.set_ylabel("cells at VC (millions)")
    a.set_ylim(0, None)
    a.grid(color=LINE, lw=0.5, zorder=0)
    a.set_title("The cells against Re, with and without the transition band\n(line: the median of the 20 reference "
                "wings; shade: their range)", fontsize=9.5)
    fig.text(0.01, 0.005, "Rule set 2, level VC, counted (data/studies/size_factors.json).", fontsize=7.6, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, PAGE / "size_factors.png")


def ladder() -> None:
    d = json.loads((STUDIES / "ladder.json").read_text())
    s = d["summary"]
    res = [k for k in ("3e+05", "4e+06") if k in s["today"]["by_re"]]
    levels = list(next(iter(s["today"]["by_re"].values())))
    fig, ax = plt.subplots(1, len(res), figsize=(5.0 * len(res), 4.3), sharey=True)
    ax = np.atleast_1d(ax)
    for a, re in zip(ax, res):
        for pack, col, ls, name, dy in (("today", MUTED, "--", "today (rule set 2)", 8), ("light", ACCENT, "-", "lighter rules", -14)):
            by = s[pack]["by_re"][re]
            y = np.array([by[lev]["cells"]["median"] for lev in levels]) / 1e6
            a.plot(range(len(levels)), y, ls, color=col, lw=2, zorder=3)
            for x, lev in enumerate(levels):
                hard = by[lev]["yplus"] <= 1.0 + 1e-9                  # inside the hard minimum y+ <= 1
                a.plot(x, y[x], "o", ms=7, color=col if hard else "white", mec=col, mew=1.6, zorder=4)
                a.annotate(f"{y[x]:.1f}" if y[x] >= 1 else f"{y[x]:.2f}", (x, y[x]), xytext=(0, dy),
                           textcoords="offset points", ha="center", fontsize=8.2, color=INK)
            a.annotate(name, (len(levels) - 1, y[-1]), xytext=(10, 0), textcoords="offset points", va="center",
                       fontsize=8.5, color=INK)
        a.axhline(10, color=LIMIT, lw=1.0, ls="--", zorder=2)
        a.annotate("10 M", (0, 10), xytext=(-2, 3), textcoords="offset points", ha="left", va="bottom", fontsize=8,
                   color=LIMIT)
        a.set_yscale("log")
        a.set_xticks(range(len(levels)), levels)
        a.set_xlim(-0.4, len(levels) + 0.75)
        a.set_title(RE_WORDS[re], fontsize=9.5)
        a.grid(axis="y", color=LINE, lw=0.5, zorder=0)
        a.set_yticks([0.5, 1, 2, 5, 10, 20, 30], ["0.5", "1", "2", "5", "10", "20", "30"])
        a.set_ylim(0.33, 42)
        a.minorticks_off()
    ax[0].set_ylabel("cells (millions, log scale)")
    fig.suptitle("The level ladder: today and with the three too-strict rules loosened (median of wing 0 of each type)",
                 fontsize=9.8, x=0.01, ha="left", color=INK)
    fig.text(0.01, 0.005, "Each level has 1.3 × finer cells in every direction. Open marker: VVC, one step under VC, is "
             "past the hard minimums (y⁺ 1.3). Counted (data/studies/ladder.json).", fontsize=7.6, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    save(fig, PAGE / "ladder.png")


if __name__ == "__main__":
    for name, src in ((far_field, "far_field_scenarios.json"), (re_band, "size_factors.json"), (ladder, "ladder.json")):
        if (STUDIES / src).exists():
            name()
        else:
            print("no", src, "yet")
