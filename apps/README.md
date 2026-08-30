# AERIS workbenches

Two desktop applications over the same four-stage workflow — geometry, mesh,
solve, results — one per meshing strategy.

| | S7 workbench | S6 workbench |
|---|---|---|
| launch | `python3 apps/s7_workbench.py` | `python3 apps/s6_workbench.py` |
| port | 8770 | 8771 |
| geometry | pyGeo | pyGeo |
| mesher | Gmsh, unstructured tet + prism | pyHyp / S6 bounded mesh atlas |
| solver | SU2 8.5 | ADflow |
| runs in | project `.venv`, all in one place | GUI in `.venv`, mesher and solver in conda |

Both open in the browser and render with VTK, the same engine ParaView uses.

## Read this first if you are looking at S6

The S6 tab has **two mesh generation modes and they are not interchangeable.**

**Governed S6 Atlas** is the evidence path. It calls S6's own campaign —
`campaign.make_manifest` then `campaign.mesh_case` — which ranks the frozen
atlas templates by design distance, deforms the nearest one onto this exact
target surface, tries S6's automatic target-specific fallback when no template
reaches the preferred quality, writes the CGNS, **reopens it and audits it
again**, and applies the production floor of 0.10 minimum scaled Jacobian. None
of that logic lives in this application; the workbench calls the study's
functions and renders their reports.

**Experimental direct pyHyp march** is a development tool. It marches pyHyp
directly on the structured surface. There is no atlas, no template, no
deformation and no registry provenance behind the result. It IS audited — the
written CGNS is reopened and scored with `shared.volume_qc.volume_report` and
`deform`'s own interface and wall-spacing reports — but an audited direct march
is not S6 acceptance, and the interface labels it `experimental` everywhere it
appears.

**Governed mode never falls back to the direct march.** If the registry, the
flow definitions or the template artifacts are missing, the mode is disabled and
says exactly what is missing and which environment variable points at it.

### What governed mode needs

| variable | what it points at | default |
|---|---|---|
| `S6_REGISTRY` | the frozen template registry from `campaign.py build-registry` | `<repo>/template_registry.json` |
| `S6_FLOWS_CSV` | flow definitions | `.../S6_bounded_mesh_atlas/examples/flows_single.csv` |
| `S6_CAMPAIGN_ROOT` | where campaign output is written | `apps/workspace/s6_campaign` |

`campaign.verify_registry` is what decides availability, so a registry whose
CGNS has been moved or regenerated fails at startup rather than half way through
a mesh. **No registry exists in this repository today**, so governed mode is
disabled on this machine until one is built. See "Still blocked" below.

## Geometry identity

Geometry has one explicit source, chosen on the Geometry tab:

* **Interactive design** — the sliders build one pyGeo case.
* **Development-set index** — S6's own locked geometry at one index. The sliders
  are moved onto that design's values and **disabled**, so the two sources
  cannot describe different aircraft at the same time.

Whichever is chosen, one `design.GeometryCase` feeds the viewport, the planform
summary, the S6 structured surface, the mesh and the solver's `areaRef` and
`chordRef`. It carries a **design fingerprint** that is shown in the interface
and stamped into every run directory and provenance record.

`areaRef` is **half** the planform area, matching `campaign.solve_case`'s
`area_ref=0.5 * refs["area_m2"]` for a half model.

## Qualified grid family

The S6 Geometry tab selects **G1 coarse / G2 medium / G3 fine**, read at call
time from `qualification._grid_family()`. Selecting one sets the complete
coupled definition — surface level and its chord/end/collar/span counts, the
wall-normal point count, and the wall spacing — together:

| grid | surface | chord × span | N | s0/L | volume level |
|---|---|---|---|---|---|
| G1 coarse | smoke | 33 × 89 | 129 | 7.2e-6 | smoke |
| G2 medium | medium | 49 × 127 | 193 | 5.1e-6 | fine |
| G3 fine | fine | 65 × 179 | 257 | 3.6e-6 | production |

The wall spacing is the reason a surface level alone is not a grid: G1's
7.2e-6 is not `resolution.S6_FIRST_CELL_FRACTION["smoke"]`, which is 8.8e-6.

There is no G0 and no G4. "Manual" is available and is labelled as
experimental — a combination the study has no acceptance evidence for.

The **Experimental structured surface controls** vary that surface only. pyHyp
marches the surface rigidly outward, so there is no arbitrary 3D local
refinement in S6: refining a region of the volume means refining the surface
patch beneath it. Every control is declared in `aeris_workbench/controls.py`
with its range and the effective input it reaches, the panel is generated from
that table, and a test asserts each one arrives at the mesher.

A cell-count estimate is shown before marching. It is exact rather than
approximate — surface quads × wall-normal cell layers ÷ coarsening — and
reproduces the 1,621,504-cell figure recorded from an earlier G1 march.

## Acceptance, and what the words mean

The interface shows distinct states and never collapses them:

`generated` → `audited_accepted` / `audited_rejected` for a mesh, and
`running` → `solve_completed` → `cfd_accepted` / `cfd_rejected` for a solve.

**A zero exit code means the process finished.** The solver status is reported
as `completed`, never `converged`. Acceptance is decided afterwards by S6's own
gates, reused rather than reimplemented: `campaign._force_plausibility_gate`,
`campaign._force_tail_gate`, `campaign._wall_yplus_gate`, and the 6.0-order
residual threshold. Every gate is shown with its actual value and its limit.

ADflow is enabled only for a mesh that passed the applicable audit, and the
button carries the reason when it is disabled.

### A surface control invalidates the GEOMETRY

Found by running the app rather than by testing it: changing a surface control
used to clear only the mesh. The structured surface is built on the geometry
tab, so `geometry_ready` stayed set and "Generate mesh" marched the PREVIOUSLY
built surface - 12,668 quads from a 33x89 surface while the boxes on screen read
29x75, under a label still claiming the surface matched G1. Surface controls now
invalidate the geometry exactly as a design slider does, and the grid selector
stops claiming a qualified grid the moment the numbers stop matching one.

The surface controls are also bound to ONE FLAT STATE KEY EACH (`s6c_<name>`),
for the reason already recorded above the design sliders: a widget bound into a
nested dict mutates that dict in the browser and the mutation does not reliably
return, so the box and the mesher can hold different numbers.

## No stale results

Every mesh and every solve writes to a fresh, immutable directory named
`<design fingerprint>_<settings hash>_<run id>`, created with `exist_ok=False`.

A pyHyp march counts as successful only when **all four** hold: the process
returned zero, pyHyp reported `march_completed`, the CGNS was written during
this run (checked by modification time *and* by digest change), and the written
mesh passes its audit. A leftover `wing_vol.cgns` from a previous attempt is
never accepted.

Changing the geometry source, a design slider, the grid, a mesh control or the
mode clears the mesh, the audit verdict, the solver state and the results.
Pressing Run with a mesh whose fingerprint and settings hash no longer match the
loaded geometry is refused.

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

Paths are configurable rather than hard-coded: `AERIS_MACH_AERO_ENV`,
`AERIS_MACH_AERO_PACKAGES`, `AERIS_WORKBENCH_WORKSPACE`, plus the three `S6_*`
variables above. Each keeps its measured local value as its default, and the
Mesh tab lists them with a tick or a cross when governed mode is unavailable.

## The four tabs

**Geometry** — the geometry source, all 20 design variables as sliders with
bounds read live from `configs/geometry/bwb.yaml`, the qualified grid selector
(S6) or tessellation level (S7), and the design fingerprint. Build runs the real
pyGeo loft and reports span, area, MAC, aspect ratio and a per-station table.

**Mesh** — for S6, the mode selector and either the governed registry summary or
the experimental march controls, with the cell estimate, the audit verdict as
gates, the per-template attempt table with each rejection reason, and the run
provenance. For S7, the full Gmsh sizing/boundary-layer/core/far-field/algorithm
set with a live cell estimate. Both: cut the mesh open, show edges, colour by
scaled Jacobian, aspect ratio or condition number.

**Solver** — flow conditions and solver settings, Run and Stop, and the CFD
acceptance card. While it runs, a floating monitor plots every residual channel
and CL/CD/CMy live against the convergence gate.

**Results** — the fields written by *this* run, cut planes, field statistics and
the integrated force set.

## What the settings actually do

Neither mesher nor solver is reimplemented, and S6 is never modified to suit the
application. For S7 the workbench builds a **policy overlay** — a deep copy of
the study's `POLICY.yaml` with your settings written in — and calls the study's
own generator. For S6 it calls `strategy_s6.build_surface`, `pyhyp_runner.prepare`
and `campaign.mesh_case`/`campaign.solve_case` directly. The one local mechanism
is a throwaway entry in `strategy_s6.LEVELS`, added and removed under a lock, so
the experimental controls can vary a resolution that S6 otherwise reads only
from its own table; the surface builder verifies afterwards that S6's four
declared levels are unchanged.

## What has actually been tested

Automated, in `tests/apps/test_s6_workbench.py` — 43 tests, all passing, with
the expensive subprocesses faked:

* the two geometry sources cannot be mixed, and a locked slider cannot change an
  indexed design;
* summary, surface, flow references and fingerprint all come from one case, and
  the structured surface is built from that case's `pygeo_result`;
* every declared surface control reaches `strategy_s6.build_surface`, and every
  march control reaches `pyhyp_runner.prepare`;
* the removed "Constant layers" control provably reached nothing —
  `prepare` has no such parameter and `nConstantStart` defaults to 5;
* a march that exits non-zero, or does not report `march_completed`, or does not
  rewrite the CGNS, is rejected and hands back no mesh;
* run directories are unique and cannot be reused;
* a failed solve does not expose an old `adflow_result.json`;
* changing a design variable, the grid or a mesh control clears mesh and results;
* a mesh below the 0.10 floor or with inverted cells cannot start ADflow;
* exit code 0 with no other evidence is `CFD_REJECTED`;
* governed mode refuses, and does not call `run_pyhyp`, when its artifacts are
  missing;
* G1/G2/G3 match `qualification._grid_family()` field by field, and G0/G4 raise;
* missing pyHyp, ADflow or MPI disables the correct buttons.

Also run and passing alongside them: `S6_bounded_mesh_atlas/test_s6.py` and
`tests/cfd/{test_pyhyp_options_snapshot,test_pyhyp_subprocess_inputs,test_volume_audit,test_adflow_adapter}.py`
— 120 tests in total. Ruff is clean across `apps/` and `tests/apps/`.

Manual, in-process, on this machine: the S6 geometry stage from both sources
(interactive and development index 5), producing a 13-block, 12,668-quad G1
surface and an exact 1,621,504-cell estimate at N129; downstream invalidation on
an index change; and the S7 geometry stage unaffected.

### A configuration that runs on 16 GiB

Measured end to end on this machine (i7-1255U, 16 GiB, ~11.8 GiB free):

| | surface | N | cells | min scaled Jacobian | ADflow peak | outcome |
|---|---|---|---|---|---|---|
| G1 | smoke 33x89 | 129 | 1,621,504 | +0.132 | >9.0 GiB | **killed** |
| manual | smoke 33x89 | 97 | 1,216,128 | +0.129 | >10.6 GiB | **killed** |
| manual | 29x75, max cell 0.020 | 97 | **912,768** | **+0.152** | **9.47 GiB** | **completed** |

The third row is the recipe: Geometry tab -> grid `G1 coarse` (to pick up its
wall spacing and tip settings), then `Manual`, then chord 29 / span 75 / max
spanwise cell 0.020, and wall-normal points 97 on the Mesh tab. It marches in
about a minute and ADflow runs it.

Note that its quality is BETTER than G1's (+0.152 against +0.132), so this is
not simply a degraded mesh - but it is not a qualified grid and carries no S6
acceptance evidence.

### ADflow memory, measured rather than inferred

`ADFLOW_BYTES_PER_CELL_PER_RANK` was 8000, inferred from two out-of-memory
kills. Sampling RSS during real start-ups, with volume and surface output
disabled, showed that was optimistic:

* 913 k cells, 1 rank: **9.47 GiB**, completed (11.1 KiB/cell)
* 1.22 M cells, 1 rank: over 10.55 GiB, killed (9.3 KiB/cell, still climbing)
* 1.62 M cells, 1 rank: over 9.04 GiB, killed
* 1.62 M cells, 4 ranks: over 9.11 GiB total, killed - **the same peak, sooner**

Three things follow. Ranks partition the work, not the footprint, so adding
them is not a way past a memory ceiling. The per-cell figure rises as the mesh
shrinks, so a meaningful part of the footprint is fixed overhead. And 11 KiB per
cell is high for structured RANS - the likely cause is this topology, since
S6's nose and base blocks are two cells across and ADflow stores two halo layers
each side, so those blocks cost about three times their interior.

The constant is now 11000 B/cell at an 0.85 budget fraction, calibrated so the
one configuration measured to complete is allowed and both measured to die are
refused. Allocation arrives in two steps, one at the end of preprocessing and
one at iteration 0, so **a run that has printed its first iteration line has not
yet proved it will survive.**

### Measured S6 marches

Both run through `Workbench.build_geometry` and `Workbench.build_mesh` — the
same code the buttons call — on the baseline development design, 12-thread
i7-1255U, 16 GiB:

| grid | surface | cells | march | min scaled Jacobian | audit |
|---|---|---|---|---|---|
| manual | coarse | 869,888 | 34 s | **-0.113** | **rejected** |
| G1 | smoke | 1,621,504 | 90 s | **+0.132** | **accepted**, all 8 gates |

The coarse result is the useful one: it marches, produces zero inverted cells
and a positive minimum volume, and still fails the 0.10 production floor on
scaled Jacobian. That is very likely why S6's qualified family has no member
below G1, and it is why the manual selector warns against `coarse` rather than
offering it as a cheap way out.

G1 at 1.62 M cells forecasts 12.1 GiB at the pessimistic 8 KiB/cell bound
against an 8.86 GiB budget, so ADflow declines it until "Run over the memory
budget" is set. At a realistic 1-3 KiB/cell the same mesh is 1.6-4.9 GiB.

## What has NOT been tested

* **No governed mesh has been produced**, because no template registry exists in
  this repository. The governed path is unit-tested against fakes only.
* **No CONVERGED ADflow solve has been produced.** One 25-cycle solve completed
  through the generated runner and returned forces, which proves the path runs;
  it is nowhere near converged, so the CFD acceptance gates have still only been
  exercised against synthetic inputs, and no reported coefficient means anything
  yet.

Treat the S6 mesh chain as measured and the S6 solve chain as wired but
unvalidated. Do not describe either as production-ready.

For S7, an earlier session ran geometry (5.4 s), a 47,967-cell half-domain Gmsh
mesh (4.0 s), an SU2 solve streaming eight live channels, and post-processing
reading 14 fields; the mesh and solve directories have moved since, so that path
is worth re-running before it is relied on.

## Still blocked

Governed S6 needs, in order:

1. frozen S1 template artifacts under a source root
   (`campaign.DEFAULT_S1_ROOT` or an explicit `--source-root`);
2. an enriched atlas manifest;
3. `campaign.py build-registry` output at `$S6_REGISTRY`.

Until (3) exists, only the experimental march is reachable, and the interface
says so.

## Requirements

Rendering needs a display: on the desktop session it uses GLX; over SSH it falls
back to EGL or OSMesa, and the Scene reports which backend it chose.
