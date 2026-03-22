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
) -> dict[str, str]:
    """
    Export the exact artifacts needed for later airplane reconstruction:
      - airfoils/openvsp_sections.csv
      - airfoils/xfoil/*.dat

    This is intentionally aligned with the legacy proven workflow.
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

    rows: list[dict[str, float | int]] = []

    ys = [float(xs.xyz_le[1]) for xs in xsecs]
    zs = [float(xs.xyz_le[2]) for xs in xsecs]

    seg_dihedral_deg: list[float] = []
    for i in range(len(xsecs)):
        if i == 0:
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

        rows.append(
            {
                "idx": idx,
                "y_span_m": y_span,
                "le_x_m": le_x,
                "chord_m": chord,
                "twist_deg_segment": twist_seg,
                "dihedral_deg_segment": dih_seg,
            }
        )

        y_file = y_span
        dat_name = f"airfoil_{idx:03d}_y{y_file:.4f}m.dat"
        dat_path = xfoil_dir / dat_name
        _write_airfoil_dat(xsec.airfoil, dat_path)

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
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return {
        "airfoils_root": str(airfoils_root),
        "xfoil_dir": str(xfoil_dir),
        "openvsp_sections_csv": str(csv_path),
    }


def _write_airfoil_dat(airfoil: asb.Airfoil, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    coords = getattr(airfoil, "coordinates", None)
    if coords is None:
        airfoil = asb.Airfoil("naca0012")
        coords = airfoil.coordinates

    coords = np.asarray(coords, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError(f"Invalid airfoil coordinates for {path.name}")

    name = getattr(airfoil, "name", None) or path.stem
    with path.open("w", encoding="utf-8") as f:
        f.write(f"{name}\n")
        for x, z in coords:
            f.write(f"{float(x):.8f} {float(z):.8f}\n")