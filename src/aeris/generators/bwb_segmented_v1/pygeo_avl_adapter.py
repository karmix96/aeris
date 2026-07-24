"""Production pyGeo -> AVL adapter with section-CST viscous correction.

Drives the existing production AVL solver (`AeroSandboxAVLSolver`) from a pyGeo
realized loft — no new AVL/injection/strip-drag code. The chain is:

    pyGeo realized sections (CST)
      ├─ build_aerosandbox_airplane  → ASB Airplane (AVL serializer, retained)
      └─ per-section CST coords       → NeuralFoilPolarSource + SectionAirfoilMap
                                        (solver_options: section_map / polar_store)
    → AeroSandboxAVLSolver.run_case → AVL induced drag
        + CDCL injection (inject_polar_cdcl)
        + independent strip profile-drag integration (_compute_strip_profile_drag)
    → cd_corrected = cd_induced_AVL + cd_profile_NeuralFoil

The viscous correction is "section CST from the realized surface": each realized
extracted section's own CST shape is registered and governs its spanwise
neighbourhood (nearest-section, midpoint boundaries), reproducing the standalone
study's validated approach rather than the coarser 4-airfoil step model. Pass
`viscous_model="station_airfoils"` for the coarse 4-segment variant.

AeroSandbox is used ONLY as the AVL serializer here (per roadmap step 4); the
neutral loft / geometry path stays AeroSandbox-decoupled. A native AVL writer that
removes even this coupling is future work.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

import numpy as np

from aeris.aero.models import (
    AeroGeometryView,
    AeroInput,
    AeroSolverSettings,
    FlightCondition,
)
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
    ExtractedSection,
    build_aerosandbox_airplane,
)

_DEFAULT_MODEL_SIZE = "large"
_DEFAULT_CST_POINTS = 181


def _nearest_section_y_frac_ends(fracs: list[float]) -> list[float]:
    """Midpoint segment boundaries so each section governs its own neighbourhood.

    Section i owns (mid[i-1], mid[i]] where mid is the midpoint to the next
    section; the outboard-most section owns out to the tip (1.0).
    """
    n = len(fracs)
    if n == 1:
        return [1.0]
    ends = [0.5 * (fracs[i] + fracs[i + 1]) for i in range(n - 1)]
    ends.append(1.0)
    return ends


def build_realized_section_polar_bridge(
    extracted: Sequence[ExtractedSection],
    *,
    semispan_m: float,
    model_size: str = _DEFAULT_MODEL_SIZE,
    n_crit: float = 9.0,
    re_grid: "list[float] | None" = None,
    mach: float = 0.0,
    cst_points: int = _DEFAULT_CST_POINTS,
) -> tuple[Any, Any]:
    """Build (SectionAirfoilMap, NeuralFoilPolarSource) from realized CST sections.

    Each realized section's own CST coordinates are registered and mapped to its
    spanwise neighbourhood — section-resolved viscous correction from the master
    surface. Returns objects that drop straight into
    ``solver_options["section_map" | "polar_store"]``.
    """
    from aeris.airfoil.neuralfoil_polar_source import NeuralFoilPolarSource
    from aeris.airfoil.section_map import SectionAirfoilMap

    if semispan_m <= 0:
        raise ValueError("semispan_m must be positive")
    ordered = sorted(extracted, key=lambda s: s.y_m)
    if len(ordered) < 2:
        raise ValueError("at least two realized sections are required")

    source = NeuralFoilPolarSource(model_size=model_size, n_crit=n_crit)
    fracs = [min(max(float(s.y_m) / float(semispan_m), 0.0), 1.0) for s in ordered]
    y_frac_ends = _nearest_section_y_frac_ends(fracs)

    segments = []
    for sec, y_end in zip(ordered, y_frac_ends):
        coords = sec.cst.coordinates(n_per_surface=cst_points)
        aid = source.register_shape(coords)
        segments.append(SimpleNamespace(airfoil_id=aid, y_frac_end=float(y_end)))

    section_map = SectionAirfoilMap.from_segments(
        segments=segments, library_root=None, semispan_m=float(semispan_m)
    )
    if re_grid:
        source.warm_cdcl_grid(re_grid=list(re_grid), mach=float(mach))
    return section_map, source


def build_station_airfoil_polar_bridge(
    station_coords: Sequence[tuple[np.ndarray, float]],
    *,
    semispan_m: float,
    model_size: str = _DEFAULT_MODEL_SIZE,
    n_crit: float = 9.0,
    re_grid: "list[float] | None" = None,
    mach: float = 0.0,
) -> tuple[Any, Any]:
    """Coarse 4-airfoil step variant: (coords, y_frac_end) per station airfoil."""
    from aeris.airfoil.neuralfoil_polar_source import (
        build_neuralfoil_polar_store_for_segments,
    )

    return build_neuralfoil_polar_store_for_segments(
        list(station_coords),
        semispan_m=float(semispan_m),
        model_size=model_size,
        n_crit=n_crit,
        re_grid=re_grid,
        mach=mach,
    )


def build_pygeo_aero_input(
    *,
    extracted_sections: Sequence[ExtractedSection],
    flight_condition: FlightCondition,
    semispan_m: float,
    name: str = "pygeo_bwb",
    control: dict[str, Any] | None = None,
    viscous: bool = True,
    viscous_model: str = "realized_sections",
    station_coords: Sequence[tuple[np.ndarray, float]] | None = None,
    model_size: str = _DEFAULT_MODEL_SIZE,
    n_crit: float = 9.0,
    re_grid: "list[float] | None" = None,
    paneling: dict[str, Any] | None = None,
    avl_command: str | None = None,
    timeout_sec: int = 180,
    case_id: str | None = None,
    source_geometry_id: str | None = None,
) -> AeroInput:
    """Assemble an AeroInput that drives production AVL from a pyGeo loft.

    ``viscous_model``: "realized_sections" (default; per-section realized CST) or
    "station_airfoils" (coarse 4-segment step — requires ``station_coords``).
    """
    wing, airplane = build_aerosandbox_airplane(
        extracted_sections,
        name=name,
        representation="cst",
        symmetric=True,
        control=control,
    )

    cs_names = (str(control.get("name", "elevon")),) if control else ()
    view = AeroGeometryView(
        view_id=case_id or f"{name}_view",
        airplane=airplane,
        source_generator="bwb_segmented_v1_pygeo",
        source_geometry_id=source_geometry_id,
        has_control_surfaces=bool(control),
        control_surface_names=cs_names,
        metadata={"backend": "pygeo", "representation": "cst",
                  "viscous_model": viscous_model if viscous else "none"},
    )

    solver_options: dict[str, Any] = {}
    if paneling:
        solver_options["paneling"] = paneling
    if viscous:
        mach = flight_condition.mach or 0.0
        if viscous_model == "realized_sections":
            section_map, polar_store = build_realized_section_polar_bridge(
                extracted_sections, semispan_m=semispan_m, model_size=model_size,
                n_crit=n_crit, re_grid=re_grid, mach=mach,
            )
        elif viscous_model == "station_airfoils":
            if not station_coords:
                raise ValueError(
                    "viscous_model='station_airfoils' requires station_coords"
                )
            section_map, polar_store = build_station_airfoil_polar_bridge(
                station_coords, semispan_m=semispan_m, model_size=model_size,
                n_crit=n_crit, re_grid=re_grid, mach=mach,
            )
        else:
            raise ValueError(f"unknown viscous_model {viscous_model!r}")
        solver_options["section_map"] = section_map
        solver_options["polar_store"] = polar_store

    settings = AeroSolverSettings(
        avl_command=avl_command,
        timeout_sec=timeout_sec,
        solver_options=solver_options,
    )
    return AeroInput(
        geometry=view,
        flight_condition=flight_condition,
        settings=settings,
        case_id=case_id,
        provenance={"backend": "pygeo", "viscous": viscous,
                    "viscous_model": viscous_model if viscous else "none"},
    )


def run_pygeo_avl_case(
    *,
    flight_condition: FlightCondition,
    output_dir: Path,
    pygeo_result: Any | None = None,
    extracted_sections: Sequence[ExtractedSection] | None = None,
    semispan_m: float | None = None,
    **kwargs: Any,
):
    """Convenience: build the AeroInput and run the production AVL solver."""
    from aeris.aero.solvers.aerosandbox_avl import AeroSandboxAVLSolver

    if extracted_sections is None:
        if pygeo_result is None:
            raise ValueError("pass either pygeo_result or extracted_sections")
        extracted_sections = pygeo_result.extracted
    if semispan_m is None:
        semispan_m = max(float(s.y_m) for s in extracted_sections)

    aero_input = build_pygeo_aero_input(
        extracted_sections=extracted_sections,
        flight_condition=flight_condition,
        semispan_m=semispan_m,
        **kwargs,
    )
    return AeroSandboxAVLSolver().run_case(aero_input, Path(output_dir))
