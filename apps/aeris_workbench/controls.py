"""Every visible S6 control, declared once, with the input it actually reaches.

Three faults in the old mesh tab share one cause - controls that existed in the
interface and nowhere else:

  * "Constant layers" showed 3 and moved nothing.  `shared.pyhyp_runner.prepare`
    takes no such argument, so pyHyp ran at the schema default of 5 (see
    `pyhyp_options.CuratedOption("n_constant_start", "nConstantStart", int, 5)`)
    no matter what the box said.
  * "Design index" and "Surface level" appeared on the Mesh tab as well as on
    Geometry, so the surface shown and the surface marched could disagree.
  * Nothing was range-checked, so a typo went to the mesher rather than to a
    validation message.

The fix is to declare the controls in ONE table that the layout is built from
and the tests read back.  A control that is not in this table is not drawn, and
every control in it names the effective input it lands on - which is what makes
"does this knob do anything?" a question with a testable answer.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable

from .environment import REPO_ROOT, S6_DIR, STRATEGY_DIR

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR), str(S6_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Beyond this a march is not a workbench interaction any more; the ceiling is
# advisory for the estimate and hard for the validator.
MAX_ESTIMATED_CELLS = 40_000_000


def _level_span(attribute: str) -> tuple[int, int]:
    """Bracket one surface count across S6's OWN declared levels.

    The floor is the coarsest value S6 declares and the ceiling is four times
    the finest.  Below the floor there is no S6 level to compare against; above
    the ceiling the surface is far outside anything the study has marched.  Both
    ends are derived from `strategy_s6.LEVELS` rather than invented here, so a
    new S6 level widens the range automatically.
    """
    from strategy_s6 import LEVELS  # noqa: PLC0415

    values = [int(getattr(spec, attribute)) for spec in LEVELS.values()]
    return min(values), 4 * max(values)


@dataclass(frozen=True)
class Control:
    """One visible control and the effective input it reaches."""

    key: str
    label: str
    help: str
    kind: str                      # "int" | "float" | "choice"
    target: str                    # the effective input this lands on
    state: str                     # the client state path the widget binds to
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1.0
    unit: str = ""
    choices: Callable[[], list[Any]] | None = None
    governed: bool = False         # part of a governed grid definition
    experimental: bool = False     # arbitrary, outside the qualified family

    def validate(self, value: Any) -> str:
        """The reason this value is unusable, or an empty string."""
        try:
            number = int(value) if self.kind == "int" else float(value)
        except (TypeError, ValueError):
            return f"{self.label}: {value!r} is not a number"
        if self.kind == "int" and float(value) != float(number):
            return f"{self.label}: must be a whole number, got {value}"
        if self.minimum is not None and number < self.minimum:
            return f"{self.label}: {number:g} is below the minimum {self.minimum:g}"
        if self.maximum is not None and number > self.maximum:
            return f"{self.label}: {number:g} is above the maximum {self.maximum:g}"
        return ""

    def coerce(self, value: Any) -> Any:
        return int(value) if self.kind == "int" else float(value)


def surface_controls() -> list[Control]:
    """The structured-surface controls.

    These are EXPERIMENTAL by construction.  S6 qualifies whole levels, not
    individual counts, so any combination that is not one of G1/G2/G3 is a
    surface the study has no acceptance evidence for.  They are still worth
    having - a refinement UI you cannot vary teaches nothing - but they are
    labelled for what they are, and they change the structured surface only.
    They are NOT arbitrary 3D local refinement: pyHyp marches this surface
    rigidly outward, so there is no way to refine one region of the volume
    without refining the surface patch beneath it.
    """
    chord_min, chord_max = _level_span("chord_points")
    end_min, end_max = _level_span("end_points")
    collar_min, collar_max = _level_span("collar_points")
    span_min, span_max = _level_span("span_cells")
    return [
        Control("chord_points", "Chordwise divisions",
                "Points along each chordwise arc of the structured surface",
                "int", "strategy_s6.LevelSpec.chord_points", "s6_surface.chord_points",
                chord_min, chord_max, step=2, experimental=True, governed=True),
        Control("span_cells", "Spanwise divisions",
                "Spanwise cells - the lever for trailing-edge aspect ratio",
                "int", "strategy_s6.build_surface(span_cells=)", "s6_surface.span_cells",
                span_min, span_max, step=2, experimental=True, governed=True),
        Control("end_points", "LE/TE divisions",
                "Points across the leading and trailing edge blocks",
                "int", "strategy_s6.LevelSpec.end_points", "s6_surface.end_points",
                end_min, end_max, step=1, experimental=True, governed=True),
        Control("collar_points", "Tip collar divisions",
                "Points around each block of the six-block tip cap",
                "int", "strategy_s6.LevelSpec.collar_points", "s6_surface.collar_points",
                collar_min, collar_max, step=2, experimental=True, governed=True),
        Control("span_max_cell_m", "Max spanwise cell",
                "Largest spanwise cell allowed by the clustering",
                "float", "strategy_s6.LevelSpec.span_max_cell_m", "s6_surface.span_max_cell_m",
                1.0e-4, 1.0, step=0.001, unit="m", experimental=True),
        Control("end_scale", "LE/TE clustering",
                "Clustering strength at the leading and trailing edges",
                "float", "strategy_s6.build_surface(end_scale=)", "s6_surface.end_scale",
                1.0, 40.0, step=0.5, experimental=True),
        Control("te_abs_m", "TE thickness",
                "Absolute trailing-edge opening",
                "float", "strategy_s6.build_surface(te_abs_m=)", "s6_surface.te_abs_m",
                1.0e-5, 0.01, step=0.0001, unit="m", experimental=True),
        Control("te_floor_frac", "TE floor",
                "Trailing-edge opening floor, as a fraction of local chord",
                "float", "strategy_s6.build_surface(te_floor_frac=)", "s6_surface.te_floor_frac",
                1.0e-5, 0.05, step=0.001, experimental=True),
        Control("tip_first_cell_frac_of_tip_chord", "Tip first cell",
                "First spanwise cell at the tip, as a fraction of tip chord",
                "float", "strategy_s6.build_surface(tip_first_cell_frac_of_tip_chord=)",
                "s6_surface.tip_first_cell_frac_of_tip_chord",
                1.0e-5, 0.2, step=0.0005, experimental=True),
    ]


def march_controls() -> list[Control]:
    """The pyHyp marching controls the workbench actually passes through.

    `eps_e` reaches `prepare(epse_ladder=)`; the volume level reaches
    `prepare(level=)` and through it both the wall-normal point count and the
    coarsening.  There is no third control here, and in particular no
    "constant layers": `prepare` has no such parameter and pyHyp therefore runs
    at the curated default of 5 whatever a box might claim.
    """
    from shared.gates import EPSE_LADDER  # noqa: PLC0415

    return [
        Control("volume_level", "Wall-normal level",
                "S6 volume level: wall-normal point count and coarsening",
                "choice", "shared.pyhyp_runner.prepare(level=)", "pyhyp_volume_level",
                choices=_volume_level_choices),
        Control("eps_e", "Smoothing epsE",
                f"Explicit smoothing, from S6's frozen ladder {EPSE_LADDER}",
                "float", "shared.pyhyp_runner.prepare(epse_ladder=)", "pyhyp_eps_e",
                min(EPSE_LADDER), max(EPSE_LADDER), step=0.5),
        Control("normal_points_override", "Wall-normal points",
                "Points across the boundary layer; cells = surface quads x (N-1)",
                "int", "shared.pyhyp_runner.prepare(level=) via a scratch grid level",
                "pyhyp_normal_points", 17, 257, step=16),
        Control("s0_fraction", "Wall spacing s0/L",
                "First cell height as a fraction of the characteristic length",
                "float", "shared.pyhyp_runner.prepare(s0_fraction_override=)",
                "pyhyp_s0_fraction", 1.0e-8, 1.0e-3, step=1.0e-6, governed=True),
    ]


def _volume_level_choices() -> list[str]:
    from .meshing import pyhyp_level_choices  # noqa: PLC0415

    return list(pyhyp_level_choices()["volume"])


def all_controls() -> list[Control]:
    return surface_controls() + march_controls()


def by_key() -> dict[str, Control]:
    return {control.key: control for control in all_controls()}


def validate(values: dict[str, Any]) -> list[str]:
    """Every reason this settings dict cannot be meshed."""
    controls = by_key()
    problems: list[str] = []
    for key, value in values.items():
        control = controls.get(key)
        if control is None or control.kind == "choice":
            continue
        if reason := control.validate(value):
            problems.append(reason)
    return problems


def coerce(values: dict[str, Any]) -> dict[str, Any]:
    """Clamp a settings dict into range, leaving unknown keys alone."""
    controls = by_key()
    out = dict(values)
    for key, value in values.items():
        control = controls.get(key)
        if control is None or control.kind == "choice":
            continue
        try:
            number = control.coerce(value)
        except (TypeError, ValueError):
            continue
        if control.minimum is not None:
            number = max(number, control.coerce(control.minimum))
        if control.maximum is not None:
            number = min(number, control.coerce(control.maximum))
        out[key] = number
    return out


def coarsening_problem(blocks: Any, volume_level: str) -> str:
    """Whether this surface survives the coarsening the level asks for.

    pyHyp halves every block dimension `coarsen - 1` times and stops with
    "User specified coarsen is N, can only coarsen M levels" if any of them will
    not divide.  S6's own levels are all coarsen=1 so this normally passes, but
    the check is cheap and the failure is otherwise a crash deep in the mesher.
    """
    from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: PLC0415

    from .meshing import coarsen_limit  # noqa: PLC0415

    if volume_level not in GRID_LEVELS:
        return f"{volume_level!r} is not a known pyHyp grid level"
    wanted = int(GRID_LEVELS[volume_level]["coarsen"])
    if wanted <= 1:
        return ""
    possible = coarsen_limit(blocks)
    if possible < wanted:
        return (f"{volume_level} asks pyHyp to coarsen {wanted} levels but this "
                f"surface only survives {possible}; its block dimensions do not "
                "halve that many times")
    return ""


def size_problem(estimated_cells: int) -> str:
    if estimated_cells > MAX_ESTIMATED_CELLS:
        return (f"{estimated_cells:,} cells is beyond the {MAX_ESTIMATED_CELLS:,} "
                "cell ceiling for an interactive march; choose a coarser grid")
    return ""
