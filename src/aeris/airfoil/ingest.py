"""
Airfoil .dat library ingest (Selig format).

Reads a directory of .dat files — one file per airfoil, standard Selig format:
  Line 1:       airfoil name (may be empty → use filename)
  Lines 2..N:   x y  (whitespace-separated float pairs)

Upper surface is listed TE→LE, lower surface LE→TE (standard UIUC layout).
Some files use a single-surface listing (LE→TE); both are handled.

Writes:
  data/airfoil_library/airfoil_inventory.csv   (one row per airfoil)
  data/airfoil_library/coords/<id>.npz         (x, y float64 arrays)
  data/airfoil_library/ingest_report.json

Fail-loud: raises on no valid files. Skips unparseable files with a warning.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.airfoil.models import (
    AirfoilRecord,
    compute_airfoil_id,
    compute_geometry_stats,
)

_REQUIRED_MIN_COORDS = 10  # fewer points = degenerate


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _infer_family(name: str) -> str:
    n = name.upper().replace("-", "").replace("_", "").replace(" ", "")
    if n.startswith("NACA"):
        digits = n[4:].strip()
        if len(digits) == 4:
            return "naca4"
        if len(digits) == 5:
            return "naca5"
        return "naca"
    if n.startswith("FX") or n.startswith("WORTMANN"):
        return "wortmann"
    if n.startswith("EPPLER") or n.startswith("E"):
        return "eppler"
    if n.startswith("DAE"):
        return "dae"
    if n.startswith("S") and n[1:].isdigit():
        return "selig"
    if n.startswith("CLARK"):
        return "clark"
    return "custom"


def _parse_dat_file(path: Path) -> tuple[str, np.ndarray, np.ndarray]:
    """Parse one Selig-format .dat file.

    Returns (name, x_array, y_array).
    Raises ValueError on unreadable or degenerate files.
    """
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    lines = [l.strip() for l in text.splitlines()]

    if not lines:
        raise ValueError("File is empty")

    # Strip leading comment/blank lines before deciding if line 1 is a name.
    # Comment lines start with '#' or '!' and must be skipped first.
    non_comment_lines = [
        l for l in lines
        if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("!")
    ]
    if not non_comment_lines:
        raise ValueError("File contains only comments or blank lines")

    # Line 1 (first non-comment): name if it cannot be parsed as two floats.
    first = non_comment_lines[0]
    try:
        parts = first.split()
        float(parts[0])
        float(parts[1])
        # First non-comment line is coordinates — use filename as name
        name = path.stem
        coord_lines = non_comment_lines
    except (ValueError, IndexError):
        # First non-comment line is the airfoil name
        name = first.strip() or path.stem
        coord_lines = non_comment_lines[1:]

    # Some dat files have a blank line or a second header between upper/lower
    # Parse all lines that look like "float float"
    xy_pairs: list[tuple[float, float]] = []
    for line in coord_lines:
        # Skip comment lines and blank lines
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
            xy_pairs.append((x, y))
        except ValueError:
            # Non-numeric line (e.g. "Upper surface", "1." single value) — skip
            continue

    if len(xy_pairs) < _REQUIRED_MIN_COORDS:
        raise ValueError(
            f"Only {len(xy_pairs)} valid coordinate pairs found "
            f"(minimum {_REQUIRED_MIN_COORDS})"
        )

    coords = np.array(xy_pairs, dtype=float)
    x_raw, y_raw = coords[:, 0], coords[:, 1]

    # Validate finiteness
    if not (np.all(np.isfinite(x_raw)) and np.all(np.isfinite(y_raw))):
        raise ValueError("Non-finite values in coordinate arrays")

    # Normalise: chord = 1, LE at x=0
    x_min, x_max = x_raw.min(), x_raw.max()
    chord = x_max - x_min
    if chord < 1e-6:
        raise ValueError(f"Chord length near zero ({chord:.2e}) — check scale")
    x = (x_raw - x_min) / chord
    y = y_raw / chord

    return name, x, y


def ingest_airfoil_library(
    *,
    db_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Ingest all .dat files in db_dir into the AERIS airfoil library.

    Parameters
    ----------
    db_dir:     Directory containing .dat airfoil files.
    output_dir: Library root. Writes airfoil_inventory.csv and coords/<id>.npz.

    Returns
    -------
    dict with report content (also written to output_dir/ingest_report.json).
    """
    db_dir = db_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    coords_dir = output_dir / "coords"
    coords_dir.mkdir(parents=True, exist_ok=True)

    dat_files = sorted(db_dir.glob("*.dat"))
    if not dat_files:
        raise FileNotFoundError(
            f"No .dat files found in {db_dir}.\n"
            "The AeroSandbox airfoil_database contains files like 'naca4412.dat'."
        )

    records: list[AirfoilRecord] = []
    failures: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for path in dat_files:
        try:
            name, x, y = _parse_dat_file(path)
            airfoil_id = compute_airfoil_id(x, y)

            if airfoil_id in seen_ids:
                failures.append({
                    "file": path.name,
                    "reason": f"duplicate_geometry (id={airfoil_id})",
                })
                continue
            seen_ids.add(airfoil_id)

            stats = compute_geometry_stats(x, y)
            record = AirfoilRecord(
                airfoil_id=airfoil_id,
                name=name,
                family=_infer_family(name),
                source_file=path.name,
                n_coords=len(x),
                x=x,
                y=y,
                stats=stats,
            )
            records.append(record)
            np.savez_compressed(coords_dir / f"{airfoil_id}.npz", x=x, y=y)

        except Exception as exc:
            failures.append({"file": path.name, "reason": str(exc)})

    if not records:
        raise RuntimeError(
            f"No valid airfoils ingested from {db_dir}. "
            f"{len(failures)} failures — check file format."
        )

    inventory_rows = [r.to_inventory_row() for r in records]
    inventory_df = pd.DataFrame(inventory_rows)
    inventory_csv = output_dir / "airfoil_inventory.csv"
    inventory_df.to_csv(inventory_csv, index=False)

    report: dict[str, Any] = {
        "schema_version": "airfoil_library_v1",
        "source_format": "dat_selig",
        "ingested_at_utc": _utc_now(),
        "db_dir": str(db_dir),
        "output_dir": str(output_dir),
        "total_dat_files": len(dat_files),
        "ingested": len(records),
        "failures": len(failures),
        "failure_details": failures,
        "inventory_csv": str(inventory_csv),
        "coords_dir": str(coords_dir),
        "stats_summary": {
            "t_c_mean":  round(float(inventory_df["t_c"].mean()),  4),
            "t_c_min":   round(float(inventory_df["t_c"].min()),   4),
            "t_c_max":   round(float(inventory_df["t_c"].max()),   4),
            "families":  inventory_df["family"].value_counts().to_dict(),
        },
    }
    (output_dir / "ingest_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print(f"[AERIS 2D] Ingested {len(records)} airfoils from {len(dat_files)} .dat files")
    print(f"[AERIS 2D] Failures: {len(failures)}")
    print(f"[AERIS 2D] Inventory: {inventory_csv}")
    return report
