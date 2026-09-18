"""Strict ingestion of the S8 CFD mission authority."""

from __future__ import annotations

import math
from pathlib import Path

from aeris.common.config import file_sha256, load_yaml_config

MISSION_SCHEMA = "aeris.s6.mission_authority.v1"


def load_mission_authority(path: Path) -> dict[str, object]:
    resolved = path.expanduser().resolve()
    raw = load_yaml_config(resolved)
    if raw.get("schema_version") != MISSION_SCHEMA:
        raise ValueError(
            f"mission authority schema must be {MISSION_SCHEMA!r}, "
            f"got {raw.get('schema_version')!r}"
        )
    if not str(raw.get("status", "")).startswith("authoritative"):
        raise ValueError(f"mission authority is not authoritative: {raw.get('status')!r}")
    flow = raw.get("flow")
    state = raw.get("state")
    if not isinstance(flow, dict) or not isinstance(state, dict):
        raise ValueError("mission authority requires flow and state mappings")
    required_positive = (
        "speed_mps",
        "temperature_K",
        "pressure_Pa",
        "density_kg_m3",
        "dynamic_viscosity_Pa_s",
        "reference_chord_m",
        "reynolds",
        "mach",
    )
    for key in required_positive:
        value = flow.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"mission flow.{key} must be numeric")
        if not math.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"mission flow.{key} must be finite and positive")
    alphas = state.get("alpha_deg")
    if not isinstance(alphas, list) or len(alphas) < 2:
        raise ValueError("mission state.alpha_deg must contain at least two points")
    alpha_values = [float(value) for value in alphas]
    if any(not math.isfinite(value) for value in alpha_values) or len(set(alpha_values)) != len(
        alpha_values
    ):
        raise ValueError("mission state.alpha_deg must be unique finite values")
    return {
        "path": str(resolved),
        "sha256": file_sha256(resolved),
        "authority_id": raw.get("authority_id"),
        "status": raw.get("status"),
        "flow": dict(flow),
        "state": dict(state),
        "high_load_case": raw.get("high_load_case"),
    }
