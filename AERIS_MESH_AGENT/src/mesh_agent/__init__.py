"""Mesh agent — learned routing, retry and stopping for S6 bounded-atlas meshing.

Paper code. Nothing here writes to the AERIS mesh study artifacts; every
input is read-only and every output lands under AERIS_MESH_AGENT/.
"""

__all__ = ["ledger", "features", "outcome", "policy", "evaluate"]
