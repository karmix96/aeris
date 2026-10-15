from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .common import (
    atomic_write_text,
    output_manifest,
    utc_now,
    write_csv,
    write_json,
    write_latex_table,
)
from .evidence import QualificationEvidence, RunEvidence, parse_adflow_history

BLUE = "#0072B2"
ORANGE = "#D55E00"
GREEN = "#009E73"
PURPLE = "#CC79A7"
GREY = "#6B7280"


def _save_figure(figure: plt.Figure, stem: Path) -> None:
    figure.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    figure.savefig(stem.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _format_number(value: Any, digits: int = 5) -> Any:
    if isinstance(value, float):
        return f"{value:.{digits}g}" if math.isfinite(value) else ""
    return value


def _write_table_pair(
    directory: Path,
    name: str,
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    caption: str,
) -> None:
    write_csv(directory / f"{name}.csv", rows, columns)
    latex_rows = [{key: _format_number(row.get(key)) for key in columns} for row in rows]
    write_latex_table(
        directory / f"{name}.tex",
        latex_rows,
        columns,
        caption=caption,
        label=f"tab:{name.replace('_', '-')}",
    )


def _run_inventory(runs: list[RunEvidence]) -> list[dict[str, Any]]:
    output = []
    for run in runs:
        row, gate = run.row, run.gate or {}
        output.append(
            {
                "run_name": row["run_name"],
                "status": run.status,
                "reasons": ";".join(run.reasons),
                "geometry_index": row.get("geometry_index"),
                "grid_level": row.get("grid_level"),
                "alpha_deg": row.get("alpha_deg"),
                "gate_verdict": gate.get("verdict"),
                "converged": (run.result or {}).get("converged"),
                "routine_failed": (run.result or {}).get("routine_failed"),
                "iterations": gate.get("iterations"),
                "relative_residual": gate.get("relative_residual"),
                "surface_hash_verified": "surface_hash_mismatch" not in run.reasons
                and run.archive is not None,
            }
        )
    return output


def _convergence_rows(runs: list[RunEvidence]) -> list[dict[str, Any]]:
    output = []
    for run in runs:
        gate = run.gate or {}
        checks = gate.get("checks") or {}
        output.append(
            {
                "run_name": run.row["run_name"],
                "grid_level": run.row.get("grid_level"),
                "alpha_deg": run.row.get("alpha_deg"),
                "status": run.status,
                "verdict": gate.get("verdict"),
                "iterations": gate.get("iterations"),
                "residual_orders": (checks.get("residual_orders") or {}).get("value"),
                "cl_tail_percent": (checks.get("cl_percent") or {}).get("value"),
                "cd_tail_percent": (checks.get("cd_percent") or {}).get("value"),
                "cmy_tail_absolute": (checks.get("cmy_absolute") or {}).get("value"),
                "solver_frozen": gate.get("solver_frozen"),
            }
        )
    return output


def _cost_rows(evidence: QualificationEvidence, runs: list[RunEvidence]) -> list[dict[str, Any]]:
    output = []
    timing_pattern = re.compile(r"Total Call Time\s*:\s*([0-9.eE+-]+)\s*sec")
    for run in runs:
        memory = run.memory or {}
        samples = memory.get("samples") or []
        elapsed = max((float(sample.get("t", 0.0)) for sample in samples), default=None)
        log_elapsed = None
        if run.log is not None:
            text = evidence.ledger.read_text(run.log)
            matches = timing_pattern.findall(text)
            if matches:
                log_elapsed = float(matches[-1])
        output.append(
            {
                "run_name": run.row["run_name"],
                "grid_level": run.row.get("grid_level"),
                "cells": run.row.get("cells"),
                "alpha_deg": run.row.get("alpha_deg"),
                "status": run.status,
                "wall_time_s": log_elapsed if log_elapsed is not None else elapsed,
                "peak_rank_rss_sum_gib": memory.get("peak_rank_rss_sum_gib"),
                "peak_swap_used_gib": memory.get("peak_swap_used_gib"),
                "memory_abort_reason": memory.get("aborted_reason"),
            }
        )
    return output


def _refinement_rows(runs: list[RunEvidence]) -> list[dict[str, Any]]:
    by_alpha: dict[float, dict[str, RunEvidence]] = defaultdict(dict)
    for run in runs:
        if run.status == "FINAL_ACCEPTED" and run.row.get("grid_level") in {"gci_C", "gci_M"}:
            by_alpha[float(run.row["alpha_deg"])][run.row["grid_level"]] = run
    output = []
    for alpha, levels in sorted(by_alpha.items()):
        if set(levels) != {"gci_C", "gci_M"}:
            continue
        coarse, fine = levels["gci_C"].row, levels["gci_M"].row
        refinement_ratio = (float(fine["cells"]) / float(coarse["cells"])) ** (1.0 / 3.0)
        for quantity in ("CL", "CD", "CDp", "CDv", "CMy"):
            coarse_value, fine_value = float(coarse[quantity]), float(fine[quantity])
            change = fine_value - coarse_value
            relative = abs(change / fine_value) * 100.0 if fine_value else None
            output.append(
                {
                    "alpha_deg": alpha,
                    "quantity": quantity,
                    "coarse_cells": coarse["cells"],
                    "fine_cells": fine["cells"],
                    "r21": refinement_ratio,
                    "coarse_value": coarse_value,
                    "fine_value": fine_value,
                    "fine_minus_coarse": change,
                    "relative_change_percent": relative,
                    "observed_order": None,
                    "gci_21_percent": None,
                    "study_type": "TREND_NOT_GCI",
                }
            )
    return output


def _mesh_records(evidence: QualificationEvidence) -> list[dict[str, Any]]:
    report = evidence.report("s8_robustness_screen_final.json")
    return list(report.get("records") or [])


def _mesh_statistics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quantities = (
        "cells",
        "wall_time_s",
        "negative_cells",
        "min_cell_volume_m3",
        "min_cell_over_s0",
        "worst_le_turn_per_cell_deg",
        "outboard_span_growth",
    )
    output = []
    for name in quantities:
        values = np.asarray(
            [float(record[name]) for record in records if record.get(name) is not None], dtype=float
        )
        if not values.size:
            continue
        output.append(
            {
                "quantity": name,
                "count": values.size,
                "minimum": float(values.min()),
                "p05": float(np.percentile(values, 5)),
                "median": float(np.median(values)),
                "p95": float(np.percentile(values, 95)),
                "maximum": float(values.max()),
            }
        )
    return output


def _pilot_rows(
    evidence: QualificationEvidence, mesh_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    pilots = evidence.report("s8_pilot_geometries.json")
    selected = pilots.get("selected_in_selection_order") or pilots.get("selected") or []
    mesh_by_index = {int(record["index"]): record for record in mesh_records}
    former = set(pilots.get("former_folders_included") or [])
    output = []
    for order, index in enumerate(selected, start=1):
        mesh = mesh_by_index.get(int(index), {})
        valid = mesh.get("built") is True and mesh.get("negative_cells") == 0
        output.append(
            {
                "selection_order": order,
                "geometry_index": index,
                "former_fold_case": int(index) in former,
                "mesh_status": "PASS" if valid else "FAIL" if mesh else "NOT_AVAILABLE",
                "cells": mesh.get("cells"),
                "negative_cells": mesh.get("negative_cells"),
                "cfd_status": "NOT_IN_ARCHIVE",
            }
        )
    return output


def _robustness_rows(
    evidence: QualificationEvidence, mesh_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    holdout = evidence.report("check_holdout_lock.json")
    development_valid = sum(
        record.get("built") is True and record.get("negative_cells") == 0 for record in mesh_records
    )
    return [
        {
            "cohort": "lhs100_seed42 development",
            "sample_count": len(mesh_records),
            "built": sum(record.get("built") is True for record in mesh_records),
            "valid_zero_negative_cells": development_valid,
            "failed": len(mesh_records) - development_valid,
            "status": "MEASURED",
        },
        {
            "cohort": "round_c_lhs10_seed42 holdout",
            "sample_count": None,
            "built": None,
            "valid_zero_negative_cells": None,
            "failed": None,
            "status": (
                "LOCKED_NOT_ACCESSED"
                if holdout.get("details", {}).get("contents_read") is False
                else "LOCK_CONTRACT_VIOLATION"
            ),
        },
    ]


def _onera_rows(evidence: QualificationEvidence) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report = evidence.report("s8_onera_m6_comparison.json")
    rows = []
    for station in report.get("stations") or []:
        rows.append(
            {
                "station": station.get("station"),
                "eta": station.get("eta"),
                "n_experiment": station.get("n_experiment"),
                "n_cfd_cells": station.get("n_cfd_cells"),
                "rms_dcp_vs_experiment": station.get("rms_dcp_vs_experiment"),
                "cp_min_experiment": station.get("cp_min_experiment"),
                "cp_min_cfd": station.get("cp_min_cfd"),
                "shock_experiment": station.get("shock_experiment"),
                "shock_cfd": station.get("shock_cfd"),
                "shock_dx_over_c": station.get("shock_dx_over_c"),
            }
        )
    return rows, report


def _plot_convergence(
    evidence: QualificationEvidence, runs: list[RunEvidence], output: Path
) -> int:
    histories = []
    for run in runs:
        if run.status != "FINAL_ACCEPTED" or run.log is None:
            continue
        text = evidence.ledger.read_text(run.log)
        history = parse_adflow_history(text)
        if history:
            histories.append((run, history))
    if not histories:
        return 0
    figure, axes = plt.subplots(2, 2, figsize=(10.0, 7.0), sharex=True)
    colours = {-2.0: BLUE, 0.0: GREEN, 4.0: ORANGE, 8.0: PURPLE}
    for run, history in histories:
        alpha = float(run.row["alpha_deg"])
        style = "-" if run.row["grid_level"] == "gci_M" else "--"
        label = f"{run.row['grid_level']}, alpha={alpha:g} deg"
        iteration = [entry["iteration"] for entry in history]
        colour = colours.get(alpha, GREY)
        axes[0, 0].semilogy(
            iteration,
            np.maximum([entry["relative_residual"] for entry in history], 1e-16),
            style,
            color=colour,
            label=label,
        )
        for axis, key in zip(
            (axes[0, 1], axes[1, 0], axes[1, 1]), ("cl", "cd", "cmy"), strict=True
        ):
            axis.plot(iteration, [entry[key] for entry in history], style, color=colour)
    axes[0, 0].set_ylabel("Relative total residual")
    axes[0, 1].set_ylabel(r"$C_L$")
    axes[1, 0].set_ylabel(r"$C_D$")
    axes[1, 1].set_ylabel(r"$C_{M_y}$")
    for axis in axes[1]:
        axis.set_xlabel("Nonlinear iteration")
    for axis in axes.flat:
        axis.grid(True, alpha=0.22)
    axes[0, 0].legend(fontsize=7, ncol=2)
    figure.tight_layout()
    _save_figure(figure, output / "convergence_histories")
    return len(histories)


def _plot_refinement(rows: list[dict[str, Any]], output: Path) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(10.0, 3.35))
    for axis, quantity in zip(axes, ("CL", "CD", "CMy"), strict=True):
        selected = [row for row in rows if row["quantity"] == quantity]
        alpha = [row["alpha_deg"] for row in selected]
        axis.plot(
            alpha, [row["coarse_value"] for row in selected], "o--", color=ORANGE, label="gci_C"
        )
        axis.plot(alpha, [row["fine_value"] for row in selected], "s-", color=BLUE, label="gci_M")
        axis.set(xlabel="Angle of attack (deg)", ylabel=rf"${quantity.replace('My', 'M_y')}$")
        axis.grid(True, alpha=0.22)
    axes[0].legend()
    figure.suptitle("Two-level refinement trend (not an observed-order GCI)", fontsize=11)
    figure.tight_layout()
    _save_figure(figure, output / "grid_refinement_trend")


def _plot_mesh_distributions(records: list[dict[str, Any]], output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(9.0, 6.5))
    definitions = (
        ("min_cell_over_s0", r"Minimum cell / $s_0$"),
        ("worst_le_turn_per_cell_deg", "Worst LE turn per cell (deg)"),
        ("outboard_span_growth", "Outboard span growth"),
        ("min_cell_volume_m3", r"Minimum cell volume ($m^3$)"),
    )
    for axis, (name, label) in zip(axes.flat, definitions, strict=True):
        values = [record[name] for record in records if record.get(name) is not None]
        axis.hist(values, bins=min(16, max(5, int(np.sqrt(len(values))))), color=BLUE, alpha=0.82)
        axis.set_xlabel(label)
        axis.set_ylabel("Geometries")
        axis.grid(True, axis="y", alpha=0.2)
        if name == "min_cell_volume_m3":
            axis.set_xscale("log")
    figure.tight_layout()
    _save_figure(figure, output / "mesh_quality_distributions")


def _plot_onera(report: dict[str, Any], output: Path) -> None:
    stations = report.get("stations") or []
    if not stations:
        return
    figure, axes = plt.subplots(2, 4, figsize=(12.0, 6.2), sharex=True, sharey=True)
    for axis, station in zip(axes.flat, stations, strict=False):
        experiment, cfd = station["experiment"], station["cfd"]
        upper = np.asarray(experiment.get("upper", [True] * len(experiment["cp"])), dtype=bool)
        x_exp, cp_exp = np.asarray(experiment["x_over_c"]), np.asarray(experiment["cp"])
        axis.scatter(
            x_exp[upper],
            cp_exp[upper],
            s=10,
            facecolors="none",
            edgecolors=ORANGE,
            label="Experiment",
        )
        axis.scatter(x_exp[~upper], cp_exp[~upper], s=10, marker="x", color=ORANGE)
        axis.plot(cfd["x_over_c"], cfd["cp"], color=BLUE, linewidth=1.1, label="CFD")
        axis.set_title(rf"$\eta={station['eta']:.2f}$", fontsize=9)
        axis.grid(True, alpha=0.2)
    for axis in axes.flat[len(stations) :]:
        axis.axis("off")
    for axis in axes[-1]:
        axis.set_xlabel(r"$x/c$")
    for axis in axes[:, 0]:
        axis.set_ylabel(r"$C_p$")
    axes[0, 0].invert_yaxis()
    axes[0, 0].legend(fontsize=8)
    figure.tight_layout()
    _save_figure(figure, output / "onera_m6_cp")


def _plot_failure_evidence(evidence: QualificationEvidence, output: Path) -> list[dict[str, Any]]:
    before = evidence.report("s8_robustness_screen.json")
    after = evidence.report("s8_robustness_screen_final.json")
    s6 = evidence.report("m2_grid_screen_terminal_report.json")
    old_records, new_records = before.get("records") or [], after.get("records") or []
    old_failed = sum(record.get("negative_cells", 0) > 0 for record in old_records)
    new_failed = sum(record.get("negative_cells", 0) > 0 for record in new_records)
    rows = [
        {
            "strategy_or_state": "S8 transported frame (superseded)",
            "cohort": before.get("set_name"),
            "sample_count": len(old_records),
            "invalid_meshes": old_failed,
            "comparable_rate": True,
            "status": "MEASURED",
        },
        {
            "strategy_or_state": "S8 span-normal frame (final)",
            "cohort": after.get("set_name"),
            "sample_count": len(new_records),
            "invalid_meshes": new_failed,
            "comparable_rate": True,
            "status": "MEASURED",
        },
        {
            "strategy_or_state": "S6 bounded atlas",
            "cohort": "qualification candidate, not lhs100 cohort",
            "sample_count": None,
            "invalid_meshes": None,
            "comparable_rate": False,
            "status": s6.get("status", "NOT_MEASURED_ON_COMPARABLE_COHORT"),
        },
    ]
    figure, axes = plt.subplots(1, 2, figsize=(9.2, 3.8))
    rates = [100.0 * old_failed / len(old_records), 100.0 * new_failed / len(new_records)]
    axes[0].bar(["Superseded\nframe", "Final\nframe"], rates, color=[ORANGE, GREEN])
    axes[0].set(ylabel="Invalid meshes (%)", title="Measured S8 frame correction")
    axes[0].set_ylim(0, max(20.0, max(rates) * 1.25))
    for index, (rate, count) in enumerate(zip(rates, (old_failed, new_failed), strict=True)):
        axes[0].text(index, rate + 0.7, f"{count}/100", ha="center")
    axes[0].grid(True, axis="y", alpha=0.2)
    axes[1].axis("off")
    axes[1].text(0.5, 0.68, "S6 vs S8 failure rate: N/A", ha="center", fontsize=12, weight="bold")
    axes[1].text(
        0.5,
        0.43,
        "S6 has a terminal qualification NO-GO,\n"
        "but no matching 100-geometry cohort.\n"
        "A percentage comparison would be misleading.",
        ha="center",
        va="center",
        fontsize=10,
    )
    figure.tight_layout()
    _save_figure(figure, output / "s6_vs_s8_failure_evidence")
    return rows


def build_paper_package(evidence: QualificationEvidence, output: Path) -> dict[str, Any]:
    output = Path(output).resolve()
    tables, figures = output / "tables", output / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 300,
        }
    )

    runs = evidence.runs()
    inventory = _run_inventory(runs)
    _write_table_pair(
        tables,
        "run_inventory",
        inventory,
        tuple(inventory[0]),
        "Archived CFD run evidence and completion classification.",
    )
    convergence = _convergence_rows(runs)
    _write_table_pair(
        tables,
        "convergence",
        convergence,
        tuple(convergence[0]),
        "Convergence-gate results; process exit alone is never acceptance.",
    )
    costs = _cost_rows(evidence, runs)
    _write_table_pair(
        tables,
        "computational_cost_memory",
        costs,
        tuple(costs[0]),
        "Measured wall time and peak aggregate rank memory.",
    )
    refinement = _refinement_rows(runs)
    _write_table_pair(
        tables,
        "gci_refinement",
        refinement,
        tuple(refinement[0]),
        "Two-level refinement evidence. Observed order and GCI are intentionally absent.",
    )

    mesh_records = _mesh_records(evidence)
    mesh_columns = tuple(mesh_records[0])
    write_csv(tables / "mesh_quality_100.csv", mesh_records, mesh_columns)
    mesh_statistics = _mesh_statistics(mesh_records)
    _write_table_pair(
        tables,
        "mesh_quality_statistics",
        mesh_statistics,
        tuple(mesh_statistics[0]),
        "Distribution statistics over the 100-geometry development mesh screen.",
    )
    robustness = _robustness_rows(evidence, mesh_records)
    _write_table_pair(
        tables,
        "development_and_holdout",
        robustness,
        tuple(robustness[0]),
        "Development robustness and holdout-lock status.",
    )
    pilots = _pilot_rows(evidence, mesh_records)
    _write_table_pair(
        tables,
        "pilot_status",
        pilots,
        tuple(pilots[0]),
        "Pilot geometry selection, mesh outcome, and current CFD availability.",
    )
    onera_rows, onera_report = _onera_rows(evidence)
    _write_table_pair(
        tables,
        "onera_m6_stations",
        onera_rows,
        tuple(onera_rows[0]),
        "ONERA M6 pressure-comparison metrics by span station.",
    )
    failure_rows = _plot_failure_evidence(evidence, figures)
    _write_table_pair(
        tables,
        "strategy_failure_evidence",
        failure_rows,
        tuple(failure_rows[0]),
        "Available failure evidence; S6 and S8 rates are not treated as comparable.",
    )

    histories = _plot_convergence(evidence, runs, figures)
    _plot_refinement(refinement, figures)
    _plot_mesh_distributions(mesh_records, figures)
    _plot_onera(onera_report, figures)
    evidence.ledger.verify_unchanged()

    status_counts = Counter(run.status for run in runs)
    limitations = [
        "Only two grid levels are archived, so observed order and formal GCI are not identifiable.",
        "The holdout remains locked and was not read; no holdout statistics are fabricated.",
        "S6 lacks a matching 100-geometry screen, so no S6-vs-S8 failure-rate claim is made.",
        "Pilot CFD outcomes are not present in the trusted dataset; mesh outcomes are "
        "reported separately.",
    ]
    summary_lines = [
        "# Paper-1 generated evidence package",
        "",
        f"Generated: {utc_now()}",
        "",
        f"Runs classified: {len(runs)}; final accepted: {status_counts['FINAL_ACCEPTED']}; "
        f"incomplete: {status_counts['INCOMPLETE']}; integrity errors: "
        f"{status_counts['INTEGRITY_ERROR']}.",
        f"Convergence histories parsed: {histories}.",
        f"Development mesh screen: {len(mesh_records)} geometries.",
        "",
        "## Scientific limitations",
        "",
        *[f"- {item}" for item in limitations],
        "",
    ]
    atomic_write_text(output / "SUMMARY.md", "\n".join(summary_lines))
    manifest = {
        "schema_version": "aeris.paper1_package.v1",
        "created_utc": utc_now(),
        "qualification_root": str(evidence.root),
        "run_status_counts": dict(status_counts),
        "convergence_histories": histories,
        "mesh_development_count": len(mesh_records),
        "holdout_contents_read": False,
        "scientific_limitations": limitations,
        "source_inputs": evidence.ledger.manifest(evidence.repo),
    }
    manifest["outputs"] = output_manifest(output, exclude={"MANIFEST.json"})
    write_json(output / "MANIFEST.json", manifest)
    return manifest
