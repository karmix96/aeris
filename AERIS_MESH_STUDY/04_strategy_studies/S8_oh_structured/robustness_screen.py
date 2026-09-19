#!/usr/bin/env python
"""Does S8 build a valid grid on every design, or only on index 83?

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/robustness_screen.py \
        --indices 0 5 10 15 20 25 30 35 40 45 50 55 60 65 70 75 80 85 90 95

S8 has been demonstrated on ONE geometry.  That is exactly the position S2 was in
before anyone measured it: excellent on one section, and then block counts of
27, 31, 37, 39 across six designs, which is what ADR-0011 section 6.1 forbids and
what ended that strategy.  S8 should pass the same gate by construction -- an
O-ring has no singularity structure to drift -- but "should by construction" is
an argument, not a measurement, and this study runs on measurements.

Meshing only.  No CFD, no CGNS: this asks whether a grid exists and is valid,
which is the question that decides whether the strategy survives at all.  Grid
convergence asks how accurate one design's numbers are, which only matters
afterwards and needs a bigger machine.

Recorded per design, all of them things that killed an earlier strategy or a
recent build:

  block count and shape          the ADR-0011 determinism gate (killed S2)
  inverted cells                 the volume hard gate
  min cell / s0                  the ADR-0010 marchability floor, about 13
  worst leading-edge turning     the number ADR-0018 exists to control
  spanwise LE spacing step       defect 15; invisible to the turning metric
  tip-cap scaled Jacobian        oh_L3 on index 83 has one cell at 0.049
  build wall time                what a 100-design campaign would cost

Each design runs in its own subprocess and its own output directory, so one
geometry failing to build cannot take the screen down with it, and nothing
overwrites the index-83 mesh the CFD sweep used.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BUILD = REPO / "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py"


def screen_one(index: int, level: str, set_name: str, out_root: Path,
               python: str, timeout: int, frame_mode: str = "svd") -> dict:
    directory = out_root / f"{set_name}_{index:03d}"
    directory.mkdir(parents=True, exist_ok=True)
    started = time.time()
    proc = subprocess.run(
        [python, str(BUILD), "--level", level, "--set-name", set_name,
         "--index", str(index), "--out", str(directory), "--no-plot3d",
         "--frame-mode", frame_mode],
        capture_output=True, text=True, timeout=timeout, cwd=REPO,
    )
    elapsed = time.time() - started
    record: dict = {"index": index, "level": level, "wall_time_s": round(elapsed, 1),
                    "returncode": proc.returncode}
    summary = directory / f"{level}_summary.json"
    if proc.returncode != 0 or not summary.exists():
        record["built"] = False
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        record["error"] = tail[-1][:300] if tail else "no output"
        return record

    data = json.loads(summary.read_text())
    surface = data.get("surface", {})
    stations = surface.get("stations", [])
    smoothing = surface.get("le_spacing_smoothing", {})
    record.update({
        "built": True,
        "cells": data.get("cells"),
        "blocks": sorted(data.get("blocks", {})),
        "block_shapes": {k: v.get("shape") for k, v in data.get("blocks", {}).items()},
        "negative_cells": data.get("negative_cells_all_blocks"),
        "min_cell_volume_m3": data.get("min_cell_volume_all_blocks_m3"),
        "min_cell_over_s0": surface.get("min_cell_over_s0"),
        "worst_le_turn_per_cell_deg": surface.get("worst_le_turn_per_cell_deg"),
        "target_le_turn_deg": surface.get("target_le_turn_deg"),
        "all_stations_met_target": surface.get("all_stations_met_target"),
        "le_spacing_step_before": smoothing.get("worst_step_before"),
        "le_spacing_step_after": smoothing.get("worst_step_after"),
        "le_stations_clamped": smoothing.get("stations_clamped"),
        "n_stations": len(stations),
        "wall_orthogonality_median_deg": data.get("wall_orthogonality_median_deg"),
        "outboard_span_growth": data.get("outboard", {}).get("span_growth_ratio"),
    })
    return record


def signature(record: dict, wing_only: bool = True) -> str:
    """The connectivity signature ADR-0011 section 6.1 requires to be constant.

    `wing_only` because the gate is about TOPOLOGY and the outboard blocks are
    not topology.  `o_out` and `cap_out` take their spanwise count from a
    growth-ratio law marching to the far field, so it lands on 47, 48 or 49
    depending on the geometry's root chord -- which is a sizing consequence, not
    a different mesh structure.  Counting it made the gate report FAILS on a run
    where `o_wing` was (93, 65, 49) on all 100 designs, which is exactly what the
    gate exists to check.  Both are reported.
    """
    if not record.get("built"):
        return "FAILED"
    shapes = record.get("block_shapes") or {}
    if wing_only:
        return f"o_wing{tuple(shapes.get('o_wing', ()))}"
    return "|".join(f"{k}{tuple(v)}" for k, v in sorted(shapes.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indices", type=int, nargs="+",
                    default=list(range(0, 100, 5)))
    ap.add_argument("--level", default="oh_L3")
    ap.add_argument("--set-name", default="lhs100_seed42")
    ap.add_argument("--out-root", type=Path,
                    default=HERE / "runs/s8_robustness")
    ap.add_argument("--python", default=str(REPO / ".venv/bin/python"))
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--frame-mode", default="span_normal",
                    choices=("svd", "span_normal"))
    ap.add_argument("--report", type=Path,
                    default=HERE / "reports"
                                   "/s8_robustness_screen.json")
    args = ap.parse_args()
    args.out_root.mkdir(parents=True, exist_ok=True)

    print(f"S8 robustness screen: {len(args.indices)} designs at {args.level}, "
          f"meshing only\n")
    print(f"{'idx':>4}{'built':>7}{'cells':>10}{'neg':>5}{'minc/s0':>9}"
          f"{'LEturn':>8}{'met':>5}{'step':>7}{'clamp':>7}{'time s':>8}")
    records = []
    for index in args.indices:
        try:
            record = screen_one(index, args.level, args.set_name,
                                args.out_root, args.python, args.timeout,
                                args.frame_mode)
        except subprocess.TimeoutExpired:
            record = {"index": index, "built": False, "error": "TIMEOUT",
                      "wall_time_s": args.timeout}
        records.append(record)
        if record.get("built"):
            print(f"{index:>4}{'yes':>7}{record['cells']:>10,}"
                  f"{record['negative_cells']:>5}{record['min_cell_over_s0']:>9.2f}"
                  f"{record['worst_le_turn_per_cell_deg']:>8.3f}"
                  f"{'y' if record['all_stations_met_target'] else 'N':>5}"
                  f"{record['le_spacing_step_before']:>7.2f}"
                  f"{record['le_stations_clamped']:>7}{record['wall_time_s']:>8.0f}")
        else:
            print(f"{index:>4}{'NO':>7}   {record.get('error','')[:60]}")
        args.report.write_text(json.dumps(
            {"set_name": args.set_name, "level": args.level,
             "records": records}, indent=2) + "\n")

    built = [r for r in records if r.get("built")]
    signatures = {signature(r) for r in built}
    all_signatures = {signature(r, wing_only=False) for r in built}
    print(f"\n{'-'*72}")
    print(f"built            : {len(built)} / {len(records)}")
    print(f"zero inverted    : {sum(1 for r in built if r['negative_cells'] == 0)} / {len(built)}")
    print(f"turn target met  : {sum(1 for r in built if r['all_stations_met_target'])} / {len(built)}")
    print(f"o_wing signatures: {len(signatures)}  "
          f"-> ADR-0011 6.1 determinism gate "
          f"{'PASSES' if len(signatures) == 1 else 'FAILS'}")
    for s in sorted(signatures):
        print(f"    {s}")
    if len(all_signatures) != 1:
        print(f"  (outboard blocks take {len(all_signatures)} shapes; their spanwise "
              f"count follows a far-field growth law, not the topology)")
    if built:
        floors = [r["min_cell_over_s0"] for r in built]
        turns = [r["worst_le_turn_per_cell_deg"] for r in built]
        steps = [r["le_spacing_step_before"] for r in built]
        print(f"min cell / s0    : {min(floors):.2f} to {max(floors):.2f}  "
              f"(ADR-0010 marchability floor is about 13)")
        print(f"worst LE turning : {min(turns):.3f} to {max(turns):.3f} deg  "
              f"(target {built[0]['target_le_turn_deg']})")
        print(f"LE spanwise step : {min(steps):.2f} to {max(steps):.2f} before smoothing")
        print(f"total wall time  : {sum(r['wall_time_s'] for r in records)/60:.1f} min")
    print(f"\nwrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
