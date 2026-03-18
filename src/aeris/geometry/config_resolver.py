from __future__ import annotations

from typing import Any

from aeris.geometry.registry import get_geometry_generator


def resolve_generator_and_config(raw_config: dict[str, Any]) -> tuple[str, Any]:
    """
    Resolve the generator ID from raw YAML and delegate typed config construction
    to the registered generator implementation.
    """
    geometry_cfg = raw_config.get("geometry", {})
    generator_cfg = geometry_cfg.get("generator", {})

    family = generator_cfg.get("family", "bwb_segmented")
    version = generator_cfg.get("version", "v1")

    generator_id = f"{family}_{version}"
    generator = get_geometry_generator(generator_id)
    config_obj = generator.build_config(raw_config)

    return generator_id, config_obj
