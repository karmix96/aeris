# Audit prompt — "how reliable and validated is S8?"

Paste everything between the lines into a fresh chat.

---

You are auditing a CFD study called **S8** for reliability and validation
status. I wrote it (with an AI assistant). I want an adversarial, independent
assessment — not a summary, and not encouragement. Assume the study overstates
its own confidence until you prove otherwise from the artifacts.

## Where everything is

Repository: `~/aeris`, branch `main`. Everything S8 is under one folder:

    AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/

    docs/       the written record. S8_REPORT_2026-09-15.md is the main
                narrative (long, with dated addenda); SU2_REPORT_2026-09-18.md
                covers the second solver; AUDIT_2026-09-05.md and
                AUDIT_2026-09-10.md are earlier self-audits.
    reports/    ~35 machine-written JSON files. These are the evidence.
    data/       run outputs.
    external/   third-party reference data: tmr_flatplate/, tmr_naca0012/,
                naca4412/, onera_m6/, e387/ (McGhee TM-4062 scans + digitised).
    runs/       per-run evidence records.
    *.py        the tooling at folder top level (gci.py, gci_four_level.py,
                audit_runs.py, convergence_gate.py, su2_validation.py, ...).

**Read the JSON in `reports/` and the raw run data before you read the prose in
`docs/`.** The prose is the thing under audit. Where prose and JSON disagree,
the JSON wins and the disagreement is a finding. Where the JSON and the raw
solver output disagree, the raw output wins.

## What S8 is

A structured O-H mesh study of a low-speed blended-wing-body (BWB) wing, run in
**ADflow 2.13.1**, RANS with the Spalart–Allmaras model, ANK-only (no Newton–
Krylov), converged to a 1e-6 relative L2 residual. 52 runs over a geometry
family (~83 wings x 4 angles of attack: -2, 0, 4, 8 deg). A second solver,
**SU2 8.5.0**, was added later for cross-checking and for transition modelling
(SA / SST, Langtry-Menter, Bas-Cakmakcioglu).

The engineering question the study is supposed to answer is a **difference
between wings** of order **5-9 drag counts** (1 count = 1e-4 in C_D), against a
total C_D of roughly 179 counts. At one point the study adopted a **1-count
materiality gate**. Test whether that gate is defensible.

## The validation evidence base — check each of these

These are the studies that were actually run to show the results are validated.
For each one: find the artifact, extract the numbers yourself, and judge
(a) whether it was done correctly, (b) whether it actually supports the claim
made from it, and (c) whether it covers S8's actual operating regime.

**External code-validation cases (solver vs published reference data)**

1. **NASA TMR flat plate**, three grid levels — skin friction and total drag vs
   the TMR reference. `reports/` + `external/tmr_flatplate/`.
2. **NACA 0012**, NASA TMR case at Ma 0.15, Re 6e6, alpha 10 deg, three grid
   levels, compared to CFL3D/FUN3D SA (no point-vortex correction).
   `reports/s8_naca0012_tmr.json`, `external/tmr_naca0012/`.
   Look specifically at how the **pressure/viscous drag split** compares, not
   just total C_D — a total that matches while the split does not is a warning.
3. **NACA 4412** vs experiment. `reports/s8_naca4412_tmr.json`.
4. **ONERA M6** at Ma 0.8395, alpha 3.06 deg, Re 11.72e6, vs AGARD AR-138
   (Schmitt & Charpin) — run **twice**: once on NASA's own grid, once through
   our mesh generator, so the mesher itself is under test.
   `reports/s8_onera_m6_comparison*.json`, `s8_onera_m6_our_mesh.json`.
   The study states the our-mesh run **misses its own acceptance criteria** on
   suction-peak and shock-location. Verify, and say what that implies about the
   mesher.
5. **Eppler 387** at Re 200,000, vs McGhee NASA TM-4062. This is the only
   validation case anywhere near AERIS's actual Reynolds number and the only one
   with a laminar separation bubble. `external/e387/`,
   `reports/s8_su2_validation.json`, `docs/SU2_REPORT_2026-09-18.md`.
   The study's verdict on this case was **revised** once already. Check whether
   the current verdict is supported by a *converged* solution or not.
6. **Transitional flat plate** (`fp_bc`) — transition onset vs turbulence
   intensity.
7. **ERCOFTAC T3A / T3A-** — attempted, **not completed**: the reference data
   server is offline. One of these produced a skin-friction coefficient that
   sits flat at 2.0e-3 across a decade of Re_x, which is physically impossible
   and is still unexplained. Say whether that anomaly casts doubt on anything
   else.

**Grid work — read this part carefully**

8. There is a **grid-independence study, NOT a GCI.** Two levels were solved:
   `gci_C` (603,592 cells) and `gci_M` (1,172,856 cells), across the geometry
   family and all four angles. The finer levels `gci_F` (2.32M) and `gci_FF`
   (4.68M) have **not** been solved — `gci_F` does not fit in this machine's
   memory.

   Consequences the audit must treat as first-class:
   - With two levels there is **no observed order of convergence p**, no
     Richardson extrapolation, and no discretisation-uncertainty band derived
     from the data. `p` can only be *assumed*.
   - The tooling (`gci_four_level.py`) is written and unit-verified (it recovers
     p = 2.0000 from a constructed case) and correctly refuses to produce a GCI
     from two levels — it reports `TREND_ONLY`. `reports/s8_gci_a*.json`
     carry the label `"study": "TREND_NOT_GCI"`. Confirm that no downstream
     document quietly treats the trend as if it were a GCI.
   - Refinement ratio: the study claims **r = 1.300 measured on the node arrays**,
     while the cube root of the cell-count ratio is ~1.25. Check which is the
     right quantity and whether the ASME r >= 1.3 requirement is really met.
   - The two-grid fallback (safety factor Fs = 3) reportedly gives an
     uncertainty of about **98 counts on a C_D of 179**. Assuming p = 1 rather
     than p = 2 reportedly moves the extrapolated answer by **82 counts**.
     Verify both, then state plainly what that means for a 5-9 count effect.

9. **Directional refinement studies** — chordwise, spanwise, edge, and
   wall-normal refined separately (`reports/s8_directional_refinement.json`,
   `s8_chord_gci_a0.json`, `s8_chord_gci_a4.json`, `s8_edge_refinement_test.json`,
   `s8_refinement_analysis.json`). One of these (wall-normal) reportedly
   **diverges** rather than converging: 208.2 -> 209.1 -> 213.3 counts. Confirm,
   and say what a diverging direction does to the whole grid-independence claim.

10. **Iterative convergence** — L2 1e-6 target, `reports/s8_l2_sensitivity.json`,
    `s8_l2_revalidation.json`, `s8_gci_gate.json`, `s8_gci_M_gate.json`.
    Is the iterative error actually small compared to the effect being measured?

**Internal consistency and cross-checks**

11. **Mass-balance** check, **cp-bound** check, **reference-area** audit
    (`s8_reference_area_audit.json`), **geometry** audit
    (`s8_geometry_audit.json`), **archive** audit (`s8_archive_audit*.json`).
12. **AVL (vortex-lattice) cross-comparison.** The study once claimed CFD and
    AVL agreed to "+-2%". That claim was **refuted** — the measured medians were
    roughly 16%, 21%, 6% and 0.7% at alpha -2, 0, 4, 8. Verify, and check
    whether any conclusion still rests on the withdrawn claim.
13. **Transition sensitivity via NeuralFoil** — drag ratio median ~1.57, range
    0.46-1.97. Values **below 1** mean a fully-turbulent assumption is *not* a
    guaranteed upper bound on drag. Check that reasoning.
14. **SU2 cross-solver campaign** — 10 cases, `docs/SU2_REPORT_2026-09-18.md`,
    `reports/s8_su2_*.json`. Note: there is **no converged SU2 solution on an
    actual AERIS wing** yet. Confirm.

**Reliability of the measuring instruments themselves**

15. The project keeps a numbered defect ledger — **31 defects** so far, several
    of them found by feeding synthetic inputs to the real checker functions.
    `tests/` holds ~25 regression assertions (`test_checkers_reject.py`).
    Read the ledger in the report. Several defects are cases where a checker
    **passed something it should have rejected** (a divergent grid family; a
    runaway force; missing/NaN fields; a 500-iteration acceptance window against
    a ~10,000-iteration oscillation, which let a case wander ~85 counts while
    looking flat to 0.10 counts).
    The question for you: **how much of the study's output was produced before
    the corresponding defect was fixed, and was it re-run afterwards?** A fixed
    checker does not retroactively fix conclusions drawn under the broken one.

## What I already know is missing — verify, don't just repeat

- No third grid level, so no GCI, no observed order.
- ANK-only has never been demonstrated on a mesh above ~1.17M cells.
- No low-speed 3D BWB experimental dataset exists to validate against, anywhere.
- Neither solver has a *validated* transition model in this regime.
- `gci_M` is itself not demonstrably grid-converged.
- Mission mass, cruise speed and trim state are unspecified, so every run is
  fixed-alpha rather than fixed-lift.

## Deliver

1. **A verdict in one paragraph**: for what class of question are S8's numbers
   trustworthy *today*, and for what class are they not? Be specific about the
   magnitude of effect that is and is not resolvable.
2. **A table of every validation study**: what it tested, what the artifact
   actually shows, whether it passes, and whether it is *relevant* to AERIS's
   regime (low speed, low Reynolds, 3D BWB). Relevance failures matter as much
   as accuracy failures.
3. **The total uncertainty budget**, assembled from the artifacts — grid,
   iterative, model-form, geometry/reference-quantity — compared against the
   5-9 count effect being measured. State whether the study can support its own
   claims.
4. **Every place the prose over-claims relative to the JSON.** Quote both.
5. **The shortest path to a defensible result**, ranked by cost: what is the
   minimum additional computation that would make the central claim stand up,
   and is a third grid level the first thing on that list or not?
6. **Anything I have not thought to ask about.**

Cite file paths and numbers for every finding. If a claim cannot be checked from
the artifacts, say "unverifiable" rather than accepting it. If you conclude the
study cannot currently support its central claim, say so directly.

---
