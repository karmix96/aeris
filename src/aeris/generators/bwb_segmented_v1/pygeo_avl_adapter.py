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


def build_pygeo_sections_from_config(
    config_path: "Path | str",
    *,
    n_sections: int | None = None,
    seed: int | None = None,
    span_margin: float | None = None,
    snap_sections_to_control: bool | None = None,
    sample: Any | None = None,
) -> "tuple[list[ExtractedSection], float, dict[str, Any]]":
    """Build the pyGeo loft from a geometry config and extract its sections.

    Encapsulates the load→sample→planform→sections→loft→extract pipeline (no
    asb.Airplane). Returns (extracted_sections, semispan_m, meta).

    ``span_margin`` insets the extraction from both span ends
    (``linspace(margin, 1-margin, n)``). It defaults to **0.0 — the FULL span**.
    A non-zero margin is a modelling error on the AVL path: the innermost
    section lands at y>0, so YDUPLICATE mirrors it into a centreline GAP of
    2·y_min and AVL sheds a spurious inboard tip-vortex pair, while the tip is
    simultaneously truncated. Measured on the baseline seed, margin 0.02 shifts
    CL by more than a factor of two at α=3° (see DECISION-0005). It also matches
    the existing rule that integrated metrics must be extracted over the full
    span.
    """
    from pathlib import Path as _Path

    from aeris.common.config import load_yaml_config
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        build_pygeo,
        extract_sections,
        stations_from_records,
    )
    from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
    from aeris.generators.bwb_segmented_v1.services import (
        build_section_geometry_from_sample,
        generate_bwb_planform_from_sample,
    )
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    raw = load_yaml_config(_Path(config_path))
    gid, gcfg = resolve_generator_and_config(raw)
    if not gcfg.pygeo.enabled:
        raise ValueError(
            f"{config_path}: geometry.pygeo.enabled is false; this entry needs the pyGeo backend."
        )
    _d = getattr(gcfg, "aero_discretisation", None)
    if n_sections is None:
        n_sections = int(getattr(_d, "n_sections", 25))
    if span_margin is None:
        span_margin = float(getattr(_d, "span_margin", 0.0))
    if snap_sections_to_control is None:
        snap_sections_to_control = bool(getattr(_d, "snap_sections_to_control", True))

    gen = get_geometry_generator(gid)
    # ``sample`` lets a caller supply a CONSTRUCTED design instead of a random
    # one. Random sampling in 19 dimensions essentially never lands near a
    # corner of the design space, so deliberately built extreme cases are the
    # only way to test the discretisation at the edges (Task 5).
    if sample is None:
        sample = gen.sample_one(gcfg, seed=gcfg.generator.seed if seed is None else seed)
    planform = generate_bwb_planform_from_sample(sample, gcfg)
    section_geometry = build_section_geometry_from_sample(planform, sample, gcfg)
    stations = tuple(stations_from_records(section_geometry.sections, _resolve_airfoil_database(gcfg)))
    frame_mode = "asb_frame" if gcfg.pygeo.frame_mode == "aeris_frame" else gcfg.pygeo.frame_mode
    build = build_pygeo(
        stations, k_span=gcfg.pygeo.k_span, frame_mode=frame_mode,
        n_ctl=gcfg.pygeo.n_ctl, tip=gcfg.pygeo.tip, tip_scale=gcfg.pygeo.tip_scale,
    )
    control = None
    surfaces = getattr(gcfg.control_surfaces, "surfaces", None)
    if surfaces:
        cs = surfaces[0]
        # The three elevon DVs (start/end/hinge) are SAMPLED per design, so the
        # elevon geometry must come from the sample, not from the static config —
        # otherwise every design in a DoE flies the same elevon and the DVs are
        # inert on the aero path. `services.generate_geometry_case` already does
        # this override for the geometry path; this is the same rule for the aero
        # path, which reimplements the pipeline. Guarded on `elevon_bounds is not
        # None` because v1/v2 configs carry no elevon DVs and must not be patched
        # (BWBDesignSample always has the fields regardless).
        hinge = cs.hinge_point
        start, end = cs.spanwise.start_frac, cs.spanwise.end_frac
        if getattr(gcfg, "elevon_bounds", None) is not None:
            hinge = float(getattr(sample, "elevon_hinge_frac", hinge))
            start = float(getattr(sample, "elevon_start_frac", start))
            end = float(getattr(sample, "elevon_end_frac", end))
        control = {
            "name": cs.name, "hinge_point": hinge, "symmetric": cs.symmetric,
            "start_frac": start, "end_frac": end,
        }

    disc = getattr(gcfg, "aero_discretisation", None)
    lo, hi = float(span_margin), float(1.0 - span_margin)
    fractions = np.linspace(lo, hi, int(n_sections))
    placement_used = "uniform"

    # Snap two sections onto the elevon band edges so the control extent is the
    # geometry's extent, not whatever the uniform grid happens to bracket. AVL
    # ramps the control gain linearly between sections, so without an exact
    # boundary section the elevon's effective area is quantised to the section
    # spacing — which would give the DoE's three elevon DVs a staircase control
    # response instead of a smooth one.
    #
    # The edges are INSERTED, not swapped onto the nearest neighbour. Moving the
    # neighbour gives an exact extent but leaves the next section a full spacing
    # outside the band, which WIDENS the gain ramp AVL builds there — measured
    # 11.8% -> 23.0% of band width, breaching the DECISION-0010 criterion.
    # Inserting keeps both: the edge is exact AND its neighbour stays close.
    # Cost is two extra sections, which is cheap against a 25-section budget.
    snapped: list[float] = []

    # ---- adaptive placement (DECISION-0011) --------------------------------
    # Uniform spacing is fine for most wings, but it is misallocated when the
    # control band is short: AVL ramps the control gain over the interval just
    # outside each band edge, and on a narrow band those ramps swamp it. The
    # information metric redistributes the SAME budget toward where the geometry
    # (and the control) actually changes. "auto" applies it only when uniform
    # spacing breaches the ramp criterion, which is the DoE-safe setting.
    band = ((float(control["start_frac"]), float(control["end_frac"]))
            if control is not None else None)

    # HARD FEATURE PINS (DECISION-0012). The de Boor monitor |g''|^(1/2) is built
    # for SMOOTH functions; at a true kink it cannot resolve the feature no matter
    # how much density it piles nearby — a kink needs a node placed exactly ON it.
    # The BWB planform has two such kinks by construction (the b1/b2 and b2/b3
    # break stations, where sweep and taper change slope discontinuously in the
    # authored geometry), plus the two control-band edges. Pinning them exactly is
    # cheaper and more effective than any amount of nearby refinement.
    feature_pins: list[float] = [0.0, 1.0]
    try:
        b3r = float(getattr(sample, "b3_ratio"))
        splt = float(getattr(sample, "split_ratio"))
        feature_pins += [(1.0 - b3r) * splt, 1.0 - b3r]
    except (AttributeError, TypeError, ValueError):
        pass
    if band is not None:
        feature_pins += list(band)
    feature_pins = sorted({round(v, 9) for v in feature_pins if lo <= v <= hi})
    # Applied on BOTH paths. Uniform spacing needs the pins just as much as
    # adaptive does -- a kink that falls between two sections is mis-represented
    # whatever rule chose those sections.
    if snap_sections_to_control and feature_pins:
        fractions = np.unique(np.concatenate([fractions, feature_pins]))
        snapped = [v for v in feature_pins if v not in (lo, hi)]
    mode = getattr(disc, "section_placement", "never") if disc else "never"
    if band is not None and mode in {"auto", "always"}:
        from aeris.geometry.geometric_information import (
            adaptive_span_fractions, ramp_fraction, spanwise_information_profile,
        )

        limit = float(getattr(disc, "ramp_fraction_limit", 0.15))
        uniform_ramp = ramp_fraction(fractions, band)
        if mode == "always" or uniform_ramp > limit:
            try:
                profile = spanwise_information_profile(
                    build, n_probe=301, chordwise_probe=21, control_band=band
                )
                adaptive = adaptive_span_fractions(
                    profile, int(n_sections), must_include=feature_pins
                )
                if len(adaptive) >= 2:
                    fractions = adaptive
                    placement_used = "adaptive"
            except Exception:  # pragma: no cover - never fail a run over placement
                placement_used = "uniform (adaptive failed)"

    ex = list(extract_sections(
        build, fractions,
        cst_order=gcfg.pygeo.extraction.cst_order,
        chordwise_points=gcfg.pygeo.extraction.chordwise_points,
    ))
    semispan = max(float(s.y_m) for s in ex)
    meta = {"generator_id": gid, "geometry_id": getattr(build, "geometry_id", None),
            "n_sections": len(ex), "semispan_m": semispan, "control": control,
            "span_margin": float(span_margin),
            "control_edges_snapped": snapped,
            "section_placement": placement_used,
            "feature_pins": feature_pins}
    if band is not None:
        from aeris.geometry.geometric_information import ramp_fraction as _rf

        meta["ramp_fraction"] = _rf(fractions, band)
    return ex, semispan, meta


def build_realized_section_polar_bridge(
    extracted: Sequence[ExtractedSection],
    *,
    semispan_m: float,
    model_size: str = _DEFAULT_MODEL_SIZE,
    n_crit: float = 9.0,
    re_grid: "list[float] | None" = None,
    mach: float = 0.0,
    cst_points: int = _DEFAULT_CST_POINTS,
    polar_source_cls: type | None = None,
) -> tuple[Any, Any]:
    """Build (SectionAirfoilMap, polar source) from realized CST sections.

    Each realized section's own CST coordinates are registered and mapped to its
    spanwise neighbourhood — section-resolved viscous correction from the master
    surface. Returns objects that drop straight into
    ``solver_options["section_map" | "polar_store"]``.

    ``polar_source_cls`` selects the polar backend (default: the ASB-Airplane-free
    ``NeuralFoilCoordinateSource``). Pass ``NeuralFoilPolarSource`` for the legacy
    asb-Kulfan path.
    """
    from aeris.airfoil.section_map import SectionAirfoilMap

    if polar_source_cls is None:
        from aeris.airfoil.neuralfoil_coordinate_source import NeuralFoilCoordinateSource

        polar_source_cls = NeuralFoilCoordinateSource

    if semispan_m <= 0:
        raise ValueError("semispan_m must be positive")
    ordered = sorted(extracted, key=lambda s: s.y_m)
    if len(ordered) < 2:
        raise ValueError("at least two realized sections are required")

    source = polar_source_cls(model_size=model_size, n_crit=n_crit)
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
    control_input_deg: float | None = None,
    diff_input_deg: float | None = None,
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
    if control_input_deg is not None:
        solver_options["control_input_deg"] = float(control_input_deg)
    if diff_input_deg is not None:
        solver_options["diff_input_deg"] = float(diff_input_deg)
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


def summarize_pygeo_avl_qc(
    result: Any,
    *,
    drag_agreement_tol: float = 0.10,
    max_extrapolated_strips: int = 0,
) -> dict[str, Any]:
    """QC gate over the viscous cross-check the production solver already records.

    Reads (additively, no solver change) the metadata the AVL solver stores for
    the polar bridge and applies documented tolerances:

    - **drag agreement**: |cd_total(strip) − CDtot(AVL)| / cd_total, from
      ``solver_metadata["profile_drag_cd_total_vs_avl_cdtot_rel_diff"]``. The
      standalone study observed ~4.1%; the solver warns at 15%. Default gate 10%.
    - **strip reliability**: ``profile_drag_n_extrapolated_strips`` — strips whose
      CL fell outside the 2D polar range (clamped, unreliable). This is the
      production reliability proxy; the raw NeuralFoil analysis_confidence is NOT
      surfaced by NeuralFoilPolarSource (future enhancement). Default gate 0.

    NOTE (for Mike): the two thresholds are QC choices, not physics — review and
    adjust `drag_agreement_tol` / `max_extrapolated_strips` to taste.

    Returns a dict with the metrics and boolean `pass`.
    """
    meta = getattr(result, "solver_metadata", {}) or {}
    rel_diff = meta.get("profile_drag_cd_total_vs_avl_cdtot_rel_diff")
    n_extrap = meta.get("profile_drag_n_extrapolated_strips")

    drag_ok = rel_diff is None or float(rel_diff) <= drag_agreement_tol
    reliability_ok = n_extrap is None or int(n_extrap) <= max_extrapolated_strips

    return {
        "drag_agreement_rel_diff": rel_diff,
        "drag_agreement_tol": drag_agreement_tol,
        "drag_agreement_ok": bool(drag_ok),
        "cd_avl_cdtot": meta.get("cd_avl_cdtot"),
        "cd_total_strip": getattr(result, "cd_total", None),
        "n_extrapolated_strips": n_extrap,
        "max_extrapolated_strips": max_extrapolated_strips,
        "reliability_ok": bool(reliability_ok),
        "pass": bool(drag_ok and reliability_ok),
    }


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


def run_pygeo_native_avl_case(
    *,
    flight_condition: FlightCondition,
    output_dir: Path,
    pygeo_result: Any | None = None,
    extracted_sections: Sequence[ExtractedSection] | None = None,
    semispan_m: float | None = None,
    control: dict[str, Any] | None = None,
    control_input_deg: float = 0.0,
    diff_input_deg: float = 0.0,
    viscous: bool = True,
    model_size: str = _DEFAULT_MODEL_SIZE,
    n_crit: float = 9.0,
    re_grid: "list[float] | None" = None,
    avl_command: str = "avl",
    timeout_sec: int = 180,
    name: str = "pygeo_bwb",
    nchordwise: int = 24,          # DECISION-0009
    spanwise_panels_per_section: int = 4,
    cspace: float = 1.0,
    moment_reference_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    moment_reference_is_cg: bool = False,
    save_element_forces: bool = False,
    write_result_json: bool = True,
):
    """Fully asb.Airplane-free entry: pyGeo sections -> native AVL + viscous.

    Authors the .avl natively (no asb.Airplane) and drives the viscous correction
    from a NeuralFoilCoordinateSource (no asb.Airfoil in AERIS code). Returns a
    ``NativeAvlResult``. aerosandbox may still be imported transitively via
    NeuralFoil; nothing here constructs an AeroSandbox airplane.
    """
    from aeris.aero.solvers.native_avl import run_native_avl_case

    if extracted_sections is None:
        if pygeo_result is None:
            raise ValueError("pass either pygeo_result or extracted_sections")
        extracted_sections = pygeo_result.extracted
    if semispan_m is None:
        semispan_m = max(float(s.y_m) for s in extracted_sections)

    section_map = polar_store = None
    if viscous:
        mach = flight_condition.mach or 0.0
        section_map, polar_store = build_realized_section_polar_bridge(
            extracted_sections, semispan_m=semispan_m, model_size=model_size,
            n_crit=n_crit, re_grid=re_grid, mach=mach,
        )  # default source is the ASB-Airplane-free NeuralFoilCoordinateSource

    return run_native_avl_case(
        extracted_sections,
        flight_condition=flight_condition,
        output_dir=Path(output_dir),
        section_map=section_map,
        polar_store=polar_store,
        control=control,
        control_input_deg=control_input_deg,
        diff_input_deg=diff_input_deg,
        avl_command=avl_command,
        timeout_sec=timeout_sec,
        name=name,
        nchordwise=nchordwise,
        spanwise_panels_per_section=spanwise_panels_per_section,
        cspace=cspace,
        moment_reference_m=moment_reference_m,
        moment_reference_is_cg=moment_reference_is_cg,
        save_element_forces=save_element_forces,
        write_result_json=write_result_json,
    )
