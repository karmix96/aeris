"""Where the stations go along the span (laws 8 and 9).

- A station exactly on every loft station (b0, b1, b2, b3 and any station the loft adds,
  such as the trailing-edge switch station): the ruled loft has a crease there.
- Target gap = spacing_c x local chord, so the count follows the semi-span in local chords;
  at least min_cells_per_panel gaps between two loft stations.
- Squeezed toward the tip: the last gap is the tip first cell (s0), growth limited.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .laws import Rules
from .spacing import cells_needed, equidistribute, flat_ends, limit_growth

Array = np.ndarray


def _chord_and_y(loft, v: Array) -> tuple[Array, Array]:
    z = np.zeros_like(v)
    le = loft.upper(z, v)
    te = 0.5 * (loft.upper(z + 1.0, v) + loft.lower(z + 1.0, v))
    return np.linalg.norm(te - le, axis=1), le[:, 1]


@dataclass
class SpanTable:
    v: Array
    y: Array
    chord: Array
    semi_span: float
    mean_chord: float          # half area / semi-span (the chord the Re levels are quoted on)
    loft_y: Array              # y of every loft station

    @classmethod
    def of(cls, loft, n: int) -> "SpanTable":
        """n dense points per panel (a panel can be under 1 mm wide when a break sits next to the
        root, and the station placement integrates on this grid), plus every loft station."""
        sv = np.asarray(loft.station_v, dtype=float)
        v = np.unique(np.concatenate([np.linspace(a, b, n) for a, b in zip(sv[:-1], sv[1:])] + [sv]))
        v = v[np.concatenate([[True], np.diff(v) > 1e-12])]        # a loft station within 1e-12 of a grid point
        chord, y = _chord_and_y(loft, v)
        if np.any(np.diff(y) <= 0):
            raise ValueError("the loft's leading edge does not move outboard monotonically")
        loft_y = np.interp(loft.station_v, v, y)
        area = float(np.trapezoid(chord, y))
        return cls(v, y, chord, float(y[-1]), area / float(y[-1]), loft_y)

    def refined_at_tip(self, loft, finest: float) -> "SpanTable":
        """The same table with points packed toward the tip, so a tip gap of `finest` is resolved."""
        d = finest * 0.05 * 1.05 ** np.arange(400)
        d = d[d < self.semi_span * 0.5]
        v_extra = np.interp(self.semi_span - d, self.y, self.v)    # y is linear in v on every straight panel
        v = np.unique(np.concatenate([self.v, v_extra]))
        chord, y = _chord_and_y(loft, v)
        return SpanTable(v, y, chord, self.semi_span, self.mean_chord, self.loft_y)

    def chord_at(self, y) -> Array:
        return np.interp(y, self.y, self.chord)

    def v_at(self, y) -> Array:
        return np.interp(y, self.y, self.v)


def place_stations(tab: SpanTable, rules: Rules, tip_gap: float, loft_v: Array) -> dict:
    """Station y and v, root to tip, and what was asked and delivered."""
    h = rules.span_spacing_c * tab.chord
    for a, b in zip(tab.loft_y[:-1], tab.loft_y[1:]):      # at least min_cells_per_panel gaps per panel
        m = (tab.y >= a) & (tab.y <= b)
        h[m] = np.minimum(h[m], (b - a) / rules.min_cells_per_panel)
    h = limit_growth(tab.y, flat_ends(tab.y, h, None, tip_gap), rules.span_growth)
    ys, counts = [0.0], []
    for a, b in zip(tab.loft_y[:-1], tab.loft_y[1:]):
        m = (tab.y >= a - 1e-14) & (tab.y <= b + 1e-14)
        n_cells = max(1, int(np.ceil(cells_needed(tab.y[m], h[m]) - 1e-9)))
        counts.append(n_cells)
        ys.extend(equidistribute(tab.y[m], h[m], n_cells + 1)[1:])
    y = np.array(ys)
    v = tab.v_at(y)
    for yl, vl in zip(tab.loft_y, loft_v):      # loft stations hit exactly, in v as well as in y
        j = int(np.argmin(np.abs(y - yl)))
        y[j], v[j] = yl, vl
    gaps = np.diff(y)
    return {"y": y, "v": v, "cells_per_panel": counts, "tip_gap_asked": float(tip_gap),
            "tip_gap": float(gaps[-1]), "size_field": h}
