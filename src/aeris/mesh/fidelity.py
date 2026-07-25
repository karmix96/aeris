"""The five-level mesh fidelity ladder, shared by the structured and unstructured paths.

Why this module exists
----------------------
AERIS already has both mesh families: structured (``wing_cap4_v1`` surface →
pyHyp extrusion, ``airfoil_ogrid_v1``) and unstructured (``airfoil_gmsh_tri_v1``,
``cad_gmsh_tet_v1``). What it did not have is a **single definition of what a
fidelity level means**, so two things were impossible:

1. **Grid convergence with a verified order.** The structured family had three
   levels. Three levels give exactly one GCI triplet, so the observed order of
   convergence *p* can be computed but never checked — a single number with no
   way to tell a converging sequence from a coincidence. Five levels give three
   nested triplets, so *p* is computed three times and its consistency is itself
   evidence.
2. **A controlled structured-vs-unstructured comparison.** With separate,
   independently-chosen parameters, "structured L2 vs unstructured L2" compared
   two arbitrary meshes. Here one level means one nominal cell size in *both*
   families, so the difference that remains is attributable to the discretisation
   type rather than to resolution.

The ladder
----------
One geometric refinement ratio ``r`` applied to the *linear* cell size, held
constant across every level and every backend::

    h_k = h_ref * r**(L_REF - k)          k = 0 (coarsest) … 4 (finest)

``r = 1.4`` is inherited from the validated cap4 family (49 → 71 → 97
points-per-side is r = 1.449, 1.366). A constant ratio is what Richardson
extrapolation and the Roache GCI assume; drifting it invalidates the estimate.

Anchoring, and one deliberate change to the existing family
-----------------------------------------------------------
Level 2 is the anchor and reproduces the validated ``production`` preset exactly
— 97 points per side, s0_frac 4.4e-6, 8 spanwise panels. L0 reproduces ``smoke``
exactly (49).

**L1 is 69 points, where the historical ``fine`` preset is 71.** That is not a
transcription error. The old three-level family is 49 → 71 → 97, i.e. r = 1.449
then 1.366 — the ratio *drifts by 6 %*. Richardson extrapolation and the GCI
both assume a constant ratio, so a family with a drifting r cannot support a
defensible convergence estimate no matter how many levels it has. Fixing r at
exactly 1.4 costs two points at one level and buys an assumption the method
actually requires.

Consequence to be honest about: solver results computed on the old ``fine``
preset are on a 71-point mesh, not this ladder's L1. They remain valid as
results; they may not be mixed into a GCI triplet with L0/L2 without noting the
ratio drift. Anything new should use the ladder.

L3 and L4 extend finer, which is the direction GCI needs — the reference
solution must be the finest rung, not the middle one.

The wall-spacing law ``s0_frac(p) = S0_FRAC_REF * (P_REF / p)`` is likewise
inherited: wall spacing coarsens at the same rate as in-plane spacing, so y+
scales with the family rather than jumping between levels.

What is NOT scaled, and why
---------------------------
The structured tip cap is held constant across all levels (validated policy —
see ``aeris.mesh.presets``: it tiles a fixed-size feature, and every attempt to
coarsen it folds the hyperbolic march). It covers < 2 % of the surface, so the
family ratio is unaffected in practice. This is a documented, deliberate
departure from uniform refinement and it is recorded in every report this module
produces, because a reviewer is entitled to know the refinement is not uniform
everywhere.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "REFINEMENT_RATIO",
    "P_REF",
    "S0_FRAC_REF",
    "L_REF",
    "FidelityLevel",
    "LEVELS",
    "level",
    "structured_params",
    "unstructured_params",
    "cell_size_ratio",
    "richardson_extrapolate",
    "grid_convergence_index",
    "observed_order",
]

# ---------------------------------------------------------------- the law ---
REFINEMENT_RATIO: float = 1.4
"""Linear cell-size ratio between adjacent levels. Constant by construction —
Richardson extrapolation and the Roache GCI both assume it."""

P_REF: int = 97
"""Structured points-per-side at the anchor level (L2). Inherited from the
validated cap4 production preset."""

S0_FRAC_REF: float = 4.4e-6
"""Wall-spacing fraction at the anchor level (y+ ~ 0.2 at the design condition)."""

L_REF: int = 2
"""Index of the anchor level. L0 and L2 reproduce the validated smoke/production
presets exactly; L1 is 69 rather than the historical 71 so that r is exactly
constant (see the module docstring). L3/L4 extend the ladder finer."""

_NAMES = ("L0_smoke", "L1_coarse", "L2_production", "L3_fine", "L4_reference")
_ROLES = (
    "laptop smoke test; solver plumbing only, not for reported numbers",
    "cheap sweep level; DoE screening",
    "anchor — the validated production mesh; default for reported results",
    "refinement rung for grid convergence",
    "finest rung; the Richardson reference solution",
)


@dataclass(frozen=True)
class FidelityLevel:
    """One rung of the ladder, backend-independent."""

    index: int
    name: str
    role: str
    h_ratio: float
    """Linear cell size relative to the anchor level. <1 = finer."""

    def scaled(self, anchor_value: float) -> float:
        """Scale a length-like anchor quantity to this level."""
        return anchor_value * self.h_ratio

    def scaled_count(self, anchor_count: int, *, minimum: int = 2) -> int:
        """Scale a count-like anchor quantity (inverse of cell size)."""
        return max(int(minimum), int(round(anchor_count / self.h_ratio)))


LEVELS: tuple[FidelityLevel, ...] = tuple(
    FidelityLevel(
        index=k,
        name=_NAMES[k],
        role=_ROLES[k],
        h_ratio=REFINEMENT_RATIO ** (L_REF - k),
    )
    for k in range(5)
)


def level(which: int | str) -> FidelityLevel:
    """Look a level up by index (0-4) or by name (``"L2_production"``, ``"L2"``)."""
    if isinstance(which, int):
        if not 0 <= which < len(LEVELS):
            raise ValueError(f"fidelity level must be 0..{len(LEVELS)-1}, got {which}")
        return LEVELS[which]
    key = str(which).strip()
    for lv in LEVELS:
        if key in (lv.name, lv.name.split("_")[0], lv.name.split("_", 1)[1]):
            return lv
    raise ValueError(f"unknown fidelity level {which!r}; known: {[l.name for l in LEVELS]}")


def cell_size_ratio(coarse: int | str, fine: int | str) -> float:
    """h_coarse / h_fine — the ``r`` a GCI on this pair must use."""
    return level(coarse).h_ratio / level(fine).h_ratio


# ------------------------------------------------------- backend mappings ---
def structured_params(which: int | str) -> dict[str, Any]:
    """Structured (cap4 + pyHyp) parameters for a level.

    ``points_per_side`` and ``spanwise_panels`` scale as 1/h; the wall spacing
    follows the inherited family law so y+ tracks the family. The tip cap is
    held constant by validated policy and is flagged as such.
    """
    lv = level(which)
    pts = lv.scaled_count(P_REF, minimum=17)
    # Spanwise panels must stay even for the cap4 topology's symmetric split.
    panels = max(2, int(round(8 / lv.h_ratio)))
    if panels % 2:
        panels += 1
    return {
        "level": lv.name,
        "level_index": lv.index,
        "h_ratio": lv.h_ratio,
        "points_per_side": pts,
        "spanwise_panels": panels,
        "s0_frac": S0_FRAC_REF * (P_REF / pts),
        # Validated constant cap policy — deliberately NOT refined.
        "cap_width_frac": 0.5,
        "cap_wrap_points": 17,
        "cap_wrap_x": 0.015,
        "cap_is_refined": False,
        "uniform_refinement": False,
        "uniform_refinement_note": (
            "tip cap held constant across the family by validated policy "
            "(covers <2% of the surface; coarsening it folds the hyperbolic march)"
        ),
    }


def unstructured_params(
    which: int | str,
    *,
    reference_length: float,
    anchor_cells_per_length: float = 97.0,
    first_layer_frac: float | None = None,
    growth: float = 1.2,
    target_bl_thickness_frac: float = 0.02,
) -> dict[str, Any]:
    """Unstructured (gmsh) parameters for the SAME level.

    The link that makes the two families comparable: the unstructured
    characteristic length is set so that a reference length is spanned by the
    same number of cells the structured family would use at that level. So
    "L2" means one nominal resolution in both, and a structured-vs-unstructured
    comparison at fixed level is controlled.

    The boundary layer follows the same wall-spacing law, and the layer count is
    derived (not chosen) from first height, growth ratio and a target BL
    thickness — so it refines with the family instead of being a free parameter.
    """
    lv = level(which)
    if reference_length <= 0:
        raise ValueError("reference_length must be positive")
    cells = anchor_cells_per_length / lv.h_ratio
    h = reference_length / cells

    s0_frac = first_layer_frac if first_layer_frac is not None else (
        S0_FRAC_REF * (P_REF / lv.scaled_count(P_REF, minimum=17))
    )
    first_layer = s0_frac * reference_length
    target = target_bl_thickness_frac * reference_length
    # n such that first_layer * (growth**n - 1)/(growth - 1) >= target
    if growth <= 1.0:
        raise ValueError("growth must exceed 1")
    n_layers = max(
        5,
        int(math.ceil(math.log1p(target * (growth - 1.0) / first_layer) / math.log(growth))),
    )
    return {
        "level": lv.name,
        "level_index": lv.index,
        "h_ratio": lv.h_ratio,
        "characteristic_length": h,
        "cells_per_reference_length": cells,
        "first_layer_height": first_layer,
        "bl_growth_ratio": growth,
        "bl_layers": n_layers,
        "bl_thickness": first_layer * (growth**n_layers - 1.0) / (growth - 1.0),
        "uniform_refinement": True,
    }


# --------------------------------------------------- convergence machinery --
def observed_order(
    f_coarse: float, f_medium: float, f_fine: float, r: float = REFINEMENT_RATIO
) -> float | None:
    """Observed order of convergence p from three levels at constant ratio r.

        p = ln(|f_coarse - f_medium| / |f_medium - f_fine|) / ln(r)

    Returns None when the differences are degenerate (equal or zero), which is
    the honest answer — an oscillating or converged-to-noise triplet has no
    meaningful order and reporting one would be fabrication.
    """
    d_cm = f_coarse - f_medium
    d_mf = f_medium - f_fine
    if abs(d_mf) < 1e-30 or abs(d_cm) < 1e-30:
        return None
    ratio = d_cm / d_mf
    if ratio <= 0:  # non-monotone: the triplet is not in the asymptotic range
        return None
    return math.log(ratio) / math.log(r)


def richardson_extrapolate(
    f_medium: float, f_fine: float, p: float, r: float = REFINEMENT_RATIO
) -> float:
    """Estimate the h -> 0 value from the two finest levels and the order p."""
    return f_fine + (f_fine - f_medium) / (r**p - 1.0)


def grid_convergence_index(
    f_coarse: float,
    f_medium: float,
    f_fine: float,
    *,
    r: float = REFINEMENT_RATIO,
    safety_factor: float = 1.25,
) -> dict[str, Any]:
    """Roache Grid Convergence Index for one triplet.

    Returns the observed order, the extrapolated value, the fine-grid GCI (an
    error band on the finest level, expressed as a fraction), and — importantly
    — an ``asymptotic_ratio`` that should be near 1 if the triplet really is in
    the asymptotic range. A GCI quoted without that check is not evidence.

    ``safety_factor`` 1.25 is Roache's recommendation when three or more grids
    are used (3.0 for two).
    """
    p = observed_order(f_coarse, f_medium, f_fine, r)
    out: dict[str, Any] = {
        "f_coarse": f_coarse, "f_medium": f_medium, "f_fine": f_fine,
        "r": r, "safety_factor": safety_factor, "observed_order": p,
    }
    if p is None:
        out.update(
            converging=False,
            reason="non-monotone or degenerate triplet — not in the asymptotic range",
            gci_fine=None, extrapolated=None, asymptotic_ratio=None,
        )
        return out

    denom = f_fine if abs(f_fine) > 1e-30 else 1.0
    e_fine = abs((f_fine - f_medium) / denom)
    e_coarse = abs((f_medium - f_coarse) / denom)
    gci_fine = safety_factor * e_fine / (r**p - 1.0)
    gci_coarse = safety_factor * e_coarse / (r**p - 1.0)
    out.update(
        converging=True,
        extrapolated=richardson_extrapolate(f_medium, f_fine, p, r),
        relative_error_fine=e_fine,
        gci_fine=gci_fine,
        gci_coarse=gci_coarse,
        # ~1 means the pair of GCIs is consistent with the claimed order.
        asymptotic_ratio=(gci_coarse / (r**p * gci_fine)) if gci_fine > 0 else None,
    )
    return out


def convergence_study(values: dict[int | str, float], **kwargs: Any) -> dict[str, Any]:
    """Run GCI on every nested triplet of a 5-level sweep.

    This is what five levels buys over three: the observed order is computed
    three times instead of once, so a claim that the sequence is converging can
    be *checked* rather than asserted. Spread in p across triplets is reported
    and is the honest signal of whether the asymptotic range has been reached.
    """
    ordered = sorted(((level(k).index, v) for k, v in values.items()))
    idx = [i for i, _ in ordered]
    vals = [v for _, v in ordered]
    triplets = []
    for a in range(len(idx) - 2):
        c, m, f = idx[a], idx[a + 1], idx[a + 2]
        r = cell_size_ratio(c, m)
        r2 = cell_size_ratio(m, f)
        if abs(r - r2) > 1e-9:
            continue  # non-uniform triplet: GCI's constant-r assumption fails
        g = grid_convergence_index(vals[a], vals[a + 1], vals[a + 2], r=r, **kwargs)
        g["levels"] = (LEVELS[c].name, LEVELS[m].name, LEVELS[f].name)
        triplets.append(g)

    orders = [t["observed_order"] for t in triplets if t.get("observed_order") is not None]
    out: dict[str, Any] = {"triplets": triplets, "n_triplets": len(triplets)}
    if orders:
        out["order_mean"] = sum(orders) / len(orders)
        out["order_spread"] = max(orders) - min(orders)
        out["orders_consistent"] = out["order_spread"] < 0.5
    else:
        out["order_mean"] = None
        out["order_spread"] = None
        out["orders_consistent"] = False
    finest = [t for t in triplets if t.get("gci_fine") is not None]
    out["gci_finest"] = finest[-1]["gci_fine"] if finest else None
    return out
