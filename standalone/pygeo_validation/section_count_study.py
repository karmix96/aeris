"""Step-5 section-count convergence study: how many sections define the wing.

Builds the pyGeo loft ONCE, then extracts it at several spanwise section counts
and runs the production viscous pyGeo->AVL chain at a few alphas for each. Reports
CL / cd_ind / cd_profile / cd_total convergence vs the finest count — extending the
standalone study's 17-vs-33 point across a small alpha range.

This is the LIGHT in-session version (one design, few counts, few alphas; each AVL
case ~5 s). The full design-space sweep is a desktop runbook (see RUNBOOK.md).

Usage:
    PYTHONPATH=src .venv/bin/python -m standalone.pygeo_validation.section_count_study \
        --config configs/geometry/paper1_bwb_pygeo.yaml \
        --counts 9,13,17,25,33 --alphas 0,4,8 \
        --report-dir configs/geometry/pygeo_validation_evidence
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from aeris.aero.models import FlightCondition
from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
    build_pygeo,
    extract_sections,
    stations_from_records,
)
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import run_pygeo_avl_case
from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
from aeris.generators.bwb_segmented_v1.services import (
    build_section_geometry_from_sample,
    generate_bwb_planform_from_sample,
)
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator


def _build_loft(config_path: Path):
    raw = load_yaml_config(config_path)
    gid, g = resolve_generator_and_config(raw)
    gen = get_geometry_generator(gid)
    s = gen.sample_one(g, seed=g.generator.seed)
    pf = generate_bwb_planform_from_sample(s, g)
    sg = build_section_geometry_from_sample(pf, s, g)
    st = tuple(stations_from_records(sg.sections, _resolve_airfoil_database(g)))
    frame_mode = "asb_frame" if g.pygeo.frame_mode == "aeris_frame" else g.pygeo.frame_mode
    build = build_pygeo(st, k_span=g.pygeo.k_span, frame_mode=frame_mode,
                        n_ctl=g.pygeo.n_ctl, tip=g.pygeo.tip, tip_scale=g.pygeo.tip_scale)
    return g, build


def run_study(config_path: Path, counts: list[int], alphas: list[float],
              out_dir: Path) -> dict:
    g, build = _build_loft(config_path)
    cst_order = g.pygeo.extraction.cst_order
    chordwise = g.pygeo.extraction.chordwise_points

    # cases[count][alpha] = metrics
    cases: dict[int, dict[float, dict]] = {}
    for count in counts:
        ex = extract_sections(build, np.linspace(0.02, 0.98, count),
                              cst_order=cst_order, chordwise_points=chordwise)
        cases[count] = {}
        for a in alphas:
            fc = FlightCondition(alpha_deg=a, velocity_mps=28.0, altitude_m=0.0)
            case_dir = out_dir / f"count{count}_a{a:+.0f}"
            res = run_pygeo_avl_case(
                flight_condition=fc, output_dir=case_dir, extracted_sections=ex,
                viscous=True, name=f"sc{count}",
            )
            cases[count][a] = {
                "status": res.status.name,
                "CL": res.cl, "cd_ind": res.cd_ind,
                "cd_profile": res.cd_profile, "cd_total": res.cd_total,
            }

    ref = max(counts)
    metrics = ["CL", "cd_ind", "cd_profile", "cd_total"]
    convergence: dict[int, dict[str, float]] = {}
    for count in counts:
        worst = {m: 0.0 for m in metrics}
        for a in alphas:
            for m in metrics:
                v = cases[count][a].get(m)
                vr = cases[ref][a].get(m)
                if v is None or vr is None or vr == 0:
                    continue
                worst[m] = max(worst[m], abs(v - vr) / abs(vr))
        convergence[count] = worst

    return {
        "config": str(config_path),
        "generated_utc": datetime.now(UTC).isoformat(),
        "counts": counts, "alphas": alphas, "reference_count": ref,
        "cases": {str(c): {str(a): cases[c][a] for a in alphas} for c in counts},
        "max_rel_err_vs_reference": {str(c): convergence[c] for c in counts},
    }


def _fmt_md(d: dict) -> str:
    ref = d["reference_count"]
    L = [
        "# pyGeo section-count convergence (step 5)",
        "",
        f"- config: `{d['config']}`",
        f"- generated: {d['generated_utc']}",
        f"- counts: {d['counts']}  alphas: {d['alphas']}  reference: {ref}",
        "",
        f"## Max relative error vs {ref}-section reference (over all alphas)",
        "",
        "| count | CL | cd_ind | cd_profile | cd_total |",
        "|---|---|---|---|---|",
    ]
    for c in d["counts"]:
        e = d["max_rel_err_vs_reference"][str(c)]
        L.append(
            f"| {c} | {e['CL']*100:.3f}% | {e['cd_ind']*100:.3f}% | "
            f"{e['cd_profile']*100:.3f}% | {e['cd_total']*100:.3f}% |"
        )
    L.append("")
    L.append("## Absolute values at each (count, alpha)")
    L.append("")
    L.append("| count | alpha | CL | cd_ind | cd_profile | cd_total |")
    L.append("|---|---|---|---|---|---|")
    for c in d["counts"]:
        for a in d["alphas"]:
            m = d["cases"][str(c)][str(a)]
            def f(x):
                return f"{x:.5f}" if isinstance(x, (int, float)) else str(x)
            L.append(f"| {c} | {a:+.0f} | {f(m['CL'])} | {f(m['cd_ind'])} | "
                     f"{f(m['cd_profile'])} | {f(m['cd_total'])} |")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--counts", type=str, default="9,13,17,25,33")
    ap.add_argument("--alphas", type=str, default="0,4,8")
    ap.add_argument("--report-dir", type=Path, default=None)
    ap.add_argument("--work-dir", type=Path,
                    default=Path("data/runs/pygeo_section_count_study"))
    args = ap.parse_args()

    counts = [int(x) for x in args.counts.split(",") if x.strip()]
    alphas = [float(x) for x in args.alphas.split(",") if x.strip()]
    args.work_dir.mkdir(parents=True, exist_ok=True)

    d = run_study(args.config, counts, alphas, args.work_dir)
    md = _fmt_md(d)
    print(md)
    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        stem = args.config.stem
        (args.report_dir / f"{stem}_section_count.json").write_text(
            json.dumps(d, indent=2), encoding="utf-8")
        (args.report_dir / f"{stem}_section_count.md").write_text(md, encoding="utf-8")
        print(f"\n[written] {args.report_dir}/{stem}_section_count.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
