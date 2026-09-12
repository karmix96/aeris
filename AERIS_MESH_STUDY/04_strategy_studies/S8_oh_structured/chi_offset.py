"""What changes when the freestream turbulence goes to NASA's standard?

Every S8 run so far used ADflow's default eddy-viscosity ratio, 0.009, which the
solver turns into SA's chi ~1.3. The TMR prescribes chi = 3 to 5, high enough
that the model's ft2 term cannot quietly hold part of the boundary layer
laminar. `queue6.sh` re-runs the campaign at chi = 3 into a separate tree; this
compares each new run against its own predecessor, same grid, same incidence.

    python chi_offset.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
CHI3 = STUDY / "artifacts/s8_chi3"
BASE = STUDY / "artifacts/s8_pilot"
KEYS = ("cl", "cd", "cdp", "cdv")


def forces(path: Path) -> dict | None:
    result = path / "result.json"
    if not result.exists():
        return None
    data = json.loads(result.read_text())
    if not data.get("converged"):
        return None
    return {k.split("_")[-1]: float(v) for k, v in data["functions"].items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=STUDY /
                    "05_s6_cfd_qualification/reports/s8_freestream_turbulence.json")
    args = ap.parse_args()

    pairs = []
    for run in sorted(CHI3.glob("g*/gci_*_a*")):
        new = forces(run)
        old = forces(BASE / run.parent.name / run.name)
        if not (new and old):
            continue
        index = int(run.parent.name[1:])
        level, _, alpha = run.name.partition("_a")
        pairs.append({"geometry": index, "level": level, "alpha_deg": float(alpha),
                      "default_chi": {k: old[k] for k in KEYS},
                      "chi_3": {k: new[k] for k in KEYS},
                      "percent_change": {k: 100 * (new[k] - old[k]) / old[k]
                                         if old[k] else None for k in KEYS}})
    if not pairs:
        print("no matched pairs yet")
        return 0

    print(f"{'geom':>5}{'level':>8}{'alpha':>7}" + "".join(f"{k.upper():>10}" for k in KEYS))
    for p in pairs:
        print(f"{p['geometry']:>5}{p['level']:>8}{p['alpha_deg']:>7.0f}"
              + "".join(f"{p['percent_change'][k]:>9.2f}%" for k in KEYS))

    summary = {}
    for k in KEYS:
        v = np.array([p["percent_change"][k] for p in pairs if p["percent_change"][k] is not None])
        summary[k] = {"mean_percent": float(v.mean()), "min": float(v.min()),
                      "max": float(v.max()), "std": float(v.std(ddof=1)) if v.size > 1 else 0.0}
    report = {"schema": "aeris.s8.freestream_turbulence.v1",
              "change": "eddyVisInfRatio 0.009 (SA chi ~1.3) -> 0.21 (chi 3, the TMR's prescription)",
              "pairs": pairs, "summary_percent_change": summary,
              "reading": ("a constant offset can be carried as a correction; a spread that "
                          "grows with grid or incidence cannot, and would force the whole "
                          "campaign to be re-run rather than corrected")}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print("\n  mean change: " + ", ".join(
        f"{k.upper()} {summary[k]['mean_percent']:+.2f}% (spread {summary[k]['min']:+.2f} to "
        f"{summary[k]['max']:+.2f})" for k in KEYS))
    print(f"  {len(pairs)} pairs; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
