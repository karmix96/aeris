"""Checks that refuse. Each returns (name, passed, value, limit, note); the build writes no
mesh unless every check passes. A violation is shown per station, never averaged away."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

Array = np.ndarray


@dataclass
class Check:
    name: str
    passed: bool
    value: float
    limit: str
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def scaled_jacobian(grid: Array, wrap_i: bool = False) -> Array:
    """Smallest corner scaled Jacobian of every quad of a (ni, nj, 3) surface grid.

    1 = right angles; 0 = a corner angle of 0 or 180 deg; below 0 = folded. The reference
    normal is the cross product of the quad's diagonals; corners are taken in turning order.
    """
    g = np.concatenate([grid, grid[:1]], axis=0) if wrap_i else grid
    p = [g[:-1, :-1], g[1:, :-1], g[1:, 1:], g[:-1, 1:]]     # counter-clockwise in (i, j)
    n = np.cross(p[2] - p[0], p[3] - p[1])
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    out = None
    for k in range(4):
        a, b, c = p[k], p[(k + 1) % 4], p[(k - 1) % 4]
        e1, e2 = b - a, c - a
        j = (np.cross(e1, e2) * n).sum(-1) / (np.linalg.norm(e1, axis=-1) * np.linalg.norm(e2, axis=-1))
        out = j if out is None else np.minimum(out, j)
    return out
