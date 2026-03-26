from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import aerosandbox as asb
import numpy as np

from aeris.aero.models import AeroGeometryView

RECONSTRUCTION_FORMAT_VERSION = "openvsp_sections_xfoil_v1"

# Reconstruction contract note:
# This module currently reconstructs AeroSandbox geometry from the specific
# generator artifact layout:
#   airfoils/openvsp_sections.csv
#   airfoils/xfoil/*.dat
#
# Changing the generator export format requires updating this reconstruction
# logic as well. This is intentional for now, but it is a versioned contract,
# not magic.


def _airplane_has_any_control_surface(airplane: Any) -> bool:
    for wing in getattr(airplane, "wings", []) or []:
        for xsec in getattr(wing, "xsecs", []) or []:
            control_surfaces = getattr(xsec, "control_surfaces", None)
            if control_surfaces and len(control_surfaces) > 0:
                return True
    return False


def _collect_control_surface_names_from_airplane(airplane: Any) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    for wing in getattr(airplane, "wings", []) or []:
        for xsec in getattr(wing, "xsecs", []) or []:
            for cs in getattr(xsec, "control_surfaces", []) or []:
                name = str(getattr(cs, "name", "")).strip()
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)

    return names


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}, got {type(data).__name__}.")
    return data


def _find_geometry_summary_paths(case_dir: Path) -> list[Path]:
    case_dir = Path(case_dir).resolve()
    candidates = [
        case_dir / "geometry_summary.json",
        case_dir / "artifacts" / "geometry_summary.json",
        case_dir.parent / "geometry_summary.json",
        case_dir.parent / "artifacts" / "geometry_summary.json",
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _load_geometry_summary_for_case_dir(case_dir: Path) -> dict[str, Any] | None:
    for candidate in _find_geometry_summary_paths(case_dir):
        data = _load_json_if_exists(candidate)
        if data is not None:
            return data
    return None


def _extract_control_surface_summary_from_summary(
    summary: dict[str, Any] | None,
) -> tuple[bool, tuple[str, ...], dict[str, Any] | None]:
    if not summary:
        return False, (), None

    cs_summary = summary.get("control_surface_summary", {})
    if not isinstance(cs_summary, dict):
        return False, (), None

    configured = cs_summary.get("configured", {})
    applied = cs_summary.get("applied", {})

    if not isinstance(configured, dict):
        configured = {}
    if not isinstance(applied, dict):
        applied = {}

    names_raw = configured.get("names", [])
    if not isinstance(names_raw, list):
        names_raw = []

    names = tuple(str(name).strip() for name in names_raw if str(name).strip())
    has_control_surfaces = bool(applied.get("has_control_surfaces", False))

    return has_control_surfaces, names, cs_summary


def _normalized_semispan_fractions_from_airplane(airplane: asb.Airplane) -> np.ndarray:
    if not getattr(airplane, "wings", None):
        raise RuntimeError("Cannot compute span fractions: airplane has no wings.")
    wing = airplane.wings[0]
    y_stations = np.array([float(xsec.xyz_le[1]) for xsec in wing.xsecs], dtype=float)
    if len(y_stations) == 0:
        raise RuntimeError("Cannot compute span fractions for airplane with no xsecs.")

    y_abs = np.abs(y_stations)
    y_max = float(np.max(y_abs))
    if y_max <= 0.0:
        return np.zeros_like(y_abs)
    return y_abs / y_max


def _xsec_is_in_control_region(
    frac: float,
    *,
    start_frac: float,
    end_frac: float,
    is_last_xsec: bool,
) -> bool:
    # Match the generator adapter logic:
    # apply to section starts, but do not tag the final xsec.
    if is_last_xsec:
        return False
    return start_frac <= frac <= end_frac


def _control_surface_from_definition(defn: dict[str, Any]) -> asb.ControlSurface:
    family = str(defn.get("family", "")).strip()
    if family != "trailing_edge":
        raise ValueError(
            f"Unsupported reconstructed control-surface family {family!r}. "
            "Only 'trailing_edge' is supported in v1."
        )

    return asb.ControlSurface(
        name=str(defn["name"]),
        trailing_edge=True,
        hinge_point=float(defn["hinge_point"]),
        deflection=0.0,
        symmetric=bool(defn.get("symmetric", True)),
    )


def _apply_control_surfaces_from_summary(
    airplane: asb.Airplane,
    cs_summary: dict[str, Any] | None,
) -> tuple[bool, tuple[str, ...]]:
    """
    Reattach control surfaces to a reconstructed airplane using geometry summary
    definitions. This is required because the reconstruction contract
    (openvsp_sections.csv + xfoil/*.dat) carries geometry shape but not control
    objects.
    """
    if not cs_summary:
        return False, ()

    configured = cs_summary.get("configured", {}) or {}
    enabled = bool(configured.get("enabled", False))
    definitions = configured.get("definitions", []) or []

    if not enabled or not definitions:
        return False, ()

    if not getattr(airplane, "wings", None):
        raise RuntimeError("Cannot apply reconstructed control surfaces: airplane has no wings.")

    wing = airplane.wings[0]
    span_fracs = _normalized_semispan_fractions_from_airplane(airplane)
    n = len(wing.xsecs)

    applied_any = False
    names: list[str] = []
    seen_names: set[str] = set()

    for defn in definitions:
        name = str(defn.get("name", "")).strip()
        if name and name not in seen_names:
            seen_names.add(name)
            names.append(name)

        start_frac = float(defn["start_frac"])
        end_frac = float(defn["end_frac"])

        for i, xsec in enumerate(wing.xsecs):
            frac = float(span_fracs[i])
            if _xsec_is_in_control_region(
                frac,
                start_frac=start_frac,
                end_frac=end_frac,
                is_last_xsec=(i == n - 1),
            ):
                existing = list(getattr(xsec, "control_surfaces", []) or [])
                existing.append(_control_surface_from_definition(defn))
                xsec.control_surfaces = existing
                applied_any = True

    return applied_any, tuple(names)


def geometry_view_from_case(
    *,
    case: Any,
    generator_id: str,
    case_dir: Path | None = None,
    source_policy: str = "native",
) -> AeroGeometryView:
    source_policy = source_policy.strip().lower()

    if source_policy == "native":
        airplane = _extract_native_airplane(case)
        if airplane is None:
            raise RuntimeError("Native airplane object not found on geometry case.")

        _validate_airplane_for_aero(airplane, context="native_geometry_case")

        metadata: dict[str, Any] = {
            "source_policy": "native",
            "case_dir": None if case_dir is None else str(Path(case_dir).resolve()),
        }

        asb_result = getattr(case, "aerosandbox_result", None)
        if asb_result is not None:
            raw_meta = getattr(asb_result, "metadata", None)
            if isinstance(raw_meta, dict):
                metadata.update(raw_meta)

        has_control_surfaces = _airplane_has_any_control_surface(airplane)
        control_surface_names = tuple(_collect_control_surface_names_from_airplane(airplane))

        metadata["has_control_surfaces"] = has_control_surfaces
        metadata["control_surface_names"] = list(control_surface_names)

        return AeroGeometryView(
            view_id="aerosandbox_airplane_native_v1",
            airplane=airplane,
            source_generator=generator_id,
            source_geometry_id=None if case_dir is None else Path(case_dir).name,
            metadata=metadata,
            has_control_surfaces=has_control_surfaces,
            control_surface_names=control_surface_names,
        )

    if source_policy == "reconstruct":
        if case_dir is None:
            raise RuntimeError("Reconstruction requires a case_dir.")

        case_dir = Path(case_dir).resolve()
        airplane = reconstruct_airplane_from_case_dir(case_dir=case_dir)
        summary = _load_geometry_summary_for_case_dir(case_dir)
        has_control_surfaces, control_surface_names, cs_summary = (
            _extract_control_surface_summary_from_summary(summary)
        )

        if cs_summary is not None:
            applied_any, reconstructed_names = _apply_control_surfaces_from_summary(
                airplane,
                cs_summary,
            )
            if applied_any:
                has_control_surfaces = True
                if reconstructed_names:
                    control_surface_names = reconstructed_names

        _validate_airplane_for_aero(airplane, context=f"reconstructed:{case_dir}")

        airplane_has_controls = _airplane_has_any_control_surface(airplane)
        if airplane_has_controls and not has_control_surfaces:
            has_control_surfaces = True
        if airplane_has_controls and not control_surface_names:
            control_surface_names = tuple(_collect_control_surface_names_from_airplane(airplane))

        metadata: dict[str, Any] = {
            "source_policy": "reconstruct",
            "case_dir": str(case_dir),
            "reconstruction_format_version": RECONSTRUCTION_FORMAT_VERSION,
            "has_control_surfaces": has_control_surfaces,
            "control_surface_names": list(control_surface_names),
        }
        if cs_summary is not None:
            metadata["control_surface_summary"] = cs_summary

        return AeroGeometryView(
            view_id="aerosandbox_airplane_reconstructed_v1",
            airplane=airplane,
            source_generator=generator_id,
            source_geometry_id=case_dir.name,
            metadata=metadata,
            has_control_surfaces=has_control_surfaces,
            control_surface_names=control_surface_names,
        )

    raise ValueError(f"Unknown source_policy '{source_policy}'.")


def geometry_view_from_run_dir(
    *,
    run_dir: Path,
    generator_id: str = "bwb_segmented_v1",
) -> AeroGeometryView:
    run_dir = Path(run_dir).resolve()
    case_dir = resolve_run_geometry_dir(run_dir)
    airplane = reconstruct_airplane_from_case_dir(case_dir=case_dir)
    summary = _load_geometry_summary_for_case_dir(case_dir)
    has_control_surfaces, control_surface_names, cs_summary = (
        _extract_control_surface_summary_from_summary(summary)
    )

    if cs_summary is not None:
        applied_any, reconstructed_names = _apply_control_surfaces_from_summary(
            airplane,
            cs_summary,
        )
        if applied_any:
            has_control_surfaces = True
            if reconstructed_names:
                control_surface_names = reconstructed_names

    _validate_airplane_for_aero(airplane, context=f"run_dir:{run_dir}")

    airplane_has_controls = _airplane_has_any_control_surface(airplane)
    if airplane_has_controls and not has_control_surfaces:
        has_control_surfaces = True
    if airplane_has_controls and not control_surface_names:
        control_surface_names = tuple(_collect_control_surface_names_from_airplane(airplane))

    metadata: dict[str, Any] = {
        "source_policy": "reconstruct",
        "run_dir": str(run_dir),
        "case_dir": str(case_dir),
        "reconstruction_format_version": RECONSTRUCTION_FORMAT_VERSION,
        "has_control_surfaces": has_control_surfaces,
        "control_surface_names": list(control_surface_names),
    }
    if cs_summary is not None:
        metadata["control_surface_summary"] = cs_summary

    return AeroGeometryView(
        view_id="aerosandbox_airplane_reconstructed_v1",
        airplane=airplane,
        source_generator=generator_id,
        source_geometry_id=case_dir.name,
        metadata=metadata,
        has_control_surfaces=has_control_surfaces,
        control_surface_names=control_surface_names,
    )


def geometry_view_from_dataset_case(
    *,
    dataset_root: Path,
    geometry_id: str,
    generator_id: str = "bwb_segmented_v1",
) -> AeroGeometryView:
    dataset_root = Path(dataset_root).resolve()
    case_dir = resolve_dataset_geometry_dir(dataset_root, geometry_id)
    airplane = reconstruct_airplane_from_case_dir(case_dir=case_dir)
    summary = _load_geometry_summary_for_case_dir(case_dir)
    has_control_surfaces, control_surface_names, cs_summary = (
        _extract_control_surface_summary_from_summary(summary)
    )

    if cs_summary is not None:
        applied_any, reconstructed_names = _apply_control_surfaces_from_summary(
            airplane,
            cs_summary,
        )
        if applied_any:
            has_control_surfaces = True
            if reconstructed_names:
                control_surface_names = reconstructed_names

    _validate_airplane_for_aero(airplane, context=f"dataset:{geometry_id}")

    airplane_has_controls = _airplane_has_any_control_surface(airplane)
    if airplane_has_controls and not has_control_surfaces:
        has_control_surfaces = True
    if airplane_has_controls and not control_surface_names:
        control_surface_names = tuple(_collect_control_surface_names_from_airplane(airplane))

    metadata: dict[str, Any] = {
        "source_policy": "reconstruct",
        "dataset_root": str(dataset_root),
        "geometry_id": geometry_id,
        "case_dir": str(case_dir),
        "reconstruction_format_version": RECONSTRUCTION_FORMAT_VERSION,
        "has_control_surfaces": has_control_surfaces,
        "control_surface_names": list(control_surface_names),
    }
    if cs_summary is not None:
        metadata["control_surface_summary"] = cs_summary

    return AeroGeometryView(
        view_id="aerosandbox_airplane_reconstructed_v1",
        airplane=airplane,
        source_generator=generator_id,
        source_geometry_id=geometry_id,
        metadata=metadata,
        has_control_surfaces=has_control_surfaces,
        control_surface_names=control_surface_names,
    )


def resolve_run_geometry_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir).resolve()
    candidates = [
        run_dir,
        run_dir / "geometry",
        run_dir / "artifacts" / "geometry",
    ]
    for candidate in candidates:
        if _has_reconstruction_artifacts(candidate):
            return candidate
    raise FileNotFoundError(
        f"Could not find reconstruction-ready geometry case dir under: {run_dir}"
    )


def resolve_dataset_geometry_dir(dataset_root: Path, geometry_id: str) -> Path:
    dataset_root = Path(dataset_root).resolve()
    case_dir = dataset_root / "geometry" / geometry_id
    if not case_dir.exists():
        raise FileNotFoundError(f"Dataset geometry case not found: {case_dir}")
    if not _has_reconstruction_artifacts(case_dir):
        raise FileNotFoundError(
            f"Reconstruction artifacts missing in dataset case: {case_dir}. "
            f"Expected airfoils/openvsp_sections.csv and airfoils/xfoil/*.dat"
        )
    return case_dir


def reconstruct_airplane_from_case_dir(*, case_dir: Path) -> asb.Airplane:
    case_dir = Path(case_dir).resolve()
    csv_path = case_dir / "airfoils" / "openvsp_sections.csv"
    airfoil_dir = case_dir / "airfoils" / "xfoil"

    if not csv_path.exists():
        raise FileNotFoundError(f"Missing {csv_path}")
    if not airfoil_dir.exists():
        raise FileNotFoundError(f"Missing {airfoil_dir}")

    airplane = build_asb_airplane_from_paths(csv_path, airfoil_dir)
    _validate_airplane_for_aero(airplane, context=str(case_dir))
    return airplane


def build_asb_airplane_from_paths(csv_path: Path, airfoil_dir: Path) -> asb.Airplane:
    sections = _load_sections_from_csv(csv_path)

    n = len(sections)
    if n < 2:
        raise RuntimeError(f"Need at least 2 sections in {csv_path}, got {n}")

    y = [s["y"] for s in sections]
    le_x = [s["le_x"] for s in sections]
    chord = [s["chord"] for s in sections]
    twist_seg = [s["twist_seg"] for s in sections]
    dih_seg = [s["dih_seg"] for s in sections]

    _validate_reconstructed_sections(sections, csv_path=csv_path)

    z = [0.0]
    for i in range(1, n):
        dy = y[i] - y[i - 1]
        gamma = math.radians(dih_seg[i - 1])
        z.append(z[-1] + dy * math.tan(gamma))

    wing_xsecs = []
    for i, sec in enumerate(sections):
        idx = sec["idx"]
        y_file = sec["y_file"]
        af_name = f"airfoil_{idx:03d}_y{y_file:.4f}m.dat"
        af_path = airfoil_dir / af_name

        if not af_path.exists():
            raise FileNotFoundError(
                f"Missing reconstructed airfoil file: {af_path}. "
                "Refusing silent fallback because it corrupts aero fidelity."
            )

        coords = np.loadtxt(af_path, skiprows=1)
        if getattr(coords, "ndim", 0) != 2 or coords.shape[1] < 2 or coords.shape[0] < 3:
            raise RuntimeError(f"Invalid airfoil coordinate file: {af_path}")

        airfoil = asb.Airfoil(name=af_path.stem, coordinates=coords)

        wing_xsecs.append(
            asb.WingXSec(
                xyz_le=[le_x[i], y[i], z[i]],
                chord=chord[i],
                twist=twist_seg[i],
                airfoil=airfoil,
            )
        )

    airplane = asb.Airplane(
        name=csv_path.parent.parent.name,
        wings=[asb.Wing(name="main", symmetric=True, xsecs=wing_xsecs)],
    )
    return airplane


def _load_sections_from_csv(csv_path: Path) -> list[dict[str, float | int]]:
    with open(csv_path, "r", newline="", encoding="utf-8") as handle:
        header_line = handle.readline()
        if "," in header_line and "\t" not in header_line:
            delimiter = ","
        elif "\t" in header_line and "," not in header_line:
            delimiter = "\t"
        else:
            delimiter = ","

    sections: list[dict[str, float | int]] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)

        for row in reader:
            def fget(*names: str, default: float = 0.0) -> float:
                for name in names:
                    raw = row.get(name)
                    if raw is not None and raw.strip() != "":
                        return float(raw)
                return float(default)

            idx = int(row["idx"])
            y_span = fget("y_span_m", "y", "y_span")
            le_x = fget("le_x_m", "le_x")
            chord = fget("chord_m", "chord")
            twist_seg = fget("twist_deg_segment", "twist_deg_local", "twist_deg")
            dihedral_seg = fget("dihedral_deg_segment", "dihedral_deg_local", "dihedral_deg")

            sections.append(
                {
                    "idx": idx,
                    "y": y_span,
                    "y_file": y_span,
                    "le_x": le_x,
                    "chord": chord,
                    "twist_seg": twist_seg,
                    "dih_seg": dihedral_seg,
                }
            )

    sections.sort(key=lambda s: float(s["y"]))
    if len(sections) >= 2:
        sections[0]["dih_seg"] = 0.0

    return sections


def _validate_reconstructed_sections(
    sections: list[dict[str, float | int]],
    *,
    csv_path: Path,
) -> None:
    if len(sections) < 2:
        raise RuntimeError(f"Need at least 2 sections in {csv_path}")

    y_values = [float(s["y"]) for s in sections]
    chords = [float(s["chord"]) for s in sections]
    le_x_values = [float(s["le_x"]) for s in sections]

    for i, y in enumerate(y_values):
        if not math.isfinite(y):
            raise RuntimeError(f"Non-finite span coordinate at section {i} in {csv_path}")

    for i, x in enumerate(le_x_values):
        if not math.isfinite(x):
            raise RuntimeError(f"Non-finite leading-edge x at section {i} in {csv_path}")

    for i, c in enumerate(chords):
        if not math.isfinite(c) or c <= 0.0:
            raise RuntimeError(f"Invalid chord {c} at section {i} in {csv_path}")

    if any(y2 < y1 for y1, y2 in zip(y_values, y_values[1:])):
        raise RuntimeError(f"Section span locations are not monotonic in {csv_path}")

    if len(set(y_values)) != len(y_values):
        raise RuntimeError(f"Duplicate span stations found in {csv_path}")


def _validate_airplane_for_aero(airplane: Any, *, context: str) -> None:
    if airplane is None:
        raise RuntimeError(f"Airplane is None for {context}")

    wings = getattr(airplane, "wings", None)
    if not wings:
        raise RuntimeError(f"Airplane has no wings for {context}")

    wing = wings[0]
    xsecs = getattr(wing, "xsecs", None)
    if not xsecs or len(xsecs) < 2:
        raise RuntimeError(f"Airplane wing has insufficient sections for {context}")

    y_values: list[float] = []
    for i, xsec in enumerate(xsecs):
        chord = float(getattr(xsec, "chord"))
        if not math.isfinite(chord) or chord <= 0.0:
            raise RuntimeError(f"Invalid chord at xsec {i} for {context}")

        xyz_le = list(getattr(xsec, "xyz_le"))
        if len(xyz_le) != 3 or any(not math.isfinite(float(v)) for v in xyz_le):
            raise RuntimeError(f"Invalid leading-edge coordinates at xsec {i} for {context}")

        y_values.append(float(xyz_le[1]))

    if any(y2 < y1 for y1, y2 in zip(y_values, y_values[1:])):
        raise RuntimeError(f"Airplane span stations are not monotonic for {context}")


def _has_reconstruction_artifacts(case_dir: Path) -> bool:
    case_dir = Path(case_dir)
    return (
        (case_dir / "airfoils" / "openvsp_sections.csv").exists()
        and (case_dir / "airfoils" / "xfoil").exists()
    )


def _extract_native_airplane(case: Any) -> Any | None:
    for attr in ("airplane", "aerosandbox_airplane", "asb_airplane", "airplane_asb"):
        value = getattr(case, attr, None)
        if value is not None:
            return value

    asb_result = getattr(case, "aerosandbox_result", None)
    if asb_result is not None:
        value = getattr(asb_result, "airplane", None)
        if value is not None:
            return value

    if isinstance(case, dict):
        for key in ("airplane", "aerosandbox_airplane", "asb_airplane", "airplane_asb"):
            value = case.get(key)
            if value is not None:
                return value

        nested = case.get("aerosandbox_result")
        if hasattr(nested, "airplane"):
            value = getattr(nested, "airplane", None)
            if value is not None:
                return value
        if isinstance(nested, dict):
            value = nested.get("airplane")
            if value is not None:
                return value

    return None