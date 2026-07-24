"""NeuralFoilCoordinateSource: feed NeuralFoil from pyGeo section coordinates.

AERIS never builds an asb.Airplane/asb.Airfoil on this path — coordinates go
straight to neuralfoil.get_aero_from_coordinates. (aerosandbox is still imported
transitively BY neuralfoil; that is out of AERIS's control and acceptable.)

The source must be a behaviour-identical drop-in for NeuralFoilPolarSource, since
NeuralFoil's coordinate and Kulfan cores agree for a coordinate-defined airfoil.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("neuralfoil")

from aeris.airfoil.neuralfoil_coordinate_source import (  # noqa: E402
    NeuralFoilCoordinateSource,
)
from aeris.airfoil.neuralfoil_polar_source import NeuralFoilPolarSource  # noqa: E402


def _load_airfoil(name: str = "naca2412") -> np.ndarray:
    dat = sorted(Path("data/airfoil_database").rglob(f"{name}*.dat"))[0]
    pts = []
    for line in dat.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                pts.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass
    return np.asarray(pts, dtype=float)


def test_coordinate_source_matches_kulfan_source() -> None:
    coords = _load_airfoil()
    csrc = NeuralFoilCoordinateSource(model_size="large")
    ksrc = NeuralFoilPolarSource(model_size="large")
    a1 = csrc.register_shape(coords)
    a2 = ksrc.register_shape(coords)

    assert csrc.has_airfoil(a1)
    # CDCL fit is finite and usable
    params = csrc.fit_cdcl(a1, re=1.0e6, mach=0.0)
    assert params is not None

    # Drag agrees with the ASB-Kulfan path across the working CL range
    for cl in (0.0, 0.3, 0.6):
        cd_coord = float(csrc.query_cd(a1, cl=cl, re=1.0e6, mach=0.0))
        cd_kulfan = float(ksrc.query_cd(a2, cl=cl, re=1.0e6, mach=0.0))
        assert cd_coord == pytest.approx(cd_kulfan, rel=1e-3, abs=1e-5)


def test_coordinate_source_registration_is_idempotent() -> None:
    coords = _load_airfoil()
    src = NeuralFoilCoordinateSource()
    a1 = src.register_shape(coords)
    a2 = src.register_shape(coords)
    assert a1 == a2
    assert len(src._shapes) == 1
