"""
2-D airfoil O-grid topology (``airfoil_ogrid_v1``).

The O-topology is the canonical structured mesh for single-element airfoil
RANS validation (the NASA Turbulence Modeling Resource publishes its NACA
0012 reference solutions on O-family grids), and it is exactly the 2-D case
of the pyHyp hyperbolic-extrusion workflow AERIS already validated in 3-D:
the closed surface loop marches outward to the farfield with the same
options, QC, and quarantine machinery.

Mechanics: the generator writes the loop as a one-unit-deep PLOT3D strip
(the layout pyHyp's own ``examples/naca0012`` script produces) plus a
``surface_report.json`` carrying ``pyhyp_hints`` — options the topology
*requires* (explicit z-symmetry side planes instead of auto-symmetry
edges) that the volume stage applies as a provenance-tracked layer.  The
march produces the one-cell-wide 3-D CGNS that ADflow needs (ADflow has
no true 2-D mode; SU2 will consume the same grid natively in 2-D).

Blunt trailing edges: if the input loop has a TE gap it is closed with a
straight base resolved by ``te_base_points`` (an open loop cannot march).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from aeris.cfd.meshing.airfoil_geometry import (
    load_airfoil_dat,
    naca4_coordinates,
    resample_selig_loop,
)
from aeris.cfd.meshing.base import MeshTopologyGenerator
from aeris.cfd.meshing.quality import block_quality_metrics
from aeris.cfd.meshing.registry import register_topology

SURFACE_REPORT_SCHEMA_VERSION = "aeris.cfd.airfoil_surface_report.v1"

KNOWN_PARAMS = frozenset({"n_per_surface", "te_base_points", "reverse_loop"})


def _close_blunt_te(loop: np.ndarray, te_base_points: int) -> tuple[np.ndarray, bool]:
    gap = float(np.linalg.norm(loop[0] - loop[-1]))
    chord = float(loop[:, 0].max() - loop[:, 0].min())
    if gap <= 1e-6 * max(chord, 1e-12):
        # sharp TE: snap the endpoints together exactly
        te = 0.5 * (loop[0] + loop[-1])
        closed = loop.copy()
        closed[0] = te
        closed[-1] = te
        return closed, False
    n_base = max(int(te_base_points), 2)
    base = np.linspace(loop[-1], loop[0], n_base + 1)[1:-1]
    return np.concatenate([loop, base, loop[:1]], axis=0), True


def write_plot3d_curve(path: Path, loop: np.ndarray) -> None:
    """Write the loop as a one-unit-deep formatted PLOT3D surface.

    Layout (n, 2, 1): the curve at z=0 and duplicated at z=1 — the input
    convention of pyHyp's 2-D mode (mach-aero airfoil tutorial).
    """
    n = len(loop)
    x, y = loop[:, 0], loop[:, 1]
    with path.open("w", encoding="utf-8") as handle:
        handle.write("1\n")
        handle.write(f"{n} 2 1\n")
        for values in (x, x, y, y, np.zeros(n), np.ones(n)):
            handle.write(" ".join(f"{v:.16e}" for v in values) + "\n")


@register_topology
class AirfoilOGridV1(MeshTopologyGenerator):
    TOPOLOGY_ID = "airfoil_ogrid_v1"
    DIMENSION = 2
    DESCRIPTION = (
        "Closed airfoil loop with cosine LE/TE clustering for pyHyp 2D "
        "hyperbolic O-grid extrusion (NASA TMR-style validation topology)."
    )

    def generate(
        self,
        geometry: object,
        output_dir: Path,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        """geometry: (N, 2) Selig-ordered array, a .dat Path, or 'naca<4 digits>'."""
        unknown = set(params) - KNOWN_PARAMS
        if unknown:
            raise ValueError(
                f"[{self.TOPOLOGY_ID}] unknown params {sorted(unknown)}. "
                f"Known: {sorted(KNOWN_PARAMS)}"
            )
        n_per_surface = int(params.get("n_per_surface", 129))
        te_base_points = int(params.get("te_base_points", 4))
        reverse_loop = bool(params.get("reverse_loop", False))

        if isinstance(geometry, str) and geometry.lower().startswith("naca"):
            loop = naca4_coordinates(geometry[4:].strip(), n_per_surface)
            source = geometry.lower()
        elif isinstance(geometry, (str, Path)):
            loop = resample_selig_loop(load_airfoil_dat(Path(geometry)), n_per_surface)
            source = str(geometry)
        else:
            coords = np.asarray(geometry, dtype=float)
            if coords.ndim != 2 or coords.shape[1] != 2:
                raise ValueError(
                    f"[{self.TOPOLOGY_ID}] geometry must be (N, 2) Selig coordinates, "
                    f"a .dat path, or 'naca####'; got shape {getattr(coords, 'shape', None)}"
                )
            loop = resample_selig_loop(coords, n_per_surface)
            source = "array"

        loop, blunt_te = _close_blunt_te(loop, te_base_points)
        if reverse_loop:
            loop = loop[::-1]

        chord = float(loop[:, 0].max() - loop[:, 0].min())
        segment_lengths = np.linalg.norm(np.diff(loop, axis=0), axis=1)
        if np.any(segment_lengths <= 0):
            raise ValueError(f"[{self.TOPOLOGY_ID}] degenerate (zero-length) loop segment")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        surface_fmt = output_dir / "surface.fmt"
        write_plot3d_curve(surface_fmt, loop)

        strip = np.zeros((len(loop), 2, 3))
        strip[:, 0, :2] = loop
        strip[:, 1, :2] = loop
        strip[:, 1, 2] = 1.0
        quality = block_quality_metrics(strip)

        report: dict[str, object] = {
            "schema": SURFACE_REPORT_SCHEMA_VERSION,
            "topology": self.TOPOLOGY_ID,
            "source": source,
            "characteristic_length": chord,
            "n_loop_points": int(len(loop)),
            "n_per_surface": n_per_surface,
            "blunt_te_closed": blunt_te,
            "min_segment_length": float(segment_lengths.min()),
            "max_segment_length": float(segment_lengths.max()),
            "quality": quality,
            # Options this topology REQUIRES from the pyHyp volume stage;
            # applied as a provenance-tracked layer by the case runner.  The
            # one-unit-deep strip marches as a normal 3-D surface with
            # explicit z-symmetry side planes — the recipe from pyHyp's own
            # naca0012_rans example (pyhyp/examples/naca0012).
            "pyhyp_hints": {
                "unattached_edges_are_symmetry": False,
                "bc": {1: {"jLow": "zSymm", "jHigh": "zSymm"}},
            },
            # The airfoil lies in the x-y plane (z is the unit extrusion):
            # lift is +y, so alpha must rotate the freestream in x-y.  The
            # wing convention (liftIndex=3, lift=z) yields zero lift here —
            # measured on the first TMR solve, 2026-07-19.
            "adflow_hints": {"lift_index": 2},
        }
        (output_dir / "surface_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return report
