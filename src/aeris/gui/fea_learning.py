"""Streamlit learning cockpit for interactive AERIS FEA/OAS exploration."""

# Streamlit labels and educational prose are intentionally readable.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import streamlit as st

from aeris.common.config import load_yaml_config
from aeris.fea.case.loader import load_case_spec
from aeris.fea.case.runner import run_case
from aeris.fea.case.spec import (
    AnalysisSpec,
    CaseSpec,
    GeometryInput,
    OpenAeroStructValidationSpec,
)
from aeris.fea.fields import contour_data, mesh_data
from aeris.fea.geometry import generate_aeris_stations, generate_custom_aeris_stations
from aeris.fea.mission import load_mission_authority
from aeris.fea.openaerostruct import (
    build_oas_mesh,
    run_oas_case,
    run_oas_prediction,
    run_oas_validation,
)

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


def _mesh_figure(
    coordinates: np.ndarray,
    faces: np.ndarray,
    values: np.ndarray,
    *,
    title: str,
    label: str,
    colorscale: str,
    edges: np.ndarray | None = None,
    render_mode: str = "Surface",
) -> object:
    if go is None:
        raise RuntimeError("Plotly is not installed; install the FEA GUI extra")
    if len(faces) == 0:
        raise ValueError("the generated mesh has no plottable shell faces")
    if render_mode not in {"Surface", "Wireframe", "Surface + edges"}:
        raise ValueError(f"unknown mesh render mode: {render_mode}")
    traces: list[object] = []
    if render_mode != "Wireframe":
        traces.append(go.Mesh3d(
            x=coordinates[:, 0],
            y=coordinates[:, 1],
            z=coordinates[:, 2],
            i=faces[:, 0],
            j=faces[:, 1],
            k=faces[:, 2],
            intensity=values,
            colorscale=colorscale,
            colorbar={"title": label},
            flatshading=True,
            hovertemplate=f"{label}: %{{intensity:.4g}}<extra></extra>",
            name="shell surface",
        ))
    if render_mode != "Surface":
        if edges is None or len(edges) == 0:
            raise ValueError("wireframe rendering requires structural element edges")
        x: list[float | None] = []
        y: list[float | None] = []
        z: list[float | None] = []
        line_values: list[float] = []
        for start, end in np.asarray(edges, dtype=int):
            x.extend((float(coordinates[start, 0]), float(coordinates[end, 0]), None))
            y.extend((float(coordinates[start, 1]), float(coordinates[end, 1]), None))
            z.extend((float(coordinates[start, 2]), float(coordinates[end, 2]), None))
            line_values.extend((float(values[start]), float(values[end]), float("nan")))
        colored_wireframe = render_mode == "Wireframe"
        traces.append(go.Scatter3d(
            x=x,
            y=y,
            z=z,
            mode="lines",
            line={
                "color": line_values if colored_wireframe else "rgba(20,20,20,0.72)",
                "colorscale": colorscale,
                "showscale": colored_wireframe,
                "colorbar": {"title": label},
                "width": 2.4 if colored_wireframe else 1.4,
            },
            hoverinfo="skip",
            name="element edges",
        ))
    return go.Figure(data=traces).update_layout(
        title=title,
        scene={
            "aspectmode": "data",
            "xaxis_title": "x [m]",
            "yaxis_title": "span y [m]",
            "zaxis_title": "z [m]",
        },
        showlegend=False,
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
    )


def _figure_geometry_mesh(case_dir: Path, render_mode: str = "Surface + edges") -> object:
    data = mesh_data(case_dir)
    return _mesh_figure(
        np.asarray(data["coordinates"], dtype=float),
        np.asarray(data["faces"], dtype=int),
        np.asarray(data["region_values"], dtype=float),
        title="Generated structural shell mesh — drag to rotate, wheel to zoom",
        label="region index",
        colorscale="Turbo",
        edges=np.asarray(data["edges"], dtype=int),
        render_mode=render_mode,
    )


def _figure_fea(
    case_dir: Path,
    load_case: str,
    field: str,
    exaggeration: float,
    render_mode: str = "Surface + edges",
) -> object:
    data = contour_data(case_dir, load_case)
    coordinates = np.asarray(data["coordinates"], dtype=float)
    values = np.asarray(data[field], dtype=float)
    faces = np.asarray(data["faces"], dtype=int)
    shown = coordinates.copy()
    if field == "displacement_m" and exaggeration > 0.0:
        vectors = np.asarray(data["displacement_vectors_m"], dtype=float)
        max_displacement = max(float(values.max()), 1e-30)
        span = max(float(np.ptp(coordinates[:, 1])), 1e-9)
        display_multiplier = exaggeration * 0.02 * span / max_displacement
        shown = coordinates + vectors * display_multiplier
    colorscale = "Turbo" if field == "stress_pa" else "Viridis"
    label = "von Mises stress [Pa]" if field == "stress_pa" else "displacement magnitude [m]"
    if not np.any(values > 0.0):
        raise ValueError(f"{label} field is empty; the solver result was not written")
    return _mesh_figure(
        shown,
        faces,
        values,
        title=f"CalculiX FEA contour — {load_case}",
        label=label,
        colorscale=colorscale,
        edges=np.asarray(data["edges"], dtype=int),
        render_mode=render_mode,
    )


def _figure_oas(case: dict[str, object], stations: dict[str, object]) -> object:
    mesh = build_oas_mesh(stations, 5)
    chordwise, spanwise, _ = mesh.shape
    coordinates = mesh.reshape((-1, 3))
    faces: list[tuple[int, int, int]] = []
    for chord_index in range(chordwise - 1):
        for span_index in range(spanwise - 1):
            a = chord_index * spanwise + span_index
            b = (chord_index + 1) * spanwise + span_index
            faces.extend(((a, b, b + 1), (a, b + 1, a + 1)))
    forces = np.asarray(case["spanwise_force_xyz_n_tip_to_root"], dtype=float)
    panel_load = np.abs(forces[:, 2])
    span_load = np.zeros(spanwise)
    span_count = np.zeros(spanwise)
    for index, value in enumerate(panel_load):
        span_load[index] += value
        span_load[index + 1] += value
        span_count[index] += 1.0
        span_count[index + 1] += 1.0
    span_load /= np.maximum(span_count, 1.0)
    values = np.tile(span_load, chordwise)
    return _mesh_figure(
        coordinates,
        np.asarray(faces, dtype=int),
        values,
        title=f"OpenAeroStruct sectional aerodynamic load — alpha {case['alpha_deg']}°",
        label="|section Fz| [N]",
        colorscale="Plasma",
    )


def _cfd_validated_indices(
    validation: OpenAeroStructValidationSpec,
    mission: dict[str, object],
) -> set[int]:
    """Return indices with a complete accepted CFD alpha set for this authority."""
    if validation.cfd_dataset is None or validation.geometry_set is None:
        return set()
    rows = json.loads(validation.cfd_dataset.read_text(encoding="utf-8"))
    state = mission.get("state")
    if not isinstance(rows, list) or not isinstance(state, dict):
        return set()
    wanted = {float(value) for value in state.get("alpha_deg", [])}
    accepted: dict[int, set[float]] = {}
    for row in rows:
        if (
            isinstance(row, dict)
            and row.get("geometry_set") == validation.geometry_set
            and row.get("grid_level") == validation.grid_level
            and row.get("gate_verdict") == "ACCEPTED"
            and isinstance(row.get("geometry_index"), int)
        ):
            accepted.setdefault(int(row["geometry_index"]), set()).add(float(row["alpha_deg"]))
    return {index for index, alphas in accepted.items() if wanted <= alphas}


def _run_oas_report(
    spec: CaseSpec,
    stations: dict[str, object],
    mission: dict[str, object],
    output_path: Path,
) -> dict[str, object]:
    validation = spec.openaerostruct_validation
    if validation.enabled:
        return run_oas_validation(stations, mission, validation, output_path)
    return run_oas_prediction(
        stations,
        mission,
        output_path,
        chordwise_nodes=validation.chordwise_nodes,
    )



def _build_case(
    index: int, custom_values: dict[str, float], source: str
) -> tuple[CaseSpec, Path]:
    if source == "locked":
        run_key = f"index{index}"
    else:
        encoded = json.dumps(custom_values, sort_keys=True).encode("utf-8")
        run_key = f"custom_{hashlib.sha256(encoded).hexdigest()[:12]}"
    workdir = ROOT / "data/fea_learning" / run_key
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
    if source == "locked":
        mission = load_mission_authority(MISSION)
        validated_indices = _cfd_validated_indices(spec.openaerostruct_validation, mission)
        spec = replace(
            spec,
            openaerostruct_validation=replace(
                spec.openaerostruct_validation,
                enabled=index in validated_indices,
                geometry_index=index,
            ),
        )
    else:
        # Custom geometry is not an S8 CFD identity, so use an explicit
        # educational pressure load and label the OAS comparison as unvalidated.
        loads = tuple(
            replace(
                load,
                source="pressure",
                pressure_pa=1000.0 * load.direction,
                distribution="elliptical",
            )
            for load in spec.loads
        )
        spec = replace(
            spec,
            loads=loads,
            openaerostruct_validation=OpenAeroStructValidationSpec(enabled=False),
        )
    return spec, workdir


def _legacy_main() -> None:
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
                    step=max((maximum - minimum) / 100.0, 1e-6),
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
        st.plotly_chart(_figure_mesh(workdir, contour, deformation), width="stretch")
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


def _selected_oas_case(report: dict[str, object], load_case: str) -> dict[str, object] | None:
    wanted_alpha = 8.0 if load_case == "positive_limit" else -2.0
    for case in report.get("cases", []):
        if abs(float(case["alpha_deg"]) - wanted_alpha) < 1e-9:
            return case
    return None


def main() -> None:
    st.set_page_config(page_title="AERIS FEA Learning Cockpit", layout="wide")
    st.title("AERIS FEA learning cockpit")
    st.caption(
        "Generate a wing, inspect its real shell mesh, run CalculiX or OpenAeroStruct, "
        "and explore the resulting 3D fields."
    )
    st.info(
        "FEA answers: how does the structure move and where is it stressed? "
        "OpenAeroStruct answers: how is aerodynamic load distributed? The Compare mode "
        "runs both and puts those complementary answers beside each other."
    )

    with st.sidebar:
        st.header("1. Choose a wing")
        source_label = st.radio(
            "Geometry source",
            ["Locked S8 design", "Custom variable values"],
            key="learning_geometry_source",
        )
        source = "locked" if source_label.startswith("Locked") else "custom"
        index = st.slider(
            "S8 design index", 0, 99, 83,
            disabled=source != "locked", key="learning_design_index",
        )
        custom_values: dict[str, float] = {}
        if source == "custom":
            st.caption("Variables are limited to the governed AERIS design-space bounds.")
            defaults = _locked_design_values(83)
            with st.expander("Geometry variables", expanded=True):
                for name, (minimum, maximum) in _design_ranges().items():
                    if abs(maximum - minimum) < 1e-12:
                        custom_values[name] = st.number_input(
                            name, value=float(minimum), disabled=True,
                            key=f"custom_{name}",
                        )
                    else:
                        custom_values[name] = st.slider(
                            name, float(minimum), float(maximum), float(defaults[name]),
                            step=max((maximum - minimum) / 100.0, 1e-6),
                            key=f"custom_{name}",
                        )

        st.header("2. Choose what to run")
        analysis = st.radio(
            "Analysis",
            ["FEA structure", "OpenAeroStruct aerodynamics", "Compare both"],
            key="learning_analysis",
        )
        load_case = st.selectbox(
            "Load case", ["positive_limit", "negative_limit"],
            key="learning_load_case",
        )
        contour_labels = {
            "Displacement magnitude": "displacement_m",
            "Von Mises stress": "stress_pa",
        }
        contour_label = st.selectbox("FEA contour", list(contour_labels))
        contour = contour_labels[contour_label]
        mesh_render_mode = st.selectbox(
            "Mesh visualization",
            ["Surface + edges", "Wireframe", "Surface"],
            help=(
                "Surface + edges exposes the real element boundaries; Wireframe hides the "
                "shell faces; Surface gives the cleanest contour view."
            ),
        )
        exaggeration = st.slider(
            "Displayed deformation exaggeration", 0.0, 10.0, 2.0, 0.25,
            help="Changes the displayed shape only; contour values remain physical.",
        )
        generate_clicked = st.button("Generate fresh geometry + mesh", type="primary")
        run_clicked = st.button("Run fresh selected analysis", type="secondary")
        st.caption("Every click executes the requested stages again; solver timing is shown below.")

    if generate_clicked or run_clicked:
        try:
            spec, requested_workdir = _build_case(index, custom_values, source)
            run_identity = str(requested_workdir)
            if st.session_state.get("active_run") != run_identity:
                for key in ("oas_report", "oas_case", "fea_complete", "timings"):
                    st.session_state.pop(key, None)
            st.session_state["active_run"] = run_identity
            st.session_state["spec"] = spec
            st.session_state["workdir"] = requested_workdir
            timings: dict[str, float] = {}

            if generate_clicked:
                started = time.perf_counter()
                with st.status("Generating geometry and audited shell mesh…", expanded=True) as status:
                    st.write("Creating canonical structural stations")
                    st.write("Building skins, spars, ribs, doublers, hinge, and cut-out regions")
                    run_case(
                        spec, workdir=requested_workdir,
                        stages=("geometry", "mesh"), dry_run=True,
                    )
                    timings["mesh_seconds"] = time.perf_counter() - started
                    status.update(label="Geometry and mesh generated", state="complete")
                st.session_state["timings"] = timings
                st.session_state["fea_complete"] = False
                st.session_state.pop("oas_report", None)
                st.session_state.pop("oas_case", None)

            if run_clicked:
                run_fea = analysis in {"FEA structure", "Compare both"}
                run_oas = analysis in {"OpenAeroStruct aerodynamics", "Compare both"} or (
                    run_fea and any(load.source == "openaerostruct" for load in spec.loads)
                )
                if not run_fea:
                    st.session_state["fea_complete"] = False
                if not run_oas:
                    st.session_state.pop("oas_report", None)
                    st.session_state.pop("oas_case", None)

                with st.status("Executing requested solvers…", expanded=True) as status:
                    if run_oas:
                        started = time.perf_counter()
                        validation_label = (
                            "with accepted S8 CFD comparison"
                            if spec.openaerostruct_validation.enabled
                            else "as prediction-only load model (no CFD row for this wing)"
                        )
                        st.write(f"Running OpenAeroStruct {validation_label}")
                        mission = load_mission_authority(MISSION)
                        stations = json.loads(
                            (requested_workdir / "inputs" / "stations.json").read_text()
                        )
                        oas_path = (
                            requested_workdir
                            / "validation"
                            / "openaerostruct_validation.json"
                        )
                        st.session_state["oas_report"] = _run_oas_report(
                            spec, stations, mission, oas_path,
                        )
                        timings["oas_seconds"] = time.perf_counter() - started

                    if run_fea:
                        started = time.perf_counter()
                        st.write("Running fresh CalculiX static solves for both limit cases")
                        stages = (
                            ("geometry", "validate", "mesh", "solve", "post")
                            if spec.openaerostruct_validation.enabled
                            else ("geometry", "mesh", "solve", "post")
                        )
                        run_case(spec, workdir=requested_workdir, stages=stages)
                        result_file = requested_workdir / "solve" / load_case / "model.dat"
                        if not result_file.is_file() or result_file.stat().st_size == 0:
                            raise ValueError("CalculiX returned without a non-empty model.dat result")
                        st.session_state["fea_complete"] = True
                        if run_oas:
                            validation_file = (
                                requested_workdir
                                / "validation"
                                / "openaerostruct_validation.json"
                            )
                            st.session_state["oas_report"] = json.loads(validation_file.read_text())

                        timings["fea_seconds"] = time.perf_counter() - started
                    st.session_state["timings"] = timings
                    status.update(label="Requested solvers completed", state="complete")
                st.success("Fresh results are ready below.")
        except Exception as exc:
            st.exception(exc)

    workdir_value = st.session_state.get("workdir")
    if not workdir_value:
        st.subheader("Start here")
        st.write(
            "Choose a geometry and click **Generate fresh geometry + mesh**. "
            "The interactive mesh appears before you run either solver."
        )
        return

    workdir = Path(workdir_value)
    timings = st.session_state.get("timings", {})
    st.caption(f"Active run directory: {workdir}")
    active_spec = st.session_state.get("spec")
    if isinstance(active_spec, CaseSpec):
        if active_spec.openaerostruct_validation.enabled:
            st.success(
                "This wing has a complete accepted S8 CFD comparison set. "
                "OpenAeroStruct will be checked against the matching geometry index."
            )
        elif source == "locked":
            st.warning(
                "This S8 wing has no complete accepted CFD comparison set. "
                "OpenAeroStruct is prediction-only here; its spanwise shape may drive the "
                "FEA limit load, but no CFD-validation claim is made."
            )
    if timings:
        timing_columns = st.columns(3)
        timing_columns[0].metric(
            "Mesh generation",
            f"{timings.get('mesh_seconds', 0.0):.2f} s"
            if "mesh_seconds" in timings else "not run",
        )
        timing_columns[1].metric(
            "OpenAeroStruct",
            f"{timings.get('oas_seconds', 0.0):.2f} s"
            if "oas_seconds" in timings else "not run",
        )
        timing_columns[2].metric(
            "CalculiX FEA",
            f"{timings.get('fea_seconds', 0.0):.2f} s"
            if "fea_seconds" in timings else "not run",
        )

    st.subheader("3. Generated geometry and structural mesh")
    mesh_report_path = workdir / "mesh" / "mesh_report.json"
    mesh_input = workdir / "mesh" / "wingbox_mesh.inp"
    if mesh_report_path.is_file() and mesh_input.is_file():
        mesh_report = json.loads(mesh_report_path.read_text())
        metric_columns = st.columns(3)
        metric_columns[0].metric("Mesh nodes", f"{mesh_report['node_count']:,}")
        metric_columns[1].metric("Shell elements", f"{mesh_report['element_count']:,}")
        metric_columns[2].metric(
            "Structural mass", f"{mesh_report['full_structural_mass_kg']:.3f} kg"
        )
        st.plotly_chart(
            _figure_geometry_mesh(workdir, mesh_render_mode),
            width="stretch",
        )
        st.caption(
            "This is the actual CalculiX shell mesh. Rotate it with the mouse. "
            "Colors distinguish structural regions; they are not solver results yet."
        )
    else:
        st.warning("No mesh exists for this selection. Click Generate fresh geometry + mesh.")

    result_path = workdir / "solve" / load_case / "model.dat"
    verification_path = workdir / "verification.json"
    if st.session_state.get("fea_complete") and result_path.is_file() and verification_path.is_file():
        st.subheader("4. CalculiX structural result")
        verification = json.loads(verification_path.read_text())
        result = verification["loads"][load_case]
        result_columns = st.columns(3)
        result_columns[0].metric(
            "Maximum displacement", f"{float(result['max_displacement_m']) * 1e3:.4f} mm"
        )
        result_columns[1].metric(
            "Maximum von Mises stress", f"{float(result['max_von_mises_pa']) / 1e6:.3f} MPa"
        )
        result_columns[2].metric(
            "Yield safety factor", f"{float(result['safety_factor_yield']):.1f}"
        )
        try:
            st.plotly_chart(
                _figure_fea(
                    workdir,
                    load_case,
                    contour,
                    exaggeration,
                    mesh_render_mode,
                ),
                width="stretch",
            )
        except Exception as exc:
            st.error(f"Could not build the FEA contour: {exc}")
        st.caption(
            "Contour values come from the fresh CalculiX DAT result using original mesh IDs. "
            "Deformation exaggeration affects display only."
        )
    else:
        st.info("No FEA result for this load case yet. Choose FEA or Compare and run it.")

    stations_path = workdir / "inputs" / "stations.json"
    stations = json.loads(stations_path.read_text()) if stations_path.is_file() else None
    oas_report = st.session_state.get("oas_report")
    oas_case = st.session_state.get("oas_case")
    validation_path = workdir / "validation" / "openaerostruct_validation.json"
    selected_case = (
        _selected_oas_case(oas_report, load_case)
        if isinstance(oas_report, dict)
        else oas_case
    )
    if selected_case and stations:
        st.subheader("5. OpenAeroStruct aerodynamic result")
        if isinstance(oas_report, dict) and oas_report.get("status") == "prediction_only":
            st.warning(
                "Prediction-only result: useful for learning and load-shape screening, "
                "but not validated against an accepted CFD row for this geometry."
            )
        aero_columns = st.columns(3)
        aero_columns[0].metric("Lift coefficient CL", f"{float(selected_case['cl']):.4f}")
        aero_columns[1].metric(
            "Inviscid drag coefficient", f"{float(selected_case['cd_inviscid']):.5f}"
        )
        aero_columns[2].metric(
            "Reference area", f"{float(selected_case['reference_area_full_m2']):.4f} m²"
        )
        st.plotly_chart(_figure_oas(selected_case, stations), width="stretch")
        st.caption(
            "This contour is sectional aerodynamic force, not structural stress. "
            "It shows where OAS says the air loads the wing."
        )
    else:
        st.info("No OpenAeroStruct result yet. Choose OAS or Compare and run it.")

    if selected_case and verification_path.is_file():
        st.subheader("6. Compare what each model means")
        st.markdown(
            "- **OpenAeroStruct:** aerodynamic load and whole-wing coefficients.\n"
            "- **CalculiX FEA:** displacement, stress, mass, and safety factor under that load.\n"
            "- **Difference:** these are different physical quantities; compare the load path "
            "and trends, not CL numerically against stress."
        )

    st.subheader("7. Open or download this run's reports")
    oas_report_label = (
        "OAS prediction"
        if isinstance(oas_report, dict) and oas_report.get("status") == "prediction_only"
        else "OAS validation"
    )
    report_candidates = {
        "FEA verification": verification_path,
        "Case manifest": workdir / "case_manifest.json",
        oas_report_label: validation_path,
    }
    for label, path in report_candidates.items():
        if path.is_file():
            st.download_button(
                f"Download {label}",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/json",
                key=f"download_{label}_{workdir.name}",
            )
            st.caption(f"{label}: {path}")



if __name__ == "__main__":
    main()
