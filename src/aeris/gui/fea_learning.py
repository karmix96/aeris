"""Streamlit learning cockpit for interactive AERIS FEA/OAS exploration."""

# Streamlit labels and educational prose are intentionally readable.
# ruff: noqa: E501

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import streamlit as st

from aeris.common.config import load_yaml_config
from aeris.fea.case.loader import load_case_spec
from aeris.fea.case.runner import run_case
from aeris.fea.case.spec import AnalysisSpec, GeometryInput, OpenAeroStructValidationSpec
from aeris.fea.fields import contour_data
from aeris.fea.geometry import generate_aeris_stations, generate_custom_aeris_stations
from aeris.fea.mission import load_mission_authority
from aeris.fea.openaerostruct import run_oas_case, run_oas_validation

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover - handled in the browser
    go = None


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "configs/fea/bwb_baseline.yaml"
GEOMETRY = ROOT / "configs/geometry/bwb.yaml"
MATRIX = ROOT / "AERIS_MESH_STUDY/00_governance/lhs100_seed42_samples.csv"
MISSION = ROOT / "AERIS_MESH_STUDY/05_s6_cfd_qualification/mission_authority_v1.yaml"


def _design_ranges() -> dict[str, tuple[float, float]]:
    from aeris.geometry.config_resolver import resolve_generator_and_config

    raw = load_yaml_config(GEOMETRY)
    _, config = resolve_generator_and_config(raw)
    ranges = {}
    for name in config.active_design_variable_names():
        section = config.planform_bounds if hasattr(config.planform_bounds, name) else config.section_bounds
        if hasattr(config.elevon_bounds, name):
            section = config.elevon_bounds
        value = getattr(section, name)
        ranges[name] = (float(value.min), float(value.max))
    return ranges


def _locked_design_values(index: int) -> dict[str, float]:
    import csv

    with MATRIX.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    row = next(row for row in rows if int(row["sample_index"]) == index)
    return {key: float(value) for key, value in row.items() if key != "sample_index" and value}


def _figure_mesh(case_dir: Path, field: str, scale: float) -> object:
    if go is None:
        raise RuntimeError("Plotly is not installed; install the FEA GUI extra")
    data = contour_data(case_dir, st.session_state["load_case"])
    coordinates = np.asarray(data["coordinates"], dtype=float)
    values = np.asarray(data[field], dtype=float)
    faces = np.asarray(data["faces"], dtype=int)
    center = coordinates.mean(axis=0)
    scale_factor = 1.0 + scale * values / max(float(values.max()), 1e-30)
    shown = center + (coordinates - center) * scale_factor[:, None]
    colorscale = "Turbo" if field == "stress_pa" else "Viridis"
    label = "von Mises proxy [Pa]" if field == "stress_pa" else "displacement [m]"
    return go.Figure(
        go.Mesh3d(
            x=shown[:, 0], y=shown[:, 1], z=shown[:, 2],
            i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            intensity=values, colorscale=colorscale, colorbar={"title": label},
            flatshading=True, hovertemplate=f"{label}: %{{intensity:.4g}}<extra></extra>",
        )
    ).update_layout(
        title="FEA contour: colors show where the structure responds most",
        scene_aspectmode="data", margin={"l": 0, "r": 0, "t": 45, "b": 0},
    )


def _build_case(index: int, custom_values: dict[str, float], source: str) -> tuple[object, Path]:
    workdir = ROOT / "data/fea_learning" / (f"index{index}" if source == "locked" else "custom")
    stations = workdir / "inputs/stations.json"
    if source == "locked":
        generate_aeris_stations(
            GEOMETRY, stations, design_matrix_file=MATRIX,
            design_set="lhs100_seed42", design_index=index,
        )
    else:
        generate_custom_aeris_stations(GEOMETRY, stations, custom_values)
    spec = load_case_spec(BASELINE)
    spec = replace(
        spec,
        name=f"fea_learning_{source}_{index}",
        geometry=GeometryInput(stations_file=stations),
        # The cockpit's interactive FEA mode is deliberately static-only.
        # Modal/buckling/nonlinear analyses remain available through the
        # governed CLI and should not be demanded by the static post gate.
        analyses=AnalysisSpec(),
    )
    if source != "locked":
        # Custom geometry is not an S8 CFD identity, so use an explicit
        # educational pressure load and label the OAS comparison as unvalidated.
        loads = tuple(
            replace(load, source="pressure", pressure_pa=1000.0, distribution="elliptical")
            for load in spec.loads
        )
        spec = replace(
            spec,
            loads=loads,
            openaerostruct_validation=OpenAeroStructValidationSpec(enabled=False),
        )
    return spec, workdir


def main() -> None:
    st.set_page_config(page_title="AERIS FEA Learning Cockpit", layout="wide")
    st.title("AERIS FEA learning cockpit")
    st.caption("Explore a wing, see its mesh, run structural or aerodynamic analysis, and learn what the colors mean.")
    st.info(
        "A mesh is the structure split into small tiles. FEA estimates how much those tiles "
        "move and stress under a load. OpenAeroStruct estimates aerodynamic lift with a fast "
        "lifting-line/VLM model. They answer different questions, so agreement is useful—but "
        "it does not make OAS a stress validation tool."
    )
    with st.sidebar:
        st.header("1. Choose a wing")
        source_label = st.radio("Geometry source", ["Locked S8 design", "Custom variable values"])
        source = "locked" if source_label.startswith("Locked") else "custom"
        index = st.slider("S8 design index", 0, 99, 83, disabled=source != "locked")
        custom_values: dict[str, float] = {}
        if source == "custom":
            st.write("These sliders are bounded by the canonical AERIS design space.")
            defaults = _locked_design_values(83)
            for name, (minimum, maximum) in _design_ranges().items():
                custom_values[name] = st.slider(
                    name, minimum, maximum, float(defaults[name]),
                    step=(maximum - minimum) / 100.0,
                )
        st.header("2. Choose what to run")
        analysis = st.radio("Analysis", ["FEA structure", "OpenAeroStruct aerodynamics", "Compare both"])
        st.session_state["load_case"] = st.selectbox("FEA load case", ["positive_limit", "negative_limit"])
        contour = st.selectbox("FEA contour", ["displacement_m", "stress_pa"])
        deformation = st.slider("Deformation display exaggeration", 0.0, 25.0, 5.0)
        prepare = st.button("Generate geometry and mesh", type="primary")
        run = st.button("Run selected analysis")

    if prepare or run:
        try:
            spec, workdir = _build_case(index, custom_values, source)
            st.session_state["spec"] = spec
            st.session_state["workdir"] = workdir
            if prepare:
                run_case(spec, workdir=workdir, stages=("geometry", "mesh"), dry_run=True)
                st.success(f"Mesh ready at `{workdir}`. Scroll down to inspect it.")
            if run:
                if analysis in {"OpenAeroStruct aerodynamics", "Compare both"}:
                    mission = load_mission_authority(MISSION)
                    stations = json.loads((workdir / "inputs/stations.json").read_text())
                    if source == "locked":
                        oas_path = workdir / "validation/openaerostruct_validation.json"
                        st.session_state["oas_report"] = run_oas_validation(
                            stations, mission, spec.openaerostruct_validation, oas_path
                        )
                    else:
                        st.session_state["oas_case"] = run_oas_case(stations, mission, 8.0)
                if analysis in {"FEA structure", "Compare both"}:
                    stages = ("geometry", "validate", "mesh", "solve", "post") if source == "locked" else (
                        "geometry", "mesh", "solve", "post"
                    )
                    run_case(spec, workdir=workdir, stages=stages)
                st.success("Analysis finished. The plots below are ready.")
        except Exception as exc:  # GUI should explain failures instead of crashing
            st.error(str(exc))

    workdir = st.session_state.get("workdir")
    if not workdir:
        st.subheader("Start here")
        st.write("Choose a wing, generate its mesh, then run one analysis. Every control has a plain-language explanation.")
        return
    workdir = Path(workdir)
    st.subheader("3. Inspect the structural mesh")
    mesh_report = workdir / "mesh/mesh_report.json"
    if mesh_report.is_file():
        report = json.loads(mesh_report.read_text())
        st.metric("Mesh tiles", f"{report['element_count']:,}")
        st.metric("Structural mass", f"{report['full_structural_mass_kg']:.3f} kg")
        st.caption("More tiles usually resolve detail better, but they also cost more computation. A mesh-convergence study checks whether the answer changes when tiles get smaller.")
    if (workdir / "solve" / st.session_state["load_case"] / "model.frd").is_file():
        st.plotly_chart(_figure_mesh(workdir, contour, deformation), use_container_width=True)
        st.caption("Displacement means movement. Stress is an intensity of internal force; hotspots deserve engineering attention, but a contour alone is not a pass/fail decision.")
    if st.session_state.get("oas_report") or st.session_state.get("oas_case"):
        st.subheader("4. Aerodynamic view")
        oas = st.session_state.get("oas_report", {})
        if oas:
            comparisons = oas.get("comparisons", [])
            st.line_chart({"S8 CFD CL": {str(x["alpha_deg"]): x["cfd_cl"] for x in comparisons}, "OAS CL": {str(x["alpha_deg"]): x["oas_cl"] for x in comparisons}})
            st.caption("This plot compares whole-wing lift. It does not predict shell stress or buckling.")
        else:
            case = st.session_state["oas_case"]
            st.metric("OpenAeroStruct CL at 8°", f"{case['cl']:.4f}")
            st.metric("Inviscid CD", f"{case['cd_inviscid']:.5f}")
    if st.session_state.get("oas_report") and (workdir / "verification.json").is_file():
        st.subheader("5. What do the two models say differently?")
        verification = json.loads((workdir / "verification.json").read_text())
        oas = st.session_state["oas_report"]
        st.write(
            f"OpenAeroStruct checks global lift (maximum |ΔCL| = "
            f"{max(abs(float(row['cl_error'])) for row in oas['comparisons']):.4f}). "
            f"FEA checks structural response (maximum displacement = "
            f"{max(float(row['max_displacement_m']) for row in verification['loads'].values()) * 1e3:.3f} mm)."
        )
        st.warning("A small aerodynamic difference does not guarantee a safe structure. The models are complementary, not interchangeable.")


if __name__ == "__main__":
    main()
