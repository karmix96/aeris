"""
Structured-quad surface mesh quality metrics (industry standard set).

Definitions follow common industry/verification practice (equiangle
skewness and orthogonality per the Fluent/ANSYS meshing guides; scaled
Jacobian per the Verdict mesh-metric library used by CUBIT/ParaView):

* **scaled_jacobian** — min over corners of cross(e1, e2)/(|e1||e2|) per
  quad, in [-1, 1]; 1 = perfect right angles, <= 0 = degenerate/inverted.
* **equiangle_skewness** — max(|theta - 90|)/90 over corner angles, in
  [0, 1]; 0 = perfect, > 0.85 commonly flagged unacceptable.
* **aspect_ratio** — max/min of the two mean edge lengths of a quad; 1 =
  square.  High AR is expected and acceptable in boundary layers, so it is
  reported, not gated.
* **growth_ratio** — max adjacent-cell edge-length ratio along each index
  direction; smooth structured families keep this near the design r.

All functions take an (ni, nj, 3) structured block of node coordinates.
"""

from __future__ import annotations

import numpy as np


def _quad_corner_vectors(nodes: np.ndarray) -> tuple[np.ndarray, ...]:
    p00 = nodes[:-1, :-1, :]
    p10 = nodes[1:, :-1, :]
    p11 = nodes[1:, 1:, :]
    p01 = nodes[:-1, 1:, :]
    return p00, p10, p11, p01


def scaled_jacobian(nodes: np.ndarray) -> np.ndarray:
    """Per-quad minimum scaled corner Jacobian, shape (ni-1, nj-1)."""
    p00, p10, p11, p01 = _quad_corner_vectors(nodes)
    corners = (
        (p00, p10 - p00, p01 - p00),
        (p10, p11 - p10, p00 - p10),
        (p11, p01 - p11, p10 - p11),
        (p01, p00 - p01, p11 - p01),
    )
    per_corner = []
    reference_normal = None
    for _origin, e1, e2 in corners:
        cross = np.cross(e1, e2)
        norm = np.linalg.norm(cross, axis=-1)
        len1 = np.linalg.norm(e1, axis=-1)
        len2 = np.linalg.norm(e2, axis=-1)
        denom = np.where(len1 * len2 > 0, len1 * len2, 1.0)
        if reference_normal is None:
            reference_normal = cross
            sign = np.ones_like(norm)
        else:
            sign = np.sign(np.sum(cross * reference_normal, axis=-1))
            sign = np.where(sign == 0, 1.0, sign)
        per_corner.append(sign * norm / denom)
    return np.min(np.stack(per_corner, axis=0), axis=0)


def equiangle_skewness(nodes: np.ndarray) -> np.ndarray:
    """Per-quad equiangle skewness max(|theta-90|)/90, shape (ni-1, nj-1)."""
    p00, p10, p11, p01 = _quad_corner_vectors(nodes)
    corner_edges = (
        (p10 - p00, p01 - p00),
        (p11 - p10, p00 - p10),
        (p01 - p11, p10 - p11),
        (p00 - p01, p11 - p01),
    )
    worst = None
    for e1, e2 in corner_edges:
        len1 = np.linalg.norm(e1, axis=-1)
        len2 = np.linalg.norm(e2, axis=-1)
        denom = np.where(len1 * len2 > 0, len1 * len2, 1.0)
        cos_theta = np.clip(np.sum(e1 * e2, axis=-1) / denom, -1.0, 1.0)
        theta = np.degrees(np.arccos(cos_theta))
        deviation = np.abs(theta - 90.0) / 90.0
        worst = deviation if worst is None else np.maximum(worst, deviation)
    return worst


def aspect_ratio(nodes: np.ndarray) -> np.ndarray:
    """Per-quad aspect ratio (mean i-edge length vs mean j-edge length)."""
    i_edges = np.linalg.norm(nodes[1:, :, :] - nodes[:-1, :, :], axis=-1)
    j_edges = np.linalg.norm(nodes[:, 1:, :] - nodes[:, :-1, :], axis=-1)
    mean_i = 0.5 * (i_edges[:, :-1] + i_edges[:, 1:])
    mean_j = 0.5 * (j_edges[:-1, :] + j_edges[1:, :])
    lo = np.minimum(mean_i, mean_j)
    hi = np.maximum(mean_i, mean_j)
    return np.where(lo > 0, hi / np.where(lo > 0, lo, 1.0), np.inf)


def growth_ratio(nodes: np.ndarray) -> float:
    """Max adjacent-cell size ratio along each index direction (scalar)."""
    i_len = np.linalg.norm(nodes[1:, :, :] - nodes[:-1, :, :], axis=-1)
    j_len = np.linalg.norm(nodes[:, 1:, :] - nodes[:, :-1, :], axis=-1)
    ratios = []
    for lengths, axis in ((i_len, 0), (j_len, 1)):
        if lengths.shape[axis] < 2:
            continue
        a = np.take(lengths, range(1, lengths.shape[axis]), axis=axis)
        b = np.take(lengths, range(0, lengths.shape[axis] - 1), axis=axis)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(b > 0, a / np.where(b > 0, b, 1.0), np.inf)
        ratios.append(np.max(np.maximum(ratio, 1.0 / np.where(ratio > 0, ratio, 1.0))))
    return float(max(ratios)) if ratios else 1.0


def block_quality_metrics(nodes: np.ndarray) -> dict[str, float]:
    """The industry metric set for one structured block, JSON-ready."""
    nodes = np.asarray(nodes, dtype=float)
    if nodes.ndim != 3 or nodes.shape[2] != 3 or min(nodes.shape[:2]) < 2:
        raise ValueError(f"expected (ni>=2, nj>=2, 3) node array, got {nodes.shape}")
    jacobian = scaled_jacobian(nodes)
    skew = equiangle_skewness(nodes)
    ar = aspect_ratio(nodes)
    return {
        "min_scaled_jacobian": float(np.min(jacobian)),
        "mean_scaled_jacobian": float(np.mean(jacobian)),
        "max_equiangle_skewness": float(np.max(skew)),
        "mean_equiangle_skewness": float(np.mean(skew)),
        "max_aspect_ratio": float(np.max(ar)),
        "max_growth_ratio": growth_ratio(nodes),
    }
