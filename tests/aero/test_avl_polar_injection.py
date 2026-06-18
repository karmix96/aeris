"""Unit tests for AVL CDCL polar injection."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aeris.airfoil.polar_store import AirfoilPolarStore, CdclParams
from aeris.airfoil.section_map import SectionAirfoilMap
from aeris.aero.solvers.avl_polar_injection import (
    _is_zero_cdcl_line,
    _kinematic_viscosity,
    _process_avl_text,
    inject_polar_cdcl,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path, airfoil_id: str = "foil_abc") -> AirfoilPolarStore:
    rows = []
    for alpha, cl, cd in [
        (-4.0, -0.20, 0.020), (-2.0, 0.00, 0.012), (0.0, 0.20, 0.009),
        (2.0, 0.40, 0.010), (4.0, 0.60, 0.012), (6.0, 0.80, 0.016),
        (8.0, 0.95, 0.025),
    ]:
        rows.append({
            "airfoil_id": airfoil_id, "airfoil_name": "Test",
            "alpha_deg": alpha, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": cl, "cd": cd, "cm": -0.05,
            "converged": True, "solver_id": "xfoil_python",
        })
    csv = tmp_path / "curated_airfoil_dataset.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    return AirfoilPolarStore(csv)


_SIMPLE_AVL = """\
test_wing
#Mach
0.0
#IYsym   IZsym   Zsym
0   0   0.0
#Sref    Cref    Bref
20.0  2.0  10.0
#Xref    Yref    Zref
0.0  0.0  0.0

SURFACE
BWB
12   1
YDUPLICATE
0
CDCL
#CL1  CD1  CL2  CD2  CL3  CD3
0 0 0 0 0 0

SECTION
#Xle    Yle    Zle     Chord   Ainc
0 0 0 2.8 0
AFIL
/tmp/test.af0
CLAF
1.092
CDCL
#CL1  CD1  CL2  CD2  CL3  CD3
0 0 0 0 0 0

SECTION
#Xle    Yle    Zle     Chord   Ainc
0 2.5 0 2.0 0
AFIL
/tmp/test.af1
CLAF
1.090
CDCL
#CL1  CD1  CL2  CD2  CL3  CD3
0 0 0 0 0 0
"""


# ---------------------------------------------------------------------------
# _is_zero_cdcl_line
# ---------------------------------------------------------------------------

def test_is_zero_cdcl_line_all_zeros():
    assert _is_zero_cdcl_line("0 0 0 0 0 0") is True


def test_is_zero_cdcl_line_nonzero():
    assert _is_zero_cdcl_line("-0.5 0.02 0.2 0.008 1.0 0.025") is False


def test_is_zero_cdcl_line_wrong_length():
    assert _is_zero_cdcl_line("0 0 0 0 0") is False
    assert _is_zero_cdcl_line("0 0 0 0 0 0 0") is False


def test_is_zero_cdcl_line_with_floats():
    assert _is_zero_cdcl_line("0.0 0.0 0.0 0.0 0.0 0.0") is True


# ---------------------------------------------------------------------------
# _kinematic_viscosity
# ---------------------------------------------------------------------------

def test_kinematic_viscosity_sea_level():
    nu = _kinematic_viscosity(0.0)
    assert 1.0e-5 < nu < 2.0e-5   # ISA sea-level ≈ 1.46e-5 m²/s


def test_kinematic_viscosity_increases_with_altitude():
    nu_low = _kinematic_viscosity(0.0)
    nu_high = _kinematic_viscosity(5000.0)
    assert nu_high > nu_low   # kinematic viscosity increases with altitude (rho drops faster than mu)


# ---------------------------------------------------------------------------
# _process_avl_text
# ---------------------------------------------------------------------------

def test_process_avl_text_replaces_section_cdcl(tmp_path):
    store = _make_store(tmp_path)
    section_map = SectionAirfoilMap.from_single("foil_abc", semispan_m=5.0)

    modified, n = _process_avl_text(
        _SIMPLE_AVL, section_map, store,
        velocity_mps=30.0, mach=0.0, nu=1.46e-5
    )

    # Both section-level CDCL lines should be replaced
    assert n == 2

    # Surface-level CDCL (first CDCL) should still be zeros
    lines = modified.split("\n")
    cdcl_data_lines = []
    prev_was_cdcl = False
    for line in lines:
        stripped = line.strip()
        if stripped.upper() == "CDCL":
            prev_was_cdcl = True
            continue
        if prev_was_cdcl and stripped.startswith("#"):
            continue   # skip comment
        if prev_was_cdcl and stripped:
            cdcl_data_lines.append(stripped)
            prev_was_cdcl = False

    # Should have 3 CDCL data lines total: 1 surface + 2 section
    assert len(cdcl_data_lines) == 3
    # Surface-level stays as zeros
    assert cdcl_data_lines[0] == "0 0 0 0 0 0"
    # Section-level lines were replaced
    for data_line in cdcl_data_lines[1:]:
        assert data_line != "0 0 0 0 0 0"
        parts = data_line.split()
        assert len(parts) == 6
        assert float(parts[3]) > 0   # cd_min > 0


def test_process_avl_text_leaves_nonzero_cdcl_alone(tmp_path):
    store = _make_store(tmp_path)
    section_map = SectionAirfoilMap.from_single("foil_abc", semispan_m=5.0)

    real_cdcl = "-0.5 0.02  0.2 0.008  1.0 0.025"
    avl_with_real = _SIMPLE_AVL.replace(
        "SECTION\n#Xle    Yle    Zle     Chord   Ainc\n0 0 0 2.8 0\nAFIL\n/tmp/test.af0\nCLAF\n1.092\nCDCL\n#CL1  CD1  CL2  CD2  CL3  CD3\n0 0 0 0 0 0",
        f"SECTION\n#Xle    Yle    Zle     Chord   Ainc\n0 0 0 2.8 0\nAFIL\n/tmp/test.af0\nCLAF\n1.092\nCDCL\n#CL1  CD1  CL2  CD2  CL3  CD3\n{real_cdcl}",
    )
    modified, n = _process_avl_text(
        avl_with_real, section_map, store,
        velocity_mps=30.0, mach=0.0, nu=1.46e-5
    )
    # Only the second section (zeros) should be replaced
    assert n == 1
    assert real_cdcl in modified   # first section's real values preserved


def test_process_avl_text_unknown_airfoil_leaves_zeros(tmp_path):
    store = _make_store(tmp_path, airfoil_id="different_foil")
    # Map to an airfoil NOT in the store
    section_map = SectionAirfoilMap.from_single("foil_abc", semispan_m=5.0)

    modified, n = _process_avl_text(
        _SIMPLE_AVL, section_map, store,
        velocity_mps=30.0, mach=0.0, nu=1.46e-5
    )
    assert n == 0
    # All section CDCL lines still zeros
    assert modified.count("0 0 0 0 0 0") == 3


# ---------------------------------------------------------------------------
# inject_polar_cdcl (file-level)
# ---------------------------------------------------------------------------

def test_inject_polar_cdcl_modifies_file(tmp_path):
    avl_path = tmp_path / "test.avl"
    avl_path.write_text(_SIMPLE_AVL, encoding="utf-8")

    store = _make_store(tmp_path)
    section_map = SectionAirfoilMap.from_single("foil_abc", semispan_m=5.0)

    n = inject_polar_cdcl(
        avl_path, section_map, store,
        velocity_mps=30.0, mach=0.0, altitude_m=0.0
    )
    assert n == 2
    content = avl_path.read_text()
    # Section-level zeros replaced; file actually changed
    section_cdcl_zeros = content.count("0 0 0 0 0 0")
    assert section_cdcl_zeros == 1   # only surface-level remains


def test_inject_polar_cdcl_no_change_when_no_match(tmp_path):
    avl_path = tmp_path / "test.avl"
    avl_path.write_text(_SIMPLE_AVL, encoding="utf-8")
    original_mtime = avl_path.stat().st_mtime

    store = _make_store(tmp_path, airfoil_id="other_id")
    section_map = SectionAirfoilMap.from_single("foil_abc", semispan_m=5.0)

    n = inject_polar_cdcl(avl_path, section_map, store, velocity_mps=30.0)
    assert n == 0
    # File not modified when nothing was replaced
    assert avl_path.stat().st_mtime == original_mtime


# ---------------------------------------------------------------------------
# SectionAirfoilMap — basic tests
# ---------------------------------------------------------------------------

def test_section_map_from_single():
    m = SectionAirfoilMap.from_single("foil_x", semispan_m=5.0)
    assert m.get_airfoil_id(0.0) == "foil_x"
    assert m.get_airfoil_id(4.9) == "foil_x"
    assert m.get_airfoil_id(5.0) == "foil_x"


def test_section_map_from_segments():
    from aeris.generators.bwb_segmented_v1.params import SegmentAirfoilConfig
    segs = [
        SegmentAirfoilConfig(airfoil_id="inboard", y_frac_end=0.4),
        SegmentAirfoilConfig(airfoil_id="tip",     y_frac_end=1.0),
    ]
    m = SectionAirfoilMap.from_segments(segs, library_root=None, semispan_m=10.0)
    assert m.get_airfoil_id(0.0) == "inboard"
    assert m.get_airfoil_id(3.9) == "inboard"
    assert m.get_airfoil_id(4.0) == "inboard"   # boundary inclusive
    assert m.get_airfoil_id(4.1) == "tip"
    assert m.get_airfoil_id(9.9) == "tip"


def test_section_map_three_segments():
    from aeris.generators.bwb_segmented_v1.params import SegmentAirfoilConfig
    segs = [
        SegmentAirfoilConfig(airfoil_id="root",    y_frac_end=0.3),
        SegmentAirfoilConfig(airfoil_id="mid",     y_frac_end=0.7),
        SegmentAirfoilConfig(airfoil_id="tip",     y_frac_end=1.0),
    ]
    m = SectionAirfoilMap.from_segments(segs, library_root=None, semispan_m=6.0)
    assert m.get_airfoil_id(1.0) == "root"
    assert m.get_airfoil_id(3.0) == "mid"
    assert m.get_airfoil_id(5.0) == "tip"


def test_section_map_no_library_coords_returns_none():
    m = SectionAirfoilMap.from_single("no_lib_foil", semispan_m=5.0)
    assert m.get_coordinates(2.5) is None
    assert m.get_t_c(2.5) is None
