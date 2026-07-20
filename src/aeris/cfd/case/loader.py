"""YAML → CaseSpec with field-named validation errors (aeris.ml.config style)."""

from __future__ import annotations

from pathlib import Path

from aeris.cfd.case.spec import (
    CASE_SCHEMA_VERSION,
    CaseSpec,
    FlowConditions,
    GeometryInput,
    PostSpec,
    SolveSpec,
    SurfaceMeshSpec,
    VolumeMeshSpec,
)
from aeris.common.config import load_yaml_config


def _mapping(raw: object, name: str) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"case.{name} must be a mapping, got {type(raw).__name__}")
    return dict(raw)


def _opt_float(raw: dict[str, object], key: str, section: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        # YAML 1.1 parses "6.0e6" (no sign) as a STRING — a gotcha every
        # config author hits; coerce cleanly instead of failing.
        try:
            return float(value)
        except ValueError:
            pass
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"case.{section}.{key} must be a number, got {value!r}")
    return float(value)


def _req_float(raw: dict[str, object], key: str, section: str) -> float:
    value = _opt_float(raw, key, section)
    if value is None:
        raise ValueError(f"case.{section}.{key} is required")
    return value


def _opt_str(raw: dict[str, object], key: str, section: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"case.{section}.{key} must be a non-empty string, got {value!r}")
    return value


def _geometry(raw: dict[str, object]) -> GeometryInput:
    section = _mapping(raw.get("geometry"), "geometry")
    surface_dir = _opt_str(section, "surface_dir", "geometry")
    aeris_config = _opt_str(section, "aeris_config", "geometry")
    airfoil = _opt_str(section, "airfoil", "geometry")
    cad = _opt_str(section, "cad", "geometry")
    n_sources = sum(value is not None for value in (surface_dir, aeris_config, airfoil, cad))
    if n_sources != 1:
        raise ValueError(
            "case.geometry must set exactly one of 'surface_dir' (standalone, "
            "pre-built surface mesh), 'aeris_config' (AERIS geometry YAML), "
            "'airfoil' ('naca####' or a Selig .dat path, 2-D cases), or 'cad' "
            "(STEP/BREP/IGES solid, 3-D unstructured cases)."
        )
    wing_index = section.get("wing_index", 0)
    if not isinstance(wing_index, int) or isinstance(wing_index, bool) or wing_index < 0:
        raise ValueError(f"case.geometry.wing_index must be a non-negative int, got {wing_index!r}")
    seed = section.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ValueError(f"case.geometry.seed must be an int, got {seed!r}")
    return GeometryInput(
        surface_dir=Path(surface_dir) if surface_dir else None,
        aeris_config=Path(aeris_config) if aeris_config else None,
        airfoil=airfoil,
        cad=Path(cad) if cad else None,
        wing_index=wing_index,
        seed=seed,
    )


def _surface_mesh(raw: dict[str, object]) -> SurfaceMeshSpec | None:
    if "surface_mesh" not in raw:
        return None
    section = _mapping(raw.get("surface_mesh"), "surface_mesh")
    return SurfaceMeshSpec(
        preset=_opt_str(section, "preset", "surface_mesh"),
        topology=_opt_str(section, "topology", "surface_mesh"),
        overrides=_mapping(section.get("overrides"), "surface_mesh.overrides"),
    )


def _volume_mesh(raw: dict[str, object]) -> VolumeMeshSpec | None:
    if "volume_mesh" not in raw:
        return None
    section = _mapping(raw.get("volume_mesh"), "volume_mesh")
    tool = _opt_str(section, "tool", "volume_mesh") or "pyhyp"
    if tool != "pyhyp":
        raise ValueError(f"case.volume_mesh.tool: only 'pyhyp' is supported, got {tool!r}")
    return VolumeMeshSpec(
        tool=tool,
        preset=_opt_str(section, "preset", "volume_mesh"),
        level=_opt_str(section, "level", "volume_mesh"),
        march_dist_factor=_opt_float(section, "march_dist_factor", "volume_mesh"),
        overrides=_mapping(section.get("overrides"), "volume_mesh.overrides"),
        raw_options=_mapping(section.get("pyhyp_options"), "volume_mesh.pyhyp_options"),
    )


def _solve(raw: dict[str, object]) -> SolveSpec | None:
    if "solve" not in raw:
        return None
    section = _mapping(raw.get("solve"), "solve")
    flow_raw = section.get("flow")
    flow = None
    if flow_raw is not None:
        flow_map = _mapping(flow_raw, "solve.flow")
        flow = FlowConditions(
            alpha=_req_float(flow_map, "alpha", "solve.flow"),
            mach=_req_float(flow_map, "mach", "solve.flow"),
            reynolds=_req_float(flow_map, "reynolds", "solve.flow"),
            temperature=_opt_float(flow_map, "temperature", "solve.flow") or 288.15,
        )
    mpi_np = section.get("mpi_np", 1)
    if not isinstance(mpi_np, int) or isinstance(mpi_np, bool) or mpi_np < 1:
        raise ValueError(f"case.solve.mpi_np must be a positive int, got {mpi_np!r}")
    solver = _opt_str(section, "solver", "solve") or "adflow"
    raw_key = f"{solver}_options"
    return SolveSpec(
        solver=solver,
        preset=_opt_str(section, "preset", "solve"),
        flow=flow,
        area_ref=_opt_float(section, "area_ref", "solve"),
        chord_ref=_opt_float(section, "chord_ref", "solve"),
        mpi_np=mpi_np,
        overrides=_mapping(section.get("overrides"), "solve.overrides"),
        raw_options=_mapping(section.get(raw_key), f"solve.{raw_key}"),
    )


def _post(raw: dict[str, object]) -> PostSpec | None:
    if "post" not in raw:
        return None
    section = _mapping(raw.get("post"), "post")
    reports = section.get("reports", [])
    if not isinstance(reports, list) or not all(isinstance(r, str) for r in reports):
        raise ValueError(f"case.post.reports must be a list of strings, got {reports!r}")
    return PostSpec(reports=tuple(reports))


def case_spec_from_mapping(raw: dict[str, object], *, source_path: Path | None = None) -> CaseSpec:
    """Validate an already-loaded case mapping (schema.case) into a CaseSpec.

    Shared by ``load_case_spec`` (reads the mapping from a YAML file) and the
    study runner (builds the mapping in-memory by deep-merging a variant
    patch onto a base case, so validation and defaulting stay identical
    between a plain case run and a study variant run).
    """
    schema = raw.get("schema")
    if schema != CASE_SCHEMA_VERSION:
        raise ValueError(f"case schema must be {CASE_SCHEMA_VERSION!r}, got {schema!r}")

    case = _mapping(raw.get("case"), "case")
    if not case:
        raise ValueError("top-level 'case' mapping is required")
    name = _opt_str(case, "name", "case")
    if name is None:
        raise ValueError("case.name is required")

    return CaseSpec(
        name=name,
        geometry=_geometry(case),
        surface_mesh=_surface_mesh(case),
        volume_mesh=_volume_mesh(case),
        solve=_solve(case),
        post=_post(case),
        source_path=source_path,
    )


def load_case_spec(config_path: str | Path) -> CaseSpec:
    """Load and validate a case YAML into a frozen CaseSpec."""
    path = Path(config_path)
    raw = load_yaml_config(path)
    return case_spec_from_mapping(raw, source_path=path)
