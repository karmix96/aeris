"""The four-stage layout: a settings rail on the left, one 3D viewport right.

Every commercial workbench puts the controls beside the picture rather than
above it, because a setting and its effect have to be visible at the same time.
The tab strip is the workflow order - geometry, mesh, solve, results - and the
viewport persists across all four so the camera never resets under the user.
"""

from __future__ import annotations

from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import html
from trame.widgets import vtk as vtk_widgets
from trame.widgets import vuetify3 as v3

CARD = {"classes": "mb-3", "variant": "flat", "color": "surface-variant"}
DENSE = {"density": "compact", "hide_details": True, "variant": "outlined"}


def _section(title: str, subtitle: str = ""):
    with v3.VCardTitle(classes="text-body-2 font-weight-bold py-2"):
        html.Span(title)
    if subtitle:
        with v3.VCardSubtitle(classes="text-caption pb-2"):
            html.Span(subtitle)


def _number(label: str, model: str, *, step: float = 0.01, suffix: str = "", cols: int = 6):
    with v3.VCol(cols=cols, classes="py-1"):
        v3.VTextField(label=label, v_model=(model,), type="number", step=step,
                      suffix=suffix, **DENSE)


def _stat_row(label: str, value_expr: str):
    with html.Div(classes="d-flex justify-space-between text-caption py-1"):
        html.Span(label, classes="text-medium-emphasis")
        html.Span(f"{{{{ {value_expr} }}}}", classes="font-weight-medium")


# --------------------------------------------------------------------------- #

def geometry_panel(app):
    with v3.VCard(**CARD):
        _section("Design variables", "Bounds come from configs/geometry/bwb.yaml")
        with v3.VCardText(classes="pt-0"):
            with v3.VExpansionPanels(multiple=True, model_value=([0],), variant="accordion"):
                with v3.VExpansionPanel(v_for="g in groups", key="g.key"):
                    v3.VExpansionPanelTitle("{{ g.label }}", classes="text-caption")
                    with v3.VExpansionPanelText():
                        with html.Div(v_for="m in design_meta.filter(d => d.group === g.key)",
                                      key="m.key", classes="mb-2"):
                            with html.Div(classes="d-flex justify-space-between text-caption"):
                                html.Span("{{ m.label }}")
                                html.Span("{{ design[m.key].toFixed(m.decimals) }} {{ m.unit }}",
                                          classes="font-weight-medium")
                            v3.VSlider(
                                v_model=("design[m.key]",),
                                min=("m.min",), max=("m.max",), step=("m.step",),
                                density="compact", hide_details=True, thumb_label=False,
                                color=("accent",),
                            )
            with v3.VRow(classes="mt-2"):
                with v3.VCol(cols=6, classes="py-1"):
                    v3.VSelect(label="Surface level", v_model=("surface_level",),
                               items=("grid_levels",), **DENSE)
                with v3.VCol(cols=6, classes="py-1"):
                    v3.VSelect(label="Trailing edge", v_model=("te_variant",),
                               items=("te_variants",), **DENSE)
            with v3.VRow(classes="mt-1"):
                with v3.VCol(cols=12):
                    v3.VBtn("Build geometry", block=True, color=("accent",),
                            loading=("busy",), click=app.build_geometry,
                            prepend_icon="mdi-cube-outline")
                with v3.VCol(cols=12, classes="pt-0"):
                    v3.VBtn("Reset to baseline", block=True, variant="text",
                            size="small", click=app.reset_design)

    with v3.VCard(**CARD, v_if="geometry_ready"):
        _section("Planform")
        with v3.VCardText(classes="pt-0"):
            _stat_row("Span", "planform.span_m?.toFixed(4) + ' m'")
            _stat_row("Reference area", "planform.area_m2?.toFixed(4) + ' m²'")
            _stat_row("Mean aerodynamic chord", "planform.mac_m?.toFixed(4) + ' m'")
            _stat_row("Aspect ratio", "planform.aspect_ratio?.toFixed(3)")
            v3.VDivider(classes="my-2")
            _stat_row("Triangles", "surface_stats.triangles")
            _stat_row("Points", "surface_stats.points")
            _stat_row("Wetted area", "surface_stats.wetted_area_m2?.toFixed(4) + ' m²'")
            _stat_row("Edge length", "surface_stats.min_edge_m?.toExponential(2) + ' … ' "
                                     "+ surface_stats.max_edge_m?.toExponential(2) + ' m'")
            v3.VDivider(classes="my-2")
            v3.VSelect(label="Colour by", v_model=("geometry_color",),
                       items=(["label", "span_fraction"],), **DENSE)


def mesh_panel(app):
    gmsh = app.profile.mesher == "gmsh"
    with v3.VCard(**CARD):
        _section(f"{app.profile.mesher_label}",
                 "Settings are written into a policy overlay, then the study's own mesher runs")
        with v3.VCardText(classes="pt-0"):
            if gmsh:
                with v3.VExpansionPanels(multiple=True, model_value=([0, 1],), variant="accordion"):
                    with v3.VExpansionPanel():
                        v3.VExpansionPanelTitle("Surface sizing", classes="text-caption")
                        with v3.VExpansionPanelText():
                            with v3.VRow():
                                _number("Surface edge / L", "mesh_settings.surface_edge_over_L", step=0.005)
                                _number("TE edge / L", "mesh_settings.te_surface_edge_over_L", step=0.002)
                                _number("Tip edge / L", "mesh_settings.tip_surface_edge_over_L", step=0.002)
                    with v3.VExpansionPanel():
                        v3.VExpansionPanelTitle("Boundary layer", classes="text-caption")
                        with v3.VExpansionPanelText():
                            with v3.VRow():
                                _number("First cell / L", "mesh_settings.first_cell_height_over_L", step=1e-4)
                                _number("Prism layers", "mesh_settings.prism_layers", step=1)
                                _number("Growth ratio", "mesh_settings.prism_growth_ratio", step=0.01)
                    with v3.VExpansionPanel():
                        v3.VExpansionPanelTitle("Volume core", classes="text-caption")
                        with v3.VExpansionPanelText():
                            with v3.VRow():
                                _number("Near core / L", "mesh_settings.near_core_edge_over_L", step=0.01)
                                _number("Far core / L", "mesh_settings.far_core_edge_over_L", step=0.01)
                                _number("Wake edge / L", "mesh_settings.wake_edge_over_L", step=0.01)
                                _number("Max growth", "mesh_settings.core_max_growth_ratio", step=0.01)
                    with v3.VExpansionPanel():
                        v3.VExpansionPanelTitle("Far field", classes="text-caption")
                        with v3.VExpansionPanelText():
                            with v3.VRow():
                                _number("Upstream / L", "mesh_settings.upstream_over_L", step=0.5)
                                _number("Downstream / L", "mesh_settings.downstream_over_L", step=0.5)
                                _number("Radial / L", "mesh_settings.radial_over_L", step=0.5)
                                _number("Wake length / L", "mesh_settings.wake_length_over_L", step=0.5)
                    with v3.VExpansionPanel():
                        v3.VExpansionPanelTitle("Algorithms", classes="text-caption")
                        with v3.VExpansionPanelText():
                            with v3.VRow():
                                with v3.VCol(cols=12, classes="py-1"):
                                    v3.VSelect(label="Surface algorithm",
                                               v_model=("mesh_settings.surface_algorithm",),
                                               items=("algorithms_2d",), **DENSE)
                                with v3.VCol(cols=12, classes="py-1"):
                                    v3.VSelect(label="Volume algorithm",
                                               v_model=("mesh_settings.volume_algorithm",),
                                               items=("algorithms_3d",), **DENSE)
                                with v3.VCol(cols=7, classes="py-1"):
                                    v3.VSelect(label="Optimiser", v_model=("mesh_settings.optimizer",),
                                               items=("optimizers",), **DENSE)
                                _number("Passes", "mesh_settings.optimize_passes", step=1, cols=5)
                with html.Div(classes="text-caption text-medium-emphasis mt-2"):
                    html.Span("Estimated cells: {{ mesh_estimate.toLocaleString() }}")
            else:
                with v3.VRow():
                    with v3.VCol(cols=6, classes="py-1"):
                        v3.VSelect(label="Volume level", v_model=("pyhyp_settings.volume_level",),
                                   items=("pyhyp_levels",), **DENSE)
                    with v3.VCol(cols=6, classes="py-1"):
                        v3.VSelect(label="Surface level", v_model=("pyhyp_settings.surface_level",),
                                   items=("pyhyp_levels",), **DENSE)
                    _number("Smoothing εₑ", "pyhyp_settings.eps_e", step=0.1)
                    _number("Constant layers", "pyhyp_settings.n_constant", step=1)
                    _number("Design index", "pyhyp_settings.development_index", step=1)
                with html.Div(classes="text-caption text-medium-emphasis mt-2"):
                    html.Span("Runs in the conda mach-aero interpreter as a subprocess.")

            v3.VBtn(f"Generate mesh", block=True, color=("accent",), classes="mt-3",
                    loading=("busy",), click=app.build_mesh, prepend_icon="mdi-grid")

    with v3.VCard(**CARD, v_if="mesh_ready"):
        _section("Mesh")
        with v3.VCardText(classes="pt-0"):
            _stat_row("Cells", "mesh_stats.cells?.toLocaleString()")
            _stat_row("Points", "mesh_stats.points?.toLocaleString()")
            _stat_row("Cell types", "Object.entries(mesh_stats.cell_types || {})"
                                    ".map(([k,v]) => k + ' ' + v).join(', ')")
            _stat_row("Extent", "(mesh_stats.extent_m || []).map(v => v.toFixed(2)).join(' × ') + ' m'")
            v3.VDivider(classes="my-2")
            v3.VSwitch(label="Show edges", v_model=("mesh_show_edges",),
                       density="compact", hide_details=True, color=("accent",))
            v3.VSwitch(label="Cut open", v_model=("mesh_clip",),
                       density="compact", hide_details=True, color=("accent",))
            v3.VSlider(v_model=("mesh_clip_position",), min=0.0, max=1.0, step=0.01,
                       density="compact", hide_details=True, v_if="mesh_clip",
                       color=("accent",))
            v3.VSelect(label="Colour by quality", v_model=("mesh_quality_field",),
                       items=(["none", "scaled_jacobian", "aspect_ratio", "condition"],),
                       classes="mt-2", **DENSE)


def solver_panel(app):
    su2 = app.profile.solver == "su2"
    with v3.VCard(**CARD):
        _section("Flow conditions")
        with v3.VCardText(classes="pt-0"):
            with v3.VRow():
                _number("Mach", "flow.mach", step=0.01)
                _number("Angle of attack", "flow.alpha_deg", step=0.5, suffix="°")
                _number("Sideslip", "flow.beta_deg", step=0.5, suffix="°")
                _number("Reynolds", "flow.reynolds", step=1e5)
                _number("Temperature", "flow.temperature_k", step=1.0, suffix="K")
                _number("Reference area", "flow.area_ref_m2", step=0.01, suffix="m²")
                _number("Reference chord", "flow.chord_ref_m", step=0.01, suffix="m")

    with v3.VCard(**CARD):
        _section(app.profile.solver_label, "Turbulence model and numerics")
        with v3.VCardText(classes="pt-0"):
            if su2:
                with v3.VRow():
                    with v3.VCol(cols=12, classes="py-1"):
                        v3.VSelect(label="Turbulence model", v_model=("su2.turbulence",),
                                   items=("su2_turbulence",), **DENSE)
                    with v3.VCol(cols=6, classes="py-1"):
                        v3.VSelect(label="Convective scheme", v_model=("su2.convective",),
                                   items=("convective_schemes",), **DENSE)
                    with v3.VCol(cols=6, classes="py-1"):
                        v3.VSelect(label="Limiter", v_model=("su2.limiter",),
                                   items=("limiters",), **DENSE)
                    _number("Venkatakrishnan coeff.", "su2.venkat_coefficient", step=0.05)
                    _number("CFL", "su2.cfl", step=1.0)
                    _number("CFL ceiling", "su2.cfl_ceiling", step=10.0)
                    with v3.VCol(cols=6, classes="py-1"):
                        v3.VSelect(label="Preconditioner", v_model=("su2.linear_preconditioner",),
                                   items=("preconditioners",), **DENSE)
                    _number("Linear iterations", "su2.linear_iterations", step=1)
                    _number("Multigrid levels", "su2.multigrid_levels", step=1)
                    _number("Iterations", "su2.iterations", step=100)
                    _number("Stop residual", "su2.stop_residual", step=0.5)
                    _number("MPI ranks", "su2.processes", step=1)
                v3.VSwitch(label="MUSCL reconstruction", v_model=("su2.muscl",),
                           density="compact", hide_details=True, color=("accent",))
                v3.VSwitch(label="Adaptive CFL", v_model=("su2.cfl_adaptive",),
                           density="compact", hide_details=True, color=("accent",))
                v3.VSwitch(label="Newton–Krylov", v_model=("su2.newton_krylov",),
                           density="compact", hide_details=True, color=("accent",))
                with html.Div(classes="text-caption text-medium-emphasis mt-1"):
                    html.Span("Newton–Krylov is the setting the S7 solver study found "
                              "decisive; it bypasses multigrid when active.")
            else:
                with v3.VRow():
                    with v3.VCol(cols=12, classes="py-1"):
                        v3.VSelect(label="Turbulence model", v_model=("adflow.turbulence",),
                                   items=("adflow_turbulence",), **DENSE)
                    with v3.VCol(cols=6, classes="py-1"):
                        v3.VSelect(label="Equations", v_model=("adflow.equation",),
                                   items=("adflow_equations",), **DENSE)
                    with v3.VCol(cols=6, classes="py-1"):
                        v3.VSelect(label="Smoother", v_model=("adflow.smoother",),
                                   items=("adflow_smoothers",), **DENSE)
                    _number("CFL", "adflow.cfl", step=0.1)
                    _number("CFL coarse", "adflow.cfl_coarse", step=0.1)
                    _number("Cycles", "adflow.iterations", step=100)
                    _number("Turb subiterations", "adflow.n_subiterations", step=1)
                    _number("L2 convergence", "adflow.l2_convergence", step=1e-9)
                    _number("MPI ranks", "adflow.processes", step=1)

            with v3.VRow(classes="mt-2"):
                with v3.VCol(cols=8):
                    v3.VBtn("Run", block=True, color=("accent",), click=app.start_solver,
                            prepend_icon="mdi-play", disabled=("run_status === 'running'",))
                with v3.VCol(cols=4):
                    v3.VBtn("Stop", block=True, variant="tonal", color="error",
                            click=app.stop_solver, disabled=("run_status !== 'running'",))


def post_panel(app):
    with v3.VCard(**CARD):
        _section("Results")
        with v3.VCardText(classes="pt-0"):
            v3.VBtn("Load latest solution", block=True, color=("accent",),
                    loading=("busy",), click=app.load_results,
                    prepend_icon="mdi-chart-areaspline")
            v3.VSelect(label="Source", v_model=("post_source",), classes="mt-3",
                       items=("[...post_files.surface, ...post_files.volume]",), **DENSE)
            v3.VSelect(label="Field", v_model=("post_field",), classes="mt-2",
                       items=("post_fields",), **DENSE)
            v3.VSelect(label="Colour map", v_model=("post_colormap",), classes="mt-2",
                       items=("colormaps",), **DENSE)
            v3.VDivider(classes="my-3")
            v3.VSwitch(label="Cut plane", v_model=("post_slice",),
                       density="compact", hide_details=True, color=("accent",))
            with html.Div(v_if="post_slice"):
                v3.VSelect(label="Normal", v_model=("post_slice_axis",),
                           items=(["X", "Y", "Z"],), classes="mt-2", **DENSE)
                v3.VSlider(v_model=("post_slice_position",), min=0.0, max=1.0, step=0.01,
                           density="compact", hide_details=True, color=("accent",))

    with v3.VCard(**CARD, v_if="post_summary.field"):
        _section("Field statistics")
        with v3.VCardText(classes="pt-0"):
            _stat_row("Field", "post_summary.field")
            _stat_row("Minimum", "post_summary.min?.toPrecision(5)")
            _stat_row("Maximum", "post_summary.max?.toPrecision(5)")
            _stat_row("Mean", "post_summary.mean?.toPrecision(5)")
            _stat_row("95th percentile", "post_summary.p95?.toPrecision(5)")
            _stat_row("99th percentile", "post_summary.p99?.toPrecision(5)")

    with v3.VCard(**CARD, v_if="Object.keys(forces || {}).length"):
        _section("Integrated forces")
        with v3.VCardText(classes="pt-0"):
            with html.Div(v_for="(value, key) in forces", key="key"):
                with html.Div(classes="d-flex justify-space-between text-caption py-1"):
                    html.Span("{{ key }}", classes="text-medium-emphasis")
                    html.Span("{{ typeof value === 'number' ? value.toPrecision(6) : value }}",
                              classes="font-weight-medium")


# --------------------------------------------------------------------------- #

def build_layout(app):
    state, ctrl = app.state, app.server.controller

    with SinglePageWithDrawerLayout(app.server, width=430,
                                    theme=("'dark'",)) as layout:
        layout.title.set_text(app.profile.title)

        with layout.toolbar:
            v3.VSpacer()
            html.Span("{{ subtitle }}", classes="text-caption text-medium-emphasis mr-4")
            html.Span("{{ machine }}", classes="text-caption text-medium-emphasis mr-4")
            v3.VProgressCircular(indeterminate=True, size=18, width=2,
                                 v_if="busy", classes="mr-2", color=("accent",))
            html.Span("{{ stage }}", v_if="busy", classes="text-caption mr-4")
            v3.VBtn(icon="mdi-crop-free", variant="text", size="small",
                    click=app.scene.reset_camera)
            with v3.VMenu():
                with v3.Template(v_slot_activator="{ props }"):
                    v3.VBtn(icon="mdi-axis-arrow", variant="text", size="small",
                            v_bind="props")
                with v3.VList(density="compact"):
                    with v3.VListItem(v_for="v in view_options", key="v",
                                      click=(app.set_view, "[v]")):
                        v3.VListItemTitle("{{ v }}")

        with layout.drawer as drawer:
            drawer.width = 430
            with v3.VTabs(v_model=("tab",), grow=True, density="compact"):
                v3.VTab("Geometry", value="geometry")
                v3.VTab("Mesh", value="mesh")
                v3.VTab("Solver", value="solver")
                v3.VTab("Results", value="post")
            with html.Div(classes="pa-3", style="overflow-y:auto"):
                with html.Div(v_if="tab === 'geometry'"):
                    geometry_panel(app)
                with html.Div(v_if="tab === 'mesh'"):
                    mesh_panel(app)
                with html.Div(v_if="tab === 'solver'"):
                    solver_panel(app)
                with html.Div(v_if="tab === 'post'"):
                    post_panel(app)

                v3.VAlert(text=("error",), v_if="error", type="error",
                          density="compact", variant="tonal", classes="mt-2")

        with layout.content:
            with v3.VContainer(fluid=True, classes="pa-0 fill-height"):
                with html.Div(style="position:relative; width:100%; height:100%"):
                    view = vtk_widgets.VtkRemoteView(
                        app.scene.window, interactive_ratio=1, ref="view")
                    app.html_view = view
                    ctrl.view_update = view.update
                    ctrl.view_reset_camera = view.reset_camera

                    # Live monitor floats over the viewport while a solve runs.
                    with html.Div(
                        v_if="tab === 'solver'",
                        style=("position:absolute; right:14px; top:14px; width:640px;"
                               "max-width:52vw; background:rgba(13,17,23,.94);"
                               "border:1px solid #30363d; border-radius:10px; padding:12px;"
                               "backdrop-filter:blur(6px)"),
                    ):
                        with html.Div(classes="d-flex align-center mb-2"):
                            v3.VChip("{{ run_status }}", size="x-small", label=True,
                                     color=("run_status === 'running' ? 'primary' : "
                                            "run_status === 'converged' ? 'success' : "
                                            "run_status === 'idle' ? 'grey' : 'error'",),
                                     classes="mr-2")
                            html.Span("iteration {{ run_iteration }}",
                                      classes="text-caption mr-3")
                            html.Span("{{ run_wall.toFixed(0) }} s", classes="text-caption")
                            v3.VSpacer()
                            html.Span("{{ convergence.orders_dropped ? "
                                      "convergence.orders_dropped.toFixed(3) + ' orders' : '' }}",
                                      classes="text-caption font-weight-medium")
                        html.Div(v_html=("residual_svg",))
                        html.Div(v_html=("force_svg",), classes="mt-1")

                    # Rolling log, bottom-left, for every stage.
                    with html.Div(
                        v_if="log_lines.length || solver_log.length",
                        style=("position:absolute; left:14px; bottom:14px; right:14px;"
                               "max-height:168px; overflow-y:auto;"
                               "background:rgba(13,17,23,.92); border:1px solid #30363d;"
                               "border-radius:8px; padding:8px 12px;"
                               "font:11.5px ui-monospace,Menlo,monospace; color:#c9d1d9"),
                    ):
                        html.Div("{{ line }}",
                                 v_for="line in (tab === 'solver' && solver_log.length "
                                       "? solver_log : log_lines)",
                                 key="line", style="white-space:pre-wrap")

        return layout
