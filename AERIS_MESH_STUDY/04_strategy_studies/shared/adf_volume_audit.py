#!/usr/bin/env python
"""Independent ADF-CGNS reader bridge for the shared direct volume QC."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STUDIES = Path(__file__).resolve().parent.parent
REPO = STUDIES.parents[1]
for candidate in (STUDIES, REPO / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from cgnsutilities.cgnsutilities import readGrid

from shared.volume_qc import volume_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cgns", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    grid = readGrid(str(args.cgns))
    blocks = {
        block.name: block.coords.transpose(2, 1, 0, 3)
        for block in grid.blocks
    }
    report = volume_report(blocks)
    report["source_cgns"] = str(args.cgns.resolve())
    report["independent_reader"] = "cgnsUtilities.readGrid ADF route"
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
