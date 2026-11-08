"""The Greek tactical UAV programmes against the Re levels (owner, 8 Nov 2026).

    python scripts/greek_uavs.py      # seconds: writes docs/greek_uavs.json and docs/greek_uavs.png

Reads configs/greek_uavs.yaml (sourced values, conflicts and the assumptions each Re needs), docs/real_uavs.json (the
real Class I-II wings with a published area: their Re range) and the Stage 0 Re levels. The method is the one of
real_uavs.yaml: mean chord = area / full span; Re low = cruise at 3,048 m; Re high = top speed at sea level; ISA with
Sutherland's viscosity (checked against the Stage 0 air values). No wing area is published for the Greek aircraft, so
every Re here rests on an assumed aspect ratio (8, the AUTh RX-3's) or, for the Patroller, on the Stemme S15 wing.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
import yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))          # CFD_Automation: the cfdauto package
from cfdauto.paths import STAGE0, re_levels  # noqa: E402

DOCS = ROOT / "docs"
OLD_LEVELS = (1.0e5, 3.0e5, 1.5e6, 3.0e6)     # the levels until 8 Nov 2026
FT = 0.3048
INK, MUTED, LINE, GREY = "#142230", "#566573", "#D6DEE6", "#9AA6B2"
TAILLESS, CONVENTIONAL, LEVEL, SHADE = "#2E8B57", "#0C5EA8", "#9A6200", "#F4EFE6"


def isa(h: float) -> tuple[float, float]:
    """rho / mu [s/m2] and the speed of sound [m/s] at altitude h [m] (ISA troposphere, Sutherland)."""
    t = 288.15 - 0.0065 * h
    p = 101325.0 * (t / 288.15) ** 5.25588
    rho = p / (287.053 * t)
    mu = 1.458e-6 * t ** 1.5 / (t + 110.4)
    return rho / mu, math.sqrt(1.4 * 287.053 * t)


def check_air() -> dict:
    """Our ISA against the Stage 0 air values (values.yaml is rounded to 3 digits)."""
    d = yaml.safe_load((STAGE0 / "values.yaml").read_text())
    out = {}
    for k, h in (("sea_level", 0.0), ("1524_m", 1524.0), ("3048_m", 3048.0)):
        ours = isa(h)[0]
        out[k] = round(ours)
    out["note"] = "Stage 0: 68,500 / 60,600 / 53,500 s/m2 (rounded); here unrounded"
    return out


def span_list(v) -> list[float]:
    return [] if v is None else ([float(v)] if not isinstance(v, list) else [float(x) for x in v])


def one(a: dict, top_level: float) -> dict | None:
    asm = a.get("assumed") or {}
    cruise = a.get("cruise_kmh") or asm.get("cruise_kmh")
    tops = span_list(a.get("top_kmh") or asm.get("top_kmh"))
    if not cruise or not tops:
        return None
    b = float(a["span_m"])
    area = a.get("area_m2") or asm.get("area_m2")
    ar = a.get("ar") or asm.get("ar")
    c = float(area) / b if area else b / float(ar)
    rm3, _ = isa(3048.0)
    rm0, a0 = isa(0.0)
    v_c = cruise / 3.6
    re_lo = rm3 * v_c * c
    re_hi = [rm0 * (v / 3.6) * c for v in tops]
    mach = [(v / 3.6) / a0 for v in tops]
    pg = [(1 / math.sqrt(1 - m * m)) / (1 / math.sqrt(1 - 0.01)) - 1 for m in mach]
    r = {"name": a["name"], "family": a.get("family"), "span_m": b, "mean_chord_m": round(c, 4),
         "chord_from": f"area {area} m2 (assumed: {'area_m2' in asm})" if area else f"AR {ar} (assumed: {'ar' in asm})",
         "cruise_kmh": cruise, "cruise_assumed": "cruise_kmh" in asm, "top_kmh": tops, "top_assumed": "top_kmh" in asm,
         "re_cruise_3048m": re_lo, "re_top_sea_level": re_hi, "mach_top": mach, "pg_from_mach_0p1_pct": [100 * x for x in pg],
         "inside_levels": max(re_hi) <= top_level * 1.0001,
         "above_top_factor": max(re_hi) / top_level}
    if a.get("plot_note"):
        r["plot_note"] = a["plot_note"]
    if a.get("ceiling_ft"):
        rmc, _ = isa(a["ceiling_ft"] * FT)
        r["re_cruise_at_ceiling"] = rmc * v_c * c
    if ar and not area:
        r["re_top_if_ar6"] = [x * float(ar) / 6.0 for x in re_hi]
    return r


def main() -> None:
    cfg = yaml.safe_load((ROOT / "configs" / "greek_uavs.yaml").read_text())
    levels = re_levels()
    top = max(levels)
    rows = [r for a in cfg["aircraft"] if (r := one(a, top))]
    real = [r for r in json.loads((DOCS / "real_uavs.json").read_text())["rows"]
            if r.get("use") == "ranges" and r.get("re_low") and r.get("re_high")]
    out = {"what": "Greek tactical UAVs against the Re levels on the mean chord (area / full span)",
           "date": "2026-11-08", "levels": list(levels), "old_levels": list(OLD_LEVELS), "air_check": check_air(),
           "method": "Re low: cruise at 3,048 m; Re high: top speed at sea level; ISA + Sutherland",
           "real_class_I_II": {"n": len(real), "re_min": min(r["re_low"] for r in real),
                               "re_max": max(r["re_high"] for r in real)},
           "rows": rows, "projects": cfg["projects"], "nato_classes": cfg["nato_classes"]}
    (DOCS / "greek_uavs.json").write_text(json.dumps(out, indent=1, default=str))
    plot(rows, real, levels, DOCS / "greek_uavs.png")
    for r in rows:
        hi = r["re_top_sea_level"]
        print(f"{r['name']:20s} c {r['mean_chord_m']:.3f} m  Re {r['re_cruise_3048m']:.2e} -> "
              f"{min(hi):.2e}{'' if len(hi) == 1 else f'-{max(hi):.2e}'}  Mach {max(r['mach_top']):.3f}  "
              + ("inside" if r["inside_levels"] else f"above the top x{r['above_top_factor']:.2f}"))
    print(f"wrote {DOCS / 'greek_uavs.json'} and greek_uavs.png")


def plot(rows: list[dict], real: list[dict], levels, path: Path) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": INK, "text.color": INK})
    rows = sorted(rows, key=lambda r: r["re_cruise_3048m"])
    n = len(rows)
    fig, ax = plt.subplots(figsize=(10.5, 0.62 * (n + 3) + 1.2), dpi=150)
    top = max(levels)
    ax.axvspan(top, 2e7, color=SHADE, zorder=0)
    ax.text(top * 1.06, n + 1.15, "above the top level:\nextrapolation", fontsize=8.5, color=LEVEL, va="center")
    lo_r, hi_r = min(r["re_low"] for r in real), max(r["re_high"] for r in real)
    ax.plot([lo_r, hi_r], [n + 1.2, n + 1.2], color=GREY, lw=7, solid_capstyle="butt", zorder=2)
    ax.text(lo_r, n + 1.75, f"{len(real)} real Class I–II wings with a published area and speeds: "
            f"{lo_r / 1e5:.2f} × 10⁵ to {hi_r / 1e6:.2f} × 10⁶", fontsize=8.5, color=MUTED)
    for i, r in enumerate(rows):
        col = TAILLESS if r["family"] == "tailless" else (CONVENTIONAL if r["family"] == "conventional" else GREY)
        hi = r["re_top_sea_level"]
        ax.plot([r["re_cruise_3048m"], min(hi)], [i, i], color=col, lw=7, solid_capstyle="butt", zorder=3)
        if len(hi) > 1:             # the top speed is a range in the sources: the lighter part
            ax.plot([min(hi), max(hi)], [i, i], color=col, lw=7, solid_capstyle="butt", zorder=3, alpha=0.4)
            ax.plot([min(hi)], [i], "D", ms=5.5, mfc="white", mec=INK, zorder=5)
        ax.plot([r["re_cruise_3048m"]], [i], "o", ms=7, color=INK, zorder=5)
        ax.plot([max(hi)], [i], "D", ms=6, color=INK, zorder=5)
        asm = []
        if "AR" in r["chord_from"] and "True" in r["chord_from"]:
            asm.append("AR 8 assumed")
        if "area" in r["chord_from"] and "True" in r["chord_from"]:
            asm.append("S15 wing assumed")
        if r["cruise_assumed"] and r["top_assumed"]:
            asm.append("speeds of the RX-3 (not published)")
        elif r["cruise_assumed"]:
            asm.append("cruise of the RX-3 (not published)")
        if r.get("plot_note"):
            asm.append(r["plot_note"])
        lab = f"{r['name']}  ({r['span_m']:g} m; Mach {max(r['mach_top']):.2f})"
        ax.text(r["re_cruise_3048m"] / 1.08, i + 0.04, lab, ha="right", va="center", fontsize=9)
        if asm:
            ax.text(r["re_cruise_3048m"] / 1.08, i - 0.34, "; ".join(asm), ha="right", va="center", fontsize=7.6,
                    color=MUTED)
    for re_ in OLD_LEVELS:
        if re_ not in levels:
            ax.axvline(re_, color=GREY, lw=1.0, ls=":", zorder=1)
    for re_ in levels:
        ax.axvline(re_, color=LEVEL, lw=1.4, ls="--", zorder=1)
        lab = {1e5: "10⁵", 3e5: "3 × 10⁵", 1e6: "10⁶", 4e6: "4 × 10⁶"}.get(re_, f"{re_:.1e}")
        ax.text(re_, -1.35, lab, color=LEVEL, fontsize=8.5, ha="center", va="top", fontweight="bold")
    ax.text(2.1e6, -2.05, "dotted: 1.5 × 10⁶ and 3 × 10⁶, the levels until 8 Nov", color=MUTED, fontsize=7.8, ha="center")
    ax.set_xscale("log")
    ax.set_xlim(2.5e4, 1.6e7)
    ax.set_ylim(-2.4, n + 2.3)
    ax.set_yticks([])
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel("Re on the mean chord (area / full span):  ● cruise at 3,048 m   ◆ top speed at sea level "
                  "(◇ the lower top speed where sources give a range)")
    ax.plot([], [], color=TAILLESS, lw=6, label="tailless (BWB)")
    ax.plot([], [], color=CONVENTIONAL, lw=6, label="conventional")
    ax.plot([], [], color=GREY, lw=6, label="family not stated")
    ax.plot([], [], color=LEVEL, lw=1.4, ls="--", label="Re levels (8 Nov)")
    ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=1, bbox_to_anchor=(0.0, 0.86))
    ax.set_title("Greek tactical UAVs against the Re levels: every cruise point is inside; LOTUS 11 m and the Patroller "
                 "\nat top speed are above 4 × 10⁶ (no wing area is published: every Re rests on an assumption)",
                 fontsize=10.5, loc="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, facecolor="white")


if __name__ == "__main__":
    main()
