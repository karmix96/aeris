"""The extreme shapes of each type, in the focus and the full space, at unit mean chord; the local Re they see.

Since decision 70 (7 Nov 2026) every wing is built at unit mean chord: mean chord = area / full span = 1.
So a wing has no size. Every length is in mean chords, the full span b equals the aspect ratio, and the
area equals the aspect ratio too. Size enters only through the Re on the mean chord, an input of each solve
(the Stage 0 levels: 1e5, 3e5, 1e6, 4e6 since 8 Nov 2026; 1e5, 3e5, 1.5e6, 3e6 before).

    python scripts/size_extremes.py     # writes docs/size_extremes.json and docs/size_extremes.gif

Searched over all corners of the planform inputs (aspect ratio, chord ratios, panel shares); the other
inputs stay mid-range:
  lowest / highest aspect ratio    the two outlines in the GIF
  smallest tip chord               with the lowest Re level, the lowest local Re (tip Re = 1e5 x tip chord)
  largest root chord               with the top Re level, the highest local Re (root Re = 4e6 x root chord)
  local Re = (Re on the mean chord) x (local chord in mean chords)

The first approach (real size and real speeds, 30 Oct - 6 Nov 2026) is kept, not rebuilt:
docs/first_approach/size_extremes.json and docs/first_approach/size_extremes.gif.
"""

from __future__ import annotations

import io
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))   # CFD_Automation: the cfdauto package

from cfdauto.geometry.params import WING_TYPES, from_unit, load_config  # noqa: E402
from cfdauto.geometry.planform import build_planform  # noqa: E402

DOCS = ROOT / "docs"
SHAPE_VARS = ("aspect_ratio", "c2_ratio", "c3_ratio", "c4_ratio", "b3_ratio", "split_ratio")
NAME = {"bwb": "BWB", "cranked": "Cranked", "tapered": "Tapered", "flying_wing": "Flying wing"}
STAGE0 = ROOT.parent / "Stage_0_decisions" / "values.yaml"


def re_levels() -> list[float]:
    """The Stage 0 Re levels on the mean chord (area / full span)."""
    d = yaml.safe_load(STAGE0.read_text())
    return sorted(float(x) for x in d["D3_conditions_and_measurement"]["reynolds_levels"]["value"])


def corners(spec) -> list[dict]:
    """Every corner of the planform inputs of this space (others mid-range)."""
    free = [v for v in SHAPE_VARS if v in spec.free_variables]
    vecs = [from_unit(spec, dict(zip(free, bits))) for bits in itertools.product((0.0, 1.0), repeat=len(free))]
    out = []
    for vec in vecs:
        pf = build_planform(spec, vec)
        b = 2 * pf.semi_span
        out.append({"vector": vec, "aspect_ratio": b * b / pf.area(), "full_span": b,
                    "mean_chord": pf.area() / b, "root_chord": float(pf.chord[0]), "tip_chord": float(pf.chord[-1]),
                    "taper": float(pf.chord[-1] / pf.chord[0]), "outline": outline(pf)})
    return out


def outline(pf) -> list[list[float]]:
    """Full-wing top view (both halves): leading edge root to tip, trailing edge back."""
    y, x, c = pf.y, pf.x_le, pf.chord
    half = list(zip(y, x)) + list(zip(y[::-1], (x + c)[::-1]))
    right = [[float(a), float(b)] for a, b in half]
    left = [[-a, b] for a, b in right[::-1]]
    return right + left


def main() -> None:
    cfg = load_config()
    levels = re_levels()
    res = {"_meta": {"date": "2026-11-07", "unit": "mean chords (every wing at unit mean chord, decision 70)",
                     "re_levels": levels, "search": "all corners of " + ", ".join(SHAPE_VARS) + "; others mid-range"}}
    for t in WING_TYPES:
        for space, spec in (("focus", cfg.types[t]), ("full", cfg.full[t])):
            cs = corners(spec)
            lo, hi = min(cs, key=lambda r: r["aspect_ratio"]), max(cs, key=lambda r: r["aspect_ratio"])
            tip, root = min(cs, key=lambda r: r["tip_chord"]), max(cs, key=lambda r: r["root_chord"])
            assert all(abs(r["mean_chord"] - 1) < 1e-9 for r in cs)          # unit mean chord on every corner
            res[f"{t}/{space}"] = {
                "type": t, "space": space, "lowest_ar": lo, "highest_ar": hi, "smallest_tip": tip, "largest_root": root,
                "aspect_ratio": [lo["aspect_ratio"], hi["aspect_ratio"]],
                "root_chord": [min(r["root_chord"] for r in cs), root["root_chord"]],
                "tip_chord": [tip["tip_chord"], max(r["tip_chord"] for r in cs)],
                "taper": [min(r["taper"] for r in cs), max(r["taper"] for r in cs)],
                "re_tip_min": tip["tip_chord"] * levels[0],
                "re_root_max": root["root_chord"] * levels[-1],
                "root_over_tip_max": max(r["root_chord"] / r["tip_chord"] for r in cs),
            }
    (DOCS / "size_extremes.json").write_text(json.dumps(res, indent=1))
    for k, r in res.items():
        if k.startswith("_"):
            continue
        print(f"{k:20s} AR {r['aspect_ratio'][0]:5.2f}-{r['aspect_ratio'][1]:5.2f}  root {r['root_chord'][0]:.3f}-"
              f"{r['root_chord'][1]:.3f}  tip {r['tip_chord'][0]:.3f}-{r['tip_chord'][1]:.3f} mean chords  "
              f"tip Re at {levels[0]:.0e}: {r['re_tip_min']:.2e}  root Re at {levels[-1]:.0e}: {r['re_root_max']:.2e}")
    gif(res, DOCS / "size_extremes.gif")


# ---------------------------------------------------------------------------------------------
def draw(ax, rec, color, dashed, label):
    import matplotlib.patches as mp
    pts = np.array(rec["outline"])
    poly = np.column_stack([pts[:, 0], -pts[:, 1]])
    if dashed:
        ax.add_patch(mp.Polygon(poly, closed=True, fill=False, ec=color, lw=1.6, ls=(0, (5, 3)), label=label))
    else:
        ax.add_patch(mp.Polygon(poly, closed=True, fc=color, ec=color, alpha=0.55, lw=1.2, label=label))


def gif(res: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    col = {"bwb": "#2E8B57", "cranked": "#0C5EA8", "tapered": "#6A9FD8", "flying_wing": "#B07000"}
    keys = [k for k in res if not k.startswith("_")]
    wide = max(res[k]["highest_ar"]["full_span"] for k in keys) / 2 * 1.06
    deep_wide = max(max(p[1] for p in res[k]["highest_ar"]["outline"]) for k in keys) * 1.15
    narrow = max(res[k]["lowest_ar"]["full_span"] for k in keys) / 2 * 1.25
    deep_narrow = max(max(p[1] for p in res[k]["lowest_ar"]["outline"]) for k in keys) * 1.10
    frames = []

    def frame(types, title):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 6.4), dpi=90, gridspec_kw={"width_ratios": [1, 2.2]})
        for t in types:
            f, u = res[f"{t}/focus"], res[f"{t}/full"]
            one = len(types) == 1
            draw(a1, f["lowest_ar"], col[t], False, f"{NAME[t]} focus" if one else NAME[t])
            draw(a2, f["highest_ar"], col[t], False, f"{NAME[t]} focus" if one else NAME[t])
            if one:
                draw(a1, u["lowest_ar"], col[t], True, f"{NAME[t]} full")
                draw(a2, u["highest_ar"], col[t], True, f"{NAME[t]} full")
        a1.set_xlim(-narrow, narrow); a1.set_ylim(-deep_narrow, 0.06 * deep_narrow)
        a2.set_xlim(-wide, wide); a2.set_ylim(-deep_wide, 0.06 * deep_wide)
        for a, sub in ((a1, f"Lowest aspect ratio  ·  view {2 * narrow:.1f} mean chords wide"),
                       (a2, f"Highest aspect ratio  ·  view {2 * wide:.0f} mean chords wide")):
            a.set_aspect("equal"); a.grid(alpha=0.25); a.set_title(sub, fontsize=10)
            a.set_xlabel("y along the full span [mean chords]")
        a1.set_ylabel("chordwise x [mean chords]  (flight direction up)")
        for a, w, d in ((a1, narrow, deep_narrow), (a2, wide, deep_wide)):    # a ruler of one mean chord
            yb = -0.92 * d
            a.plot([-0.9 * w, -0.9 * w + 1.0], [yb, yb], color="#566573", lw=3)
            a.text(-0.9 * w + 0.5, yb + 0.04 * d, "1 mean chord", ha="center", fontsize=9, color="#566573")
        lines = []
        for t in types:
            for sp in ("focus", "full"):
                r = res[f"{t}/{sp}"]
                lines.append(f"{NAME[t]:11s} {sp:5s}: AR (= full span) {r['aspect_ratio'][0]:.1f} → {r['aspect_ratio'][1]:.1f}, "
                             f"root chord up to {r['root_chord'][1]:.2f}, tip chord down to {r['tip_chord'][0]:.3f} mean chords")
        fig.suptitle(title, fontsize=13, fontweight="bold", x=0.01, ha="left")
        fig.text(0.01, 0.01, "\n".join(lines), family="monospace", fontsize=8.5, va="bottom", color="#1f2a33")
        a2.legend(loc="lower right", fontsize=8.5)
        fig.tight_layout(rect=(0, 0.30, 1, 0.95))          # the same layout in every frame: room for 8 text lines
        buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig)
        frames.append(Image.open(io.BytesIO(buf.getvalue())).convert("P", palette=Image.ADAPTIVE, colors=128))

    for t in WING_TYPES:
        frame([t], f"{NAME[t]}: lowest and highest aspect ratio, at unit mean chord (solid = focus, dashed = full)")
    frame(list(WING_TYPES), "All four types, focus space, at unit mean chord")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[3000] * 4 + [4500], loop=0, optimize=True)


if __name__ == "__main__":
    main()
