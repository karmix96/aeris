"""pyGeo vs AeroSandbox geometry comparison over a DoE (tasks 1 + 2).

For N sampled designs, realizes BOTH backends and compares the common geometric
metrics, quantifying how the two tools differ across the design space. Geometry
only (no CAD/mesh/exports) — light enough to run in-session.

Usage:
    PYTHONPATH=src .venv/bin/python -m standalone.pygeo_asb_comparison.compare \
        --config configs/geometry/bwb.yaml --n 20 --base-seed 5000 \
        --report-dir configs/geometry/pygeo_asb_comparison_evidence
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from standalone.pygeo_asb_comparison.build import build_both
from standalone.pygeo_asb_comparison.metrics import (
    COMMON_METRIC_KEYS,
    asb_metrics,
    pygeo_metrics,
    relative_diff,
)


def run_comparison(config_path: Path, n: int, base_seed: int, n_sections: int) -> dict:
    rows = []
    failures = []
    for i in range(n):
        seed = base_seed + i
        try:
            both = build_both(config_path, seed=seed, n_sections=n_sections)
            pm = pygeo_metrics(both.extracted)
            am = asb_metrics(both.asb_result)
            rd = relative_diff(pm, am)
            rows.append({"seed": seed, "pygeo": pm, "asb": am, "rel_diff": rd})
        except Exception as exc:  # a realization failure is a robustness result
            failures.append({"seed": seed, "error": f"{type(exc).__name__}: {exc}"})

    # Aggregate |rel_diff| per metric across the DoE.
    agg = {}
    for k in COMMON_METRIC_KEYS:
        vals = [abs(r["rel_diff"][k]) for r in rows if np.isfinite(r["rel_diff"][k])]
        if vals:
            agg[k] = {
                "mean_pct": float(np.mean(vals) * 100),
                "p95_pct": float(np.percentile(vals, 95) * 100),
                "max_pct": float(np.max(vals) * 100),
            }
        else:
            agg[k] = {"mean_pct": float("nan"), "p95_pct": float("nan"),
                      "max_pct": float("nan")}

    return {
        "config": str(config_path),
        "generated_utc": datetime.now(UTC).isoformat(),
        "n_requested": n,
        "n_built": len(rows),
        "n_failed": len(failures),
        "base_seed": base_seed,
        "n_sections": n_sections,
        "aggregate_abs_rel_diff": agg,
        "cases": rows,
        "failures": failures,
    }


def _fmt_md(d: dict) -> str:
    L = [
        "# pyGeo vs AeroSandbox geometry comparison",
        "",
        f"- config: `{d['config']}`",
        f"- generated: {d['generated_utc']}",
        f"- samples: {d['n_built']}/{d['n_requested']} built, {d['n_failed']} failed "
        f"(seeds {d['base_seed']}..{d['base_seed'] + d['n_requested'] - 1})",
        "",
        "Both backends realize the SAME sampled design, so these are tool-realization "
        "differences (smooth pyGeo B-spline loft vs AeroSandbox piecewise), not "
        "different designs.",
        "",
        "## |pyGeo − ASB| / ASB across the DoE",
        "",
        "| metric | mean | p95 | max |",
        "|---|---|---|---|",
    ]
    for k in COMMON_METRIC_KEYS:
        a = d["aggregate_abs_rel_diff"][k]
        L.append(f"| {k} | {a['mean_pct']:.3f}% | {a['p95_pct']:.3f}% | {a['max_pct']:.3f}% |")
    L.append("")
    if d["failures"]:
        L.append("## Failures")
        L.append("")
        for f in d["failures"]:
            L.append(f"- seed {f['seed']}: {f['error']}")
        L.append("")
    # A couple of representative absolute rows for sanity.
    L.append("## Sample absolute values (first 3 seeds)")
    L.append("")
    L.append("| seed | metric | pyGeo | ASB | rel Δ |")
    L.append("|---|---|---|---|---|")
    for r in d["cases"][:3]:
        for k in ("span_m", "planform_area_m2", "aspect_ratio", "volume_m3", "taper_ratio"):
            L.append(f"| {r['seed']} | {k} | {r['pygeo'][k]:.4f} | {r['asb'][k]:.4f} "
                     f"| {r['rel_diff'][k]*100:+.2f}% |")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--base-seed", type=int, default=5000)
    ap.add_argument("--n-sections", type=int, default=25)
    ap.add_argument("--report-dir", type=Path, default=None)
    args = ap.parse_args()

    d = run_comparison(args.config, args.n, args.base_seed, args.n_sections)
    md = _fmt_md(d)
    print(md)
    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        stem = args.config.stem
        (args.report_dir / f"{stem}_pygeo_vs_asb.json").write_text(
            json.dumps(d, indent=2), encoding="utf-8")
        (args.report_dir / f"{stem}_pygeo_vs_asb.md").write_text(md, encoding="utf-8")
        print(f"\n[written] {args.report_dir}/{stem}_pygeo_vs_asb.{{json,md}}")
    return 0 if d["n_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
