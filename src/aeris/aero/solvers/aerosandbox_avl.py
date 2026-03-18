from __future__ import annotations

from typing import Any, Mapping

from aeris.aero.base import AeroSolver
from aeris.aero.registry import register_aero_solver

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry


@register_aero_solver
class AeroSandboxSolver(AeroSolver):

    SOLVER_ID = "aerosandbox_vlm"

    @property
    def solver_id(self) -> str:
        return self.SOLVER_ID

    def prepare_input(self, geometry_case: Any, config: Mapping[str, Any]) -> Any:
        """
        Extract section_geometry and rebuild AeroSandbox geometry.
        """
        if not hasattr(geometry_case, "section_geometry"):
            raise ValueError("geometry_case missing section_geometry")

        return build_aerosandbox_geometry(
            section_geometry=geometry_case.section_geometry,
            config=config,
        )

    def run(self, prepared_input: Any, config: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Currently no solver execution layer.
        """
        return {
            "status": "geometry_only",
            "aspect_ratio": prepared_input.aspect_ratio,
            "n_xsecs": prepared_input.n_xsecs,
        }