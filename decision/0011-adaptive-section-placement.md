# DECISION-0011 — Adaptive section placement: targeted, not universal

Status: ACCEPTED (with a negative principal result)
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/adaptive_section_placement.md`,
`configs/aero/adaptive_sections_evidence/`

## Decision

**Uniform section spacing with sections snapped to the elevon band edges remains
the production default.** Adaptive, information-weighted placement is applied
**only** when uniform spacing violates the DECISION-0010 criterion:

```
if ramp_fraction(uniform_sections, band) > 0.15:
    use adaptive placement          # measured 2.78x better on a narrow band
else:
    keep uniform                    # adaptive is neutral-to-slightly-worse here
```

`ramp_fraction` is exported from `aeris.geometry.geometric_information` and costs
nothing to evaluate — it is arithmetic on the section list.

## Why not universal: the principal result is negative

Pure equidistribution — the theoretically correct construction — was **worse than
uniform on all six designs tested**, by up to **10×** (benign case: 0.21 % → 2.19 %
CL_δe error at an identical budget).

It failed while *succeeding* at its stated objective: the gain-ramp fraction fell
in every case. The cost landed elsewhere. On the benign case it moved the inboard
section count 8 → 5 and opened a maximum gap of **0.184 span fraction, 4.4× the
uniform spacing**, in the region where chord changes fastest.

This is the classic equidistribution failure and it has a standard remedy —
gradation control. Implemented here as uniform-density mixing raised from
`floor = 0.15` to **0.50**, declared before running and tested once:

| case | max gap ratio | CL_δe uniform → adaptive | gain |
|---|---|---|---|
| benign | 2.0× | 0.21 % → 0.21 % | 1.00× |
| **elevon_narrow** | 1.5× | 1.18 % → **0.42 %** | **2.78×** |
| max_gradient | 1.7× | 0.36 % → 0.49 % | 0.73× |

So the method is **conditionally useful**, not generally better — hence the gated
rule above. `floor = 0.50` is therefore a **measured** default in the module, not
a preference.

## What is adopted from the metric, and what is not

**Adopted — the control-gain channel.** The control gain is itself a spanwise
function AVL interpolates linearly (a boxcar, 1 inside the band, 0 outside), so it
enters the monitor as an ordinary channel rather than as special-case logic. Its
curvature concentrates sections at the band edges automatically, and a narrow band
automatically attracts more budget. This is the design's novel element and it
behaved as intended in all six cases.

**Adopted — the ramp fraction as a difficulty predictor.** r = **+0.964** against
CL_δe error, independently confirming DECISION-0010 (r = +0.978) on a different
design set.

**NOT adopted — the metric's `concentration()` score.** It correlates with
difficulty in the **wrong direction** (−0.813): more concentrated information means
an *easier* design at fixed budget, because most of the wing is then featureless.
It remains in the module for reporting but **must not be used as a difficulty
score**.

## Not delivered

- **Budget selection.** The original ambition included the metric choosing *how
  many* sections a design needs, not just where to put them. Only fixed-budget
  placement was tested. The ramp criterion suggests a rule (add sections until
  ramp ≲ 15 %) but it is unvalidated as a budget selector.
- **A proper gradation limiter.** Uniform mixing is a crude proxy for bounding the
  cell-size ratio directly.
- **`floor` optimisation.** One value, three cases, no sweep.

## Known bias in the evidence

Both candidates are measured against a 49-section **uniform** reference, so
uniform-25 shares its distribution family and adaptive-25 does not. Part of
adaptive's measured disadvantage is that bias rather than error. The §4 failure is
far too large (10×) to be explained by it, but the 2.78 % gain in §5 is
correspondingly **conservative**.
