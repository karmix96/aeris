"""
AERIS geometry framework package.

Defines the abstract GeometryGenerator contract, the generator registry, and
config resolution. Concrete generator implementations live under
aeris.generators.* and register themselves via the side-effect import below.

Adding a new generator:
    1. Implement it under aeris/generators/<name>/
    2. Register it on the registry (decorator on its class)
    3. Add a side-effect import line below, so the generator registers on
       first `import aeris.geometry`.
"""

from __future__ import annotations

# Side-effect imports: trigger generator registrations on first use of
# aeris.geometry. Do NOT move these to aeris.__init__ — that would pull
# heavy dependencies (AeroSandbox, matplotlib) on every `import aeris`.
from aeris.generators.bwb_segmented_v1 import generator as _bwb_segmented_v1  # noqa: F401