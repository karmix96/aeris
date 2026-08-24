"""Interactive flat-tip cap4 structured surface mesh tuner.

Launch from the repository root with:

    .venv/bin/python -m streamlit run standalone/structured_mesh_comparison/mesh_tuning_gui.py

or:

    aeris gui mesh-tuner
"""

# ruff: noqa: E402,I001
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aeris.mesh.pyhyp_runner import GRID_LEVELS, subprocess_run_pyhyp  # noqa: E402
from aeris.mesh.surface import MeshBuildError, export_surface_mesh  # noqa: E402
from standalone.structured_mesh_comparison.baseline_structured_compare import (  # noqa: E402
    _build_baseline_geometry,
    _common,
)


BASELINE_CONFIG = ROOT / "configs" / "cfd" / "pygeo_surface_mesh_study.yaml"
OUT_ROOT = ROOT / "data" / "meshes" / "gui_structured_mesh_tuner"
RUNS_DIR = OUT_ROOT / "runs"
GEOMETRY_DIR = OUT_ROOT / "_geometry"

BLOCK_COLORS = (
    "#2563eb",
    "#059669",
    "#dc2626",
    "#9333ea",
    "#d97706",
    "#0891b2",
    "#be123c",
    "#4f46e5",
)


@dataclass(frozen=True)
class MeshParams:
    tip_topology: str
    cap_wrap_x: float
    cap_wrap_points: int
    points_per_block_side: int
    spanwise_panels_per_section: int
    tip_radial_points: int
    tip_smooth_iters: int
    chordwise_distribution: str
    chordwise_beta: float
    spanwise_allocation: str
    spanwise_distribution: str
    spanwise_beta: float
    dense_airfoil_points_per_surface: int
    te_thickness: float
    minimum_te_thickness: float
    minimum_shape_metric: float

    def build_kwargs(self) -> dict[str, Any]:
        common = _common()
        common.update(
            {
                "oml_topology": "cap4",
                "tip_topology": self.tip_topology,
                "tip_dome_scale": 0.0,
                "tip_conformal_ring": False,
                "points_per_block_side": int(self.points_per_block_side),
                "spanwise_panels_per_section": int(self.spanwise_panels_per_section),
                "spanwise_allocation": self.spanwise_allocation,
                "cap_wrap_x": float(self.cap_wrap_x),
                "cap_width_frac": 0.50,
                "cap_wrap_points": int(self.cap_wrap_points),
                "tip_radial_points": int(self.tip_radial_points),
                "tip_smooth_iters": int(self.tip_smooth_iters),
                "chordwise_distribution": self.chordwise_distribution,
                "chordwise_beta": float(self.chordwise_beta),
                "spanwise_distribution": self.spanwise_distribution,
                "spanwise_beta": float(self.spanwise_beta),
                "dense_airfoil_points_per_surface": int(
                    self.dense_airfoil_points_per_surface
                ),
                "te_thickness": float(self.te_thickness),
                "minimum_te_thickness": float(self.minimum_te_thickness),
                "minimum_shape_metric": float(self.minimum_shape_metric),
            }
        )
        return common


def _round_token(value: float, scale: int) -> str:
    return str(int(round(value * scale))).zfill(4)


def _case_name(params: MeshParams) -> str:
    chord = params.chordwise_distribution[:3]
    span = params.spanwise_allocation[:4]
    return (
        f"{params.tip_topology[:5]}"
        f"_x{_round_token(params.cap_wrap_x, 1000)}"
        f"_p{params.points_per_block_side}"
        f"_w{params.cap_wrap_points}"
        f"_s{params.spanwise_panels_per_section}"
        f"_t{params.tip_radial_points}"
        f"_sm{params.tip_smooth_iters}"
        f"_{chord}_{span}"
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@st.cache_resource(show_spinner="Building baseline wing geometry...")
def _baseline_geometry() -> dict[str, Any]:
    return _build_baseline_geometry(BASELINE_CONFIG, GEOMETRY_DIR)


def _strict_pass(report: dict[str, Any]) -> bool:
    global_metrics = report.get("global") or {}
    free_edges = report.get("free_edges") or {}
    min_jac = global_metrics.get("min_scaled_jacobian")
    min_align = global_metrics.get("min_triangle_normal_alignment")
    alignment_floor = global_metrics.get("alignment_floor", -0.25)
    return bool(
        report.get("accepted_pre_pyhyp")
        and free_edges.get("closed_except_root")
        and min_jac is not None
        and float(min_jac) > 0.0
        and min_align is not None
        and float(min_align) > float(alignment_floor)
    )


def _surface_summary(report: dict[str, Any], error: str | None) -> dict[str, Any]:
    global_metrics = report.get("global") or {}
    free_edges = report.get("free_edges") or {}
    artifacts = report.get("artifacts") or {}
    vtk_path = ((artifacts.get("vtk") or {}).get("path")) if artifacts else None
    npz_path = ((artifacts.get("npz") or {}).get("path")) if artifacts else None
    failure_reasons = report.get("failure_reasons") or []
    checks = [
        str(reason.get("check", "unknown"))
        + (f" in {reason.get('block')}" if reason.get("block") else "")
        for reason in failure_reasons
    ]
    return {
        "aeris_pre_pyhyp_pass": bool(report.get("accepted_pre_pyhyp")),
        "strict_surface_pass": _strict_pass(report),
        "closed_except_root": free_edges.get("closed_except_root"),
        "off_root_free_edges": free_edges.get("off_root_free_edges"),
        "block_count": report.get("block_count"),
        "cells": global_metrics.get("total_cells"),
        "min_scaled_jacobian": global_metrics.get("min_scaled_jacobian"),
        "min_shape_metric": global_metrics.get("min_shape_metric"),
        "min_triangle_normal_alignment": global_metrics.get("min_triangle_normal_alignment"),
        "max_equiangle_skewness": global_metrics.get("max_equiangle_skewness"),
        "max_aspect_ratio": global_metrics.get("max_aspect_ratio"),
        "max_growth_ratio": global_metrics.get("max_growth_ratio"),
        "max_adjacent_normal_angle_deg": global_metrics.get(
            "max_adjacent_normal_angle_deg"
        ),
        "failure_checks": "; ".join(checks),
        "error": error,
        "vtk": vtk_path,
        "npz": npz_path,
    }


def _fallback_report(path: Path, error: str | None) -> dict[str, Any]:
    report = _read_json(path)
    if report is not None:
        return report
    return {
        "accepted_pre_pyhyp": False,
        "global": {},
        "free_edges": {},
        "failure_reasons": [],
        "error": error,
    }


def _build_or_load_mesh(
    params: MeshParams, *, force_rebuild: bool
) -> tuple[dict[str, Any], dict[str, Any], Path, bool]:
    case_dir = RUNS_DIR / _case_name(params)
    surface_dir = case_dir / "surface"
    report_path = surface_dir / "surface_report.json"
    manifest_path = case_dir / "run_manifest.json"

    if report_path.exists() and manifest_path.exists() and not force_rebuild:
        report = _fallback_report(report_path, None)
        manifest = _read_json(manifest_path) or {}
        manifest["loaded_from_cache"] = True
        return report, manifest, surface_dir, True

    geometry = _baseline_geometry()
    source = geometry["asb_wing"]
    build_kwargs = params.build_kwargs()
    t0 = time.perf_counter()
    error: str | None = None
    try:
        report = export_surface_mesh(source, surface_dir, **build_kwargs)
        status = "ok"
    except MeshBuildError as exc:
        error = f"{type(exc).__name__}: {exc}"
        report = _fallback_report(report_path, error)
        status = "failed_qc"
    except Exception as exc:  # noqa: BLE001 - the GUI should report every failure.
        error = f"{type(exc).__name__}: {exc}"
        report = _fallback_report(report_path, error)
        status = "failed"

    elapsed = time.perf_counter() - t0
    summary = _surface_summary(report, error)
    manifest = {
        "schema": "aeris.mesh_tuning_gui.run.v1",
        "case": _case_name(params),
        "status": status,
        "elapsed_seconds": elapsed,
        "flat_tip_policy": {
            "tip_topology": params.tip_topology,
            "tip_dome_scale": 0.0,
            "tip_conformal_ring": False,
        },
        "params": asdict(params),
        "build_kwargs": build_kwargs,
        "summary": summary,
        "surface_dir": str(surface_dir),
        "loaded_from_cache": False,
    }
    _write_json(manifest_path, manifest)
    return report, manifest, surface_dir, False


def _metric_text(value: Any, precision: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(fval) >= 1000:
        return f"{fval:,.0f}"
    if 0 < abs(fval) < 1.0e-3:
        return f"{fval:.3e}"
    return f"{fval:.{precision}f}"


def _status_badge(summary: dict[str, Any]) -> None:
    if summary["strict_surface_pass"]:
        st.success("Strict surface PASS")
    elif summary["aeris_pre_pyhyp_pass"]:
        st.warning("Aeris QC PASS, strict signed-Jacobian check FAIL")
    else:
        st.error("Surface QC FAIL")


def _append_curve(
    xs: list[float | None],
    ys: list[float | None],
    zs: list[float | None],
    curve: np.ndarray,
) -> None:
    xs.extend(curve[:, 0].tolist())
    ys.extend(curve[:, 1].tolist())
    zs.extend(curve[:, 2].tolist())
    xs.append(None)
    ys.append(None)
    zs.append(None)


def _mesh_figure(npz_path: Path, line_budget: int) -> go.Figure:
    blocks = np.load(npz_path)
    fig = go.Figure()
    for idx, name in enumerate(blocks.files):
        xyz = np.asarray(blocks[name])
        if xyz.ndim != 3 or xyz.shape[-1] != 3:
            continue
        ni, nj, _ = xyz.shape
        step_i = max(1, math.ceil(ni / line_budget))
        step_j = max(1, math.ceil(nj / line_budget))
        i_indices = list(range(0, ni, step_i))
        j_indices = list(range(0, nj, step_j))
        if i_indices[-1] != ni - 1:
            i_indices.append(ni - 1)
        if j_indices[-1] != nj - 1:
            j_indices.append(nj - 1)

        xs: list[float | None] = []
        ys: list[float | None] = []
        zs: list[float | None] = []

        for i in i_indices:
            _append_curve(xs, ys, zs, xyz[i, :, :])
        for j in j_indices:
            _append_curve(xs, ys, zs, xyz[:, j, :])

        fig.add_trace(
            go.Scatter3d(
                x=xs,
                y=ys,
                z=zs,
                mode="lines",
                name=name,
                line={"color": BLOCK_COLORS[idx % len(BLOCK_COLORS)], "width": 2},
                hoverinfo="name",
            )
        )

    fig.update_layout(
        height=650,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        legend={"orientation": "h", "y": 0.01, "x": 0.01},
        scene={
            "aspectmode": "data",
            "xaxis": {"title": "x"},
            "yaxis": {"title": "y"},
            "zaxis": {"title": "z"},
        },
    )
    return fig


def _history_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not RUNS_DIR.exists():
        return rows
    for manifest_path in sorted(
        RUNS_DIR.glob("*/run_manifest.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        manifest = _read_json(manifest_path)
        if not manifest:
            continue
        params = manifest.get("params") or {}
        summary = manifest.get("summary") or {}
        rows.append(
            {
                "case": manifest.get("case"),
                "strict": summary.get("strict_surface_pass"),
                "aeris": summary.get("aeris_pre_pyhyp_pass"),
                "x": params.get("cap_wrap_x"),
                "p": params.get("points_per_block_side"),
                "wrap": params.get("cap_wrap_points"),
                "span": params.get("spanwise_panels_per_section"),
                "tip": params.get("tip_radial_points"),
                "cells": summary.get("cells"),
                "min jac": summary.get("min_scaled_jacobian"),
                "shape": summary.get("min_shape_metric"),
                "skew": summary.get("max_equiangle_skewness"),
                "AR": summary.get("max_aspect_ratio"),
                "growth": summary.get("max_growth_ratio"),
                "vtk": summary.get("vtk"),
            }
        )
    return rows


def _open_in_paraview(path: Path) -> str | None:
    exe = shutil.which("paraview")
    if exe is None:
        return "ParaView is not on PATH."
    try:
        subprocess.Popen(
            [exe, str(path)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # pragma: no cover - desktop environment dependent.
        return f"Could not launch ParaView: {exc}"
    return None


def _controls() -> tuple[MeshParams, bool, bool, int]:
    with st.sidebar:
        st.header("Mesh Parameters")
        auto_build = st.checkbox("Live rebuild", value=True)
        force_rebuild = st.button("Rebuild current case")

        st.divider()
        tip_topology = st.selectbox(
            "tip_topology", ["airfoil_face", "cgrid_face", "single", "ring"], index=0
        )
        cap_wrap_x = st.number_input(
            "cap_wrap_x",
            min_value=0.005,
            max_value=0.600,
            value=0.015,
            step=0.005,
            format="%.3f",
        )
        cap_wrap_points = st.slider("cap_wrap_points", 5, 41, 17, step=2)
        points_per_block_side = st.slider("points_per_block_side", 25, 257, 49, step=2)
        spanwise_panels_per_section = st.slider(
            "spanwise_panels_per_section", 1, 32, 4, step=1
        )
        tip_radial_points = st.slider("tip_radial_points", 3, 25, 3, step=2)
        tip_smooth_iters = st.slider("tip_smooth_iters", 0, 120, 0, step=5)

        st.divider()
        chordwise_distribution = st.selectbox(
            "chordwise_distribution", ["uniform", "cosine"], index=0
        )
        chordwise_beta = st.number_input(
            "chordwise_beta", min_value=0.5, max_value=8.0, value=2.0, step=0.25
        )
        spanwise_allocation = st.selectbox(
            "spanwise_allocation", ["uniform", "proportional"], index=0
        )
        spanwise_distribution = st.selectbox(
            "spanwise_distribution", ["uniform", "cosine"], index=0
        )
        spanwise_beta = st.number_input(
            "spanwise_beta", min_value=0.5, max_value=8.0, value=2.0, step=0.25
        )

        with st.expander("Advanced"):
            dense_airfoil_points_per_surface = st.slider(
                "dense_airfoil_points_per_surface", 101, 801, 301, step=50
            )
            te_thickness = st.number_input(
                "te_thickness", min_value=0.0, max_value=0.050, value=0.005, step=0.001
            )
            minimum_te_thickness = st.number_input(
                "minimum_te_thickness",
                min_value=0.0,
                max_value=0.020,
                value=0.002,
                step=0.0005,
                format="%.4f",
            )
            minimum_shape_metric = st.number_input(
                "minimum_shape_metric",
                min_value=0.0,
                max_value=1.0e-2,
                value=1.0e-6,
                step=1.0e-6,
                format="%.1e",
            )
            line_budget = st.slider("preview line density", 12, 80, 44, step=4)

        params = MeshParams(
            tip_topology=str(tip_topology),
            cap_wrap_x=float(cap_wrap_x),
            cap_wrap_points=int(cap_wrap_points),
            points_per_block_side=int(points_per_block_side),
            spanwise_panels_per_section=int(spanwise_panels_per_section),
            tip_radial_points=int(tip_radial_points),
            tip_smooth_iters=int(tip_smooth_iters),
            chordwise_distribution=str(chordwise_distribution),
            chordwise_beta=float(chordwise_beta),
            spanwise_allocation=str(spanwise_allocation),
            spanwise_distribution=str(spanwise_distribution),
            spanwise_beta=float(spanwise_beta),
            dense_airfoil_points_per_surface=int(dense_airfoil_points_per_surface),
            te_thickness=float(te_thickness),
            minimum_te_thickness=float(minimum_te_thickness),
            minimum_shape_metric=float(minimum_shape_metric),
        )
        return params, bool(auto_build), bool(force_rebuild), int(line_budget)


def _show_metrics(summary: dict[str, Any], manifest: dict[str, Any]) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cells", _metric_text(summary["cells"]))
    c2.metric("Min signed Jacobian", _metric_text(summary["min_scaled_jacobian"], 6))
    c3.metric("Max skewness", _metric_text(summary["max_equiangle_skewness"], 6))
    c4.metric("Max aspect ratio", _metric_text(summary["max_aspect_ratio"], 3))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Min shape", _metric_text(summary["min_shape_metric"], 6))
    c2.metric("Normal alignment", _metric_text(summary["min_triangle_normal_alignment"], 6))
    c3.metric("Growth ratio", _metric_text(summary["max_growth_ratio"], 3))
    c4.metric("Build time", f"{float(manifest.get('elapsed_seconds') or 0.0):.2f}s")

    rows = [
        {"check": "Aeris pre-pyHyp QC", "value": summary["aeris_pre_pyhyp_pass"]},
        {"check": "Strict surface gate", "value": summary["strict_surface_pass"]},
        {"check": "Closed except symmetry root", "value": summary["closed_except_root"]},
        {"check": "Off-root free edges", "value": summary["off_root_free_edges"]},
        {"check": "Failure checks", "value": summary["failure_checks"] or "-"},
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)



def _volume_summary(report: dict[str, Any], error: str | None) -> dict[str, Any]:
    march = report.get("march_metrics") or {}
    audit = report.get("volume_audit") or {}
    return {
        "status": report.get("status") or ("failed" if error else "unknown"),
        "output_cgns": report.get("output_cgns"),
        "error": error or report.get("error"),
        "N": report.get("N"),
        "coarsen": report.get("coarsen"),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "passed": march.get("passed"),
        "min_quality": march.get("min_quality"),
        "min_volume": march.get("min_volume"),
        "first_invalid_layer": march.get("first_invalid_layer"),
        "low_quality_layers": march.get("low_quality_layers"),
        "audit_classification": audit.get("classification"),
        "inverted_cells": audit.get("inverted_cells"),
        "inverted_fraction": audit.get("inverted_fraction"),
    }


def _run_pyhyp_volume(
    surface_dir: Path,
    *,
    level: str,
    n_grid: int | None,
    n_coarsen: int | None,
    force_rebuild: bool,
) -> dict[str, Any]:
    report_path = surface_dir / "volume_report.json"
    if report_path.exists() and not force_rebuild:
        report = _read_json(report_path) or {}
        return _volume_summary(report, None)

    error: str | None = None
    try:
        report = subprocess_run_pyhyp(
            surface_dir,
            level=level,
            n_grid=n_grid,
            n_coarsen=n_coarsen,
            c_max=0.5,
            vol_smooth_iter=1200,
            n_constant_start=3,
            march_dist_factor=25.0,
        )
    except Exception as exc:  # noqa: BLE001 - failed marching is a useful result.
        error = f"{type(exc).__name__}: {exc}"
        report = _read_json(report_path) or {"status": "failed", "error": error}
    return _volume_summary(report, error)


def _show_volume_controls(summary: dict[str, Any], surface_dir: Path) -> None:
    if not summary.get("aeris_pre_pyhyp_pass"):
        st.warning("Surface must pass Aeris pre-pyHyp QC before volume marching.")
        return

    key_prefix = surface_dir.parent.name
    level_names = list(GRID_LEVELS)
    level_index = level_names.index("smoke") if "smoke" in level_names else 0
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        level = st.selectbox("level", level_names, index=level_index, key=f"{key_prefix}_vol_level")
    with c2:
        n_grid_value = st.number_input(
            "N override",
            min_value=0,
            max_value=401,
            value=0,
            step=2,
            key=f"{key_prefix}_vol_n_grid",
        )
    with c3:
        n_coarsen_value = st.number_input(
            "coarsen override",
            min_value=0,
            max_value=8,
            value=1,
            step=1,
            key=f"{key_prefix}_vol_coarsen",
        )
    with c4:
        force_volume = st.checkbox("rerun volume", value=False, key=f"{key_prefix}_vol_force")

    if st.button("Run pyHyp volume", key=f"{key_prefix}_vol_run"):
        with st.spinner("Running pyHyp volume march..."):
            volume_summary = _run_pyhyp_volume(
                surface_dir,
                level=str(level),
                n_grid=None if int(n_grid_value) == 0 else int(n_grid_value),
                n_coarsen=None if int(n_coarsen_value) == 0 else int(n_coarsen_value),
                force_rebuild=bool(force_volume),
            )
        _write_json(surface_dir.parent / "volume_summary_last.json", volume_summary)

    volume_summary = _read_json(surface_dir.parent / "volume_summary_last.json")
    if volume_summary is None and (surface_dir / "volume_report.json").exists():
        volume_summary = _volume_summary(_read_json(surface_dir / "volume_report.json") or {}, None)
    if volume_summary is None:
        st.caption("No volume canary run for this surface yet.")
        return

    if volume_summary.get("status") == "valid" or volume_summary.get("passed") is True:
        st.success("pyHyp volume PASS")
    else:
        st.error("pyHyp volume FAIL")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("N", _metric_text(volume_summary.get("N")))
    c2.metric("coarsen", _metric_text(volume_summary.get("coarsen")))
    c3.metric("min quality", _metric_text(volume_summary.get("min_quality"), 6))
    c4.metric("min volume", _metric_text(volume_summary.get("min_volume"), 6))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("first invalid layer", _metric_text(volume_summary.get("first_invalid_layer")))
    c2.metric("inverted cells", _metric_text(volume_summary.get("inverted_cells")))
    c3.metric("inverted fraction", _metric_text(volume_summary.get("inverted_fraction"), 6))
    c4.metric("march time", _metric_text(volume_summary.get("elapsed_seconds"), 2))

    output = volume_summary.get("output_cgns")
    if output:
        cgns_path = Path(str(output))
        st.code(f"paraview {cgns_path}", language="bash")
        if cgns_path.exists() and st.button("Open CGNS in ParaView", key=f"{key_prefix}_vol_pv"):
            err = _open_in_paraview(cgns_path)
            if err:
                st.warning(err)
            else:
                st.success("ParaView launched")
    if volume_summary.get("error"):
        st.code(str(volume_summary["error"]), language="text")


def _show_block_table(report: dict[str, Any]) -> None:
    blocks = report.get("blocks") or []
    if not blocks:
        return
    rows: list[dict[str, Any]] = []
    for block in blocks:
        rows.append(
            {
                "block": block.get("name"),
                "ni": block.get("ni"),
                "nj": block.get("nj"),
                "cells": block.get("cells"),
                "min area": block.get("min_area"),
                "median area": block.get("median_area"),
                "min shape": block.get("min_shape_metric"),
                "max skew": block.get("max_equiangle_skewness"),
                "AR": block.get("max_aspect_ratio"),
                "growth": block.get("max_growth_ratio"),
                "normal angle": block.get("max_adjacent_normal_angle_deg"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(
        page_title="Aeris Structured Mesh Tuner",
        page_icon=None,
        layout="wide",
    )
    st.title("Aeris Structured Mesh Tuner")
    st.caption("Baseline BWB, cap4 OML, flat full-airfoil tip cap.")

    params, auto_build, force_rebuild, line_budget = _controls()
    case_name = _case_name(params)

    top_left, top_right = st.columns([2, 1])
    with top_left:
        st.subheader(case_name)
    with top_right:
        st.write("Output")
        st.code(str(RUNS_DIR / case_name / "surface"), language="text")

    if not auto_build and not force_rebuild:
        st.info("Live rebuild is off. Press Rebuild current case to generate this parameter set.")
    else:
        with st.spinner("Building surface mesh..."):
            report, manifest, surface_dir, cached = _build_or_load_mesh(
                params, force_rebuild=force_rebuild
            )
        summary = manifest.get("summary") or _surface_summary(report, manifest.get("error"))

        _status_badge(summary)
        if summary.get("error"):
            st.code(str(summary["error"]), language="text")
        if cached:
            st.caption("Loaded existing artifacts for this parameter set.")

        left, right = st.columns([3, 2])
        with left:
            npz_value = summary.get("npz")
            if npz_value and Path(npz_value).is_file():
                st.plotly_chart(
                    _mesh_figure(Path(npz_value), line_budget),
                    use_container_width=True,
                    config={"displaylogo": False},
                )
            else:
                st.warning("No surface_blocks.npz available for preview.")
        with right:
            _show_metrics(summary, manifest)
            vtk_value = summary.get("vtk")
            if vtk_value:
                vtk_path = Path(vtk_value)
                st.code(f"paraview {vtk_path}", language="bash")
                if st.button("Open VTK in ParaView"):
                    err = _open_in_paraview(vtk_path)
                    if err:
                        st.warning(err)
                    else:
                        st.success("ParaView launched")

        with st.expander("pyHyp volume canary", expanded=False):
            _show_volume_controls(summary, surface_dir)

        with st.expander("Block metrics", expanded=False):
            _show_block_table(report)

    st.subheader("Recent Candidates")
    history = _history_rows()
    if history:
        st.dataframe(history[:80], use_container_width=True, hide_index=True)
    else:
        st.info("No candidates written yet.")


if __name__ == "__main__":
    main()
