"""
Registry for AERIS geometry generator implementations.

Provides:
    - decorator-based registration of generator classes
    - lookup and instantiation by generator ID
    - listing of available generators
    - test-only registry-clearing helper

This registry decouples the framework layer from concrete generator
implementations.

Contract:
    Generators MUST be cheap to instantiate. The registry constructs a new
    instance on every get_geometry_generator() call. Heavy initialization
    (large mesh templates, ML weights, etc.) should be deferred to the first
    method call that actually needs it. If/when a heavy generator arrives,
    we will add per-process caching (see deferred tracker).
"""

from __future__ import annotations

from aeris.geometry.base import GeometryGenerator


_GEOMETRY_GENERATORS: dict[str, type[GeometryGenerator]] = {}


def register_geometry_generator(
    generator_cls: type[GeometryGenerator],
) -> type[GeometryGenerator]:
    """Class decorator for registering geometry generators.

    The generator class MUST declare a non-empty ``GENERATOR_ID`` class
    attribute. This is enforced at registration time so failures occur on
    import rather than at first use.

    Raises:
        ValueError: if GENERATOR_ID is missing/invalid or already registered.
    """
    generator_id = getattr(generator_cls, "GENERATOR_ID", None)
    if not generator_id or not isinstance(generator_id, str):
        raise ValueError(
            f"Cannot register geometry generator {generator_cls.__name__}: "
            "missing or invalid class attribute 'GENERATOR_ID' "
            "(must be a non-empty string)."
        )

    if generator_id in _GEOMETRY_GENERATORS:
        existing = _GEOMETRY_GENERATORS[generator_id].__name__
        raise ValueError(
            f"Geometry generator '{generator_id}' is already registered "
            f"(existing class: {existing}, new class: {generator_cls.__name__})."
        )

    _GEOMETRY_GENERATORS[generator_id] = generator_cls
    return generator_cls


def get_geometry_generator(generator_id: str) -> GeometryGenerator:
    """Instantiate and return a registered geometry generator by ID.

    Raises:
        KeyError: if no generator is registered for the given ID. The error
            message lists currently available IDs to aid debugging.
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
    """Return sorted list of registered geometry generator IDs."""
    return sorted(_GEOMETRY_GENERATORS.keys())


def _clear_geometry_registry() -> None:
    """Clear all registered generators.

    Intended for test isolation only. Underscore-prefixed to mark it as
    internal (not part of the public API).
    """
    _GEOMETRY_GENERATORS.clear()