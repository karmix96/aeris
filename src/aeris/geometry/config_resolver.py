from __future__ import annotations

from typing import Any, Tuple

from aeris.geometry.params import build_bwb_generator_config


def resolve_generator_and_config(
    raw_config: dict[str, Any],
) -> Tuple[str, Any]:
    """
    Resolve generator ID and build the appropriate generator config.

    Returns:
        (generator_id, generator_config_object)
    """

    geometry_cfg = raw_config.get("geometry", {})
    generator_cfg = geometry_cfg.get("generator", {})

    family = generator_cfg.get("family", "bwb_segmented")
    version = generator_cfg.get("version", "v1")

    generator_id = f"{family}_{version}"

    # --- TEMPORARY ROUTING (Checkpoint 5D stage) ---
    if generator_id == "bwb_segmented_v1":
        config_obj = build_bwb_generator_config(raw_config)
    else:
        raise ValueError(f"Unknown generator: {generator_id}")

    return generator_id, config_obj