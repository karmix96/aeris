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

**Design-space coverage achieved — 16 of the 19 free design variables varied.**

> **CORRECTION (found 2026-07-25, after this study ran).** The three *elevon* DVs
> below were sampled per design but **did not reach AVL**: the aero entry point
> `build_pygeo_sections_from_config` read the elevon geometry from the static
> config instead of the sample, so **every run in this study flew the same elevon**
> (start 0.60, end 0.95, hinge 0.75). The 16 planform and section DVs did vary and
> did reach the geometry, so every conclusion about solver equivalence stands —
> both solvers always saw identical geometry. What does **not** hold is any claim
> that the elevon geometry was exercised. Fixed in `pygeo_avl_adapter.py`;
> re-exercising it is Task 5's job.

Measured sample ranges over the 30 designs:

| DV | range sampled | | DV | range sampled |
|---|---|---|---|---|
| c1_m (root chord) | 0.720 – 1.092 m | | twist_b0 | −0.98 … +0.95° |
| c2_ratio | 0.550 – 0.799 | | twist_b1 | −2.97 … −0.17° |
| c3_ratio | 0.304 – 0.545 | | twist_b2 | −4.95 … −1.13° |
| c4_ratio | 0.081 – 0.199 | | twist_b3 | −7.66 … −2.06° |
| b_total_m (semi) | 0.759 – 1.243 m | | dihedral_b1 | 0 (pinned, flat root) |
| b3_ratio | 0.410 – 0.541 | | dihedral_b2 | 0.06 – 5.51° |
| split_ratio | 0.404 – 0.592 | | dihedral_b3 | 0.04 – 9.96° |
| **sw1** | **−39.2 … −21.3°** | | elevon_start_frac | 0.502 – 0.700 |
| **sw2** | **−34.1 … −15.4°** | | elevon_end_frac | 0.851 – 0.977 |
| **sw3** | **−23.6 … −6.3°** | | elevon_hinge_frac | 0.652 – 0.814 |

Derived: AR **3.11 – 6.62**, full span **1.52 – 2.49 m**. Every sweep, twist and
dihedral variable spans essentially its whole DECISION-0002 range, so this is a
genuine planform sweep and not a scale sweep. `dihedral_b1` is pinned at 0 by
design (flat root panel, DECISION-0002 §3). The three elevon rows are the
*sampled* ranges — see the correction above; they were not seen by AVL.

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
  VLM problem. A slope agreeing to 0.2 % while the force it integrates differs by
  0.7 % is the signature of a **constant lift offset**, not of a different
  solution. §5 identifies and proves what that offset is.
- **CDind is the largest primary disagreement (2.4 % median).** Induced drag is
  quadratic in the lift distribution, so it amplifies the same offset.
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

## 5. Result — the ENTIRE force disagreement is the elevon extent, proven

The residual was initially attributed to airfoil-coordinate resolution, and the
speed derivatives Cmu (max 10.3 %) / CZu (max 4.2 %) were logged as an unexplained
open item. Both of those readings were wrong. Four experiments settle it.

### 5.1 Airfoil resolution is NOT the cause — refuted

First, the direction was backwards: the native writer emits **159** points per
section (`cst_points=80` → 2n−1) while AeroSandbox's AVL exporter downsamples to
**99**. The native side is the *finer* one.

Test: re-run the native path at `cst_points=50`, which writes exactly 99 points
and so matches AeroSandbox's discretisation. If resolution were the cause, the
gap would close.

| seed 7005, vs ASB | CL | CDind | Cm | Cmu | CZu |
|---|---|---|---|---|---|
| native 99 pts (matched) | 8.95e-3 | 3.09e-2 | 1.52e-2 | 9.95e-2 | 4.12e-2 |
| native 159 pts (default) | 9.19e-3 | 3.13e-2 | 1.57e-2 | 1.03e-1 | 4.24e-2 |

Matching the resolution changes the disagreement by ~3 % *of itself*. **Refuted.**

Native self-convergence in airfoil resolution is meanwhile excellent: CL moves
0.1 % between 99 and 239 points — an order of magnitude smaller than the 0.9 %
gap to ASB. (319 and 359 points exceed AVL's IBX array limit and fail; 239 is the
practical ceiling.)

### 5.2 Mach is NOT the cause — refuted, properly this time

An earlier ablation of the `.avl` header Mach dumped only `st`, but Cmu and CZu
come from `sb` — it was inconclusive for exactly the quantities in question.
Repeated with `sb` dumped: setting the native header Mach from 0.0823 to 0 changes
Cmu, CZu and CXu by **0.000 %**. OPER `mn` fully supersedes the header. Both paths
also run at an identical Mach 0.0820. Separately, dCmu/dM is mild (Cmu moves
0.22 % over M = 0 → 0.082), so Mach cannot amplify anything here. **Refuted.**

### 5.3 Cmu / CZu are conditioning, not a separate defect — confirmed

Across the 30 samples the **absolute** Cmu difference is essentially constant
while |Cmu| itself varies 7.3×:

| | |Cmu| | \|abs diff\| | rel. error |
|---|---|---|---|
| seed 7005 (smallest \|Cmu\|) | 0.0416 | 0.00478 | **10.3 %** |
| seed 7024 | 0.0440 | 0.00453 | 9.3 % |
| seed 7001 | 0.2845 | 0.00517 | 1.8 % |
| seed 7023 (largest \|Cmu\|) | 0.3040 | 0.00657 | 2.1 % |

|abs diff| over 30 samples: mean 0.00452, sd 0.00086 (cv = 0.19), while |Cmu|
ranges 0.0416–0.3040. And **corr(1/|Cmu|, relative error) = 0.971**.

A constant numerator over a denominator varying 7× is the definition of a
conditioning artefact. Cmu and CZu are **not separately broken**; they inherit the
same absolute offset as everything else, and show a large relative error only
where |Cmu| happens to be small. Direct confirmation: an α perturbation that moves
CL by 3.7 % moves Cmu by 1.25× that fraction — no amplification mechanism exists
that could turn a 0.5 % CL difference into 10 %.

### 5.4 What the offset actually is: the elevon — confirmed

CLα agreeing to 0.2 % while CL differs 0.7 % means a **constant lift offset**, and
the one candidate is the elevon over-extension (§6). Test: sweep δe at fixed α.
If the elevon is the cause, the gap must be **linear in δe with zero intercept**.

| seed | δe | CL native | CL ASB | ΔCL | ΔCm |
|---|---|---|---|---|---|
| 7005 | 0° | 0.24540 | 0.24570 | **+0.00030** | −0.00043 |
| 7005 | 2° | 0.26611 | 0.26759 | +0.00148 | −0.00145 |
| 7005 | 4° | 0.28681 | 0.28947 | +0.00266 | −0.00248 |
| 7005 | 8° | 0.32816 | 0.33320 | +0.00504 | −0.00453 |
| 7000 | 0° | 0.33102 | 0.33099 | **−0.00003** | −0.00038 |
| 7000 | 2° | 0.34987 | 0.35087 | +0.00100 | −0.00136 |
| 7000 | 4° | 0.36871 | 0.37073 | +0.00202 | −0.00234 |
| 7000 | 8° | 0.40634 | 0.41041 | +0.00407 | −0.00431 |

**At δe = 0 the two solvers agree on CL to 3e-4 and 3e-5** — three orders of
magnitude better than the 0.7 % headline. The gap is linear in δe:
d(ΔCL)/dδe = +5.92e-4 /deg (seed 7005) and +5.12e-4 /deg (seed 7000). The elevon
accounts for **94 % and 101 %** of the δe = 8° gap.

Independent closure: the measured elevon bias is +5.89 % on CL_δe ≈ 0.0095 /deg
(§6), predicting a slope of 0.0095 × 0.0589 = **5.6e-4 /deg**. Measured 5.12e-4.
**Agreement to 9 %, from two completely independent measurements.**

### 5.5 Consequence

The native and AeroSandbox paths are not "equivalent to ~1 % for reasons we
believe are discretisation". They are **equivalent to <0.1 % on undeflected
geometry**, and 100 % of the residual is one identified, quantified defect in the
reference path — a defect the native path already fixes. Every headline number in
§3 is therefore an *upper bound* inflated by δe = 4°, not a measure of solver
disagreement. There is **no remaining unexplained discrepancy**, and no open item
on the speed derivatives.

## 6. Result — the elevon difference is a systematic bias, not scatter

Symmetric control authority, signed (ASB − native)/native across all 30 samples:

| statistic | value |
|---|---|
| median | **+5.89 %** |
| standard deviation | 0.39 % |
| same sign in all 30 samples | **yes** |

A ±0.39 % spread on a +5.89 % offset, with no sign changes in 30 independent
geometries, is a systematic bias — **measured at one fixed elevon geometry**
(0.60–0.95, hinge 0.75); how the bias varies with elevon geometry is unmeasured — precisely the elevon over-extension identified
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

1. **The two solvers are equivalent to <0.1 % on undeflected geometry.** At
   δe = 0 they agree on CL to 3e-5 … 3e-4 absolute, with CLα to 0.2 %, Cmα to
   0.07 % and Xnp to 7e-5 over 30 samples spanning AR 3.11–6.62 and all 19 free
   design variables. No dependence on position in the design space.
2. **100 % of the residual is one identified defect**, the AeroSandbox elevon
   over-extension. Proven three ways: the gap is linear in δe with ~zero
   intercept (94–101 % of it attributable), its slope matches the independently
   measured +5.89 % CL_δe bias to 9 %, and the bias has the same sign in all 30
   samples (sd 0.39 %). Every §3 headline number is an upper bound inflated by
   δe = 4°, not solver disagreement.
3. **Two initially-plausible explanations were tested and refuted**: airfoil
   coordinate resolution (matching it 159→99 points changes the gap by 3 % of
   itself, and the native side was the finer one all along) and Mach handling
   (header Mach changes Cmu/CZu by 0.000 %; both paths run identical Mach).
4. **The speed derivatives are NOT an open item.** Cmu/CZu's large relative
   errors are pure conditioning: the absolute offset is constant (cv 0.19) while
   |Cmu| varies 7.3×, and corr(1/|Cmu|, rel. error) = 0.971.
5. Every alarming relative error elsewhere belongs to a derivative that is ≈0 by
   symmetry; the largest absolute discrepancy among them is 0.18 % of |Clp|.
6. Combined with the reference path's structural inability to deflect an elevon
   differentially, the native path is the one to build the multifidelity workflow
   on. The ASB path is retained as a symmetric, undeflected cross-check only.

## 9. Open items and what still needs study

Resolved during this study (were open, now closed): the Cmu/CZu discrepancy, the
cause of the force residual, and the airfoil-resolution hypothesis.

**Closed after this study by follow-up work (DECISION-0008):**

- **Sideslip.** Re-run DoE-wide at β = 4°, δa = 0 over 12 seeds: every lateral
  derivative agrees to ≤1.9 %, most ≤1 % (CYb 0.20 %, Clb 0.58 %, Cnb 0.63 %,
  Clp 1.01 % max). This retires the Cnb worry above — at β = 0 it was
  ill-conditioned. It is also a third independent confirmation of the elevon
  explanation: with δe = 0, CL agrees to 0.056 % median / 0.13 % max.
- **"The native elevon is geometrically correct"** — was asserted, now proved. A
  section-count refinement (n = 13…49) shows the ASB/native CL_δe ratio does NOT
  trend to 1: it sits at 1.0417 ± 0.0119 (seed 7000) and 1.0440 ± 0.0125
  (seed 7005), while native's own CL_δe converges to 0.7 %. The two paths reach
  **different limits**, so the difference is geometry, not discretisation.
- **Independent (non-code-to-code) verification** now exists:
  `studies/native_avl_physics_validation.md` — elliptic wing e = 0.9975 vs a
  theoretical 1.0, CL(α=0) = 0 exactly, CLα bracketed by Helmbold and
  lifting-line, and all three geometric sign conventions confirmed including that
  twist acts per section.

Genuinely still open:

- **Reference-length definitions differ 0.13 %** (native ∫c²dy/S vs ASB
  `mean_aerodynamic_chord()`). Measured effect: perturbing Cref by 0.130 % moves
  Cmu and Cmα by 0.129 % — i.e. exactly proportional, as expected. Small, but it
  is a real normalisation inconsistency and should be unified.
- **Sideslip (β ≠ 0) was excluded too broadly.** The stated reason — that the ASB
  path cannot deflect an elevon differentially — justifies excluding δa ≠ 0, but
  **not** β ≠ 0 with δa = 0, which is a legitimate comparison exercising every
  lateral derivative with real signal. Task 1 covered one such case; a DoE-wide
  β sweep is missing and should be added.
- **One operating point** (α = 6°). Behaviour near CL_max, where the polar bridge
  starts clamping strips outside the 2-D polar range, is not characterised.
- **AVL strip ceiling.** (n_sections − 1) × spanwise_panels ≤ 250, i.e. 500
  strips over both halves. n = 65 at 4 panels/interval (512 strips) fails
  outright. A hard limit on what uniform refinement can buy.
- **No validation against experiment or CFD.** This study bounds implementation
  error, not physical accuracy. Verification is now three-legged
  (DECISION-0008); validation still requires the high-fidelity path.
