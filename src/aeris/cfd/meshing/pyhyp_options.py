"""
Single source of truth for pyHyp volume-extrusion options.

This module owns the pyHyp curated schema, the grid-level table, and the one
options builder both execution paths (in-process and subprocess) consume.
Before this existed the options dict lived in two hand-synchronized copies
inside ``aeris.mesh.pyhyp_runner`` — a documented drift risk.

Any pyHyp option not curated here can be passed verbatim through the
``pyhyp_options`` raw mapping (full user authority, provenance-tracked).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from aeris.cfd.options.layers import (
    EffectiveOptions,
    OptionLayer,
    aeris_defaults_layer,
    resolve_options,
)
from aeris.cfd.options.schema import CuratedOption, ToolOptionSchema

# `coarsen` decimates the INPUT surface before marching (coarsen=4 keeps every
# 8th surface point).  With the mid4 topology the flat wing-tip O-grid cap has
# cells ~1e3-1e4x smaller than the OML cells; empirically only coarsen=4
# decimates that jump enough for the hyperbolic marcher to produce a valid
# (positive-volume) volume mesh, so mid4 in-plane resolution is topology-
# limited.  The cap4 (camber-split, M6-style) topology removes that limit: it
# marches valid volumes at coarsen=1 (full in-plane resolution, validated at
# L1) but is incompatible with coarsening — decimation breaks its thin collar
# blocks.  Wall-NORMAL resolution is not limited in either topology: N up to
# 257 with s0 down to ~1e-5 m is validated valid.  Each level sets N and a
# default first-cell height as a fraction of characteristic length
# (overridable via s0); the coarsen values below apply to mid4/split8 runs.
GRID_LEVELS: dict[str, dict[str, object]] = {
    "candidate_c01": {"coarsen": 1, "N": 61, "s0_frac": 5.0e-6},
    "candidate_c02": {"coarsen": 1, "N": 73, "s0_frac": 4.7e-6},
    "candidate_c03": {"coarsen": 1, "N": 97, "s0_frac": 3.6e-6},
    "L1": {"coarsen": 4, "N": 257, "s0_frac": 4.4e-6},  # fine wall-resolved RANS (y+ ~ 0.2)
    "L2": {"coarsen": 4, "N": 193, "s0_frac": 8.8e-6},  # standard wall-resolved RANS
    "L3": {"coarsen": 4, "N": 129, "s0_frac": 2.2e-5},  # DEFAULT — validated baseline
    "L4": {"coarsen": 4, "N": 37, "s0_frac": 2.2e-5},  # coarse / quick topology check
    # cap4 family levels (see aeris.mesh.presets): full in-plane resolution,
    # all three index directions refine together at r ~ 1.4, and s0 follows
    # the family law s0_frac = 4.4e-6 * (97 / points_per_side).
    "smoke": {"coarsen": 1, "N": 129, "s0_frac": 8.8e-6},
    "fine": {"coarsen": 1, "N": 193, "s0_frac": 6.0e-6},
    "production": {"coarsen": 1, "N": 257, "s0_frac": 4.4e-6},
}

DEFAULT_LEVEL = "L3"

# Geometry-adaptive first-cell height fallback: fraction of characteristic
# length used when a level has no s0_frac.  Empirically 2.2e-5 * char_len gives
# y+ ~ 1 for the small low-Re BWB (char ≈ 2.27 m, Re ≈ 1e6 → s0 ≈ 5e-5 m).
S0_CHAR_FRACTION: float = 2.2e-5


def _positive(value: object) -> str | None:
    return None if float(value) > 0 else "must be > 0"  # type: ignore[arg-type]


def _non_negative(value: object) -> str | None:
    return None if float(value) >= 0 else "must be >= 0"  # type: ignore[arg-type]


def _at_least_one(value: object) -> str | None:
    return None if int(value) >= 1 else "must be >= 1"  # type: ignore[arg-type]


def _at_least_two(value: object) -> str | None:
    return None if int(value) >= 2 else "must be >= 2"  # type: ignore[arg-type]


PYHYP_SCHEMA = ToolOptionSchema(
    tool="pyhyp",
    curated=(
        CuratedOption(
            "input_file",
            "inputFile",
            str,
            doc="Surface mesh file to extrude (PLOT3D .fmt).",
        ),
        CuratedOption(
            "file_type",
            "fileType",
            str,
            "PLOT3D",
            doc="Surface file format.",
            citation="PLOT3D because pyHyp's CGNS reader fails on cgnsutilities output "
            "(AERIS finding, mesh WP1).",
        ),
        CuratedOption(
            "unattached_edges_are_symmetry",
            "unattachedEdgesAreSymmetry",
            bool,
            True,
            doc="Treat unattached surface edges as symmetry planes (half-model root plane).",
        ),
        CuratedOption(
            "outer_face_bc",
            "outerFaceBC",
            str,
            "farfield",
            doc="Boundary condition on the outer marched face.",
        ),
        CuratedOption(
            "auto_connect",
            "autoConnect",
            bool,
            True,
            doc="Auto-detect block-to-block connectivity of the input surface.",
        ),
        CuratedOption("bc", "BC", dict, {}, doc="Explicit boundary-condition overrides."),
        CuratedOption(
            "families",
            "families",
            str,
            "wall",
            doc="Family name assigned to wall surfaces (ADflow wall-function lookup).",
        ),
        CuratedOption(
            "n_grid",
            "N",
            int,
            doc="Number of wall-normal grid layers.",
            validate=_at_least_two,
        ),
        CuratedOption(
            "n_coarsen",
            "coarsen",
            int,
            doc="Input-surface decimation factor (1 = full in-plane resolution; "
            "cap4 topology requires 1, mid4 requires 4).",
            citation="GRID_LEVELS rationale; DSE_READINESS §5.",
            validate=_at_least_one,
        ),
        CuratedOption(
            "s0",
            "s0",
            float,
            doc="First cell wall-normal height [m]. For wall-resolved RANS pick "
            "s0 ≈ chord * 5 / (Re * sqrt(Cf/2)) for y+ ~ 1.",
            citation="Family law s0_frac = 4.4e-6 * (97/points_per_side); DSE_READINESS §5.",
            validate=_positive,
        ),
        CuratedOption(
            "march_dist",
            "marchDist",
            float,
            doc="Farfield march distance [m]; 25–50 characteristic lengths is "
            "standard external-aero practice.",
            validate=_positive,
        ),
        CuratedOption(
            "ps0",
            "ps0",
            float,
            -1.0,
            doc="Pseudo-grid initial spacing; -1 = automatic.",
        ),
        CuratedOption(
            "p_grid_ratio",
            "pGridRatio",
            float,
            -1.0,
            doc="Pseudo-grid growth ratio; -1 = automatic.",
        ),
        CuratedOption(
            "c_max",
            "cMax",
            float,
            0.7,
            doc="Max allowable cell size ratio before the marcher backs off. "
            "Lower = smoother but slower march.",
            citation="0.7 robust-AERIS default; damped MARCH_POLICY uses 0.5 "
            "(cap4 family, DSE_READINESS 2026-07-17).",
            validate=_positive,
        ),
        CuratedOption(
            "theta",
            "theta",
            float,
            3.0,
            doc="Angle-based smoothing weight; higher = better orthogonality "
            "near curved surfaces (2–5 typical).",
        ),
        CuratedOption(
            "n_constant_start",
            "nConstantStart",
            int,
            5,
            doc="Number of rigid (constant-spacing) first layers; keeps the "
            "blunt-TE wing-tip corner from folding on early steps.",
            validate=_non_negative,
        ),
        CuratedOption(
            "vol_coef",
            "volCoef",
            float,
            0.5,
            doc="Volume smoothing coefficient (0.1–0.5 typical).",
        ),
        CuratedOption(
            "vol_smooth_iter",
            "volSmoothIter",
            int,
            800,
            doc="Volume smoothing iterations per step.",
            citation="Heavier than the MDO Lab BWB reference (150) because the "
            "AERIS tip cap has sharper local curvature.",
            validate=_non_negative,
        ),
        CuratedOption(
            "vol_blend",
            "volBlend",
            float,
            0.004,
            doc="Blend factor between smoothed and marched coordinates.",
        ),
        CuratedOption(
            "eps_e_far",
            "epsE",
            float,
            4.0,
            doc="Explicit smoothing amplitude at the farfield boundary.",
        ),
        CuratedOption(
            "eps_i_far",
            "epsI",
            float,
            8.0,
            doc="Implicit smoothing amplitude at the farfield boundary.",
        ),
        CuratedOption(
            "ksp_rel_tol",
            "kspRelTol",
            float,
            1.0e-8,
            doc="PETSc KSP linear-solver relative convergence tolerance.",
            validate=_positive,
        ),
        CuratedOption(
            "ksp_max_its",
            "kspMaxIts",
            int,
            1500,
            doc="Maximum KSP iterations per marching step.",
            validate=_at_least_one,
        ),
        CuratedOption(
            "ksp_subspace_size",
            "kspSubspaceSize",
            int,
            50,
            doc="GMRES restart subspace size.",
            validate=_at_least_one,
        ),
        CuratedOption(
            "output_file",
            "outputFile",
            str,
            doc="Output volume CGNS path.",
        ),
    ),
)


def build_pyhyp_options(
    surface_plot3d: Path,
    *,
    level: str,
    characteristic_length: float,
    output_file: Path | None = None,
    # wall / marching
    s0: float | None = None,
    march_dist_factor: float = 25.0,
    # normal-direction grid overrides (None = use level defaults)
    n_grid: int | None = None,
    n_coarsen: int | None = None,
    # stability / smoothing overrides (None = aeris defaults from PYHYP_SCHEMA)
    c_max: float | None = None,
    theta: float | None = None,
    vol_coef: float | None = None,
    eps_e_far: float | None = None,
    eps_i_far: float | None = None,
    vol_smooth_iter: int | None = None,
    vol_blend: float | None = None,
    n_constant_start: int | None = None,
    # linear solver overrides
    ksp_rel_tol: float | None = None,
    ksp_max_its: int | None = None,
    # extra layers (e.g. preset:<name>, config) inserted between the derived
    # values and the explicit user overrides — curated aeris names only
    extra_layers: Sequence[OptionLayer] = (),
    # raw pass-through: any native pyHyp option, verbatim, merged last
    pyhyp_options: Mapping[str, object] | None = None,
) -> EffectiveOptions:
    """Resolve the full pyHyp options dict with per-key provenance.

    Layer order: aeris defaults < level table < derived (paths, march
    distance) < extra layers (preset, config) < explicit user overrides
    < raw pass-through.
    """
    if level not in GRID_LEVELS:
        raise ValueError(f"Unknown level {level!r}. Choose from: {list(GRID_LEVELS)}")
    if not characteristic_length > 0:
        raise ValueError(f"characteristic_length must be > 0, got {characteristic_length!r}")

    cfg = GRID_LEVELS[level]
    s0_frac = float(cfg.get("s0_frac", S0_CHAR_FRACTION))
    level_layer = OptionLayer(
        f"level:{level}",
        {
            "n_grid": int(cfg["N"]),
            "n_coarsen": int(cfg["coarsen"]),
            "s0": s0_frac * characteristic_length,
        },
    )
    derived: dict[str, object] = {
        "input_file": str(surface_plot3d),
        "march_dist": float(march_dist_factor) * characteristic_length,
    }
    if output_file is not None:
        derived["output_file"] = str(output_file)

    user_layer = OptionLayer(
        "user",
        {
            "s0": s0,
            "n_grid": n_grid,
            "n_coarsen": n_coarsen,
            "c_max": c_max,
            "theta": theta,
            "vol_coef": vol_coef,
            "eps_e_far": eps_e_far,
            "eps_i_far": eps_i_far,
            "vol_smooth_iter": vol_smooth_iter,
            "vol_blend": vol_blend,
            "n_constant_start": n_constant_start,
            "ksp_rel_tol": ksp_rel_tol,
            "ksp_max_its": ksp_max_its,
        },
    )

    layers = [
        aeris_defaults_layer(PYHYP_SCHEMA),
        level_layer,
        OptionLayer("derived", derived),
        *extra_layers,
        user_layer,
    ]
    if pyhyp_options:
        layers.append(OptionLayer("raw", dict(pyhyp_options), raw=True))
    return resolve_options(PYHYP_SCHEMA, layers)
