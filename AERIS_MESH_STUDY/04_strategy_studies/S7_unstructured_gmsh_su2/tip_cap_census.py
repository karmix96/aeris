"""Census the tip-cap construction across the development set, surface only.

M2 gave the tip cap an instrumentation field; this answers the question that
field exists for.  Two things are unknown from one geometry:

1. **How many designs take the ladder fallback.**  The fixed-topology exploit
   needs index correspondence to be exact across the family, and a design whose
   cap fell back has different connectivity from one that did not.  If the
   fallback is never taken, freezing the surface grid is a much smaller change
   than if it is taken by a fifth of the set.
2. **Whether cap quality degrades across the design space or only on index 0**,
   where minimum angle falls 18.33 -> 12.91 -> 9.48 -> 7.03 degrees from
   laptop_smoke to fine, ending below the 7.209 of the rigid ladder this study
   rejected for being too slender.

Surfaces only: no volume mesh, no solver.  One core, a few hundred MB, and it is
resumable, so it can run beside a solve without disturbing it.

    python tip_cap_census.py --level coarse --output <dir>
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from .common import load_policy
from .geometry import build_pygeo_case, build_surface


def census(
    output: Path,
    *,
    set_name: str,
    level: str,
    te_variant: str,
    indices: list[int],
) -> list[dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    policy = load_policy()
    records_path = output / f"tip_cap_census_{level}.json"
    # Resume: a design already measured is not rebuilt.  Surfaces are
    # deterministic, so re-running one would only cost time.
    done: dict[int, dict[str, Any]] = {}
    if records_path.is_file():
        for row in json.loads(records_path.read_text(encoding="utf-8")):
            done[int(row["index"])] = row

    for index in indices:
        if index in done:
            continue
        started = time.time()
        row: dict[str, Any] = {"index": index, "level": level}
        try:
            case = build_pygeo_case(set_name, index, output / "geom" / f"{index:03d}")
            surface = build_surface(
                case, level=level, te_variant=te_variant, policy=policy
            )
            cap = surface.metadata["tip_cap"]
            row.update(
                {
                    "status": "ok",
                    "surface_triangles": int(len(surface.triangles)),
                    "any_fallback": bool(cap["any_fallback"]),
                    "min_angle_deg": float(cap["min_angle_deg"]),
                    "by_side": cap["by_side"],
                }
            )
        except Exception as error:  # a failed surface is data, not a crash
            row.update({"status": "error", "error": f"{type(error).__name__}: {error}"})
        row["wall_s"] = round(time.time() - started, 1)
        done[index] = row
        rows = [done[k] for k in sorted(done)]
        records_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in row.items() if k != "by_side"}), flush=True)

    return [done[k] for k in sorted(done)]


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("status") == "ok"]
    angles = [r["min_angle_deg"] for r in ok]
    fell_back = [r["index"] for r in ok if r["any_fallback"]]
    return {
        "designs": len(rows),
        "surfaces_built": len(ok),
        "errors": [r["index"] for r in rows if r.get("status") != "ok"],
        "fallback_count": len(fell_back),
        "fallback_indices": fell_back,
        "min_angle_deg": {
            "min": min(angles) if angles else None,
            "median": statistics.median(angles) if angles else None,
            "max": max(angles) if angles else None,
        },
        # The rigid ladder rejected earlier in this study measured 7.209 degrees.
        # A Delaunay cap below that is more slender than the construction thrown
        # out for being too slender.
        "below_rejected_ladder_7p209": [
            r["index"] for r in ok if r["min_angle_deg"] < 7.209
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-name", default="lhs100_seed42")
    parser.add_argument("--level", default="coarse")
    parser.add_argument("--te-variant", default="te_1p0mm")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = census(
        args.output,
        set_name=args.set_name,
        level=args.level,
        te_variant=args.te_variant,
        indices=list(range(args.count)),
    )
    summary = summarise(rows)
    (args.output / f"tip_cap_summary_{args.level}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
