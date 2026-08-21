# S7 roadmap and readiness gates

## Completed implementation gates

- [x] Strategy ADR and executable policy created before real BWB results.
- [x] Independent pyGeo full-wing surface path with declared TE variants, closure,
  orientation, self-intersection, exact-node, and facet-centroid fidelity checks.
- [x] Gmsh fixed-wall/prism/tet pipeline and native SU2 writer.
- [x] Independent Gmsh plus native-SU2 labels/topology/quality audit.
- [x] Fixed SU2 RANS-SA configuration, residual/force/y+ parsers, one-restart logic,
  immutable attempts, and process-tree timeout handling.
- [x] Development batch, resume, terminal manifests, source/policy/config/input/log/
  mesh/result hashing, laptop refusal, desktop launcher, and Slurm array launcher.
- [x] Coupled grid/TE qualification collector using actual counts and unequal-grid
  Richardson/GCI, plus evidence-compatible S6/S7 comparison output.
- [x] Focused unit/synthetic tests and static checks: 24 tests and Ruff pass.

These are software facts, not campaign results.

## Lead session findings, 2026-08-21

Real geometry and real volume meshes now exist for `lhs100_seed42` index 0.  Four
source-surface/instrument defects and two mis-specified gates were corrected, and
one causal claim was measured, then withdrawn.

- [x] Tip cap: centre fan -> chordwise ladder -> planar Delaunay.  Self-intersections
  24 -> 0; tip prism minSJ -4.471 -> +0.554; inverted cells 2 -> 0.
- [x] Node vs facet fidelity separated; per-level facet limits calibrated.
- [x] Self-intersection instrument distinguishes contact from interpenetration.
- [x] Wake box size field graded with a transition thickness.
- [x] Surface node distribution driven by the declared edge targets instead of
  whatever a cosine produces at the chosen count.
- [x] Mesh audit reports violating counts, not only extremes.
- [x] WITHDRAWN: the "BL stack must fit inside the TE opening" law.  It was a
  confound for the tip-cap slivers; the same geometry now meshes at 15.3x the
  opening and the preregistered stacks are not condemned.

Remaining, and the reason this is not finished:

- [ ] Six gates still fail, all maxima whose p99 passes, driven by 17 bad tets of
  921 739 at the blunt trailing edge.  Recorded in ADR-0017 as an open question
  with two candidate resolutions; **no gate was relaxed**.
- [ ] `wall_normal_first_cell_height` fails at ~0.5 against a 0.05 limit.  It is a
  maximum over all columns, and normal extrusion at a sharp convex edge projects
  onto a face normal by roughly cos(half-angle), so the metric may be measuring
  geometry rather than a defect.  Not yet investigated.
- [ ] Nothing above is production resolution.  `coarse` needs far more than the
  9 GiB available on this laptop.

## Open numerical and operational gates

- [ ] Run one real `lhs100_seed42` laptop diagnostic after the local execution
  blocker is removed. Interpret it only as bounded plumbing evidence.
- [ ] Confirm the exact SU2 8.5 configuration/output/restart path on a machine with
  the pinned executable.
- [ ] Mesh 100/100 development designs at the declared development resolution; no
  manual repair and no hold-out access.
- [ ] Pass every source, surface, boundary, volume, prism, quality, and TE/tip gate.
- [ ] Complete 10–20 unattended development SU2 pilots with residual, force-tail,
  restart, provenance, and production wall-y+ acceptance.
- [ ] Complete and pass the five fixed coupled coarse/medium/fine grid studies.
- [ ] Complete the five fixed 0.5/1.0/1.5 mm TE sensitivity groups and report force
  deltas without changing the baseline from their outcome.
- [ ] Demonstrate production-resolution RAM, disk, runtime, restart, worker, and
  storage recovery on suitable desktop/HPC hardware.
- [ ] Obtain a completed Opus/max independent audit with no unresolved acceptance
  blocker against the final source/policy digest.
- [ ] Freeze the entire implementation and governance schema.
- [ ] Through a new explicit unlock decision, run approximately ten hold-out cases
  once without tuning.

## Decision points

If all frozen Gmsh candidates share a TE/tip topology or quality failure, quarantine
S7 and write a superseding ADR for one alternative. Do not alter geometry treatment,
sizes, layers, retry order, optimizer, metric definitions, thresholds, solver, or
report schema in response to results.

If S7 reaches comparable evidence, compare S6/S7 on the same design/flow list and
full-wing normalization for robustness, actual cells, wall-clock/process-tree RSS,
wall-y+, and CL/CD/CMy. Missing/incompatible evidence remains explicit. No `auto`
selection rule exists until that comparison is complete and separately governed.

## Current blockers

The current 15 GiB-class laptop is below the 48 GiB production floor, `SU2_CFD` is
absent, and the real pyGeo smoke launch was blocked by the execution sandbox/usage
approval. No production or hold-out work should be attempted here.
