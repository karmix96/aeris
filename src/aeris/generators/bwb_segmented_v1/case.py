"""
Backward-compatible wrapper for geometry case generation.

Prefer using services.py for new code.
"""

from aeris.generators.bwb_segmented_v1.services import (
    GeometryArtifactPaths,
    GeometryCaseResult,
    generate_geometry_case_from_sample,
)

__all__ = [
    "GeometryArtifactPaths",
    "GeometryCaseResult",
    "generate_geometry_case_from_sample",
]