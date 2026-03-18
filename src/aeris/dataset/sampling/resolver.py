from __future__ import annotations

from typing import Any


def resolve_dataset_sampler(
    raw_config: dict[str, Any],
    *,
    sampler_override: str | None = None,
    sampler_seed_override: int | None = None,
    legacy_lhs_seed: int | None = None,
) -> tuple[str, int | None]:
    """
    Resolve dataset sampler identity and seed.

    Priority:
    1. explicit sampler_override / sampler_seed_override
    2. legacy lhs_seed
    3. config file dataset.sampling.{method, seed}
    4. defaults -> lhs_v1 / None
    """
    dataset_cfg = raw_config.get("dataset", {})
    sampling_cfg = dataset_cfg.get("sampling", {})

    cfg_sampler = sampling_cfg.get("method") or sampling_cfg.get("sampler")
    cfg_seed = sampling_cfg.get("seed")

    sampler_id = sampler_override or cfg_sampler or "lhs_v1"

    if sampler_seed_override is not None:
        sampler_seed = sampler_seed_override
    elif legacy_lhs_seed is not None:
        sampler_seed = legacy_lhs_seed
    elif cfg_seed is not None:
        sampler_seed = int(cfg_seed)
    else:
        sampler_seed = None

    return sampler_id, sampler_seed
