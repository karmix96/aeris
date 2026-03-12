from __future__ import annotations

import csv
import json
from pathlib import Path

from aeris.geometry.params import WingGeometryParams


def export_geometry_summary(params: WingGeometryParams, output_path: Path) -> None:
    output_path.write_text(
        json.dumps(params.to_dict(), indent=2),
        encoding="utf-8",
    )


def export_planform_sections_csv(params: WingGeometryParams, output_path: Path) -> None:
    rows = [
        {
            "section": "root",
            "y_m": 0.0,
            "chord_m": params.root_chord,
            "x_le_m": 0.0,
            "z_m": 0.0,
        },
        {
            "section": "tip",
            "y_m": params.span / 2.0,
            "chord_m": params.tip_chord,
            "x_le_m": (params.span / 2.0) * 0.0,  # placeholder for sweep logic later
            "z_m": (params.span / 2.0) * 0.0,     # placeholder for dihedral logic later
        },
    ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["section", "y_m", "chord_m", "x_le_m", "z_m"],
        )
        writer.writeheader()
        writer.writerows(rows)
