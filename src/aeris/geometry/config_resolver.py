from __future__ import annotations

from typing import Any, Tuple

from aeris.geometry.registry import get_geometry_generator


def resolve_generator_and_config(
    raw_config: dict[str, Any],
) -> Tuple[str, Any]:
    """
    Resolve generator ID and delegate config construction
    to the generator itself.
    """

    geometry_cfg = raw_config.get("geometry", {})
    generator_cfg = geometry_cfg.get("generator", {})

    family = generator_cfg.get("family", "bwb_segmented")
    version = generator_cfg.get("version", "v1")

    generator_id = f"{family}_{version}"

    generator = get_geometry_generator(generator_id)

    # NEW: generator owns config construction
    if not hasattr(generator, "build_config"):
        raise AttributeError(
            f"Generator '{generator_id}' does not implement build_config()."
        )

    config_obj = generator.build_config(raw_config)

    return generator_id, config_obj