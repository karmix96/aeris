"""
AVL CDCL polar injection.

AeroSandbox writes all-zero CDCL placeholders (``0 0 0 0 0 0``) for every
SECTION in the generated .avl file.  This module parses the written file,
replaces those zeros with real polar-fitted values from the 2D XFOIL library,
and writes the file back before AVL is invoked.

Design
------
- SURFACE-level CDCL (written before the first SECTION keyword) is left
  untouched; it has no effect when every section carries its own CDCL.
- Only SECTION-level CDCL values are replaced.
- If a polar lookup fails for a section (airfoil not in store, insufficient
  data), the zeros are preserved and a warning is logged so the section
  simply contributes no profile drag — a safe conservative fallback.
- Reynolds number per section is estimated from V × chord / ν.

Public API
----------
  inject_polar_cdcl(avl_path, section_map, polar_store, velocity_mps, mach, altitude_m)
    → int   (number of sections actually updated)
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)

# Tokens that start a new AVL block, ending the current section body
_BLOCK_KEYWORDS = frozenset({
    "SURFACE", "BODY", "COMPONENT",
})

# Keywords that begin sub-blocks inside a section
_SECTION_SUBBLOCK_KEYWORDS = frozenset({
    "NSPAN", "SSPACE", "NCHORD", "CSPACE",
    "AFIL", "AFILE", "CLAF", "CDCL",
    "CONTROL", "DESIGN", "NOWAKE", "NOLOAD", "NOALBE",
    "TRANSLATE", "SCALE", "ANGLE",
    "YDUPLICATE", "COMPONENT", "BODYMOVE",
})

_SURFACE_ONLY_SUBBLOCKS = frozenset({
    "NSPAN", "SSPACE", "NCHORD", "CSPACE",
    "YDUPLICATE", "COMPONENT", "BODYMOVE", "TRANSLATE", "SCALE", "ANGLE",
    "NOWAKE", "NOLOAD", "NOALBE",
})


class _SectionInfo(NamedTuple):
    yle: float
    chord: float


def inject_polar_cdcl(
    avl_path: Path,
    section_map,            # SectionAirfoilMap
    polar_store,            # AirfoilPolarStore
    velocity_mps: float,
    mach: float = 0.0,
    altitude_m: float = 0.0,
) -> int:
    """Replace all-zero SECTION-level CDCL blocks with polar-fitted values.

    Reads *avl_path*, modifies in memory, writes back only if ≥1 section was
    updated.  Returns the number of sections updated.

    Args:
        avl_path:       Path to the .avl file already written by AeroSandbox.
        section_map:    SectionAirfoilMap mapping Yle → airfoil_id.
        polar_store:    AirfoilPolarStore providing fit_cdcl().
        velocity_mps:   True airspeed for local Reynolds number estimation.
        mach:           Mach number for polar bin selection.
        altitude_m:     Flight altitude for kinematic viscosity.

    Returns:
        Count of CDCL data lines replaced with real polar data.
    """
    text = avl_path.read_text(encoding="utf-8")
    nu = _kinematic_viscosity(altitude_m)
    modified, n_replaced = _process_avl_text(
        text, section_map, polar_store, velocity_mps, mach, nu
    )
    if n_replaced > 0:
        avl_path.write_text(modified, encoding="utf-8")
        log.debug(
            "avl_polar_injection: updated %d section CDCL blocks in %s",
            n_replaced, avl_path.name,
        )
    else:
        log.debug(
            "avl_polar_injection: no CDCL blocks replaced in %s "
            "(no matching airfoils or no zero placeholders found)",
            avl_path.name,
        )
    return n_replaced


# ---------------------------------------------------------------------------
# Core text processor
# ---------------------------------------------------------------------------

def _process_avl_text(
    text: str,
    section_map,
    polar_store,
    velocity_mps: float,
    mach: float,
    nu: float,
) -> tuple[str, int]:
    """Parse the AVL file text line by line and return (modified_text, n_replaced)."""
    lines = text.split("\n")
    out: list[str] = []
    n_replaced = 0

    # Parser state
    in_surface = False
    in_section = False          # True once the first SECTION keyword is seen within current SURFACE

    # Within section body
    current_yle: float | None = None
    current_chord: float | None = None
    waiting_section_data = False    # True just after SECTION keyword, expecting data line
    waiting_cdcl_data = False       # True just after section-level CDCL keyword

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        # -----------------------------------------------------------------
        # Block boundaries
        # -----------------------------------------------------------------
        if upper == "SURFACE":
            in_surface = True
            in_section = False
            current_yle = None
            current_chord = None
            waiting_section_data = False
            waiting_cdcl_data = False
            out.append(line)
            continue

        if upper == "SECTION":
            in_section = True
            current_yle = None
            current_chord = None
            waiting_section_data = True
            waiting_cdcl_data = False
            out.append(line)
            continue

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            out.append(line)
            continue

        # -----------------------------------------------------------------
        # Detect keywords (no data on keyword lines)
        # -----------------------------------------------------------------
        kw = upper.split()[0] if upper.split() else ""

        if kw == "CDCL":
            if in_section:
                # SECTION-level CDCL — arm the data-line replacer
                waiting_cdcl_data = True
            # else: SURFACE-level CDCL — leave untouched
            waiting_section_data = False
            out.append(line)
            continue

        if kw in _SECTION_SUBBLOCK_KEYWORDS or kw in _BLOCK_KEYWORDS:
            # Any other keyword ends the section-data and cdcl-data pending states
            waiting_section_data = False
            if not waiting_cdcl_data:
                pass  # cdcl state stays until its data line is consumed
            out.append(line)
            continue

        # -----------------------------------------------------------------
        # Data lines
        # -----------------------------------------------------------------
        if waiting_section_data:
            # Parse Yle (field 1) and Chord (field 3) from SECTION data line
            parts = stripped.split()
            if len(parts) >= 4:
                try:
                    current_yle = float(parts[1])
                    current_chord = float(parts[3])
                except (ValueError, IndexError):
                    log.debug("avl_polar_injection: could not parse section data line: %r", line)
            waiting_section_data = False
            out.append(line)
            continue

        if waiting_cdcl_data and in_section:
            # This is the CDCL data line for the current section
            waiting_cdcl_data = False
            replacement = _try_replace_cdcl_line(
                line=line,
                yle=current_yle,
                chord=current_chord,
                section_map=section_map,
                polar_store=polar_store,
                velocity_mps=velocity_mps,
                mach=mach,
                nu=nu,
            )
            if replacement is not None:
                out.append(replacement)
                n_replaced += 1
            else:
                out.append(line)
            continue

        # Default: pass through unchanged
        out.append(line)

    return "\n".join(out), n_replaced


def _try_replace_cdcl_line(
    *,
    line: str,
    yle: float | None,
    chord: float | None,
    section_map,
    polar_store,
    velocity_mps: float,
    mach: float,
    nu: float,
) -> str | None:
    """Return a replacement CDCL data line, or None if the line should not be changed."""
    # Only replace all-zero placeholders
    if not _is_zero_cdcl_line(line.strip()):
        return None

    if yle is None or chord is None:
        log.debug("avl_polar_injection: unknown yle/chord for CDCL line — leaving as zeros")
        return None

    airfoil_id = section_map.get_airfoil_id(yle)
    if airfoil_id is None:
        log.debug("avl_polar_injection: no airfoil_id for Yle=%.4f — leaving as zeros", yle)
        return None

    re = velocity_mps * chord / nu if nu > 0 else 1e6

    params = polar_store.fit_cdcl(airfoil_id, re=re, mach=mach)
    if params is None:
        log.debug(
            "avl_polar_injection: fit_cdcl returned None for %r Re=%.0f Mach=%.2f",
            airfoil_id, re, mach,
        )
        return None

    # Preserve indentation / leading whitespace
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}{params.as_avl_line()}"


def _is_zero_cdcl_line(stripped: str) -> bool:
    """Return True if the stripped line is a zero CDCL placeholder (all tokens = 0)."""
    parts = stripped.split()
    if len(parts) != 6:
        return False
    try:
        return all(float(p) == 0.0 for p in parts)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Atmospheric helper
# ---------------------------------------------------------------------------

def _kinematic_viscosity(altitude_m: float) -> float:
    """Return kinematic viscosity of air [m²/s] at *altitude_m* (ISA model)."""
    # ISA temperature gradient: T = 288.15 - 0.0065 * h  (troposphere, h < 11000 m)
    h = min(float(altitude_m), 10999.0)
    T = 288.15 - 0.0065 * h                        # K
    rho = 1.225 * (T / 288.15) ** 4.256             # kg/m³ (ISA approximation)
    mu = 1.458e-6 * T ** 1.5 / (T + 110.4)         # Pa·s (Sutherland)
    return mu / rho                                  # m²/s
