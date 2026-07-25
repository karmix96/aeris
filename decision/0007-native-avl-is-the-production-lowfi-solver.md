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
- **Cmu / CZu are conditioning artefacts, not a defect — RESOLVED.** Their large
  relative errors (max 10.3 % / 4.2 %) come from a constant absolute offset
  (mean 0.0045, cv 0.19) divided by an |Cmu| that varies 7.3× across the DoE;
  corr(1/|Cmu|, relative error) = **0.971**. No separate cause exists. Report them
  with their magnitude, or on a common scale — never as a bare relative error.

## The residual is fully accounted for

**At δe = 0 the two paths agree on CL to 3e-5 … 3e-4 absolute** (<0.1 %). The
entire ~0.7 % CL / 2.4 % CDind headline is the elevon over-extension, proven by a
δe sweep: the gap is linear in δe with ~zero intercept, 94–101 % attributable,
and its slope (5.12e-4 /deg) matches the independently measured +5.89 % CL_δe bias
prediction (5.6e-4 /deg) to 9 %.

Two plausible explanations were tested and **refuted**:

- *Airfoil coordinate resolution* — and the premise was backwards: native writes
  **159** points per section, AeroSandbox downsamples to **99**. Re-running native
  at a matched 99 points changes the disagreement by ~3 % of itself. Native's own
  resolution convergence is 0.1 % between 99 and 239 points (319+ exceeds AVL's
  IBX limit and fails).
- *Mach handling* — the header Mach changes Cmu/CZu by 0.000 % (ablation with the
  `sb` dump; an earlier test that dumped only `st` was inconclusive for these very
  quantities). Both paths run at identical Mach 0.0820.

Remaining known inconsistency: **Cref differs 0.13 %** (native ∫c²dy/S vs ASB
`mean_aerodynamic_chord()`), which moves Cmu and Cmα by exactly 0.129 %. Small but
real; should be unified.

## Not established by this decision

- Any validation against experiment or CFD. This is code-to-code equivalence; it
  bounds implementation error, not physical accuracy.
- That 25 sections / 8×4 panels is a converged discretisation (DECISION-0008).
- That 30 samples suffice for these statistics to be design-space representative
  (Task 5). Coverage itself is confirmed: all 19 free DVs varied over essentially
  their whole ranges (sweeps −39.2…−6.3°, all four twists, dihedrals b2/b3, all
  three elevon DVs); only `dihedral_b1` is pinned, by design.
- Agreement at other angles of attack, near CL_max, or in **sideslip** — the
  β ≠ 0 / δa = 0 comparison is legitimate and was wrongly excluded; it is
  outstanding.
- Any independent (non-code-to-code) check: the two paths share the CDCL
  injection and strip-drag integration, and both read twist from the same source,
  so a shared error or a twist-convention error is invisible to this comparison.
