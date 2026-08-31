# Review of the mesh-paper roadmap

**Date:** 2026-08-31
**Status:** adversarial review of `mesh_paper_roadmap.md` (commit 24b4b96)
**Method:** every claim below is checked against the atlas ledger, the S6/S7
master execution guides, and the host inventory. New measurements are
reproducible via `AERIS_MESH_AGENT/experiments/exp06_attempt_decomposition.py`.

## Verdict

The portfolio logic is sound and the discipline is unusual: gates before
results, holdouts named and untouched, negative results retained. Three things
survive review unchanged — Paper 1 as the backbone, S7 as a second method rather
than a standalone paper, and the refusal to claim that AI is required for
robustness.

Five things do not survive, and they are not stylistic. In order of how much
they cost if left alone:

1. **No hardware line exists in a plan whose every terminal gate is grid
   convergence.** The host cannot run the ladder Paper 3 specifies.
2. **The Paper 2 evidence is keyed to a configuration that is not frozen** —
   and the roadmap schedules the expensive matrix campaign *before* the freeze.
3. **Paper 2's central diagnosis is backwards.** The incumbent's stopping rule
   is profitable in 10 of 11 cases; routing is where it loses.
4. **Paper 2's go-gate measures the one quantity that does not matter** (ten
   minutes of wall time), and the claim it should defend — tail risk — rests on
   a single geometry.
5. **Paper 4's go-gate is set below the baseline it has to beat.**

One thing is missing that would be cheap and is more novel than Paper 2.

---

## Finding 1 — the portfolio has no hardware gate, and it needs one first

Every paper terminates in a grid-convergence requirement. Paper 1: "five or more
representative grid studies meeting the frozen uncertainty rule." Paper 3: "five
paired coarse/medium/fine studies per route." Nothing in the roadmap asks
whether the machine can produce them.

Measured host: **15 GiB total, ~10 GiB available, 12 cores.** Not a cluster.

The S6 guide already saw this coming and named the terminal state
(`RESOURCE_BLOCKED_16GB`, line 44): forecast peak 9.35 GiB against ~11.36 GiB
available is about 2 GiB of headroom, which "authorizes one measured canary, not
a production claim."

The S7 side is quantified and worse. Each MPI rank reads the whole mesh before
partitioning, so peak memory scales with **ranks × cells**:

    GiB per rank ≈ 1.20 × (cells / 1e6)

| level | cells | GiB/rank | ranks that fit in ~10 GiB | wall time |
|---|---|---|---|---|
| coarse (measured) | 1.55 M | 1.86 | 4 | 5.1 h at 4 ranks (1.8× speedup *assumed*, not measured) |
| medium (~2.2× cells) | ~3.4 M | 4.1 | 2 | ~20 h, extrapolated |
| fine (~2.2× again) | ~7.5 M | 9.0 | 1 | infeasible |

A three-level ladder with a refinement ratio large enough to satisfy any
uncertainty rule does not fit. And the campaign around it does not fit either:
Paper 3 as specified is 20 geometries × 2 routes at coarse resolution, which for
the S7 half alone is **~100 h of exclusive, sequential desktop time** (memory
forbids concurrency), before the 30 grid-study runs, before the S6 half, whose
per-case cost has never been measured.

**What to do, in this order:**

- **Add a Stage −1 hardware gate to the whole portfolio, ahead of Paper 1's
  grid studies.** Its output is a per-route, per-level table of measured peak
  RSS and wall time, and a verdict on the finest level that fits.
- **Test the rank-replicated read before accepting the limit.** The 1.2 GiB/rank
  law is an implementation property, not physics. If SU2 can be given a
  pre-partitioned mesh or a parallel read path, the entire ladder becomes
  affordable. This is a half-day check with the coarse mesh already in hand and
  it is the highest-leverage unstarted task in the portfolio — it decides whether
  Papers 1, 3 and 4 have terminal evidence at all.
- **If the finest level still does not fit, decide now, not after 100 hours.**
  Either acquire memory/HPC time, or reduce Paper 3 to a defensible scope
  (below), or record `RESOURCE_BLOCKED` and say so in the manuscript. The S6
  guide's own rule applies: this "does not authorize weaker science."

The roadmap's item 6 ("measure per-case CFD cost before approving the 20-case
paired campaign") is the right instinct in the wrong place — it is listed after
the design has already been fixed at 20 geometries and three levels. Cost the
design before writing it down.

---

## Finding 2 — the Paper 2 evidence sits on an unfrozen configuration

The whole 384-attempt production pool carries one config key:

    1.5 | 3.5999999999999994e-06 | 257 | production
     ^eps_e   ^first-cell fraction   ^N   ^level

The S6 guide, line 259: *"Initial candidate: current `s0/L_s0 = 3.6e-6`"*, and
line 261: *"A flat-plate estimate may initialize `s0`; only measured CFD y+ can
qualify it."* The guide then specifies exactly what happens if it does not
qualify — a global update `s0_new = s0_old · 0.8 / max(y+_95)` applied to **all
affected templates**, followed by rebuild, re-audit and rerun of both wall
canaries. The roadmap itself lists production y+ as open.

So a y+ result that is currently unknown can invalidate the entire mesh-outcome
dataset. Not all of it: of the 247 measured cells, the 21 `SURFACE_BUILD_ERROR`
cells (8.5%) are wall-spacing-independent. **The other 91.5% — every
`FAIL_FOLDED`, `FAIL_LOW_QUALITY` and `PASS` quality value — is at risk.** The
farfield screen (`d_F/b_full ∈ {5,10,15,(20)}`) and `N = 257` are two further
unfrozen knobs in the same key.

Against that, the roadmap's immediate execution order says: *"2. Continue S6
production mesh, y+, TE, grid and CFD qualification. 3. **In parallel**, complete
the S6 100 by 21 mesh-outcome matrix."*

Those two are not parallel. Item 3 is a 2100-cell campaign — roughly 8–12 hours
of the same scarce desktop — spent at a config key that item 2 may retire.

**Fix:** make matrix completion depend on the wall-spacing freeze. The y+
qualification is one CFD case; run it first. Sequence the immediate order as
`y+ canary → freeze s0/N/farfield → complete the matrix`.

There is an upside worth naming. The current paper lists "one configuration" as
a limitation — `eps_e` frozen at 1.5, action space "which template" only. If s0
*does* move, you end up holding two matrices at two configurations, which turns
that limitation into a generalisation test: does the learned routing transfer
across a wall-spacing change? That is a better paper than one matrix. So the
risk is real but it is not purely downside — it just must not be paid for twice
by running the campaign at the wrong key first.

---

## Finding 3 — Paper 2's diagnosis is backwards, and its own data says so

The paper's conclusion: *"The incumbent proximity heuristic is already good at
routing; where it loses is in stopping."* Experiment 3's closing line: *"the
missing stopping rule, not the routing, is the incumbent's larger defect."*

Decomposing the 162 attempts (new, `exp06`):

| class | attempts | recoverable by |
|---|---:|---|
| irreducible — one successful extrusion per geometry | 100 | nothing |
| routing — spent before any mesh passed | 27 | routing only |
| quality search — spent after a mesh had already passed | 35 | routing, or stopping |

Then the part that changes the story. Of the 11 geometries that continued after a
PASS:

- **all 11** had a first PASS below the 0.15 preferred threshold, so every one of
  those searches was *mandated* by the incumbent's own acceptance rule;
- **10 of 11 searches paid off**, and every one of the 10 lifted a fallback-grade
  mesh (≥0.10) to preferred grade (≥0.15), for 15 attempts total;
- the 11th is `lhs100_seed42_095`: **20 attempts, zero return.**

So the incumbent's stopping behaviour is not a defect. It is a profitable rule
with one catastrophic exception. The entire quality-preserving prize available to
*any* stopping rule is **20 attempts on one geometry**, and collecting it means
predicting that no template in the atlas can reach 0.15 for that geometry — a
**ceiling prediction**, not a stopping heuristic.

This also re-reads the model-free baseline. `accept-first-valid` saves 35
attempts and drops the preferred-threshold rate from 0.99 to 0.89 — those are
exactly the 10 profitable upgrades, destroyed. It is not, as the limitations
section says, "the crudest possible stopping rule" awaiting a tuned successor: it
is a baseline paying a **known, itemised** price, and no tuned variant of it can
do better, because the 10 searches it kills were each correct.

And at matched quality the attribution table already agrees: learned ordering
alone saves 29, learned stopping alone saves 15. The "stopping matters more"
sentence is supported only by the unmatched 35, which costs 2.79% quality.

**Fix — reframe Paper 2 around routing, with ceiling prediction as the safety
valve:**

- Headline claim: the nearest-template heuristic misroutes; a model trained on
  design variables routes better, and the oracle (100 attempts, quality and
  preferred-rate unchanged) proves the whole 62-attempt gap is reachable by
  routing alone.
- Secondary claim: one geometry in the family has a ceiling below the preferred
  threshold, and predicting that is what stops a 21-attempt scan. Present it as a
  named case study, not a general stopping result — the sample size is one.
- Delete the "stopping is the larger defect" sentence from both the paper and
  experiment 3's prose.
- State the completion guarantee as **structural, not empirical**. Both stopping
  rules fire only after a PASS exists; failure recovery still exhausts the atlas.
  So "100% completion" is an invariant with a unit test, not an outcome to hope
  for. The roadmap currently lists it as a preregistered *requirement*, which
  reads as though it might fail.
- Report quality regret in interpretable units. "0.30% mean accepted quality" is
  a mean of per-geometry minima and means nothing to a referee. The same fact
  states as: *the policy moves 2 of 100 geometries from preferred to fallback
  acceptance and leaves the worst accepted mesh unchanged at 0.1468.*

---

## Finding 4 — the Paper 2 go-gate measures the wrong quantity, and the right one is n=1

The gate: *"at least 15% wall-time improvement relative to tuned deterministic
heuristics at no more than 0.5% quality regret."*

The measured campaign is **48 minutes**, of which 36 is irreducible. The headline
policy takes it to **38 minutes**. Ten minutes, over 100 geometries. Meanwhile a
single S7 coarse CFD case is 5.1 h and the S6 per-case cost is not yet measured.
Mesh routing is on the order of **0.2%** of the campaign it belongs to. A referee
who asks "why does this matter" gets an answer that defeats the paper, and the
gate as written is a gate on that answer.

Worse, the number that *does* matter — worst route 21 → 4 — is one geometry.
74 of 100 geometries cost exactly one attempt under every policy; all separation
comes from 26; the tail claim comes from 1. A geometry-level bootstrap over 100
will look reassuring and will be measuring the wrong resample unit.

**Fix:**

- Replace the wall-time gate with a **risk gate**: `P(attempts > 4)`, CVaR95 of
  attempt count, and first-attempt acceptance on unseen geometries. Report wall
  time as a secondary number with the 36-minute irreducible floor stated beside
  it, so nobody can read 21% as a campaign-level saving.
- **Report n_hard (26) everywhere n (100) appears**, and bootstrap over hard
  geometries.
- **Size the prospective holdout on the hard-case rate, not on a round number.**
  At the observed 26% multi-attempt rate, 50 geometries buys ~13 informative
  cases and an expected ~0.5 pathological ones. 100 is the minimum that can
  observe the tail event at all, and even then the expectation is ~1. Either
  commit to ≥100 or state the tail result as a case study and stop claiming
  distributional support for it.

---

## Finding 5 — Paper 4's gate is below its own baseline

Gate as written: *"at least 90% one-shot accepted volumes on an untouched test
set."*

Measured first-attempt acceptance in experiment 3: atlas 0.74, learned ranking
0.88–0.89, learned ranking + accept-first-valid **0.93–0.94**, + ceiling stopping
0.89–0.90.

A neural generator that hits exactly 90% therefore **loses** to the Paper 2
policy it is supposed to supersede, on the metric it is being gated on.

**Fix:** make the gate relative and preregistered against the strongest baseline
*measured at freeze time* — one-shot acceptance ≥ (best routed baseline + margin)
— and require at least one endpoint no baseline can reach: fewer stored
templates, or accepted meshes outside both deterministic envelopes. Absolute
thresholds go stale the moment the baseline improves, and here it already has.

---

## Refinement 1 — Paper 3's solver confound is probably removable; do not concede it

The roadmap concedes: *"If [running both mesh families through the same solver]
is not technically possible, the manuscript must explicitly compare complete
pipelines rather than claim to isolate mesh topology."* That is the honest
fallback, but it is being adopted before the check.

The installed `SU2_CFD` binary links a CGNS reader (CGNS base/version handling is
present in the binary). The open question is not whether SU2 reads CGNS but
whether the S6 multiblock structured CGNS and its boundary markers ingest
cleanly. That is a half-day test against one already-accepted S6 mesh.

If it passes, Paper 3 changes character:

- **primary comparison:** S6 mesh in SU2 vs S7 mesh in SU2 — isolates topology;
- **secondary:** S6 mesh in ADflow vs S6 mesh in SU2 — *measures* the solver
  transfer term instead of leaving it as a caveat;
- ADflow stays the production S6 solver; nothing about Paper 1 changes.

That converts "we compared two pipelines and cannot attribute the difference"
into "we compared two mesh topologies under one solver, and separately bounded
the solver effect." It is the difference between a descriptive study and a causal
one, for one extra run per grid level.

Run this check *before* the hardware gate's cost table, since it changes what
goes in the table.

---

## Refinement 2 — the missing portfolio item: publish the outcome matrix

The most unusual asset in this project is buried in experiment 1's third table:
across 384 attempts spanning independent campaigns, **cells measured twice that
disagree: 0.** A bit-deterministic mesh-generation outcome oracle over a
parametric family, with four separated failure modes.

Nobody publishes that. It is also what licenses every counterfactual claim in
Paper 2 — replay is a valid evaluation method here *only because* the pipeline is
deterministic — and the roadmap never mentions it.

Two consequences:

- **Promote determinism to a stated contribution of Paper 1.** "Independent
  campaigns reproduce identical mesh outcomes on every repeated cell" is a
  verification result most CFD-automation papers cannot make, and it costs
  nothing to claim because it is already measured.
- **Add a dataset/benchmark paper at priority 2.5.** The completed 100 × 21
  matrix — geometry parameters, template, outcome class, quality, timing, all
  reproducible — is a byproduct of a step already scheduled. It is reusable by
  other people's routing, surrogate and RL work; it has better novelty-per-hour
  than Paper 2; and it gives the routing result a home if the learned policy
  fails to beat a tuned heuristic. Right now, if Paper 2's go/no-go says "merge
  into Paper 1," roughly 12 hours of campaign and five experiments become an
  appendix. With the dataset paper they do not.

---

## Refinement 3 — ask the matrix the question that is worth more than routing

Once the 100 × 21 matrix is dense, the first query should not be the policy
replay. It should be **set cover: how many templates does this design family
actually need?**

The atlas holds 21 qualified templates and 20 of them were the accepted template
at least twice — but that is under nearest-template routing, which spreads usage
by construction. On the sparse observed cells, template 42 alone covers 25
geometries at preferred grade. Whether 3, 5 or 15 templates cover 100 geometries
is unanswerable with 11.8% of the matrix and immediate with 100% of it.

Why it is worth more than the ten minutes:

- every template carries a build, audit and maintenance cost in Paper 1, so a
  smaller atlas reduces the qualification burden directly;
- it is a real, transferable claim about the design family, not about a policy;
- it hands Paper 4 the "fewer required stored templates" endpoint as a *measured*
  baseline rather than an aspiration;
- it survives the learned policy losing to a tuned heuristic.

Cost: one query on data already being collected.

---

## What the roadmap gets right and should not be talked out of

- **S6 first, S7 must not expand Paper 1.** Correct, and the pressure to merge
  them will be constant.
- **S7 standalone is not a PhD paper slot.** Correct. The listed S7-specific
  findings — isoparametric prism validity, protected schedules with rollback,
  exact wall-point y+ coverage, independent auditing of both Gmsh and native SU2
  files — are strong Paper 3 content and a weak standalone paper.
- **The refusal to claim AI is required for robustness.** This is the single
  most defensible position in the document and it is what makes the rest
  credible.
- **The final portfolio rule.** "Implementation effort does not automatically
  earn a paper" should stay exactly as written.

---

## Revised immediate execution order

Changes from the roadmap are marked.

1. Do not touch the protected S6 or S7 holdouts. *(unchanged)*
2. **[NEW, blocks 3]** Run the S6 production y+ canary and freeze `s0`, `N` and
   the farfield extent. Record the freeze in `decision/`.
3. **[NEW, half-day]** Test S6 multiblock CGNS ingestion in SU2 against one
   accepted mesh. Outcome decides Paper 3's design.
4. **[NEW, blocks all grid work]** Stage −1 hardware gate: measured peak RSS and
   wall time per route per level; verdict on the finest feasible level; test
   whether SU2's rank-replicated mesh read can be avoided.
5. Complete the S6 100 × 21 matrix — **only after step 2**.
6. First query on the completed matrix: **minimum-atlas set cover**, before the
   policy replay.
7. Continue S6 TE, grid and CFD qualification within the Stage −1 verdict.
8. Run the S7 coarse Newton-Krylov shortlist; adopt through the governed record.
9. Complete the S7 production-resolution mesh sweep and one accepted coarse CFD
   case.
10. Freeze the Paper 2 model, the tuned heuristics **and the risk-based gate**
    before the prospective holdout; size the holdout at ≥100 geometries.
11. Begin the paired comparison only after both pipelines pass Stage 0 **and the
    Stage −1 gate says the ladder fits**.

## Exact edits to `mesh_paper_roadmap.md`

| section | edit |
|---|---|
| Executive decision | insert a Stage −1 hardware gate ahead of item 1 |
| Portfolio table | add row 2.5, "Outcome-matrix dataset / benchmark", practicality high, novelty medium-high, standalone yes |
| Paper 1 → required contribution | add cross-campaign outcome determinism as a claimed result |
| Paper 2 → correct framing | replace the stopping-defect diagnosis with routing + ceiling prediction; cite `exp06` |
| Paper 2 → minimum experiment, item 2 | replace the wall-time objective with P(attempts>4) and CVaR95; state the completion guarantee as structural |
| Paper 2 → item 4 | holdout ≥100 geometries, justified by the 26% hard-case rate |
| Paper 2 → go/no-go | replace "≥15% wall-time" with the risk gate; keep wall time as reported-only |
| Paper 3 → critical confound | replace the concession with the SU2-common-solver design and the ADflow/SU2 transfer term |
| Paper 3 → required design | make cell counts and level count outputs of the Stage −1 gate, not fixed inputs |
| Paper 4 → go/no-go | make the one-shot gate relative to the best baseline at freeze time |
| Immediate execution order | replace with the revised order above |

## Reproducing the new numbers

```bash
PYTHONPATH=AERIS_MESH_AGENT/src python AERIS_MESH_AGENT/experiments/exp06_attempt_decomposition.py
```

Sources for everything else: `AERIS_MESH_AGENT/results/exp01–exp04`,
`AERIS_MESH_STUDY/AERIS_S6_AUTOMATED_CFD_MASTER_EXECUTION_GUIDE.md` (lines 34–44,
259–271), `AERIS_MESH_STUDY/AERIS_S7_UNSTRUCTURED_CFD_MASTER_EXECUTION_GUIDE.md`
(lines 215–250), and `free -g` / `nproc` on the host.
