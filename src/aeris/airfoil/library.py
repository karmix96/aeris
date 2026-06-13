"""Airfoil library reader — look up airfoils by name or airfoil_id."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.airfoil.models import (
    AirfoilRecord,
    AirfoilGeometryStats,
    compute_geometry_stats,
)


class AirfoilLibrary:
    """Read-only view of an ingested airfoil library."""

    def __init__(self, library_dir: Path) -> None:
        self._root = Path(library_dir).expanduser().resolve()
        inv = self._root / "airfoil_inventory.csv"
        if not inv.exists():
            raise FileNotFoundError(
                f"airfoil_inventory.csv not found at {inv}. "
                "Run 'aeris airfoil ingest' first."
            )
        self._df = pd.read_csv(inv)
        self._coords_dir = self._root / "coords"

    # ── Lookup ──────────────────────────────────────────────────────────────

    def get_by_name(self, name: str) -> AirfoilRecord:
        """Case-insensitive name lookup."""
        mask = self._df["name"].str.lower() == name.strip().lower()
        rows = self._df[mask]
        if rows.empty:
            raise KeyError(
                f"Airfoil '{name}' not in library. "
                f"Available: {self._df['name'].tolist()[:10]}..."
            )
        if len(rows) > 1:
            raise ValueError(f"Multiple airfoils named '{name}' in library.")
        return self._load_record(rows.iloc[0])

    def get_by_id(self, airfoil_id: str) -> AirfoilRecord:
        mask = self._df["airfoil_id"] == airfoil_id
        rows = self._df[mask]
        if rows.empty:
            raise KeyError(f"airfoil_id '{airfoil_id}' not found in library.")
        return self._load_record(rows.iloc[0])

    def all_ids(self) -> list[str]:
        return self._df["airfoil_id"].tolist()

    def all_records(self) -> list[AirfoilRecord]:
        return [self._load_record(row) for _, row in self._df.iterrows()]

    # AERIS_PATCH_CST_AIRFOIL_V1_LIBRARY_METADATA
    def metadata_for_id(self, airfoil_id: str) -> dict[str, Any]:
        """Return one inventory row as metadata for downstream dataset rows.

        Generated CST libraries add coefficient columns such as cst_u0/cst_l0.
        The XFOIL dataset builder propagates those columns into
        airfoil_dataset.csv so EDA/ML feature presets can consume them without
        any solver-specific special case.
        """
        mask = self._df["airfoil_id"] == airfoil_id
        rows = self._df[mask]
        if rows.empty:
            raise KeyError(f"airfoil_id {airfoil_id!r} not found in library inventory")
        return rows.iloc[0].to_dict()

    def __len__(self) -> int:
        return len(self._df)

    # ── Internal ────────────────────────────────────────────────────────────

    def _load_record(self, row: pd.Series) -> AirfoilRecord:
        aid = str(row["airfoil_id"])
        npz_path = self._coords_dir / f"{aid}.npz"
        if not npz_path.exists():
            raise FileNotFoundError(f"Coordinate file missing: {npz_path}")
        data = np.load(npz_path)
        x, y = data["x"], data["y"]
        stats = AirfoilGeometryStats(
            t_c=float(row["t_c"]),
            t_c_x=float(row["t_c_x"]),
            camber_max=float(row["camber_max"]),
            camber_max_x=float(row["camber_max_x"]),
            le_radius=float(row["le_radius"]),
            te_angle_deg=float(row["te_angle_deg"]),
        )
        return AirfoilRecord(
            airfoil_id=aid,
            name=str(row["name"]),
            family=str(row["family"]),
            source_file=str(row["source_file"]),
            n_coords=int(row["n_coords"]),
            x=x,
            y=y,
            stats=stats,
        )
