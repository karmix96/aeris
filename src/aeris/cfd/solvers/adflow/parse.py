"""
ADflow output parsing: monitor history and run-report normalization.

Monitor row layout (verified against ANK and NK solves; the same convention
the GUI live chart uses):

    Grid  Iter  IterTot  IterType  CFL  Step  LinRes  Res_rho  Res_turb  CL  CD  totalRes

The columns are positional. In NK rows CFL is ----, so collecting only
numeric tokens shifts the later columns and silently drops the final Newton
history. Res_rho, CL, and CD are always tokens 7, 9, and 10 respectively.
"""

from __future__ import annotations

import math


def resrho_from_line(line: str) -> float | None:
    """Extract Res_rho from one ADflow monitor row, else None."""
    parts = line.split()
    if len(parts) < 12 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    try:
        return float(parts[7])
    except ValueError:
        return None


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

    Same positional column layout as resrho_from_line.
    """
    parts = line.split()
    if len(parts) < 12 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    try:
        return {
            "resrho": float(parts[7]),
            "cl": float(parts[9]),
            "cd": float(parts[10]),
        }
    except ValueError:
        return None


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
