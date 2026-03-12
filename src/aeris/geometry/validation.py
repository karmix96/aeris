from __future__ import annotations

from aeris.geometry.params import WingGeometryParams


def validate_wing_geometry_params(params: WingGeometryParams) -> None:
    if params.span <= 0:
        raise ValueError("span must be > 0")

    if params.aspect_ratio <= 0:
        raise ValueError("aspect_ratio must be > 0")

    if not (0 < params.taper_ratio <= 1):
        raise ValueError("taper_ratio must be in the range (0, 1]")

    if not (0 <= params.sweep_deg <= 60):
        raise ValueError("sweep_deg must be in the range [0, 60]")

    if not (0 <= params.dihedral_deg <= 15):
        raise ValueError("dihedral_deg must be in the range [0, 15]")

    if params.root_chord <= 0:
        raise ValueError("root_chord must be > 0")

    if params.tip_chord <= 0:
        raise ValueError("tip_chord must be > 0")
