"""
Solution-verification post-processing.

``grid_convergence_index`` implements the three-grid GCI procedure of
Celik et al., "Procedure for Estimation and Reporting of Uncertainty Due
to Discretization in CFD Applications" (ASME J. Fluids Eng. 130, 2008) —
the procedure ASME V&V 20 builds on and journals commonly require:

1. observed order  p = ln(e32 / e21) / ln(r)   (uniform ratio r)
2. Richardson extrapolate  f_exact ≈ f1 + (f1 - f2) / (r^p - 1)
3. GCI_fine = Fs * |e21 / f1| / (r^p - 1),  Fs = 1.25 for 3-grid studies

The AERIS cap4 family was designed with a near-uniform r ≈ 1.4 in all
three index directions precisely so this procedure applies (mesh presets
docstring / DSE_READINESS §5); the 2-D O-grid ladder follows the same law.

``solve_summary`` normalizes a set of solve_report.json files into one
comparison table — the cross-solver / cross-fidelity artifact.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


def grid_convergence_index(
    f_fine: float,
    f_medium: float,
    f_coarse: float,
    *,
    refinement_ratio: float,
    safety_factor: float = 1.25,
) -> dict[str, float | str]:
    """Three-grid observed order, Richardson extrapolation, and GCI.

    Inputs are a scalar QoI (CL, CD, ...) on the fine/medium/coarse grids of
    a family with (near-)uniform refinement ratio.  Returns NaNs with a
    diagnostic when the sequence is not monotone (oscillatory convergence —
    reportable, but Richardson extrapolation is then not defensible).
    """
    r = float(refinement_ratio)
    if r <= 1.0:
        raise ValueError(f"refinement_ratio must be > 1, got {r}")
    e21 = f_medium - f_fine
    e32 = f_coarse - f_medium
    if e21 == 0.0 or e32 == 0.0 or (e32 / e21) <= 0.0:
        return {
            "observed_order": math.nan,
            "extrapolated": math.nan,
            "gci_fine_percent": math.nan,
            "convergence": (
                "oscillatory" if (e21 == 0 or e32 == 0 or e32 / e21 < 0) else "degenerate"
            ),
        }
    p = math.log(e32 / e21) / math.log(r)
    extrapolated = f_fine + (f_fine - f_medium) / (r**p - 1.0)
    relative_e21 = abs(e21 / f_fine) if f_fine != 0 else abs(e21)
    gci = safety_factor * relative_e21 / (r**p - 1.0)
    return {
        "observed_order": p,
        "extrapolated": extrapolated,
        "gci_fine_percent": 100.0 * gci,
        "convergence": "monotone",
    }


def load_solve_report(path: Path) -> dict[str, object]:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if report.get("schema") != "aeris.cfd.solve_report.v1":
        raise ValueError(f"{path}: not an aeris.cfd.solve_report.v1 file")
    return report


def solve_summary(report_paths: list[Path], labels: list[str] | None = None) -> dict[str, object]:
    """Normalize several solve reports into one comparison table.

    Rows keep solver id, status, flow condition, forces, and final residual —
    the cross-solver (ADflow vs SU2, same grid) and cross-fidelity
    (smoke/fine/production) comparison artifact.
    """
    if labels is not None and len(labels) != len(report_paths):
        raise ValueError("labels must match report_paths length")
    rows: list[dict[str, object]] = []
    for index, path in enumerate(report_paths):
        report = load_solve_report(path)
        convergence = report.get("convergence", {}) or {}
        rows.append(
            {
                "label": labels[index] if labels else Path(path).parent.name,
                "solver": report.get("solver_id"),
                "status": report.get("status"),
                "flow": report.get("flow", {}),
                "forces": report.get("forces", {}),
                "final_resrho": convergence.get(
                    "final_resrho", convergence.get("final_resrho_log10")
                ),
                "iterations": convergence.get("iterations"),
                "report": str(path),
            }
        )
    return {"schema": "aeris.cfd.solve_summary.v1", "rows": rows}


def iterative_tolerance_sensitivity(
    log_path: Path,
    *,
    targets_orders_dropped: tuple[float, ...] = (3.0, 4.0, 5.0, 5.5, 6.0),
) -> dict[str, object]:
    """Post-hoc force-vs-stopping-criterion sensitivity from one ADflow log.

    A run that goes to completion contains, as a byproduct, the answer for
    every *looser* stopping criterion: the CL/CD reported at the iteration
    where the residual first drops N orders is exactly what a run stopped
    at that tolerance would have reported (ADflow's history is monotone in
    iteration, not in residual, so this is a lookup, not an approximation).
    This lets the solver-convergence-criteria sensitivity (rubric 4.6, 4.7,
    DSE_READINESS C6) be reported from existing logs at zero extra compute.
    """
    # local import: keeps this module solver-agnostic except where a caller
    # explicitly asks for ADflow-log parsing
    from aeris.cfd.solvers.adflow.parse import parse_force_history

    log_text = Path(log_path).read_text(encoding="utf-8")
    history = parse_force_history(log_text)
    if not history:
        return {
            "schema": "aeris.cfd.iterative_tolerance_sensitivity.v1",
            "log": str(log_path),
            "rows": [],
        }
    initial_resrho = history[0]["resrho"]
    rows: list[dict[str, object]] = []
    for target in sorted(targets_orders_dropped):
        threshold = initial_resrho / (10.0**target)
        hit = next((row for row in history if row["resrho"] <= threshold), None)
        rows.append(
            {
                "orders_dropped_target": target,
                "reached": hit is not None,
                "iteration": history.index(hit) + 1 if hit else None,
                "cl": hit["cl"] if hit else None,
                "cd": hit["cd"] if hit else None,
                "resrho": hit["resrho"] if hit else None,
            }
        )
    final = history[-1]
    rows.append(
        {
            "orders_dropped_target": None,
            "reached": True,
            "iteration": len(history),
            "cl": final["cl"],
            "cd": final["cd"],
            "resrho": final["resrho"],
            "note": "final iteration reached by the run (not a tolerance target)",
        }
    )
    return {
        "schema": "aeris.cfd.iterative_tolerance_sensitivity.v1",
        "log": str(log_path),
        "initial_resrho": initial_resrho,
        "rows": rows,
    }


def gci_study(
    report_paths_fine_to_coarse: list[Path],
    *,
    quantity: str,
    refinement_ratio: float,
) -> dict[str, object]:
    """GCI on one QoI across a fine→medium→coarse trio of solve reports."""
    if len(report_paths_fine_to_coarse) != 3:
        raise ValueError("GCI needs exactly three reports, ordered fine, medium, coarse")
    values: list[float] = []
    for path in report_paths_fine_to_coarse:
        forces = load_solve_report(path).get("forces", {})
        if quantity not in forces:
            raise ValueError(f"{path}: quantity {quantity!r} not in forces {sorted(forces)}")
        values.append(float(forces[quantity]))
    result = grid_convergence_index(
        values[0], values[1], values[2], refinement_ratio=refinement_ratio
    )
    return {
        "schema": "aeris.cfd.gci_study.v1",
        "quantity": quantity,
        "refinement_ratio": refinement_ratio,
        "values_fine_to_coarse": values,
        **result,
    }
