"""
Dataset sampler resolution for AERIS.

This module resolves the dataset sampler identifier and seed from raw config
plus optional CLI overrides. It also validates that the resolved sampler id
is registered so configuration errors fail early and clearly.
"""

from __future__ import annotations

from typing import Any

from aeris.dataset.sampling.registry import list_dataset_samplers


def resolve_dataset_sampler(
    raw_config: dict[str, Any],
    *,
    sampler_override: str | None = None,
    sampler_seed_override: int | None = None,
) -> tuple[str, int | None]:
    """
    Resolve dataset sampler identity and seed.

    Priority:
    1. explicit sampler_override / sampler_seed_override
    2. config file dataset.sampling.{method, seed}
    3. defaults -> lhs_v1 / None
    """
    dataset_cfg = raw_config.get("dataset", {})
    if not isinstance(dataset_cfg, dict):
        raise TypeError("Config field 'dataset' must be a mapping if provided.")

    sampling_cfg = dataset_cfg.get("sampling", {})
    if not isinstance(sampling_cfg, dict):
        raise TypeError("Config field 'dataset.sampling' must be a mapping if provided.")

    cfg_sampler = sampling_cfg.get("method") or sampling_cfg.get("sampler")
    cfg_seed = sampling_cfg.get("seed")

    sampler_id = sampler_override or cfg_sampler or "lhs_v1"

    available = set(list_dataset_samplers())
    if sampler_id not in available:
        available_text = ", ".join(sorted(available)) or "<none>"
        raise ValueError(
            f"Unknown dataset sampler '{sampler_id}'. "
            f"Available samplers: {available_text}"
        )

    if sampler_seed_override is not None:
        # RES-1: validate seed type explicitly — wrong type causes silent non-reproducibility
        if not isinstance(sampler_seed_override, int) or sampler_seed_override < 0:
            raise ValueError(
                f"sampler_seed_override must be a non-negative integer, got: {sampler_seed_override!r}"
            )
        sampler_seed = sampler_seed_override
    elif cfg_seed is not None:
        sampler_seed = int(cfg_seed)
    else:
        sampler_seed = None

    return sampler_id, sampler_seed