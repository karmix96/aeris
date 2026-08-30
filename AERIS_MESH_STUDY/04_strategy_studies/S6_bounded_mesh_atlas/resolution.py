"""Frozen S6 mesh-resolution candidates and their validation status."""

from __future__ import annotations

from shared.gates import EPSE_LADDER

S6_FIRST_CELL_FRACTION = {
    "candidate_c01": 6.1e-6,
    "candidate_c02": 4.7e-6,
    "candidate_c03": 3.6e-6,
    "smoke": 8.8e-6,
    "fine": 6.0e-6,
    # The fixed N257/epsE=1.5 development calibration passed all 16 seeds at
    # 3.6e-6. This remains provisional until production CFD verifies y+.
    "production": 3.6e-6,
}

REFERENCE_REYNOLDS = 1.0e6
PRODUCTION_WALL_SPACING_STATUS = "candidate_pending_cfd_yplus_validation"


def first_cell_fraction(level: str) -> float:
    try:
        return S6_FIRST_CELL_FRACTION[level]
    except KeyError as error:
        raise ValueError(f"S6 has no wall-spacing policy for level {level!r}") from error


def epsilon_tag(eps_e: float) -> str:
    """Return the on-disk tag for one value in the governed epsE ladder."""
    if eps_e not in EPSE_LADDER:
        raise ValueError(f"epsE must be in the frozen ladder {EPSE_LADDER}")
    return f"eps{int(round(10.0 * eps_e)):02d}"
