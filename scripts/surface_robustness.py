#!/usr/bin/env python3
"""Run ONE surface recipe across N sampled geometries and report robustness.

The surface study that produced the selected recipe was run entirely on a
single fixed wing, so nothing in it is known to generalise.  Surface
generation costs ~1 s, so the whole design space can be screened for the
price of one volume march -- and the answer decides whether the remaining
tip-cap defect is worth a structural fix or is a non-issue in practice.

Usage:
    python scripts/surface_robustness.py [--n 50] [--config CONFIG] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

# The recipe selected by the 2026-07-22 surface study (SURFACE_MESH_LAWS.md).
SELECTED_RECIPE = {
    "points_per_side": 49,
    "spanwise_panels": 16,
    "spanwise_allocation": "proportional",
    "cap_wrap_points": 17,
    "cap_wrap_x": 0.15,
    "tip_radial_points": 9,
    "tip_smooth_iters": 20,
    "te_thickness": 0.005,
}
TOPOLOGY_ID = "wing_cap4_v1"


def _group_metrics(blocks: list[dict], prefix: str) -> dict[str, float]:
    members = [b for b in blocks if str(b.get("name", "")).startswith(prefix)]
    if not members:
        return {}
    return {
        "min_jacobian": min(float(b["min_scaled_corner_jacobian"]) for b in members),
        "max_skewness": max(float(b["max_equiangle_skewness"]) for b in members),
        "max_aspect_ratio": max(float(b["max_aspect_ratio"]) for b in members),
        "max_growth_ratio": max(float(b["max_growth_ratio"]) for b in members),
        "max_normal_angle_deg": max(float(b["max_adjacent_normal_angle_deg"]) for b in members),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--config", default="configs/geometry/bwb_explore_wide.yaml")
    parser.add_argument("--out", default="data/cfd_cases/surface_robustness")
    args = parser.parse_args()

    from aeris.cfd.meshing.registry import get_topology
    from aeris.commands.mesh import _build_wing
    from aeris.mesh.surface import MeshBuildError

    generator = get_topology(TOPOLOGY_ID)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = Path(args.config)

    rows: list[dict] = []
    for index in range(args.n):
        seed = args.seed_start + index
        sample_dir = out_dir / f"seed_{seed:05d}"
        row: dict[str, object] = {"seed": seed}
        started = time.perf_counter()
        try:
            wing, _airplane, _gen = _build_wing(
                config_path,
                wing_index=0,
                geometry_output_dir=sample_dir / "geometry",
                seed_override=seed,
                save_plot=False,
            )
        except Exception as exc:  # noqa: BLE001 - must classify, not crash
            row.update(status="geometry_failed", error=f"{type(exc).__name__}: {exc}")
            rows.append(row)
            print(f"  seed {seed:5d}  geometry_failed")
            continue

        try:
            generator.generate(wing, sample_dir / "surface", dict(SELECTED_RECIPE))
            row["status"] = "ok"
        except (MeshBuildError, ValueError) as exc:
            row["status"] = "surface_failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["seconds"] = time.perf_counter() - started

        report_path = sample_dir / "surface" / "surface_report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            blocks = report.get("blocks") or []
            row["oml"] = _group_metrics(blocks, "oml")
            row["tip"] = _group_metrics(blocks, "tip")
            row["total_cells"] = report.get("global", {}).get("total_cells")
            row["free_edges_off_root"] = report.get("free_edges", {}).get("off_root_free_edges")
            row["failure_reasons"] = [
                r.get("check") for r in (report.get("failure_reasons") or [])
            ]
        rows.append(row)
        tip = row.get("tip") or {}
        print(
            f"  seed {seed:5d}  {row['status']:<15}"
            f" oml_jac={(row.get('oml') or {}).get('min_jacobian', float('nan')):.3f}"
            f" tip_skew={tip.get('max_skewness', float('nan')):.3f}"
            f" tip_jac={tip.get('min_jacobian', float('nan')):.4f}"
        )

    ok = [r for r in rows if r["status"] == "ok"]
    failures: dict[str, int] = {}
    for r in rows:
        if r["status"] != "ok":
            failures[r["status"]] = failures.get(r["status"], 0) + 1
        for reason in r.get("failure_reasons") or []:
            failures[f"qc:{reason}"] = failures.get(f"qc:{reason}", 0) + 1

    def spread(group: str, key: str) -> dict[str, float]:
        values = [float((r.get(group) or {})[key]) for r in ok if (r.get(group) or {}).get(key) is not None]
        if not values:
            return {}
        arr = np.array(values)
        return {
            "min": float(arr.min()),
            "p10": float(np.percentile(arr, 10)),
            "median": float(np.median(arr)),
            "p90": float(np.percentile(arr, 90)),
            "max": float(arr.max()),
        }

    summary = {
        "schema": "aeris.cfd.surface_robustness.v1",
        "config": str(config_path),
        "recipe": SELECTED_RECIPE,
        "topology": TOPOLOGY_ID,
        "n_samples": len(rows),
        "n_ok": len(ok),
        "success_rate_percent": 100.0 * len(ok) / len(rows) if rows else 0.0,
        "failures": failures,
        "spread": {
            group: {key: spread(group, key) for key in
                    ("min_jacobian", "max_skewness", "max_aspect_ratio",
                     "max_growth_ratio", "max_normal_angle_deg")}
            for group in ("oml", "tip")
        },
        "rows": rows,
    }
    report_path = out_dir / "surface_robustness_report.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"\nsuccess: {len(ok)}/{len(rows)} ({summary['success_rate_percent']:.1f}%)")
    if failures:
        print(f"failures: {failures}")
    for group in ("oml", "tip"):
        print(f"\n{group.upper()} metric spread over the {len(ok)} successes:")
        print(f"  {'metric':<22}{'min':>9}{'p10':>9}{'median':>9}{'p90':>9}{'max':>9}")
        for key, stats in summary["spread"][group].items():
            if stats:
                print(
                    f"  {key:<22}{stats['min']:>9.3f}{stats['p10']:>9.3f}"
                    f"{stats['median']:>9.3f}{stats['p90']:>9.3f}{stats['max']:>9.3f}"
                )
    print(f"\nreport: {report_path}")


if __name__ == "__main__":
    main()
