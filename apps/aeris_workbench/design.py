"""One geometry, one fingerprint, one case - for everything downstream.

The bug this module exists to remove: the sliders built a pyGeo case that fed
the viewport, the planform summary and the solver's `areaRef`/`chordRef`, while
the structured surface pyHyp actually marched was rebuilt from
`build_locked_surface(set_name, index)` - a DIFFERENT design out of the locked
development set.  The workbench could therefore show one aircraft, mesh a
second, and hand ADflow the references of the first.  Nothing in the interface
said so, and every number it reported looked internally consistent.

So geometry is now an explicit source with exactly two values, and a case
carries a FINGERPRINT that every later artifact is stamped with.  If the mesh's
fingerprint is not the geometry's, the two are not the same aircraft and the app
can say so instead of quietly proceeding.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import geometry as geo

INTERACTIVE = "interactive"
DEVELOPMENT_INDEX = "development_index"
SOURCES = (INTERACTIVE, DEVELOPMENT_INDEX)

SOURCE_LABELS = {
    INTERACTIVE: "Interactive design",
    DEVELOPMENT_INDEX: "Development-set index",
}


def fingerprint(payload: Any) -> str:
    """A short, stable digest of anything JSON-representable.

    Short because it is shown in the interface and has to be comparable at a
    glance; sixteen hex characters is 64 bits, which is far beyond what a
    session can collide.
    """
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def design_fingerprint(source: str, values: dict[str, float] | None,
                       index: int | None) -> str:
    if source not in SOURCES:
        raise ValueError(f"unknown geometry source {source!r}")
    if source == DEVELOPMENT_INDEX:
        return fingerprint({"source": source, "set": geo.DEVELOPMENT_SET,
                            "index": int(index or 0)})
    rounded = {key: round(float(value), 10) for key, value in sorted((values or {}).items())}
    return fingerprint({"source": source, "values": rounded})


@dataclass
class GeometryCase:
    """One pyGeo case and everything derived from it, under one fingerprint."""

    source: str
    fingerprint: str
    case: Any
    values: dict[str, float]
    index: int | None
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        if self.source == DEVELOPMENT_INDEX:
            return f"{geo.DEVELOPMENT_SET}[{self.index:03d}]"
        return "interactive"

    @property
    def geometry_id(self) -> str:
        """The identifier S6's own staging uses for this geometry.

        The development set keeps S6's own naming so an indexed build is
        directly comparable with a study artifact; an interactive design gets a
        name that cannot be mistaken for a locked one.
        """
        if self.source == DEVELOPMENT_INDEX:
            return f"{geo.DEVELOPMENT_SET}_{int(self.index or 0):03d}"
        return f"interactive_{self.fingerprint}"

    @property
    def pygeo_result(self) -> Any:
        return self.case.pygeo_result

    def reference_values(self) -> dict[str, float]:
        return geo.reference_values(self.case)

    def flow_references(self) -> dict[str, float]:
        """`areaRef` and `chordRef`, from THIS case and no other.

        S6's own campaign halves the reference area before handing it to ADflow
        (`campaign.solve_case`: `area_ref=0.5 * refs["area_m2"]`) because the
        geometry is a full-span planform while the mesh is a half model.  The
        workbench used the whole area, so every coefficient it produced was low
        by a factor of two against the study's own numbers for the same design.
        """
        summary = self.summary or geo.planform_summary(self.case)
        reference = summary.get("reference") or self.reference_values()
        area = float(reference.get("area_m2", summary.get("area_m2", 0.0)))
        chord = float(reference.get("mean_aerodynamic_chord_m", summary.get("mac_m", 0.0)))
        return {"area_ref_m2": 0.5 * area, "chord_ref_m": chord}

    def provenance(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_label": SOURCE_LABELS[self.source],
            "design_fingerprint": self.fingerprint,
            "geometry_id": self.geometry_id,
            "development_set": geo.DEVELOPMENT_SET if self.source == DEVELOPMENT_INDEX else None,
            "development_index": self.index,
            "flow_references": self.flow_references(),
        }


def indexed_design_values(index: int) -> dict[str, float]:
    """The locked development design at one index, as slider values.

    Sweeps are stored negative-aft in the sample and shown as magnitudes, the
    same convention `geometry.design_variables` uses, so synchronising the
    sliders to an indexed geometry puts each slider where the user would have
    had to drag it to reproduce that design.
    """
    from shared.geometry_sets import sample  # noqa: PLC0415

    values = dict(sample(geo.DEVELOPMENT_SET, int(index)).to_dict())
    for key in geo.SWEEP_VARIABLES:
        if key in values:
            values[key] = abs(float(values[key]))
    return {key: float(value) for key, value in values.items()
            if key in geo.VARIABLE_META and isinstance(value, (int, float))}


def development_set_size() -> int:
    from shared.geometry_sets import design_matrix  # noqa: PLC0415

    matrix, _names = design_matrix(geo.DEVELOPMENT_SET)
    return int(matrix.shape[0])


def build(source: str, *, values: dict[str, float] | None = None,
          index: int | None = None, output_dir: Path) -> GeometryCase:
    """Build the ONE pyGeo case this workbench is going to use.

    Both sources end in the same object, so nothing downstream has to know
    which one it came from - it asks the case for its surface, its summary and
    its references, and gets answers that cannot disagree with each other.
    """
    if source not in SOURCES:
        raise ValueError(f"unknown geometry source {source!r}")
    output_dir = Path(output_dir)

    if source == DEVELOPMENT_INDEX:
        index = int(index or 0)
        values = indexed_design_values(index)
        case = _build_indexed(index, output_dir)
    else:
        values = {key: float(value) for key, value in (values or {}).items()}
        index = None
        case = geo.build_case(values, output_dir)

    if getattr(case, "pygeo_result", None) is None:
        raise RuntimeError("pyGeo did not produce the master geometry")

    built = GeometryCase(
        source=source,
        fingerprint=design_fingerprint(source, values, index),
        case=case,
        values=values,
        index=index,
    )
    built.summary = geo.planform_summary(case)
    return built


def _build_indexed(index: int, output_dir: Path) -> Any:
    """S6's own locked geometry builder, at one index."""
    from .environment import S6_DIR  # noqa: PLC0415

    if str(S6_DIR) not in sys.path:
        sys.path.insert(0, str(S6_DIR))
    from strategy_s6 import build_pygeo_case  # noqa: PLC0415

    return build_pygeo_case(geo.DEVELOPMENT_SET, int(index), Path(output_dir))
