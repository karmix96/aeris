# Study — Independent physics validation of the native AVL writer

Date: 2026-07-25
Decision produced: `decision/0008-native-avl-verification-standard.md`
Script: `standalone/lowfi_avl_study/validate_native_avl_physics.py`
Tests: `tests/aero/test_native_avl_physics_validation.py` (10 regression gates)
Evidence: `configs/aero/native_avl_verification_evidence/physics_validation.*`

## 1. Question — and why the previous studies could not answer it

Tasks 1 and 3 compared the native pyGeo→AVL path against the AeroSandbox
reference path and found agreement to <0.1 % on undeflected geometry. That bounds
*implementation divergence* between two wrappers. It cannot establish
correctness, for two structural reasons:

1. **Shared code.** Both paths call the same `inject_polar_cdcl` and the same
   `_compute_strip_profile_drag`. A bug in either is invisible to their agreement.
2. **Shared inputs.** Both writers read `twist_deg`, `x_le_m` and `z_le_m` from
   the *same* section objects. A sign error, or a wrong reference axis, would be
   *identically wrong in both* — and they would agree to 1e-7 while both being
   wrong. **No amount of code-to-code comparison can detect this class of error.**

This is the gap that matters most for a defensible workflow, and it is exactly the
class of error that silently invalidates an entire optimisation campaign: a wing
optimised with an inverted twist convention converges to a physically wrong shape
while every internal consistency check passes.

So this study validates the writer against **closed-form aerodynamics** and
against **sign conventions**, on wings whose answers are known independently of
any code in this repository.

## 2. Method

Wings are built by a local `SyntheticSection` stub — a duck-typed stand-in
exposing only what `write_native_avl` reads (`y_m`, `chord_m`, `x_le_m`,
`z_le_m`, `twist_deg`, `span_fraction`, `cst.coordinates()`). **pyGeo is not
involved at all.** Two consequences:

- the reference answers are analytic, not produced by another AERIS component;
- it demonstrates as a side effect that the writer is genuinely backend-
  independent, i.e. the geometry backend is swappable.

Airfoil: NACA 0012 from the closed-form Jacobs/Ward/Pinkerton thickness
distribution — symmetric and zero-camber by construction, so any non-zero lift at
zero incidence is a defect rather than a property of the section.

All cases: aspect ratio 6.0 exactly by construction, 41 sections, 12 chordwise ×
3 spanwise panels per interval, V = 28 m/s.

Closed-form references at AR = 6:

| reference | value |
|---|---|
| Helmbold low-AR lift slope, 2πAR/(2+√(AR²+4)) | 4.5287 /rad |
| Lifting-line with e = 1, a₀/(1+a₀/(πAR)) | 4.7124 /rad |
| Elliptic-planform span efficiency | e = 1 exactly |
| Unswept straight-wing aerodynamic centre | 0.25 c |

## 3. Results — 11/11 checks pass

| # | check | measured | reference | error |
|---|---|---|---|---|
| A1 | aspect ratio encoded | 5.9938 | 6.0000 | 0.10 % |
| A2 | **elliptic wing e = 1** | **0.99750** | 1.0 | **0.25 %** |
| B1 | symmetric untwisted CL(α=0) | **0.00000** | 0 | 0 |
| B2 | CLα vs Helmbold | 4.4367 | 4.5287 | 2.03 % |
| B3 | unswept neutral point / c | 0.2151 | 0.25 | 0.035 abs |
| C1 | washout reduces CL | 0.2178 | < 0.3896 | ✓ |
| C2 | wash-in increases CL | 0.5609 | > 0.3896 | ✓ |
| C3 | washout unloads the **tip** specifically | −0.1306 | < root change | ✓ |
| D | +10° dihedral makes Clb more negative | −0.1868 | < −0.0507 | ✓ |
| E1 | 30° aft sweep moves Xnp aft | 0.3373 | > 0.0717 | ✓ |
| E2 | 30° aft sweep reduces CLα | 4.0691 | < 4.4367 | ✓ |

### 3.1 The elliptic-wing test is the strongest single result

**e = 0.99750 against a theoretical 1.0.** Elliptic loading is *the*
minimum-induced-drag spanwise distribution, so an elliptic planform must return
e = 1. Producing it requires, simultaneously and correctly:

- the chord law c(y) = c₀√(1−η²) transcribed into SECTION chords,
- the spanwise station positions,
- the reference area and span (Sref, Bref) used to normalise,
- AVL's Trefftz-plane wake integration on the lattice the writer built.

A wrong chord law, a mis-scaled span, an off-by-one in the section loop or an
incorrect Sref all break this test. It passing to 0.25 % is strong evidence the
geometry encoding is correct — not merely self-consistent.

### 3.2 Lift slope brackets correctly

CLα = 4.4367 /rad sits **2.0 % below Helmbold (4.5287)** and **5.8 % below the
e = 1 lifting-line value (4.7124)**. Both relations are correct and expected: a
rectangular wing's loading is less efficient than elliptic, so its 3-D lift slope
*must* fall below the e = 1 result. The value is bracketed on the physically
correct side, not merely "close to something".

### 3.3 Neutral point — passes, but honestly the loosest result

Xnp/c = 0.2151 against the thin-airfoil 0.25, i.e. **3.5 % of chord ahead of the
quarter chord** (14 % relative). Finite-aspect-ratio VLM does place the
aerodynamic centre slightly forward of c/4, so the sign of the deviation is
right, but this is the least tight of the checks and is recorded as such rather
than presented as confirmation. It bounds the moment-reference and chordwise
geometry encoding to ~4 % of chord; a gross error (a half-chord offset, a sign
flip) would be caught, a subtle one would not.

### 3.4 The sign conventions — what code-to-code cannot see

All three geometric sign conventions are confirmed independently:

- **Twist.** Washout (−5° at the tip) reduces CL from 0.3896 to 0.2178; wash-in
  (+5°) raises it to 0.5609. Monotone and correctly ordered about the untwisted
  case.
- **Twist is per-section, not global.** Under washout the strip loading changes by
  **−0.1306 at the tip versus −0.1119 at the root** — the distribution shifts
  inboard rather than scaling down uniformly. A globally applied incidence would
  produce equal changes. This distinguishes "the twist number reached AVL" from
  "the twist reached the *right section*".
- **Dihedral.** +10° dihedral drives Clb from −0.0507 to −0.1868, a 3.7×
  strengthening of roll stiffness in sideslip. This is the textbook dihedral
  effect and confirms the `z_le` sign.
- **Sweep.** 30° aft sweep moves Xnp from 0.0717 m to 0.3373 m (aft) and reduces
  CLα from 4.4367 to 4.0691 (the cos-sweep effect on the effective section slope).
  Confirms the `x_le` sign.

## 4. Assumptions and limits

- **These are inviscid, VLM-level checks.** No CDCL or CLAF is involved; the
  viscous and thickness corrections are validated separately
  (`studies/avl_section_corrections.md`).
- **The references are analytic approximations, not truth.** Helmbold and
  lifting-line are themselves models; agreement to 2 % means "AVL is behaving
  like a vortex-lattice code should", not "AVL is correct to 2 %". Only the
  elliptic e = 1 and the symmetric CL(0) = 0 checks are exact statements.
- **Tolerances are stated up front, not fitted after the fact.** CLα ±10 %,
  e ±0.06, Xnp/c ±0.06, CL(0) ±5e-3. All measured values beat these
  comfortably except Xnp (§3.3).
- **Sign checks are ordering tests, not magnitude tests.** They establish
  direction and, for twist, spanwise locality. They do not certify magnitudes.
- **AR 6, unswept-or-30°, thin symmetric section.** The DoE's BWB planforms are
  more extreme (AR 3.1–6.6, ~30° inboard sweep, 15 % thick, strongly washed out).
  These cases verify the *encoding*, which is planform-independent; they do not
  extrapolate to claim accuracy on the BWB.
- **Discretisation is deliberately fine** (41 sections, 12×3 panels) so
  discretisation is not the limiting error. Convergence at the production
  discretisation is a separate study (Task 4).

## 5. Conclusions

1. The native writer's **geometry encoding is independently validated**, not just
   internally consistent: an elliptic planform returns e = 0.9975 against a
   theoretical 1.0, a symmetric untwisted wing returns exactly zero lift at zero
   incidence, and the aspect ratio round-trips to 0.10 %.
2. The **lift slope is bracketed correctly** between Helmbold and the e = 1
   lifting-line value, on the physically correct side of both.
3. **All three geometric sign conventions are confirmed** — twist, dihedral and
   sweep — by their known physical consequences. Crucially, twist is shown to act
   *per section*, which is the check that no code-to-code comparison could make,
   because both writers read the same twist field.
4. The **writer is backend-independent**: every case here runs it from a
   duck-typed stub with no pyGeo present.
5. The weakest link is the **neutral-point check (0.215 c vs 0.25 c)**, which
   bounds the chordwise/moment-reference encoding to ~4 % of chord. Recorded as a
   limit, not as a confirmation.

## 6. What this still does not establish

- **Physical accuracy against experiment or CFD.** Everything here is
  verification (is the code solving the intended equations correctly?), not
  validation against reality. The high-fidelity ADflow path is where that has to
  come from.
- **Accuracy on BWB planforms.** The encoding is verified; extrapolating the
  ~2 % Helmbold agreement to a swept, twisted, thick BWB would be unjustified.
- **Nonlinear / high-CL behaviour.** All cases are in the linear regime.
- **The chordwise pressure distribution.** Only integrated quantities and
  spanwise loading are checked.
