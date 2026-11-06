"""The surface-mesh laws: one function per setting, read from one YAML file.

Each function takes the wing, the flow or the level and returns the setting; `Rules.reason(name)` says in one
line where the value comes from. Most return a starting value today; when a law is fitted later (Grand Roadmap
stage 5) only its function changes. The numbers and their sources live in Stage_2_surface_mesh/configs/surface.yaml.

Anchors (decision 71, 6 Nov 2026). A value written {value: x, at: LEVEL} is met at LEVEL and follows the family
rule on the other levels. With r = 1.3, level k and anchor a (VC = 0, C = 1, M = 2, F = 3):

    spacings and turning angles   x * r^(a - k)      10 deg at M: 16.9 at VC, 13 at C, 7.7 at F
    counts                        x * r^(k - a)      20 cells per bubble at F: 9.1 at VC; whole numbers are
                                                     rounded (the base to an even count, the gaps per panel up)
    growth ratios                 x ** r^(a - k)     1.2 at VC: 1.15 at C, 1.11 at M, 1.087 at F

The power of r is a whole number of level steps, so a value is exactly x at its anchor. A plain number keeps the
first approach's meaning (configs/surface_first.yaml, configs/surface_plan_VC.yaml): the value at the coarsest
level, scaled as the first code did (spacings / r^k, counts * r^k, growth g^(1/r^k)); the nose angle, the growth
limits and every other plain number stay the same at every level.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

from ..paths import STAGE2

CONFIG = STAGE2 / "configs" / "surface.yaml"

# name: (YAML group, YAML key, how it moves between levels, does a plain number scale?, what it is)
#   size: x * r^(a - k);  count: x * r^(k - a);  even / up: a count rounded to an even number / up;  growth: x ** r^(a - k)
SETTINGS = {
    "nose_turning_deg":    ("chord", "nose_turning_deg", "size", False, "law 1: largest turning per ring cell [deg]"),
    "te_spacing_c":        ("chord", "te_spacing_c", "size", True, "law 3: trailing-edge cell / local chord"),
    "max_spacing_c":       ("chord", "max_spacing_c", "size", True, "largest ring cell / local chord"),
    "base_cells":          ("chord", "base_cells", "even", True, "law 6: cells across the blunt base"),
    "chord_growth":        ("chord", "growth", "growth", True, "growth that builds the ring's size field"),
    "chord_growth_limit":  ("chord", "growth_limit", "growth", False, "checked growth between ring cells"),
    "cells_per_bubble":    ("chord", "nodes_per_bubble", "count", True, "band cells across a laminar bubble"),
    "span_spacing_c":      ("span", "spacing_c", "size", True, "law 8: station gap / local chord"),
    "min_cells_per_panel": ("span", "min_cells_per_panel", "up", True, "fewest station gaps per panel"),
    "span_growth":         ("span", "growth", "growth", True, "growth that builds the station gaps"),
    "span_growth_limit":   ("span", "growth_limit", "growth", False, "checked growth between station gaps"),
    "yplus":               ("wall", "yplus", "size", True, "law 13: y+ of the first wall cell (for the tip gap)"),
}


@lru_cache(maxsize=8)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def _move(x: float, kind: str, n: int, r: float):
    """x from its anchor to a level n steps coarser (n > 0) or finer (n < 0) than the anchor."""
    up = r ** abs(n)                                   # a whole power: exactly 1 at the anchor
    if kind == "size":
        return x * up if n >= 0 else x / up
    if kind == "growth":
        return x ** (up if n >= 0 else 1.0 / up)
    c = x / up if n >= 0 else x * up                   # counts: the inverse of a size
    if kind == "count":
        return c
    if kind == "even":
        return max(2, int(2 * round(c / 2)))
    if kind == "up":
        return int(np.ceil(c - 1e-9))
    raise ValueError(f"unknown kind {kind!r}")


@dataclass(frozen=True)
class Rules:
    """All surface rules at one level: every value already moved from its anchor to this level."""

    level: str
    k: int
    ratio: float
    raw: dict
    config: str = ""

    @property
    def names(self) -> list[str]:
        return list(self.raw["levels"]["names"])

    @property
    def scale(self) -> float:
        """r^k: the nose spacing, written at the coarsest level, is divided by this here (the family rule)."""
        return self.ratio ** self.k

    # --- anchors -------------------------------------------------------------------------
    def anchor(self, name: str) -> tuple[float, str | None, str]:
        """(value at its anchor, anchor level or None for a plain number, the 'why' written with it)."""
        group, key = SETTINGS[name][:2]
        e = self.raw[group][key]
        if isinstance(e, dict):
            at = str(e["at"])
            if at not in self.names:
                raise ValueError(f"{group}.{key}: anchor {at!r} is not a level of {self.names}")
            return float(e["value"]), at, str(e.get("why", ""))
        return float(e), None, ""

    def setting(self, name: str):
        """The value of one setting at this level."""
        kind, plain_scales = SETTINGS[name][2:4]
        x, at, _ = self.anchor(name)
        if at is None and not plain_scales:
            return x                                   # the same at every level
        n = (self.names.index(at) if at else 0) - self.k
        return _move(x, kind, n, self.ratio)

    def reason(self, name: str) -> str:
        """Why the setting has its value at this level, in one line."""
        kind, plain_scales, what = SETTINGS[name][2:]
        x, at, why = self.anchor(name)
        v = self.setting(name)
        if at is None and not plain_scales:
            return f"{what}: {x:g} at every level"
        src = at or self.names[0]
        head = f"{what}: {x:g} at {src}" + (f" ({why})" if why else "") + ("" if at else " (the first approach's way)")
        n = self.names.index(src) - self.k
        if n == 0:
            return head + ", this level"
        steps = f"{self.level} is {abs(n)} level{'s' if abs(n) > 1 else ''} {'coarser' if n > 0 else 'finer'}"
        p = f"{self.ratio:g}^{abs(n)}"
        how = {"size": ("x " if n > 0 else "/ ") + p, "growth": f"^({p})" if n > 0 else f"^(1/{p})"}.get(
            kind, ("/ " if n > 0 else "x ") + p)
        rnd = {"even": ", to an even count", "up": ", rounded up"}.get(kind, "")
        return f"{head}; {steps}: {how}{rnd} = {v:.4g}"

    def reasons(self) -> dict[str, str]:
        out = {n: self.reason(n) for n in SETTINGS}
        out["tip_gap_in_s0"] = (f"law 10: last station gap = {self.tip_gap_in_s0:g} x the tip first cell s0, at every "
                                f"level; s0 follows this level's y+ ({self.yplus:.3g})")
        return out

    # --- around the section ----------------------------------------------------------------
    @property
    def nose_turning_deg(self) -> float:
        """law 1 at this level: no ring cell turns the surface by more than this (the turning check, the repair and
        the curvature cap read it). The nose spacing itself is solved at nose_solve_levels and moved to this level
        by the family rule (build_surface)."""
        return float(self.setting("nose_turning_deg"))

    @property
    def nose_solve_levels(self) -> list[str]:
        """Where the nose spacing is solved, each for that level's own angle (chord.nose_solved_at; default the
        coarsest level, the first approach's way). The strictest solve, moved to each level by the family rule
        (x r^(solve level - k)), is the nose spacing of every level, so the family rule stays exact."""
        at = self.raw["chord"].get("nose_solved_at", [self.names[0]])
        at = [str(a) for a in (at if isinstance(at, list) else [at])]
        bad = [a for a in at if a not in self.names]
        if bad or not at:
            raise ValueError(f"chord.nose_solved_at: {bad or at} must be levels of {self.names}")
        return at

    @property
    def nose_turning_tol_deg(self) -> float:
        return float(self.raw["chord"]["nose_turning_tol_deg"])

    @property
    def nose_envelope(self) -> float:
        return float(self.raw["chord"]["nose_envelope"])

    @property
    def te_spacing_c(self) -> float:
        return float(self.setting("te_spacing_c"))

    @property
    def base_cells(self) -> int:
        """law 6: cells across the base, even (so n_base is odd for the cap)."""
        return int(self.setting("base_cells"))

    @property
    def n_base(self) -> int:
        return self.base_cells + 1

    @property
    def chord_growth(self) -> float:
        """Growth used to build the size field. A finer level is then a true scaled copy (every cell, also in the
        stretched parts, is the coarser cell divided by r); with the same g at every level the stretched parts
        would not refine (law 23)."""
        return float(self.setting("chord_growth"))

    @property
    def chord_growth_limit(self) -> float:
        return float(self.setting("chord_growth_limit"))

    @property
    def max_spacing_c(self) -> float:
        return float(self.setting("max_spacing_c"))

    @property
    def band_upper(self) -> tuple[float, float]:
        return tuple(self.raw["chord"]["band_upper"])

    @property
    def band_lower(self) -> tuple[float, float]:
        return tuple(self.raw["chord"]["band_lower"])

    def bubble_length_c(self, re_local: float) -> float:
        """Laminar-bubble length / chord at a local Re (Stage 1 XFOIL table, log-log, constant outside)."""
        tab = self.raw["chord"]["bubble_length"]
        lr = np.log(np.asarray(tab["re"], dtype=float))
        ll = np.log(np.asarray(tab["l_c"], dtype=float))
        return float(np.exp(np.interp(np.log(re_local), lr, ll)))

    @property
    def cells_per_bubble(self) -> float:
        return float(self.setting("cells_per_bubble"))

    def band_spacing_c(self, re_local: float) -> float:
        """Cell size over the transition band / chord: bubble length / cells per bubble, at most the largest cell."""
        return min(self.bubble_length_c(re_local) / self.cells_per_bubble, self.max_spacing_c)

    # --- along the span -----------------------------------------------------------------
    @property
    def span_spacing_c(self) -> float:
        """law 8: station gap / local chord."""
        return float(self.setting("span_spacing_c"))

    @property
    def min_cells_per_panel(self) -> int:
        return int(self.setting("min_cells_per_panel"))

    @property
    def span_growth(self) -> float:
        """As chord_growth."""
        return float(self.setting("span_growth"))

    @property
    def span_growth_limit(self) -> float:
        return float(self.setting("span_growth_limit"))

    @property
    def tip_gap_in_s0(self) -> float:
        return float(self.raw["span"]["tip_gap_in_s0"])

    # --- wall ---------------------------------------------------------------------------
    @property
    def yplus(self) -> float:
        return float(self.setting("yplus"))

    def first_cell_c(self, re_local: float) -> float:
        """law 13: first wall cell / local chord for this level's y+ (turbulent flat plate, White 2006)."""
        return first_cell_c(re_local, self.yplus)

    # --- sampling and checks ------------------------------------------------------------
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
        """Every rule value at this level, with its anchor and its reason, for the manifest."""
        out = {"level": self.level, "k": self.k, "ratio": self.ratio, "levels": self.names, "config": self.config}
        out |= {n: self.setting(n) for n in SETTINGS}
        out |= {"nose_turning_tol_deg": self.nose_turning_tol_deg, "nose_envelope": self.nose_envelope,
                "band_upper": list(self.band_upper), "band_lower": list(self.band_lower),
                "bubble_length": self.raw["chord"]["bubble_length"], "tip_gap_in_s0": self.tip_gap_in_s0,
                "anchors": {n: self.anchor(n)[1] or f"{self.names[0]} (plain)" for n in SETTINGS},
                "reasons": self.reasons()}
        return out


def first_cell_c(re_c: float, yplus: float = 1.0) -> float:
    """First wall cell / chord for a y+ target on a turbulent flat plate of length c (Cf = 0.026 Re^-1/7)."""
    cf = 0.026 * re_c ** (-1.0 / 7.0)
    return yplus / (re_c * np.sqrt(0.5 * cf))


def rules(level: str | None = None, config: str | Path | None = None) -> Rules:
    """The rules at one level of the config's ladder (default: its coarsest level)."""
    path = str(config or CONFIG)
    raw = _load(path)
    names = list(raw["levels"]["names"])
    level = names[0] if level is None else level
    if level not in names:
        raise ValueError(f"level must be one of {names} (config {path})")
    return Rules(level=level, k=names.index(level), ratio=float(raw["levels"]["ratio"]), raw=raw, config=path)
