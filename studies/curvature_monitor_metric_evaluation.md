# Study — Evaluation of the proposed curvature-monitor metric, and the metric AERIS now uses

Date: 2026-07-26
Decision produced: `decision/0012-spanwise-monitor-and-feature-pins.md`
Study evaluated: `standalone/lowfi_avl_study/curvature_monitor_aero_study.py`
(Codex, 100 native AVL runs, ~1.5 h)
Evidence: `artifacts/curvature_monitor_aero_study/`, `configs/aero/monitor_evaluation_evidence/`

## 1. Verdict in one paragraph

**The study's method is better than the one it replaces, and its selected winner is
wrong.** It fixes three real weaknesses in the previous AERIS metric, and it is the
first monitor study here to rank on *actual AVL output error* rather than on a
geometry proxy — a genuine advance. But the ranking statistic is dominated by
AVL's printed output precision on one near-zero derivative, and once that is
removed the selected policy falls from 1st to 7th of 9. A different policy from
the same study wins, and it happens to be the one with the best physical
justification.

## 2. What the study got right — three fixes AERIS needed

Each of these was an open weakness in `geometric_information.py`, and the study
resolves it:

| weakness | previous AERIS | the study |
|---|---|---|
| **kinks unresolvable by a curvature monitor** | none — the monitor was expected to find breaks itself | **hard pins** at root, tip, the two BWB planform/airfoil breaks, and the elevon edges |
| **channel combination had no derivation** | `sum(w·√\|g''\|)` — a weighted average of per-channel densities, with no error argument behind it | `√(Σ w·\|g''\|)` and `max(w·\|g''\|)`, both derivable from an error norm |
| **gradation control was crude** | a uniform-density `floor` mixed in | an explicit **max-gap ratio** limit |

The pin fix matters most. The monitor is `|g''|^(1/2)`, which is built for *smooth*
functions; at a genuine kink it cannot resolve the feature however much density it
piles up nearby. I had identified this limitation and left it unimplemented. Pinning
is the correct answer and it is now in AERIS.

The study is also right on a **physics point** the previous metric got wrong: AVL's
vortex-lattice core is a **mean-surface** method. It sees the camber line, not the
thickness. Thickness reaches the answer only through the CLAF lift-slope multiplier
and the CDCL profile-drag polar — both per-section *scalars*, which do not need the
section *grid* refined to be resolved. Weighting thickness equally with camber spent
budget on a channel the VLM cannot use.

## 3. Why the selection is invalid

The ranking is by `worst_control_error` against a 49-section reference. Seven of the
nine policies scored a max of **exactly 4.35 %**, to three significant figures.

That is impossible if section placement drove it. On the case that produced it
(`random_1020`) those policies built visibly different meshes:

| policy | ramp fraction | max gap ratio | sections in band | worst control err |
|---|---|---|---|---|
| uniform_pinned25 | 0.514 | 1.39 | 7 | 4.35 % |
| current_sum_sqrt_w3 | 0.179 | 1.82 | 8 | 4.35 % |
| proposed_sqrt_sum_w3 | 0.088 | 1.82 | 7 | 4.35 % |
| proposed_max_channel_w3 | 0.213 | 1.85 | 9 | 4.35 % |
| proposed_sqrt_sum_w3_no_thickness | 0.200 | 2.21 | 9 | 4.35 % |

A 6× spread in ramp fraction producing bit-identical error is a saturated metric,
not a physical result.

**The cause.** The driver is `Cn_da` — yaw moment per differential-elevon degree —
whose reference value on that case is **−2.3e−05**. AVL prints six decimals, so one
unit in the last printed digit is 1e−6:

```
1e-6 / 2.3e-5 = 4.35 %
```

Every policy differing from the reference by **one count in AVL's last printed
digit** scored 4.348 %. The selected policy `sqrt_sum_w3_gap15` happened to print
the identical value and scored 0.000 %, which is what won it the ranking.

`Cn_da`'s reference is below 1e−4 in **7 of the 10 geometries**. It should never have
been in a ranking statistic. This is exactly the trap DECISION-0007 documents for
the solver comparison — relative error is meaningless on a derivative that is
itself ≈0 — and it was not carried across to this study.

## 4. Re-ranked with the print-noise quantity removed

Excluding any quantity whose reference magnitude is below 1e−4 (100× AVL's print
resolution, so print noise contributes <1 % to the relative error). `Cn_da` is the
only exclusion.

| policy | mean control err | **max control err** | was ranked |
|---|---|---|---|
| **`max_channel_w3_no_thickness`** | **0.56 %** | **1.23 %** | 5th |
| `sqrt_sum_w1` | 0.59 % | 1.52 % | 2nd |
| `sqrt_sum_w3` | 0.72 % | 1.81 % | 7th |
| `current_sum_sqrt_w3` (previous AERIS) | 0.80 % | 1.81 % | 8th |
| `sqrt_sum_w3_no_thickness` | 0.60 % | 2.39 % | 4th |
| `max_channel_w3` | 0.68 % | 2.49 % | 6th |
| **`sqrt_sum_w3_gap15`** (selected by the study) | 0.66 % | **2.80 %** | **1st** |
| `uniform_pinned25` | 1.08 % | 3.65 % | 9th |
| `sqrt_sum_w0` | 1.50 % | 4.14 % | 3rd |

`max_channel_w3_no_thickness` is best on **both** statistics. The study's selection
is 7th of 9 on the corrected max.

Per-case, worst control error with the noise quantity removed:

| case | uniform | previous AERIS | study's pick | **winner** |
|---|---|---|---|---|
| benign | 0.47 % | 0.58 % | 0.32 % | 0.61 % |
| elevon_narrow | 2.08 % | 1.81 % | 2.80 % | **0.67 %** |
| elevon_wide | 0.49 % | 0.21 % | 0.11 % | 0.25 % |
| max_ar | 0.28 % | 1.37 % | 0.37 % | 0.61 % |
| max_gradient | 0.30 % | 0.63 % | 1.19 % | 1.23 % |
| nominal | 0.30 % | 1.40 % | 0.36 % | 0.64 % |
| random_1001 | 1.77 % | 0.73 % | 0.60 % | 0.80 % |
| random_1002 | 0.92 % | 1.12 % | 0.92 % | **0.51 %** |
| random_1010 | 2.16 % | 0.61 % | 1.57 % | 0.89 % |
| random_1020 | 3.65 % | 1.81 % | 0.16 % | 1.13 % |
| **mean** | 1.24 % | 1.03 % | 0.84 % | **0.74 %** |
| **max** | 3.65 % | 1.81 % | 2.80 % | **1.23 %** |

## 5. What may and may not be claimed

**May be claimed.** Every adaptive policy beats uniform on the worst case
(1.23–2.80 % vs 3.65 %). `max_channel_w3_no_thickness` has the tightest worst case
and the lowest mean. It is also the best-justified physically: worst-channel
combination resolves whichever function bends most sharply at a station rather than
letting a well-behaved channel dilute a badly-behaved one, and dropping thickness
matches what a mean-surface method can actually use.

**May not be claimed.** The winner beats uniform on only **6 of 10** cases,
the study's pick on 3 of 10, and the previous AERIS metric on 5 of 10. No policy
dominates case by case. At n = 10 the mean differences (0.74 / 0.84 / 1.03 %) are
not separable, and a max statistic over ten samples is unstable — one new geometry
could reorder the top three. **The defensible claim is about the tail, not the
typical case.**

## 6. Other limits of the study, recorded

- **The 49-section reference is a discretisation reference, not truth.** The study
  says so explicitly, which is correct.
- **The reference is uniform-pinned**, so it shares a distribution family with the
  `uniform_pinned25` candidate. Here that bias works *against* the adaptive
  policies, so it strengthens rather than weakens their win.
- **One operating point** (α = 6°, β = 0°, δe = δa = 4°).
- **`Cl_da`, `CY_da` and `Cn_da` are all differential-elevon derivatives** and all
  small; only `Cn_da` fell below the noise floor, but the other two are within an
  order of magnitude of it and should be watched.
- **The gap-repair result is not reproduced.** `gap15` was best on the case that
  turned out to be noise-dominated and mediocre elsewhere; its 2.80 % on
  `elevon_narrow` is the worst of the proposed family on the case adaptive
  placement exists to fix. Max-gap control may still be worth having, but this
  study does not establish it.

## 7. What AERIS now does

Adopted (see DECISION-0012): hard feature pins on both the uniform and adaptive
paths; worst-channel combination; thickness channel off. Rejected: the study's
selected policy, and the gap-repair as configured.
