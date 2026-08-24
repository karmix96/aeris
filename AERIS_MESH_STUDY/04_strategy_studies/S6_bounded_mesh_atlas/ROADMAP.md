# AERIS automated CFD roadmap

This file is the persistent work order for the automated CFD campaign. Passing a
mesh unit test does not make a pipeline campaign-ready.

## Current order

1. Finish and validate `s6_atlas + ADflow`.
2. Add `Gmsh prism/tet + SU2` as an independent unstructured pipeline.
3. Add `auto` (S6, then Gmsh fallback) and `compare` modes with one acceptance schema.
4. Use the recorded S6 experience for AI-assisted meshing research.

## Current evidence

- The 16-seed maximin smoke atlas passed all 100 development geometries.
- It required 131 attempts, passed 80 cases first try, never exceeded five attempts,
  and had worst accepted scaled quality +0.15184.
- Smoke enrichment added no seeds, but cannot unlock the holdout.
- A fixed provisional production policy (`N=257`, `epsE=1.5`, first-cell fraction
  `3.6e-6`) passed 16/16 maximin seeds. Independent quality spans `0.10535` to
  `0.23471`; zero cells are below `0.10` and three are below `0.15`.
- A campaign-equivalent written-CGNS canary passed 2/2. The full 100-target
  production audit is running and checkpointed.
- The wall law is not frozen until production CFD proves y+.
- The locked holdout remains untouched.

## S6 release gate for 10,000 CFD cases

S6 can be frozen for the 10,000-case campaign only after all of these pass:

- production-resolution CFD passes the frozen wall-y+ limits;
- the locked unseen hold-out passes without tuning;
- at least 99 of 100 CFD pilot cases finish automatically with accepted meshes and CFD;
- about 20 representative cases show stable lift and drag under grid refinement;
- all 10,000 planned geometries pass mesh preflight or an automatic fallback;
- a 500-1,000-case HPC rehearsal proves restart, failure recovery, storage, and collection.

The immediate blocker is production-resolution y+ validation.

## Reduced gate for a 100 CFD campaign

- preflight all 100 meshes and accept 100/100;
- run 10-20 CFD pilots, including geometric extremes;
- pass production-resolution y+;
- perform grid convergence on five representative cases;
- keep about ten geometries as an untouched hold-out;
- prove unattended restart and failure recovery.

## Unstructured pipeline

The Gmsh + SU2 route is not equivalent to S6 until it has wall-normal prism layers.
Benchmark it on the same ten extreme geometries. Require 10/10 automatic meshes,
zero invalid cells, accepted y+, converged RANS-SA solutions, and stable lift and drag
under refinement.

## AI research record

Save these fields for every attempted mesh and CFD case:

- geometry design variables and normalized coordinates;
- ranked templates, selected template, and rejected alternatives;
- deformation field and deformation cost;
- cell-level and summary mesh quality;
- failed attempts and exact gate reasons;
- mesh generation time and resource use;
- wall y+, residual history, force history, convergence state, and final forces.

The first paper targets AI-assisted meshing: AI ranks templates and predicts failure or
quality, while deterministic deformation and hard gates retain authority. A working
title is "Quality-Constrained AI-Assisted Mesh Atlas Deformation for Automated CFD
Design Campaigns."

## Joint validation programme

The shared S6/S7 sequence this study feeds - staging, the paired comparison and
the decisions that must be taken before any CFD is recorded - is in
`../VALIDATION_PROGRAMME.md`.
