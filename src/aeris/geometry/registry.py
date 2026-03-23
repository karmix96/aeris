"""
Registry for geometry generator implementations.

Provides:
- decorator-based registration of generator classes
- lookup and instantiation by generator ID
- listing of available generators

This registry decouples the framework layer from concrete generator implementations.
"""

from __future__ import annotations

from typing import Dict, Type

from aeris.geometry.base import GeometryGenerator


_GEOMETRY_GENERATORS: Dict[str, Type[GeometryGenerator]] = {}


def register_geometry_generator(generator_cls: Type[GeometryGenerator]) -> Type[GeometryGenerator]:
    """
    Class decorator for registering geometry generators.
    """
    generator_id = getattr(generator_cls, "GENERATOR_ID", None)
    if not generator_id:
        raise ValueError(
            f"Cannot register geometry generator {generator_cls.__name__}: "
            "missing class attribute 'GENERATOR_ID'."
        )

    if generator_id in _GEOMETRY_GENERATORS:
        raise ValueError(f"Geometry generator '{generator_id}' is already registered.")

    _GEOMETRY_GENERATORS[generator_id] = generator_cls
    return generator_cls


def get_geometry_generator(generator_id: str) -> GeometryGenerator:
    """
    Instantiate and return a registered geometry generator by ID.
    """
    try:
        generator_cls = _GEOMETRY_GENERATORS[generator_id]
    except KeyError as exc:
        available = ", ".join(sorted(_GEOMETRY_GENERATORS)) or "<none>"
        raise KeyError(
            f"Unknown geometry generator '{generator_id}'. "
            f"Available generators: {available}"
        ) from exc

    return generator_cls()


def list_geometry_generators() -> list[str]:
    """
    Return sorted registered geometry generator IDs.
    """
    return sorted(_GEOMETRY_GENERATORS.keys())