"""Measure what it would cost to freeze the surface grid across the design family.

S6 generalises by meshing a few templates and deforming onto the rest, which needs
exact index-based node correspondence.  S7 cannot do that today because the
sampling counts are derived per design.  This reads the surface reports already on
disk and reports the spread and the freezing cost; it meshes nothing and runs in
about a second.

    python fixed_topology_probe.py [artifacts_root]
"""

from __future__ import annotations

import collections
import glob
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = (
    Path(__file__).resolve().parents[2]
    / "artifacts/strategy_studies/S7_unstructured_gmsh_su2"
)


def _records(root: Path) -> list[dict[str, object]]:
    rows = []
    for path in glob.glob(str(root / "**/source_surface_report.json"), recursive=True):
        report = json.load(open(path, encoding="utf-8"))
        sampling, topology = report["sampling"], report["topology"]
        match = re.search(r"__([a-z0-9_]+)__te_", path)
        rows.append(
            {
                "level": match.group(1) if match else report.get("level", "unknown"),
                "case": Path(path).parents[1].name,
                "n_u": int(sampling["chordwise_points"]),
                "n_v": int(sampling["half_span_points"]),
                "nodes": int(topology["node_count"]),
                "triangles": int(topology["triangle_count"]),
            }
        )
    return rows


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROOT
    rows = _records(root)
    if not rows:
        print(f"no surface reports under {root}")
        return 1

    by_level = collections.defaultdict(list)
    for row in rows:
        by_level[row["level"]].append(row)

    print("%-14s %6s %-12s %-12s %-10s %-10s" % (
        "level", "cases", "n_u", "n_v", "mean cost", "worst cost"))
    for level, group in sorted(by_level.items()):
        us = [r["n_u"] for r in group]
        vs = [r["n_v"] for r in group]
        # Freezing to the family maximum keeps every design at or above the
        # resolution it has today, so the cost is pure inflation and never a loss.
        frozen = (max(us) - 1) * (max(vs) - 1)
        actual = [(r["n_u"] - 1) * (r["n_v"] - 1) for r in group]
        print("%-14s %6d %-12s %-12s %-10s %-10s" % (
            level,
            len(group),
            f"{min(us)}-{max(us)} ({len(set(us))})",
            f"{min(vs)}-{max(vs)} ({len(set(vs))})",
            f"{frozen / (sum(actual) / len(actual)):.2f}x",
            f"{frozen / min(actual):.2f}x",
        ))

    print("\nDistinct (n_u, n_v) grids per level:")
    for level, group in sorted(by_level.items()):
        pairs = collections.Counter((r["n_u"], r["n_v"]) for r in group)
        print(f"  {level}: {len(pairs)} distinct over {len(group)} cases")
        for (u, v), count in pairs.most_common(6):
            print(f"      n_u={u:<4d} n_v={v:<4d} {count} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
