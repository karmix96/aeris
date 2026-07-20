"""
Preset registry: validated recipes as data, never as code.

Presets are YAML files under ``data/`` with schema ``aeris.cfd.preset.v1``.
A preset may only set *curated* option names — raw tool pass-through is a
user privilege, presets must stay inside the validated envelope.  Loading
validates every volume key against the pyHyp curated schema and every
surface key against the known topology parameter set, so a preset typo
fails at load, not mid-run.

Keeping presets as data (not constants in code) means: they diff cleanly
in review, they can be listed/shown by the CLI and GUI without importing
mesh code, and third parties can read the validated recipe without reading
Python — the "one documented policy, no per-case tuning" C1/C2 criterion
made inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS, PYHYP_SCHEMA

PRESET_SCHEMA_VERSION = "aeris.cfd.preset.v1"

DATA_DIR = Path(__file__).parent / "data"

PRESET_KINDS = ("mesh_family", "solver_strategy")

# Surface/topology parameters a preset may set (typed schema arrives with
# the topology registry in M4; until then this set is the guard).
ALLOWED_SURFACE_KEYS = frozenset(
    {
        "oml_topology",
        "points_per_side",
        "spanwise_panels",
        "tip_radial_points",
        "tip_inner_scale",
        "cap_width_frac",
        "cap_wrap_points",
        "cap_wrap_x",
        "split_x_fore",
    }
)


@dataclass(frozen=True)
class CfdPreset:
    name: str
    kind: str
    description: str
    citation: str = ""
    tool: str = ""  # solver_strategy presets name their solver ("adflow", "su2")
    surface: dict[str, object] = field(default_factory=dict)
    volume: dict[str, object] = field(default_factory=dict)
    solver: dict[str, object] = field(default_factory=dict)


def _validate_preset(raw: dict[str, object], path: Path) -> CfdPreset:
    schema = raw.get("schema")
    if schema != PRESET_SCHEMA_VERSION:
        raise ValueError(f"{path.name}: schema must be {PRESET_SCHEMA_VERSION!r}, got {schema!r}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{path.name}: 'name' must be a non-empty string")
    kind = raw.get("kind")
    if kind not in PRESET_KINDS:
        raise ValueError(f"{path.name}: 'kind' must be one of {PRESET_KINDS}, got {kind!r}")
    description = raw.get("description")
    if not isinstance(description, str) or not description:
        raise ValueError(f"{path.name}: 'description' must be a non-empty string")

    surface = dict(raw.get("surface") or {})
    unknown_surface = set(surface) - ALLOWED_SURFACE_KEYS
    if unknown_surface:
        raise ValueError(
            f"{path.name}: unknown surface keys {sorted(unknown_surface)}. "
            f"Allowed: {sorted(ALLOWED_SURFACE_KEYS)}"
        )

    volume = dict(raw.get("volume") or {})
    allowed_volume = set(PYHYP_SCHEMA.by_name) | {"level"}
    unknown_volume = set(volume) - allowed_volume
    if unknown_volume:
        raise ValueError(
            f"{path.name}: unknown volume keys {sorted(unknown_volume)} — presets may "
            "only set curated pyHyp options (raw pass-through is a user privilege)."
        )
    level = volume.get("level")
    if level is not None and level not in GRID_LEVELS:
        raise ValueError(f"{path.name}: unknown grid level {level!r}. Valid: {list(GRID_LEVELS)}")

    tool = str(raw.get("tool") or "")
    solver = dict(raw.get("solver") or {})
    if solver:
        if kind != "solver_strategy":
            raise ValueError(f"{path.name}: only solver_strategy presets may set 'solver'")
        if tool == "adflow":
            # local import: registry stays loadable without the solver package
            from aeris.cfd.solvers.adflow.options_schema import ADFLOW_SCHEMA

            schema = ADFLOW_SCHEMA
        elif tool == "su2":
            from aeris.cfd.solvers.su2.options_schema import SU2_SCHEMA

            schema = SU2_SCHEMA
        elif not tool:
            raise ValueError(f"{path.name}: solver_strategy presets must set 'tool'")
        else:
            schema = None
        if schema is not None:
            unknown_solver = set(solver) - set(schema.by_name)
            if unknown_solver:
                raise ValueError(
                    f"{path.name}: unknown {tool} solver keys {sorted(unknown_solver)} — "
                    "presets may only set curated options (raw pass-through is a "
                    "user privilege)."
                )

    return CfdPreset(
        name=name,
        kind=str(kind),
        description=description,
        citation=str(raw.get("citation") or ""),
        tool=tool,
        surface=surface,
        volume=volume,
        solver=solver,
    )


@lru_cache(maxsize=1)
def _load_all() -> dict[str, CfdPreset]:
    presets: dict[str, CfdPreset] = {}
    for path in sorted(DATA_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path.name}: preset file must contain a mapping")
        preset = _validate_preset(raw, path)
        if preset.name in presets:
            raise ValueError(f"{path.name}: duplicate preset name {preset.name!r}")
        presets[preset.name] = preset
    return presets


def get_preset(name: str) -> CfdPreset:
    presets = _load_all()
    if name not in presets:
        raise ValueError(f"Unknown preset {name!r}. Available: {sorted(presets)}")
    return presets[name]


def list_presets(kind: str | None = None) -> list[CfdPreset]:
    presets = _load_all().values()
    if kind is None:
        return list(presets)
    return [p for p in presets if p.kind == kind]
