#!/usr/bin/env python3
"""Portable CLI for S7; defaults to a non-executing, laptop-safe plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for path in (HERE.parent, HERE.parent.parent.parent / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from S7_unstructured_gmsh_su2.campaign import plan_case, run_case, run_cases  # noqa: E402


def _indices(value: str) -> list[int]:
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            raise argparse.ArgumentTypeError("empty index component")
        if "-" in item:
            left, right = item.split("-", 1)
            start, stop = int(left), int(right)
            if stop < start:
                raise argparse.ArgumentTypeError(f"descending index range: {item}")
            result.extend(range(start, stop + 1))
        else:
            result.append(int(item))
    if not result:
        raise argparse.ArgumentTypeError("indices must not be empty")
    if len(result) != len(set(result)):
        raise argparse.ArgumentTypeError("indices must be unique")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="S7 preregistered unstructured workflow")
    p.add_argument("--set-name", default="lhs100_seed42")
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument("--index", type=int)
    selection.add_argument(
        "--indices",
        type=_indices,
        help="comma-separated indices/ranges, for example 0-19,24,49",
    )
    p.add_argument("--level", default="laptop_smoke")
    p.add_argument("--te-variant", default="te_1p0mm")
    p.add_argument("--flow-id", default="mesh")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--execute", action="store_true", help="run geometry and mesh (never production/holdout)"
    )
    p.add_argument(
        "--run-cfd",
        action="store_true",
        help="run the frozen cruise condition after an accepted mesh",
    )
    p.add_argument("--flow-json", type=Path)
    p.add_argument("--references-json", type=Path)
    p.add_argument("--timeout-s", type=float, default=3600.0)
    p.add_argument("--solver-command", nargs="+", default=["SU2_CFD"])
    p.add_argument("--mpi-ranks", type=int, default=1)
    a = p.parse_args()
    if a.run_cfd and not a.execute:
        p.error("--run-cfd requires --execute")
    if a.mpi_ranks < 1:
        p.error("--mpi-ranks must be >= 1")
    flow = json.loads(a.flow_json.read_text()) if a.flow_json else None
    refs = json.loads(a.references_json.read_text()) if a.references_json else None
    indices = [a.index] if a.index is not None else a.indices
    solver_command = list(a.solver_command)
    if a.mpi_ranks > 1:
        solver_command = ["mpirun", "-np", str(a.mpi_ranks), *solver_command]
    try:
        if not a.execute:
            plans = [
                plan_case(
                    set_name=a.set_name,
                    index=index,
                    level=a.level,
                    te_variant=a.te_variant,
                    output=a.output,
                    flow_id=("cruise" if a.run_cfd else a.flow_id),
                )
                for index in indices
            ]
            result = (
                plans[0]
                if len(plans) == 1
                else {
                    "schema": "aeris.s7.batch_plan.v1",
                    "mode": "plan_only",
                    "cases": plans,
                }
            )
        elif len(indices) == 1:
            result = run_case(
                set_name=a.set_name,
                index=indices[0],
                level=a.level,
                te_variant=a.te_variant,
                output=a.output,
                flow=flow,
                references=refs,
                run_cfd=a.run_cfd,
                timeout_s=a.timeout_s,
                solver_command=solver_command,
                flow_id=a.flow_id,
            )
        else:
            result = run_cases(
                set_name=a.set_name,
                indices=indices,
                level=a.level,
                te_variant=a.te_variant,
                output=a.output,
                flow=flow,
                references=refs,
                run_cfd=a.run_cfd,
                timeout_s=a.timeout_s,
                solver_command=solver_command,
                flow_id=a.flow_id,
            )
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"status": "OK", **result}, indent=2, default=str))
    passed = result.get("technical_all_passed", result.get("accepted", True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
