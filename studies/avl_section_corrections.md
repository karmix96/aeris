# Study — AVL section corrections: are CDCL (viscous) and CLAF (thickness) active, correct and section-resolved?

Date: 2026-07-25
Decision produced: `decision/0006-lowfi-viscous-and-thickness-model.md`
Script: `standalone/lowfi_avl_study/verify_viscous_and_claf.py`
Tests: `tests/aero/test_avl_section_corrections.py` (7 regression guards)
Evidence: `configs/aero/native_avl_verification_evidence/viscous_claf_verification.*`

## 1. Question

AVL is an inviscid vortex-lattice code. It offers exactly two per-section hooks
that let a VLM carry real airfoil information, and the AERIS low-fi model uses
both:

- **CDCL** — a 3-point (cl, cd) polar attached to each SECTION, from which AVL
  forms the section profile drag;
- **CLAF** — a multiplier on the section lift-curve slope, capturing that a
  thick airfoil has dCl/dα above the thin-airfoil 2π.

Task 2 asks whether both are (a) actually active, (b) numerically correct, and
(c) resolved *per section from the pyGeo surface* rather than from the four
authored station airfoils.

This matters because these two blocks are the *entire* difference between "AVL
on a wireframe" and "AVL that knows what airfoil it is flying". They have
regressed silently before: the OPER `v` keystroke once toggled viscous forces
**off**, so CDCL was injected into the file but AVL never counted it (recorded in
`aerosandbox_avl.py`). Presence in the `.avl` text is therefore not evidence.

## 2. Method — three independent axes per correction

| axis | what it rules out |
|---|---|
| **PRESENT** | the block is missing or written for only some sections |
| **CORRECT** | the value is written but wrong (bad t/c measurement, wrong Re, stale polar) |
| **ACTIVE** | the value is written and right but AVL ignores it |

"ACTIVE" is established by **ablation**: neutralise the block on an otherwise
byte-identical `.avl`, re-run AVL, and require the answer to move in the
predicted direction *and* by the predicted magnitude.

Conditions: `configs/geometry/bwb.yaml` default seed, α = 6° (well above this
wing's ≈2° zero-lift angle, so CL and e are well-conditioned), V = 28 m/s, sea
level, 25 extraction sections, full span.

Independence of the checks was taken seriously:

- t/c is re-measured with a *different algorithm* from the solver's (both
  surfaces interpolated onto a shared 2001-point abscissa, versus the solver's
  matching of rounded x values), so agreement is a cross-check rather than a
  tautology.
- The injected CDCL triplets are compared against a **fresh** NeuralFoil
  evaluation of the same section coordinates at the same local Reynolds number,
  through a separately constructed polar source.

## 3. Results — (a) CDCL, the viscous correction

| axis | result |
|---|---|
| PRESENT | 25/25 sections carry a real CDCL triplet; runner reports `n_cdcl_injected = 25`. With `viscous=False`, 25/25 remain zero placeholders. |
| CORRECT | max abs. difference between the injected triplet and an independent NeuralFoil refit: **4.28e-07** |
| ACTIVE | AVL `CDvis`: **0.0 → 0.00663** when viscous is enabled |
| SECTION-RESOLVED | **25 distinct** min-drag cd values across 25 sections |

Spanwise trend of the injected minimum-drag cd:

| station | cd_min |
|---|---|
| root (mh91, Re ≈ 1.8e6) | 0.00547 |
| mid (e374 blend) | 0.00637 |
| tip (nlf1015, Re ≈ 1.8e5) | 0.02065 |

The tip is **3.8×** draggier than the root. That is the expected low-Reynolds
penalty at the tip chord, and it is exactly the effect a single wing-level CDCL —
or a 4-airfoil step model — would smear away. It is consistent with the
trailing-edge study's finding that the low-Re tip behaves qualitatively
differently from the root.

**Two independent routes to the same drag agree.** AVL's own injected-CDCL
`CDvis` = 0.00663 and the AERIS strip integration `cd_profile` = 0.006926 differ
by **4.28 %**. These are genuinely different computations — AVL integrates its
3-point fit over its own panels, AERIS re-queries the full NeuralFoil polar per
strip and integrates over AVL's strip areas — so their agreement bounds the error
of the 3-point CDCL fit itself. 4.3 % reproduces the ≈4.1 % the earlier
standalone study observed, and sits inside the 10 % QC gate.

## 4. Results — (b) CLAF, the thickness lift-slope correction

| axis | result |
|---|---|
| PRESENT | 25/25 sections |
| CORRECT | max abs. error vs an independently recomputed 1 + 0.77·(t/c): **1.46e-06** |
| ACTIVE | CLα **3.48426 → 3.68502** (+5.76 %) when CLAF goes from 1.0 to as-written |
| SECTION-RESOLVED | 16 distinct values; t/c 0.1500 (root) → 0.1093 (interior minimum) → 0.1507 (tip) |

The t/c trace recovers the authored airfoil sequence from the *loft*, without
being told it: 15.00 % at the root (mh91, published 14.98 %), a smooth blend down
to 10.93 % (e374, published ≈10.9 %), then back up to 15.07 % at the tip
(nlf1015, published ≈15 %). The minimum is interior, and there are 16 distinct
values across 4 authored stations — so CLAF is genuinely resolved from the
realized surface, including the blend regions, not stepped off the station list.

### The ablation magnitude is itself a physics check

CLAF scales the **section** lift slope a₀, but the wing-level CLα is diluted by
induced downwash. So the measured ratio must sit strictly between 1.0 (CLAF
ignored) and the mean CLAF (applied with no 3-D dilution):

| quantity | value |
|---|---|
| mean CLAF written | 1.10096 |
| measured CLα ratio | **1.05762** |
| lifting-line prediction, CLα = a₀/(1 + a₀/(π·AR·e)), AR = 4.133, e = 0.925 | **1.06406** |

Measured 1.0576 against a predicted 1.0641 — **0.6 % apart**, and on the correct
side: the wing's ≈30° inboard sweep further reduces the effective section slope
below the unswept lifting-line estimate. A ratio of 1.0 would have meant AVL was
ignoring CLAF; a ratio of 1.101 would have meant it was being applied as a
wing-level scalar. Neither is what happens.

Both the direction and the magnitude of the response are therefore accounted
for — which is the standard this needed to meet, since a "CLα changed, therefore
it works" test would pass even if CLAF were being applied wrongly.

## 5. Assumptions and their limits

- **CLAF = 1 + 0.77·(t/c) is AVL's own documented rule**, not an AERIS
  invention; AeroSandbox computes the identical value (1.1154678 vs the native
  1.1154674 at the root). It is a thin-airfoil-theory thickness correction and
  carries all of that theory's limits.
- **NeuralFoil is the 2-D truth source**, itself a surrogate trained on XFOIL. Its
  own error is not assessed here; this study establishes only that the low-fi
  chain transmits NeuralFoil's answer faithfully into AVL.
- **The 3-point CDCL fit is lossy by construction.** The 4.3 % AVL-vs-strip gap
  quantifies that loss. AERIS therefore reports the strip-integrated
  `cd_total = cd_ind + cd_profile` as primary and keeps AVL's `CDtot` as an
  audit cross-check, which is the right way round.
- **Mach is a documented no-op** in NeuralFoil's coordinate core (incompressible).
  At M = 0.082 this is immaterial, but it would not be at transonic conditions.
- **Single geometry, single α.** Whether the corrections behave across the DoE is
  Task 3/5, not this study.

## 6. Conclusions

1. Both AVL section corrections are **present on every section, numerically
   correct against independent recomputation, and demonstrably active in AVL** by
   ablation.
2. Both are **resolved per section from the realized pyGeo surface** — 25/25
   distinct CDCL polars and 16 distinct CLAF values across only 4 authored
   station airfoils, correctly tracking the mh91 → e374 → nlf1015 blend and the
   3.8× root-to-tip Reynolds drag penalty.
3. The CLAF ablation magnitude matches lifting-line theory to 0.6 %, confirming
   AVL treats it as a section property diluted by 3-D downwash rather than as a
   wing-level fudge factor.
4. The 3-point CDCL fit loses ≈4.3 % against direct strip integration; AERIS
   already uses the strip-integrated total as primary, so this error does not
   propagate into the reported drag.

Seven regression guards now hold all of this in `tests/aero/test_avl_section_corrections.py`,
including an explicit guard against the historical `v`-toggle failure mode.
