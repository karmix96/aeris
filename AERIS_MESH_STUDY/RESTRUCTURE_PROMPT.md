# AERIS Mesh Study — restructure to six independent strategy studies

Paste this into a new Claude Code session. Read `AERIS_MESH_STUDY/status` and
`AERIS_MESH_STUDY/RUNBOOK.md` first; this document assumes both and supersedes the
Stage 02 structure described there.

---

## 0. The objective

**Deliver one structured meshing method that runs unattended, robustly, across the
production design space.** That is the deliverable. Everything below — the
independence, the frozen metrics, the ledgers — exists to make that method
trustworthy, not to produce a well-documented catalogue of failures.

Stage 02 was rigorous about recording what did not work and slow to produce
something that did. Both halves matter, but the working method is the point. If a
strategy is close to passing, the right move is to finish it, not to write up why
it nearly worked.

**Success looks like:** a strategy that passes every hard gate on ten unseen
geometries at its own calibrated settings, with laws that extend it to the full DSE.

## 0.1 What changes and why

Stage 02 ran the six strategies as variants of a shared implementation. The tip
closure was built once and inherited by all of them, so S3, S4 and S5 converged on
S1's cap and scored identically. S4's own analytic tip was built, measured, rejected,
and replaced by S1's. The tournament compared one topology wearing four labels.

**New structure: six independent studies.** Each strategy is implemented from scratch
in its own folder, developed to the best state it can reach, and only then compared
on metrics frozen in advance.

This is a restructure, not a reset. All Stage 00/01 governance stands. Stage 02's
measured results stand as recorded findings.

---

## 1. First task — ADR-0011, the restructure decision

Write `00_governance/decisions/ADR-0011-independent-strategy-studies.md` before any
implementation. It must contain everything in sections 2–7, and must:

- **supersede ADR-0006**, which recorded S0/cap4 as failed-not-repaired on the grounds
  that repairing the control meant investing in the topology the tournament exists to
  replace. The new design says the opposite: every strategy, including S0, is
  developed to its best achievable state and then judged. State the reversal and its
  reason explicitly. Do not silently change course.
- **re-scope Round A/B/C** in RUNBOOK terms to match the new structure.
- **restate epsE handling** — see §5. `epsE_common_start` as a single global constant
  no longer applies; it was calibrated on S1's surface.

**STOP CONDITION:** no strategy implementation begins until ADR-0011 exists.

---

## 2. The independence line

**Per-strategy, written from scratch, no shared code:**

- all blocking and block-graph construction
- tip closure, in full
- spanwise distribution and station placement
- chordwise laws, point counts, clustering, distribution choice
- any smoothing, projection or deformation the method calls for
- the strategy's own choice of pyHyp-facing surface staging

**Shared, as experimental control — one implementation, used by all six:**

- CAD/section ingestion: reading sections from the generator and mapping 2D curves to
  3D through the wing
- QC metric *definitions* (scaled Jacobian, shape metric, skewness, cell-size range,
  min-cell/`s0`)
- gate thresholds
- the pyHyp invocation and its argument construction
- the geometry sets
- the verifier

Geometry is generated the same way for every strategy; how each turns it into blocks
is the experiment. If each study writes its own section reader and its own quality
metric, the comparison measures readers and metrics rather than meshing methods.

**Do not re-litigate this line mid-study.** If a strategy genuinely cannot work within
it, record that as a finding and raise it, rather than quietly copying shared code
into the strategy folder.

---

## 3. The common brief — given to all six before any is built

Write `04_strategy_studies/COMMON_BRIEF.md`. Stage 02's lessons are general knowledge,
not S1's private advantage; building S0 naive and S5 fully-informed would bias the
result toward whatever was built last. Minimum contents:

1. **Inner boundaries must be constructed from the section, not by displacing the
   outer ring.** `inner = camber + width_frac × (surface − camber)` is a convex
   combination and lies inside the section by construction. About fifteen
   constructions that displaced the outer ring — shrink, smooth, camber-offset,
   bisector offset, arc-length re-parameterisation — all failed the same way.
2. **Chordwise inset of inner rectangles** stops collar end edges running collinear
   with the rectangle's short sides, which degenerates corner cells to zero Jacobian.
3. **Cell-size range and min-cell/`s0` predict marchability; scaled Jacobian does
   not.** A surface at `+0.3250` with a 3462× range exploded to 1e+24 m; the same
   surface at 99× marched clean. cap4 marches at `+0.0046` with a 153× range. This
   was missed for an entire stage.
4. **Consistent outward normals is a real gate.** pyHyp rejects the surface at input
   with `ERROR: Normal directions may be wrong`. Watertight plus positive Jacobian is
   not sufficient. Per-block winding checks cannot see it; orientation must be
   propagated across shared edges.
5. **Verify the verifier.** Five instrument bugs were found in Stage 02, each
   reporting a false failure on a sound mesh: point-sampled instead of segment
   distance; an open reference contour excluding the blunt base; watertightness tested
   in the wrong direction; tip-edge nodes taken from every block's outboard edge;
   determinism hashing block dimensions when the runbook freezes connectivity.
6. **Identical failure across independent strategies indicates shared infrastructure,
   not four hard problems.**
7. **Refinement is not uniformly harder.** At the finer level 8 of 10 geometries
   improved and 2 degraded — geometry-specific, not a global margin.
8. **A working implementation may already exist in git history.** The tip closure that
   works came from commit `bfaeaf1`. Read the repository before opening a parameter
   search.

**Rule:** anything *general* learned during a strategy is added to this brief, and
every already-completed strategy is re-checked against the addition. Anything
method-specific stays inside that strategy. Record which, each time.

---

## 4. Effort control — the user decides when a strategy is done

**The user signals when a strategy is finished.** No fixed budget is declared in
advance. Claude Code does not decide to stop and does not decide to keep going: it
reports the strategy's state and waits.

- When a strategy reaches a plateau — passing, or failing with a diagnosis rather
  than a guess — **report and stop.** Do not open a new construction attempt without
  the user saying to continue.
- **Never advance to the next strategy without an explicit user signal.**
- If the next reasonable action is a guess rather than a measured hypothesis, say so
  plainly and stop. Stage 02 spent about fifteen attempts inside one wrong diagnosis.
  The failure mode to avoid is continuing to search when neither the instrument nor
  the cause has been established.

**Because effort is not capped, it must be measured.** Unequal attention is the
largest threat to a valid comparison. Parity cannot be enforced under user-signalled
advancement, so it is made visible instead:

- Maintain a **per-strategy effort ledger** in `status`: distinct construction
  attempts, sessions, wall-clock, marches run, and one line on what each attempt
  changed.
- The ledger is reported alongside results in every comparison table — a reported
  metric (§6), not an internal note.
- The final report states the effort disparity explicitly and assesses whether it
  could plausibly account for the ranking.
- If Claude Code judges a strategy is being under- or over-developed relative to the
  others, it says so at the time, not after the comparison.

---

## 5. Geometry sets and epsE

**Development and refinement:** `lhs100_seed42`. Baseline geometry first, then a
subset, then widen. Cheap failures first.

**Final comparison:** `round_c_lhs10_seed42`, the hold-out. **No strategy sees this
set during development.** It is currently untouched — keep it that way. This is what
makes the winner defensible.

**epsE is per-strategy, not global.** Each strategy is marched on the same declared
ladder `{1.5, 2.0, 3.0}`; each finds its own highest value passing all geometries;
strategies are compared at each one's own best value. A value calibrated on S1's cell
distribution would rig the comparison against methods with different distributions.
The ladder is not extended after a failure without an ADR stating the physical reason.

**S1's current state, carried forward as its starting point, not as a settled
constant:** calibrated at `smoke` all three values passed all ten; confirmed at the
genuinely finer level `fine` (N=193, coarsen=1), **epsE 1.5 passes 10/10, 2.0 passes
9/10, 3.0 passes 6/10**. So S1's own value is **1.5**. Note `epsE_common_start = 2.0`
appears in older records — it failed finer-level confirmation on `lhs7_01` at min
quality −0.210 and was superseded.

---

## 6. Frozen comparison metrics and ranking rule

Written into ADR-0011 **before any strategy is optimised**.

**Hard gates — pass/fail, all geometries, no partial credit:**

- geometry fidelity ≤ 0.01% local chord
- watertight, conformal interfaces
- consistent outward normals
- `min_scaled_jacobian > 0` (surface)
- deterministic block count and connectivity across all geometries
- pyHyp completes; zero inverted and zero negative-volume cells; **min scaled quality
  strictly > 0** (volume)
- correct boundary families; deterministic cell and block counts
- no per-geometry manual repair
- confirmed at a genuinely finer level — **verify the level actually is finer.** The
  `L*` family uses `coarsen=4`; only `smoke → fine → production` is a refinement
  ladder at full surface resolution. ADR-0008 originally named `L4`, which is coarser.

**Reported for every strategy, whether or not it gates:**

- worst-case and median volume min scaled quality
- staged cell-size range and min-cell/`s0`
- surface min scaled Jacobian, max skewness
- block count and total cell count
- epsE selected, and pass count at each ladder rung
- **robustness: fraction of HOLD-OUT geometries passing at first attempt without
  escalation** (see ranking note below)
- wall-clock per march
- **effort ledger** (§4)

**Ranking rule, frozen now:**

1. Must pass every hard gate on every hold-out geometry. Failures are unranked.
2. Among those passing: rank on **robustness measured on the hold-out set**, because
   the deliverable is thousands of unattended runs.
3. Tie-break on worst-case volume quality.
4. Then cell count, then runtime.

**Robustness is measured on the hold-out, never on the refinement set.** A strategy
developed over three sessions will have a higher first-attempt rate on the geometries
it was tuned against, which would make the top-ranked criterion a proxy for effort —
the very bias §4 exists to neutralise.

**If no strategy passes every hard gate on every hold-out geometry:** do not silently
relax anything. Report no winner, rank the field on nearest-miss (fewest failing
geometries, then worst-case volume quality), and raise it as a decision for the user.
Choosing this rule after seeing results is not permitted.

`0.30` remains a **ranking target, not a gate**. The frozen hard gate is `> 0`.

---

## 7. Per-strategy workflow — identical for all six

Folder `04_strategy_studies/S<N>_<name>/` containing implementation, its own
`STUDY.md` log, its own results JSON, and its own artifacts subfolder.

1. **Read the source.** Implement as the paper specifies. Record in `STUDY.md` what
   the paper states versus what had to be invented — papers omit failure modes, and
   this distinction determines whether the study tested the method or one reading of
   it.
2. **Baseline geometry.** Get it building and marching on one geometry. Cheapest
   possible failure first.
3. **Refinement set.** Extend to a subset of `lhs100_seed42`, then widen.
4. **epsE ladder** on the refinement set; select the strategy's own value.
5. **Finer-level confirmation** at that value.
6. **Report and wait.** State where the strategy stands and what the next action
   would be. The user signals whether to continue or freeze.
7. **Freeze** on the user's signal. Record final state, close its ledger entry.
8. **Hold-out run** on `round_c_lhs10_seed42`, once, no tuning.

**Strategy order: S0, S1, S2, S3, S4, S5** — declared in advance so it cannot be
reordered after seeing results.

**S2 feasibility is resolved early, in parallel with S0**, not when its turn arrives.
It is a paper exercise costing about an hour and it determines whether this is a five-
or six-entry tournament. The question: does a cross-field quad layout map to
structured multiblock that pyHyp can march and CGNS can carry with per-block
families? `igl / QEx / meshio / shapely` are uninstalled, but the real gap is the
quad-layout-to-structured-block decomposition, which none of them supplies. If no
route exists, formally defer in an ADR. If one exists, it gets the same treatment as
the others.

**S0 note:** it starts with a genuine advantage — the only strategy that has ever
produced a complete valid volume march (54/128 bad layers, positive min volume,
`passed: True`). Its Stage 01 result is a documented starting point, not a verdict.

---

## 8. Migration — strip S1's tuning out of the shared module

`04_strategy_prototypes/stage02_common.py` is **not** a clean shared module. Stage 02
baked S1's blocking decisions into it as defaults. Migrating it unchanged would hand
every strategy S1's answers and silently recreate the problem this restructure exists
to fix.

**Move to S1's folder (these are per-strategy under §2):**

- `butterfly_from_ring` — tip closure, with `width_frac`, `chord_inset`,
  `collar_points`
- `oml_tip_ring_2d` — tip staging
- `realise_spanwise_law`, `geometric_progression_counts` — spanwise distribution
- `butterfly_cap_2d`, `map_2d_patch_to_tip`, `camber_and_thickness` — S1 cap internals

**Keep shared, but strip the defaults:**

- section ingestion and 2D→3D mapping — **with no chordwise distribution default at
  all.** `feature_split_sides` currently defaults to `distribution="uniform"`, which
  is a chordwise law and therefore per-strategy. Each study must pass its own
  explicitly; the shared function must not choose.
- `qc_blocks`, `orient_blocks_consistently`, `orient_patches_2d`,
  `spanwise_interpolation_error`, `winslow_smooth_2d` (a generic operator, available
  to all)
- `verify_strategies.py`, `export_for_paraview.py`, the pyHyp invocation

Metric definitions and gate thresholds migrate **unchanged**, so results stay
comparable to what is recorded.

---

## 9. Status discipline — for Codex cross-check

`status` is the shared record; Codex reads it to audit.

- **Update `status` before and after every task**, per its own Protocol section.
- `00_governance/stage_status.json` remains the authoritative gate state.
- **Report what was measured, not what it implies.** A surface prototype that has not
  marched is not a working strategy. Do not write "N of 6 working" unless N have
  passed the hard gates end to end.
- **Contradictions are defects.** Stage 02's `status` showed S3 failing determinism
  and declared "0 hard-gate failures" three lines later.
- **Record negative results in full** — rejected constructions, failed confirmations,
  instrument bugs. These are the study's evidence, not its embarrassments.
- **Record errors rather than quietly patching them.** The `CONFIRMATION_LEVEL = "L4"`
  mistake was caught and written down; that is the standard.
- Maintain the per-strategy **effort ledger** (§4) so Codex can audit disparity at a
  glance.

---

## 10. Immediate sequence

1. Collect Stage 02 experience into `COMMON_BRIEF.md` (§3).
2. Write ADR-0011 (§1), including effort control (§4), metrics and ranking (§6), and
   the no-winner rule.
3. Create `04_strategy_studies/` with six folders and the shared control module,
   migrated per §8 with S1's defaults stripped out.
4. Start S0 **and** the S2 feasibility question (§7) together.

**Do not begin step 4 before steps 2 and 3 are complete and `status` reflects them.**

---

## 11. Standing invariants

- No stage gate is claimed without the user's approval token. Never self-approve.
- **No strategy is frozen and no strategy is started without an explicit user
  signal.** Report state and wait.
- No tuning of any kind on `round_c_lhs10_seed42`.
- Heavy compute is prepared as commands for the user to launch, not run in-session,
  unless the user explicitly overrides — and if they do, note the override.
- The test suite must pass after every task (currently 182 tests across `tests/mesh`
  and `tests/cfd`); any change to its size is recorded. If a task breaks tests, stop
  and report rather than adapting the tests.
- Findings live in tracked folders, never `data/` or `/tmp`.
- Any deviation from this document requires an ADR, not a decision in the moment.
