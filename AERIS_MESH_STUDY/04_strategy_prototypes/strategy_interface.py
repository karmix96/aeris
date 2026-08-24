"""Common Stage 01 mesh-strategy interface.

This module is the handoff contract for Stage 02 and later. It deliberately
does not implement any strategy; it defines the callable shape, stable strategy
IDs, required artifact names, and deterministic JSON/hash helpers every
strategy runner must use.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

STRATEGY_IDS = (
    "S0_CAP4",
    "S1_TIP_FIRST_SWEEP",
    "S2_CROSS_FIELD_TIP",
    "S3_STATION_SWEEP",
    "S4_ANALYTIC_MULTIBLOCK",
    "S5_FROZEN_RBF",
)

REQUIRED_ARTIFACTS = (
    "manifest.json",
    "connectivity.json",
    "surface_qc.json",
    "volume_qc.json",
    "timing.json",
    "cfd_summary.json",
)


@dataclass(frozen=True)
class StrategyRunContext:
    """Immutable identifiers shared by every strategy run."""

    stage: str
    strategy_id: str
    geometry_id: str
    mesh_level: str
    workdir: Path
    geometry_config: Path
    geometry_config_sha256: str
    design_sample_sha256: str | None = None
    seed: int | None = None
    environment: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.strategy_id not in STRATEGY_IDS:
            raise ValueError(f"unknown strategy_id {self.strategy_id!r}; valid: {STRATEGY_IDS}")
        if not self.stage:
            raise ValueError("stage is required")
        if not self.geometry_id:
            raise ValueError("geometry_id is required")
        if not self.mesh_level:
            raise ValueError("mesh_level is required")


class MeshStrategy(Protocol):
    """Required hooks for all structured-mesh strategies."""

    strategy_id: str

    def prepare_geometry(self, context: StrategyRunContext) -> Mapping[str, Any]:
        """Create or load the geometry representation consumed by the strategy."""

    def build_surface(
        self,
        context: StrategyRunContext,
        geometry: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Write the body-fitted surface mesh and return its artifact summary."""

    def build_volume(
        self,
        context: StrategyRunContext,
        surface: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Write the volume mesh and return its artifact summary."""

    def export_solver_mesh(
        self,
        context: StrategyRunContext,
        volume: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Prepare solver-readable mesh artifacts and boundary labels."""

    def run_qc(
        self,
        context: StrategyRunContext,
        artifacts: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Run surface/volume/connectivity QC and return normalized metrics."""

    def connectivity_signature(
        self,
        context: StrategyRunContext,
        artifacts: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return deterministic block/interface/boundary-label signature data."""

    def write_manifest(
        self,
        context: StrategyRunContext,
        artifacts: Mapping[str, Any],
        qc: Mapping[str, Any],
    ) -> Path:
        """Write the run manifest."""


def stable_json_bytes(payload: Any) -> bytes:
    """Canonical JSON bytes used by hashes in this study."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def stable_hash(payload: Any) -> str:
    """SHA-256 of canonical JSON for dictionaries/lists/scalars."""

    return hashlib.sha256(stable_json_bytes(payload)).hexdigest()


def connectivity_signature_payload(
    *,
    strategy_id: str,
    block_count: int,
    block_dimensions: Mapping[str, Any],
    interfaces: Any,
    boundary_labels: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the normalized connectivity signature payload."""

    payload = {
        "schema": "aeris.mesh_study.connectivity_signature.v1",
        "strategy_id": strategy_id,
        "block_count": int(block_count),
        "block_dimensions": dict(block_dimensions),
        "interfaces": interfaces,
        "boundary_labels": dict(boundary_labels),
    }
    payload["connectivity_hash"] = stable_hash(payload)
    return payload


def write_strategy_manifest(
    *,
    context: StrategyRunContext,
    status: str,
    artifacts: Mapping[str, Any],
    qc: Mapping[str, Any],
    timing: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> Path:
    """Write ``manifest.json`` with the common Stage 01 schema."""

    context.validate()
    payload: dict[str, Any] = {
        "schema": "aeris.mesh_study.strategy_run_manifest.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "context": {
            **asdict(context),
            "workdir": str(context.workdir),
            "geometry_config": str(context.geometry_config),
        },
        "status": status,
        "artifacts": dict(artifacts),
        "qc": dict(qc),
        "timing": dict(timing or {}),
        "required_artifacts": list(REQUIRED_ARTIFACTS),
    }
    if error is not None:
        payload["error"] = error

    path = context.workdir / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path
