"""The look of the Stage 3 figures: the Stage 2 page's ink and lines; the wing type by position (never by colour
alone); Re and the levels as one blue ramp, light to dark (ordinal: validated light-end contrast, monotone);
limits in the status red with a text label."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402

INK, MUTED, LINE = "#142230", "#566573", "#D6DEE6"
LIMIT = "#d03b3b"                         # status: critical (always with a label)
OK = "#0ca30c"                            # status: good (always with a label)
RAMP4 = ("#86b6ef", "#3987e5", "#1c5cab", "#0d366b")   # ordinal blue 250 / 400 / 550 / 700
ACCENT = "#2a78d6"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
RES = (1e5, 3e5, 1e6, 4e6)
RE_NAME = {1e5: "Re 1e5", 3e5: "Re 3e5", 1e6: "Re 1e6", 4e6: "Re 4e6"}
LEVELS = ("VC", "C", "M", "F")

plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8.5,
                     "figure.dpi": 130, "savefig.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlelocation": "left"})


def strip(a, rows, value, *, limit=None, limit_text=None, log=False, ylabel="", title="", by_re=True):
    """Dots per mesh: x = wing type (groups), within a group one column per Re (dark = high Re)."""
    import numpy as np
    for ti, t in enumerate(TYPES):
        for ri, re in enumerate(RES):
            v = [value(r) for r in rows if r["type"] == t and (not by_re or r["re"] == re)]
            v = [x for x in v if x is not None]
            if not v:
                continue
            x = ti + (ri - 1.5) * 0.17 if by_re else ti
            a.plot(np.full(len(v), x), v, "o", ms=4.2, color=RAMP4[ri] if by_re else ACCENT, mec="white", mew=0.5,
                   label=RE_NAME[re] if ti == 0 else None, zorder=3)
            if not by_re:
                break
    if limit is not None:
        a.axhline(limit, color=LIMIT, lw=1.1, ls="--", zorder=2)
        if limit_text:
            a.annotate(limit_text, (1.0, limit), xycoords=("axes fraction", "data"), xytext=(-4, 3),
                       textcoords="offset points", ha="right", va="bottom", fontsize=7.8, color=LIMIT)
    a.set_xticks(range(len(TYPES)), [TYPE_NAME[t] for t in TYPES])
    if log:
        a.set_yscale("log")
    a.set_ylabel(ylabel)
    a.set_title(title)
    a.grid(axis="y", color=LINE, lw=0.5)
    a.set_xlim(-0.6, len(TYPES) - 0.4)


def save(fig, path) -> None:
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path.name)
