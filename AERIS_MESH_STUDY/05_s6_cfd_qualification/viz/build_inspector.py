#!/usr/bin/env python
"""Build a self-contained interactive inspector for the S6 leading-edge wrap.

Writes one HTML file with the mesh geometry embedded. No server, no network, no
plotting library: open it in any browser on any machine.

    python build_inspector.py --out leading_edge_inspector.html

The leading-edge defect is invisible in every integrated quantity, so the page
draws the wrap cells directly against the exact aerofoil and measures the gap.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
STUDIES = HERE.parents[2] / "04_strategy_studies"
for path in (str(STUDIES), str(STUDIES / "S6_bounded_mesh_atlas"), str(HERE.parents[3] / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

WRAP = "oml_nose"
SECTION_BLOCKS = (
    "oml_lower_aft", "oml_lower_fore", "oml_nose",
    "oml_upper_fore", "oml_upper_aft", "oml_base",
)
DEFAULT_LEVELS = ("candidate_c01", "candidate_c02", "candidate_c03", "candidate_d03")
REFERENCE_WRAP_POINTS = 161
FIRST_CELL_UM = 4.7


def build_blocks(level: str, spec=None) -> dict[str, np.ndarray]:
    import strategy_s6

    if spec is not None:
        strategy_s6.LEVELS["_inspector_tmp"] = spec
        level = "_inspector_tmp"
    with tempfile.TemporaryDirectory() as tmp:
        blocks, _info, _case = strategy_s6.build_locked_surface(
            "lhs100_seed42", 83, Path(tmp), level=level
        )
    return {b.name: np.asarray(b.xyz, dtype=float) for b in blocks}


def total_turning(line: np.ndarray) -> float:
    seg = np.diff(line, axis=0)
    length = np.linalg.norm(seg, axis=1)
    unit = seg / length[:, None]
    cosines = np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosines)).sum())


def corner_cut(line: np.ndarray) -> float:
    """Sagitta: how far the straight segments fall inside the true arc."""
    worst = 0.0
    for i in range(len(line) - 2):
        p1, p2, p3 = line[i], line[i + 1], line[i + 2]
        a = np.linalg.norm(p2 - p3)
        b = np.linalg.norm(p1 - p3)
        c = np.linalg.norm(p1 - p2)
        s = 0.5 * (a + b + c)
        area = max(s * (s - a) * (s - b) * (s - c), 1.0e-30) ** 0.5
        radius = a * b * c / (4.0 * area)
        half = 0.5 * c
        worst = max(worst, radius - np.sqrt(max(radius * radius - half * half, 0.0)))
    return float(worst)


def xz(points: np.ndarray) -> list[list[float]]:
    return [[round(float(p[0]), 6), round(float(p[2]), 6)] for p in points]


def collect(levels, stations: int) -> dict:
    reference_spec = None
    import strategy_s6

    reference_spec = replace(
        strategy_s6.LEVELS[levels[-1]], end_points=REFERENCE_WRAP_POINTS
    )
    reference = build_blocks(None, reference_spec)
    ref_wrap = reference[WRAP]
    span = ref_wrap.shape[1]
    picks = [int(round(f * (span - 1))) for f in np.linspace(0.06, 0.94, stations)]

    data = {"first_cell_um": FIRST_CELL_UM, "stations": [], "levels": {}}
    for j in picks:
        data["stations"].append(round(float(ref_wrap[0, j, 1]), 5))
    data["reference"] = [xz(ref_wrap[:, j, :]) for j in picks]

    for name in levels:
        blocks = build_blocks(name)
        wrap = blocks[WRAP]
        entry = {"wrap_cells": int(wrap.shape[0] - 1), "sections": [], "metrics": []}
        for y in data["stations"]:
            k = int(np.argmin(np.abs(wrap[0, :, 1] - y)))
            section = {}
            for block_name in SECTION_BLOCKS:
                if block_name not in blocks:
                    continue
                block = blocks[block_name]
                kk = int(np.argmin(np.abs(block[0, :, 1] - y)))
                section[block_name] = xz(block[:, kk, :])
            entry["sections"].append(section)
            line = wrap[:, k, :]
            cells = wrap.shape[0] - 1
            entry["metrics"].append({
                "turn": round(total_turning(line) / cells, 2),
                "cut": round(corner_cut(line) * 1e6, 1),
            })
        data["levels"][name.replace("candidate_", "").upper()] = entry
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", nargs="*", default=list(DEFAULT_LEVELS))
    ap.add_argument("--stations", type=int, default=9)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    data = collect(args.levels, args.stations)
    template = (HERE.parent / "inspector_template.html").read_text()
    payload = json.dumps(data, separators=(",", ":"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(template.replace("/*__MESH_DATA__*/null", payload))
    print(json.dumps({
        "out": str(args.out),
        "bytes": args.out.stat().st_size,
        "levels": list(data["levels"]),
        "stations": len(data["stations"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
