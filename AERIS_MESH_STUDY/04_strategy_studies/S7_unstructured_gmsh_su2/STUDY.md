# S7 study record

## Question

Can a deterministic Gmsh tri/prism/tet path produce auditable, wall-resolved
unstructured meshes and converged SU2 RANS-SA solutions over the same AERIS pyGeo
development space as S6, without geometry-specific repair?

## Preregistered hypothesis and falsifiers

The hypothesis is conditional: the frozen Gmsh candidates may pass every geometry,
mesh, solver, y+, and recovery gate without case tuning. It is falsified for
campaign readiness by any missing required readiness result. A common TE/tip
topology or quality failure across all candidates triggers a stop and superseding
mesher ADR; it never triggers a weaker threshold.

The following do not support the hypothesis by themselves: a mesh file being
written, SU2 exiting zero, a residual decreasing without stable forces, a nominal
first height without measured y+, a laptop diagnostic, a synthetic fixture, or a
literature benchmark.

## Fixed experiment

1. Use only `lhs100_seed42` during development and preserve every immutable attempt.
2. Use the canonical pyGeo design and one declared 0.5/1.0/1.5 mm numerical-TE
   member. Require exact design/index identity and full-wing reference quantities.
3. Build the fixed wall triangulation, prism schedule, and tet core. The first
   candidate passing every independent Gmsh/native-SU2 audit gate wins.
4. Run the frozen cruise condition in SU2 8.5 RANS-SA only after mesh acceptance.
   Permit one hash-linked restart; require process, residual, force-tail, restart,
   provenance, and exact wall-y+ gates.
5. Mesh all 100 development designs with no manual repair. Complete 10–20 unattended
   CFD pilots.
6. For fixed indices 0, 24, 49, 74, and 99, complete coupled coarse/medium/fine
   families and medium-grid 0.5/1.0/1.5 mm TE studies. Report non-asymptotic results
   as failures, not convergence.
7. Demonstrate production-resolution memory/runtime and restart recovery on suitable
   desktop/HPC hardware.
8. Resolve an independent Claude Code `--model opus --effort max` audit against the
   exact source/policy digest.
9. Freeze settings, schemas, retries, and gates. Only then authorize one untouched
   hold-out run of approximately ten cases, with no tuning afterward.

## Acceptance semantics

Per-case `accepted` is scoped technical evidence (`mesh_only` or `mesh_and_cfd`). A
technically passing case is not a campaign-readiness claim. Campaign readiness
requires every target in `POLICY.yaml`, a compatible S6/S7 report, and resolved
independent review. Missing or stale terminal/hash evidence rejects qualification.

## Recorded evidence at this revision

- 24/24 focused tests pass; Ruff passes.
- Synthetic Gmsh tri/prism/tet creation, wall mapping, native SU2 conversion, and
  topology checks execute successfully.
- Synthetic post-extrusion relocation corrupts the layer schedule; optimization is
  disabled without changing any quality threshold.
- A fake solver demonstrates one digest-linked restart and idempotent resume. It is
  not SU2 evidence.
- A manufactured unequal-grid sequence recovers observed order 2 and exercises the
  policy GCI rejection.
- No real BWB pyGeo/Gmsh run launched. The attempted local smoke was blocked by the
  execution environment before launch.
- `SU2_CFD` is absent. No real CFD, y+, force, grid, TE, robustness, or hold-out
  result exists.

The policy therefore remains preregistered development with no accepted campaign
result. The locked hold-out remains untouched and forbidden.
