# DECISION-0006 — The low-fidelity viscous + thickness model

Status: ACCEPTED
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/avl_section_corrections.md`,
`configs/aero/native_avl_verification_evidence/viscous_claf_verification.*`

Records what the AERIS low-fidelity aerodynamic model *is*, now that it has been
verified rather than assumed (Task 2).

## The model

AVL is inviscid vortex-lattice. AERIS adds exactly the two per-section
corrections AVL supports, and nothing else:

```
CL, Cm, stability derivatives  <- AVL VLM, with CLAF section lift-slope correction
CD  = cd_induced_AVL  +  cd_profile_NeuralFoil
```

| correction | AVL hook | source | resolution |
|---|---|---|---|
| viscous profile drag | `CDCL` (3-point cl/cd polar per SECTION) | NeuralFoil evaluated on **that section's own CST coordinates** at **that section's local Reynolds number** (V·c/ν) | one polar per extraction section |
| thickness lift slope | `CLAF = 1 + 0.77·(t/c)` per SECTION | t/c measured off the same realized section coordinates | one value per extraction section |

Both are computed from the **realized pyGeo loft**, not from the four authored
station airfoils — so the blend regions between mh91 / e374 / nlf1015 carry their
own intermediate polars and thicknesses.

## Reported drag: strip integration is primary, AVL's CDtot is the audit

`cd_total = cd_ind_AVL + cd_profile_NeuralFoil`, where `cd_profile` is obtained by
re-querying the **full** NeuralFoil polar per AVL strip and integrating over AVL's
own strip areas. AVL's internally computed `CDvis` (from the lossy 3-point CDCL
fit) is retained only as a cross-check.

**Why this way round:** the two routes differ by 4.28 %, which is the error of
the 3-point fit, not of the physics. Using the strip integration as primary keeps
that fitting error out of the reported drag. The QC gate
(`summarize_pygeo_avl_qc`) flags a run when the two disagree by more than 10 %.

## Verification standard adopted

A correction counts as verified only when all three hold, each independently:

1. **PRESENT** — written for every section;
2. **CORRECT** — reproduced by a recomputation using a *different algorithm* or a
   *freshly constructed* source, not the solver's own code path;
3. **ACTIVE** — an ablation on a byte-identical `.avl` moves AVL's answer in the
   predicted direction **and** by the predicted magnitude.

Requirement (3)'s magnitude clause is deliberate. For CLAF the wing-level CLα
ratio must land strictly between 1.0 and the mean CLAF, because CLAF is a section
property diluted by 3-D downwash; measured 1.05762 against a lifting-line
prediction of 1.06406 (AR 4.133, e 0.925) — 0.6 % apart. A weaker "the number
changed" test would pass even if CLAF were applied as a wing-level scalar.

Measured against this standard both corrections pass: CDCL 25/25 sections,
independent refit agreeing to 4.3e-7, `CDvis` 0 → 0.00663 on toggle; CLAF 25/25
sections, independent recompute agreeing to 1.5e-6, CLα 3.484 → 3.685 on
ablation. Section resolution: 25 distinct CDCL polars and 16 distinct CLAF values
from only 4 authored station airfoils, with the tip 3.8× draggier than the root
from the Reynolds effect alone.

## Guards

`tests/aero/test_avl_section_corrections.py` (7 tests) holds all of the above,
including an explicit guard against the historical failure mode where the OPER
`v` keystroke switched viscous forces off, leaving the injected CDCL inert. That
regression was invisible in the `.avl` text — hence the ablation requirement.

## Accepted limits

- NeuralFoil is the 2-D truth source and is itself an XFOIL surrogate; its own
  accuracy is out of scope. This decision covers only faithful transmission of
  NeuralFoil's answer into AVL.
- NeuralFoil's coordinate core is incompressible — `mach` is a documented no-op.
  Immaterial at M ≈ 0.08; not valid transonically.
- CLAF is thin-airfoil theory's thickness correction (AVL's own documented rule),
  with all of that theory's limits.
- Stall, separation and post-stall behaviour are outside the model. Strips whose
  local cl falls outside the 2-D polar range are counted and warned about
  (`n_extrapolated_strips`), and the QC gate defaults to zero tolerance for them.
