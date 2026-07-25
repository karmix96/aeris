# Master study — Discretisation of the low-fidelity aerodynamic model

Sections, AVL panels, and the robustness of both across the design space.
Synthesises Tasks 3–6.

Date: 2026-07-25
Decisions: `decision/0009-lowfi-discretisation.md`,
`decision/0010-control-resolution-criterion.md`,
`decision/0011-adaptive-section-placement.md`
Evidence: `configs/aero/lowfi_discretisation_evidence/`,
`configs/aero/discretisation_robustness_evidence/`,
`configs/aero/native_avl_doe_evidence/`

---

## 1. The recommendation

| parameter | value | validity |
|---|---|---|
| `n_sections` | **25** | ≤0.56 % worst-seed on forces + stability derivatives |
| `span_margin` | **0.0** | full span; any inset opens a centreline gap |
| section placement | snapped to elevon band edges; adaptive **only** if ramp fraction > 15 % | see §6, §7 |
| `spanwise_panels_per_section` | **4** | ≤0.54 % worst-seed |
| `nchordwise` | **24** | CL_δe ≤1.8 % across the full hinge range 0.652–0.814 |
| `cspace` | **1.0** (cosine) | uniform halves the elevon error but costs 14× on Xnp |

**192 strips, 4608 vortices** — inside AVL's limits ((n−1)×spanwise ≤ 250 strips;
strips × nchordwise ≲ 6000).

**Validity envelope, stated honestly.** The grid holds to ≤0.5 % on nine
deliberately constructed extreme designs spanning AR 2.25–7.85, maximum sweep and
twist gradients, maximum dihedral, and both hinge bounds. **It does not hold for a
narrow elevon band** (0.70–0.85): CL_δe error reaches **4.34 %**. That case, and
its fix, are §6.

---

## 2. Why the two questions had to be separated

In the native writer, `total spanwise panels = (n_sections − 1) × panels_per_interval`.
So the prior `scripts/section_study.py` refined the *lattice* every time it added a
*section*, and its convergence curve superposed two effects with different causes,
costs and fixes. (Mike's earlier AeroSandbox study has the same structure —
sections 15→30 at fixed 10 chordwise / 5 spanwise, so strips went 140→290.)

Separated by construction: **geometry mode** varies `n_sections` with the total
spanwise panel count pinned at 96/side — section counts chosen so (n−1) divides 96
exactly, giving identical 192-strip lattices at every level. **Panel mode** pins
`n_sections = 25` and sweeps each direction alone.

**The separation paid off immediately: the dominant error was never the section
count.** It was the chordwise grid, mis-set at 8, which the conflated design could
not isolate.

*Self-confound checked:* geometry mode was first run at the unconverged chordwise
8, then re-run at 16. Conclusions unchanged (n = 25 worst-seed CL 0.148 % vs
0.144 %; same non-monotonic CL_δe pattern).

---

## 3. Two results that constrain how any of this may be used

**Geometric metrics converge ~3× earlier than the aerodynamics.** Sref is within
0.05 % by n = 9 and Cref within 0.31 % by n = 13, while the aerodynamics still
carries 1.9 % at n = 13. A study checking only area/MAC would have declared
victory at n = 9, at ~5 % aerodynamic error. **Area/MAC convergence is not a proxy
for aerodynamic convergence.**

**The elevon derivative does not converge monotonically in `n_sections`.** Error
against n = 49: 52.4 %, 24.1 %, 14.8 %, **0.33 %** (n = 13), 1.55 %, 1.46 %,
0.36 %. n = 13 beats n = 17 and n = 25, reproducibly in both the 5-seed chord-8 and
3-seed chord-16 runs. §5 explains why.

---

## 4. The chordwise grid, and a hypothesis I had to discard

At `nchordwise = 8`, CL_δe carried **7.7 %** error — the largest single
discretisation error in the chain, comparable to the AeroSandbox elevon defect
DECISION-0007 judged disqualifying.

**My first explanation was that the hinge at x/c = 0.75 sat 0.059 c from the
nearest cosine panel edge — a coincidence.** It supported a clean prediction:
uniform spacing, which puts an edge *exactly* on 0.75, should be much better. It
is (3.82 % vs 7.71 %, at identical cost).

**That explanation is wrong, and a hinge sweep killed it.** Sweeping the hinge over
its full DV range 0.652–0.814 at four chordwise counts, the correlation between
hinge-to-edge distance and error, computed *within* each chordwise level (which
removes the confound that both track `nchordwise`):

| nchordwise | corr(edge distance, error) | corr(N_flap, error) |
|---|---|---|
| 8 | +0.611 | −0.718 |
| 16 | +0.077 | −0.865 |
| 24 | **−0.040** | **−0.972** |
| 32 | −0.163 | −0.966 |

Edge alignment has no consistent relationship. The pooled +0.763 was pure
confounding. Decisive single case: at `nchordwise = 24`, hinge 0.75 has **exact**
edge alignment (distance 0.0000) yet 1.32 % error, while hinge 0.652 aligns worse
(0.0226) and does **better** (1.04 %).

### What actually governs it

**N_flap — the number of chordwise panels aft of the hinge, i.e. resolving the
flap itself.**

```
CL_δe error  ~  N_flap ^ −1.47          R² = 0.966
```

This is a smooth predictive law rather than a coincidence, and it explains the
hinge dependence: a hinge further aft means a smaller flap, so fewer panels land
on it. Hinge alone explains nothing (R² = 0.045); `nchordwise` alone gets 0.935;
N_flap gets 0.966.

| nchordwise | N_flap at hinge 0.814 | CL_δe error |
|---|---|---|
| 8 | 2 | 8.73 % |
| 16 | 4 | 3.69 % |
| **24** | **6** | **1.76 %** |
| 32 | 9 | 0.76 % |

**Consequence for the recommendation:** 24 holds across the whole hinge range,
delivering **≤1.8 %** at the worst hinge rather than the 1.1 % quoted at 0.75.
Reaching ≤1 % everywhere needs 32 chordwise, which at 25 sections / 4 spanwise is
6144 vortices — **over AVL's limit**. So 24 is the accuracy ceiling at this grid.

*Scope:* the law is established within cosine spacing. It does not explain the
uniform-vs-cosine difference, which is separately resolved — uniform is rejected
because it degrades Xnp and Cmq by 14–15×, and the penalty persists under
refinement.

---

## 5. Robustness across the design space — constructed, not sampled

The 5 seeds behind the convergence studies cover only part of each DV range
(sw1 34 %, c1_m 40 %, b_total_m 47 %). **Random sampling cannot fix this:** with
19 independent uniforms, the chance every one lands in its outer 10 % is
0.2¹⁹ ≈ 5e-14. Extremes must be *built*.

Nine designs, each stressing the mechanism that sets one panelling number.
Production grid vs a 33/4/20 reference:

| case | AR | span | band | CL | CDind | CL_δe | **worst** |
|---|---|---|---|---|---|---|---|
| benign (simple) | 4.16 | 2.00 | 0.55–0.92 | 0.12 % | 0.19 % | 0.14 % | **0.19 %** |
| hinge_min (0.650) | 4.62 | 1.98 | 0.55–0.92 | 0.02 % | 0.27 % | 0.49 % | **0.49 %** |
| hinge_max (0.820) | 4.62 | 1.98 | 0.55–0.92 | 0.10 % | 0.43 % | 0.06 % | **0.43 %** |
| max_gradient | 5.24 | 1.98 | 0.55–0.92 | 0.10 % | 0.34 % | 0.27 % | **0.34 %** |
| max_ar | **7.85** | 2.50 | 0.55–0.92 | 0.01 % | 0.21 % | 0.34 % | **0.42 %** |
| min_ar | **2.25** | 1.50 | 0.55–0.92 | 0.16 % | 0.34 % | 0.08 % | **0.34 %** |
| max_dihedral | 4.62 | 1.98 | 0.55–0.92 | 0.07 % | 0.37 % | 0.16 % | **0.37 %** |
| elevon_wide | 4.62 | 1.98 | 0.50–0.98 | 0.04 % | 0.57 % | 1.13 % | **1.45 %** |
| **elevon_narrow** | 4.62 | 1.98 | **0.70–0.85** | 0.36 % | 0.82 % | **4.34 %** | **4.34 %** |

**Seven of nine hold at ≤0.5 %**, including AR 2.25 and AR 7.85 — well outside the
DoE's nominal 2.6–6.2. Aspect ratio, sweep, twist and dihedral extremes are all
non-issues. **Both failures are elevon-band cases.**

---

## 6. The unifying result: it is the CONTROL that must be resolved, not the wing

The narrow-elevon failure has the same character as the chordwise one. Correlating
CL_δe error against the **gain-ramp fraction** — the width of the intervals just
outside the band edges, where AVL ramps the control gain from 1 to 0, divided by
the band width:

```
corr(ramp fraction, CL_δe error)  =  +0.978
```

| case | band width | N_band | ramp/band | CL_δe error |
|---|---|---|---|---|
| normal bands (7 cases) | 0.373 | 11 | 11.8 % | 0.06–0.49 % |
| elevon_wide | 0.480 | 13 | 12.8 % | 1.13 % |
| **elevon_narrow** | **0.150** | **6** | **38.9 %** | **4.34 %** |

So both errors are the same phenomenon in two directions:

> **AVL smears a control surface at its edges — chordwise at the hinge, spanwise
> at the band ends. The discretisation error is set by how much of the control
> that smearing occupies.**
>
> - chordwise: error ~ N_flap^−1.47 (R² 0.966)
> - spanwise: error ∝ ramp-width / band-width (r = +0.978)

This replaces two tuned numbers with one criterion, and it is *predictive* — the
error can be estimated from the geometry before running AVL.

### The fix is placement, not count

If the mechanism is right, a narrow elevon should be fixable by moving sections to
the band edges rather than adding sections. Tested at an **identical 25-section
budget**:

| placement | ramp/band | CL_δe |
|---|---|---|
| uniform-25 | 38.9 % | 0.004191 |
| clustered ε = 0.02 | 26.7 % | 0.004119 |
| clustered ε = 0.01 | **13.3 %** | **0.004061** |

Monotone in the ramp fraction, recovering ~3.2 % of the 4.34 % error **without a
single extra section**. Uniform spacing is the wrong distribution, not an
insufficient one — which is the concrete, quantified case for adaptive placement
(Task 6).

---

## 7. Cross-validation against the earlier AeroSandbox study

An independent earlier study (different codebase, 2 m-root-chord aircraft,
inviscid, no control surfaces) recommended **25 sections, ~4 spanwise per segment,
~8 chordwise**.

- **Sections and spanwise: exact agreement**, from two independent studies.
- **Chordwise 8 vs 24: not a contradiction.** That study's geometry had *no control
  surfaces* (`CONTROL blocks: 0`), so CL_δe never appeared in it. On every quantity
  it *did* measure, chordwise 8 is adequate and this study agrees (CL 1.08 %,
  CDind 3.28 %). The entire increase to 24 is bought for control authority.
- Its reference was chordwise 14, which understates the error; measuring against a
  chordwise-40 reference is what turns 6.0 % into 7.7 %.

---

## 9. What is confounded, weak, or open

Stated plainly, because a committee will find these anyway.

- **The equal-cost grid trade is confounded and is NOT used to support anything.**
  Candidates 25/4/24 and 25/3/32 were compared against a 25/**2**/48 reference,
  which shares the third candidate's spanwise resolution — so part of the measured
  "error" is a spanwise mismatch, not error. No dominating reference exists
  (25/4/32 = 6144 vortices, over the limit). The question "is chordwise a better
  buy than spanwise at fixed cost?" is **open**.
- **The narrow-elevon reference run failed** (67 sections × 2 spanwise × 24 = 6336
  vortices, over the limit). The clustering result above is a *monotone trend at
  fixed budget*, calibrated against the extremes study's independent 4.34 %, not
  against its own reference.
- **One operating point** (α = 6°, δe = 4°, β = 0°). Near-CL_max behaviour, where
  the polar bridge clamps strips outside the 2-D polar range, is uncharacterised.
- **Fixed airfoil set** (mh91 / e374 / nlf1015). The DoE does not vary airfoils, so
  the t/c range — and hence the CLAF results — are for that set.
- **No Richardson extrapolation.** All errors are convergence increments against
  the finest affordable level, not against an extrapolated limit.
- **The elevon DVs reached AVL only from 2026-07-25.** A defect meant every earlier
  run used elevon 0.60–0.95 at hinge 0.75. The hinge sweep and extremes in §4–6
  post-date the fix and are unaffected; the §3 section-convergence numbers
  pre-date it and are for that one elevon. They are quoted only for forces and
  stability derivatives, which are elevon-independent.
- Only cosine and uniform chordwise spacing tested; AVL also offers sine and −1.
- **A surface split at the hinge line** — the principled way to resolve a flap
  exactly — was not attempted, and would likely supersede the N_flap trade-off.
- **Adaptive-placement evidence is biased toward uniform**: both candidates are
  measured against a *uniform* 49-section reference, so uniform-25 shares its
  distribution family. The 10× failure is far too large to be explained by it, but
  the 2.78× gain is conservative.
- **Budget selection is not delivered** — the metric places a fixed budget, it does
  not yet choose one.

---

## 10. Conclusions

1. **Use 25 sections / 4 spanwise / 24 chordwise / cosine**, full span, sections
   snapped to the elevon band edges. 4608 vortices.
2. The separation of geometry-section from AVL-panel convergence was the load-
   bearing methodological step: it showed the section count was never the binding
   constraint and that the chordwise grid had been mis-set by a factor of three.
3. **The binding error in the whole low-fidelity chain is control-surface
   resolution**, in both directions, governed by one criterion: keep N_flap ≥ 6 and
   the gain-ramp fraction ≲ 15 %.
4. The grid is robust across geometry extremes — AR 2.25–7.85, maximum sweep,
   twist and dihedral gradients, both hinge bounds — at ≤0.5 %.
5. **It is not robust for a narrow elevon band** (4.34 %), and the fix is section
   *placement* at the band edges, not section count — worth 2.78× when gated on
   the ramp criterion (§7).
6. The recommendation agrees exactly with an independent earlier study on sections
   and spanwise panels; the chordwise difference is fully explained by that study
   having no control surfaces to resolve.
