# S5 Implementation Note - Frozen RBF Block Transfer

S5 builds a reliable block layout on a reference geometry or section set, then transfers it to related BWB geometries using frozen landmark correspondence and RBF displacement mapping.

## Algorithm

Store a reference block graph in semantic coordinates, compute landmark displacements for each target BWB geometry, use RBF interpolation to transfer the block graph, project surface nodes back to the target OML, and preserve the connectivity signature.

## Inputs

- Frozen landmarks: `b0`, `b1`, `b2`, `b3`, leading edge, trailing edge, root, tip, planform breaks, and elevon boundaries
- Reference block graph and connectivity signature
- Projection/fidelity tolerances
- Topology-drift policy from `gate_registry.yaml`
- Source paper: Wang 2026, especially section 4.2

## Outputs

- reference topology package
- landmark correspondence table
- RBF conditioning and residual report
- transferred surface mesh and projection-error report
- connectivity signature and volume QC report

## Missing Details

The reference block graph has not been chosen. The accepted landmark set must include enough interior/support points to avoid poor RBF conditioning on high sweep/twist/dihedral combinations.

## Dependencies

Available: `scipy.interpolate.RBFInterpolator`, `numpy`, AERIS geometry code, `pyhyp`, `cgnsutilities`, and `h5py`. No extra RBF package is required for the smallest geometry-only prototype.

## Risks

The Wang paper solution-dependent flow-feature alignment is deferred outside production DSE. The production-safe S5 candidate must use geometry mapping only. The key technical risks are RBF ill-conditioning, topology drift, and projection error near tip and TE corners.

## Smallest Feasible Prototype

Use the S0 baseline block graph as the reference, transfer it to three LHS geometries, and require stable connectivity, bounded RBF condition diagnostics, and valid surface projection before any volume march.
