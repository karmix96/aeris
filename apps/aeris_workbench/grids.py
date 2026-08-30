"""The qualified S6 grid family, read from S6's own qualification definitions.

G1/G2/G3 are not the workbench's idea of a grid family.  They are declared in
`qualification._grid_family()` as a COUPLED definition - a surface level, its
chord/end/collar/span counts, the wall-normal point count and the wall spacing
that goes with it - and picking one has to set all of them together, because a
surface level with someone else's wall spacing is a grid the study has never
qualified and has no acceptance evidence for.

There is deliberately no G0 and no G4.  Inventing a level outside the declared
family would produce a mesh the study cannot speak for, presented in a selector
that implies it can.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .environment import REPO_ROOT, S6_DIR, STRATEGY_DIR

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR), str(S6_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# The registry's own epsE, and the value S6's frozen production calibration
# used.  It is the smoothing the qualified family was qualified at.
QUALIFIED_EPS_E = 1.5

GRID_LABELS = {"G1_coarse": "G1 coarse", "G2_medium": "G2 medium", "G3_fine": "G3 fine"}


@dataclass(frozen=True)
class GridDefinition:
    """One complete, coupled grid definition from the qualification plan."""

    name: str
    surface_level: str
    chord_points: int
    end_points: int
    collar_points: int
    span_cells: int
    normal_points: int
    first_cell_fraction: float
    volume_level: str
    eps_e: float = QUALIFIED_EPS_E

    @property
    def label(self) -> str:
        return GRID_LABELS.get(self.name, self.name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "label": self.label,
            "surface_level": self.surface_level,
            "chord_points": self.chord_points, "end_points": self.end_points,
            "collar_points": self.collar_points, "span_cells": self.span_cells,
            "normal_points": self.normal_points,
            "first_cell_fraction": self.first_cell_fraction,
            "volume_level": self.volume_level, "eps_e": self.eps_e,
        }

    def describe(self) -> str:
        return (f"{self.label}: surface {self.surface_level} "
                f"({self.chord_points}×{self.span_cells}), "
                f"N{self.normal_points}, s0/L {self.first_cell_fraction:.2e}")


def _volume_level(normal_points: int) -> str:
    """S6's own mapping from wall-normal points to its atlas volume level."""
    from campaign import _volume_level_from_normal_points  # noqa: PLC0415

    return str(_volume_level_from_normal_points(int(normal_points)))


def qualified_grids() -> dict[str, GridDefinition]:
    """Every declared grid, built from `qualification._grid_family()`.

    Read at call time rather than frozen into a table here, so that a change to
    S6's qualification plan reaches the workbench instead of silently leaving
    it presenting an out-of-date definition as a qualified one.
    """
    import qualification  # noqa: PLC0415

    out: dict[str, GridDefinition] = {}
    for row in qualification._grid_family():
        normal_points = int(row["normal_points"])
        out[str(row["name"])] = GridDefinition(
            name=str(row["name"]),
            surface_level=str(row["surface_level"]),
            chord_points=int(row["chord_points"]),
            end_points=int(row["end_points"]),
            collar_points=int(row["collar_points"]),
            span_cells=int(row["span_cells"]),
            normal_points=normal_points,
            first_cell_fraction=float(row["first_cell_fraction_characteristic"]),
            volume_level=_volume_level(normal_points),
        )
    return out


def grid(name: str) -> GridDefinition:
    grids = qualified_grids()
    try:
        return grids[name]
    except KeyError as error:
        raise ValueError(
            f"{name!r} is not a qualified S6 grid; choose from {sorted(grids)}"
        ) from error


def grid_names() -> list[str]:
    return list(qualified_grids())


def grid_items() -> list[dict[str, str]]:
    return [{"value": definition.name, "title": definition.describe()}
            for definition in qualified_grids().values()]


def estimate_cells(blocks: Any, normal_points: int) -> int:
    """How many volume cells this surface will march into.

    pyHyp extrudes every surface quad through the wall-normal direction, so the
    count is exactly the surface quad total times the number of cell layers -
    one fewer than the node count.  Knowing it BEFORE marching is the
    difference between a user choosing G3 deliberately and discovering what G3
    costs by waiting for it.
    """
    import numpy as np  # noqa: PLC0415

    quads = 0
    for block in blocks or []:
        shape = np.asarray(block.xyz).shape
        if shape[0] > 1 and shape[1] > 1:
            quads += int((shape[0] - 1) * (shape[1] - 1))
    return int(quads * max(0, int(normal_points) - 1))


def write_grid_provenance(definition: GridDefinition, path: Path) -> Path:
    import json  # noqa: PLC0415

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(definition.as_dict(), indent=2), encoding="utf-8")
    return path
