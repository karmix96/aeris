"""Flow maps of the focus space: each type's mid wing, slow and fast, with three section sets.

    python scripts/focus_flowmaps.py     # needs xfoil; writes docs/flowmap_<type>.png, docs/focus_flowmaps.json

Wing: the focus mid-range wing of each type (reference wing 0). Conditions (speeds of the real wings
of its family, configs/real_uavs.yaml):
  slow: lowest cruise at 3,048 m, root angle 5 deg   (our choice: high lift at low speed)
  fast: highest top speed at sea level, root angle 1 deg
Section sets: the suggested one and two sourced alternatives (configs/shape_evidence.yaml sources;
SD7032 on the Puma 3AE and LA2573A on the Dragon Eye: NTNU UAV database).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))   # CFD_Automation: the cfdauto package

from cfdauto.flowmap.core import BANDS, band, flow_map  # noqa: E402
from cfdauto.geometry.build import load_set  # noqa: E402
from cfdauto.geometry.params import FAMILY_OF, TAILLESS_TYPES, WING_TYPES, load_config  # noqa: E402

DOCS = ROOT / "docs"
NAME = {"bwb": "BWB", "flying_wing": "Flying wing", "cranked": "Cranked", "tapered": "Tapered"}
SETS = {
    "bwb": [("suggested: MH 104 / MH 61", ["mh104", "mh104", "mh61", "mh61"]),
            ("S5010 (Lehmkuehler BWB)", ["s5010"] * 4),
            ("NACA 4415 / 4412 (not reflexed)", ["naca4415", "naca4415", "naca4412", "naca4412"])],
    "flying_wing": [("suggested: MH 60 / MH 45", ["mh60", "mh60", "mh45", "mh45"]),
                    ("S5010", ["s5010"] * 4),
                    ("MH 104 / MH 61", ["mh104", "mh104", "mh61", "mh61"])],
    "cranked": [("suggested: NACA 4415 / 4412", ["naca4415", "naca4415", "naca4412", "naca4412"]),
                ("SD7032 (Puma 3AE)", ["sd7032"] * 4),
                ("LA2573A (Dragon Eye)", ["la2573a"] * 4)],
    "tapered": [("suggested: NACA 4415 / 4412", ["naca4415", "naca4415", "naca4412", "naca4412"]),
                ("SD7032 (Puma 3AE)", ["sd7032"] * 4),
                ("LA2573A (Dragon Eye)", ["la2573a"] * 4)],
}


def speeds() -> dict:
    d = yaml.safe_load((ROOT / "configs" / "real_uavs.yaml").read_text())
    out = {}
    for fam in ("tailless", "conventional"):
        rows = [r for r in d["aircraft"] if r["family"] == fam and r["use"] in ("ranges", "span")]
        out[fam] = (min(r["cruise"] for r in rows if r.get("cruise")),
                    max((r["max"] or r["cruise"]) for r in rows if (r.get("max") or r.get("cruise"))))
    return out


def main() -> None:
    cfg = load_config()
    sp = speeds()
    res = {}
    for t in WING_TYPES:
        vec = load_set(t, "reference")["vectors"][0]
        lo, hi = sp[FAMILY_OF[t]]
        conds = [("slow", lo, 3048.0, 5.0), ("fast", hi, 0.0, 1.0)]
        res[t] = []
        for lab, secs in SETS[t]:
            for cname, v, alt, al in conds:
                fm = flow_map(cfg.types[t], vec, t in TAILLESS_TYPES, v, alt, al, secs)
                res[t].append({"set": lab, "airfoils": secs, "condition": cname, "map": fm})
                m = fm["model"]
                print(f"{t:11s} {lab:34s} {cname}: bias {m['sa_drag_bias'] if m['sa_drag_bias'] is None else round(100 * m['sa_drag_bias'])} %  {m['model'][:40]}")
        grid(t, res[t])
    (DOCS / "focus_flowmaps.json").write_text(json.dumps(res, indent=1, default=float))


def grid(t: str, maps: list[dict]) -> None:
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    import matplotlib.patches as mp

    sets = list(dict.fromkeys(m["set"] for m in maps))
    fig, axes = plt.subplots(len(sets), 2, figsize=(12.5, 2.9 * len(sets) + 0.9), dpi=105)
    for m in maps:
        r_ = sets.index(m["set"]); c_ = 0 if m["condition"] == "slow" else 1
        ax, fm = axes[r_, c_], m["map"]
        g, rows = fm["geometry"], fm["strips"]
        S = g["semi_span_m"]
        yy, xl, ch = np.array(g["y"]), np.array(g["x_le"]), np.array(g["chord"])
        ys = np.array([r["y"] for r in rows])
        edges = np.concatenate([[0.0], 0.5 * (ys[1:] + ys[:-1]), [S]])
        for (e0, e1), r in zip(zip(edges[:-1], edges[1:]), rows):
            x0, x1 = np.interp([e0, e1], yy, xl); c0, c1 = np.interp([e0, e1], yy, ch)
            ax.add_patch(mp.Polygon([(e0, -x0), (e1, -x1), (e1, -(x1 + c1)), (e0, -(x0 + c0))], closed=True,
                                    fc=band(r["re"])[1], ec="white", lw=0.4, alpha=0.85))
        tr = [(r["y"], r["x_le"] + r["xtr_upper"] * r["chord"]) for r in rows if r.get("xtr_upper") is not None]
        if tr:
            ax.plot([a for a, _ in tr], [-b for _, b in tr], color="white", lw=2.6)
            ax.plot([a for a, _ in tr], [-b for _, b in tr], color="#1F2A33", lw=1.3, ls="--")
        for r in rows:
            for b0, b1 in r.get("bubbles_upper") or []:
                ax.plot([r["y"]] * 2, [-(r["x_le"] + b0 * r["chord"]), -(r["x_le"] + b1 * r["chord"])], color="#7A1F1F",
                        lw=4, solid_capstyle="butt")
            if r.get("te_separation"):
                ax.plot(r["y"], -(r["x_le"] + 0.95 * r["chord"]), marker="x", color="#7A1F1F", ms=6, mew=2)
        ax.plot(yy, -xl, color="#1F2A33", lw=0.9); ax.plot(yy, -(xl + ch), color="#1F2A33", lw=0.9)
        ax.set_aspect("equal", adjustable="datalim"); ax.set_xticks([]); ax.set_yticks([])
        for s_ in ax.spines.values():
            s_.set_visible(False)
        c, mo = fm["conditions"], fm["model"]
        res_ = [r["re"] for r in rows]
        xt = [r["xtr_upper"] for r in rows if r.get("xtr_upper") is not None]
        bias = mo["sa_drag_bias"]
        ax.set_title(f"{m['set']} — {m['condition']}: {c['speed_m_s']:g} m/s, {c['altitude_m']:.0f} m, α {c['alpha_deg']:g}°",
                     fontsize=8.5, loc="left")
        txt = (f"Re {min(res_):.1e} – {max(res_):.1e};  transition {100 * min(xt):.0f}–{100 * max(xt):.0f} % c" if xt else
               f"Re {min(res_):.1e} – {max(res_):.1e}")
        txt += (f";  SA drag {100 * bias:+.0f} %" if bias is not None else "")
        ax.text(0.0, -0.06, txt.replace("e+0", "e"), transform=ax.transAxes, fontsize=7.8, va="top", color="#34495E")
    h = [mp.Patch(color=col, label=f"Re {n}") for _, _, n, col in BANDS]
    h += [plt.Line2D([], [], color="#1F2A33", ls="--", label="transition (upper)"),
          plt.Line2D([], [], color="#7A1F1F", lw=4, label="laminar bubble (upper)"),
          plt.Line2D([], [], color="#7A1F1F", marker="x", ls="none", label="TE separation")]
    fig.legend(handles=h, loc="lower center", ncol=7, fontsize=7.5, frameon=False)
    g0 = maps[0]["map"]["geometry"]
    fig.suptitle(f"{NAME[t]} mid wing (full span {g0['full_span_m']:.1f} m, root chord {g0['root_chord_m']:.2f} m): "
                 "half wing, root at left; rows = section sets, columns = slow / fast", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96), h_pad=2.0)
    fig.savefig(DOCS / f"flowmap_{t}.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
