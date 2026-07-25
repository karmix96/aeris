# DECISION-0009 — Low-fidelity discretisation: sections, panels, and chordwise spacing

Status: ACCEPTED
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/section_and_panel_convergence.md`,
`studies/hinge_panel_alignment.md`,
`configs/aero/lowfi_discretisation_evidence/`

## 1. The production discretisation

| parameter | value | was | worst-seed error it buys |
|---|---|---|---|
| `n_sections` (geometry) | **25** | 25 | ≤0.56 % on all forces + stability derivatives |
| `spanwise_panels_per_section` | **4** | 4 | ≤0.54 % |
| `nchordwise` | **24** | **8** | CL_δe ~1.1 % (was 7.7 %) |
| chordwise spacing (`cspace`) | **1.0 = cosine** | 1.0 | — |

For force/stability work where the elevon derivative is not the object of study,
`nchordwise = 16` is an accepted economy setting (CL_δe ~2.6 %, everything else
≤0.4 %).

**Total discretisation error, measured jointly** against the best reference that
fits AVL's array limits (33 sections / 4 spanwise / 20 chordwise, 3 seeds):

| grid | vortices | CL | CDind | Cm | Xnp | **CL_δe** |
|---|---|---|---|---|---|---|
| 25/4/8 (old production) | 1536 | 1.07 % | 3.20 % | 1.70 % | 5.3e-4 | **7.06 %** |
| 25/4/16 | 3072 | 0.081 % | 0.34 % | 0.28 % | 3.6e-4 | 1.94 % |
| **25/4/24 (new production)** | 4608 | 0.15 % | 0.51 % | 0.11 % | 3.8e-4 | **0.38 %** |

(Quote CL_δe as ~1.1 % for 25/4/24 and ~2.6 % for 25/4/16 — those are the values
against the finer cosine-40 reference of the hinge study. The 0.38 %/1.94 % figures
above are against a chordwise-20 reference and are therefore optimistic.)

## 2. Why the two convergence questions had to be separated

In the native writer, `total spanwise panels = (n_sections − 1) × spanwise_panels`,
so the prior `scripts/section_study.py` design refined the *lattice* every time it
added a *section*. Its "section convergence" curve was a superposition of two
effects with different causes, costs and fixes.

Separated by construction: **geometry mode** varies `n_sections` with the total
spanwise panel count pinned at 96 per side (section counts chosen so (n−1) divides
96 exactly, giving identical 192-strip lattices at every level); **panel mode**
pins `n_sections = 25` and sweeps each panel direction one at a time.

The separation immediately paid off: it showed the dominant error was **not** the
section count at all, but the chordwise grid — which the conflated design could
not isolate and which had been mis-set at 8 since the beginning.

**Self-confound checked.** Geometry mode was first run at the (unconverged)
chordwise 8, then **re-run at chordwise 16**. Conclusions unchanged (n = 25
worst-seed: CL 0.148 % vs 0.144 %; CL_δe 1.37 % vs 1.46 %; same non-monotonic
pattern). The section-convergence result is not an artefact of the coarse
chordwise grid.

## 3. Findings that constrain how the results may be used

**Geometric metrics converge far earlier than aerodynamics.** Sref is within
0.05 % by n = 9 and Cref within 0.31 % by n = 13, while the aerodynamics still
carries 1.9 % at n = 13. **Area/MAC convergence must never be used as a proxy for
aerodynamic convergence** — a study checking only geometry would have declared
victory at n = 9, at ~5 % aerodynamic error.

**The elevon derivative does not converge monotonically in `n_sections`.** CL_δe
error against n = 49: 52.4 %, 24.1 %, 14.8 %, **0.33 %** (n = 13), 1.55 %, 1.46 %,
0.36 %. n = 13 beats n = 17 and n = 25, reproducibly, in both the 5-seed chord-8
and 3-seed chord-16 runs. Cause: sections are snapped onto the elevon band edges
(DECISION-0005), but AVL still ramps the control gain over the interval *just
outside* each edge, whose width depends on where the neighbouring section falls.
The result is an oscillatory **±1.5 % floor** on control authority that uniform
refinement cannot reliably remove. **This is the central motivation for adaptive
section placement.**

## 4. Chordwise spacing: uniform is better for the elevon and is still rejected

The elevon hinge at x/c = 0.75 sits **0.059 c from the nearest cosine-8 panel
edge**. Uniform-8 spacing puts an edge *exactly* on it and **halves the elevon
error at identical cost (3.82 % vs 7.71 %)** — hypothesis confirmed, and alignment
is measurable.

Alignment is nevertheless **not the whole mechanism**: `cosine-12` also lands an
edge exactly on the hinge yet still shows 3.83 %, worse than `uniform-12`'s
2.04 %. Uniform spacing helps for a second reason — it spreads panels over the
flap's chord instead of clustering at the edges.

**Uniform spacing is rejected anyway**, because the cost lands on the
pitch-stability quantities and does not go away with refinement:

| quantity | cosine-8 | uniform-8 | uniform-40 |
|---|---|---|---|
| Xnp | 3.6e-4 | 5.1e-3 (**14× worse**) | 1.1e-3 |
| Cmq | 3.2e-4 | 4.7e-3 (**15× worse**) | 1.4e-3 |

Leading-edge clustering is what resolves the suction peak that sets the pitching
moment. Trading a 14× degradation in neutral-point accuracy for a 2× gain in
elevon authority is the wrong trade for a stability-and-control study.

**Reference trustworthiness:** uniform-40 and cosine-40 agree to 0.52 % on CL_δe
and 0.007 % on CL — two different spacing laws converging to the same physics.

## 5. Hard AVL array limits — a quantified ceiling on uniform refinement

| limit | constraint | first fails at |
|---|---|---|
| NSMAX = 500 strips (both halves) | (n_sections − 1) × spanwise_panels ≤ 250 | n = 65, 4 panels/interval → 512 |
| NVMAX ≈ 6000 vortices | strips × nchordwise ≤ ~6000 | n = 49, 4 spanwise, 16 chordwise → 6144 |

| configuration | strips | vortices | |
|---|---|---|---|
| 25/4/24 (production) | 192 | 4608 | ok |
| 33/4/16 | 256 | 4096 | ok |
| 33/4/20 (study reference) | 256 | 5120 | ok |
| 49/4/16 | 384 | 6144 | **fails** |

Refining sections and chordwise resolution simultaneously is therefore **not
free**, and `n_sections = 33` with `nchordwise = 24` (256 × 24 = 6144) already
fails. This is a real, quantified ceiling — and the reason adaptive section
placement matters: it raises geometric fidelity **without** spending strips.

## 6. Open

- **Surface split at the hinge line** — the standard AVL technique for an exactly
  resolved flap, and the principled fix for §4 rather than paying for resolution.
  Not attempted.
- **Hinge position varies across the DoE** (`elevon_hinge_frac` 0.652–0.814),
  so the hinge-to-edge distance and hence the elevon error vary design-space-wide.
  This study fixes it at the nominal 0.75; the error at other hinge positions is
  unmapped and could be worse.
- **One operating point** (α = 6°, δe = 4°, β = 0°). Convergence near CL_max,
  where the polar bridge clamps strips, is uncharacterised.
- **No Richardson extrapolation.** Errors are convergence increments against the
  finest affordable level, not against an extrapolated limit.
- Only cosine and uniform spacing tested; AVL also offers sine and −1.
