"""Smallest and largest wing of each type, in the focus and the full space; the Re and Mach they fly at.

    python scripts/size_extremes.py     # writes docs/size_extremes.json and docs/size_extremes.gif

Smallest / largest = least / most wing area. Area = AR * (c_root * K)^2, so the extremes sit at the
corners of the size variables (root chord, aspect ratio, chord ratios, panel shares); all corners
are searched, the other variables stay mid-range.

Speeds: the speed range of the real wings of the family (configs/real_uavs.yaml): lowest cruise at
3,048 m and highest top speed at sea level (Stage 0 air). The generator itself sets no speed.
  Re  = (rho/mu) * V * chord      Mach = V / a   (a = 328.6 m/s at 3,048 m, 340.3 m/s at sea level)
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
sys.path.insert(0, str(ROOT))

from cfdauto.geometry.params import WING_TYPES, from_unit, load_config  # noqa: E402
from cfdauto.geometry.planform import build_planform  # noqa: E402

DOCS = ROOT / "docs"
SIZE_VARS = ("root_chord_m", "aspect_ratio", "c2_ratio", "c3_ratio", "c4_ratio", "b3_ratio", "split_ratio")
FAMILY = {"bwb": "tailless", "flying_wing": "tailless", "conventional": "tailed", "tapered": "tailed"}
A_SL, A_3048 = 340.3, 328.6
NAME = {"bwb": "BWB", "conventional": "Cranked", "tapered": "Tapered", "flying_wing": "Flying wing"}


def corners(spec) -> list[dict]:
    free = [v for v in SIZE_VARS if v in spec.free_variables]
    out = []
    for bits in itertools.product((0.0, 1.0), repeat=len(free)):
        vec = from_unit(spec, dict(zip(free, bits)))
        pf = build_planform(spec, vec)
        out.append({"vector": vec, "span_m": 2 * pf.semi_span, "area_m2": pf.area(),
                    "root_chord_m": float(pf.chord[0]), "tip_chord_m": float(pf.chord[-1]),
                    "mean_chord_m": pf.area() / (2 * pf.semi_span),
                    "outline": outline(pf)})
    return out


def outline(pf) -> list[list[float]]:
    """Full-wing top view (both halves): leading edge root to tip, trailing edge back."""
    y, x, c = pf.y, pf.x_le, pf.chord
    half = list(zip(y, x)) + list(zip(y[::-1], (x + c)[::-1]))
    right = [[float(a), float(b)] for a, b in half]
    left = [[-a, b] for a, b in right[::-1]]
    return right + left


def speeds() -> tuple[dict, dict]:
    d = yaml.safe_load((ROOT / "configs" / "real_uavs.yaml").read_text())
    air, out = d["air"], {}
    for fam in ("tailless", "tailed"):
        rows = [r for r in d["aircraft"] if r["family"] == fam and r["use"] in ("ranges", "span")]
        lo = min(r["cruise"] for r in rows if r.get("cruise"))
        hi = max((r["max"] or r["cruise"]) for r in rows if (r.get("max") or r.get("cruise")))
        out[fam] = (lo, hi)
    return air, out


def main() -> None:
    cfg = load_config()
    air, spd = speeds()
    res = {}
    for t in WING_TYPES:
        for space, spec in (("focus", cfg.types[t]), ("full", cfg.full[t])):
            cs = corners(spec)
            small, large = min(cs, key=lambda r: r["area_m2"]), max(cs, key=lambda r: r["area_m2"])
            lo, hi = spd[FAMILY[t]]
            rl, rh = air["3048_m"] * lo, air["sea_level"] * hi
            res[f"{t}/{space}"] = {
                "type": t, "space": space, "smallest": small, "largest": large,
                "span_m": [min(r["span_m"] for r in cs), max(r["span_m"] for r in cs)],
                "area_m2": [small["area_m2"], large["area_m2"]],
                "speed_m_s": [lo, hi], "mach": [lo / A_3048, hi / A_SL],
                "re_mean_chord": [min(r["mean_chord_m"] for r in cs) * rl, max(r["mean_chord_m"] for r in cs) * rh],
                "re_tip_min": min(r["tip_chord_m"] for r in cs) * rl,
                "re_root_max": max(r["root_chord_m"] for r in cs) * rh,
            }
    (DOCS / "size_extremes.json").write_text(json.dumps(res, indent=1))
    for k, r in res.items():
        print(f"{k:24s} span {r['span_m'][0]:5.2f}-{r['span_m'][1]:5.2f} m  area {r['area_m2'][0]:.3f}-{r['area_m2'][1]:.2f} m2  "
              f"Re {r['re_mean_chord'][0]:.2e}-{r['re_mean_chord'][1]:.2e}  tip {r['re_tip_min']:.1e}  root {r['re_root_max']:.2e}  "
              f"M {r['mach'][0]:.3f}-{r['mach'][1]:.3f}")
    gif(res, DOCS / "size_extremes.gif")


# ---------------------------------------------------------------------------------------------
def person(ax, x0, h=1.8, color="#566573"):
    """Simple standing figure, h metres tall, feet at (x0, 0) in a side-on scale box."""
    r = 0.12 * h / 1.8
    ax.add_patch(__import__("matplotlib").patches.Circle((x0, h - r), r, color=color))
    ax.plot([x0, x0], [h - 2 * r, 0.45 * h], color=color, lw=2.2)
    ax.plot([x0 - 0.18 * h / 1.8, x0, x0 + 0.18 * h / 1.8], [0, 0.45 * h, 0], color=color, lw=2.2)
    ax.plot([x0 - 0.25 * h / 1.8, x0 + 0.25 * h / 1.8], [0.75 * h, 0.75 * h], color=color, lw=2.2)


def draw(ax, rec, color, dashed, label):
    pts = np.array(rec["outline"])
    import matplotlib.patches as mp
    if dashed:
        ax.add_patch(mp.Polygon(pts[:, ::-1] * [1, -1] if False else np.column_stack([pts[:, 0], -pts[:, 1]]),
                                closed=True, fill=False, ec=color, lw=1.6, ls=(0, (5, 3)), label=label))
    else:
        ax.add_patch(mp.Polygon(np.column_stack([pts[:, 0], -pts[:, 1]]), closed=True, fc=color, ec=color,
                                alpha=0.55, lw=1.2, label=label))


def gif(res: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    col = {"bwb": "#2E8B57", "conventional": "#0C5EA8", "tapered": "#6A9FD8", "flying_wing": "#B07000"}
    big = max(res[f"{t}/full"]["largest"]["span_m"] for t in WING_TYPES) / 2 * 1.08
    deep_big = max(max(p[1] for p in res[k]["largest"]["outline"]) for k in res) * 1.08
    small_w = max(res[k]["smallest"]["span_m"] for k in res) / 2 * 1.15
    deep_small = max(max(p[1] for p in res[k]["smallest"]["outline"]) for k in res) * 1.12
    frames = []

    def frame(types, title):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.0), dpi=90, gridspec_kw={"width_ratios": [1, 2.2]})
        for t in types:
            f, u = res[f"{t}/focus"], res[f"{t}/full"]
            one = len(types) == 1
            draw(a1, f["smallest"], col[t], False, f"{NAME[t]} focus" if one else NAME[t])
            draw(a2, f["largest"], col[t], False, f"{NAME[t]} focus" if one else NAME[t])
            if one:
                draw(a1, u["smallest"], col[t], True, f"{NAME[t]} full")
                draw(a2, u["largest"], col[t], True, f"{NAME[t]} full")
        a1.set_xlim(-small_w, small_w); a1.set_ylim(-deep_small, 0.05 * deep_small)
        a2.set_xlim(-big, big); a2.set_ylim(-deep_big, 0.05 * deep_big)
        for a, sub in ((a1, f"Smallest (least area)  ·  {2 * small_w:.1f} m wide view"), (a2, f"Largest (most area)  ·  {2 * big:.0f} m wide view")):
            a.set_aspect("equal"); a.grid(alpha=0.25); a.set_title(sub, fontsize=10); a.set_xlabel("span y [m]")
        a1.set_ylabel("chordwise x [m]  (flight direction up)")
        # scale objects: a 30 cm ruler on the small view, a 1.8 m person on the big one
        yb = -0.93 * deep_small
        a1.plot([-0.93 * small_w, -0.93 * small_w + 0.3], [yb, yb], color="#566573", lw=3)
        a1.text(-0.93 * small_w + 0.15, yb + 0.03 * deep_small, "30 cm", ha="center", fontsize=9, color="#566573")
        yb = -0.92 * deep_big
        a2.plot([-0.9, 0.9], [yb, yb], color="#566573", lw=3)
        a2.text(0, yb + 0.04 * deep_big, "1.8 m (a person)", ha="center", fontsize=9, color="#566573")
        lines = []
        for t in types:
            for sp in ("focus", "full"):
                r = res[f"{t}/{sp}"]
                s, l = r["smallest"], r["largest"]
                lines.append(f"{NAME[t]:11s} {sp:5s}: span {s['span_m']:.2f} → {l['span_m']:.1f} m, area {s['area_m2']:.3f} → {l['area_m2']:.2f} m²")
        fig.suptitle(title, fontsize=13, fontweight="bold", x=0.01, ha="left")
        fig.text(0.01, 0.01, "\n".join(lines), family="monospace", fontsize=8.5, va="bottom", color="#1f2a33")
        a2.legend(loc="lower right", fontsize=8.5)
        fig.tight_layout(rect=(0, 0.03 + 0.021 * len(lines), 1, 0.95))
        buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig)
        frames.append(Image.open(io.BytesIO(buf.getvalue())).convert("P", palette=Image.ADAPTIVE, colors=128))

    for t in WING_TYPES:
        frame([t], f"{NAME[t]}: smallest and largest wing we can make (true scale; solid = focus, dashed = full)")
    frame(list(WING_TYPES), "All four types, focus space (true scale)")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[3000] * 4 + [4500], loop=0, optimize=True)


if __name__ == "__main__":
    main()
