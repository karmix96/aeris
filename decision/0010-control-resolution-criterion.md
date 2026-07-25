# DECISION-0010 — The control-resolution criterion supersedes tuned panel counts

Status: ACCEPTED
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/discretisation_master_study.md`,
`configs/aero/discretisation_robustness_evidence/`
Amends: DECISION-0009 (the numbers stand; the *reason* for them is replaced)

## Decision

The binding discretisation error in the low-fidelity chain is **resolution of the
control surface**, not of the wing. It is governed by one criterion in two
directions, and that criterion — not a tuned panel count — is what must be
satisfied for any design:

```
chordwise:  N_flap  ≥ 6          panels aft of the hinge
spanwise:   ramp fraction ≲ 15 % (width of the gain-ramp intervals just
                                  outside the band edges) / (band width)
```

**Why a criterion rather than a number.** `nchordwise = 24` is not a physical
constant; it is whatever happens to give N_flap ≥ 6 at the hinge positions this
DoE samples. A design outside that range needs a different count, and the
criterion says which. The production numbers in DECISION-0009 remain correct **as
the setting that satisfies this criterion across the current design space**.

## The mechanism, and the hypothesis it replaces

AVL smears a control surface at its edges — chordwise where the hinge falls
mid-panel, spanwise where the control gain ramps from 1 to 0 over the interval
outside each band edge. The error is set by how much of the control that smearing
occupies:

| direction | law | fit |
|---|---|---|
| chordwise | CL_δe error ~ N_flap^−1.47 | R² = 0.966 |
| spanwise | CL_δe error ∝ ramp-width / band-width | r = +0.978 |

**This replaces the "hinge/panel-edge coincidence" explanation published in
DECISION-0009 §4, which is wrong.** A hinge sweep over the full DV range
0.652–0.814 shows the correlation between hinge-to-edge distance and error,
computed *within* each chordwise level, is +0.611, +0.077, −0.040, −0.163 —
no consistent relationship. The pooled correlation of +0.763 was confounding with
`nchordwise`. The decisive case: at `nchordwise = 24`, hinge 0.75 has **exact**
edge alignment and 1.32 % error; hinge 0.652 aligns worse and does better
(1.04 %).

The uniform-vs-cosine result that motivated the coincidence hypothesis still
stands as an observation (uniform halves the elevon error at equal cost) and
uniform is still **rejected**, because it degrades Xnp and Cmq by 14–15× and the
penalty persists under refinement.

## Validity envelope of the production grid

25 / 4 / 24 holds to **≤1.3 %** on all nine constructed extremes spanning
AR **2.25–7.85**, maximum sweep, twist and dihedral gradients, and **both hinge
bounds** — the geometry extremes are all non-issues.

**Narrow elevon bands are the binding case, but no longer a failure.** A
0.70–0.85 band drives the uniform ramp fraction to 38.9 % against 11.8 % for a
normal band, and the error tracks it. Originally measured at **4.34 %**; that was
inflated by band-edge snapping *moving* a section onto each edge (which widens the
ramp to 23 % even on a normal band). With snapping corrected to *insert*
(DECISION-0005), the same case measures **1.18 % uniform / 0.74 % adaptive**. The
mechanism stands; the severity was partly self-inflicted.

Across the full hinge range, CL_δe is **≤1.8 %** (worst at hinge 0.814), not the
1.1 % previously quoted at hinge 0.75 alone. Reaching ≤1 % everywhere needs 32
chordwise = 6144 vortices, **over AVL's array limit**. So 1.8 % is the accuracy
ceiling at this grid, and improving it requires placement, not count.

## Consequence: where uniform spacing is misallocated, placement beats count

Head-to-head at matched conditions against a common 49-section reference:

| design | placement | ramp | CL_δe error |
|---|---|---|---|
| narrow band | uniform (27 sec) | 38.9 % | 1.18 % |
| narrow band | **adaptive (25 sec)** | 25.0 % | **0.68 %** — 1.7× better |
| normal band | **uniform (27 sec)** | 11.8 % | **0.33 %** — 2.4× better |
| normal band | adaptive (25 sec) | 5.0 % | 0.78 % |

Uniform spacing is *misallocated* only where the ramp criterion is breached, and
correct where it is not. That is why DECISION-0011 gates adaptive placement on
this criterion rather than applying it everywhere: the gate picks the winner in
both directions. The control-band edges are a required feature of any information
metric used to drive it.

## Explicitly not established

- **Whether chordwise is a better buy than spanwise at fixed cost.** The equal-cost
  grid trade was confounded (its reference shared one candidate's spanwise
  resolution) and no dominating reference fits inside AVL's arrays. Open.
- **The N_flap law across spacing laws.** Established within cosine only; it does
  not explain the uniform-vs-cosine difference.
- **Behaviour near CL_max**, at other α, or with a different airfoil set.
- **A surface split at the hinge line**, which would likely supersede the N_flap
  trade-off entirely, was not attempted.
