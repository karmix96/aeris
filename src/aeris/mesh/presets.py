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

# Preset VALUES live as data in aeris.cfd.presets (YAML, schema
# aeris.cfd.preset.v1) — one inspectable source of truth for CLI, GUI, and
# the case runner.  This module keeps its public exports (MESH_PRESETS,
# MARCH_POLICY, CAP_*) for backward compatibility; the scaling LAWS stay
# here as code.  tests/cfd/test_presets_registry.py pins the loaded values
# to the validated numbers.
from aeris.cfd.presets.registry import list_presets

P_REF: int = 97  # points_per_side of the production level
S0_FRAC_REF: float = 4.4e-6  # production wall-spacing fraction (y+ ~ 0.2)


def family_s0_frac(points_per_side: int) -> float:
    """Wall-spacing law: s0 coarsens at the same ratio as the in-plane spacing."""
    return S0_FRAC_REF * (P_REF / float(points_per_side))


@dataclass(frozen=True)
class MeshPreset:
    name: str
    points_per_side: int
    spanwise_panels: int
    description: str
    cap_width_frac: float
    cap_wrap_points: int
    cap_wrap_x: float


def _load_family() -> tuple[dict[str, MeshPreset], dict[str, float | int]]:
    family = sorted(
        list_presets(kind="mesh_family"),
        key=lambda p: int(p.surface["points_per_side"]),  # coarse -> fine
    )
    if not family:
        raise RuntimeError("No mesh_family presets found in aeris.cfd.presets data")

    policies = [{k: v for k, v in p.volume.items() if k != "level"} for p in family]
    if any(policy != policies[0] for policy in policies[1:]):
        raise RuntimeError(
            "mesh_family presets must share one family-wide march policy "
            "(C1/C2: one documented policy, no per-case tuning)"
        )

    presets = {
        p.name: MeshPreset(
            name=p.name,
            points_per_side=int(p.surface["points_per_side"]),
            spanwise_panels=int(p.surface["spanwise_panels"]),
            description=p.description,
            cap_width_frac=float(p.surface["cap_width_frac"]),
            cap_wrap_points=int(p.surface["cap_wrap_points"]),
            cap_wrap_x=float(p.surface["cap_wrap_x"]),
        )
        for p in family
    }
    return presets, dict(policies[0])


MESH_PRESETS, MARCH_POLICY = _load_family()

# Fixed cap policy (validated; held constant across the family).
_reference = MESH_PRESETS[max(MESH_PRESETS, key=lambda n: MESH_PRESETS[n].points_per_side)]
CAP_WIDTH_FRAC: float = _reference.cap_width_frac
CAP_WRAP_POINTS: int = _reference.cap_wrap_points
CAP_WRAP_X: float = _reference.cap_wrap_x
