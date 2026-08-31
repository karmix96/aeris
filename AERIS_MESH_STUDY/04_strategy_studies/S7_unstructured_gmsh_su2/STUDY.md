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
setup is sound and implicating the limiter.  Multigrid tripled the residual drop
at a 770-fold tighter force spread and was still descending when the run ended,
and was read at the time as the fix.  **That reading was wrong** - see below.

### Steady convergence: achieved, and the fix is not multigrid

A ten-variant matrix on one 42 745-cell half-wing mesh, every variant carrying
multigrid and adding one thing on top, each run to 6 000 iterations with the
solver stop moved to -12 so that each could reach whatever it was capable of.
Gates below are the frozen policy gates, evaluated by `su2_pipeline.residual_gate`
and `force_tail_gate`:

| variant | added to multigrid | drop | final rms | min at iter | gates |
|---|---|---|---|---|---|
| `I_combined` | NK + ILU/25 + CFL 25 | 6.906 | -9.508 | 5999 | **pass** |
| `J_nk_no_mg` | as above, multigrid removed | 6.906 | -9.508 | 5999 | **pass** |
| `G_nk_cfl` | NK + CFL 25 | 6.363 | -8.966 | 5999 | **pass** |
| `F_nk_linear` | NK + ILU/25 | 6.265 | -8.868 | 5999 | **pass** |
| `B_newton_krylov` | NK alone | 5.954 | -8.556 | 5999 | residual fail by 0.046 |
| `D_high_cfl` | CFL 25 | 1.798 | -4.401 | 927 | fail |
| `C_strong_linear` | ILU/25 | 1.465 | -4.068 | 953 | fail |
| `A_baseline` | nothing | 1.082 | -3.685 | 3604 | fail |
| `E_quasi_newton` | `QUASI_NEWTON_NUM_SAMPLES` | 1.082 | -3.685 | 3604 | fail |
| `H_linear_cfl` | ILU/25 + CFL 25 | 1.036 | -3.639 | 5961 | fail |

**Newton-Krylov is the discriminating ingredient.**  Every variant carrying it is
monotonic and reached its minimum residual at iteration 5999 of 6000 - none turned
around, all were still descending when the budget ran out.  Every variant without
it limit-cycled, and none exceeded 3.02 orders of best drop.  Multigrid alone,
given 6 000 iterations rather than 1 500, ends at 1.082 orders: the earlier
"multigrid is the fix" reading was an artifact of stopping at 1 500 while the
residual happened to be on a downswing.

Newton-Krylov is necessary but **not sufficient** within the budget: alone it
reaches 5.954 orders and misses the gate by 0.046.  It needs either the stronger
linear solve or the higher CFL to clear six orders in 6 000 iterations, and both
together are fastest.

The accelerators are coupled, not additive.  `CFL_NUMBER= 25` with the aggressive
ramp is the worst variant in the matrix without Newton-Krylov (`D`, 2.041 orders
best) and the second best with it (`G`, 6.363).  The earlier matrix rejected a
high CFL correctly *for the stock scheme*, and carrying that forward would have
been the wrong lesson.

Final forces separate exactly along the gate:

| group | CL spread | CD spread | CMy spread |
|---|---|---|---|
| four gate-passing variants | 0.00 % | 0.00 % | 0.01 % |
| five gate-failing variants | 5.54 % | 0.62 % | 10.74 % |

The accepted runs agree to within 5e-7 on all three coefficients no matter how the
solver reached them - CL 0.018883, CD 0.087040, CMy -0.006617.  The rejected runs
disagree by a tenth of CMy.  The gate is discriminating what it was written to
discriminate.

Three SU2 8.5.0 behaviours are established here by byte comparison, not inference:

1. `QUASI_NEWTON_NUM_SAMPLES` is a **no-op**.  `A_baseline` and `E_quasi_newton`
   differ by that one line; their 6 000-row histories are byte-identical and SU2
   never writes the string "quasi" to its log.
2. Multigrid is **bypassed** under `NEWTON_KRYLOV`.  `I_combined` and `J_nk_no_mg`
   differ by seven `MG*` options; their histories are byte-identical.  SU2 echoes
   the multigrid settings regardless, so the log cannot be used to tell.
3. SU2 **never reports Newton-Krylov activation**: "Newton" and "Krylov" appear
   zero times in a run with `NEWTON_KRYLOV= YES`.  Whether it took effect can only
   be established from the residual history.

This matrix ran at 42 745 cells on a laptop.  It selects a solver configuration.
It does **not** establish convergence at production resolution.

### Coarse resolution: cost measured, and the gate found unsatisfiable again

Two bounded probes of the shortlisted `G_nk_cfl` on the index-0 `coarse` half mesh
(1 549 111 cells, two MPI ranks, 5 and 25 iterations, wall 65 s and 174 s) settle
two things the confirmation budget depends on.

**Cost.**  Differencing the two separates startup from iteration:

| quantity | measured |
|---|---|
| per iteration, 2 ranks | 5.45 s |
| startup: mesh read, partition, preprocessing | 37.8 s |
| 6 000 iterations, 2 ranks | 9.1 h per variant |

Memory follows ranks x cells, because each rank reads the whole mesh before
partitioning: **1.20 GiB per rank per million cells**, so 1.86 GiB per rank here.
That reproduces the recorded OOM exactly - eight ranks at 2.5 M cells needs 24 GiB
against a 16 GiB machine - and four ranks at coarse, 7.44 GiB, is what fits the
desktop budget.

**And the residual gate was unsatisfiable at this resolution.**  Every
`laptop_smoke` history starts between -2.576 and -2.687, so the policy's assumed
worst initial residual of -3.0 and its derived solver stop of -9.0 were safe
there.  The coarse mesh starts at **-3.6643**, identically on both probes, and a
run starting there must reach -9.6643 to drop six orders.  A solver stopping at
-9.0 halts having dropped 5.336 and is rejected on `insufficient_residual_drop`,
which is indistinguishable from a solver that failed to converge.

This is defect 10 recurring one resolution level up, from the same cause.  It is
recorded as defect 11 below.  Neither acceptance threshold changed.

The cost consequence is real: at smoke the fastest passing variant needed 5 872
iterations to reach -9.5, and coarse asks -9.6643 with 36 times the cells.  A
6 000-iteration confirmation may land short.  That is a measurement to make, not a
threshold to lower.

### The rank sweep: parallelism does not help, and does not change the answer

A clean sweep on an idle machine, 5- and 25-iteration probes differenced at each
rank count, on the index-0 `coarse` half mesh:

| ranks | s/iteration | startup | GiB | 6 000 iterations |
|---|---|---|---|---|
| **1** | **4.60** | 12.0 s | **1.86** | **7.7 h** |
| 2 | 5.65 | 39.8 s | 3.72 | 9.4 h |
| 4 | 8.50 | 59.5 s | 7.44 | 14.2 h |

More ranks are monotonically slower.  The solve is memory-bandwidth bound, so
extra ranks buy halo exchange and partitioning for no arithmetic gain, and each
holds another full copy of the mesh.  One rank is simultaneously the fastest and
the smallest; four ranks is 1.85x slower per iteration and costs four times the
memory to be so.

The three histories are **identical to the byte** (sha `9378f811...`), so the
decomposition is a pure cost choice and results are reproducible across it.  The
serial laptop matrix and a multi-rank production run are therefore the same
experiment.  Checked over 25 iterations; worth re-checking at 6 000.

Measurement hygiene, recorded because it nearly went the other way: a first
4-rank probe taken while a test suite and a geometry build were running read
6.35 s per iteration against the clean 8.50 - a 25 per cent error, in the
direction that would have made 4 ranks look acceptable.

### The grid family, measured where it can be and bounded where it cannot

Surfaces built at all three levels for index 0.  Surface triangles and prisms are
**exact**; only the tetrahedral count is estimated, by two independent methods
that agree:

| level | surface tris | prisms | cells | GiB/rank | tip cap min angle |
|---|---|---|---|---|---|
| coarse | 5 356 | 126 984 | 1 549 111 (measured) | 1.86 | 12.91 deg |
| medium | 10 826 | 343 456 | ~4 317 000 | 5.18 | 9.48 deg |
| fine | 21 010 | 835 160 | ~12 056 000 | 14.47 | 7.03 deg |

Surface triangles scale as r^2 exactly as the edge-length definitions require
(2.021x and 3.923x against 2.0 and 4.0).  The two tet estimates - an r^3 scaling
of the measured coarse core, and the pipeline's own conservative ceiling
de-rated by the 1.2035x factor it over-counts coarse by - agree to 1.4 per cent
at medium and 2.8 per cent at fine.

**Consequence: `fine` is not solvable on the inventoried host.**  At 14.47 GiB
for a *single* rank against the S6 guide's reported 11.36 GiB available, and with
every rank holding the whole mesh, no decomposition rescues it.  That is the same
`RESOURCE_BLOCKED` wall S6 hit, and it blocks the three-level grid convergence M5
requires.  `medium` fits at one rank, 5.18 GiB, about 21 h for 6 000 iterations.
The laptop refuses `medium` meshing outright on its own resource preflight.

**And the tip cap degrades with refinement.**  Minimum cap angle falls
monotonically: 18.33 deg at `laptop_smoke`, 12.91 at `coarse`, 9.48 at `medium`,
7.03 at `fine`.  Refining chordwise on a thin cambered tip section makes the
Delaunay cap more slender, not less.  **The rejected rigid ladder measured
7.209 deg**, so the accepted construction at `fine` is worse than the one thrown
out for being too slender.  This was invisible before the tip-cap instrumentation
existed, and it is a quality trend the grid study must account for rather than a
defect in any one mesh.

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

10. **The residual gate was unsatisfiable by construction.**
   `CONV_RESIDUAL_MINVAL` was derived from `residual_log10_final_max`, halting SU2
   at the acceptance bar, so the final residual was -8 by construction and the
   achievable drop was exactly `initial + 8`.  Every S7 run starts between -2.576
   and -2.687, capping the drop at 5.42 orders against a gate asking 6.0.  Two runs
   that had genuinely converged - `conv_matrix/A_first_order` at 5.445 and
   `solver_tuning/B_newton_krylov` at 5.397, both `Exit Success` - were rejected on
   `insufficient_residual_drop` alone, and the same truncation caused
   `B_newton_krylov`'s only force-tail failure (CMy 1.094e-3; the same
   configuration run deeper reaches 2.9e-6).  The stop is now a separate policy
   key, `solver_stop_residual_log10`, checked fail-closed against
   `min(residual_log10_final_max, assumed_worst_initial - drop_min)` on every
   config emission.  It was set to -9.0 here; defect 11 supersedes that value.
   **Neither acceptance threshold changed.**

11. **The repaired stop was itself calibrated at the wrong resolution.**  The
   assumption behind it, `assumed_worst_initial_residual_log10: -3.0`, bounded
   every `laptop_smoke` initial residual (-2.576 to -2.687) and none at coarse
   (-3.6643).  The stop of -9.0 that followed truncates a coarse run at 5.336
   orders against a gate asking 6.0.  The assumption is now set from the
   measurement (-4.0) and the stop follows (-10.0) - but raising a constant would
   only move the defect to the next resolution, so `residual_gate` now derives the
   required final residual **from each run's own initial** and reports
   `solver_stop_truncates_drop_gate` when the stop sits above it.  The gate names
   a truncated setup instead of blaming the solver.  The reason provably cannot
   fire on a run that would otherwise pass - such a run descended past
   `initial - 6.0` without stopping, so the stop is at or below it - and a test
   asserts that on all three measured initial residuals.  Verified on the real
   coarse history: the reason fires under the old stop and clears under the new.
   **Neither acceptance threshold changed.**

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
- **Multigrid as the convergence fix.**  It tripled the residual drop at 1 500
  iterations and was still descending, which read as a fix.  Run to 6 000 it ends
  at 1.082 orders having peaked at 3.019 and turned around; the earlier reading
  caught a downswing.  It is also bypassed entirely under `NEWTON_KRYLOV`.
- **Quasi-Newton acceleration.**  `QUASI_NEWTON_NUM_SAMPLES` is a no-op in
  SU2 8.5.0: byte-identical 6 000-row history to the baseline.
- **A stronger linear solve or a higher CFL as the fix.**  Neither clears 3.02
  orders without Newton-Krylov, and combining them (`H`) is worse than either
  alone.

## Not established

- No converged CFD solution exists **at production resolution**.  Four solver
  configurations pass both frozen gates at 42 745 cells; the coarse level is 1.55 M
  and the matrix must be repeated there before any convergence claim.  The coarse
  chain is now measured to start, run and parse - `G_nk_cfl` exits 0 on two ranks
  and its history reads back - but 25 iterations is a start-check, not a result.
- **How many iterations coarse convergence needs is unmeasured.**  The requirement
  is now known to be -9.6643 rather than smoke's -8.687, and the only comparable
  datum is 5 872 iterations to -9.5 at smoke.
- The 4-rank speedup is **assumed at 1.8x** in the wall-time budget; only the
  2-rank cost is measured.
- The selected configuration is not yet wired into `POLICY.yaml`'s
  `su2.numerical_method`; the matrix chose it, the policy does not yet carry it.
- No production-resolution volume mesh beyond five designs.
- No grid-convergence or trailing-edge sensitivity result.
- Quality limits for facet fidelity and tetrahedral shape are provisional,
  calibrated from what the mesher achieves rather than a required accuracy;
  `geometric_fidelity_sensitivity_study_passed` is false.
- The required independent Claude Opus/max review has never completed.
- `round_c_lhs10_seed42` is untouched and forbidden.
