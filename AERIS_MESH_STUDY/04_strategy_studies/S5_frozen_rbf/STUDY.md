# S5 — frozen topology with RBF deformation

**Status:** NOT STARTED — awaiting the user's signal (ADR-0011 §7.2)
**Strategy ID:** `S5_FROZEN_RBF`
**RUNBOOK source:** §6 S5 — Frozen topology with RBF deformation
**Order in the tournament:** 6 of 6 (order declared in advance, ADR-0011 §7.1)

Read `../COMMON_BRIEF.md` in full before writing a line of implementation. It is
prior knowledge available to every strategy, so no entrant wins on hindsight.

Read `../shared/__init__.py` for the independence line. Everything about **how this
strategy blocks the wing** is written here, from scratch. Nothing is copied from
another strategy folder, and nothing from here is pushed into `shared/`.

---

## 1. What the paper states, versus what had to be invented

*ADR-0011 §7.1 step 1. Papers omit failure modes, and this distinction is what
decides whether the study tested the method or one reading of it. Fill this in
while implementing, not afterwards.*

| aspect | the source specifies | had to be invented here | why |
|---|---|---|---|
| | | | |

**Source read:**

---

## 2. Construction log

*One entry per distinct construction attempt. This is the raw material of the
effort ledger (§5) — an entry here is an entry there.*

| # | date | what changed | measured outcome | kept? |
|---:|---|---|---|---|
| | | | | |

---

## 3. Results

### 3.1 Baseline geometry (step 2)

### 3.2 Refinement set — subset of `lhs100_seed42`, then widened (step 3)

### 3.3 epsE ladder on the refinement set (step 4)

| epsE | geometries passing | worst min quality |
|---:|---:|---:|
| 1.5 | | |
| 2.0 | | |
| 3.0 | | |

**Selected epsE:** — · selection rule: highest value passing every geometry; the
ladder is never extended after a failure (ADR-0008 §6, ADR-0011 §5.1).

### 3.4 Finer-level confirmation (step 5)

Confirmation runs at `fine` (N=193, coarsen=1) against calibration at `smoke`
(N=129, coarsen=1). **Verify the level actually is finer** —
`shared.pyhyp_runner.level_is_finer` enforces it. The `L*` family is coarsen=4 and
is not a refinement of `smoke`.

### 3.5 Hold-out run (step 8) — `round_c_lhs10_seed42`, once, no tuning

**Not run until the user's freeze signal.** `shared.geometry_sets` refuses this set
unless the caller states the strategy is frozen.

---

## 4. Negative results

*Recorded in full — rejected constructions, failed confirmations, instrument bugs.
These are the study's evidence, not its embarrassments. A rejected construction
that is not written down gets rebuilt by someone later.*

---

## 5. Effort ledger

*ADR-0011 §7.3. Effort is not capped, so it is measured. This is a REPORTED metric
and appears in every comparison table alongside the results.*

| metric | value |
|---|---:|
| distinct construction attempts | 0 |
| sessions | 0 |
| wall-clock | 0 |
| marches run | 0 |

Mirrored into `status`. If this strategy is being under- or over-developed relative
to the others, say so **at the time**, not after the comparison.

---

## 6. State and next action

**Where this strategy stands:** not started.

**What the next action would be:** re-implement from scratch, on its own frozen topology rather than seeded from another strategy's mesh. COMMON_BRIEF §9.6 is the governing measurement: deformation alone left the surface 2.35–3.50% of chord off target against a 0.01% gate, with machine-zero landmark residual, so projection to prescribed CAD is mandatory rather than a refinement.

**Report and wait.** No new construction attempt is opened, and no freeze is
declared, without an explicit user signal (ADR-0011 §7.2).
