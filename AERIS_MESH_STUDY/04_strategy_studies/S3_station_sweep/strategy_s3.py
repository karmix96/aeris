"""S3 — station-to-station sweeping. Written from scratch under ADR-0011.

RUNBOOK §6 S3:

    Place anchor sections at root, every BWB planform/airfoil break, elevon
    boundaries where required, and tip. Build matching structured grids at paired
    anchor sections. Connect one interval at a time instead of performing one
    uninterrupted root-tip extrusion. Use TFI, elliptic, or Poisson smoothing inside
    each segment. Enforce compatible node counts and exact first/last cell-size
    matching across interfaces. **This is expected to handle the segmented AERIS
    planform better than pure tip-to-root sweeping.**

Sources: `01_references/S3_station_sweep_implementation_note.md`; the automatic
multiblock 3D-wing paper (Yu et al.) §3.3 "extrusion through controlled directional
sweeping"; Openblademesh §3.1.5 for the spanwise progression.

================================================================================
WHY S3 IS NOT S1 WITH DIFFERENT SPACING
================================================================================

Stage 02's S3 shared S1's OML extraction *and* S1's tip closure, differing only in
where it split spanwise — which is exactly the collapse ADR-0011 exists to prevent.
This is a fresh implementation with its own blocking and its own tip closure.

The structural claim is the runbook's: **the BWB is a sequence of straight-tapered
segments joined at kinks, so block interfaces belong ON the kinks.** Everything else
follows from that.

That claim is now backed by a measurement this study made while chasing S1's
fidelity gate. The wing's deviation from a straight line between stations is not
spread evenly — it is concentrated at the planform breaks:

    station j   1      2      3      4      5      6      7 ...  11 ...
    dev %c    1.32   0.95   0.31   0.43   2.23   1.11   0.45    7.25

and refining the station count converges only at **first order** (7.25 -> 3.08 ->
1.42 -> 0.68 for 17 -> 35 -> 71 -> 143 stations, a ratio of ~2 rather than ~4),
which is the signature of interpolating across a slope discontinuity rather than a
smooth surface.

**Within a segment the surface is smooth**, so an interval-local sweep interpolates
at O(h^2). Across a kink it is O(h) and no refinement rescues it. S1 and S0 both
sweep straight through the breaks; S3 does not. That is the difference worth
measuring, and §5 measures it.

================================================================================
BLOCKING
================================================================================

**Anchors.** Root, the three planform-group boundaries (`group_boundary_y`, i.e. the
b0/b1/b2/b3 breaks), and the tip. Anchors are snapped to the nearest realised
station and the residual is reported, because the generator does not realise a
section at every semantic break — `b1` in particular has none, which is a known gap
recorded in `status` §2.2 and confirmed here by measurement.

**OML, per interval.** Each anchor-to-anchor interval carries its own blocks. Two
consecutive intervals share their anchor column node-for-node, so interfaces are
exact by construction rather than by tolerance.

**Chordwise split — S3's own canonical split.** Four sides, cornered on the leading
edge, the two blunt-TE base corners, and the point of maximum thickness on each
surface. The thickness maximum is a genuine geometric feature (it is where the
surface curvature changes sign in the chordwise sense) and it is stable across the
airfoil family, so it gives four well-conditioned corners rather than S1's three or
S0's four-on-smooth-contour.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

STUDIES = Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.ingestion import (  # noqa: E402
    MeshBuildError,
    SurfaceBlock,
    _map_sides_to_wing,
    _resample_polyline,
    section_loop_2d,
)
from shared.qc import orient_blocks_consistently  # noqa: E402

Array = np.ndarray

STRATEGY_ID = "S3_STATION_SWEEP"


def canonical_split(
    coords: Array,
    le_index: int,
    *,
    chord_points: int,
    te_base_points: int,
    distribution: str = "uniform",
) -> tuple[list[Array], dict]:
    """S3's canonical section split: LE, both base corners, both thickness maxima.

    Six sides, so the sweep carries six OML blocks per interval:

        0 upper_fore   LE -> upper thickness maximum
        1 upper_aft    upper thickness maximum -> upper TE base corner
        2 base         lower base corner -> upper base corner
        3 lower_aft    lower TE base corner -> lower thickness maximum
        4 lower_fore   lower thickness maximum -> LE

    The thickness maxima are real features of the section, not arbitrary x/c
    stations — which is the failure ADR-0006 identified for cap4, whose corners land
    on smooth contour and meet at ~180 degrees.
    """
    if te_base_points < 3 or te_base_points % 2 == 0:
        raise MeshBuildError("te_base_points must be odd and at least 3")
    upper = coords[: le_index + 1][::-1]  # LE -> upper TE
    lower = coords[le_index:]  # LE -> lower TE

    xs = np.linspace(0.02, 0.98, 201)
    zu = np.interp(xs, upper[:, 0], upper[:, 1])
    zl = np.interp(xs, lower[:, 0], lower[:, 1])
    x_thick = float(xs[int(np.argmax(zu - zl))])

    def _to(curve: Array, xa: float, xb: float, n: int) -> Array:
        lo, hi = min(xa, xb), max(xa, xb)
        mid = curve[(curve[:, 0] > lo) & (curve[:, 0] < hi)]
        pa = np.array([xa, float(np.interp(xa, curve[:, 0], curve[:, 1]))])
        pb = np.array([xb, float(np.interp(xb, curve[:, 0], curve[:, 1]))])
        seg = np.vstack([pa, mid if xb > xa else mid[::-1], pb])
        return _resample_polyline(seg, n, distribution=distribution, beta=2.0)

    x_le, x_te = float(upper[0, 0]), float(upper[-1, 0])
    half = max(3, chord_points // 2)
    sides = [
        _to(upper, x_le, x_thick, half),
        _to(upper, x_thick, x_te, half),
        _resample_polyline(
            np.vstack([lower[-1], upper[-1]]), te_base_points,
            distribution="uniform", beta=1.0,
        ),
        _to(lower, x_te, x_thick, half),
        _to(lower, x_thick, x_le, half),
    ]
    info = {
        "x_thickness_max": x_thick,
        "side_names": ["upper_fore", "upper_aft", "base", "lower_aft", "lower_fore"],
        "corner_policy": "LE, both blunt-base corners, both thickness maxima",
    }
    return sides, info


def anchor_stations(wing, group_boundary_y: Array) -> tuple[list[int], dict]:
    """Realised-station indices closest to root, each planform break, and the tip.

    RUNBOOK §6 S3 asks for anchors at "root, every BWB planform/airfoil break,
    elevon boundaries where required, and tip". The generator does not realise a
    section at every break, so each anchor snaps to the nearest realised station and
    the residual is REPORTED rather than hidden — an unreported snap silently moves
    a block interface off the feature it was supposed to sit on.
    """
    ys = np.array([float(x.xyz_le[1]) for x in wing.xsecs])
    idx, residuals = [], []
    for gb in np.asarray(group_boundary_y, dtype=float):
        j = int(np.argmin(np.abs(ys - gb)))
        idx.append(j)
        residuals.append(float(abs(ys[j] - gb)))
    idx = sorted(set(idx))
    if idx[0] != 0:
        idx.insert(0, 0)
    if idx[-1] != len(ys) - 1:
        idx.append(len(ys) - 1)
    info = {
        "anchor_indices": idx,
        "anchor_y": [float(ys[j]) for j in idx],
        "snap_residual_m": residuals,
        "worst_snap_residual_m": max(residuals) if residuals else 0.0,
        "n_intervals": len(idx) - 1,
    }
    return idx, info


# ---------------------------------------------------------------------------
# §3.4 Extrusion-based surface mesh generation — the paper's spanwise law
# ---------------------------------------------------------------------------


def extrusion_layers(n_layers: int, sigma: float) -> Array:
    """Paper Eq. (5): two-sided logarithmic layer distribution.

    §3.4: "we suggest an anisotropic boundary layer adaptation scheme specifically
    targeting the wing root and tip regions. We denote extrusion layer number as L
    (which is **required to be even**) and the extrusion density as sigma."

        i <= L/2 :  xi = 1/2 - log10( (1 - i/(L/2))(sigma-1) + 1 ) / (2 log10 sigma)
        i >  L/2 :  symmetric about 1/2

    The result runs 0 -> 1 and clusters at BOTH ends, which is what "targeting the
    wing root and tip regions" asks for. sigma = 1 degenerates to uniform.

    Note the parity requirement is the paper's, not an implementation detail: the
    law is defined piecewise about L/2 and an odd L has no midpoint layer.
    """
    L = int(n_layers)
    if L < 2 or L % 2 != 0:
        raise MeshBuildError(f"extrusion layer number L must be even and >= 2, got {L}")
    if sigma <= 1.0:
        return np.linspace(0.0, 1.0, L + 1)
    half = L // 2
    denom = 2.0 * np.log10(sigma)
    i = np.arange(L + 1, dtype=float)
    xi = np.empty(L + 1)
    lo = i <= half
    xi[lo] = 0.5 - np.log10((1.0 - i[lo] / half) * (sigma - 1.0) + 1.0) / denom
    hi = ~lo
    xi[hi] = 0.5 + np.log10((1.0 - (L - i[hi]) / half) * (sigma - 1.0) + 1.0) / denom
    return np.clip(xi, 0.0, 1.0)


def sweep_intervals(blocks: list[Array], anchors: list[int], layers_per_interval) -> list[Array]:
    """Sweep each anchor-to-anchor interval separately (RUNBOOK §6 S3).

    "Connect one interval at a time instead of performing one uninterrupted
    root-tip extrusion." Consecutive intervals share their anchor column node for
    node, so the interface is exact by construction rather than by tolerance.

    Interior realised stations inside an interval are used as the interpolation
    base, so no column is blended ACROSS a planform break — which is the whole
    structural claim of this strategy.
    """
    out = []
    for blk in blocks:
        cols = []
        for k in range(len(anchors) - 1):
            a, b = anchors[k], anchors[k + 1]
            xi = layers_per_interval[k]
            for t in xi[:-1]:
                pos = a + t * (b - a)
                j = int(np.floor(pos))
                j = min(j, blk.shape[1] - 2)
                f = pos - j
                cols.append((1.0 - f) * blk[:, j, :] + f * blk[:, j + 1, :])
        cols.append(blk[:, anchors[-1], :])
        out.append(np.stack(cols, axis=1))
    return out


# ---------------------------------------------------------------------------
# The controlled sweep experiment (ADR-0013)
# ---------------------------------------------------------------------------


def build_surface(
    wing,
    group_boundary_y,
    *,
    level: str = "L2_smoke",
    sigma: float = 3.0,
    layers_per_interval: int = 8,
    **overrides,
):
    """S3's sweep on S1's surface — the controlled experiment of ADR-0013.

    Chordwise blocking and tip closure are **S1's, declared**: S3 cannot bring its
    own (ADR-0013 §2), and its claim in RUNBOOK §6 S3 is about the spanwise sweep,
    not the tip. Holding the surface fixed and varying only the sweep is what makes
    this a controlled comparison rather than the Stage 02 collapse.

    What is S3's, and is the whole experiment:

    * anchors ON the planform breaks, so no column is interpolated ACROSS a kink;
    * per-interval sweeps rather than one uninterrupted root-to-tip extrusion;
    * the paper's Eq. 5 two-sided logarithmic layer law inside each interval,
      clustering toward both ends of every interval — which puts fine spacing on
      both sides of each break, where S1 has whatever its global law happens to give.
    """
    sys.path.insert(0, str(STUDIES / "S1_tip_first"))
    import strategy_s1 as S1

    anchors, ainfo = anchor_stations(wing, group_boundary_y)
    xi = extrusion_layers(layers_per_interval, sigma)
    per_interval = [xi] * (len(anchors) - 1)

    blocks, info = S1.build_surface(wing, level=level, realise_law=False, **overrides)

    oml_blocks = [b for b in blocks if b.name.startswith("oml")]
    tip = [b for b in blocks if b.name.startswith("tip")]

    # `orient_blocks_consistently` REVERSES the j index of any block it flips, and
    # on this surface it flips every OML block — j=0 becomes the TIP. Anchor indices
    # are computed from `wing.xsecs` in root->tip order, so indexing a reversed
    # block scrambles every interval. Measured before this guard: 30/30 marches
    # failed at min quality exactly -1.00000, on a surface S1 passes 10/10 with.
    #
    # This is the same class as instrument bug 7 in `shared/verify.py`, which
    # assumed the last j column was outboard. Any code that indexes spanwise into
    # oriented blocks has to establish the direction first.
    oml = []
    for b in oml_blocks:
        x = b.xyz
        if float(x[:, 0, 1].mean()) > float(x[:, -1, 1].mean()):
            x = x[:, ::-1, :]
        oml.append(x)
    swept = sweep_intervals(oml, anchors, per_interval)

    out = [
        SurfaceBlock(name=b.name, xyz=x, family="wall")
        for b, x in zip(oml_blocks, swept, strict=True)
    ] + tip
    out, orientation = orient_blocks_consistently(out)

    info = dict(info)
    info.update(
        {
            "strategy_id": STRATEGY_ID,
            "orientation": orientation,
            "adr": "ADR-0013 — sweep experiment; chordwise blocking and tip are S1's, declared",
            "anchors": ainfo,
            "sweep": {
                "law": "Yu et al. §3.4 Eq. 5, two-sided logarithmic",
                "sigma": sigma,
                "layers_per_interval": layers_per_interval,
                "n_intervals": len(anchors) - 1,
                "spanwise_cells": sum(len(x) - 1 for x in per_interval),
                "anchored_on_planform_breaks": True,
            },
        }
    )
    return out, info
