# Study — pyGeo-native AVL vs AeroSandbox AVL across the DoE design space

Date: 2026-07-25
Decision produced: `decision/0007-native-avl-is-the-production-lowfi-solver.md`
Script: `standalone/lowfi_avl_study/doe_native_vs_asb.py`
Evidence: `configs/aero/native_avl_doe_evidence/`

## 1. Question

`studies/native_avl_output_and_fidelity.md` (Task 1) established that the native
pyGeo→AVL path and the AeroSandbox reference path agree to ≤0.6 % on **one**
geometry. A single sample proves nothing about a 20-dimensional design space.
This study asks whether the equivalence holds *design-space-wide*, with the
viscous correction on and off, over forces **and** stability derivatives.

## 2. Method

30 DoE samples (seeds 7000–7029) of `configs/geometry/bwb.yaml`. Per sample the
pyGeo loft is built **once** and its sections extracted **once**, then both
solvers are driven from those same `ExtractedSection` objects — so every observed
difference is solver plumbing, never geometry.

4 AVL runs per sample = {native, ASB} × {viscous on, viscous off} = **120 runs,
120/120 successful**, 884 s wall clock.

Conditions: α = 6° (above every sample's ≈2° zero-lift angle, so CL and e are
well-conditioned), β = 0°, symmetric elevon δe = 4°, V = 28 m/s, sea level,
25 extraction sections, 8 chordwise × 4 spanwise panels per interval (192 strips,
1536 vortices in both solvers).

**Design-space coverage achieved:** AR **3.11 – 6.62**, full span **1.52 – 2.49 m**
— essentially the whole DECISION-0002 range (AR 2.6–6.2 nominal, span 1.5–2.5 m).

### Scope restriction, and why it is not a dodge

Comparisons are **symmetric only** (β = 0, no differential elevon). Task 1 showed
AeroSandbox's AVL exporter collapses every control surface into a single
`all_deflections` variable, so the reference path has **no roll degree of freedom
at all**. Including lateral cases would measure that structural limitation of the
reference rather than solver agreement. It is reported separately and quantified,
not averaged away.

### Two honesty measures in the statistics

1. **Fields where both solvers return ≈0 are excluded, not scored as perfect
   matches.** 20 of 43 derivatives are zero by symmetry at β = 0; counting them
   as 0 % error would have flattered every headline number.
2. **Every disagreement is also placed on a common, well-conditioned scale.** A
   relative error is meaningless on a derivative that is itself ≈0. Each absolute
   difference is therefore also expressed as a fraction of |Clp| ≈ 0.33, an
   O(0.3) derivative present in every case.

## 3. Result — the primary quantities agree design-space-wide

Viscous on, n = 30, relative difference native vs ASB:

| quantity | median | p95 | max |
|---|---|---|---|
| **CL** | 0.69 % | 0.90 % | 1.04 % |
| **CD** (viscous total) | 1.37 % | 1.71 % | 1.92 % |
| CDind | 2.40 % | 3.55 % | 3.68 % |
| **cd_profile** | **0.056 %** | 0.086 % | 0.111 % |
| **L/D** | 0.60 % | 1.05 % | 1.25 % |
| Cm | 1.23 % | 1.53 % | 1.58 % |
| e | 1.08 % | 2.26 % | 2.85 % |
| **Xnp** | **3.6e-5** | 6.5e-5 | 7.3e-5 |
| **CLα** | 0.100 % | 0.181 % | 0.203 % |
| **Cmα** | 0.030 % | 0.063 % | 0.070 % |
| Cmq | 0.157 % | 0.226 % | 0.301 % |
| Clp | 0.475 % | 0.981 % | 1.05 % |
| Clb | 0.334 % | 0.995 % | 1.18 % |
| Cnb | 0.922 % | 2.87 % | 3.07 % |
| CZw | 0.082 % | 0.166 % | 0.190 % |

Three things worth drawing out:

- **The stability derivatives that matter agree far better than the forces.** CLα
  to 0.2 %, Cmα to 0.07 %, Xnp to 7e-5 — i.e. the two solvers are solving the same
  VLM problem. The force differences come from the airfoil camber discretisation
  (native 80 points/surface, forced by AVL's IBX limit; ASB 181), which shifts the
  zero-lift angle ≈0.05° and so moves CL but not its slope.
- **CDind is the largest primary disagreement (2.4 % median).** Induced drag is
  quadratic in the lift distribution, so it amplifies the same camber difference.
- **The viscous chain is essentially identical**: cd_profile agrees to 0.056 %,
  which is expected since both paths use the same polar bridge. This *improves*
  the L/D agreement (0.60 % viscous vs 1.65 % inviscid): profile drag dominates
  the total at this scale, diluting the CDind disagreement.

Viscous-off results are within noise of viscous-on for every inviscid quantity,
confirming the viscous correction does not perturb the VLM core.

### No degradation anywhere in the design space

| correlation with aspect ratio | value |
|---|---|
| corr(AR, CL rel. error) | −0.287 |
| corr(AR, CDind rel. error) | +0.218 |
| corr(AR, Cm rel. error) | −0.108 |

At n = 30 none of these is significant (|r| < 0.36 at p = 0.05). Agreement does
not deteriorate toward either end of the AR 3.11–6.62 range, so the Task-1
single-geometry conclusion generalises.

## 4. Result — the large relative errors are all near-zero derivatives

Taken at face value the table contains alarming entries — CYr differs by 135 %,
Cnv by 31 %. On the common scale they vanish:

| field | max rel. | median \|value\| | max \|diff\| | as fraction of \|Clp\| |
|---|---|---|---|---|
| CYr | 1.35 | 1.5e-2 | 4.5e-4 | 1.5e-3 |
| Cnv | 0.313 | 1.9e-3 | 8.8e-5 | 2.9e-4 |
| CYp | 0.112 | 1.8e-2 | 6.5e-4 | 1.8e-3 |
| Cnb | 0.031 | 6.4e-3 | 1.7e-4 | 6.1e-4 |

Splitting the 44 derivatives by conditioning:

- **30 ill-conditioned** (median |value| ≤ 0.05): relative errors up to 135 %, but
  the largest absolute difference anywhere is **6.5e-4**, i.e. **0.18 % of |Clp|**.
- **14 well-conditioned** (median |value| > 0.05): all agree to **≤1.7 %** — with
  two exceptions, below.

## 5. Result — one genuine open item: the speed derivatives

Among the well-conditioned derivatives, **Cmu (max 10.3 %) and CZu (max 4.2 %)**
stand out; every other one is ≤1.7 %. These are the ∂/∂u speed derivatives, which
feed the phugoid and speed-stability modes.

Two candidate causes were tested and **eliminated**:

- *Operating Mach mismatch* — both solvers run at Mach 0.0820 (verified in both
  totals dumps).
- *Header Mach* — the native writer puts M = 0.0823 in the `.avl` header while
  AeroSandbox writes `0` with a note that it is overwritten. Ablation: editing the
  native header to `0` and re-running changes **nothing** (CL 0.36871 and
  CLα 3.93958 identical to 6 significant figures). AVL's OPER `mn` command fully
  supersedes the header.

The remaining likely mechanism is conditioning: the u-derivatives are small
residuals of much larger terms, so they amplify the ~0.5 % CL and ~0.13 % Cref
differences between the paths. This is **not resolved here**. Anyone doing
dynamic-mode (phugoid / speed-stability) analysis should not take Cmu or CZu from
either path without a dedicated verification.

## 6. Result — the elevon difference is a systematic bias, not scatter

Symmetric control authority, signed (ASB − native)/native across all 30 samples:

| statistic | value |
|---|---|
| median | **+5.89 %** |
| standard deviation | 0.39 % |
| same sign in all 30 samples | **yes** |

A ±0.39 % spread on a +5.89 % offset, with no sign changes in 30 independent
geometries, is a systematic bias — precisely the elevon over-extension identified
in DECISION-0005: AeroSandbox tags one section *outboard* of `elevon_end_frac`,
so its elevon always reaches further toward the tip, where the moment arm is
largest. The native path's elevon matches the geometry's band exactly.

This is the single most consequential difference between the paths, because the
DoE varies three elevon design variables specifically so that control authority
can be optimised.

## 7. Assumptions and limits

- **One operating point** (α = 6°, β = 0°, δe = 4°). Agreement at other α is not
  established here, though Task 1 covered α = 3° with the same conclusions.
- **Fixed discretisation** (25 sections, 8×4 panels). Whether that discretisation
  is itself converged is Task 4, deliberately separate; both solvers see the
  *same* discretisation here, so the comparison is valid regardless.
- **Code-to-code only.** Neither path is validated against experiment or CFD.
  Agreement between two VLM implementations bounds implementation error, not
  physical accuracy.
- **30 samples.** Whether 30 is enough for these statistics to be design-space
  representative is Task 5, not asserted here.
- Lateral/roll behaviour is **not** compared, for the structural reason in §2.

## 8. Conclusions

1. The native pyGeo→AVL path and the AeroSandbox reference are **equivalent
   design-space-wide** for symmetric aerodynamics: CL ≤1.0 %, L/D ≤1.3 %,
   CLα ≤0.2 %, Cmα ≤0.07 %, Xnp ≤7e-5 over 30 samples spanning AR 3.11–6.62,
   with no dependence on position in the design space.
2. Every alarming relative error belongs to a derivative that is ≈0 by symmetry;
   the largest absolute discrepancy anywhere among them is 0.18 % of |Clp|.
3. Two well-conditioned exceptions remain — the speed derivatives Cmu and CZu
   (10.3 % / 4.2 %) — with the two obvious Mach explanations experimentally
   eliminated. Flagged, not explained.
4. The elevon authority difference is a **systematic +5.89 % ± 0.39 %** bias in
   the reference path's favour, consistent in sign across all 30 samples, and is
   the known ASB over-extension. The native value is the geometrically correct one.
5. Combined with the reference path's structural inability to deflect an elevon
   differentially, the native path is the one to build the multifidelity workflow
   on. The ASB path is retained as a symmetric-case cross-check.
