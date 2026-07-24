# Standalone pyGeo BWB generator

This workflow generates the same segmented BWB definition used by Aeris,
but keeps pyGeo as the only 3-D geometry/lofting engine. It does not create
an AeroSandbox `Wing` or `Airplane`, and it does not change anything under
`src/aeris`.

The standalone layer deliberately reuses two deterministic Aeris functions:

- `generate_bwb_planform_from_sample`
- `build_section_geometry_from_sample`

This prevents the BWB definition from drifting. The new YAML presents the
design variables in physical form (`c1...c4` and `b1...b3`) and converts
them to Aeris's internal ratio representation before those functions run:

```text
c2_ratio = c2 / c1
c3_ratio = c3 / c1
c4_ratio = c4 / c1
b_total   = b1 + b2 + b3
b3_ratio  = b3 / b_total
split     = b1 / (b1 + b2)
```

The four airfoils are fixed in the YAML and resolved from
`data/airfoil_database`. Planform, sweep, twist, and dihedral variables are
sampled with a deterministic Latin hypercube.

## Run

From the repository root:

```bash
.venv/bin/python standalone/pygeo_bwb_generator/generate.py \
  --config standalone/pygeo_bwb_generator/config.yaml
```

Module execution (`python -m standalone.pygeo_bwb_generator.generate`) is
equivalent.

## GUI

pyGeo is now exposed by the production Aeris GUI rather than a second GUI
implementation:

```bash
aeris gui run
```

Open **3D Geometry**. The page uses the real Aeris YAML schema, CLI commands,
`data/runs` layout, manifests, and artifact paths. It supports:

- YAML, pyGeo-only, AeroSandbox-only, and dual-backend comparison execution;
- the four fixed b0-b3 profiles from `data/airfoil_database`;
- the flat b0-b1 root-panel invariant for pyGeo;
- native pyGeo loft/section/CST previews and quality metrics;
- comparison CSV/overlay inspection without geometry-object translation;
- neutral IGES/Tecplot/NPZ/DAT exports and named physical-control STEP bodies;
- the existing symmetric/differential command pair and Gmsh STEP audit.

The previous launch command remains a compatibility entry point and opens the
same integrated Aeris Geometry page:

```bash
.venv/bin/python -m streamlit run \
  standalone/pygeo_bwb_generator/gui.py
```

The original standalone interface is preserved as `gui_legacy.py` for study
reproduction only. New operator work should use `aeris gui run`.

Useful focused runs:

```bash
# Validate the YAML and write the DoE table without building geometry.
.venv/bin/python standalone/pygeo_bwb_generator/generate.py \
  --config standalone/pygeo_bwb_generator/config.yaml \
  --dry-run

# One complete smoke geometry, including plots and CAD/curve exports.
.venv/bin/python standalone/pygeo_bwb_generator/generate.py \
  --config standalone/pygeo_bwb_generator/config.yaml \
  --n-samples 1 \
  --output artifacts/pygeo_bwb_generator/smoke

# Build selected rows from the deterministic DoE.
.venv/bin/python standalone/pygeo_bwb_generator/generate.py \
  --config standalone/pygeo_bwb_generator/config.yaml \
  --indices 0,7,15
```

## Outputs

The output root contains:

- `doe.csv`: direct physical variables, normalized LHS coordinates, derived
  Aeris ratios, and stable geometry IDs;
- `geometry_metrics.csv`: span, area, MAC, aspect ratio, volume, wetted
  area, loft/CST quality, runtime, and status;
- `doe_parallel_coordinates.png` and `geometry_metrics.png`;
- `campaign_manifest.json` and an exact YAML snapshot.

Each case directory contains:

- `case_manifest.json`, with direct and internal Aeris variables;
- `authored_stations.csv`, `extracted_sections.csv`, CST coefficients, and
  every realised section as a Selig `.dat`;
- `pygeo_surface.igs`, `pygeo_surface.dat`, and `pygeo_surface.npz`;
- neutral full, neutral split, and physical deflected STEP assemblies, plus
  an optional Gmsh re-import/solid-count audit;
- named per-body STEP files under `cad/bodies/`;
- diagnostic physical-surface STL, OBJ, VTK, and NPZ under `mesh_handoff/`;
- physical/neutral PNG visualizations and section/planform plots;
- control, physical-CAD, and mesh-handoff manifests with state IDs, units,
  topology, solid QC, hinge accuracy, and overlap evidence.

## Conventions

- `c1 > c2 > c3 > c4` is guaranteed globally by non-overlapping YAML
  ranges. Invalid bounds fail before sampling.
- `b1`, `b2`, and `b3` are positive semispan segment lengths.
- Aeris `section_bounds.dihedral_root_deg` and standalone
  `dihedral_b1_deg` are both hard-fixed at `0`. The latter keeps the complete
  first/inboard panel flat; a zero angle only at the centerline is insufficient
  for mirrored finite-thickness solids.
- The reconstructed CAD root is canonicalized onto XZ (`y=0`) and QC rejects
  any non-negligible right/left neutral-volume intersection.
- Sweep bounds are positive conventional aft-sweep magnitudes. Aeris's
  internal `BWBDesignSample` stores them as negative values.
- `b0...b3` airfoils are assigned with the same span-group convention used
  by the current BWB configuration.
- `frame_mode: aeris_frame` reconstructs the local section orientation used
  by the current Aeris wing definition. It is implemented numerically in the
  pyGeo bridge and does not build an AeroSandbox geometry object.

The CST fit is an exported section representation and quality diagnostic.
The IGES and sampled surfaces remain the realised pyGeo loft.

The generator records one trailing-edge control definition using the same
metadata shape as Aeris (`hinge_point`, spanwise start/end, symmetric and
differential command mix). It calculates neutral control area, hinge length,
and span. The physical CAD backend then:

1. reconstructs closed solids from realised, planarised pyGeo sections;
2. cuts a fixed cove sized for `design_deflection_limit_deg`;
3. lofts a separate elevon over the configured span;
4. rotates each elevon rigidly about a straight three-dimensional hinge axis;
5. applies `right = delta_e + delta_a`, `left = delta_e - delta_a`;
6. rejects invalid solids or material intersection and records every
   reconstruction/hinge approximation;
7. measures every sampled native-pyGeo OML point against the tessellated
   neutral OCC surface and enforces `max_master_to_cad_deviation_cref`, then
   optionally re-imports the STEP assembly in Gmsh to verify its solid count.

The neutral IGES is still the master pyGeo OML. STEP is an OCC solid
reconstruction because pyGeo is a surface-lofting tool, not a general
split/sew/solid Boolean kernel.

## CFD mesh handoff

There are two routes; they should not be mixed:

- **Neutral geometry / ADflow:** realised pyGeo sections feed the existing
  Aeris structured single-body surface topology, then PLOT3D and pyHyp volume
  extrusion.
- **Split/gapped deflected controls:** import the deflected STEP assembly into
  a CAD-aware mesher. Aeris already has `cad_gmsh_tet_v1` for an initial
  Gmsh/SU2 geometry, Euler, or wall-function tier. Production wall-resolved
  CFD still needs a prism-layer-capable backend.

The visible void in the current CAD is intentional fluid domain, not a missing
wall. The implemented `simple_clearance_cove` prioritizes collision-free rigid
rotation over reproducing a specific manufactured hinge; it is screening CAD,
not automatically the best production-CFD representation.

Choose the control treatment by fidelity role:

- **Sealed/morphed surface:** preferred baseline for a large DoE and consistent
  AVL/CFD correlation when hinge leakage is outside the research question.
- **Resolved physical gap/cove:** use only for selected high-fidelity cases when
  real dimensions and leakage physics matter.
- **Simple clearance cove (current):** useful for kinematic, CAD, mesher, and
  collision screening, but do not interpret its gap drag as aircraft truth.

For an explicit gap, the volume mesher must fill it with fluid, retain multiple
named wall bodies, resolve several cells across the minimum clearance, and grow
valid prism layers on both the wing cove and control nose.
The neutral pyHyp mesh must not simply be rotated and reused for a physical
split control: block connectivity, cove/gap resolution, wall normals, and
volume-cell quality would no longer be valid. ADflow needs either a dedicated
multiblock topology regenerated per command or an overset strategy. Mesh
deformation is appropriate only for sealed, small-deflection studies where a
physical gap is deliberately excluded.

Constant-span cuts through a smooth swept/dihedral loft are not mathematically
required to be planar. The config therefore records two planarity levels:
`warn_plane_warp_chord` marks sections that should be planarized before a
2-D use such as CST/NeuralFoil, while `max_plane_warp_chord` is the hard
geometry gate. Both the raw warp and the decision are stored per case.

