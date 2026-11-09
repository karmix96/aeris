"""The volume-mesh laws: one function per setting, read from Stage_3_volume_mesh/configs/volume.yaml.

Anchors as in Stage 2 (decision 71). A value written {value: x, at: LEVEL} is met at LEVEL and follows the family
rule (law 23) on the other levels. With r = 1.3, level k and anchor a (VC = 0, C = 1, M = 2, F = 3):

    sizes    x * r^(a - k)      0.0075 c at M: 0.0127 c at VC, 0.0058 c at F
    counts   x * r^(k - a)      30 cells at VC: 39 at C, 51 at M, 66 at F
    growth   x ** r^(a - k)     1.25 at VC: 1.187 at C, 1.141 at M, 1.107 at F

Distances (the far field, the fine zone, the band length) are the same at every level. The first wall cell is
Stage 2's law 13 at the level's y+ (cfdauto.mesh.laws.first_cell_c): the volume reads it from the surface rules so
the tip gap and the wall layers use one s0.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

from ..mesh.laws import first_cell_c as _first_cell_c
from ..mesh.laws import rules as surface_rules
from ..paths import STAGE3

CONFIG = STAGE3 / "configs" / "volume.yaml"

# name: (yaml path, kind, what it is)
SETTINGS = {
    "wall_growth": (("wall", "growth"), "growth", "growth limit in the boundary layer and the fine zone (law 14)"),
    "bl_cells": (("wall", "bl_cells"), "count", "cells across the boundary layer (law 14)"),
    "far_growth": (("far", "growth"), "growth", "growth limit beyond the fine zone (law 15)"),
    "far_growth_built": (("far", "growth_built"), "growth", "growth built beyond the fine zone (law 15)"),
    "band_spacing_c": (("wake", "band", "spacing_c"), "size", "cross-wake cell at the trailing edge (law 17)"),
    "band_fan_cells": (("wake", "band", "fan_cells"), "count", "cells across the wake fan (law 18)"),
    "outboard_growth": (("outboard", "growth"), "growth", "station-gap growth past the tip (law 12)"),
}


@lru_cache(maxsize=8)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def _get(raw: dict, keys: tuple[str, ...]):
    d = raw
    for k in keys:
        d = d[k]
    return d


def move(x: float, kind: str, n: int, r: float) -> float:
    """x from its anchor to a level n steps coarser (n > 0) or finer (n < 0)."""
    up = r ** abs(n)
    if kind == "size":
        return x * up if n >= 0 else x / up
    if kind == "growth":
        return x ** (up if n >= 0 else 1.0 / up)
    if kind == "count":
        return x / up if n >= 0 else x * up
    raise ValueError(kind)


@dataclass(frozen=True)
class VolumeRules:
    level: str
    k: int
    ratio: float
    raw: dict
    config: str

    @property
    def names(self) -> list[str]:
        return list(self.raw["levels"]["names"])

    # --- the family rule ---------------------------------------------------------------
    def anchor(self, name: str) -> tuple[float, str, str]:
        e = _get(self.raw, SETTINGS[name][0])
        if not isinstance(e, dict):
            raise ValueError(f"{name}: every volume setting carries an anchor level")
        return float(e["value"]), str(e["at"]), str(e.get("why", ""))

    def setting(self, name: str) -> float:
        x, at, _ = self.anchor(name)
        return move(x, SETTINGS[name][1], self.names.index(at) - self.k, self.ratio)

    def reason(self, name: str) -> str:
        x, at, why = self.anchor(name)
        what = SETTINGS[name][2]
        v = self.setting(name)
        return f"{what}: {x:g} at {at} ({why}); {self.level}: {v:.5g}"

    # --- wall ----------------------------------------------------------------------------
    @property
    def surface(self):
        """The Stage 2 surface rules at this level (law 13's y+, the base cells, the tip gap)."""
        return surface_rules(self.level)

    @property
    def yplus(self) -> float:
        return float(self.surface.yplus)

    def first_cell(self, re_local: float, chord: float) -> float:
        """law 13: first wall cell [mean chords] at a station of local chord `chord` and local Re."""
        return float(_first_cell_c(re_local, self.yplus) * chord)

    @property
    def wall_growth(self) -> float:
        return self.setting("wall_growth")

    @property
    def bl_cells(self) -> float:
        return self.setting("bl_cells")

    def delta(self, re_local: float, chord: float) -> float:
        """Boundary-layer thickness [mean chords] that the bl_cells must cross, from the local Re (decision 86)."""
        d = self.raw["wall"]["delta"]
        x = float(d["x_c"]) * chord
        re_x = re_local * float(d["x_c"])
        if d["law"] == "turbulent":
            return 0.37 * x * re_x ** (-0.2)
        if d["law"] == "laminar":
            return 4.91 * x / np.sqrt(re_x)
        raise ValueError(f"wall.delta.law {d['law']!r}")

    @property
    def fine_zone_local_c(self) -> float:
        return float(self.raw["wall"]["fine_zone_local_c"])

    # --- far field -----------------------------------------------------------------------
    @property
    def far_distance(self) -> float:
        return float(self.raw["far"]["distance_c"])

    @property
    def far_growth(self) -> float:
        """The checked limit beyond the fine zone."""
        return self.setting("far_growth")

    @property
    def far_growth_built(self) -> float:
        """The growth the far zone is built with (the far-field blend may raise it toward far_growth)."""
        return self.setting("far_growth_built")

    # --- wake --------------------------------------------------------------------------
    @property
    def wake(self) -> dict:
        return dict(self.raw["wake"])

    @property
    def band(self) -> dict:
        b = dict(self.raw["wake"]["band"])
        b["spacing_c"] = self.setting("band_spacing_c")
        b["fan_cells"] = self.setting("band_fan_cells")
        return b

    def band_cell(self, d: np.ndarray) -> np.ndarray:
        """Cross-wake cell cap [c] at a distance d behind the trailing edge: the trailing-edge value, growing so the
        fan from alpha_lo to alpha_hi keeps fan_cells cells (decision 87)."""
        b = self.band
        fan = np.tan(np.radians(b["alpha_hi_deg"])) - np.tan(np.radians(b["alpha_lo_deg"]))
        return b["spacing_c"] + np.asarray(d, dtype=float) * fan / b["fan_cells"]

    # --- outboard ------------------------------------------------------------------------
    @property
    def outboard_growth(self) -> float:
        return self.setting("outboard_growth")

    @property
    def outboard_fine_zone(self) -> float:
        return float(self.raw["outboard"]["fine_zone_c"])

    # --- plane, checks -------------------------------------------------------------------
    @property
    def plane(self) -> dict:
        return dict(self.raw["plane"])

    @property
    def checks(self) -> dict:
        return dict(self.raw["checks"])

    def ram_gib(self, cells: float) -> float:
        c = self.checks
        return float(c["ram_gib_base"]) + float(c["ram_gib_per_mcell"]) * cells / 1e6

    def values(self) -> dict:
        out = {"level": self.level, "k": self.k, "ratio": self.ratio, "config": self.config,
               "yplus": self.yplus, "fine_zone_local_c": self.fine_zone_local_c, "far_distance_c": self.far_distance,
               "delta": dict(self.raw["wall"]["delta"]), "wake": self.raw["wake"] | {"band": self.band},
               "outboard_fine_zone_c": self.outboard_fine_zone, "plane": self.plane}
        out |= {n: self.setting(n) for n in SETTINGS}
        out["reasons"] = {n: self.reason(n) for n in SETTINGS}
        return out


def rules(level: str | None = None, config: str | Path | None = None) -> VolumeRules:
    path = str(config or CONFIG)
    raw = _load(path)
    names = list(raw["levels"]["names"])
    level = names[0] if level is None else level
    if level not in names:
        raise ValueError(f"level must be one of {names}")
    return VolumeRules(level, names.index(level), float(raw["levels"]["ratio"]), raw, path)
