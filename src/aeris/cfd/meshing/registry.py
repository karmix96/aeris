"""
Topology registry: decorator registration + plugin loading.

Mirrors the proven ``aeris.geometry.registry`` semantics (decorator with a
required versioned class-attribute id).  Topologies implemented on top of
AERIS geometry (the wing family) live *outside* the aeris.cfd core in
``aeris.mesh.topologies`` and register themselves through the plugin hook:
the core never imports geometry code, it only tolerates plugins that import
it — that keeps the suite standalone while AERIS plugs its wing builders in.
"""

from __future__ import annotations

import importlib
import os
import sys

from aeris.cfd.meshing.base import MeshTopologyGenerator

_TOPOLOGIES: dict[str, type[MeshTopologyGenerator]] = {}

# Modules imported (by name, best-effort) before the registry is read.
# Core topologies first, then external plugins.  Extendable via the
# AERIS_CFD_TOPOLOGY_PLUGINS env var (comma-separated).
DEFAULT_PLUGIN_MODULES = (
    "aeris.cfd.meshing.airfoil_ogrid",
    "aeris.cfd.meshing.gmsh_backend",
    "aeris.cfd.meshing.gmsh_cad",
    "aeris.mesh.topologies",
)
PLUGIN_ENV = "AERIS_CFD_TOPOLOGY_PLUGINS"

_plugins_loaded = False
_needs_reload = False  # set after a registry reset: cached modules must re-execute


def register_topology(cls: type[MeshTopologyGenerator]) -> type[MeshTopologyGenerator]:
    """Class decorator: register a topology generator by its TOPOLOGY_ID."""
    topology_id = getattr(cls, "TOPOLOGY_ID", "")
    if not topology_id:
        raise ValueError(f"{cls.__name__} must define a non-empty TOPOLOGY_ID")
    if getattr(cls, "DIMENSION", 0) not in (2, 3):
        raise ValueError(f"{cls.__name__} must define DIMENSION as 2 or 3")
    if topology_id in _TOPOLOGIES and _TOPOLOGIES[topology_id] is not cls:
        raise ValueError(f"Duplicate topology id {topology_id!r}")
    _TOPOLOGIES[topology_id] = cls
    return cls


def _load_plugins() -> None:
    global _plugins_loaded, _needs_reload
    if _plugins_loaded:
        return
    _plugins_loaded = True
    modules = list(DEFAULT_PLUGIN_MODULES)
    extra = os.environ.get(PLUGIN_ENV, "")
    modules.extend(name.strip() for name in extra.split(",") if name.strip())
    for name in modules:
        try:
            cached = sys.modules.get(name)
            if cached is None:
                importlib.import_module(name)
            elif _needs_reload:
                # registration happens via decorators at module execution; a
                # cached module only re-executes after a registry reset
                importlib.reload(cached)
            # cached and no reset: its decorators already registered
        except ImportError:
            # Standalone install without the plugin package — fine: only the
            # topologies shipped inside aeris.cfd are available.
            continue
    _needs_reload = False


def get_topology(topology_id: str) -> MeshTopologyGenerator:
    _load_plugins()
    if topology_id not in _TOPOLOGIES:
        raise ValueError(f"Unknown topology {topology_id!r}. Available: {sorted(_TOPOLOGIES)}")
    return _TOPOLOGIES[topology_id]()


def list_topologies() -> list[type[MeshTopologyGenerator]]:
    _load_plugins()
    return [_TOPOLOGIES[key] for key in sorted(_TOPOLOGIES)]


def clear_registry_for_tests() -> None:
    """Test hook: reset registration state (mirrors geometry registry)."""
    global _plugins_loaded, _needs_reload
    _TOPOLOGIES.clear()
    _plugins_loaded = False
    _needs_reload = True
