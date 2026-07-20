"""
Single source of truth for SU2 configuration options.

SU2's native configuration is a flat ``KEY= VALUE`` text file, which makes
the raw pass-through trivial: any of SU2's several hundred config keys can
be injected verbatim through ``su2_options`` and lands as a line in the
generated ``.cfg`` — with provenance recorded, like every other tool.

Curated split mirrors the ADflow adapter: physics/convention invariants
(compressible RANS, CGNS mesh input, CSV history output, marker names
matching the pyHyp-generated grids) are aeris defaults; the solver strategy
(turbulence model, CFL, iteration budget, convergence target) lives in the
``su2_rans_sa_v1`` preset so model/strategy studies swap presets, not code.

Verification role (ASME V&V 20 style): SU2 consumes the *identical* CGNS
grid ADflow solved — same mesh, independent code — so force-coefficient
agreement is a code-verification statement, not a tuning exercise.
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


def _positive(value: object) -> str | None:
    return None if float(value) > 0 else "must be > 0"  # type: ignore[arg-type]


SU2_SCHEMA = ToolOptionSchema(
    tool="su2",
    curated=(
        CuratedOption("solver", "SOLVER", str, "RANS", doc="Governing equations."),
        CuratedOption(
            "turb_model",
            "KIND_TURB_MODEL",
            str,
            doc="Turbulence model (SA for TMR comparisons; SST available).",
        ),
        CuratedOption(
            "restart_sol", "RESTART_SOL", str, "NO", doc="Restart from a previous solution."
        ),
        # flow condition (derived from the case spec)
        CuratedOption("mach", "MACH_NUMBER", float, doc="Freestream Mach.", validate=_positive),
        CuratedOption("aoa", "AOA", float, doc="Angle of attack [deg]."),
        CuratedOption("sideslip", "SIDESLIP_ANGLE", float, 0.0, doc="Sideslip [deg]."),
        CuratedOption(
            "reynolds", "REYNOLDS_NUMBER", float, doc="Reynolds number.", validate=_positive
        ),
        CuratedOption(
            "reynolds_length",
            "REYNOLDS_LENGTH",
            float,
            doc="Reynolds reference length (chord).",
            validate=_positive,
        ),
        CuratedOption(
            "freestream_temperature",
            "FREESTREAM_TEMPERATURE",
            float,
            doc="Freestream static temperature [K].",
            validate=_positive,
        ),
        # references
        CuratedOption("ref_area", "REF_AREA", float, doc="Reference area.", validate=_positive),
        CuratedOption(
            "ref_length", "REF_LENGTH", float, doc="Moment reference length.", validate=_positive
        ),
        # mesh I/O — CGNS is the interchange format of the whole suite
        CuratedOption("mesh_filename", "MESH_FILENAME", str, doc="Mesh file path."),
        CuratedOption(
            "mesh_format",
            "MESH_FORMAT",
            str,
            "CGNS",
            doc="CGNS: the same grids pyHyp writes and ADflow solves.",
            citation="AIAA CGNS standard; suite-wide interchange format.",
        ),
        # markers — must match the BC names in the pyHyp-generated CGNS
        CuratedOption(
            "marker_wall",
            "MARKER_HEATFLUX",
            str,
            doc="Adiabatic viscous wall markers, e.g. '( wall, 0.0 )'.",
        ),
        CuratedOption("marker_far", "MARKER_FAR", str, doc="Farfield markers, e.g. '( far )'."),
        CuratedOption("marker_sym", "MARKER_SYM", str, doc="Symmetry markers."),
        CuratedOption(
            "marker_monitoring", "MARKER_MONITORING", str, doc="Markers for force monitoring."
        ),
        # numerics (strategy: preset; SU2 requires the convective scheme
        # to be set explicitly — no tool default)
        CuratedOption(
            "conv_num_method_flow",
            "CONV_NUM_METHOD_FLOW",
            str,
            doc="Convective scheme for the mean flow (ROE standard for RANS).",
        ),
        CuratedOption(
            "muscl_flow",
            "MUSCL_FLOW",
            str,
            doc="Second-order reconstruction (YES/NO).",
        ),
        CuratedOption(
            "slope_limiter_flow",
            "SLOPE_LIMITER_FLOW",
            str,
            doc="Slope limiter (NONE for smooth subsonic flows).",
        ),
        # convergence / budget (strategy: preset)
        CuratedOption("iter", "ITER", int, doc="Maximum solver iterations.", validate=_positive),
        CuratedOption("cfl", "CFL_NUMBER", float, doc="CFL number.", validate=_positive),
        CuratedOption("cfl_adapt", "CFL_ADAPT", str, doc="Adaptive CFL (YES/NO)."),
        CuratedOption("conv_field", "CONV_FIELD", str, doc="Convergence monitor field."),
        CuratedOption(
            "conv_residual_minval",
            "CONV_RESIDUAL_MINVAL",
            int,
            doc="Convergence target as log10 of the residual (e.g. -10).",
        ),
        # output
        CuratedOption(
            "output_files",
            "OUTPUT_FILES",
            str,
            "(RESTART, PARAVIEW, SURFACE_CSV)",
            doc="Solution outputs; ParaView for visualization parity with ADflow runs.",
        ),
        CuratedOption("tabular_format", "TABULAR_FORMAT", str, "CSV", doc="History table format."),
        CuratedOption(
            "history_output",
            "HISTORY_OUTPUT",
            str,
            "(ITER, RMS_RES, AERO_COEFF)",
            doc="Columns of history.csv (drives convergence parsing).",
        ),
    ),
)


def build_su2_options(
    mesh_cgns: Path,
    *,
    extra_layers: Sequence[OptionLayer] = (),
    su2_options: Mapping[str, object] | None = None,
) -> EffectiveOptions:
    """Resolve the full SU2 config with per-key provenance.

    Layer order: aeris defaults < derived (mesh path) < extra layers
    (flow, preset, config) < raw pass-through.
    """
    derived = OptionLayer("derived", {"mesh_filename": str(mesh_cgns)})
    layers = [aeris_defaults_layer(SU2_SCHEMA), derived, *extra_layers]
    if su2_options:
        layers.append(OptionLayer("raw", dict(su2_options), raw=True))
    return resolve_options(SU2_SCHEMA, layers)
