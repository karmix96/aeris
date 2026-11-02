"""One spacing tool, used around the section and along the span.

Three steps on a dense 1-D grid along a line (arc length s from 0 to L):

1. a target cell size h(s), the smallest of every rule that applies at s;
2. a growth limit: h may grow by at most ln(g) per unit length, so two
   neighbouring cells differ by at most about g (equidistributed cells on
   h = h0 + k d grow by exp(k) per cell);
3. equidistribution: points placed so every cell holds the same share of the
   integral of 1/h. With n points and n - 1 >= the integral, every cell is at
   most its target size, and neighbouring cells keep the ratio of h.

Step 3 is what lets every station use one common point count (a structured
mesh needs it): a station that needs fewer cells than the count gets cells that
are all smaller than asked by the same factor, never larger.
"""

from __future__ import annotations

import numpy as np

Array = np.ndarray


def limit_growth(s: Array, h: Array, g: float) -> Array:
    """Smallest h' <= h with |h'(j) - h'(j-1)| <= ln(g) * (s(j) - s(j-1)).

    Equidistributed cells on h = h0 + k s grow by exp(k) per cell, so k = ln(g) gives
    neighbouring cells in the ratio g."""
    if g <= 1.0:
        raise ValueError("growth ratio must be above 1")
    # the answer is min over i of h(i) + k |s(j) - s(i)|; two running minima give it exactly
    s = np.asarray(s, dtype=float)
    h = np.asarray(h, dtype=float)
    k = float(np.log(g))
    fwd = k * s + np.minimum.accumulate(h - k * s)
    bwd = -k * s + np.minimum.accumulate((h + k * s)[::-1])[::-1]
    return np.minimum(fwd, bwd)


def cells_needed(s: Array, h: Array) -> float:
    """Integral of ds / h: how many cells of the target size fit along the line."""
    return float(np.trapezoid(1.0 / np.asarray(h, dtype=float), np.asarray(s, dtype=float)))


def equidistribute(s: Array, h: Array, n_points: int) -> Array:
    """n_points positions on [s0, sL], first and last included, one equal share of int ds/h per cell."""
    if n_points < 2:
        raise ValueError("need at least two points")
    s = np.asarray(s, dtype=float)
    inv = 1.0 / np.asarray(h, dtype=float)
    cum = np.concatenate([[0.0], np.cumsum(0.5 * (inv[1:] + inv[:-1]) * np.diff(s))])
    targets = np.linspace(0.0, cum[-1], n_points)
    out = np.interp(targets, cum, s)
    out[0], out[-1] = s[0], s[-1]
    return out


def flat_ends(s: Array, h: Array, h0: float | None, h1: float | None, n0: int = 1, n1: int = 1) -> Array:
    """Hold the size at h0 over the first n0 cells (n0 * h0 of the line) and at h1 over the last n1.

    A cell is about the size of h at its middle, so an end cell is the asked size only if
    h stays at that size over the whole cell."""
    h = np.asarray(h, dtype=float).copy()
    if h0 is not None:
        m = s <= s[0] + n0 * h0
        h[m] = np.minimum(h[m], h0)
    if h1 is not None:
        m = s >= s[-1] - n1 * h1
        h[m] = np.minimum(h[m], h1)
    return h


def fill_to_count(s: Array, h: Array, n_points: int) -> Array:
    """The size field for exactly n_points: the largest cells are made smaller first.

    h' = min(h, H) with H chosen so that int ds / h' = n_points - 1. Every fine region (nose,
    trailing edge, band) keeps its asked size; the extra points go where the cells are largest.
    """
    need = n_points - 1
    if cells_needed(s, h) > need + 1e-9:
        raise ValueError("fewer points than the size field needs")
    lo, hi = 1e-6 * float(np.min(h)), float(np.max(h))
    if cells_needed(s, h) >= need - 1e-9:
        return h
    for _ in range(200):
        mid = np.sqrt(lo * hi)
        if cells_needed(s, np.minimum(h, mid)) > need:
            lo = mid
        else:
            hi = mid
        if hi / lo - 1.0 < 1e-12:
            break
    return np.minimum(h, hi)


def spacing_stats(x: Array) -> dict[str, float]:
    """Smallest and largest cell and the largest neighbour ratio of one line of points."""
    d = np.diff(np.asarray(x, dtype=float))
    r = d[1:] / d[:-1]
    return {"min": float(d.min()), "max": float(d.max()),
            "max_ratio": float(max(r.max(), (1.0 / r).max())) if len(r) else 1.0}
