# Stage 00 Paper Inventory

Created local: 2026-08-11

This inventory records how each provided paper feeds the AERIS mesh study. It is
not a literature review; it is an implementation map for the staged runbook.

## Files

| File | Bytes | SHA-256 | Stage use |
| --- | ---: | --- | --- |
| `2210.09546v1.pdf` | 10,601,058 | `e694a6bca035186f8509fc4667640edd2d71a679217f3c3e3c5c28a00b7cd152` | Stage 11 AI-readiness context |
| `Automatic Multiblock Mesh Generation for 3D-Wing Aerodynamic Analysis.pdf` | 21,423,841 | `05174dccbe73a07973ffdbeba1285b3a48504d233bf5f0b9cde5b0c8c831d0af` | S2/S3 tip/cross-field/sweep strategy source |
| `Numerical Meth Engineering - 2026 - Wang - Flow Feature Aligned Structured Mesh Generation via Sweeping Cross-Field.pdf` | 24,092,344 | `a3162600fbdb4c147b5aea9b15a8845aa87966cf4c20e3d6800b04a77436d23b` | S5 frozen-RBF and station-sweep context |
| `Openblademesh_Bachelor_Thesis_Michael_Heider_Abgabe_noBK.pdf` | 100,001,585 | `b9d4343aea19138866e1139609b37e358e8cc569a65309fd38b35a9d2af9c3f7` | S1 tip-first sweep source |
| `applsci-16-07588.pdf` | 59,808,320 | `a8811ac5765eda624c84cc18ea976e423ce134f9e7cc89cd2abb6837f6580336` | S4 analytical multiblock source |

## Implementation Takeaways

Openblademesh is the main source for S1. The useful pattern is to build the
wingtip topology first, with explicit curve/node-count progression control, and
then sweep inward through ordered span stations. Its limitations are directly
relevant to AERIS: pyHyp can fail when adjacent surface-cell sizes change too
aggressively, and spanwise growth laws need explicit control rather than an
implicit one-size progression.

The automatic 3D-wing multiblock paper is the main source for S2 and part of
S3. Its tip method combines a support triangle mesh, constrained cross-field
parameterization, quad extraction, smoothing, projection to the original
surface, and block extraction from singularities. Its volume result is the
important caution: good surface quality did not guarantee a strong hex scaled
Jacobian. AERIS must therefore rank strategies after pyHyp/volume marching, not
after surface-only checks.

The Applied Sciences paper is the main source for S4. It gives the clearest
recipe for direct analytical blocks from control vertices, control edges,
surface domains, and volume transfinite interpolation. AERIS should adopt the
entity logic, but not blindly copy absolute farfield distances, first-layer
thickness, or wing-scale constants. The boundary-layer height must come from
mission/y+ requirements.

The Wang 2026 paper is useful for S5 and also informs S3. The production-safe
piece is not solution-dependent flow-feature alignment; it is the geometry
mapping workflow: create a reliable block layout on a representative section,
map displacements with RBF to related sections, project to curved surfaces, and
connect corresponding corners. Topology drift and singularity changes must be
recorded and gated.

The PINN mesh paper (`2210.09546v1.pdf`) belongs in the later AI-readiness
stage. It is useful for thinking about learned mesh proposals and diagnostics,
but it must not bypass exact geometry projection, boundary-label generation, or
deterministic quality gates.
