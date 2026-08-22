# Geometry Fidelity Gate Resolution

Created local: 2026-08-11

## Problem

The original Stage 00 gate used a simple `0.01% local chord` limit. That is
clear at root-chord scale, but it becomes very small at the minimum tip chord.

Computed from `configs/geometry/bwb.yaml`:

| Chord case | Chord m | 0.01% chord mm |
| --- | ---: | ---: |
| minimum root chord | 0.700 | 0.0700 |
| nominal root chord | 0.900 | 0.0900 |
| maximum root chord | 1.100 | 0.1100 |
| minimum tip chord | 0.056 | 0.0056 |
| nominal tip chord | 0.126 | 0.0126 |
| maximum tip chord | 0.220 | 0.0220 |

The minimum tip value is 5.6 microns. That is tighter than the current CST
section-refit RMS allowance of `0.001 chord` and much tighter than the physical
CAD tessellation tolerance of `0.00075 m`.

## Resolution

The hard Stage 00 rule is now source-aware:

- No strategy may intentionally alter the prescribed OML to make meshing easier.
- For direct neutral pyGeo/analytical OML evaluation, report projection residual
  against the source surface and target `<= 0.01% local chord`.
- For CST-refit, tessellated CAD, or physical-control CAD paths, the hard
  comparison cannot be tighter than the source representation tolerance. In
  those paths, report both the source tolerance and the mesh projection error,
  and require an ADR before using the path in Round A scoring.
- The minimum tip value of 0.0056 mm is kept as a reporting target, not as a
  blind hard failure against a looser source representation.

This preserves the scientific rule that the mesher cannot change the OML while
removing false precision from the gate.

## Addendum 2026-08-13 — the two questions are not the same measurement

Stage 02 reports **0.000000% of local chord** for every strategy. That number
answers only the first of two distinct questions, and the report must say which:

1. **Mesh vs generated OML.** Do the mesh nodes lie on the OML the generator
   produced? This is what Stage 02 measured, and 0.000000% is the honest answer:
   node-to-polyline-segment distance against the closed section contour mapped
   through the same trusted path used to build the blocks.
2. **Generated OML vs source geometry.** How accurately does the generated OML
   represent the underlying source/CST definition? Stage 02 **did not measure
   this**, and the section polyline is itself an approximation — 61 points per
   section, with a CST section-refit RMS allowance of `0.001 chord` (0.1%), ten
   times the 0.01% mesh gate.

A mesh matching an already-approximated OML to machine precision says nothing
about (2). The Stage 02 result must therefore be reported as *"mesh reproduces
the generated OML exactly"*, never as *"geometry fidelity 0.000000%"*
unqualified.

Measuring (2) requires comparing the generated section against the pyGeo/CST
source at higher sampling density, and belongs to Stage 03 alongside the
spanwise-redistribution work. Until then the total geometry error is bounded
below by the OML's own representation tolerance, not by the mesh gate.
