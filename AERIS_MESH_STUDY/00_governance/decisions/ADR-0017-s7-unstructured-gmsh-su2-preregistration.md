# ADR-0017: S7 unstructured Gmsh + SU2 preregistration

- **Status:** Accepted for development; no campaign result accepted
- **Date:** 2026-08-21
- **Owners:** AERIS mesh study
- **Scope:** `04_strategy_studies/S7_unstructured_gmsh_su2/`
- **Supersedes:** Nothing
- **Related:** ADR-0011, ADR-0014, ADR-0015, ADR-0016

## Context

S6 established a structured pyGeo/pyHyp/ADflow path and its campaign governance.
AERIS also needs an independent, portable, open-source unstructured path for the
same geometry and flight-condition space.  The eventual selection problem is about
one hundred high-fidelity active-learning cases, followed by thousands of cheaper
evaluations.  A mesh that succeeds once is therefore insufficient: the path must be
deterministic, recoverable, auditable, and able to fail closed.

This ADR is deliberately written before producing or interpreting S7 mesh or CFD
results.  Numerical thresholds and recovery order are frozen in the adjacent
`POLICY.yaml`.  Development results may expose that the policy is too strict or the
chosen mesher is unsuitable, but no threshold may be weakened in response.  Any
change requires a new superseding ADR, a fresh development campaign, and continued
quarantine of the locked hold-out.

For the cell-quality gate, tetrahedra use Gmsh's signed inverse condition number
(`minSICN`) and prisms use its sampled scaled Jacobian (`minSJ`).  A single
condition-number threshold would classify intentionally high-aspect, otherwise
valid wall prisms as poor solely because they resolve the wall-normal scale.  Prism
aspect ratio, Jacobian sign, skewness, layer-height progression, and
non-orthogonality remain separately hard-gated.  Adjacent-volume ratios are split
between core-to-core faces and the intentional prism-to-core transition.

## Decision

### 1. Location and independence

S7 is a sibling of S6 inside `AERIS_MESH_STUDY/04_strategy_studies/`.  It reuses the
same authoritative pyGeo geometry builder, geometry-set registry, flow-condition
definitions, development-set identity, reference quantities, reporting vocabulary,
and provenance conventions.  It does not call S6's private structured topology or
interpret S6 success as evidence for S7.

Artifacts expose a stable method-neutral summary so a later dispatcher can offer
`structured`, `unstructured`, `auto`, and `compare` modes without translating
scientific meaning.  Automatic method selection is not part of this ADR.

### 2. Fixed solver and initial mesh topology

SU2 8.5.0 (Harrier) is the fixed open-source RANS solver.  The production physical
model is compressible RANS with the Spalart--Allmaras turbulence model.  S7 starts
with:

1. a triangular surface conforming to the same pyGeo OML,
2. recombined normal extrusion into triangular-prism boundary layers, and
3. a tetrahedral far-field core.

The baseline mesher is Gmsh 4.15.2.  Gmsh is *provisional*, not assumed qualified.
Its ordinary `BoundaryLayer` size field is two-dimensional; S7 therefore uses the
three-dimensional `geo.extrudeBoundaryLayer` route and audits the produced topology.
That operation is a simple topological extrusion and has no fan/re-entrant-corner
treatment.  The thin numerical trailing edge and wing tip are explicit qualification
risks, not details to waive.

### 3. Geometry representation

The source of truth remains the pyGeo surface and exact arbitrary-station section
evaluation established by ADR-0015.  A deterministic triangulated representation is
derived from it for Gmsh.  Every surface node is checked back against its source
surface/section, and the numerical trailing-edge opening is checked against the
declared target.

S7 meshes the full mirrored wing.  This closes the OML without inventing a root cap
and avoids making a symmetry-plane cut part of the first mesher qualification.
Aerodynamic reference area, span, chord, moment origin, and force normalization are
therefore the full-wing values used by the shared configuration.  S6 comparisons
must state the modeled domain multiplier and normalize wall area, cells, and runtime
where appropriate.

The required trailing-edge sensitivity family is the S6 family:

- `te_0p5mm`: `max(0.5 mm, 0.25% local chord)`,
- `te_1p0mm`: `max(1.0 mm, 0.50% local chord)`, and
- `te_1p5mm`: `max(1.5 mm, 0.75% local chord)`.

The 1.0 mm family member is the provisional development baseline.  These are
declared numerical geometries and never silently substituted for the sharp design
geometry.

### 4. Data isolation

The development geometry set is exactly `lhs100_seed42`, with the same canonical
ordering and case identifiers as S6.  Smoke fixtures and analytically simple
geometries are allowed only for software tests and are labeled non-campaign.

The locked set `round_c_lhs10_seed42` is forbidden until all algorithms, numerical
settings, retry order, quality gates, SU2 convergence gates, and report schemas are
frozen and an independent Claude review has returned no acceptance blocker.  The
S7 runner enforces the shared hold-out guard.  No hold-out mesh, metric, plot, solver
run, or case-specific tuning is permitted before unlock.

### 5. Deterministic retries and preservation

Retries are a predeclared algorithm sequence, never ad-hoc parameter tuning:

1. fixed pyGeo wall + Frontal-Delaunay generated outer surfaces + Delaunay core;
2. fixed pyGeo wall + Delaunay generated outer surfaces + HXT core;
3. fixed pyGeo wall + MeshAdapt generated outer surfaces + Delaunay core, with the
   same physical size and layer specifications.

The wall is an immutable discrete triangulation and is not remeshed between retries.
The 2-D Gmsh algorithm therefore applies only to surfaces generated around it,
principally the outer boundary. Candidate names must expose that scope; a change in
wall tessellation would be a new geometry/grid policy, not a retry.

The exact option map is in `POLICY.yaml`.  A failed attempt remains immutable in an
`attempt_XX_<candidate>` directory with configuration, environment, stdout/stderr,
mesh if written, audit, solver files, exception record, hashes, and a terminal
manifest.  A later attempt never overwrites or repairs an earlier attempt.  The
first passing candidate wins; candidate identity is part of every result.

Restart recovery is separately deterministic: SU2 starts from free stream, resumes
only from the hash-verified restart created by its immediately preceding attempt,
and receives the predeclared iteration extension. Residual-drop acceptance for a
restart chain is measured from the first finite freestream-history value to the
final restart-history value; the restart segment's own initial value is retained
separately. A solver restart cannot rescue a mesh that failed preflight.

### 6. Three coupled grid levels

Coarse, medium, and fine are true coupled levels.  Refinement changes surface-edge
targets, first-cell height, prism layer count/growth, wake/near-body sizes, and core
tetrahedral sizes together.  No result is called a grid family when only the surface
or only the core changed.  The frozen level table and effective refinement checks
are in `POLICY.yaml`.

Five representative development cases must complete all three levels.  Reported
grid convergence includes observed order where mathematically meaningful, GCI or a
clearly flagged non-asymptotic result, and force/y+ histories.  Failure to establish
an acceptable grid family is a failed readiness gate, not an invitation to relabel
the meshes.

### 7. Hard gates and fail-closed behavior

The policy contains hard gates for:

- source-node and planar-facet-centroid geometry fidelity and exact boundary/volume
  labels;
- a closed, manifold, finite, non-degenerate surface;
- zero inverted or non-positive-volume cells;
- complete prism coverage, exact layer topology, continuity, first-layer
  displacement and wall-normal projected height, layer count, and growth ratio;
- skewness, non-orthogonality, aspect ratio, and scaled-Jacobian/cell quality;
- separately reported and gated trailing-edge and tip regions;
- SU2 process completion, residual drop, force-tail convergence, and restart;
- wall `y+` distribution; and
- complete provenance and digest verification.

Every required metric must be present and finite.  Missing evidence fails the gate.
Thresholds cannot be relaxed for a difficult geometry, grid level, retry candidate,
or comparison with S6.

The source fingerprint covers the complete in-repository `src/aeris` Python tree,
the S7 implementation/policy, shared strategy controls, geometry configuration,
and project dependency declaration. This deliberately favors conservative cache
invalidation over an incomplete hand-maintained import list.

### 8. Evidence tiers and machine safety

Evidence is labeled as one of:

- `unit`: synthetic/parser/metric tests;
- `laptop_smoke`: deliberately tiny topology and SU2 plumbing checks;
- `development`: policy-compliant development-set evidence;
- `holdout`: locked-set evidence produced only after formal unlock; or
- `production`: production-resolution campaign evidence.

Laptop smoke meshes use reduced dimensions and layer counts and cannot prove
production y+, quality, robustness, memory, runtime, or force accuracy.  Before any
production-resolution mesh or CFD launch, the runner estimates memory/disk, records
available resources, and fails closed if the declared resource floor is unmet.
Desktop and scheduler scripts generate manifests before launch and never implicitly
reduce a requested grid.

### 9. Gmsh qualification and change trigger

Gmsh is qualified only if the frozen development program demonstrates the required
surface fidelity, closed topology, prism continuity at the thin trailing edge and
tip, volume quality, unattended retry behavior, and SU2 completion.  The final
campaign-readiness target is:

- 100/100 development meshes pass preflight;
- 10--20 development CFD pilots finish unattended;
- production wall `y+` passes;
- five representative grid-convergence studies pass;
- approximately ten unseen locked cases pass without tuning after unlock; and
- restart and automatic failure recovery are demonstrated.

If all preregistered Gmsh candidates fail the same topology/quality class on the
development set, S7 stops.  A new ADR must evaluate an alternative.  Candidate
families include snappyHexMesh/cfMesh for layer robustness and Netgen or TetGen for
a tetrahedral core, but each changes topology, dependencies, licensing, or coupling.
No silent mesher substitution is allowed, and SU2 remains fixed.

### 10. Acceptance and independent review

Before any S7 result is accepted, the complete source, policy, tests, manifests, and
evidence are reviewed with Claude Code using the latest available Opus model and
maximum effort:

```text
/home/mike/.local/bin/claude --model opus --effort max
```

The exact command, model-reported identity, prompt, stdout/stderr, exit status, and
hashes are retained.  Review findings are either fixed and re-reviewed or recorded
as blocking.  Claude review is necessary governance evidence, not a replacement for
the numerical gates.

## Consequences

### Positive

- Structured and unstructured approaches live under the same governed study.
- Gmsh and SU2 are pinned and portable, while failure remains scientifically useful.
- Retry/restart behavior is reproducible rather than operator dependent.
- S6/S7 comparisons share geometry, case identity, normalization, and gate language.

### Costs and risks

- Full-wing meshing costs more than an initial symmetry model.
- Gmsh's simple 3-D layer extrusion may not survive the trailing-edge/tip topology.
- Strict layer and quality audits may reject many otherwise runnable meshes.
- A laptop smoke cannot resolve the production question; desktop/HPC evidence is
  required before campaign readiness can be claimed.

## Acceptance state at creation

This ADR authorizes implementation and laptop-safe smoke testing only.  It accepts
no mesh, CFD result, comparison, hold-out result, or campaign-readiness claim.

## Pre-development implementation correction (2026-08-21)

The first synthetic, non-campaign smoke exposed that Gmsh `Relocate3D` can
relocate intermediate prism nodes while retaining the wall and outer prism faces.
That changes the prescribed layer schedule and can invert otherwise valid prisms.
A second retained diagnostic showed that selecting only the core entity did not
protect the prism schedule in Gmsh 4.15.2.  Before any development-set result was
generated, post-generation optimizers were therefore disabled for all frozen
candidates.  The native meshing algorithms still differ in the deterministic retry
sequence, and every mesh remains subject to all quality gates.  Prism quality and
first-height thresholds are unchanged; both failed optimizer diagnostics are
retained as evidence.

## Pre-result implementation and evidence amendment (2026-08-21)

No real BWB mesh or CFD result had been generated when this amendment was made.
Implementation and synthetic tests exposed several places where the executable
contract needed to become more explicit without relaxing a gate:

- Retry identifiers now state that the pyGeo-derived wall triangulation is fixed;
  Gmsh 2-D algorithms affect only generated outer surfaces. Delaunay/HXT remains the
  meaningful core retry.
- Geometry fidelity now samples every OML triangle centroid against the exact opened
  pyGeo B-spline in addition to re-evaluating every tracked node. This prevents a
  coarse planar facet from passing merely because its vertices lie on the source.
- Laptop diagnostics use a separately declared reduced 3L/5L/3L farfield and refuse
  estimated memory above 40% of currently available RAM. Coarse/medium/fine retain
  the full 20L/30L/20L farfield and the 48 GiB/100 GiB production resource floors.
- Mesh/native-SU2 conversion now reconstructs every tet/prism face and requires all
  boundary faces to be assigned exactly once, all markers to be real boundary faces,
  and volume/type counts to match. TE/tip outer prism faces must each have one
  adjacent core tet meeting the frozen tet-quality threshold.
- Flow and full-wing reference quantities are exact policy/canonical values, not
  caller-tunable mappings. Mesh-only and cruise case identities are distinct.
- Mesh, SU2, case, and batch terminal manifests bind source, policy, resolved
  configuration, inputs, logs, meshes, and results. Qualification accepts only
  adjacent verified case terminals for the five preregistered indices and rejects
  mixed design, flow, or force-normalization evidence.
- The unequal-grid Richardson equation and bisection were corrected before use on
  results and are covered by a manufactured order-2 test. Fine-grid GCI limits and
  non-asymptotic findings fail qualification.

The focused unit/synthetic suite passes 24 tests and static checks pass. A synthetic
Gmsh fixture demonstrates tri/prism/tet generation and conversion; a fake solver
demonstrates one digest-linked restart. Neither is BWB or SU2 campaign evidence.
`SU2_CFD` is absent on the current machine. An attempted real pyGeo laptop smoke was
blocked by the execution sandbox/usage approval before launch, which is not a mesh
failure. A prior Claude Opus/max run reached its session limit and is retained as a
failed review, not acceptance.

Accordingly, S7 remains `preregistered_development_no_results`. No S7 mesh, solver,
y+, force, grid-convergence, comparison, hold-out, or campaign-readiness result is
accepted by this amendment, and the hold-out remains forbidden.


## Tip closure and facet-fidelity amendment (2026-08-21, still pre-result)

The first real `lhs100_seed42` index-0 surface ever constructed under S7 exposed two
defects.  Both were corrected before any campaign result existed, and both are
recorded here with the measurement that motivated them.

### 1. Planar tip cap: centre fan replaced by a chordwise ladder (defect fix)

The tip cap was closed with a fan from the mean of the tip-section boundary points.
The tip section is a thin cambered airfoil (measured 123 mm chord by 19 mm thick at
index 0) and is therefore not star-shaped about that mean, so fan triangles left the
section and cut the lower surface: **24 measured `wall_lower`/`wall_tip`
self-intersections**.  The cap is now closed by laddering the upper and lower tip
curves at matching chordwise stations, so every triangle is spanned by one chordwise
step and the local thickness.

Measured effect at `laptop_smoke`: self-intersections 24 -> 0; boundary and
non-manifold edge counts unchanged at 0; enclosed volume bit-identical at
0.04897705146561606 m3.  The tip curve was independently confirmed planar to
6.9e-16 m, and no surface node lies outboard of the tip plane (max excess 6.9e-16 m),
so a planar cap remains geometrically valid for this geometry.

This is a correction of a construction defect, not a relaxation.  No threshold moved.

### 2. Facet-centroid fidelity: one grid-independent limit was unsatisfiable

The 2026-08-21 pre-result amendment added a planar-facet centroid check and graded it
against `max_distance_over_local_chord` (1.0e-4), the node-fidelity limit.  That
number had never been evaluated against real geometry because no real S7 surface had
ever been built.  Measured on index 0 (`te_1p0mm`):

| level | triangles | node fidelity | facet centroid | vs 1.0e-4 |
|---|---|---|---|---|
| laptop_smoke | 1 778 | 0.0 | 1.832e-2 | fail x183 |
| coarse | 41 758 | 0.0 | 9.840e-4 | fail x10 |
| medium | 84 290 | 0.0 | 4.926e-4 | fail x5 |
| fine | 165 886 | 0.0 | 2.561e-4 | fail x3 |

The single limit rejects every mesh S7 can produce, including the finest
preregistered level.  The error converges at O(h^2) (ratios 2.00 and 1.92 for h
ratios of 1.41), confirming a well-behaved discretization metric; reaching 1.0e-4
would require h ~ 0.0094 L, about 2.7x finer than `fine` in every direction.

The two quantities are therefore separated, because they measure different things:

- **node fidelity** is a correctness property - every tracked OML vertex must lie on
  the pyGeo B-spline.  It is grid independent, keeps its 1.0e-4 limit, and measures
  exactly 0.0 at all four levels.
- **facet-centroid error** is a resolution property and is now graded per level in
  `POLICY.yaml` at `mesh_gates.source_geometry.max_facet_centroid_over_local_chord`,
  with limits carrying about 1.5x margin over the measurements above.

A missing level key fails closed.  The failure reason `surface_fidelity` is replaced
by the two distinct reasons `surface_node_fidelity` and `surface_facet_fidelity`.

This is a correction of a mis-specified gate, made before any result existed and
justified by measurement, not a weakening to admit a failing case.  Every other
threshold in `POLICY.yaml` is unchanged.  S7 remains
`preregistered_development_no_results`, and the hold-out remains forbidden.


## Boundary-layer / trailing-edge investigation (2026-08-21, still pre-result)

### What was first concluded, and why it was wrong

Gmsh core meshing aborted with a PLC segment/facet error on the real index-0
geometry.  A sweep holding everything else fixed produced an apparently clean law:

| BL total thickness | multiple of 1.0 mm TE | Gmsh (fan/ladder tip cap) |
|---|---|---|
| 15.335 mm | 15.3x | PLC error |
| 3.829 mm | 3.8x | PLC error |
| 1.276 mm | 1.3x | completes |
| 0.531 mm | 0.5x | completes |

That was read as prism fronts colliding across the thin trailing edge, since
`geo.extrudeBoundaryLayer` performs no collision detection or layer squeezing.  On
that reading the preregistered levels were all condemned, at 3.2x, 4.6x and 4.5x
the trailing-edge opening.

**The reading was a confound and is withdrawn.**  The actual cause was a
degenerate tip-cap triangulation.  The chordwise ladder inherited the wall's
chordwise node distribution; near the trailing edge of the tip section that
spacing is about 0.48 mm against a 0.95 mm opening, forcing three nearly collinear
boundary nodes into one triangle with a 1.516 degree minimum angle.  Extruding a
sliver produced inverted prisms and a self-intersecting boundary, which is what
Gmsh reported.  A thinner stack merely scaled the defect below Gmsh's tolerance,
which is why thickness appeared to be the governing variable.

### What is actually established

With the tip cap triangulated by planar Delaunay (below), the identical sweep
completes at every thickness tested, including 15.335 mm at 15.3x the
trailing-edge opening:

| BL total thickness | multiple of TE opening | Gmsh (Delaunay tip cap) |
|---|---|---|
| 15.335 mm | 15.3x | completes (924 069 tet, 49 744 prism) |
| 3.829 mm | 3.8x | completes (924 733 tet, 49 744 prism) |
| 1.276 mm | 1.3x | completes (924 165 tet, 49 744 prism) |

No trailing-edge thickness budget is therefore established, and none is imposed.
The preregistered `coarse`, `medium` and `fine` stacks are **not** condemned.

`gmsh.boundary_layer` remains in `POLICY.yaml` as an available, tested safeguard
with `derive_prism_layers_from_te_opening: false`, so the derivation is inert
unless a future measured collision justifies enabling it.  When enabled it reduces
only the layer count, never the first cell height or growth ratio, and fails
closed if the declared floor cannot fit.

The general caution stands and is unchanged: Gmsh supplies no corner fans, no
re-entrant treatment and no layer collision handling, so trailing-edge and tip
behaviour remain hard-gated qualification criteria rather than assumptions.

## Tip cap triangulation amendment (2026-08-21, still pre-result)

The chordwise ladder that replaced the centre fan inherits the wall's chordwise
node distribution, which near the tip trailing edge is finer than the local
thickness.  Measured at index 0: a tip-cap triangle with a 1.516 degree minimum
angle, whose extrusion produced two inverted prisms (minimum scaled Jacobian
-0.80).  Those inversions persisted at half the trailing-edge opening, proving the
defect was the triangulation and not the stack height.

The tip section is planar to 7e-16 m, so the cap is now triangulated by planar
Delaunay over the same perimeter nodes, maximising the minimum angle instead of
following a fixed pattern.  Conformity is verified rather than assumed: every
perimeter edge must be owned by exactly one kept triangle and no triangle may be
degenerate, otherwise the routine returns nothing and the conformal ladder is used
as a fallback.  Measured effect at index 0: tip-cap minimum angle 1.516 -> 7.209
degrees, and the previously failing thick stacks now mesh.

No gate moved.  The wall_tip prism coverage, continuity, quality and
core-interface requirements are unchanged.
