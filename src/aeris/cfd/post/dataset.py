"""
CFD-to-ML dataset collection with per-row verification gating.

Each completed case workdir contributes one row: flow condition (features),
force coefficients (targets), and the solution-verification evidence from
``verification.json`` — so a surrogate training set built from CFD carries
per-row quality tags instead of trusting every solve equally.

This deliberately upgrades the existing AERIS curation granularity: the
AVL/NeuralFoil chain gates per geometry *group* (binary keep/reject,
``aeris.dataset.curate_aero``) because low-fidelity rows carry no
verification evidence; CFD rows do (iterative convergence, mesh march QC,
sha256 chain), so they are gated **per row** on that evidence (NASA CFD
Vision 2030 ML+UQ integration; AIAA V&V practice for simulation-derived
data).

Stdlib-only (csv/json) — this module lives inside the standalone core.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

DATASET_GATE_SCHEMA_VERSION = "aeris.cfd.dataset_gate.v1"

ROW_COLUMNS = [
    "case",
    "workdir",
    # features
    "alpha",
    "mach",
    "reynolds",
    "temperature",
    "area_ref",
    "chord_ref",
    # targets
    "cl",
    "cd",
    "cmy",
    # verification evidence
    "solver",
    "solve_status",
    "iterations",
    "orders_dropped",
    "final_resrho",
    "mesh_march_status",
    "mesh_min_quality",
    "mesh_quality_warning",
    "mesh_cgns_sha256",
    "solve_report_sha256",
]


def collect_case_row(case_workdir: Path) -> dict[str, object]:
    """One dataset row from a case workdir (solve + verification artifacts)."""
    case_workdir = Path(case_workdir)
    solve_dir = case_workdir / "solve"
    report = json.loads((solve_dir / "solve_report.json").read_text(encoding="utf-8"))

    verification: dict[str, object] = {}
    verification_path = solve_dir / "verification.json"
    if verification_path.is_file():
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
    iterative = verification.get("iterative", {}) or {}
    mesh = verification.get("mesh", {}) or {}

    case_name = case_workdir.name
    manifest_path = case_workdir / "case_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        case_name = manifest.get("case", case_name)

    flow = report.get("flow", {}) or {}
    refs = report.get("refs", {}) or {}
    forces = report.get("forces", {}) or {}
    convergence = report.get("convergence", {}) or {}
    return {
        "case": case_name,
        "workdir": str(case_workdir),
        "alpha": flow.get("alpha"),
        "mach": flow.get("mach"),
        "reynolds": flow.get("reynolds"),
        "temperature": flow.get("temperature"),
        "area_ref": refs.get("area_ref"),
        "chord_ref": refs.get("chord_ref"),
        "cl": forces.get("cl"),
        "cd": forces.get("cd"),
        "cmy": forces.get("cmy"),
        "solver": report.get("solver_id"),
        "solve_status": report.get("status"),
        "iterations": iterative.get("iterations", convergence.get("iterations")),
        "orders_dropped": iterative.get("orders_dropped", convergence.get("orders_dropped")),
        "final_resrho": iterative.get(
            "final_resrho",
            convergence.get("final_resrho", convergence.get("final_resrho_log10")),
        ),
        "mesh_march_status": mesh.get("march_status"),
        "mesh_min_quality": mesh.get("min_quality"),
        "mesh_quality_warning": mesh.get("quality_warning"),
        "mesh_cgns_sha256": mesh.get("cgns_sha256"),
        "solve_report_sha256": verification.get("solve_report_sha256"),
    }


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def gate_row(row: dict[str, object], *, min_orders_dropped: float = 4.0) -> list[str]:
    """Return the list of gate violations for one row (empty = keep).

    Gates (each independently reportable):
    * solver reported a converged solution
    * pyHyp march produced a valid (non-inverted) mesh
    * iterative convergence dropped >= min_orders_dropped orders
      (default 4 — below that, force coefficients still drift)
    * all target coefficients finite
    """
    reasons: list[str] = []
    if row.get("solve_status") != "converged":
        reasons.append("solve_not_converged")
    march = row.get("mesh_march_status")
    if march is not None and march != "valid":
        reasons.append("mesh_march_invalid")
    orders = row.get("orders_dropped")
    if not _finite(orders) or float(orders) < min_orders_dropped:  # type: ignore[arg-type]
        reasons.append("insufficient_residual_drop")
    if not all(_finite(row.get(key)) for key in ("cl", "cd")):
        reasons.append("nonfinite_targets")
    return reasons


def collect_cfd_dataset(
    case_workdirs: list[Path],
    output_dir: Path,
    *,
    min_orders_dropped: float = 4.0,
) -> dict[str, object]:
    """Collect + gate case rows into cfd_dataset.csv / cfd_rejected.csv.

    Returns the gate report (also written as ``cfd_dataset_gate.json``).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    kept: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    reason_counts: dict[str, int] = {}
    for workdir in case_workdirs:
        row = collect_case_row(Path(workdir))
        reasons = gate_row(row, min_orders_dropped=min_orders_dropped)
        if reasons:
            row["rejection_reasons"] = ";".join(reasons)
            rejected.append(row)
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        else:
            kept.append(row)

    def _write(path: Path, rows: list[dict[str, object]], extra: list[str]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ROW_COLUMNS + extra)
            writer.writeheader()
            writer.writerows(rows)

    kept_path = output_dir / "cfd_dataset.csv"
    rejected_path = output_dir / "cfd_rejected.csv"
    _write(kept_path, kept, [])
    _write(rejected_path, rejected, ["rejection_reasons"])

    report = {
        "schema": DATASET_GATE_SCHEMA_VERSION,
        "min_orders_dropped": min_orders_dropped,
        "n_cases": len(case_workdirs),
        "kept_rows": len(kept),
        "rejected_rows": len(rejected),
        "rejection_reason_counts": reason_counts,
        "dataset_csv": str(kept_path),
        "rejected_csv": str(rejected_path),
    }
    (output_dir / "cfd_dataset_gate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def trust_chain_artifacts(case_workdir: Path) -> list[Path]:
    """The canonical artifact chain of one case, for evidence packaging.

    Pass to ``aeris.ml.evidence_package.build_evidence_package(
    extra_artifacts=...)`` to attach the CFD provenance chain (mesh ->
    options -> solve -> verification, all sha256-linked) to a model's
    evidence package.
    """
    case_workdir = Path(case_workdir)
    candidates = [
        case_workdir / "case_manifest.json",
        case_workdir / "surface" / "surface_report.json",
        case_workdir / "surface" / "volume_report.json",
        case_workdir / "surface" / "pyhyp_effective_options.json",
        case_workdir / "solve" / "solve_report.json",
        case_workdir / "solve" / "verification.json",
        case_workdir / "solve" / "adflow_effective_options.json",
        case_workdir / "solve" / "su2_effective_options.json",
        case_workdir / "post" / "solve_summary.json",
    ]
    return [path for path in candidates if path.is_file()]
