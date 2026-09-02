# AERIS mesh-paper roadmap

**Date:** 2026-08-31
**Status:** research decision record
**Scope:** structured S6 automation, unstructured S7 automation, matched validation,
and AI-assisted meshing papers

## Executive decision

If S7 succeeds completely, it strengthens the publication portfolio but changes
the scientific framing. AERIS should no longer claim that AI is required merely
to make BWB meshing robust. Instead, the thesis-level question becomes:

> Two independently automated mesh pipelines exist. Which is more reliable,
> efficient, and numerically trustworthy across the declared BWB design family,
> and can AI select or improve them without controlling acceptance?

The recommended publication order is:

1. finish the S6 fail-closed structured CFD-factory paper;
2. complete and judge the fast learned S6 routing-and-stopping paper;
3. qualify S7 through production-resolution CFD and grid convergence;
4. publish a paired S6/S7 pipeline comparison if both routes pass;
5. attempt direct neural mesh construction only against the resulting strong
   deterministic baselines;
6. pursue cross-family AI selection only if the paired evidence demonstrates a
   nontrivial choice between the routes.

S7 should not delay the S6 paper. A standalone S7 automation paper is not a high
priority unless it produces a reusable algorithmic contribution beyond scripting
Gmsh and SU2.

## Evidence boundary at this decision

### S6 structured route

- The final production-resolution written-CGNS development audit passed 100/100.
- It required 162 attempts, with 74 first-attempt completions.
- The qualified atlas contains 21 templates.
- The worst accepted scaled quality is 0.146811 and no selected cell is below
  the hard 0.10 floor.
- Production y+, grid convergence, CFD reliability, and the locked holdout remain
  open.

### S7 hybrid unstructured route

- The surface pipeline passed 60/60 development cases.
- The volume pipeline passed 100/100 development cases in 101 attempts.
- Five production-resolution coarse meshes passed on the first candidate.
- One coarse y+ diagnostic passed: p95 0.5573 and maximum 0.8744.
- Newton-Krylov is the leading production-resolution convergence candidate, but
  it has not yet been confirmed through an accepted converged coarse case.
- Production-resolution CFD convergence, five grid studies, TE sensitivity,
  geometric-fidelity sensitivity, independent review, and the holdout remain
  open.

Therefore S7 has strong mesh evidence but is not yet a qualified CFD data
pipeline.

## Portfolio assessment

| Priority | Candidate paper | Practicality | Novelty | Standalone verdict |
|---:|---|---|---|---|
| 1 | S6 fail-closed structured CFD factory | Medium | Medium-high | Yes |
| 2 | Learned S6 routing and stopping | High | Medium | Conditional yes |
| 3 | Matched S6/S7 structured-hybrid comparison | Medium-low | High | Yes; strongest follow-up |
| 4 | Direct neural node redistribution | Medium | High | Conditional |
| 5 | S7 automation alone | Medium | Low-medium | Usually merge or software paper |
| 6 | AI selection between S6 and S7 | Low until paired data exist | Potentially high | Conditional on a real crossover |

## Paper 1 -- deterministic S6 foundation

### Working title

**A Fail-Closed, Resource-Constrained Automated RANS Data Factory for Parametric
Blended-Wing-Body UAV Design**

### Scientific question

Can a fixed-semantics BWB geometry family be converted into accepted structured
meshes and verified RANS cases without manual repair, while every geometry, mesh,
solver, and provenance failure is detected mechanically?

### Required contribution

- fixed pyGeo BWB family and fixed multiblock surface graph;
- structured template atlas and bounded volume deformation;
- exact written-mesh and CFD acceptance gates;
- qualified wall, TE, farfield, and grid policies;
- unattended recovery with immutable provenance;
- development, prospective holdout, cost, and failure evidence.

### Go gate

- accepted production-resolution y+;
- accepted CFD on the declared development campaign;
- five or more representative grid studies meeting the frozen uncertainty rule;
- frozen TE, farfield, solver, fallback, and acceptance policies;
- untouched holdout run after the freeze.

### Challenge

S7 must not expand this manuscript into an uncontrolled dual-pipeline paper. S6
already has a complete and distinct research question. S7 is future comparison
infrastructure.

### Verdict

**Definite paper and PhD backbone.**

## Paper 2 -- fast AI companion

### Working title

**Quality-Constrained Learned Routing and Optimal Stopping for Fail-Closed
Structured-Mesh Generation of Parametric BWB UAVs**

### Correct framing

This paper is about routing cost, stopping, and tail risk. It must not claim that
AI makes the design family meshable or that AI is required for robustness.

The existing result reduces the S6 campaign from 162 to 114 counterfactual
attempts and the worst route from 21 to 4, with approximately 0.30% accepted-
quality regret. The current evidence is still restricted by the incomplete
geometry-template matrix.

### Minimum publishable experiment

1. Complete the 100 by 21 S6 outcome matrix.
2. Freeze the objective before rerunning:

   - minimize expected wall time and CVaR95 attempt count;
   - require 100% observed completion;
   - require every accepted mesh to clear the existing 0.10 floor;
   - limit mean accepted-quality regret to at most 0.5%;
   - never change an acceptance threshold in response to the result.

3. Compare against:

   - the actual nearest-template baseline;
   - accept-first-valid;
   - stop after k non-improving attempts;
   - a fixed quality-margin stopping rule;
   - a historical-ceiling heuristic;
   - random routing;
   - an oracle lower bound.

4. Run a separately registered prospective holdout of 50-100 new geometries.
   Do not consume the protected S6 holdout.
5. Report geometry-level bootstrap uncertainty, wall time, attempt count, tail
   risk, accepted quality, and all failure states.

### Role of S7

At first, S7 should be a deterministic terminal fallback only:

```text
learned S6 ordering
-> deterministic S6 acceptance gates
-> direct S7 only if S6 exhausts its accepted routes
-> human escalation if both fail
```

Do not add a learned S6-versus-S7 selector until paired data demonstrate that the
choice is nontrivial.

### Go/no-go

- **Go as a separate paper:** at least 15% wall-time improvement relative to
  tuned deterministic heuristics at no more than 0.5% quality regret, confirmed
  prospectively.
- **Merge into Paper 1:** a tuned deterministic stopping rule matches the learned
  method within uncertainty.

### Verdict

**Fastest additional paper, but conditional on defeating honest heuristic
baselines.**

## Paper 3 -- matched S6/S7 comparison

### Working title

**A Paired Evaluation of Structured Hexahedral and Hybrid Prism-Tetrahedral
Automation for Parametric BWB RANS Campaigns**

### Why S7 creates this opportunity

The valuable result is not that Gmsh can create a hybrid mesh. Automated
prism-tetrahedral aircraft meshing already exists. The contribution is a paired,
design-family-wide comparison in which both pipelines are fail-closed and every
failure remains part of the evidence.

### Research questions

1. Which pipeline has the higher unattended acceptance rate across the same BWB
   geometries?
2. What are the distributions of time, memory, retries, and failure mechanisms?
3. At controlled numerical uncertainty, do the two pipelines agree on CL, CD,
   and Cm?
4. Where in the design space does either route become expensive or fragile?
5. Does an inexpensive deterministic fallback policy capture most of the value
   of maintaining two routes?

### Required design

- the same half-domain geometry definition;
- the same operating point;
- identical reference area, length, and moment origin;
- 100 production-resolution mesh-only cases per route;
- the same 20 geometries solved by both routes;
- five paired coarse/medium/fine studies per route;
- a frozen holdout after both methods are fixed;
- total time to an accepted result, not meshing time alone;
- full failure, retry, y+, convergence, force, memory, and uncertainty records.

### Critical confound

The current paths are:

```text
S6 mesh -> ADflow
S7 mesh -> SU2
```

Consequently, differences in convergence, forces, and runtime cannot be assigned
causally to structured versus unstructured meshing. The strongest study would
run both mesh families through the same solver. If that is not technically
possible, the manuscript must explicitly compare complete pipelines rather than
claim to isolate mesh topology.

Cell-count matching alone is also insufficient. The comparison must use each
route's grid-converged error or combined numerical uncertainty.

### Go/no-go

- **Go:** both routes pass Stage 0; at least 19 of 20 matched CFD cases converge
  unattended; both have credible grid studies; and a measurable robustness,
  cost, or accuracy trade exists.
- **No-go as a comparison paper:** S7 cannot converge at coarse resolution, the
  evidence remains solver-confounded without honest pipeline wording, or one
  route dominates every relevant metric.

### Verdict

**Potentially the strongest mesh follow-up, but not a fast paper.**

## S7 automation as a standalone paper

### Candidate title

**A Fail-Closed Hybrid Prism-Tetrahedral Mesh Factory for Parametric BWB UAV
RANS**

### Challenge

Gmsh scripting, prism-layer construction, tetrahedral filling, and SU2 automation
are not individually novel. A 100/100 mesh result is valuable evidence but is
primarily an engineering achievement unless it is connected to downstream CFD
accuracy, grid convergence, and a reusable methodological contribution.

The strongest S7-specific technical findings are:

- independent auditing of both Gmsh and native SU2 files;
- isoparametric rather than decomposition-dependent prism validity;
- protected prism schedules with core-only optimization and rollback;
- tier-aware unstructured quality distributions;
- exact wall-point y+ coverage and fail-closed solver recovery;
- measured and recorded negative results during solver diagnosis.

These are excellent content for Paper 3, but may not carry a separate major paper
without broader algorithmic novelty.

### Verdict

- **Preferred:** include S7 as the second method in Paper 3.
- **Fallback:** publish a reproducible software paper if the implementation is
  openly released with examples and tests.
- **Avoid:** use a major PhD paper slot merely to report that Gmsh and SU2 were
  scripted successfully.

## Paper 4 -- direct AI mesh construction

### Working title

**Extrusion-Aware Monotone Neural Node Redistribution for CAD-Conforming
Structured BWB Meshes**

### Effect of S7 success

If both S6 and S7 are deterministically robust, an AI generator cannot justify
itself through robustness alone. It must demonstrate one or more of:

- higher volume quality at the same cell budget;
- lower total time to an independently audited mesh;
- fewer required stored templates;
- better CFD accuracy per cell;
- success outside both deterministic methods' reliable envelope.

### Defensible method

- predict low-dimensional monotone spline/log-spacing coefficients, not raw XYZ
  coordinates;
- use positive increments and cumulative sums for ordered curve parameters;
- tie every shared interface distribution;
- place nodes through deterministic pyGeo/curve evaluation;
- use differentiable surface metrics only for pretraining;
- use true pyHyp and written-volume outcomes for volume-aware calibration;
- retain the existing independent audit as the only acceptance authority.

The model guarantees ordered parameters along a curve. It does not guarantee an
untangled global surface or valid volume; those remain measured hard gates.

### Go/no-go

- **Go:** at least 90% one-shot accepted volumes on an untouched test set, zero
  accepted inversions, no fidelity/interface regression, non-inferior accepted
  quality, and a material improvement over the best globally tuned analytic
  distribution.
- **Stop:** only surface metrics improve, or deterministic per-geometry
  optimization matches the neural model at acceptable cost.

### Verdict

**Higher novelty but lower priority after S7; it must beat two strong
deterministic baselines.**

## Conditional cross-family AI paper

### Possible title

**Risk-Aware Mesh-Method Selection for Automated Parametric CFD Campaigns**

### Proposed action space

```text
S6 template 2
S6 template 42
...
S6 template 95
direct S7
human escalation
```

### Necessary scientific condition

Both routes must occupy meaningful parts of the cost-accuracy-robustness Pareto
frontier. A learned selector is unnecessary if one route dominates.

### Go/no-go

- **Go:** at least roughly 10% of matched cases genuinely favor each family, or
  the routes show complementary failures; the crossover is predictable on an
  untouched geometry-grouped test; and the model beats the simple S6-first/S7-
  fallback rule.
- **No-go:** S6 always succeeds more cheaply, S7 always wins, or the apparent
  crossover disappears after grid uncertainty and solver differences are
  controlled.

### Verdict

**Do not schedule this paper yet. Let the paired campaign decide whether the
research question exists.**

## Decision tree

```text
Finish S6 gates
|
+-- S6 fails irreparably
|   `-- S7 becomes the primary deterministic pipeline; rewrite Paper 1 scope
|
`-- S6 passes
    |
    +-- learned routing beats tuned heuristics prospectively
    |   `-- publish Paper 2
    |
    `-- learned routing does not beat them
        `-- retain it as an ablation in Paper 1

Finish S7 coarse Newton-Krylov and CFD gates
|
+-- S7 fails production CFD
|   `-- retain S7 as mesh research/fallback; no comparison paper
|
`-- S7 passes
    |
    +-- matched study reveals a real trade
    |   `-- publish Paper 3
    |
    `-- one route dominates
        `-- use the dominant route; report the other as negative evidence

After both baselines are frozen
|
+-- neural mesh construction beats both on volume/CFD endpoints
|   `-- publish Paper 4
|
`-- only proxy surface metrics improve
    `-- stop; do not manufacture a paper
```

## Immediate execution order

1. Do not change the protected S6 or S7 holdouts.
2. Continue S6 production mesh, y+, TE, grid, and CFD qualification.
3. In parallel, complete the S6 100 by 21 mesh-outcome matrix.
4. Run the S7 coarse Newton-Krylov shortlist and adopt a winner only through the
   governed decision record.
5. Complete the S7 production-resolution mesh sweep and one accepted coarse CFD
   case.
6. Measure per-case CFD cost before approving the 20-case paired campaign.
7. Freeze the Paper 2 model and heuristics before its prospective holdout.
8. Begin the paired comparison only after both pipelines pass their Stage 0
   case.

## Final portfolio rule

Implementation effort does not automatically earn a paper. A mesh-related study
gets a separate manuscript only when it answers a distinct falsifiable question,
has a baseline capable of defeating it, and is judged on accepted volume/CFD
outcomes rather than attractive mesh images or proxy metrics.
