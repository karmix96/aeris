# Research basis and decision

## Decision

Use a structured, geometry-family-specific mesh atlas with exact-wall deformation
and full post-write rejection. Use pyGeo for geometry, S1 plus pyHyp for seed
volumes, and ADflow for RANS/SA.

This is tailored to this project. The geometries vary strongly, but all come from
one four-station BWB generator. Reusing a validated block graph is therefore more
valuable than asking a general unstructured mesher to rediscover topology 10,000
times.

## Why this route

- Structured multiblock RANS gives predictable near-wall resolution and low cell
  count for repeated aerodynamic solves.
- The local S1 study already proves that its topology marches on all ten
  development geometries.
- The old direct exact-surface march diagnostic failed before the surface-interface
  basis correction, so it is not evidence against a corrected direct march. The atlas
  remains preferable because it reuses audited volumes and bounds production risk.
- Smooth volume deformation is established practice in aerodynamic optimization.
  Secco et al. report a robust structured mesh generation and deformation
  workflow built around pyHyp and IDWarp.
- A mesh atlas limits deformation magnitude without making parameter distance a
  substitute for geometric quality.
- Independent post-write gates prevent silent bad meshes from entering CFD.

## Open-source stack

- Geometry: [pyGeo](https://github.com/mdolab/pygeo)
- Seed volume mesher: [pyHyp](https://mdolab-pyhyp.readthedocs-hosted.com/en/latest/)
- CFD: [ADflow](https://mdolab-adflow.readthedocs-hosted.com/en/latest/introduction.html)
- Inspection: ParaView
- Optional future deformation backend:
  [IDWarp](https://mdolab-idwarp.readthedocs-hosted.com/en/latest/tutorial.html)

The implemented bounded column deformation is deterministic and preserves the
wall-normal columns of the proven seed. IDWarp should be benchmarked against it,
not adopted without the same 100-case and holdout gates.

## Evidence from similar work

MDO Lab's published workflow uses pyGeo, pyHyp, IDWarp, and ADflow for aerodynamic
shape optimization. The mesh method is described in
[Secco et al. 2021](https://mdolab.engin.umich.edu/bibliography/Secco2021a).
A pyGeo/IDWarp/ADflow RANS application is also documented in
[Wu et al. 2022](https://public.websites.umich.edu/~mdolaboratory/pdf/Wu2022b.pdf).
An automated, knowledge-based geometry and meshing workflow for large design
variation is described by
[DLR](https://link.springer.com/article/10.1007/s13272-017-0264-1).

ADflow supports structured multiblock RANS. Its solver guide recommends ANK for
robust startup and NK for final convergence:
[ADflow solver strategy](https://mdolab-adflow.readthedocs-hosted.com/en/latest/solvers.html).

The planned independent route is Gmsh prism/tet meshing with SU2 RANS-SA. It is a
valid backup for broader geometry changes, but AERIS's current Gmsh volume path lacks
the validated wall-normal prism stack required for wall-resolved RANS. It will be
implemented and judged with the same geometry, y+, convergence, and force gates after
S6 is validated.

## What is new here

The atlas is not copied from one paper. It combines established mesh deformation
with this project's locked design-space geometry and measured failure modes:

- direct pyGeo evaluation closes S1's spanwise fidelity gap;
- each seed retains the dimensions that already marched successfully;
- maximin sampling spreads 16 initial seeds through the normalized 16-variable
  neutral-OML design space; fixed and neutral elevon-placement variables are omitted;
- every frozen compatible seed is available, nearest first, and distance only orders
  attempts;
- weak-quality, slow, and failed development routes deterministically enrich the
  atlas before it is frozen;
- the fallback uses the proven S1 march, then corrects to the exact S6 wall;
- every output mesh is rescored from its coordinates.

## Limits

The mesh pilots and one coarse CFD solve are development evidence, not proof over
10,000 cases. Production y+, the final enriched 100-case development run, frozen
holdout, 100-case CFD pilot, grid convergence, 10,000-mesh preflight, and HPC
rehearsal remain mandatory. See `ROADMAP.md` for the release gates and later AI work.
