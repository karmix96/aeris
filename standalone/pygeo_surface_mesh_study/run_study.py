"""Command-line interface for the pyGeo-native surface-mesh study.

Examples
--------
PYTHONPATH=src .venv/bin/python -m standalone.pygeo_surface_mesh_study.run_study \
    validate --config configs/cfd/pygeo_surface_mesh_study.yaml

PYTHONPATH=src .venv/bin/python -m standalone.pygeo_surface_mesh_study.run_study \
    run --config configs/cfd/pygeo_surface_mesh_study.yaml \
    --workdir artifacts/pygeo_surface_mesh_study/run_001 --stage all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .analysis import analyze_workdir
from .runner import (
    initialize_workdir,
    load_generator_config,
    run_smoke,
    run_stage,
    validate_ready,
    write_json,
)
from .spec import load_study_spec


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="pyGeo-native BWB surface-mesh sensitivity/refinement study"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate schema and geometry wiring")
    validate.add_argument("--config", required=True)
    validate.add_argument(
        "--require-limits",
        action="store_true",
        help="also fail if any enabled metric limit is still null",
    )

    plan = subparsers.add_parser("plan", help="write the deterministic initial case plan")
    plan.add_argument("--config", required=True)
    plan.add_argument("--output", required=True)

    smoke = subparsers.add_parser("smoke", help="build one baseline geometry and one coarse mesh")
    smoke.add_argument("--config", required=True)
    smoke.add_argument("--workdir", required=True)
    smoke.add_argument("--level", default="L1")

    run = subparsers.add_parser("run", help="run a staged or complete campaign")
    run.add_argument("--config", required=True)
    run.add_argument("--workdir", required=True)
    run.add_argument(
        "--stage",
        choices=("baseline", "ofat", "pairwise", "lhs", "all"),
        default="all",
    )
    run.add_argument(
        "--allow-unset-limits",
        action="store_true",
        help="development only: treat null limits as non-gating",
    )
    run.add_argument(
        "--rerun-failed",
        action="store_true",
        help="retry finalized failed/unresolved cases while preserving successful cases",
    )

    analyze = subparsers.add_parser("analyze", help="rebuild laws from saved case results")
    analyze.add_argument("--config", required=True)
    analyze.add_argument("--workdir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        spec = load_study_spec(args.config)
        if args.command == "validate":
            load_generator_config(spec)
            validate_ready(spec, allow_unset_limits=not args.require_limits)
            payload = {
                "valid": True,
                "campaign_ready": not spec.unset_enabled_limits(),
                "study": spec.name,
                "variables": len(spec.variables),
                "levels": [level.name for level in spec.levels],
                "reference_level": spec.reference_level,
                "initial_counts": spec.initial_plan()["counts"],
                "unset_enabled_limits": spec.unset_enabled_limits(),
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "plan":
            load_generator_config(spec)
            output = Path(args.output).resolve()
            write_json(output, spec.initial_plan())
            print(output)
            return 0

        if args.command == "smoke":
            result = run_smoke(spec, Path(args.workdir).resolve(), level=args.level)
            print(
                json.dumps(
                    {
                        "status": result["status"],
                        "selected_level": result.get("selected_level"),
                        "result": str(
                            Path(args.workdir).resolve() / "cases" / "baseline" / "result.json"
                        ),
                    },
                    indent=2,
                )
            )
            return 0 if result["status"] == "complete" else 1

        if args.command == "run":
            report = run_stage(
                spec,
                Path(args.workdir).resolve(),
                stage=args.stage,
                allow_unset_limits=args.allow_unset_limits,
                rerun_failed=args.rerun_failed,
            )
            analysis = analyze_workdir(spec, Path(args.workdir).resolve())
            print(
                json.dumps(
                    {
                        "result_count": report["result_count"],
                        "status_counts": report["status_counts"],
                        "ranked_variables": [row["variable"] for row in analysis["ranking"]],
                        "workdir": str(Path(args.workdir).resolve()),
                    },
                    indent=2,
                )
            )
            return 0

        if args.command == "analyze":
            manifest = initialize_workdir(spec, Path(args.workdir).resolve())
            analysis = analyze_workdir(spec, Path(args.workdir).resolve())
            print(
                json.dumps(
                    {
                        "run_fingerprint": manifest["run_fingerprint"],
                        "eligible_common_reference_count": analysis[
                            "eligible_common_reference_count"
                        ],
                        "ranked_variables": [row["variable"] for row in analysis["ranking"]],
                    },
                    indent=2,
                )
            )
            return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
