#!/usr/bin/env python3
"""Run the project-local pyGeo versus AeroSandbox/AVL feasibility study.

The script is intentionally isolated under ``standalone``.  It reads existing
Aeris code and configurations to ensure the comparison is representative, but
does not modify or register anything in ``src/aeris``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from aeris.aero.solvers.aerosandbox_avl import AVLStrips
from aeris.aero.solvers.avl_polar_injection import _kinematic_viscosity
from aeris.airfoil.neuralfoil_polar_source import NeuralFoilPolarSource

from standalone.pygeo_avl_study.avl_bridge import run_avl_case
from standalone.pygeo_avl_study.case_factory import StudyCase, build_study_case
from standalone.pygeo_avl_study.geometry_bridge import (
    ExtractedSection,
    PyGeoBuild,
    build_aerosandbox_airplane,
    build_pygeo,
    extract_sections,
    realised_reference_metrics,
    sample_main_surfaces,
)
from standalone.pygeo_avl_study.plotting import (
    plot_avl_comparison,
    plot_convergence,
    plot_cst_order_study,
    plot_doe_summary,
    plot_geometry_comparison,
    plot_polar_comparison,
    plot_section_reconstruction,
)
from standalone.pygeo_avl_study.polar_bridge import (
    LiveNeuralFoilSource,
    SectionAirfoilMap,
    cdcl_bucket_cd,
    evaluate_neuralfoil,
    fit_cdcl_corrected,
    fit_cdcl_current,
)
from standalone.pygeo_comparison.compare import (
    structured_grid_faces,
    surface_distance_metrics,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/geometry/paper1_bwb_naca_stations.yaml"
DEFAULT_DOE_CONFIG = PROJECT_ROOT / "configs/geometry/paper1_bwb_doe_naca_stations.yaml"
DEFAULT_AIRFOILS = PROJECT_ROOT / "data/airfoil_database"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/pygeo_avl_study"


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_").lower()


def _unique_run_directory(root: Path, label: str | None = None) -> Path:
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    base = root / f"{_slug(label or 'study')}_{stamp}"
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = Path(f"{base}_{counter:02d}")
        counter += 1
    candidate.mkdir(parents=True)
    return candidate


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "_asdict"):
        return _json_safe(value._asdict())
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    return value


def _write_json(path: Path, payload: Any) -> None:
    Path(path).write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def _package_versions() -> dict[str, str]:
    packages = ("pygeo", "pyspline", "aerosandbox", "neuralfoil", "numpy", "scipy", "pandas")
    result = {"python": platform.python_version(), "platform": platform.platform()}
    for package in packages:
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not-installed"
    return result


def _control_spec(case: StudyCase) -> dict[str, float | str | bool] | None:
    cfg = case.config.control_surfaces
    if not cfg.enabled or not cfg.surfaces:
        return None
    surface = cfg.surfaces[0]
    return {
        "name": surface.name,
        "hinge_point": surface.hinge_point,
        "symmetric": surface.symmetric,
        "start_frac": surface.spanwise.start_frac,
        "end_frac": surface.spanwise.end_frac,
    }


def _surface_distance_to_asb(
    build: PyGeoBuild,
    asb_wing,
    *,
    reference_length: float,
    chordwise: int,
    spanwise: int,
) -> dict[str, Any]:
    upper, lower = sample_main_surfaces(
        build,
        chordwise_points=chordwise,
        spanwise_points=spanwise,
    )
    grids = (upper, lower)
    pygeo_points = np.concatenate([grid.reshape(-1, 3) for grid in grids])
    pygeo_faces = structured_grid_faces(grids)
    asb_points, asb_faces = asb_wing.mesh_body(
        method="quad",
        chordwise_resolution=max(30, chordwise // 2),
        mesh_surface=True,
        mesh_tips=False,
        mesh_trailing_edge=False,
        mesh_symmetric=False,
    )
    result, _, _ = surface_distance_metrics(
        pygeo_points,
        pygeo_faces,
        np.asarray(asb_points),
        np.asarray(asb_faces),
        reference_length,
    )
    return result


def geometry_study(
    case: StudyCase,
    run_dir: Path,
    *,
    quick: bool,
) -> tuple[
    dict[str, PyGeoBuild],
    dict[str, list[ExtractedSection]],
    pd.DataFrame,
]:
    """Build loft variants, extract dense sections, and compare outer surfaces."""
    builds = {
        f"pyGeo kSpan={order}": build_pygeo(
            case.pygeo_stations,
            k_span=order,
            frame_mode="asb_frame",
            tip="none",
        )
        for order in (2, 3, 4)
    }
    builds["pyGeo global-y"] = build_pygeo(
        case.pygeo_stations,
        k_span=3,
        frame_mode="global_y",
        tip="none",
    )
    n_extract = 33 if quick else 65
    fractions = np.linspace(0.0, 1.0, n_extract)
    curves = {
        label: extract_sections(
            build,
            fractions,
            cst_order=8,
            chordwise_points=121 if quick else 181,
        )
        for label, build in builds.items()
    }

    geometry_dir = run_dir / "geometry"
    geometry_dir.mkdir()
    # A reusable CAD and Tecplot export of the recommended smooth loft.
    builds["pyGeo kSpan=3"].geometry.writeIGES(str(geometry_dir / "baseline_kspan3.igs"))
    builds["pyGeo kSpan=3"].geometry.writeTecplot(
        str(geometry_dir / "baseline_kspan3.dat"), surfs=True, coef=True
    )

    rows: list[dict[str, Any]] = []
    reference_mac = float(case.intended_asb.wing.mean_aerodynamic_chord())
    for label, build in builds.items():
        sections = curves[label]
        refs = realised_reference_metrics(sections)
        distance = _surface_distance_to_asb(
            build,
            case.intended_asb.wing,
            reference_length=reference_mac,
            chordwise=51 if quick else 81,
            spanwise=61 if quick else 101,
        )
        symmetric = distance["symmetric"]
        rows.append(
            {
                "geometry": label,
                "k_span": build.k_span,
                "frame_mode": build.frame_mode,
                "frame_reconstruction_error": build.frame_reconstruction_error,
                **refs,
                "asb_s_ref_m2": float(case.intended_asb.airplane.s_ref),
                "area_delta_pct": 100.0
                * (refs["s_ref_xy_m2"] - float(case.intended_asb.airplane.s_ref))
                / float(case.intended_asb.airplane.s_ref),
                "surface_rms_mm": symmetric["rms_mm"],
                "surface_p95_mm": symmetric["p95_mm"],
                "surface_max_mm": symmetric["sampled_hausdorff_mm"],
                "surface_rms_pct_mac": symmetric["rms_percent_mac"],
                "max_cst_rms_chord": max(s.cst_rms_chord for s in sections),
                "max_cst_error_chord": max(s.cst_max_chord for s in sections),
                "max_plane_warp_chord": max(s.plane_warp_max_chord for s in sections),
                "cst_valid_fraction": np.mean([s.cst_valid for s in sections]),
            }
        )
        upper, lower = sample_main_surfaces(
            build, chordwise_points=81, spanwise_points=101
        )
        np.savez_compressed(
            geometry_dir / f"{_slug(label)}_surface.npz",
            upper=upper,
            lower=lower,
            span_fraction=np.asarray([s.span_fraction for s in sections]),
            v_parameter=np.asarray([s.v_parameter for s in sections]),
            le_xyz_m=np.asarray([s.le_xyz_m for s in sections]),
            te_xyz_m=np.asarray([s.te_xyz_m for s in sections]),
        )

    frame = pd.DataFrame(rows)
    frame.to_csv(geometry_dir / "geometry_comparison.csv", index=False)
    section_rows = []
    for label, sections in curves.items():
        for section in sections:
            section_rows.append({"geometry": label, **section.as_metrics_row()})
    pd.DataFrame(section_rows).to_csv(geometry_dir / "extracted_sections.csv", index=False)
    plot_geometry_comparison(
        builds=builds,
        curves=curves,
        intended_records=case.intended_sections.sections,
        path=geometry_dir / "geometry_comparison.png",
    )
    plot_section_reconstruction(
        curves["pyGeo kSpan=3"],
        path=geometry_dir / "section_reconstruction.png",
    )
    return builds, curves, frame


def cst_and_polar_study(
    build: PyGeoBuild,
    run_dir: Path,
    *,
    velocity_mps: float,
    altitude_m: float,
    model_size: str,
    quick: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[int, list[ExtractedSection]]]:
    """CST-order sweep, NeuralFoil comparison, and CDCL fit audit."""
    cst_dir = run_dir / "cst_neuralfoil"
    cst_dir.mkdir()
    orders = (4, 6, 7, 8, 10) if quick else (3, 4, 5, 6, 7, 8, 10, 12)
    fractions = np.linspace(0.0, 1.0, 7 if quick else 11)
    by_order: dict[int, list[ExtractedSection]] = {}
    cst_rows: list[dict[str, Any]] = []
    for order in orders:
        start = time.perf_counter()
        sections = extract_sections(
            build,
            fractions,
            cst_order=order,
            chordwise_points=121 if quick else 201,
        )
        elapsed = time.perf_counter() - start
        by_order[order] = sections
        for section in sections:
            cst_rows.append(
                {
                    **section.as_metrics_row(),
                    "runtime_sec": elapsed / len(sections),
                }
            )
    cst_frame = pd.DataFrame(cst_rows)
    cst_frame.to_csv(cst_dir / "cst_order_study.csv", index=False)
    plot_cst_order_study(cst_frame, cst_dir / "cst_order_study.png")

    selected_indices = (0, len(fractions) // 2, len(fractions) - 1)
    alpha = np.linspace(-10.0, 20.0, 16 if quick else 31)
    atmosphere_mach = velocity_mps / float(
        __import__("aerosandbox").Atmosphere(altitude=altitude_m).speed_of_sound()
    )
    nu = _kinematic_viscosity(altitude_m)
    polar_rows: list[dict[str, Any]] = []
    cdcl_rows: list[dict[str, Any]] = []
    representations = [("direct", None)]
    for order in (min(orders), 8, max(orders)):
        if order in by_order and (f"cst{order}", order) not in representations:
            representations.append((f"cst{order}", order))

    for selected_index in selected_indices:
        base = by_order[8][selected_index]
        section_label = (
            "root"
            if selected_index == 0
            else "tip"
            if selected_index == len(fractions) - 1
            else "midspan"
        )
        reynolds = velocity_mps * base.chord_m / nu
        for representation, order in representations:
            source_section = base if order is None else by_order[order][selected_index]
            coordinates = (
                source_section.direct_coordinates
                if order is None
                else source_section.cst.coordinates(181)
            )
            interfaces = (
                ("core", "aerosandbox_extended")
                if representation == "direct"
                else ("aerosandbox_extended",)
            )
            for interface in interfaces:
                curve = evaluate_neuralfoil(
                    coordinates,
                    alpha_deg=alpha,
                    reynolds=reynolds,
                    mach=atmosphere_mach,
                    interface=interface,
                    model_size=model_size,
                    include_360_deg_effects=False,
                )
                for i in range(len(alpha)):
                    polar_rows.append(
                        {
                            "section_label": section_label,
                            "span_fraction": base.span_fraction,
                            "representation": representation,
                            "interface": interface,
                            "alpha_deg": curve.alpha_deg[i],
                            "CL": curve.cl[i],
                            "CD": curve.cd[i],
                            "CM": curve.cm[i],
                            "analysis_confidence": curve.confidence[i],
                            "reynolds": reynolds,
                            "mach": atmosphere_mach,
                        }
                    )
                if interface == "aerosandbox_extended":
                    for fitter_name, fitter in (
                        ("production_current", fit_cdcl_current),
                        ("symmetric_corrected", fit_cdcl_corrected),
                    ):
                        params = fitter(curve)
                        inside = (
                            (curve.cl >= params.cl1)
                            & (curve.cl <= params.cl3)
                            & curve.finite_mask()
                        )
                        predicted = cdcl_bucket_cd(params, curve.cl[inside])
                        error = predicted - curve.cd[inside]
                        cdcl_rows.append(
                            {
                                "section_label": section_label,
                                "representation": representation,
                                "fitter": fitter_name,
                                **params._asdict(),
                                "n_inside": int(np.count_nonzero(inside)),
                                "cd_rmse_inside": float(np.sqrt(np.mean(error**2))),
                                "cd_max_abs_inside": float(np.max(np.abs(error))),
                                "min_confidence": curve.min_confidence,
                            }
                        )

    polar_frame = pd.DataFrame(polar_rows)
    polar_frame.to_csv(cst_dir / "neuralfoil_polars.csv", index=False)
    cdcl_frame = pd.DataFrame(cdcl_rows)
    cdcl_frame.to_csv(cst_dir / "cdcl_fit_audit.csv", index=False)
    plot_polar_comparison(polar_frame, cst_dir / "neuralfoil_polars.png")
    return cst_frame, polar_frame, cdcl_frame, by_order

def _polar_bridge_for_sections(
    sections: Sequence[ExtractedSection], *, model_size: str
) -> tuple[SectionAirfoilMap, LiveNeuralFoilSource]:
    source = LiveNeuralFoilSource(
        interface="aerosandbox_extended", model_size=model_size,
        alpha_grid_deg=np.linspace(-12.0, 22.0, 35), fitter="current",
    )
    coordinates = [section.cst.coordinates(181) for section in sections]
    ids = [source.register_shape(coords) for coords in coordinates]
    section_map = SectionAirfoilMap(
        [section.y_m for section in sections], ids, coordinates
    )
    return section_map, source


def _polar_bridge_for_wing(
    wing, *, model_size: str
) -> tuple[SectionAirfoilMap, LiveNeuralFoilSource]:
    source = LiveNeuralFoilSource(
        interface="aerosandbox_extended", model_size=model_size,
        alpha_grid_deg=np.linspace(-12.0, 22.0, 35), fitter="current",
    )
    y_m: list[float] = []
    ids: list[str] = []
    coordinates: list[np.ndarray] = []
    for xsec in wing.xsecs:
        coords = np.asarray(
            xsec.airfoil.repanel(n_points_per_side=181).coordinates, dtype=float
        )
        y_m.append(float(xsec.xyz_le[1]))
        coordinates.append(coords)
        ids.append(source.register_shape(coords))
    return SectionAirfoilMap(y_m, ids, coordinates), source


def avl_comparison_study(
    case: StudyCase,
    builds: dict[str, PyGeoBuild],
    run_dir: Path,
    *,
    velocity_mps: float,
    altitude_m: float,
    model_size: str,
    quick: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[ExtractedSection]]]:
    """Run the same AVL executable on production ASB and pyGeo-derived models."""
    avl_dir = run_dir / "avl_comparison"
    avl_dir.mkdir()
    n_sections = 13 if quick else 17
    fractions = np.linspace(0.0, 1.0, n_sections)
    control = _control_spec(case)
    pygeo_sections: dict[str, list[ExtractedSection]] = {}
    geometries: dict[str, tuple[Any, Any, Any]] = {}
    for order in (2, 3, 4):
        label = f"pyGeo kSpan={order}"
        sections = extract_sections(
            builds[label], fractions, cst_order=8, chordwise_points=141
        )
        pygeo_sections[label] = sections
        _, airplane = build_aerosandbox_airplane(
            sections, name=_slug(label), representation="cst",
            symmetric=True, control=control,
        )
        section_map, source = _polar_bridge_for_sections(
            sections, model_size=model_size
        )
        geometries[label] = (airplane, section_map, source)

    for label, asb_result in (
        ("AeroSandbox production", case.production_asb),
        ("AeroSandbox intended", case.intended_asb),
    ):
        section_map, source = _polar_bridge_for_wing(
            asb_result.wing, model_size=model_size
        )
        geometries[label] = (asb_result.airplane, section_map, source)

    alphas = (-2.0, 4.0, 10.0) if quick else (-4.0, 0.0, 4.0, 8.0, 12.0)
    rows: list[dict[str, Any]] = []
    for label, (airplane, section_map, source) in geometries.items():
        for alpha in alphas:
            result = run_avl_case(
                airplane,
                case_name=f"{label}_alpha_{alpha:+.1f}",
                workdir=avl_dir / "cases" / _slug(label) / f"alpha_{alpha:+05.1f}",
                alpha_deg=alpha, velocity_mps=velocity_mps,
                altitude_m=altitude_m,
                paneling={
                    "spanwise_resolution": 2, "chordwise_resolution": 8,
                    "spanwise_spacing": "equal", "chordwise_spacing": "cosine",
                },
                section_map=section_map, polar_source=source,
                inject_cdcl=True, preserve_viscous_mode=True, timeout_sec=25.0,
            )
            rows.append({"geometry": label, **result.as_row()})
    frame = pd.DataFrame(rows)
    frame.to_csv(avl_dir / "avl_geometry_comparison.csv", index=False)
    plot_avl_comparison(frame, avl_dir / "avl_geometry_comparison.png")

    audit_rows: list[dict[str, Any]] = []
    audit_airplane, audit_map, audit_source = geometries["pyGeo kSpan=3"]
    variants = (
        ("production_keystrokes", False, False),
        ("viscous_on_surface_placeholder_kept", True, False),
        ("viscous_on_surface_placeholder_removed", True, True),
    )
    for name, preserve_viscous, remove_surface in variants:
        result = run_avl_case(
            audit_airplane, case_name=name,
            workdir=avl_dir / "cdcl_semantics" / name,
            alpha_deg=4.0, velocity_mps=velocity_mps, altitude_m=altitude_m,
            paneling={"spanwise_resolution": 2, "chordwise_resolution": 8},
            section_map=audit_map, polar_source=audit_source, inject_cdcl=True,
            preserve_viscous_mode=preserve_viscous,
            remove_surface_placeholder=remove_surface, timeout_sec=25.0,
        )
        audit_rows.append({
            "variant": name, "preserve_viscous_mode": preserve_viscous,
            "remove_surface_placeholder": remove_surface,
            "raw_CDvis": float(result.raw.get("CDvis", float("nan"))),
            **result.as_row(),
        })
    audit_frame = pd.DataFrame(audit_rows)
    audit_frame.to_csv(avl_dir / "cdcl_semantics_audit.csv", index=False)
    return frame, audit_frame, pygeo_sections


def section_convergence_study(
    build: PyGeoBuild,
    run_dir: Path,
    *,
    velocity_mps: float,
    altitude_m: float,
    quick: bool,
) -> pd.DataFrame:
    convergence_dir = run_dir / "section_convergence"
    convergence_dir.mkdir()
    section_counts = (5, 9, 17) if quick else (5, 9, 17, 33)
    target_semispan_panels = 48 if quick else 64
    alphas = (4.0, 8.0) if quick else (0.0, 4.0, 8.0)
    rows: list[dict[str, Any]] = []
    for count in section_counts:
        intervals = count - 1
        if target_semispan_panels % intervals:
            raise ValueError(
                f"{target_semispan_panels} panels cannot be distributed exactly "
                f"over {intervals} section intervals"
            )
        sections = extract_sections(
            build, np.linspace(0.0, 1.0, count),
            cst_order=8, chordwise_points=121,
        )
        _, airplane = build_aerosandbox_airplane(
            sections, name=f"k3_n{count}", representation="cst"
        )
        span_resolution = target_semispan_panels // intervals
        for alpha in alphas:
            result = run_avl_case(
                airplane, case_name=f"k3_n{count}_a{alpha:g}",
                workdir=convergence_dir / "cases" / f"n{count}" / f"alpha_{alpha:+05.1f}",
                alpha_deg=alpha, velocity_mps=velocity_mps,
                altitude_m=altitude_m,
                paneling={
                    "spanwise_resolution": span_resolution,
                    "chordwise_resolution": 8,
                },
                inject_cdcl=False, timeout_sec=25.0,
            )
            rows.append({
                "n_sections": count,
                "spanwise_resolution_per_interval": span_resolution,
                "estimated_semispan_panels": span_resolution * (count - 1),
                **result.as_row(),
            })
    frame = pd.DataFrame(rows)
    reference_count = max(section_counts)
    reference = frame[frame.n_sections == reference_count].set_index("alpha_deg")
    frame["CL_error_pct"] = [
        100.0 * (row.CL - float(reference.loc[row.alpha_deg, "CL"]))
        / max(abs(float(reference.loc[row.alpha_deg, "CL"])), 1.0e-8)
        for row in frame.itertuples()
    ]
    frame["CL_error_abs"] = [
        row.CL - float(reference.loc[row.alpha_deg, "CL"])
        for row in frame.itertuples()
    ]
    frame["CDi_error_pct"] = [
        100.0 * (row.CD_induced - float(reference.loc[row.alpha_deg, "CD_induced"]))
        / max(abs(float(reference.loc[row.alpha_deg, "CD_induced"])), 1.0e-10)
        for row in frame.itertuples()
    ]
    frame["CDi_error_abs"] = [
        row.CD_induced - float(reference.loc[row.alpha_deg, "CD_induced"])
        for row in frame.itertuples()
    ]
    frame.to_csv(convergence_dir / "section_convergence.csv", index=False)
    plot_convergence(frame, convergence_dir / "section_convergence.png")
    return frame

def implementation_audit(
    case: StudyCase,
    representative_section: ExtractedSection,
    run_dir: Path,
    *,
    velocity_mps: float,
    altitude_m: float,
    model_size: str,
) -> dict[str, Any]:
    """Quantify repository integration assumptions without modifying Aeris."""
    audit_dir = run_dir / "implementation_audit"
    audit_dir.mkdir()
    coordinates = representative_section.cst.coordinates(181)
    re_values = np.asarray([2.0e5, 5.0e5, 1.0e6, 2.0e6])
    cl_values = np.full_like(re_values, 0.5)

    production_nf = NeuralFoilPolarSource(model_size=model_size)
    production_id = production_nf.register_shape(coordinates)
    production_batch_cd = production_nf.query_cd_batch(
        [production_id] * len(re_values), cl_values, re_values, mach=0.15
    )
    exact_nf = LiveNeuralFoilSource(
        interface="aerosandbox_extended", model_size=model_size,
        alpha_grid_deg=np.linspace(-12.0, 20.0, 65),
    )
    exact_id = exact_nf.register_shape(coordinates)
    exact_cd = exact_nf.query_cd_batch(
        [exact_id] * len(re_values), cl_values, re_values, mach=0.15
    )
    re_frame = pd.DataFrame({
        "reynolds": re_values, "CL_query": cl_values,
        "production_batch_CD": production_batch_cd, "exact_Re_CD": exact_cd,
    })
    re_frame["relative_error_pct"] = 100.0 * (
        re_frame.production_batch_CD - re_frame.exact_Re_CD
    ) / re_frame.exact_Re_CD
    re_frame.to_csv(audit_dir / "neuralfoil_batch_reynolds_audit.csv", index=False)

    import aerosandbox as asb
    mach = velocity_mps / float(asb.Atmosphere(altitude=altitude_m).speed_of_sound())
    alpha = np.linspace(-6.0, 12.0, 10)
    reynolds = velocity_mps * representative_section.chord_m / _kinematic_viscosity(altitude_m)
    core_0 = evaluate_neuralfoil(
        coordinates, alpha_deg=alpha, reynolds=reynolds, mach=0.0,
        interface="core", model_size=model_size,
    )
    core_m = evaluate_neuralfoil(
        coordinates, alpha_deg=alpha, reynolds=reynolds, mach=mach,
        interface="core", model_size=model_size,
    )
    extended_0 = evaluate_neuralfoil(
        coordinates, alpha_deg=alpha, reynolds=reynolds, mach=0.0,
        interface="aerosandbox_extended", model_size=model_size,
    )
    extended_m = evaluate_neuralfoil(
        coordinates, alpha_deg=alpha, reynolds=reynolds, mach=mach,
        interface="aerosandbox_extended", model_size=model_size,
    )

    # Reproduce the relative-path AFILE problem without running AVL.
    afile_audit_dir = audit_dir / "relative_afile"
    afile_audit_dir.mkdir()
    relative_afile_result: dict[str, Any]
    try:
        relative_dir = afile_audit_dir.relative_to(PROJECT_ROOT)
        op = asb.OperatingPoint(
            atmosphere=asb.Atmosphere(altitude=altitude_m),
            velocity=velocity_mps, alpha=4.0,
        )
        writer = AVLStrips(
            airplane=case.intended_asb.airplane, op_point=op,
            working_directory=str(relative_dir), avl_command="avl",
        )
        avl_path = relative_dir / "airplane.avl"
        writer.write_avl(avl_path)
        text = (PROJECT_ROOT / avl_path).read_text(encoding="utf-8")
        lines = text.splitlines()
        afile_index = next(i for i, line in enumerate(lines) if line.strip() == "AFIL")
        declared = lines[afile_index + 1].strip()
        solver_resolution = (PROJECT_ROOT / relative_dir / declared).resolve()
        relative_afile_result = {
            "declared_afile": declared,
            "actual_companion_exists": (PROJECT_ROOT / declared).is_file(),
            "solver_cwd_resolution": str(solver_resolution),
            "solver_cwd_resolution_exists": solver_resolution.is_file(),
        }
    except Exception as exc:
        relative_afile_result = {"audit_error": f"{type(exc).__name__}: {exc}"}

    result = {
        "station_airfoils": {
            "configured": list(case.prescribed_airfoil_names),
            "production_unique": list(case.production_unique_airfoils),
            "applied_in_production": case.prescribed_airfoils_applied_in_production,
        },
        "query_cd_batch_reynolds": {
            "max_abs_relative_error_pct": float(np.nanmax(np.abs(re_frame.relative_error_pct))),
            "median_re_used_by_production": float(np.median(re_values)),
        },
        "mach_semantics": {
            "mach": mach,
            "core_max_abs_delta_CL": float(np.max(np.abs(core_m.cl - core_0.cl))),
            "core_max_abs_delta_CD": float(np.max(np.abs(core_m.cd - core_0.cd))),
            "extended_max_abs_delta_CL": float(np.max(np.abs(extended_m.cl - extended_0.cl))),
            "extended_max_abs_delta_CD": float(np.max(np.abs(extended_m.cd - extended_0.cd))),
        },
        "confidence": {
            "minimum_on_audit_grid": extended_m.min_confidence,
            "production_source_has_confidence_gate": False,
        },
        "relative_working_directory_afile": relative_afile_result,
    }
    _write_json(audit_dir / "implementation_audit.json", result)
    return result


def doe_stress_study(
    config_path: Path,
    run_dir: Path,
    *,
    samples: int,
    seed_start: int,
    velocity_mps: float,
    altitude_m: float,
    quick: bool,
) -> pd.DataFrame:
    """Stress pyGeo extraction and a representative AVL point over the wide DOE."""
    doe_dir = run_dir / "doe_stress"
    doe_dir.mkdir()
    rows: list[dict[str, Any]] = []
    fractions = np.linspace(0.0, 1.0, 9 if quick else 17)
    for sample_index in range(samples):
        seed = seed_start + sample_index
        row: dict[str, Any] = {"sample_index": sample_index, "seed": seed, "failed": False}
        started = time.perf_counter()
        try:
            case = build_study_case(
                config_path, airfoil_database=DEFAULT_AIRFOILS, seed=seed
            )
            sample_payload = asdict(case.sample)
            for key, value in sample_payload.items():
                if isinstance(value, (int, float, bool)):
                    row[f"dv_{key}"] = value
            row["n_authored_sections"] = len(case.pygeo_stations)
            row["min_chord_m"] = min(s.chord_m for s in case.pygeo_stations)
            row["max_abs_twist_deg"] = max(abs(s.twist_deg) for s in case.pygeo_stations)
            row["max_abs_dihedral_deg"] = max(abs(s.dihedral_deg) for s in case.pygeo_stations)
            row["asb_area_m2"] = float(case.intended_asb.airplane.s_ref)

            extracted_by_order: dict[int, list[ExtractedSection]] = {}
            builds: dict[int, PyGeoBuild] = {}
            for order in (2, 3, 4):
                builds[order] = build_pygeo(
                    case.pygeo_stations, k_span=order,
                    frame_mode="asb_frame", tip="none",
                )
                extracted_by_order[order] = extract_sections(
                    builds[order], fractions, cst_order=8,
                    chordwise_points=101 if quick else 141,
                )
                refs = realised_reference_metrics(extracted_by_order[order])
                row[f"k{order}_area_m2"] = refs["s_ref_xy_m2"]
                row[f"area_delta_k{order}_pct"] = 100.0 * (
                    refs["s_ref_xy_m2"] - row["asb_area_m2"]
                ) / row["asb_area_m2"]

            k3_sections = extracted_by_order[3]
            row["max_cst_rms_chord"] = max(s.cst_rms_chord for s in k3_sections)
            row["max_cst_error_chord"] = max(s.cst_max_chord for s in k3_sections)
            row["max_plane_warp_chord"] = max(s.plane_warp_max_chord for s in k3_sections)
            row["cst_valid_fraction"] = float(np.mean([s.cst_valid for s in k3_sections]))

            _, pygeo_airplane = build_aerosandbox_airplane(
                k3_sections, name=f"doe_{seed}_k3", representation="cst",
                control=_control_spec(case),
            )
            paneling = {"spanwise_resolution": 1, "chordwise_resolution": 6}
            asb_result = run_avl_case(
                case.intended_asb.airplane, case_name=f"doe_{seed}_asb",
                workdir=doe_dir / "cases" / f"seed_{seed}" / "asb",
                alpha_deg=4.0, velocity_mps=velocity_mps,
                altitude_m=altitude_m, paneling=paneling, inject_cdcl=False,
            )
            pygeo_result = run_avl_case(
                pygeo_airplane, case_name=f"doe_{seed}_pygeo",
                workdir=doe_dir / "cases" / f"seed_{seed}" / "pygeo_k3",
                alpha_deg=4.0, velocity_mps=velocity_mps,
                altitude_m=altitude_m, paneling=paneling, inject_cdcl=False,
            )
            row.update({
                "asb_CL_alpha4": asb_result.cl,
                "pygeo_CL_alpha4": pygeo_result.cl,
                "CL_delta_pct": 100.0 * (pygeo_result.cl - asb_result.cl)
                / max(abs(asb_result.cl), 1.0e-8),
                "asb_CDi_alpha4": asb_result.cd_induced,
                "pygeo_CDi_alpha4": pygeo_result.cd_induced,
                "CDi_delta_pct": 100.0 * (pygeo_result.cd_induced - asb_result.cd_induced)
                / max(abs(asb_result.cd_induced), 1.0e-10),
            })
        except Exception as exc:
            row["failed"] = True
            row["failure_type"] = type(exc).__name__
            row["failure_message"] = str(exc)
        row["geometry_runtime_sec"] = time.perf_counter() - started
        rows.append(row)
        print(f"  DOE {sample_index + 1:02d}/{samples}: seed={seed} failed={row['failed']}", flush=True)

    frame = pd.DataFrame(rows)
    required = (
        "area_delta_k3_pct", "max_cst_rms_chord", "max_plane_warp_chord",
        "max_abs_twist_deg", "min_chord_m", "geometry_runtime_sec",
    )
    for column in required:
        if column not in frame:
            frame[column] = np.nan
    frame.to_csv(doe_dir / "doe_stress.csv", index=False)
    if len(frame) and np.any(~frame.failed):
        plot_doe_summary(frame, doe_dir / "doe_stress.png")
    return frame

def _format_cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return "—"
        magnitude = abs(float(value))
        if magnitude and (magnitude < 1.0e-3 or magnitude >= 1.0e4):
            return f"{float(value):.3e}"
        return f"{float(value):.4f}"
    return str(value).replace("|", "\\|")


def _markdown_table(frame: pd.DataFrame, columns: Sequence[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| " + " | ".join(_format_cell(row[column]) for column in columns) + " |"
        for _, row in frame.loc[:, columns].iterrows()
    ]
    return "\n".join([header, separator, *rows])


def write_report(
    run_dir: Path,
    *,
    case: StudyCase,
    geometry: pd.DataFrame,
    cst: pd.DataFrame,
    polars: pd.DataFrame,
    cdcl: pd.DataFrame,
    avl: pd.DataFrame,
    cdcl_semantics: pd.DataFrame,
    convergence: pd.DataFrame,
    doe: pd.DataFrame,
    audit: dict[str, Any],
    versions: dict[str, str],
) -> Path:
    """Write the persistent evidence-backed recommendation."""
    k3_geometry = geometry[geometry.geometry == "pyGeo kSpan=3"].iloc[0]
    k2_geometry = geometry[geometry.geometry == "pyGeo kSpan=2"].iloc[0]
    cst_summary = (
        cst.groupby("cst_order")
        .agg(
            median_RMS=("cst_rms_chord", "median"),
            worst_RMS=("cst_rms_chord", "max"),
            worst_point=("cst_max_chord", "max"),
            valid_fraction=("cst_valid", "mean"),
        )
        .reset_index()
    )
    alpha_target = min(avl.alpha_deg.unique(), key=lambda value: abs(value - 4.0))
    avl_at_4 = avl[np.isclose(avl.alpha_deg, alpha_target)].copy()
    intended_row = avl_at_4[avl_at_4.geometry == "AeroSandbox intended"].iloc[0]
    avl_at_4["delta_CL_pct_vs_intended"] = 100.0 * (
        avl_at_4.CL - intended_row.CL
    ) / max(abs(intended_row.CL), 1.0e-8)
    avl_at_4["delta_CDi_pct_vs_intended"] = 100.0 * (
        avl_at_4.CD_induced - intended_row.CD_induced
    ) / max(abs(intended_row.CD_induced), 1.0e-10)
    avl_at_4["delta_CDcorr_pct_vs_intended"] = 100.0 * (
        avl_at_4.CD_corrected - intended_row.CD_corrected
    ) / max(abs(intended_row.CD_corrected), 1.0e-10)

    successful_doe = doe[~doe.failed] if len(doe) else doe
    failure_count = int(doe.failed.sum()) if len(doe) else 0
    if len(successful_doe):
        doe_area_p95 = float(np.percentile(np.abs(successful_doe.area_delta_k3_pct), 95))
        doe_cl_p95 = float(np.percentile(np.abs(successful_doe.CL_delta_pct), 95))
        doe_cdi_p95 = float(np.percentile(np.abs(successful_doe.CDi_delta_pct), 95))
        doe_warp_max = float(successful_doe.max_plane_warp_chord.max())
        doe_cst_max = float(successful_doe.max_cst_rms_chord.max())
    else:
        doe_area_p95 = doe_cl_p95 = doe_cdi_p95 = doe_warp_max = doe_cst_max = float("nan")

    reference_sections = int(convergence.n_sections.max())
    convergence_panels = sorted(
        int(value) for value in convergence.estimated_semispan_panels.unique()
    )
    converged_17 = convergence[convergence.n_sections == 17]
    operating_17 = converged_17[np.abs(converged_17.alpha_deg) >= 4.0 - 1.0e-12]
    convergence_cl = (
        float(np.max(np.abs(operating_17.CL_error_pct)))
        if len(operating_17) else float("nan")
    )
    convergence_cdi = (
        float(np.max(np.abs(operating_17.CDi_error_pct)))
        if len(operating_17) else float("nan")
    )
    near_zero_17 = converged_17[np.isclose(converged_17.alpha_deg, 0.0)]
    if len(near_zero_17):
        zero_cl_abs = float(np.max(np.abs(near_zero_17.CL_error_abs)))
        zero_cdi_abs = float(np.max(np.abs(near_zero_17.CDi_error_abs)))
        zero_lift_note = (
            f" At alpha=0 deg, where a relative percentage is ill-conditioned, "
            f"the absolute differences were ΔCL={zero_cl_abs:.3e} and "
            f"ΔCDi={zero_cdi_abs:.3e}."
        )
    else:
        zero_lift_note = ""
    production_semantics = cdcl_semantics[
        cdcl_semantics.variant == "production_keystrokes"
    ].iloc[0]
    fixed_semantics = cdcl_semantics[
        cdcl_semantics.variant == "viscous_on_surface_placeholder_kept"
    ].iloc[0]
    cdvis_agreement = 100.0 * abs(
        fixed_semantics.raw_CDvis - fixed_semantics.CD_profile_integrated
    ) / fixed_semantics.CD_profile_integrated

    geometry_table = geometry.copy()
    geometry_table["cst_valid_pct"] = 100.0 * geometry_table.cst_valid_fraction
    cst_summary["valid_pct"] = 100.0 * cst_summary.valid_fraction
    avl_table = avl_at_4[
        [
            "geometry", "CL", "CD_induced", "CD_profile_integrated",
            "CD_corrected", "L_over_D_corrected", "delta_CL_pct_vs_intended",
            "delta_CDi_pct_vs_intended", "delta_CDcorr_pct_vs_intended",
        ]
    ]

    report = f"""# pyGeo as the master geometry for Aeris/AVL

Run directory: `{run_dir}`  
Baseline: `{case.config_path}`  
Environment: Python {versions['python']}, pyGeo {versions['pygeo']}, pySpline {versions['pyspline']}, AeroSandbox {versions['aerosandbox']}, NeuralFoil {versions['neuralfoil']}.

## Decision

**Use pyGeo as the master 3-D geometry and retain AeroSandbox as a complementary AVL serializer plus NeuralFoil interface.** The standalone chain works end to end:

`design variables -> pyGeo loft -> physical-span slices -> CST -> NeuralFoil -> CDCL + strip integration -> AVL`.

Do not replace the current path by merely handing pyGeo's authored control stations to AVL. For `kSpan > 2`, extract sections from the *realised B-spline surface*. The recommended initial setting is `kSpan=3`, exact AeroSandbox-compatible station frames, CST order 8, and at least 17 AVL sections (then demonstrate convergence for each design family).

This is a useful PhD contribution because the master CAD loft and the aerodynamic section polars are now generated from the same realised geometry. The defensible novelty is **geometry-consistent, section-resolved viscous drag correction**, not a claim that AVL becomes a nonlinear viscous solver.

## What changed in the geometry

`kSpan=2` is the control case: it reproduces piecewise-linear lofting. `kSpan=3/4` smooth the spanwise control net, so interior authored sections are control points rather than guaranteed interpolation points. This changes chord, sweep, twist, camber transition, area, and hence AVL loads.

{_markdown_table(geometry_table, ['geometry', 'area_delta_pct', 'surface_rms_mm', 'surface_p95_mm', 'surface_max_mm', 'max_plane_warp_chord', 'max_cst_rms_chord', 'cst_valid_pct'])}

The baseline smooth loft (`kSpan=3`) changes projected reference area by **{k3_geometry.area_delta_pct:.3f}%** relative to the intended AeroSandbox model. Its bidirectional outer-surface RMS difference is **{k3_geometry.surface_rms_mm:.3f} mm**. The piecewise-linear pyGeo control has **{k2_geometry.surface_rms_mm:.3f} mm** RMS difference.

The extracted curves are not perfectly planar when frames, twist, dihedral, and airfoil shape all vary through a B-spline. That is why the bridge records a plane-warp metric and explicitly projects onto the local chord/span frame before CST fitting.

Visual evidence: [geometry comparison](geometry/geometry_comparison.png), [section/CST overlays](geometry/section_reconstruction.png). The recommended baseline CAD is [IGES](geometry/baseline_kspan3.igs), with [Tecplot surface/control data](geometry/baseline_kspan3.dat).

## CST and NeuralFoil

{_markdown_table(cst_summary, ['cst_order', 'median_RMS', 'worst_RMS', 'worst_point', 'valid_pct'])}

CST order 8 is the practical default: it is already the Aeris convention, is rich enough for these NACA-to-NACA blended sections, and is converted through coordinates to NeuralFoil's canonical eight-weight Kulfan representation. The conversion is deliberately not a coefficient copy because the two parameterisations are not identical.

The NeuralFoil CSV and plot retain `analysis_confidence`; the current production source does not gate on it. The raw NeuralFoil core is incompressible, so its `mach` argument has no effect in the current Aeris source. AeroSandbox's extended wrapper adds its own compressibility correction. At the audited Mach {audit['mach_semantics']['mach']:.3f}, the raw-core max changes were ΔCL={audit['mach_semantics']['core_max_abs_delta_CL']:.3e} and ΔCD={audit['mach_semantics']['core_max_abs_delta_CD']:.3e}; the extended-interface changes were ΔCL={audit['mach_semantics']['extended_max_abs_delta_CL']:.3e} and ΔCD={audit['mach_semantics']['extended_max_abs_delta_CD']:.3e}.

The current batched strip query also evaluates all strips of one shape at their median Reynolds number. Across Re=2e5..2e6, the measured worst CD error in this audit was **{audit['query_cd_batch_reynolds']['max_abs_relative_error_pct']:.2f}%**. The standalone source groups by both shape and Reynolds bin instead.

Visual/numerical evidence: [polar plot](cst_neuralfoil/neuralfoil_polars.png), [polar CSV](cst_neuralfoil/neuralfoil_polars.csv), [CDCL audit](cst_neuralfoil/cdcl_fit_audit.csv), and [Re batching audit](implementation_audit/neuralfoil_batch_reynolds_audit.csv).

## AVL comparison at alpha = {alpha_target:g} deg

{_markdown_table(avl_table, list(avl_table.columns))}

`CD_corrected = CDind_AVL + CDprofile_NeuralFoil` is the primary viscous-corrected result. AVL's own CDCL integration is retained as an independent cross-check. With profile forces actually enabled, AVL `CDvis` and the strip-integrated profile drag differed by **{cdvis_agreement:.2f}%** in the controlled case.

The production runner currently sends `v` in AVL's OPER options. AVL starts with viscous/profile forces **on**, so that command toggles them **off**: the controlled production-semantics run produced `CDvis={production_semantics.raw_CDvis:.5f}` despite injecting {int(production_semantics.n_cdcl_injected)} section polars. Omitting that toggle produced `CDvis={fixed_semantics.raw_CDvis:.5f}`. The surface-level zero placeholder did not change the result when every section contained CDCL.

Visual/numerical evidence: [AVL plot](avl_comparison/avl_geometry_comparison.png), [all AVL cases](avl_comparison/avl_geometry_comparison.csv), and [CDCL semantics](avl_comparison/cdcl_semantics_audit.csv).

## Section convergence and DOE stress test

At 17 extracted sections, the worst error against the {reference_sections}-section reference over |alpha|>=4 deg was **{convergence_cl:.3f}% in CL** and **{convergence_cdi:.3f}% in CDi**.{zero_lift_note} Every resolution used the same {convergence_panels[0]} semispan panels, so this isolates section sampling rather than panel density. See [convergence plot](section_convergence/section_convergence.png) and [CSV](section_convergence/section_convergence.csv).

The wide-bound DOE completed **{len(successful_doe)}/{len(doe)}** cases; failures: **{failure_count}**. Across successful cases, the 95th-percentile absolute kSpan=3 area shift was **{doe_area_p95:.3f}%**, the alpha=4 deg pyGeo-vs-intended-ASB CL shift was **{doe_cl_p95:.3f}%**, and the CDi shift was **{doe_cdi_p95:.3f}%**. Worst extracted-plane warp was **{100*doe_warp_max:.3f}% chord** and worst CST RMS was **{100*doe_cst_max:.3f}% chord**. See [DOE plot](doe_stress/doe_stress.png) and [CSV](doe_stress/doe_stress.csv).

## Existing-code findings that must be resolved before integration

1. `station_airfoils` is configured as `{', '.join(case.prescribed_airfoil_names)}`, but the current section builder produced only `{', '.join(case.production_unique_airfoils)}`. The standalone intended case applies the four configured shapes without changing Aeris.
2. The AVL `v` option currently disables the injected CDCL contribution. Strip post-integration still creates a corrected total, but the claimed AVL-vs-strip cross-check is otherwise ineffective.
3. A relative AVL working directory causes AeroSandbox's AFILE path to be resolved twice after AVL changes directory. The standalone runner resolves every case directory to an absolute path.
4. The raw NeuralFoil core ignores Mach; use the AeroSandbox extended interface if its compressibility model is desired, and document that this is a wrapper correction rather than network output.
5. The current NeuralFoil batch query collapses different strip Reynolds numbers to one median Re and does not use confidence as a QC gate.
6. Audit the negative-side CDCL endpoint selector: with multiple consecutive high-drag points it can choose another point outside the intended threshold. Both production and symmetric corrected fits are saved for comparison.

## Interpretation limits

- CDCL changes profile drag only. It does **not** change AVL circulation, CL(alpha), stall, separation, or nonlinear lift. CLAF can alter the linear section lift slope but is not a nonlinear viscous coupling.
- For a swept, low-aspect-ratio BWB, assigning a 2-D polar to AVL's local strip `cl` is a model assumption. The AVL documentation itself warns that local section lift and stall interpretation is ambiguous for strongly three-dimensional wings.
- NeuralFoil is a fast XFoil-trained surrogate. Confidence filtering, XFoil spot checks, and selected RANS/experimental validation remain necessary for thesis-grade claims.
- A smooth loft is not automatically “more accurate” than a piecewise model. It is a new geometry definition whose area and aerodynamic shifts must be included in the design variables and convergence/validation story.

## Recommended integration boundary

Keep the implementation boundary narrow:

1. pyGeo owns the master outer mould line and CAD export.
2. A deterministic extractor returns normalised section coordinates, CST coefficients, physical LE/chord/twist, plane-warp QC, and a stable shape ID.
3. AeroSandbox receives those realised sections only to serialize/run AVL and to access its maintained NeuralFoil wrapper.
4. Run both section CDCL injection and independent strip-area profile-drag integration; require agreement within a declared tolerance.
5. Store loft order, section count, CST order/error, NeuralFoil model/version/confidence, Re/Mach, and all raw AVL files in every case manifest.

Primary references: [MIT AVL user primer](https://web.mit.edu/drela/Public/web/avl/AVL_User_Primer.pdf), [pyGeo documentation](https://mdolab-pygeo.readthedocs-hosted.com/), [NeuralFoil repository](https://github.com/peterdsharpe/NeuralFoil), and [NeuralFoil paper](https://arxiv.org/abs/2503.16323).
"""
    path = run_dir / "REPORT.md"
    path.write_text(report, encoding="utf-8")
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--doe-config", type=Path, default=DEFAULT_DOE_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--label", default="full_study")
    parser.add_argument("--velocity-mps", type=float, default=35.0)
    parser.add_argument("--altitude-m", type=float, default=0.0)
    parser.add_argument("--model-size", default="large")
    parser.add_argument("--doe-samples", type=int, default=24)
    parser.add_argument("--doe-seed-start", type=int, default=41000)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-doe", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.doe_samples < 1:
        raise ValueError("--doe-samples must be positive")
    run_dir = _unique_run_directory(args.output_root, args.label)
    versions = _package_versions()
    started = time.perf_counter()
    print(f"Study output: {run_dir}", flush=True)

    print("[1/7] Building production and intended baseline cases", flush=True)
    case = build_study_case(
        args.config, airfoil_database=DEFAULT_AIRFOILS, seed=None
    )
    _write_json(run_dir / "environment.json", versions)
    _write_json(run_dir / "baseline_sample.json", asdict(case.sample))
    _write_json(run_dir / "baseline_config_snapshot.json", case.raw_config)

    print("[2/7] Lofting and geometric surface comparison", flush=True)
    builds, curves, geometry_frame = geometry_study(
        case, run_dir, quick=args.quick
    )

    print("[3/7] CST order and NeuralFoil polar studies", flush=True)
    cst_frame, polar_frame, cdcl_frame, by_order = cst_and_polar_study(
        builds["pyGeo kSpan=3"], run_dir,
        velocity_mps=args.velocity_mps, altitude_m=args.altitude_m,
        model_size=args.model_size, quick=args.quick,
    )

    print("[4/7] AVL geometry and viscous-correction comparison", flush=True)
    avl_frame, semantics_frame, _ = avl_comparison_study(
        case, builds, run_dir,
        velocity_mps=args.velocity_mps, altitude_m=args.altitude_m,
        model_size=args.model_size, quick=args.quick,
    )

    print("[5/7] AVL section-sampling convergence", flush=True)
    convergence_frame = section_convergence_study(
        builds["pyGeo kSpan=3"], run_dir,
        velocity_mps=args.velocity_mps, altitude_m=args.altitude_m,
        quick=args.quick,
    )

    print("[6/7] Auditing existing bridge semantics", flush=True)
    representative = by_order[8][len(by_order[8]) // 2]
    audit = implementation_audit(
        case, representative, run_dir,
        velocity_mps=args.velocity_mps, altitude_m=args.altitude_m,
        model_size=args.model_size,
    )

    print("[7/7] Wide-bound DOE stress test", flush=True)
    doe_samples = min(args.doe_samples, 6) if args.quick else args.doe_samples
    if args.skip_doe:
        doe_frame = pd.DataFrame(columns=["failed"])
    else:
        doe_frame = doe_stress_study(
            args.doe_config, run_dir, samples=doe_samples,
            seed_start=args.doe_seed_start,
            velocity_mps=args.velocity_mps, altitude_m=args.altitude_m,
            quick=args.quick,
        )

    report_path = write_report(
        run_dir, case=case, geometry=geometry_frame, cst=cst_frame,
        polars=polar_frame, cdcl=cdcl_frame, avl=avl_frame,
        cdcl_semantics=semantics_frame, convergence=convergence_frame,
        doe=doe_frame, audit=audit, versions=versions,
    )
    summary = {
        "run_dir": run_dir,
        "report": report_path,
        "runtime_sec": time.perf_counter() - started,
        "quick": args.quick,
        "doe_samples": len(doe_frame),
        "doe_failures": int(doe_frame.failed.sum()) if len(doe_frame) else None,
        "station_airfoils_applied_in_production": case.prescribed_airfoils_applied_in_production,
        "geometry": geometry_frame.to_dict(orient="records"),
        "implementation_audit": audit,
    }
    _write_json(run_dir / "summary.json", summary)
    print(f"Completed in {summary['runtime_sec']:.1f} s", flush=True)
    print(f"REPORT={report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
