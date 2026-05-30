"""
Stable re-export shim from services.py.

Why this exists:
    The active generator (generator.py) and several legacy scripts under
    aeris/../scripts/ import geometry case helpers via this path:

        from aeris.generators.bwb_segmented_v1.case import (
            GeometryArtifactPaths,
            GeometryCaseResult,
            generate_geometry_case_from_sample,
        )

    Keeping this shim avoids breaking those callers. New code SHOULD prefer
    importing directly from aeris.generators.bwb_segmented_v1.services.

    See deferred tracker item D19 — once scripts/ is migrated (or removed),
    this shim can be deleted.
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