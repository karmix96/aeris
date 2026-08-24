# RUNBOOK — Adaptive spanwise section positioning for AVL (v1)

Date issued: 2026-07-29 · Owner: Mike (lead researcher) · Executor: a fresh agent
Companion decision to be produced: `decision/0012-section-positioning-doe.md`
Builds on and supersedes the *evidence* (not the ideas) of:
`studies/adaptive_section_placement.md`, `decision/0011-adaptive-section-placement.md`,
`src/aeris/geometry/geometric_information.py`.

**Read this first, in full, before running anything.** It fixes the two flaws that
would sink the prior study at review: (1) the reference biased toward uniform, and
(2) gates that were not decision-relevant. Every aggregation rule, gate threshold,
normalisation scale and stop condition is fixed here and must not be adjusted to
produce a winner. If a *stage gate* fails, STOP and report — do not work around it.

Defend this as if presenting at AIAA SciTech: pre-registered, worst-case
aggregation, a reference whose legitimacy is *proven not assumed*, negative results
reported in full, and no claim that AVL is truth.

---

## 0. The question, stated so it can be falsified

An optimiser will call AVL thousands of times over blended-wing-body (BWB) shapes.
The chordwise/spanwise **panel** density was settled by the panelling study
(selection **c16s2u**: chord 16, span-2 multiplier, uniform spacing). This study
settles the orthogonal axis: **where the defining wing sections go, and how many
are needed** — the spanwise stations at which the airfoil/planform is sampled and
between which AVL interpolates **piecewise-linearly**.

Two deliberately separable claims (either can fail without taking the other down):

- **C1 — predictive.** A metric computed from the geometry alone forecasts *which
  designs are hard to discretise* and *how many sections they need*, before any AVL
  run. Useful as a budget selector even if placement is never adapted.
- **C2 — prescriptive.** At an identical section budget, information-weighted
  placement that concentrates nodes *where geometry varies AND where the
  aerodynamics is sensitive to it* beats uniform placement, worst-case over the
  design set — and never corrupts a DoE decision.

The deliverable is a **placement + count policy** for DoE/optimisation use, with an
honest statement of where it helps, where it is neutral, and where it must escalate.

---

## 1. What is fixed, what varies

**Frozen (not swept):**
- Panel mesh = **c16s2u** (chord 16, spanwise-panels-per-section 2, cspace uniform).
  Section placement is the *only* discretisation axis this study moves. Stage 2
  proves count⊥panel so this freeze is legitimate.
- Solver, freestream, altitude, provenance rules — inherited from the panelling
  study infrastructure (`standalone/panelling_study/common.py`, its cache and
  `all_runs.csv`). Reuse it; do not re-implement.
- Geometry family: `configs/geometry/bwb.yaml` — 3 LE-sweep segments
  (sw1/sw2/sw3), chords c1..c4 at breaks b0..b3, semi-span b_total, one
  trailing-edge elevon **pair**, four **fixed-station airfoils** mh91/mh91/e374/nlf1015
  at b0/b1/b2/b3.

**Varies (the study's independent variables):**
- **N** — section count (budget).
- **Placement policy** — how the N sections are distributed along the span.
- **Design** — 30 LHS "normal" designs (reuse the panelling seed family
  `lhs30s2000`) + an **extreme set** chosen to stress *placement* specifically
  (see §6).

**Mandatory nodes (hard points) — these are constraints, not choices.** Every
candidate placement, at every N, MUST land a section exactly on:
1. the four fixed-airfoil stations b0,b1,b2,b3 (a section is where the airfoil is
   *defined*; interpolating across a fixed airfoil is a modelling error, not a
   discretisation error);
2. the planform breaks where LE-sweep or chord slope is discontinuous (subset of
   b0..b3 for this family, but treat generally);
3. the **elevon band edges** (control-gain is a boxcar → its 2nd derivative is a
   pair of deltas; DECISION-0005 requires an exact node, `snap_sections_to_control`).

The free budget is `N − |mandatory nodes|`, distributed by the placement policy.
Stage 4 proves each mandatory node earns its place (ablation); if one does not, it
is demoted, with evidence.

---

## 2. Ground truth without CFD — the crux, made legitimate

There is no CFD or wind tunnel. But unlike CFD, **the geometry is exact**: pyGeo
lofts an analytic surface, and AVL's *only* section-related error is the
piecewise-linear interpolation of the spanwise functions between sections. So a
legitimate reference is an AVL solve on a section set dense enough that the result
is **independent of where the sections are placed**. That independence is the whole
game, and it must be *demonstrated per design*, not assumed.

**Reference construction (Stage 1).** For each design, build three dense placements
at a high count N_ref (target N_ref ≈ 97, i.e. two doublings above 25, subject to
the strip/vortex caps at c16s2u):
- `ref_uniform` — uniform in span fraction,
- `ref_adaptive` — the information-weighted density,
- `ref_clustered` — deliberately clustered at the *opposite* places (inboard-heavy).

**Gate G1 — reference legitimacy (two parts, both mandatory):**
- **G1a placement-neutrality.** On the frozen quantity list, the worst-case spread
  across the three dense placements must be **< ½ of the tightest downstream
  accuracy gate** (i.e. < 0.5%). If the dense placements disagree by more than
  that, the reference is not truth — STOP and raise N_ref. This is exactly the bias
  that invalidated the prior study (a 49-section *uniform* reference shares a family
  with the uniform candidate); here the reference is only accepted once it is
  provably family-independent.
- **G1b Richardson band.** Along uniform placement at counts {25, 49, 97}
  (ratio-≈2 in 1/N), each key quantity must converge monotonically and its
  Richardson/GCI band (Fs=1.25) at N_ref must be < 0.5%. The reference value is the
  Richardson-extrapolated N→∞ (continuous-loft) limit where admissible, else the
  N_ref value with its finest-grid discrepancy reported.

Only quantities passing G1 carry a reference. A quantity that cannot be made
placement-neutral at any affordable N_ref is declared **section-unresolvable** and
excluded from the accuracy gates (reported, not hidden) — the honest analogue of
"below the noise floor".

**Honesty carried to the defence:** this bounds *section-placement* (spanwise
interpolation) error against converged-section AVL. It does **not** claim AVL is
reality — the vortex-lattice + strip-viscous model has its own error (the panelling
study put elevon power ~1.5% short of the truth). Every number here is
self-consistency to converged-section AVL. State this in the abstract.

> **CORRECTION found during execution (2026-07-30, kept for the record).**
> The G1a "placement-neutrality" criterion as originally written was WRONG and is
> superseded. Requiring uniform / adaptive / clustered to agree at N_ref conflates
> two different things: whether the reference is converged, and whether a
> deliberately non-uniform *candidate* has converged. Adaptive and clustered keep a
> non-uniform distribution at every N, so they need not match a dense uniform mesh
> even when that mesh is converged. Measured: at N_ref they differ from dense
> uniform by ~2–3% on `cd_ind` and this does **not** shrink with N.
>
> The correct legitimacy test is **G1b alone: Richardson convergence of DENSE
> UNIFORM in N.** Verified (2026-07-30): dense uniform is converged to
> **< 0.4%** between N=151 and N=201 on every key quantity (`cd_ind` 0.01–0.13%),
> so **uniform-201 is a legitimate reference**. The prior study's real error was a
> *sparse* (49-section) uniform reference, not uniformity itself.
>
> Two further execution facts that reshape the study:
> 1. **Separability of the section axis from the panel mesh is confirmed** — the
>    uniform→adaptive placement effect is 2.74% at c16s2u vs 3.04% at c8s1u
>    (≈ equal). So the reference is built on the cheap mesh **c8s1u**, where N≈201
>    is affordable (c16s2u caps at N≈92 under the 6000-vortex limit), and the
>    placement/count POLICY transfers to c16s2u. Stage 2 formalises this.
> 2. **Induced drag `cd_ind` is irreducibly ~2–3% section-placement-sensitive** even
>    at high N: different placements give different spanwise strip distributions and
>    AVL's Trefftz induced-drag integral depends on that distribution. `cd_ind` and
>    the near-print-floor `hinge_sym` are therefore reported as *placement-sensitive*
>    and are NOT held to the < 1% accuracy gate (§5 G3); forces, moments, stability
>    and control-surface derivatives do converge and carry the gate.

---

## 3. The quantities, angles, control states — FROZEN

**Quantity list:** identical to the panelling study §4.3 (drag, forces, stability,
control, hinge; 19 quantities) plus the derived `delta_trim`, `static_margin`,
`roll_power`. Normalisation scales = the panelling study's frozen Stage-0 medians;
do not recompute.

**Angles:** −2, 0, +4 for placement/decision stages; add +2 only in the
count-convergence stage (Stage 3) to form the ratio-2 chain. (AVL's influence
matrix is α-independent; placement error is expected weakly α-dependent — verify,
do not assume.)

**Control states — the control-surface part is central, treat it as such:**
- Validate placement at a **deflected** state (sym +4, diff +4). Antisymmetric
  loading has the highest spanwise wavenumber, so a placement proven adequate under
  differential deflection is **conservative** for the symmetric production sweep.
- Stage 8 re-tests at (0,0) and at the production symmetric sweep {−5,0,+5} to prove
  the placement choice does not depend on the control state (the transfer test,
  analogue of the panelling study's Stage 6b — which passed cleanly).
- The elevon band position/width is a DoE variable; a placement policy that only
  works for a centred band is useless. §6 extremes exercise narrow / wide / inboard
  / outboard bands.

**Aggregation rule (§4.6 analogue): WORST CASE.** Wherever a stage reduces errors to
one number, it is the **maximum over (design × angle × control state × the gated
quantities)** — never a mean that hides a bad corner. Report the argmax cell.

**Noise floor:** 1e-4 absolute; below it a quantity is assessed on normalised
discrepancy (error / frozen scale), never a runaway ratio. Same rule that caught the
false Cnb/α=0 failures in the panelling study.

---

## 4. Expressing complexity — the metric horse-race (Stage 5)

The core intellectual claim is *how to express geometric complexity so that it
predicts where sections buy accuracy.* Pre-register these candidate monitors and let
the reference-neutral truth pick the winner. Do **not** hand-tune after seeing the
answer.

- **M0 — uniform** (control; no complexity notion). Baseline every other monitor
  must beat to justify its existence.
- **M1 — ramp fraction** (scalar). `ramp_fraction(band)` — validated difficulty
  predictor (r=+0.964, DECISION-0011). Difficulty/budget only, cannot place.
- **M2 — geometric curvature equidistribution.** de Boor: ρ(y) ∝ (Σ_c |g_c″(y)|)^½
  over the 7 channels {x_le, z_le, chord, twist, t/c, camber, control_gain},
  **magnitude-preserving** (fixed physical reference scales — the corrected metric;
  the unit-integral normalisation that erased magnitude was the prior study's fatal
  bug — DO NOT reintroduce it). `spanwise_information_profile(...)`.
- **M3 — hybrid feature×goal (the new contribution).** Weight the geometric monitor
  by an **aerodynamic-influence** field w(y): ρ(y) ∝ (Σ_c |g_c″(y)| · w(y))^½.
  w(y) is the local sensitivity of the *outputs that matter* to the section there —
  the goal-oriented / output-based idea (literature: Hessian-metric feature
  detection × adjoint output weighting). Build w(y) cheaply from AVL-native fields on
  ONE coarse solve per design, e.g. |dΓ/dy| (spanwise loading gradient) and the
  control-influence kernel (∂CL_δe/∂(local section)), so nodes concentrate where the
  wing is *both* geometrically busy *and* aerodynamically loaded — leading-edge
  sweep breaks under load, the control band, the loaded mid-span; not a featureless
  tip that happens to be curved.
- **M4 — M3 + proper gradation limiter + hard nodes + budget selector.** A true
  cell-size-ratio limiter (bound adjacent-cell ratio ≤ g_max, e.g. 1.5–2.0), not the
  crude uniform-`floor` mixing; hard `must_include` at §1's mandatory nodes; and the
  budget rule of §7. This is the policy actually proposed for adoption.

**Gate G6 — predictivity (anti-circularity).** Each monitor's per-design difficulty
score must rank designs by their *actual* uniform-placement error (from Stage 3)
with Spearman ρ ≥ 0.7. A monitor that cannot predict difficulty may not be used as a
budget selector. (The prior `concentration()` score failed this at −0.82 — wrong
direction — and must be reported as a negative control, not used.)

---

## 5. The gates — fixed now, decision-relevant, do not adjust

All must hold on the 30 normal designs (extremes reported separately, §6). A policy
is **admissible** only if it passes every gate. Thresholds chosen to match the
downstream decision, not to be easy.

| # | Gate | Threshold | Why it is decision-relevant |
|---|---|---|---|
| G1 | Reference legitimacy | neutrality < 0.5%, Richardson band < 0.5% (§2) | Without it, no number below is truth |
| G2 | Hard-point fidelity | every mandatory node present at every N; ablation shows each node's omission costs > gate | A missed fixed-airfoil/control edge is a modelling error, not roundoff |
| G3 | Accuracy | worst-case < **1%** on {cl, cm, cd_ind, cd_total, x_np, elevon_sym.CL, elevon_sym.Cm, hinge_sym} vs the §2 reference | The coefficients feeding the optimiser |
| G4 | Control-authority preservation | sign kept on all 5 control derivs; \|bias\| ≤ 5% and scatter ≤ 5%-of-bias on elevon_sym.Cm & elevon_diff.Cl; **\|Δδ_trim\| ≤ 0.5°** every design/angle; 0 trim/stability label flips | Placement must not move a design across the feasibility boundary |
| G5 | DoE decision preservation | Spearman on l_over_d ≥ 0.98 (max rank displacement ≤ 4); top-10 retention 10/10; objective regret ≤ 0.5% | The policy serves a design sweep; ranking must survive |
| G6 | Complexity predictivity | difficulty score ranks Stage-3 error with ρ ≥ 0.7 | Licenses the metric as a budget selector (anti-circular) |
| G7 | Budget efficiency & safety | metric-selected N reaches G3 with **≤** the sections uniform needs (efficiency) and **never** returns an N that misses G3 (safety), worst-case | The "how many sections" deliverable |
| G8 | Gradation / no-starvation | max adjacent section-gap ratio ≤ 2.0; no region > (baseline gap × 2) unresolved | The prior study's catastrophic failure mode (4.4× gap starved the inboard) |
| G9 | Deflection transfer | G5 decision unchanged between (sym+4,diff+4) and (0,0) and the production sweep | Placement validated conservatively must transfer to production |
| G10 | Success | 100% of runs `status == SUCCESS` | — |

**Selection rule.** Among placement+count policies passing G2–G5, G8, choose the one
reaching the G3 tolerance at the **fewest sections** (cheapest end-to-end wall-clock,
measured honestly in Stage 9). That is the entire rule — it *is* the budget knee.

**If nothing passes:** do not lower a gate. Report that the design tier needs more
sections than hoped, or a better monitor, and state the cost. A conditional result
("adaptive pays only when uniform breaches the ramp criterion") is a legitimate
outcome — the prior study reached exactly that; this study must either confirm it on
a proper reference or overturn it.

---

## 6. Design set and extremes

**Normal:** the 30 `lhs30s2000` designs (reuse the panelling cache where the mesh
matches; new solves only for new section placements).

**Placement-stress extremes (reported separately; a failure here is a documented
limitation, not a disqualification):**
- `narrow_elevon`, `wide_elevon`, `inboard_elevon`, `outboard_elevon` — control-band
  position/width extremes (the boxcar-edge stress).
- `sharp_sweep_break` — max discontinuity in LE sweep (the geometric-kink stress).
- `high_taper` — fastest inboard chord change (the equidistribution-starvation
  stress that broke the prior metric).
- `high_ar`, `min_chord` — reuse the panelling extremes for continuity.
Also re-run the prior study's six cases (benign/nominal/narrow/wide/max_gradient/
max_ar) so the new reference can be compared head-to-head with DECISION-0011's
numbers.

---

## 7. Budget selection — deliver what the prior study punted

DECISION-0011 delivered placement at fixed N but **not** the count selector. Deliver
it here. The rule, pre-registered:

> Starting from the mandatory nodes, add sections by equidistributing the chosen
> monitor until the *predicted* interpolation error ≤ τ, where τ is calibrated once
> (Stage 5) so that predicted-error = τ corresponds to G3 (measured 1%) at the 90th
> percentile of the design set. Cap at N_max (strip/vortex limit at c16s2u).

Validate against G7: the selector must be **efficient** (≤ uniform's N for the same
accuracy) and **safe** (never under-count into a G3 miss). Report the N distribution
across the design set and the mean section saving.

---

## 8. Stages (execution order) and per-stage gate

| Stage | Name | Runs (order-of-mag) | Produces / gate |
|---|---|---|---|
| 0 | Lock inputs | ~40 | Freeze mesh=c16s2u, mandatory-node list per design, scales, gates, git SHA. Resolve any bwb.yaml inconsistency (esp. `spanwise.start/end_frac` 0.60/0.95 vs `elevon_bounds`). |
| 1 | Build & legitimise the reference | ~200 | Dense placements; **G1** neutrality + Richardson. The ground-truth stage — nothing downstream is interpretable until G1 passes. |
| 2 | Separability | ~120 | count ⊥ panel (licenses the c16s2u freeze); placement ⊥ deflection (interaction index < 0.2). |
| 3 | Count convergence (uniform) | ~200 | error vs N per design; the count knee; feeds G6 difficulty ranking. |
| 4 | Hard-point / control-edge ablation | ~150 | **G2**: omit each mandatory node, measure the penalty → proves the must_include set. |
| 5 | Complexity horse-race | ~150 | **G6**: which monitor predicts difficulty on the neutral reference; calibrate τ. `concentration()` as negative control. |
| 6 | Placement head-to-head @ fixed N | ~500 | **G3,G4,G8**: uniform vs M2 vs M3 vs M4, worst-case, full set × angles × control. |
| 7 | Budget selector | ~250 | **G7**: metric picks N; efficiency + safety. |
| 8 | DoE decision + deflection transfer | ~500 | **G5,G9**: the decisive ranking test; transfer to production control state. |
| 9 | Honest timings | ~30 | serial, cache-bypassed; sections drive build + strip cost; end-to-end for the selection rule. |

Extremes (§6) are run through Stages 4–8 and reported in their own tables, never
pooled into the normal-design statistics.

---

## 9. Method, provenance, plots — inherit the panelling study's discipline

- **Provenance hash** must now include the **full section-fraction vector** (not just
  N) and the placement-policy id — otherwise two placements at the same N collide in
  cache and silently return the wrong numbers. This is the direct analogue of the
  control-input hash bug the panelling study had to fix; assert it in Stage 0 with a
  two-placement hash-difference check before any solving.
- Reuse `run_pygeo_native_avl_case`, the subprocess-slice parallelism, and the
  §4.5 floor / GCI / worst-case machinery from `common.py`.
- **Plot rules** (identical to the panelling study §8): ≤ 4 lines / 5 bars per axes;
  label lines at the right end; a title that states the finding; matplotlib defaults;
  readable in three seconds. Mandatory plots: reference-neutrality spread (G1);
  error-vs-N knee (per complexity tier); monitor predictivity scatter (G6);
  placement head-to-head worst-case bars (G3); a *span map* per policy showing where
  sections land vs the loading/curvature (the money figure); budget-selector N
  distribution (G7); timings (G9).
- **Negative results are first-class.** If M3/M4 lose to uniform on easy wings (the
  prior study found this near the noise floor), report it plainly and keep the
  conditional rule. The AIAA-credible outcome is a *targeted* policy with stated
  limits, not "always adapt".

## 10. Stop conditions (§9 analogue)
STOP and report, do not work around, if: G1 cannot be met at affordable N_ref (the
reference is not truth); the provenance hash ignores the section vector; any stage
gate fails; or a cache hit's provenance does not match field-for-field.

---

## 11. What a successful study concludes (the shape of the answer)
A single table: for DoE use, the recommended **placement policy** and **budget rule**,
the worst-case accuracy it guarantees, the section saving vs uniform at equal
accuracy, and the explicit boundary — *where it helps (narrow bands, sharp breaks,
high taper), where it is neutral (benign wings near the floor), and where it must
escalate.* Plus the one defensible complexity scalar (expected: a magnitude-preserving,
aerodynamically-weighted curvature monitor; ramp fraction as the cheap difficulty
proxy) and the one that must not be used (`concentration()`). Honest, bounded,
reproducible — defensible at review.
