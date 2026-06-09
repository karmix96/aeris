from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from aeris.generators.bwb_segmented_v1.deflected_cad import save_physical_deflected_planform_preview


class _Airfoil:
    coordinates = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 0.05], [0.0, 0.0]], dtype=float)


def test_save_physical_deflected_planform_preview_writes_png(tmp_path):
    xsecs = [
        SimpleNamespace(xyz_le=[0.0, 0.0, 0.0], chord=1.0, airfoil=_Airfoil()),
        SimpleNamespace(xyz_le=[0.2, 1.0, 0.0], chord=0.5, airfoil=_Airfoil()),
    ]
    wing = SimpleNamespace(name="test_wing", xsecs=xsecs)
    airplane = SimpleNamespace(name="test_airplane", wings=[wing])
    out = tmp_path / "preview.png"

    result = save_physical_deflected_planform_preview(airplane, out)

    assert result == out.resolve()
    assert out.exists()
    assert out.stat().st_size > 0
