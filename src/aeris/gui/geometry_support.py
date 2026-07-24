"""Pure support functions for the backend-aware Aeris geometry GUI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

USE_YAML_BACKENDS = "Use YAML backend settings"
PYGEO_ONLY = "pyGeo only"
AEROSANDBOX_ONLY = "AeroSandbox only"
DUAL_BACKEND = "Both backends + comparison"


@dataclass(frozen=True)
class GeometryBackendState:
    """Backend configuration read directly from one Aeris geometry YAML."""

    config_path: Path
    name: str
    pygeo_enabled: bool
    aerosandbox_enabled: bool
    physical_cad_enabled: bool
    save_pygeo_visualization: bool
    station_airfoils: dict[str, str]

    @property
    def configured_backends(self) -> tuple[str, ...]:
        result: list[str] = []
        if self.aerosandbox_enabled:
            result.append("AeroSandbox")
        if self.pygeo_enabled:
            result.append("pyGeo")
        return tuple(result)

    def effective_backends(self, aerosandbox_override: bool | None) -> tuple[str, ...]:
        result: list[str] = []
        use_aerosandbox = (
            self.aerosandbox_enabled
            if aerosandbox_override is None
            else aerosandbox_override
        )
        if use_aerosandbox:
            result.append("AeroSandbox")
        if self.pygeo_enabled:
            result.append("pyGeo")
        return tuple(result)


@dataclass(frozen=True)
class GeometryRunEvidence:
    """Canonical geometry-run evidence consumed by the GUI."""

    run_dir: Path
    manifest: dict[str, Any]
    summary: dict[str, Any]
    backends: dict[str, Any]
    metrics: dict[str, Any]
    pygeo: dict[str, Any]
    comparison: dict[str, Any]
    preview_images: tuple[Path, ...]
    pygeo_surface_npz: Path | None
    pygeo_interactive_html: Path | None
    pygeo_cad_dir: Path | None


def read_geometry_backend_state(config_path: str | Path) -> GeometryBackendState:
    """Read backend switches from the production Aeris YAML schema."""

    path = Path(config_path).expanduser().resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    geometry = raw.get("geometry") or {}
    outputs = geometry.get("outputs") or {}
    pygeo = geometry.get("pygeo") or {}
    pygeo_outputs = pygeo.get("outputs") or {}
    physical = pygeo.get("physical_cad") or {}
    sections = geometry.get("section_bounds") or {}
    station_airfoils = sections.get("station_airfoils") or {}
    return GeometryBackendState(
        config_path=path,
        name=str(raw.get("name") or path.stem),
        pygeo_enabled=bool(pygeo.get("enabled", False)),
        aerosandbox_enabled=bool(outputs.get("build_aerosandbox", True)),
        physical_cad_enabled=bool(physical.get("enabled", False)),
        save_pygeo_visualization=bool(pygeo_outputs.get("save_visualization", True)),
        station_airfoils={
            station: str(station_airfoils[station])
            for station in ("b0", "b1", "b2", "b3")
            if station in station_airfoils
        },
    )


def backend_policy_options(state: GeometryBackendState) -> tuple[str, ...]:
    """Return only policies the CLI can honor without rewriting the YAML."""

    if state.pygeo_enabled:
        return (USE_YAML_BACKENDS, PYGEO_ONLY, DUAL_BACKEND)
    return (USE_YAML_BACKENDS, AEROSANDBOX_ONLY)


def aerosandbox_override_for_policy(policy: str) -> bool | None:
    """Translate a GUI policy into the real geometry CLI override."""

    if policy == USE_YAML_BACKENDS:
        return None
    if policy == PYGEO_ONLY:
        return False
    if policy in {AEROSANDBOX_ONLY, DUAL_BACKEND}:
        return True
    raise ValueError(f"Unknown geometry backend policy: {policy}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _existing_file(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_file() else None


def load_geometry_run_evidence(run_dir: str | Path) -> GeometryRunEvidence:
    """Load the same manifests and artifact paths written by Aeris geometry runs."""

    root = Path(run_dir).expanduser().resolve()
    manifest = _read_json(root / "manifest.json")
    summary_path = root / "artifacts" / "geometry" / "geometry_summary.json"
    summary = _read_json(summary_path)
    if not summary:
        summary = ((manifest.get("geometry") or {}).get("case_summary") or {})

    geometry_dir = root / "artifacts" / "geometry"
    pygeo_dir = geometry_dir / "pygeo"
    artifacts = summary.get("artifacts") or {}
    pygeo = summary.get("pygeo") or {}
    pygeo_artifacts = pygeo.get("artifacts") or {}

    candidates = [
        geometry_dir / "plots" / "planform.png",
        geometry_dir / "plots" / "pygeo_vs_aerosandbox.png",
        pygeo_dir / "geometry_3d.png",
        pygeo_dir / "sections.png",
        pygeo_dir / "physical_deflected_geometry.png",
    ]
    for mapping in (artifacts, pygeo_artifacts):
        for value in mapping.values():
            if isinstance(value, str) and value.lower().endswith(".png"):
                candidates.append(Path(value).expanduser())

    previews: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and resolved not in seen:
            previews.append(resolved)
            seen.add(resolved)

    surface_npz = _existing_file(pygeo_artifacts.get("pygeo_surface_npz"))
    if surface_npz is None:
        surface_npz = _existing_file(pygeo_dir / "pygeo_surface.npz")
    interactive = _existing_file(pygeo_dir / "pygeo_interactive_3d.html")
    cad_dir = pygeo_dir / "cad"

    return GeometryRunEvidence(
        run_dir=root,
        manifest=manifest,
        summary=summary,
        backends=summary.get("realization_backends") or {},
        metrics=summary.get("metrics") or {},
        pygeo=pygeo,
        comparison=summary.get("backend_comparison") or {},
        preview_images=tuple(previews),
        pygeo_surface_npz=surface_npz,
        pygeo_interactive_html=interactive,
        pygeo_cad_dir=cad_dir.resolve() if cad_dir.is_dir() else None,
    )
