# S7 research basis

## What the literature supports

Gmsh is a general finite-element mesh generator with documented 3-D algorithms,
size fields, boundary-layer extrusion, and HXT tetrahedral meshing. The Gmsh
paper and manual document capabilities, not success on this BWB or suitability
for wall-resolved RANS. HXT is relevant to the preregistered second retry, but a
paper benchmark is not local evidence.

SU2 documents compressible RANS and the Spalart–Allmaras model and provides
verification tutorials. Those sources justify the solver/model choice; they do
not verify this geometry, numerical TE, wall law, or convergence thresholds.

Quality metrics are deliberately plural. Knupp's algebraic framework explains why
Jacobian/condition metrics are useful but not interchangeable in 3-D. Verdict's
scaled-Jacobian terminology provides an independent quality vocabulary. S7
therefore gates signed tet `minSICN`, prism `minSJ`, layer geometry, skewness,
non-orthogonality, and regional TE/tip statistics separately. Passing one scalar
is never sufficient.

NASA TMR material supports a disciplined verification sequence: y+ is part of the
near-wall model evidence, and coupled/nested grids plus observed order and GCI are
needed to discuss discretization error. S7 adopts that principle without claiming
that a TMR case is evidence for AERIS.

## Why retain Gmsh provisionally

The route is portable and open-source, has a Python API, supports a declared
prism-plus-tet topology, and includes a documented HXT option. It is therefore a
reasonable experiment and a possible independent fallback to S6. The same reasons
do not make it qualified: Gmsh's 3-D extrusion is a simple topological operation
with known re-entrant-corner limitations, while this geometry has a thin numerical
trailing edge and a tip. Only the frozen development program can answer that
qualification question.

## Alternatives and trigger

OpenFOAM's official `snappyHexMesh` documentation describes castellated/snapped
meshes and prismatic layers with quality controls; it is a credible alternative,
but would change the core topology, input/control language, dependencies, and
SU2 conversion path. Netgen, TetGen, and cfMesh are other candidate families;
none is silently substituted. If all preregistered Gmsh candidates fail the same
class of development gate, stop, preserve the attempts, and issue a superseding
ADR that selects and preregisters one alternative. If Gmsh passes, it remains
frozen until an explicitly governed change is approved.

## Evidence boundary

At document creation there is no S7 campaign evidence to summarize. Code presence,
policy values, literature, and test fixtures are not mesh or CFD results. Results
must be reported with evidence tier (`unit`, `laptop_smoke`, `development`,
`holdout`, `production`), immutable attempt paths, tool versions, and hashes.

