from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from aeris_research.cgns import pressure_coefficients, read_surface

REPO = Path(__file__).resolve().parents[2]
QUALIFICATION = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification"


@pytest.mark.skipif(not QUALIFICATION.is_dir(), reason="AERIS qualification archive unavailable")
def test_real_adf_archive_preserves_topology_and_pressure_force_contract():
    rows = json.loads((QUALIFICATION / "dataset/rows.json").read_text())
    selected = {row["run_name"]: row for row in rows if row["run_name"] in {"gci_C_a0", "gci_C_a4"}}
    surfaces = {}
    for name, row in selected.items():
        archive = QUALIFICATION / "dataset" / row["surface_field_archive"]
        surface = read_surface(archive)
        surfaces[name] = surface
        integrated = pressure_coefficients(
            surface.fields["CoefPressure"],
            surface.coordinates,
            surface.connectivity,
            surface.normals,
            surface.areas,
            alpha_deg=row["alpha_deg"],
            area_ref=row["area_ref"],
            chord_ref=row["chord_ref"],
            moment_ref_xyz=np.asarray(row["moment_ref_xyz"]),
        )
        assert abs(integrated["cl_pressure"] - row["CL"]) < 0.01
        assert abs(integrated["cmy_pressure"] - row["CMy"]) < 0.001
    assert surfaces["gci_C_a0"].topology_hash == surfaces["gci_C_a4"].topology_hash
    np.testing.assert_array_equal(
        surfaces["gci_C_a0"].connectivity, surfaces["gci_C_a4"].connectivity
    )
