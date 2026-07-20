"""
SU2 output parsing: ``history.csv`` → normalized convergence + forces.

SU2 writes a CSV history with quoted column names like ``"Inner_Iter"``,
``"rms[Rho]"``, ``"CL"``, ``"CD"``.  The density residual column is
log10-valued (unlike ADflow's absolute residuals); ``orders_dropped`` is
therefore first-minus-last directly.
"""

from __future__ import annotations

import csv
from pathlib import Path


def _clean(name: str) -> str:
    return name.strip().strip('"').strip()


def parse_history_csv(path: Path) -> dict[str, object]:
    """Parse SU2 history.csv into convergence metrics + final coefficients."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            headers = [_clean(name) for name in next(reader)]
        except StopIteration:
            return {"iterations": 0, "resrho_log10": [], "final_coefficients": {}}
        rows = [row for row in reader if len(row) == len(headers)]

    columns: dict[str, list[float]] = {name: [] for name in headers}
    for row in rows:
        for name, token in zip(headers, row):
            try:
                columns[name].append(float(token))
            except ValueError:
                columns[name].append(float("nan"))

    rho_key = next((name for name in headers if name.lower() == "rms[rho]"), None)
    resrho = columns.get(rho_key, []) if rho_key else []

    final_coefficients: dict[str, float] = {}
    if rows:
        for name in headers:
            if name.upper() in {"CL", "CD", "CSF", "CMX", "CMY", "CMZ", "CFX", "CFY", "CFZ"}:
                final_coefficients[name.lower()] = columns[name][-1]

    return {
        "iterations": len(rows),
        "resrho_log10": resrho,
        "final_resrho_log10": resrho[-1] if resrho else None,
        "initial_resrho_log10": resrho[0] if resrho else None,
        "orders_dropped": (resrho[0] - resrho[-1]) if len(resrho) >= 2 else None,
        "final_coefficients": final_coefficients,
    }
