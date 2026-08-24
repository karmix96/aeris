# S7 study record

## Question

Can a deterministic Gmsh triangular-wall / prism-layer / tetrahedral-core path
produce auditable wall-resolved unstructured meshes and converged SU2 RANS-SA
solutions over the same AERIS pyGeo development space as S6, without
geometry-specific repair?

## Hypothesis and falsifiers

The hypothesis is conditional: the frozen Gmsh candidates may pass every
geometry, mesh, solver, y+ and recovery gate without per-case tuning.  It is
falsified for campaign readiness by any missing readiness result.  A trailing-edge
or tip failure common to all candidates triggers a stop and a superseding mesher
ADR; it never triggers a weaker threshold.

None of the following supports the hypothesis on its own: a mesh file being
written, SU2 exiting zero, a residual decreasing without stable forces, a nominal
first cell height without measured y+, a laptop diagnostic, a synthetic fixture,
or a literature benchmark.

## Established, with numbers

### Geometry, across the design space

| level | accepted | notes |
|---|---|---|
| laptop_smoke | 15 / 15 | indices 0/24/49/74/99 x three TE variants |
| coarse | 15 / 15 | |
| medium | 15 / 15 | |
| fine | 15 / 15 | |

**60 / 60**, zero self-intersections, zero boundary or non-manifold edges, node
fidelity exactly 0.0 throughout.

### Volume meshing, whole development set

100 designs at the diagnostic tier: **100 / 100 accepted**, 101 attempts for 100
geometries with 99 first-try.  Prism wall coverage and column continuity
1.000000 on every design; zero negative cells.  Per design: 44 639 to 96 474
cells, tet SICN minimum 0.0378 to 0.1679 (p01 0.2286 to 0.3524), prism minSJ
0.2738 to 0.4607.

For comparison S6 needed 131 attempts for 100 geometries with 80 first-try, using
a 16-seed atlas; S7 uses three frozen candidates and no atlas.

### Volume meshing, production resolution

Five representative designs at `coarse`, all accepted on the first candidate:

| design | cells | tet SICN | tet p01 | prism SJ | core skew p99 | core nonortho p99 |
|---|---|---|---|---|---|---|
| dev_000 | 2 549 227 | 0.0651 | 0.6702 | 0.6183 | 0.413 | 31.7 |
| dev_024 | 2 231 389 | 0.0954 | 0.6764 | 0.6362 | 0.409 | 31.4 |
| dev_049 | 2 201 979 | 0.0702 | 0.6773 | 0.6342 | 0.409 | 31.4 |
| dev_074 | 2 505 872 | 0.0591 | 0.6753 | 0.6593 | 0.410 | 31.5 |
| dev_099 | 2 575 993 | 0.1038 | 0.6737 | 0.6161 | 0.410 | 31.5 |

Measured cost: 245 s meshing at 1.8 GB peak, 325 s auditing at 5.3 GB peak,
263 MB written, about 9.5 minutes per case.

### Solver chain

SU2 8.5.0 "Harrier" installed and pinned-version verified.  End to end on the
diagnostic tier: SU2 runs clean, 400 history rows, forces parse (CD 0.09200,
CL 0.02397, CMy -0.01213), y+ parses, restart is produced and digest-linked, and
every gate evaluates.

### Wall resolution

Measured on the index-0 coarse mesh, 120 iterations on 2 ranks:

| statistic | value | limit | |
|---|---|---|---|
| p95 | 0.5573 | 1.0 | pass |
| p99 | 0.7552 | 2.0 | pass |
| maximum | 0.8744 | 5.0 | pass |

All 5 293 wall points reported.  This is a bounded diagnostic, not a converged
campaign case, so `production_y_plus_passed` remains unmet.

### Steady convergence: not achieved, and diagnosed

The preregistered numerics reach a limit cycle: over 3 000 iterations the density
residual oscillates between about -3.2 and -5.2 for a net drop of 1.658 orders
against a six-order gate, while CD settles to a 1.8e-3 spread.  Forces converging
while residuals do not is the signature of limiter-induced limit cycling.

A six-variant search, 1 500 iterations each:

| variant | rms final | orders dropped | CD | CD spread |
|---|---|---|---|---|
| first order (control) | -8.021 | 5.445 | 0.29991 | 4.1e-06 |
| multigrid | -5.826 | 3.250 | 0.09099 | 2.4e-06 |
| Venkatakrishnan 0.05 | -4.320 | 1.745 | 0.09707 | 2.2e-03 |
| limiter frozen at 1 200 | -3.961 | 1.385 | 0.09936 | 4.6e-02 |
| baseline as preregistered | -3.685 | 1.109 | 0.09169 | 1.8e-03 |
| non-dimensionalised | -4.125 | -0.601 | 0.03135 | 7.9e-02 |

First order converges to the -8 criterion and stops at iteration 460, proving the
setup is sound and implicating the limiter.  **Multigrid is the fix**: triple the
residual drop, a 770-fold tighter force spread at the same CD, still descending
when the run ended.  The policy configures no multigrid at all.

## Half domain versus mirrored, measured

S6 meshes y >= 0 and S7 mirrored the whole wing, so the two were solving different
domains while their results were meant to be compared.  Neither policy declared a
domain; the difference was found by reading coordinates out of the mesh files.
S7 is now a half model and the mirrored path is kept for comparison.

Both domains, same five designs, `laptop_smoke`, same machine:

| design | full cells | half cells | full prism_q | half prism_q | full tet_q | half tet_q |
|---|---|---|---|---|---|---|
| 000 | 77 348 | 42 745 | 0.3795 | 0.3795 | 0.1107 | 0.1500 |
| 024 | 66 469 | 37 905 | 0.3676 | 0.3676 | 0.1499 | 0.1863 |
| 049 | 65 313 | 37 156 | 0.4261 | 0.4261 | 0.0664 | 0.0774 |
| 074 | 76 476 | 42 466 | 0.4327 | 0.4327 | 0.0831 | 0.0893 |
| 099 | 77 924 | 42 723 | 0.4111 | 0.4111 | 0.1679 | 0.2009 |

5/5 accepted either way, all 56 gates.  Prism quality is identical to four decimals
on every design, which is the point: the marched layer reproduces what Gmsh's
extrusion was doing rather than approximating it.  Tetrahedral quality is higher on
every design, because the half core runs the size field and the optimisation passes
together.

Cost falls by 1.791x in cells and 1.62x in wall time, 82.2 s against 50.6 s for the
five.  Not 2x: only the spanwise extent is halved, the farfield box keeps its full
reach upstream, downstream and radially, and the symmetry plane is new boundary
that did not exist before.

The reference area is halved with the domain.  The reference values describe the
whole wing whatever is meshed, while SU2 integrates force over the markers it is
given, so leaving it alone would report CL and CD at exactly half their true value
on a run that looked entirely healthy.

### Verification of the half domain

Breadth, at `laptop_smoke`: **20 / 20 accepted** over indices 0, 5, ... 95, in 192 s.

Production resolution, index 0 at `coarse`: **accepted, no failures**.  1 549 111
cells as 126 984 prisms and 1 422 127 tetrahedra over 318 865 nodes, meshed in
146 s and audited in 202 s, 3.6 GB peak against the mirrored mesh's 5.3 GB.
Quality: prism 0.61826, tet 0.10739, first-cell-height error exactly zero.

Solver chain: SU2 8.5.0 accepts the mesh and reports the boundary as
`Symmetry plane | symmetry` with 1 799 elements on it; `REF_AREA` is written as
0.480549 against the whole-wing 0.961097, and the run exits zero.

**Not verified: that the half and mirrored domains give the same converged
coefficients.**  Both were run for 250 iterations at smoke resolution and neither
converged - the mirrored dropped 1.500 orders and the half 2.339, against a gate of
six - with CL still moving in both.  CL differed by 13.5 per cent and CD by 4.7 per
cent, which is a comparison between two unconverged solutions on two different
meshes and settles nothing about the physics.  It does establish that the reference
area is right to within a factor: a missing halving would show as roughly 100 per
cent, not 13.

That the half mesh fell further in the same 250 iterations is a hint and no more.
The comparison becomes meaningful only once the convergence problem is resolved,
and it should be repeated then.

## Defects found and corrected, in order

Each was found by measurement, and the fix preceded any change to acceptance
criteria.

1. **Tip cap centre fan** left the thin cambered tip section: 24 measured
   wall_lower/wall_tip self-intersections.  Replaced by a chordwise ladder, then
   by planar Delaunay when the ladder proved to create near-collinear slivers
   (1.516 degree minimum angle, two inverted prisms, minSJ -0.80).  Tip cap
   minimum angle 1.516 -> 7.209 -> 20.649 degrees.
2. **Facet fidelity graded against the node-fidelity limit**, which no
   preregistered level could satisfy.  Split into a correctness gate (node, still
   1e-4, measures exactly 0.0) and a resolution gate (facet, per level).
3. **The self-intersection instrument counted contact as interpenetration** -
   measured penetration 3.8e-17 m.  Interpenetration now requires material
   strictly on both sides of the other triangle's plane.
4. **Surface node distribution was accidental**: cosine clustering gave an end
   interval 22 times finer than the declared trailing-edge target.  Replaced by a
   blend that requests the declared target directly.  Wall minimum angle
   0.85 -> 2.90 degrees, aspect 67.5 -> 19.7.
5. **The size-field ramp was too short**: near-to-far over a fixed six near-body
   lengths, a sevenfold size change across two or three cells.  Ramp length is now
   derived from a declared growth ratio.  Violating faces' distance-to-wall p95
   fell from 4.396 L to 0.168 L.
6. **Prism validity was decomposition-dependent**: two prisms negative under one
   3-tetrahedron split and positive under another, with Gmsh's Jacobian positive
   throughout.  Validity now uses the isoparametric Jacobian.
7. **Post-generation optimisation was disabled on an over-general claim.**
   Relocate3D does destroy the prism schedule (minSJ 0.3332 -> -33.3); Netgen does
   not, leaving the prism block bit-identical while removing slivers (tet SICN
   0.029 -> 0.146).  Enabled scoped to the core, with rollback if it ever makes a
   mesh less valid.
8. **Face metrics judged the boundary layer by a core criterion.**  Split by face
   family: tet-tet p99 31.1, prism-tet 57.0, prism-prism 82.5, combined 70.5.
   Prism lateral faces are anisotropic by design.
9. **Three SU2 integration defects**, each findable only by running the solver:
   `SURFACE_OUTPUT` is not an 8.5 option; y+ is absent from the surface CSV and
   only present in the surface Paraview file; and the alias `"Y+"` collapsed to
   `"y"` and matched the y coordinate, reporting wall y+ of 1.135, the semi-span.

## Refuted hypotheses, recorded so they are not retried

- **A boundary-layer thickness limit tied to the trailing-edge opening.**  Measured
  as a clean law across four stack heights, then withdrawn: the PLC failures were
  the tip-cap slivers, and after the Delaunay cap the same geometry meshes at
  15.3x the opening.
- **Netgen creating index 49's negative cells.**  They were present unoptimised;
  Netgen improved that mesh 150-fold.
- **Cap-matched near-core sizing.**  No change to tet quality, four percent more
  cells.
- **Trailing-edge core refinement.**  Localisation showed only 0.9 percent of bad
  cells were near the trailing edge.
- **Non-dimensionalisation.**  The leading convergence hypothesis, and wrong: the
  residual rose and the force spread grew to 7.9e-2.
- **Limiter freezing**, at 400 and at 1 200.  Destabilised the solution or left
  forces 25 times worse than baseline.

## Not established

- No converged CFD solution exists; the residual gate may be unreachable as
  preregistered, and multigrid is a candidate fix that has not been adopted.
- No production-resolution volume mesh beyond five designs.
- No grid-convergence or trailing-edge sensitivity result.
- Quality limits for facet fidelity and tetrahedral shape are provisional,
  calibrated from what the mesher achieves rather than a required accuracy;
  `geometric_fidelity_sensitivity_study_passed` is false.
- The required independent Claude Opus/max review has never completed.
- `round_c_lhs10_seed42` is untouched and forbidden.
