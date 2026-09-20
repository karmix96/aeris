#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from aeris_research.audits import run_scientific_audits  # noqa: E402
from aeris_research.baseline import build_baselines  # noqa: E402
from aeris_research.common import PipelineError, reject_output_inside_inputs  # noqa: E402
from aeris_research.dataset import audit_canonical_dataset, build_canonical_dataset  # noqa: E402
from aeris_research.evidence import QualificationEvidence  # noqa: E402
from aeris_research.monitor import scan_campaign, write_monitor_outputs  # noqa: E402
from aeris_research.paper import build_paper_package  # noqa: E402
from aeris_research.release import create_release  # noqa: E402
from aeris_research.workflow import refresh_research_products  # noqa: E402

DEFAULT_SOURCE = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification"
DEFAULT_BUILD = HERE / "build"
DEFAULT_RUN_ROOTS = (
    REPO / "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd",
    REPO / "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_pilot",
)
DEFAULT_LOCK = REPO / "AERIS_MESH_STUDY/artifacts/.s8_campaign.lock"


def _source(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _guard_output(value: str, source: Path) -> Path:
    return reject_output_inside_inputs(
        Path(value),
        (
            source,
            REPO / "AERIS_MESH_STUDY/artifacts",
            REPO / "AERIS_MESH_STUDY/04_strategy_studies",
        ),
    )


def _campaign_roots(arguments: argparse.Namespace) -> list[Path]:
    values = arguments.run_root or [str(path) for path in DEFAULT_RUN_ROOTS]
    return [Path(value).expanduser().resolve() for value in values]


def _add_campaign_inputs(command: argparse.ArgumentParser) -> None:
    command.add_argument("--source", default=str(DEFAULT_SOURCE))
    command.add_argument(
        "--run-root",
        action="append",
        help="Campaign artifact root; repeat for multiple roots (defaults to S8 CFD and pilot)",
    )
    command.add_argument("--lock", default=str(DEFAULT_LOCK))
    command.add_argument(
        "--stale-after",
        type=float,
        default=1800.0,
        help="Seconds without a file update before partial evidence is INCOMPLETE, not RUNNING",
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Build read-only paper and AI products from frozen AERIS CFD evidence."
    )
    commands = root.add_subparsers(dest="command", required=True)

    paper = commands.add_parser("paper", help="Generate Paper-1 tables and figures")
    paper.add_argument("--source", default=str(DEFAULT_SOURCE))
    paper.add_argument("--output", default=str(DEFAULT_BUILD / "paper"))

    dataset = commands.add_parser("dataset", help="Build canonical topology-safe HDF5 fields")
    dataset.add_argument("--source", default=str(DEFAULT_SOURCE))
    dataset.add_argument("--output", default=str(DEFAULT_BUILD / "ai_surface_fields.h5"))
    dataset.add_argument(
        "--accepted-only",
        action="store_true",
        help="Exclude incomplete/failed snapshots instead of preserving their status metadata",
    )

    baseline = commands.add_parser("baseline", help="Build POD and latent field baselines")
    baseline.add_argument("--dataset", default=str(DEFAULT_BUILD / "ai_surface_fields.h5"))
    baseline.add_argument("--output", default=str(DEFAULT_BUILD / "baselines"))
    baseline.add_argument("--topology", default=None, help="Unique topology-hash prefix")
    baseline.add_argument("--pod-rank", type=int, default=16)
    baseline.add_argument("--latent-dim", type=int, default=16)
    baseline.add_argument("--epochs", type=int, default=250)
    baseline.add_argument("--seed", type=int, default=42)
    baseline.add_argument(
        "--pod-only",
        action="store_true",
        help="Build POD but do not train predictive models",
    )

    audit = commands.add_parser("audit", help="Re-run topology audit on canonical HDF5")
    audit.add_argument("--dataset", default=str(DEFAULT_BUILD / "ai_surface_fields.h5"))

    monitor = commands.add_parser(
        "monitor", help="Read-only campaign discovery, classification, alerts, and advice"
    )
    _add_campaign_inputs(monitor)
    monitor.add_argument("--output", default=str(DEFAULT_BUILD / "monitor"))
    monitor.add_argument("--watch", action="store_true", help="Rescan until interrupted")
    monitor.add_argument("--interval", type=float, default=60.0)

    release = commands.add_parser(
        "release", help="Create an immutable accepted-only snapshot release"
    )
    _add_campaign_inputs(release)
    release.add_argument("--output", default=str(DEFAULT_BUILD / "releases"))

    audit_science = commands.add_parser(
        "audit-science", help="Audit axes, pressure integration, topology, and holdout leakage"
    )
    audit_science.add_argument("--dataset", default=str(DEFAULT_BUILD / "ai_surface_fields.h5"))
    audit_science.add_argument("--evidence-root", default=str(DEFAULT_SOURCE))
    audit_science.add_argument("--holdout-contract-root", default=str(DEFAULT_SOURCE))
    audit_science.add_argument("--output", default=str(DEFAULT_BUILD / "audits"))

    refresh = commands.add_parser(
        "refresh", help="Monitor, release, rebuild paper/AI products, and audit"
    )
    _add_campaign_inputs(refresh)
    refresh.add_argument("--output", default=str(DEFAULT_BUILD))
    refresh.add_argument(
        "--train",
        action="store_true",
        help="Explicitly enable POD/latent predictors; off by default to avoid CFD contention",
    )
    refresh.add_argument("--pod-rank", type=int, default=16)
    refresh.add_argument("--latent-dim", type=int, default=16)
    refresh.add_argument("--epochs", type=int, default=250)
    refresh.add_argument("--seed", type=int, default=42)

    all_command = commands.add_parser("all", help="Build paper, canonical dataset, and baselines")
    all_command.add_argument("--source", default=str(DEFAULT_SOURCE))
    all_command.add_argument("--output", default=str(DEFAULT_BUILD))
    all_command.add_argument("--pod-rank", type=int, default=16)
    all_command.add_argument("--latent-dim", type=int, default=16)
    all_command.add_argument("--epochs", type=int, default=250)
    all_command.add_argument("--seed", type=int, default=42)
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "paper":
            source = _source(arguments.source)
            output = _guard_output(arguments.output, source)
            result = build_paper_package(QualificationEvidence(source), output)
        elif arguments.command == "dataset":
            source = _source(arguments.source)
            output = _guard_output(arguments.output, source)
            result = build_canonical_dataset(
                QualificationEvidence(source),
                output,
                include_incomplete=not arguments.accepted_only,
            )
        elif arguments.command == "baseline":
            dataset = Path(arguments.dataset).expanduser().resolve()
            output = _guard_output(arguments.output, DEFAULT_SOURCE)
            result = build_baselines(
                dataset,
                output,
                topology_selector=arguments.topology,
                pod_rank=arguments.pod_rank,
                latent_dim=arguments.latent_dim,
                epochs=arguments.epochs,
                seed=arguments.seed,
                train_predictors=not arguments.pod_only,
            )
        elif arguments.command == "audit":
            result = audit_canonical_dataset(Path(arguments.dataset).expanduser().resolve())
        elif arguments.command == "monitor":
            source = _source(arguments.source)
            output = _guard_output(arguments.output, source)
            while True:
                scan = scan_campaign(
                    source,
                    _campaign_roots(arguments),
                    lock_path=Path(arguments.lock).expanduser().resolve(),
                    stale_after_seconds=arguments.stale_after,
                )
                report = write_monitor_outputs(scan, output)
                result = {
                    "counts": report["counts"],
                    "accepted_distinct_geometries": report["accepted_distinct_geometries"],
                    "training_ready": report["training_ready"],
                    "campaign_lock": report["campaign_lock"],
                    "output": str(output),
                }
                if not arguments.watch:
                    break
                print(json.dumps(result, indent=2, sort_keys=True), flush=True)
                time.sleep(max(1.0, arguments.interval))
        elif arguments.command == "release":
            source = _source(arguments.source)
            output = _guard_output(arguments.output, source)
            scan = scan_campaign(
                source,
                _campaign_roots(arguments),
                lock_path=Path(arguments.lock).expanduser().resolve(),
                stale_after_seconds=arguments.stale_after,
            )
            released = create_release(scan, output)
            result = {
                "release_id": released["release_id"],
                "path": released["path"],
                "accepted_snapshots": released["accepted_snapshots"],
                "excluded_snapshots": released["excluded_snapshots"],
                "distinct_geometries": released["distinct_geometries"],
                "reused": released["reused"],
            }
        elif arguments.command == "audit-science":
            source = _source(arguments.holdout_contract_root)
            output = _guard_output(arguments.output, source)
            result = run_scientific_audits(
                Path(arguments.dataset).expanduser().resolve(),
                Path(arguments.evidence_root).expanduser().resolve(),
                source,
                output,
            )
        elif arguments.command == "refresh":
            source = _source(arguments.source)
            output = _guard_output(arguments.output, source)
            result = refresh_research_products(
                source,
                _campaign_roots(arguments),
                output,
                lock_path=Path(arguments.lock).expanduser().resolve(),
                stale_after_seconds=arguments.stale_after,
                train_predictors=arguments.train,
                pod_rank=arguments.pod_rank,
                latent_dim=arguments.latent_dim,
                epochs=arguments.epochs,
                seed=arguments.seed,
            )
        else:
            source = _source(arguments.source)
            output = _guard_output(arguments.output, source)
            paper_result = build_paper_package(QualificationEvidence(source), output / "paper")
            dataset_path = output / "ai_surface_fields.h5"
            dataset_result = build_canonical_dataset(QualificationEvidence(source), dataset_path)
            baseline_result = build_baselines(
                dataset_path,
                output / "baselines",
                pod_rank=arguments.pod_rank,
                latent_dim=arguments.latent_dim,
                epochs=arguments.epochs,
                seed=arguments.seed,
            )
            result = {
                "paper": {
                    "status_counts": paper_result["run_status_counts"],
                    "outputs": len(paper_result["outputs"]),
                },
                "dataset": {
                    "snapshots": dataset_result["snapshots"],
                    "topology_families": dataset_result["topology_families"],
                    "container_sha256": dataset_result["dataset_sha256"],
                    "logical_hash": dataset_result["logical_dataset_hash"],
                },
                "baselines": {
                    "pod": baseline_result["pod"]["status"],
                    "prediction": baseline_result["prediction"]["status"],
                },
            }
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
