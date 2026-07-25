# DECISION-0007 — The native pyGeo→AVL path is the production low-fidelity solver

Status: ACCEPTED
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/pygeo_native_vs_asb_avl_doe.md`,
`configs/aero/native_avl_doe_evidence/`

## Decision

`run_pygeo_native_avl_case` (native `.avl` authoring, no `asb.Airplane`) is the
**production** low-fidelity aerodynamic solver for the multifidelity workflow.

`AeroSandboxAVLSolver` (`run_pygeo_avl_case`) is **retained** as a symmetric-case
cross-check and regression reference. It is **not** to be used for lateral or
roll-control results.

## Basis

30 DoE samples, 120 AVL runs, both solvers driven from identical pyGeo sections,
viscous on and off, covering AR 3.11–6.62 and full span 1.52–2.49 m.

**Equivalence established design-space-wide** (max over 30 samples): CL 1.04 %,
L/D 1.25 %, CD 1.92 %, CLα 0.203 %, Cmα 0.070 %, Cmq 0.301 %, Xnp 7.3e-5,
cd_profile 0.111 %. No correlation with aspect ratio (|r| ≤ 0.29, not significant
at n = 30), so the single-geometry result of DECISION-0005 generalises.

**Capability, not just parity, decides it.** The reference path has two structural
limits the native path does not:

1. **No roll degree of freedom.** AeroSandbox's AVL exporter collapses all control
   surfaces into one `all_deflections` variable (SgnDup +1); AVL reports
   `1 Control variables` and the `d2` keystroke addresses nothing. Differential
   elevon deflection is silently ignored.
2. **Elevon over-extension**, a systematic **+5.89 % ± 0.39 %** bias in control
   authority, same sign in all 30 samples — its elevon always reaches one section
   past `elevon_end_frac`, toward the tip where the moment arm is largest.

Since the DoE varies three elevon design variables *in order to optimise control
authority*, a solver that cannot deflect an elevon differentially and biases
symmetric authority by ~6 % cannot be the production path.

## Reporting rules that follow

- **Relative error is not reported for near-zero derivatives.** 30 of 44
  derivatives are ≈0 by symmetry at β = 0; their relative errors reach 135 % on
  absolute differences of ≤6.5e-4 (0.18 % of |Clp|). Any comparison must either
  exclude them or place them on a common well-conditioned scale. Scoring them as
  0 % error because both solvers return ~0 is equally wrong — it flatters the
  headline numbers.
- **Cmu and CZu are NOT trusted from either path** (max 10.3 % / 4.2 % apart,
  versus ≤1.7 % for every other well-conditioned derivative). Two candidate causes
  were experimentally eliminated: the operating Mach is identical (0.0820 in
  both), and the `.avl` header Mach is irrelevant (ablation: setting it to 0
  changes CL and CLα by nothing at 6 s.f. — OPER `mn` supersedes it). Cause
  unresolved; most likely conditioning, since the u-derivatives are small
  residuals of large terms. **Open item — must be resolved before any phugoid or
  speed-stability mode analysis.**

## Accepted, understood differences (not defects)

- **CL differs ~0.7 %, CDind ~2.4 %** from airfoil camber discretisation: the
  native writer is capped at 80 points per surface by AVL's IBX limit, ASB uses
  181. This shifts the zero-lift angle ≈0.05°, so it moves CL but not CLα (which
  agrees to 0.2 %). Induced drag, being quadratic in the lift distribution,
  amplifies it.
- **Cref differs 0.13 %**: native uses ∫c²dy/S, ASB uses
  `mean_aerodynamic_chord()`. Worth unifying, harmless as is.

## Not established by this decision

- Any validation against experiment or CFD. This is code-to-code equivalence; it
  bounds implementation error, not physical accuracy.
- That 25 sections / 8×4 panels is a converged discretisation (DECISION-0008).
- That 30 samples suffice for these statistics to be design-space representative
  (Task 5).
- Agreement at other angles of attack or in sideslip.
