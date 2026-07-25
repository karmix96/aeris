# AERIS — Memories

Single consolidated project memory (Mike's convention: all memories live here).
Decisions live in `decision/` (ADR-style); study write-ups in `studies/`.

---

## User & working style

- **Mike** — founder + lead researcher of AERIS, a BWB-UAV aircraft-design codebase.
  Building toward a defensible PhD multifidelity workflow. Works collaboratively and
  fast; wants decisions made deliberately and documented, and honest/calibrated
  reporting (no overclaiming — say what's verified vs not).
- **Full authority:** act as lead research engineer without asking approval, EXCEPT
  (a) important physics/modelling decisions → surface and confirm; (b) never delete
  the codebase, important files, memory, or evidence; (c) never force-push / rewrite
  history. Emit a clear progress message per change.

## Working conventions (feedback)

- **Decisions → `decision/`** (ADR files, numbered, e.g. `0001-...md`).
- **Studies → `studies/`** (each study: short description, assumptions, results,
  conclusions).
- **Memories → `memories/memories.md`** (this single file).
- **Heavy compute → desktop:** don't launch long/heavy runs in-session (big DoEs,
  full CFD, CAD/Gmsh/pyHyp campaigns, 50-case visual batches). Prepare runnable
  runbook commands for Mike; a single case / modest sweep in-session is fine.
- **Findings live in `configs/`:** rescue REPORT/evidence out of `data/`+`artifacts/`
  (gitignored, regenerable) into tracked `configs/` before anything is wiped.
- **Save data in the project tree** (never /tmp or scratch for deliverables).
- **Nothing saved by default:** geometry/CAD/mesh/plot outputs off unless requested
  at run time (CLI flag / GUI toggle).
- **Mesh inspection:** Mike inspects meshes in ParaView, not custom plots.

## Key decisions (see decision/ for full ADRs)

- **Master geometry = the smooth MACH-Aero pyGeo B-spline loft.** Do NOT force it to
  interpolate the piecewise Aeris authored stations. The pyGeo loft's metrics are
  authoritative; sub-% smooth-vs-piecewise shifts live in the design space, not
  errors. (Validation gate = frame reconstruction + reference metrics + control
  invariance; all pass.)
- **ASB-free AVL target:** AERIS must not construct an `asb.Airplane` for the
  AVL+viscous path. aerosandbox may be IMPORTED (NeuralFoil hard-depends on it).
  Native AVL writer + coordinate-NeuralFoil satisfy this; the geometry path is truly
  aerosandbox-free (guard test).
- **One geometry config:** `configs/geometry/bwb.yaml` for BOTH backends. All other
  geometry configs deleted (suite RED by design until tests are rebuilt).
- **Fixed airfoils at b0/b1/b2/b3:** mh91 / mh91 / e374 / nlf1015 (Panagiotou &
  Yakinthos BWB UAV baseline). NOT AH 94-145. Swap the four `station_airfoils` names
  for any `data/airfoil_database` entry.
- **TE thickness (DECISION-0004):** airfoils are sharp; blunt TE =
  **FIXED constant 0.5 mm absolute along span** (1.0 mm if sturdier edge needed). Study (`studies/trailing_edge_thickness.md`, NeuralFoil
  sweep on our airfoils at Re tip 1.85e5 / MAC 7.7e5 / root 1.8e6): ΔCd ~linear in TE
  thickness (Hoerner); ≤0.5%c costs ≤~7 section drag counts, RAISES CL_max (van Dam),
  small Cm; >1%c material; blunting nlf1015 at low-Re tip REDUCES drag. **WING-LEVEL
  (the driver): ΔCD ≈ −0.5 drag counts (<0.5% of total), slightly favorable** —
  area-weighted integral (wing.py), largest %c TE at low-area tip. Applies to
  the MESH TE floor. OPEN: validate 0.25%c pyHyp marchability floor; 3-D ADflow base
  drag check. pyGeo master surface stays sharp; blunt TE is a downstream mesh/mfg
  transform.

- **Native AVL fidelity + capture (DECISION-0005, 2026-07-25):** three things.
  (1) The native runner now captures the COMPLETE AVL output family (e, Xnp, 25
  stability + 18 body derivatives, per-control authority derivs, hinge moments,
  surface forces, strips, shear/bending) into `native_avl_result.json`; parsers
  live in the shared asb-free `aero/solvers/avl_output.py` used by BOTH solvers.
  (2) **`span_margin` default 0.02 → 0.0 (FULL span).** The 2% inset left a
  32.6 mm centreline GAP under YDUPLICATE → spurious inboard tip vortices:
  CL was −54.9%, CLα −26.2% (2.741 vs 3.715 /rad), L/D halved. **All low-fi aero
  numbers from before 2026-07-25 are invalid.** (3) Elevon now spans exactly its
  geometric band (edge sections snapped + both boundaries tagged): CL_δe +16.7%.
  Verified vs ASB: NO field missing, clean symmetric case agrees ≤0.6% (CLα 8e-7,
  Xnp 1e-5). Study: `studies/native_avl_output_and_fidelity.md`.

- **Low-fi viscous+thickness model (DECISION-0006, 2026-07-25) — VERIFIED, not
  assumed.** `CD = cd_ind_AVL + cd_profile_NeuralFoil`; AVL's two per-section
  hooks are both used and both proven PRESENT/CORRECT/ACTIVE by ablation:
  **CDCL** (25/25 sections, per-section CST NeuralFoil at the section's own Re;
  independent refit agrees 4.3e-7; CDvis 0→0.00663 on toggle; tip 3.8× draggier
  than root from Re alone) and **CLAF** = 1+0.77·t/c (16 distinct values from 4
  authored airfoils; t/c 15.00%→10.93%→15.07% recovers mh91→e374→nlf1015;
  ablation CLα 3.484→3.685, ratio 1.0576 vs lifting-line 1.0641 — 0.6% apart,
  proving it acts as a SECTION property diluted by 3-D downwash).
  **Verification standard adopted: presence in the .avl is NOT evidence** — an
  ablation must move AVL's answer by the *predicted magnitude*. (The OPER `v`
  toggle once silently disabled viscous forces with CDCL still in the file.)
  Strip integration is PRIMARY, AVL CDtot is the audit — they differ 4.28%,
  which is the 3-point CDCL fit's own error. Study: `studies/avl_section_corrections.md`.

- **Low-fi DISCRETISATION (DECISION-0009, 2026-07-25).** The two convergence
  questions were CONFLATED before (adding a section also refined the lattice,
  since total spanwise panels = (n−1)×panels_per_interval). Separated: geometry
  mode varies n_sections with the panel count PINNED at 96/side; panel mode pins
  n_sections and sweeps each direction alone.
  **PRODUCTION = 25 sections / 4 spanwise / `nchordwise` 24 / cosine.**
  **`nchordwise` 8 → 24** — at 8 the elevon CL_δe carried **7.7 %** error, the
  biggest in the whole chain, because the hinge at x/c=0.75 sits 0.059c from the
  nearest cosine panel edge. Joint check 25/4/8 → 25/4/24: CL 1.07→0.15 %,
  CDind 3.20→0.51 %, CL_δe 7.06→0.38 %.
  Three gotchas worth remembering:
  (a) **geometric metrics converge ~3× earlier than aerodynamics** (Sref 0.05 % by
  n=9 vs aero 1.9 % at n=13) — NEVER use area/MAC convergence as a proxy;
  (b) **CL_δe is NON-MONOTONIC in n_sections** (n=13 beats 17 and 25,
  reproducibly): a ±1.5 % oscillatory floor from section alignment vs the elevon
  band edges, which uniform refinement cannot fix → motivates adaptive placement;
  (c) **uniform chordwise spacing halves the elevon error but wrecks Xnp/Cmq
  (14–15× worse, and it does NOT improve with refinement)** — rejected; LE
  clustering is what resolves the pitching moment.
  **Hard AVL limits: (n−1)×spanwise ≤ 250 strips; strips×nchordwise ≤ ~6000
  vortices.** 49/4/16 and 65/4/* both FAIL. Studies:
  `studies/section_and_panel_convergence.md`, `studies/hinge_panel_alignment.md`.

- **CONTROL RESOLUTION is the binding low-fi error (DECISION-0010, 2026-07-25).**
  Not wing resolution. AVL smears a control at its EDGES — chordwise at the hinge,
  spanwise at the band ends — and the error is set by how much of the control the
  smearing occupies. One criterion replaces two tuned numbers:
  **N_flap ≥ 6** (chordwise panels aft of the hinge; error ~ N_flap^-1.47, R²0.966)
  and **ramp fraction ≲ 15%** (gain-ramp width outside the band edges / band width;
  r = +0.978, re-confirmed +0.964 on an independent set). PREDICTIVE — estimable
  from geometry before running AVL. `ramp_fraction()` is in
  `aeris.geometry.geometric_information`.
  **I published a WRONG mechanism first** (hinge/panel-edge "coincidence") and a
  hinge sweep killed it: within-chordwise-level corr(edge distance, error) =
  +0.611/+0.077/-0.040/-0.163, inconsistent. At nchordwise=24 the hinge with EXACT
  edge alignment is not the most accurate. Lesson: pooled correlations across a
  refinement level are confounded by the level.
- **Robustness (Task 5):** 25/4/24 holds ≤0.5% on 9 CONSTRUCTED extremes —
  AR 2.25–7.85, max sweep/twist/dihedral, both hinge bounds. Geometry extremes are
  a NON-ISSUE. Both failures are elevon-BAND: narrow band (0.70–0.85) = 4.34%.
  Random sampling CANNOT reach a 19-D corner (0.2^19 ≈ 5e-14) — extremes must be
  BUILT. `build_pygeo_sections_from_config(sample=...)` accepts a constructed design.
  Honest number: nchordwise=24 gives CL_δe **≤1.8%** across the hinge range (not the
  1.1% quoted at hinge 0.75 alone). 32 chordwise would give 0.76% but is 6144
  vortices — over AVL's limit. So 1.8% is the ceiling at this grid.
- **Adaptive section placement (DECISION-0011): principal result NEGATIVE.** Pure
  de Boor equidistribution was WORSE than uniform on all 6 designs (up to 10×),
  while succeeding at its objective — it starved featureless regions, max gap 4.4×
  uniform. Gradation control (uniform-mixing floor 0.15→**0.50**, a MEASURED
  default) recovers it: 2.78× on a narrow band, neutral on benign, 0.73× on
  max_gradient. So it is **GATED, not universal**: adapt only if
  ramp_fraction(uniform) > 0.15. The metric's `concentration()` score predicts
  difficulty in the WRONG DIRECTION (r=-0.813) — do not use it.
- **BUG CLASS TO WATCH: two pipelines, one override.** The 3 elevon DVs were
  sampled but never reached AVL — `services.generate_geometry_case` applied the
  sampled-elevon override, `build_pygeo_sections_from_config` (which reimplements
  the pipeline for the AERO path) did not. Every aero run before 2026-07-25 flew
  elevon 0.60–0.95 at hinge 0.75. Invisible to every check: geometry built fine,
  both solvers saw the same elevon so they still agreed. Guarded by
  `tests/aero/test_elevon_dvs_reach_avl.py`. **Whenever a second pipeline
  reimplements a first, diff the override steps.**

## Project state (2026-07-24)

- **pyGeo backend committed** and decoupled from AeroSandbox (geometry import graph
  is asb-free; regression-guarded).
- **Native pyGeo→AVL+viscous chain** (no asb.Airplane): `native_avl.py` +
  `pygeo_avl_adapter.run_pygeo_native_avl_case` + `NeuralFoilCoordinateSource`.
  CLI `aeris aero pygeo-native`; GUI Aero page tab "④ pyGeo native". Matches the
  asb-serialized numbers to 0.1–0.4%.
- **Elevon does pitch + roll:** native AVL emits `<name>_sym` (d1, δe pitch) +
  `<name>_diff` (d2, δa roll); result reports Cm/Cl_roll/Cn/CY. `--control-input-deg`
  (δe) + `--diff-input-deg` (δa). Verified δe→pitch, δa→roll.
- **DoE design space** = `bwb.yaml` ranges (small BWB ISR UAV, full span 1.5–2.5 m,
  AR 2.6–6.2). **20 design variables** = 10 planform + 7 section + 3 elevon geometry
  (start/end/hinge via `elevon_bounds`, so the DoE varies the elevon for the later
  controllability optimization). Root dihedral enforced 0.
- **pyGeo vs ASB comparison** done (`studies/pygeo_vs_aerosandbox_geometry.md`):
  50/50 build both backends; metrics agree <1.3%. Interactive side-by-side 3D viewer
  exists.
- Generator id renamed `bwb_segmented_v1` → **`bwb_segmented`** (config-facing;
  package path unchanged).
- **Geometry creation is opt-in + backend-selectable.** `aeris geometry generate`
  flags: `--backend aerosandbox|pygeo|both`, `--exports iges,tecplot,sections,npz,
  step,stl,obj,vtk` (default NONE; CAD-family auto-enables physical CAD),
  `--physical-cad`, `--save-metrics` (→ `geometry_metrics.json` with span/area/AR/
  MAC/volume/wetted + taper/root/tip, attributed to the backend(s) that built),
  `--seed`. Nothing (CAD/VTK/STEP/plots) written unless requested. GUI geometry page
  "① Create geometry" has two backend tabs (AeroSandbox | pyGeo), pyGeo tab exposes
  the export checkboxes + physical-CAD + save-metrics.

## Technical gotchas (hard-won)

- **`planform_bounds.b_total_m` is the SEMI-span** (full span = 2×). Config comments
  it now.
- **Integrated-metric comparisons MUST extract pyGeo over the FULL span** (margin
  1e-4). A [0.02, 0.98] margin understates span ~4% and biases every integral.
- **NeuralFoil hard-depends on aerosandbox** (imports it at load) — zero-aerosandbox
  viscous is impossible while using NeuralFoil; the target is only "no asb.Airplane".
- **AVL `.avl` airfoil files must be ≤ IBX (~360 pts)** — native writer downsamples
  (cst_points=80 → 159-pt loop); AeroSandbox uses ~99. This 80-vs-181-point camber
  difference is the whole residual ~0.5% CL gap between the native and ASB paths.
- **The ASB reference path CANNOT do roll.** AeroSandbox's AVL exporter collapses
  every control surface into ONE variable `all_deflections` (SgnDup +1); AVL
  reports "1 Control variables", so the `d2` keystroke hits nothing and δa is
  silently ignored (measured Cl_roll = the sideslip term alone). Its elevon also
  over-extends to the tip. Only the NATIVE path models differential elevon —
  which is what the 3 elevon DVs exist to optimise. Don't trust ASB-path lateral
  numbers.
- **AVL interpolates control gain linearly between sections** — a control band
  edge exists only where a SECTION declares the control. Tag both boundary
  sections, and snap sections onto the band edges, or the elevon extent quantises
  to the section grid (staircase response vs the elevon DVs).
- **No CG exists yet** → AVL Xref=(0,0,0) is the geometry origin, not the CG, so
  `static_margin` is deliberately NOT reported (only `x_np_over_c_ref`). Pass
  `moment_reference_m=` + `moment_reference_is_cg=True` once a mass model exists.
- **`section_bounds.airfoil_name`** is the fallback airfoil (overridden per station
  by `station_airfoils`); kept = root airfoil to avoid confusion.
- **Generator-id rename gotcha:** renaming GENERATOR_ID to `bwb_segmented` broke
  code that hardcoded `generator_id != "bwb_segmented_v1"` (neutral + deflected CAD
  export). Fixed to accept `("bwb_segmented","bwb_segmented_v1")`. If more id-gated
  code surfaces, apply the same. Package import path stays `bwb_segmented_v1`.
- **Split-elevon physical CAD is DEFERRED (broken at small scale).** Both the
  neutral `--physical-cad` and the deflected `export-deflected-cad` produce INVALID
  OCC solids for the rescaled small BWB — `validity_ok = all bodies shape.isValid()`
  is False systematically (all seeds), and the deflected loft fails 2-3/8 bodies
  (`StdFail_NotDone`). NOT the airfoils (clean), NOT flaky, NOT the split-epsilon.
  Root cause: thin split-elevon bodies at small scale degenerate for OCC; the
  standalone "worked" at the OLD larger scale. Real fix = denser elevon sections +
  shape healing (each CAD build is >2 min — slow to iterate). Secondary path;
  control authority is covered by native AVL. GUI: CAD removed from the Create-
  geometry tab, lives only in "⑤ CAD export".
- **Geometry runs are LEAN by default:** write-only inspection CSVs (control_points/
  planform_sections/section_3d + pyGeo authored/extracted/cst) are gated behind
  `geometry.outputs.save_detail_csv` / `--save-detail` (off). Empty `sections/` dir
  only created when section DATs are written. GUI Visualize tab embeds the pyGeo
  interactive 3-D HTML in-page (streamlit.components.v1.html).

## Key references

- Config: `configs/geometry/bwb.yaml` (the one config).
- Backend: `src/aeris/generators/bwb_segmented_v1/` (pygeo_*.py, PYGEO_BACKEND.md).
- Native AVL: `src/aeris/aero/solvers/native_avl.py`; adapter
  `pygeo_avl_adapter.py`; polar `src/aeris/airfoil/neuralfoil_coordinate_source.py`.
- Comparison tooling: `standalone/pygeo_asb_comparison/`.
- Evidence: `configs/geometry/{pygeo_avl_evidence,pygeo_validation_evidence,pygeo_asb_comparison_evidence}/`.
- Parallel work: Codex owns `standalone/pygeo_surface_mesh_study/` — leave it alone.
