"""Interactive meshing for both strategies.

Gmsh runs in process, because it is a Python API and a laptop-tier mesh returns
in seconds - that is what makes the mesh tab feel live.  pyHyp cannot: it lives
in the conda `mach-aero` interpreter, so it is driven exactly the way S6 already
drives it, by writing a runner and launching the other Python.

Neither mesher is reimplemented here.  The workbench builds a POLICY OVERLAY -
a deep copy of the study policy with the user's settings written into it - and
then calls the study's own generator.  The settings a user moves are therefore
the same numbers the study freezes, and a workbench mesh is reproducible from a
policy file rather than from whatever the GUI happened to be holding.
"""

from __future__ import annotations

import contextlib
import copy
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import runs
from .environment import REPO_ROOT, S6_DIR, S7_DIR, STRATEGY_DIR, conda_python, worker_env


@contextlib.contextmanager
def _gmsh_off_main_thread():
    """Let Gmsh initialise on a worker thread.

    `gmsh.initialize` installs its own SIGINT handler, and Python refuses to set
    a signal handler anywhere but the main thread - so meshing from the UI's
    worker died with "signal only works in main thread of the main interpreter"
    before Gmsh had drawn a single cell.  The API already supports skipping that
    step; it is just not the default, so the default is supplied here for the
    duration of one mesh.
    """
    import gmsh

    original = gmsh.initialize

    def initialize(argv=None, readConfigFiles=True, run=False, interruptible=True):
        return original(argv if argv is not None else [], readConfigFiles, run,
                        interruptible=False)

    gmsh.initialize = initialize
    try:
        yield
    finally:
        gmsh.initialize = original

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR), str(S7_DIR.parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


# --------------------------------------------------------------------------- #
# Gmsh                                                                          #
# --------------------------------------------------------------------------- #

GMSH_ALGORITHMS_2D = {
    1: "MeshAdapt",
    5: "Delaunay",
    6: "Frontal-Delaunay",
    7: "BAMG",
    8: "Frontal-Delaunay for quads",
}
GMSH_ALGORITHMS_3D = {1: "Delaunay", 4: "Frontal", 7: "MMG3D", 9: "R-tree", 10: "HXT"}
OPTIMIZERS = ("none", "Netgen", "Relocate3D", "HighOrder")


@dataclass
class GmshSettings:
    """Every knob the mesh tab exposes, in the policy's own units.

    Lengths are fractions of the mean aerodynamic chord, exactly as the policy
    stores them, so a value here and a value in `POLICY.yaml` mean the same
    thing.  `first_cell_height_over_L` is what sets y+, and the prism schedule
    is the part a solver cares most about.
    """

    # Surface sizing
    surface_edge_over_L: float = 0.140
    te_surface_edge_over_L: float = 0.028
    tip_surface_edge_over_L: float = 0.056
    # Boundary layer
    first_cell_height_over_L: float = 2.0e-3
    prism_layers: int = 6
    prism_growth_ratio: float = 1.35
    # Core
    near_core_edge_over_L: float = 0.233
    far_core_edge_over_L: float = 0.490
    wake_edge_over_L: float = 0.190
    core_max_growth_ratio: float = 1.20
    # Far field, in chords
    upstream_over_L: float = 3.0
    downstream_over_L: float = 5.0
    radial_over_L: float = 3.0
    wake_length_over_L: float = 4.0
    # Algorithms
    surface_algorithm: int = 6
    volume_algorithm: int = 1
    optimizer: str = "Netgen"
    optimize_passes: int = 1
    # Provenance
    level: str = "laptop_smoke"
    te_variant: str = "te_1p0mm"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def study_policy() -> dict[str, Any]:
    from S7_unstructured_gmsh_su2.common import load_policy

    return load_policy()


def settings_from_policy(policy: dict[str, Any], level: str) -> GmshSettings:
    """Read one grid level out of the policy into editable settings."""
    block = dict(policy["laptop_smoke"]) if level == "laptop_smoke" \
        else dict(policy["grid_family"]["levels"][level])
    farfield = dict(block.get("farfield") or policy["farfield"])
    candidate = policy["gmsh"]["retries"][0]
    settings = GmshSettings(level=level)
    for key in ("surface_edge_over_L", "te_surface_edge_over_L", "tip_surface_edge_over_L",
                "first_cell_height_over_L", "prism_layers", "prism_growth_ratio",
                "near_core_edge_over_L", "far_core_edge_over_L", "wake_edge_over_L"):
        if key in block:
            setattr(settings, key, type(getattr(settings, key))(block[key]))
    for key in ("upstream_over_L", "downstream_over_L", "radial_over_L", "wake_length_over_L"):
        if key in farfield:
            setattr(settings, key, float(farfield[key]))
    settings.core_max_growth_ratio = float(policy["gmsh"]["core_size_field"]["max_growth_ratio"])
    settings.surface_algorithm = int(candidate["generated_surface_algorithm"])
    settings.volume_algorithm = int(candidate["volume_algorithm"])
    settings.optimizer = str(candidate["optimize"])
    settings.optimize_passes = int(candidate["optimize_passes"])
    return settings


def policy_overlay(settings: GmshSettings, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """A study policy with the user's settings written into the active level."""
    policy = copy.deepcopy(base or study_policy())
    level = settings.level
    target = policy["laptop_smoke"] if level == "laptop_smoke" \
        else policy["grid_family"]["levels"][level]

    for key in ("surface_edge_over_L", "te_surface_edge_over_L", "tip_surface_edge_over_L",
                "first_cell_height_over_L", "near_core_edge_over_L",
                "far_core_edge_over_L", "wake_edge_over_L"):
        target[key] = float(getattr(settings, key))
    target["prism_layers"] = int(settings.prism_layers)
    target["prism_growth_ratio"] = float(settings.prism_growth_ratio)

    farfield = {
        "upstream_over_L": float(settings.upstream_over_L),
        "downstream_over_L": float(settings.downstream_over_L),
        "radial_over_L": float(settings.radial_over_L),
        "wake_length_over_L": float(settings.wake_length_over_L),
    }
    if level == "laptop_smoke":
        target["farfield"] = farfield
    else:
        policy["farfield"] = farfield

    policy["gmsh"]["core_size_field"]["max_growth_ratio"] = float(settings.core_max_growth_ratio)
    candidate = policy["gmsh"]["retries"][0]
    candidate["generated_surface_algorithm"] = int(settings.surface_algorithm)
    candidate["volume_algorithm"] = int(settings.volume_algorithm)
    candidate["optimize"] = settings.optimizer
    candidate["optimize_passes"] = int(settings.optimize_passes)
    return policy


def estimate_gmsh_cells(surface: Any, settings: GmshSettings) -> int:
    """Cheap cell-count estimate, so the user is warned before a slow mesh."""
    from S7_unstructured_gmsh_su2 import gmsh_pipeline

    policy = policy_overlay(settings)
    spec = gmsh_pipeline.resolved_mesh_spec(
        surface, level=settings.level, candidate_index=0, policy=policy)
    try:
        return int(gmsh_pipeline.estimate_cells(surface, spec, policy))
    except Exception:  # noqa: BLE001 - an estimate must never block meshing
        return 0


def run_gmsh(surface: Any, settings: GmshSettings, output_dir: Path,
             *, refine: Any = None, log: Any = None) -> dict[str, Any]:
    """Generate one volume mesh with the study's Gmsh pipeline.

    `refine` carries the workbench's local controls.  They are applied by
    wrapping the study's background-field builder for the duration of the call,
    so the study's own sizing runs first and the local fields are added on top.
    """
    from S7_unstructured_gmsh_su2 import gmsh_pipeline

    from .refinement import RefinementSettings, applied

    output_dir = Path(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    policy = policy_overlay(settings)
    started = time.time()
    if log:
        log(f"Gmsh: level={settings.level} surface={settings.surface_edge_over_L:.4g} L "
            f"layers={settings.prism_layers} growth={settings.prism_growth_ratio:.3g}")

    refine = refine or RefinementSettings()
    reference = surface.metadata["reference_values"]["mean_aerodynamic_chord_m"]
    with _gmsh_off_main_thread(), applied(
            gmsh_pipeline, refine, surface=surface, L=float(reference),
            growth=float(settings.core_max_growth_ratio), log=log) as fields:
        report = gmsh_pipeline.generate_mesh(
            surface, output_dir=output_dir, level=settings.level,
            candidate_index=0, policy=policy)
    if fields.get("workbench_refinement"):
        report["workbench_refinement"] = {
            "fields": len(fields["workbench_refinement"]),
            "settings": refine.as_dict(),
        }
    report["wall_seconds"] = round(time.time() - started, 2)
    report["settings"] = settings.as_dict()
    (output_dir / "workbench_settings.json").write_text(
        json.dumps(settings.as_dict(), indent=2), encoding="utf-8")
    if log:
        cells = report.get("volume_cell_count") or report.get("cells") or "?"
        log(f"Gmsh: done in {report['wall_seconds']:.1f}s, {cells} cells")
    return report


AUDIT_HEADLINE = (
    "surface", "volume", "prisms", "quality", "regional", "source_geometry", "labels")


def su2_mesh_path(report: Mapping[str, Any]) -> Path:
    """The .su2 file a build report points at.

    `mesh_msh` is a plain string but `mesh_su2` is a dict carrying the path
    alongside its digest and marker counts, so the two cannot be read the same
    way - which is exactly the mistake that reached the solver as
    "argument should be a str or an os.PathLike object ... not 'dict'".
    """
    entry = report.get("mesh_su2")
    if isinstance(entry, dict):
        return Path(str(entry["path"]))
    return Path(str(entry))


def audit_gmsh(surface: Any, mesh_dir: Path, settings: GmshSettings,
               *, log: Any = None) -> dict[str, Any]:
    """Run the study's OWN mesh audit against a workbench mesh.

    This is the difference between a mesh that looks right and one that has been
    checked: closure, manifoldness, orientation, label coverage, prism layer
    count and first height, element shape, and the distribution metrics.  The
    audit is the study's, not a workbench re-implementation, so a mesh the
    workbench calls acceptable is acceptable by the same rules the campaign uses.
    """
    from S7_unstructured_gmsh_su2 import mesh_audit

    mesh_dir = Path(mesh_dir)
    policy = policy_overlay(settings)
    with _gmsh_off_main_thread():
        report = mesh_audit.audit_mesh(
            msh_path=mesh_dir / "mesh.msh",
            su2_path=mesh_dir / "mesh.su2",
            surface=surface,
            level=settings.level,
            candidate_index=0,
            output_path=mesh_dir / "mesh_audit.json",
            policy=policy,
        )
    if log:
        summary = audit_summary(report)
        if summary["accepted"]:
            log(f"Mesh audit: ACCEPTED at tier {summary['evidence_tier']}"
                + (f", {len(summary['warnings'])} warnings" if summary["warnings"] else ""))
        else:
            log(f"Mesh audit: REJECTED — {', '.join(summary['failed'])}")
        for row in summary["warnings"]:
            log(f"   warning {row['gate']}: {row['actual']} against {row['limit']}")
    return report


def _format_gate_value(value: Any) -> str:
    return f"{value:.4g}" if isinstance(value, (int, float)) else str(value)[:60]


def _rows(entries: Any) -> list[dict[str, Any]]:
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict) or "name" not in entry:
            continue
        actual, limit = entry.get("actual"), entry.get("limit")
        fmt = _format_gate_value
        out.append({
            "gate": str(entry["name"]),
            "passed": bool(entry.get("passed", False)),
            "actual": fmt(actual),
            "limit": fmt(limit),
        })
    return out


def audit_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Flatten an audit into something a panel can render.

    Distribution metrics are reported as WARNINGS below the development tier,
    because they are resolution dependent and gating them on a diagnostic mesh
    measures the tier rather than the method.  They are shown either way, so a
    laptop mesh cannot look cleaner than it is.
    """
    acceptance = report.get("acceptance", {})
    gates = _rows(acceptance.get("gates"))
    warnings = [row for row in _rows(acceptance.get("warnings")) if not row["passed"]]
    return {
        "accepted": bool(acceptance.get("accepted", False)),
        "evidence_tier": str(acceptance.get("evidence_tier", "")),
        "distribution_gates_enforced": bool(
            acceptance.get("distribution_gates_enforced", False)),
        "rows": gates,
        "warnings": warnings,
        "failed": [r["gate"] for r in gates if not r["passed"]]
                  + list(acceptance.get("failures", [])),
    }


# --------------------------------------------------------------------------- #
# pyHyp                                                                         #
# --------------------------------------------------------------------------- #

def pyhyp_level_choices() -> dict[str, list[str]]:
    """The two DIFFERENT level vocabularies S6 uses, read from their sources.

    The surface levels and the volume levels are unrelated name sets, and using
    one where the other belongs is a KeyError deep inside the mesher.  The
    volume list is further narrowed to the levels that also have a declared wall
    spacing, because `prepare()` is given `first_cell_fraction(level)` and that
    table is smaller than the grid table.
    """
    if str(S6_DIR) not in sys.path:
        sys.path.insert(0, str(S6_DIR))
    from resolution import S6_FIRST_CELL_FRACTION  # noqa: PLC0415
    from strategy_s6 import LEVELS as SURFACE_LEVELS  # noqa: PLC0415

    from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: PLC0415

    # L1-L4 all ask for coarsen=4, which needs every block dimension to survive
    # three halvings.  S6's surface cannot: the spanwise direction is 89 cells
    # (odd, so not even one halving) and the nose and base blocks are 2 cells
    # across.  pyHyp answers "User specified coarsen is 4, can only coarsen 2
    # levels" and stops.  That is why S6's own levels are all coarsen=1, and why
    # offering the L family here was a mistake: it cannot ever work on this
    # topology.  `coarsen_limit` re-derives it from the surface rather than
    # trusting this note.
    order = {"coarse": 0, "smoke": 1, "medium": 2, "fine": 3, "production": 4}
    usable = [name for name, spec in GRID_LEVELS.items() if int(spec["coarsen"]) == 1]
    return {
        "surface": sorted(SURFACE_LEVELS, key=lambda n: order.get(n, 99)),
        "volume": sorted(usable, key=lambda n: order.get(n, 99)),
        "wall_spacing_levels": sorted(S6_FIRST_CELL_FRACTION),
    }


def coarsen_limit(blocks: Any) -> int:
    """How many times pyHyp could halve this surface, from the surface itself."""
    import numpy as np  # noqa: PLC0415

    def halvings(count: int) -> int:
        cells, times = count - 1, 0
        while cells > 1 and cells % 2 == 0:
            cells //= 2
            times += 1
        return times

    worst = 99
    for block in blocks:
        ni, nj = np.asarray(block.xyz).shape[:2]
        worst = min(worst, halvings(ni), halvings(nj))
    return max(1, worst + 1)


def volume_level_has_wall_policy(level: str) -> bool:
    """Whether S6 declares a wall spacing for this level.

    When it does, that spacing is passed as an override.  When it does not, the
    level's own `s0_frac` stands - which is what makes L1-L4 usable.
    """
    if str(S6_DIR) not in sys.path:
        sys.path.insert(0, str(S6_DIR))
    from resolution import S6_FIRST_CELL_FRACTION  # noqa: PLC0415

    return level in S6_FIRST_CELL_FRACTION


@dataclass
class PyHypSettings:
    """The hyperbolic marching controls the workbench actually passes through.

    Every field here reaches `shared.pyhyp_runner.prepare`.  Two former fields
    do not appear, deliberately:

      * `n_constant` moved nothing.  `prepare` takes no such argument, so pyHyp
        ran at the curated default `nConstantStart = 5` whatever the box showed
        - and the box showed 3.
      * `development_index` and `set_name` chose a SECOND geometry.  Geometry is
        now chosen once, on the geometry tab, and the mesh follows it.

    The two level names come from different tables - see `pyhyp_level_choices`.
    """

    volume_level: str = "smoke"
    surface_level: str = "smoke"
    eps_e: float = 1.5
    s0_fraction: float | None = None
    normal_points_override: int | None = None
    grid: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def wall_spacing_fraction(settings: PyHypSettings) -> float | None:
    """The wall spacing this march will actually use, and where it came from.

    A qualified grid carries its own `first_cell_fraction_characteristic`, which
    is NOT the same as `resolution.S6_FIRST_CELL_FRACTION` for the same level
    (G1 is 7.2e-6 against smoke's 8.8e-6).  Selecting a grid therefore has to
    override the level's spacing, or the wall-normal half of the definition is
    silently the wrong one.  `None` means the level's own `s0_frac` stands.
    """
    if settings.s0_fraction is not None:
        return float(settings.s0_fraction)
    if volume_level_has_wall_policy(settings.volume_level):
        if str(S6_DIR) not in sys.path:
            sys.path.insert(0, str(S6_DIR))
        from resolution import first_cell_fraction  # noqa: PLC0415

        return float(first_cell_fraction(settings.volume_level))
    return None


def normal_points(volume_level: str) -> int:
    from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: PLC0415

    return int(GRID_LEVELS[volume_level]["N"])


def effective_normal_points(settings: PyHypSettings) -> int:
    if settings.normal_points_override:
        return int(settings.normal_points_override)
    return normal_points(settings.volume_level)


# The wall-normal counts S6's own atlas levels use, plus the two halvings below
# the smallest of them.  A mesh is `surface quads x (N - 1)` cells, so this is
# the only lever that shrinks the volume WITHOUT coarsening the surface - and
# the surface is the part that has to stay fine, because that is what carries
# the tip-cap quality the production floor measures.
NORMAL_POINT_CHOICES = (33, 49, 65, 97, 129, 193, 257)


@contextlib.contextmanager
def _normal_points_override(level: str, points: int):
    """Register a throwaway pyHyp grid level with a different N.

    `prepare()` takes a level NAME and looks it up in
    `aeris.cfd.meshing.pyhyp_options.GRID_LEVELS`; there is no argument for the
    wall-normal count, and the table has no coarsen=1 entry below N129.  So a
    scratch entry is added under a name the study does not use, and removed
    again - the same mechanism `surface_s6` already uses for
    `strategy_s6.LEVELS`, and for the same reason: no study file is modified and
    no declared level is read, written or shadowed.

    The entry inherits the level's own coarsening and wall spacing, so the only
    thing that changes is N.
    """
    import uuid  # noqa: PLC0415

    from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: PLC0415

    if points == int(GRID_LEVELS[level]["N"]):
        yield level
        return
    scratch = f"__workbench_n{int(points)}_{uuid.uuid4().hex[:6]}"
    declared = dict(GRID_LEVELS)
    GRID_LEVELS[scratch] = dict(GRID_LEVELS[level]) | {"N": int(points)}
    try:
        yield scratch
    finally:
        GRID_LEVELS.pop(scratch, None)
        if dict(GRID_LEVELS) != declared:
            raise RuntimeError("the workbench altered the declared pyHyp grid table")


def estimate_pyhyp_cells(blocks: Any, volume_level: str, points: int = 0) -> int:
    """The volume cell count this march will produce, before it runs.

    pyHyp extrudes the surface rigidly, so the answer is exact rather than an
    estimate: surface quads times wall-normal cell layers, divided by the
    coarsening in each direction.
    """
    from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: PLC0415

    from . import grids  # noqa: PLC0415

    if volume_level not in GRID_LEVELS:
        return 0
    level = GRID_LEVELS[volume_level]
    cells = grids.estimate_cells(blocks, int(points or level["N"]))
    coarsen = max(1, int(level["coarsen"]))
    return int(cells // (4 ** (coarsen - 1)))


def characteristic_length(blocks: Any) -> float:
    from shared.pyhyp_runner import characteristic_length as study_length  # noqa: PLC0415

    return float(study_length(blocks))


def run_pyhyp(settings: PyHypSettings, run: Any, *, blocks: Any,
              surface_info: dict[str, Any], geometry_id: str,
              log: Any = None) -> dict[str, Any]:
    """March a volume mesh in the conda interpreter, and PROVE it is this run's.

    S6 already stages pyHyp this way - `prepare()` writes a runner script and a
    manifest, and the other Python executes it - so the workbench reuses that
    rather than inventing a second path to the same mesher.

    What is new is the definition of success.  It used to be "a file called
    `wing_vol.cgns` exists in the run directory", which is true of a directory
    that still holds the output of a march from an hour ago.  A march now counts
    only when the process returned zero, pyHyp reported `march_completed`, the
    CGNS was written DURING this run, and its digest was recorded at the time.

    There is also no longer a fallback that builds its own surface from a
    development index.  Marching a surface nobody asked for is how the workbench
    came to display one aircraft and mesh another; if there are no blocks, that
    is an error.
    """
    from shared.pyhyp_runner import prepare, read_result  # noqa: PLC0415
    from strategy_s6 import STRATEGY_ID  # noqa: PLC0415

    if not blocks:
        raise RuntimeError("build the geometry before marching: pyHyp needs the "
                           "structured surface from the Geometry tab")

    march_root = Path(run.path) / "march"
    march_root.mkdir(parents=True, exist_ok=True)
    override = wall_spacing_fraction(settings)
    if log:
        log(f"pyHyp: marching the surface from the Geometry tab ({len(blocks)} blocks)")
        log(f"pyHyp: volume level {settings.volume_level} "
            f"(N{effective_normal_points(settings)}), epsE {settings.eps_e}, "
            + (f"s0/L {override:.3e}" if override is not None
               else "level default wall spacing"))

    points = effective_normal_points(settings)
    with _normal_points_override(settings.volume_level, points) as level:
        manifest = prepare(
            strategy_id=STRATEGY_ID,
            geometry_id=geometry_id,
            blocks=blocks,
            out_dir=march_root,
            level=level,
            epse_ladder=(settings.eps_e,),
            s0_fraction_override=override,
        )
    run_dir = Path(manifest["runs"][0]["dir"]).resolve()
    runner = Path(manifest["runs"][0]["runner"]).resolve()
    cgns = run_dir / "wing_vol.cgns"
    # A fresh run directory should never hold one of these.  Recording the
    # digest anyway is what makes "the file changed" checkable rather than
    # assumed, and costs nothing when there is no file.
    prior_digest = runs.existing_digest(cgns)

    if log:
        log(f"pyHyp: marching in {conda_python()}")
    started = time.time()
    log_path = run_dir / "run_stdout.log"
    with log_path.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            [str(conda_python()), str(runner)], cwd=run_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=worker_env())
        for line in process.stdout:  # type: ignore[union-attr]
            handle.write(line)
            if log:
                log(line.rstrip())
        code = process.wait()

    result = read_result(run_dir) or {}
    artifact = runs.claim_output(cgns, produced_after=started, previous_digest=prior_digest)
    march_completed = bool(result.get("march_completed"))
    marched = bool(code == 0 and march_completed and artifact.fresh)

    reasons: list[str] = []
    if code != 0:
        reasons.append(f"pyHyp exited with code {code}")
    if not march_completed:
        reasons.append("pyHyp did not report march_completed")
    if not artifact.fresh:
        reasons.append(f"no fresh volume mesh: {artifact.reason}")

    report = {
        "return_code": code,
        "march_completed": march_completed,
        "wall_seconds": round(time.time() - started, 2),
        "cgns": str(cgns) if marched else None,
        "cgns_artifact": artifact.as_dict(),
        "surface_npz": str(run_dir / "surface_blocks.npz"),
        "log": str(log_path),
        "march_result": result,
        "settings": settings.as_dict(),
        "geometry_id": geometry_id,
        "characteristic_length_m": float(manifest["characteristic_length"]),
        "s0_fraction_used": override,
        "normal_points": points,
        "normal_points_is_override": points != normal_points(settings.volume_level),
        "prepare_manifest": str(Path(march_root) / geometry_id / "prepare_manifest.json"),
        "surface_qualified_grid": surface_info.get("workbench_qualified_grid", ""),
        "marched": marched,
        "failure_reasons": reasons,
    }
    if log:
        log(f"pyHyp: {'complete' if marched else 'FAILED'} in "
            f"{report['wall_seconds']:.1f}s"
            + ("" if marched else " — " + "; ".join(reasons)))
    return report


PRODUCTION_FLOOR = 0.10
WALL_TOLERANCE_M = 1.0e-10


def audit_pyhyp(report: dict[str, Any], *, log: Any = None) -> dict[str, Any]:
    """Reopen the written CGNS and apply S6's own volume gates to it.

    Not a workbench reimplementation: `shared.volume_qc.volume_report` is the
    same V1-V5 report `deform.acceptance_report` scores a governed mesh with,
    and `deform.volume_interface_report` and `deform.first_layer_spacing_report`
    are the study's own conformity and wall-spacing measurements.  Reading the
    file back from disk rather than scoring the array in memory is the point -
    it is the written file that ADflow will open.

    This is the EXPERIMENTAL path's audit.  It is a real audit and a mesh that
    fails it must not be solved, but it is not governed acceptance: there is no
    template, no deformation replay and no registry provenance behind it.
    """
    from deform import first_layer_spacing_report, volume_interface_report  # noqa: PLC0415
    from shared.volume_qc import volume_report  # noqa: PLC0415

    from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: PLC0415

    if not report.get("marched") or not report.get("cgns"):
        return {"mode": "experimental", "state": "NOT_AUDITED", "accepted": False,
                "rows": [], "failed": ["no mesh to audit"],
                "reason": "; ".join(report.get("failure_reasons") or ["no mesh"])}

    path = Path(report["cgns"])
    blocks = read_volume_blocks(path)
    quality = volume_report(blocks)
    interfaces = volume_interface_report(blocks)
    length = float(report.get("characteristic_length_m") or 0.0)
    spacing = (first_layer_spacing_report(blocks, characteristic_length_m=length)
               if length > 0.0 else {})

    requested = report.get("s0_fraction_used")
    realized = spacing.get("median_fraction_characteristic")
    wall_error = (abs(float(realized) - float(requested)) / float(requested)
                  if requested and isinstance(realized, float) and realized == realized
                  else None)

    rows = [
        _audit_row("generation completed", quality.get("generation_completed"),
                   "true", bool(quality.get("generation_completed"))),
        _audit_row("inverted cells", quality.get("inverted_cells"), "0",
                   quality.get("inverted_cells") == 0),
        _audit_row("minimum volume", quality.get("min_volume"), "> 0",
                   isinstance(quality.get("min_volume"), (int, float))
                   and float(quality["min_volume"]) > 0.0),
        _audit_row("min scaled Jacobian", quality.get("min_scaled_quality"),
                   f"> {PRODUCTION_FLOOR:.2f}",
                   isinstance(quality.get("min_scaled_quality"), (int, float))
                   and float(quality["min_scaled_quality"]) > PRODUCTION_FLOOR),
        _audit_row("block interface conformity", interfaces.get("max_mismatch_m"),
                   f"<= {WALL_TOLERANCE_M:g} m",
                   interfaces.get("paired_face_count", 0) > 0
                   and float(interfaces.get("max_mismatch_m", 1.0)) <= WALL_TOLERANCE_M),
        _audit_row("first layer spacing finite", spacing.get("nonfinite_count"),
                   "0 non-finite, 0 non-positive",
                   int(spacing.get("nonfinite_count", 1)) == 0
                   and int(spacing.get("nonpositive_count", 1)) == 0),
        _audit_row("wall coordinate error", wall_error, "<= 5% of requested s0/L",
                   wall_error is not None and wall_error <= 0.05),
        _audit_row("written CGNS digest",
                   (report.get("cgns_artifact") or {}).get("sha256", "")[:12],
                   "recorded for this run",
                   bool((report.get("cgns_artifact") or {}).get("fresh"))),
    ]
    failed = [row["gate"] for row in rows if not row["passed"]]
    summary = {
        "mode": "experimental",
        "state": "MESH_AUDITED_ACCEPTED" if not failed else "MESH_AUDITED_REJECTED",
        "accepted": not failed,
        "cgns": str(path),
        "cgns_sha256": (report.get("cgns_artifact") or {}).get("sha256", ""),
        "cells": quality.get("total_cells"),
        "min_scaled_quality": quality.get("min_scaled_quality"),
        "inverted_cells": quality.get("inverted_cells"),
        "interfaces": {k: interfaces.get(k) for k in
                       ("paired_face_count", "max_mismatch_m")},
        "first_layer_spacing": {k: spacing.get(k) for k in
                                ("median_m", "median_fraction_characteristic")},
        "requested_s0_fraction": requested,
        "rows": rows,
        "failed": failed,
    }
    if log:
        if summary["accepted"]:
            log(f"Volume audit: ACCEPTED, {quality.get('total_cells'):,} cells, "
                f"min scaled Jacobian {quality.get('min_scaled_quality')}")
        else:
            log(f"Volume audit: REJECTED — {', '.join(failed)}")
    return summary


def _audit_row(name: str, actual: Any, limit: str, passed: bool) -> dict[str, Any]:
    if isinstance(actual, float):
        shown = f"{actual:.6g}"
    else:
        shown = "—" if actual is None else str(actual)
    return {"gate": name, "actual": shown, "limit": limit, "passed": bool(passed)}


# --------------------------------------------------------------------------- #
# Mesh -> VTK                                                                   #
# --------------------------------------------------------------------------- #

def gmsh_export_vtk(msh_path: Path, vtk_path: Path) -> Path:
    """Re-export a .msh through the Gmsh API, which VTK can then read."""
    import gmsh

    with _gmsh_off_main_thread():
        gmsh.initialize([])
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(msh_path))
        gmsh.write(str(vtk_path))
    finally:
        gmsh.finalize()
    return vtk_path


def read_volume_mesh(path: Path):
    """Read a volume mesh into a VTK dataset, whatever the study wrote."""
    import vtk

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".msh":
        vtk_path = path.with_suffix(".vtk")
        if not vtk_path.is_file() or vtk_path.stat().st_mtime < path.stat().st_mtime:
            gmsh_export_vtk(path, vtk_path)
        path, suffix = vtk_path, ".vtk"
    if suffix == ".vtk":
        reader = vtk.vtkUnstructuredGridReader()
        reader.SetFileName(str(path))
        reader.ReadAllScalarsOn()
        reader.ReadAllVectorsOn()
    elif suffix == ".vtu":
        reader = vtk.vtkXMLUnstructuredGridReader()
        reader.SetFileName(str(path))
    elif suffix == ".cgns":
        reader = vtk.vtkCGNSReader()
        reader.SetFileName(str(path))
        reader.UpdateInformation()
        reader.EnableAllBases()
        reader.EnableAllCellArrays()
        reader.EnableAllPointArrays()
    else:
        raise ValueError(f"no reader for {path.name}")
    reader.Update()
    return reader.GetOutput()


def iter_blocks(dataset):
    """Yield every leaf dataset, whether or not the input is composite.

    pyHyp writes CGNS, and VTK reads CGNS as a multiblock - thirteen structured
    grids for one wing.  Gmsh gives back a single unstructured grid.  Everything
    downstream has to cope with both, so it goes through here rather than
    assuming a flat dataset and failing with `GetCell` on a multiblock.
    """
    if dataset is None:
        return
    if hasattr(dataset, "NewIterator"):
        walker = dataset.NewIterator()
        walker.InitTraversal()
        while not walker.IsDoneWithTraversal():
            leaf = walker.GetCurrentDataObject()
            if leaf is not None and leaf.GetNumberOfPoints():
                yield leaf
            walker.GoToNextItem()
    else:
        yield dataset


def is_composite(dataset) -> bool:
    return hasattr(dataset, "NewIterator")


def mesh_surface(dataset, *, clip_normal=None, clip_origin=None):
    """The visible surface of a mesh, optionally cut open to show the interior.

    Cutting keeps WHOLE CELLS on one side of the plane rather than slicing
    through them.  Two reasons.  It is what you want when inspecting a mesh -
    the cut face is made of real cell faces, so the boundary-layer stack and the
    growth ratio are visible as they actually are, instead of the triangles a
    clip leaves behind.  And it is the difference between a slider that responds
    and one that does not: measured on the 1.62 M cell pyHyp mesh, extracting
    every block takes 0.2 s, while clipping a SINGLE block takes 84.8 s because
    vtkClipDataSet tetrahedralises every hexahedron it touches.
    """
    import vtk

    if clip_normal is None:
        if is_composite(dataset):
            geometry = vtk.vtkCompositeDataGeometryFilter()
            geometry.SetInputData(dataset)
            geometry.Update()
            return geometry.GetOutput()
        surface = vtk.vtkDataSetSurfaceFilter()
        surface.SetInputData(dataset)
        surface.Update()
        return surface.GetOutput()

    plane = vtk.vtkPlane()
    plane.SetNormal(*clip_normal)
    plane.SetOrigin(*(clip_origin or (0.0, 0.0, 0.0)))

    append = vtk.vtkAppendPolyData()
    pieces = 0
    for block in iter_blocks(dataset):
        extract = vtk.vtkExtractGeometry()
        extract.SetInputData(block)
        extract.SetImplicitFunction(plane)
        extract.ExtractInsideOn()
        extract.ExtractBoundaryCellsOff()
        extract.Update()
        kept = extract.GetOutput()
        if not kept.GetNumberOfCells():
            continue
        surface = vtk.vtkDataSetSurfaceFilter()
        surface.SetInputData(kept)
        surface.Update()
        piece = surface.GetOutput()
        if piece.GetNumberOfPoints():
            append.AddInputData(piece)
            pieces += 1
    if not pieces:
        return vtk.vtkPolyData()
    append.Update()
    return append.GetOutput()


def mesh_slice(dataset, *, normal=(0.0, 1.0, 0.0), origin=(0.0, 0.0, 0.0)):
    """A cut plane through the volume, which is how a mesh is really inspected."""
    import vtk

    plane = vtk.vtkPlane()
    plane.SetNormal(*normal)
    plane.SetOrigin(*origin)
    append = vtk.vtkAppendPolyData()
    pieces = 0
    for block in iter_blocks(dataset):
        cutter = vtk.vtkCutter()
        cutter.SetInputData(block)
        cutter.SetCutFunction(plane)
        cutter.Update()
        piece = cutter.GetOutput()
        if piece.GetNumberOfPoints():
            append.AddInputData(piece)
            pieces += 1
    if not pieces:
        return vtk.vtkPolyData()
    append.Update()
    return append.GetOutput()


def mesh_bounds(dataset) -> tuple[float, ...]:
    """Bounds across every block, since a multiblock reports them per leaf."""
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for block in iter_blocks(dataset):
        bounds = block.GetBounds()
        for axis in range(3):
            lows[axis] = min(lows[axis], bounds[2 * axis])
            highs[axis] = max(highs[axis], bounds[2 * axis + 1])
    if lows[0] == float("inf"):
        return (0.0,) * 6
    return tuple(v for pair in zip(lows, highs, strict=True) for v in pair)


def cell_quality(dataset, measure: str = "scaled_jacobian"):
    """Per-cell quality, so the mesh tab can colour by it rather than assert it."""
    import vtk

    quality = vtk.vtkMeshQuality()
    quality.SetInputData(dataset)
    for setter_name in MEASURE_SETTERS.get(measure, MEASURE_SETTERS["scaled_jacobian"]):
        setter = getattr(quality, setter_name, None)
        if setter is not None:
            try:
                setter()
            except Exception:  # noqa: BLE001 - not every measure suits every cell type
                pass

    if is_composite(dataset):
        output = vtk.vtkMultiBlockDataSet()
        output.SetNumberOfBlocks(0)
        low, high = float("inf"), float("-inf")
        index = 0
        for block in iter_blocks(dataset):
            step = vtk.vtkMeshQuality()
            step.SetInputData(block)
            for setter_name in MEASURE_SETTERS.get(measure, MEASURE_SETTERS["scaled_jacobian"]):
                setter = getattr(step, setter_name, None)
                if setter is not None:
                    try:
                        setter()
                    except Exception:  # noqa: BLE001
                        pass
            step.Update()
            result = step.GetOutput()
            output.SetNumberOfBlocks(index + 1)
            output.SetBlock(index, result)
            array = result.GetCellData().GetArray("Quality")
            if array is not None:
                block_low, block_high = array.GetRange()
                low, high = min(low, block_low), max(high, block_high)
            index += 1
        if low == float("inf"):
            return output, (0.0, 1.0)
        return output, (float(low), float(high))

    quality.Update()
    output = quality.GetOutput()
    array = output.GetCellData().GetArray("Quality")
    if array is None:
        return output, (0.0, 1.0)
    return output, tuple(float(v) for v in array.GetRange())


MEASURE_SETTERS = {
    "scaled_jacobian": ("SetTetQualityMeasureToScaledJacobian",
                        "SetHexQualityMeasureToScaledJacobian"),
    "aspect_ratio": ("SetTetQualityMeasureToAspectRatio",
                     "SetHexQualityMeasureToMaxAspectFrobenius"),
    "condition": ("SetTetQualityMeasureToCondition",
                  "SetHexQualityMeasureToCondition"),
}

CELL_TYPE_NAMES = {5: "Triangle", 9: "Quad", 10: "Tetra", 12: "Hexahedron",
                   13: "Wedge", 14: "Pyramid", 3: "Line", 1: "Vertex"}


def validity_report(dataset) -> dict[str, Any]:
    """Negative and near-degenerate cells, with where they are.

    ADflow answers an inverted grid with "Negative volumes present in grid",
    writes a failed_mesh file and returns nan for every force - after paying for
    partitioning and preprocessing.  Checking here costs a second and says which
    part of the wing is at fault.
    """
    import numpy as np  # noqa: PLC0415
    import vtk  # noqa: PLC0415
    from vtk.util.numpy_support import vtk_to_numpy  # noqa: PLC0415

    quality, _range = cell_quality(dataset, "scaled_jacobian")
    values, centres = [], []
    for block in iter_blocks(quality):
        array = block.GetCellData().GetArray("Quality")
        if array is None:
            continue
        values.append(vtk_to_numpy(array))
        centre = vtk.vtkCellCenters()
        centre.SetInputData(block)
        centre.Update()
        centres.append(vtk_to_numpy(centre.GetOutput().GetPoints().GetData()))
    if not values:
        return {"checked": False}

    value = np.concatenate(values)
    centre = np.concatenate(centres)
    inverted = value <= 0.0
    report = {
        "checked": True,
        "cells": int(value.size),
        "min_scaled_jacobian": round(float(value.min()), 5),
        "inverted_count": int(inverted.sum()),
        "below_0p01": int((value < 0.01).sum()),
        "valid": bool(not inverted.any()),
    }
    if inverted.any():
        bad = centre[inverted]
        report["inverted_bounds_m"] = [round(float(v), 4) for v in (
            bad[:, 0].min(), bad[:, 0].max(), bad[:, 1].min(),
            bad[:, 1].max(), bad[:, 2].min(), bad[:, 2].max())]
        report["inverted_centroid_m"] = [round(float(v), 4) for v in bad.mean(axis=0)]
    return report


def summarize_mesh(dataset) -> dict[str, Any]:
    """Counts, cell types and bounds, for a flat OR a multiblock mesh.

    Cell types come from the type array rather than from GetCell in a loop: a
    pyHyp CGNS carries well over a million cells and instantiating each one to
    read its class name is far too slow to sit in front of a user.
    """
    from vtk.util.numpy_support import vtk_to_numpy

    points = cells = blocks = 0
    counts: dict[str, int] = {}
    for block in iter_blocks(dataset):
        blocks += 1
        points += int(block.GetNumberOfPoints())
        cells += int(block.GetNumberOfCells())
        if block.IsA("vtkStructuredGrid") or block.IsA("vtkRectilinearGrid"):
            counts["Hexahedron"] = counts.get("Hexahedron", 0) + int(block.GetNumberOfCells())
            continue
        types = getattr(block, "GetCellTypesArray", lambda: None)()
        if types is not None:
            values, occurrences = np.unique(vtk_to_numpy(types), return_counts=True)
            for value, occurrence in zip(values, occurrences, strict=True):
                name = CELL_TYPE_NAMES.get(int(value), f"type{int(value)}")
                counts[name] = counts.get(name, 0) + int(occurrence)

    bounds = mesh_bounds(dataset)
    summary = {
        "points": points,
        "cells": cells,
        "cell_types": counts,
        "bounds_m": [round(v, 5) for v in bounds],
        "extent_m": [round(bounds[1] - bounds[0], 5),
                     round(bounds[3] - bounds[2], 5),
                     round(bounds[5] - bounds[4], 5)],
    }
    if blocks > 1:
        summary["blocks"] = blocks
    return summary
