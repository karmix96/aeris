# pyGeo realization backend

The pyGeo integration is a realization backend of the existing
`bwb_segmented_v1` generator. It is not a second BWB definition and it does
not translate a pyGeo object into an AeroSandbox object.

The shared Aeris pipeline remains:

```text
BWB config -> sampled design -> Aeris planform -> Aeris section records
                                               |-> AeroSandbox realization
                                               |-> pyGeo B-spline realization
```

This preserves one source of truth for the design variables, four fixed
station airfoils, control geometry, and sampled case identity.

## Selecting a backend

The two switches are independent.

| Configuration | AeroSandbox | pyGeo |
|---|---:|---:|
| `outputs.build_aerosandbox: true`, `pygeo.enabled: false` | yes | no |
| `outputs.build_aerosandbox: false`, `pygeo.enabled: true` | no | yes |
| both true | yes | yes |

Use both when numerical cross-checks or an AeroSandbox aerodynamic adapter are
needed. Use pyGeo only when the realised loft and extracted sections are the
authoritative geometry.

A complete pyGeo-only example is
`configs/geometry/paper1_bwb_pygeo.yaml`.

## Capabilities

The production backend provides:

- MDOLab pyGeo B-spline lifting-surface lofting;
- exact Aeris section-frame reconstruction without constructing an
  AeroSandbox geometry;
- fixed-span slicing of the realised loft;
- planarisation and CST fitting for every extracted section;
- CST and plane-warp quality gates;
- reference area, span, MAC, aspect ratio, volume, wetted area, and surface
  area from the realised geometry;
- neutral native IGES and Tecplot exports;
- sampled master-surface NPZ and extracted Selig DAT files;
- 3-D loft and section/CST visualisations;
- the frozen split-elevon physical CAD implementation;
- named STEP assemblies and per-body STEP files;
- STL, OBJ, VTK, and NPZ diagnostic surface exports;
- Gmsh STEP re-import audit and a mesh-handoff manifest.

## Root-panel invariant

When `pygeo.enforce_flat_root_panel: true`, both of these must be exactly
zero:

```yaml
section_bounds:
  dihedral_root_deg: 0.0
  dihedral_b1_deg: {min: 0.0, max: 0.0}
```

This keeps the complete b0-b1 panel flat and prevents mirrored
finite-thickness halves from penetrating at the symmetry plane. Equal
`min=max=0` bounds are accepted only for this pyGeo invariant; existing
Aeris configs retain their normal range validation.

## Controls and physical CAD

No new three-mode control model is introduced. The backend consumes the
existing Aeris control-surface definition. The current frozen physical-CAD
implementation supports exactly one symmetric trailing-edge surface and the
existing command pair:

```yaml
pygeo:
  commands:
    delta_e_sym_deg: 0.0
    delta_a_diff_deg: 0.0
```

Right and left commands are:

```text
right = delta_e_sym_deg + delta_a_diff_deg
left  = delta_e_sym_deg - delta_a_diff_deg
```

The native pyGeo IGES/Tecplot geometry remains the neutral master OML.
Deflected geometry is a named, split-solid reconstruction with fixed wing and
elevon bodies on each side. Its clearance cove is fluid domain and is intended
for robust screening and meshing studies, not as a resolved hinge mechanism.

## Mesh policy

For neutral geometry, the preferred high-quality route remains:

```text
realised pyGeo sections -> Aeris structured surface adapter
-> PLOT3D surface -> pyHyp volume -> ADflow
```

For a split, deflected elevon, do not rotate or reuse the connected neutral
surface mesh. The gap and cove change topology. Use:

```text
named multi-solid STEP -> CAD-aware surface/volume mesher -> CFD solver
```

The exported `mesh_handoff/mesh_handoff.json` records this policy and the
available artifacts. A future production viscous route should add prism
layers or overset/multi-block support; the facet exports are diagnostics, not
automatically solver-ready meshes.

## Running

```bash
# pyGeo only, as configured
aeris geometry generate --config configs/geometry/paper1_bwb_pygeo.yaml

# Realise the exact same Aeris case with both backends and compare them
aeris geometry generate \
  --config configs/geometry/paper1_bwb_pygeo.yaml \
  --build-aerosandbox

aeris geometry inspect --run-dir data/runs/<run_id>
```

All outputs are written inside the standard Aeris run directory under:

```text
artifacts/geometry/pygeo/
```

The primary index is `pygeo_manifest.json`. The Aeris
`geometry_summary.json` and top-level run `manifest.json` also include the
backend selection, pyGeo metrics, QC state, reference values, and artifact
paths. A dual-backend run additionally writes `backend_comparison.csv` and
`plots/pygeo_vs_aerosandbox.png`. The comparison is made from the two
independently realised versions of the shared Aeris sections; no geometry
translation is used.

## GUI

Launch the production operator interface with:

```bash
aeris gui run
```

Open **3D Geometry**. The GUI reads the same YAML schema and delegates to the
real `aeris geometry` commands. It supports pyGeo-only and dual-backend runs,
native pyGeo previews, numerical comparison evidence, and canonical CAD
artifacts under `data/runs`; it does not maintain a second geometry workflow.


## Runtime dependencies

pyGeo is optional and imported only when `pygeo.enabled` is true. Physical
CAD additionally requires CadQuery; STEP verification requires Gmsh. Run
`aeris geometry info` to see which optional components are available in the
active environment.

### AeroSandbox decoupling

The pyGeo-only geometry path is fully decoupled from AeroSandbox: the neutral
loft, exact frame reconstruction, section extraction, and their whole import
chain (generator `services` → `aerosandbox_adapter`, `reconstruction_export`,
`export`) build and run with `aerosandbox` unavailable. Every `aerosandbox`
import in the shared generator modules is lazy (in-function); all `asb.*`
annotations are strings under `from __future__ import annotations` and are never
evaluated. AeroSandbox is imported only when the AeroSandbox realization or the
dual-backend comparison is actually requested. A subprocess regression guard
(`tests/generators/bwb_segmented_v1/test_pygeo_aerosandbox_decoupled.py`) blocks
`aerosandbox` and rebuilds the loft frame, so a reintroduced module-level import
fails CI. AeroSandbox is still retained as the AVL serializer (see roadmap
step 4); that runtime coupling is intentional and separate.

