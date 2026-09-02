# Learned routing and stopping for automated structured-mesh generation over a parametric BWB family

**Status:** draft, numbers generated from `AERIS_MESH_AGENT/experiments/`.
**Data:** AERIS S6 bounded mesh atlas, development set `lhs100_seed42` (ADR-0011).
**Hold-out:** `round_c_lhs10_seed42` is untouched and must remain so until freeze.

---

## Abstract

Automated CFD dataset generation for aircraft design is throttled less by the
solver than by the mesher: before a geometry can be simulated, some meshing
recipe must be found that produces a valid, good-enough grid for *that*
particular shape. Published datasets report the geometries that meshed; the
attempts that failed, and the cost of finding the ones that worked, are usually
discarded. We take the complete attempt ledger of an automated structured-meshing
system for a blended-wing-body family — every attempt, its outcome, its quality
and its wall-clock — and treat mesh generation as a sequential decision problem.
Three results follow. First, the recorded failures are not one mode but three,
with different costs and different remedies. Second, a large share of the cost is
not failure recovery at all but an unbounded search for quality with no stopping
rule: in the worst case a geometry consumed 21 attempts and then accepted the
result of its first. Third, a gradient-boosted model trained only on design
variables, evaluated out-of-fold with each geometry held out, reorders the
candidate templates and supplies a stopping rule that reaches meshes of
statistically indistinguishable quality — within 0.3 % of the incumbent's mean
accepted quality — for 30 % fewer attempts. We separate how much of that saving is machine
learning and how much is simply the absence of a stopping rule in the incumbent —
a stopping rule alone, with no model, recovers two thirds of it — and we report
the saving in wall-clock as well as attempts, where it is smaller, because the
attempts a good policy avoids are disproportionately the cheap failures. We state
precisely which claim the current data cannot yet support.

---

## 1. Why meshing, and why now

A geometry-generalising aerodynamic surrogate needs hundreds to thousands of
converged high-fidelity solutions across a design space. The literature on
learned physics surrogates treats the dataset as given. In practice, generating
it means meshing every geometry in an automated, unattended way, and that is
where campaigns actually stall: a mesher that works on the geometry its author
tuned it for does not necessarily work on the next one.

The system studied here is a *bounded atlas*: a set of reference structured
meshes (templates), each of which can be deformed onto a nearby target geometry
and then extruded to a volume. Routing a new geometry means choosing a template.
The incumbent policy chooses by proximity in normalised design space — it sorts
candidates by distance and works down the list — and accepts a result when its
minimum scaled quality clears a preferred threshold, falling back at the end to
the best result above a production floor.

That policy is reasonable, and it is what we compare against. It is not a straw
man: proximity routing already resolves three quarters of the geometries in one
attempt.

## 2. The observational dataset

Every attempt the atlas has ever made is recorded with an immutable identity: the
target geometry, the template, the resulting state, the minimum scaled quality,
inverted-cell count, minimum volume, deformation distance, wall and interface
errors, surface fidelity and elapsed time.

Pooling only campaigns that share one meshing configuration
(`eps_e = 1.5`, first-cell fraction 3.6e-6, 257 normal points, production volume
level) gives **384 attempts** over **100 geometries** and **21 templates**,
covering **247** unique (geometry, template) cells — **11.8 %** of the 2,100-cell
matrix.

**Determinism check.** Cells measured independently by more than one campaign
disagree in **0** cases. The pipeline reproduces itself exactly, which is what
makes the ledger usable as ground truth at all.

## 3. What the ledger shows

### 3.1 The single recorded FAIL state hides three different events

| Outcome | Cells | Share | Mean cost | Meaning |
|---|---:|---:|---:|---|
| `PASS` | 139 | 56.3 % | 20.0 s | valid volume at or above the floor |
| `FAIL_FOLDED` | 49 | 19.8 % | 11.2 s | negative cell volumes; the march folded |
| `FAIL_LOW_QUALITY` | 38 | 15.4 % | 9.4 s | perfectly valid, simply not good enough |
| `SURFACE_BUILD_ERROR` | 21 | 8.5 % | ≈ 0 s | no surface was built; extrusion never started |

These demand different responses. A folded march is a marching-parameter or
template-fit problem; an under-quality mesh is a routing problem; a surface build
error happens before any of that and costs nothing, so it should be screened, not
recovered from. Collapsing them into one `FAIL` label — as the raw records do —
makes the problem look harder and less structured than it is.

The cost column is why the paper reports wall-clock as well as attempt counts.
Failing fast is not the same as failing.

### 3.2 The cost is a tail, not an average

In the headline production campaign, 100 geometries took **162 attempts**: 74 in
one, then 15, 6, 2, 1, 1 — and one geometry taking **21**.

![Retry tail](../figures/fig1_retry_tail.png)

### 3.3 The decisive case: a stopping-rule failure, not a meshing failure

Geometry 95 (`lhs100_seed42_095`) is itself one of the 21 atlas templates, so its
first attempt is an identity deformation. That attempt scored 0.1468 — **the best
of all twenty-one attempts it went on to make**. Because 0.1468 falls 0.003 short
of the 0.15 preference, and because nothing in the loop can say "0.1468 is this
geometry's ceiling", the campaign scanned the entire atlas and then accepted its
own first result.

![Worst case](../figures/fig2_worst_case.png)

Across the campaign, **35 of the 162 attempts were made after a PASS already
existed**. That is not failure recovery. It is an unbounded search for quality
with no stopping rule, and it is the single largest addressable cost.

### 3.4 Most of the matrix has never been measured

![Coverage](../figures/fig3_coverage.png)

The incumbent policy stops as soon as it is satisfied, so the cells it measured
are exactly the ones it chose to try. Any evaluation on this data is therefore
restricted to those cells — see §6 and the completion campaign in
`runbook/RUNBOOK_matrix_completion.md`.

## 4. Predicting an attempt before making it

**Features.** Two sets, deliberately separated by what they cost:

- *design only* (free, known before anything is built): the 20 sampled design
  variables of target and template, their differences, and normalised
  design-space distances — 63 features.
- *design + surface* (requires geometry realisation and the bounded surface
  deformation, but not extrusion): adds realised planform metrics, their ratios
  to the template's, and the recorded deformation `distance_rms` — 86 features.

**Models.** Gradient-boosted trees: a four-class classifier over the outcomes,
and a regressor for minimum scaled quality fitted only where a volume was
actually written, since a surface-build error has no quality to impute.

**Validation.** Grouped out-of-fold with the *target geometry* as the group, so
no geometry ever informs its own prediction. This is the only split that answers
the question the paper asks — an aircraft the atlas has never seen.

| Feature set | Features | Balanced accuracy | Macro F1 | PASS AUC | Quality MAE | Quality Spearman |
|---|---:|---:|---:|---:|---:|---:|
| design only | 63 | 0.631 | 0.640 | 0.891 | 0.075 | 0.756 |
| design + surface | 86 | 0.601 | 0.598 | 0.894 | 0.062 | 0.843 |

Chance is 0.25 balanced accuracy over four classes; an uninformed ranker has AUC
0.5 and Spearman 0.

![Quality prediction](../figures/fig5_quality_prediction.png)

**Reading it.** Feasibility is predictable from the design vector alone — adding
the surface build barely moves PASS AUC (0.891 → 0.894). What the surface build
buys is *ranking precision* on quality (Spearman 0.756 → 0.843). Whether that is
worth its cost is answered not here but by the policy it produces (§5).

## 5. Policies

All policies are measured by counterfactual replay of the recorded campaign.

- **atlas (as run)** — the incumbent: proximity ordering, accept at 0.15, fall
  back to best above 0.10.
- **atlas ordering + accept-first-valid** — *ablation with no model at all*:
  keep the incumbent's ordering, and simply stop at the first mesh that clears
  the floor. This exists to prevent crediting machine learning with a saving that
  comes from adding any stopping rule whatsoever.
- **learned ranking** — order candidates by predicted score, which is expected
  quality discounted by the probability that no surface builds.
- **learned ranking + accept-first-valid**
- **learned ranking + ceiling stopping** — stop when no remaining candidate is
  predicted to beat what is already held. This is the rule geometry 95 needed.
- **oracle** — perfect foresight, one attempt. The lower bound.

![Policy comparison](../figures/fig4_policy_comparison.png)

### All 100 geometries

| policy                                                |   geometries |   total_attempts |   total_seconds |   mean_attempts |   max_attempts |   success_rate |   first_attempt_success |   mean_accepted_quality |   reached_preferred_rate |
|:------------------------------------------------------|-------------:|-----------------:|----------------:|----------------:|---------------:|---------------:|------------------------:|------------------------:|-------------------------:|
| atlas (as run)                                        |          100 |              162 |         2859.51 |            1.62 |             21 |              1 |                    0.74 |                  0.2118 |                     0.99 |
| atlas ordering + accept-first-valid                   |          100 |              127 |         2356.53 |            1.27 |              5 |              1 |                    0.83 |                  0.2059 |                     0.89 |
| learned ranking (design only)                         |          100 |              133 |         2508.05 |            1.33 |             21 |              1 |                    0.89 |                  0.2118 |                     0.99 |
| learned ranking + accept-first-valid (design only)    |          100 |              109 |         2198.52 |            1.09 |              3 |              1 |                    0.93 |                  0.2101 |                     0.96 |
| learned ranking + ceiling stopping (design only)      |          100 |              114 |         2262.67 |            1.14 |              4 |              1 |                    0.9  |                  0.2112 |                     0.97 |
| learned ranking (design+surface)                      |          100 |              137 |         2575.03 |            1.37 |             21 |              1 |                    0.88 |                  0.2118 |                     0.99 |
| learned ranking + accept-first-valid (design+surface) |          100 |              109 |         2203.21 |            1.09 |              3 |              1 |                    0.94 |                  0.209  |                     0.94 |
| learned ranking + ceiling stopping (design+surface)   |          100 |              117 |         2339.24 |            1.17 |              5 |              1 |                    0.89 |                  0.2112 |                     0.97 |
| oracle (upper bound)                                  |          100 |              100 |         2150.52 |            1    |              1 |              1 |                    1    |                  0.2118 |                     0.99 |

### The 26 geometries the atlas could not do in one attempt

The other 74 cost exactly one attempt for every policy, so they dilute the comparison without informing it.

| policy                                                |   geometries |   total_attempts |   mean_attempts |   max_attempts |   mean_quality |
|:------------------------------------------------------|-------------:|-----------------:|----------------:|---------------:|---------------:|
| atlas (as run)                                        |           26 |               88 |          3.3846 |             21 |         0.1996 |
| atlas ordering + accept-first-valid                   |           26 |               53 |          2.0385 |              5 |         0.1769 |
| learned ranking (design only)                         |           26 |               59 |          2.2692 |             21 |         0.1996 |
| learned ranking (design+surface)                      |           26 |               63 |          2.4231 |             21 |         0.1996 |
| learned ranking + accept-first-valid (design only)    |           26 |               35 |          1.3462 |              3 |         0.193  |
| learned ranking + accept-first-valid (design+surface) |           26 |               35 |          1.3462 |              3 |         0.1888 |
| learned ranking + ceiling stopping (design only)      |           26 |               40 |          1.5385 |              4 |         0.1971 |
| learned ranking + ceiling stopping (design+surface)   |           26 |               43 |          1.6538 |              5 |         0.1972 |
| oracle (upper bound)                                  |           26 |               26 |          1      |              1 |         0.1996 |

### The trade the stopping rule makes

| policy                                                |   total_attempts |   attempts_saved_pct |   hours |   mean_accepted_quality |   quality_loss_pct |   reached_preferred_rate |
|:------------------------------------------------------|-----------------:|---------------------:|--------:|------------------------:|-------------------:|-------------------------:|
| atlas (as run)                                        |              162 |                0     |   0.794 |                   0.212 |              0     |                     0.99 |
| atlas ordering + accept-first-valid                   |              127 |               21.605 |   0.655 |                   0.206 |              2.791 |                     0.89 |
| learned ranking (design only)                         |              133 |               17.901 |   0.697 |                   0.212 |              0     |                     0.99 |
| learned ranking + accept-first-valid (design only)    |              109 |               32.716 |   0.611 |                   0.21  |              0.808 |                     0.96 |
| learned ranking + ceiling stopping (design only)      |              114 |               29.63  |   0.629 |                   0.211 |              0.303 |                     0.97 |
| learned ranking (design+surface)                      |              137 |               15.432 |   0.715 |                   0.212 |              0     |                     0.99 |
| learned ranking + accept-first-valid (design+surface) |              109 |               32.716 |   0.612 |                   0.209 |              1.332 |                     0.94 |
| learned ranking + ceiling stopping (design+surface)   |              117 |               27.778 |   0.65  |                   0.211 |              0.298 |                     0.97 |
| oracle (upper bound)                                  |              100 |               38.272 |   0.597 |                   0.212 |              0     |                     0.99 |

**Headline (quality-preserving).** Atlas 162 attempts -> **114** with `learned ranking + ceiling stopping (design only)`, a 29.6% reduction for a 0.30% change in accepted quality. An oracle would need 100, so this recovers 77% of the attainable saving.

**The cheaper, lossier option.** `learned ranking + accept-first-valid (design only)` reaches 109 attempts (32.7%) but gives up 0.81% of accepted quality and drops the preferred-threshold rate to 0.96. Speed bought with quality is not the same result, and the paper reports both rather than picking the flattering one.

**Attempts are not minutes.** The incumbent spends 48 min, of which 36 min is irreducible: every geometry needs one successful extrusion, and a successful attempt is the expensive kind (20.0 s, against 11.2 s for a folded march, 9.4 s for an under-quality mesh and about 0 s for a surface-build error). Only 12 min is addressable overhead, and the headline policy removes 84% of it (48 -> 38 min). So a 30% cut in attempts is a 21% cut in time; quoting the attempt figure alone would overstate the gain.

### Attribution: which half does the work?

| policy                                         |   total_attempts |   attempts_saved |   pct_of_available |   quality_loss_pct |   reached_preferred_rate |
|:-----------------------------------------------|-----------------:|-----------------:|-------------------:|-------------------:|-------------------------:|
| atlas (as run)                                 |              162 |                0 |               0    |               0    |                     0.99 |
| atlas ordering + accept-first-valid (no model) |              127 |               35 |              56.45 |               2.79 |                     0.89 |
| atlas ordering + learned stopping              |              147 |               15 |              24.19 |               0.3  |                     0.97 |
| learned ordering only                          |              133 |               29 |              46.77 |               0    |                     0.99 |
| learned ordering + learned stopping            |              114 |               48 |              77.42 |               0.3  |                     0.97 |
| oracle (upper bound)                           |              100 |               62 |             100    |               0    |                     0.99 |

Ordering and stopping are separable and they compose: alone they save 29 and 15 of the 62 attempts an oracle would save, together 48. The line that matters is the model-free one — stopping at the first valid mesh needs no machine learning and saves 35, but it pays **2.79 %** of accepted quality and drops the preferred-threshold rate from 0.99 to 0.89. The learned policy saves more (48) for **0.30 %**, roughly a ninth of that cost. So the defensible claim is not that learning beats a heuristic on attempts; it is that **the cheap fix cannot reach this operating point at all** — at matched quality, no model-free policy in this comparison gets past 29.

**How much of this is machine learning?** Adding *only* a stopping rule to the incumbent ordering — no model at all — already reaches 127 attempts (21.6%), at a 2.79% quality cost. The learned ranking's contribution is what it adds beyond that line, and the honest reading is that the missing stopping rule, not the routing, is the incumbent's larger defect.


20 independent grouped partitions of the 100 geometries. Every number below is a counterfactual replay of the 162-attempt production campaign.

| policy                                        |   repeats |   attempts_mean |   attempts_sd |   attempts_min |   attempts_max |   first_attempt_mean |   worst_case_mean |   quality_mean |   quality_loss_pct |
|:----------------------------------------------|----------:|----------------:|--------------:|---------------:|---------------:|---------------------:|------------------:|---------------:|-------------------:|
| ranking (design only)                         |        20 |          132.85 |         2.134 |            130 |            139 |                0.893 |             21    |          0.212 |              0     |
| ranking (design+surface)                      |        20 |          133    |         2.575 |            128 |            139 |                0.901 |             21    |          0.212 |              0     |
| ranking + accept-first-valid (design only)    |        20 |          107.35 |         1.424 |            105 |            110 |                0.946 |              3    |          0.209 |              1.281 |
| ranking + accept-first-valid (design+surface) |        20 |          105.95 |         1.701 |            103 |            109 |                0.957 |              3.05 |          0.209 |              1.222 |
| ranking + ceiling stopping (design only)      |        20 |          114.8  |         3.205 |            110 |            123 |                0.898 |              4.25 |          0.211 |              0.162 |
| ranking + ceiling stopping (design+surface)   |        20 |          112.85 |         3.376 |            107 |            119 |                0.911 |              3.85 |          0.211 |              0.43  |

Reference: atlas as run = **162** attempts (first-attempt 0.74, worst case 21); oracle lower bound = **100**.

**Reading it.** The cheapest policy that holds accepted quality within 0.5% of the incumbent (`ranking + ceiling stopping (design+surface)`) averages 112.8 +/- 3.4 attempts against the atlas's 162, recovering 79% of the 62 attempts an oracle would save. Across 20 partitions it never needed more than 119 nor fewer than 107: the spread is an order of magnitude smaller than the saving, so this is a property of the method and not of one partition.

`ranking + accept-first-valid (design+surface)` is cheaper still at 106.0 +/- 1.7, but gives up 1.22% of accepted quality. It is reported, not headlined.


## 6. What this data cannot yet support

Stated plainly, because these are the objections a referee will raise:

1. **Restricted replay.** Learned policies may only reorder templates the atlas
   actually attempted; the outcomes of the other 88 % of the matrix are unknown.
   Every saving reported here is therefore a **lower bound** on what an
   unrestricted policy could achieve — but it also means the comparison is not
   the one we ultimately want. The completion campaign (≈ 8 h, mesh-only) removes
   this restriction entirely.
2. **Selection bias in which cells exist.** The observed cells were chosen by the
   incumbent policy, which stopped when satisfied. Geometries that were easy
   contribute one cell each; the hard ones contribute many. The model is
   therefore trained on a sample enriched in difficulty.
3. **No feasibility boundary exists in this data.** The development set reaches
   100/100 eventually. Nothing here supports a claim about predicting
   *meshability*; the claim is about predicting *routing cost*. Campaign B in the
   runbook is what would change that.
4. **One configuration.** `eps_e` is frozen at 1.5 throughout. The agent's action
   space in this paper is therefore "which template", not yet "which template and
   which marching parameters".
5. **The model-free baseline is not yet tuned.** `accept-first-valid` is the
   crudest possible stopping rule. A tuned heuristic — stop after *k* attempts
   without improvement, or stop once the best result is within a fixed margin of
   the historical median ceiling — has no model in it and might recover much of
   the 48 attempts the learned policy saves. That experiment is cheap and it is
   the one that could most deflate this paper's headline; it must be run before
   submission rather than after review.
6. **Scale.** 100 geometries, 247 measured cells. This supports gradient-boosted
   trees with grouped validation. It does not support claims requiring deep
   models, and none are made.

## 7. Conclusion

Treating the mesher's own attempt ledger as data turns an engineering nuisance
into a measurable decision problem. The incumbent proximity heuristic is already
good at *routing*; where it loses is in *stopping*, and the single worst case in
the campaign is a geometry that scanned an entire atlas to rediscover its own
first attempt. A model trained only on design variables, validated with each
geometry held out, reproduces the same accepted meshes for materially fewer
attempts, and the ablation separates how much of that comes from learning and how
much from simply knowing when to stop.

---

## Appendix A — reproduction

```bash
python AERIS_MESH_AGENT/experiments/exp01_ledger_audit.py       # ledger audit
python AERIS_MESH_AGENT/experiments/exp02_outcome_model.py      # outcome model
python AERIS_MESH_AGENT/experiments/exp03_policy_evaluation.py  # policy replay
python AERIS_MESH_AGENT/experiments/exp04_robustness.py         # fold-partition spread
python AERIS_MESH_AGENT/experiments/exp05_figures.py            # figures
```

All inputs are read-only; all outputs land in `tables/`, `figures/`, `results/`.

## Appendix B — references still to be added

Deliberately empty rather than fabricated. The draft needs citations for, at
minimum: hyperbolic mesh extrusion (pyHyp), the mesh-quality metrics used
(scaled Jacobian, equiangle skewness), automated aerodynamic dataset generation
and its published meshing-failure handling, contextual bandits and offline policy
evaluation, and prior work on machine learning for mesh generation and adaptive
refinement. Every number in this draft comes from the AERIS ledger and is
reproducible with the commands above; no external result is cited yet.
