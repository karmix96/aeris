# AERIS — two-paper AI plan: robust BWB meshing, then AI-native use of the mesh corpus

**Date:** 2026-08-30 · **Status:** proposal
**Supersedes:** the six-paper portfolio drafted earlier the same day (rejected).
**Direction (Mike's):** Paper 1 = use AI to make BWB meshing robust.
Paper 2 = use the resulting corpus of meshes for a more AI-native contribution.

---

## 1. The evidence that makes Paper 1 real

Extracted from
`artifacts/s6_bounded_mesh_atlas/development_atlas_qualified21_production_written_v3/atlas_validation_checkpoint.json`
(21-template atlas, 100 LHS geometries, `eps_e = 1.5`, preferred quality 0.15):

| Quantity | Value |
|---|---|
| Geometries | 100 (all eventually PASS) |
| Total attempts | **162** |
| Attempt outcomes | PASS 116 · **FAIL 32** · **SURFACE_BUILD_ERROR 14** |
| First-pass geometries | **74 / 100** |
| Retry tail | 15 need 2, 6 need 3, 2 need 4, 1 needs 5, 1 needs 6, **1 needs 21** |
| Hard-gate failure reasons | `inverted_cells` 19, `positive_volume` 19, `positive_scaled_quality` 19 (co-occurring — mesh folding) |
| Distinct accepted templates | 20 of 21; template 42 accepts 21/100, template 70 accepts 10 |
| Cost per attempt | ~25 s (`elapsed_s` on a passing attempt) |

Three things follow, and they are the paper.

1. **The failure is routing cost, not infeasibility.** The atlas reaches 100/100.
   What it does not do is reach it *cheaply*: 62 wasted attempts, and a worst case
   that burns 21 attempts — effectively a linear scan of the whole atlas.
2. **There are two distinct failure modes, not one.** `FAIL` (32) is a marching /
   folding failure caught by the hard gates after extrusion.
   `SURFACE_BUILD_ERROR` (14) happens *before* extrusion. They need separate
   predictors and separate remedies; lumping them is a modelling error.
3. **Template usage is heavily non-uniform.** One template covers a fifth of the
   space. So template choice is a learnable function of geometry, not a lottery.

Scaling: a 1,000-geometry campaign at today's 1.62 attempts/geometry costs
~11 h of mesh time, and the tail means the schedule is unpredictable — which is
exactly what blocks unattended dataset generation.

---

## 2. Paper 1 — Learned routing and parameter selection for robust automated structured meshing of a parametric BWB family

**Claim.** Mesh robustness for an automated CFD dataset pipeline can be moved from
human tuning and exhaustive trial to a learned decision, and the gain can be
measured in attempts, wall-clock and unattended completion rate.

**What the AI decides.** Given only the design vector θ (20 parameters in
`campaign_preflight_10000/designs.csv`) plus cheap geometry descriptors computed
before meshing (curvature statistics, LE radius distribution, TE thickness,
sweep/taper gradients, span-station twist rates, tip-region metrics):

- **(a) Template routing** — predict the atlas template that will pass first, or a
  ranked shortlist. Metric: attempts per accepted mesh; first-pass rate; and the
  elimination of the 21-attempt tail.
- **(b) Pre-extrusion screen** — predict `SURFACE_BUILD_ERROR` before any surface
  is built. This mode is 14/162 attempts and is pure waste.
- **(c) Marching-parameter selection** — predict the pyHyp option vector likely to
  march cleanly. The exposed knobs are already in `pyhyp_options.py`:
  `epsE`, `epsI`, `theta`, `volCoef`, `volBlend`, `volSmoothIter`, `cMax`,
  `nConstantStart`, `pGridRatio`, `marchDist`, `N`, plus first-cell spacing.
  Today `eps_e` is a frozen constant (1.5) for the whole design space. That is
  the human-tuned choice the paper replaces with a per-geometry one.
- **(d) Quality prediction** — regress `min_scaled_quality` before meshing, so the
  campaign can rank and schedule rather than discover cost at run time.

**Why it is publishable.** Automated CFD dataset papers report the geometries that
meshed and omit the meshing cost. AERIS has a per-attempt ledger with hashes,
outcome states, quality metrics, wall/interface errors and surface fidelity —
i.e. the record that is normally thrown away. Publishing the *failures with their
reasons* is the contribution as much as the classifier is.

**Data campaign needed** (mesh only — **no CFD**, so it is not blocked by the
current solver state):
- Sample 600–1,000 designs from the existing 10,000-design pool.
- Deliberately include regions expected to fail. The present pool passes 100/100,
  so it contains no feasibility boundary; without genuine failures the classifier
  learns only routing, and the feasibility claim is unsupported. Widen sweep,
  taper, twist and tip geometry beyond the current bounds for a deliberate
  hard-case stratum.
- Record every attempt, including rejected ones, with the existing schema.
- Estimated desktop cost: ~7–12 h, interruptible, resumable, no solver.

**Model.** Gradient-boosted trees for routing/screening (θ is 20-dimensional and
tabular — a neural net buys nothing here), with conformal risk control on the
accept decision so the screen carries a stated false-accept bound rather than an
accuracy number. Trains in seconds on CPU.

**Headline result to aim for.** First-pass rate 74% → >90%, attempts per accepted
mesh 1.62 → ~1.1, worst case bounded, and an unattended holdout campaign that
completes with zero manual repair. That last one is also **claim 5 of the S6
guide** — so this paper is the natural write-up of work already scheduled.

**Compute.** Training: seconds. Labelling: desktop-hours. No GPU. **Risk:** low.
**Venue:** Engineering with Computers · Advances in Engineering Software ·
Computer-Aided Design · AIAA Aviation.

---

## 3. Paper 2 — Learned free-form node distributions for structured surface meshing, with a differentiable quality objective

**Decision (Mike, 2026-08-30): the AI builds the mesh.** Options B (flow surrogate)
and C (mesh-independence/leakage) are deferred until the S6 solver campaign
produces converged cases; they are recorded at the end as later work.

### 3.1 What the AI replaces

`src/aeris/mesh/surface.py:170` (`_distribution`) builds every arc of the S6
surface by resampling along arc length with one of a **fixed analytic family**:
`uniform`, `cosine`, `cluster_start`, `cluster_end`, `cluster_center`,
`tanh(beta)`. Segment point counts are split by arc-length proportion
(`_split_counts`). That family, its strength parameter and the count split are a
human prior — chosen once, applied to the whole design space, exactly like the
frozen `eps_e = 1.5`.

**Paper 2 removes the family.** The network outputs, for every arc and every span
column, a free-form monotone distribution of parametric coordinates
`s in [0,1]` — not a choice among cosine/tanh, but the distribution itself.

### 3.2 Three guarantees by construction (this is what makes it defensible)

1. **Exact wall geometry.** The network predicts *parametric* coordinates, never
   points in R^3. Nodes are then evaluated on the pyGeo curve at those
   parameters — the same instrument the audit already uses
   (`surface_fidelity.instrument`: "each OML node is independently re-evaluated on
   the pyGeo curve at its tracked parametric coordinate"). So the learned mesh
   inherits today's fidelity: max node-to-curve 4.59e-6 m, 1.41e-5 of local chord,
   tip planarity 2.2e-16 m. A network predicting xyz could never promise this.
2. **No surface tangling.** Predict positive increments, normalise (softmax over
   the segment), cumulative-sum to get `s`. Monotonicity is structural, so nodes
   cannot cross or fold along an arc regardless of what the network learns.
3. **Volume validity still audited, not assumed.** `volume_audit.signed_cell_volumes`
   and `quality.block_quality_metrics` re-check every written mesh exactly as now.
   The paper claims a better *proposal*, never an unchecked one.

### 3.3 The AI-native part: a differentiable mesh-quality loss

`quality.py` already computes `scaled_jacobian`, `equiangle_skewness`,
`aspect_ratio`, `growth_ratio` — all differentiable in node positions almost
everywhere (the `min`/`max` reductions behave like max-pooling). Node positions
are differentiable in `s` if the pyGeo curve is replaced by a densely sampled
polyline with differentiable interpolation, which is how `_resample_polyline`
already works.

Consequence: **the quality objective needs no reference mesh.** Training is

- **supervised warm start** on the accepted meshes from Paper 1's corpus
  (a few hundred to ~1,000 known-good distributions), then
- **self-supervised refinement** on the differentiable quality functional, which
  can run over the full 10,000-design pool *without meshing any of them*.

That answers the data-hunger objection that normally sinks learned mesh
generation on a small dataset, and it is the honest reason this is trainable on a
CPU workstation.

### 3.4 Model and cost

Output is a fixed-size tensor over the structured index space (6 OML arcs x ~95
span columns; ~9,500 surface quads in the current production candidate), so a
small U-Net or MLP over the (i,j) grid suffices. Conditioning: the 20-parameter
design vector plus the same cheap geometry descriptors as Paper 1. Order 10^5-10^6
parameters. CPU-trainable in hours, no GPU.

### 3.5 Evaluation, against the atlas as the baseline

Held-out geometries, never used in training, scored with the existing audit:

| Metric | Atlas baseline (measured) | Target |
|---|---|---|
| First-pass marchability | 74 / 100 | higher |
| Attempts per accepted mesh | 1.62 | ~1 (no search) |
| Worst case | 21 attempts | one shot |
| min scaled quality (accepted) | 0.147 / 0.162 / 0.220 (min / p05 / median) | match or beat |
| Inverted cells | 0 | 0 (hard requirement) |
| Wall / surface fidelity | 1.7e-18 m / 1.41e-5 chord | unchanged by construction |

**Honest expected outcome.** The learned distribution may not beat hand-tuned
atlas quality everywhere. "Matches atlas quality in a single shot, with no
template search, on unseen geometries" is already the result — and it is the
thing that makes 10^3-geometry campaigns schedulable.

### 3.6 Known work items and risks

- `quality.py` is numpy; the loss needs a torch re-implementation of the same
  metrics, verified to agree with the numpy version to machine precision (the
  audit path must stay the independent one).
- pyGeo curve evaluation must be differentiable in `s`; fall back to dense
  polyline + differentiable interpolation, consistent with `_resample_polyline`.
- Surface quality is a proxy for marchability, not a guarantee. The relationship
  between predicted surface distribution and extrusion folding must be measured,
  not assumed — Paper 1's `FAIL` records (32 attempts, folding) are the data for it.
- Span-column and arc counts vary between templates; fix the output topology per
  template class, or train per class.

---

## 4. The meshing agent — how Papers 1 and 2 compose

**Corrected accounting (supersedes section 1's reading of the 162 attempts).**
The atlas loop is not a naive retry-until-success loop. It has two thresholds:
`preferred_quality = 0.15` and production floor `0.1`. It accepts immediately at
>= 0.15, otherwise keeps trying templates hoping for better and falls back to the
best result >= 0.1. So the 162 attempts decompose as:

| | Count |
|---|---|
| Attempts up to and including the first PASS | 127 |
| Attempts spent **after** a PASS, purely searching for higher quality | **35** |
| PASS | 116 |
| `SURFACE_BUILD_ERROR` (pre-extrusion) | 14 |
| `FAIL_folded` (inverted cells > 0) | 19 |
| `FAIL_low_quality` (valid mesh, 0 inverted, quality below floor) | 13 |

Two corrections follow. Failures are **three** classes, not one — a valid but
under-quality mesh is a different event from a folded one and demands a different
response. And a large share of the cost is not failure at all; it is an
**unbounded quality search with no stopping rule**.

**The decisive case.** Geometry `lhs100_seed42_095` took 21 attempts. Its
per-attempt quality was:

`0.147, 0.08, -0.11, -0.197, err, err, 0.09, 0.109, 0.044, err, 0.113, 0.104,
0.124, 0.121, -0.144, err, 0.026, 0.048, 0.119, err, -0.235`

The **first** attempt was the best of all 21, and the campaign accepted 0.1468 —
essentially that first result — after scanning the entire atlas. It did so because
0.147 fell 0.003 short of the 0.15 preference, and nothing told it that 0.147 was
this geometry's ceiling. That is not a meshing failure. It is a **stopping-rule
failure**, and it is the clearest argument in the dataset for an agent.

### 4.1 What the agent is

Four decisions. Papers 1 and 2 supply two of them; the agent supplies the rest.

1. **First action** — which template and which marching knobs to try first.
   *= Paper 1*, a one-shot policy.
2. **Next action after a failure** — conditioned on *where and how* it failed.
   `volume_audit._cluster_report` already localises every defect: block, first/last
   layer, j/i ranges, `on_spanwise_edge` (root symmetry vs tip cap junction),
   `wall_adjacent`, and an xyz bounding box on the wall. **Today none of this
   feeds the next choice** — the loop simply tries another template. Using the
   diagnostic to select the next action is the agent's genuinely new content.
3. **When to stop** — predict the achievable quality ceiling for this geometry and
   halt when expected gain from another attempt falls below its cost. On
   `lhs100_seed42_095` alone this converts 21 attempts into 1.
4. **Continuous action** — rather than choosing among 21 fixed templates,
   synthesise the node distribution directly. *= Paper 2.*

### 4.2 Why both papers are needed, in one sentence

The atlas imposes a **per-geometry quality ceiling** that no routing policy can
exceed — `lhs100_seed42_095` could not reach 0.15 with any of the 21 templates.
Paper 1 finds the ceiling faster; **Paper 2 raises it.**

### 4.3 Method, scoped honestly to the data budget

- Formulation: contextual bandit with a failure-conditioned retry policy and a
  learned stopping rule. State = design vector + geometry descriptors + the
  diagnostic record of attempts so far; action = template + knob vector (Paper 1)
  or distribution (Paper 2); cost = attempts and wall-clock; constraint = accepted
  quality and zero inverted cells.
- **Not deep RL.** 162 logged attempts today; even a 5,000-attempt campaign
  (~35 h desktop, no solver) is bandit/imitation/tree territory, not deep RL.
  Claiming otherwise would not survive review, and the honest version is stronger.
- **Not an LLM agent.** The decision space is a 20-dimensional numeric vector with
  a numeric objective; an LLM adds latency and nondeterminism and forfeits the
  reproducibility the S6 covenant requires. The agent must be a deterministic,
  seeded, replayable policy.
- **Auditability as a feature.** Every action, observation and terminal state keeps
  an immutable attempt ID exactly as now; the agent escalates to a human terminal
  state rather than silently degrading a threshold. An autonomous agent that
  cannot quietly weaken its own acceptance gate is an unusual and defensible
  contribution in its own right.

### 4.4 Packaging options

- **(a) Agent as deployment, no extra paper.** P1 + P2 publish separately; the
  agent is the engineering artifact that generates the mesh corpus. Fastest.
- **(b) Agent as Paper 3.** P1 (one-shot) becomes the baseline; the paper's
  contribution is failure-conditioned retry + learned stopping, measured as
  expected attempts to acceptance at fixed quality. Real added science, and the
  data campaign for P1 already produces its training data. **Recommended.**
- **(c) One combined paper.** Higher impact if it lands, harder to place, and it
  puts the unblocked meshing work at the mercy of a single review.

---

## 4. Deferred (gated on the S6 solver campaign)

- **Flow surrogate:** theta + condition + (x,y,z) -> Cp on the corpus. Blocked:
  `cfd_pilot_083` and `..._n65` both report `status: failed`, `forces: {}`.
- **Mesh-independence / fingerprint leakage:** the atlas gives *controlled*
  topology and resolution variation on one geometry — rare, and the right way to
  test the "cheat sheet" claim. Needs CFD and a working surrogate first.
