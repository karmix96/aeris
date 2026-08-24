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

## Sequence

    Stage 0   one accepted CFD each      S6 needs production meshes first
    Stage 1   20 + 20, fixed condition   geometric generalisation
    Stage 2   5 geometries x 3 levels    mesh independence
    Stage 3   settings fixed + ~5 each   superseding ADR for any gate change
    Stage 4   freeze, then hold-out      hashes recorded
    Stage 5   100 + 100, paired          comparison campaign

Run counts beyond Stage 1 are provisional until Stage 0 supplies a measured cost
per case.
