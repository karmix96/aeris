"""
ADflow output parsing: monitor history and run-report normalization.

Legacy monitor row layout (verified against ANK and NK solves):

    Grid  Iter  IterTot  IterType  CFL  Step  LinRes  Res_rho  Res_turb  CL  CD  totalRes

The governed canary requests the expanded layout:

    Grid Iter IterTot IterType CFL Step LinRes Res_rho Res_rhou Res_rhov
    Res_rhow Res_rhoE Res_nuturb CL CD CDp CDv CMy totalRes

The columns are positional. In NK rows CFL is ----, so collecting only numeric
tokens shifts later columns and silently corrupts the history. This parser
recognizes both layouts and retains every expanded native monitor value.
"""

from __future__ import annotations

import math


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def monitor_row_from_line(line: str) -> dict[str, object] | None:
    """Extract one legacy or expanded ADflow monitor row."""
    parts = line.split()
    if len(parts) < 12 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    try:
        row: dict[str, object] = {
            "grid_level": int(parts[0]),
            "iteration": int(parts[1]),
            "iteration_total": int(parts[2]),
            "iteration_type": parts[3],
            "cfl": _optional_float(parts[4]),
            "step": _optional_float(parts[5]),
            "linear_residual": _optional_float(parts[6]),
            "residual_density": float(parts[7]),
        }
        if len(parts) >= 19:
            row.update(
                {
                    "layout": "expanded_components_v1",
                    "residual_momentum_x": float(parts[8]),
                    "residual_momentum_y": float(parts[9]),
                    "residual_momentum_z": float(parts[10]),
                    "residual_energy": float(parts[11]),
                    "residual_sa": float(parts[12]),
                    "cl": float(parts[13]),
                    "cd": float(parts[14]),
                    "cd_pressure": float(parts[15]),
                    "cd_viscous": float(parts[16]),
                    "cmy": float(parts[17]),
                    "total_residual": float(parts[18]),
                }
            )
        else:
            row.update(
                {
                    "layout": "legacy_density_turbulence_forces_v1",
                    "residual_sa": float(parts[8]),
                    "cl": float(parts[9]),
                    "cd": float(parts[10]),
                    "total_residual": float(parts[11]),
                }
            )
        return row
    except ValueError:
        return None


def resrho_from_line(line: str) -> float | None:
    """Extract Res_rho from one ADflow monitor row, else None."""
    row = monitor_row_from_line(line)
    return float(row["residual_density"]) if row is not None else None


def parse_monitor_history(log_text: str) -> dict[str, object]:
    """Extract complete native rows plus the legacy density summary."""
    rows = [
        row
        for row in (monitor_row_from_line(line) for line in log_text.splitlines())
        if row is not None
    ]
    resrho = [float(row["residual_density"]) for row in rows]
    return {
        "iterations": len(resrho),
        "native_monitor_rows": rows,
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
    """Extract (Res_rho, CL, CD) from either monitor layout."""
    row = monitor_row_from_line(line)
    if row is None:
        return None
    try:
        return {
            "resrho": float(row["residual_density"]),
            "cl": float(row["cl"]),
            "cd": float(row["cd"]),
        }
    except (KeyError, TypeError, ValueError):
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
