"""Regression guard: the pyGeo geometry path must NOT import AeroSandbox.

Roadmap step 3 decoupled the pyGeo-only geometry path from AeroSandbox — the
neutral loft, frame reconstruction, section extraction, and their whole import
chain (generator services) must build with `aerosandbox` unavailable. All
`aerosandbox` imports in the shared generator modules are lazy (in-function).

This runs in a SUBPROCESS so sys.modules is pristine — a prior test importing
aerosandbox cannot mask a regression. If someone reintroduces a module-level
`import aerosandbox` anywhere in the generator import chain, this fails.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"

# Import the full generator chain + build the pure-math pyGeo frame with
# aerosandbox blocked. Frame reconstruction is numpy-only (no pyGeo package
# required), so this guard runs even where pyGeo/pySpline are not installed.
CHILD = textwrap.dedent(
    """
    import sys, importlib.abc

    class _Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "aerosandbox" or name.startswith("aerosandbox."):
                raise ImportError("aerosandbox is blocked by the decoupling guard")
            return None

    sys.meta_path.insert(0, _Blocker())

    # The shared generator import chain (services -> aerosandbox_adapter,
    # reconstruction_export, export) must import without aerosandbox.
    from pathlib import Path
    import numpy as np
    from aeris.common.config import load_yaml_config
    from aeris.generators.bwb_segmented_v1.services import (
        build_section_geometry_from_sample,
        generate_bwb_planform_from_sample,
    )
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        stations_from_records,
        pygeo_frame_inputs,
    )
    from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    raw = load_yaml_config(Path("configs/geometry/paper1_bwb_pygeo.yaml"))
    gid, g = resolve_generator_and_config(raw)
    gen = get_geometry_generator(gid)
    s = gen.sample_one(g, seed=g.generator.seed)
    pf = generate_bwb_planform_from_sample(s, g)
    sg = build_section_geometry_from_sample(pf, s, g)
    st = tuple(stations_from_records(sg.sections, _resolve_airfoil_database(g)))

    # Pure-math frame reconstruction (the ASB-frame, no ASB object, no pyGeo pkg).
    rot_x, rot_y, rot_z, thickness, err = pygeo_frame_inputs(st, "asb_frame")
    assert err < 1.0e-9, f"frame reconstruction residual too large: {err}"

    assert "aerosandbox" not in sys.modules, "aerosandbox was imported by the pyGeo path"
    print("DECOUPLED_OK", len(st))
    """
)


def test_pygeo_geometry_path_does_not_import_aerosandbox() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"decoupling guard failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "DECOUPLED_OK" in proc.stdout
