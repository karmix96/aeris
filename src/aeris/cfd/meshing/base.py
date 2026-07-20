"""
Mesh topology generator contract.

A topology generator turns a geometry input into a structured surface mesh
directory (surface files + ``surface_report.json``) that the volume/solve
stages consume.  Versioned IDs (``wing_cap4_v1``, ``airfoil_ogrid_v1``)
follow the aeris.geometry generator convention: behavior changes get a new
version, never a silent redefinition — the id printed in a manifest pins
the exact recipe.

Geometry input is deliberately loose-typed (``object``): 3-D wing
topologies consume an AeroSandbox ``Wing`` (supplied by the AERIS plugin
layer), 2-D airfoil topologies consume an (N, 2) coordinate array.  Each
generator documents what it accepts and validates it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar


class MeshTopologyGenerator(ABC):
    """One mesh topology recipe, registered by TOPOLOGY_ID."""

    TOPOLOGY_ID: ClassVar[str] = ""
    DIMENSION: ClassVar[int] = 0  # 2 or 3
    DESCRIPTION: ClassVar[str] = ""

    @abstractmethod
    def generate(
        self,
        geometry: object,
        output_dir: Path,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        """Build the surface mesh into ``output_dir``; return the surface report.

        The report must include ``characteristic_length`` and QC metrics, and
        the directory must contain the PLOT3D ``surface.fmt`` +
        ``surface_report.json`` pair the volume stage consumes.
        """
