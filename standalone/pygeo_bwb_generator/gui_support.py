"""Pure helpers for the standalone pyGeo BWB Streamlit interface."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from standalone.pygeo_avl_study.geometry_bridge import read_airfoil_coordinates
from standalone.pygeo_bwb_generator.generate import (
    AIRFOIL_STATIONS,
    DIRECT_VARIABLES,
    BuiltCase,
    ControlSurfaceSpec,
    GeneratorConfig,
    Range,
)

VARIABLE_GROUPS = {
    "c1_m": "Chord",
    "c2_m": "Chord",
    "c3_m": "Chord",
    "c4_m": "Chord",
    "b1_m": "Span",
    "b2_m": "Span",
    "b3_m": "Span",
    "sw1_deg": "Sweep",
    "sw2_deg": "Sweep",
    "sw3_deg": "Sweep",
    "twist_b0_deg": "Twist",
    "twist_b1_deg": "Twist",
    "twist_b2_deg": "Twist",
    "twist_b3_deg": "Twist",
    "dihedral_b1_deg": "Root invariant",
    "dihedral_b2_deg": "Dihedral",
    "dihedral_b3_deg": "Dihedral",
}

VARIABLE_UNITS = {
    **{name: "m" for name in ("c1_m", "c2_m", "c3_m", "c4_m", "b1_m", "b2_m", "b3_m")},
    **{name: "deg" for name in DIRECT_VARIABLES if name.startswith(("sw", "twist", "dihedral"))},
}


@dataclass(frozen=True)
class ExportCapability:
    format: str
    status: str
    geometry: str
    purpose: str
    caveat: str


EXPORT_CAPABILITIES = (
    ExportCapability(
        "IGES (.igs)",
        "available",
        "native neutral pyGeo B-spline surfaces",
        "CAD/outer-mould-line handoff",
        "Surface model; not a verified watertight solid.",
    ),
    ExportCapability(
        "Tecplot (.dat)",
        "available",
        "native neutral pyGeo surfaces and control data",
        "surface inspection and MDOLab workflows",
        "Not an airfoil Selig DAT and not an AVL file.",
    ),
    ExportCapability(
        "NumPy (.npz)",
        "available",
        "sampled upper/lower neutral surfaces",
        "numerical processing and mesh bridging",
        "Resolution is controlled by surface_sampling.",
    ),
    ExportCapability(
        "Selig sections (.dat)",
        "available",
        "realised, planarised fixed-span sections",
        "CST, NeuralFoil, XFoil, and audit work",
        "These are extracted from the loft, not authored input profiles.",
    ),
    ExportCapability(
        "CSV / JSON / YAML",
        "available",
        "DoE, stations, sections, metrics, manifests, config snapshot",
        "traceability and ML dataset assembly",
        "Metadata only; no surface topology.",
    ),
    ExportCapability(
        "PNG",
        "available",
        "3-D loft, planform, sections, DoE and metric plots",
        "reports and rapid QC",
        "Static visualization.",
    ),
    ExportCapability(
        "STEP (.step)",
        "available",
        "neutral solid, neutral split assembly, and named deflected assembly",
        "CAD-aware meshing and solid exchange",
        "Section-reconstructed OCC solid; optional Gmsh re-import verifies the named solid count.",
    ),
    ExportCapability(
        "BREP (.brep)",
        "optional",
        "per-body native OpenCascade topology",
        "loss-minimized OCC debugging and handoff",
        "Enable outputs.write_brep; coordinates remain in metres.",
    ),
    ExportCapability(
        "STL / OBJ / VTK / NPZ",
        "available",
        "named tessellation of the exact exported physical bodies",
        "interactive inspection and mesher handoff diagnostics",
        "Coordinates are metres; these facets are not a quality-gated CFD mesh.",
    ),
    ExportCapability(
        "Physical deflected CAD",
        "available",
        "fixed wing plus separate rigid elevon on each side",
        "symmetric/differential CFD geometry",
        "Straight 3-D hinge axis, cove/gap model, solid/intersection QC, and traceable commands.",
    ),
    ExportCapability(
        "OpenVSP / CFD volume mesh",
        "separate downstream stage",
        "STEP assembly is the geometry handoff",
        "Gmsh/SU2 now; dedicated pyHyp/overset topology later",
        "The existing neutral structured pyHyp mesh is not reusable for split/gapped deflection.",
    ),
)


def airfoil_catalog(database: Path) -> dict[str, Path]:
    """Return unique, selectable two-column airfoils from a database tree."""

    result: dict[str, Path] = {}
    for path in sorted(Path(database).rglob("*")):
        if path.is_file() and path.suffix.lower() == ".dat":
            result.setdefault(path.stem, path.resolve())
    if not result:
        raise FileNotFoundError(f"No .dat airfoils found under {database}")
    return result


def variable_frame(config: GeneratorConfig) -> pd.DataFrame:
    """Build the editable direct-physical-variable table used by the GUI."""

    return pd.DataFrame(
        [
            {
                "group": VARIABLE_GROUPS[name],
                "variable": name,
                "minimum": config.ranges[name].minimum,
                "maximum": config.ranges[name].maximum,
                "unit": VARIABLE_UNITS[name],
                "varied": config.ranges[name].varied,
            }
            for name in DIRECT_VARIABLES
        ]
    )


def ranges_from_frame(frame: pd.DataFrame) -> dict[str, Range]:
    """Convert the GUI editor result back to validated Range objects."""

    rows = {str(row["variable"]): row for _, row in frame.iterrows()}
    missing = [name for name in DIRECT_VARIABLES if name not in rows]
    if missing:
        raise ValueError(f"Design-variable editor is missing {missing}")
    result: dict[str, Range] = {}
    for name in DIRECT_VARIABLES:
        minimum = float(rows[name]["minimum"])
        maximum = float(rows[name]["maximum"])
        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise ValueError(f"{name} bounds must be finite")
        if maximum < minimum:
            raise ValueError(f"{name}: maximum must be >= minimum")
        if name == "dihedral_b1_deg" and (abs(minimum) > 1.0e-12 or abs(maximum) > 1.0e-12):
            raise ValueError("dihedral_b1_deg is locked at 0 degrees for root symmetry")
        result[name] = Range(minimum=minimum, maximum=maximum)
    return result


def build_config_payload(
    base: GeneratorConfig,
    *,
    name: str,
    ranges: Mapping[str, Range],
    airfoils: Mapping[str, str],
    method: str,
    seed: int,
    n_samples: int,
    k_span: int,
    spanwise_sections: int,
    chordwise_section_points: int,
    cst_order: int,
    surface_chordwise_points: int,
    surface_spanwise_points: int,
    control: ControlSurfaceSpec,
    output_root: str,
    output_flags: Mapping[str, bool],
) -> dict[str, Any]:
    """Create a complete YAML payload while preserving Aeris-definition data."""

    raw = copy.deepcopy(base.raw)
    raw["name"] = str(name).strip()
    raw["fixed_airfoils"] = {key: str(airfoils[key]) for key in AIRFOIL_STATIONS}
    raw["doe"] = {
        "method": str(method),
        "seed": int(seed),
        "n_samples": int(n_samples),
        "variables": {
            variable: {
                "min": float(ranges[variable].minimum),
                "max": float(ranges[variable].maximum),
            }
            for variable in DIRECT_VARIABLES
        },
    }
    geometry = raw.setdefault("geometry", {})
    pygeo = geometry.setdefault("pygeo", {})
    pygeo["k_span"] = int(k_span)
    extraction = geometry.setdefault("extraction", {})
    extraction.update(
        {
            "spanwise_sections": int(spanwise_sections),
            "chordwise_points": int(chordwise_section_points),
            "cst_order": int(cst_order),
        }
    )
    sampling = geometry.setdefault("surface_sampling", {})
    sampling.update(
        {
            "chordwise_points": int(surface_chordwise_points),
            "spanwise_points": int(surface_spanwise_points),
        }
    )
    geometry["control_surfaces"] = {
        "enabled": bool(control.enabled),
        "surfaces": (
            [
                {
                    "name": control.name,
                    "family": control.family,
                    "hinge_point": float(control.hinge_point),
                    "symmetric": bool(control.symmetric),
                    "spanwise": {
                        "start_frac": float(control.start_frac),
                        "end_frac": float(control.end_frac),
                    },
                    "deflection_sign": control.deflection_sign,
                }
            ]
            if control.enabled
            else []
        ),
        "commands": {
            "delta_e_sym_deg": float(control.delta_e_sym_deg),
            "delta_a_diff_deg": float(control.delta_a_diff_deg),
        },
        "physical_cad": copy.deepcopy(
            (base.geometry.get("control_surfaces") or {}).get("physical_cad", {})
        ),
    }
    outputs = raw.setdefault("outputs", {})
    outputs["root"] = str(output_root)
    for key, value in output_flags.items():
        outputs[str(key)] = bool(value)
    return raw


def dump_config(payload: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(payload), sort_keys=False, width=100)


def write_config(payload: Mapping[str, Any], path: Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_config(payload), encoding="utf-8")
    return target


def _unit(vector: np.ndarray) -> np.ndarray:
    magnitude = float(np.linalg.norm(vector))
    if magnitude <= 1.0e-12:
        raise ValueError("Cannot normalize a degenerate vector")
    return vector / magnitude


def _rotate_points(
    points: np.ndarray,
    origin: np.ndarray,
    axis: np.ndarray,
    angle_deg: float,
) -> np.ndarray:
    """Rodrigues rotation about a local hinge tangent."""

    angle = math.radians(float(angle_deg))
    vector = points - origin
    direction = _unit(axis)
    return (
        origin
        + vector * math.cos(angle)
        + np.cross(direction, vector) * math.sin(angle)
        + np.outer(vector @ direction, direction) * (1.0 - math.cos(angle))
    )


def deflect_surface_pair(
    upper: np.ndarray,
    lower: np.ndarray,
    spec: ControlSurfaceSpec,
    deflection_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply a kinematic trailing-edge rotation to sampled half-wing grids.

    Positive deflection is trailing-edge down. This is intentionally a visual
    sampled-surface transformation; it is not used for IGES/Tecplot export.
    """

    upper_out = np.asarray(upper, dtype=float).copy()
    lower_out = np.asarray(lower, dtype=float).copy()
    if not spec.enabled or abs(float(deflection_deg)) <= 1.0e-12:
        return upper_out, lower_out
    if upper_out.shape != lower_out.shape or upper_out.ndim != 3:
        raise ValueError("upper/lower surfaces must be equal (n_chord, n_span, 3) grids")

    endpoint_0 = 0.5 * (upper_out[0] + lower_out[0])
    endpoint_1 = 0.5 * (upper_out[-1] + lower_out[-1])
    first_is_le = endpoint_0[:, 0] <= endpoint_1[:, 0]
    le = np.where(first_is_le[:, None], endpoint_0, endpoint_1)
    te = np.where(first_is_le[:, None], endpoint_1, endpoint_0)
    hinge = le + spec.hinge_point * (te - le)
    span_coordinate = hinge[:, 1]
    denominator = max(float(span_coordinate[-1] - span_coordinate[0]), 1.0e-12)
    span_fraction = (span_coordinate - span_coordinate[0]) / denominator

    for j in range(upper_out.shape[1]):
        if not spec.start_frac <= span_fraction[j] <= spec.end_frac:
            continue
        before = max(0, j - 1)
        after = min(upper_out.shape[1] - 1, j + 1)
        tangent = _unit(hinge[after] - hinge[before])
        if tangent[1] < 0.0:
            tangent = -tangent
        chord_vector = te[j] - le[j]
        chord_squared = float(chord_vector @ chord_vector)
        for surface in (upper_out, lower_out):
            chord_fraction = ((surface[:, j] - le[j]) @ chord_vector) / chord_squared
            mask = chord_fraction >= spec.hinge_point
            surface[mask, j] = _rotate_points(
                surface[mask, j],
                hinge[j],
                tangent,
                float(deflection_deg),
            )
    return upper_out, lower_out


def display_surfaces(
    case: BuiltCase,
    spec: ControlSurfaceSpec,
    *,
    show_deflection: bool,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return right/left upper/lower surfaces for interactive visualization."""

    if show_deflection:
        right = deflect_surface_pair(
            case.upper_surface,
            case.lower_surface,
            spec,
            spec.right_deflection_deg,
        )
        left_positive = deflect_surface_pair(
            case.upper_surface,
            case.lower_surface,
            spec,
            spec.left_deflection_deg,
        )
    else:
        right = (case.upper_surface.copy(), case.lower_surface.copy())
        left_positive = (case.upper_surface.copy(), case.lower_surface.copy())
    left = tuple(surface * np.array([1.0, -1.0, 1.0]) for surface in left_positive)
    return {"right": right, "left": left}  # type: ignore[return-value]


def export_capability_frame() -> pd.DataFrame:
    return pd.DataFrame([capability.__dict__ for capability in EXPORT_CAPABILITIES])


def latest_study_run(root: Path) -> Path | None:
    candidates = [
        path.parent
        for path in Path(root).glob("artifacts/pygeo_avl_study/*/REPORT.md")
        if (path.parent / "summary.json").is_file()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def load_study_summary(run_dir: Path | None) -> dict[str, Any]:
    if run_dir is None:
        return {}
    path = Path(run_dir) / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def airfoil_preview_data(
    catalog: Mapping[str, Path],
    selections: Mapping[str, str],
) -> dict[str, np.ndarray]:
    return {
        station: read_airfoil_coordinates(catalog[selections[station]])
        for station in AIRFOIL_STATIONS
    }


def metric_rows(case: BuiltCase) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "metric": name,
                "value": f"{value:.10g}" if isinstance(value, float) else str(value),
                "type": type(value).__name__,
            }
            for name, value in case.metrics.items()
        ]
    )


def case_artifact_rows(case_dir: Path) -> pd.DataFrame:
    root = Path(case_dir)
    if not root.is_dir():
        return pd.DataFrame(columns=["artifact", "size_kib"])
    return pd.DataFrame(
        [
            {
                "artifact": str(path.relative_to(root)),
                "size_kib": round(path.stat().st_size / 1024.0, 2),
            }
            for path in sorted(root.rglob("*"))
            if path.is_file()
        ]
    )
