# DECISION-0008 — Verification standard for the low-fidelity solver, and closure of the Task-3 gaps

Status: ACCEPTED
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/native_avl_physics_validation.md`,
`configs/aero/native_avl_verification_evidence/physics_validation.*`,
`configs/aero/native_avl_doe_evidence/beta_and_asymptote.txt`

## 1. The standard: code-to-code agreement is NOT verification

**Decision.** No claim about low-fidelity solver correctness may rest on
native-vs-AeroSandbox agreement alone. Every such claim needs at least one
check that does not share code or inputs with the thing being checked.

**Why this is a decision and not a platitude.** The two paths share
`inject_polar_cdcl` and `_compute_strip_profile_drag`, and both read `twist_deg`,
`x_le_m` and `z_le_m` from the *same* section objects. Two error classes are
therefore **structurally invisible** to their agreement:

- a bug in the shared viscous code;
- a sign or reference-axis error in a geometry field — identically wrong in both
  writers, agreeing to 1e-7 while both are wrong.

The second is the one that silently destroys an optimisation campaign: a wing
optimised with an inverted twist convention converges to a physically wrong shape
while every internal consistency check passes.

**The standard adopted** — three independent legs, all now in place:

| leg | what it establishes | where |
|---|---|---|
| closed-form aerodynamics | the geometry encoding is right, not just consistent | `tests/aero/test_native_avl_physics_validation.py` |
| sign-convention physics | twist / dihedral / sweep act in the right direction and at the right *place* | same |
| ablation | a correction AVL is given is actually applied, by the predicted magnitude | `tests/aero/test_avl_section_corrections.py` |

## 2. Physics validation result — 11/11, with the elliptic wing as the keystone

Analytic wings built from a duck-typed stub (no pyGeo at all, which also proves
the writer is backend-independent), checked against closed-form answers:

- **Elliptic planform, AR 6: e = 0.99750 against a theoretical 1.0 (0.25 %).**
  Elliptic loading is the minimum-induced-drag distribution, so this simultaneously
  validates the chord law, the spanwise stations, Sref/Bref and AVL's Trefftz
  integration on the lattice the writer built. This is the single strongest
  geometry-encoding result we have.
- **Symmetric untwisted wing: CL(α=0) = 0.00000 exactly.**
- **CLα = 4.4367 /rad**, 2.0 % below Helmbold (4.5287) and 5.8 % below the e = 1
  lifting-line value (4.7124) — bracketed on the physically correct side, since a
  rectangular wing's loading is less efficient than elliptic.
- **Twist acts per section**: washout changes the tip strip cl by −0.1306 versus
  −0.1119 at the root, so the loading shifts inboard rather than scaling down.
  This is the check no code-to-code comparison can make.
- **Dihedral**: +10° drives Clb from −0.0507 to −0.1868 (3.7× stiffer in
  sideslip). Confirms the `z_le` sign.
- **Sweep**: 30° aft moves Xnp from 0.0717 m to 0.3373 m and cuts CLα to 4.0691.
  Confirms the `x_le` sign.

**Weakest link, recorded as such:** the unswept neutral point comes out at
0.2151 c against the thin-airfoil 0.25 c — 3.5 % of chord forward. The sign of the
deviation is correct for finite-AR VLM, but this check only bounds the
chordwise/moment-reference encoding to ~4 % of chord. It would catch a gross
error, not a subtle one.

## 3. Closure — sideslip was wrongly excluded from Task 3

Task 3 compared symmetric cases only, justified by the AeroSandbox path having no
differential-elevon degree of freedom. **That reasoning was too broad.** It
justifies excluding δa ≠ 0; it does not justify excluding β ≠ 0 with δa = 0,
which is the only way to exercise the lateral derivatives with real signal.

Run DoE-wide (12 seeds, α = 6°, **β = 4°**, δa = 0, δe = 0):

| derivative | median \|value\| | median rel. | max rel. |
|---|---|---|---|
| CYb | 1.6e-2 | 0.13 % | 0.20 % |
| Clb | 8.3e-2 | 0.23 % | 0.58 % |
| Cnb | 6.7e-3 | 0.26 % | 0.63 % |
| Clp | 3.2e-1 | 0.42 % | 1.01 % |
| Clr | 9.6e-2 | 0.39 % | 0.97 % |
| Cnr | 8.2e-3 | 0.41 % | 0.99 % |
| CYp | 1.4e-2 | 0.48 % | 1.87 % |
| Cnp | 1.3e-2 | 0.20 % | 0.61 % |
| CYr | 1.5e-2 | 0.29 % | 0.59 % |
| CL | 2.9e-1 | **0.056 %** | **0.13 %** |

**Every lateral derivative agrees to ≤1.9 %, most to ≤1 %.** This retires the
Task-3 worry about Cnb (3.07 % max there): at β = 0 it was ill-conditioned; with
real signal it agrees to 0.63 %.

It is also a **third independent confirmation of the elevon explanation**: with
δe = 0, CL agrees to 0.056 % median / 0.13 % max, versus 0.69 % / 1.04 % at
δe = 4° in Task 3.

## 4. Closure — the elevon difference is a REAL geometry difference, proved

Task 3 asserted the native elevon extent is "geometrically correct". Differing
from AeroSandbox at one discretisation does not establish which is right. The
decisive test is whether the two converge to the **same** limit under refinement.

Section-count refinement at δe = 6°, inviscid, ratio ASB/native of CL_δe:

| n_sections | seed 7000 | seed 7005 |
|---|---|---|
| 13 | 1.0465 | 1.0495 |
| 17 | 1.0489 | 1.0516 |
| 25 | 1.0548 | 1.0575 |
| 33 | 1.0204 | 1.0217 |
| 49 | 1.0380 | 1.0396 |
| **mean ± sd** | **1.0417 ± 0.0119** | **1.0440 ± 0.0125** |

The ratio **does not trend toward 1.0**. Meanwhile native's own CL_δe is
essentially converged (0.009575 → 0.009506 from n = 13 to 49, 0.7 %).

**Conclusion: the two paths converge to different limits ~4.2 % apart.** The
difference is therefore a genuine geometry difference, not discretisation — and
the direct cause is already identified: AeroSandbox tags a section *outboard* of
`elevon_end_frac`, so its elevon reaches y/y_tip = 1.000 where the geometry says
0.950. The native value is the geometrically correct one.

**Honest magnitude:** the bias measures +2.0 % to +5.8 % depending on section
count (mean +4.2 % here; +5.89 % ± 0.39 % in the Task-3 DoE at n = 25). It is
never zero, never negative, and does not shrink under refinement. Quote it as a
range, not a single figure.

## 5. New hard constraint discovered: AVL's strip limit

**n = 65 sections × 4 spanwise panels × 2 halves = 512 strips exceeds AVL's
NSMAX = 500** and the run fails. The binding constraint on the section budget is

    (n_sections − 1) × spanwise_panels_per_section ≤ 250

This is a hard ceiling on how much geometric fidelity the uniform-section approach
can buy, and it is a direct argument for adaptive section placement (Task 6): the
only way past it is to spend sections where they matter rather than everywhere.

## 6. Still not established

- **Physical accuracy.** Everything above is verification (is the code solving the
  intended equations correctly), not validation against experiment or CFD. That
  must come from the ADflow path.
- **Accuracy on BWB planforms.** The *encoding* is verified on AR-6 rectangular
  and elliptic wings; the ~2 % Helmbold agreement must not be extrapolated to a
  swept, twisted, 15 %-thick BWB.
- **Nonlinear / near-CL_max behaviour**, where the polar bridge starts clamping
  strips outside the 2-D polar range.
- **Chordwise pressure distribution** — only integrated loads and spanwise
  loading are checked.
- The **Cref definition mismatch** (0.13 %, native ∫c²dy/S vs ASB
  `mean_aerodynamic_chord()`) remains unresolved; it moves Cmu and Cmα by exactly
  0.129 %.
