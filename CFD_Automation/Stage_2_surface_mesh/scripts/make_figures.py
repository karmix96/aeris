"""Pictures of the reference meshes for docs/ (one overview per type, plus the BWB tip cap),
and the screen summary figure from data/studies/screen_C.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.mesh.figures import INK, MUTED, cap_figure, overview  # noqa: E402
from cfdauto.mesh.surface import build_surface, wing_from_set  # noqa: E402
from cfdauto.paths import STAGE2  # noqa: E402

DOCS = STAGE2 / "docs"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")


def reference_pictures() -> None:
    for t in TYPES:
        w = wing_from_set(t, "reference", 0)
        m = build_surface(w.loft, 3.0e5, "C")
        overview(m, f"{t} reference wing 0, level C, Re 3e5 on the mean chord", DOCS / f"surface_{t}.png")
        if t == "bwb":
            cap_figure(m, "BWB reference wing 0: the tip cap (level C, Re 3e5)", DOCS / "surface_bwb_cap.png")
        print(t, "ring", m.info["n_ring"], "x", m.info["n_span"], "passed", m.passed)


def screen_picture(path: Path = STAGE2 / "data" / "studies" / "screen_C.json") -> None:
    if not path.exists():
        print("no screen file yet")
        return
    rows = [r for r in json.loads(path.read_text())["rows"] if r["built"]]
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    cols = {"bwb": "#2B6CB0", "flying_wing": "#6B46C1", "cranked": "#D9822B", "tapered": "#2F855A"}
    for t in TYPES:
        rr = [r for r in rows if r["wing_type"] == t and r["re_mean"] == 3.0e5]
        c = np.array([r["mean_chord_m"] for r in rr])
        ax[0].scatter(c, [r["n_ring"] for r in rr], s=8, color=cols[t], label=t)
        ax[1].scatter([r["semi_span_m"] / r["mean_chord_m"] for r in rr], [r["n_span"] for r in rr], s=8, color=cols[t])
        ax[2].scatter(c, [r["seconds"] for r in rr], s=8, color=cols[t])
    ax[0].set_xlabel("mean chord [m]"); ax[0].set_ylabel("ring nodes"); ax[0].legend(fontsize=8)
    ax[1].set_xlabel("semi-span / mean chord"); ax[1].set_ylabel("stations")
    ax[2].set_xlabel("mean chord [m]"); ax[2].set_ylabel("build time [s]")
    for a in ax:
        a.set_xscale("log"); a.tick_params(colors=MUTED); a.xaxis.label.set_color(INK); a.yaxis.label.set_color(INK)
    n_ok = sum(r["passed"] for r in rows)
    fig.suptitle(f"Screen at level C, Re 3e5: {n_ok} of {len(rows)} meshes passed every check", fontsize=11, color=INK)
    fig.tight_layout()
    DOCS.mkdir(parents=True, exist_ok=True)
    fig.savefig(DOCS / "screen_C.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    DOCS.mkdir(parents=True, exist_ok=True)
    reference_pictures()
    screen_picture()
