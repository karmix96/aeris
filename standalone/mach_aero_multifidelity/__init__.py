"""Standalone pyGeo/MACH-Aero multifidelity campaign tools.

The package intentionally lives outside :mod:`aeris`.  It consumes the
existing Aeris BWB configuration, surface-mesh, CFD-case, and ML contracts,
but pyGeo is the geometry source of truth and the AVL input is written
directly.
"""

SCHEMA_VERSION = "mach_aero.multifidelity.v1"

