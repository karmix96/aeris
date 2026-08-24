"""Region-resolved surface-mesh QC.

``aeris.mesh.surface`` reports quality per *block*. A block is a topology
artefact; the reviewer's question is about *places on the aircraft* — the
leading edge, the trailing edge, the tip, the root, the mid-chord run. This
module re-scores an existing structured surface by region so a failure can be
attributed to a feature rather than to a zone name.

Metrics are the same Verdict/Fluent definitions the rest of the codebase uses
(``aeris.cfd.meshing.quality``), computed per cell so they can be pooled into
any subset.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Array = np.ndarray


# --------------------------------------------------------------- per cell ---
def cell_metrics(nodes: Array) -> dict[str, Array]:
    """Per-cell metric fields for one (ni, nj, 3) structured block."""
    p00 = nodes[:-1, :-1, :]
    p10 = nodes[1:, :-1, :]
    p11 = nodes[1:, 1:, :]
    p01 = nodes[:-1, 1:, :]

    corners = (
        (p10 - p00, p01 - p00),
        (p11 - p10, p00 - p10),
        (p01 - p11, p10 - p11),
        (p00 - p01, p11 - p01),
    )

    shape_parts, skew_parts, jac_parts = [], [], []
    reference = None
    for e1, e2 in corners:
        cross = np.cross(e1, e2)
        norm = np.linalg.norm(cross, axis=-1)
        l1 = np.linalg.norm(e1, axis=-1)
        l2 = np.linalg.norm(e2, axis=-1)
        denom = np.where(l1 * l2 > 0, l1 * l2, 1.0)

        sq = np.sum(e1 * e1, axis=-1) + np.sum(e2 * e2, axis=-1)
        shape_parts.append(np.divide(2.0 * norm, sq, out=np.zeros_like(norm), where=sq > 0))

        cos_t = np.clip(np.sum(e1 * e2, axis=-1) / denom, -1.0, 1.0)
        skew_parts.append(np.abs(np.degrees(np.arccos(cos_t)) - 90.0) / 90.0)

        if reference is None:
            reference = cross
            sign = np.ones_like(norm)
        else:
            sign = np.sign(np.sum(cross * reference, axis=-1))
            sign = np.where(sign == 0, 1.0, sign)
        jac_parts.append(sign * norm / denom)

    i_edges = np.linalg.norm(nodes[1:, :, :] - nodes[:-1, :, :], axis=-1)
    j_edges = np.linalg.norm(nodes[:, 1:, :] - nodes[:, :-1, :], axis=-1)
    mean_i = 0.5 * (i_edges[:, :-1] + i_edges[:, 1:])
    mean_j = 0.5 * (j_edges[:-1, :] + j_edges[1:, :])
    lo = np.minimum(mean_i, mean_j)
    hi = np.maximum(mean_i, mean_j)

    n1 = np.cross(p10 - p00, p11 - p00)
    n2 = np.cross(p11 - p00, p01 - p00)
    area = 0.5 * (np.linalg.norm(n1, axis=-1) + np.linalg.norm(n2, axis=-1))
    fold_denom = np.linalg.norm(n1, axis=-1) * np.linalg.norm(n2, axis=-1)
    fold = np.divide(
        np.sum(n1 * n2, axis=-1), fold_denom, out=np.full_like(area, -1.0), where=fold_denom > 0
    )

    return {
        "shape": np.min(np.stack(shape_parts), axis=0),
        "skew": np.max(np.stack(skew_parts), axis=0),
        "scaled_jacobian": np.min(np.stack(jac_parts), axis=0),
        "aspect_ratio": np.where(lo > 0, hi / np.where(lo > 0, lo, 1.0), np.inf),
        "area": area,
        "fold": fold,
        "centroid": 0.25 * (p00 + p10 + p11 + p01),
    }


def growth_field(nodes: Array) -> Array:
    """Per-cell worst adjacent size ratio, aligned with the cell grid."""
    i_len = np.linalg.norm(nodes[1:, :, :] - nodes[:-1, :, :], axis=-1)
    j_len = np.linalg.norm(nodes[:, 1:, :] - nodes[:, :-1, :], axis=-1)
    size_i = 0.5 * (i_len[:, :-1] + i_len[:, 1:])
    size_j = 0.5 * (j_len[:-1, :] + j_len[1:, :])
    out = np.ones_like(size_i)
    for size, axis in ((size_i, 0), (size_j, 1)):
        if size.shape[axis] < 2:
            continue
        a = np.take(size, range(1, size.shape[axis]), axis=axis)
        b = np.take(size, range(0, size.shape[axis] - 1), axis=axis)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(b > 0, a / np.where(b > 0, b, 1.0), np.inf)
        ratio = np.maximum(ratio, 1.0 / np.where(ratio > 0, ratio, 1.0))
        pad = [(0, 0), (0, 0)]
        lo = np.pad(ratio, [(1, 0), (0, 0)] if axis == 0 else [(0, 0), (1, 0)], constant_values=1.0)
        hi = np.pad(ratio, [(0, 1), (0, 0)] if axis == 0 else [(0, 0), (0, 1)], constant_values=1.0)
        _ = pad
        out = np.maximum(out, np.maximum(lo, hi))
    return out


# ---------------------------------------------------------------- summary ---
_WORST = {
    "shape": "min",
    "scaled_jacobian": "min",
    "fold": "min",
    "skew": "max",
    "aspect_ratio": "max",
    "growth": "max",
}


@dataclass(frozen=True)
class RegionScore:
    name: str
    cells: int
    values: dict[str, float]

    def line(self) -> str:
        v = self.values
        return (
            f"{self.name:<16}{self.cells:>8}"
            f"{v['shape']:>9.3f}{v['skew']:>9.3f}{v['scaled_jacobian']:>9.3f}"
            f"{v['aspect_ratio']:>9.2f}{v['growth']:>9.3f}{v['fold']:>9.3f}"
            f"{v['skew_p99']:>9.3f}"
        )


HEADER = (
    f"{'region':<16}{'cells':>8}{'shape':>9}{'skew':>9}{'sclJac':>9}"
    f"{'AR':>9}{'growth':>9}{'fold':>9}{'skew99':>9}"
)


def score(fields: dict[str, Array], mask: Array | None, name: str) -> RegionScore | None:
    """Pool per-cell fields over ``mask`` into one worst-case region score."""
    take = (lambda a: a) if mask is None else (lambda a: a[mask])
    n = int(take(fields["shape"]).size)
    if n == 0:
        return None
    out: dict[str, float] = {}
    for key, how in _WORST.items():
        values = take(fields[key])
        out[key] = float(np.min(values) if how == "min" else np.max(values))
    out["skew_p99"] = float(np.percentile(take(fields["skew"]), 99))
    out["skew_mean"] = float(np.mean(take(fields["skew"])))
    out["area_min"] = float(np.min(take(fields["area"])))
    return RegionScore(name, n, out)


def block_fields(nodes: Array) -> dict[str, Array]:
    fields = cell_metrics(nodes)
    fields["growth"] = growth_field(nodes)
    return fields


def pooled(blocks: dict[str, Array], names: list[str]) -> dict[str, Array]:
    """Concatenate per-cell fields from several blocks into flat arrays."""
    keys = ("shape", "skew", "scaled_jacobian", "aspect_ratio", "growth", "fold", "area")
    acc: dict[str, list[Array]] = {k: [] for k in keys}
    for name in names:
        fields = block_fields(blocks[name])
        for k in keys:
            acc[k].append(np.asarray(fields[k]).ravel())
    return {k: np.concatenate(v) if v else np.zeros(0) for k, v in acc.items()}
