# S7 roadmap and readiness gates

## Done

- [x] Strategy ADR and executable policy written before any real result.
- [x] Independent pyGeo full-wing surface with declared TE variants, closure,
      orientation, self-intersection, exact-node and facet-centroid checks.
- [x] Gmsh fixed-wall / prism / tet pipeline and native SU2 writer.
- [x] Independent Gmsh plus native-SU2 audit of labels, topology and quality.
- [x] Fixed SU2 RANS-SA configuration, parsers, one-restart logic, immutable
      attempts, process-tree timeout handling.
- [x] Development batch, resume, terminal manifests, full hashing, laptop
      refusal, desktop and Slurm launchers.
- [x] Coupled grid and TE qualification with unequal-grid Richardson and GCI.
- [x] Focused tests and static checks: 26 tests, Ruff clean.
- [x] **Surface qualified across the design space: 60 / 60.**
- [x] **Volume across the whole development set: 100 / 100, 101 attempts.**
- [x] **Production-resolution volume on five designs: 5 / 5, first try.**
- [x] **SU2 8.5.0 installed, pinned, and the whole chain verified end to end.**
- [x] **Wall y+ at coarse measured and passing: p95 0.5573, max 0.8744.**
- [x] Convergence failure diagnosed by a six-variant search; multigrid identified
      as the fix and two leading hypotheses refuted.
- [x] Desktop runbook with measured costs.

## Domain

S7 meshes the **half model**, y >= 0 closed by a symmetry plane at the root, which
is the domain S6 meshes.  The mirrored model remains reachable through
`modeled_domain` for comparison and passes the same audit.  Meshes produced before
this change are mirrored and superseded.

## Next, in order

1. **Confirm Newton-Krylov at coarse resolution.**  Superseded "confirm
   multigrid", which is refuted: multigrid alone ends at 1.082 orders over 6 000
   iterations and is bypassed entirely under `NEWTON_KRYLOV`.  Four
   Newton-Krylov configurations pass both frozen gates at 42 745 cells and agree
   on CL/CD/CMy to 5e-7; see `../RUN_LOG/s7_solver_tuning_matrix.md`.

   The residual gate itself does **not** need re-deriving.  It was unsatisfiable
   because the solver was being stopped at the acceptance bar; that is repaired
   in `POLICY.yaml` as `solver_stop_residual_log10`, with both acceptance
   thresholds unchanged.  See the 2026-08-25 amendment in ADR-0017.

   The confirmation job is small - repeat two or three variants at `coarse`
   (1.55 M cells), not all ten.  Recommended shortlist, cheapest first:

   | rank | variant | why |
   |---|---|---|
   | 1 | `G_nk_cfl` | fewest options changed from the frozen block; fastest wall time of the passing set |
   | 2 | `I_combined` | deepest drop (6.906) and most headroom if coarse converges more slowly |
   | 3 | `F_nk_linear` | falls back if the high CFL destabilises at production resolution |

   `J_nk_no_mg` need not be run: it is byte-identical to `I_combined`.  Adopt the
   winner into `su2.numerical_method` through a superseding ADR amendment
   carrying the coarse measurements.  **Do not adopt from the laptop matrix
   alone** - 42 745 cells is a solver diagnostic, not a production result.
2. **The 100-design coarse sweep on the desktop, in the half domain.**  About 10
   hours sequential.  This supersedes the mirrored meshes rather than adding to
   them, and should run before the multigrid confirmation so that decision rests
   on a mesh that will be kept.  See `RUNBOOK.md`.
3. **A converged coarse CFD case**, which is what actually earns
   `production_y_plus_passed`.  Note MPI memory: each rank reads the full mesh
   before partitioning, so 2.5 M cells needed about 3 GB per rank; eight ranks was
   OOM-killed on 16 GiB.
4. **Ten to twenty unattended CFD pilots.**
5. **Five coupled coarse/medium/fine grid studies** and the three TE variants.
6. **Geometric fidelity sensitivity study.**  The facet and tet limits are
   provisional and calibrated from what the mesher achieves; this is the
   prerequisite before any accuracy claim rests on them.
7. **Independent Claude Opus/max review**, which has never completed.
8. Freeze everything, then one hold-out run of about ten cases.

## Decision points

If a trailing-edge or tip failure recurs across all frozen candidates, quarantine
S7 and write a superseding ADR for one alternative; do not weaken a threshold.
The specific capability Gmsh lacks is layer collision handling, which
snappyHexMesh and cfMesh both provide.

The fixed-topology exploit is now measured rather than merely proposed; see
`FIXED_TOPOLOGY.md`.  Freezing the surface grid costs about 1.11x mean surface
cells at `coarse` over six cases, and the wall is already a structured tensor
grid, so index correspondence follows directly.  The blocker is the tip cap, whose
Delaunay connectivity follows each design's geometry and which falls back to the
ladder without recording that it did.  The next step is one instrumentation field,
not a redesign.  Original framing: freeze the surface sampling counts across the family so
node correspondence is exact and index-based, mesh a few templates to full
quality, then deform onto the remaining designs and audit the result.  S6 already
works this way.  Surface triangle counts currently vary per design.

## Current blockers

The 16 GiB laptop carries the diagnostic tier and single coarse cases, but not the
full coarse campaign and not converged CFD at production resolution.  Those are
desktop or HPC work.

## Joint validation programme

The shared S6/S7 sequence this study feeds - staging, the paired comparison and
the decisions that must be taken before any CFD is recorded - is in
`../VALIDATION_PROGRAMME.md`.
