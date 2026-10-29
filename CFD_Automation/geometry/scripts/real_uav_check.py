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
FAMILY_TYPES = {"tailless": ("bwb",), "tailed": ("conventional", "tapered")}
N_SAMPLE = 2000
TOL = 0.10


def real_wings() -> tuple[dict, list[dict]]:
    d = yaml.safe_load((ROOT / "configs" / "real_uavs.yaml").read_text())
    air = d["air"]
    rows = []
    for a in d["aircraft"]:
        r = dict(a)
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


def generated() -> dict[str, np.ndarray]:
    cfg = load_config()
    out = {}
    for t, spec in cfg.types.items():
        pts = []
        for v in lhs(spec, N_SAMPLE, 7):
            pf = build_planform(spec, v)
            span = 2 * pf.semi_span
            pts.append((span, pf.area() / span))
        out[t] = np.array(pts)
    return out


def covered(r: dict, gen: dict[str, np.ndarray]) -> bool:
    pts = np.vstack([gen[t] for t in FAMILY_TYPES[r["family"]]])
    ok = (np.abs(pts[:, 0] / r["span"] - 1) <= TOL) & (np.abs(pts[:, 1] / r["mean_chord"] - 1) <= TOL)
    return bool(ok.any())


def plot(rows: list[dict], gen: dict[str, np.ndarray], path: Path, db: list[dict] = ()) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=110)
    style = {"bwb": "#2E8B57", "conventional": "#0C5EA8", "tapered": "#6A9FD8"}
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
            elif r["use"] == "span":
                ax.axvline(r["span"], color="#9A6200", lw=0.8, ls=":", zorder=1)
                ax.annotate(r["name"], (r["span"], ax.get_ylim()[1] if False else 0), fontsize=6.5, rotation=90,
                            xytext=(2, 4), textcoords="offset points", color="#9A6200", va="bottom")
        for r in db:
            if r["family"] == fam and r["use"] == "span":
                ax.axvline(r["span"], color="#6A4BB0", lw=0.9, ls="--", alpha=0.7, zorder=1)
                ax.annotate(r["model"], (r["span"], 0), fontsize=6.5, rotation=90, xytext=(2, 60),
                            textcoords="offset points", color="#6A4BB0", va="bottom")
        ax.set_title({"tailless": "Tailless (flying wing / BWB) vs the bwb type",
                      "tailed": "Wing + tail vs the conventional and tapered types"}[fam], fontsize=10)
        ax.set_xlabel("full span [m]")
        ax.set_ylabel("mean chord = area / span [m]")
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7.5, loc="upper left", markerscale=3)
    fig.text(0.01, 0.01, "Red dots: real wings with a published wing area. Brown dotted: sourced span only. "
             "Violet dashed: span from the HCDI UAS database. Chord unknown for both line kinds.", fontsize=8, color="#566573")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    air, rows = real_wings()
    db = hcdi_wings()
    gen = generated()
    for r in rows:
        if r.get("mean_chord") and r["use"] == "ranges":
            r["covered"] = covered(r, gen)
        if r["use"] in ("ranges", "span"):
            r["span_covered"] = span_covered(r, gen)
    for r in db:
        if r["use"] == "span":
            r["span_covered"] = span_covered(r, gen)
    spans = [r for r in rows + db if "span_covered" in r]
    outside = sorted({(r.get("name") or r.get("model"), r["family"], r["class"], r["span"])
                      for r in spans if not r["span_covered"]}, key=lambda x: (x[1], x[3]))
    used = [r for r in rows if r["use"] == "ranges"]
    envelope = {t: {"span_m": [float(g[:, 0].min()), float(g[:, 0].max())],
                    "mean_chord_m": [float(g[:, 1].min()), float(g[:, 1].max())]} for t, g in gen.items()}
    summary = {
        "re_low_min": min(r["re_low"] for r in used if r.get("re_low")),
        "re_high_max": max(r["re_high"] for r in used if r.get("re_high")),
        "all_covered": all(r["covered"] for r in used),
        "spans_checked": len(spans),
        "spans_outside": [{"name": n, "family": f, "class": c, "span": s} for n, f, c, s in outside],
        "envelope": envelope,
    }
    (DOCS / "real_uavs.json").write_text(json.dumps({"air": air, "summary": summary, "rows": rows, "hcdi_db": db},
                                                    indent=1))
    plot(rows, gen, DOCS / "real_uavs.png", db)
    for r in used:
        print(f"{r['name'][:30]:30s} span {r['span']:5.2f}  c {r['mean_chord']:.3f}  AR {r['aspect_ratio']:4.1f}  "
              f"Re {r['re_low']:.2e} - {r['re_high']:.2e}  covered {r['covered']}")
    for t, e in envelope.items():
        print(f"{t:13s} span {e['span_m'][0]:.2f}-{e['span_m'][1]:.2f} m, mean chord "
              f"{e['mean_chord_m'][0]:.3f}-{e['mean_chord_m'][1]:.3f} m")
    print(f"Re of real wings: {summary['re_low_min']:.2e} to {summary['re_high_max']:.2e}; "
          f"all covered: {summary['all_covered']}")
    print(f"spans checked {len(spans)}; outside the generated span range:")
    for n, f, c, s in outside:
        print(f"   {f:8s} class {c:3s} {s:6.2f} m  {n}")


if __name__ == "__main__":
    main()
