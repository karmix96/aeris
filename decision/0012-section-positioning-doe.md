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

Two runs, both with worst-case aggregation over designs × angles and a normalized
(error/typical-scale) metric that removes the α=0 near-zero inflation:

- **Primary — the full study at the production mesh c16s2u**, all **30 normal + 6
  extreme designs**, reference = densest-affordable uniform (N=89).
- **Cross-check — a converged-reference run at c8s1u** (uniform-N=201, Richardson
  < 0.6%), which the c16s2u vortex cap forbids. Section-placement error is
  **separable from the panel mesh** (2.74% at c16s2u vs 3.04% at c8s1u), so this
  is a legitimate cross-check of the same quantity.

**1. The hard points do essentially all the work** — production mesh c16s2u,
36 designs, worst-key resolvable error vs the densest-affordable reference:

| placement | median | worst-case |
|---|---|---|
| uniform, **no** mandatory nodes | 12.7 % | **34.8 %** |
| uniform **+ hard-point pins** | **1.0 %** | **7.8 %** |
| adaptive density placement | 1.6 % | 9.3 % |

Pinned-uniform beats no-pins on **35/36** designs — the pins (control edges +
planform breaks + fixed-airfoil stations) cut the median error more than
**12×**. (The converged-reference c8s1u run gives the same story: 21.1% → 5.2%.)

**2. Adaptive density placement never helps.** At the production mesh it beats
pinned-uniform meaningfully (>0.3 pp) on **0 / 36** designs; worst-case 9.3% vs
7.8%. Against the *converged* c8s1u reference it loses outright on all **14**
designs tested (6 hard + 8 normal), worst 2.9% vs 9.1%. Adaptive *does* lower the
control-gain ramp fraction (0.01–0.1 vs 0.12–0.39) — it does what it is told — but
equidistributing the free budget **starves smooth-but-loaded regions** and the
error rises. This is the "reduces the ramp yet worsens the error" paradox
DECISION-0011 flagged in its flawed-metric section.

**A finding the production mesh forced into the open:** c16s2u **cannot host a
converged section reference** — its 6000-vortex cap limits sections to N≈89, and
dense uniform is only converged there to ~1% (33/36 designs < 1%, 3 sensitive
outliers up to 14%). A converged reference needs N≈150–200, affordable only at
reduced panel density. So the *count* question genuinely cannot be answered at
c16s2u alone; it is answered on the separability-justified reference mesh.

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

- The placement decision is established on **all 36 designs** (30 normal + 6
  extreme) × angles {−2,0,+4} at the validation control state (sym+4,diff+4), **at
  the production mesh c16s2u** — no transfer assumption. The adaptive-loses result
  is additionally confirmed against a fully converged reference (c8s1u, 14 designs,
  adaptive lost 14/14). Robust.
- **NOT yet run** (recommended before this fully supersedes DECISION-0011 in
  production): the complexity horse-race (Stage 5 — only the production adaptive
  metric was tested, not the M3 hybrid, and the G6 predictivity gate); the DoE
  ranking gate (G5); the trim/stability decision gate (G4, |Δδ_trim| ≤ 0.5°); the
  deflection-transfer check (G9); honest timings (G9); and an isolation of the
  DECISION-0011 reversal (reproduce its exact CL_δe/α=6 test against the converged
  reference). The placement conclusion is monotone and unanimous and is unlikely to
  move; the count recommendation should be confirmed against the trim gate.
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
