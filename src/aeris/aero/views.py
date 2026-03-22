from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np
import aerosandbox as asb

from aeris.aero.models import AeroGeometryView


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
        return AeroGeometryView(
            view_id="aerosandbox_airplane_reconstructed_v1",
            airplane=airplane,
            source_generator=generator_id,
            metadata={
                "source_policy": "reconstruct",
                "case_dir": str(case_dir),
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
    return AeroGeometryView(
        view_id="aerosandbox_airplane_reconstructed_v1",
        airplane=airplane,
        source_generator=generator_id,
        metadata={
            "source_policy": "reconstruct",
            "run_dir": str(Path(run_dir).resolve()),
            "case_dir": str(case_dir),
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
    return AeroGeometryView(
        view_id="aerosandbox_airplane_reconstructed_v1",
        airplane=airplane,
        source_generator=generator_id,
        metadata={
            "source_policy": "reconstruct",
            "dataset_root": str(Path(dataset_root).resolve()),
            "geometry_id": geometry_id,
            "case_dir": str(case_dir),
        },
    )


def resolve_run_geometry_dir(run_dir: Path) -> Path:
    """
    Accept either:
      - the run root
      - the geometry subdir itself
    """
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

    return build_asb_airplane_from_paths(csv_path, airfoil_dir)


def build_asb_airplane_from_paths(csv_path: Path, airfoil_dir: Path) -> asb.Airplane:
    sections = _load_sections_from_csv(csv_path)

    n = len(sections)
    if n == 0:
        raise RuntimeError(f"No sections found in {csv_path}")

    y = [s["y"] for s in sections]
    le_x = [s["le_x"] for s in sections]
    chord = [s["chord"] for s in sections]
    twist_seg = [s["twist_seg"] for s in sections]
    dih_seg = [s["dih_seg"] for s in sections]

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

        try:
            coords = np.loadtxt(af_path, skiprows=1)
            airfoil = asb.Airfoil(name=af_path.stem, coordinates=coords)
        except Exception as exc:
            print(f"[WARN] could not read {af_path}, using NACA0012. Error: {exc}")
            airfoil = asb.Airfoil("naca0012")

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
                    if name in row and row[name].strip() != "":
                        return float(row[name])
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


def _has_reconstruction_artifacts(case_dir: Path) -> bool:
    case_dir = Path(case_dir)
    return (
        (case_dir / "airfoils" / "openvsp_sections.csv").exists()
        and (case_dir / "airfoils" / "xfoil").exists()
    )


def _extract_native_airplane(case: Any) -> Any | None:
    for attr in ["airplane", "aerosandbox_airplane", "asb_airplane", "airplane_asb"]:
        if hasattr(case, attr):
            value = getattr(case, attr)
            if value is not None:
                return value

    asb_result = getattr(case, "aerosandbox_result", None)
    if asb_result is not None and hasattr(asb_result, "airplane"):
        value = getattr(asb_result, "airplane")
        if value is not None:
            return value

    if isinstance(case, dict):
        for key in ["airplane", "aerosandbox_airplane", "asb_airplane", "airplane_asb"]:
            value = case.get(key)
            if value is not None:
                return value
        asb_result = case.get("aerosandbox_result")
        if isinstance(asb_result, dict):
            value = asb_result.get("airplane")
            if value is not None:
                return value

    return None