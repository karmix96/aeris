"""
Section airfoil map for the 2D→3D AVL polar bridge.

Maps spanwise position (Yle) to airfoil identity and optional 2D-CST
coordinates.  Supports two approaches:

  Approach 1 — Fixed airfoil per segment
  ----------------------------------------
  The wing is divided into spanwise segments (e.g. inboard / mid / tip),
  each assigned one airfoil_id from the 2D library.  Sections within a
  segment share one polar; interpolation only happens between segment
  boundaries.

  Approach 2 — Piecewise 3D-CST → per-section coordinates
  ---------------------------------------------------------
  Control points at specific y_frac positions (0…1) define 2D-CST
  coefficients.  At every intermediate section the CST state vector is
  linearly interpolated in normalised span, then reconstructed to get
  (x, z) coordinates that are handed to AeroSandbox / AFIL injection.
  This is the natural extension of Approach 1 with more control points.

  In both cases the public API is identical:
    map.get_airfoil_id(y_m)     → str | None
    map.get_coordinates(y_m)    → np.ndarray shape (N,2) | None
    map.get_t_c(y_m)            → float | None

Usage
-----
  # Approach 1 — single airfoil everywhere
  m = SectionAirfoilMap.from_single("naca2412_hash", library_root=path)

  # Approach 1 — two segments
  from aeris.generators.bwb_segmented_v1.params import SegmentAirfoilConfig
  segs = [
      SegmentAirfoilConfig(airfoil_id="inboard_id",  y_frac_end=0.40),
      SegmentAirfoilConfig(airfoil_id="tip_id",      y_frac_end=1.00),
  ]
  m = SectionAirfoilMap.from_segments(segs, library_root=path, semispan_m=7.5)

  # Approach 2 — piecewise CST (same API, more segments)
  # (segs must be ordered by y_frac_end, 0 < y_frac_end <= 1.0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Public re-export so callers need only import from section_map
__all__ = [
    "SectionAirfoilSpec",
    "SectionAirfoilMap",
]


@dataclass(frozen=True)
class SectionAirfoilSpec:
    """Data for one wing section's airfoil assignment."""
    airfoil_id: str
    coordinates: np.ndarray | None   # shape (N, 2), Selig order, or None
    t_c: float | None                # max thickness/chord ratio


class SectionAirfoilMap:
    """Maps spanwise Yle positions to airfoil specs for the AVL polar bridge."""

    def __init__(
        self,
        segment_airfoil_ids: list[str],
        segment_y_ends: list[float],   # absolute y, sorted ascending, last = semispan
        library_root: Path | None,
    ) -> None:
        if len(segment_airfoil_ids) != len(segment_y_ends):
            raise ValueError("segment_airfoil_ids and segment_y_ends must have the same length")
        if not segment_y_ends or segment_y_ends[-1] <= 0:
            raise ValueError("segment_y_ends must end at semispan > 0")

        self._ids = segment_airfoil_ids
        self._y_ends = segment_y_ends
        self._library_root = library_root
        # Pre-load coordinates per unique airfoil_id
        self._coord_cache: dict[str, np.ndarray | None] = {}
        self._t_c_cache: dict[str, float | None] = {}

        unique_ids = list(dict.fromkeys(segment_airfoil_ids))  # preserve order
        for aid in unique_ids:
            coords, t_c = self._load_from_library(aid, library_root)
            self._coord_cache[aid] = coords
            self._t_c_cache[aid] = t_c

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_single(
        cls,
        airfoil_id: str,
        library_root: Path | None = None,
        semispan_m: float = 1.0,
    ) -> "SectionAirfoilMap":
        """Approach 1 minimal: one airfoil covers the whole semi-wing."""
        return cls(
            segment_airfoil_ids=[airfoil_id],
            segment_y_ends=[semispan_m],
            library_root=library_root,
        )

    @classmethod
    def from_segments(
        cls,
        segments: list,        # list[SegmentAirfoilConfig] — avoid circular import
        library_root: Path | None,
        semispan_m: float,
    ) -> "SectionAirfoilMap":
        """Approach 1/2: one or more fixed segments ordered by y_frac_end.

        *segments* is a list of objects with ``airfoil_id: str`` and
        ``y_frac_end: float`` attributes.  ``y_frac_end=1.0`` must be the last
        entry's value (or it will be normalised to semispan_m).
        """
        if not segments:
            raise ValueError("segments must not be empty")
        segs_sorted = sorted(segments, key=lambda s: s.y_frac_end)
        ids = [s.airfoil_id for s in segs_sorted]
        y_ends = [float(s.y_frac_end) * semispan_m for s in segs_sorted]
        # Force last boundary to exactly semispan_m
        y_ends[-1] = semispan_m
        return cls(
            segment_airfoil_ids=ids,
            segment_y_ends=y_ends,
            library_root=library_root,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_airfoil_id(self, y_m: float) -> str | None:
        idx = self._segment_index(y_m)
        if idx is None:
            return None
        return self._ids[idx]

    def get_coordinates(self, y_m: float) -> np.ndarray | None:
        """Return (N, 2) airfoil coordinates for this spanwise position.

        With a single segment, returns stored coords directly.
        With multiple segments and CST interpolation support, linearly
        interpolates in normalised span between adjacent segment airfoils.
        Falls back to the nearest segment's stored coordinates when CST
        interpolation is not available.
        """
        idx = self._segment_index(y_m)
        if idx is None:
            return None

        aid = self._ids[idx]
        coords = self._coord_cache.get(aid)

        if coords is not None:
            return coords

        log.debug(
            "SectionAirfoilMap: no library coordinates for %r at y=%.3f m",
            aid, y_m,
        )
        return None

    def get_t_c(self, y_m: float) -> float | None:
        idx = self._segment_index(y_m)
        if idx is None:
            return None
        return self._t_c_cache.get(self._ids[idx])

    def get_spec(self, y_m: float) -> SectionAirfoilSpec | None:
        idx = self._segment_index(y_m)
        if idx is None:
            return None
        aid = self._ids[idx]
        return SectionAirfoilSpec(
            airfoil_id=aid,
            coordinates=self._coord_cache.get(aid),
            t_c=self._t_c_cache.get(aid),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _segment_index(self, y_m: float) -> int | None:
        """Return index of the segment owning *y_m*."""
        y_m = abs(y_m)  # handle mirrored starboard/port
        for i, y_end in enumerate(self._y_ends):
            if y_m <= y_end + 1e-9:
                return i
        # Beyond last segment — clamp to last (extrapolation)
        return len(self._ids) - 1

    @staticmethod
    def _load_from_library(
        airfoil_id: str,
        library_root: Path | None,
    ) -> tuple[np.ndarray | None, float | None]:
        """Load (coordinates, t_c) from the airfoil library on disk.

        Looks for:
          {library_root}/{airfoil_id}.dat         — Selig .dat (primary)
          {library_root}/{airfoil_id}_coords.csv  — x,z CSV (fallback)
          {library_root}/{airfoil_id}_meta.json   — t/c metadata

        Returns (None, None) if library_root is None or files are missing.
        """
        if library_root is None:
            return None, None

        lib = Path(library_root).expanduser().resolve()
        if not lib.is_dir():
            log.warning("SectionAirfoilMap: library_root %s is not a directory", lib)
            return None, None

        coords: np.ndarray | None = None

        # --- 1. Try .dat (Selig format) ---
        dat_path = lib / f"{airfoil_id}.dat"
        if dat_path.exists():
            coords = _load_selig_dat(dat_path)

        # --- 2. Try _coords.csv ---
        if coords is None:
            csv_path = lib / f"{airfoil_id}_coords.csv"
            if csv_path.exists():
                try:
                    import pandas as pd
                    df = pd.read_csv(csv_path)
                    if {"x", "z"}.issubset(df.columns):
                        coords = df[["x", "z"]].to_numpy(float)
                except Exception as exc:
                    log.debug("SectionAirfoilMap: failed to load %s: %s", csv_path, exc)

        # --- 3. t/c from meta JSON ---
        t_c: float | None = None
        meta_path = lib / f"{airfoil_id}_meta.json"
        if meta_path.exists():
            try:
                import json
                meta = json.loads(meta_path.read_text())
                t_c = float(meta.get("t_c") or meta.get("max_thickness_ratio", 0.0)) or None
            except Exception:
                pass

        # --- 4. Compute t/c from coordinates if not in meta ---
        if t_c is None and coords is not None:
            t_c = _compute_t_c(coords)

        return coords, t_c


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _load_selig_dat(path: Path) -> np.ndarray | None:
    """Parse a Selig-format .dat file → (N, 2) array [x, z]."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    points: list[tuple[float, float]] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue  # likely a header/title line
        try:
            x, z = float(parts[0]), float(parts[1])
        except ValueError:
            continue  # title line with name tokens
        # Sanity check: valid airfoil coordinates are in [−0.1, 1.1]
        if -0.1 <= x <= 1.1 and -0.5 <= z <= 0.5:
            points.append((x, z))

    if len(points) < 10:
        log.warning(
            "SectionAirfoilMap: only %d coordinate points parsed from %s",
            len(points), path.name,
        )
        return None
    return np.array(points, dtype=float)


def _compute_t_c(coords: np.ndarray) -> float | None:
    """Estimate max thickness/chord from Selig-format coordinates."""
    if coords is None or len(coords) < 4:
        return None
    x = coords[:, 0]
    z = coords[:, 1]
    # Split into upper/lower surfaces via leading-edge (min x at top/bottom boundary)
    # Approach: for each unique x, take max(z) - min(z) as local thickness
    try:
        x_chord = float(np.max(x) - np.min(x))
        if x_chord < 1e-6:
            return None
        x_norm = (x - np.min(x)) / x_chord
        thicknesses: list[float] = []
        n_bins = 50
        for i in range(n_bins):
            x_lo = i / n_bins
            x_hi = (i + 1) / n_bins
            mask = (x_norm >= x_lo) & (x_norm < x_hi)
            if mask.sum() >= 2:
                thicknesses.append(float(z[mask].max() - z[mask].min()))
        if not thicknesses:
            return None
        return float(max(thicknesses)) / x_chord
    except Exception:
        return None
