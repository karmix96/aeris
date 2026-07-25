# Study — A geometric-information metric for adaptive section placement

Date: 2026-07-25
Decision produced: `decision/0011-adaptive-section-placement.md`
Module: `src/aeris/geometry/geometric_information.py`
Scripts: `standalone/lowfi_avl_study/{validate_adaptive_sections,probe_gradation_control}.py`
Evidence: `configs/aero/adaptive_sections_evidence/`

**Headline: one claim confirmed, one refuted as first implemented, then partially
recovered.** Reported in that order because that is the order it happened.

## 1. Question

Task 4 showed the elevon control derivative does not converge monotonically in
`n_sections`, and Task 5 showed why: the binding error is *control-surface*
resolution, governed by the gain-ramp fraction (r = +0.978). Task 5 also showed
the fix is placement, not count — clustering sections at the band edges recovered
~3.2 % of a 4.34 % error at an identical budget.

So: can a metric computed from the geometry alone decide **where** the sections
should go, and **how many** are needed?

Two deliberately separable claims, so one can fail without taking the other down:

- **Claim 1 (predictive)** — the metric forecasts which designs are hard to
  discretise, before any AVL run. Useful as a diagnostic even if placement is
  never adopted.
- **Claim 2 (prescriptive)** — at an identical budget, information-weighted
  placement beats uniform.

## 2. The metric

Classical equidistribution (de Boor 1973). AVL interpolates the wing
*piecewise-linearly* between sections, so the discretisation error is the
interpolation error of the spanwise functions, which for linear interpolation
scales as h²·|g''|. Equidistributing that error gives node density

```
ρ(y) ∝ |g''(y)|^(1/2)
```

and sections are placed at equal increments of ∫ρ dy.

A wing is not one function, so ρ blends seven channels — the independent spanwise
functions AVL actually interpolates: `x_le` (sweep), `z_le` (dihedral), `chord`
(taper), `twist`, `t/c`, `camber`, and **`control_gain`**.

**The control channel is the design's key idea.** Task 5 established the control
surface as the binding error source. Rather than handling it as a special case,
note that the control gain *is* a spanwise function AVL interpolates linearly — a
boxcar, 1 inside the band and 0 outside. Its second derivative is a pair of deltas
at the band edges, so the *same* monitor automatically concentrates sections
there, and a narrow band automatically attracts more of the budget. No bespoke
logic.

Each channel is range-normalised before differentiating, so the blend is
dimensionless. Cost is negligible: the probe samples the loft with ~21 chordwise
points per station and no CST fitting, so it runs *before* the budget is spent.

## 3. Result — Claim 1: the ramp fraction predicts; the concentration score does not

Across six designs (benign, nominal, narrow band, wide band, max gradient,
max AR), against the CL_δe error at uniform 25 sections:

| predictor | correlation with error |
|---|---|
| **gain-ramp fraction** | **+0.964** |
| metric's own `concentration()` score | **−0.813** |

The ramp fraction is strongly predictive — an **independent confirmation of
DECISION-0010 on a different design set** (there r = +0.978, here +0.964).

The metric's concentration score, however, correlates in the **wrong direction**.
A design whose information is more concentrated is *easier*, not harder, at fixed
budget — presumably because concentrated information means most of the wing is
featureless and cheap to resolve. **Claim 1 holds only for the simple quantity,
not for the elaborate one.** The concentration measure as defined does not earn
its place and should not be used as a difficulty score.

## 4. Result — Claim 2: refuted as first implemented

At the theoretically "pure" setting (uniform floor 0.15), adaptive placement was
**worse than uniform on all six designs**:

| case | ramp uniform → adaptive | CL_δe uniform → adaptive | gain |
|---|---|---|---|
| benign | 11.8 % → 6.2 % | 0.21 % → **2.19 %** | 0.09× |
| nominal | 11.8 % → 7.6 % | 0.33 % → 0.84 % | 0.39× |
| elevon_narrow | 38.9 % → 22.6 % | 1.18 % → 1.28 % | 0.92× |
| elevon_wide | 12.8 % → 7.4 % | 0.12 % → 0.20 % | 0.62× |
| max_gradient | 11.8 % → 9.0 % | 0.36 % → 1.43 % | 0.25× |
| max_ar | 11.8 % → 7.7 % | 0.32 % → 0.45 % | 0.73× |

Note the paradox: adaptive placement **reduced the ramp fraction in every case**
— it did exactly what it was asked to do — and the error still got worse.

**Diagnosis.** The failure is not in the criterion but in what equidistribution
does to the *rest* of the wing. On the benign case:

| region | uniform | adaptive |
|---|---|---|
| inboard 0–0.30 | 8 | **5** |
| mid → band start | 6 | 7 |
| inside band | 9 | 8 |
| outboard band→tip | 1 | 4 |
| **max section gap** | **0.0417** | **0.1840 (4.4×)** |

Concentrating on the sharp features starved the inboard region — where the chord
changes fastest — and opened an 18 %-of-semispan gap. This is the classic
equidistribution failure mode, and mesh adaptation has a standard remedy:
**gradation control**, bounding how far cell size may depart from uniform.

## 5. Result — gradation control recovers it, conditionally

The remedy was implemented as the existing uniform-mixing `floor`, raised
0.15 → 0.50, **declared before running and tested once** on three cases:

| case | max gap ratio | CL_δe uniform → adaptive | gain |
|---|---|---|---|
| benign | 2.0× | 0.21 % → 0.21 % | **1.00× (neutral)** |
| **elevon_narrow** | 1.5× | 1.18 % → **0.42 %** | **2.78×** |
| max_gradient | 1.7× | 0.36 % → 0.49 % | 0.73× |

The catastrophic failure is gone (benign 0.09× → 1.00×), and on the case the
method was built for — a narrow control band, where uniform spacing violates the
15 % ramp criterion — it is **2.78× better at the same section budget**. It
remains mildly negative on `max_gradient` (0.73×).

So the honest conclusion is **conditional usefulness**: adaptive placement pays
where uniform spacing fails the ramp criterion, and is neutral-to-slightly-costly
elsewhere. That gives a targeted rule rather than "always adapt".

## 6. Assumptions and limits

- **The reference favours uniform.** Both candidates are compared against a
  49-section *uniform* reference, so uniform-25 shares its distribution family
  while adaptive-25 does not. Part of adaptive's measured disadvantage is this
  bias, not error. The direction of the §4 failure is not in doubt (10× on
  benign is far too large to be bias), but the magnitudes are pessimistic for
  adaptive, and §5's 2.78× is correspondingly conservative.
- **`floor = 0.50` was tested once, on three cases.** It is not optimised, and no
  sweep of it was run. A different value may be better; that is untested.
- **Six designs, one seed family, one operating point** (α = 6°, δe = 4°).
- **`concentration()` is retained in the module but is not validated** — it
  correlates the wrong way and must not be used as a difficulty score.
- **The budget-selection ambition is NOT delivered.** Mike's framing included
  "refine/reduce the spacing if needed", i.e. the metric choosing *how many*
  sections a design needs. Only placement at fixed budget was tested. The ramp
  criterion does give a usable rule for this (add sections until ramp ≲ 15 %) but
  it has not been validated as a budget selector.
- Gradation control is implemented as uniform mixing, which is a crude form of it;
  a proper cell-size-ratio limiter was not implemented.

## 7. Conclusions

1. **The control gain belongs in the metric as an ordinary channel**, not as
   special-case logic — its curvature naturally concentrates sections at the band
   edges. This is the design's one genuinely novel element and it works as
   intended (the ramp fraction fell in all six cases).
2. **The gain-ramp fraction predicts discretisation difficulty (r = +0.964)**,
   independently confirming DECISION-0010 on a new design set. Use it.
3. **The metric's concentration score does not predict difficulty** — it
   correlates in the wrong direction (−0.813). Do not use it.
4. **Pure equidistribution is worse than uniform**, by up to 10×, because it
   starves featureless regions and opens gaps 4.4× the uniform spacing. This is
   the main result and it is negative.
5. **With gradation control it becomes conditionally useful**: 2.78× better on a
   narrow control band, neutral on benign geometry, mildly worse on a
   high-gradient planform.
6. **Recommended use: targeted, not universal.** Apply adaptive placement when the
   uniform ramp fraction exceeds the 15 % criterion. Otherwise keep uniform
   spacing with sections snapped to the band edges, which is the current
   production behaviour and is already adequate.
