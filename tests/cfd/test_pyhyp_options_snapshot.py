"""
Golden snapshots of the effective pyHyp options.

These dicts were captured from the behavior of the pre-refactor
``aeris.mesh.pyhyp_runner._build_options`` (two hand-synchronized copies at
the time).  They pin the single-builder refactor to the validated behavior:
any change to these values is a *mesh-recipe change* and must be deliberate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS, build_pyhyp_options
from aeris.mesh.pyhyp_runner import _build_options

CHAR_LEN = 2.27
SURFACE = Path("/tmp/surface/surface.fmt")

# level -> (N, coarsen, s0_frac) — the validated table (DSE_READINESS §5)
LEVEL_TABLE = {
    # S6 M2 bounded-mesh-atlas family; the governed source of truth for the
    # wall-normal count and first-cell fraction is
    # AERIS_MESH_STUDY/05_s6_cfd_qualification/grid_family_candidate_v1.yaml.
    "candidate_c01": (61, 1, 5.0e-6),
    "candidate_c02": (73, 1, 4.7e-6),
    "candidate_c03": (97, 1, 3.6e-6),
    # Candidate D family shares the C family's validated wall-normal law exactly.
    "candidate_d01": (61, 1, 5.0e-6),
    "candidate_d02": (73, 1, 4.7e-6),
    "candidate_d03": (97, 1, 3.6e-6),
    "L1": (257, 4, 4.4e-6),
    "L2": (193, 4, 8.8e-6),
    "L3": (129, 4, 2.2e-5),
    "L4": (37, 4, 2.2e-5),
    "smoke": (129, 1, 8.8e-6),
    "fine": (193, 1, 6.0e-6),
    "production": (257, 1, 4.4e-6),
}

BASE_EXPECTED = {
    "inputFile": str(SURFACE),
    "fileType": "PLOT3D",
    "unattachedEdgesAreSymmetry": True,
    "outerFaceBC": "farfield",
    "autoConnect": True,
    "BC": {},
    "families": "wall",
    "marchDist": 25.0 * CHAR_LEN,
    "ps0": -1.0,
    "pGridRatio": -1.0,
    "cMax": 0.7,
    "theta": 3.0,
    "nConstantStart": 5,
    "volCoef": 0.5,
    "volSmoothIter": 800,
    "volBlend": 0.004,
    "epsE": 4.0,
    "epsI": 8.0,
    "kspRelTol": 1.0e-8,
    "kspMaxIts": 1500,
    "kspSubspaceSize": 50,
}


def test_level_table_is_unchanged():
    assert set(GRID_LEVELS) == set(LEVEL_TABLE)
    for level, (n, coarsen, s0_frac) in LEVEL_TABLE.items():
        assert GRID_LEVELS[level]["N"] == n, level
        assert GRID_LEVELS[level]["coarsen"] == coarsen, level
        assert GRID_LEVELS[level]["s0_frac"] == s0_frac, level


@pytest.mark.parametrize("level", sorted(LEVEL_TABLE))
def test_default_options_match_pre_refactor_golden(level: str):
    n, coarsen, s0_frac = LEVEL_TABLE[level]
    expected = dict(BASE_EXPECTED, N=n, coarsen=coarsen, s0=s0_frac * CHAR_LEN)
    effective = build_pyhyp_options(SURFACE, level=level, characteristic_length=CHAR_LEN)
    assert effective.values == expected


def test_back_compat_wrapper_matches_builder():
    wrapped = _build_options(
        SURFACE,
        level="smoke",
        characteristic_length=CHAR_LEN,
        s0=None,
        march_dist_factor=25.0,
        n_grid=None,
        n_coarsen=None,
        c_max=0.7,
        theta=3.0,
        vol_coef=0.5,
        eps_e_far=4.0,
        eps_i_far=8.0,
        vol_smooth_iter=800,
        vol_blend=0.004,
        n_constant_start=5,
        ksp_rel_tol=1.0e-8,
        ksp_max_its=1500,
    )
    built = build_pyhyp_options(SURFACE, level="smoke", characteristic_length=CHAR_LEN)
    assert wrapped == built.values


def test_explicit_overrides_and_provenance():
    effective = build_pyhyp_options(
        SURFACE,
        level="smoke",
        characteristic_length=CHAR_LEN,
        s0=5.0e-5,
        n_grid=193,
        c_max=0.5,
        march_dist_factor=30.0,
    )
    assert effective.values["s0"] == 5.0e-5
    assert effective.values["N"] == 193
    assert effective.values["cMax"] == 0.5
    assert effective.values["marchDist"] == 30.0 * CHAR_LEN
    assert effective.provenance["s0"] == "user"
    assert effective.provenance["N"] == "user"
    assert effective.provenance["coarsen"] == "level:smoke"
    assert effective.provenance["cMax"] == "user"
    assert effective.provenance["fileType"] == "aeris-default"
    assert effective.provenance["marchDist"] == "derived"


def test_raw_pass_through_gives_full_pyhyp_authority():
    effective = build_pyhyp_options(
        SURFACE,
        level="smoke",
        characteristic_length=CHAR_LEN,
        pyhyp_options={"splay": 0.25, "cornerAngle": 60.0, "cMax": 0.9},
    )
    # non-curated native options pass verbatim
    assert effective.values["splay"] == 0.25
    assert effective.values["cornerAngle"] == 60.0
    assert effective.provenance["splay"] == "raw"
    # curated shadowing wins but is traceable
    assert effective.values["cMax"] == 0.9
    assert effective.overridden_curated_keys == ("c_max",)


def test_output_file_included_when_given():
    effective = build_pyhyp_options(
        SURFACE,
        level="L3",
        characteristic_length=CHAR_LEN,
        output_file=Path("/tmp/surface/wing_vol_L3.cgns"),
    )
    assert effective.values["outputFile"] == "/tmp/surface/wing_vol_L3.cgns"


def test_unknown_level_and_bad_char_len_raise():
    with pytest.raises(ValueError, match="Unknown level"):
        build_pyhyp_options(SURFACE, level="L9", characteristic_length=CHAR_LEN)
    with pytest.raises(ValueError, match="characteristic_length"):
        build_pyhyp_options(SURFACE, level="L3", characteristic_length=0.0)
