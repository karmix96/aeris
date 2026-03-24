from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np
import aerosandbox as asb

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
        return AeroGeometryView(
            view_id="aerosandbox_airplane_native_v1",
            airplane=airplane,
            source_generator=generator_id,
            metadata={
                "source_policy": "native",
                "case_dir": None if case_dir is None else str(case_dir),
            },
        )

    if source_policy == "reconstruct":
        if case_dir is None:
            raise RuntimeError("Reconstruction requires a case_dir.")
        airplane = reconstruct_airplane_from_case_dir(case_dir=case_dir)
        _validate_airplane_for_aero(airplane, context=f"reconstructed:{case_dir}")
        return AeroGeometryView(
            view_id="aerosandbox_airplane_reconstructed_v1",
            airplane=airplane,
            source_generator=generator_id,
            metadata={
                "source_policy": "reconstruct",
                "case_dir": str(case_dir),
                "reconstruction_format_version": RECONSTRUCTION_FORMAT_VERSION,
            },
        )

    raise ValueError(f"Unknown source_policy '{source_policy}'.")


def geometry_view_from_run_dir(
    *,
    run_dir: Path,
    generator_id: str = "bwb_segmented_v1",
) -> AeroGeometryView:
    case_dir = resolve_run_geometry_dir(run_dir)
    airplane = reconstruct_airplane_from_case_dir(case_dir=case_dir)
    _validate_airplane_for_aero(airplane, context=f"run_dir:{run_dir}")
    return AeroGeometryView(
        view_id="aerosandbox_airplane_reconstructed_v1",
        airplane=airplane,
        source_generator=generator_id,
        metadata={
            "source_policy": "reconstruct",
            "run_dir": str(Path(run_dir).resolve()),
            "case_dir": str(case_dir),
            "reconstruction_format_version": RECONSTRUCTION_FORMAT_VERSION,
        },
    )


def geometry_view_from_dataset_case(
    *,
    dataset_root: Path,
    geometry_id: str,
    generator_id: str = "bwb_segmented_v1",
) -> AeroGeometryView:
    case_dir = resolve_dataset_geometry_dir(dataset_root, geometry_id)
    airplane = reconstruct_airplane_from_case_dir(case_dir=case_dir)
    _validate_airplane_for_aero(airplane, context=f"dataset:{geometry_id}")
    return AeroGeometryView(
        view_id="aerosandbox_airplane_reconstructed_v1",
        airplane=airplane,
        source_generator=generator_id,
        metadata={
            "source_policy": "reconstruct",
            "dataset_root": str(Path(dataset_root).resolve()),
            "geometry_id": geometry_id,
            "case_dir": str(case_dir),
            "reconstruction_format_version": RECONSTRUCTION_FORMAT_VERSION,
        },
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
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        header_line = f.readline()
        if "," in header_line and "\t" not in header_line:
            delimiter = ","
        elif "\t" in header_line and "," not in header_line:
            delimiter = "\t"
        else:
            delimiter = ","

    sections = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter)

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

    sections.sort(key=lambda s: s["y"])
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