# S1 Implementation Note - Tip-First Sweep

S1 translates the Openblademesh pattern into AERIS terms: close and quality the physical tip first, then sweep inward through the known span stations.

## Algorithm

Build a deterministic multiblock cap on the `b3` physical tip, assign transfinite curve distributions with bounded geometric progression, then sweep the matched block graph inward through `b2`, `b1`, and `b0`.

## Inputs

- Tip station: `b3`
- Inward station order: `b3 -> b2 -> b1 -> b0`
- Semantic edges: leading edge, trailing edge, root symmetry, tip, planform breaks, and elevon span boundaries
- Mesh laws: curve progression, spanwise node counts, and regional cap/wake constraints
- Source paper: Openblademesh sections 1.1.2, 1.1.4, 3.1.4-3.1.7, 3.3, and 4.2

## Outputs

- tip block graph and node-count manifest
- spanwise sweep-interval manifest
- surface PLOT3D/CGNS/VTK/NPZ outputs
- surface QC with tip, root, TE-crown, and planform-break regions
- pyHyp volume report and failure localization

## Missing Details

The exact AERIS tip subdivision must be designed. Openblademesh provides the pattern but not a direct BWB block graph. Spanwise growth-law limits must be derived from Stage 01 or Stage 02 smoke meshes.

## Dependencies

Available: `numpy`, `scipy`, AERIS surface builders, `gmsh`, `pyhyp`, `cgnsutilities`, and `h5py`. No separate Openblademesh package is available; the prototype must be implemented in AERIS.

## Risks

The source warns that pyHyp can fail when adjacent cell sizes change abruptly. S1 therefore needs a spanwise growth-law gate before volume marching. It must also avoid smoothing or thickening the prescribed trailing edge.

## Smallest Feasible Prototype

Prototype only the `b3 -> b2` interval on the baseline geometry, with a fixed tip block graph and three candidate spanwise progression laws. Accept the prototype only if it writes conformal surface blocks and a valid pyHyp volume.
