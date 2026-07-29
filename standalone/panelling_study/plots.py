"""Shared plotting for the panelling study. §8 rules are enforced here:
matplotlib defaults only, <=4 lines or 5 bars per axes, labels at line ends,
titles state the finding, dpi=150, bbox_inches='tight', percentages as percents.
No twin axes, no log-log, no colour maps, no dashboards (one documented
exception: stage6_rank_agreement, a single row of small scatters).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ACCENT = "crimson"
GREY = "0.6"
REF = "0.4"


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def lines_labelled_at_end(x, series: dict, *, xlabel, ylabel, title, path: Path,
                          logx2: bool = False):
    """<=4 lines, each labelled at its right-hand end (§8). `series` maps label
    -> y-values aligned with x."""
    assert len(series) <= 4, "§8: at most 4 lines per axes"
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    colors = [ACCENT, "navy", "seagreen", "darkorange"]
    for (label, ys), c in zip(series.items(), colors):
        ax.plot(x, ys, marker="o", color=c)
        ax.annotate(str(label), (x[-1], ys[-1]), color=c, fontsize=9,
                    xytext=(5, 0), textcoords="offset points", va="center")
    if logx2:
        ax.set_xscale("log", base=2)
        ax.set_xticks(x)
        ax.get_xaxis().set_major_formatter(plt.matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return _save(fig, path)


def bars(labels, heights, *, ylabel, title, path: Path, hline=None,
         hline_label=None, value_labels=None):
    """<=5 bars (§8). Optional reference hline and per-bar text labels."""
    assert len(labels) <= 5, "§8: at most 5 bars per axes"
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    xs = range(len(labels))
    ax.bar(xs, heights, color=ACCENT)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([str(l) for l in labels])
    if hline is not None:
        ax.axhline(hline, color=REF, linestyle="--")
        if hline_label:
            ax.annotate(hline_label, (len(labels) - 0.5, hline), color=REF,
                        fontsize=9, va="bottom", ha="right")
    if value_labels:
        for x, h, t in zip(xs, heights, value_labels):
            ax.annotate(str(t), (x, h), fontsize=8, ha="center", va="bottom")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return _save(fig, path)


def grouped_bars(groups, series: dict, *, xlabel, ylabel, title, path: Path,
                 hline=None, hline_label=None):
    """Grouped bar chart (e.g. Stage 4 spacing). `series` maps legend-label ->
    list aligned with `groups`."""
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    import numpy as np
    n = len(series)
    width = 0.8 / n
    x = np.arange(len(groups))
    colors = [ACCENT, "navy", "seagreen", "darkorange", "grey"]
    for i, ((label, vals), c) in enumerate(zip(series.items(), colors)):
        ax.bar(x + (i - (n - 1) / 2) * width, vals, width, label=label, color=c)
    if hline is not None:
        ax.axhline(hline, color=REF, linestyle="--")
        if hline_label:
            ax.annotate(hline_label, (len(groups) - 0.5, hline), color=REF,
                        fontsize=9, va="bottom", ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([str(g) for g in groups])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    return _save(fig, path)
