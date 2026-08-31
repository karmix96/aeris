"""
Case specification dataclasses (schema ``aeris.cfd.case.v1``).

One YAML file describes a full run — geometry input, surface mesh, volume
mesh, solve, post — runnable per-stage or end-to-end.  This mirrors the
single-file case definition model of SU2 (``.cfg``) and OpenFOAM (case
directory): the entire run is reviewable and reproducible from one
artifact, which is the reproducibility unit the thesis defends.

Geometry enters one of two ways:

* ``surface_dir`` — a pre-built surface-mesh directory (standalone mode;
  keeps the aeris.cfd import boundary: no geometry imports in the core).
* ``aeris_config`` — an AERIS geometry YAML, resolved to a surface_dir by
  the CLI layer (``aeris.commands.cfd``), which may import geometry code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CASE_SCHEMA_VERSION = "aeris.cfd.case.v1"


@dataclass(frozen=True)
class GeometryInput:
    surface_dir: Path | None = None
    aeris_config: Path | None = None
    airfoil: str | None = None  # "naca0012" or a Selig .dat path (2-D cases)
    cad: Path | None = None  # STEP/BREP/IGES solid (3-D unstructured cases)
    wing_index: int = 0
    seed: int | None = None


@dataclass(frozen=True)
class SurfaceMeshSpec:
    preset: str | None = None
    topology: str | None = None  # topology registry id (M4); None = preset default
    overrides: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VolumeMeshSpec:
    tool: str = "pyhyp"
    preset: str | None = None
    level: str | None = None
    march_dist_factor: float | None = None
    overrides: dict[str, object] = field(default_factory=dict)  # curated aeris names
    raw_options: dict[str, object] = field(default_factory=dict)  # native pass-through


@dataclass(frozen=True)
class FlowConditions:
    alpha: float
    mach: float
    reynolds: float
    temperature: float = 288.15


@dataclass(frozen=True)
class SolveSpec:
    solver: str = "adflow"
    preset: str | None = None
    flow: FlowConditions | None = None
    area_ref: float | None = None
    chord_ref: float | None = None
    reynolds_length_ref: float | None = None
    moment_reference: tuple[float, float, float] | None = None
    secondary_moment_reference: tuple[float, float, float] | None = None
    mpi_np: int = 1
    overrides: dict[str, object] = field(default_factory=dict)
    raw_options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PostSpec:
    reports: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseSpec:
    name: str
    geometry: GeometryInput
    surface_mesh: SurfaceMeshSpec | None = None
    volume_mesh: VolumeMeshSpec | None = None
    solve: SolveSpec | None = None
    post: PostSpec | None = None
    source_path: Path | None = None  # the YAML this spec was loaded from
