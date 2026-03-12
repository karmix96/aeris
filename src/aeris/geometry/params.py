from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class WingGeometryParams:
    span: float
    aspect_ratio: float
    taper_ratio: float
    sweep_deg: float
    dihedral_deg: float
    root_chord: float
    tip_chord: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_wing_geometry_params(config: dict[str, Any]) -> WingGeometryParams:
    geometry_cfg = config.get("geometry", {})

    span = float(geometry_cfg["span"])
    aspect_ratio = float(geometry_cfg["aspect_ratio"])
    taper_ratio = float(geometry_cfg["taper_ratio"])
    sweep_deg = float(geometry_cfg["sweep_deg"])
    dihedral_deg = float(geometry_cfg["dihedral_deg"])

    wing_area = span ** 2 / aspect_ratio
    root_chord = (2.0 * wing_area) / (span * (1.0 + taper_ratio))
    tip_chord = taper_ratio * root_chord

    return WingGeometryParams(
        span=span,
        aspect_ratio=aspect_ratio,
        taper_ratio=taper_ratio,
        sweep_deg=sweep_deg,
        dihedral_deg=dihedral_deg,
        root_chord=root_chord,
        tip_chord=tip_chord,
    )
