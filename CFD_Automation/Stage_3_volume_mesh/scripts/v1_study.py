"""V1: one wing, one level, the C-H topology. BWB reference wing 0 at VC, Re 3e5.

Builds the 13 blocks on the Stage 2 surface, runs every check, draws slices (the root, the mid semi-span, the tip,
a wake plane) and compares the cells with the Stage 2 estimate (wing blocks only, pure growth to 2 local chords).
Writes data/studies/v1.json and docs/page/v1_slices.png.

    python scripts/v1_study.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import _jsonable, build_surface, wing_from_set     # noqa: E402
from cfdauto.volume.volume import build_volume                             # noqa: E402

WALL_DEPTH_C, WALL_GROWTH_VC = 2.0, 1.25          # Stage 2's estimate (Stage_2_surface_mesh/scripts/screen.py)


def stage2_estimate(sm) -> dict:
    """Stage 2's count: n = max over the stations of ceil(ln(1 + (g - 1) D / s0) / ln g), D = 2 local chords;
    cells = (ring - 1)(stations - 1) n + cap quads x n."""
    from cfdauto.mesh.laws import rules
    rl = rules(sm.level)
    g = WALL_GROWTH_VC ** (1.0 / rl.scale)
    n = max(int(np.ceil(np.log(1 + (g - 1) * WALL_DEPTH_C * r["chord_m"] / (rl.first_cell_c(r["re_local"]) * r["chord_m"]))
                        / np.log(g) - 1e-9)) for r in sm.stations)
    wing = (sm.info["n_ring"] - 1) * (sm.info["n_span"] - 1) * n
    return {"wall_layers": n, "cells": int(wing + sm.info["cap_quads"] * n)}


def breakdown(vm) -> dict:
    out = {}
    for name, b in vm.blocks.items():
        out[name] = int(np.prod(np.array(b.shape[:3]) - 1))
    inb = sum(v for k, v in out.items() if k.endswith("_in"))
    outb = sum(v for k, v in out.items() if k.endswith("_out"))
    wake = sum(v for k, v in out.items() if k.startswith(("WU", "WL", "B_")))
    return {"per_block": out, "inboard": inb, "outboard": outb, "cap": out["CAP"], "wake_blocks": wake,
            "total": vm.cells}


def figure(vm, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    B = vm.blocks
    yk = B["CU_in"][0, 0, :, 1]
    ks = [0, int(np.argmin(np.abs(yk - 0.5 * yk[-1]))), len(yk) - 1]
    fig, ax = plt.subplots(2, 3, figsize=(15, 9.5))
    colors = {"WU": "tab:blue", "CU": "tab:green", "CN": "tab:red", "CL": "tab:olive", "WL": "tab:purple", "B": "tab:orange"}

    def draw(a, k, blocks=("WU", "CU", "CN", "CL", "WL", "B"), every=1, lw=0.3):
        for n in blocks:
            X = B[f"{n}_in"][:, :, k]
            for j in range(0, X.shape[1], every):
                a.plot(X[:, j, 0], X[:, j, 2], "-", color=colors[n], lw=lw)
            for i in range(0, X.shape[0], every):
                a.plot(X[i, :, 0], X[i, :, 2], "-", color=colors[n], lw=lw)

    for a, k, title in zip(ax[0], ks, ("root (y = 0)", "mid semi-span", "tip station")):
        X = B["CU_in"][:, 0, k]
        c = X[:, 0].max() - X[:, 0].min()
        draw(a, k)
        x0 = X[:, 0].min()
        a.set_xlim(x0 - 0.6 * c, x0 + 1.9 * c)
        a.set_ylim(X[:, 2].mean() - 0.9 * c, X[:, 2].mean() + 0.9 * c)
        a.set_aspect("equal")
        a.set_title(f"{title}: y = {B['CU_in'][0, 0, k, 1]:.3f} c")
    # the trailing edge of the root, close up
    a = ax[1, 0]
    draw(a, 0)
    te = B["CU_in"][0, 0, 0]
    a.set_xlim(te[0] - 0.02, te[0] + 0.03)
    a.set_ylim(te[2] - 0.025, te[2] + 0.025)
    a.set_aspect("equal")
    a.set_title("root trailing edge (base block orange)")
    # the whole root plane
    a = ax[1, 1]
    draw(a, 0, every=3, lw=0.25)
    a.set_aspect("equal")
    a.set_title("root plane to the far field (every 3rd line)")
    # a wake plane: x about 1 c behind the root trailing edge, the y-z grid of the wake blocks
    a = ax[1, 2]
    q = int(np.argmin(np.abs(B["WL_in"][:, 0, 0, 0] - (te[0] + 1.0))))
    for n, side in (("WL", "lower"), ("B", "base"), ("WU", "upper")):
        for part in ("in", "out"):
            X = B[f"{n}_{part}"]
            P = X[q] if n == "WL" else (X[:, q] if n == "B" else X[X.shape[0] - 1 - q])
            for j in range(P.shape[0]):
                a.plot(P[j, :, 1], P[j, :, 2], "-", color=colors[n], lw=0.25)
            for kk in range(P.shape[1]):
                a.plot(P[:, kk, 1], P[:, kk, 2], "-", color=colors[n], lw=0.25)
    y_tip = B["CU_in"][0, 0, -1, 1]
    a.set_xlim(0.0, y_tip + 1.0)
    a.set_ylim(te[2] - 0.6, te[2] + 0.8)
    a.axvline(y_tip, color="k", lw=0.8, ls="--")
    a.set_title(f"wake plane x = {B['WL_in'][q, 0, 0, 0]:.2f} c (dashed: the tip)")
    a.set_xlabel("y [c]")
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def main() -> None:
    w = wing_from_set("bwb", "reference", 0)
    sm = build_surface(w.loft, 3e5, "VC")
    vm = build_volume(sm)
    est = stage2_estimate(sm)
    br = breakdown(vm)
    out = {"what": "V1: BWB reference wing 0, VC, Re 3e5, the C-H volume mesh on the Stage 2 surface",
           "outcome": vm.outcome, "review": vm.review, "checks": [c.as_dict() for c in vm.checks],
           "cells": br, "stage2_estimate": est, "ratio_to_stage2_estimate": vm.cells / est["cells"],
           "counts": {k: vm.info[k] for k in ("n_wake", "n_layers", "n_c", "n_span", "n_out", "cap_shape")},
           "need": vm.info["need"], "ram_gib_adflow": vm.info["ram_gib_adflow"], "fits": vm.info["fits"],
           "wall_angle_3d_deg": vm.info["wall_angle_3d_deg"], "te_corner_angle_deg": vm.info["te_corner_angle_deg"],
           "quality_by_block": vm.info["quality_by_block"], "bl_cells_min": vm.info["bl_cells_min"],
           "band_cell_ratio_max": vm.info["band_cell_ratio_max"], "seconds": vm.info["seconds_total"],
           "domain": vm.info["domain"], "kappa": vm.info["kappa"], "rung": vm.info["rung"]}
    (HERE / "data" / "studies" / "v1.json").write_text(json.dumps(_jsonable(out), indent=1))
    figure(vm, HERE / "docs" / "page" / "v1_slices.png")
    print(json.dumps(_jsonable({k: out[k] for k in ("outcome", "cells", "stage2_estimate", "ratio_to_stage2_estimate",
                                                    "counts", "ram_gib_adflow")}), indent=1))


if __name__ == "__main__":
    main()
