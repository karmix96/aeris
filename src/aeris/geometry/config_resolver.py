"""
Resolves geometry generator identity and constructs typed configuration objects.

This module:
    - extracts generator selection from raw YAML configuration
    - retrieves the corresponding generator from the registry
    - delegates typed configuration construction to the generator

Acts as the boundary between raw YAML input and typed generator logic.

Config schema (preferred):

    geometry:
      generator:
        id: bwb_segmented_v1
      ...

Config schema (legacy, accepted with a deprecation warning):

    geometry:
      generator:
        family: bwb_segmented
        version: v1
      ...

The legacy schema reconstructs the ID as f"{family}_{version}". Both raise a
clear ValueError if the required fields are missing. There is no implicit
default — a config without an identifiable generator fails loudly.
"""

from __future__ import annotations

import logging
from typing import Any

from aeris.geometry.registry import get_geometry_generator

_LOGGER = logging.getLogger(__name__)


def resolve_generator_and_config(raw_config: dict[str, Any]) -> tuple[str, Any]:
    """Resolve generator ID + build typed config from raw YAML.

    Returns:
        (generator_id, config_obj) tuple.

    Raises:
        ValueError: if the raw config lacks a 'geometry.generator' block, or
            the block does not specify a generator identity via either
            'id' (preferred) or both 'family' and 'version' (legacy).
        KeyError: if the resolved generator ID is not in the registry.
    """
    if not isinstance(raw_config, dict):
        raise ValueError(
            f"raw_config must be a dict, got {type(raw_config).__name__}."
        )

    geometry_cfg = raw_config.get("geometry")
    if not isinstance(geometry_cfg, dict) or "generator" not in geometry_cfg:
        raise ValueError(
            "Config missing required 'geometry.generator' block. Provide:\n"
            "  geometry:\n"
            "    generator:\n"
            "      id: <generator_id>          # preferred\n"
            "or (legacy):\n"
            "  geometry:\n"
            "    generator:\n"
            "      family: <family>\n"
            "      version: <version>"
        )

    generator_cfg = geometry_cfg["generator"]
    if not isinstance(generator_cfg, dict):
        raise ValueError(
            "'geometry.generator' must be a mapping, "
            f"got {type(generator_cfg).__name__}."
        )

    generator_id = _resolve_generator_id(generator_cfg)
    generator = get_geometry_generator(generator_id)
    config_obj = generator.build_config(raw_config)

    return generator_id, config_obj


def _resolve_generator_id(generator_cfg: dict[str, Any]) -> str:
    """Resolve the generator ID from the generator config block.

    Prefers the 'id' field. Falls back to 'family' + 'version' with a
    deprecation warning. Raises ValueError if neither path yields a valid ID.
    """
    explicit_id = generator_cfg.get("id")
    if explicit_id is not None:
        if not isinstance(explicit_id, str) or not explicit_id.strip():
            raise ValueError(
                f"'geometry.generator.id' must be a non-empty string, "
                f"got {explicit_id!r}."
            )
        return explicit_id.strip()

    family = generator_cfg.get("family")
    version = generator_cfg.get("version")

    if family and version:
        if not isinstance(family, str) or not isinstance(version, str):
            raise ValueError(
                "'geometry.generator.family' and 'version' must both be "
                f"strings, got family={family!r}, version={version!r}."
            )
        reconstructed_id = f"{family.strip()}_{version.strip()}"
        _LOGGER.warning(
            "'geometry.generator.family' + 'version' is a legacy schema. "
            "Replace with a single 'geometry.generator.id: %s'.",
            reconstructed_id,
        )
        return reconstructed_id

    raise ValueError(
        "Could not resolve generator ID. Provide 'geometry.generator.id' "
        "(preferred) or both 'family' and 'version'. "
        f"Got id={generator_cfg.get('id')!r}, family={family!r}, "
        f"version={version!r}."
    )