# AERIS workbenches

Two desktop applications over the same four-stage workflow — geometry, mesh,
solve, results — one per meshing strategy.

| | S7 workbench | S6 workbench |
|---|---|---|
| launch | `python3 apps/s7_workbench.py` | `python3 apps/s6_workbench.py` |
| port | 8770 | 8771 |
| geometry | pyGeo | pyGeo |
| mesher | Gmsh, unstructured tet + prism | pyHyp, hyperbolic structured |
| solver | SU2 8.5 | ADflow |
| runs in | project `.venv`, all in one place | GUI in `.venv`, mesher and solver in conda |

Both open in the browser and render with VTK, the same engine ParaView uses.

## The environment split, and why it shapes the design

No single interpreter on this machine can run both chains:

| capability | project `.venv` (3.13) | conda `mach-aero` (3.11) |
|---|---|---|
| pyGeo / pySpline | yes | no |
| Gmsh | yes | no |
| SU2_CFD | yes (binary) | — |
| VTK / PyVista / trame | yes | no |
| pyHyp | no — `libcgns.so.4.5` will not load | yes |
| ADflow | no | yes |

So the interface always runs in the `.venv` — it is the only one that can draw —
and pyHyp and ADflow are launched in the conda interpreter as subprocesses. That
is also how a commercial workbench is built: the GUI process is never the
solver, so a diverging run cannot take the window down with it.

The Environment panel probes all ten tools at startup and reports what is
actually available rather than assuming.

## The four tabs

**Geometry** — all 20 design variables as sliders, with bounds read live from
`configs/geometry/bwb.yaml`, so the workbench and the DoE cannot disagree about
the design space. Build runs the real pyGeo loft. Reports span, area, MAC,
aspect ratio and a per-station table; colours the surface by patch or span.

**Mesh** — every sizing, boundary-layer, core, far-field and algorithm setting,
with a live cell-count estimate as you change them. Cut the mesh open with a
clip plane, show element edges, colour by scaled Jacobian, aspect ratio or
condition number.

**Solver** — flow conditions, turbulence model, convective scheme, limiter, CFL
and its adaptation, preconditioner, multigrid, Newton–Krylov. Run and Stop.
While it runs, a floating monitor plots **every residual channel and CL/CD/CMy
live**, against the convergence gate.

**Results** — load the solution, colour by any field the solver wrote (Cp, Mach,
y+, skin friction …), cut a plane through the volume, read field statistics and
the integrated force set.

## What the settings actually do

Neither mesher nor solver is reimplemented. The workbench builds a **policy
overlay** — a deep copy of the study's `POLICY.yaml` with your settings written
in — and then calls the study's own generator. So a mesh built here is
reproducible from a policy file, and the numbers you move are the numbers the
study freezes.

Every run writes into `apps/workspace/<strategy>/` with the resolved settings
beside the result.

## Requirements

Everything needed is already installed. Rendering needs a display: on the
desktop session it uses GLX; over SSH it falls back to EGL or OSMesa, and the
Scene reports which backend it chose.

## Verified

Built and tested end to end on this machine: geometry (5.4 s), a 47,967-cell
half-domain Gmsh mesh (4.0 s), an SU2 solve streaming eight live channels, and
post-processing reading 14 fields off the result. The S6 chain's pyHyp and
ADflow interpreters were probed and import cleanly; those two stages have not
been run end to end from the GUI yet.
