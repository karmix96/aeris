"""Summarise a campaign run into a small file that belongs in git.

The artifact trees are large and are wiped between campaigns, so a run that is
only recorded there is a run nobody can evaluate later.  This reads the
`case_result.json` files a campaign leaves behind and writes a compact Markdown
and JSON pair into `RUN_LOG/`, small enough to commit and pull back on another
machine.

    python run_report.py <artifacts_root> --name s7_stage0_multigrid
    python run_report.py <artifacts_root> --name s7_stage1 --push

`--push` commits and pushes the report only; it never touches the artifacts.
Safe to re-run while a campaign is still going: it reports whatever has landed so
far, which is what makes it usable as a live progress check.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUN_LOG = HERE / "RUN_LOG"


def _dig(payload: Any, *path: str, default: Any = None) -> Any:
    """Follow a key path, returning default rather than raising on any miss."""
    current = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _collect(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("case_result.json")):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"case_id": str(path.parent.name), "unreadable": str(exc)})
            continue
        rows.append(
            {
                "case_id": result.get("case_id"),
                "index": result.get("development_index"),
                "level": result.get("grid_level"),
                "scope": result.get("acceptance_scope"),
                "accepted": result.get("accepted"),
                "cells": _dig(result, "cell_counts", "volume_cells"),
                "attempts": len(_dig(result, "gate_results", "mesh_attempts", default=[]) or []),
                "cl": _dig(result, "forces", "cl"),
                "cd": _dig(result, "forces", "cd"),
                "cmy": _dig(result, "forces", "cmy"),
                "y_plus_p95": _dig(result, "gate_results", "cfd", "y_plus_p95"),
                "y_plus_max": _dig(result, "gate_results", "cfd", "y_plus_max"),
                "residual_drop": _dig(result, "gate_results", "cfd", "orders_dropped"),
                "rss_bytes": _dig(result, "peak_memory", "rss_bytes"),
                "wall_s": result.get("wall_seconds"),
                "failure_reasons": result.get("failure_reasons") or [],
            }
        )
    return rows


def _fmt(value: Any, spec: str = "") -> str:
    if value is None:
        return "-"
    if spec and isinstance(value, (int, float)):
        return format(value, spec)
    return str(value)


def _render(rows: list[dict[str, Any]], name: str, root: Path) -> str:
    good = [r for r in rows if r.get("accepted")]
    bad = [r for r in rows if r.get("accepted") is False]
    lines = [
        f"# Run report: {name}",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')} from `{root}`.",
        "",
        f"**{len(good)} accepted / {len(rows)} cases**"
        + (f", {len(bad)} failed" if bad else "")
        + ".",
        "",
    ]

    finished = [r for r in rows if r.get("residual_drop") is not None]
    if finished:
        drops = [r["residual_drop"] for r in finished]
        lines += [
            f"Residual drop over {len(finished)} solved cases: "
            f"min {min(drops):.3f}, median {statistics.median(drops):.3f}, "
            f"max {max(drops):.3f} orders.",
            "",
        ]

    cds = [r["cd"] for r in rows if isinstance(r.get("cd"), (int, float))]
    if len(cds) > 1:
        lines += [f"CD across {len(cds)} cases: {min(cds):.6f} to {max(cds):.6f}.", ""]

    lines += [
        "| case | lvl | ok | cells | att | y+ p95 | y+ max | drop | CL | CD | Cm |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r.get("case_id", "?"),
                _fmt(r.get("level")),
                "yes" if r.get("accepted") else "NO",
                _fmt(r.get("cells"), ",d") if r.get("cells") else "-",
                _fmt(r.get("attempts")),
                _fmt(r.get("y_plus_p95"), ".4f"),
                _fmt(r.get("y_plus_max"), ".4f"),
                _fmt(r.get("residual_drop"), ".3f"),
                _fmt(r.get("cl"), ".5f"),
                _fmt(r.get("cd"), ".5f"),
                _fmt(r.get("cmy"), ".5f"),
            )
        )

    if bad:
        lines += ["", "## Failures", ""]
        for r in bad:
            reasons = ", ".join(r["failure_reasons"]) or "no reason recorded"
            lines.append(f"- `{r.get('case_id')}`: {reasons}")

    lines += [
        "",
        "## How to read this",
        "",
        "`ok` is the declared technical scope passing, not campaign readiness.",
        "`drop` is orders of residual reduction; the policy gate is six.",
        "A case still running simply has not written its result yet and is absent.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="campaign artifacts root to scan")
    parser.add_argument("--name", required=True, help="short label, becomes the filename")
    parser.add_argument("--push", action="store_true", help="commit and push the report")
    args = parser.parse_args()

    if not args.root.exists():
        print(f"no such path: {args.root}")
        return 1

    rows = _collect(args.root)
    if not rows:
        print(f"no case_result.json found under {args.root}")
        return 1

    RUN_LOG.mkdir(parents=True, exist_ok=True)
    md = RUN_LOG / f"{args.name}.md"
    js = RUN_LOG / f"{args.name}.json"
    md.write_text(_render(rows, args.name, args.root), encoding="utf-8")
    js.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    accepted = sum(1 for r in rows if r.get("accepted"))
    print(f"{accepted}/{len(rows)} accepted -> {md}")

    if args.push:
        message = f"Run report: {args.name} ({accepted}/{len(rows)} accepted)"
        for command in (
            ["git", "add", str(md), str(js)],
            ["git", "commit", "-q", "-m", message],
            ["git", "push"],
        ):
            done = subprocess.run(command, capture_output=True, text=True)
            if done.returncode != 0 and "nothing to commit" not in done.stdout:
                print("git step failed:", " ".join(command), done.stderr.strip())
                return 1
        print("pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
