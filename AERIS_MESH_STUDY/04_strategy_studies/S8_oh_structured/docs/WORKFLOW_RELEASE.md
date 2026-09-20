# The S8 production workflow: what it delivers, what it costs, what it may claim

Written 2026-09-21. **Draft — two tolerances are deliberately left blank** because they cannot be
filled until a third grid level exists. Everything else is settled and measured.

This is the document a user of S8 should read before asking it a question. It exists because the
study's value is a repeatable workflow with known limits, not a single drag number.

---

## 1. What S8 answers, and to what accuracy

| question | answer quality | evidence |
|---|---|---|
| **Which of these wings has less drag?** | reliable when the gap exceeds **10 counts** | ordering preserved across both grid levels: g47 < g13 < g83 at α 0 |
| **What is C_L at this incidence?** | grid-converged; ΔC_L ≤ 0.0015 coarse→medium | `s8_refinement_analysis.json` |
| **What is C_m / the neutral point?** | grid-converged; ΔC_m ≤ 0.0006. Area-independent | neutral point moved 5.6e-17 m under the area fix |
| **Is this mesh valid?** | yes, and automatically | 100/100 coarse and 61/61 `gci_F` meshes built with zero negative cells |
| **Has this run converged?** | yes, and it is recorded | 52/52 production runs ACCEPTED; iterative error ≤0.04 counts |
| **What is the absolute C_D?** | **not answerable** | still moving 22–25 counts per refinement; also dissipation-dominated (57-count swing across a 4× vis4 range) |
| **Is this design change worth X counts, X < 10?** | **not answerable** | the credit's own grid sensitivity is 5.5–6.2 counts |
| **Does the low-speed 3-D pressure field match reality?** | **unvalidated** | no low-speed 3-D measurement has been run. See `VALIDATION_PLAN_low_speed_3D.md` |

**The one-line statement of scope:** S8 is a verified low-speed RANS automation that ranks designs
and predicts lift and moment. It is not yet a drag-prediction tool and it is not yet validated
against a low-speed 3-D experiment.

## 2. Declared tolerances

| quantity | tolerance | basis |
|---|---|---|
| Iterative (solver convergence) | **≤ 0.04 counts** | measured: forces move ≤0.023 % beyond L2 1e-6 over 3 geometries; all 52 runs settle C_D to ≤0.017 % |
| Reference-quantity / geometry | **≤ 0.3 counts** | own-area fix exact; worst twist error 0.246° on 1 of 10 designs |
| Unphysical surface pressure | **≤ 0.31 counts** | measured 2026-09-21: 4 over-bound cells carry 4.70 counts of which **0.31 is the unphysical excess** (`s8_cp_drag_map_gci_C_a0.json`) |
| Freestream turbulence (χ choice) | **1.3 counts** on a difference | fleet spread of the χ 1.3→3 change |
| Artificial dissipation, on a difference | **≤ 0.63 counts** | measured: credit moves 0.63 counts across a 4× vis4 range while absolute drag spans 57 |
| Artificial dissipation, on absolute drag | **−20.6 / +35.1 counts** | unresolved and probably unresolvable; do not quote absolute drag |
| **Discretisation, on a difference** | **≈ 6 counts today** | credit drift 5.5–6.2 counts coarse→medium on three wings |
| **Discretisation, at the finest level** | *pending third grid level* | ← blank until `gci_F` exists |
| **Model form, low-speed 3-D** | *pending validation* | ← blank until RIBES or equivalent is run |

**Interim decision threshold: 10 counts.** A safety factor of ~1.6 on the measured 6-count floor,
chosen as policy, not derived. The 1-count gate is withdrawn. Anything below 10 counts is recorded
and not acted on.

## 3. The cheapest grid that meets these tolerances

Today: **`gci_C` (≈604k cells)** for ranking, lift and moment; **`gci_M` (≈1.17M)** adds nothing to
lift or moment and does not settle drag either, so it is not worth 2× the cost for screening.

| level | cells | solve time, 6 ranks | memory | use |
|---|---|---|---|---|
| `gci_C` | 604k | ~19 min | 6.9 GiB | **screening, ranking, lift, moment** |
| `gci_M` | 1.17M | ~45–60 min | 11.4 GiB | grid-trend evidence only |
| `gci_F` | 2.32M | — | **~22 GiB — does not fit this host** | required to close the drag tolerance |
| `gci_FF` | 4.68M | — | **~38 GiB** | order-consistency check |

A 100-design screen at `gci_C` is ~8 days of solving on this host. Meshing is 0.2 % of that, so mesh
choice is not a throughput decision (PLAN §0.9).

## 4. What every released run must carry

Enforced by `dataset_row.py` and checked by `audit_runs.py`. A row missing any of these is not
training data; it is a run somebody still has to look at.

| field | why it is mandatory |
|---|---|
| **mesh family** | `gci_C`/`gci_M` name two different meshes (tip cap 10.2 vs 2.04 × s0) differing by 5.4–7.2 counts. A level name alone does not identify a mesh |
| solver version, options hash, `solver_overrides` | the production campaign runs χ 3 and ANK-only, both non-default |
| `gate_verdict`, `iterations`, `equation_orders`, force-tail spreads | a missing verdict is an unjudged run, not a passing one. This was lost for a day when a path moved |
| `relative_residual`, `l2_target` | the stopping rule actually reached |
| mesh + geometry + connectivity hashes | so a rebuilt mesh can be checked against the one that produced a number |
| surface-field sha256, read back from the stored archive | recording the *source* hash let 44 of 52 rows point at another wing's flow (defect 26) |
| `inverted_cells`, `wall_layer_error_m` | mesh validity at solve time |
| `yplus_min_p50_p95_p99_max` | the tip cap still exceeds y+ 1 (1.22–1.85); p99 ≤ 1.16 |
| `cp_cells_over_bound`, `cp_peak_excess` | now costed at 0.31 counts, but it must stay visible |
| `area_ref`, `moment_ref_xyz`, `mac_m` | defect 23 rescaled nine wings by −25…+31 % |
| **uncertainty flag** | which tolerances in §2 are measured and which are pending, so no consumer can read a number as better than it is |

## 5. How to use the output, stated as rules

1. **Never quote absolute C_D.** Quote differences, and only above the threshold in §2.
2. **Compare at matched C_L or trim, not at matched α.** At α 0 the ten pilot wings span C_L −0.160
   to −0.0087, which is **18.6 counts of induced drag** from the lift mismatch alone against a
   35-count C_D spread. Fixed-α comparisons mix profile and induced drag.
3. **Never combine runs across mesh families.** Check the tip cap in the mesh summary first.
4. **Do not treat a two-level trend as a GCI.** No observed order, no Richardson extrapolation, no
   band. The artifacts label this `TREND_NOT_GCI`; keep it that way.
5. **The fully-turbulent assumption is not a one-sided bound.** NeuralFoil section drag ratios span
   0.46–1.97; below 1 means free transition gives *more* drag, which happens at the low-Re tip.
6. **A checker that did not run has not passed.** An absent field is not a pass.

## 6. What closes the two blanks

| blank | what closes it | cost | blocked by |
|---|---|---|---|
| Discretisation at the finest level | `gci_F` on 3 wings, both configurations, + `gci_FF` at 2 α on one | ~255 core-hours, $15–40 | needs rented compute; **and** the wall-normal divergence must be understood first, since a global refinement refines that direction too |
| Model form, low-speed 3-D | RIBES T40 tripped, α 0/4, C_L + C_m + sectional C_p at 6 stations | days of setup, fits this host | obtaining the dataset (`ribes-project.eu` TLS certificate expired) |

Neither is optional for a drag claim. The first makes the number converged; the second makes it
converged to the right answer.

---

*Two tolerances in §2 are blank. That is the honest state of this workflow, and filling them in with
estimates is what produced the 1-count gate.*
