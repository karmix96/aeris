"""Independent OpenAeroStruct aerodynamic comparison and load extraction.

OpenAeroStruct's VLM is used to check global lift behavior and to provide a
spanwise load *shape*.  It is deliberately not treated as validation of local
CalculiX shell stress: OAS's structural model is a reduced-order beam.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import os
from pathlib import Path

import numpy as np

from aeris.common.config import file_sha256
from aeris.fea.case.spec import OpenAeroStructValidationSpec


class OpenAeroStructError(RuntimeError):
    """OpenAeroStruct comparison cannot be completed without ambiguity."""


def build_oas_mesh(stations_payload: dict[str, object], chordwise_nodes: int) -> np.ndarray:
    """Build a tip-first OAS mesh directly from canonical AERIS stations."""
    stations = stations_payload["stations"]
    assert isinstance(stations, list)
    xis = np.linspace(0.0, 1.0, chordwise_nodes)
    mesh = np.zeros((chordwise_nodes, len(stations), 3))
    for j, raw in enumerate(reversed(stations)):
        assert isinstance(raw, dict)
        theta = math.radians(float(raw["twist_deg"]))
        chord = float(raw["chord_m"])
        # AERIS convention: positive twist is nose-up, hence the TE moves down.
        mesh[:, j, 0] = float(raw["x_le_m"]) + xis * chord * math.cos(theta)
        mesh[:, j, 1] = float(raw["y_m"])
        mesh[:, j, 2] = float(raw["z_le_m"]) - xis * chord * math.sin(theta)
    if abs(float(mesh[0, -1, 1])) > 1e-12:
        raise OpenAeroStructError("OAS symmetry mesh root is not at y=0")
    if not np.all(np.diff(mesh[0, :, 1]) < 0.0):
        raise OpenAeroStructError("OAS mesh must be strictly tip-to-root")
    if np.any(np.linalg.norm(mesh[-1] - mesh[0], axis=1) <= 0.0):
        raise OpenAeroStructError("OAS mesh contains a non-positive chord")
    return mesh


def _run_oas_point(
    mesh: np.ndarray, mission: dict[str, object], alpha_deg: float
) -> dict[str, object]:
    os.environ.setdefault("OPENMDAO_REPORTS", "0")
    try:
        import openmdao.api as om
        from openaerostruct.aerodynamics.aero_groups import AeroPoint
        from openaerostruct.geometry.geometry_group import Geometry
    except ImportError as exc:  # pragma: no cover - exercised by CLI environments
        raise OpenAeroStructError(
            "OpenAeroStruct validation requires the open-source 'fea-validation' extra: "
            "pip install -e '.[fea-validation]'"
        ) from exc

    flow = mission["flow"]
    assert isinstance(flow, dict)
    surface = {
        "name": "bwb",
        "symmetry": True,
        "S_ref_type": "projected",
        "mesh": mesh,
        "CL0": 0.0,
        "CD0": 0.0,
        "k_lam": 0.05,
        "t_over_c_cp": np.array([0.12]),
        "c_max_t": 0.30,
        "with_viscous": False,
        "with_wave": False,
    }
    problem = om.Problem(reports=False)
    variables = om.IndepVarComp()
    variables.add_output("v", val=float(flow["speed_mps"]), units="m/s")
    variables.add_output("alpha", val=alpha_deg, units="deg")
    variables.add_output("Mach_number", val=float(flow["mach"]))
    variables.add_output(
        "re",
        val=float(flow["reynolds"]) / float(flow["reference_chord_m"]),
        units="1/m",
    )
    variables.add_output("rho", val=float(flow["density_kg_m3"]), units="kg/m**3")
    variables.add_output("cg", val=np.array([0.4, 0.0, 0.0]), units="m")
    problem.model.add_subsystem("mission", variables, promotes=["*"])
    problem.model.add_subsystem("bwb", Geometry(surface=surface))
    problem.model.add_subsystem(
        "aero",
        AeroPoint(surfaces=[surface]),
        promotes_inputs=["v", "alpha", "Mach_number", "re", "rho", "cg"],
    )
    problem.model.connect("bwb.mesh", "aero.bwb.def_mesh")
    problem.model.connect("bwb.mesh", "aero.aero_states.bwb_def_mesh")
    problem.model.connect("bwb.t_over_c", "aero.bwb_perf.t_over_c")
    problem.setup(check=False)
    problem.run_model()
    section_forces = np.asarray(problem.get_val("aero.aero_states.bwb_sec_forces"))
    spanwise_forces = np.sum(section_forces, axis=0)
    span_y = np.asarray(mesh[0, :, 1])
    panel_y = 0.5 * (span_y[:-1] + span_y[1:])
    result = {
        "alpha_deg": alpha_deg,
        "cl": float(problem.get_val("aero.CL").item()),
        "cd_inviscid": float(problem.get_val("aero.CD").item()),
        "cm": np.asarray(problem.get_val("aero.CM")).reshape(-1).tolist(),
        "reference_area_full_m2": float(problem.get_val("aero.bwb_perf.S_ref").item()),
        "panel_y_m_tip_to_root": panel_y.tolist(),
        "span_y_nodes_m_tip_to_root": span_y.tolist(),
        "spanwise_force_xyz_n_tip_to_root": spanwise_forces.tolist(),
        "half_model_force_xyz_n": np.sum(spanwise_forces, axis=0).tolist(),
    }
    problem.cleanup()
    return result


def _selected_cfd_rows(
    dataset_path: Path,
    validation: OpenAeroStructValidationSpec,
    mission: dict[str, object],
    stations: dict[str, object],
) -> list[dict[str, object]]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise OpenAeroStructError("CFD validation dataset must be a JSON row list")
    state = mission["state"]
    flow = mission["flow"]
    assert isinstance(state, dict) and isinstance(flow, dict)
    wanted_alphas = {float(value) for value in state["alpha_deg"]}  # type: ignore[index]
    candidates = [
        row
        for row in raw
        if isinstance(row, dict)
        and row.get("geometry_set") == validation.geometry_set
        and row.get("geometry_index") == validation.geometry_index
        and row.get("grid_level") == validation.grid_level
        and row.get("gate_verdict") == "ACCEPTED"
        and float(row.get("alpha_deg", math.nan)) in wanted_alphas
    ]
    selected: dict[float, dict[str, object]] = {}
    for row in candidates:
        alpha = float(row["alpha_deg"])
        previous = selected.get(alpha)
        if previous is None or bool(row.get("solver_is_governed_configuration")):
            selected[alpha] = row
    missing = sorted(wanted_alphas - set(selected))
    if missing:
        raise OpenAeroStructError(f"CFD dataset is missing accepted comparison alphas: {missing}")
    for alpha, row in selected.items():
        for field, expected in (
            ("mach", flow["mach"]),
            ("reynolds", flow["reynolds"]),
            ("temperature_K", flow["temperature_K"]),
        ):
            if not math.isclose(float(row[field]), float(expected), rel_tol=1e-10, abs_tol=1e-10):
                raise OpenAeroStructError(
                    f"CFD row alpha={alpha:g} {field}={row[field]} conflicts "
                    f"with mission {expected}"
                )
        if row.get("design_vector") != stations.get("design_vector"):
            raise OpenAeroStructError(
                f"CFD row alpha={alpha:g} design vector does not match the structural geometry"
            )
    return [selected[alpha] for alpha in sorted(selected)]


def run_oas_validation(
    stations: dict[str, object],
    mission: dict[str, object],
    validation: OpenAeroStructValidationSpec,
    output_path: Path,
) -> dict[str, object]:
    if validation.cfd_dataset is None:
        raise OpenAeroStructError("OpenAeroStruct comparison has no CFD dataset")
    dataset_path = validation.cfd_dataset.expanduser().resolve()
    if not dataset_path.is_file():
        raise OpenAeroStructError(f"CFD validation dataset not found: {dataset_path}")
    if stations.get("design_set") != validation.geometry_set or stations.get(
        "design_index"
    ) != validation.geometry_index:
        raise OpenAeroStructError("station artifact identity does not match validation geometry")

    rows = _selected_cfd_rows(dataset_path, validation, mission, stations)
    mesh = build_oas_mesh(stations, validation.chordwise_nodes)
    cases = [_run_oas_point(mesh, mission, float(row["alpha_deg"])) for row in rows]
    comparisons = []
    for case, row in zip(cases, rows, strict=True):
        error = float(case["cl"]) - float(row["CL"])
        area_target = 2.0 * float(row["area_ref"])
        area_error = abs(float(case["reference_area_full_m2"]) - area_target) / area_target
        comparisons.append(
            {
                "alpha_deg": case["alpha_deg"],
                "oas_cl": case["cl"],
                "cfd_cl": row["CL"],
                "cl_error": error,
                "oas_cd_inviscid_information_only": case["cd_inviscid"],
                "cfd_cd_rans_information_only": row["CD"],
                "reference_area_relative_error": area_error,
            }
        )
    alpha = np.asarray([float(item["alpha_deg"]) for item in comparisons])
    oas_cl = np.asarray([float(item["oas_cl"]) for item in comparisons])
    cfd_cl = np.asarray([float(item["cfd_cl"]) for item in comparisons])
    oas_slope = float(np.polyfit(alpha, oas_cl, 1)[0])
    cfd_slope = float(np.polyfit(alpha, cfd_cl, 1)[0])
    slope_error = abs(oas_slope - cfd_slope) / abs(cfd_slope)
    checks = {
        "geometry_identity": True,
        "mission_identity": True,
        "reference_area": max(
            float(item["reference_area_relative_error"]) for item in comparisons
        )
        <= validation.max_reference_area_relative_error,
        "cl_absolute_error": max(abs(float(item["cl_error"])) for item in comparisons)
        <= validation.max_abs_cl_error,
        "lift_curve_slope": slope_error
        <= validation.max_lift_curve_slope_relative_error,
    }
    payload = {
        "schema": "aeris.fea.openaerostruct_validation.v1",
        "status": "pass" if all(checks.values()) else "fail",
        "scope": {
            "validated": [
                "canonical geometry bridge",
                "global CL",
                "lift-curve slope",
                "load shape",
            ],
            "not_validated": [
                "viscous drag",
                "local shell stress",
                "buckling",
                "composite failure",
            ],
        },
        "solver": {
            "name": "OpenAeroStruct",
            "version": importlib.metadata.version("openaerostruct"),
            "model": "inviscid VLM; rigid geometry",
        },
        "mission": mission,
        "geometry": {
            "design_set": stations.get("design_set"),
            "design_index": stations.get("design_index"),
            "design_matrix_sha256": stations.get("design_matrix_sha256"),
            "chordwise_nodes": validation.chordwise_nodes,
            "spanwise_nodes": int(mesh.shape[1]),
        },
        "cfd_dataset": {"path": str(dataset_path), "sha256": file_sha256(dataset_path)},
        "tolerances": {
            "max_abs_cl_error": validation.max_abs_cl_error,
            "max_lift_curve_slope_relative_error": validation.max_lift_curve_slope_relative_error,
            "max_reference_area_relative_error": validation.max_reference_area_relative_error,
        },
        "checks": checks,
        "comparisons": comparisons,
        "lift_curve": {
            "oas_dcl_dalpha_per_deg": oas_slope,
            "cfd_dcl_dalpha_per_deg": cfd_slope,
            "relative_error": slope_error,
        },
        "cases": cases,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_oas_case(validation_path: Path, alpha_deg: float) -> dict[str, object]:
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    matches = [
        case
        for case in payload.get("cases", [])
        if math.isclose(float(case["alpha_deg"]), alpha_deg, abs_tol=1e-12)
    ]
    if len(matches) != 1:
        raise OpenAeroStructError(
            f"OpenAeroStruct report contains {len(matches)} cases at alpha={alpha_deg:g}"
        )
    return matches[0]
