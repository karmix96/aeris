"""The app's engine: a wing from a set, from its numbers or from a file; then its geometry (Stage 1), surface mesh
(Stage 2) and volume mesh (Stage 3). No Streamlit here, so the tests can run it.

Every build calls the stage code itself (the cfdauto package), with its own rules and checks: nothing is copied, and
nothing in cfdauto is changed. The hold-out sets are sealed: they are never offered and never loaded.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]                   # CFD_Automation
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cfdauto.geometry import airfoils as airfoil_db           # noqa: E402
from cfdauto.geometry.build import SEALED_SETS, build_spec, load_set   # noqa: E402
from cfdauto.geometry.loft import build_loft                  # noqa: E402
from cfdauto.geometry.params import STATIONS, VARIABLES, load_config, mid_vector, resolve   # noqa: E402
from cfdauto.geometry.sections import build_wing_sections     # noqa: E402
from cfdauto.mesh.surface import Wing, build_surface          # noqa: E402
from cfdauto.mesh.surface import mesh_name as surface_name    # noqa: E402
from cfdauto.mesh.surface import write as write_surface       # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume  # noqa: E402
from cfdauto.volume.volume import mesh_name as volume_name    # noqa: E402
from cfdauto.volume.volume import write as write_volume       # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
SETS = ("reference", "training_focus", "training_full", "corner1", "corner2")    # never the hold-outs
LEVELS = ("VC", "C", "M", "F")
RES = (1e5, 3e5, 1e6, 4e6)                                     # the Stage 0 Re levels (decision 78)
OUT = ROOT / "app" / "output"                                  # what the app writes (not in git)

# The 17 variables in words (lengths in mean chords: every wing is built at unit mean chord, decision 70).
LABEL = {
    "c2_ratio": "chord ratio c2", "c3_ratio": "chord ratio c3", "c4_ratio": "chord ratio c4",
    "semi_span_m": "semi-span (mean chords)", "aspect_ratio": "aspect ratio",
    "b3_ratio": "b3 ratio (outer panel share)", "split_ratio": "split ratio (b1 between root and b2)",
    "sweep1_deg": "sweep, panel 1 (deg)", "sweep2_deg": "sweep, panel 2 (deg)", "sweep3_deg": "sweep, panel 3 (deg)",
    "twist0_deg": "twist at b0 (deg)", "twist1_deg": "twist at b1 (deg)", "twist2_deg": "twist at b2 (deg)",
    "twist3_deg": "twist at b3 (deg)", "dihedral_p1_deg": "dihedral, panel 1 (deg)",
    "dihedral_p2_deg": "dihedral, panel 2 (deg)", "dihedral_p3_deg": "dihedral, panel 3 (deg)",
}
CHORD_LAW = {"stations": "c2, c3, c4: chords at b1, b2, b3 as fractions of the root chord",
             "per_panel": "c2, c3, c4: each panel's own taper (outer chord / inner chord)",
             "linear_taper": "c4: tip chord / root chord; c2 and c3 follow (straight edges)"}


# --- the wing ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class WingInput:
    """One wing: its type and its full design vector (the 17 numbers and the four sections)."""
    wing_type: str
    vector: dict
    source: str                     # in words: "BWB reference 0", "created", "file wing.json"
    set_name: str = "custom"
    index: int = -1

    def key(self) -> str:
        return json.dumps({"type": self.wing_type, "vector": self.vector}, sort_keys=True)

    def to_json(self) -> str:
        return json.dumps({"wing_type": self.wing_type, "source": self.source, "vector": self.vector}, indent=2)


@lru_cache(maxsize=1)
def config():
    return load_config()


def spec(wing_type: str, space: str = "focus"):
    """The type's rules: the focus space (realistic ranges) or the full space (what the generator supports)."""
    c = config()
    return c.types[wing_type] if space == "focus" else c.full[wing_type]


def _open(wing_type: str, set_name: str) -> dict:
    if set_name in SEALED_SETS or set_name not in SETS:
        raise PermissionError(f"{set_name!r} is not offered here (the hold-out sets are sealed)")
    return load_set(wing_type, set_name)


def set_size(wing_type: str, set_name: str) -> int:
    return len(_open(wing_type, set_name)["vectors"])


def set_space(wing_type: str, set_name: str) -> str:
    return "focus" if _open(wing_type, set_name).get("space", "focus") == "focus" else "full"


def from_set(wing_type: str, set_name: str, index: int) -> WingInput:
    vec = _open(wing_type, set_name)["vectors"][index]
    return WingInput(wing_type, resolve(spec(wing_type), vec), f"{TYPE_NAME[wing_type]} {set_name} {index}",
                     set_name, int(index))


def middle(wing_type: str, space: str = "focus") -> WingInput:
    return WingInput(wing_type, resolve(spec(wing_type), mid_vector(spec(wing_type, space))), "created")


def from_values(wing_type: str, values: dict, airfoils: list[str], source: str = "created") -> WingInput:
    """A wing from the free variables (the rest is derived by the type's laws) and four section names."""
    for n in airfoils:
        if not airfoil_db.exists(n):
            raise ValueError(f"section {n!r} not found (project files, the AERIS database or a NACA 4/5-digit name)")
    vec = {**{v: 0.0 for v in VARIABLES}, **{k: float(x) for k, x in values.items()}, "airfoils": list(airfoils)}
    return WingInput(wing_type, resolve(spec(wing_type), vec), source)


def from_json(text: str, wing_type: str | None = None, name: str = "file") -> WingInput:
    """The app's own file ({"wing_type", "vector"}) or a Stage 1 vector.json (then the type comes from the caller)."""
    d = json.loads(text)
    vec = d.get("vector", d)
    t = d.get("wing_type", wing_type)
    if t not in TYPES:
        raise ValueError("the file does not say the wing type: choose it, then load the file again")
    missing = [v for v in VARIABLES if v not in vec and v not in spec(t).derived]
    if missing:
        raise ValueError(f"the file misses {', '.join(missing)}")
    return WingInput(t, resolve(spec(t), vec), f"file {name}")


def in_space(w: WingInput, space: str) -> list[str]:
    """The free variables outside the chosen space's ranges (empty: the wing is inside)."""
    s = spec(w.wing_type, space)
    return [v for v in s.free_variables if not s.ranges[v][0] - 1e-9 <= w.vector[v] <= s.ranges[v][1] + 1e-9]


# --- the builds -------------------------------------------------------------------------------------------------

@dataclass
class Geometry:
    wing: WingInput
    summary: dict          # Stage 1: passed, the gate and reason if refused, labels, area, MAC, aspect ratio
    stations: list | None
    loft: object | None
    seconds: float

    @property
    def passed(self) -> bool:
        return bool(self.summary.get("passed"))

    def mesh_wing(self) -> Wing:
        return Wing(self.wing.wing_type, self.wing.set_name, self.wing.index, self.summary["input_hash"], self.loft)


def build_geometry(w: WingInput) -> Geometry:
    """Stage 1: build, measure, label and check the wing (the four gates that refuse), then its loft for the mesh."""
    t0 = time.time()
    s, c = spec(w.wing_type), config()
    summary = build_spec(s, w.vector, c.te, w.wing_type, out_dir=None, iges=False)
    stations = loft = None
    if summary.get("passed"):
        _, stations = build_wing_sections(s, w.vector, c.te)
        loft = build_loft(stations, 2)
    return Geometry(w, summary, stations, loft, time.time() - t0)


def build_surface_mesh(g: Geometry, level: str, re: float):
    """Stage 2 at one level and Re (the transition band on, decision 81)."""
    t0 = time.time()
    sm = build_surface(g.loft, float(re), level)
    sm.info["app_seconds"] = round(time.time() - t0, 2)
    return sm


def count_cells(sm) -> dict:
    """Stage 3 cells and RAM without building (the same laws as the build)."""
    return count_volume(sm)


def build_volume_mesh(sm):
    """Stage 3 on the surface mesh (rule set 2)."""
    return build_volume(sm)


def ram_gib(cells: float) -> dict:
    """ADflow memory by S8's two laws (two-point fits at 0.57 and 1.11 M cells; decision 112): a guide, not a
    measurement (decision 113: V7 measures it)."""
    m = cells / 1e6
    return {"ANK only": 2.69 + 7.23 * m, "ANK then NK": 1.51 + 9.46 * m}


# --- what the volume mesh holds, for the pictures ---------------------------------------------------------------

PLANE_BLOCKS = ("WU", "CU", "CN", "CL", "WL", "B")
BLOCK_NAME = {"WU": "upper wake", "CU": "upper side", "CN": "nose arc", "CL": "lower side", "WL": "lower wake",
              "B": "base", "CAP": "tip cap"}


def planes(vm) -> list[dict]:
    """Every station plane in order, root to far field: the wing stations (blocks *_in), then past the tip (*_out,
    its first plane is the tip plane again, so it is skipped)."""
    b = vm.blocks
    n_in = b["CU_in"].shape[2]
    n_out = b["CU_out"].shape[2]
    out = [{"side": "in", "k": k, "y": float(b["CU_in"][0, 0, k, 1])} for k in range(n_in)]
    out += [{"side": "out", "k": k, "y": float(b["CU_out"][0, 0, k, 1])} for k in range(1, n_out)]
    return out


def plane_grids(vm, side: str, k: int) -> dict:
    """The blocks of one station plane: name -> (ni, nj, 3); past the tip, the tip cap's slice too."""
    out = {n: vm.blocks[f"{n}_{side}"][:, :, k] for n in PLANE_BLOCKS}
    if side == "out":
        out["CAP"] = vm.blocks["CAP"][:, :, k]
    return out


def block_table(vm) -> list[dict]:
    rows = []
    for n, a in vm.blocks.items():
        ni, nj, nk = a.shape[:3]
        base = n.split("_")[0]
        rows.append({"block": n, "what": BLOCK_NAME.get(base, base) + (" (past the tip)" if n.endswith("_out") else ""),
                     "nodes i × j × k": f"{ni} × {nj} × {nk}", "cells": int((ni - 1) * (nj - 1) * (nk - 1))})
    return rows


def check_rows(checks, review=()) -> list[dict]:
    rows = []
    for c in checks:
        d = c.as_dict()
        rows.append({"check": d.get("n", ""), "name": d["name"], "result": "pass" if d["passed"] else "FAIL",
                     "value": _num(d["value"]), "limit": d["limit"], "note": d.get("note", "")})
    for r in review or ():
        rows.append({"check": "", "name": str(r), "result": "review", "value": "", "limit": "", "note": ""})
    return rows


def _num(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if x == 0 or 1e-3 <= abs(x) < 1e5:
        return f"{x:.4g}"
    return f"{x:.3e}"


# --- writing ----------------------------------------------------------------------------------------------------

def write_wing(g: Geometry) -> Path:
    """Stage 1 wing folder (vector, stations, sections, measured, labels, gates; IGES with pyGeo)."""
    c = config()
    out = OUT / "wings" / f"{g.wing.wing_type}_{g.summary['input_hash'][:8]}"
    build_spec(spec(g.wing.wing_type), g.wing.vector, c.te, g.wing.wing_type, out_dir=out, iges=True)
    (out / "app_wing.json").write_text(g.wing.to_json())
    return out


def write_surface_mesh(g: Geometry, sm) -> Path:
    w = g.mesh_wing()
    return write_surface(sm, w, OUT / "surface" / surface_name(sm, w))


def write_volume_mesh(g: Geometry, vm, formats=("npz", "cgns", "su2")) -> Path:
    w = g.mesh_wing()
    return write_volume(vm, w, OUT / "volume" / volume_name(vm, w), formats=formats)


def folder_files(path: Path) -> list[dict]:
    return [{"file": p.name, "MB": round(p.stat().st_size / 1e6, 2)} for p in sorted(Path(path).iterdir()) if p.is_file()]


def wall_ring(sm, k: int) -> np.ndarray:
    """The wing section at surface station k: (n_ring, 3)."""
    return sm.wing[:, k, :]


def station_names() -> tuple[str, ...]:
    return STATIONS
