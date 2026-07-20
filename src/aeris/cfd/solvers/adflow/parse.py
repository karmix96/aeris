"""
ADflow output parsing: monitor history and run-report normalization.

Monitor row layout (verified against a 2026-07-17 smoke solve; the same
convention the GUI live chart uses):

    Grid  Iter  IterTot  IterType  CFL  Step  LinRes  Res_rho  Res_turb  CL  CD  totalRes

After dropping the non-numeric IterType token the float columns are
[IterTot, CFL, Step, LinRes, Res_rho, Res_turb, CL, CD, totalRes], so
Res_rho is floats[4].
"""

from __future__ import annotations

import math


def resrho_from_line(line: str) -> float | None:
    """Extract Res_rho from one ADflow monitor row, else None."""
    parts = line.split()
    if len(parts) < 10 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    floats: list[float] = []
    for token in parts[2:]:
        try:
            floats.append(float(token))
        except ValueError:
            continue
    return floats[4] if len(floats) >= 9 else None


def parse_monitor_history(log_text: str) -> dict[str, object]:
    """Extract the density-residual convergence history from a run log."""
    resrho = [
        value
        for value in (resrho_from_line(line) for line in log_text.splitlines())
        if value is not None
    ]
    return {
        "iterations": len(resrho),
        "resrho": resrho,
        "final_resrho": resrho[-1] if resrho else None,
        "initial_resrho": resrho[0] if resrho else None,
        "orders_dropped": (
            None
            if len(resrho) < 2 or resrho[0] <= 0 or resrho[-1] <= 0
            else math.log10(resrho[0] / resrho[-1])
        ),
    }


def force_row_from_line(line: str) -> dict[str, float] | None:
    """Extract (Res_rho, CL, CD) from one monitor row, else None.

    Same column layout as ``resrho_from_line``: after dropping the
    non-numeric IterType token, floats = [IterTot, CFL, Step, LinRes,
    Res_rho, Res_turb, CL, CD, totalRes] -> CL = floats[6], CD = floats[7].
    """
    parts = line.split()
    if len(parts) < 10 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    floats: list[float] = []
    for token in parts[2:]:
        try:
            floats.append(float(token))
        except ValueError:
            continue
    if len(floats) < 9:
        return None
    return {"resrho": floats[4], "cl": floats[6], "cd": floats[7]}


def parse_force_history(log_text: str) -> list[dict[str, float]]:
    """Full per-iteration (Res_rho, CL, CD) history — the raw material for a
    post-hoc force-vs-convergence-tolerance sensitivity table (no rerun
    needed: every looser stopping criterion is a prefix of a fully-run
    history)."""
    return [
        row
        for row in (force_row_from_line(line) for line in log_text.splitlines())
        if row is not None
    ]
