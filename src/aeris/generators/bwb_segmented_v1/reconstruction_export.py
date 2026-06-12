"""
Exports reconstruction artifacts for downstream external-geometry workflows.

Currently writes:
- OpenVSP-style section CSV metadata
- XFOIL-compatible airfoil .dat files

This module is aligned with the existing legacy reconstruction workflow.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import aerosandbox as asb


def export_reconstruction_artifacts(
    *,
    airplane: asb.Airplane,
    output_dir: Path,
) -> dict[str, object]:
    """
    Export the exact artifacts needed for later airplane reconstruction:
      - airfoils/openvsp_sections.csv
      - airfoils/xfoil/*.dat

    This is intentionally aligned with the legacy proven workflow.

    AERIS_PATCH_BATCH3_RECON_FALLBACK_METADATA
    Also returns airfoil fallback metadata so GUI/dataset/QC layers can detect
    when an intended airfoil could not be exported and NACA0012 was used.
    """
    output_dir = Path(output_dir)
    airfoils_root = output_dir / "airfoils"
    xfoil_dir = airfoils_root / "xfoil"

    airfoils_root.mkdir(parents=True, exist_ok=True)
    xfoil_dir.mkdir(parents=True, exist_ok=True)

    if not airplane.wings:
        raise ValueError("Airplane has no wings.")
    wing = airplane.wings[0]
    xsecs = wing.xsecs
    if len(xsecs) < 2:
        raise ValueError("Need at least 2 wing sections to export reconstruction artifacts.")

    rows: list[dict[str, float | int | str | bool | None]] = []
    airfoil_fallbacks: list[dict[str, object]] = []

    ys = [float(xs.xyz_le[1]) for xs in xsecs]
    zs = [float(xs.xyz_le[2]) for xs in xsecs]

    seg_dihedral_deg: list[float] = []
    for i in range(len(xsecs)):
        if i == 0:
            # Root dihedral is always 0° by generator convention
            # (dihedral_root_deg is a fixed config value, not sampled).
            # If a future generator introduces non-zero root dihedral,
            # this must be replaced with: atan2(zs[1]-zs[0], ys[1]-ys[0]).
            seg_dihedral_deg.append(0.0)
        elif i < len(xsecs) - 1:
            dy = ys[i + 1] - ys[i]
            dz = zs[i + 1] - zs[i]
            gamma = math.degrees(math.atan2(dz, dy)) if abs(dy) > 1e-12 else 0.0
            seg_dihedral_deg.append(float(gamma))
        else:
            seg_dihedral_deg.append(seg_dihedral_deg[-1])

    for idx, xsec in enumerate(xsecs):
        y_span = float(xsec.xyz_le[1])
        le_x = float(xsec.xyz_le[0])
        chord = float(xsec.chord)
        twist_seg = float(xsec.twist)
        dih_seg = float(seg_dihedral_deg[idx])

        y_file = y_span
        dat_name = f"airfoil_{idx:03d}_y{y_file:.4f}m.dat"
        dat_path = xfoil_dir / dat_name
        fallback_info = _write_airfoil_dat(xsec.airfoil, dat_path)
        if fallback_info.get("used_fallback"):
            airfoil_fallbacks.append(
                {
                    "section_index": idx,
                    "y_span_m": y_span,
                    "filename": str(dat_path),
                    **fallback_info,
                }
            )

        rows.append(
            {
                "idx": idx,
                "y_span_m": y_span,
                "le_x_m": le_x,
                "chord_m": chord,
                "twist_deg_segment": twist_seg,
                "dihedral_deg_segment": dih_seg,
                "airfoil_dat": dat_name,
                "airfoil_used_fallback": bool(fallback_info.get("used_fallback", False)),
                "airfoil_original_name": fallback_info.get("original_name"),
                "airfoil_exported_name": fallback_info.get("exported_name"),
            }
        )

    csv_path = airfoils_root / "openvsp_sections.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "idx",
                "y_span_m",
                "le_x_m",
                "chord_m",
                "twist_deg_segment",
                "dihedral_deg_segment",
                "airfoil_dat",
                "airfoil_used_fallback",
                "airfoil_original_name",
                "airfoil_exported_name",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return {
        "airfoils_root": str(airfoils_root),
        "xfoil_dir": str(xfoil_dir),
        "openvsp_sections_csv": str(csv_path),
        "airfoil_dat_count": len(xsecs),
        "airfoil_fallback_count": len(airfoil_fallbacks),
        "airfoil_fallbacks": airfoil_fallbacks,
    }


def _write_airfoil_dat(airfoil: asb.Airfoil, path: Path) -> dict[str, object]:
    """Write an XFOIL .dat file and report whether fallback geometry was used."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    original_name = getattr(airfoil, "name", None) or path.stem
    used_fallback = False
    coords = getattr(airfoil, "coordinates", None)
    if coords is None:
        # 2D.8 — Airfoil coordinates unavailable; falling back to NACA 0012.
        # This means the original airfoil name was unresolvable by AeroSandbox.
        # The .dat file will contain NACA 0012 coordinates, NOT the intended
        # airfoil. This is a data quality issue: check airfoil_name in section_3d.csv.
        import warnings
        warnings.warn(
            f"Airfoil coordinates not found for {path.name!r}; "
            "falling back to NACA 0012. Check airfoil_name in section_3d.csv.",
            UserWarning,
            stacklevel=2,
        )
        airfoil = asb.Airfoil("naca0012")
        coords = airfoil.coordinates
        used_fallback = True

    coords = np.asarray(coords, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError(f"Invalid airfoil coordinates for {path.name}")

    exported_name = getattr(airfoil, "name", None) or path.stem
    with path.open("w", encoding="utf-8") as f:
        f.write(f"{exported_name}\n")
        for x, z in coords:
            f.write(f"{float(x):.8f} {float(z):.8f}\n")

    return {
        "used_fallback": used_fallback,
        "original_name": original_name,
        "exported_name": exported_name,
    }

