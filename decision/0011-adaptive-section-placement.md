# DECISION-0011 — Adaptive section placement: targeted, not universal

Status: ACCEPTED (REVISED 2026-07-25 after a design flaw was found in the metric)
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/adaptive_section_placement.md`,
`configs/aero/adaptive_sections_evidence/`

## Decision

**Adaptive, information-weighted placement is adopted for DoE use.** It lowers
the worst-case error across the design set from **1.23 % to 0.84 %**, which is the
relevant number when one policy must serve every wing.

Uniform spacing with band-edge snapping remains correct for one-off analyses of an
ordinary wing, where it is marginally better and simpler.

```
DoE / optimisation  -> adaptive placement (worst case 0.84 % vs 1.23 %)
single ordinary wing -> uniform is fine, and slightly better on easy geometry
```

**Validated head-to-head 2026-07-25**, at matched conditions against a common
49-section reference, after the snapping correction:

| design | placement | ramp | CL_δe error | |
|---|---|---|---|---|
| narrow band | uniform (27 sec) | 38.9 % | 1.18 % | |
| narrow band | **adaptive (25 sec)** | 25.0 % | **0.68 %** | **1.7× better** |
| normal band | **uniform (27 sec)** | 11.8 % | **0.33 %** | **2.4× better** |
| normal band | adaptive (25 sec) | 5.0 % | 0.78 % | |

**The `auto` gate picks the winner in both directions** — adaptive where uniform
is weak, uniform where it is strong. That is the cleanest justification this
decision has, and it replaces the earlier argument which rested on a narrow-band
failure that was partly an artefact of the old snapping.

**Wired 2026-07-25.** `geometry.aero_discretisation.section_placement` selects
`auto` (default) | `always` | `never`. `auto` engages adaptive placement only when
uniform spacing breaches `ramp_fraction_limit` (0.15), which in practice means
short elevon bands. Exposed on the CLI (`--section-placement`) and in the GUI, and
the placement actually used plus the resulting ramp fraction are recorded in the
run's `meta` and result JSON. Guarded by `tests/aero/test_discretisation_wiring.py`.
Before this the module was validated but never called from production — the
decision was unimplementable.

`ramp_fraction` is exported from `aeris.geometry.geometric_information` and costs
nothing to evaluate — it is arithmetic on the section list.

## The first version of this decision was wrong

It recorded adaptive placement as a **negative result** — worse than uniform on all
six designs, by up to 10×. That finding was real but the cause was a **design flaw
in the metric**, not a property of adaptive placement.

**The flaw.** Each channel was normalised to unit integral before blending, so a
sweep break of range 1.05 and a wiggle of range 0.0002 both contributed exactly
1.000. The metric preserved *where* each property varied and destroyed *how much
it mattered* — the judgement it exists to make.

**The fix.** Fixed physical reference scales (lengths by root chord, twist by 10°,
thickness/camber by 0.1), no per-channel re-normalisation. Verified against de Boor
theory: density now scales as √amplitude (1 : 0.32 : 0.10 for amplitudes
1.0 : 0.1 : 0.01).

**Result with the corrected metric** (identical experiment):

| case | CL_δe uniform → adaptive | gain | was (flawed) |
|---|---|---|---|
| max_gradient | 0.36 % → **0.09 %** | **4.21×** | 0.25× |
| elevon_wide | 0.12 % → **0.05 %** | **2.25×** | 0.62× |
| elevon_narrow | 1.18 % → **0.68 %** | **1.72×** | 0.92× |
| benign | 0.21 % → 0.75 % | 0.27× | 0.09× |
| nominal | 0.33 % → 0.77 % | 0.42× | 0.39× |
| max_ar | 0.32 % → 0.65 % | 0.49× | 0.73× |

The three hard cases now improve substantially; the three easy ones degrade
slightly from an already near-noise-floor 0.12–0.33 %. **Worst case over the set:
1.23 % → 0.84 %.**

## The superseded finding, kept for the record

With the flawed metric, pure equidistribution was worse than uniform on all six
designs, by up to **10×** (benign: 0.21 % → 2.19 %).

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

`floor = 0.50` remains a **measured** default in the module, not a preference —
it was established on the flawed metric and has not been re-optimised for the
corrected one, which is an open item.

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
difficulty in the **wrong direction**, and still does after the fix
(−0.813 before, −0.820 after). So this is a genuine property of that measure, not
an artefact of the flaw. It remains in the module for reporting but **must not be
used as a difficulty score**.

## Not delivered

- **Budget selection.** The original ambition included the metric choosing *how
  many* sections a design needs, not just where to put them. Only fixed-budget
  placement was tested. The ramp criterion suggests a rule (add sections until
  ramp ≲ 15 %) but it is unvalidated as a budget selector.
- **A proper gradation limiter.** Uniform mixing is a crude proxy for bounding the
  cell-size ratio directly.
- **`floor` optimisation.** One value, three cases, no sweep — and it was tuned
  against the FLAWED metric, so it may no longer be the right value.
- **The monitor cannot resolve true kinks.** |g''|^(1/2) gives features sharper
  than the smoothing window roughly equal weight (measured 3.35 / 3.36 / 3.24 at
  widths 0.10 / 0.03 / 0.01). Control-band edges therefore still need hard node
  constraints, not density alone.

## Known bias in the evidence

Both candidates are measured against a 49-section **uniform** reference, so
uniform-25 shares its distribution family and adaptive-25 does not. Part of
adaptive's measured disadvantage is that bias rather than error. The §4 failure is
far too large (10×) to be explained by it, but the 2.78 % gain in §5 is
correspondingly **conservative**.
