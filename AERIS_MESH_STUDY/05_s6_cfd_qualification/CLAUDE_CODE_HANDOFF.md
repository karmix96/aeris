# Claude Code continuation order — S6 qualification

Updated: 2026-09-02T22:49:49+03:00

## Human-directed six-rank execution override

At 2026-09-02 22:49 EEST the principal investigator explicitly ordered one
immediate corrected-mesh CFD run with six MPI ranks and directed Codex not to
wait for the Claude audit. Policy `policies/m2_a_c03_canary_v5.yaml` and the
honest waiver record
`reviews/human_m2_a_c03_six_rank_override_20260902.json` bind attempt04. Do not
reinterpret this as closure of the earlier Claude findings. Periodic
checkpoints are disabled because multi-rank signal collectives are unverified;
all residuals/logs/resource samples and final surface/double-volume outputs are
still required. No retry is authorized. If attempt04 is running, monitor it;
do not start any second process. If terminal, audit and classify it before any
further action.

## Current correction order — 2026-09-02 19:59 EEST

Delegation status at 20:06 EEST: Claude Opus exited before making any code
change because its session limit was reached; the CLI reported a reset at
00:20 Europe/Athens. The implementation files and tests therefore remain at
commit `21ec3ef35fe48c3c7965f7b91cd98e5274047688`. Resume this exact order after
the reset. Do not assume any item below was implemented merely because the
delegation was attempted.

The first independent recovery review is complete and retained at
`reviews/claude_m2_a_c03_desktop_recovery_review_20260902.json`; its verdict is
`NO_GO_DESKTOP_RECOVERY_CANARY`. Do not launch CFD. Implement and test these
bounded corrections:

1. Extend checkpoint inventory to require finite `ReferenceState` arrays
   `Density`, `Pressure`, and ADflow's actual `Mach_Velocity`; require density
   and pressure to be strictly positive. Keep the label
   `structurally_validated_not_restart_tested` until a separately governed real
   restart round-trip exists.
2. Move watchdog resource sampling onto an independent continuous thread so
   hashing/copying/CGNS validation cannot create a sampling blind spot. Record
   the maximum sample gap and samples observed during checkpoint capture.
3. Record the latest parseable ADflow nonlinear iteration, total minor
   iteration and component residual row with every checkpoint request and
   completed checkpoint. Assert/record native `monitor.writevolume=true`
   immediately before `solver(ap)`.
4. Add a governed, transparent ANK density-slope diagnostic and terminal
   `SOLVER_STAGNATION_MEASURED` classification; it must not silently convert a
   partial result into acceptance or trigger an automatic blind rerun.
5. Correct the resource plan with itemized write/validator allowances, an
   explicit MemAvailable preflight check, and a note that bytes/cell is derived.
   Reconsider whether `L2Convergence=1e-10` provides the best defensible
   component-residual margin versus the current unbounded `1e-11` extrapolation.
6. Add focused regression tests and run the full existing focused suite.
   Refresh both handoffs with exact test result and remaining gate.
7. Add a read-only MPI scaling assessment before policy v5. Attempt03 used
   exactly one MPI rank and GNU time measured 99% of one CPU, while this host
   exposes 6 physical / 12 logical CPUs. Design (do not execute) the cheapest
   governed 1/2/4/6-rank fixed-work benchmark that can measure elapsed time,
   peak full-session RSS and convergence-rate invariance on the exact corrected
   mesh. Quantify duplicated/halo-memory risk from installed ADflow/OpenMPI
   sources where possible. No ADflow initialization is authorized by this item.

H1 in the historical Claude review is a false source-reading conclusion, not a
code defect. Installed
`/home/mike_kara/packages/mdolab/adflow/adflow/pyADflow.py` calls
`self._setForcedFileNames()` immediately after `setAeroProblem()` (near line
1214), and `_setForcedFileNames` assigns
`self.adflow.inputio.forcedvolumefile = <outputDirectory>/<AP.name>_forced_vol.cgns`
(near lines 6631-6648). With AP name `aeris_cfd`, the watchdog's path is exact.
Add a source-contract regression/evidence record and ask the next independent
review to withdraw H1. Do not initialize ADflow merely to prove this source
fact.

This is the live recovery-audit handoff for the AERIS S6 automated CFD
qualification study. Preserve the evidence chain. A mesh correction and
restartable low-memory solver path have been implemented but are not yet
independently accepted. **No CFD is currently authorized.**

## Read first, in order

1. `MASTER_EXECUTION_GUIDE.md`
2. `LIVE_STATUS.md`
3. `reports/m2_a_c03_desktop_recovery_plan_20260902.json`
4. `reports/m2_a_c03_ank_only_convergence_forecast_20260902.json`
5. `reports/m2_c03_wall_normal_recovery_family_20260902.json`
6. `04_strategy_studies/S6_bounded_mesh_atlas/wall_normal.py`
7. `04_strategy_studies/S6_bounded_mesh_atlas/cfd_qc.py`
8. `05_s6_cfd_qualification/canary.py`
9. `../../src/aeris/cfd/presets/data/adflow_rans_ank_memory_safe_v1.yaml`
10. `policies/m2_a_c03_canary_v4.yaml`
11. `reports/m2_a_c03_canary_authorization_consumed_20260901_attempt03.json`
12. `reports/m2_a_c03_canary_execution_20260901_attempt03.json`
13. `reports/m2_a_c03_solver_postmortem_20260902_attempt03.json`
14. `reviews/claude_m2_a_c03_attempt03_postrun_review_20260902.json`
15. `studies/canary/m2_a_c03_measurement_20260901_003/adflow_effective_options.json`
16. `studies/canary/m2_a_c03_measurement_20260901_003/solve_report.json`
17. `studies/canary/m2_a_c03_measurement_20260901_003/adflow_run.log`
18. `studies/canary/m2_a_c03_measurement_20260901_003/resource_watchdog.jsonl`

Do not read or inspect the locked holdout contents.

## Recovery candidate to audit

- Immutable implementation review target:
  `21ec3ef35fe48c3c7965f7b91cd98e5274047688`.
- Recovery-plan SHA-256:
  `e1eaea665ff8df4b04507f5cd3dfa2d44db1a170244cb7dbb8d3294c7e8bc17b`.
- Family-report SHA-256:
  `392ef9850de8e7795c35ef50082a3583bc1ed21855668e16b59b925e2dfa65e9`.
- Four development meshes A/B/C/E were redistributed with one common method.
  Each retains 943,104 cells, zero inversions, exact wall/farfield, 20 paired
  interfaces, and qmin above 0.10. Re-open and recompute; do not trust reports.
- The selected A output file SHA-256 is
  `0fe4a4c00bbed1e47fcdaa46b60d00334d48c0cfe9b617cb2a3b0ec51cbd7ced`;
  its deterministic coordinate-payload hash is
  `6295e5ab83aa145dad887ec4ccbb2093067de87578d22099695f97897bdf480f`.
- Actual attempt03 y+ scaled facewise only by the exact new/old local
  first-cell height projects to global p95 0.2366, p99 0.2682, max 0.2932,
  with no failed wall region. Treat this only as a projection.
- Proposed numerical change: one-rank ANK remains; NK is disabled. All
  subspace and ILU values stay 10/20 and 1/1. Limits remain nCycles 20,000 and
  the independent 27,000-second wall-clock cap. `L2Convergence` is tightened
  from 1e-8 to 1e-11 because all four late-ANK fits predict 1e-8 would stop
  before density passes 1e-5. Independently reproduce the fit and decide
  whether 1e-11 has defensible convergence and time margins.
- Proposed resource model: measured pre-NK/ANK peak 8.31702 GiB, forecast 9.2
  GiB, unchanged 75% WSL cap, 2 GiB headroom/floor and 0.25 GiB swap limits.
  Check both the phase attribution and arithmetic.
- Final volume output is double precision. Surface output adds rho and vector
  skin friction. Native SIGUSR1 is requested every 1,800 s; the watchdog
  targets only the exact MPI Python rank. It requires all 13 zones, all three
  coordinates, and fully readable finite Density/Velocity/Pressure/SA fields;
  hashes source and fsynced staging copy independently; reopens the staging
  copy; then atomically publishes and directory-fsyncs it. Inspect remaining
  crash windows and do not equate structural validation with a tested restart.
- Focused suite currently reports 79 passed, including live subprocess
  SIGUSR1 publication, invalid-checkpoint nonpublication, and real ADF-CGNS
  full-field inventory tests. Re-run it.

## Terminal attempt03 outcome

- Execution: `m2_a_c03_measurement_20260901_003`.
- Bound launch commit: `579c561368d68aacdda067c978246128b3d27a21`.
- Policy SHA-256:
  `95a70fad10e745d6f8f82267bfd887470b38fb8a77301f430b61d6e2272cfb3c`.
- Mesh SHA-256:
  `be2805ff85b6b1043863d7678d1551a52b6e8a65b299534d4ec0aaeffa51aeb4`.
- Case: A/C03, development index 83, 943,104 cells, one rank, ADflow
  2.13.1 RANS/SA, ANK/NK subspaces 10/20, ILU fill 1/1.
- Terminal status: **`SOLVER_MEASUREMENT_FAILED`**.
- Attempt03 launched exactly once. Its authorization is consumed permanently.
  Never reconstruct or reuse its execute token.
- The host completed the workload: 6 h 39 min watchdog elapsed, no OOM, no
  swap growth, no watchdog stop, and surface output written.
- Peak full-session RSS: 9.855038 GiB. Forecast: 9.45 GiB. Minimum available
  memory: 2.046471 GiB versus the 2 GiB floor. Physical executability was
  demonstrated, but the immutable resource forecast check failed.
- ADflow completed 944 native monitor rows through nonlinear row 943 and total
  minor iteration 20,021, then returned `solve_failed=true`.
- Density `1.202361e-4` and energy `2.586341e-5` failed their `1e-5` limits;
  momentum and SA passed. Force-tail stability passed but is diagnostic only.
- NK practical stagnation: last-200 median linear residual 0.9775, p95 0.997,
  and 98/200 steps at 0.01. The tail decreased slowly and did not diverge.
- y+ failed globally by absolute maximum and in 9/13 regions. All seven
  tip/cap blocks failed; `tip_base` reached p95 5.79 and max 5.86.
- Signed boundary mass balance and interface-field continuity remain unproven.
- Independent post-run review verdict: faithful evidence, desktop execution
  proven, resource/convergence/y+ gates failed, no new CFD authorized.

## Non-negotiable state

- V2, v3 and v4 authorizations are all consumed. Never retry or reuse any of
  them.
- Do not launch ADflow, MPI, a preconditioner build, a short CFD probe, C01,
  C02, C03, a campaign, or a holdout case.
- A "memory probe" that initializes or advances ADflow is a governed heavy
  action and is not authorized by a review alone.
- Do not classify the diagnostic forces as accepted or use them for design
  ranking.
- Do not claim grid independence. C01-to-C02 is not a strong wall-normal step,
  and C03 now has measured local y+ failures.
- Do not change flow physics, turbulence model, mesh identity, mission
  references, convergence limits, watchdog floor, or WSL configuration.
- Do not delete, clean, truncate, regenerate or overwrite any attempt
  directory or immutable record.
- Preserve unrelated user work:
  - `AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/campaign.py`
  - `configs/aero/section_study/stage1_reference_subset.json`
  - `configs/aero/section_study/stage1_summary_subset.txt`
- Do not create policy v5, an attempt directory, or an execute token. The
  review output is evidence for Codex; it does not launch or self-authorize.

## Evidence retention

The complete attempt directory is:

`studies/canary/m2_a_c03_measurement_20260901_003/`

Retain the case, requested/effective options, static runner, launch record,
combined solver log, ADflow JSON, all 944 residual rows, solve report, all
11,715 watchdog samples, GNU-time output and surface CGNS. The surface file is
retained locally with SHA-256
`3abf9350bd92d66933f3a02fabbc84e62291aa2501534ee2d9531ec1818ab973`;
repository policy permits its hash but not the CGNS file itself to be committed.
No volume or restart state exists.

## Independent audit order while Codex is unavailable

Work through these read-only/mesh-QC tasks without waiting for Codex:

1. Inspect `git status` and the review-target commit. Preserve unrelated changes
   and every existing CFD artifact.
2. Independently hash and reopen all four v3 output CGNS files. Recompute cells,
   signed volumes, scaled quality, wall/farfield fidelity, paired interfaces,
   per-zone first-cell spacing, and deterministic coordinate hashes.
3. Recompute A's facewise y+ projection from the retained attempt03 surface and
   old/new meshes. Verify CGNS ordering and sample-count correspondence. State
   explicitly why this is not actual candidate y+.
4. Recompute ANK/NK row counts and NK linear statistics from `adflow_run.json`.
   Recompute the RSS phase change from `resource_watchdog.jsonl`. Check whether
   ANK-only is the lowest-memory coherent single lever and whether 9.2 GiB is a
   defensible bound for that changed execution.
5. Inspect the exact installed ADflow 2.13.1 docs and Python/Fortran/C sources.
   Verify useNKSolver semantics, nCycles/L2/timeLimit, automatic volume output,
   double restart precision, SIGUSR1 behavior and forced filenames.
6. Audit `canary.py` for exact option propagation, target-PID uniqueness,
   checkpoint completeness/races, final-versus-forced output selection,
   immutable retention and resource/watchdog behavior. Re-run the focused
   suite. Do not initialize ADflow.
7. Return one severity-ranked JSON review. It must include `decision.verdict`,
   `decision.bound_artifact`, plus `resource_decision.verdict`,
   `bound_artifact`, `bound_solver_change`, `bound_resource_policy`,
   `bound_output_controls` and `bound_checkpoint_policy`. Use
   `GO_DESKTOP_RECOVERY_CANARY` only if there is no unresolved HIGH finding;
   otherwise use `NO_GO_DESKTOP_RECOVERY_CANARY` and prescribe exact fixes.
8. Do not edit governed files and do not run CFD. End with
   `cfd_authorized: false`; only Codex may convert a GO into a separate
   immutable policy and fresh one-shot authorization.

## Required output from the continuation analysis

Return a severity-ranked report answering:

1. Which solver mechanism most likely caused the near-unit NK linear residual,
   and what local source evidence supports that conclusion?
2. Is ANK-only the lowest-memory option most likely to clear density and energy
   below `1e-5`, without changing equations or turbulence physics?
3. Is the 8.317 GiB phase anchor defensible, does 9.2 GiB fit the immutable
   resource arithmetic, and what uncertainty remains for checkpoint writes?
4. Is every completed checkpoint valid, durable, versioned and restartable
   after an abrupt WSL shutdown?
5. Does one geometry-independent redistribution fix every known y+ hotspot
   without changing cells, wall, farfield or interfaces?
6. Are all residuals/logs/output fields retained, and which acceptance checks
   remain deliberately unproven?

Separate measured facts, source-backed behavior, engineering estimates and
untested hypotheses. No review may authorize CFD by itself.

## Gate for any future heavy action

A future CFD or ADflow initialization requires all of the following:

1. new immutable policy and unique attempt ID;
2. corrected resource model and safe live preflight;
3. one isolated numerical or mesh change with source-backed rationale;
4. restart/output retention policy;
5. independent review with no unresolved HIGH finding;
6. green identity/environment/one-shot tests;
7. fresh one-shot token consumed before launch; and
8. explicit human authorization after reviewing the exact proposal.

Until then, `cfd_authorized: false`.

There is deliberately no execute command or reusable token in this handoff.
