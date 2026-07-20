"""
Single source of truth for ADflow solver options.

Curated split (deliberate, defensible):

* **aeris defaults** carry only physics/mesh-convention invariants that are
  tied to how AERIS builds meshes and reports results — equation type,
  lift index (span=y, lift=z), monitor/surface variable lists, CGNS-only
  surface output.  These are stable across studies.
* **Solver strategy** (MG cycle, ANK/NK switching, cycle budget,
  convergence target) lives in the ``rans_ank_nk_v1`` preset — it is a
  *choice* validated for the cap4 meshes (tip collar blocks are 2 cells
  wide, so no multigrid), and different meshes/studies may swap it.

Everything else ADflow accepts (hundreds of options) flows through the
``adflow_options`` raw pass-through with provenance recording.
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


ADFLOW_SCHEMA = ToolOptionSchema(
    tool="adflow",
    curated=(
        CuratedOption("grid_file", "gridFile", str, doc="Volume mesh CGNS to solve on."),
        CuratedOption("output_directory", "outputDirectory", str, doc="Solution output directory."),
        CuratedOption(
            "monitor_variables",
            "monitorVariables",
            list,
            ["resrho", "resturb", "cl", "cd"],
            doc="Per-iteration monitor columns (drives live residual charts).",
        ),
        CuratedOption(
            "surface_variables",
            "surfaceVariables",
            list,
            ["cp", "cf", "yplus", "vx", "vy", "vz"],
            doc="Surface solution fields; yplus supports the wall-resolution claim (C5).",
        ),
        CuratedOption(
            "write_tecplot_surface_solution",
            "writeTecplotSurfaceSolution",
            bool,
            False,
            doc="CGNS-only output; visualization is delegated to ParaView.",
        ),
        CuratedOption(
            "equation_type",
            "equationType",
            str,
            "RANS",
            doc="Governing equations (RANS / laminar NS / Euler).",
        ),
        CuratedOption(
            "lift_index",
            "liftIndex",
            int,
            3,
            doc="Lift axis: AERIS meshes span +y, lift +z.",
            citation="AERIS mesh axis convention (surface builder).",
        ),
        CuratedOption(
            "mg_cycle",
            "MGCycle",
            str,
            doc="Multigrid cycle ('sg' = single grid).",
            citation="cap4 tip collar blocks are 2 cells wide -> no MG coarsening "
            "(adflow_smoke WP1 rationale).",
        ),
        CuratedOption(
            "use_ank_solver", "useANKSolver", bool, doc="Approximate Newton-Krylov phase."
        ),
        CuratedOption(
            "ank_switch_tol",
            "ANKSwitchTol",
            float,
            doc="Relative residual to switch to ANK (1.0 = from the start).",
        ),
        CuratedOption("use_nk_solver", "useNKSolver", bool, doc="Newton-Krylov end game."),
        CuratedOption(
            "nk_switch_tol",
            "NKSwitchTol",
            float,
            doc="Relative residual to switch to NK.",
            validate=_positive,
        ),
        CuratedOption("n_cycles", "nCycles", int, doc="Maximum solver cycles.", validate=_positive),
        CuratedOption(
            "l2_convergence",
            "L2Convergence",
            float,
            doc="Target relative L2 residual drop.",
            validate=_positive,
        ),
        CuratedOption(
            "turbulence_model",
            "turbulenceModel",
            str,
            doc="Turbulence model (ADflow default: SA). Set explicitly for "
            "model-sensitivity studies.",
        ),
        CuratedOption("cfl", "CFL", float, doc="CFL number.", validate=_positive),
        CuratedOption("smoother", "smoother", str, doc="Multigrid smoother (when MG is active)."),
    ),
)


def build_adflow_options(
    mesh_cgns: Path,
    output_directory: Path,
    *,
    extra_layers: Sequence[OptionLayer] = (),
    adflow_options: Mapping[str, object] | None = None,
) -> EffectiveOptions:
    """Resolve the full ADflow options dict with per-key provenance.

    Layer order: aeris defaults < derived (paths) < extra layers (preset,
    config) < raw pass-through.
    """
    derived = OptionLayer(
        "derived",
        {
            "grid_file": str(mesh_cgns),
            "output_directory": str(output_directory),
        },
    )
    layers = [aeris_defaults_layer(ADFLOW_SCHEMA), derived, *extra_layers]
    if adflow_options:
        layers.append(OptionLayer("raw", dict(adflow_options), raw=True))
    return resolve_options(ADFLOW_SCHEMA, layers)
