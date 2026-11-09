"""V2 and V3 on the 20 reference wings at VC, 4 Re (80 meshes): the summary, two figures.

    python scripts/screen.py --sets reference --types bwb flying_wing --re 1e5 3e5 1e6 4e6 --tag ref_VC_a
    python scripts/screen.py --sets reference --types cranked tapered --re 1e5 3e5 1e6 4e6 --tag ref_VC_b
    python scripts/v23_study.py        # -> data/studies/v23.json, docs/page/v2_wall.png, docs/page/v3_tip.png

V2: wall layers, fine zone, far field; the in-plane angle at the nose and off the base; the cells at the base.
V3: the cap and the outboard blocks; the tip-vortex path; quality by part.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import style as S                                          # noqa: E402

STUDIES = HERE / "data" / "studies"
PAGE = HERE / "docs" / "page"


def load(tags=("ref_VC_a", "ref_VC_b")) -> list[dict]:
    return [json.loads(l) for t in tags for l in (STUDIES / f"screen_{t}.jsonl").read_text().splitlines()]


def dist(v) -> dict:
    v = np.asarray([x for x in v if x is not None], float)
    return {"n": int(v.size), "min": float(v.min()), "median": float(np.median(v)), "p95": float(np.percentile(v, 95)),
            "max": float(v.max())}


def summary(rows: list[dict]) -> dict:
    out = {"meshes": len(rows), "outcomes": dict(Counter(r["outcome"] for r in rows)),
           "outcomes_by_type": {t: dict(Counter(r["outcome"] for r in rows if r["type"] == t)) for t in S.TYPES},
           "review": dict(Counter(tuple(r.get("review") or []) for r in rows).most_common()),
           "rungs": dict(Counter(r["rung"] for r in rows))}
    out["review"] = {str(k): v for k, v in out["review"].items()}
    checks = {}
    for name in rows[0]["checks"]:
        v = [r["checks"][name]["value"] for r in rows]
        checks[name] = {"limit": rows[0]["checks"][name]["limit"], "passed": sum(r["checks"][name]["passed"] for r in rows)} | dist(v)
    out["checks"] = checks
    g = lambda k: [r[k] for r in rows]
    out["v2"] = {
        "cells": dist(g("cells")), "ram_gib": dist(g("ram_gib")),
        "cells_by_re": {S.RE_NAME[re]: dist([r["cells"] for r in rows if r["re"] == re]) for re in S.RES},
        "fits_16GB": sum(r["fits"]["desktop_16GB"] for r in rows), "fits_52GB": sum(r["fits"]["desktop_52GB"] for r in rows),
        "layers": dist([r["counts"]["n_layers"] for r in rows]), "wake_nodes": dist([r["counts"]["n_wake"] for r in rows]),
        "stations": dist([r["counts"]["n_span"] for r in rows]), "outboard_stations": dist([r["counts"]["n_out"] for r in rows]),
        "c_line_nodes": dist([r["counts"]["n_c"] for r in rows]),
        "bl_cells_min": dist(g("bl_cells_min")),
        "wall_angle_in_plane_deg": dist([r["checks"]["wall_orthogonality"]["value"] for r in rows]),
        "nose_angle_deg": dist(g("nose_wall_angle_deg")), "base_angle_deg": dist(g("base_wall_angle_deg")),
        "te_corner_angle_deg": dist(g("te_corner_angle_deg")),
        "wall_angle_3d_median_deg": dist([r["wall_angle_3d_deg"]["median"] for r in rows]),
        "wall_angle_3d_p95_deg": dist([r["wall_angle_3d_deg"]["p95"] for r in rows]),
        "wall_angle_3d_max_deg": dist([r["wall_angle_3d_deg"]["max"] for r in rows]),
        "base_cells_min_sj": dist(g("base_cells_min_sj")), "te_corner_cells_min_sj": dist(g("te_corner_cells_min_sj")),
        "te_jump_ratio": {S.RE_NAME[re]: dist([r["te_jump_ratio_max"] for r in rows if r["re"] == re]) for re in S.RES},
        "far_field_c": dist([r["checks"]["far_field"]["value"] for r in rows]),
        "growth_over_limit": dist([r["checks"]["growth"]["value"] for r in rows]),
        "band_cell_ratio_max": dist(g("band_cell_ratio_max")),
        "seconds_build": dist(g("seconds")),
    }
    share = [r["parts"]["outboard"] / r["cells"] for r in rows]
    vp = {}
    for d in (0.5, 1.0, 2.0):
        for al in (-5.0, 4.0, 12.0, 20.0):
            pts = [p for r in rows for p in r["vortex_path"] if p["d_c"] == d and p["alpha_deg"] == al]
            vp[f"d{d:g}c_a{al:g}"] = {"cross": dist([p["h_cross_c"] for p in pts]),
                                      "streamwise": dist([p["h_streamwise_c"] for p in pts])}
    out["v3"] = {
        "cap_min_sj": dist(g("cap_min_sj")), "outboard_min_sj": dist(g("outboard_min_sj")),
        "inboard_min_sj": dist(g("inboard_min_sj")),
        "worst_part": dict(Counter(min((("cap", r["cap_min_sj"]), ("outboard", r["outboard_min_sj"]),
                                        ("inboard", r["inboard_min_sj"])), key=lambda x: x[1])[0] for r in rows)),
        "outboard_share_of_cells": dist(share),
        "parts_cells_median": {k: float(np.median([r["parts"][k] for r in rows])) for k in ("inboard", "outboard", "cap")},
        "vortex_path": vp, "station_gap_near_tip_c": dist(g("vortex_span_gap_max_c")),
        "outboard_check": dist([r["checks"]["outboard"]["value"] for r in rows]),
    }
    return out


def figures(rows: list[dict]) -> None:
    fig, ax = S.plt.subplots(2, 3, figsize=(13.2, 7.4))
    a = ax[0, 0]
    S.strip(a, rows, lambda r: r["cells"] / 1e6, ylabel="cells (millions)", title="(a) Cells per mesh at VC")
    for v, t in ((1.2, "desktop 16 GB ≈ 1.2 M"), (5.0, "desktop + 36 GB ≈ 5.0 M")):
        a.axhline(v, color=S.MUTED, lw=0.9, ls=":")
        a.annotate(t, (0.0, v), xycoords=("axes fraction", "data"), xytext=(4, 3), textcoords="offset points",
                   fontsize=7.6, color=S.MUTED)
    a.legend(loc="upper right", frameon=False, ncol=2)
    S.strip(ax[0, 1], rows, lambda r: r["bl_cells_min"], limit=30, limit_text="limit ≥ 30",
            ylabel="cells (smallest station)", title="(b) Cells across the boundary layer")
    ax[0, 1].set_ylim(29, 34)
    S.strip(ax[0, 2], rows, lambda r: r["checks"]["wall_orthogonality"]["value"], limit=5.0, limit_text="limit ≤ 5°",
            log=True, ylabel="degrees (largest wall node)", title="(c) Wall angle in the station plane")
    S.strip(ax[1, 0], rows, lambda r: r["wall_angle_3d_deg"]["p95"], ylabel="degrees (95th percentile)",
            title="(d) 3-D angle to the surface normal (reported)")
    S.strip(ax[1, 1], rows, lambda r: min(r["base_cells_min_sj"], r["te_corner_cells_min_sj"]), limit=0.05,
            limit_text="limit ≥ 0.05", ylabel="smallest scaled Jacobian", title="(e) Cells at the base and the TE corners")
    ax[1, 1].set_ylim(0, 1.05)
    S.strip(ax[1, 2], rows, lambda r: r["te_jump_ratio_max"], log=True, ylabel="last chordwise cell / s0",
            title="(f) Spacing jump across the trailing edge")
    S.save(fig, PAGE / "v2_wall.png")

    fig, ax = S.plt.subplots(1, 3, figsize=(13.2, 3.9))
    S.strip(ax[0], rows, lambda r: r["cap_min_sj"], limit=0.05, limit_text="limit ≥ 0.05", ylabel="smallest scaled Jacobian",
            title="(a) Cap block (the worst part)")
    ax[0].set_ylim(0, 0.3)
    a = ax[1]
    for name, key, col, dx in (("across the wake (z)", "h_cross_c", "#2a78d6", -0.03), ("streamwise", "h_streamwise_c", "#eb6834", 0.03)):
        for al, mk in ((4.0, "o"),):
            med, lo, hi = [], [], []
            for d in (0.5, 1.0, 2.0):
                v = [p[key] for r in rows for p in r["vortex_path"] if p["d_c"] == d and p["alpha_deg"] == al]
                med.append(np.median(v)); lo.append(min(v)); hi.append(max(v))
            xs = np.log10([0.5, 1.0, 2.0]) + dx
            a.errorbar(xs, med, yerr=[np.array(med) - lo, np.array(hi) - med], fmt=mk + "-", color=col, ms=5, lw=1.6,
                       capsize=3, label=f"{name}, α = {al:g}°")
            a.annotate(name, (xs[-1], med[-1]), xytext=(6, 0), textcoords="offset points", fontsize=7.8, color=S.INK,
                       va="center")
    a.set_xticks(np.log10([0.5, 1.0, 2.0]), ["0.5 c", "1 c", "2 c"])
    a.set_yscale("log")
    a.set_xlim(np.log10(0.4), np.log10(4.0))
    a.set_ylabel("cell size [c] (median, min–max)")
    a.set_title("(b) Tip-vortex path: cells behind the tip TE")
    a.legend(loc="upper left", frameon=False)
    a.grid(axis="y", color=S.LINE, lw=0.5)
    S.strip(ax[2], rows, lambda r: r["parts"]["outboard"] / r["cells"] * 100, ylabel="% of the cells",
            title="(c) Share of the cells in the outboard blocks")
    S.save(fig, PAGE / "v3_tip.png")


def main() -> None:
    rows = load()
    s = summary(rows)
    (STUDIES / "v23.json").write_text(json.dumps(s, indent=1))
    figures(rows)
    print(json.dumps({k: s[k] for k in ("meshes", "outcomes", "rungs")}, indent=1))


if __name__ == "__main__":
    main()
