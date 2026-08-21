# S2 Implementation Note - Cross-Field Tip Blocks

S2 uses a constrained cross-field method for the physical tip region, then projects the resulting block layout back to the prescribed OML.

## Algorithm

Create a support triangulation on the tip surface, solve a constrained cross-field, extract a quad/block candidate, smooth it in parameter space, project all points back to the original geometry, and record singularities and block connectivity.

## Inputs

- Tip surface from the BWB geometry contract
- Boundary constraints from leading edge, trailing edge, and tip perimeter
- Existing station and boundary-label schema
- Surface fidelity gate from `00_governance/gate_registry.yaml`
- Source paper: automatic multiblock 3D wing paper, sections 3.2-3.4

## Outputs

- support triangle mesh manifest
- cross-field solution manifest
- singularity and quad-extraction manifest
- projected tip-block mesh
- surface and volume QC with worst-region report

## Missing Details

The project does not currently contain a cross-field solver or QEx-style quad extraction implementation. A dependency or implementation decision is required before S2 can be an executable Stage 02 candidate.

## Dependencies

Available: `gmsh`, `numpy`, `scipy`, `pyhyp`, `cgnsutilities`, and `h5py`. Unavailable in both checked environments: `igl`, `pyigl`, `qex`, `quadpy`, and `meshio`. This makes S2 blocked until the project either installs an acceptable cross-field and quad-extraction stack or explicitly approves an in-house prototype.

## Risks

Nondeterministic singularity placement or topology drift across nearby geometries is fatal for production DSE. The source paper also showed that good surface quality can still produce weak volume quality.

## Smallest Feasible Prototype

After dependency approval, run a baseline-only tip experiment: triangulate the tip, impose LE/TE/tip boundary constraints, extract one block graph, project it back to the OML, and verify deterministic singularity/connectivity signatures across three repeated runs.
