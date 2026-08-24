# Joint validation programme for S6 and S7

One programme covering both meshing strategies, run as a paired comparison: the
same geometries, the same operating condition, the same acceptance gates, so any
difference in the results is a difference between the pipelines and not between
the experiments.

It supersedes nothing.  S6's `ROADMAP.md` already carries a reduced gate for a
100-case campaign and S7's carries its own ordering; this states the shared
sequence they both feed, and where the two differ in how far they still are from
it.

## Decisions to take before Stage 0, not during

These are cheap now and expensive to retrofit, because changing any of them
invalidates every result recorded before the change.

- **Operating condition.**  One condition, fixed for Stages 0 to 3.  Record
  altitude, velocity, angle of attack, reference temperature and the resulting
  Reynolds and Mach numbers in the policy, not in a script.
- **Moment reference point.**  Cm is meaningless without it and cannot be
  compared across designs unless the convention is fixed.  Declare the point and
  whether it moves with the geometry (for example, quarter-MAC) or is absolute.
- **Reference area and length.**  Both pipelines must use the same definitions or
  their coefficients are not comparable.  S7's surface report already records
  `area_m2`, `area_yz_m2`, `mean_aerodynamic_chord_m` and both span conventions;
  pick which of them is the reference and say so once.
- **The resolution ladder.**  Name the coarse, medium and fine levels explicitly.
  Stage 1 must run at the *same* coarse level that Stage 2 will use as its coarse
  leg, or the runs cannot be reused and Stage 2 costs 30 runs instead of 20.

## Stage 0 - one accepted CFD case per pipeline

The gate is the same for both: a production-resolution mesh, a converged solve,
and wall y+ inside the frozen limits, with nothing repaired by hand.

The two pipelines are **not** equally close to it.

- **S7** has five production-resolution meshes and a verified solver chain, and
  y+ passes at coarse (p95 0.5573, max 0.8744).  What is missing is convergence:
  the residual limit-cycles at 1.658 orders against a six-order gate while the
  forces settle.  Multigrid reached 3.250 orders and tightened the CD spread by a
  factor of 770; confirming it is the whole of S7's Stage 0.
- **S6** has 100/100 at *development* resolution and **zero production-resolution
  meshes**.  Its Stage 0 therefore starts one step earlier: produce production
  meshes, then run ADflow.  This is the larger of the two gaps and should start
  first because it is longer, not because it is harder.

Do not begin Stage 1 on a pipeline until its Stage 0 case is accepted.  Twenty
runs against an unresolved defect produce twenty instances of the same defect.

**Budget the programme only after Stage 0.**  Cost per CFD is currently unknown
for both pipelines, so any total run count quoted now is a guess.  One converged
case gives the wall time, the memory ceiling and the retry rate that make the rest
of the estimate real.

## Stage 1 - twenty-case geometric generalisation, per pipeline

Fixed condition, varying geometry.  The question is narrow and worth keeping
narrow: *does the automation handle very different BWB geometries without
intervention?*

Twenty geometries, chosen rather than drawn at random:

- five geometric extremes, taken from the corners of the sampled ranges;
- ten maximin-spread designs covering the interior;
- five drawn at random and never inspected beforehand.

The same twenty for both pipelines.  Record per case: geometry id, planform
(twist, dihedral, sweep - now in S7's surface report), mesh outcome and quality,
attempts and failures, convergence history, y+, CL, CD, Cm, wall time and peak
memory.

Target: 20/20 meshes accepted, at least 19/20 converged unattended, y+ passing,
zero invalid cells, no manual repair.

**Wording, for the eventual paper.**  Twenty cases are development evidence of
robustness.  They do not prove generalisation over the design space, and the text
should not say they do.

### What Stage 1 cannot cover

Root dihedral is pinned to zero by the `enforce_flat_root_panel` invariant, so no
case at any stage exercises a non-flat root panel.  State this as a scope limit
rather than discovering it in review.

## Stage 2 - mesh independence on five geometries

Five of the twenty, chosen for difficulty and spread rather than convenience: the
nominal design, two opposing geometric extremes, the hardest case to mesh in Stage
1, and one representative high-loading design.

Each at coarse, medium and fine.  If the level pinning above held, the coarse legs
already exist and this costs ten new runs per pipeline rather than fifteen.

Report Richardson extrapolation and GCI on CL, CD and Cm, with the observed order
of convergence stated - not assumed to be the formal order.  Where the observed
order is far from formal, say so; that is a finding about the discretisation, not
an inconvenience to be smoothed over.

## Stage 3 - fix the production configuration

This is the stage the preregistration exists to protect, because it is where
settings are chosen *after* seeing results.

Permitted: efficiency and robustness changes - resolution where Stage 2 shows it
is unnecessary, solver settings, retry logic, wall spacing chosen to hit the
existing y+ limit.

Not permitted: moving an acceptance threshold so that a case which failed now
passes.  If a gate is genuinely wrong, it is re-derived in a superseding ADR that
carries the measurement showing the old value was mis-derived, and the ADR is
written before the re-run, not after.  `POLICY.yaml` carries
`no_gate_weakening: true` for exactly this.

Then about five dress-rehearsal runs per pipeline under the final settings.

## Stage 4 - freeze

Freeze together, and record the hashes: geometry definitions, mesh settings, wall
spacing, refinement, solver, turbulence model, convergence criteria, retry logic,
quality gates and the output schema.

Only then the hold-out.  `round_c_lhs10_seed42` has never been constructed,
meshed, solved or inspected, and must stay that way until the freeze is recorded.
A hold-out looked at early is not a hold-out.

## Stage 5 - the paired production campaign

At least 100 CFD per pipeline, the same geometries and condition for both, giving
a paired table where each row is one geometry under both strategies.

The comparison is the point, and it is more interesting than the aerodynamics
alone: where structured and unstructured disagree and by how much, cost per case,
unattended success rate, convergence robustness, mesh quality, and which regions
of the design space are hard for which pipeline and why.

Operating conditions may expand here.  Not before - varying angle of attack during
Stage 1 turns a twenty-case test into a hundred-case one and answers a question
nobody asked yet.

# Desktop execution - step by step

This section is written to be handed to a fresh Claude Code session on the
desktop.  It assumes nothing from any earlier conversation.

## Step 1 - get the code

    cd /path/to/v.0.1_Project
    git checkout main
    git pull

Everything is on `main`.  There are no other branches to worry about.

## Step 2 - open Claude Code and paste this as the first message

    Read AERIS_MESH_STUDY/04_strategy_studies/VALIDATION_PROGRAMME.md and
    AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/HANDOFF.md,
    follow the HANDOFF reload order, then execute the S7 Stage 0 work in
    RUNBOOK.md. I am on the desktop, heavy runs are allowed here.
    Report progress with run_report.py and push it.

## Step 3 - check the machine before running anything

    free -g
    df -h .
    nproc

S7 needs roughly **3 GB per MPI rank**, because every rank reads the whole mesh
before partitioning.  The rule is `workers x ranks x 3 GB` must fit in RAM with
headroom.  Eight ranks were OOM-killed on a 16 GiB machine; two were stable.  On
32 GiB use no more than six ranks total.  If `free -g` shows less than 8 GiB
available, the campaign will refuse to start - that is the floor working, not a
bug, and it must not be lowered.

## Step 4 - S7 Stage 0, the multigrid confirmation

This is the single blocker on every S7 accuracy claim.  Full detail is in
`S7_unstructured_gmsh_su2/RUNBOOK.md` under "Confirm multigrid".

    export PATH="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin:$PATH"
    export SU2_RUN="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin"
    .venv/bin/python \
      AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/convergence_matrix.py \
      /path/to/coarse_mesh.su2  6000  2  3  round-two

Arguments in order: mesh, iterations, ranks per variant, concurrent variants, and
any fifth argument to select the three multigrid variants instead of all six.

If `AERIS_MESH_STUDY/tools/su2_8.5.0` is missing on the desktop, SU2 8.5.0 is a
gitignored download rather than lost work; re-fetch the pinned release before
running.

Two outcomes, both decisive.  If a variant reaches six orders, adopt it in a
superseding ADR carrying the measurements.  If none does while CD stays flat, the
residual gate was mis-derived and is re-derived - in an ADR, before the re-run.
Neither outcome is "lower the gate until it passes".

## Step 5 - report progress and push it back

Run this at any time, including while a campaign is still going.  It reports
whatever has landed so far.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/run_report.py \
      <artifacts_root> --name s7_stage0_multigrid --push

It writes a small Markdown and JSON pair into
`AERIS_MESH_STUDY/04_strategy_studies/RUN_LOG/` and, with `--push`, commits and
pushes **only those two files**.  It never touches the artifacts and never
commits mesh data.

This exists because the artifact trees are large and get wiped between campaigns.
A run recorded only there is a run nobody can evaluate later.

Then, back on the laptop:

    git pull

and the reports are there to read.

## Step 6 - what to run after Stage 0 passes

In order, and not before Stage 0 is accepted:

1. the remaining 95 coarse meshes - about 16 hours sequential, four hours split
   four ways, see `RUNBOOK.md`;
2. a converged coarse CFD case, which is what actually earns
   `production_y_plus_passed`;
3. S6 production-resolution meshes, which is S6's Stage 0 and the longer of the
   two gaps;
4. Stage 1, the twenty-case generalisation test, once **both** pipelines have one
   accepted case.

## Rules that hold regardless of what the session decides

- The hold-out `round_c_lhs10_seed42` is forbidden: never constructed, meshed,
  solved, inspected, or worked around.  It stays untouched until the Stage 4
  freeze is recorded.
- No acceptance threshold moves to rescue a failing case.  `POLICY.yaml` carries
  `no_gate_weakening: true`.  A gate that is genuinely wrong is re-derived in a
  superseding ADR that states the measurement showing the old value was wrong,
  written before the re-run.
- Everything lives under the project tree.  Nothing in `/tmp`, nothing in a
  scratchpad.
- Findings go in tracked files, because `data/` and the artifact trees are wiped.
- Relocate3D must never be used as a Gmsh optimiser; it corrupts the boundary
  layer.  `HANDOFF.md` carries the rest of these invariants.


## Sequence

    Stage 0   one accepted CFD each      S6 needs production meshes first
    Stage 1   20 + 20, fixed condition   geometric generalisation
    Stage 2   5 geometries x 3 levels    mesh independence
    Stage 3   settings fixed + ~5 each   superseding ADR for any gate change
    Stage 4   freeze, then hold-out      hashes recorded
    Stage 5   100 + 100, paired          comparison campaign

Run counts beyond Stage 1 are provisional until Stage 0 supplies a measured cost
per case.
