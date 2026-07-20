"""
Airfoil geometry sources for 2-D meshing: NACA 4-digit generator + .dat loader.

The NACA 4-digit thickness equation uses the **closed-trailing-edge**
modification (last coefficient -0.1036 instead of -0.1015), the exact form
used by the NASA Turbulence Modeling Resource for its NACA 0012 validation
cases — matching TMR geometry is a precondition for comparing against TMR
reference solutions (turbmodels.larc.nasa.gov, 2D NACA 0012 case).

``.dat`` files are read in Selig format: one loop, trailing edge → upper
surface → leading edge → lower surface → trailing edge.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def naca4_coordinates(code: str, n_per_surface: int = 100) -> np.ndarray:
    """Selig-ordered (N, 2) coordinates for a NACA 4-digit section, chord 1.

    Cosine x-spacing (clusters LE and TE — the standard airfoil
    discretization).  Closed sharp TE via the -0.1036 coefficient (TMR
    form).  Returns 2*n_per_surface - 1 points: TE -> upper -> LE ->
    lower -> TE.
    """
    if len(code) != 4 or not code.isdigit():
        raise ValueError(f"NACA 4-digit code expected, got {code!r}")
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    t = int(code[2:]) / 100.0
    if n_per_surface < 3:
        raise ValueError("n_per_surface must be >= 3")

    theta = np.linspace(0.0, np.pi, n_per_surface)
    x = 0.5 * (1.0 - np.cos(theta))  # 0 (LE) .. 1 (TE), cosine clustered

    yt = (
        5.0
        * t
        * (
            0.2969 * np.sqrt(x)
            - 0.1260 * x
            - 0.3516 * x**2
            + 0.2843 * x**3
            - 0.1036 * x**4  # closed TE (TMR); classic open form uses -0.1015
        )
    )

    if m == 0.0 or p == 0.0:
        yc = np.zeros_like(x)
        dyc = np.zeros_like(x)
    else:
        yc = np.where(
            x < p,
            m / p**2 * (2.0 * p * x - x**2),
            m / (1.0 - p) ** 2 * ((1.0 - 2.0 * p) + 2.0 * p * x - x**2),
        )
        dyc = np.where(
            x < p,
            2.0 * m / p**2 * (p - x),
            2.0 * m / (1.0 - p) ** 2 * (p - x),
        )
    angle = np.arctan(dyc)

    x_upper = x - yt * np.sin(angle)
    y_upper = yc + yt * np.cos(angle)
    x_lower = x + yt * np.sin(angle)
    y_lower = yc - yt * np.cos(angle)

    # Selig loop: TE -> upper -> LE -> lower -> TE (LE point shared once)
    upper = np.stack([x_upper[::-1], y_upper[::-1]], axis=1)
    lower = np.stack([x_lower[1:], y_lower[1:]], axis=1)
    return np.concatenate([upper, lower], axis=0)


def load_airfoil_dat(path: Path) -> np.ndarray:
    """Load a Selig-format .dat file into (N, 2) coordinates."""
    rows: list[tuple[float, float]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            continue  # header/name line
        rows.append((x, y))
    if len(rows) < 5:
        raise ValueError(f"{path}: not enough coordinate rows for an airfoil")
    coords = np.asarray(rows, dtype=float)
    if np.max(np.abs(coords)) > 10.0:
        raise ValueError(f"{path}: coordinates look unnormalized (max |v| > 10 chords)")
    return coords


def resample_selig_loop(coords: np.ndarray, n_per_surface: int) -> np.ndarray:
    """Resample a Selig loop with cosine x-spacing on each surface.

    Splits the loop at the leading edge (minimum x), interpolates each
    surface in x, and rebuilds the loop with LE/TE-clustered cosine
    stations — giving arbitrary .dat input the same distribution quality
    as the analytic generator.
    """
    coords = np.asarray(coords, dtype=float)
    le_index = int(np.argmin(coords[:, 0]))
    upper = coords[: le_index + 1][::-1]  # LE -> TE (upper)
    lower = coords[le_index:]  # LE -> TE (lower)
    if len(upper) < 3 or len(lower) < 3:
        raise ValueError("cannot split loop at leading edge — check .dat ordering")

    theta = np.linspace(0.0, np.pi, n_per_surface)
    x_lo, x_hi = float(coords[:, 0].min()), float(coords[:, 0].max())
    x_new = x_lo + (x_hi - x_lo) * 0.5 * (1.0 - np.cos(theta))

    def _interp(surface: np.ndarray) -> np.ndarray:
        order = np.argsort(surface[:, 0])
        return np.interp(x_new, surface[order, 0], surface[order, 1])

    y_upper = _interp(upper)
    y_lower = _interp(lower)
    upper_new = np.stack([x_new[::-1], y_upper[::-1]], axis=1)
    lower_new = np.stack([x_new[1:], y_lower[1:]], axis=1)
    return np.concatenate([upper_new, lower_new], axis=0)
