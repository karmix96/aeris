"""Make the workbench package importable, and keep the fixtures cheap.

`apps/` is not on the package path - the applications add their own directory
to `sys.path` at startup - so the tests do the same thing the entry points do.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS = REPO_ROOT / "apps"
if str(APPS) not in sys.path:
    sys.path.insert(0, str(APPS))


def _environment(**available: bool):
    """A capability table with no subprocess probes in it.

    `environment.detect()` shells out to the conda interpreter twice, which is
    two seconds a test and, worse, makes the result depend on the machine.  Every
    test that cares about capabilities states them instead.
    """
    from aeris_workbench.environment import Capability, Environment

    defaults = {"pygeo": True, "pyspline": True, "gmsh": True, "vtk": True,
                "pyvista": True, "trame": True, "su2": True, "mpi": True,
                "pyhyp": True, "adflow": True, "atlas": False}
    defaults.update(available)
    env = Environment()
    for key, ok in defaults.items():
        env.capabilities[key] = Capability(
            key, key, ok, "" if ok else f"{key} is not installed here", "", "test")
    return env


@pytest.fixture
def environment():
    return _environment


@pytest.fixture
def make_app(environment):
    """A workbench with a named profile and an explicit capability table."""
    from aeris_workbench.workbench import S6_PROFILE, S7_PROFILE, Workbench
    from trame.app import get_server

    created = []
    counter = [0]

    def build(profile="S6", **capabilities):
        counter[0] += 1
        chosen = S6_PROFILE if profile == "S6" else S7_PROFILE
        app = Workbench(
            chosen,
            server=get_server(f"test_{profile}_{counter[0]}", client_type="vue3"),
            environment=environment(**capabilities),
        )
        created.append(app)
        return app

    return build
