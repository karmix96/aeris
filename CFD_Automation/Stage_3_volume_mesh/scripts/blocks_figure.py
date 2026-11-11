"""The 13 blocks, named: a picture the page did not have (11 Nov 2026). BWB reference wing 0 at VC, Re 3e5.

    python scripts/blocks_figure.py
-> docs/page/blocks.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import INK, LINE, MUTED, plt, save                    # noqa: E402
sys.path.insert(0, str(HERE.parent))
from cfdauto.mesh.surface import build_surface, wing_from_set     # noqa: E402
from cfdauto.volume.volume import build_volume                    # noqa: E402

COL = {"WU": "tab:blue", "CU": "tab:green", "CN": "tab:red", "CL": "tab:olive", "WL": "tab:purple", "B": "tab:orange"}
WORDS = {"WU": "WU\nupper wake", "CU": "CU\nupper side", "CN": "CN\nnose", "CL": "CL\nlower side", "WL": "WL\nlower wake",
         "B": "B (base)"}


def outline(G: np.ndarray) -> np.ndarray:
    """The edge of one block face (ni, nj, 3) as a closed line."""
    return np.concatenate([G[:, 0], G[-1, :], G[::-1, -1], G[0, ::-1]])


def plane(a, B, side: str, k: int, box, step: int, label: dict) -> None:
    for n in ("WU", "CU", "CN", "CL", "WL", "B"):
        G = B[f"{n}_{side}"][:, :, k]
        e = outline(G)
        a.fill(e[:, 0], e[:, 2], color=COL[n], alpha=0.10, lw=0, zorder=1)
        for i in range(0, G.shape[0], step):
            a.plot(G[i, :, 0], G[i, :, 2], "-", color=COL[n], lw=0.25, zorder=2)
        for j in range(0, G.shape[1], step):
            a.plot(G[:, j, 0], G[:, j, 2], "-", color=COL[n], lw=0.25, zorder=2)
        a.plot(e[:, 0], e[:, 2], "-", color=COL[n], lw=1.3, zorder=3)
        if n in label:
            a.annotate(WORDS[n], label[n], ha="center", va="center", fontsize=8.5, color=INK, zorder=5,
                       bbox=dict(fc="white", ec=COL[n], lw=0.9, boxstyle="round,pad=0.25"))
    a.set_xlim(box[0], box[1])
    a.set_ylim(box[2], box[3])
    a.set_aspect("equal")
    a.set_xlabel("x [mean chords]")
    a.set_ylabel("z [mean chords]")


def main() -> None:
    w = wing_from_set("bwb", "reference", 0)
    vm = build_volume(build_surface(w.loft, 3e5, "VC"))
    B = vm.blocks
    fig, ax = plt.subplots(1, 3, figsize=(15.5, 4.9))
    plane(ax[0], B, "in", 0, (-1.6, 4.6, -2.3, 2.3), 3,
          {"WU": (3.4, 1.3), "CU": (0.7, 1.5), "CN": (-1.0, 0.0), "CL": (0.7, -1.5), "WL": (3.4, -1.3)})
    ax[0].annotate(WORDS["B"], (3.3, 0.02), xytext=(3.3, 0.55), ha="center", fontsize=8.5, color=INK,
                   arrowprops=dict(arrowstyle="-", color=COL["B"], lw=1.0),
                   bbox=dict(fc="white", ec=COL["B"], lw=0.9, boxstyle="round,pad=0.25"))
    ax[0].set_title("(a) one station plane (the root): six blocks around the section")
    plane(ax[1], B, "in", 0, (-95, 95, -95, 95), 6, {"WU": (48, 45), "CU": (-28, 62), "CN": (-62, 0), "CL": (-28, -62),
                                                    "WL": (48, -45)})
    ax[1].set_title("(b) the same plane out to the far field (80 mean chords)")
    a = ax[2]                                                    # (c) from above: the stations, in and out
    CU_in, CU_out, cap = B["CU_in"], B["CU_out"], B["CAP"]
    y_in, y_out = CU_in[0, 0, :, 1], CU_out[0, 0, :, 1]
    x0, x1 = float(CU_in[:, 0, :, 0].min()) - 0.9, float(CU_in[:, 0, :, 0].max()) + 2.6
    for y in y_in:
        a.plot([x0, x1], [y, y], "-", color="tab:green", lw=0.3, zorder=2)
    for y in y_out[y_out <= 4.6]:
        a.plot([x0, x1], [y, y], "-", color=MUTED, lw=0.3, zorder=2)
    le = np.array([[CU_in[:, 0, k, 0].min(), CU_in[0, 0, k, 1]] for k in range(CU_in.shape[2])])
    te = np.array([[CU_in[:, 0, k, 0].max(), CU_in[0, 0, k, 1]] for k in range(CU_in.shape[2])])
    wing = np.concatenate([le, te[::-1]])
    a.fill(wing[:, 0], wing[:, 1], color="white", ec=INK, lw=1.1, zorder=3)
    y_tip = float(y_in[-1])
    a.plot([le[-1, 0], te[-1, 0]], [y_tip, y_tip], "-", color="tab:orange", lw=2.2, zorder=4)
    for txt, xy, col in (("the wing (the wall)", (float(wing[:, 0].mean()) - 0.15, 0.9), INK),
                         (f"blocks *_in: {len(y_in)} stations,\nroot to tip", (x1 - 1.25, 1.2), "tab:green"),
                         (f"blocks *_out: {len(y_out)} stations,\ntip to 80 mean chords away", (x1 - 1.25, 4.05), MUTED),
                         ("CAP: on the tip cap, between\nthe tip and the far field", (x0 + 1.15, 4.05), "tab:orange")):
        a.annotate(txt, xy, ha="center", va="center", fontsize=8.5, color=INK, zorder=6,
                   bbox=dict(fc="white", ec=col, lw=0.9, boxstyle="round,pad=0.25"))
    a.annotate("", (float(le[-1, 0] + te[-1, 0]) / 2, y_tip + 0.03), xytext=(x0 + 1.15, 3.78),
               arrowprops=dict(arrowstyle="-", color="tab:orange", lw=1.0), zorder=5)
    a.set_xlim(x0, x1)
    a.set_ylim(-0.1, 4.6)
    a.set_xlabel("x [mean chords]")
    a.set_ylabel("y along the semi-span [mean chords]")
    a.set_title("(c) from above: the planes are stacked root to tip, then past the tip")
    del cap
    for a in ax:
        a.grid(color=LINE, lw=0.4, zorder=0)
    n_cells = vm.cells
    fig.text(0.01, 0.005, f"BWB reference wing 0, VC, Re 3 × 10⁵, rule set 2 ({n_cells:,} cells). 6 blocks in every "
             "station plane × 2 (wing stations, past the tip) + the CAP block = 13. In (c) each line is one station "
             "plane: they crowd at the tip, where the gap is 2 × the first wall cell.", fontsize=7.8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, HERE / "docs" / "page" / "blocks.png")


if __name__ == "__main__":
    main()
