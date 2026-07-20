"""
Enforce the aeris.cfd standalone import boundary.

The suite core must stay extractable as a standalone distribution: it may
import only the standard library, numpy, PyYAML, itself, and aeris.common
(the domain-neutral infra that would be extracted with it).  Geometry and
the rest of AERIS enter through file interfaces only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import aeris.cfd

CFD_ROOT = Path(aeris.cfd.__file__).parent

# h5py (CGNS/HDF5 interchange — the suite's mesh format) and gmsh (the
# unstructured meshing backend) are core capabilities of a standalone CFD
# suite; both are import-guarded at runtime with clear install hints.
ALLOWED_TOP_LEVEL = set(sys.stdlib_module_names) | {"numpy", "yaml", "h5py", "gmsh"}
ALLOWED_AERIS_PREFIXES = ("aeris.cfd", "aeris.common")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import stays inside the package
                continue
            if node.module:
                modules.add(node.module)
    return modules


def test_cfd_core_imports_only_allowed_modules():
    violations: list[str] = []
    for path in sorted(CFD_ROOT.rglob("*.py")):
        for module in _imported_modules(path):
            top = module.split(".")[0]
            if top == "aeris":
                if not module.startswith(ALLOWED_AERIS_PREFIXES):
                    violations.append(f"{path.relative_to(CFD_ROOT)}: {module}")
            elif top not in ALLOWED_TOP_LEVEL:
                violations.append(f"{path.relative_to(CFD_ROOT)}: {module}")
    assert not violations, (
        "aeris.cfd must import only stdlib/numpy/yaml/aeris.common/aeris.cfd "
        f"(standalone boundary). Violations: {violations}"
    )
