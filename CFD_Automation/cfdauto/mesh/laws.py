"""The surface-mesh laws: one function per setting, read from one YAML file.

Each function takes the wing, the flow or the level and returns the setting. Most return
a starting value today; when a law is fitted later (Grand Roadmap stage 5) only its function
changes. The numbers and their sources live in Stage_2_surface_mesh/configs/surface.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

from ..paths import STAGE2

CONFIG = STAGE2 / "configs" / "surface.yaml"


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


@dataclass(frozen=True)
class Rules:
    """All surface rules at one level (spacings already divided by r^k)."""

    level: str
    k: int
    ratio: float
    raw: dict

    # --- around the section ------------------------------------------------
    @property
    def nose_turning_deg(self) -> float:
        """law 1, at level C. Finer levels keep the C nose spacing divided by r^k."""
        return float(self.raw["chord"]["nose_turning_deg"])

    @property
    def nose_turning_tol_deg(self) -> float:
        return float(self.raw["chord"]["nose_turning_tol_deg"])

    @property
    def nose_envelope(self) -> float:
        return float(self.raw["chord"]["nose_envelope"])

    @property
    def te_spacing_c(self) -> float:
        return float(self.raw["chord"]["te_spacing_c"]) / self.scale

    @property
    def base_cells(self) -> int:
        """law 6: cells across the base, even (so n_base is odd for the cap), times r^k."""
        c = float(self.raw["chord"]["base_cells"]) * self.scale
        return max(2, int(2 * round(c / 2)))

    @property
    def n_base(self) -> int:
        return self.base_cells + 1

    @property
    def chord_growth(self) -> float:
        """Growth used to build the size field: g_C ** (1 / r^k). A finer level is then a true
        scaled copy (every cell, also in the stretched parts, is the C cell divided by r^k);
        with the same g at every level the stretched parts would not refine (law 23)."""
        return float(self.raw["chord"]["growth"]) ** (1.0 / self.scale)

    @property
    def chord_growth_limit(self) -> float:
        return float(self.raw["chord"]["growth_limit"])

    @property
    def max_spacing_c(self) -> float:
        return float(self.raw["chord"]["max_spacing_c"]) / self.scale

    @property
    def band_upper(self) -> tuple[float, float]:
        return tuple(self.raw["chord"]["band_upper"])

    @property
    def band_lower(self) -> tuple[float, float]:
        return tuple(self.raw["chord"]["band_lower"])

    def bubble_length_c(self, re_local: float) -> float:
        """Laminar-bubble length / chord at a local Re (Stage 1 XFOIL table, log-log)."""
        tab = self.raw["chord"]["bubble_length"]
        lr = np.log(np.asarray(tab["re"], dtype=float))
        ll = np.log(np.asarray(tab["l_c"], dtype=float))
        return float(np.exp(np.interp(np.log(re_local), lr, ll)))

    def band_spacing_c(self, re_local: float) -> float:
        """Cell size over the transition band / chord: bubble length / nodes per bubble, / r^k."""
        n = float(self.raw["chord"]["nodes_per_bubble"])
        return min(self.bubble_length_c(re_local) / n, self.max_spacing_c * self.scale) / self.scale

    # --- along the span -----------------------------------------------------
    @property
    def span_spacing_c(self) -> float:
        """law 8: station gap / local chord."""
        return float(self.raw["span"]["spacing_c"]) / self.scale

    @property
    def min_cells_per_panel(self) -> int:
        return int(np.ceil(float(self.raw["span"]["min_cells_per_panel"]) * self.scale))

    @property
    def span_growth(self) -> float:
        """As chord_growth: g_C ** (1 / r^k)."""
        return float(self.raw["span"]["growth"]) ** (1.0 / self.scale)

    @property
    def span_growth_limit(self) -> float:
        return float(self.raw["span"]["growth_limit"])

    @property
    def tip_gap_in_s0(self) -> float:
        return float(self.raw["span"]["tip_gap_in_s0"])

    # --- wall ---------------------------------------------------------------
    @property
    def yplus(self) -> float:
        return float(self.raw["wall"]["yplus"]) / self.scale

    def first_cell_c(self, re_local: float) -> float:
        """law 13: first wall cell / local chord for the y+ target (turbulent flat plate, White 2006)."""
        return first_cell_c(re_local, self.yplus)

    # --- sampling and checks ---------------------------------------------------
    @property
    def scale(self) -> float:
        return self.ratio ** self.k

    @property
    def dense_per_side(self) -> int:
        return int(self.raw["sampling"]["dense_per_side"])

    @property
    def dense_span(self) -> int:
        return int(self.raw["sampling"]["dense_span"])

    @property
    def cap_smoothing(self) -> int:
        return int(self.raw["sampling"]["cap_smoothing"])

    @property
    def checks(self) -> dict:
        return dict(self.raw["checks"])

    def values(self) -> dict:
        """Every rule value at this level, for the manifest."""
        return {
            "level": self.level, "k": self.k, "ratio": self.ratio,
            "nose_turning_deg_at_C": self.nose_turning_deg, "nose_envelope": self.nose_envelope,
            "te_spacing_c": self.te_spacing_c, "base_cells": self.base_cells,
            "chord_growth": self.chord_growth, "chord_growth_limit": self.chord_growth_limit,
            "max_spacing_c": self.max_spacing_c, "band_upper": list(self.band_upper),
            "band_lower": list(self.band_lower),
            "nodes_per_bubble_at_C": float(self.raw["chord"]["nodes_per_bubble"]),
            "bubble_length": self.raw["chord"]["bubble_length"],
            "span_spacing_c": self.span_spacing_c, "min_cells_per_panel": self.min_cells_per_panel, "span_growth": self.span_growth,
            "span_growth_limit": self.span_growth_limit, "tip_gap_in_s0": self.tip_gap_in_s0,
            "yplus": self.yplus,
        }


def first_cell_c(re_c: float, yplus: float = 1.0) -> float:
    """First wall cell / chord for a y+ target on a turbulent flat plate of length c (Cf = 0.026 Re^-1/7)."""
    cf = 0.026 * re_c ** (-1.0 / 7.0)
    return yplus / (re_c * np.sqrt(0.5 * cf))


def rules(level: str = "C", config: str | Path | None = None) -> Rules:
    raw = _load(str(config or CONFIG))
    names = list(raw["levels"]["names"])
    if level not in names:
        raise ValueError(f"level must be one of {names}")
    return Rules(level=level, k=names.index(level), ratio=float(raw["levels"]["ratio"]), raw=raw)
