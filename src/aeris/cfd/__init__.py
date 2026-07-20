"""
AERIS CFD suite core — pre-process, mesh, solve, post-process.

Standalone-capable by design: this package (and everything below it) imports
only the standard library, numpy, PyYAML, and ``aeris.common``.  Geometry
enters exclusively through file interfaces (a surface-mesh directory), never
through ``aeris.geometry`` / AeroSandbox imports.  The boundary is enforced
by ``tests/cfd/test_import_boundary.py`` so the package can later be
extracted as a standalone distribution without a rewrite.

Option philosophy (full user authority, provenance-tracked):

    tool-default < aeris-default < preset:<name> < user config < CLI < raw pass-through

Curated options (``aeris.cfd.options.schema``) carry types, docs, citations,
and validators for the knobs AERIS has validated; every other tool option
flows through raw pass-through dicts, verbatim.  Each run records the fully
resolved options with per-key provenance in an ``effective_options`` manifest.
"""
