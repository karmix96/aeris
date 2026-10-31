"""Do the generator's size ranges cover real Class I and II wings, and at what Reynolds numbers do
those wings fly?

    python scripts/real_uav_check.py      # writes docs/real_uavs.json and docs/real_uavs.png

Reads configs/real_uavs.yaml (sourced data) and configs/wing.yaml (ranges). For every real wing
with a published wing area: mean chord = area / span, aspect ratio = span^2 / area, and
  Re low  = mean chord x cruise speed x (rho/mu at 3,048 m)
  Re high = mean chord x top speed (cruise if none) x (rho/mu at sea level)
Coverage: a real wing is covered when some generated wing of its family lies within 10 % of it
in span and in mean chord (2,000 Latin-hypercube wings per type). Wings with a span only (sourced, or
from the HCDI UAS database in the same YAML) are checked on span alone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.geometry.params import load_config  # noqa: E402
from cfdauto.geometry.planform import build_planform  # noqa: E402
from cfdauto.geometry.sample import lhs  # noqa: E402

DOCS = ROOT / "docs"
FAMILY_TYPES = {"tailless": ("bwb", "flying_wing"), "conventional": ("cranked", "tapered")}
N_SAMPLE = 2000
TOL = 0.10


def real_wings() -> tuple[dict, list[dict]]:
    d = yaml.safe_load((ROOT / "configs" / "real_uavs.yaml").read_text())
    air = d["air"]
    rows = []
    for a in d["aircraft"]:
        r = dict(a)
        if not a["area"] and a.get("ar"):          # database rows: area from the listed aspect ratio
            a = dict(a, area=a["span"] ** 2 / a["ar"])
            r["area"] = a["area"]
        if a["area"]:
            c = a["area"] / a["span"]
            r["mean_chord"] = c
            r["aspect_ratio"] = a["span"] ** 2 / a["area"]
            r["re_low"] = c * a["cruise"] * air["3048_m"] if a["cruise"] else None
            v_hi = a["max"] or a["cruise"]
            r["re_high"] = c * v_hi * air["sea_level"] if v_hi else None
        rows.append(r)
    return air, rows


def hcdi_wings() -> list[dict]:
    """Span-only rows from the HCDI UAS database (no wing areas there)."""
    d = yaml.safe_load((ROOT / "configs" / "real_uavs.yaml").read_text())
    return [dict(r) for r in d.get("hcdi_db", [])]


def span_covered(r: dict, gen: dict[str, np.ndarray]) -> bool:
    """Span inside the span range of the generated wings of its family (chord unknown)."""
    pts = np.vstack([gen[t] for t in FAMILY_TYPES[r["family"]]])
    return bool(pts[:, 0].min() * (1 - TOL) <= r["span"] <= pts[:, 0].max() * (1 + TOL))


TYPE_FAMILY = {"bwb": "tailless", "flying_wing": "tailless", "cranked": "conventional", "tapered": "conventional"}


def generated(space: str = "focus") -> dict[str, np.ndarray]:
    """Columns: full span (tip to tip), mean chord, area, aspect ratio, overall taper, root chord, tip chord."""
    cfg = load_config()
    out = {}
    for t, spec in (cfg.types if space == "focus" else cfg.full).items():
        pts = []
        for v in lhs(spec, N_SAMPLE, 7):
            pf = build_planform(spec, v)
            span, area = 2 * pf.semi_span, pf.area()
            pts.append((span, area / span, area, span ** 2 / area, pf.chord[-1] / pf.chord[0], pf.chord[0], pf.chord[-1]))
        out[t] = np.array(pts)
    return out


def reynolds_by_type(rows: list[dict], gen: dict[str, np.ndarray], air: dict) -> dict:
    """Re range each type reaches over the speed range of the real wings of its family:
    lowest = smallest chord x lowest cruise at 3,048 m; highest = largest chord x highest top speed at sea level."""
    out = {}
    for t, g in gen.items():
        fam = [r for r in rows if r["family"] == TYPE_FAMILY[t] and r["use"] in ("ranges", "span")]
        v_lo = min(r["cruise"] for r in fam if r.get("cruise"))
        v_hi = max((r["max"] or r["cruise"]) for r in fam if (r.get("max") or r.get("cruise")))
        lo, hi = air["3048_m"] * v_lo, air["sea_level"] * v_hi
        out[t] = {"speed_m_s": [v_lo, v_hi],
                  "mean_chord": [float(g[:, 1].min() * lo), float(g[:, 1].max() * hi)],
                  "tip": [float(g[:, 6].min() * lo), float(g[:, 6].max() * hi)],
                  "root_max": float(g[:, 5].max() * hi),
                  "mach_max": v_hi / 340.3}
    return out


def covered(r: dict, gen: dict[str, np.ndarray]) -> bool:
    """Some generated wing of the family within 10 % in full span and in mean chord."""
    pts = np.vstack([gen[t] for t in FAMILY_TYPES[r["family"]]])
    ok = (np.abs(pts[:, 0] / r["span"] - 1) <= TOL) & (np.abs(pts[:, 1] / r["mean_chord"] - 1) <= TOL)
    return bool(ok.any())


def plot(rows: list[dict], gen: dict[str, np.ndarray], path: Path, db: list[dict] = ()) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=110)
    style = {"bwb": "#2E8B57", "flying_wing": "#9A6200", "cranked": "#0C5EA8", "tapered": "#6A9FD8"}
    for ax, (fam, types) in zip(axes, FAMILY_TYPES.items()):
        for t in types:
            ax.scatter(gen[t][:, 0], gen[t][:, 1], s=4, alpha=0.25, color=style[t], label=f"generated: {t}")
        for r in rows:
            if r["family"] != fam:
                continue
            if r.get("mean_chord") and r["use"] == "ranges":
                ax.scatter(r["span"], r["mean_chord"], s=60, color="#B02A20", zorder=3, edgecolor="white")
                ax.annotate(r["name"], (r["span"], r["mean_chord"]), fontsize=7.5, xytext=(4, 4),
                            textcoords="offset points")
            elif r["use"] == "span":       # span only: a tick on the span axis (chord unknown)
                ax.plot([r["span"]] * 2, [0, 0.035], color="#9A6200", lw=1.4, zorder=2,
                        transform=ax.get_xaxis_transform())
        for r in db:
            if r["family"] == fam and r["use"] == "span":
                ax.plot([r["span"]] * 2, [0.04, 0.075], color="#6A4BB0", lw=1.4, zorder=2,
                        transform=ax.get_xaxis_transform())
        ax.set_title({"tailless": "Tailless vs the bwb and flying-wing types",
                      "conventional": "Wing + tail vs the conventional and tapered types"}[fam], fontsize=10)
        ax.set_xlabel("full span [m]")
        ax.set_ylabel("mean chord = area / span [m]")
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7.5, loc="upper left", markerscale=3)
    fig.text(0.01, 0.01, "Red dots: real wings with a published wing area or aspect ratio. Ticks on the span axis: span only "
             "(brown: sources and the NTNU / CNAS databases; violet: HCDI UAS database); chord unknown.", fontsize=8, color="#566573")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def fmt_re(x) -> str:
    return "   n/a  " if x is None else f"{x:.2e}"


def main() -> None:
    air, rows = real_wings()
    db = hcdi_wings()
    gen = generated("focus")
    gen_full = generated("full")
    for r in rows:
        if r.get("mean_chord") and r["use"] == "ranges":
            r["covered"] = covered(r, gen)                  # by the focus space (span cap)
            r["covered_full"] = covered(r, gen_full)        # by the full space
        if r["use"] in ("ranges", "span"):
            r["span_covered"] = span_covered(r, gen)
            r["span_covered_full"] = span_covered(r, gen_full)
    for r in db:
        if r["use"] == "span":
            r["span_covered"] = span_covered(r, gen)
            r["span_covered_full"] = span_covered(r, gen_full)
    spans = [r for r in rows + db if "span_covered" in r]
    outside = sorted({(r.get("name") or r.get("model"), r["family"], r["class"], r["span"])
                      for r in spans if not r["span_covered"]}, key=lambda x: (x[1], x[3]))
    outside_full = [r.get("name") or r.get("model") for r in spans if not r["span_covered_full"]]
    used = [r for r in rows if r["use"] == "ranges"]
    names = ("span_m", "mean_chord_m", "area_m2", "aspect_ratio", "taper", "root_chord_m", "tip_chord_m")
    envelope = {t: {n: [float(g[:, k].min()), float(g[:, k].max())] for k, n in enumerate(names)}
                for t, g in gen.items()}
    summary = {
        "re_low_min": min(r["re_low"] for r in used if r.get("re_low")),
        "re_high_max": max(r["re_high"] for r in used if r.get("re_high")),
        "all_covered": all(r["covered_full"] for r in used),
        "focus_covered": sum(r["covered"] for r in used),
        "not_in_focus": [r["name"] for r in used if not r["covered"]],
        "n_ranges": len(used),
        "reynolds": reynolds_by_type(rows, gen, air),
        "spans_checked": len(spans),
        "spans_outside": [{"name": n, "family": f, "class": c, "span": s} for n, f, c, s in outside],
        "spans_outside_full": outside_full,
        "envelope": envelope,
    }
    (DOCS / "real_uavs.json").write_text(json.dumps({"air": air, "summary": summary, "rows": rows, "hcdi_db": db},
                                                    indent=1))
    plot(rows, gen, DOCS / "real_uavs.png", db)
    for r in used:
        print(f"{r['name'][:30]:30s} span {r['span']:5.2f}  c {r['mean_chord']:.3f}  AR {r['aspect_ratio']:4.1f}  "
              f"Re {fmt_re(r.get('re_low'))} - {fmt_re(r.get('re_high'))}  focus {r['covered']}  full {r['covered_full']}")
    for t, e in envelope.items():
        print(f"{t:13s} span {e['span_m'][0]:.2f}-{e['span_m'][1]:.2f} m, mean chord "
              f"{e['mean_chord_m'][0]:.3f}-{e['mean_chord_m'][1]:.3f} m")
    print(f"Re of real wings: {summary['re_low_min']:.2e} to {summary['re_high_max']:.2e}; "
          f"all covered by the full space: {summary['all_covered']}; by the focus space: "
          f"{summary['focus_covered']} of {len(used)} (not: {', '.join(summary['not_in_focus'])})")
    print(f"spans checked {len(spans)}; outside the full space: {outside_full}; outside the focus space:")
    for n, f, c, s in outside:
        print(f"   {f:8s} class {c:3s} {s:6.2f} m  {n}")


if __name__ == "__main__":
    main()
