# AERIS studies

Each file is one study: question, method, assumptions, results, conclusions, and
what it does **not** establish. Decisions extracted from them live in `decision/`
as numbered ADRs. Evidence is rescued out of `data/` (gitignored, wiped) into
`configs/*/`*`_evidence/`.

**Visual report:** [`figures/lowfi_avl_verification_report.html`](figures/lowfi_avl_verification_report.html)
— 11 charts across the whole low-fidelity campaign. Open it in a browser;
self-contained, light/dark aware, every chart has a table view.
Regenerate with `python studies/figures/make_figures.py` (reads only tracked
evidence, so it survives a `data/` wipe).

---

## THE PANELLING TO USE FROM NOW ON

Settled by `decision/0009` / `0010` / `0011`. **Versioned in the config** at
`geometry.aero_discretisation` in `configs/geometry/bwb.yaml`, so a saved design
states the grid it was evaluated on. Overridable per run on the CLI
(`--nchordwise`, `--spanwise-panels`, `--span-margin`, `--cspace`,
`--section-placement`) and in the GUI's pyGeo-native tab, which also warns before
you exceed AVL's array limits. Resolution order: **CLI flag → config block → code
default.**

| parameter | value | | why |
|---|---|---|---|
| `n_sections` | **25** | | ≤0.56 % worst-seed on all forces + stability derivatives |
| `span_margin` | **0.0** | | full span — any inset opens a centreline gap under `YDUPLICATE` |
| section placement | snap to elevon band edges | | keeps control extent = geometric extent |
| `spanwise_panels_per_section` | **4** | | 96/side; ≤0.54 % worst-seed |
| `nchordwise` | **24** | *(was 8)* | CL_δe 7.7 % → ~1.1 % |
| `cspace` | **1.0** (cosine) | | uniform halves the elevon error but costs 14× on Xnp |
| adaptive placement | **on for DoE work** | | worst case 1.23 % → 0.84 % across the design set |

Cost: **192 strips, 4608 vortices** — inside both AVL array limits.

**Economy setting** for work where the elevon derivative is *not* the object of
study: `nchordwise = 16` → CL_δe ~2.6 %, everything else ≤0.4 %, 3072 vortices.

**Hard ceilings — exceed either and AVL fails outright:**

```
(n_sections − 1) × spanwise_panels_per_section ≤ 250      # NSMAX = 500 strips, both halves
n_strips × nchordwise                          ≲ 6000      # NVMAX vortices
```

`49/4/16` (6144 vortices) and `65/4/anything` (512 strips) both fail. So sections
and chordwise resolution cannot be refined together without limit — which is why
adaptive section placement is worth pursuing rather than simply buying more
sections.

### What the change to `nchordwise = 24` buys

Total discretisation error against the best reference that fits AVL's limits
(33 sections / 4 spanwise / 20 chordwise, 3 seeds):

| grid | CL | CDind | Cm | **CL_δe** |
|---|---|---|---|---|
| 25/4/8 — old | 1.07 % | 3.20 % | 1.70 % | **7.06 %** |
| 25/4/16 | 0.081 % | 0.34 % | 0.28 % | 1.94 % |
| **25/4/24 — new** | 0.15 % | 0.51 % | 0.11 % | **0.38 %** |

The elevon error at `nchordwise = 8` was the largest single discretisation error
anywhere in the low-fidelity chain — comparable to the AeroSandbox elevon defect
that DECISION-0007 judged disqualifying. Cause: the hinge at x/c = 0.75 sat
0.059 c from the nearest cosine panel edge, so AVL smeared the control gain across
a panel.

### Two things to remember when using these numbers

- **Geometric metrics converge ~3× earlier than the aerodynamics** (Sref within
  0.05 % by n = 9, while the aero still carries 1.9 % at n = 13). **Never** use
  area/MAC convergence as a proxy for aerodynamic convergence.
- **CL_δe is non-monotonic in `n_sections`** — n = 13 beats n = 17 *and* n = 25,
  reproducibly. It has a ±1.5 % oscillatory floor set by where sections fall
  relative to the elevon band edges, which uniform refinement cannot remove.

---

## Low-fidelity AVL campaign (2026-07-25)

Read in this order; each depends on the one before.

| # | study | establishes | decision |
|---|---|---|---|
| 1 | [`native_avl_output_and_fidelity.md`](native_avl_output_and_fidelity.md) | Complete AVL output capture; two geometry defects found and fixed (full-span extraction, exact elevon extent) | [0005](../decision/0005-native-avl-output-and-geometry-fidelity.md) |
| 2 | [`avl_section_corrections.md`](avl_section_corrections.md) | CDCL (viscous) and CLAF (thickness) are PRESENT, CORRECT and ACTIVE by ablation, and section-resolved from the loft | [0006](../decision/0006-lowfi-viscous-and-thickness-model.md) |
| 3 | [`pygeo_native_vs_asb_avl_doe.md`](pygeo_native_vs_asb_avl_doe.md) | Native ≡ AeroSandbox design-space-wide (30 samples); the entire residual is the elevon | [0007](../decision/0007-native-avl-is-the-production-lowfi-solver.md) |
| 4 | [`native_avl_physics_validation.md`](native_avl_physics_validation.md) | Independent closed-form validation, 11/11 — the leg code-to-code comparison cannot provide | [0008](../decision/0008-native-avl-verification-standard.md) |
| 5 | [`section_and_panel_convergence.md`](section_and_panel_convergence.md) | Geometry-section and AVL-panel convergence, **separated** | [0009](../decision/0009-lowfi-discretisation.md) |
| 6 | [`hinge_panel_alignment.md`](hinge_panel_alignment.md) | Chordwise spacing vs the hinge; why uniform spacing is rejected. **Its "coincidence" explanation is superseded — see 0010** | 0009 |
| 7 | [`discretisation_master_study.md`](discretisation_master_study.md) | **THE SYNTHESIS** — sections, panels, robustness across the design space, adaptive placement. Read this one first | [0010](../decision/0010-control-resolution-criterion.md) |
| 8 | [`adaptive_section_placement.md`](adaptive_section_placement.md) | Information-metric placement. **Contains a corrected error** — the metric's first version erased channel magnitudes; fixed, and the verdict reversed | [0011](../decision/0011-adaptive-section-placement.md) |

### The three results most likely to be challenged

1. **Every low-fidelity number before 2026-07-25 is invalid.** The section
   extractor inset 2 % at both span ends, so `YDUPLICATE` mirrored the innermost
   section into a **32.6 mm centreline gap** and AVL shed a spurious inboard
   tip-vortex pair. CL was understated by 54.9 %, CLα by 26.2 %, L/D halved.

2. **The native/AeroSandbox residual is one defect, not a fog of small ones.**
   At δe = 0 the two solvers agree on CL to 3e-5. The gap is linear in δe with
   ~zero intercept (94–101 % attributable), and its slope matches the
   independently measured +5.89 % CL_δe bias to 9 %. Two earlier explanations —
   airfoil coordinate resolution and Mach handling — were tested and **refuted**;
   the speed-derivative "open item" turned out to be pure conditioning
   (corr(1/|Cmu|, rel. error) = 0.971).

3. **The AeroSandbox path cannot deflect an elevon differentially at all.** Its
   AVL exporter collapses every control surface into one `all_deflections`
   variable, so AVL reports `1 Control variables` and δa is silently ignored.
   Since the DoE varies three elevon DVs specifically to optimise control
   authority, this is disqualifying — it is why the native path is production.

### Open across the campaign

- **No validation against experiment or CFD.** All of the above is *verification*
  — is the code solving the intended equations correctly. Physical accuracy has to
  come from the high-fidelity ADflow path.
- **Surface split at the hinge line** — the principled fix for the elevon
  resolution rather than paying for chordwise panels. Not attempted.
- **The panelling is validated at hinge = 0.75 ONLY.** A defect found 2026-07-25
  meant the three elevon DVs never reached AVL — every run in every study used
  elevon 0.60–0.95 at hinge 0.75. Since the chordwise recommendation is driven by
  a hinge/panel-edge coincidence, `nchordwise = 24` is unvalidated at other hinge
  positions (the DV range is 0.652–0.814). Fixed; Task 5 closes it.
- **One operating point** (α = 6°). Near-CL_max behaviour, where the polar bridge
  clamps strips outside the 2-D polar range, is uncharacterised.
- **Cref definition mismatch** of 0.13 % between the paths (∫c²dy/S vs
  `mean_aerodynamic_chord()`); moves Cmu and Cmα by 0.129 %.
- **Budget selection** — the information metric places a fixed section budget but
  does not yet choose one.
- **Whether chordwise is a better buy than spanwise at fixed cost** — the equal-cost
  grid trade was confounded and no dominating reference fits in AVL's arrays.

---

## Earlier studies

| study | establishes | decision |
|---|---|---|
| [`pygeo_vs_aerosandbox_geometry.md`](pygeo_vs_aerosandbox_geometry.md) | pyGeo and AeroSandbox geometry backends agree to <1.3 % over 50 samples | [0003](../decision/0003-pygeo-vs-asb-geometry-and-metrics.md) |
| [`trailing_edge_thickness.md`](trailing_edge_thickness.md) | Blunt-TE thickness = fixed 0.5 mm; wing-level ΔCD ≈ −0.5 counts | [0004](../decision/0004-te-thickness.md) |
