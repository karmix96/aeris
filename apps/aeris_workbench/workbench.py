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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from trame.app import get_server
from trame.decorators import TrameApp, change
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import html
from trame.widgets import vtk as vtk_widgets
from trame.widgets import vuetify3 as v3

from . import (charts, geometry as geo, meshing, postprocess as post,
               refinement as refine_mod, solvers, surface_s6)
from .environment import WORKSPACE, available_memory_gib, cpu_count, detect
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
    def __init__(self, profile: StrategyProfile, server=None):
        self.profile = profile
        self.server = server or get_server(f"aeris_{profile.key.lower()}", client_type="vue3")
        self.scene = Scene()
        self.scene.show_orientation_axes()
        self.job = Job()

        self.workspace = WORKSPACE / profile.key.lower()
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.env = detect()
        self.case: Any = None
        self._built_design: dict[str, float] | None = None
        self.surface: Any = None
        self.volume_dataset: Any = None
        self.solution: Any = None
        self.mesh_report: dict[str, Any] = {}
        self.mesh_paths: dict[str, str] = {}

        self.gmsh_settings = meshing.settings_from_policy(
            meshing.study_policy(), "laptop_smoke")
        self.refine = refine_mod.RefinementSettings()
        self.s6_surface = surface_s6.settings_from_level("smoke")
        self.surface_info: dict[str, Any] = {}
        self.pyhyp_settings = meshing.PyHypSettings()
        self.flow = solvers.FlowConditions()
        self.su2_settings = solvers.SU2Settings()
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
        state.s6_surface = self.s6_surface.as_dict()
        state.s6_help = surface_s6.CONTROL_HELP
        state.surface_quality = {}
        state.quality_patches = []
        state.refine = self.refine.as_dict()

        # Mesh
        state.mesher = self.profile.mesher
        state.mesh_ready = False
        state.mesh_settings = self.gmsh_settings.as_dict()
        state.pyhyp_volume_level = self.pyhyp_settings.volume_level
        state.pyhyp_surface_level = self.pyhyp_settings.surface_level
        state.pyhyp_eps_e = self.pyhyp_settings.eps_e
        state.pyhyp_n_constant = self.pyhyp_settings.n_constant
        state.pyhyp_index = self.pyhyp_settings.development_index
        state.mesh_stats = {}
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

    def build_geometry(self) -> None:
        def work() -> None:
            self.job.log("pyGeo: lofting sections")
            started = time.time()
            values = self.design_values()
            # Re-lofting takes seconds; changing only the tessellation does not.
            # Skip pyGeo entirely when the design itself has not moved.
            if self.case is not None and values == self._built_design:
                self.job.log("pyGeo: design unchanged, reusing the existing loft")
            else:
                self.case = geo.build_case(values, self.workspace / "geometry")
                self._built_design = dict(values)
            summary = geo.planform_summary(self.case)
            self.job.log(f"pyGeo: span {summary['span_m']:.4f} m, "
                         f"area {summary['area_m2']:.4f} m2, MAC {summary['mac_m']:.4f} m")

            level = self.state.surface_level
            quality: dict[str, Any] = {}
            if self.state.surface_is_structured:
                self.job.log(f"Building S6's structured surface at {level}")
                self._sync_s6_surface(level)
                blocks, info, _case = surface_s6.build_with_controls(
                    self.s6_surface, int(self.state.pyhyp_index),
                    self.workspace / "geometry_s6")
                self.surface = blocks
                self.surface_info = info
                stats = geo.s6_surface_statistics(blocks)
                quality = surface_s6.quad_quality(blocks)
                stats["min_angle_deg"] = quality["min_angle_deg"]
                stats["aspect_p99"] = quality["aspect_p99"]
                self.job.log(
                    f"Surface: {stats['blocks']} blocks, {stats['quads']:,} quads, "
                    f"min angle {quality['min_angle_deg']:.2f} deg, aspect p99 "
                    f"{quality['aspect_p99']:.1f} ({time.time() - started:.1f}s)")
            else:
                self.job.log(f"Tessellating at {level}")
                self.surface = geo.build_surface(
                    self.case, level=level, te_variant=self.state.te_variant)
                stats = geo.surface_statistics(self.surface)
                self.job.log(f"Surface: {stats['triangles']} triangles, "
                             f"wetted {stats['wetted_area_m2']:.4f} m2 "
                             f"({time.time() - started:.1f}s)")

            estimate = (meshing.estimate_gmsh_cells(self.surface, self.gmsh_settings)
                        if self.profile.mesher == "gmsh" else 0)
            overall = {k: v for k, v in quality.items()
                       if k not in ("patches", "per_cell_min_angle")}
            patches = quality.get("patches", [])
            # The pyHyp tab marches whichever level the geometry tab just built.
            self.pyhyp_settings.surface_level = level
            self.flow.area_ref_m2 = float(summary["area_m2"])
            self.flow.chord_ref_m = float(summary["mac_m"])

            def apply() -> None:
                self.state.planform = {k: v for k, v in summary.items()
                                       if k not in ("stations", "reference")}
                self.state.stations = summary["stations"]
                self.state.surface_stats = stats
                self.state.surface_quality = overall
                self.state.quality_patches = patches
                self.state.geometry_ready = True
                self.state.flow = self.flow.as_dict()
                self.state.mesh_estimate = estimate
                self.show_geometry()

            return apply

        self._run_async("Building geometry", work)

    def _sync_s6_surface(self, level: str) -> None:
        self.s6_surface = surface_s6.settings_from_level(level)
        for key, value in dict(self.state.s6_surface).items():
            if key == "level" or not hasattr(self.s6_surface, key):
                continue
            current = getattr(self.s6_surface, key)
            try:
                setattr(self.s6_surface, key, type(current)(value))
            except (TypeError, ValueError):
                pass
        self.s6_surface.level = level

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
        defaults = surface_s6.settings_from_level(self.state.surface_level)
        self.state.s6_surface = defaults.as_dict()

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
        if self.surface is None and self.profile.mesher == "gmsh":
            self.job.log("Build the geometry first")
            self._push_log()
            return

        def work() -> None:
            if self.profile.mesher == "gmsh":
                self._sync_mesh_settings()
                self._sync_refinement()
                report = meshing.run_gmsh(
                    self.surface, self.gmsh_settings, self.workspace / "mesh",
                    refine=self.refine, log=self.job.log)
                self.mesh_report = report
                self.mesh_paths = {
                    "msh": report.get("mesh_msh", ""),
                    "su2": report.get("mesh_su2", ""),
                }
                path = Path(self.mesh_paths["msh"])
            else:
                self.pyhyp_settings.volume_level = str(self.state.pyhyp_volume_level)
                self.pyhyp_settings.surface_level = str(self.state.pyhyp_surface_level)
                self.pyhyp_settings.eps_e = float(self.state.pyhyp_eps_e)
                self.pyhyp_settings.n_constant = int(self.state.pyhyp_n_constant)
                self.pyhyp_settings.development_index = int(self.state.pyhyp_index)
                self.job.log(f"pyHyp: surface={self.pyhyp_settings.surface_level} "
                             f"volume={self.pyhyp_settings.volume_level} "
                             f"epsE={self.pyhyp_settings.eps_e}")
                report = meshing.run_pyhyp(
                    self.pyhyp_settings, self.workspace / "mesh",
                    blocks=self.surface, surface_info=self.surface_info,
                    log=self.job.log)
                self.mesh_report = report
                if not report.get("cgns"):
                    raise RuntimeError("pyHyp did not produce a volume mesh")
                self.mesh_paths = {"cgns": report["cgns"]}
                path = Path(report["cgns"])

            self.job.log(f"Reading {path.name} into the viewport")
            self.volume_dataset = meshing.read_volume_mesh(path)
            stats = meshing.summarize_mesh(self.volume_dataset)
            self.job.log(f"Mesh: {stats['cells']} cells, {stats['points']} points")

            def apply() -> None:
                self.state.mesh_stats = stats
                self.state.mesh_ready = True
                self.show_mesh()

            return apply

        self._run_async(f"Meshing with {self.profile.mesher_label}", work)

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
        if self.runner is not None and self.runner.running:
            return
        self._sync_solver_settings()
        run_dir = self.workspace / "solve"
        run_dir.mkdir(parents=True, exist_ok=True)

        if self.profile.solver == "su2":
            mesh = self.mesh_paths.get("su2")
            if not mesh:
                self.job.log("No SU2 mesh yet — build one on the Mesh tab")
                self._push_log()
                return
            self.runner = solvers.SU2Runner()
            self.runner.start(Path(mesh), self.flow, self.su2_settings, run_dir)
        else:
            mesh = self.mesh_paths.get("cgns")
            if not mesh:
                self.job.log("No CGNS volume mesh yet — march one on the Mesh tab")
                self._push_log()
                return
            self.runner = solvers.ADflowRunner()
            cells = int(self.state.mesh_stats.get("cells") or 0)
            try:
                self.runner.start(Path(mesh), self.flow, self.adflow_settings,
                                  run_dir, cells=cells)
            except MemoryError as exc:
                self.job.log(f"REFUSED: {exc}")
                self.state.error = str(exc)
                self.runner = None
                self._push_log()
                return

        self.job.log(f"{self.profile.solver_label}: launched in {run_dir}")
        self._push_log()
        self.server.controller.start_monitor()

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
        state.flush()
        return snapshot["status"] == "running"

    # ------------------------------------------------------------------ #
    # post                                                                #
    # ------------------------------------------------------------------ #

    def load_results(self) -> None:
        def work() -> None:
            run_dir = self.workspace / "solve"
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
                      else solvers.ADflowRunner.read_result(run_dir))
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

    @change("adflow", "mesh_stats")
    def _on_adflow_memory(self, **_kwargs):
        if self.profile.solver != "adflow":
            return
        cells = int(self.state.mesh_stats.get("cells") or 0)
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

    def set_view(self, name: str) -> None:
        self.scene.set_view(name)
        self.update_view()

    def design_values(self) -> dict[str, float]:
        return {key: float(getattr(self.state, f"dv_{key}")) for key in self.design_keys}

    def reset_design(self) -> None:
        for variable in geo.design_variables():
            setattr(self.state, f"dv_{variable.key}", variable.value)
        self._built_design = None

    # ------------------------------------------------------------------ #
    # layout                                                              #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        from .ui.layout import build_layout

        build_layout(self)
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
