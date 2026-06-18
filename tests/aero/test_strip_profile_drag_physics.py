"""
Physics validation for _compute_strip_profile_drag.

These tests verify the integration formula against known analytical results,
not just that "the code does what the code intends."

Reference case: flat rectangular wing, span b, chord c, uniform cl everywhere.

For a symmetric wing where AVL writes BOTH halves in strips.txt:
    CD_profile = 2 × Σ_half(cd_2d × area_i) / S_ref_full
               = 2 × (cd_2d × S_half) / S_full
               = cd_2d   ✓

For a half-wing model where AVL writes ONE half only:
    CD_profile = 1 × Σ_half(cd_2d × area_i) / S_ref_full
               = cd_2d × S_half / S_full
               = cd_2d / 2
    This is physically correct: with only half the strip data, using the full
    planform area as S_ref gives half the drag.  In AERIS all wings are
    symmetric (YDUPLICATE) so AVL always writes both halves — the half-wing
    case is validated here only to confirm the symmetry-detection logic.

Physical checks:
  - factor-of-2 symmetry (most common silent bug)
  - area integration vs chord×Δy reconstruction
  - linearity: doubling cd_2d must double CD_profile
  - extrapolation flag fires when cl > polar cl_max
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aeris.airfoil.polar_store import AirfoilPolarStore
from aeris.airfoil.section_map import SectionAirfoilMap
from aeris.aero.solvers.aerosandbox_avl import _compute_strip_profile_drag


# ---------------------------------------------------------------------------
# Test-fixture constants (easy to hand-verify)
# ---------------------------------------------------------------------------
_FOIL_ID = "uniform_foil"
_CD_2D   = 0.012   # known 2D profile drag at operating cl
_CL_OP   = 0.40    # operating cl
_SPAN    = 10.0    # m total span (semispan = 5 m)
_CHORD   = 1.5     # m constant chord
_S_REF   = _SPAN * _CHORD   # = 15.0 m² (full planform)


def _polar_csv(directory: Path, cd_min: float = _CD_2D) -> Path:
    """Write a clean parabolic polar centred at cl=_CL_OP with cd_min."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "airfoil_id": _FOIL_ID, "airfoil_name": "Uniform",
            "alpha_deg": float(cl * 10), "reynolds": 1e6, "mach": 0.0,
            "ncrit": 9.0, "cl": float(cl),
            "cd": float(cd_min + 0.02 * (cl - _CL_OP) ** 2),
            "cm": -0.05, "converged": True, "solver_id": "xfoil_python",
        }
        for cl in np.linspace(-0.4, 1.2, 17)
    ]
    csv = directory / "curated_airfoil_dataset.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    return csv


def _strips_both_sides(n: int = 20, cl: float = _CL_OP) -> pd.DataFrame:
    """Strips for a symmetric wing — both semi-wings present (as AVL writes them)."""
    semispan = _SPAN / 2
    strip_area = _CHORD * (semispan / n)
    y_right = np.linspace(0.0, semispan, n)
    y_left = -y_right[1:]   # exclude root duplicate
    y_all = np.sort(np.concatenate([y_left, y_right]))
    return pd.DataFrame({
        "y_le": y_all,
        "chord": _CHORD,
        "area": strip_area,
        "cl_local": cl,
    })


def _strips_half_wing(n: int = 20, cl: float = _CL_OP) -> pd.DataFrame:
    """Strips for a half-wing model — only y ≥ 0."""
    semispan = _SPAN / 2
    strip_area = _CHORD * (semispan / n)
    y_vals = np.linspace(0.0, semispan, n)
    return pd.DataFrame({
        "y_le": y_vals,
        "chord": _CHORD,
        "area": strip_area,
        "cl_local": cl,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_symmetric_wing_cd_profile_equals_2d_cd(tmp_path):
    """
    PRIMARY PHYSICS TEST.

    Rectangular wing, uniform cl = cl_op, both semi-wings in strips.txt:
        CD_profile = cd_2d(cl_op)   — exact by definition.

    This catches:
      - factor-of-2 error (would give cd_2d/2)
      - strip-area integration bug (would give wrong absolute value)
      - sign errors or off-by-one in symmetry detection
    """
    store = AirfoilPolarStore(_polar_csv(tmp_path))
    section_map = SectionAirfoilMap.from_single(_FOIL_ID, semispan_m=_SPAN / 2)

    cd_prof, n_extrap = _compute_strip_profile_drag(
        strips_df=_strips_both_sides(n=20),
        section_map=section_map,
        polar_store=store,
        s_ref=_S_REF,
        velocity_mps=30.0,
        mach=0.0,
        altitude_m=0.0,
    )

    assert cd_prof is not None, "cd_profile is None — check required column names"
    assert n_extrap == 0, f"Unexpected extrapolated strips: {n_extrap}"
    assert cd_prof == pytest.approx(_CD_2D, rel=0.01), (
        f"CD_profile = {cd_prof:.6f}, expected {_CD_2D:.6f}. "
        "A value of ~cd_2d/2 indicates a factor-of-2 symmetry bug."
    )


def test_half_wing_model_gives_half_cd(tmp_path):
    """
    Half-wing model (only y≥0 strips) with full S_ref gives cd_2d/2 by design.

    This is *correct* behaviour: strip areas cover only one half of the reference
    area.  In AERIS, AVL always writes both halves (YDUPLICATE), so this case
    confirms symmetry detection rather than exposing a bug.
    """
    store = AirfoilPolarStore(_polar_csv(tmp_path))
    section_map = SectionAirfoilMap.from_single(_FOIL_ID, semispan_m=_SPAN / 2)

    cd_prof, _ = _compute_strip_profile_drag(
        strips_df=_strips_half_wing(n=20),
        section_map=section_map,
        polar_store=store,
        s_ref=_S_REF,       # full reference area, but only half covered
        velocity_mps=30.0,
        mach=0.0,
        altitude_m=0.0,
    )

    assert cd_prof is not None
    # No symmetry doubling → result is exactly half of cd_2d
    assert cd_prof == pytest.approx(_CD_2D / 2, rel=0.01), (
        f"Half-wing with full S_ref should give cd_2d/2 = {_CD_2D/2:.6f}, "
        f"got {cd_prof:.6f}"
    )


def test_symmetric_and_half_wing_agree_when_s_ref_halved(tmp_path):
    """
    Half-wing + s_ref=S_half gives the same CD_profile as symmetric + s_ref=S_full.

    This verifies the symmetry-detection logic is applied once and only once.
    """
    store = AirfoilPolarStore(_polar_csv(tmp_path))
    section_map = SectionAirfoilMap.from_single(_FOIL_ID, semispan_m=_SPAN / 2)

    cd_sym, _ = _compute_strip_profile_drag(
        _strips_both_sides(n=20), section_map, store,
        s_ref=_S_REF, velocity_mps=30.0, mach=0.0, altitude_m=0.0
    )
    cd_half, _ = _compute_strip_profile_drag(
        _strips_half_wing(n=20), section_map, store,
        s_ref=_S_REF / 2,  # half planform reference
        velocity_mps=30.0, mach=0.0, altitude_m=0.0
    )

    assert cd_sym is not None and cd_half is not None
    assert cd_sym == pytest.approx(cd_half, rel=0.02), (
        f"Symmetric/full-S ({cd_sym:.6f}) and half-wing/half-S ({cd_half:.6f}) should agree"
    )


def test_cd_profile_scales_linearly_with_cd_2d(tmp_path):
    """Doubling cd_2d must double CD_profile (linearity check)."""
    store_lo = AirfoilPolarStore(_polar_csv(tmp_path / "lo", cd_min=0.008))
    store_hi = AirfoilPolarStore(_polar_csv(tmp_path / "hi", cd_min=0.016))

    section_map = SectionAirfoilMap.from_single(_FOIL_ID, semispan_m=_SPAN / 2)
    strips = _strips_both_sides(n=20)

    cd_lo, _ = _compute_strip_profile_drag(strips, section_map, store_lo, _S_REF, 30.0, 0.0, 0.0)
    cd_hi, _ = _compute_strip_profile_drag(strips, section_map, store_hi, _S_REF, 30.0, 0.0, 0.0)

    assert cd_lo is not None and cd_hi is not None
    assert cd_hi / cd_lo == pytest.approx(2.0, rel=0.03), (
        f"CD scaling: expected ratio 2.0, got {cd_hi / cd_lo:.4f}"
    )


def test_missing_area_column_returns_none(tmp_path):
    """Missing 'area' column → (None, 0) not a silent zero."""
    store = AirfoilPolarStore(_polar_csv(tmp_path))
    section_map = SectionAirfoilMap.from_single(_FOIL_ID, semispan_m=_SPAN / 2)
    strips_no_area = _strips_both_sides().drop(columns=["area"])

    cd_prof, n_extrap = _compute_strip_profile_drag(
        strips_no_area, section_map, store, _S_REF, 30.0, 0.0, 0.0
    )
    assert cd_prof is None
    assert n_extrap == 0


def test_extrapolated_strips_counted_when_cl_exceeds_polar_max(tmp_path):
    """Strips with cl > polar cl_max increment n_extrapolated_strips."""
    store = AirfoilPolarStore(_polar_csv(tmp_path))
    section_map = SectionAirfoilMap.from_single(_FOIL_ID, semispan_m=_SPAN / 2)

    # Polar cl_max ≈ 1.2; force cl = 2.5 to trigger flag on all strips
    strips = _strips_both_sides(cl=2.5)
    _, n_extrap = _compute_strip_profile_drag(
        strips, section_map, store, _S_REF, 30.0, 0.0, 0.0
    )
    assert n_extrap > 0, (
        "Expected extrapolated strip count > 0 when cl=2.5 exceeds polar cl_max ≈ 1.2"
    )


def test_no_extrapolation_within_polar_range(tmp_path):
    """No strips flagged when cl is within the polar's covered range."""
    store = AirfoilPolarStore(_polar_csv(tmp_path))
    section_map = SectionAirfoilMap.from_single(_FOIL_ID, semispan_m=_SPAN / 2)

    _, n_extrap = _compute_strip_profile_drag(
        _strips_both_sides(cl=_CL_OP), section_map, store, _S_REF, 30.0, 0.0, 0.0
    )
    assert n_extrap == 0
