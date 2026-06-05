"""AERIS aero control metadata and naming contract.

This module is intentionally small and boring.

Current reality:
- Existing AERIS aero runs use `control_input_deg`.
- For the BWB elevon setup, that value represents symmetric elevon deflection.

Forward-compatible naming:
- `delta_e_sym_deg`: symmetric elevon deflection, pitch-control variable.
- `delta_a_diff_deg`: differential elevon deflection, roll-control variable.

Do not remove `control_input_deg` yet. It remains the backward-compatible alias.
"""

from __future__ import annotations

from typing import Any

CONTROL_METADATA_SCHEMA_VERSION = "aeris.control_metadata.v1"

DEFAULT_BWB_ELEVON_CONTROL_METADATA: dict[str, Any] = {
    "schema_version": CONTROL_METADATA_SCHEMA_VERSION,
    "control_architecture": "bwb_trailing_edge_elevon_v1",
    "legacy_aliases": {
        "control_input_deg": "delta_e_sym_deg",
    },
    "variables": {
        "delta_e_sym_deg": {
            "description": "Symmetric elevon deflection used as pitch-control input.",
            "units": "deg",
            "legacy_column": "control_input_deg",
            "positive_convention": "trailing edge down; expected nose-up pitching moment convention must be verified per solver/sign setup",
            "status": "active",
        },
        "delta_a_diff_deg": {
            "description": "Differential elevon deflection used as roll-control input.",
            "units": "deg",
            "positive_convention": "right elevon down, left elevon up; expected positive roll convention must be verified before production use",
            "status": "reserved_not_solver_wired_yet",
            "default_value": 0.0,
        },
    },
    "geometry_defaults": {
        "control_surface_name": "elevon",
        "family": "trailing_edge",
        "hinge_point_chord_fraction": 0.75,
        "control_span_start_frac": 0.60,
        "control_span_end_frac": 0.95,
        "symmetric": True,
    },
    "notes": [
        "control_input_deg is retained for backward compatibility.",
        "New datasets should expose delta_e_sym_deg explicitly.",
        "delta_a_diff_deg is reserved until differential elevon solver wiring is implemented.",
    ],
}


def default_control_metadata() -> dict[str, Any]:
    """Return a copy of the default BWB elevon control metadata."""
    return {
        **DEFAULT_BWB_ELEVON_CONTROL_METADATA,
        "legacy_aliases": dict(DEFAULT_BWB_ELEVON_CONTROL_METADATA["legacy_aliases"]),
        "variables": {
            k: dict(v)
            for k, v in DEFAULT_BWB_ELEVON_CONTROL_METADATA["variables"].items()
        },
        "geometry_defaults": dict(DEFAULT_BWB_ELEVON_CONTROL_METADATA["geometry_defaults"]),
        "notes": list(DEFAULT_BWB_ELEVON_CONTROL_METADATA["notes"]),
    }


def control_alias_row(control_input_deg: float | None) -> dict[str, float | None]:
    """Return backward-compatible and explicit control-name columns.

    For now:
        control_input_deg == delta_e_sym_deg
        delta_a_diff_deg == 0.0

    This is deliberately conservative. It names the current behavior without
    pretending differential elevon support exists yet.
    """
    value = None if control_input_deg is None else float(control_input_deg)
    return {
        "control_input_deg": value,
        "delta_e_sym_deg": value,
        "delta_a_diff_deg": 0.0,
    }
