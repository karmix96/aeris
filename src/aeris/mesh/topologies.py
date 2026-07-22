"""
AERIS wing topologies registered into the aeris.cfd topology registry.

This module is the *plugin* side of the boundary: aeris.cfd never imports
geometry code; instead it best-effort-imports this module (see
``aeris.cfd.meshing.registry.DEFAULT_PLUGIN_MODULES``), which registers the
AeroSandbox-coupled wing surface builders.  The adapters delegate to the
validated ``aeris.mesh.surface.export_surface_mesh`` — zero mesh math is
duplicated here.

Geometry input: an AeroSandbox ``Wing`` (as produced by the AERIS geometry
generators and selected via ``aeris.mesh.surface.select_wing``).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from aeris.cfd.meshing.base import MeshTopologyGenerator
from aeris.cfd.meshing.registry import register_topology
from aeris.mesh.surface import export_surface_mesh

# topology param name -> export_surface_mesh kwarg
_PARAM_MAP = {
    "points_per_side": "points_per_block_side",
    "spanwise_panels": "spanwise_panels_per_section",
    "tip_radial_points": "tip_radial_points",
    "tip_inner_scale": "tip_inner_scale",
    "tip_dome_scale": "tip_dome_scale",
    "tip_conformal_ring": "tip_conformal_ring",
    "split_x_fore": "split_x_fore",
    "min_te_thickness": "minimum_te_thickness",
    "min_scaled_jacobian": "minimum_scaled_jacobian",
    "max_adjacent_normal_angle": "maximum_adjacent_normal_angle_deg",
    "cap_width_frac": "cap_width_frac",
    "cap_wrap_points": "cap_wrap_points",
    "cap_wrap_x": "cap_wrap_x",
    "tip_topology": "tip_topology",
    "chordwise_distribution": "chordwise_distribution",
    "chordwise_beta": "chordwise_beta",
    "spanwise_distribution": "spanwise_distribution",
    "spanwise_beta": "spanwise_beta",
}


class _WingTopology(MeshTopologyGenerator):
    """Shared adapter: params -> export_surface_mesh with a fixed OML topology."""

    OML_TOPOLOGY: str = ""
    DEFAULT_TIP_RADIAL_POINTS: int = 9

    def generate(
        self,
        geometry: object,
        output_dir: Path,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        unknown = set(params) - set(_PARAM_MAP) - {"oml_topology"}
        if unknown:
            raise ValueError(
                f"[{self.TOPOLOGY_ID}] unknown surface params {sorted(unknown)}. "
                f"Known: {sorted(_PARAM_MAP)}"
            )
        kwargs: dict[str, object] = {
            _PARAM_MAP[key]: value for key, value in params.items() if key in _PARAM_MAP
        }
        kwargs.setdefault("tip_radial_points", self.DEFAULT_TIP_RADIAL_POINTS)
        kwargs["oml_topology"] = self.OML_TOPOLOGY
        return export_surface_mesh(geometry, Path(output_dir), **kwargs)


@register_topology
class WingMid4V1(_WingTopology):
    TOPOLOGY_ID = "wing_mid4_v1"
    DIMENSION = 3
    DESCRIPTION = (
        "Stable 4-block OML + tip-ring wing surface; requires pyHyp coarsen=4 "
        "(tip cap limits in-plane resolution)."
    )
    OML_TOPOLOGY = "mid4"


@register_topology
class WingSplit8V1(_WingTopology):
    TOPOLOGY_ID = "wing_split8_v1"
    DIMENSION = 3
    DESCRIPTION = "mid4 variant with doubled LE/TE blocks."
    OML_TOPOLOGY = "split8"


@register_topology
class WingCap4V1(_WingTopology):
    TOPOLOGY_ID = "wing_cap4_v1"
    DIMENSION = 3
    DESCRIPTION = (
        "Camber-aligned tip cap; full in-plane resolution (pyHyp coarsen=1), "
        "validated at L1 — the DSE grid-convergence family topology."
    )
    OML_TOPOLOGY = "cap4"
    DEFAULT_TIP_RADIAL_POINTS = 3
