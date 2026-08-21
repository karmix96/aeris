# S3 Implementation Note - Station-Sweep Blocks

S3 treats the BWB as a sequence of known cross-sections and builds blocks by connecting corresponding section landmarks.

## Algorithm

Define one canonical split of every station section, match node counts across sections, connect corresponding curves spanwise, and insert extra sweep planes at planform breaks and control-region boundaries where labels require them.

## Inputs

- Frozen station order: `b0 -> b1 -> b2 -> b3`
- Airfoil assignments: mh91, mh91, e374, nlf1015
- Elevon span start and end fractions when the neutral mesh needs control-region labels
- Mesh-law registry and regional quality gates
- Source papers: Openblademesh, automatic multiblock 3D wing paper, and Wang 2026 section-sweep/RBF mapping discussion

## Outputs

- per-section curve-split manifest
- spanwise interface/connectivity manifest
- boundary label map
- surface PLOT3D/CGNS/VTK/NPZ outputs
- pyHyp volume report and regional failure localization

## Missing Details

The canonical AERIS section split has not been chosen. Stage 02 must test at least one split that resolves the blunt trailing-edge crown and keeps matching node counts through all station intervals.

## Dependencies

Available: `numpy`, `scipy`, AERIS mesh code, `pygeo`, `pyspline`, `gmsh`, `pyhyp`, `cgnsutilities`, and `h5py`. No extra cross-field package is required for the smallest prototype.

## Risks

A single section split may not remain high quality across large chord, twist, sweep, and dihedral changes. S3 must detect high skew, folding, bad spanwise growth, and planform-break discontinuities before pyHyp volume marching.

## Smallest Feasible Prototype

Build the baseline geometry using only the four semantic stations, one fixed section split, and no elevon-induced extra planes. Then add the elevon boundary planes and compare connectivity and regional QC.
