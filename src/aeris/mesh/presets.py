"""
Named mesh family presets for the cap4 structured-mesh campaign.

The family (smoke / fine / production) refines the OML in all three index
directions at a near-constant ratio r ~ 1.4 (DSE_READINESS.md section 5), so
Richardson extrapolation / GCI on solver outputs is defensible:

    preset       pts/side  span panels   N (normal)   s0_frac
    smoke            49         4           129        8.8e-6
    fine             71         6           193        6.0e-6
    production       97         8           257        4.4e-6

s0 follows the family law s0_frac(p) = S0_FRAC_REF * (P_REF / p): the wall
spacing coarsens at the same ratio as the in-plane spacing.  (The pre-family
"y+ ~ 1 at the coarse level" fracs of 2.2e-5 marched invalid on cap4 at 49
pts/side: the first layers stride too far relative to the blunt-TE base
cells and the front folds at the root TE base before smoothing can act —
measured, 2026-07-17.)

The tip cap does NOT coarsen with the family, by policy.  The cap tiles a
fixed-size feature (tip thickness x tip chord), so its cells cannot grow
with the OML spacing; every attempt to coarsen it (fewer wrap points,
narrower camber rectangle) concentrates the blunt-TE corner turn or shrinks
the center-strip cells and folds the march (measured: wrap 9 -> 143 deg
adjacent-normal angle, inversion at layer 15; width_frac 0.15 -> 1.5e-7
center cells, NaN at layer 5).  The validated cap (width_frac 0.5, wrap 17,
collar 3 points) is therefore held constant on every level; it covers < 2%
of the surface, so the family ratio is unaffected in practice.

``cap_wrap_x`` is 0.015 on every level (not the old 0.03): the wrap points
spread uniformly over the wrap arc, and at 0.03 the blunt base is crossed by
a single cell that absorbs both ~90 deg corner turns — the coarse-level march
folds exactly there (root TE base, measured).  Halving the arc doubles the
base resolution and the whole family marches with zero low-quality layers.

March control is one family-wide policy (damped harder than the old
defaults; needed at 49 pts/side, harmless above): cMax 0.5, epsE 6, epsI 12,
volSmoothIter 1200, nConstantStart 3.

Everything here is a deterministic function of the preset name, satisfying
the C1/C2 "one documented policy, no per-case tuning" criterion.
"""

from __future__ import annotations

from dataclasses import dataclass

P_REF: int = 97            # points_per_side of the production level
S0_FRAC_REF: float = 4.4e-6  # production wall-spacing fraction (y+ ~ 0.2)

# Fixed cap policy (validated; held constant across the family).
CAP_WIDTH_FRAC: float = 0.5
CAP_WRAP_POINTS: int = 17
CAP_WRAP_X: float = 0.015

# Family-wide pyHyp march policy.
MARCH_POLICY: dict[str, float | int] = {
    "c_max": 0.5,
    "eps_e_far": 6.0,
    "eps_i_far": 12.0,
    "vol_smooth_iter": 1200,
    "n_constant_start": 3,
}


def family_s0_frac(points_per_side: int) -> float:
    """Wall-spacing law: s0 coarsens at the same ratio as the in-plane spacing."""
    return S0_FRAC_REF * (P_REF / float(points_per_side))


@dataclass(frozen=True)
class MeshPreset:
    name: str
    points_per_side: int
    spanwise_panels: int
    description: str
    cap_width_frac: float = CAP_WIDTH_FRAC
    cap_wrap_points: int = CAP_WRAP_POINTS
    cap_wrap_x: float = CAP_WRAP_X


MESH_PRESETS: dict[str, MeshPreset] = {
    "smoke": MeshPreset(
        name="smoke",
        points_per_side=49,
        spanwise_panels=4,
        description="Coarse family level - cheap solver smoke tests on a laptop.",
    ),
    "fine": MeshPreset(
        name="fine",
        points_per_side=71,
        spanwise_panels=6,
        description="Medium family level - grid-convergence middle rung.",
    ),
    "production": MeshPreset(
        name="production",
        points_per_side=97,
        spanwise_panels=8,
        description="Fine family level - full-resolution DSE recipe.",
    ),
}
