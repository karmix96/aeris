# S4 Implementation Note - Analytical Multiblock

S4 follows the analytical multiblock workflow from the Applied Sciences paper: construct control vertices, control edges, surface domains, and volume blocks directly from geometry semantics.

## Algorithm

Derive Type 1-4 control vertices from the BWB station and edge semantics, generate control edges, interpolate surface domains, and build volume blocks using TFI-like interpolation.

## Inputs

- Geometry entities from `geometry_topology_contract.json`
- Design-variable bounds from `design_space_snapshot.yaml`
- Mission/y+ inputs from `operating_points.yaml`
- Gate definitions from `gate_registry.yaml`
- Source paper: Applied Sciences 2026 paper, sections 2-4

## Outputs

- control-vertex table
- control-edge table
- surface-domain manifest
- volume-block manifest
- boundary-label/connectivity signature
- volume quality report before solver export

## Missing Details

AERIS-specific Type 2 and Type 3 coefficients are not calibrated. Boundary-layer height must be derived from the actual wall treatment and Reynolds condition, not copied from the paper. Farfield extent must wait for the farfield independence study.

## Dependencies

Available: `numpy`, `scipy`, `h5py`, AERIS geometry code, and CGNS/PLOT3D writers through the current mesh stack. No external direct-volume library is installed; the smallest prototype must use in-house TFI/Poisson-style code or an approved dependency.

## Risks

The source paper coefficients and farfield distances are not AERIS constants. Bad Type 2 or Type 3 placement can create self-intersections or nearfield block collapse even when the surface projection is valid.

## Smallest Feasible Prototype

Build the baseline neutral BWB with only Type 1 surface vertices and a simple nearfield frame, write the block manifest, and run geometry-fidelity and surface-validity checks before attempting boundary-layer or volume refinement.
