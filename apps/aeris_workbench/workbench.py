"""The workbench shell: geometry, mesh, solver and post, over one 3D viewport.

Both strategies get the same four-stage shell because the workflow is the same;
what differs is which mesher and which solver sit behind stages two and three.
That is expressed as a `StrategyProfile` rather than as two copies of the UI, so
a change to the layout lands in both applications at once.

Long work never runs on the UI thread.  Geometry, meshing and solving all go to
a worker, and the interface polls a snapshot - which is what keeps the window
responsive while a mesh builds or a solver runs.
"""

from __future__ import annotations

import asyncio
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from trame.app import get_server
from trame.decorators import TrameApp, change

from . import charts, controls, design, governed, grids, meshing, runs, solvers, surface_s6
from . import geometry as geo
from . import postprocess as post
from . import refinement as refine_mod
from .environment import WORKSPACE, available_memory_gib, configured_paths, cpu_count, detect
from .viewer import COLORMAPS, Scene

GRID_LEVELS = ("laptop_smoke", "coarse", "medium", "fine")
TE_VARIANTS = ("te_0p5mm", "te_1p0mm", "te_1p5mm")


@dataclass
class StrategyProfile:
    """What separates the two applications."""

    key: str
    title: str
    subtitle: str
    mesher: str                  # "gmsh" | "pyhyp"
    solver: str                  # "su2"  | "adflow"
    mesher_label: str
    solver_label: str
    accent: str = "#4da3ff"


S7_PROFILE = StrategyProfile(
    key="S7", title="AERIS S7 Workbench",
    subtitle="pyGeo · Gmsh · SU2",
    mesher="gmsh", solver="su2",
    mesher_label="Gmsh unstructured", solver_label="SU2 RANS",
    accent="#4da3ff",
)
S6_PROFILE = StrategyProfile(
    key="S6", title="AERIS S6 Workbench",
    subtitle="pyGeo · pyHyp · ADflow",
    mesher="pyhyp", solver="adflow",
    mesher_label="pyHyp hyperbolic", solver_label="ADflow RANS",
    accent="#ff8a4c",
)


class Job:
    """A single background task with a log the UI can read while it runs."""

    def __init__(self) -> None:
        self.busy = False
        self.stage = ""
        self.error = ""
        self.lines: list[str] = []
        self._lock = threading.Lock()

    def log(self, message: str) -> None:
        with self._lock:
            self.lines.append(str(message))
            if len(self.lines) > 2000:
                del self.lines[:1000]

    def tail(self, count: int = 200) -> list[str]:
        with self._lock:
            return self.lines[-count:]

    def start(self, stage: str) -> None:
        with self._lock:
            self.busy, self.stage, self.error = True, stage, ""

    def finish(self, error: str = "") -> None:
        with self._lock:
            self.busy, self.error = False, error


@TrameApp()
class Workbench:
    def __init__(self, profile: StrategyProfile, server=None, environment=None):
        self.profile = profile
        self.server = server or get_server(f"aeris_{profile.key.lower()}", client_type="vue3")
        self.scene = Scene()
        self.scene.show_orientation_axes()
        self.job = Job()

        self.workspace = WORKSPACE / profile.key.lower()
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env = environment or detect()
        # ONE geometry case.  `design.GeometryCase` carries the pyGeo result,
        # the planform summary, the solver references and a fingerprint, so the
        # viewport, the mesh and the solver cannot be looking at different
        # aircraft - which is exactly what they used to do.
        self.geometry: design.GeometryCase | None = None
        self.case: Any = None
        self.surface: Any = None
        self.volume_dataset: Any = None
        self.solution: Any = None
        self.mesh_report: dict[str, Any] = {}
        self.mesh_paths: dict[str, str] = {}
        self.mesh_validity: dict[str, Any] = {}
        self.mesh_run: runs.RunDirectory | None = None
        self.solve_run: runs.RunDirectory | None = None
        self.solve_started_at: float = 0.0
        self._cfd_scored = False
        self.mesh_stage = runs.Stage()
        self.governed_run_dir: Path | None = None

        self.gmsh_settings = meshing.settings_from_policy(
            meshing.study_policy(), "laptop_smoke")
        if profile.mesher == "gmsh":
            # The laptop tier's in-plane sizing with the COARSE tier's wall
            # spacing.  Measured: 69 831 cells, every audit gate passed, and
            # y+ p50 0.36 / p95 0.54 / max 0.79 against a gate of p95 <= 1.
            # The policy default (1.07e-3 m) gives y+ 11 to 47 - forty times too
            # coarse - and prisms are anisotropic, so fixing it costs almost
            # nothing: 47 967 cells becomes 69 831.
            self.gmsh_settings.first_cell_height_over_L = 7.20e-6
            self.gmsh_settings.prism_layers = 24
            self.gmsh_settings.prism_growth_ratio = 1.25
        self.refine = refine_mod.RefinementSettings()
        # G1 is the coarsest grid S6 declares, so it is where an interactive
        # session starts: a qualified definition rather than an arbitrary one.
        self.grid_name = grids.grid_names()[0] if profile.mesher == "pyhyp" else ""
        self.s6_surface = (surface_s6.settings_from_grid(self.grid_name)
                           if self.grid_name else surface_s6.settings_from_level("smoke"))
        self.surface_info: dict[str, Any] = {}
        self.pyhyp_settings = meshing.PyHypSettings()
        if self.grid_name:
            self._apply_grid_to_settings(self.grid_name)
        self.flow = solvers.FlowConditions()
        # The configuration the S7 solver study selected: Newton-Krylov is what
        # separates converging from limit-cycling, and it is not sufficient on
        # its own - alone it reached 5.954 orders and missed the six-order gate
        # by 0.046.  With the stronger linear solve and the higher CFL it
        # reached 6.906, monotonically, still descending at the cap.
        self.su2_settings = solvers.SU2Settings(
            newton_krylov=True, linear_preconditioner="ILU", linear_iterations=25,
            cfl=25.0, cfl_ceiling=1000.0, multigrid_levels=0, stop_residual=-9.0)
        self.adflow_settings = solvers.ADflowSettings()
        self.runner: solvers.SolverRun | None = None

        self._build_state()
        self._build_ui()

    # ------------------------------------------------------------------ #
    # state                                                               #
    # ------------------------------------------------------------------ #

    @property
    def state(self):
        return self.server.state

    def _build_state(self) -> None:
        state = self.state
        variables = geo.design_variables()
        self.design_keys = [v.key for v in variables]
        # ONE FLAT STATE KEY PER VARIABLE.  A nested `design` dict looked tidier
        # but the sliders mutate it in place in the browser, and that mutation
        # did not come back across the wire - the sliders moved and the geometry
        # never changed.  Flat keys are watched individually and always sync.
        for variable in variables:
            setattr(state, f"dv_{variable.key}", variable.value)
        state.design_meta = [
            {"key": v.key, "label": v.label, "unit": v.unit, "group": v.group,
             "min": v.minimum, "max": v.maximum, "step": v.step, "decimals": v.decimals}
            for v in variables
        ]
        state.groups = [
            {"key": "planform", "label": "Planform"},
            {"key": "section", "label": "Sections"},
            {"key": "control", "label": "Control surfaces"},
        ]

        state.tab = "geometry"
        state.title = self.profile.title
        state.subtitle = self.profile.subtitle
        state.accent = self.profile.accent
        state.busy = False
        state.stage = ""
        state.error = ""
        state.log_lines = []
        state.capabilities = self.env.as_rows()
        state.machine = f"{cpu_count()} cores · {available_memory_gib():.1f} GiB free"

        # Geometry
        state.geometry_ready = False
        # ONE explicit source.  The sliders and the development index used to be
        # live at the same time: the sliders drove the summary and the index
        # drove the surface that was meshed.  Choosing a source is now the first
        # thing on the tab, and the other input is disabled while it is not the
        # chosen one.
        state.geometry_source = design.INTERACTIVE
        state.geometry_sources = [{"value": key, "title": design.SOURCE_LABELS[key]}
                                  for key in design.SOURCES]
        state.development_index = 0
        state.development_set = geo.DEVELOPMENT_SET
        state.development_set_size = 0
        state.sliders_locked = False
        state.design_fingerprint = ""
        state.design_moved = True
        state.geometry_provenance = {}
        state.control_problems = []
        state.configured_paths = configured_paths()
        # The two strategies tessellate differently and their level names are
        # unrelated.  S6 marches a structured multiblock surface of its own; S7
        # triangulates.  Showing one in the other's workbench is showing a
        # surface that will never be meshed.
        s6_surface = self.profile.mesher == "pyhyp"
        state.surface_levels = (list(geo.S6_SURFACE_LEVELS) if s6_surface
                                else list(GRID_LEVELS))
        state.surface_level = "smoke" if s6_surface else "laptop_smoke"
        state.surface_is_structured = s6_surface
        state.te_variant = "te_1p0mm"
        state.planform = {}
        state.stations = []
        state.surface_stats = {}
        state.geometry_color = "label"
        # ONE FLAT STATE KEY PER SURFACE CONTROL, for the reason recorded above
        # the design sliders: a widget bound into a nested dict mutates that
        # dict in the browser, and the mutation does not reliably come back
        # across the wire - so the box shows one number and the server holds
        # another. `s6_surface` is kept as a read-only mirror for display.
        self.surface_control_keys = [c.key for c in controls.surface_controls()]
        for control in controls.surface_controls():
            setattr(state, f"s6c_{control.key}", getattr(self.s6_surface, control.key))
        state.s6_surface = self.s6_surface.as_dict()
        state.s6_help = surface_s6.CONTROL_HELP
        state.s6_controls = [
            {"key": c.key, "label": c.label, "help": c.help, "kind": c.kind,
             "min": c.minimum, "max": c.maximum, "step": c.step, "unit": c.unit,
             "state": c.state, "target": c.target}
            for c in controls.surface_controls()
        ]
        state.grid_name = self.grid_name
        state.grid_items = grids.grid_items() + [
            {"value": "", "title": "Manual — experimental, not a qualified grid"}]
        state.grid_summary = (grids.grid(self.grid_name).describe()
                              if self.grid_name else "")
        state.qualified_grid = self.grid_name
        state.surface_quality = {}
        state.quality_patches = []
        state.refine = self.refine.as_dict()

        # Mesh
        state.mesher = self.profile.mesher
        state.mesh_ready = False
        state.mesh_settings = self.gmsh_settings.as_dict()
        state.pyhyp_volume_level = self.pyhyp_settings.volume_level
        state.pyhyp_eps_e = self.pyhyp_settings.eps_e
        state.pyhyp_s0_fraction = self.pyhyp_settings.s0_fraction or 0.0
        state.pyhyp_normal_points = meshing.effective_normal_points(self.pyhyp_settings)
        state.pyhyp_normal_choices = list(meshing.NORMAL_POINT_CHOICES)
        # `pyhyp_n_constant` and `pyhyp_index` are deliberately absent.  The
        # first reached nothing - `prepare` has no such argument, so pyHyp ran
        # at the curated default of 5 while the box showed 3 - and the second
        # selected a second geometry behind the geometry tab's back.
        state.s6_mode = governed.GOVERNED
        state.s6_modes = [{"value": key, "title": governed.MODE_LABELS[key]}
                          for key in governed.MODES]
        state.mode_help = governed.MODE_HELP
        state.governed = {}
        state.mesh_state = "none"
        state.mesh_verdict = {}
        state.mesh_attempts = []
        state.mesh_provenance = {}
        state.cfd_state = "none"
        state.cfd_verdict = {}
        state.can_mesh = False
        state.can_solve = False
        state.mesh_blockers = []
        state.solve_blockers = []
        state.mesh_stats = {}
        state.mesh_validity = {}
        state.mesh_audit = {}
        state.mesh_estimate = 0
        state.mesh_clip = False
        state.mesh_clip_position = 0.0
        state.mesh_show_edges = True
        state.mesh_quality_field = "none"
        state.mesh_quality_range = [0.0, 1.0]
        state.mesh_auto = True
        state.algorithms_2d = [{"value": k, "title": f"{k} · {v}"}
                               for k, v in meshing.GMSH_ALGORITHMS_2D.items()]
        state.algorithms_3d = [{"value": k, "title": f"{k} · {v}"}
                               for k, v in meshing.GMSH_ALGORITHMS_3D.items()]
        state.optimizers = list(meshing.OPTIMIZERS)
        state.grid_levels = list(GRID_LEVELS)
        state.te_variants = list(TE_VARIANTS)
        levels = meshing.pyhyp_level_choices()
        state.pyhyp_surface_levels = levels["surface"]
        state.pyhyp_volume_levels = levels["volume"]
        if self.profile.mesher == "pyhyp":
            state.development_set_size = design.development_set_size()
            self._refresh_governed()
            self._refresh_capabilities()

        # Solver
        state.solver_label = self.profile.solver_label
        state.flow = self.flow.as_dict()
        state.su2 = self.su2_settings.as_dict()
        state.adflow = self.adflow_settings.as_dict()
        state.su2_turbulence = [{"value": k, "title": f"{k} — {v}"}
                                for k, v in solvers.SU2_TURBULENCE.items()]
        state.adflow_turbulence = [{"value": k, "title": f"{k} — {v}"}
                                   for k, v in solvers.ADFLOW_TURBULENCE.items()]
        state.convective_schemes = list(solvers.SU2_CONVECTIVE)
        state.limiters = list(solvers.SU2_LIMITERS)
        state.preconditioners = list(solvers.SU2_LINEAR_PREC)
        state.adflow_smoothers = list(solvers.ADFLOW_SMOOTHERS)
        state.adflow_equations = list(solvers.ADFLOW_EQUATIONS)
        state.max_processes = cpu_count()
        state.memory_forecast = {}
        # The user's own machine, the user's own call.  Off by default, so the
        # forecast still has to be overruled deliberately.
        state.allow_over_budget = False
        state.run_status = "idle"
        state.run_iteration = 0
        state.run_wall = 0.0
        state.run_message = ""
        state.residual_svg = charts.residual_chart({}, {})
        state.force_svg = charts.force_chart({}, [], {})
        state.solver_log = []
        state.convergence = {}

        # Post
        state.post_files = {"surface": [], "volume": []}
        state.post_source = ""
        state.post_field = ""
        state.post_association = "point"
        state.post_fields = []
        state.post_colormap = "Cool to warm"
        state.colormaps = list(COLORMAPS)
        state.post_range = [0.0, 1.0]
        state.post_slice = False
        state.post_slice_axis = "Y"
        state.post_slice_position = 0.0
        state.post_summary = {}
        state.forces = {}
        state.view_options = ["Isometric", "+X", "-X", "+Y", "-Y", "+Z", "-Z"]

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #

    def _ui(self, function: Callable[[], None]) -> None:
        """Run something on the server's event loop, from any thread.

        Everything that touches VTK or client state has to land here.  An
        OpenGL context belongs to the thread that made it, so rendering from a
        worker aborts the process rather than raising - which is what "connection
        lost" looks like from the browser.  `state.flush()` is no safer.
        """
        loop = getattr(self, "_loop", None)
        if loop is None or threading.current_thread() is threading.main_thread():
            function()
            return
        loop.call_soon_threadsafe(function)

    def _push_log(self) -> None:
        def apply() -> None:
            self.state.log_lines = self.job.tail(200)
            self.state.busy = self.job.busy
            self.state.stage = self.job.stage
            self.state.error = self.job.error
            self.state.flush()

        self._ui(apply)

    def _refuse(self, message: str) -> None:
        """Decline an action, and make the reason survive the next log push.

        Setting `state.error` directly did not work: `_push_log` copies the
        JOB's error over it, and a refusal happens outside any job - so the
        message appeared and vanished in the same call, and the button simply
        did nothing with no explanation.
        """
        self.job.log(f"REFUSED: {message}")
        self.job.finish(message)
        self._push_log()

    def _run_async(self, stage: str, work: Callable[[], Callable[[], None] | None]) -> None:
        """Compute off the UI thread; apply the result back on it.

        `work` runs on a worker and must not touch VTK or state.  What it
        returns - if anything - is a callable that does, and that is run on the
        event loop.
        """
        if self.job.busy:
            return
        self.job.start(stage)
        self.job.log(f"── {stage}")
        self._push_log()

        def target() -> None:
            try:
                apply = work()
                if apply is not None:
                    self._ui(apply)
                self.job.finish()
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI, not swallowed
                self.job.log(f"ERROR {type(exc).__name__}: {exc}")
                for line in traceback.format_exc().splitlines()[-6:]:
                    self.job.log("  " + line)
                self.job.finish(f"{type(exc).__name__}: {exc}")
            self._push_log()

        threading.Thread(target=target, daemon=True, name=stage).start()

    def update_view(self) -> None:
        self.scene.render()
        if hasattr(self, "html_view"):
            self.html_view.update()

    # ------------------------------------------------------------------ #
    # geometry                                                            #
    # ------------------------------------------------------------------ #

    # -- geometry source, grids, capabilities ---------------------------- #

    def _apply_grid_to_settings(self, name: str) -> None:
        """Set the COMPLETE coupled definition, both halves of it.

        A grid is a surface AND a wall-normal specification.  Setting only the
        surface level - which is all the old "surface level" selector did -
        leaves the wall spacing at whatever the level table says, and for G1
        that is 8.8e-6 where the qualified definition says 7.2e-6.  The mesh
        would then be labelled G1 and not be G1.
        """
        definition = grids.grid(name)
        self.s6_surface = surface_s6.settings_from_grid(name)
        self.pyhyp_settings.surface_level = definition.surface_level
        self.pyhyp_settings.volume_level = definition.volume_level
        self.pyhyp_settings.s0_fraction = definition.first_cell_fraction
        self.pyhyp_settings.normal_points_override = None
        self.pyhyp_settings.eps_e = definition.eps_e
        self.pyhyp_settings.grid = name
        self.grid_name = name

    def select_grid(self, name: str = "") -> None:
        """Choose a qualified grid, or drop into manual (experimental) mode."""
        name = str(name or self.state.grid_name or "")
        if not name:
            self.grid_name = ""
            self.pyhyp_settings.grid = ""
            self.state.grid_summary = ""
            self.state.qualified_grid = surface_s6.matches_qualified_grid(self.s6_surface)
            self._invalidate_geometry("the grid definition changed")
            return
        self._apply_grid_to_settings(name)
        definition = grids.grid(name)
        self.state.grid_name = name
        self.state.grid_summary = definition.describe()
        self.state.surface_level = definition.surface_level
        self.state.qualified_grid = name
        self._write_surface_controls()
        self.state.pyhyp_volume_level = self.pyhyp_settings.volume_level
        self.state.pyhyp_eps_e = self.pyhyp_settings.eps_e
        self.state.pyhyp_s0_fraction = self.pyhyp_settings.s0_fraction or 0.0
        self.state.pyhyp_normal_points = definition.normal_points
        self._invalidate_geometry(f"grid {name} selected")

    def _refresh_governed(self) -> None:
        found = governed.availability()
        self.state.governed = found.as_dict()
        if not found.available and self.state.s6_mode == governed.GOVERNED:
            # Never silently.  The mode stays selected and disabled, and the
            # reason is on screen, because switching the user to the direct
            # march without telling them is the failure this whole mode exists
            # to prevent.
            self.job.log(f"Governed S6 atlas unavailable: {found.summary()}")

    def _refresh_capabilities(self) -> None:
        """Which buttons are usable, and the reason for each that is not."""
        state = self.state
        mesh_blockers: list[str] = []
        solve_blockers: list[str] = []

        if not state.geometry_ready:
            mesh_blockers.append("Build the geometry first")
        if self.profile.mesher == "pyhyp":
            if not self.env.ok("pyhyp"):
                mesh_blockers.append(
                    f"pyHyp is not available: {self.env['pyhyp'].detail}")
            if state.s6_mode == governed.GOVERNED and not (state.governed or {}).get("available"):
                # Says what is missing AND says what will not happen instead,
                # because the tempting failure mode here is a quiet fallback to
                # the direct march under a governed label.
                mesh_blockers.append(
                    "Governed mode needs the S6 atlas artifacts and will NOT "
                    "fall back to a direct pyHyp march: "
                    + str((state.governed or {}).get("summary", "")))
        if self.profile.solver == "adflow":
            if not self.env.ok("adflow"):
                solve_blockers.append(
                    f"ADflow is not available: {self.env['adflow'].detail}")
            if not self.env.ok("mpi"):
                solve_blockers.append("mpirun is not on PATH")
        elif not self.env.ok("su2"):
            solve_blockers.append("SU2_CFD is not on PATH")

        verdict = dict(state.mesh_verdict or {})
        if state.mesh_state not in ("audited_accepted", "accepted"):
            solve_blockers.append(
                "No mesh has passed its audit" if not verdict
                else f"Mesh {state.mesh_state}: " + ", ".join(verdict.get("failed", [])[:3]))

        state.mesh_blockers = mesh_blockers
        state.solve_blockers = solve_blockers
        state.can_mesh = not mesh_blockers
        state.can_solve = not solve_blockers

    def _invalidate_geometry(self, why: str) -> None:
        """A new geometry or grid makes every downstream artifact meaningless."""
        self.geometry = None
        self.case = None
        self.surface = None
        self.surface_info = {}
        self.state.geometry_ready = False
        self.state.design_fingerprint = ""
        self.state.geometry_provenance = {}
        self._invalidate_mesh(why)

    def _invalidate_mesh(self, why: str) -> None:
        self.volume_dataset = None
        self.mesh_report = {}
        self.mesh_paths = {}
        self.mesh_validity = {}
        self.mesh_run = None
        self.mesh_stage = runs.Stage()
        state = self.state
        state.mesh_ready = False
        state.mesh_state = "none"
        state.mesh_verdict = {}
        state.mesh_attempts = []
        state.mesh_provenance = {}
        state.mesh_stats = {}
        state.mesh_validity = {}
        state.mesh_audit = {}
        state.mesh_estimate = 0
        self._invalidate_results(why)
        if why:
            self.job.log(f"Cleared mesh and results: {why}")

    def _invalidate_results(self, why: str = "") -> None:
        self.solution = None
        self.solve_run = None
        self.runner = None
        self.solve_started_at = 0.0
        self._cfd_scored = False
        state = self.state
        state.cfd_state = "none"
        state.cfd_verdict = {}
        state.forces = {}
        state.convergence = {}
        state.run_status = "idle"
        state.run_iteration = 0
        state.run_wall = 0.0
        state.run_message = ""
        state.solver_log = []
        state.post_files = {"surface": [], "volume": []}
        state.post_source = ""
        state.post_field = ""
        state.post_fields = []
        state.post_summary = {}
        state.residual_svg = charts.residual_chart({}, {})
        state.force_svg = charts.force_chart({}, [], {})

    def sync_sliders_to_index(self) -> None:
        """Put the sliders where the chosen indexed design actually is.

        The two sources cannot coexist, and the honest way to express that in a
        slider UI is to show the indexed design's own values and lock them,
        rather than leaving stale numbers on screen beside a different geometry.
        """
        index = int(self.state.development_index or 0)
        for key, value in design.indexed_design_values(index).items():
            if key in self.design_keys:
                setattr(self.state, f"dv_{key}", float(value))

    # -- geometry -------------------------------------------------------- #

    def build_geometry(self) -> None:
        source = str(self.state.geometry_source or design.INTERACTIVE)
        index = int(self.state.development_index or 0)
        if source == design.DEVELOPMENT_INDEX:
            size = int(self.state.development_set_size or 0)
            if size and not 0 <= index < size:
                self.state.error = (f"development index {index} is outside "
                                    f"[0, {size}) for {geo.DEVELOPMENT_SET}")
                return
            self.sync_sliders_to_index()
        self.state.sliders_locked = source == design.DEVELOPMENT_INDEX

        values = self.design_values()

        def work() -> None:
            self.job.log(f"pyGeo: lofting {design.SOURCE_LABELS[source]}")
            started = time.time()
            built = design.build(source, values=values, index=index,
                                 output_dir=self.workspace / "geometry" / source)
            self.geometry = built
            self.case = built.case
            summary = built.summary
            self.job.log(f"pyGeo: {built.label} fingerprint {built.fingerprint}")
            self.job.log(f"pyGeo: span {summary['span_m']:.4f} m, "
                         f"area {summary['area_m2']:.4f} m2, MAC {summary['mac_m']:.4f} m")

            quality: dict[str, Any] = {}
            estimate = 0
            problems: list[str] = []
            if self.state.surface_is_structured:
                # Pull the MARCH settings too, not just the surface ones.  The
                # estimate is what tells a user whether the mesh will fit before
                # they spend 90 seconds on it, and it was reporting the level's
                # declared N while the wall-normal override said something else.
                self._sync_pyhyp_settings()
                problems = controls.validate(self.s6_surface.as_dict())
                if problems:
                    raise ValueError("; ".join(problems))
                self.job.log(
                    f"Building S6's structured surface from THIS pyGeo case "
                    f"(level basis {self.s6_surface.level})")
                # The one call that used to take an index and build its own
                # geometry.  It now takes the case above and cannot disagree
                # with the picture, the summary or the reference values.
                blocks, info = surface_s6.build_from_case(
                    self.s6_surface, built.pygeo_result)
                self.surface = blocks
                self.surface_info = info
                stats = geo.s6_surface_statistics(blocks)
                quality = surface_s6.quad_quality(blocks)
                stats["min_angle_deg"] = quality["min_angle_deg"]
                stats["aspect_p99"] = quality["aspect_p99"]
                estimate = meshing.estimate_pyhyp_cells(
                    blocks, self.pyhyp_settings.volume_level,
                    meshing.effective_normal_points(self.pyhyp_settings))
                self.job.log(
                    f"Surface: {stats['blocks']} blocks, {stats['quads']:,} quads, "
                    f"min angle {quality['min_angle_deg']:.2f} deg, aspect p99 "
                    f"{quality['aspect_p99']:.1f} ({time.time() - started:.1f}s)")
                self.job.log(
                    f"pyHyp will march this into {estimate:,} cells at "
                    f"N{meshing.effective_normal_points(self.pyhyp_settings)}"
                    + (f" (grid {info['workbench_qualified_grid']})"
                       if info.get("workbench_qualified_grid") else " (experimental surface)"))
            else:
                level = self.state.surface_level
                self.job.log(f"Tessellating at {level}")
                self.surface = geo.build_surface(
                    self.case, level=level, te_variant=self.state.te_variant)
                stats = geo.surface_statistics(self.surface)
                estimate = meshing.estimate_gmsh_cells(self.surface, self.gmsh_settings)
                self.job.log(f"Surface: {stats['triangles']} triangles, "
                             f"wetted {stats['wetted_area_m2']:.4f} m2 "
                             f"({time.time() - started:.1f}s)")

            overall = {k: v for k, v in quality.items()
                       if k not in ("patches", "per_cell_min_angle")}
            patches = quality.get("patches", [])
            # areaRef and chordRef come from THIS case, halved the way S6's own
            # campaign halves them for a half model.
            references = built.flow_references()
            self.flow.area_ref_m2 = references["area_ref_m2"]
            self.flow.chord_ref_m = references["chord_ref_m"]
            provenance = built.provenance()
            provenance["surface_qualified_grid"] = self.surface_info.get(
                "workbench_qualified_grid", "")

            def apply() -> None:
                self.state.planform = {k: v for k, v in summary.items()
                                       if k not in ("stations", "reference")}
                self.state.stations = summary["stations"]
                self.state.surface_stats = stats
                self.state.surface_quality = overall
                self.state.quality_patches = patches
                self.state.design_fingerprint = built.fingerprint
                self.state.geometry_provenance = provenance
                self.state.qualified_grid = provenance["surface_qualified_grid"]
                self.state.geometry_ready = True
                self.state.flow = self.flow.as_dict()
                self.state.mesh_estimate = estimate
                self._refresh_capabilities()
                self.show_geometry()

            return apply

        # A new loft invalidates everything downstream BEFORE it starts, so a
        # failed rebuild cannot leave the old mesh on screen looking current.
        self._invalidate_mesh("geometry is being rebuilt")
        self._run_async("Building geometry", work)

    def _read_surface_controls(self) -> None:
        """Pull the flat surface-control keys into the settings object."""
        incoming = {key: getattr(self.state, f"s6c_{key}", None)
                    for key in self.surface_control_keys}
        for key, value in controls.coerce(
                {k: v for k, v in incoming.items() if v is not None}).items():
            if hasattr(self.s6_surface, key):
                try:
                    setattr(self.s6_surface, key, type(
                        getattr(self.s6_surface, key))(value))
                except (TypeError, ValueError):
                    pass
        self.state.s6_surface = self.s6_surface.as_dict()

    def _write_surface_controls(self) -> None:
        """Push the settings object back out to the flat keys."""
        for key in self.surface_control_keys:
            setattr(self.state, f"s6c_{key}", getattr(self.s6_surface, key))
        self.state.s6_surface = self.s6_surface.as_dict()

    def _sync_s6_surface(self) -> None:
        """Pull the surface controls out of client state, in range.

        The level basis is the surface level of the selected grid when one is
        selected, so a grid cannot be half-applied.
        """
        self._read_surface_controls()
        if self.grid_name:
            self.s6_surface.level = grids.grid(self.grid_name).surface_level
        else:
            self.s6_surface.level = str(self.state.surface_level or self.s6_surface.level)
        self.state.s6_surface = self.s6_surface.as_dict()

    def _sync_refinement(self) -> None:
        for key, value in dict(self.state.refine).items():
            if key in ("region_a", "region_b"):
                region = getattr(self.refine, key)
                for sub, sub_value in dict(value).items():
                    if not hasattr(region, sub):
                        continue
                    current = getattr(region, sub)
                    try:
                        setattr(region, sub,
                                tuple(sub_value) if isinstance(current, tuple)
                                else type(current)(sub_value))
                    except (TypeError, ValueError):
                        pass
                continue
            if not hasattr(self.refine, key):
                continue
            current = getattr(self.refine, key)
            try:
                setattr(self.refine, key, type(current)(value))
            except (TypeError, ValueError):
                pass

    def reset_surface_controls(self) -> None:
        """Back to the selected grid's definition, or the level's own."""
        defaults = (surface_s6.settings_from_grid(self.grid_name) if self.grid_name
                    else surface_s6.settings_from_level(self.state.surface_level))
        self.s6_surface = defaults
        self._write_surface_controls()
        self.state.qualified_grid = surface_s6.matches_qualified_grid(defaults)

    def show_geometry(self) -> None:
        if self.surface is None:
            return
        if self.state.surface_is_structured:
            polydata, _names = geo.s6_blocks_to_polydata(self.surface)
            scalars, colormap, label = "block", "rainbow", "block"
        else:
            polydata, _labels = geo.surface_to_polydata(
                self.surface, color_by=self.state.geometry_color)
            scalars = self.state.geometry_color
            colormap = "viridis" if scalars == "span_fraction" else "rainbow"
            label = "patch" if scalars == "label" else "span"
        self.scene.clear()
        self.scene.add_surface(
            "geometry", polydata, scalars=scalars, association="cell",
            colormap=colormap, edges=True, label=label,
        )
        self.scene.reset_camera()
        self.update_view()

    # ------------------------------------------------------------------ #
    # mesh                                                                #
    # ------------------------------------------------------------------ #

    def _sync_mesh_settings(self) -> None:
        for key, value in dict(self.state.mesh_settings).items():
            if hasattr(self.gmsh_settings, key):
                current = getattr(self.gmsh_settings, key)
                try:
                    setattr(self.gmsh_settings, key, type(current)(value))
                except (TypeError, ValueError):
                    pass
        self.gmsh_settings.level = self.state.surface_level
        self.gmsh_settings.te_variant = self.state.te_variant

    def build_mesh(self) -> None:
        """Generate a volume mesh, and say honestly what kind of thing it is.

        Two paths for S6 and they are never confused with each other.  Governed
        mode runs S6's own campaign - template ranking, deformation, written
        CGNS re-audit, production floor - and if its artifacts are missing it
        refuses rather than quietly marching pyHyp and calling that S6.
        """
        self._refresh_capabilities()
        if not self.state.can_mesh:
            self._refuse("; ".join(self.state.mesh_blockers))
            return

        mode = str(self.state.s6_mode) if self.profile.mesher == "pyhyp" else ""
        if mode == governed.GOVERNED and not (self.state.governed or {}).get("available"):
            self._refuse("Governed S6 is unavailable and will NOT fall back to a "
                         "direct pyHyp march: "
                         + str((self.state.governed or {}).get("summary", "")))
            return

        # Everything downstream belongs to the mesh that is being replaced.
        self._invalidate_mesh("a new mesh is being generated")

        def work() -> None:
            if self.profile.mesher == "gmsh":
                return self._build_gmsh_mesh()
            if mode == governed.GOVERNED:
                return self._build_governed_mesh()
            return self._build_experimental_mesh()

        label = (self.profile.mesher_label if self.profile.mesher == "gmsh"
                 else governed.MODE_LABELS[mode])
        self._run_async(f"Meshing — {label}", work)

    def _load_volume(self, path: Path) -> dict[str, Any]:
        self.job.log(f"Reading {Path(path).name} into the viewport")
        self.volume_dataset = meshing.read_volume_mesh(Path(path))
        stats = meshing.summarize_mesh(self.volume_dataset)
        self.job.log(f"Mesh: {stats['cells']} cells, {stats['points']} points")
        return stats

    def _build_gmsh_mesh(self) -> Callable[[], None]:
        self._sync_mesh_settings()
        self._sync_refinement()
        run = runs.create(self.workspace, "mesh",
                          design_fingerprint=self.geometry.fingerprint,
                          settings={"gmsh": self.gmsh_settings.as_dict(),
                                    "refine": self.refine.as_dict()})
        self.mesh_run = run
        report = meshing.run_gmsh(self.surface, self.gmsh_settings, run.path / "gmsh",
                                  refine=self.refine, log=self.job.log)
        self.mesh_report = report
        # mesh_su2 is a dict carrying the path with its digest and marker
        # counts, while mesh_msh is a bare string; reading them the same way
        # handed a dict to the solver.
        self.mesh_paths = {"msh": str(report.get("mesh_msh", "")),
                           "su2": str(meshing.su2_mesh_path(report))}
        stats = self._load_volume(Path(self.mesh_paths["msh"]))

        audit: dict[str, Any] = {}
        try:
            audit = meshing.audit_summary(meshing.audit_gmsh(
                self.surface, run.path / "gmsh", self.gmsh_settings, log=self.job.log))
        except Exception as exc:  # noqa: BLE001 - an audit must not lose the mesh
            self.job.log(f"Mesh audit could not run: {type(exc).__name__}: {exc}")
        validity = meshing.validity_report(self.volume_dataset)
        self.mesh_validity = validity
        self._log_validity(validity)
        accepted = bool(audit.get("accepted")) and validity.get("valid", False)
        verdict = {"mode": "gmsh", "accepted": accepted,
                   "rows": audit.get("rows", []), "failed": audit.get("failed", [])}
        provenance = run.provenance() | {"design_fingerprint": self.geometry.fingerprint}
        return self._apply_mesh(stats, validity, audit, verdict, provenance,
                                accepted=accepted)

    def _build_experimental_mesh(self) -> Callable[[], None]:
        """Direct pyHyp march: a development tool, audited but not governed."""
        self._sync_pyhyp_settings()
        problems = controls.validate(
            self.s6_surface.as_dict() | {"eps_e": self.pyhyp_settings.eps_e})
        problems += [reason for reason in (
            controls.coarsening_problem(self.surface, self.pyhyp_settings.volume_level),
            controls.size_problem(meshing.estimate_pyhyp_cells(
                self.surface, self.pyhyp_settings.volume_level)),
        ) if reason]
        if problems:
            raise ValueError("; ".join(problems))

        run = runs.create(self.workspace, "mesh",
                          design_fingerprint=self.geometry.fingerprint,
                          settings={"mode": governed.EXPERIMENTAL,
                                    "pyhyp": self.pyhyp_settings.as_dict(),
                                    "surface": self.s6_surface.as_dict()})
        self.mesh_run = run
        report = meshing.run_pyhyp(
            self.pyhyp_settings, run, blocks=self.surface,
            surface_info=self.surface_info,
            geometry_id=self.geometry.geometry_id, log=self.job.log)
        self.mesh_report = report
        if not report["marched"]:
            raise RuntimeError("pyHyp did not produce a fresh volume mesh: "
                               + "; ".join(report["failure_reasons"]))

        verdict = meshing.audit_pyhyp(report, log=self.job.log)
        self.mesh_paths = {"cgns": report["cgns"]}
        stats = self._load_volume(Path(report["cgns"]))
        validity = meshing.validity_report(self.volume_dataset)
        self.mesh_validity = validity
        self._log_validity(validity)
        provenance = run.provenance() | {
            "mode": governed.EXPERIMENTAL,
            "design_fingerprint": self.geometry.fingerprint,
            "geometry_id": self.geometry.geometry_id,
            "cgns_sha256": verdict.get("cgns_sha256", ""),
            "normal_points": report["normal_points"],
            "s0_fraction_used": report["s0_fraction_used"],
            "qualified_grid": report.get("surface_qualified_grid", ""),
        }
        run.write_provenance(provenance)
        return self._apply_mesh(stats, validity, verdict, verdict, provenance,
                                accepted=bool(verdict["accepted"]))

    def _build_governed_mesh(self) -> Callable[[], None]:
        """S6's own atlas route, called rather than reimplemented."""
        run = runs.create(self.workspace, "mesh",
                          design_fingerprint=self.geometry.fingerprint,
                          settings={"mode": governed.GOVERNED,
                                    "registry": (self.state.governed or {}).get("registry", "")})
        self.mesh_run = run
        self.governed_run_dir = run.path
        report = governed.mesh(self.geometry, run.path, log=self.job.log)
        self.mesh_report = report
        verdict = governed.mesh_verdict(report)
        if not verdict["accepted"]:
            attempts = verdict["attempts"]
            raise RuntimeError(
                f"S6 rejected every candidate for this design ({len(attempts)} "
                "template attempt(s)); see the attempts table for each reason")

        self.mesh_paths = {"cgns": verdict["cgns"]}
        stats = self._load_volume(Path(verdict["cgns"]))
        validity = meshing.validity_report(self.volume_dataset)
        self.mesh_validity = validity
        self._log_validity(validity)
        provenance = run.provenance() | {
            "mode": governed.GOVERNED,
            "design_fingerprint": self.geometry.fingerprint,
            "design_id": verdict["design_id"],
            "template_id": verdict["template_id"],
            "cgns_sha256": verdict["cgns_sha256"],
            "registry_sha256": verdict["registry_sha256"],
            "manifest_sha256": verdict["manifest_sha256"],
            "mesh_implementation_sha256": verdict["implementation_sha256"],
        }
        run.write_provenance(provenance)
        return self._apply_mesh(stats, validity, verdict, verdict, provenance,
                                accepted=True)

    def _log_validity(self, validity: dict[str, Any]) -> None:
        if not validity.get("checked"):
            return
        if validity["valid"]:
            self.job.log("Mesh check: valid, worst scaled Jacobian "
                         f"{validity['min_scaled_jacobian']}")
        else:
            self.job.log(
                f"Mesh check: {validity['inverted_count']} INVERTED cells, worst "
                f"{validity['min_scaled_jacobian']}, centred near "
                f"{validity.get('inverted_centroid_m')}. The solver will refuse this mesh.")

    def _apply_mesh(self, stats: dict[str, Any], validity: dict[str, Any],
                    audit: dict[str, Any], verdict: dict[str, Any],
                    provenance: dict[str, Any], *, accepted: bool) -> Callable[[], None]:
        attempts = list(verdict.get("attempts") or [])
        settings = ({"gmsh": self.gmsh_settings.as_dict()} if self.profile.mesher == "gmsh"
                    else {"pyhyp": self.pyhyp_settings.as_dict(),
                          "surface": self.s6_surface.as_dict()})
        stage = runs.Stage(design_fingerprint=self.geometry.fingerprint,
                           settings_hash=runs.settings_hash(settings),
                           run_id=self.mesh_run.run_id if self.mesh_run else "")

        def apply() -> None:
            self.mesh_stage = stage
            self.state.mesh_stats = stats
            self.state.mesh_validity = validity
            self.state.mesh_audit = audit
            self.state.mesh_verdict = verdict
            self.state.mesh_attempts = attempts
            self.state.mesh_provenance = provenance
            # Distinct states, so "it exists" and "it passed" are never the
            # same word: generated -> audited -> accepted or rejected.
            self.state.mesh_state = "audited_accepted" if accepted else "audited_rejected"
            self.state.mesh_ready = True
            self._refresh_capabilities()
            self.show_mesh()

        return apply

    def _sync_pyhyp_settings(self) -> None:
        self._sync_s6_surface()
        self.pyhyp_settings.volume_level = str(self.state.pyhyp_volume_level)
        self.pyhyp_settings.surface_level = self.s6_surface.level
        self.pyhyp_settings.eps_e = float(self.state.pyhyp_eps_e)
        fraction = float(self.state.pyhyp_s0_fraction or 0.0)
        self.pyhyp_settings.s0_fraction = fraction if fraction > 0.0 else None
        points = int(self.state.pyhyp_normal_points or 0)
        declared = meshing.normal_points(self.pyhyp_settings.volume_level)
        self.pyhyp_settings.normal_points_override = points if points != declared else None
        self.pyhyp_settings.grid = self.grid_name

    def show_mesh(self) -> None:
        if self.volume_dataset is None:
            return
        bounds = meshing.mesh_bounds(self.volume_dataset)
        clip_normal = clip_origin = None
        if self.state.mesh_clip:
            span = bounds[3] - bounds[2]
            clip_normal = (0.0, 1.0, 0.0)
            clip_origin = (0.0, bounds[2] + span * float(self.state.mesh_clip_position), 0.0)

        dataset = self.volume_dataset
        scalars = None
        colormap = "coolwarm"
        scalar_range = None
        if self.state.mesh_quality_field != "none":
            # Range comes from the WHOLE mesh, not from whatever survives the
            # clip.  A clip that removes every cell leaves an empty array whose
            # range is VTK's uninitialised [1e299, -1e299], and rescaling per
            # clip position would make the colours mean something different at
            # every slider step anyway.
            dataset, scalar_range = meshing.cell_quality(
                dataset, self.state.mesh_quality_field)
            scalars = "Quality"
            colormap = "viridis"
            self.state.mesh_quality_range = [round(v, 5) for v in scalar_range]

        polydata = meshing.mesh_surface(dataset, clip_normal=clip_normal, clip_origin=clip_origin)
        self.scene.clear()
        self.scene.add_surface(
            "mesh", polydata, color=(0.55, 0.63, 0.74),
            edges=bool(self.state.mesh_show_edges),
            scalars=scalars, association="cell", colormap=colormap,
            scalar_range=scalar_range,
            label=self.state.mesh_quality_field.replace("_", " "),
        )
        self.scene.reset_camera()
        self.update_view()

    # ------------------------------------------------------------------ #
    # solver                                                              #
    # ------------------------------------------------------------------ #

    def _sync_solver_settings(self) -> None:
        for key, value in dict(self.state.flow).items():
            if hasattr(self.flow, key):
                setattr(self.flow, key, float(value))
        target, source = ((self.su2_settings, dict(self.state.su2))
                          if self.profile.solver == "su2"
                          else (self.adflow_settings, dict(self.state.adflow)))
        for key, value in source.items():
            if not hasattr(target, key):
                continue
            current = getattr(target, key)
            try:
                setattr(target, key, type(current)(value) if not isinstance(current, tuple)
                        else tuple(value))
            except (TypeError, ValueError):
                pass

    def start_solver(self) -> None:
        """Launch a solver only on a mesh that passed the applicable audit."""
        if self.runner is not None and self.runner.running:
            return
        self._refresh_capabilities()
        if not self.state.can_solve:
            self._refuse("; ".join(self.state.solve_blockers))
            return

        # The mesh has to be the one built from the geometry currently loaded.
        # Without this, moving a slider and pressing Run would solve the
        # previous aircraft's mesh against the new one's reference values.
        settings = ({"gmsh": self.gmsh_settings.as_dict()} if self.profile.mesher == "gmsh"
                    else {"pyhyp": self.pyhyp_settings.as_dict(),
                          "surface": self.s6_surface.as_dict()})
        if self.geometry is None or not self.mesh_stage.matches(
                self.geometry.fingerprint, settings):
            self._refuse("The mesh does not belong to the geometry and settings "
                         "now loaded. Re-generate it before solving.")
            return

        validity = getattr(self, "mesh_validity", {})
        if validity.get("checked") and not validity.get("valid", True):
            message = (
                f"Mesh has {validity['inverted_count']} inverted cells "
                f"(worst scaled Jacobian {validity['min_scaled_jacobian']}) "
                f"near {validity.get('inverted_centroid_m')}. Both solvers "
                "reject a grid with negative volumes."
            )
            self._refuse(message)
            return

        self._sync_solver_settings()
        # A fresh directory per solve.  A failed rerun therefore cannot expose
        # the previous run's `adflow_result.json` or solution files as current.
        self._invalidate_results("a new solve is starting")
        run = runs.create(self.workspace, "solve",
                          design_fingerprint=self.geometry.fingerprint,
                          settings={"flow": self.flow.as_dict(),
                                    "solver": (self.su2_settings.as_dict()
                                               if self.profile.solver == "su2"
                                               else self.adflow_settings.as_dict()),
                                    "mesh_run": self.mesh_stage.run_id})
        self.solve_run = run
        run.write_provenance({"mesh_provenance": dict(self.state.mesh_provenance or {})})
        run_dir = run.path

        if self.profile.solver == "su2":
            mesh = self.mesh_paths.get("su2")
            if not mesh:
                self.job.log("No SU2 mesh yet — build one on the Mesh tab")
                self._push_log()
                return
            self.runner = solvers.SU2Runner()
            self.solve_started_at = time.time()
            self.runner.start(Path(mesh), self.flow, self.su2_settings, run_dir)
        else:
            mesh = self.mesh_paths.get("cgns")
            if not mesh:
                self.job.log("No CGNS volume mesh yet — mesh one on the Mesh tab")
                self._push_log()
                return
            self.runner = solvers.ADflowRunner()
            cells = int(self.state.mesh_stats.get("cells") or 0)
            forecast = solvers.ADflowRunner.memory_forecast(
                cells, self.adflow_settings.processes)
            override = bool(self.state.allow_over_budget)
            self.job.log(
                f"ADflow memory: {forecast['estimated_gib']} GiB estimated for "
                f"{cells:,} cells, budget {forecast['budget_gib']} GiB of "
                f"{forecast['available_gib']} GiB free -> "
                + ("fits" if forecast["fits"]
                   else ("OVER BUDGET, launching anyway because the override is on"
                         if override else "OVER BUDGET")))
            self.solve_started_at = time.time()
            try:
                self.runner.start(Path(mesh), self.flow, self.adflow_settings,
                                  run_dir, cells=cells,
                                  allow_over_budget=bool(self.state.allow_over_budget))
            except MemoryError as exc:
                self.runner = None
                self._refuse(str(exc))
                return

        self.state.cfd_state = "running"
        self.job.log(f"{self.profile.solver_label}: launched in {run_dir}")
        self.job.log("Reminder: a zero exit code means the process finished. "
                     "Acceptance is decided by the CFD gates afterwards.")
        self._push_log()
        self.server.controller.start_monitor()

    def evaluate_cfd(self) -> dict[str, Any]:
        """Score the finished solve against S6's CFD gates.

        This is what turns "the process exited" into a verdict.  It runs once
        the monitor sees the run stop, so the interface never shows an accepted
        result that nothing checked.
        """
        if self.solve_run is None or self.runner is None:
            return {}
        snapshot = self.runner.snapshot()
        if self.profile.solver != "adflow":
            history = snapshot["history"]
            summary = post.convergence_summary(history)
            orders = summary.get("orders_dropped")
            passed = (snapshot["return_code"] == 0 and orders is not None
                      and float(orders) >= 6.0)
            return {
                "mode": "su2", "accepted": bool(passed),
                "state": "CFD_ACCEPTED" if passed else "CFD_REJECTED",
                "rows": [
                    {"gate": "solver return code", "actual": str(snapshot["return_code"]),
                     "limit": "0", "passed": snapshot["return_code"] == 0},
                    {"gate": "residual reduction",
                     "actual": "-" if orders is None else f"{float(orders):.3f}",
                     "limit": ">= 6 orders",
                     "passed": orders is not None and float(orders) >= 6.0},
                ],
                "failed": [],
            }
        return solvers.adflow_cfd_verdict(
            self.solve_run.path, return_code=snapshot["return_code"],
            started_at=self.solve_started_at)

    def stop_solver(self) -> None:
        if self.runner is not None:
            self.runner.stop()
            self.job.log("Stop requested")
            self._push_log()

    def refresh_monitor(self) -> bool:
        """Pull one snapshot from the running solver into the UI."""
        if self.runner is None:
            return False
        snapshot = self.runner.snapshot()
        history = snapshot["history"]
        state = self.state
        state.run_status = snapshot["status"]
        state.run_iteration = snapshot["iteration"]
        state.run_wall = snapshot["wall_seconds"]
        state.run_message = snapshot["message"]
        state.solver_log = snapshot["log_tail"][-160:]

        residual_labels = {k: v for k, v in solvers.RESIDUAL_LABELS.items() if k in history}
        gate = float(self.su2_settings.stop_residual) if self.profile.solver == "su2" else None
        state.residual_svg = charts.residual_chart(history, residual_labels, gate=gate)
        force_keys = [k for k in ("CL", "CD", "CMy", "yplus") if k in history]
        state.force_svg = charts.force_chart(history, force_keys, solvers.FORCE_LABELS)
        state.convergence = post.convergence_summary(history)

        running = snapshot["status"] == "running"
        if running:
            state.cfd_state = "running"
        else:
            # The process is done.  That is "solve completed", never
            # "CFD accepted" - the gates decide the second one.
            state.cfd_state = "solve_completed"
            # Score ONCE.  The monitor pulls a final snapshot after it stops, so
            # scoring on every non-running tick printed the verdict twice and
            # re-read the whole solver log to do it.
            if snapshot["status"] not in ("idle",) and not self._cfd_scored:
                self._cfd_scored = True
                verdict = self.evaluate_cfd()
                if verdict:
                    state.cfd_verdict = verdict
                    state.cfd_state = ("cfd_accepted" if verdict["accepted"]
                                       else "cfd_rejected")
                    state.forces = verdict.get("forces", {})
                    self.job.log(
                        f"CFD gates: {verdict['state']}"
                        + (f" — {', '.join(verdict['failed'][:4])}"
                           if verdict.get("failed") else ""))
        state.flush()
        return running

    # ------------------------------------------------------------------ #
    # post                                                                #
    # ------------------------------------------------------------------ #

    def load_results(self) -> None:
        if self.solve_run is None:
            self.job.log("No solve has run in this session")
            self._push_log()
            return

        def work() -> None:
            # THIS run's directory, never a shared one.  Reading `workspace/
            # solve` meant a failed rerun loaded the previous run's fields.
            run_dir = self.solve_run.path
            files = post.find_solution_files(run_dir)
            candidates = files["surface"] + files["volume"]
            if not candidates:
                raise RuntimeError(f"no solution files under {run_dir}")
            source = self.state.post_source or candidates[0]
            self.job.log(f"Loading {Path(source).name}")
            self.solution = post.load(Path(source))
            fields = post.available_fields(self.solution)
            options = ([{"value": f"point:{n}", "title": f"{n} (point)"} for n in fields["point"]]
                       + [{"value": f"cell:{n}", "title": f"{n} (cell)"} for n in fields["cell"]])
            name, association = post.best_field(self.solution)
            forces = (post.su2_forces(run_dir) if self.profile.solver == "su2"
                      else solvers.ADflowRunner.read_result(
                          run_dir, produced_after=self.solve_started_at or None))
            self.job.log(f"{len(fields['point'])} point fields, {len(fields['cell'])} cell fields")

            def apply() -> None:
                self.state.post_files = files
                self.state.post_source = source
                self.state.post_fields = options
                self.state.post_field = f"{association}:{name}" if name else ""
                self.state.forces = forces
                self.show_results()

            return apply

        self._run_async("Loading results", work)

    def show_results(self) -> None:
        if self.solution is None:
            return
        selector = self.state.post_field or ""
        association, _, name = selector.partition(":")
        if not name:
            return
        low, high = post.field_range(self.solution, name, association)
        self.state.post_range = [round(low, 6), round(high, 6)]
        self.state.post_summary = post.surface_scalar_summary(self.solution, name, association)

        dataset = self.solution
        if self.state.post_slice:
            axis = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[self.state.post_slice_axis]
            bounds = post.dataset_bounds(dataset)
            index = {"X": 0, "Y": 2, "Z": 4}[self.state.post_slice_axis]
            low_b, high_b = bounds[index], bounds[index + 1]
            position = low_b + (high_b - low_b) * float(self.state.post_slice_position)
            origin = [0.0, 0.0, 0.0]
            origin[index // 2] = position
            dataset = post.slice_plane(dataset, normal=axis, origin=tuple(origin))
        elif not dataset.IsA("vtkPolyData"):
            # A volume grid or a CGNS multiblock has to be reduced to a surface
            # before a mapper will take it; a surface file already is one.
            dataset = meshing.mesh_surface(dataset)

        self.scene.clear()
        self.scene.add_surface(
            "solution", dataset, scalars=name, association=association,
            colormap=COLORMAPS.get(self.state.post_colormap, "coolwarm"),
            scalar_range=(low, high), label=name,
        )
        self.scene.reset_camera()
        self.update_view()

    # ------------------------------------------------------------------ #
    # reactions                                                           #
    # ------------------------------------------------------------------ #

    @change("geometry_color")
    def _on_geometry_color(self, **_kwargs):
        self.show_geometry()

    @change("mesh_clip", "mesh_clip_position", "mesh_show_edges", "mesh_quality_field")
    def _on_mesh_display(self, **_kwargs):
        if self.state.mesh_ready:
            self.show_mesh()

    @change("post_field", "post_colormap", "post_slice", "post_slice_position", "post_slice_axis")
    def _on_post_display(self, **_kwargs):
        if self.solution is not None:
            self.show_results()

    @change("adflow", "mesh_stats", "mesh_estimate", "allow_over_budget")
    def _on_adflow_memory(self, **_kwargs):
        """Forecast from the estimate too, so the warning arrives BEFORE the march.

        Waiting for `mesh_stats` meant the memory problem was only visible after
        paying for the mesh. The pre-march estimate is exact for pyHyp, so there
        is no reason to wait for it.
        """
        if self.profile.solver != "adflow":
            return
        cells = int(self.state.mesh_stats.get("cells") or 0) or int(
            self.state.mesh_estimate or 0)
        if not cells:
            self.state.memory_forecast = {}
            return
        ranks = int(dict(self.state.adflow).get("processes", 1) or 1)
        self.state.memory_forecast = solvers.ADflowRunner.memory_forecast(cells, ranks)

    @change("mesh_settings")
    def _on_mesh_settings(self, **_kwargs):
        if self.surface is not None and self.profile.mesher == "gmsh":
            self._sync_mesh_settings()
            self.state.mesh_estimate = meshing.estimate_gmsh_cells(
                self.surface, self.gmsh_settings)

    @change("geometry_source")
    def _on_geometry_source(self, **_kwargs):
        """Two sources cannot be live at once."""
        source = str(self.state.geometry_source)
        self.state.sliders_locked = source == design.DEVELOPMENT_INDEX
        if source == design.DEVELOPMENT_INDEX:
            self.sync_sliders_to_index()
        self._invalidate_geometry(f"geometry source is now {source}")
        self._refresh_capabilities()

    @change("development_index")
    def _on_development_index(self, **_kwargs):
        if str(self.state.geometry_source) != design.DEVELOPMENT_INDEX:
            return
        self.sync_sliders_to_index()
        self._invalidate_geometry("the development index changed")
        self._refresh_capabilities()

    @change("surface_level")
    def _on_surface_level(self, **_kwargs):
        """Manual mode only: rebase the surface on one of S6's own levels.

        The qualified family has no member below G1 (1.62 M cells at N129), but
        `strategy_s6.LEVELS` declares `coarse` - 6,796 quads, 869,888 cells -
        which is the honest coarse option for a laptop.  It is not a qualified
        grid and is labelled accordingly.
        """
        if self.profile.mesher != "pyhyp" or self.grid_name:
            return
        level = str(self.state.surface_level)
        if level == self.s6_surface.level:
            return
        self.s6_surface = surface_s6.settings_from_level(level)
        self._write_surface_controls()
        self.state.qualified_grid = surface_s6.matches_qualified_grid(self.s6_surface)
        self._invalidate_geometry(f"the surface level basis is now {level}")
        self._refresh_capabilities()

    @change("grid_name")
    def _on_grid_name(self, **_kwargs):
        if self.profile.mesher != "pyhyp":
            return
        if str(self.state.grid_name or "") != self.grid_name:
            self.select_grid(str(self.state.grid_name or ""))
            self._refresh_capabilities()

    @change("s6_mode")
    def _on_s6_mode(self, **_kwargs):
        if self.profile.mesher != "pyhyp":
            return
        self._refresh_governed()
        self._invalidate_mesh("the mesh generation mode changed")
        self._refresh_capabilities()

    def _on_s6_surface_control(self, **_kwargs):
        """A SURFACE control moved, so the built surface is stale.

        This used to clear only the mesh.  But the structured surface is built
        on the geometry tab, so leaving `geometry_ready` set meant "Generate
        mesh" happily marched the PREVIOUS surface while the panel displayed the
        new numbers - 12,668 quads from a 33x89 surface while the boxes read
        29x75.  A surface control therefore invalidates the geometry, exactly as
        a design slider does.
        """
        if self.profile.mesher != "pyhyp":
            return
        self._read_surface_controls()
        self.state.control_problems = controls.validate(self.s6_surface.as_dict())
        self.state.qualified_grid = surface_s6.matches_qualified_grid(self.s6_surface)
        if not self.state.qualified_grid and self.state.grid_name:
            # The numbers no longer describe the selected grid, so the selector
            # must stop claiming they do.
            self.grid_name = ""
            self.state.grid_name = ""
            self.state.grid_summary = ""
        if self.state.geometry_ready or self.state.mesh_ready:
            self._invalidate_geometry("a surface control changed")
        self._refresh_capabilities()

    @change("pyhyp_volume_level", "pyhyp_eps_e", "pyhyp_s0_fraction",
            "pyhyp_normal_points")
    def _on_s6_march_control(self, **_kwargs):
        """A MARCH control moved: the surface still stands, the mesh does not."""
        if self.profile.mesher != "pyhyp":
            return
        self._sync_pyhyp_settings()
        self.state.control_problems = controls.validate({
            "eps_e": self.pyhyp_settings.eps_e,
            "normal_points_override": meshing.effective_normal_points(self.pyhyp_settings),
            **({"s0_fraction": self.pyhyp_settings.s0_fraction}
               if self.pyhyp_settings.s0_fraction else {}),
        })
        if self.surface is not None:
            self.state.mesh_estimate = meshing.estimate_pyhyp_cells(
                self.surface, self.pyhyp_settings.volume_level,
                meshing.effective_normal_points(self.pyhyp_settings))
        if self.state.mesh_ready:
            self._invalidate_mesh("a march control changed")
        self._refresh_capabilities()

    def _on_design_changed(self, **_kwargs) -> None:
        if str(self.state.geometry_source) == design.DEVELOPMENT_INDEX:
            return
        moved = self.design_moved()
        self.state.design_moved = moved
        if moved and (self.state.geometry_ready or self.state.mesh_ready):
            self._invalidate_geometry("a design variable changed")
            self._refresh_capabilities()

    def set_view(self, name: str) -> None:
        self.scene.set_view(name)
        self.update_view()

    def design_values(self) -> dict[str, float]:
        return {key: float(getattr(self.state, f"dv_{key}")) for key in self.design_keys}

    def design_moved(self) -> bool:
        """Whether the sliders now describe a different aircraft."""
        if self.geometry is None:
            return True
        return design.design_fingerprint(
            str(self.state.geometry_source),
            self.design_values(),
            int(self.state.development_index or 0)) != self.geometry.fingerprint

    def reset_design(self) -> None:
        for variable in geo.design_variables():
            setattr(self.state, f"dv_{variable.key}", variable.value)
        self._invalidate_geometry("the design was reset to baseline")
        self._refresh_capabilities()

    # ------------------------------------------------------------------ #
    # layout                                                              #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        from .ui.layout import build_layout

        build_layout(self)
        # Every design slider invalidates the mesh and the results.  There is
        # one state key per variable (see `_build_state`), so the watcher is
        # registered over the whole set rather than named one at a time.
        self.state.change(*[f"dv_{key}" for key in self.design_keys])(
            self._on_design_changed)
        if self.profile.mesher == "pyhyp":
            self.state.change(*[f"s6c_{key}" for key in self.surface_control_keys])(
                self._on_s6_surface_control)
        self.server.controller.start_monitor = self._start_monitor
        self._loop = None

        @self.server.controller.add("on_server_ready")
        def _capture_loop(*_args, **_kwargs) -> None:
            # The one thread allowed to touch VTK and client state.  Workers
            # marshal onto it through `_ui`.
            self._loop = asyncio.get_running_loop()
            self.job.log(f"Render backend: {self.scene.backend}")
            self._push_log()

    def _start_monitor(self) -> None:
        """Poll the running solver on the server's own event loop.

        The solver writes on its reader thread; this coroutine is what carries
        those numbers into client state.  It stops itself when the run does, so
        an idle workbench is not pushing empty frames at the browser.
        """
        if getattr(self, "_monitor_task", None) is not None:
            if not self._monitor_task.done():
                return

        async def loop() -> None:
            while True:
                still_running = self.refresh_monitor()
                self._push_log()
                if not still_running:
                    break
                await asyncio.sleep(0.7)
            # One last pull so the final iteration is never missing from the plot.
            self.refresh_monitor()
            self._push_log()

        self._monitor_task = asyncio.create_task(loop())

    def start(self, **kwargs) -> None:
        self.server.start(**kwargs)
