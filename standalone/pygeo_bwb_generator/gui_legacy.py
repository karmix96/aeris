"""Legacy standalone Streamlit mission control for the config-driven pyGeo BWB generator.

Launch from the repository root:

    .venv/bin/python -m streamlit run \
        standalone/pygeo_bwb_generator/gui.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from standalone.pygeo_bwb_generator.generate import (  # noqa: E402
    AIRFOIL_STATIONS,
    BuiltCase,
    ControlSurfaceSpec,
    build_case,
    create_doe,
    load_config,
    resolve_control_surface,
    run_campaign,
    write_case,
)
from standalone.pygeo_bwb_generator.gui_support import (  # noqa: E402
    airfoil_catalog,
    airfoil_preview_data,
    build_config_payload,
    case_artifact_rows,
    display_surfaces,
    dump_config,
    export_capability_frame,
    latest_study_run,
    load_study_summary,
    metric_rows,
    ranges_from_frame,
    variable_frame,
    write_config,
)

st.set_page_config(
    page_title="pyGeo BWB Generator",
    page_icon="△",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
  .stApp {background: #F5F7FA;}
  [data-testid="stSidebar"] {background: #152436;}
  [data-testid="stSidebar"] * {color: #E5EEF8;}
  [data-testid="stMain"] {color: #1D3145;}
  [data-testid="stMain"] h1,
  [data-testid="stMain"] h2,
  [data-testid="stMain"] h3,
  [data-testid="stMain"] h4,
  [data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
  [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
  [data-testid="stMain"] [data-testid="stCaptionContainer"] p,
  [data-testid="stMain"] [data-testid="stMetricLabel"] p,
  [data-testid="stMain"] [data-testid="stMetricValue"] {
    color: #1D3145 !important;
  }
  [data-testid="stMain"] [data-testid="stCaptionContainer"] p {
    color: #60758A !important;
  }
  [data-testid="stMain"] .stButton button p,
  [data-testid="stMain"] .stDownloadButton button p {
    color: #FFFFFF !important;
  }
  [data-testid="stMain"] .stTabs button[data-baseweb="tab"] p {
    color: #52697E !important; font-weight: 650;
  }
  [data-testid="stMain"] .stTabs button[aria-selected="true"] p {
    color: #D9364A !important;
  }
  [data-testid="stMain"] [data-testid="stExpander"] summary p {
    color: #29445D !important;
  }
  .hero {
    padding: 1.1rem 1.3rem; border-radius: 14px; margin-bottom: .8rem;
    color: white; background: linear-gradient(110deg,#10263d,#1f4d72 58%,#287a8a);
    border: 1px solid #5ea7c0; box-shadow: 0 8px 28px #0f2d4424;
  }
  .hero h1 {
    color: #FFFFFF !important; font-size: 1.65rem; margin: 0 0 .2rem 0;
  }
  .hero p {margin: 0; color: #D6E8F3 !important;}
  .cap {
    padding: .75rem .9rem; border: 1px solid #CCD7E2; border-radius: 10px;
    color: #344B60 !important; background: #FFFFFF; min-height: 90px;
    box-shadow: 0 3px 12px #20364A12;
  }
  .cap b {color: #1D3145 !important;}
  .available {color:#087A5B;font-weight:800}
  .partial {color:#A65B00;font-weight:800}
  .missing {color:#B42318;font-weight:800}
</style>
""",
    unsafe_allow_html=True,
)


def _hero() -> None:
    st.markdown(
        """
<div class="hero">
  <h1>△ Standalone pyGeo BWB Generator</h1>
  <p>Aeris BWB definition · pyGeo master loft · deterministic DoE · realised-section QC</p>
</div>
""",
        unsafe_allow_html=True,
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _surface_figure(
    case: BuiltCase,
    control: ControlSurfaceSpec,
    *,
    show_deflection: bool,
) -> go.Figure:
    surfaces = display_surfaces(case, control, show_deflection=show_deflection)
    figure = go.Figure()
    colors = {
        ("right", 0): [[0.0, "#2E7DA6"], [1.0, "#2E7DA6"]],
        ("right", 1): [[0.0, "#52A39A"], [1.0, "#52A39A"]],
        ("left", 0): [[0.0, "#2E7DA6"], [1.0, "#2E7DA6"]],
        ("left", 1): [[0.0, "#52A39A"], [1.0, "#52A39A"]],
    }
    for side, pair in surfaces.items():
        for index, surface in enumerate(pair):
            stride_chord = max(1, surface.shape[0] // 70)
            stride_span = max(1, surface.shape[1] // 70)
            shown = surface[::stride_chord, ::stride_span]
            figure.add_trace(
                go.Surface(
                    x=shown[:, :, 0],
                    y=shown[:, :, 1],
                    z=shown[:, :, 2],
                    surfacecolor=np.zeros(shown.shape[:2]),
                    colorscale=colors[(side, index)],
                    showscale=False,
                    opacity=0.94,
                    name=f"{side} {'upper' if index == 0 else 'lower'}",
                    hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>z=%{z:.4f} m<extra></extra>",
                )
            )
    figure.update_layout(
        height=690,
        margin=dict(l=0, r=0, t=45, b=0),
        title=(
            "Kinematic sampled-surface control preview"
            if show_deflection and control.enabled
            else "Neutral native pyGeo loft"
        ),
        scene=dict(
            xaxis_title="x [m]",
            yaxis_title="y [m]",
            zaxis_title="z [m]",
            aspectmode="data",
            camera=dict(eye=dict(x=-1.55, y=-1.8, z=0.85)),
        ),
        paper_bgcolor="white",
    )
    return figure


def _physical_cad_figure(mesh_path: Path) -> go.Figure:
    """Interactive rendering of the exact tessellated split-solid assembly."""

    with np.load(mesh_path, allow_pickle=False) as data:
        vertices = np.asarray(data["vertices_m"], dtype=float)
        triangles = np.asarray(data["triangles"], dtype=np.int64)
        body_ids = np.asarray(data["triangle_body_id"], dtype=np.int32)
        body_names = [str(value) for value in data["body_names"]]
    figure = go.Figure()
    colors = ("#397FA7", "#E28E2C", "#4E9F78", "#C44E52")
    for body_id, body_name in enumerate(body_names):
        selected = triangles[body_ids == body_id]
        if len(selected) == 0:
            continue
        stride = max(1, int(np.ceil(len(selected) / 30000)))
        shown = selected[::stride]
        figure.add_trace(
            go.Mesh3d(
                x=vertices[:, 0],
                y=vertices[:, 1],
                z=vertices[:, 2],
                i=shown[:, 0],
                j=shown[:, 1],
                k=shown[:, 2],
                name=body_name,
                color=colors[body_id % len(colors)],
                opacity=0.94,
                flatshading=False,
                hovertemplate=(
                    f"{body_name}<br>x=%{{x:.4f}} m<br>y=%{{y:.4f}} m"
                    "<br>z=%{z:.4f} m<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        height=710,
        margin=dict(l=0, r=0, t=45, b=0),
        title="Authoritative reconstructed physical-control CAD bodies",
        scene=dict(
            xaxis_title="x [m]",
            yaxis_title="y [m]",
            zaxis_title="z [m]",
            aspectmode="data",
            camera=dict(eye=dict(x=-1.55, y=-1.8, z=0.85)),
        ),
        paper_bgcolor="white",
        legend=dict(orientation="h"),
    )
    return figure


def _planform_figure(case: BuiltCase, control: ControlSurfaceSpec) -> go.Figure:
    planform = case.planform
    figure = go.Figure()
    for side_index, sign in enumerate((1.0, -1.0)):
        y = sign * np.asarray(planform.front_y_fine)
        le = np.asarray(planform.front_x_fine)
        te = np.asarray(planform.rear_x_fine)
        polygon_x = np.concatenate([le, te[::-1], le[:1]])
        polygon_y = np.concatenate([y, y[::-1], y[:1]])
        figure.add_trace(
            go.Scatter(
                x=polygon_x,
                y=polygon_y,
                fill="toself",
                fillcolor="rgba(46,125,166,.20)",
                line=dict(color="#2E7DA6", width=2),
                name="neutral planform" if side_index == 0 else None,
                showlegend=side_index == 0,
                hoverinfo="skip",
            )
        )
    if control.enabled:
        y0 = control.start_frac * float(planform.semi_span_m)
        y1 = control.end_frac * float(planform.semi_span_m)
        y_control = np.linspace(y0, y1, 101)
        le = np.interp(y_control, planform.front_y_fine, planform.front_x_fine)
        te = np.interp(y_control, planform.front_y_fine, planform.rear_x_fine)
        hinge = le + control.hinge_point * (te - le)
        for side_index, sign in enumerate((1.0, -1.0)):
            polygon_x = np.concatenate([hinge, te[::-1], hinge[:1]])
            polygon_y = np.concatenate(
                [sign * y_control, (sign * y_control)[::-1], sign * y_control[:1]]
            )
            figure.add_trace(
                go.Scatter(
                    x=polygon_x,
                    y=polygon_y,
                    fill="toself",
                    fillcolor="rgba(245,158,11,.48)",
                    line=dict(color="#B45309", width=2, dash="dash"),
                    name=control.name if side_index == 0 else None,
                    showlegend=side_index == 0,
                    hovertemplate=(
                        f"{control.name}<br>hinge={control.hinge_point:.3f}"
                        "<br>x=%{x:.4f} m<br>y=%{y:.4f} m<extra></extra>"
                    ),
                )
            )
    figure.update_layout(
        height=620,
        title="Planform and control footprint",
        xaxis_title="x [m]",
        yaxis_title="y [m]",
        xaxis=dict(scaleanchor="y", scaleratio=1),
        template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return figure


def _airfoil_figure(data: Mapping[str, np.ndarray], selections: Mapping[str, str]) -> go.Figure:
    figure = go.Figure()
    colors = ("#2E7DA6", "#2E8B73", "#B36A28", "#7355A8")
    for station, color in zip(AIRFOIL_STATIONS, colors, strict=True):
        coordinates = data[station]
        figure.add_trace(
            go.Scatter(
                x=coordinates[:, 0],
                y=coordinates[:, 1],
                mode="lines",
                name=f"{station}: {selections[station]}",
                line=dict(color=color, width=2),
            )
        )
    figure.update_layout(
        height=430,
        template="plotly_white",
        title="Selected fixed airfoils",
        xaxis_title="x/c",
        yaxis_title="z/c",
        xaxis=dict(scaleanchor="y", scaleratio=1),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return figure


def _campaign_dirs(root: Path) -> list[Path]:
    manifests = sorted(
        root.glob("artifacts/pygeo_bwb_generator/**/campaign_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [path.parent for path in manifests]


_hero()
cap1, cap2, cap3, cap4 = st.columns(4)
cap1.markdown(
    '<div class="cap"><span class="available">AVAILABLE</span><br>'
    "<b>Neutral pyGeo geometry</b><br>DoE, loft, extraction, metrics, IGES.</div>",
    unsafe_allow_html=True,
)
cap2.markdown(
    '<div class="cap"><span class="available">AVAILABLE</span><br>'
    "<b>Airfoil selection</b><br>Independent b0–b3 database profiles.</div>",
    unsafe_allow_html=True,
)
cap3.markdown(
    '<div class="cap"><span class="available">AVAILABLE</span><br>'
    "<b>Physical controls</b><br>Named split-solid STEP and δe/δa CAD.</div>",
    unsafe_allow_html=True,
)
cap4.markdown(
    '<div class="cap"><span class="missing">SEPARATE STUDY</span><br>'
    "<b>AVL + NeuralFoil</b><br>Validated bridge, not run by this generator.</div>",
    unsafe_allow_html=True,
)


default_config = REPO_ROOT / "standalone" / "pygeo_bwb_generator" / "config.yaml"
with st.sidebar:
    st.markdown("### Configuration")
    config_path_text = st.text_input(
        "Base YAML",
        value=str(default_config),
        help="The GUI starts from this standalone YAML and preserves its Aeris definition link.",
    )
    st.caption(
        "All generated files stay inside the project workspace; no temporary output is used."
    )

try:
    base_config = load_config(config_path_text)
    catalog = airfoil_catalog(base_config.airfoil_database)
    base_control = resolve_control_surface(base_config)
except Exception as exc:
    st.error(f"Could not load the standalone config: {type(exc).__name__}: {exc}")
    st.stop()

with st.sidebar:
    campaign_name = st.text_input("Campaign name", value=base_config.name)
    output_parent = st.text_input(
        "Output parent",
        value=str(base_config.output_root),
        help="GUI preview and campaign folders are timestamped below this directory.",
    )
    st.markdown("### DoE")
    method = st.selectbox(
        "Sampling method",
        ("lhs", "random", "center"),
        index=("lhs", "random", "center").index(base_config.method),
    )
    seed = int(st.number_input("Seed", min_value=0, value=int(base_config.seed), step=1))
    n_samples = int(
        st.number_input(
            "Number of designs",
            min_value=1,
            value=1 if method == "center" else int(base_config.n_samples),
            step=1,
            disabled=method == "center",
        )
    )
    if method == "center":
        n_samples = 1
    st.markdown("### Loft and extraction")
    pygeo_raw = base_config.geometry.get("pygeo", {})
    extraction_raw = base_config.geometry.get("extraction", {})
    sampling_raw = base_config.geometry.get("surface_sampling", {})
    k_span = int(
        st.number_input(
            "pyGeo kSpan",
            min_value=2,
            max_value=4,
            value=int(pygeo_raw.get("k_span", 3)),
            help="2 is piecewise/linear-like; 3 is the recommended smooth baseline.",
        )
    )
    spanwise_sections = int(
        st.number_input(
            "Realised sections",
            min_value=4,
            value=int(extraction_raw.get("spanwise_sections", 25)),
        )
    )
    chordwise_section_points = int(
        st.number_input(
            "Points per extracted section",
            min_value=41,
            value=int(extraction_raw.get("chordwise_points", 241)),
            step=20,
        )
    )
    cst_order = int(
        st.number_input(
            "CST order",
            min_value=3,
            max_value=16,
            value=int(extraction_raw.get("cst_order", 8)),
        )
    )
    surface_chordwise_points = int(
        st.number_input(
            "Surface chordwise points",
            min_value=21,
            value=int(sampling_raw.get("chordwise_points", 141)),
            step=20,
        )
    )
    surface_spanwise_points = int(
        st.number_input(
            "Surface spanwise points",
            min_value=21,
            value=int(sampling_raw.get("spanwise_points", 121)),
            step=20,
        )
    )

tab_generate, tab_visualize, tab_design, tab_inspect, tab_exports = st.tabs(
    [
        "① Generate",
        "② Visualize",
        "③ Design space",
        "④ Inspect & metrics",
        "⑤ Exports & studies",
    ]
)

# Render shared design widgets before consuming their values in Generate.
with tab_design:
    st.subheader("Direct physical design variables")
    st.info(
        "This standalone definition uses c1…c4 and b1…b3 directly. It converts them "
        "to Aeris ratios only at the deterministic BWB-definition boundary."
    )
    st.warning(
        "Root rule: dihedral_b1_deg is locked at 0°. It is the complete "
        "inboard panel, so this prevents mirrored finite-thickness halves from "
        "intersecting. dihedral_b2_deg and dihedral_b3_deg remain DoE variables."
    )
    edited_variables = st.data_editor(
        variable_frame(base_config),
        hide_index=True,
        width="stretch",
        disabled=["group", "variable", "unit", "varied"],
        column_config={
            "minimum": st.column_config.NumberColumn(format="%.6f"),
            "maximum": st.column_config.NumberColumn(format="%.6f"),
            "varied": st.column_config.CheckboxColumn(),
        },
        key="pygeo_variable_editor",
    )

    st.subheader("Fixed airfoils")
    st.caption(
        "The four profiles are fixed across the DoE, but you may choose any .dat profile "
        "from data/airfoil_database for each BWB station group."
    )
    airfoil_names = list(catalog)
    airfoil_selections: dict[str, str] = {}
    columns = st.columns(4)
    for column, station in zip(columns, AIRFOIL_STATIONS, strict=True):
        configured = base_config.fixed_airfoils[station]
        default_index = airfoil_names.index(configured) if configured in airfoil_names else 0
        airfoil_selections[station] = column.selectbox(
            station,
            airfoil_names,
            index=default_index,
            key=f"airfoil_{station}",
        )
    st.plotly_chart(
        _airfoil_figure(
            airfoil_preview_data(catalog, airfoil_selections),
            airfoil_selections,
        ),
        width="stretch",
        key="design_airfoil_preview",
    )

    st.subheader("Control surface definition")
    control_enabled = st.toggle(
        "Enable trailing-edge elevon metadata and preview",
        value=base_control.enabled,
    )
    c1, c2, c3 = st.columns(3)
    control_hinge = float(
        c1.slider(
            "Hinge x/c",
            0.50,
            0.95,
            float(base_control.hinge_point),
            0.01,
        )
    )
    control_start = float(
        c2.slider(
            "Span start η",
            0.0,
            0.95,
            float(base_control.start_frac),
            0.01,
        )
    )
    control_end = float(
        c3.slider(
            "Span end η",
            0.05,
            1.0,
            float(base_control.end_frac),
            0.01,
        )
    )
    c4, c5 = st.columns(2)
    delta_e = float(
        c4.number_input(
            "Symmetric command δe [deg]",
            value=float(base_control.delta_e_sym_deg),
            step=1.0,
        )
    )
    delta_a = float(
        c5.number_input(
            "Differential command δa [deg]",
            value=float(base_control.delta_a_diff_deg),
            step=1.0,
        )
    )
    control_spec = ControlSurfaceSpec(
        enabled=control_enabled,
        name=base_control.name,
        family="trailing_edge",
        hinge_point=control_hinge,
        start_frac=control_start,
        end_frac=control_end,
        symmetric=True,
        deflection_sign="standard",
        delta_e_sym_deg=delta_e,
        delta_a_diff_deg=delta_a,
    )
    if control_start >= control_end:
        st.error("Control span must satisfy start < end.")
    else:
        d1, d2, d3 = st.columns(3)
        d1.metric("Right command", f"{control_spec.right_deflection_deg:+.1f}°")
        d2.metric("Left command", f"{control_spec.left_deflection_deg:+.1f}°")
        d3.metric("Hinge", f"{control_hinge:.2f} x/c")
    st.info(
        "Native pyGeo IGES/Tecplot remain the neutral master OML. Physical CAD writes "
        "a separate fixed-wing/elevon assembly with a 3-D hinge, cove/gap, rigid δe/δa "
        "deflection, per-body exports, and solid/intersection QC."
    )

    physical_raw = (base_config.geometry.get("control_surfaces") or {}).get("physical_cad") or {}
    st.markdown("##### Physical deflected CAD")
    pc1, pc2, pc3, pc4 = st.columns(4)
    physical_cad_enabled = pc1.toggle(
        "Build split-solid CAD",
        value=bool(physical_raw.get("enabled", True)),
    )
    cad_hinge_gap = float(
        pc2.number_input(
            "Hinge gap [fraction c]",
            min_value=0.0,
            max_value=0.15,
            value=float(physical_raw.get("hinge_gap_fraction", 0.005)),
            format="%.5f",
        )
    )
    cad_design_limit = float(
        pc3.number_input(
            "Cove design limit [deg]",
            min_value=0.0,
            max_value=60.0,
            value=float(physical_raw.get("design_deflection_limit_deg", 20.0)),
        )
    )
    cad_chordwise_points = int(
        pc4.number_input(
            "CAD section points",
            min_value=21,
            value=int(physical_raw.get("chordwise_points", 81)),
            step=10,
        )
    )
    with st.expander("Physical CAD tolerances", expanded=False):
        ct1, ct2, ct3, ct4 = st.columns(4)
        cad_boundary_clearance = float(
            ct1.number_input(
                "Span-end clearance fraction",
                min_value=0.0,
                value=float(physical_raw.get("boundary_clearance_fraction", 0.005)),
                format="%.7f",
            )
        )
        cad_te_thickness = float(
            ct2.number_input(
                "Minimum TE thickness [fraction c]",
                min_value=0.0,
                value=float(physical_raw.get("minimum_te_thickness_fraction", 5.0e-4)),
                format="%.6f",
            )
        )
        cad_tessellation = float(
            ct3.number_input(
                "Facet tolerance [m]",
                min_value=1.0e-6,
                value=float(physical_raw.get("tessellation_tolerance_m", 7.5e-4)),
                format="%.7f",
            )
        )
        cad_master_to_cad_limit = float(
            ct4.number_input(
                "Master → CAD max [fraction Cref]",
                min_value=1.0e-5,
                value=float(physical_raw.get("max_master_to_cad_deviation_cref", 0.005)),
                format="%.6f",
            )
        )
    st.warning(
        "The current gap model is a simple clearance cove. Its void is fluid "
        "domain and the design-limit relief makes it wider than the nominal gap. "
        "Use it for CAD/meshing screening; use a sealed morph for broad DoE CFD or "
        "measured hinge/cove dimensions for final gap-resolved CFD."
    )
    st.caption(
        "Physical split CAD is intended for CFD-selected cases. Disable it for a "
        "large geometry/AVL campaign, then enable it when regenerating the selected "
        "multi-fidelity CFD subset."
    )
    st.subheader("Output switches")
    o1, o2, o3, o4 = st.columns(4)
    p1, p2, p3, p4, p5, p6 = st.columns(6)
    output_flags = {
        "write_iges": o1.checkbox("IGES", value=bool(base_config.outputs.get("write_iges", True))),
        "write_tecplot": o2.checkbox(
            "Tecplot", value=bool(base_config.outputs.get("write_tecplot", True))
        ),
        "write_surface_npz": o3.checkbox(
            "Surface NPZ", value=bool(base_config.outputs.get("write_surface_npz", True))
        ),
        "write_section_dat": o4.checkbox(
            "Section DAT", value=bool(base_config.outputs.get("write_section_dat", True))
        ),
        "write_step": p1.checkbox("STEP", value=bool(base_config.outputs.get("write_step", True))),
        "write_brep": p2.checkbox("BREP", value=bool(base_config.outputs.get("write_brep", False))),
        "write_stl": p3.checkbox("STL", value=bool(base_config.outputs.get("write_stl", True))),
        "write_obj": p4.checkbox("OBJ", value=bool(base_config.outputs.get("write_obj", True))),
        "write_vtk": p5.checkbox("VTK", value=bool(base_config.outputs.get("write_vtk", True))),
        "write_cad_npz": p6.checkbox(
            "CAD NPZ", value=bool(base_config.outputs.get("write_cad_npz", True))
        ),
    }
    output_flags["verify_step_import"] = st.checkbox(
        "Re-import STEP with Gmsh and verify the solid count",
        value=bool(base_config.outputs.get("verify_step_import", True)),
        help="Fails a generated case if installed Gmsh cannot recover every named solid.",
    )


try:
    edited_ranges = ranges_from_frame(edited_variables)
    config_payload = build_config_payload(
        base_config,
        name=campaign_name,
        ranges=edited_ranges,
        airfoils=airfoil_selections,
        method=method,
        seed=seed,
        n_samples=n_samples,
        k_span=k_span,
        spanwise_sections=spanwise_sections,
        chordwise_section_points=chordwise_section_points,
        cst_order=cst_order,
        surface_chordwise_points=surface_chordwise_points,
        surface_spanwise_points=surface_spanwise_points,
        control=control_spec,
        output_root=output_parent,
        output_flags=output_flags,
    )
    config_payload["geometry"]["control_surfaces"]["physical_cad"] = {
        "enabled": physical_cad_enabled,
        "topology": "split_elevon",
        "design_deflection_limit_deg": cad_design_limit,
        "hinge_gap_fraction": cad_hinge_gap,
        "boundary_clearance_fraction": cad_boundary_clearance,
        "chordwise_points": cad_chordwise_points,
        "minimum_te_thickness_fraction": cad_te_thickness,
        "tessellation_tolerance_m": cad_tessellation,
        "tessellation_angular_tolerance_rad": float(
            physical_raw.get("tessellation_angular_tolerance_rad", 0.12)
        ),
        "max_master_to_cad_deviation_cref": cad_master_to_cad_limit,
        "fail_on_invalid": bool(physical_raw.get("fail_on_invalid", True)),
    }
    design_error = None
except Exception as exc:
    config_payload = {}
    design_error = f"{type(exc).__name__}: {exc}"

with tab_generate:
    st.subheader("Config-driven generation")
    st.write(
        "The GUI writes an exact standalone YAML snapshot, validates it with the same "
        "backend as the CLI, then builds either one preview case or a timestamped DoE campaign."
    )
    config_save_path = Path(
        st.text_input(
            "Save GUI config as",
            value=str(
                REPO_ROOT
                / "artifacts"
                / "pygeo_bwb_generator"
                / "gui_configs"
                / f"{campaign_name}.yaml"
            ),
        )
    )
    if design_error:
        st.error(design_error)
    else:
        yaml_text = dump_config(config_payload)
        with st.expander("Exact YAML generated by this GUI", expanded=False):
            st.code(yaml_text, language="yaml")
        st.download_button(
            "Download YAML",
            data=yaml_text,
            file_name=f"{campaign_name}.yaml",
            mime="text/yaml",
        )

        c1, c2, c3 = st.columns(3)
        preview_index = int(
            c1.number_input(
                "Preview DoE row",
                min_value=0,
                max_value=max(0, n_samples - 1),
                value=0,
                step=1,
            )
        )
        if c1.button("Validate & save config", width="stretch"):
            try:
                saved = write_config(config_payload, config_save_path)
                validated = load_config(saved)
                st.success(
                    f"Valid: {saved} · {validated.n_samples} design(s) · "
                    f"{len(validated.fixed_airfoils)} fixed airfoils"
                )
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")

        if c2.button("Build preview case", type="primary", width="stretch"):
            try:
                saved = write_config(config_payload, config_save_path)
                validated = load_config(saved)
                doe = create_doe(validated)
                row = doe.iloc[preview_index]
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                preview_root = (
                    Path(output_parent).expanduser().resolve()
                    / "gui_previews"
                    / f"preview_{timestamp}_row{preview_index:04d}"
                )
                with st.spinner("Lofting pyGeo surface and extracting realised sections…"):
                    case = build_case(validated, row)
                    write_case(
                        validated,
                        case,
                        preview_root,
                        disable_cad=False,
                        disable_visualization=False,
                    )
                st.session_state["pygeo_preview_case"] = case
                st.session_state["pygeo_preview_config"] = validated
                st.session_state["pygeo_preview_control"] = resolve_control_surface(validated)
                st.session_state["pygeo_preview_dir"] = str(preview_root)
                st.success(f"Preview complete: {preview_root}")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")

        if c3.button("Run full DoE campaign", width="stretch"):
            try:
                saved = write_config(config_payload, config_save_path)
                validated = load_config(saved)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                campaign_root = (
                    Path(output_parent).expanduser().resolve()
                    / "gui_campaigns"
                    / f"{campaign_name}_{timestamp}"
                )
                with st.spinner(f"Building {n_samples} pyGeo design(s)…"):
                    result_root = run_campaign(
                        validated,
                        n_samples_override=None,
                        output_override=campaign_root,
                        indices=None,
                        dry_run=False,
                        disable_cad=False,
                        disable_visualization=False,
                    )
                st.success(f"Campaign complete: {result_root}")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")

        st.code(
            f".venv/bin/python standalone/pygeo_bwb_generator/generate.py "
            f"--config {config_save_path}",
            language="bash",
        )

with tab_visualize:
    st.subheader("Interactive geometry")
    case = st.session_state.get("pygeo_preview_case")
    preview_control = st.session_state.get("pygeo_preview_control", control_spec)
    if case is None:
        st.info("Build a preview case in ① Generate. The selected airfoils are shown below.")
        st.plotly_chart(
            _airfoil_figure(
                airfoil_preview_data(catalog, airfoil_selections),
                airfoil_selections,
            ),
            width="stretch",
            key="visual_airfoil_preview",
        )
    else:
        preview_dir = Path(st.session_state["pygeo_preview_dir"])
        physical_mesh = preview_dir / "mesh_handoff" / "deflected_split_surface_m.npz"
        if physical_mesh.is_file():
            st.success("Physical split-solid CAD passed backend QC and is shown below.")
            st.plotly_chart(
                _physical_cad_figure(physical_mesh),
                width="stretch",
                key="visual_physical_cad",
            )
        else:
            st.warning("No physical CAD mesh is available for this preview case.")
        show_deflection = st.toggle(
            "Show sampled-surface kinematic diagnostic",
            value=bool(
                preview_control.enabled
                and (
                    abs(preview_control.right_deflection_deg) > 1.0e-12
                    or abs(preview_control.left_deflection_deg) > 1.0e-12
                )
            ),
        )
        if show_deflection:
            st.info(
                "Secondary diagnostic: the sampled pyGeo grid is rotated section-by-section. "
                "Use the split-solid view above as the authoritative physical CAD result."
            )
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Right δ", f"{preview_control.right_deflection_deg:+.1f}°")
        v2.metric("Left δ", f"{preview_control.left_deflection_deg:+.1f}°")
        v3.metric("Hinge", f"{preview_control.hinge_point:.2f} x/c")
        v4.metric(
            "Control area",
            f"{float(case.metrics.get('control_surface_area_xy_m2', 0.0)):.4f} m²",
        )
        st.plotly_chart(
            _surface_figure(
                case,
                preview_control,
                show_deflection=show_deflection,
            ),
            width="stretch",
            key="visual_surface",
        )
        st.plotly_chart(
            _planform_figure(case, preview_control),
            width="stretch",
            key="visual_planform",
        )

with tab_inspect:
    st.subheader("Preview metrics")
    case = st.session_state.get("pygeo_preview_case")
    if case is not None:
        m = case.metrics
        columns = st.columns(6)
        columns[0].metric("Sref", f"{float(m['s_ref_xy_m2']):.4f} m²")
        columns[1].metric("Span", f"{float(m['b_ref_y_m']):.4f} m")
        columns[2].metric("MAC / Cref", f"{float(m['c_ref_m']):.4f} m")
        columns[3].metric("Aspect ratio", f"{float(m['aspect_ratio_xy']):.3f}")
        columns[4].metric("Volume", f"{float(m['volume_m3']):.4f} m³")
        columns[5].metric("Wetted area", f"{float(m['wetted_area_m2']):.4f} m²")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Geometry QC", str(m["geometry_qc"]))
        q2.metric("Planarity", str(m["section_planarity"]))
        q3.metric("Worst warp", f"{100 * float(m['max_plane_warp_chord']):.3f}% c")
        q4.metric("Worst CST RMS", f"{100 * float(m['max_cst_rms_chord']):.3f}% c")
        st.dataframe(metric_rows(case), width="stretch", hide_index=True)
        if "physical_cad_accepted" in m:
            st.markdown("##### Physical control CAD")
            p1, p2, p3, p4, p5, p6 = st.columns(6)
            p1.metric(
                "CAD QC",
                "PASS" if bool(m["physical_cad_accepted"]) else "FAIL",
            )
            step_solids = m.get("physical_cad_step_import_volume_count", "—")
            p2.metric(
                "Bodies / STEP solids",
                f"{int(m['physical_cad_body_count'])} / {step_solids}",
            )
            p3.metric(
                "Right clearance",
                f"{1e3 * float(m['physical_cad_right_clearance_m']):.3f} mm",
            )
            p4.metric(
                "Left clearance",
                f"{1e3 * float(m['physical_cad_left_clearance_m']):.3f} mm",
            )
            p5.metric(
                "Right Δz",
                f"{1e3 * float(m['physical_cad_right_center_delta_z_m']):+.3f} mm",
            )
            p6.metric(
                "Left Δz",
                f"{1e3 * float(m['physical_cad_left_center_delta_z_m']):+.3f} mm",
            )
            if m.get("physical_cad_master_to_cad_rms_m") is not None:
                st.caption(
                    "Native pyGeo → neutral CAD: "
                    f"RMS {1e3 * float(m['physical_cad_master_to_cad_rms_m']):.3f} mm · "
                    f"max {1e3 * float(m['physical_cad_master_to_cad_max_m']):.3f} mm"
                )
            if m.get("physical_cad_effective_cove_width_fraction") is not None:
                gap_width_pct = 100.0 * float(m["physical_cad_effective_cove_width_fraction"])
                nominal_gap_pct = 100.0 * float(m["physical_cad_nominal_hinge_gap_fraction"])
                root_status = "PASS" if bool(m["physical_cad_root_symmetry_ok"]) else "FAIL"
                root_overlap = float(m["physical_cad_root_intersection_m3"])
                st.warning(
                    "Simple clearance cove: "
                    f"realised chordwise opening {gap_width_pct:.3f}% c "
                    f"(nominal gap {nominal_gap_pct:.3f}% c). "
                    "Treat its drag as a sensitivity, not aircraft truth."
                )
                st.caption(f"Root symmetry QC: {root_status} · intersection {root_overlap:.3e} m³")
        preview_dir = Path(st.session_state["pygeo_preview_dir"])
        st.caption(f"Preview directory: `{preview_dir}`")
        st.dataframe(
            case_artifact_rows(preview_dir),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Build a preview in ① Generate to inspect realised metrics.")

    st.subheader("Existing campaigns")
    campaigns = _campaign_dirs(REPO_ROOT)
    if campaigns:
        selected_campaign = st.selectbox(
            "Campaign",
            campaigns,
            format_func=lambda path: str(path.relative_to(REPO_ROOT)),
        )
        manifest = _read_json(selected_campaign / "campaign_manifest.json")
        s1, s2, s3 = st.columns(3)
        s1.metric("Status", manifest.get("status", "—"))
        s2.metric("Successful", manifest.get("n_successful", "—"))
        s3.metric("Failed", manifest.get("n_failed", "—"))
        metrics_path = selected_campaign / "geometry_metrics.csv"
        if metrics_path.is_file():
            st.dataframe(pd.read_csv(metrics_path), width="stretch")
    else:
        st.caption("No campaign manifests found yet.")

with tab_exports:
    st.subheader("Export capability matrix")
    st.caption(
        "“All possible formats” is not a finite or useful promise. This table states exactly "
        "what the standalone generator writes now and which geometry each artifact represents."
    )
    st.dataframe(
        export_capability_frame(),
        width="stretch",
        hide_index=True,
    )

    preview_dir_text = st.session_state.get("pygeo_preview_dir")
    if preview_dir_text:
        preview_dir = Path(preview_dir_text)
        rows = case_artifact_rows(preview_dir)
        if not rows.empty:
            st.subheader("Download a preview artifact")
            relative = st.selectbox("Artifact", rows["artifact"].tolist())
            artifact = preview_dir / relative
            st.download_button(
                "Download selected artifact",
                data=artifact.read_bytes(),
                file_name=artifact.name,
                mime="application/octet-stream",
            )

    st.subheader("What the previous studies established")
    study_run = latest_study_run(REPO_ROOT)
    study_summary = load_study_summary(study_run)
    if study_run is None:
        st.info("No completed pyGeo/AVL study was found under artifacts/pygeo_avl_study.")
    else:
        st.caption(f"Latest complete evidence: `{study_run.relative_to(REPO_ROOT)}`")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Wide-bound DoE", f"{study_summary.get('doe_samples', '—')} cases")
        a2.metric("DoE failures", study_summary.get("doe_failures", "—"))
        geometry_rows = study_summary.get("geometry", [])
        baseline = next(
            (row for row in geometry_rows if row.get("geometry") == "pyGeo kSpan=3"),
            {},
        )
        a3.metric(
            "kSpan=3 surface RMS",
            (
                f"{float(baseline['surface_rms_mm']):.3f} mm"
                if "surface_rms_mm" in baseline
                else "—"
            ),
        )
        a4.metric(
            "kSpan=3 area shift",
            (f"{float(baseline['area_delta_pct']):+.3f}%" if "area_delta_pct" in baseline else "—"),
        )
        st.markdown(
            """
The studies had five separate purposes:

1. **Standalone feasibility:** prove pyGeo can loft and export the BWB without
   constructing an AeroSandbox geometry.
2. **Loft comparison:** compare identical authored stations visually and with
   bidirectional surface distances, area, span, MAC, and aspect ratio.
3. **Realised-section bridge:** extract the actual smooth loft, planarise it,
   fit CST, and evaluate section quality.
4. **AVL + NeuralFoil feasibility:** inject section CD–CL data and independently
   integrate profile drag, while retaining AVL induced drag.
5. **Robustness/convergence:** vary kSpan, CST order, section count, frames, and
   a wide 24-case DoE to determine defensible default settings.

The final recommendation was **pyGeo as master 3-D geometry, with AeroSandbox
kept complementarily as the maintained AVL serializer/NeuralFoil interface**.
The study did not validate authoritative physical control-surface CAD.
"""
        )
        report = study_run / "REPORT.md"
        st.download_button(
            "Download full study report",
            data=report.read_text(encoding="utf-8"),
            file_name=f"{study_run.name}_REPORT.md",
            mime="text/markdown",
        )

with st.expander("Current capability boundary", expanded=False):
    st.markdown(
        """
- The BWB planform/section mathematics are the same deterministic Aeris
  definition; pyGeo owns the loft.
- Four independently selectable database airfoils remain fixed during a DoE.
- Native pyGeo IGES/Tecplot remain the neutral master OML. Reconstructed neutral
  and physical deflected OCC solids are separate, explicitly labelled artifacts.
- Physical controls use named fixed/elevon bodies, a straight 3-D rigid hinge,
  cove/gap clearance, symmetric/differential mixing, and solid/intersection QC.
- STL/OBJ/VTK/NPZ exports are diagnostic tessellations, not solver-quality meshes.
- Neutral geometry can use a pyGeo-to-structured-surface adapter and pyHyp for
  ADflow. Split/gapped deflections go through STEP and a CAD-aware mesher first.
- AVL/NeuralFoil remains a separate solver module consuming these sections.
"""
    )
