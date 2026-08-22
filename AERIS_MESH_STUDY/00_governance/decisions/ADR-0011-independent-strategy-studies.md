# ADR-0011 — Six Independent Strategy Studies, with Metrics and Ranking Frozen in Advance

Date: 2026-08-14
Status: Accepted (restructure agreed with the user on 2026-08-14)
Authority document: `AERIS_MESH_STUDY/RESTRUCTURE_PROMPT.md`

**Supersedes ADR-0006.**
Re-scopes RUNBOOK §7 Rounds A, B and C.
Amends ADR-0007 and ADR-0008 on the scope of `epsE_common_start`.
Leaves ADR-0001, 0002, 0003, 0004, 0005, 0009 and 0010 in force.

---

## 1. The objective this decision serves

**Deliver one structured meshing method that runs unattended, robustly, across the
production design space.** That is the deliverable. Independence, frozen metrics and
effort ledgers exist to make that method trustworthy — not to produce a
well-documented catalogue of failures.

Stage 02 was rigorous about recording what did not work and slow to produce something
that did. Both halves matter, but the working method is the point. If a strategy is
close to passing, the correct action is to finish it, not to write up why it nearly
worked.

**Success is defined as:** a strategy that passes every hard gate in §6 on all ten
geometries of the `round_c_lhs10_seed42` hold-out, at its own calibrated settings, with
laws that extend it to the full design space exploration.

## 2. Context — what Stage 02 actually compared

Stage 02 implemented S1, S3, S4 and S5 as variants of one shared module,
`04_strategy_prototypes/stage02_common.py`. The tip closure was written once, in that
module, and inherited by all of them.

The consequences, all measured and recorded in `status` §4:

- **S4 was bit-identical to S1.** Topology hash matched and the maximum node coordinate
  difference was exactly `0.000e+00` on all ten geometries
  (`s1_s4_identity_check.json`). S4's own analytic four-domain tip *was* built,
  measured, and rejected — splitting on the camber line degenerates at the LE and TE
  where the line has zero thickness, giving 51 folded cells at −0.2394, identical on all
  ten geometries — and it was then replaced by S1's closure. After that substitution S4
  no longer differed from S1 anywhere.
- **S3 shared S1's OML extraction and S1's tip closure**, differing only in spanwise
  splitting.
- **S5 was seeded from S1** and, once its pure frozen-RBF form failed fidelity by
  250–350×, reduced to "S1 with RBF in the free tip-cap interior only".
- All four therefore reported the **same** surface quality: worst scaled Jacobian
  +0.3250 (S5: +0.3249), max skewness 0.7893, on every geometry.

**The tournament compared one topology wearing four labels.** That is not a defect of
execution; it is a defect of design. A tournament whose entrants share the component
under test cannot discriminate between them.

Stage 02's measured results stand as recorded findings. This is a restructure, not a
reset: all Stage 00 governance, the Stage 01 TMR anchor, and every Stage 02 measurement
remain in the record.

## 3. Decision

**Each of the six strategies is implemented from scratch, in its own folder, developed
to the best state it can reach, and only then compared on metrics frozen in advance.**

New tree:

```
04_strategy_studies/
  COMMON_BRIEF.md          Stage 02 lessons, given to all six before any is built
  shared/                  the experimental control (§4)
  S0_cap4/                 implementation + STUDY.md + results + artifacts/
  S1_tip_first/
  S2_cross_field/
  S3_station_sweep/
  S4_analytic_multiblock/
  S5_frozen_rbf/
```

`04_strategy_prototypes/` is retained unchanged as the **archived Stage 02 record**. It
is not imported by any new study.

### 3.1 This ADR supersedes ADR-0006, and the reversal is deliberate

ADR-0006 recorded S0/cap4 as **failing the volume gate, recorded and not repaired**. Its
stated reason, quoted:

> All three of AERIS's legacy tip closures fail at the tip; `cap4` merely fails less
> visibly. Repairing it now would mean investing in the topology the tournament exists
> to replace.

**That reasoning is reversed here.** Under this ADR, **every strategy, including S0, is
developed to its best achievable state and then judged.**

The reason for the reversal is that ADR-0006's argument assumed the conclusion. It
declined to develop S0 *because* S0 was the topology to be replaced — but whether S0
should be replaced is precisely the question the tournament exists to answer. Leaving
one entrant undeveloped on the grounds that it is expected to lose makes the expected
outcome unfalsifiable.

Two facts make the reversal material rather than procedural:

1. **S0 is the only strategy that has ever produced a complete valid volume march.** On
   `lhs7_00` at the Stage 01 settings: min volume +2.11e−11, `passed: True`, 54 of 128
   layers containing negative-quality cells, first invalid layer *none*, max coordinate
   35.8 m against a march distance of 37.9 m. Every other strategy in this study had, at
   the time ADR-0006 was written, marched exactly nothing.
2. **The criterion on which S0 was judged worst turned out to be the wrong criterion.**
   ADR-0010 established that cell-size range and min-cell/`s0` predict marchability
   while scaled Jacobian does not. cap4's scaled Jacobian is +0.0046 — the worst in the
   study — and its cell-size range is 153×, which was **better than every S1 variant**
   until S1 was redistributed to 99×. S0 was ranked last on the metric that does not
   predict the outcome the study cares about.

ADR-0006's *measurements* stand: the 179.737° tip corner is real, structural, invariant
to `split_x_fore`, and present on all ten geometries; `mid4` and `split8` are genuinely
worse. What is withdrawn is the decision not to attempt a repair.

S0 is therefore an ordinary entrant under §7 of this ADR, with the same workflow, the
same effort accounting and the same gates as the other five. Its Stage 01 result is its
documented starting point, not its verdict.

### 3.2 Re-scoping RUNBOOK Rounds A, B and C

Stage 02's outcome — six strategies resolving to essentially one surviving surface
topology reached by several derivations — made the original Round A/B/C structure
inapplicable. It is re-scoped as follows. The *substance* of the rounds is preserved;
what changes is that each round now runs inside each independent study rather than
across a shared implementation.

| RUNBOOK | original | as re-scoped by this ADR |
|---|---|---|
| **Round A** — surface feasibility, 6 × 6 = 36 surface meshes, shared hard surface gates | one pass over all six strategies at once, after all six exist | **per-study, steps 2–3 of §7.** Each strategy clears the surface gates on the baseline and then on a widening subset of `lhs100_seed42`, before it marches anything. **The two ADR-0010 marchability metrics — staged cell-size range and min-cell/`s0` — are added to Round A**, because Stage 02 proved a surface can pass every stated surface gate and be unmarchable. |
| **Round B** — volume feasibility on baseline + the two worst-surface geometries; per-strategy epsE from a 3-geometry budget; frozen before Round C | 6 × 3 = 18 volumes | **per-study, steps 4–5 of §7,** and **widened**: the epsE ladder runs on the refinement subset rather than three geometries, and confirmation at a genuinely finer level is mandatory (§5.3). Stage 02 showed a 3-geometry budget is not enough — a value passing ten geometries at `smoke` still failed one at `fine`. The RUNBOOK's own principle that "a topology can legitimately require a different stable epsE" is retained and strengthened into §5. |
| **Round C** — best two strategies from Round B on baseline + 8 extremes + 10 fixed-seed LHS, selection on success rate then worst-case quality | two finalists, 2 × 19 = 38 meshes | **step 8 of §7: all strategies that reach freeze run the hold-out `round_c_lhs10_seed42` once, with no tuning.** Not two finalists — a field pre-narrowed to two by the same effort disparity §7.3 exists to expose would reintroduce the bias. The eight locked validation extremes are **deferred**, not cancelled: they are not yet generated, and adding a set now would give strategies frozen earlier a different hold-out from those frozen later. They return in Stage 04 for the winner. The RUNBOOK's selection order is replaced by §6.3, which keeps its priorities (gates first, then automatic success rate, then worst-case quality, then cost) and states them precisely. |

The ADflow RANS smoke run per Round C mesh (RUNBOOK §7) remains a Round C requirement
but is **not** a hard gate of this ADR. It is a Stage 09 validation activity and cannot
be a precondition for choosing a mesh topology, since a mesh must exist before it can be
solved on. This is a scope statement, not a relaxation: the solver gates in RUNBOOK §7
Round C still apply to the winner before Stage 04 freezes it.

## 4. The independence line

**Per-strategy. Written from scratch. No shared code, and no copying between strategy
folders.**

- all blocking and block-graph construction
- tip closure, in full
- spanwise distribution and station placement
- chordwise laws, point counts, clustering, distribution choice
- any smoothing, projection or deformation the method calls for
- the strategy's own choice of pyHyp-facing surface staging

**Shared, as the experimental control. One implementation, used by all six.**

- CAD/section ingestion: reading sections from the generator and mapping 2D curves to
  3D through the wing
- QC metric *definitions* — scaled Jacobian, shape metric, equiangle skewness,
  cell-size range, min-cell/`s0`
- gate thresholds
- the pyHyp invocation and its argument construction
- the geometry sets
- the verifier

**Rationale.** Geometry is generated the same way for every strategy; how each turns it
into blocks is the experiment. If each study writes its own section reader and its own
quality metric, the comparison measures readers and metrics rather than meshing
methods.

**This line is not re-litigated mid-study.** If a strategy genuinely cannot work within
it, that is recorded as a finding and raised with the user — not resolved by quietly
copying shared code into the strategy folder or a strategy's code into `shared/`.

### 4.1 Migration: S1's tuning is stripped out of the shared module

`04_strategy_prototypes/stage02_common.py` is **not** a clean shared module. Stage 02
baked S1's blocking decisions into it as defaults. Migrating it unchanged would hand
every strategy S1's answers and silently recreate the problem this restructure exists to
fix.

**Moved into `S1_tip_first/` as S1's private implementation:**

| symbol | why it is per-strategy |
|---|---|
| `butterfly_from_ring` (with `width_frac`, `chord_inset`, `collar_points`) | tip closure |
| `oml_tip_ring_2d` | tip staging |
| `butterfly_cap_2d` | S1 cap internals (Stage 02 negative result, retained) |
| `map_2d_patch_to_tip` | S1 cap internals |
| `camber_and_thickness` | S1 cap internals |
| `realise_spanwise_law` | spanwise distribution |
| `geometric_progression_counts` | spanwise distribution |
| `_point_at_x`, `_arc_between_x`, `_closed_arclength_fractions`, `_match_closed_parameterisation` | helpers used only by the above |

**Kept shared, with defaults stripped:**

| symbol | change |
|---|---|
| `section_loop_2d` | unchanged — ingestion |
| `feature_split_sides` | **`distribution` and `te_base_points` are now required keyword arguments with no defaults.** `distribution` is a chordwise law and therefore per-strategy; the shared function must not choose. `te_base_points` sets the TE-base point count, which is a chordwise allocation. |
| `qc_blocks`, `orient_blocks_consistently`, `orient_patches_2d`, `worst_corner_angle_deg`, `spanwise_interpolation_error`, `write_surface_artifacts` | unchanged |
| `winslow_smooth_2d` | unchanged — a generic operator, available to all |
| `verify_strategies.py`, `export_for_paraview.py`, the pyHyp invocation | unchanged in substance, generalised to take any strategy |

**Metric definitions and gate thresholds migrate unchanged**, so results stay comparable
to what is already recorded.

## 5. epsE is per-strategy

### 5.1 The rule

Each strategy is marched on the same declared ladder **`{1.5, 2.0, 3.0}`**, with
`epsI = 2 × epsE`. Each finds its own highest value passing **all** geometries of its
refinement set. Strategies are compared at **each one's own best value**.

**The ladder is not extended after a failure** without a further ADR stating the
physical reason. ADR-0008 §6 (stop and report, do not extend) remains in force.

**Rationale.** A value calibrated on S1's cell distribution would rig the comparison
against methods with different distributions. RUNBOOK §7 Round B already anticipated
this: "A topology can legitimately require a different stable `epsE`; allowing the same
small calibration budget for every pyHyp strategy is fairer than forcing one universal
value."

### 5.2 `epsE_common_start` as a single global constant no longer applies

ADR-0007 re-based `epsE_common_start` to Stage 02 and made S1 its host, by an
implementation order fixed in advance. That produced a real, protocol-compliant number
— but it is **S1's number**, calibrated on S1's surface, and it has no standing as a
starting value for a method with a different cell distribution.

`epsE_common_start` is therefore **withdrawn as a global constant** and retained only as
S1's per-strategy value. The identifier should not appear in any other strategy's
configuration. ADR-0008's *protocol* — ladder fixed in advance, calibration then
confirmation at a genuinely finer level, hard gate `> 0`, highest-passing selection,
stop-do-not-extend — is unchanged and applies to each strategy separately.

Superseded record, kept so the trail is legible: `epsE_common_start = 2.0` appears in
older records. It passed all ten calibration geometries at `smoke` and then **failed
`lhs7_01` at `fine`** at min quality −0.210. It is superseded and must not be reused.

### 5.3 S1's carried-forward state

Carried forward as S1's **starting point, not as a settled constant**:

| level | epsE 1.5 | epsE 2.0 | epsE 3.0 |
|---|---:|---:|---:|
| `smoke` (N=129, coarsen=1) | 10/10 | 10/10 | 7/10 |
| **`fine` (N=193, coarsen=1)** | **10/10** | 9/10 (lhs7_01, −0.210) | 6/10 |

**S1's own value is `epsE = 1.5`.** At `fine`, all ten geometries gave 0 bad layers and
min quality +0.103 to +0.250. Note the ordering is monotonic in the *opposite* direction
from the usual expectation: less dissipation is uniformly better here.

S1 must still re-derive this under the new structure, because its implementation is
being rewritten from scratch and its cell distribution may not be identical.

### 5.4 Confirmation level

Confirmation is at a **genuinely finer** level and this must be verified, not assumed.
The `L*` family uses `coarsen=4`; only `smoke → fine → production` is a refinement
ladder at full surface resolution. ADR-0008 originally named `L4` (N=37, coarsen=4),
which is *coarser* than the `smoke` calibration and would have confirmed nothing. That
error is recorded in ADR-0008 and repeated here so it cannot recur.

## 6. Frozen comparison metrics and ranking rule

**Frozen by this ADR, before any strategy is implemented or optimised.** Nothing in this
section may be chosen, reweighted or relaxed after seeing results.

### 6.1 Hard gates — pass/fail, every geometry, no partial credit

Surface:

1. geometry fidelity ≤ **0.01% of local chord** (mesh vs generated OML, measured
   point-to-*segment* against a **closed** reference contour)
2. watertight, with conformal block interfaces
3. **consistent outward normals**, verified by edge-propagated orientation and a
   positive enclosed signed volume
4. `min_scaled_jacobian > 0`
5. deterministic **block count and connectivity signature** across all geometries.
   Node positions, spacing and permitted counts may adapt to geometry (RUNBOOK §2.1);
   dimension variation is reported, not gated.
6. correct boundary families

Volume:

7. pyHyp completes; **zero inverted cells and zero negative-volume cells**
8. **min scaled quality strictly > 0**
9. deterministic cell and block counts
10. correct boundary families on the volume mesh

Process:

11. **no per-geometry manual repair** — the same code, the same settings, every geometry
12. **confirmed at a genuinely finer level** (§5.4), with the level verified to be finer

`0.30` remains a **ranking target, not a gate.** The frozen hard gate is `> 0`.

### 6.2 Reported for every strategy, whether or not it gates

- worst-case and median volume min scaled quality
- staged cell-size range and min-cell/`s0`
- surface min scaled Jacobian, max equiangle skewness
- block count and total cell count
- epsE selected, and the pass count at each ladder rung
- **robustness: the fraction of HOLD-OUT geometries passing at first attempt without
  escalation**
- wall-clock per march
- **the per-strategy effort ledger** (§7.3)

The effort ledger is a **reported metric**, not an internal note. It appears in every
comparison table alongside the results.

### 6.3 Ranking rule

1. A strategy must pass **every** hard gate on **every** hold-out geometry. Failures are
   **unranked** — not ranked last.
2. Among those passing: rank on **robustness measured on the hold-out set**. The
   deliverable is thousands of unattended runs, so first-attempt success is the property
   that matters most.
3. Tie-break on **worst-case volume min scaled quality** — worst-case, not baseline and
   not average.
4. Then **total cell count**.
5. Then **runtime**.

**Robustness is measured on the hold-out, never on the refinement set.** A strategy
developed over three sessions will have a higher first-attempt rate on the geometries it
was tuned against, which would make the top-ranked criterion a proxy for effort — the
very bias §7.3 exists to neutralise.

### 6.4 The no-winner rule, fixed now

**If no strategy passes every hard gate on every hold-out geometry:** nothing is
silently relaxed. The study reports **no winner**, ranks the field on **nearest-miss**
— fewest failing geometries, then worst-case volume min scaled quality — and raises it
to the user as a decision.

Choosing this rule after seeing results is not permitted. It is fixed here for that
reason.

## 7. Per-strategy workflow, effort control, and geometry sets

### 7.1 Workflow — identical for all six

Each folder `04_strategy_studies/S<N>_<name>/` contains its implementation, its own
`STUDY.md` log, its own results JSON, and its own `artifacts/` subfolder.

1. **Read the source.** Implement as the paper specifies. Record in `STUDY.md` **what
   the paper states versus what had to be invented** — papers omit failure modes, and
   this distinction determines whether the study tested the method or one reading of it.
2. **Baseline geometry.** Get it building and marching on one geometry. Cheapest
   possible failure first.
3. **Refinement set.** Extend to a subset of `lhs100_seed42`, then widen.
4. **epsE ladder** on the refinement set; select the strategy's own value (§5).
5. **Finer-level confirmation** at that value (§5.4).
6. **Report and wait.** State where the strategy stands and what the next action would
   be.
7. **Freeze** on the user's signal. Record final state; close its ledger entry.
8. **Hold-out run** on `round_c_lhs10_seed42`, once, no tuning.

**Strategy order: S0, S1, S2, S3, S4, S5.** Declared in advance so it cannot be
reordered after seeing results.

**S2 feasibility is resolved early, in parallel with S0** — not when its turn arrives.
It is a paper exercise and it determines whether this is a five- or six-entry
tournament. The question: does a cross-field quad layout map to structured multiblock
that pyHyp can march and CGNS can carry with per-block families? Per ADR-0009 the real
gap is not the uninstalled packages (`igl`, `QEx`, `meshio`, `shapely`) but the
quad-layout-to-structured-block decomposition, which none of them supplies. If no route
exists, S2 is formally deferred in an ADR extending ADR-0009. If one exists, S2 gets the
same treatment as the others.

### 7.2 The user decides when a strategy is done

**No fixed effort budget is declared in advance.** Claude Code does not decide to stop
and does not decide to keep going: it reports the strategy's state and waits.

- When a strategy reaches a plateau — passing, or failing with a **diagnosis** rather
  than a guess — **report and stop.** No new construction attempt is opened without the
  user saying to continue.
- **No strategy is started, and no strategy is frozen, without an explicit user signal.**
- If the next reasonable action is a **guess** rather than a measured hypothesis, say so
  plainly and stop. Stage 02 spent about fifteen attempts inside one wrong diagnosis.
  The failure mode to avoid is continuing to search when neither the instrument nor the
  cause has been established.

### 7.3 Effort is not capped, so it is measured

Unequal attention is the largest threat to the validity of this comparison. Parity
cannot be *enforced* under user-signalled advancement, so it is made **visible**.

A **per-strategy effort ledger** is maintained in `status`, recording:

- distinct construction attempts
- sessions
- wall-clock
- marches run
- one line on what each attempt changed

The ledger is reported alongside results in every comparison table (§6.2). The final
report **states the effort disparity explicitly and assesses whether it could plausibly
account for the ranking.** If Claude Code judges that a strategy is being under- or
over-developed relative to the others, it says so **at the time**, not after the
comparison.

### 7.4 Geometry sets

| set | role under this ADR |
|---|---|
| `lhs100_seed42` (lhs_v1, seed 42, n=100) | **development and refinement.** Baseline geometry first, then a subset, then widen. Cheap failures first. |
| `round_c_lhs10_seed42` (lhs_v1, seed 42, n=10) | **final comparison — hold-out. No strategy sees this set during development.** It is currently untouched and stays that way. This is what makes the winner defensible. |
| `epse_calibration_lhs10_seed7` (lhs_v1, seed 7, n=10) | **role changed.** It was Stage 02's development and epsE-calibration set. Development now uses `lhs100_seed42` (§7.4 row 1), so this set is retained as the basis of the recorded Stage 01 and Stage 02 evidence — including S1's carried-forward epsE result in §5.3 — and is **not** the development set for the new studies. It remains permitted for tuning and remains disjoint from the hold-out, so a strategy may use it for a like-for-like comparison against a recorded Stage 02 number; doing so must be declared in that strategy's `STUDY.md`. |

Set identity is the quadruple (sampler id, seed, n, geometry-config sha256), per
ADR-0001. A seed alone is not an identifier.

**No tuning of any kind on `round_c_lhs10_seed42`.**

## 8. Consequences

- `04_strategy_studies/COMMON_BRIEF.md` is written **before** any strategy
  implementation, so no strategy has a hindsight advantage. Its §10 amendment rule
  requires re-checking already-completed strategies against later additions.
- ADR-0006's decision not to repair S0 is withdrawn; S0 is developed like any other
  entrant. Its measurements stand.
- `epsE_common_start` ceases to exist as a global constant (§5.2).
- Stage 02's strategy *ranking* was already void under ADR-0010 (measured on the wrong
  criterion). This ADR replaces the structure that produced it.
- Stage 02 does **not** claim its gate. `stage_status.json` stays at
  `active_stage 02`, `state IN_PROGRESS`. The restructure is Stage 02 work, not a new
  stage, and no stage gate is claimed without the user's approval token.
- The eight locked Round C validation extremes remain ungenerated and are deferred to
  Stage 04 for the winner (§3.2).
- `04_strategy_prototypes/` becomes a read-only archive. New studies do not import from
  it.

## 9. Evidence

- `AERIS_MESH_STUDY/status` §4 (Stage 02 results), §5.3 (S1≡S4 identity), §5D–5H
  (marchability reframing, canary, epsE calibration and confirmation)
- `AERIS_MESH_STUDY/RESTRUCTURE_PROMPT.md` — the agreed restructure brief
- `AERIS_MESH_STUDY/04_strategy_studies/COMMON_BRIEF.md`
- ADR-0006 (superseded here), ADR-0007, ADR-0008, ADR-0009, ADR-0010
- `04_strategy_prototypes/s1_s4_identity_check.json` (regenerable; deleted with the
  Stage 02 artifacts, result recorded in `status` §5.3)
- `03_cap4_epse/*.json` — Stage 01 cap4 march evidence, retained
