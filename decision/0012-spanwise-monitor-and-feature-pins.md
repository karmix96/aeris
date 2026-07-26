# DECISION-0012 — Spanwise monitor: worst-channel, thickness off, hard feature pins

Status: ACCEPTED
Date: 2026-07-26
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/curvature_monitor_metric_evaluation.md`,
`configs/aero/monitor_evaluation_evidence/`, `artifacts/curvature_monitor_aero_study/`
Amends: DECISION-0011 (the metric's form and channel set change; the gating rule stands)

## Decision

Three changes to the spanwise section-placement monitor, all measured over 100
native AVL runs on 10 geometries:

1. **Hard feature pins, on BOTH the uniform and adaptive paths.** Sections are
   placed exactly at root, tip, the two BWB planform/airfoil break stations
   (`(1−b3_ratio)·split_ratio` and `1−b3_ratio`) and both elevon band edges.
2. **Worst-channel combination**: `ρ = max_k(w_k·|g_k''|^½)`, replacing the
   previous `Σ_k w_k·|g_k''|^½`.
3. **Thickness channel weight 0** (was 1.0).

## Why pins, and why they are not optional

The monitor is `|g''|^(1/2)` — de Boor's law for piecewise-linear interpolation of
a **smooth** function. At a genuine kink it cannot resolve the feature however much
density it concentrates nearby: the second derivative is a delta, and
`√(height)·width → 0` as the feature narrows. A kink needs a node **on** it.

The BWB planform has two such kinks by construction, where sweep and taper change
slope discontinuously in the authored geometry, plus the two control-band edges.
This limitation was identified in DECISION-0011 and left unimplemented; pinning is
the fix.

**Pins are INSERTED, not swapped onto the nearest neighbour.** Replacing was wrong
twice over: it widens the gap just outside the pin (the identical defect
DECISION-0005 had to correct for the band edges), and with several pins close
together later pins silently overwrote earlier ones. Insertion costs a few sections
— 25 requested becomes 29 typical — and guarantees every pin is present, which is
the entire point of a hard pin.

## Why worst-channel rather than a sum

A section grid must resolve whichever spanwise function bends most sharply **at
that station**. Summing or averaging lets a well-behaved channel dilute a
badly-behaved one at the same place and under-refine it. Measured (max control-
derivative error over 10 geometries): worst-channel **1.23 %**, additive 1.81 %,
previous AERIS sum-of-roots 1.81 %, uniform 3.65 %.

## Why thickness is off — a physics correction

**AVL's vortex-lattice core is a mean-surface method.** It sees the camber line,
not the thickness. Thickness reaches the answer only through the CLAF lift-slope
multiplier and the CDCL profile-drag polar, and both are per-section **scalars** —
they are already resolved by having a section there at all, and do not need the
section *grid* refined. Weighting thickness equally with camber spent section
budget on a channel the VLM cannot use. Camber stays at weight 1.0: it *is* the
surface AVL sees.

## What was rejected, and why

**The evaluated study's own selected policy (`sqrt_sum_w3_gap15`) is rejected.**
Its win was an artefact of AVL's printed output precision. The ranking statistic
included `Cn_da`, whose reference value is −2.3e−05 while AVL prints six decimals;
one unit in the last printed digit is 1e−6, giving 1e−6/2.3e−5 = **4.35 %**. Seven
of nine policies scored exactly that, on meshes whose ramp fractions differed by 6×
— a saturated metric, not a physical result. The selected policy happened to print
the identical value and scored 0.000 %. With `Cn_da` excluded (its reference is
below 1e−4 in 7 of 10 geometries) that policy ranks **7th of 9** on max control
error, and is the worst of the proposed family on `elevon_narrow` — the very case
adaptive placement exists to fix.

**Max-gap repair is not adopted.** It was best only on the noise-dominated case and
mediocre elsewhere. It may still be worth having; this study does not establish it.

## A reporting rule this makes permanent

**Never rank on a relative error whose reference magnitude is within ~100× of the
solver's output precision.** For AVL that means `|reference| > 1e-4`. This is the
same rule DECISION-0007 adopted for the solver comparison; it was not carried
across to the monitor study, and cost it its conclusion. Any future ranking must
state the floor it applied and which quantities it excluded.

## Honest limits of the adopted choice

- The winner beats uniform on **6 of 10** cases, the previous metric on 5 of 10.
  **No policy dominates case by case** — the advantage is in the tail (max 1.23 %
  vs 1.81–3.65 %), not the typical case.
- At n = 10 the mean differences (0.74 / 0.84 / 1.03 %) are **not separable**, and a
  max over ten samples is unstable: one new geometry could reorder the top three.
- One operating point (α = 6°, β = 0°, δe = δa = 4°).
- `Cl_da` and `CY_da` are also small differential-elevon derivatives, within an
  order of magnitude of the noise floor. They passed the filter here but should be
  watched.
- The 49-section reference is a discretisation reference, not truth.
