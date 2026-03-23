"""Tests for reconstruction artifact export in bwb_segmented_v1.reconstruction_export."""

from __future__ import annotations

import pytest

import aerosandbox as asb

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.generators.bwb_segmented_v1.reconstruction_export import export_reconstruction_artifacts


def test_export_reconstruction_artifacts_rejects_airplane_without_wings(tmp_path):
    """Export should fail clearly when airplane has no wings."""
    airplane = asb.Airplane(
        name="empty",
        wings=[],
        s_ref=1.0,
        c_ref=1.0,
        b_ref=1.0,
    )

    with pytest.raises(ValueError, match="no wings"):
        export_reconstruction_artifacts(airplane=airplane, output_dir=tmp_path)


def test_export_reconstruction_artifacts_rejects_too_few_sections(tmp_path):
    """Export should fail clearly when the first wing has fewer than 2 sections."""
    wing = asb.Wing(
        name="bad",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[0.0, 0.0, 0.0],
                chord=1.0,
                twist=0.0,
                airfoil=asb.Airfoil("naca0012"),
            )
        ],
    )
    airplane = asb.Airplane(
        name="bad_airplane",
        wings=[wing],
        s_ref=1.0,
        c_ref=1.0,
        b_ref=1.0,
    )

    with pytest.raises(ValueError, match="at least 2 wing sections"):
        export_reconstruction_artifacts(airplane=airplane, output_dir=tmp_path)