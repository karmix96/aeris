# DECISION-0012 — Section positioning for the DoE: uniform + hard points, not adaptive density

Status: ACCEPTED (revises DECISION-0011)
Date: 2026-07-30
Owner: Mike (with Claude as lead researcher)
Study: `studies/RUNBOOK_section_positioning_study_v1.md`
Evidence: `configs/aero/section_study/` · code `standalone/section_study/`

## Decision

**Place spanwise sections UNIFORMLY, with mandatory nodes ("hard points") pinned at
the control-surface band edges, the planform breaks, and the fixed-airfoil stations.
Do NOT use information-weighted adaptive density placement.** The lever for accuracy
is the section *count*, not the density distribution.

```
DoE / optimisation  -> uniform placement + hard-point pins  (adaptive OFF)
count guidance      -> N>=~40-50 gets 90% of cells < 1% (median <0.25%); a few
                       control-derivative cells stay ~2% at any affordable N.
```

This **revises DECISION-0011**, which adopted adaptive placement for DoE use. That
decision's apparent win was real but **misattributed**: it came from *snapping the
control-band edges* (pinning), not from the density redistribution — and it was
measured against a non-converged (49-section) reference.

## Why (evidence)

Measured against a **legitimate, converged reference** — dense uniform at N=201,
verified Richardson-converged (< 0.6% between N=151 and 201) — with worst-case
aggregation over designs × angles and a normalized (error/typical-scale) metric
that removes the α=0 near-zero inflation. Section-placement error was shown
**separable from the panel mesh** (2.74% at c16s2u vs 3.04% at c8s1u), so the
reference was built on the cheap mesh where N≈201 is affordable and the *policy*
transfers to the production mesh c16s2u.

**1. The hard points do essentially all the work** (ablation, worst-case over 14 designs):

| placement | worst-case section error |
|---|---|
| uniform, **no** mandatory nodes | **21.1 %** |
| uniform **+ hard-point pins** | **5.2 %** |
| adaptive density placement | 10.8 % |

Pinning the control edges + planform breaks + fixed-airfoil stations cuts
worst-case error by **+2.9 to +18.4 percentage points**.

**2. Adaptive density placement is counterproductive** — 2× worse than pinned
uniform, on every design tested:

| design set | uniform+pins | adaptive | adaptive wins |
|---|---|---|---|
| 6 hard/extreme cases | worst 2.9 % | worst 9.1 % | **0 / 6** |
| 8 normal LHS designs | worst ~2 % | worst ~6.6 % | 0 / 8 |

Adaptive *does* lower the control-gain ramp fraction (0.01–0.1 vs 0.12–0.39) — it
does what it is told — but equidistributing the free budget **starves
smooth-but-loaded regions**, and the error rises. This is the same "reduces the
ramp yet worsens the error" paradox DECISION-0011 flagged in its flawed-metric
section; against a converged reference it dominates.

**3. Count convergence (pinned uniform):**

| N | median | p90 | worst |
|---|---|---|---|
| 25 | 0.64 % | 1.58 % | 2.89 % |
| 49 | 0.23 % | 0.81 % | 2.21 % |
| 101 | 0.12 % | 0.39 % | 1.92 % |

Typical accuracy is excellent by N=25; **N≈49 gets 90 % of cells under 1 %**. A
few control-derivative cells on specific designs plateau at ~1.8–2.9 % and do not
improve with N — section-limited, consistent with the panelling study's finding
that control effectiveness is under-resolved at affordable discretisation.

**4. `cd_ind` and `hinge_sym` are placement/print-limited**, not resolvable to < 1 %
by placement OR count: induced drag depends on the spanwise strip *distribution*
(AVL Trefftz integral) at the ~2–3 % level irreducibly; the symmetric hinge moment
sits near AVL's 6-decimal print floor. Report these separately; do not gate on them.

## The reference-legitimacy correction (the methodological point to defend)

The study's first legitimacy criterion — "uniform, adaptive and clustered agree at
N_ref" — was wrong and was corrected mid-run: adaptive/clustered stay non-uniform
by design, so requiring them to match a dense uniform mesh conflates candidate
convergence with reference convergence. The correct, and sufficient, test is
**Richardson convergence of dense uniform in N**. The prior study's error was a
*sparse* uniform reference, not uniformity itself. This is why DECISION-0011's
adaptive advantage evaporates here: it was partly reference bias.

## Scope and honest limits

- Established on **14 designs** (8 normal LHS + 6 extremes) × angles {−2,0,+4} at
  the validation control state (sym+4,diff+4), on the c8s1u reference mesh with
  policy transfer justified by separability. Robust: adaptive lost on **all 14**.
- **NOT yet run** (recommended confirmatory work before this fully supersedes
  DECISION-0011 in production): the full 30-design DoE ranking gate (G5), the
  trim/stability decision gate (G4, |Δδ_trim| ≤ 0.5°), the deflection-transfer
  check (G9), and honest end-to-end timings (G9). The placement conclusion is
  unlikely to move — it is monotone and unanimous — but the count recommendation
  should be confirmed against the trim gate.
- Reference is converged-section AVL, **not CFD/truth**; AVL's own model error
  (vortex lattice + strip viscous, ~1.5 % short on elevon power per the panelling
  study) sits underneath all of this.

## Action

- Set `geometry.aero_discretisation.section_placement = never` (uniform) for DoE
  runs; keep `snap_sections_to_control = true` (the hard-point pins) — that is the
  part that matters. `ramp_fraction` remains a useful *diagnostic* but must not
  drive placement.
- Keep `n_sections` at 25 for screening (median 0.64 %); raise toward ~49 when a
  run's control-derivative accuracy must be tight. Do not expect < 1 % worst-case
  on `cd_ind`/`hinge` from any section setting.
- The `concentration()` metric and adaptive density path remain in the code but are
  **not used**; annotate accordingly.
